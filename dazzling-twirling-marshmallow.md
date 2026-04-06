# SituationRoom — Phase 1 Implementation Plan

## Context

Greenfield OSINT platform inspired by liveuamap. The goal is a live, interactive global map that aggregates maritime traffic (AIS), air traffic (ADS-B), satellite constellations, GPS jamming zones, and user-contributed strike/event coordinates. The working directory (`SituationRoom/`) is currently empty. This plan bootstraps the full stack from scratch.

---

## Architecture Overview

```
External APIs (AISStream, OpenSky, CelesTrak, GPSJam)
        |
[Python Workers] --normalize--> [Redis Pub/Sub] --> [Go API Gateway] --WS--> [Browser]
        |                                                   |
        +--batch insert--> [TimescaleDB + PostGIS] <-- REST queries (snapshot + static layers)
```

- **Frontend**: React 19 + Vite + TypeScript, MapLibre GL JS (basemap), Deck.gl (data layers), Zustand (state)
- **API Gateway**: Go (Fiber + gorilla/websocket) — WebSocket fan-out, REST endpoints, Redis subscriber
- **Workers**: Python asyncio — one worker per data source, normalize to typed schemas per category
- **Database**: TimescaleDB + PostGIS (single PostgreSQL instance) — hypertable for position time-series, spatial indexes
- **Message Bus**: Redis Pub/Sub — workers publish, Go subscribes and broadcasts. No snapshot role — DB is the snapshot source.
- **Proxy**: Nginx — routes `/api/*` and `/ws` to Go, serves frontend static assets directly (no Vite proxy)
- **Containers**: Docker Compose v2 — single `compose.yml` at repo root

### Deploy Modes

Two explicit modes:

**Dev** (daily use): Run `docker compose up db redis api workers`. Frontend runs on the host via `npm run dev`. Vite's `vite.config.ts` proxy handles `/api` → `localhost:8080` and `/ws`. No Nginx in dev. Access at `http://localhost:5173`.

**Production / integration test**: `docker compose --profile app up`. Frontend service runs a multi-stage Docker build (Vite build → static `dist/`). Nginx serves static assets directly and proxies `/api/*` + `/ws` to Go. Access at `http://localhost:80`. The Vite dev server is not in the app profile — only a built artifact is served.

---

## Project Structure

```
SituationRoom/
├── compose.yml
├── .env.example
├── .gitignore
├── frontend/
│   ├── package.json, vite.config.ts, tsconfig.json, index.html
│   └── src/
│       ├── main.tsx, App.tsx
│       ├── store/          # entities.store.ts, ui.store.ts
│       ├── map/
│       │   ├── SituationMap.tsx
│       │   └── layers/     # AircraftLayer, ShipLayer, SatelliteLayer, GpsJamLayer, EventLayer
│       ├── workers/        # satellite-propagator.worker.ts (Web Worker, satellite.js SGP4)
│       ├── hooks/          # useWebSocket.ts, useEntityStream.ts
│       └── types/          # entities.ts (Category A), layers.ts (Category B)
├── api/
│   ├── go.mod, Dockerfile
│   ├── main.go
│   └── internal/
│       ├── config/, ws/hub.go, ws/client.go, redis/subscriber.go
│       ├── middleware/auth.go   # ADMIN_KEY enforcement for mutating endpoints
│       └── http/handlers/      # entities.go, events.go, gpsjam.go, satellites.go, health.go
├── workers/
│   ├── requirements.txt, Dockerfile, scheduler.py
│   ├── common/             # schema.py (both categories), redis_client.py, db.py
│   ├── ais/, adsb/, satellites/, gpsjam/
├── db/
│   └── migrations/         # 001_extensions, 002_entities, 003_events, 004_indexes, 005_satellites
└── nginx/
    └── nginx.conf          # /api/* + /ws → Go; / → static frontend dist
```

---

## Data Contract: Two Categories

### Category A — Tracked Point Entities
Moving entities that stream through Redis Pub/Sub → WS → Deck.gl:
- **Aircraft** (ADS-B source)
- **Ships** (AIS source)
- **Satellite positions** (propagated client-side by Web Worker, sent to frontend store directly — server never holds satellite positions)

All Category A entities share `NormalizedEntity`:

