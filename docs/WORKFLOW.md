# SituationRoom Workflow

## 1) Role Split
- Claude (coding agent): implement approved fixes/features.
- Codex (review/debug agent): review diffs, run runtime checks, identify blockers, update status docs.

## 2) Single Source of Truth
`PROJECT_STATUS.md` must be updated at end of each work session.

Required sections:
- Current state
- Step status
- Verified working
- Open issues
- Immediate debug focus
- Run commands

Template: `templates/PROJECT_STATUS_TEMPLATE.md`

## 3) Review Gate Before Push
Run a gate script for the step being shipped.

Examples:
```bash
scripts/check-step8.sh
scripts/check-step9.sh
scripts/check-prepush.sh step9
```

Push only when gate is green or blocker is explicitly documented.

## 4) Runtime-First Validation
Every step must prove:
- service/container starts
- logs show expected worker behavior
- DB has expected row presence
- API endpoint returns expected shape/content

## 5) MCP Usage Pattern
Use MCP as structured memory for handoff continuity.

Recommended step record fields:
- `step_id`
- `status`
- `last_verified_at`
- `known_blockers`
- `last_green_commands`

At handoff, sync MCP summary into `PROJECT_STATUS.md`.

## 6) Safety
- Never commit `.env`.
- Rotate credentials if exposed.
- Keep local-only tooling files (for example `.claude/settings.local.json`) out of release commits.
