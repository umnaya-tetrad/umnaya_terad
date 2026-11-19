import { defineConfig } from '@playwright/test'

// Release acceptance drives the local Compose fixture stack only.
// Teacher and staff credentials come from the environment (or a local env file
// loaded by the runner); no secret is stored here.
export default defineConfig({
  testDir: './tests/e2e/pilot',
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 20_000 },
  reporter: [['list']],
  use: {
    baseURL: process.env.PILOT_BASE_URL || 'http://127.0.0.1:5173',
    trace: 'off',
    video: 'off',
    screenshot: 'off',
    headless: true,
  },
  projects: [
    { name: 'mobile', use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
})
