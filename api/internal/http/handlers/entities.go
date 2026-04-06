package handlers

import (
	"context"
	"encoding/json"
	"log"

	fiberws "github.com/gofiber/contrib/websocket"
	"github.com/gofiber/fiber/v2"
	"github.com/jackc/pgx/v5/pgxpool"

	appdb "situationroom/api/internal/db"
	"situationroom/api/internal/ws"
)

// GetEntities handles GET /api/entities.
//
// Returns the current DB snapshot as a JSON array — the same data that is
// sent over WebSocket on connect. Useful for debugging and smoke tests.
func GetEntities(pool *pgxpool.Pool) fiber.Handler {
	return func(c *fiber.Ctx) error {
		entities, err := appdb.QuerySnapshot(c.Context(), pool)
		if err != nil {
			log.Printf("GET /api/entities: %v", err)
			return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
				"error": "failed to query entity snapshot",
			})
		}
		return c.JSON(entities)
	}
}

// WebSocketHandler handles GET /ws.
//
// Upgrades the connection to WebSocket, sends the current entity snapshot from
// the database, then streams live updates from the hub until the client disconnects.
//
// Message flow:
//  1. Server → browser:  {"type":"snapshot","entities":[...]}       (DB, sent once on connect)
//  2. Hub   → browser:   {"type":"update","entity":{...}}           (Redis, viewport-filtered)
//  3. Hub   → browser:   {"type":"remove","id":"adsb:abc123"}       (Redis, all clients)
//  4. Browser → server:  {"type":"setViewport","bbox":[...]}        (client updates its filter)
func WebSocketHandler(hub *ws.Hub, pool *pgxpool.Pool) fiber.Handler {
	return fiberws.New(func(conn *fiberws.Conn) {
		client := ws.NewClient(hub, conn)

		// Start write pump first so the outbound buffer drains immediately.
		go client.WritePump()

		// Register with the hub BEFORE querying the snapshot. This closes the
		// race window where live Redis updates arriving during the DB query would
		// be silently dropped for this client. Any updates that arrive during the
		// snapshot query are queued in the send buffer and delivered after the
		// snapshot. The frontend store should upsert by entity_id, so a live
		// update followed by a slightly older snapshot position is corrected on
		// the next broadcast (within one poll cycle, ~15 s for ADS-B).
		hub.Register(client)

		if err := sendSnapshot(client, pool); err != nil {
			log.Printf("ws: snapshot send failed: %v", err)
			// Not fatal — the client will fill in as live updates arrive.
		}

		// ReadPump blocks until the connection closes. It handles setViewport
		// messages and calls hub.Unregister on exit.
		client.ReadPump()
	})
}

type snapshotEnvelope struct {
	Type     string `json:"type"`
	Entities any    `json:"entities"`
}

func sendSnapshot(client *ws.Client, pool *pgxpool.Pool) error {
	entities, err := appdb.QuerySnapshot(context.Background(), pool)
	if err != nil {
		return err
	}

	msg, err := json.Marshal(snapshotEnvelope{Type: "snapshot", Entities: entities})
	if err != nil {
		return err
	}

	client.Send(msg)
	return nil
}
