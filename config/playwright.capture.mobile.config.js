import { defineConfig } from '@playwright/test'

import { buildIsolatedWebServer, testDir } from './playwright.shared.js'
import { MOBILE_VISUAL_CONTRACT } from './playwright.visual.contracts.js'

export default defineConfig({
  testDir,
  testMatch: '**/ui-capture.mobile.capture.js',
  outputDir: process.env.CAPTURE_PLAYWRIGHT_OUTPUT_DIR || '/tmp/darklab_shell-ui-capture-mobile-output',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    isMobile: false,
    browserName: 'chromium',
    viewport: MOBILE_VISUAL_CONTRACT.viewport,
    deviceScaleFactor: MOBILE_VISUAL_CONTRACT.deviceScaleFactor,
    userAgent:
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    hasTouch: MOBILE_VISUAL_CONTRACT.hasTouch,
    baseURL: 'http://localhost:5011',
    trace: 'off',
    video: { mode: 'off' },
  },
  projects: [{ name: 'capture-mobile' }],
  webServer: buildIsolatedWebServer(5011, 'capture-mobile'),
})
