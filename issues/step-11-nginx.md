# Step 11: Nginx integration for unified production routing

## Goal
Add an Nginx reverse proxy so that in production mode (`docker compose --profile app up`), a single `http://localhost` entry point routes traffic to the correct backend service.

## Requirements
- Serve the built React frontend (static files) from Nginx
- Proxy `/api/*` requests to the Go API gateway
- Proxy `/ws` WebSocket connections to the Go API gateway (with upgrade headers)
- Health check at `GET /api/health` must pass through
- Add `nginx.conf` and a Dockerfile (or use the official image with a config mount)
- Update `compose.yml` with the nginx service under the `app` profile

## Acceptance Criteria
- [ ] `curl -si http://localhost/` returns the React app HTML
- [ ] `curl -si http://localhost/api/health` returns `200 OK`
- [ ] `curl -si http://localhost/api/events` returns events JSON
- [ ] WebSocket upgrade at `ws://localhost/ws` succeeds
- [ ] All existing dev-mode workflows still work unchanged
