// Package schema defines the shared data structures used across the Go API.
//
// These are the Go equivalents of the Python Pydantic models in
// workers/common/schema.py and the TypeScript interfaces in
// frontend/src/types/.
//
// Two categories:
//   - Category A: NormalizedEntity — moving things streamed via WebSocket
//   - Category B: Event, JammingHex, TLERecord — static layers served via REST
//
// The JSON field names here must match what the frontend TypeScript types expect.
package schema

import (
	"time"

	"github.com/google/uuid"
)

// ---------------------------------------------------------------------------
// Category A — NormalizedEntity
// ---------------------------------------------------------------------------
// A moving object on the map (aircraft or ship), normalized from its source
// feed (OpenSky for ADS-B, AISStream for ships) into a common shape.
//
// Redis messages use this same struct, serialised as JSON, inside an envelope:
//
//	{ "type": "update", "entity": { ...NormalizedEntity fields... } }
//	{ "type": "remove", "id": "adsb:abc123" }

// NormalizedEntity is the canonical representation of a tracked moving entity.
type NormalizedEntity struct {
	// ID is "{source}:{identifier}", e.g. "adsb:abc123" or "ais:987654321"
	ID         string  `json:"id"`
	Source     string  `json:"source"`      // "adsb" | "ais"
	EntityType string  `json:"entity_type"` // "aircraft" | "ship"
	Lat        float64 `json:"lat"`
	Lon        float64 `json:"lon"`

	// Optional fields — pointer so they serialise as null when absent
	AltM       *float64 `json:"alt_m,omitempty"`
	HeadingDeg *float64 `json:"heading_deg,omitempty"`
	SpeedKnots *float64 `json:"speed_knots,omitempty"`
	Callsign   *string  `json:"callsign,omitempty"`

	// Metadata holds source-specific extras (ICAO24, MMSI, country, etc.)
	Metadata  map[string]any `json:"metadata"`
	Timestamp time.Time      `json:"timestamp"`
}

// RedisMessage is the envelope that wraps entity updates on Redis Pub/Sub.
// Workers publish this; the Go gateway reads it and fans out to WebSocket clients.
type RedisMessage struct {
	// Type is "update" (entity position changed) or "remove" (entity gone)
	Type string `json:"type"`

	// Entity is set when Type == "update"
	Entity *NormalizedEntity `json:"entity,omitempty"`

	// ID is set when Type == "remove", e.g. "adsb:abc123"
	ID string `json:"id,omitempty"`
}

// ---------------------------------------------------------------------------
// Category B — Event
// ---------------------------------------------------------------------------
// A manually pinned incident (strike, explosion, military movement, etc.)
// Served via GET /api/events; created via POST /api/events (admin only).

// Event represents a single user-contributed map incident.
type Event struct {
	ID          uuid.UUID  `json:"id"`
	CreatedAt   time.Time  `json:"created_at"`
	EventTime   time.Time  `json:"event_time"`
	Lat         float64    `json:"lat"`
	Lon         float64    `json:"lon"`
	EventType   string     `json:"event_type"` // "strike" | "explosion" | "military_movement" | "protest" | "other"
	Title       string     `json:"title"`
	Description *string    `json:"description,omitempty"`
	SourceURL   *string    `json:"source_url,omitempty"`
	Verified    bool       `json:"verified"`
	Contributor *string    `json:"contributor,omitempty"`
}

// CreateEventRequest is the body accepted by POST /api/events.
// It omits server-assigned fields (id, created_at, verified).
type CreateEventRequest struct {
	EventTime   time.Time `json:"event_time"`
	Lat         float64   `json:"lat"`
	Lon         float64   `json:"lon"`
	EventType   string    `json:"event_type"`
	Title       string    `json:"title"`
	Description *string   `json:"description,omitempty"`
	SourceURL   *string   `json:"source_url,omitempty"`
	Contributor *string   `json:"contributor,omitempty"`
}

// ---------------------------------------------------------------------------
// Category B — JammingHex
// ---------------------------------------------------------------------------
// One hexagonal cell from the GPSJam daily dataset.
// Served via GET /api/gpsjam/current as a JSON array.

// JammingHex represents GPS interference data for one H3 hexagon on one day.
type JammingHex struct {
	H3Index         string  `json:"h3_index"`         // H3 hex identifier, e.g. "8928308280fffff"
	InterferencePct float64 `json:"interference_pct"` // 0.0–100.0
	Date            string  `json:"date"`             // "YYYY-MM-DD"
}

// ---------------------------------------------------------------------------
// Category B — TLERecord
// ---------------------------------------------------------------------------
// One satellite's Two-Line Element set, fetched from CelesTrak.
// Served via GET /api/satellites/tles as a JSON array.
// The browser propagates positions client-side using satellite.js.

// TLERecord holds the orbital data for a single satellite.
type TLERecord struct {
	NoradCatID    int       `json:"norad_cat_id"`
	Name          string    `json:"name"`
	TLELine1      string    `json:"tle_line1"`
	TLELine2      string    `json:"tle_line2"`
	Constellation string    `json:"constellation"` // "starlink" | "iridium-next" | "active" | ...
	FetchedAt     time.Time `json:"fetched_at"`
}
