# SituationRoom Skill Guide

Purpose: standardize how agents and humans execute work in this repo so context, testing, and handoff are consistent.

## Core Rules
- Treat `PROJECT_STATUS.md` as the handoff source of truth.
- Implementation and review roles are split:
  - Claude: coding changes.
  - Codex: review/debug/test verification and status updates.
- No push without passing step gate checks.

## Required End-of-Step Handoff
Update `PROJECT_STATUS.md` with:
- What changed
- What passed
- What failed
- Current blocker (if any)
- Next exact command

Use template: `templates/PROJECT_STATUS_TEMPLATE.md`

## Command Standards
Run from WSL/Ubuntu terminal.

Backend/services:
```bash
docker compose --profile app up -d db redis api workers
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

## Step Gates
- Step 8 gate: `scripts/check-step8.sh`
- Step 9 gate: `scripts/check-step9.sh`
- Pre-push gate wrapper: `scripts/check-prepush.sh <step8|step9|all>`

## MCP Workflow (Operational)
MCP is optional but recommended for persistence across agents.

Track these state items per step:
- `step_id`
- `status` (`in_progress`, `blocked`, `done`)
- `last_verified_at` (UTC)
- `known_blockers`
- `last_green_commands`

Mirror MCP state summary into `PROJECT_STATUS.md` at handoff time.
