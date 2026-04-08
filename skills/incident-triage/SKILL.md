# Skill: Incident Triage

## Purpose

Systematically diagnose which component is broken when something in the SituationRoom stack isn't working. Instead of guessing, this skill walks through each layer (Docker → DB → Redis → API → Workers → Frontend) to isolate the failure.

Think of this like a doctor's checklist — start with vital signs, then narrow down to the specific organ.

## When to Use

- A page won't load or shows a blank screen.
- An API endpoint returns an error or no data.
- The map loads but a data layer is empty.
- Docker containers keep restarting.
- After a `docker compose down` / `up` cycle where something stopped working.

## Inputs

- Docker Desktop must be running.
- You should be in the repo root: `/home/michal/projects/SituationRoom`
- Know which symptom triggered the triage (blank page, 502 error, empty layer, etc.).

## Steps

### Step 1 — Container health (is everything running?)

```bash
docker compose --profile app ps
```

**What to look for:**
- All containers should say `Up`. Write down any that say `Exited`, `Restarting`, or are missing.
- If a container is missing, it may not have been started: `docker compose --profile app up -d`

**If a container shows `Exited`:**
```bash
docker compose logs <service-name> --tail=50
```
Replace `<service-name>` with: `db`, `redis`, `api`, `workers`, `frontend`, or `nginx`.

### Step 2 — Database check (is TimescaleDB alive?)

```bash
docker compose exec -T db psql -U situationroom -d situationroom -c "SELECT 1 AS alive;"
```

**Expected:** A table with `alive = 1`. If this fails, the database container is down or misconfigured.

Check that tables exist:
```bash
docker compose exec -T db psql -U situationroom -d situationroom -c "\dt"
```

**Expected tables:** `entity_positions`, `events`, `gpsjam_hexes`, `satellite_tles`

Check row counts for key tables:
```bash
docker compose exec -T db psql -U situationroom -d situationroom -c "
  SELECT 'entity_positions' AS tbl, count(*) FROM entity_positions
  UNION ALL
  SELECT 'events', count(*) FROM events
  UNION ALL
  SELECT 'gpsjam_hexes', count(*) FROM gpsjam_hexes
  UNION ALL
  SELECT 'satellite_tles', count(*) FROM satellite_tles;
"
```

### Step 3 — Redis check (is the message bus alive?)

```bash
docker compose exec -T redis redis-cli ping
```

**Expected:** `PONG`. If this fails, Redis is down.

Check if there are active subscriptions (shows the Go API is listening):
```bash
docker compose exec -T redis redis-cli pubsub channels '*'
```

**Expected:** At least `channel:entities` and `channel:events` should appear if the API is running and subscribed.

### Step 4 — API check (is the Go server responding?)

```bash
curl -si http://localhost/api/health
```

**If 502 / connection refused:**
```bash
docker compose logs api --tail=50
```

Look for:
- `listen on :8080` — means the server started successfully
- `panic:` or `fatal:` — means it crashed (read the error)
- `dial tcp ... connection refused` — means it can't reach DB or Redis

### Step 5 — Worker check (are Python workers running?)

```bash
docker compose logs workers --tail=80
```

**What to look for:**
- `[adsb]` lines — ADS-B aircraft ingest
- `[ais]` lines — AIS ship ingest
- `[gpsjam]` lines — GPS jamming ingest
- `[satellites]` lines — TLE ingest
- `ERROR` or `Exception` lines — something broke

**If a specific worker isn't producing data:**
```bash
# Check if the worker process is actually running inside the container
docker compose exec -T workers ps aux
```

### Step 6 — Frontend check (is the UI serving?)

**Production mode (via nginx):**
```bash
curl -si http://localhost/ | head -5
```

**Expected:** `HTTP/1.1 200 OK` with HTML content containing `<div id="root">`.

**Dev mode:**
```bash
curl -si http://localhost:5173/ | head -5
```

If both fail, the frontend isn't built or the dev server isn't running.

**Check for JavaScript build errors:**
```bash
cd frontend && npm run build 2>&1 | tail -10
```

### Step 7 — Isolate the layer

Based on Steps 1–6, identify which component is the root cause:

| Symptom | Failed step | Root cause |
|---|---|---|
| Everything down | Step 1 | Docker not running or compose not started |
| API errors, DB alive | Step 4 | Go API crash — read api logs |
| API healthy, no data | Step 5 | Worker not ingesting — read worker logs |
| Map loads, layer empty | Step 5 + Step 2 | Worker ran but DB is empty, or API query wrong |
| Blank page | Step 6 | Frontend build broken or not served |
| 502 on everything | Step 1 + Step 4 | nginx can't reach api — check upstream config |

## Expected Output (healthy system)

```
[containers]   all Up
[db]           alive, 4 tables present
[redis]        PONG, channels active
[api]          200 OK on /api/health
[workers]      all 4 feeds logging normally
[frontend]     200 OK on /
[diagnosis]    system healthy — no issue found
```

## Failure Handling

- If the root cause is a **crashed container**: read the last 50 lines of its logs, fix the issue, then `docker compose --profile app up -d <service>` to restart just that one.
- If the root cause is **missing data**: check if the worker ran at all (logs), then check if the external data source is reachable (CelesTrak, OpenSky, AISStream, GPSJam).
- If the root cause is **a code change you made**: use `git diff` to see what changed and revert if needed.
- If you can't determine the root cause: capture the full output of Steps 1–6 and paste it into `PROJECT_STATUS.md` under a `## Triage Log` section.

## Guardrails

- Do NOT restart all containers as a first step — diagnose first, then restart only what's broken.
- Do NOT delete database volumes (`docker compose down -v`) unless you're certain the data is corrupted. This destroys all ingested data.
- Always check logs BEFORE making changes. The error message usually tells you exactly what's wrong.

## Handoff Format

Add this block to `PROJECT_STATUS.md`:

```markdown
## Incident Triage — [DATE]
- Trigger: [what symptom was observed]
- Containers: [status]
- DB: [alive/down, table count, row summary]
- Redis: [PONG/down, channel list]
- API: [status code or error]
- Workers: [which feeds active, any errors]
- Frontend: [serving/down, build status]
- Root cause: [component + specific error]
- Fix applied: [what was done]
- Verified after fix: [yes/no + how]
```

## Example

### Invocation

User reports: "The satellite layer is empty on the map."

```bash
docker compose --profile app ps
docker compose exec -T db psql -U situationroom -d situationroom -c "SELECT count(*) FROM satellite_tles;"
docker compose logs workers --tail=80 | grep -i satellite
curl -s http://localhost/api/satellites/tles | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'rows: {len(d)}')"
```

### Example Output Summary

```
## Incident Triage — 2026-04-07
- Trigger: satellite layer empty on map
- Containers: all Up
- DB: alive, satellite_tles has 0 rows
- Redis: PONG, channels active
- API: 200 OK (returns empty array because DB is empty)
- Workers: satellite worker log shows "HTTP 403 from CelesTrak, falling back to tle.ivanstanojevic.me" then "ConnectionError: timeout"
- Root cause: workers — fallback TLE API timed out during ingest
- Fix applied: restarted workers container, fallback succeeded on retry
- Verified after fix: yes — satellite rows now 15,802, map layer populated
```
