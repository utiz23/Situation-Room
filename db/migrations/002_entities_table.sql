-- Migration 002: Create the entity_positions table (Category A — tracked point entities)
--
-- This table stores every position update we receive for aircraft and ships.
-- It becomes a TimescaleDB "hypertable" — automatically partitioned by time,
-- which makes time-range queries (e.g., "last 2 minutes") extremely fast.
--
-- Think of it like a spreadsheet where each row is:
--   "At [time], entity [id] was at [lat/lon] moving at [speed] degrees [heading]"

CREATE TABLE IF NOT EXISTS entity_positions (
    time            TIMESTAMPTZ     NOT NULL,               -- when this position was recorded (UTC)
    entity_id       TEXT            NOT NULL,               -- e.g. "adsb:abc123" or "ais:987654321"
    source          TEXT            NOT NULL,               -- "adsb" or "ais"
    entity_type     TEXT            NOT NULL,               -- "aircraft" or "ship"
    position        GEOGRAPHY(POINT, 4326) NOT NULL,        -- lat/lon stored as a geography point
    altitude_m      DOUBLE PRECISION,                       -- altitude in meters (aircraft only)
    heading_deg     DOUBLE PRECISION,                       -- direction of travel in degrees (0–360)
    speed_knots     DOUBLE PRECISION,                       -- speed in nautical miles per hour
    callsign        TEXT,                                   -- flight number or vessel name
    metadata        JSONB                                   -- extra source-specific data (MMSI, ICAO24, etc.)
);

-- Convert to a TimescaleDB hypertable, partitioned by the "time" column.
-- This is what makes time-range queries fast on millions of rows.
SELECT create_hypertable('entity_positions', 'time', if_not_exists => TRUE);

-- Index for fast per-entity history lookups (e.g., "last position of aircraft X")
CREATE INDEX IF NOT EXISTS idx_entity_positions_entity_time
    ON entity_positions (entity_id, time DESC);

-- Spatial index: speeds up geography-based queries (e.g., "all ships near this port")
CREATE INDEX IF NOT EXISTS idx_entity_positions_geo
    ON entity_positions USING GIST (position);

-- Enable TimescaleDB compression on this hypertable.
-- This must be done BEFORE calling add_compression_policy.
-- compress_segmentby groups all rows for the same entity together in storage.
-- compress_orderby ensures recent rows are at the front of each compressed chunk.
ALTER TABLE entity_positions SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'entity_id',
    timescaledb.compress_orderby = 'time DESC'
);

-- Automatically compress chunks of data older than 1 hour to save disk space.
-- Compressed data can still be queried — it just takes slightly longer.
SELECT add_compression_policy('entity_positions', INTERVAL '1 hour', if_not_exists => TRUE);
