# Skill: Schema Drift Checker

## Purpose

Detect mismatches between the three places where data structures are defined:

1. **Python** — `workers/common/schema.py` (Pydantic models)
2. **Go** — `api/pkg/schema/schema.go` (structs with JSON tags)
3. **TypeScript** — `frontend/src/types/entities.ts` and `frontend/src/types/layers.ts` (interfaces)

If these files disagree on field names, types, or required/optional status, data will silently break at runtime — a field might be missing from the API response, or the frontend might expect a field the backend doesn't send.

Think of this like checking that three copies of a form all have the same fields in the same order.

## When to Use

- After adding or renaming a field in any schema file.
- After adding a new data type (e.g., a new layer or entity type).
- Before marking an implementation step as done.
- When debugging "the data shows up in the API but not on the map" issues.

## Inputs

- Access to the three schema files listed above.
- Understanding of which data type you're checking (NormalizedEntity, Event, JammingHex, TLERecord).

## Schema File Locations

| Data type | Python | Go | TypeScript |
|---|---|---|---|
| NormalizedEntity | `workers/common/schema.py` | `api/pkg/schema/schema.go` | `frontend/src/types/entities.ts` |
| Event | `workers/common/schema.py` | `api/pkg/schema/schema.go` | `frontend/src/types/layers.ts` (MapEvent) |
| JammingHex | `workers/common/schema.py` | `api/pkg/schema/schema.go` | `frontend/src/types/layers.ts` |
| TLERecord | `workers/common/schema.py` | `api/pkg/schema/schema.go` | `frontend/src/types/layers.ts` |
| RedisMessage | `workers/common/schema.py` (implicit) | `api/pkg/schema/schema.go` | `frontend/src/types/entities.ts` (WsMessage) |
| CreateEventRequest | — | `api/pkg/schema/schema.go` | `frontend/src/types/layers.ts` (CreateEventPayload) |

## Steps

### Step 1 — Pick the data type to check

Decide which struct/model/interface you're verifying. The most common ones:
- `NormalizedEntity` — the most critical, since it crosses all three layers
- `Event` / `MapEvent` — if you changed events
- `TLERecord` — if you changed satellite data
- `JammingHex` — if you changed GPS jamming data

### Step 2 — Extract field lists

For each data type, extract the field names and their JSON keys from all three files.

**Python** (Pydantic uses the Python field name as the JSON key by default):
```bash
grep -E "^\s+\w+:" workers/common/schema.py
```

**Go** (the JSON key is in the `json:"..."` tag):
```bash
grep -E 'json:"' api/pkg/schema/schema.go
```

**TypeScript** (the property name is the JSON key):
```bash
grep -E "^\s+\w+[\?]?:" frontend/src/types/entities.ts frontend/src/types/layers.ts
```

### Step 3 — Compare field-by-field

For each data type, build a comparison table:

| JSON field | Python | Go | TypeScript | Match? |
|---|---|---|---|---|
| `id` | `id: str` | `ID string json:"id"` | `id: string` | Yes |
| `lat` | `lat: float` | `Lat float64 json:"lat"` | `lat: number` | Yes |
| ... | ... | ... | ... | ... |

**Check for these mismatches:**

1. **Missing field** — exists in one language but not another.
2. **Wrong JSON key** — Go uses `json:"entity_type"` but TypeScript uses `entityType`.
3. **Type mismatch** — Python says `int` but Go says `string`.
4. **Required vs optional** — Python says `Optional[str]` but TypeScript says `string` (not optional).
5. **Literal/enum mismatch** — Python says `Literal["adsb", "ais"]` but TypeScript allows `"satellite"` too.

### Step 4 — Check DB migration alignment

The database columns should match the schema. For each data type, compare against its migration:

```bash
# Events table
cat db/migrations/003_events_table.sql

# Entity positions table
cat db/migrations/002_entities_table.sql

# GPS jamming table
cat db/migrations/004_gpsjam_table.sql

# Satellites table
cat db/migrations/005_satellites_table.sql
```

**Check:** Do the SQL column names match the JSON field names? Do the SQL types match (e.g., `DOUBLE PRECISION` ↔ `float64` ↔ `number`)?

### Step 5 — Report findings

List every mismatch found. For each, state:
- Which field
- Which files disagree
- What the correct value should be (based on what the API actually sends)

## Known Intentional Differences

These are NOT bugs — they are documented design choices:

- **Python `NormalizedEntity.source`** includes `"satellite"` as a literal value, but Python workers never produce satellite entities. The `"satellite"` source is only used client-side (TypeScript Web Worker).
- **Python `Event.id`** is `Optional[UUID]` (None before DB insert). Go `Event.ID` is `uuid.UUID` (always set in API responses). TypeScript `MapEvent.id` is `string`. These are all correct for their contexts.
- **TypeScript `MapEvent`** is named differently from Python/Go `Event`. This is intentional to avoid collision with the DOM `Event` type in TypeScript.
- **Go `JammingHex.Date`** is `string` (not `time.Time`) because the API serves it as `"YYYY-MM-DD"`. Python uses `date`. TypeScript uses `string`. All correct.

## Expected Output (no drift)

```
Schema Drift Check — [DATE]
Checked: NormalizedEntity, Event, JammingHex, TLERecord

NormalizedEntity: 10 fields — Python ✓, Go ✓, TypeScript ✓
Event:            10 fields — Python ✓, Go ✓, TypeScript ✓
JammingHex:        3 fields — Python ✓, Go ✓, TypeScript ✓
TLERecord:         6 fields — Python ✓, Go ✓, TypeScript ✓

No drift detected.
```

## Failure Handling

If drift is found:
1. Determine which file is "correct" — usually whichever matches what the API actually returns (test with `curl`).
2. Update the other files to match.
3. If the Go struct changed, rebuild the API: `docker compose --profile app build api`
4. If the Python schema changed, rebuild workers: `docker compose --profile app build workers`
5. If the TypeScript interface changed, check the frontend build: `cd frontend && npm run build`
6. Re-run this skill to confirm the drift is fixed.

## Guardrails

- Do NOT change JSON field names in Go structs without updating Python and TypeScript — this breaks the live data pipeline.
- Do NOT remove the `omitempty` tag from Go optional fields — this would send `null` values to the frontend and break rendering.
- When adding a new field, add it to ALL THREE files in the same commit.

## Handoff Format

Add this block to `PROJECT_STATUS.md`:

```markdown
## Schema Drift Check — [DATE]
- Types checked: [list]
- Drift found: [yes/no]
- Details: [which field, which files, description]
- Fix applied: [what was changed]
- Verified: [build + API test pass]
```

## Example

### Invocation

"I just added a `flag_country` field to the NormalizedEntity in Python. Let me check if the other files match."

```bash
grep "flag_country" workers/common/schema.py
grep "flag_country" api/pkg/schema/schema.go
grep "flag_country" frontend/src/types/entities.ts
```

### Example Output Summary

```
## Schema Drift Check — 2026-04-07
- Types checked: NormalizedEntity
- Drift found: yes
- Details: `flag_country` exists in Python (schema.py:48) but missing from Go (schema.go) and TypeScript (entities.ts)
- Fix applied: added `FlagCountry *string json:"flag_country,omitempty"` to Go, `flag_country?: string` to TypeScript
- Verified: `docker compose --profile app build api` → PASS, `npm run build` → PASS
```
