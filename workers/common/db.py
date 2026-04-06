"""
Database writer for all workers.

Instead of inserting one row at a time (slow — each insert is a round-trip
to the database), this module collects entities arriving within a 1-second
window and inserts them all at once. This is called "batching" and is much
more efficient for high-volume feeds like ADS-B (hundreds of updates/second).

How it works:
  1. Workers call `batch_inserter.enqueue(entity)` — this adds to an asyncio Queue.
  2. A background coroutine (`_flush_loop`) wakes up every second, drains the
     queue, and executes a single bulk INSERT for everything that arrived.
  3. The asyncpg library handles the PostgreSQL connection pool (a "pool" is
     a set of pre-opened connections that are reused rather than reopened
     for every query — much faster).
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import asyncpg

from common.schema import NormalizedEntity


log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://situationroom:password@localhost:5432/situationroom",
)

# How often to flush the queue to the database (seconds)
FLUSH_INTERVAL = 1.0

# SQL for inserting one entity position row.
# ST_SetSRID(ST_MakePoint(lon, lat), 4326) converts a lon/lat pair into the
# PostGIS geography type that the entity_positions table expects.
# Note: ST_MakePoint takes (longitude, latitude) — X before Y, like a graph.
_INSERT_SQL = """
    INSERT INTO entity_positions
        (time, entity_id, source, entity_type, position,
         altitude_m, heading_deg, speed_knots, callsign, metadata)
    VALUES (
        $1, $2, $3, $4,
        ST_SetSRID(ST_MakePoint($5, $6), 4326)::geography,
        $7, $8, $9, $10, $11
    )
"""


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Register JSON codec so asyncpg auto-serialises Python dicts to JSONB."""
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


class BatchInserter:
    """
    Collects NormalizedEntity objects and bulk-inserts them every FLUSH_INTERVAL
    seconds. Create one instance per worker process and share it across tasks.

    Usage:
        inserter = BatchInserter()
        await inserter.start()         # opens DB pool + starts background flush loop
        inserter.enqueue(entity)       # non-blocking, thread-safe
        await inserter.stop()          # flushes remaining rows, closes pool
    """

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None
        self._queue: asyncio.Queue[NormalizedEntity] = asyncio.Queue()
        self._flush_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
            init=_init_connection,
        )
        self._flush_task = asyncio.create_task(self._flush_loop())
        log.info("BatchInserter started (flush every %.1fs)", FLUSH_INTERVAL)

    def enqueue(self, entity: NormalizedEntity) -> None:
        """Add an entity to the pending batch. Returns immediately."""
        self._queue.put_nowait(entity)

    async def stop(self) -> None:
        if self._flush_task:
            self._flush_task.cancel()
        await self._flush()  # drain any remaining rows
        if self._pool:
            await self._pool.close()

    async def _flush_loop(self) -> None:
        """Background task: sleep, then flush, repeat forever."""
        while True:
            await asyncio.sleep(FLUSH_INTERVAL)
            await self._flush()

    async def _flush(self) -> None:
        """Drain the queue and insert all pending rows in one round-trip."""
        if self._queue.empty():
            return

        rows: list[NormalizedEntity] = []
        while not self._queue.empty():
            rows.append(self._queue.get_nowait())

        records = [
            (
                e.timestamp,          # $1 time
                e.id,                 # $2 entity_id
                e.source,             # $3 source
                e.entity_type,        # $4 entity_type
                e.lon,                # $5 longitude  (ST_MakePoint takes X=lon first)
                e.lat,                # $6 latitude
                e.alt_m,              # $7 altitude_m
                e.heading_deg,        # $8 heading_deg
                e.speed_knots,        # $9 speed_knots
                e.callsign,           # $10 callsign
                e.metadata,           # $11 metadata (JSONB)
            )
            for e in rows
        ]

        # Retry up to 2 times on transient DB errors (e.g. brief connection loss).
        # On the second failure we give up and log the loss rather than
        # accumulating unbounded memory while the DB is down.
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                async with self._pool.acquire() as conn:  # type: ignore[union-attr]
                    await conn.executemany(_INSERT_SQL, records)
                log.debug("Flushed %d rows to entity_positions", len(records))
                return
            except Exception:
                if attempt < max_attempts:
                    log.warning(
                        "DB flush failed (attempt %d/%d) — retrying in 2s",
                        attempt,
                        max_attempts,
                    )
                    await asyncio.sleep(2)
                else:
                    log.exception(
                        "DB flush failed after %d attempts — %d rows dropped",
                        max_attempts,
                        len(records),
                    )