```
id: "{source}:{identifier}"   e.g. "adsb:abc123"
source: "ais" | "adsb" | "satellite"
entity_type: "ship" | "aircraft" | "satellite"
lat, lon: float
alt_m, heading_deg, speed_knots: optional float
callsign: optional string
metadata: dict (source-specific extras: MMSI, ICAO24, etc.)
timestamp: UTC datetime
```

Stored in `entity_positions` hypertable. Snapshot served from DB, not Redis.

### Category B — Static / Derived Layers
Non-streaming layers with their own schemas, served via REST only:

**GPS Jamming** (`GET /api/gpsjam/current`):
```
{ h3_index: string, interference_pct: float, date: date }[]
```

**Events** (`GET /api/events`, `POST /api/events` [admin]):
```
{ id, event_time, lat, lon, event_type, title, description, source_url, verified }
```
New events are also published to `channel:events` so live clients receive them via WS without polling.

**Satellite TLEs** (`GET /api/satellites/tles`):
```
{ norad_cat_id: number, name: string, tle_line1: string, tle_line2: string, constellation: string, fetched_at: string }[]
```
TLEs are fetched by the browser once, then propagated client-side via `satellite.js` Web Worker.

---

## Data Sources

| Layer | Category | Source | Method |
|---|---|---|---|
| AIS | A | AISStream.io (free API key) | Persistent WebSocket |
| ADS-B | A | OpenSky Network (free account) | Poll every 15s, bbox filtered |
| Satellites | B → A (client) | CelesTrak GP JSON API | Fetch TLEs hourly; REST endpoint; propagate client-side |
| GPS Jamming | B | GPSJam.org daily CSV | Fetch once daily; REST endpoint |
| Events | B | Manual user contribution | Admin-authenticated POST |

---

## Database Schema (key tables)

```sql
-- entity_positions (Category A hypertable, partitioned by time)
time TIMESTAMPTZ, entity_id TEXT, source TEXT, entity_type TEXT,
position GEOGRAPHY(POINT,4326), altitude_m FLOAT, heading_deg FLOAT,
speed_knots FLOAT, callsign TEXT, metadata JSONB
-- GIST index on position, btree on (entity_id, time DESC)
-- TimescaleDB compression after 1 hour
-- NOTE: snapshot queries use DISTINCT ON (entity_id) WHERE time > NOW() - INTERVAL '2 min'

-- events (Category B)
id UUID, created_at TIMESTAMPTZ, event_time TIMESTAMPTZ,
position GEOGRAPHY(POINT,4326), event_type TEXT, title TEXT,
description TEXT, source_url TEXT, verified BOOL DEFAULT FALSE
-- GIST index on position

-- satellite_tles (Category B)
norad_cat_id INTEGER PRIMARY KEY, name TEXT, tle_line1 TEXT, tle_line2 TEXT,
constellation TEXT, fetched_at TIMESTAMPTZ
```

---

## Entity Liveness / Expiry

**No Redis hashes for snapshot.** On new WS connection the gateway runs:
```sql
SELECT DISTINCT ON (entity_id) *
FROM entity_positions
WHERE time > NOW() - INTERVAL '2 minutes'   -- ADS-B cadence
   OR (source = 'ais' AND time > NOW() - INTERVAL '10 minutes')
ORDER BY entity_id, time DESC
```
This is DB-backed, survives gateway restarts, and is naturally pruned by time — dead entities never appear in the initial state.

**Explicit remove events**: The ADS-B worker diffs successive OpenSky polls. Entities present in poll N-1 but absent in poll N trigger a `{"type":"remove","id":"adsb:{icao24}"}` publish to Redis, which the hub broadcasts to all clients. The frontend store removes the entity immediately.

**Client-side TTL**: The Zustand store also expires any entity not updated within `2 × source_cadence` seconds as a safety net.

---

## Volume Control / Backpressure (ADS-B)

Three controls in priority order:

1. **Source-level bbox filtering**: OpenSky's API accepts `?lamin=&lomin=&lamax=&lomax=`. Phase 1 defaults to a North Atlantic + Europe + Middle East box (`lamin=20&lomin=-80&lamax=75&lomax=60`). Configurable via env var `ADSB_BBOX`. This caps the raw poll at ~3,000–4,000 aircraft instead of 10,000+.

