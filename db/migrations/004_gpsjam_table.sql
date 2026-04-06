-- Migration 004: Create the gpsjam_daily table (Category B — GPS jamming hex grid)
--
-- GPSJam.org publishes a daily file showing hexagonal grid cells where GPS
-- navigation accuracy was degraded (based on reports from aircraft ADS-B data).
--
-- H3 is a hexagonal grid system developed by Uber that divides the entire Earth
-- into hexagons at various resolutions. Each hexagon has a unique string ID.
-- Deck.gl's H3HexagonLayer can render these directly on the map.
--
-- We store one row per hex cell per day.

CREATE TABLE IF NOT EXISTS gpsjam_daily (
    id                  SERIAL          PRIMARY KEY,
    date                DATE            NOT NULL,       -- which day this reading is for
    h3_index            TEXT            NOT NULL,       -- the H3 hexagon ID (e.g. "8928308280fffff")
    interference_pct    FLOAT           NOT NULL,       -- 0.0–100.0: % of flights reporting GPS issues in this hex
    UNIQUE (date, h3_index)                             -- prevent duplicate entries for the same hex on the same day
);

-- Index for fast "get today's jamming data" queries
CREATE INDEX IF NOT EXISTS idx_gpsjam_date
    ON gpsjam_daily (date DESC);
