import { defineConfig, devices } from '@playwright/test'

import { buildIsolatedWebServer, testDir } from './playwright.shared.js'

export default defineConfig({
  testDir,
  testMatch: '**/ui-capture.desktop.capture.js',
  outputDir: '../test-results/ui-capture-desktop-output',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://localhost:5010',
    viewport: { width: 1600, height: 900 },
    deviceScaleFactor: 2,
    trace: 'off',
    video: { mode: 'off' },
  },
  projects: [{ name: 'capture-desktop' }],
  webServer: buildIsolatedWebServer(5010, 'capture-desktop'),
})