2. **Delta publishing**: The worker compares each poll against the previous state dict. Only entities with a position change > 0.01° or status change are published to Redis. Unchanged entities are not re-broadcast.

3. **Per-client viewport filtering in the Go hub**: Each client sends `{"type":"setViewport","bbox":[minLat,minLon,maxLat,maxLon]}` on map move. The hub stores each client's current viewport and only broadcasts a given entity update to clients whose viewport contains that entity's position. Clients outside the viewport for a given entity do not receive updates for it.

---

## Implementation Steps

### 1. Scaffolding + Docker Compose ✓
- `compose.yml`, `.env.example`, `.gitignore` created
- Dev profile: `docker compose up db redis` (no app services needed yet)

### 2. Database Migrations
- Write 5 SQL migration files in `db/migrations/`
- Confirm hypertable, spatial indexes, and satellite_tles table created via `docker compose run db-migrate`

### 3. Shared Schema Files
- `workers/common/schema.py` — Pydantic `NormalizedEntity` (Category A) + `TLERecord`, `JammingHex`, `Event` (Category B)
- `api/pkg/schema/` — equivalent Go structs for all four types
- `frontend/src/types/entities.ts` — Category A TypeScript interface
- `frontend/src/types/layers.ts` — Category B TypeScript interfaces (TLERecord, JammingHex, Event)

### 4. ADS-B Worker (first vertical slice)
- `workers/adsb/ingest.py`: polls OpenSky with bbox params every 15s
- `workers/adsb/normalize.py`: 17-field state vector → `NormalizedEntity`; diffs against previous state dict; publishes only changed/removed entities
- `workers/common/redis_client.py`: publishes `{"type":"update"|"remove", ...}` to `channel:adsb`
- `workers/common/db.py`: asyncpg pool, bulk insert with 1s batching

### 5. Go API Gateway
- `go mod init`, install: `fiber/v2`, `gorilla/websocket`, `go-redis/v9`, `pgx/v5`
- `internal/ws/hub.go` + `client.go`: hub with per-client viewport state; `setViewport` message handler; viewport-filtered broadcast
- `internal/redis/subscriber.go`: subscribes to all entity channels, calls `hub.BroadcastFiltered(entity)`
- `internal/middleware/auth.go`: checks `Authorization: Bearer {ADMIN_KEY}` for mutating handlers
- `http/handlers/entities.go`: DB snapshot query (DISTINCT ON, time-bounded) for initial WS state
- `http/handlers/health.go`: `GET /api/health` → 200

### 6. Frontend Map Shell (Dev mode: runs on host)
- `npm create vite@latest frontend -- --template react-ts`
- Install: `react-map-gl`, `@deck.gl/react`, `@deck.gl/mapbox`, `@deck.gl/layers`, `maplibre-gl`, `zustand`
- `SituationMap.tsx`: full-screen MapLibre map, OpenFreeMap basemap (`https://tiles.openfreemap.org/styles/liberty`)
- `useWebSocket.ts`: connect + exponential backoff; sends `setViewport` on map `onViewStateChange`
- `entities.store.ts`: Zustand with `applySnapshot`, `applyUpdate`, `removeEntity`, client-side TTL expiry
- `AircraftLayer.tsx`: Deck.gl `IconLayer`
- `vite.config.ts` dev proxy: `/api` → `localhost:8080`, `/ws` → `ws://localhost:8080`
- Frontend Dockerfile: multi-stage (`node` build → `nginx:alpine` serve `dist/`)

### 7. AIS Worker
- `workers/ais/ingest.py`: WebSocket to AISStream.io, regional bounding box
- `workers/ais/normalize.py`: `PositionReport` → `NormalizedEntity`; AIS has no clean "remove" signal — rely on client-side TTL expiry (10 min)
- Add `ShipLayer.tsx` to frontend

### 8. GPS Jamming Layer
- `workers/gpsjam/ingest.py`: fetch GPSJam daily CSV, parse H3 indexes + interference %
- Store in `gpsjam_daily` table; serve via `GET /api/gpsjam/current`
- `GpsJamLayer.tsx`: Deck.gl `H3HexagonLayer` (lazy-loaded, `@deck.gl/geo-layers` + `h3-js` ~1MB)

