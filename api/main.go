// SituationRoom API Gateway
//
// This is the entry point for the Go backend. It:
//   1. Reads configuration from environment variables
//   2. Opens a connection pool to PostgreSQL
//   3. Creates the WebSocket hub (manages all connected browsers)
//   4. Starts a Redis subscriber that forwards entity updates to the hub
//   5. Starts a Fiber HTTP server with the following routes:
//        GET  /api/health    → 200 OK (health check for Docker / Nginx)
//        GET  /api/entities  → JSON array of current entity positions (REST snapshot)
//        GET  /ws            → WebSocket: snapshot on connect + live entity stream
//
//        GET  /api/events                   → list events ✓
//        POST /api/events    [admin]        → create event ✓
//        DELETE /api/events/:id [admin]     → delete event ✓
//        GET  /api/gpsjam/current           → GPS jamming hexagons ✓
//        GET  /api/satellites/tles          → satellite TLE data ✓
package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"

	fiberws "github.com/gofiber/contrib/websocket"
	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/cors"
	"github.com/gofiber/fiber/v2/middleware/recover"
	"strings"

	"situationroom/api/internal/config"
	appdb "situationroom/api/internal/db"
	"situationroom/api/internal/http/handlers"
	"situationroom/api/internal/middleware"
	appredis "situationroom/api/internal/redis"
	"situationroom/api/internal/ws"
)

func main() {
	cfg := config.Load()

	// --- Database ---
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	pool, err := appdb.NewPool(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("database: %v", err)
	}
	defer pool.Close()
	log.Println("database: connected")

	// --- WebSocket hub ---
	hub := ws.NewHub()

	// --- Redis client (for publishing new events) ---
	redisClient, err := appredis.NewClient(cfg.RedisURL)
	if err != nil {
		log.Fatalf("redis: %v", err)
	}
	defer redisClient.Close()

	// --- Redis subscriber ---
	// Runs in a background goroutine. Subscribes to all entity channels and
	// calls hub.BroadcastFiltered / hub.BroadcastAll for each message.
	// Reconnects automatically with exponential backoff on connection drops.
	go appredis.Subscribe(ctx, cfg.RedisURL, hub)

	// --- HTTP server ---
	app := fiber.New(fiber.Config{
		// Don't print the Fiber banner — it clutters Docker logs.
		DisableStartupMessage: true,
		// Return errors as JSON rather than HTML (this is an API server).
		ErrorHandler: func(c *fiber.Ctx, err error) error {
			code := fiber.StatusInternalServerError
			if e, ok := err.(*fiber.Error); ok {
				code = e.Code
			}
			return c.Status(code).JSON(fiber.Map{"error": err.Error()})
		},
	})

	// Recover from panics in handlers so a single bad request doesn't crash
	// the whole server.
	app.Use(recover.New())

	// CORS: allow the Vite dev server and production frontend to make requests.
	app.Use(cors.New(cors.Config{
		AllowOrigins: strings.Join(cfg.CORSOrigins, ","),
		AllowHeaders: "Origin, Content-Type, Authorization",
		AllowMethods: "GET, POST, DELETE, OPTIONS",
	}))

	// WebSocket upgrade check middleware: Fiber requires this before the WS handler.
	// It rejects non-upgrade requests to /ws with 426 Upgrade Required.
	app.Use("/ws", func(c *fiber.Ctx) error {
		if fiberws.IsWebSocketUpgrade(c) {
			return c.Next()
		}
		return fiber.ErrUpgradeRequired
	})

	// --- Routes ---
	api := app.Group("/api")
	api.Get("/health", handlers.Health)
	api.Get("/entities", handlers.GetEntities(pool))
	api.Get("/gpsjam/current", handlers.GetGpsJam(pool))
	api.Get("/satellites/tles", handlers.GetSatellites(pool))

	// Events: GET is public; POST and DELETE require the admin key.
	adminAuth := middleware.RequireAdminKey(cfg.AdminKey)
	api.Get("/events", handlers.GetEvents(pool))
	api.Post("/events", adminAuth, handlers.CreateEvent(pool, redisClient))
	api.Delete("/events/:id", adminAuth, handlers.DeleteEvent(pool))

	app.Get("/ws", handlers.WebSocketHandler(hub, pool))

	// --- Graceful shutdown ---
	// Listen for Ctrl-C or Docker's SIGTERM and shut down cleanly.
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, os.Interrupt, syscall.SIGTERM)

	go func() {
		addr := ":" + cfg.APIPort
		log.Printf("api: listening on %s", addr)
		if err := app.Listen(addr); err != nil {
			log.Fatalf("api: server error: %v", err)
		}
	}()

	<-quit
	log.Println("api: shutting down…")
	cancel() // stop Redis subscriber
	_ = app.Shutdown()
	log.Println("api: stopped")
}
