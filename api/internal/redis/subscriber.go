// Package redis subscribes to the Redis Pub/Sub channels that workers publish
// entity updates to, and forwards each message to the WebSocket hub.
//
// The flow is:
//
//	Python worker → Redis "channel:adsb" → (this file) → hub.BroadcastFiltered
//	                                                      └─→ each browser's WS
//
// The message format on Redis is a JSON envelope (defined in pkg/schema.RedisMessage):
//
//	{"type":"update","entity":{...NormalizedEntity...}}   — published by Python workers
//	{"type":"remove","id":"adsb:abc123"}                  — published by Python workers
//	{"type":"event","event":{...Event...}}                — published by POST /api/events handler
//
// "update" messages are viewport-filtered before delivery.
// "remove" and "event" messages go to all clients (no position to filter by).
package redis

import (
	"context"
	"encoding/json"
	"log"
	"time"

	goredis "github.com/redis/go-redis/v9"

	"situationroom/api/internal/ws"
	"situationroom/api/pkg/schema"
)

// Publisher is the interface the events handler uses to publish a new event
// to Redis without importing the full subscriber machinery.
type Publisher interface {
	Publish(channel string, msg []byte) error
}

// Client wraps a Redis connection and implements Publisher.
type Client struct {
	rdb *goredis.Client
}

// NewClient opens a Redis connection and returns a Client.
func NewClient(redisURL string) (*Client, error) {
	opts, err := goredis.ParseURL(redisURL)
	if err != nil {
		return nil, err
	}
	return &Client{rdb: goredis.NewClient(opts)}, nil
}

// Publish sends msg to the given Redis channel.
func (c *Client) Publish(channel string, msg []byte) error {
	return c.rdb.Publish(context.Background(), channel, msg).Err()
}

// Close shuts down the Redis client connection.
func (c *Client) Close() {
	c.rdb.Close()
}

// subscribedChannels are all Redis Pub/Sub channels we listen on.
var subscribedChannels = []string{
	"channel:adsb",
	"channel:ais",
	"channel:events",
}

// Subscribe connects to Redis and blocks, forwarding every incoming message
// to the hub. Reconnects automatically with exponential backoff if the
// Redis connection drops — the goroutine never exits permanently.
//
// Call this in a goroutine: go redis.Subscribe(ctx, redisURL, hub)
func Subscribe(ctx context.Context, redisURL string, hub *ws.Hub) {
	opts, err := goredis.ParseURL(redisURL)
	if err != nil {
		log.Fatalf("redis: invalid REDIS_URL: %v", err)
	}

	backoff := time.Second
	const maxBackoff = 30 * time.Second

	for {
		if ctx.Err() != nil {
			log.Println("redis: subscriber context cancelled — exiting")
			return
		}

		client := goredis.NewClient(opts)
		pubsub := client.Subscribe(ctx, subscribedChannels...)

		log.Printf("redis: subscribed to %v", subscribedChannels)
		backoff = time.Second // reset on successful connect

		ch := pubsub.Channel()
	loop:
		for {
			select {
			case <-ctx.Done():
				pubsub.Close()
				client.Close()
				log.Println("redis: subscriber shutting down")
				return

			case msg, ok := <-ch:
				if !ok {
					// Channel closed — Redis connection dropped.
					log.Println("redis: pub/sub channel closed — reconnecting…")
					break loop
				}
				dispatch(hub, []byte(msg.Payload))
			}
		}

		pubsub.Close()
		client.Close()

		// Exponential backoff before reconnect attempt.
		log.Printf("redis: reconnecting in %s", backoff)
		select {
		case <-ctx.Done():
			return
		case <-time.After(backoff):
		}
		if backoff < maxBackoff {
			backoff *= 2
			if backoff > maxBackoff {
				backoff = maxBackoff
			}
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

	case "event":
		// New admin-submitted event — broadcast to all clients.
		hub.BroadcastAll(payload)

	default:
		log.Printf("redis: unknown message type %q", env.Type)
	}
}
