# SituationRoom — Project Status

Last updated: 2026-04-06

## Current State
- Steps 1–11 are implemented and runtime-verified.
- Full production stack (`docker compose --profile app up`) is working at `http://localhost`.
- Ready to begin Step 12: UI Polish.

## Step Status
- Step 1: Scaffolding — done.
- Step 2: DB migrations — done.
- Step 3: Shared schemas — done.
- Step 4: ADS-B worker — done (OAuth client credentials flow active).
- Step 5: Go API gateway — done.
- Step 6: Frontend shell — done.
- Step 7: AIS worker + ship layer — done.
- Step 8: GPS jamming layer — done.
- Step 9: Satellite layer — done. Gate passed: 15,802 rows in satellite_tles.
- Step 10: Events system — done (backend verified, frontend built).
- Step 11: Nginx + full integration — done. Full stack verified at http://localhost.

## Verified Working Now
- `GET /api/health` → 200
- `GET /api/entities` → live aircraft/ship snapshot
- `GET /api/gpsjam/current` → GPS jam hexes
- `GET /api/satellites/tles` → dynamic TLE count (verified: 16,135 rows on 2026-04-06)
- `GET /api/events` → [] (empty until events are posted)
- `POST /api/events` (with correct ADMIN_KEY) → 201 + event JSON
- `DELETE /api/events/:id` (with correct ADMIN_KEY) → 204
- Unauthenticated POST/DELETE → 401

## Step 10 — What Was Built

### Backend (api/)
- `api/internal/middleware/auth.go` — `RequireAdminKey(key)` Fiber middleware (already existed, verified correct)
- `api/internal/http/handlers/events.go`:
  - `GET /api/events` — returns all events ordered by event_time DESC; optional bbox filter via `?minLon=&minLat=&maxLon=&maxLat=`
  - `POST /api/events` [admin] — inserts event, publishes `{"type":"event",...}` to Redis `channel:events`
  - `DELETE /api/events/:id` [admin] — deletes by UUID, returns 404 if not found
- `api/internal/redis/subscriber.go` — two improvements:
  - Added `Publisher` interface + `Client` struct so the events handler can publish to Redis
  - Fixed reconnect: subscriber now loops with exponential backoff (1s→30s) on channel close instead of exiting permanently
  - Added `"event"` dispatch case → `hub.BroadcastAll`
- `api/main.go` — wired events routes with adminAuth middleware; creates Redis client for publishing

### Frontend (frontend/src/)
- `store/events.store.ts` — Zustand store for MapEvent[]; `setEvents` (REST load) + `addEvent` (WS live)
- `hooks/useEntityStream.ts` — now dispatches `"event"` WS messages to events store
- `map/layers/EventLayer.tsx` — fetches REST on mount; reads events store; red ScatterplotLayer (8km radius)
- `map/SituationMap.tsx` — EventLayer added (renders between gpsJam and ships)
- `types/entities.ts` — WsMessage union extended with `{ type: "event"; event: MapEvent }`

## Step 10 Post-Review Fixes (2026-04-06)
- `frontend/package.json`: `satellite.js` pinned to `^4.1.3` (valid published version; fixes Docker/frontend build failure).
- `api/internal/http/handlers/events.go`: strict bbox parsing with `strconv.ParseFloat`; now returns:
  - `400 {"error":"minLon must be a number"}` for non-numeric bbox values
  - `400 {"error":"bbox requires all four params: minLon, minLat, maxLon, maxLat"}` for partial bbox
- `api/pkg/schema/schema.go`: `RedisMessage` now documents/represents `type:"event"` with `Event *Event`.
- `api/internal/redis/subscriber.go`: package comments updated to reflect `event` payload source and behavior.
- `frontend/src/map/SituationMap.tsx`: temporary `any` typing workaround added for Deck.gl v9 `onViewStateChange` type narrowing (runtime-safe; type cleanup can be done in Step 12).

### Re-Verification Run (2026-04-06)
- `docker compose --profile app build frontend` → PASS
- `docker compose --profile app build api` → PASS
- `curl -i /api/events?minLon=abc&minLat=45&maxLon=20&maxLat=55` → 400
- `curl -i /api/events?minLon=10` → 400
- `curl -i /api/events` → 200 `[]`