### 9. Satellite Layer
- `workers/satellites/ingest.py`: CelesTrak JSON OMM fetch hourly with `If-Modified-Since`
- Store in `satellite_tles` table; serve via `GET /api/satellites/tles`
- `satellite-propagator.worker.ts`: Web Worker, `satellite.js` SGP4, posts `NormalizedEntity[]` positions every 10s
- `SatelliteLayer.tsx`: Deck.gl `ScatterplotLayer` fed directly by Web Worker output (bypasses server entirely)

### 10. Events System
- `POST /api/events` + `DELETE /api/events/:id`: require `Authorization: Bearer {ADMIN_KEY}` (middleware)
- `GET /api/events`: public; PostGIS viewport bbox filter
- New events published to `channel:events` → WS broadcast for live clients
- `EventLayer.tsx`: Deck.gl `ScatterplotLayer` + click → `EntityPopup.tsx`
- Admin event form in frontend (hidden behind key entry)

### 11. Nginx + Full Integration (Production mode)
- `nginx/nginx.conf`: `location /api/` + `location /ws` → Go; `location /` → serve `dist/` static files
- `docker compose --profile app up` → full stack; map at `http://localhost`

### 12. UI Polish
- `LayerToggle.tsx`: per-layer visibility toggles
- `ui.store.ts`: layer visibility flags
- `EntityPopup.tsx`: click entity → metadata popup
- Loading skeleton while initial WS snapshot loads

---

## Critical Files

| File | Purpose |
|---|---|
| `compose.yml` | Orchestrates all services; dev vs app profiles |
| `workers/common/schema.py` | Both category schemas — system contract |
| `api/internal/ws/hub.go` | WS hub with per-client viewport filtering |
| `api/internal/redis/subscriber.go` | Redis → filtered WS broadcast |
| `api/internal/middleware/auth.go` | Admin key enforcement |
| `frontend/src/map/SituationMap.tsx` | Root map component; sends viewport on move |
| `frontend/src/store/entities.store.ts` | Live entity state + TTL expiry |
| `db/migrations/002_entities_table.sql` | TimescaleDB hypertable |

---

## Verification

**Dev mode** (`docker compose up db redis api workers` + `npm run dev`):
1. `curl http://localhost:8080/api/health` → 200
2. `curl http://localhost:8080/api/entities` → JSON array (may be empty before workers connect)
3. Open `http://localhost:5173` → map renders with OpenFreeMap basemap
4. ADS-B aircraft appear and update; stale ones disappear after 2× cadence
5. Kill and restart Go gateway → browser reconnects and DB snapshot restores full state

**Production mode** (`docker compose --profile app up`):
6. `curl http://localhost/api/health` → 200 (routed via Nginx `/api/*` → Go)
7. Open `http://localhost` → same map from static `dist/`
8. AIS ships appear after AISStream connection established
9. GPS Jamming hexagons render when layer toggled on
10. Satellite positions update every 10s (Web Worker, no server involvement)
11. Submit event via admin form → appears on map for all connected clients via WS

---

## Key Risks / Watch-outs

- **OpenSky bbox defaults**: The default bbox covers ~3,500 aircraft. Expand via `ADSB_BBOX` env var once the stack is proven stable.
- **AISStream burst on connect**: Global box produces a flood of position reports for the first ~30s. Add a connect-time rate limiter (token bucket, 200 msg/s max) to avoid Redis saturation.
- **Deck.gl updateTriggers**: Pass stable Zustand slice references; use `updateTriggers` to avoid unnecessary GPU buffer re-uploads when only a subset of entities change.
- **h3-js bundle size**: ~1MB WASM — lazy-load the `GpsJamLayer` component so it doesn't block initial map render.
- **CelesTrak rate limits**: Max 1 fetch/hour/group — use `If-Modified-Since` headers; log 304s as success.
- **Schema drift**: The Pydantic / Go struct / TypeScript interfaces must stay in sync manually in Phase 1. Consider an OpenAPI spec in Phase 2.
- **Admin key rotation**: `ADMIN_KEY` in `.env` is the only auth for event submission. Rotate it if exposed. Phase 2 should replace with proper user auth.
