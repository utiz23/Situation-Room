"""
Satellite TLE ingest worker — fetches orbital element sets from CelesTrak hourly.

What is a TLE?
  A Two-Line Element set (TLE) is a standard format for describing a satellite's
  orbit. Two lines of numbers encode the orbit shape, inclination, and epoch.
  Given a TLE, you can compute where the satellite will be at any time using
  physics (the SGP4 model). The frontend does this calculation client-side using
  the satellite.js library — the server only stores the raw TLE strings.

What this worker does:
  1. At startup, fetch the constellation group JSON from CelesTrak.
  2. Parse each OMM record into (norad_cat_id, name, tle_line1, tle_line2,
     constellation, fetched_at) and upsert into satellite_tles.
  3. Sleep until the top of the next UTC hour, then repeat.
  4. On subsequent fetches, send If-Modified-Since so the server can reply with
     304 Not Modified when the data hasn't changed, saving bandwidth.

CelesTrak rate limits:
  Max 1 download per update cycle per group. Updates happen roughly every 2 hours.
  We fetch once per hour; roughly every other fetch will get a 304 — that's fine.

Data URL:
  https://celestrak.org/NORAD/ELEMENTS/gp.php?GROUP={group}&FORMAT=json
  GROUP is controlled by the SATELLITE_CONSTELLATION env var (default: starlink).

OMM JSON record shape (fields we use):
  NORAD_CAT_ID  — integer, the universal satellite ID (primary key in our table)
  OBJECT_NAME   — human-readable name, e.g. "STARLINK-1234"
  TLE_LINE1     — first line of the Two-Line Element set
  TLE_LINE2     — second line of the Two-Line Element set
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiohttp
import asyncpg

from common.db import DATABASE_URL


log = logging.getLogger(__name__)

# CelesTrak GP (General Perturbations) OMM JSON endpoint.
# GROUP selects the satellite constellation; FORMAT=json returns OMM records.
CELESTRAK_URL = "https://celestrak.org/NORAD/ELEMENTS/gp.php?GROUP={group}&FORMAT=json"

_UPSERT_SQL = """
    INSERT INTO satellite_tles
        (norad_cat_id, name, tle_line1, tle_line2, constellation, fetched_at)
    VALUES ($1, $2, $3, $4, $5, $6)
    ON CONFLICT (norad_cat_id) DO UPDATE
        SET name          = EXCLUDED.name,
            tle_line1     = EXCLUDED.tle_line1,
            tle_line2     = EXCLUDED.tle_line2,
            constellation = EXCLUDED.constellation,
            fetched_at    = EXCLUDED.fetched_at
"""

# How many records to insert per executemany call
_BATCH_SIZE = 500


async def _fetch_tle_json(
    session: aiohttp.ClientSession,
    group: str,
    last_modified: Optional[str],
) -> tuple[Optional[list], Optional[str]]:
    """
    Fetch TLE OMM JSON from CelesTrak for the given constellation group.

    Sends If-Modified-Since when we have a previous Last-Modified value.
    Returns:
      (records, new_last_modified)
        records is None on 304 (data unchanged) or on error.
        new_last_modified is the value to use for the next request.
    """
    url = CELESTRAK_URL.format(group=group)
    headers = {}
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    try:
        async with session.get(
            url, headers=headers, timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            if resp.status == 304:
                log.info("Satellites [%s]: 304 Not Modified — TLEs unchanged, skipping upsert", group)
                return None, last_modified

            if resp.status != 200:
                log.warning("Satellites [%s]: unexpected HTTP %d", group, resp.status)
                return None, last_modified

            new_last_modified = resp.headers.get("Last-Modified", last_modified)
            # CelesTrak may return content-type text/plain, so disable content-type check
            records = await resp.json(content_type=None)
            log.debug("Satellites [%s]: received %d records", group, len(records))
            return records, new_last_modified

    except aiohttp.ClientError as exc:
        log.warning("Satellites [%s]: request failed: %s", group, exc)
        return None, last_modified


def _parse_omm_records(records: list, group: str) -> list[tuple]:
    """
    Parse CelesTrak OMM JSON records into DB tuples.

    Each record is a dict with at least these keys:
      NORAD_CAT_ID, OBJECT_NAME, TLE_LINE1, TLE_LINE2

    Records missing any required field, or with empty TLE lines, are skipped.
    Returns a list of (norad_cat_id, name, tle_line1, tle_line2, group, fetched_at).
    """
    now = datetime.now(timezone.utc)
    rows: list[tuple] = []

    for rec in records:
        try:
            norad_id = int(rec["NORAD_CAT_ID"])
            name     = rec["OBJECT_NAME"].strip()
            line1    = rec["TLE_LINE1"].strip()
            line2    = rec["TLE_LINE2"].strip()

            if not (name and line1 and line2):
                continue  # skip records with empty required fields

            rows.append((norad_id, name, line1, line2, group, now))

        except (KeyError, ValueError, TypeError):
            continue  # skip malformed records

    return rows


async def _upsert(pool: asyncpg.Pool, rows: list[tuple]) -> int:
    """
    Bulk-upsert satellite TLE records into satellite_tles.

    Uses ON CONFLICT (norad_cat_id) DO UPDATE so repeat runs update stale TLEs
    rather than inserting duplicates.
    Returns the number of rows submitted (not necessarily newly inserted).
    """
    async with pool.acquire() as conn:
        for i in range(0, len(rows), _BATCH_SIZE):
            batch = rows[i : i + _BATCH_SIZE]
            await conn.executemany(_UPSERT_SQL, batch)
    return len(rows)


def _seconds_until_next_hour() -> float:
    """How many seconds until the top of the next UTC hour."""
    now = datetime.now(timezone.utc)
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return (next_hour - now).total_seconds()


async def run(inserter) -> None:  # type: ignore[type-arg]
    """
    Satellite TLE main loop. Fetches on startup, then once per UTC hour.

    The inserter argument is accepted for API consistency but not used —
    satellite TLEs go directly to the DB, not via the batch inserter.

    SATELLITE_CONSTELLATION env var sets which CelesTrak group to fetch.
    Defaults to "starlink". Other valid values: "iridium-next", "active",
    "stations" (ISS etc.), "gps-ops", "galileo", etc.
    """
    group = os.environ.get("SATELLITE_CONSTELLATION", "starlink")
    pool  = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)

    last_modified: Optional[str] = None

    async with aiohttp.ClientSession() as session:
        while True:
            log.info("Satellites [%s]: fetching TLEs…", group)
            try:
                records, last_modified = await _fetch_tle_json(session, group, last_modified)

                if records is not None:
                    rows = _parse_omm_records(records, group)
                    if rows:
                        submitted = await _upsert(pool, rows)
                        log.info("Satellites [%s]: upserted %d TLE records", group, submitted)
                    else:
                        log.warning("Satellites [%s]: parsed 0 usable records from response", group)

            except Exception:
                log.exception("Satellites [%s]: unexpected error during fetch", group)

            delay = _seconds_until_next_hour()
            log.info(
                "Satellites [%s]: next fetch in %.0f s (top of next UTC hour)", group, delay
            )
            await asyncio.sleep(delay)
