// Package handlers contains the HTTP request handlers for the API gateway.
package handlers

import "github.com/gofiber/fiber/v2"

// Health handles GET /api/health.
//
// Returns 200 with a simple JSON body so Nginx's upstream health check,
// Docker's healthcheck, and curl-based smoke tests all have something to hit.
// The path is /api/health (not /health) so Nginx's "location /api/" rule
// routes it to Go correctly.
func Health(c *fiber.Ctx) error {
	return c.JSON(fiber.Map{"status": "ok"})
}
