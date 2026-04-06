// Package redis subscribes to the Redis Pub/Sub channels that workers publish
// entity updates to, and forwards each message to the WebSocket hub.
//
// The flow is:
//
//	Python worker → Redis "channel:adsb" → (this file) → hub.BroadcastFiltered
//	                                                      └─→ each browser's WS
//
// The message format on Redis is a JSON envelope (defined in pkg/schema):
//
//	{"type":"update","entity":{...NormalizedEntity...}}
//	{"type":"remove","id":"adsb:abc123"}
//
// "update" messages are viewport-filtered before delivery.
// "remove" messages go to all clients (no position to filter by).
package redis

import (
	"context"
	"encoding/json"
	"log"

	goredis "github.com/redis/go-redis/v9"

	"situationroom/api/internal/ws"
	"situationroom/api/pkg/schema"
)

// subscribedChannels are all Redis Pub/Sub channels we listen on.
// Add new worker channels here as each step is implemented.
var subscribedChannels = []string{
	"channel:adsb",
	"channel:ais",    // Step 7 — workers will publish here after AIS worker is built
	"channel:events", // Step 10 — new events published here for live notification
}

// Subscribe connects to Redis and blocks, forwarding every incoming message
// to the hub. It reconnects automatically if the Redis connection drops.
//
// Call this in a goroutine: go redis.Subscribe(ctx, redisURL, hub)
func Subscribe(ctx context.Context, redisURL string, hub *ws.Hub) {
	opts, err := goredis.ParseURL(redisURL)
	if err != nil {
		log.Fatalf("redis: invalid REDIS_URL: %v", err)
	}

	client := goredis.NewClient(opts)
	defer client.Close()

	pubsub := client.Subscribe(ctx, subscribedChannels...)
	defer pubsub.Close()

	log.Printf("redis: subscribed to %v", subscribedChannels)

	ch := pubsub.Channel()
	for {
		select {
		case <-ctx.Done():
			log.Println("redis: subscriber shutting down")
			return

		case msg, ok := <-ch:
			if !ok {
				log.Println("redis: channel closed — subscriber exiting")
				return
			}
			dispatch(hub, []byte(msg.Payload))
		}
	}
}

// dispatch parses one Redis message and routes it to the correct hub method.
func dispatch(hub *ws.Hub, payload []byte) {
	var env schema.RedisMessage
	if err := json.Unmarshal(payload, &env); err != nil {
		log.Printf("redis: malformed message (skipping): %v", err)
		return
	}

	switch env.Type {
	case "update":
		if env.Entity == nil {
			log.Printf("redis: 'update' message missing entity field")
			return
		}
		hub.BroadcastFiltered(payload, env.Entity.Lat, env.Entity.Lon)

	case "remove":
		// No position available for a removed entity — broadcast to everyone.
		hub.BroadcastAll(payload)

	default:
		log.Printf("redis: unknown message type %q", env.Type)
	}
}
