# SituationRoom

An open-source live geospatial intelligence platform. Think of it as a radar screen for the world — it pulls real data from the internet and plots it on an interactive map in real time.

---

## What It Shows

| Layer | What you see |
|---|---|
| Aircraft | Live flight positions from ADS-B transponders (the same signals air traffic control uses) |
| Ships | Live vessel positions from AIS radio signals |
| Satellites | Real-time orbital positions of satellite constellations (Starlink, etc.) |
| GPS Jamming | Zones where GPS navigation interference has been detected |
| Events | Manually pinned incidents — strikes, explosions, military movements |

---

## How It Works (Simple Version)

External data sources broadcast information continuously (aircraft positions, ship locations, etc.). Python scripts pick up that data, clean it, and relay it to a database and a fast message bus. A Go server picks up those messages and streams them to your browser over a live connection. Your browser draws everything on a 3D map using GPU-accelerated rendering.

---

## Prerequisites

Before you can run this project, you need to install:

1. **Docker Desktop** — [Download here](https://www.docker.com/products/docker-desktop/)
   - This runs the database, cache, and backend services
   - After installing, make sure it's running (you'll see a whale icon in your taskbar)

2. **Node.js (v20 or later)** — [Download here](https://nodejs.org/)
   - This runs the frontend map interface
   - After installing, verify with: `node --version`

3. **Go (v1.23 or later)** — [Download here](https://go.dev/dl/)
   - This is used to build the API server
   - After installing, verify with: `go version`

4. **Git** — [Download here](https://git-scm.com/)
   - Used to download the project code
   - After installing, verify with: `git --version`

---

## Setup (Dev Mode)

> **What is "dev mode"?** It's the setup you use while building and testing. It's faster to work with than the full production setup.

### Step 1: Copy environment variables

```bash
cp .env.example .env
```

> This creates a `.env` file where you'll put your API keys and settings. The `.example` file is just a template — the real one is `.env`.

Open `.env` and fill in:
- `AISSTREAM_API_KEY` — free at [aisstream.io](https://aisstream.io/)
- `OPENSKY_USERNAME` / `OPENSKY_PASSWORD` — free at [opensky-network.org](https://opensky-network.org/) (optional but recommended)
- `ADMIN_KEY` — make up a secret password for submitting events (e.g., `mysecretkey123`)

### Step 2: Start the database and cache

```bash
docker compose up db redis -d
```

> This starts TimescaleDB (the database) and Redis (the message relay) in the background. The `-d` flag means "detached" — it runs quietly without taking over your terminal.

### Step 3: Run database migrations

```bash
docker compose run --rm db-migrate
```

> "Migrations" are SQL scripts that create the tables in the database. Like setting up the filing cabinets before you start storing files.

### Step 4: Start the API server

```bash
cd api
go run .
```

> This starts the Go backend server on port 8080.

### Step 5: Start the frontend

Open a new terminal window, then:

```bash
cd frontend
npm install
npm run dev
```

> `npm install` downloads all the JavaScript libraries the frontend needs (only needed once). `npm run dev` starts the map interface.

### Step 6: Open the app

Go to **http://localhost:5173** in your browser. You should see the map.

---

## Full Production Stack

To run everything in Docker (no need for local Node.js or Go):

```bash
docker compose --profile app up
```

Then go to **http://localhost**.

---

## Project Structure

```
SituationRoom/
├── frontend/     # The map interface (React + TypeScript)
├── api/          # The backend server (Go)
├── workers/      # Data fetching scripts (Python)
├── db/           # Database setup files (SQL)
├── nginx/        # Web server config (production only)
├── compose.yml   # Starts all services with Docker
└── .env.example  # Template for your API keys
```

---

## Architecture

See [dazzling-twirling-marshmallow.md](dazzling-twirling-marshmallow.md) for the full technical implementation plan.

---

## Data Sources

| Data | Source | Cost |
|---|---|---|
| Ship positions | [AISStream.io](https://aisstream.io/) | Free (API key required) |
| Flight positions | [OpenSky Network](https://opensky-network.org/) | Free (account recommended) |
| Satellite TLEs | [CelesTrak](https://celestrak.org/) | Free |
| GPS jamming | [GPSJam.org](https://gpsjam.org/) | Free |
| Map tiles | [OpenFreeMap](https://openfreemap.org/) | Free |

---

## Status

Currently in **Phase 1 development** — see [dazzling-twirling-marshmallow.md](dazzling-twirling-marshmallow.md) for the build plan.
