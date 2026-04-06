-- Migration 003: Create the events table (Category B — user-contributed events)
--
-- Events are manually pinned incidents: strikes, explosions, military movements, etc.
-- Unlike entity_positions (which gets millions of rows from automated feeds),
-- events are created by a human via the admin interface.
--
-- Each event has a location, a type, a title, and optional details.

CREATE TABLE IF NOT EXISTS events (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),  -- unique ID, auto-generated
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),                  -- when it was added to the system
    event_time      TIMESTAMPTZ     NOT NULL,                                -- when the real-world event happened
    position        GEOGRAPHY(POINT, 4326) NOT NULL,                         -- where it happened (lat/lon)
    event_type      TEXT            NOT NULL,                                -- "strike" | "explosion" | "military_movement" | "protest" | "other"
    title           TEXT            NOT NULL,                                -- short description, e.g. "Missile strike on fuel depot"
    description     TEXT,                                                    -- longer details (optional)
    source_url      TEXT,                                                    -- link to a news article or source (optional)
    verified        BOOLEAN         NOT NULL DEFAULT FALSE,                  -- has an admin confirmed this event?
    contributor     TEXT                                                     -- who submitted it (optional, for attribution)
);

-- Spatial index: allows fast "find all events in this map viewport" queries
CREATE INDEX IF NOT EXISTS idx_events_position
    ON events USING GIST (position);

-- Time index: allows fast "most recent events" queries
CREATE INDEX IF NOT EXISTS idx_events_event_time
    ON events (event_time DESC);
