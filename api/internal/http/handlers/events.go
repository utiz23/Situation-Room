package handlers

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strconv"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	appredis "situationroom/api/internal/redis"
	"situationroom/api/pkg/schema"
)

// ---------------------------------------------------------------------------
// GET /api/events
// ---------------------------------------------------------------------------

// listEventsSQL returns events ordered by most recent event_time.
// Optional bbox filtering: if all four query params are present, only events
// whose position falls within the bounding box are returned.
const listEventsSQL = `
SELECT id, created_at, event_time,
       ST_Y(position::geometry) AS lat,
       ST_X(position::geometry) AS lon,
       event_type, title, description, source_url, verified, contributor
FROM   events
ORDER  BY event_time DESC
LIMIT  500
`

const listEventsBBoxSQL = `
SELECT id, created_at, event_time,
       ST_Y(position::geometry) AS lat,
       ST_X(position::geometry) AS lon,
       event_type, title, description, source_url, verified, contributor
FROM   events
WHERE  ST_Within(
           position::geometry,
           ST_MakeEnvelope($1, $2, $3, $4, 4326)
       )
ORDER  BY event_time DESC
LIMIT  500
`

// GetEvents handles GET /api/events.
//
// Optional query parameters for viewport filtering:
//
//	?minLon=&minLat=&maxLon=&maxLat=
//
// Returns a JSON array of Event objects (empty array when none found).
func GetEvents(pool *pgxpool.Pool) fiber.Handler {
	return func(c *fiber.Ctx) error {
		bboxParams := []string{"minLon", "minLat", "maxLon", "maxLat"}
		bboxPresent := 0
		for _, p := range bboxParams {
			if c.Query(p) != "" {
				bboxPresent++
			}
		}

		var minLon, minLat, maxLon, maxLat float64
		useBBox := bboxPresent == 4

		if bboxPresent > 0 && bboxPresent < 4 {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
				"error": "bbox requires all four params: minLon, minLat, maxLon, maxLat",
			})
		}

		if useBBox {
			var err error
			if minLon, err = strconv.ParseFloat(c.Query("minLon"), 64); err != nil {
				return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error": "minLon must be a number"})
			}
			if minLat, err = strconv.ParseFloat(c.Query("minLat"), 64); err != nil {
				return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error": "minLat must be a number"})
			}
			if maxLon, err = strconv.ParseFloat(c.Query("maxLon"), 64); err != nil {
				return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error": "maxLon must be a number"})
			}
			if maxLat, err = strconv.ParseFloat(c.Query("maxLat"), 64); err != nil {
				return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error": "maxLat must be a number"})
			}
		}

		events, err := queryEvents(c.Context(), pool, useBBox, minLon, minLat, maxLon, maxLat)
		if err != nil {
			log.Printf("GET /api/events: %v", err)
			return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
				"error": "failed to query events",
			})
		}
		return c.JSON(events)
	}
}

func queryEvents(
	ctx context.Context,
	pool *pgxpool.Pool,
	useBBox bool,
	minLon, minLat, maxLon, maxLat float64,
) ([]schema.Event, error) {
	var rows interface{ Next() bool; Scan(...any) error; Close(); Err() error }

	if useBBox {
		// ST_MakeEnvelope(minX, minY, maxX, maxY) = (minLon, minLat, maxLon, maxLat)
		r, err := pool.Query(ctx, listEventsBBoxSQL, minLon, minLat, maxLon, maxLat)
		if err != nil {
			return nil, fmt.Errorf("events bbox query: %w", err)
		}
		rows = r
	} else {
		r, err := pool.Query(ctx, listEventsSQL)
		if err != nil {
			return nil, fmt.Errorf("events query: %w", err)
		}
		rows = r
	}
	defer rows.Close()

	events := make([]schema.Event, 0)
	for rows.Next() {
		var e schema.Event
		if err := rows.Scan(
			&e.ID, &e.CreatedAt, &e.EventTime,
			&e.Lat, &e.Lon,
			&e.EventType, &e.Title, &e.Description,
			&e.SourceURL, &e.Verified, &e.Contributor,
		); err != nil {
			return nil, fmt.Errorf("events scan: %w", err)
		}
		events = append(events, e)
	}
	return events, rows.Err()
}

