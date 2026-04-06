"""
GPS Jamming ingest worker — fetches GPSJam.org daily data once per day.

What is GPS jamming?
  Military and other actors sometimes broadcast strong radio signals on GPS
  frequencies to prevent guided weapons or drones from navigating. GPSJam.org
  detects this by analysing ADS-B reports: aircraft whose ADS-B position and
  GPS accuracy suddenly degrade are flagged as likely experiencing jamming.

What this worker does:
  1. At startup, fetch today's (or the most recent available) CSV from GPSJam.
  2. Parse the CSV — each row is an H3 hexagon covering ~85 km², plus the
     fraction of aircraft over it that reported GPS issues.
  3. Upsert into the gpsjam_daily table (safe to re-run; UNIQUE on date+hex).
  4. Sleep until the next UTC midnight, then repeat.

GPSJam CSV format (columns may vary slightly between releases):
  h3          — H3 hexagon index string, e.g. "8928308280fffff"
  avg (or pct) — fraction 0.0–1.0 of aircraft reporting GPS issues
                 (we multiply by 100 to store as a percentage)

Data URL: https://gpsjam.org/data/{YYYY-MM-DD}.csv
Data is typically available for the previous UTC day by ~06:00 UTC.
"""

import asyncio
import csv
import io
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import aiohttp
import asyncpg

from common.db import DATABASE_URL


log = logging.getLogger(__name__)

GPSJAM_URL_TEMPLATE = "https://gpsjam.org/data/{date}-h3_4.csv"

_INSERT_SQL = """
    INSERT INTO gpsjam_daily (date, h3_index, interference_pct)
    VALUES ($1, $2, $3)
    ON CONFLICT (date, h3_index) DO NOTHING
"""

# How many hex rows to insert per executemany call
_BATCH_SIZE = 2000


async def _fetch_csv(session: aiohttp.ClientSession, date_str: str) -> Optional[str]:
    """Download the GPSJam CSV for the given date (YYYY-MM-DD). Returns raw text or None."""
    url = GPSJAM_URL_TEMPLATE.format(date=date_str)
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 404:
                log.debug("GPSJam: no data for %s (404)", date_str)
                return None
            if resp.status != 200:
                log.warning("GPSJam: unexpected HTTP %d for %s", resp.status, date_str)
                return None
            return await resp.text()
    except aiohttp.ClientError as exc:
        log.warning("GPSJam: request failed for %s: %s", date_str, exc)
        return None


def _parse_csv(raw: str, date_str: str) -> list[tuple]:
    """
    Parse the GPSJam H3-resolution-4 CSV into (date, h3_index, interference_pct) tuples.

    Verified column schema (from https://gpsjam.org/data/{date}-h3_4.csv):
      hex                   — H3 index string at resolution 4
      count_good_aircraft   — aircraft in this hex with normal GPS accuracy
      count_bad_aircraft    — aircraft reporting degraded GPS accuracy

    interference_pct = count_bad / (count_good + count_bad) * 100
    Rows where total == 0 are skipped (no aircraft observed, no signal either way).
    """
    reader = csv.DictReader(io.StringIO(raw))
    rows: list[tuple] = []

    expected = {"hex", "count_good_aircraft", "count_bad_aircraft"}
    actual   = {f.strip().lower() for f in (reader.fieldnames or [])}
    if not expected.issubset(actual):
        log.error(
            "GPSJam: unexpected CSV columns %s (expected %s)",
            reader.fieldnames,
            expected,
        )
        return rows

    for row in reader:
        try:
            h3_index = row["hex"].strip()
            good     = int(row["count_good_aircraft"])
            bad      = int(row["count_bad_aircraft"])
            total    = good + bad
            if not h3_index or total == 0:
                continue
            pct = bad / total * 100.0
            rows.append((date.fromisoformat(date_str), h3_index, pct))
        except (ValueError, KeyError):
            continue  # skip malformed rows

    return rows


async def _upsert(pool: asyncpg.Pool, rows: list[tuple]) -> int:
    """
    Bulk-upsert rows into gpsjam_daily. Returns the number of rows submitted.

    Note: executemany with ON CONFLICT DO NOTHING does not report how many rows
    were actually inserted vs skipped — the returned value is the submitted count.
    On repeat runs for the same date the table stays unchanged (idempotent).
    """
    async with pool.acquire() as conn:
        for i in range(0, len(rows), _BATCH_SIZE):
            batch = rows[i : i + _BATCH_SIZE]
            await conn.executemany(_INSERT_SQL, batch)
    return len(rows)


async def _fetch_and_store(
    session: aiohttp.ClientSession,
    pool: asyncpg.Pool,
) -> None:
    """
    Try today's data; if not yet published, fall back to yesterday's.
    GPSJam typically publishes with a 1-day lag.
    """
    today     = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)

    for attempt_date in (today, yesterday):
        date_str = attempt_date.isoformat()
        raw = await _fetch_csv(session, date_str)
        if raw is None:
            continue

        rows = _parse_csv(raw, date_str)
        if not rows:
            log.warning("GPSJam: CSV for %s parsed 0 rows — skipping", date_str)
            continue

        submitted = await _upsert(pool, rows)
        log.info(
            "GPSJam: upserted %d hex cells for %s (duplicates skipped by DB)",
            submitted, date_str,
        )
        return

    log.warning("GPSJam: no data available for %s or %s", today, yesterday)


def _seconds_until_next_utc_midnight() -> float:
    """How many seconds until 00:05 UTC tomorrow (5 min after midnight for data lag)."""
    now = datetime.now(timezone.utc)
    next_run = (now + timedelta(days=1)).replace(
        hour=0, minute=5, second=0, microsecond=0
    )
    return (next_run - now).total_seconds()


async def run(inserter) -> None:  # type: ignore[type-arg]
    """
    GPS Jamming main loop. Fetches data once at startup, then once per UTC day.
    The inserter argument is accepted for API consistency but not used
    (GPS jam data goes to DB directly, not via the batch inserter).
    """
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)

    async with aiohttp.ClientSession() as session:
        while True:
            log.info("GPSJam: fetching daily data…")
            try:
                await _fetch_and_store(session, pool)
            except Exception:
                log.exception("GPSJam: unexpected error during fetch")

            delay = _seconds_until_next_utc_midnight()
            log.info("GPSJam: next fetch in %.0f s (00:05 UTC tomorrow)", delay)
            await asyncio.sleep(delay)
