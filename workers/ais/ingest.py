"""
AIS ingest worker — persistent WebSocket connection to AISStream.io.

Unlike ADS-B (which polls every 15 s), AIS is event-driven: the server pushes
a message every time a ship broadcasts a new position. Ships transmit every
2–10 seconds when underway; moored/anchored ships transmit much less often.

Because AISStream pushes only when something changes, we forward every message
we receive — there is no delta-diff needed.

There is no "remove" signal in AIS — a ship that stops transmitting simply goes
quiet. The frontend client-side TTL (10 minutes) handles cleanup.

AIS bounding box filtering:
  The AIS_BBOX env var sets the geographic region to subscribe to.
  Reducing the region drastically reduces message volume:
    North Atlantic + Europe: a few thousand ships
    Global:                  potentially tens of thousands

Connection strategy:
  - On disconnect, reconnect with exponential backoff (1 s → 2 s → 4 s … 30 s max)
  - We never give up — ships should always be visible as long as the stack is running
"""

import asyncio
import json
import logging
import os
from typing import Optional

import aiohttp

from common.db import BatchInserter
from common.redis_client import RedisPublisher
from ais.normalize import normalize


log = logging.getLogger(__name__)

AISSTREAM_URL  = "wss://stream.aisstream.io/v0/stream"
REDIS_CHANNEL  = "channel:ais"
MAX_RETRY_DELAY = 30  # seconds


def _parse_bbox(bbox_str: str) -> list[list[list[float]]]:
    """
    Parse "lamin,lomin,lamax,lomax" into AISStream's nested bbox format:
      [[[lat_min, lon_min], [lat_max, lon_max]]]
    """
    parts = [float(p.strip()) for p in bbox_str.split(",")]
    if len(parts) != 4:
        raise ValueError(
            f"AIS_BBOX must be 'lamin,lomin,lamax,lomax', got: {bbox_str!r}"
        )
    lamin, lomin, lamax, lomax = parts
    return [[[lamin, lomin], [lamax, lomax]]]


async def _run_once(
    session: aiohttp.ClientSession,
    api_key: str,
    bbox: list,
    publisher: RedisPublisher,
    inserter: BatchInserter,
) -> None:
    """
    Open one WebSocket session to AISStream, subscribe, and process messages
    until the connection closes or errors. Raises on connection failure so
    the caller can implement retry logic.
    """
    subscribe_msg = {
        "APIKey":           api_key,
        "BoundingBoxes":    bbox,
        "FilterMessageTypes": ["PositionReport"],
    }

    async with session.ws_connect(
        AISSTREAM_URL,
        heartbeat=30,   # send a ping every 30 s to keep the connection alive
    ) as ws:
        await ws.send_json(subscribe_msg)
        log.info("AIS: WebSocket connected and subscribed")

        async for msg in ws:
            if msg.type in (aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY):
                # AISStream sends binary frames (UTF-8 JSON) in practice,
                # despite the WebSocket spec suggesting text for JSON payloads.
                # Handle both so the worker isn't broken by either frame type.
                raw = msg.data if isinstance(msg.data, str) else msg.data.decode("utf-8")
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    log.warning("AIS: malformed JSON message — skipping")
                    continue

                entity = normalize(data)
                if entity is None:
                    continue  # non-position message or missing fields

                await publisher.publish_update(REDIS_CHANNEL, entity)
                inserter.enqueue(entity)

            elif msg.type == aiohttp.WSMsgType.ERROR:
                log.warning("AIS: WebSocket error — %s", ws.exception())
                return

            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING):
                log.info("AIS: WebSocket closed by server")
                return


async def run(publisher: RedisPublisher, inserter: BatchInserter) -> None:
    """
    AIS main loop. Connects to AISStream, processes messages, and reconnects
    automatically on disconnect. Runs forever until the process is killed.

    Call this from scheduler.py as an asyncio task.
    """
    api_key = os.environ.get("AISSTREAM_API_KEY") or ""
    if not api_key:
        log.warning(
            "AIS: AISSTREAM_API_KEY is not set — worker will not start. "
            "Get a free key at https://aisstream.io/"
        )
        return

    bbox_str = os.environ.get("AIS_BBOX", "20,-80,75,60")
    bbox     = _parse_bbox(bbox_str)
    log.info("AIS worker starting — bbox=%s", bbox_str)

    retries = 0
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await _run_once(session, api_key, bbox, publisher, inserter)
                # Clean disconnect — reset backoff
                retries = 0
            except Exception as exc:
                log.warning("AIS: connection failed: %s", exc)

            delay = min(2 ** retries, MAX_RETRY_DELAY)
            retries += 1
            log.info("AIS: reconnecting in %d s (attempt %d)", delay, retries)
            await asyncio.sleep(delay)