// ---------------------------------------------------------------------------
// POST /api/events  [admin]
// ---------------------------------------------------------------------------

const insertEventSQL = `
INSERT INTO events
    (event_time, position, event_type, title, description, source_url, contributor)
VALUES (
    $1,
    ST_SetSRID(ST_MakePoint($3, $2), 4326)::geography,
    $4, $5, $6, $7, $8
)
RETURNING id, created_at
`

// CreateEvent handles POST /api/events (admin only — protected by RequireAdminKey).
//
// Body (JSON):
//
//	{ event_time, lat, lon, event_type, title, description?, source_url?, contributor? }
//
// On success, publishes the new event to Redis channel:events so live clients
// receive it via WebSocket without polling.
func CreateEvent(pool *pgxpool.Pool, hub appredis.Publisher) fiber.Handler {
	return func(c *fiber.Ctx) error {
		var req schema.CreateEventRequest
		if err := c.BodyParser(&req); err != nil {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
				"error": "invalid JSON body",
			})
		}

		if req.Title == "" || req.EventType == "" {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
				"error": "title and event_type are required",
			})
		}
		if req.Lat < -90 || req.Lat > 90 || req.Lon < -180 || req.Lon > 180 {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
				"error": "lat must be -90..90, lon must be -180..180",
			})
		}

		var id uuid.UUID
		var createdAt time.Time

		err := pool.QueryRow(
			c.Context(), insertEventSQL,
			req.EventTime,   // $1
			req.Lat,         // $2 — ST_MakePoint($3=lon, $2=lat) note param order
			req.Lon,         // $3
			req.EventType,   // $4
			req.Title,       // $5
			req.Description, // $6
			req.SourceURL,   // $7
			req.Contributor, // $8
		).Scan(&id, &createdAt)
		if err != nil {
			log.Printf("POST /api/events: insert: %v", err)
			return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
				"error": "failed to create event",
			})
		}

		event := schema.Event{
			ID:          id,
			CreatedAt:   createdAt,
			EventTime:   req.EventTime,
			Lat:         req.Lat,
			Lon:         req.Lon,
			EventType:   req.EventType,
			Title:       req.Title,
			Description: req.Description,
			SourceURL:   req.SourceURL,
			Verified:    false,
			Contributor: req.Contributor,
		}

		// Publish to Redis so live clients receive the new event via WebSocket
		// without having to poll GET /api/events.
		go publishEvent(hub, event)

		return c.Status(fiber.StatusCreated).JSON(event)
	}
}

// publishEvent serialises a new event as a WS-style message and publishes it
// to channel:events. The Redis subscriber fans it out to all connected clients.
// Runs in a goroutine so a Redis hiccup never blocks the HTTP response.
func publishEvent(hub appredis.Publisher, event schema.Event) {
	type eventMsg struct {
		Type  string       `json:"type"`
		Event schema.Event `json:"event"`
	}
	msg, err := json.Marshal(eventMsg{Type: "event", Event: event})
	if err != nil {
		log.Printf("publishEvent: marshal: %v", err)
		return
	}
	if err := hub.Publish("channel:events", msg); err != nil {
		log.Printf("publishEvent: redis publish: %v", err)
	}
}

// ---------------------------------------------------------------------------
// DELETE /api/events/:id  [admin]
// ---------------------------------------------------------------------------

const deleteEventSQL = `DELETE FROM events WHERE id = $1`

// DeleteEvent handles DELETE /api/events/:id (admin only).
//
// Returns 204 No Content on success, 404 if the event doesn't exist.
func DeleteEvent(pool *pgxpool.Pool) fiber.Handler {
	return func(c *fiber.Ctx) error {
		id, err := uuid.Parse(c.Params("id"))
		if err != nil {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
				"error": "invalid event id — must be a UUID",
			})
		}

		tag, err := pool.Exec(c.Context(), deleteEventSQL, id)
		if err != nil {
			log.Printf("DELETE /api/events/%s: %v", id, err)
			return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
				"error": "failed to delete event",
			})
		}

		if tag.RowsAffected() == 0 {
			return c.Status(fiber.StatusNotFound).JSON(fiber.Map{
				"error": "event not found",
			})
		}

		return c.SendStatus(fiber.StatusNoContent)
	}
}
