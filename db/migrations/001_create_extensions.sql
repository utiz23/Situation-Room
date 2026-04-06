-- Migration 001: Enable required PostgreSQL extensions
--
-- Extensions are like plugins that add extra features to the database.
-- We need three:
--   timescaledb — adds time-series superpowers (fast queries over time ranges)
--   postgis      — adds geography support (lat/lon, distances, spatial queries)
--   uuid-ossp    — adds the ability to generate unique IDs for events

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
