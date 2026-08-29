// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { defineConfig, devices } from '@playwright/test'

import { buildIsolatedWebServer, testDir } from './playwright.shared.js'
import { DESKTOP_VISUAL_CONTRACT } from './playwright.visual.contracts.js'

export default defineConfig({
  testDir,
  testMatch: '**/ui-capture.desktop.capture.js',
  outputDir: process.env.CAPTURE_PLAYWRIGHT_OUTPUT_DIR || '/tmp/darklab_shell-ui-capture-desktop-output',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    ...devices['Desktop Chrome'],
    actionTimeout: 15_000,
    baseURL: 'http://localhost:5010',
    viewport: DESKTOP_VISUAL_CONTRACT.viewport,
    deviceScaleFactor: DESKTOP_VISUAL_CONTRACT.deviceScaleFactor,
    trace: 'off',
    video: { mode: 'off' },
  },
  projects: [{ name: 'capture-desktop' }],
  webServer: buildIsolatedWebServer(5010, 'capture-desktop'),
})
