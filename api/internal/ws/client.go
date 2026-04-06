// Package ws — client.go manages a single WebSocket connection.
//
// Each connected browser gets its own Client. The Client has two goroutines:
//   - WritePump: sits in a loop sending queued messages to the browser
//   - ReadPump:  sits in a loop reading messages from the browser
//
// The only message the browser currently sends is "setViewport", which tells
// the hub which geographic rectangle the user is looking at. The hub uses
// this to filter which entity updates to forward.
//
// Lifecycle:
//   1. WebSocket handler creates a Client and starts WritePump + ReadPump
//   2. Handler sends the DB snapshot via client.Send, then registers with hub
//   3. Hub pushes live updates into client.Send; WritePump drains it to the WS
//   4. When the browser disconnects, ReadPump returns an error and closes `quit`
//   5. WritePump sees `<-quit`, exits; handler defers Unregister from the hub
package ws

import (
	"encoding/json"
	"log"
	"sync"

	fiberws "github.com/gofiber/contrib/websocket"
)

const (
	// sendBufSize is the number of messages that can be queued before we
	// start dropping (for a slow client). 256 covers ~4 seconds at 60 msg/s.
	sendBufSize = 256
)

// Client represents one connected browser WebSocket session.
type Client struct {
	hub  *Hub
	conn *fiberws.Conn

	// send is the outbound message queue. WritePump drains it.
	// Never closed — abandoned when the client is GC'd after Unregister.
	send chan []byte

	// quit signals WritePump to stop when ReadPump exits (or vice-versa).
	quit     chan struct{}
	quitOnce sync.Once

	// viewport is the geographic bounding box the client is currently viewing.
	// nil means "no filter — send everything" (initial state before setViewport).
	vpMu     sync.RWMutex
	viewport *[4]float64 // [minLat, minLon, maxLat, maxLon]
}

// NewClient allocates a Client for the given WebSocket connection.
func NewClient(hub *Hub, conn *fiberws.Conn) *Client {
	return &Client{
		hub:  hub,
		conn: conn,
		send: make(chan []byte, sendBufSize),
		quit: make(chan struct{}),
	}
}

// InViewport reports whether the point (lat, lon) falls inside this client's
// current viewport. Returns true if no viewport has been set yet (receive all).
func (c *Client) InViewport(lat, lon float64) bool {
	c.vpMu.RLock()
	defer c.vpMu.RUnlock()

	if c.viewport == nil {
		return true // no filter set yet — send everything
	}

	vp := c.viewport
	return lat >= vp[0] && lat <= vp[2] && lon >= vp[1] && lon <= vp[3]
}

// setViewportMsg is the JSON shape the browser sends to update its viewport.
// Example: {"type":"setViewport","bbox":[48.0,14.0,55.0,24.0]}
type setViewportMsg struct {
	Type string     `json:"type"`
	BBox [4]float64 `json:"bbox"` // [minLat, minLon, maxLat, maxLon]
}

// Send queues a message for delivery to this client's browser.
// Non-blocking: if the outbound buffer is full the message is dropped.
func (c *Client) Send(msg []byte) {
	select {
	case c.send <- msg:
	default:
	}
}

// closeQuit ensures quit is closed exactly once (safe to call from both pumps).
func (c *Client) closeQuit() {
	c.quitOnce.Do(func() { close(c.quit) })
}

// ReadPump reads messages from the browser until the connection closes.
// Must run in its own goroutine (blocks until disconnect).
func (c *Client) ReadPump() {
	defer c.closeQuit()
	defer c.hub.Unregister(c)

	for {
		_, raw, err := c.conn.ReadMessage()
		if err != nil {
			// Normal close or network error — exit cleanly.
			return
		}

		var msg setViewportMsg
		if err := json.Unmarshal(raw, &msg); err != nil {
			continue // ignore malformed messages
		}

		if msg.Type == "setViewport" {
			vp := msg.BBox // copy
			c.vpMu.Lock()
			c.viewport = &vp
			c.vpMu.Unlock()
			log.Printf("ws: client set viewport [%.2f,%.2f → %.2f,%.2f]",
				vp[0], vp[1], vp[2], vp[3])
		}
	}
}

// WritePump drains the send queue and writes messages to the browser.
// Must run in its own goroutine (blocks until quit or write error).
func (c *Client) WritePump() {
	defer c.conn.Close()
	defer c.closeQuit()

	for {
		select {
		case msg := <-c.send:
			if err := c.conn.WriteMessage(fiberws.TextMessage, msg); err != nil {
				return // browser disconnected or network error
			}
		case <-c.quit:
			return // ReadPump signalled us to stop
		}
	}
}
