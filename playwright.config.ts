import { defineConfig } from '@playwright/test'

// Release acceptance drives the local Compose fixture stack only.
// Teacher and staff credentials come from the environment (or a local env file
// loaded by the runner); no secret is stored here.
const acceptancePort = process.env.PILOT_ACCEPTANCE_PORT || '5273'
const acceptanceOrigin = process.env.PILOT_BASE_URL || `http://127.0.0.1:${acceptancePort}`

export default defineConfig({
  testDir: './tests/e2e/pilot',
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 20_000 },
  reporter: [['list']],
  use: {
    // Acceptance runs against its own isolated Compose project, never the
    // working local stack.
    baseURL: acceptanceOrigin,
    trace: 'off',
    video: 'off',
    screenshot: 'off',
    headless: true,
  },
  projects: [
    { name: 'mobile', use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
})
