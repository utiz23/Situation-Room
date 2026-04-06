# SituationRoom — Project Status

Last updated: 2026-04-06

## Current State
- Steps 1-6 are implemented.
- Dev map is working at `http://localhost:5173`.
- Live aircraft are visible as cyan dots and update over time.

## Confirmed Working
- ADS-B worker uses OpenSky OAuth2 client-credentials flow (not basic auth).
- Worker publishes updates/removes to Redis and batches DB inserts.
- Go API + WebSocket are running with viewport filtering.
- Frontend connects via Vite proxy (`/api`, `/ws`) and renders aircraft layer.

## Required Local Env
Create a root `.env` file (copy from `.env.example`) and set at minimum:
- `OPENSKY_CLIENT_ID`
- `OPENSKY_CLIENT_SECRET`
- `ADMIN_KEY`
- `POSTGRES_PASSWORD` (or keep default for local dev)
- `ADSB_BBOX` (currently tested with `40,-5,55,15`)

## Dev Run Commands
From repo root:

```bash
docker compose --profile app up -d db redis workers api
docker compose --profile app ps
curl -s http://localhost:8080/api/health
curl -s http://localhost:8080/api/entities | head -c 400
```

From `frontend/`:

```bash
npm install
npm run dev
```

Open: `http://localhost:5173`

## Common Failure Modes
- API restart loop + `localhost:8080` connection refused:
  - Usually `ADMIN_KEY` missing in `.env`.
- Worker says `anonymous access`:
  - OAuth env vars not set/injected.
- Worker token error `401 unauthorized_client`:
  - `OPENSKY_CLIENT_SECRET` is wrong (must be actual client secret, not role label).

## Security Notes
- Never commit `.env`.
- If any credential was printed/shared, rotate it immediately.

## Next Planned Step
- Step 7: AIS worker (ships), then add ship layer to frontend.
