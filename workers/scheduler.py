"""
Worker scheduler — the entry point for the workers Docker container.

This file starts all data-fetching workers in parallel using asyncio.
asyncio lets Python run multiple tasks "at the same time" without needing
multiple processes or threads — each task runs until it would have to wait
(for a network response, a timer, etc.), then yields control to the others.

Current workers:
  - ADS-B (aircraft): polls OpenSky every 15 seconds
  - AIS (ships): persistent WebSocket to AISStream
  - GPS Jamming: daily CSV fetch from GPSJam

Future workers added here (Step 9):
  - Satellites: hourly TLE fetch from CelesTrak
"""

import asyncio
import logging
import sys

from common.db import BatchInserter
from common.redis_client import RedisPublisher
import adsb.ingest as adsb_ingest
import ais.ingest as ais_ingest
import gpsjam.ingest as gpsjam_ingest


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)


async def main() -> None:
    log.info("SituationRoom workers starting…")

    # Both the DB inserter and Redis publisher are shared across all workers.
    # They handle their own connection pooling internally.
    inserter = BatchInserter()
    await inserter.start()

    async with RedisPublisher() as publisher:
        try:
            # asyncio.gather runs all coroutines concurrently.
            # If any raises an unexpected exception, gather re-raises it here.
            await asyncio.gather(
                adsb_ingest.run(publisher, inserter),
                ais_ingest.run(publisher, inserter),
                gpsjam_ingest.run(inserter),
                # satellite_ingest.run(inserter),         # Step 9
            )
        finally:
            await inserter.stop()

    log.info("Workers shut down cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
