// Package db manages the PostgreSQL connection pool and snapshot queries.
//
// "Snapshot" means: the most recent known position of every active entity.
// This is what the server sends to a browser the moment it connects via
// WebSocket, so the map isn't blank while the first live updates arrive.
//
// We use pgx (a pure-Go PostgreSQL driver) instead of the standard
// database/sql interface because it handles PostGIS geography types more
// cleanly and is faster for bulk operations.
package db

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"situationroom/api/pkg/schema"
)

// NewPool opens a connection pool to PostgreSQL.
//
// A "pool" keeps several connections open and ready, so each query doesn't
// have to pay the cost of opening a new TCP connection to the database.
func NewPool(ctx context.Context, databaseURL string) (*pgxpool.Pool, error) {
	pool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		return nil, fmt.Errorf("open db pool: %w", err)
	}
	// Verify the connection is actually reachable.
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ping db: %w", err)
	}
	return pool, nil
}

// snapshotSQL fetches the latest position for every entity active recently.
//
// "DISTINCT ON (entity_id) ... ORDER BY entity_id, time DESC" is PostgreSQL's
// way of saying: "for each entity_id, give me only the newest row."
//
// ST_Y extracts latitude, ST_X extracts longitude from the PostGIS geography.
// Note: ST_MakePoint stored them as (lon, lat) = (X, Y) — geographers use
// X for East-West and Y for North-South, which is the opposite of (lat, lon).
//
// Time windows match source cadences:
//   - ADS-B: active within 2 minutes (15s poll, allow a few missed polls)
//   - AIS:   ships may be silent up to 10 minutes in quiet waters
const snapshotSQL = `
SELECT DISTINCT ON (entity_id)
    entity_id,
    source,
    entity_type,
    ST_Y(position::geometry) AS lat,
    ST_X(position::geometry) AS lon,
    altitude_m,
    heading_deg,
    speed_knots,
    callsign,
    metadata,
    time AS timestamp
FROM entity_positions
WHERE time > NOW() - INTERVAL '2 minutes'
   OR (source = 'ais' AND time > NOW() - INTERVAL '10 minutes')
ORDER BY entity_id, time DESC
`

// QuerySnapshot returns the latest known position for every active entity.
// Returns an empty (non-nil) slice when there are no active entities.
func QuerySnapshot(ctx context.Context, pool *pgxpool.Pool) ([]schema.NormalizedEntity, error) {
	rows, err := pool.Query(ctx, snapshotSQL)
	if err != nil {
		return nil, fmt.Errorf("snapshot query: %w", err)
	}
	defer rows.Close()

	entities := make([]schema.NormalizedEntity, 0)

	for rows.Next() {
		var (
			entityID   string
			source     string
			entityType string
			lat        float64
			lon        float64
			altM       *float64
			headingDeg *float64
			speedKnots *float64
			callsign   *string
			metaBytes  []byte
			timestamp  time.Time
		)

		if err := rows.Scan(
			&entityID, &source, &entityType,
			&lat, &lon,
			&altM, &headingDeg, &speedKnots, &callsign,
			&metaBytes,
			&timestamp,
		); err != nil {
			return nil, fmt.Errorf("scan snapshot row: %w", err)
		}

		metadata := map[string]any{}
		if metaBytes != nil {
			_ = json.Unmarshal(metaBytes, &metadata)
		}

		entities = append(entities, schema.NormalizedEntity{
			ID:         entityID,
			Source:     source,
			EntityType: entityType,
			Lat:        lat,
			Lon:        lon,
			AltM:       altM,
			HeadingDeg: headingDeg,
			SpeedKnots: speedKnots,
			Callsign:   callsign,
			Metadata:   metadata,
			Timestamp:  timestamp,
		})
	}

	return entities, rows.Err()
}
