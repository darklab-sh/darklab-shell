import { defineConfig } from '@playwright/test'
import { DESKTOP_VISUAL_CONTRACT } from './playwright.visual.contracts.js'

const BASE_URL = process.env.DEMO_BASE_URL || 'http://localhost:8888'
const HEADED_DEMO = process.env.DEMO_HEADED === '1'

export default defineConfig({
  testDir: '../tests/js/e2e',
  testMatch: '**/demo.spec.js',
  outputDir: process.env.DEMO_PLAYWRIGHT_OUTPUT_DIR || '/tmp/darklab_shell-demo-output',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    browserName: 'chromium',
    baseURL: BASE_URL,
    headless: !HEADED_DEMO,
    viewport: DESKTOP_VISUAL_CONTRACT.viewport,
    // Retained for the optional screenshot-frame fallback. The normal OBS
    // wrapper disables frame capture and records the headed browser window.
    deviceScaleFactor: DESKTOP_VISUAL_CONTRACT.deviceScaleFactor,
    launchOptions: HEADED_DEMO
      ? {
        args: [
            '--force-color-profile=srgb',
            '--window-size=1700,1000',
          ],
        }
      : {},
    slowMo: 60,
    // Playwright video is disabled. The wrapper records through OBS; the spec
    // can still capture screenshot frames when DEMO_DISABLE_FRAME_CAPTURE is unset.
    video: { mode: 'off' },
  },
  projects: [{ name: 'demo' }],
})
