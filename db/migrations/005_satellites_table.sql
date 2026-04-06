-- Migration 005: Create the satellite_tles table (Category B — satellite orbital data)
--
-- TLE stands for "Two-Line Element set" — it's a standardized format for
-- describing a satellite's orbit. Given a TLE, you can calculate where
-- the satellite will be at any point in time using physics.
--
-- We store TLEs from CelesTrak (a free, public source of satellite orbital data).
-- The frontend fetches these via REST and computes positions client-side
-- using a JavaScript library called satellite.js — the server never
-- has to calculate satellite positions itself.
--
-- TLEs look like this (two lines of numbers that describe the orbit):
--   ISS (ZARYA)
--   1 25544U 98067A   24001.50000000  .00006789  00000-0  12345-3 0  9991
--   2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.49815168433729

CREATE TABLE IF NOT EXISTS satellite_tles (
    norad_cat_id    INTEGER         PRIMARY KEY,        -- NORAD catalog number (unique ID for every satellite)
    name            TEXT            NOT NULL,           -- human-readable name, e.g. "STARLINK-1234"
    tle_line1       TEXT            NOT NULL,           -- first line of the TLE
    tle_line2       TEXT            NOT NULL,           -- second line of the TLE
    constellation   TEXT            NOT NULL,           -- group name: "starlink" | "iridium-next" | "active" etc.
    fetched_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()  -- when we last retrieved this TLE from CelesTrak
);

-- Index for filtering by constellation (e.g., "give me only Starlink satellites")
CREATE INDEX IF NOT EXISTS idx_satellite_tles_constellation
    ON satellite_tles (constellation);
