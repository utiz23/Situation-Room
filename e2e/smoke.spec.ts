/**
 * Smoke test — verifies the SituationRoom frontend loads and
 * the five layer-toggle buttons are visible and clickable.
 *
 * Run with:
 *   npx playwright test e2e/smoke.spec.ts
 *
 * Prerequisites:
 *   - Frontend dev server running: cd frontend && npm run dev
 *   - (Optional) Backend running for live data: docker compose up db redis api workers -d
 */

import { test, expect } from '@playwright/test'

const BASE_URL = process.env.BASE_URL ?? 'http://localhost:5173'

test.describe('SituationRoom smoke tests', () => {
  test('map canvas loads', async ({ page }) => {
    await page.goto(BASE_URL)
    // Deck.gl renders into a canvas element
    const canvas = page.locator('canvas')
    await expect(canvas.first()).toBeVisible({ timeout: 15_000 })
  })

  test('all five layer toggle buttons are visible', async ({ page }) => {
    await page.goto(BASE_URL)
    const buttons = page.locator('button')
    // Wait for at least 5 layer buttons to appear
    await expect(buttons).toHaveCount(5, { timeout: 10_000 })

    // Match by partial text — avoids emoji encoding issues with getByRole
    const expectedText = ['Aircraft', 'Ships', 'Satellites', 'GPS Jam', 'Events']
    for (const text of expectedText) {
      await expect(page.locator('button', { hasText: text })).toBeVisible()
    }
  })

  test('toggling a layer button changes its style', async ({ page }) => {
    await page.goto(BASE_URL)
    const aircraftBtn = page.locator('button', { hasText: 'Aircraft' })
    await expect(aircraftBtn).toBeVisible({ timeout: 10_000 })

    // Read the title attribute — it reflects active state ("Hide ✈ Aircraft")
    const titleBefore = await aircraftBtn.getAttribute('title')

    // Use force:true because Deck.gl's canvas overlay can intercept clicks
    await aircraftBtn.click({ force: true })

    // After toggle, the title should flip (e.g., "Hide …" → "Show …" or vice versa)
    await expect(aircraftBtn).not.toHaveAttribute('title', titleBefore!, { timeout: 5_000 })
  })

  test('page has no console errors on load', async ({ page }) => {
    const errors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text())
    })

    await page.goto(BASE_URL)
    // Give the app a moment to initialize WebSocket and layers
    await page.waitForTimeout(3_000)

    // Filter out known non-critical errors (e.g., WebSocket connection fails
    // when backend isn't running during test)
    const critical = errors.filter(
      (e) => !e.includes('WebSocket') && !e.includes('ERR_CONNECTION_REFUSED'),
    )
    expect(critical).toEqual([])
  })
})
