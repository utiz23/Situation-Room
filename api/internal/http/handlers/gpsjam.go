package handlers

import (
	"context"
	"fmt"
	"log"

	"github.com/gofiber/fiber/v2"
	"github.com/jackc/pgx/v5/pgxpool"

	"situationroom/api/pkg/schema"
)

// currentJamSQL returns every hex cell for the most recent date in the table.
// The subquery (SELECT MAX(date) ...) means we always serve the latest day's
// data without needing to know the date in advance.
const currentJamSQL = `
SELECT h3_index, interference_pct, date::text
FROM   gpsjam_daily
WHERE  date = (SELECT MAX(date) FROM gpsjam_daily)
ORDER  BY interference_pct DESC
`

// GetGpsJam handles GET /api/gpsjam/current.
//
// Returns a JSON array of JammingHex objects for the most recent day
// in the gpsjam_daily table. Returns an empty array when the table is empty
// (e.g. before the first daily fetch runs).
func GetGpsJam(pool *pgxpool.Pool) fiber.Handler {
	return func(c *fiber.Ctx) error {
		hexes, err := queryCurrentJam(c.Context(), pool)
		if err != nil {
			log.Printf("GET /api/gpsjam/current: %v", err)
			return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
				"error": "failed to query GPS jamming data",
			})
		}
		return c.JSON(hexes)
	}
}

func queryCurrentJam(ctx context.Context, pool *pgxpool.Pool) ([]schema.JammingHex, error) {
	rows, err := pool.Query(ctx, currentJamSQL)
	if err != nil {
		return nil, fmt.Errorf("gpsjam query: %w", err)
	}
	defer rows.Close()

	hexes := make([]schema.JammingHex, 0)
	for rows.Next() {
		var h schema.JammingHex
		if err := rows.Scan(&h.H3Index, &h.InterferencePct, &h.Date); err != nil {
			return nil, fmt.Errorf("gpsjam scan: %w", err)
		}
		hexes = append(hexes, h)
	}
	return hexes, rows.Err()
}
