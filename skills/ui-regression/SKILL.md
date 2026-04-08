# Skill: UI Regression

## Purpose

Verify that the SituationRoom frontend loads correctly, the map renders, all layer toggle buttons appear, and no critical JavaScript errors occur. This catches visual regressions and broken builds before they reach production.

This skill uses two methods:
1. **Automated** — Playwright tests in `e2e/smoke.spec.ts` (fast, repeatable)
2. **Manual** — Playwright MCP browser tools (for visual inspection and screenshots)

## When to Use

- After any frontend code change (components, layers, stores, styles).
- After updating npm dependencies.
- Before marking a step as done.
- When a user reports "the map is blank" or "a layer isn't showing."

## Inputs

- The frontend dev server must be running, OR the full production stack must be up.
- Playwright must be installed: `npx playwright install chromium` (one-time setup).
- System libraries must be installed: `sudo npx playwright install-deps chromium` (one-time setup).

## Steps

### Method A — Automated (Playwright test suite)

#### Step 1 — Run the smoke tests

```bash
npx playwright test e2e/smoke.spec.ts
```

The Playwright config (`playwright.config.ts`) will auto-start the Vite dev server if it isn't already running.

**Expected output:**
```
  4 passed
```

#### Step 2 — Review failures (if any)

If tests fail, Playwright saves a screenshot in `test-results/`. Open the screenshot to see what the browser actually rendered:

```bash
ls test-results/
```

Each failure folder contains:
- `test-failed-1.png` — screenshot at the moment of failure
- `error-context.md` — error details

#### Step 3 — What the tests cover

| Test | What it checks |
|---|---|
| `map canvas loads` | Deck.gl canvas element is visible within 15 seconds |
| `all five layer toggle buttons are visible` | Aircraft, Ships, Satellites, GPS Jam, Events buttons present |
| `toggling a layer button changes its style` | Clicking Aircraft toggles the button's title attribute |
| `page has no console errors on load` | No critical JS errors (WebSocket errors are ignored since backend may not be running) |

### Method B — Manual (Playwright MCP browser tools)

Use this when you need to visually inspect the map or test interactions not covered by automated tests.

#### Step 1 — Open the app

Use the Playwright MCP `browser_navigate` tool:
```
Navigate to: http://localhost:5173
```

#### Step 2 — Take a screenshot

Use the Playwright MCP `browser_take_screenshot` tool to capture the current state.

#### Step 3 — Check the snapshot

Use the Playwright MCP `browser_snapshot` tool to get the accessibility tree. Verify:
- A `<canvas>` element exists (the map).
- Five `<button>` elements exist with the layer names.
- No error overlays or blank screens.

#### Step 4 — Test interactions

Use `browser_click` to click a layer toggle, then `browser_snapshot` again to verify the button state changed.

#### Step 5 — Check console

Use `browser_console_messages` to view any JavaScript errors.

## Test File Locations

| File | Purpose |
|---|---|
| `e2e/smoke.spec.ts` | Automated smoke tests |
| `playwright.config.ts` | Playwright configuration (auto-starts dev server) |
| `test-results/` | Screenshots from failed test runs |

## Expected Output (all passing)

```
UI Regression — [DATE]
Method: automated (Playwright)

  ✓ map canvas loads (X.Xs)
  ✓ all five layer toggle buttons are visible (X.Xs)
  ✓ toggling a layer button changes its style (X.Xs)
  ✓ page has no console errors on load (X.Xs)

  4 passed
```

## Failure Handling

| Symptom | Likely cause | Action |
|---|---|---|
| `canvas` not visible | Map library failed to load, or DeckGL error | Check console errors — likely a missing dependency or broken import |
| Buttons missing | `LayerToggle.tsx` broken or Zustand store not initializing | Check `frontend/src/ui/LayerToggle.tsx` and `frontend/src/store/ui.store.ts` |
| Toggle doesn't change | `toggleLayer` function broken | Check `ui.store.ts` — the `toggleLayer` action should flip the boolean |
| Console errors | New code introduced a runtime error | Read the error, fix the source file, rebuild |
| `net::ERR_CONNECTION_REFUSED` | Dev server not running | Start it with `cd frontend && npm run dev`, or let Playwright auto-start it |
| `browser launch failed` | System libraries missing | Run `sudo npx playwright install-deps chromium` |

## Adding New Tests

When you add a new UI feature, add a test to `e2e/smoke.spec.ts`:

```typescript
test('new feature is visible', async ({ page }) => {
  await page.goto(BASE_URL)
  // Use page.locator() to find your element
  const element = page.locator('[data-testid="my-feature"]')
  await expect(element).toBeVisible({ timeout: 10_000 })
})
```

Tips:
- Use `page.locator('button', { hasText: 'label' })` instead of `getByRole` for buttons with emojis.
- Use `{ force: true }` on `.click()` when Deck.gl's canvas overlay blocks pointer events.
- Filter out WebSocket errors in console checks (backend may not be running during tests).

## Guardrails

- Do NOT skip UI regression checks before marking a frontend step as done.
- Do NOT ignore console errors — even if the map "looks fine," JS errors can cause subtle bugs.
- Screenshots from failed runs are NOT committed to git (they're in `test-results/` which should be in `.gitignore`).

## Handoff Format

Add this block to `PROJECT_STATUS.md`:

```markdown
## UI Regression — [DATE]
- Method: [automated / manual / both]
- Tests run: [count]
- Tests passed: [count]
- Tests failed: [count + which]
- Console errors: [none / list]
- Screenshots: [saved to test-results/ if failures]
- Verdict: [PASS / FAIL]
```

## Example

### Invocation

```bash
npx playwright test e2e/smoke.spec.ts
```

### Example Output Summary

```
## UI Regression — 2026-04-07
- Method: automated (Playwright)
- Tests run: 4
- Tests passed: 4
- Tests failed: 0
- Console errors: none (WebSocket errors filtered)
- Screenshots: n/a (no failures)
- Verdict: PASS
```
