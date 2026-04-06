package handlers

import (
	"context"
	"fmt"
	"log"

	"github.com/gofiber/fiber/v2"
	"github.com/jackc/pgx/v5/pgxpool"

	"situationroom/api/pkg/schema"
)

// getTLEsSQL fetches all satellite TLE records, ordered alphabetically by name.
// The frontend receives the full list and propagates positions client-side.
const getTLEsSQL = `
SELECT norad_cat_id, name, tle_line1, tle_line2, constellation, fetched_at
FROM   satellite_tles
ORDER  BY name
`

// GetSatellites handles GET /api/satellites/tles.
//
// Returns a JSON array of TLERecord objects. Returns an empty array when the
// table is empty (e.g. before the first hourly fetch runs).
//
// The browser uses these TLEs to compute satellite positions client-side with
// the satellite.js SGP4 propagator — the server never calculates positions.
func GetSatellites(pool *pgxpool.Pool) fiber.Handler {
	return func(c *fiber.Ctx) error {
		tles, err := queryTLEs(c.Context(), pool)
		if err != nil {
			log.Printf("GET /api/satellites/tles: %v", err)
			return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
				"error": "failed to query satellite TLEs",
			})
		}
		return c.JSON(tles)
	}
}

func queryTLEs(ctx context.Context, pool *pgxpool.Pool) ([]schema.TLERecord, error) {
	rows, err := pool.Query(ctx, getTLEsSQL)
	if err != nil {
		return nil, fmt.Errorf("satellites query: %w", err)
	}
	defer rows.Close()

	tles := make([]schema.TLERecord, 0)
	for rows.Next() {
		var t schema.TLERecord
		if err := rows.Scan(
			&t.NoradCatID,
			&t.Name,
			&t.TLELine1,
			&t.TLELine2,
			&t.Constellation,
			&t.FetchedAt,
		); err != nil {
			return nil, fmt.Errorf("satellites scan: %w", err)
		}
		tles = append(tles, t)
	}
	return tles, rows.Err()
}
