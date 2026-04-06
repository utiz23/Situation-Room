"""
ADS-B ingest worker — polls OpenSky Network every 15 seconds.

What this does, step by step:
  1. Every 15 seconds, request aircraft positions from OpenSky's REST API.
  2. OpenSky returns a JSON object with a "states" list — each item is one
     aircraft's current position (a 17-field state vector).
  3. Normalize each state vector into our NormalizedEntity schema.
  4. Compare against the previous poll:
       - Aircraft that moved more than 0.01° OR changed status → "update" to Redis
       - Aircraft in the previous poll that are gone now → "remove" to Redis
       - Unchanged aircraft → skip (no point broadcasting the same data)
  5. Enqueue updates for batch DB insert.

Authentication:
  OpenSky now requires OAuth2 client credentials (Bearer token).
  Set OPENSKY_CLIENT_ID + OPENSKY_CLIENT_SECRET in .env.
  Anonymous access still works but is heavily rate-limited (1 req/10 s, bbox capped).
"""

import asyncio
import logging
import os
import time
from typing import Optional

import aiohttp

from common.db import BatchInserter
from common.redis_client import RedisPublisher
from common.schema import NormalizedEntity
from adsb.normalize import normalize


log = logging.getLogger(__name__)

OPENSKY_URL       = "https://opensky-network.org/api/states/all"
OPENSKY_TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network"
    "/protocol/openid-connect/token"
)

POLL_INTERVAL      = 15    # seconds between each OpenSky request
REDIS_CHANNEL      = "channel:adsb"
MIN_POSITION_DELTA = 0.01  # degrees; 0.01° ≈ 1.1 km


# ---------------------------------------------------------------------------
# OAuth2 token management
# ---------------------------------------------------------------------------

