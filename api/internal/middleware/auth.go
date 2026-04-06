// Package middleware provides Fiber middleware for the API gateway.
package middleware

import (
	"github.com/gofiber/fiber/v2"
)

// RequireAdminKey returns a Fiber middleware that enforces the admin key on
// mutating endpoints (POST /api/events, DELETE /api/events/:id).
//
// Clients must send the header:
//
//	Authorization: Bearer <ADMIN_KEY>
//
// Any request without this header, or with the wrong key, gets a 401 response.
// The 401 body intentionally doesn't say whether the key was wrong vs missing,
// to avoid leaking information to an attacker probing the endpoint.
func RequireAdminKey(adminKey string) fiber.Handler {
	bearer := "Bearer " + adminKey

	return func(c *fiber.Ctx) error {
		if c.Get("Authorization") != bearer {
			return c.Status(fiber.StatusUnauthorized).JSON(fiber.Map{
				"error": "unauthorized",
			})
		}
		return c.Next()
	}
}
