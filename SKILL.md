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

## Skills System

Reusable, step-by-step procedures for common development tasks. Each skill lives in `skills/<name>/SKILL.md`.

| Skill | Folder | When to use |
|---|---|---|
| Runtime Gate | `skills/runtime-gate/` | Before push, after config changes, end-of-step verification |
| Incident Triage | `skills/incident-triage/` | When any service is down or returning errors |
| Schema Drift Checker | `skills/schema-drift/` | After modifying data structures in Python, Go, or TypeScript |
| UI Regression | `skills/ui-regression/` | After frontend changes, before marking a step done |

Full index: `skills/README.md`

### Using a skill

1. Open the skill's `SKILL.md` and follow the steps in order.
2. Record the result in `PROJECT_STATUS.md` using the handoff format at the bottom of each skill.
3. If a skill fails, follow its failure handling section before escalating.

### Recommended skill sequence for end-of-step handoff

1. Run **Runtime Gate** — confirm all services and APIs are green.
2. Run **Schema Drift Checker** — if any data structures were changed in this step.
3. Run **UI Regression** — if any frontend code was changed.
4. Update `PROJECT_STATUS.md` with results from all skills run.

## MCP Workflow (Operational)
MCP is optional but recommended for persistence across agents.

Track these state items per step:
- `step_id`
- `status` (`in_progress`, `blocked`, `done`)
- `last_verified_at` (UTC)
- `known_blockers`
- `last_green_commands`

Mirror MCP state summary into `PROJECT_STATUS.md` at handoff time.