## Step 9 Resolution (2026-04-06)
CelesTrak GROUP endpoint returns HTTP 403 for this host (CDN/IP-level block).
Worker auto-falls back to tle.ivanstanojevic.me paginated JSON API.
11,524 Starlink TLEs fetched in ~40s. Gate: PASS.

## Step 11 — Nginx + Full Integration (2026-04-06)

Files created:
- `nginx/nginx.conf` — upstream blocks for `api` (situationroom-api:8080) and `frontend` (situationroom-frontend:80); routes `/api/*` and `/ws` to Go, `/` to frontend
- `nginx/Dockerfile` — `FROM nginx:alpine`, copies `nginx.conf`

Verified at `http://localhost` (port 80):
- `GET /api/health` → 200
- `GET /api/events` → 200 `[]`
- `GET /api/satellites/tles` → 16,135 TLE rows at verification time (dataset is dynamic)
- `GET /api/gpsjam/current` → 46,198 hex rows
- `GET /` → 200 HTML (React app)
- `GET /ws` (with upgrade headers) → 101 Switching Protocols

## Skills System — Added 2026-04-08

### What changed
- Created `skills/` directory with 4 operational skills:
  - `skills/runtime-gate/SKILL.md` — pre-push and end-of-step service verification
  - `skills/incident-triage/SKILL.md` — systematic failure diagnosis across all components
  - `skills/schema-drift/SKILL.md` — Python/Go/TypeScript data structure comparison
  - `skills/ui-regression/SKILL.md` — Playwright-based frontend smoke testing
- Created `skills/README.md` — top-level index with usage guide
- Updated `SKILL.md` — added Skills System section with table and recommended sequence
- Playwright smoke tests already set up at `e2e/smoke.spec.ts` (4 tests, all passing)

### What was validated
- All 4 skill files contain real commands, real file paths, real repo structure
- Playwright tests run and pass: `npx playwright test e2e/smoke.spec.ts` → 4 passed
- Schema drift checker references the actual schema files and known intentional differences
- Runtime gate commands match existing gate scripts and API endpoints

### What still needs validation
- Runtime Gate: run the full sequence with production stack up to confirm all endpoints respond
- Incident Triage: will be validated organically when something next breaks
- Schema Drift: run a manual field comparison to confirm no current drift exists
- Skills integration: confirm a full end-of-step handoff using the recommended skill sequence

### Next command
```bash
npx playwright test e2e/smoke.spec.ts
```

## Next Steps
Step 12: UI Polish
  - `LayerToggle.tsx` — visible toggle buttons on the map
  - `EntityPopup.tsx` — click any entity → metadata popup
  - AircraftLayer → IconLayer with directional icon (rotates to heading_deg)
  - Fix `onViewStateChange` any-cast in SituationMap.tsx (use `ViewStateChangeParameters`)

## Required Local Env (minimum)
Create root `.env` from `.env.example` and set:
- `OPENSKY_CLIENT_ID`
- `OPENSKY_CLIENT_SECRET`
- `AISSTREAM_API_KEY`
- `ADMIN_KEY`
- `POSTGRES_PASSWORD` (or local default)

## Dev Run Commands
From repo root:
```bash
docker compose --profile app up -d db redis api workers
curl -s http://localhost:8080/api/health
curl -s http://localhost:8080/api/events
```

From `frontend/`:
```bash
npm install
npm run dev
```

Open: `http://localhost:5173`

Post a test event:
```bash
curl -s -X POST http://localhost:8080/api/events \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -d '{"event_time":"2026-04-06T22:00:00Z","lat":48.5,"lon":14.2,"event_type":"strike","title":"Test"}'
```

## Step Gates
```bash
scripts/check-step8.sh
scripts/check-step9.sh
scripts/check-prepush.sh step9
```

## Known Environment Notes
- Run commands in WSL/Ubuntu terminal (not Windows PowerShell).
- If API is unreachable on `:8080`, verify `ADMIN_KEY` is set in `.env`.
- Frontend: run `npm install` after any new layer is added.
- CelesTrak GROUP endpoint blocked on this host; fallback to tle.ivanstanojevic.me is automatic.

## Git / Remote
- Repo: `https://github.com/utiz23/Situation-Room.git`
- Local branch: `main`

## Security Notes
- Never commit `.env`.
- Rotate any credential immediately if exposed.
