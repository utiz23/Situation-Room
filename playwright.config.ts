import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: 0,
  use: {
    headless: true,
    viewport: { width: 1280, height: 720 },
    // Screenshot on failure helps debug map rendering issues
    screenshot: 'only-on-failure',
  },
  // Auto-start the Vite dev server before running tests.
  // Playwright will wait until localhost:5173 responds, then run the tests,
  // and shut the server down when done. No need to start it manually.
  webServer: {
    command: 'npm run dev',
    cwd: './frontend',
    port: 5173,
    reuseExistingServer: true, // if you already have it running, use that instead
    timeout: 30_000,
  },
})
