# Skill: Runtime Gate

## Purpose

Verify that the full SituationRoom stack is running correctly: all Docker containers are healthy, every API endpoint returns the expected response, and step gate scripts pass.

Think of this as a "pre-flight checklist" — run it before pushing code or marking a step as done.

## When to Use

- Before pushing code to the remote.
- After changing `compose.yml`, Dockerfiles, or nginx config.
- After pulling new code from the remote.
- At the end of any implementation step (Steps 1–12).
- When you want a quick "is everything still working?" check.

## Inputs

- Docker Desktop must be running.
- The WSL/Ubuntu terminal must be open.
- You should be in the repo root: `/home/michal/projects/SituationRoom`

## Steps

### Step 1 — Check container status

```bash
docker compose --profile app ps
```

**What to look for:** Every container should show `Up` or `running`. If any show `Exited` or `Restarting`, note which one — that's your first clue.

Expected containers (production mode):
- `db` (TimescaleDB)
- `redis`
- `api` (Go gateway)
- `workers` (Python ingest)
- `frontend` (React build served by its own container)
- `nginx` (reverse proxy)

### Step 2 — Health check

```bash
curl -si http://localhost/api/health
```

**Expected:** `HTTP/1.1 200 OK` with a JSON body. If this fails, the API or nginx is down.

Dev mode alternative (no nginx):
```bash
curl -si http://localhost:8080/api/health
```

### Step 3 — API endpoint checks

Run all of these. Each should return `200` with JSON data:

```bash
# Events endpoint (may return empty array if no events posted)
curl -s -o /dev/null -w "%{http_code}" http://localhost/api/events
echo ""

# GPS jamming hexes
curl -s http://localhost/api/gpsjam/current | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'gpsjam rows: {len(d)}')"

# Satellite TLEs
curl -s http://localhost/api/satellites/tles | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'satellite rows: {len(d)}')"
```

**Expected:** Events returns `200`. GPS jam returns a positive row count. Satellites returns a positive row count.

### Step 4 — WebSocket check

```bash
curl -si -H "Upgrade: websocket" -H "Connection: Upgrade" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Sec-WebSocket-Version: 13" \
  http://localhost/ws
```

**Expected:** `HTTP/1.1 101 Switching Protocols`. If you get `502` or `Connection refused`, the Go API WebSocket handler or nginx proxy is misconfigured.

### Step 5 — Step gate scripts

Run the gate script for the current step (if one exists):

```bash
# Step 8 gate (GPS jamming)
scripts/check-step8.sh

# Step 9 gate (satellites)
scripts/check-step9.sh

# Pre-push wrapper (runs all gates)
scripts/check-prepush.sh all
```

Each script prints `PASS` or `FAIL`. Stop and investigate any `FAIL`.

### Step 6 — Frontend build check (if applicable)

```bash
cd frontend && npm run build 2>&1 | tail -5
```

**Expected:** No TypeScript errors, output ends with build stats. If it fails, there's a type error or missing dependency.

## Expected Output (all green)

```
[containers]  all 6 Up
[health]      200 OK
[events]      200
[gpsjam]      rows > 0
[satellites]  rows > 0
[websocket]   101 Switching Protocols
[gate]        PASS
[build]       no errors
```

## Failure Handling

| Symptom | Likely cause | First action |
|---|---|---|
| Container shows `Exited` | Crash on startup | `docker compose logs <service> --tail=50` |
| Health returns `502` | API not started yet or crashed | Check api logs: `docker compose logs api --tail=50` |
| gpsjam rows = 0 | Worker hasn't run yet or DB empty | Check worker logs: `docker compose logs workers --tail=80` |
| satellite rows = 0 | CelesTrak blocked or worker error | Check worker logs, verify fallback API |
| WebSocket returns `502` | nginx not proxying `/ws` | Check `nginx/nginx.conf` upstream block |
| Build fails | TypeScript error | Read the error message, fix the type |

## Guardrails

- Do NOT push if any gate script returns FAIL.
- Do NOT skip the WebSocket check — it catches nginx misconfig silently.
- If any row count is 0, that means the worker for that data source hasn't completed. Wait 60 seconds and retry before reporting a failure.

## Handoff Format

Add this block to `PROJECT_STATUS.md` under `## Verified Working Now`:

```markdown
## Runtime Gate — [DATE]
- Containers: [all up / X down]
- Health: [200 / fail]
- Events API: [200 / fail]
- GPS Jam rows: [count]
- Satellite rows: [count]
- WebSocket: [101 / fail]
- Gate scripts: [PASS / FAIL — which]
- Frontend build: [clean / errors]
- Verdict: [PASS / FAIL]
```

## Example

### Invocation

```bash
docker compose --profile app ps
curl -si http://localhost/api/health
curl -s -o /dev/null -w "%{http_code}" http://localhost/api/events
curl -s http://localhost/api/gpsjam/current | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'gpsjam rows: {len(d)}')"
curl -s http://localhost/api/satellites/tles | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'satellite rows: {len(d)}')"
scripts/check-prepush.sh all
```

### Example Output Summary

```
## Runtime Gate — 2026-04-07
- Containers: all 6 up
- Health: 200 OK
- Events API: 200
- GPS Jam rows: 46,198
- Satellite rows: 16,135
- WebSocket: 101 Switching Protocols
- Gate scripts: PASS (step8, step9)
- Frontend build: clean
- Verdict: PASS
```
