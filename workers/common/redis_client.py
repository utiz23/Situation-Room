"""
Redis publisher helper used by all workers.

Redis acts as a message relay (called a "pub/sub broker"):
  - Workers PUBLISH messages to named channels (e.g. "channel:adsb")
  - The Go API server SUBSCRIBES to those channels and forwards
    each message to all connected browser clients via WebSocket

This module wraps the redis-py async client so workers can publish
entity updates and remove events with a single function call.
"""

import json
import os
from typing import Any

import redis.asyncio as aioredis

from common.schema import NormalizedEntity


REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


class RedisPublisher:
    """
    Async Redis publisher. Use as an async context manager:

        async with RedisPublisher() as pub:
            await pub.publish_update("channel:adsb", entity)
            await pub.publish_remove("channel:adsb", "adsb:abc123")
    """

    def __init__(self) -> None:
        self._client: aioredis.Redis | None = None

    async def __aenter__(self) -> "RedisPublisher":
        self._client = await aioredis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()

    async def publish_update(self, channel: str, entity: NormalizedEntity) -> None:
        """
        Publish a position update for one entity.

        The Go hub receives this, checks each connected client's viewport,
        and forwards it only to clients whose map view includes this position.
        """
        message = json.dumps(
            {
                "type": "update",
                "entity": entity.model_dump(mode="json"),
            }
        )
        await self._client.publish(channel, message)  # type: ignore[union-attr]

    async def publish_remove(self, channel: str, entity_id: str) -> None:
        """
        Publish a remove event — entity has disappeared from the feed.

        The frontend Zustand store removes it from the map immediately
        rather than waiting for the client-side TTL to expire.
        """
        message = json.dumps({"type": "remove", "id": entity_id})
        await self._client.publish(channel, message)  # type: ignore[union-attr]
