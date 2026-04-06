# SituationRoom — Agent Instructions

Instructions for AI coding agents (GitHub Copilot, Codex, etc.) working in this repository.

---

## What This Project Is

SituationRoom is a live geospatial intelligence platform. It aggregates maritime traffic (AIS), air traffic (ADS-B), satellite constellations, GPS jamming zones, and user-contributed events onto an interactive global map.

---

## Tech Stack (do not swap without discussion)

| Layer | Technology |
|---|---|
| Frontend | React 19, Vite, TypeScript, MapLibre GL JS, Deck.gl, Zustand |
| API Gateway | Go, Fiber v2, gorilla/websocket, go-redis/v9, pgx/v5 |
| Workers | Python 3.13, asyncio, aiohttp, websockets, asyncpg, Pydantic v2 |
| Database | TimescaleDB + PostGIS (single PostgreSQL 16 instance) |
| Cache / Pub-Sub | Redis 7 |
| Proxy | Nginx |
| Containers | Docker Compose v2 |

---

## Data Contract: Two Categories

All data in this system falls into one of two categories. Do not conflate them.

### Category A — Tracked Point Entities (streaming)
Aircraft, ships. Use the `NormalizedEntity` schema. Flow: Python worker → Redis Pub/Sub → Go WS hub → browser Zustand store → Deck.gl layer.

```
id, source, entity_type, lat, lon, alt_m?, heading_deg?, speed_knots?, callsign?, metadata{}, timestamp
```

### Category B — Static / Derived Layers (REST only)
GPS jamming hex grid, events, satellite TLEs. Each has its own typed schema. Served via REST endpoints. Do NOT stream these through the WebSocket except for new event notifications.

---

## Critical Architectural Rules

1. **Snapshots from DB, not Redis.** On WebSocket connect, the Go gateway queries TimescaleDB (`DISTINCT ON (entity_id) WHERE time > NOW() - INTERVAL '2 min'`). Redis has no snapshot role — it is pub/sub only.

2. **Delta publishing only.** The ADS-B worker diffs successive OpenSky polls and publishes only changed or removed entities, not the full snapshot.

3. **Viewport filtering in the Go hub.** Each WS client sends `{"type":"setViewport","bbox":[minLat,minLon,maxLat,maxLon]}`. The hub only broadcasts entity updates to clients whose viewport contains that entity.

4. **Source-level bbox.** OpenSky is polled with `?lamin=&lomin=&lamax=&lomax=` params. Default bbox set in `ADSB_BBOX` env var. Do not remove this filtering.

5. **Frontend deploy shape.** Dev = Vite dev server on host (`npm run dev`), no Nginx. Production = multi-stage Docker build (Vite → static `dist/`), Nginx serves files directly. Do not add the Vite dev server to the app Docker profile.

6. **Event auth.** `POST /api/events` and `DELETE /api/events/:id` require `Authorization: Bearer {ADMIN_KEY}`. `GET /api/events` is public.

7. **Health endpoint.** Use `GET /api/health` (not `/health`) so Nginx's `/api/*` rule routes it to Go.

---

## Deploy Modes

```
Dev:        docker compose up db redis api workers  +  npm run dev (host)
Production: docker compose --profile app up
```

---

## What NOT to Do

- Do not use Redis HSET/HGET to store entity state for snapshots
- Do not stream GPS jamming or TLE data through WebSocket (REST only)
- Do not put satellite position computation on the server — it happens client-side via a Web Worker using `satellite.js`
- Do not add the Vite dev server as a Docker service in the `app` profile
- Do not remove geographic bbox filtering from the ADS-B worker
- Do not expose `POST /api/events` without the admin key middleware
