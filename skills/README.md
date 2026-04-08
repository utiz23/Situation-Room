# SituationRoom Skills

Skills are reusable, step-by-step procedures that Claude (or a human) can follow to perform common development tasks in this repo. Each skill lives in its own folder with a `SKILL.md` file.

## Available Skills

| Skill | Folder | Purpose |
|---|---|---|
| Runtime Gate | `skills/runtime-gate/` | Verify all services are running and API endpoints respond correctly |
| Incident Triage | `skills/incident-triage/` | Diagnose which component is broken when something fails |
| Schema Drift Checker | `skills/schema-drift/` | Detect mismatches between Python, Go, and TypeScript data definitions |
| UI Regression | `skills/ui-regression/` | Verify the frontend loads, renders the map, and shows expected UI elements |

## How to Use a Skill

1. Open the skill's `SKILL.md` file.
2. Follow the steps in order.
3. Record the result in `PROJECT_STATUS.md` using the format shown in each skill.

## When to Use Skills

- **Runtime Gate**: before pushing code, after changing Docker config, after pulling new code.
- **Incident Triage**: when any service is down, an API returns errors, or the frontend won't load.
- **Schema Drift Checker**: after modifying data structures in any layer (Python, Go, or TypeScript).
- **UI Regression**: after frontend changes, before marking a step as done.

## Skill Format

Every `SKILL.md` follows the same structure:

```
Purpose        — what this skill does
When to use    — trigger conditions
Inputs         — what you need before starting
Steps          — numbered, concrete commands
Expected output — what success looks like
Failure handling — what to do when something fails
Handoff format — how to record results in PROJECT_STATUS.md
Example        — one invocation + one output summary
```

## Adding New Skills

1. Create a folder under `skills/` with a descriptive name.
2. Add a `SKILL.md` following the format above.
3. Add a row to the table in this README.
4. Reference it from the root `SKILL.md` if appropriate.
