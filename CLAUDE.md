# SituationRoom — Claude Instructions

## Communication Style

The user is a **total beginner to coding**. In every response:
- Define technical terms when they first appear. Example: instead of just saying "API", say "API (a way for two programs to talk to each other)".
- Use real-world analogies for abstract concepts.
- When showing a terminal command, explain what each part does.
- Never assume knowledge of any programming language, framework, or tool.
- Keep explanations short and concrete. Prefer examples over jargon.
- When something breaks, walk through the diagnosis — don't just hand over a fix without explaining what went wrong.

---

## What This Project Is

**SituationRoom** is an open-source map platform (like a live news map) that pulls in real data from the internet and shows it on an interactive globe. Think of it as a "radar screen" for world events.

It displays five live data layers:
1. **Ships** — real maritime vessel positions from AIS radio signals
2. **Aircraft** — real flight positions from ADS-B transponders
3. **Satellites** — live orbital positions of satellites (Starlink, etc.)
4. **GPS Jamming** — zones where GPS interference has been detected
5. **Events** — manually pinned incidents (strikes, explosions, military activity)

---

## Tech Stack (Plain English)

| Piece | What it is | Used for |
|---|---|---|
| **Docker** | A tool that packages apps into isolated "containers" so they run the same on any machine | Running the database, cache, and backend without installing them manually |
| **Docker Compose** | A tool to start multiple Docker containers at once with one command | Starting the whole stack: `docker compose up db redis` |
| **TimescaleDB** | A database (like Excel but for huge datasets) optimized for time-stamped location data | Storing ship/aircraft positions with timestamps |
| **PostGIS** | An add-on to the database that understands geography (lat/lon, distances, regions) | Spatial queries like "find all ships near this port" |
| **Redis** | An ultra-fast in-memory data store | Live message passing between backend services |
| **Go** | A programming language known for speed and handling many connections at once | The API server that talks to the browser |
| **Python** | A beginner-friendly programming language with great data libraries | Worker scripts that fetch and clean data from external APIs |
| **React** | A JavaScript framework for building interactive web UIs | The frontend map interface |
| **Vite** | A tool that bundles and serves the React app during development | Running the frontend locally with `npm run dev` |
| **MapLibre GL JS** | An open-source map renderer (like Google Maps but free and self-hosted) | Drawing the interactive globe basemap |
| **Deck.gl** | A GPU-powered data visualization library | Rendering thousands of ship/aircraft dots without lag |
| **Nginx** | A web server and traffic router | In production: routing browser requests to the right service |

---

## Current Build Status

We are on **Step 9 of 12** — GPS Jamming layer done, starting Satellite layer.

| Step | Status | What it is |
|---|---|---|
| 1. Scaffolding | ✓ Done | `compose.yml`, `.env.example`, `.gitignore` |
| 2. Database migrations | ✓ Done | SQL files that set up the database tables |
| 3. Shared schemas | ✓ Done | Data structure definitions used by all services |
| 4. ADS-B worker | ✓ Done | Python script that fetches aircraft data |
| 7. AIS worker | ✓ Done | WebSocket to AISStream, ship positions |
| 5. Go API gateway | ✓ Done | Backend server + WebSocket |
| 6. Frontend shell | ✓ Done | React map app |
| 7–12. Remaining layers | Pending | Ships, GPS jamming, satellites, events, UI polish |

Full plan: [dazzling-twirling-marshmallow.md](dazzling-twirling-marshmallow.md)

---

## Terminal Environment

**All commands must be run inside WSL/Ubuntu — not Windows PowerShell.**

WSL (Windows Subsystem for Linux) is a way to run Linux inside Windows. Your Docker, Node.js, Go, and Python tools all live there.

**How to open the WSL terminal:**
- In VS Code: bottom menu → Terminal → New Terminal → make sure it says "bash" or "Ubuntu" (not "PowerShell")
- In Windows Terminal: click the dropdown arrow → Ubuntu
- The prompt looks like: `username@computername:~$`

Docker Desktop runs on Windows but its engine is connected to WSL, so `docker compose` commands work from the WSL terminal once Docker Desktop is running.

---

## Common Commands

> Run these in the **WSL/Ubuntu terminal**, not PowerShell.

### Start the database and Redis (dev mode)
```bash
docker compose up db redis -d
```
> `-d` means "detached" — run in the background so the terminal stays usable.

### Run database migrations (set up the tables)
```bash
docker compose run --rm db-migrate
```
> `--rm` means "delete the temporary container when it's done".

### Stop everything
```bash
docker compose down
```

### Start the frontend (after `cd frontend`)
```bash
npm run dev
```
> This starts the map UI at http://localhost:5173 in your browser.

### Start the full production stack
```bash
docker compose --profile app up
```

### Check what containers are running
```bash
docker compose ps
```

---

## Deploy Modes

**Dev mode** (what you use while building):
- `docker compose up db redis api workers` — starts backend services in Docker
- `npm run dev` in the `frontend/` folder — starts the map UI on your machine
- Access at: `http://localhost:5173`

**Production mode** (full Docker stack):
- `docker compose --profile app up`
- Access at: `http://localhost`

---

## Architecture in One Paragraph

External websites (OpenSky for planes, AISStream for ships, CelesTrak for satellites) send data to Python worker scripts. Those workers clean and normalize the data, then push it into two places: a database (TimescaleDB) for permanent storage, and Redis (a fast message relay). A Go server picks up messages from Redis and streams them to the browser over a WebSocket (a live two-way connection). The browser runs a React app that draws the data on a MapLibre map using Deck.gl for GPU-accelerated rendering.

---

## Key Architectural Rules (do not violate)

- **Snapshots come from the database, never from Redis.** When a browser connects, the Go server queries TimescaleDB for recent positions. Redis is only for live fan-out.
- **Category A** (aircraft, ships) = streamed via WebSocket. **Category B** (GPS jamming, satellite TLEs, events) = fetched via REST API on demand.
- **Dev frontend runs on the host** (`npm run dev`), not inside Docker. The production Dockerfile does a full build.
- **`POST /api/events`** requires `Authorization: Bearer {ADMIN_KEY}` header. `GET /api/events` is public.
- **Health check** endpoint is `GET /api/health` (not `/health`) so Nginx routes it correctly.
