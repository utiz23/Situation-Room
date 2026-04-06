/**
 * Category B — static / derived layers fetched via REST on demand.
 *
 * Unlike Category A (entities.ts), these are not streamed. The frontend
 * requests them once (or when the layer is toggled on) and caches the result.
 *
 * Three layer types:
 *  - Event       — manually pinned incidents (strikes, explosions, etc.)
 *  - JammingHex  — GPS interference hexagons from GPSJam.org
 *  - TLERecord   — satellite orbital data from CelesTrak; positions are
 *                  computed client-side by the satellite-propagator Web Worker
 *
 * Field names here must exactly match the JSON the Go API sends.
 */

// ---------------------------------------------------------------------------
// Events  (GET /api/events)
// ---------------------------------------------------------------------------

/** Categories of real-world incidents that can be pinned on the map. */
export type EventType =
  | "strike"
  | "explosion"
  | "military_movement"
  | "protest"
  | "other";

/** A single admin-contributed map incident. */
export interface MapEvent {
  /** UUID assigned by the database */
  id: string;
  /** ISO 8601 — when this entry was added to the system */
  created_at: string;
  /** ISO 8601 — when the real-world incident occurred */
  event_time: string;
  lat: number;
  lon: number;
  event_type: EventType;
  /** Short headline, e.g. "Missile strike on fuel depot" */
  title: string;
  description?: string;
  source_url?: string;
  /** True if an admin has verified this event */
  verified: boolean;
  contributor?: string;
}

/**
 * Body sent to POST /api/events when an admin creates a new event.
 * Omits server-assigned fields (id, created_at, verified).
 */
export interface CreateEventPayload {
  event_time: string;
  lat: number;
  lon: number;
  event_type: EventType;
  title: string;
  description?: string;
  source_url?: string;
  contributor?: string;
}

// ---------------------------------------------------------------------------
// GPS Jamming  (GET /api/gpsjam/current)
// ---------------------------------------------------------------------------

/**
 * GPS interference data for one H3 hexagonal grid cell on one day.
 *
 * H3 is a geographic grid system (developed by Uber) that divides the Earth
 * into hexagons. Each hexagon has a unique string identifier. Deck.gl's
 * H3HexagonLayer can render them directly on the map.
 */
export interface JammingHex {
  /** H3 hexagon identifier, e.g. "8928308280fffff" */
  h3_index: string;
  /** 0.0–100.0: percentage of flights over this hex reporting GPS problems */
  interference_pct: number;
  /** "YYYY-MM-DD" */
  date: string;
}

// ---------------------------------------------------------------------------
// Satellite TLEs  (GET /api/satellites/tles)
// ---------------------------------------------------------------------------

/**
 * Two-Line Element set for a single satellite, fetched from CelesTrak.
 *
 * A TLE is a compact string format that encodes a satellite's orbit.
 * Given a TLE, the satellite.js library (running in a Web Worker) can
 * calculate exactly where the satellite will be at any moment in time —
 * without the server doing any work.
 */
export interface TLERecord {
  /** NORAD catalog number — the universal unique ID for every satellite */
  norad_cat_id: number;
  /** Human-readable name, e.g. "STARLINK-1234" */
  name: string;
  tle_line1: string;
  tle_line2: string;
  /** Constellation group: "starlink" | "iridium-next" | "active" | ... */
  constellation: string;
  /** ISO 8601 — when we last fetched this TLE from CelesTrak */
  fetched_at: string;
}
