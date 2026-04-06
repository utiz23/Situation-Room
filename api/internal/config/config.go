// Package config reads runtime configuration from environment variables.
//
// All configuration comes from the environment — never from hardcoded values —
// so the same binary works in dev (local .env) and production (real secrets).
package config

import (
	"log"
	"os"
	"strings"
)

// Config holds all runtime settings for the API gateway.
type Config struct {
	// DatabaseURL is the PostgreSQL connection string.
	// Example: "postgres://situationroom:password@db:5432/situationroom"
	DatabaseURL string

	// RedisURL is the Redis connection string.
	// Example: "redis://redis:6379/0"
	RedisURL string

	// APIPort is the port the HTTP server listens on, e.g. "8080".
	APIPort string

	// AdminKey is the secret token required for mutating endpoints
	// (POST /api/events, DELETE /api/events/:id).
	// Requests must send: Authorization: Bearer <AdminKey>
	AdminKey string

	// CORSOrigins is the list of allowed browser origins for CORS.
	// In dev this includes http://localhost:5173 (Vite dev server).
	CORSOrigins []string
}

// Load reads environment variables and returns a populated Config.
// It calls log.Fatal if any required variable is missing.
func Load() *Config {
	cfg := &Config{
		DatabaseURL: requireEnv("DATABASE_URL"),
		RedisURL:    requireEnv("REDIS_URL"),
		APIPort:     getEnv("API_PORT", "8080"),
		AdminKey:    requireEnv("ADMIN_KEY"),
	}

	origins := getEnv("CORS_ORIGINS", "http://localhost,http://localhost:5173")
	for _, o := range strings.Split(origins, ",") {
		o = strings.TrimSpace(o)
		if o != "" {
			cfg.CORSOrigins = append(cfg.CORSOrigins, o)
		}
	}

	return cfg
}

func requireEnv(key string) string {
	v := os.Getenv(key)
	if v == "" {
		log.Fatalf("required environment variable %q is not set", key)
	}
	return v
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
