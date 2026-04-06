// Package ws implements the WebSocket hub — the central coordinator that
// manages all connected browser clients and broadcasts entity updates to them.
//
// Key design decisions:
//
//  1. Per-client viewport filtering: each client tells the hub which geographic
//     rectangle it's currently viewing. Update messages are only sent to clients
//     whose viewport contains the entity's position. This drastically reduces
//     traffic for clients zoomed into a small area.
//
//  2. "Remove" messages bypass viewport filtering and go to all clients, because
//     once an entity is gone we don't know where it was last seen.
//
//  3. Slow clients are handled with a non-blocking send: if a client's outbound
//     buffer is full (it's not reading fast enough), the message is dropped for
//     that client rather than stalling all other clients.
package ws

import (
	"sync"
)

// Hub is the central registry of connected WebSocket clients.
// It is safe for concurrent use from multiple goroutines.
type Hub struct {
	mu      sync.RWMutex
	clients map[*Client]struct{}
}

// NewHub creates an empty hub ready to accept clients.
func NewHub() *Hub {
	return &Hub{
		clients: make(map[*Client]struct{}),
	}
}

// Register adds a client to the hub. Called when a new WebSocket connection
// is established.
func (h *Hub) Register(c *Client) {
	h.mu.Lock()
	h.clients[c] = struct{}{}
	h.mu.Unlock()
}

// Unregister removes a client from the hub. Called when a WebSocket connection
// closes (browser tab closed, network drop, etc.).
func (h *Hub) Unregister(c *Client) {
	h.mu.Lock()
	delete(h.clients, c)
	h.mu.Unlock()
}

// BroadcastFiltered sends msg to every client whose current viewport contains
// the point (lat, lon). Used for "update" entity messages.
//
// Clients with no viewport set receive all messages (useful for debugging and
// for clients that haven't sent a setViewport yet).
//
// If a client's outbound channel is full (it's processing messages too slowly),
// the message is silently dropped for that client — we never block here.
func (h *Hub) BroadcastFiltered(msg []byte, lat, lon float64) {
	h.mu.RLock()
	defer h.mu.RUnlock()

	for c := range h.clients {
		if !c.InViewport(lat, lon) {
			continue
		}
		select {
		case c.send <- msg:
		default:
			// Slow client — drop this message rather than blocking the broadcast.
		}
	}
}

// BroadcastAll sends msg to every connected client without viewport filtering.
// Used for "remove" messages and new event notifications.
func (h *Hub) BroadcastAll(msg []byte) {
	h.mu.RLock()
	defer h.mu.RUnlock()

	for c := range h.clients {
		select {
		case c.send <- msg:
		default:
			// Slow client — drop.
		}
	}
}

// ClientCount returns the number of currently connected clients.
// Used for health/metrics logging.
func (h *Hub) ClientCount() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.clients)
}
