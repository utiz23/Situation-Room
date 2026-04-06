"""
Satellite TLE ingest worker — fetches orbital element sets hourly.

Primary source:  CelesTrak GP endpoint (FORMAT=TLE, classic 3-line text)
Fallback source: tle.ivanstanojevic.me JSON API (paginated, used when CelesTrak
                 GROUP queries are blocked by CDN rate-limiting or IP policy)

What is a TLE?
  A Two-Line Element set (TLE) is a standard format for describing a satellite's
  orbit. Two lines of numbers encode the orbit shape, inclination, and epoch.
  Given a TLE, the frontend computes satellite positions client-side using the
  satellite.js library — the server only stores and serves the raw TLE strings.

Fetch schedule:
  - On success: sleep until the top of the next UTC hour.
  - On failure (all sources exhausted): retry after RETRY_AFTER_FAILURE_S (5 min).

CelesTrak rate limits:
  Max 1 GROUP download per update cycle (~2 hours). Fetching hourly is safe;
  roughly every other request will get a 304 Not Modified, which costs nothing.

Fallback API (tle.ivanstanojevic.me):
  Free public TLE mirror; updated continuously. Max page size 100; we paginate
  up to FALLBACK_MAX_PAGES pages per fetch. Automatically used only when
  CelesTrak returns 403.

Data contract for satellite_tles table:
  norad_cat_id  INTEGER PRIMARY KEY
  name          TEXT
  tle_line1     TEXT      (starts with "1 ")
  tle_line2     TEXT      (starts with "2 ")
  constellation TEXT      (the GROUP/search term used)
  fetched_at    TIMESTAMPTZ
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

# ---------------------------------------------------------------------------
# Primary source: CelesTrak
# ---------------------------------------------------------------------------

CELESTRAK_URL = "https://celestrak.org/NORAD/ELEMENTS/gp.php?GROUP={group}&FORMAT=TLE"

_HEADERS = {
    "User-Agent": "SituationRoom/1.0 (github.com/utiz23/Situation-Room)",
    "Accept": "text/plain",
}

# ---------------------------------------------------------------------------
# Fallback source: tle.ivanstanojevic.me
# ---------------------------------------------------------------------------

FALLBACK_URL = (
    "https://tle.ivanstanojevic.me/api/tle/"
    "?search={group}&page-size=100&page={page}"
)

# Safety cap: 150 pages × 100 records = up to 15,000 satellites per fetch.
# Covers Starlink (~11,500) and any other constellation.
FALLBACK_MAX_PAGES = 150

# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

# On any failure (network error, all sources exhausted, 0 rows parsed), retry
# after this many seconds rather than waiting until the next full hour.
RETRY_AFTER_FAILURE_S = 300  # 5 minutes

# Sentinel returned by _fetch_celestrak when the server replies 304 Not Modified.
# Distinct from None (failure) and a string (new TLE text).
_NOT_MODIFIED = object()

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

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

_BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# CelesTrak fetch + parse
# ---------------------------------------------------------------------------

async def _fetch_celestrak(
    session: aiohttp.ClientSession,
    group: str,
    last_modified: Optional[str],
) -> tuple[object, Optional[str]]:
    """
    Fetch TLE text from CelesTrak for the given constellation group.

    Returns (result, new_last_modified) where result is:
      _NOT_MODIFIED — server replied 304 (data unchanged; treat as success)
      None          — request failed (403, 5xx, network error; treat as failure)
      str           — new TLE text; proceed to parse and upsert
    """
    url = CELESTRAK_URL.format(group=group)
    headers = dict(_HEADERS)
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    try:
        async with session.get(
            url, headers=headers, timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            if resp.status == 304:
                log.info(
                    "Satellites [%s]: CelesTrak 304 Not Modified — data current",
                    group,
                )
                return _NOT_MODIFIED, last_modified

            if resp.status == 403:
                log.warning(
                    "Satellites [%s]: CelesTrak HTTP 403 — GROUP endpoint blocked "
                    "(IP rate-limit or CDN policy). Trying fallback source.",
                    group,
                )
                return None, last_modified

            if resp.status != 200:
                log.warning(
                    "Satellites [%s]: CelesTrak HTTP %d — trying fallback source.",
                    group,
                    resp.status,
                )
                return None, last_modified

            new_last_modified = resp.headers.get("Last-Modified", last_modified)
            text = await resp.text()
            return text, new_last_modified

    except aiohttp.ClientError as exc:
        log.warning(
            "Satellites [%s]: CelesTrak request failed: %s — trying fallback source.",
            group,
            exc,
        )
        return None, last_modified


def _looks_like_tle(text: str) -> bool:
    """True if the response contains at least one TLE line 1 (starts with '1 ')."""
    return any(ln.strip().startswith("1 ") for ln in text.splitlines())


def _parse_tle_text(text: str, group: str) -> list[tuple]:
    """
    Parse a CelesTrak TLE plain-text response into DB tuples.

    Format: 3 lines per satellite (name, line1, line2), no blank lines.
    Returns [] if the response doesn't look like TLE data (logs body snippet).
    """
    if not _looks_like_tle(text):
        snippet = text[:300].replace("\n", "\\n")
        log.warning(
            "Satellites [%s]: CelesTrak response is not TLE data — "
            "first 300 chars: %s",
            group,
            snippet,
        )
        return []

    now = datetime.now(timezone.utc)
    rows: list[tuple] = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    i = 0
    while i + 2 < len(lines):
        name  = lines[i]
        line1 = lines[i + 1]
        line2 = lines[i + 2]

        if not (line1.startswith("1 ") and line2.startswith("2 ")):
            i += 1  # resync on unexpected layout
            continue

        try:
            norad_id = int(line1[2:7].strip())
            rows.append((norad_id, name, line1, line2, group, now))
        except ValueError:
            pass

        i += 3

    return rows


# ---------------------------------------------------------------------------
# Fallback fetch + parse (tle.ivanstanojevic.me)
# ---------------------------------------------------------------------------

async def _fetch_fallback(
    session: aiohttp.ClientSession,
    group: str,
) -> list[tuple]:
    """
    Paginate through tle.ivanstanojevic.me to collect TLEs for the given group.

    Field mapping:
      satelliteId → norad_cat_id (int)
      name        → name
      line1       → tle_line1
      line2       → tle_line2

    Paginates up to FALLBACK_MAX_PAGES pages (max 100 records each).
    Returns an empty list on complete failure.
    """
    now = datetime.now(timezone.utc)
    rows: list[tuple] = []
    page = 1
    consecutive_errors = 0

    log.info("Satellites [%s]: fetching from fallback API (paginated)…", group)

    while page <= FALLBACK_MAX_PAGES:
        url = FALLBACK_URL.format(group=group, page=page)
        try:
            async with session.get(
                url,
                headers={"User-Agent": _HEADERS["User-Agent"]},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    log.warning(
                        "Satellites [%s]: fallback API HTTP %d on page %d — stopping pagination",
                        group,
                        resp.status,
                        page,
                    )
                    break

                data = await resp.json(content_type=None)
                members = data.get("member", [])

                for rec in members:
                    try:
                        norad_id = int(rec["satelliteId"])
                        name     = rec["name"].strip()
                        line1    = rec["line1"].strip()
                        line2    = rec["line2"].strip()
                        if name and line1.startswith("1 ") and line2.startswith("2 "):
                            rows.append((norad_id, name, line1, line2, group, now))
                    except (KeyError, ValueError, TypeError):
                        continue

                consecutive_errors = 0

                if len(members) < 100:
                    # Last page — no more data
                    break

                page += 1
                # Be polite: brief pause between pages
                await asyncio.sleep(0.05)

        except aiohttp.ClientError as exc:
            consecutive_errors += 1
            log.warning(
                "Satellites [%s]: fallback API error on page %d: %s",
                group,
                page,
                exc,
            )
            if consecutive_errors >= 3:
                log.warning(
                    "Satellites [%s]: 3 consecutive fallback errors — aborting",
                    group,
                )
                break
            await asyncio.sleep(2)

    log.info(
        "Satellites [%s]: fallback API yielded %d records across %d pages",
        group,
        len(rows),
        page,
    )
    return rows


# ---------------------------------------------------------------------------
# DB upsert
# ---------------------------------------------------------------------------

async def _upsert(pool: asyncpg.Pool, rows: list[tuple]) -> int:
    async with pool.acquire() as conn:
        for i in range(0, len(rows), _BATCH_SIZE):
            await conn.executemany(_UPSERT_SQL, rows[i : i + _BATCH_SIZE])
    return len(rows)


# ---------------------------------------------------------------------------
# Schedule helpers
# ---------------------------------------------------------------------------

def _seconds_until_next_hour() -> float:
    now = datetime.now(timezone.utc)
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return (next_hour - now).total_seconds()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def run(inserter) -> None:  # type: ignore[type-arg]
    """
    Satellite TLE main loop. Fetches on startup, then once per UTC hour.

    Flow:
      1. Try CelesTrak (primary).
         - 304  → data current, sleep to next hour.
         - 200  → parse TLE text, upsert, sleep to next hour.
         - 403/other → try fallback API.
      2. Fallback: tle.ivanstanojevic.me (paginated JSON).
         - Success (rows > 0) → upsert, sleep to next hour.
         - Failure (0 rows)   → sleep RETRY_AFTER_FAILURE_S, retry.

    SATELLITE_CONSTELLATION env var selects the CelesTrak group / search term.
    Defaults to "starlink". Other values: "iridium-next", "active", "stations",
    "gps-ops", "galileo", "oneweb", etc.
    """
    group = os.environ.get("SATELLITE_CONSTELLATION", "starlink")
    pool  = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)

    last_modified: Optional[str] = None

    async with aiohttp.ClientSession() as session:
        while True:
            log.info("Satellites [%s]: fetching TLEs…", group)
            success = False

            try:
                # --- Primary: CelesTrak ---
                result, last_modified = await _fetch_celestrak(
                    session, group, last_modified
                )

                if result is _NOT_MODIFIED:
                    success = True

                elif result is None:
                    # CelesTrak failed — try fallback
                    rows = await _fetch_fallback(session, group)
                    if rows:
                        submitted = await _upsert(pool, rows)
                        log.info(
                            "Satellites [%s]: upserted %d records via fallback API",
                            group,
                            submitted,
                        )
                        success = True
                    else:
                        log.warning(
                            "Satellites [%s]: fallback API also returned 0 rows — "
                            "will retry in %ds",
                            group,
                            RETRY_AFTER_FAILURE_S,
                        )

                else:
                    # CelesTrak returned TLE text
                    rows = _parse_tle_text(result, group)
                    if rows:
                        submitted = await _upsert(pool, rows)
                        log.info(
                            "Satellites [%s]: upserted %d records via CelesTrak",
                            group,
                            submitted,
                        )
                        success = True
                    else:
                        log.warning(
                            "Satellites [%s]: CelesTrak response parsed 0 rows — "
                            "will retry in %ds",
                            group,
                            RETRY_AFTER_FAILURE_S,
                        )

            except Exception:
                log.exception("Satellites [%s]: unexpected error during fetch", group)

            if success:
                delay = _seconds_until_next_hour()
                log.info(
                    "Satellites [%s]: next fetch in %.0f s (top of next UTC hour)",
                    group,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                log.info(
                    "Satellites [%s]: retrying in %ds after failure",
                    group,
                    RETRY_AFTER_FAILURE_S,
                )
                await asyncio.sleep(RETRY_AFTER_FAILURE_S)