class _TokenManager:
    """
    Fetches and caches an OAuth2 Bearer token for OpenSky's API.

    Tokens expire after ~300 s. We refresh proactively 30 s before expiry
    so we never make a request with an about-to-expire token.
    """

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id     = client_id
        self._client_secret = client_secret
        self._token: Optional[str] = None
        self._expires_at: float   = 0.0  # monotonic clock

    async def get_token(self, session: aiohttp.ClientSession) -> str:
        """Return a valid Bearer token, refreshing if needed."""
        if self._token and time.monotonic() < self._expires_at - 30:
            return self._token
        await self._refresh(session)
        return self._token  # type: ignore[return-value]

    async def _refresh(self, session: aiohttp.ClientSession) -> None:
        payload = {
            "grant_type":    "client_credentials",
            "client_id":     self._client_id,
            "client_secret": self._client_secret,
        }
        try:
            async with session.post(
                OPENSKY_TOKEN_URL,
                data=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(
                        f"Token fetch failed HTTP {resp.status}: {body[:200]}"
                    )
                body = await resp.json()
                self._token      = body["access_token"]
                expires_in       = int(body.get("expires_in", 300))
                self._expires_at = time.monotonic() + expires_in
                log.info("OpenSky: token refreshed (expires in %d s)", expires_in)
        except aiohttp.ClientError as exc:
            raise RuntimeError(f"Token fetch network error: {exc}") from exc


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _parse_bbox(bbox_str: str) -> dict[str, float]:
    """
    Parse the ADSB_BBOX env var ("lamin,lomin,lamax,lomax") into
    the four keyword arguments OpenSky's API expects.
    """
    parts = [float(p.strip()) for p in bbox_str.split(",")]
    if len(parts) != 4:
        raise ValueError(
            f"ADSB_BBOX must be 'lamin,lomin,lamax,lomax', got: {bbox_str!r}"
        )
    lamin, lomin, lamax, lomax = parts
    return {"lamin": lamin, "lomin": lomin, "lamax": lamax, "lomax": lomax}


async def _fetch_states(
    session: aiohttp.ClientSession,
    params: dict,
    token_manager: Optional[_TokenManager],
) -> Optional[dict]:
    """
    Make one HTTP GET to OpenSky. Returns the parsed JSON or None on error.
    """
    headers: dict[str, str] = {}
    if token_manager:
        try:
            token = await token_manager.get_token(session)
            headers["Authorization"] = f"Bearer {token}"
        except RuntimeError as exc:
            log.error("OpenSky: cannot get auth token — %s", exc)
            return None

    try:
        async with session.get(
            OPENSKY_URL,
            params=params,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 429:
                log.warning("OpenSky: rate limit (429) — skipping this poll")
                return None
            if resp.status == 401:
                log.warning("OpenSky: 401 Unauthorized — token may be invalid")
                return None
            if resp.status != 200:
                log.warning("OpenSky: unexpected HTTP %d", resp.status)
                return None
            return await resp.json()
    except asyncio.TimeoutError:
        log.warning("OpenSky: request timed out")
        return None
    except aiohttp.ClientError as exc:
        log.warning("OpenSky: request failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Main polling loop
# ---------------------------------------------------------------------------

async def run(publisher: RedisPublisher, inserter: BatchInserter) -> None:
    """
    Main ADS-B polling loop. Runs forever (until the process is killed).
    Call this from scheduler.py as an asyncio task.
    """
    bbox_str   = os.environ.get("ADSB_BBOX", "20,-80,75,60")
    bbox_params = _parse_bbox(bbox_str)

    client_id     = os.environ.get("OPENSKY_CLIENT_ID")  or None
    client_secret = os.environ.get("OPENSKY_CLIENT_SECRET") or None

    token_manager: Optional[_TokenManager] = None
    if client_id and client_secret:
        token_manager = _TokenManager(client_id, client_secret)
        log.info("OpenSky: OAuth2 client credentials configured (client_id=%r)", client_id)
    else:
        log.warning(
            "OpenSky: no OAuth2 credentials — using anonymous access "
            "(set OPENSKY_CLIENT_ID + OPENSKY_CLIENT_SECRET in .env for full access)"
        )

    log.info("ADS-B worker starting — bbox=%s, poll_interval=%ds", bbox_str, POLL_INTERVAL)

    # prev_state maps icao24 → (lat, lon, on_ground, callsign, squawk).
    # Only updated after a successful (non-error) API response.
    PrevState = tuple[float, float, bool, Optional[str], Optional[str]]
    prev_state: dict[str, PrevState] = {}

    async with aiohttp.ClientSession() as session:
        while True:
            data = await _fetch_states(session, bbox_params, token_manager)

            if data is None:
                # Network/auth error — don't update prev_state.
                await asyncio.sleep(POLL_INTERVAL)
                continue

            states: list[list] = data.get("states") or []
            log.debug("OpenSky returned %d state vectors", len(states))

            curr_state: dict[str, PrevState] = {}
            updated = 0
            skipped = 0

            for sv in states:
                entity: Optional[NormalizedEntity] = normalize(sv)
                if entity is None:
                    continue

                icao24: str       = sv[0]
                on_ground: bool   = sv[8]
                squawk: Optional[str] = sv[14]

                curr_state[icao24] = (entity.lat, entity.lon, on_ground, entity.callsign, squawk)

                prev = prev_state.get(icao24)
                if prev is not None:
                    prev_lat, prev_lon, prev_on_ground, prev_callsign, prev_squawk = prev
                    position_unchanged = (
                        abs(entity.lat - prev_lat) < MIN_POSITION_DELTA
                        and abs(entity.lon - prev_lon) < MIN_POSITION_DELTA
                    )
                    status_unchanged = (
                        on_ground   == prev_on_ground
                        and entity.callsign == prev_callsign
                        and squawk  == prev_squawk
                    )
                    if position_unchanged and status_unchanged:
                        skipped += 1
                        continue

                await publisher.publish_update(REDIS_CHANNEL, entity)
                inserter.enqueue(entity)
                updated += 1

            removed = 0
            for icao24 in prev_state:
                if icao24 not in curr_state:
                    await publisher.publish_remove(REDIS_CHANNEL, f"adsb:{icao24}")
                    removed += 1

            log.info(
                "ADS-B poll: %d aircraft — %d updated, %d unchanged, %d removed",
                len(curr_state), updated, skipped, removed,
            )

            prev_state = curr_state
            await asyncio.sleep(POLL_INTERVAL)
