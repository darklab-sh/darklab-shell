import { defineConfig } from '@playwright/test'
import { MOBILE_VISUAL_CONTRACT } from './playwright.visual.contracts.js'

const BASE_URL = process.env.DEMO_BASE_URL || 'http://localhost:8888'
const HEADED_DEMO = process.env.DEMO_HEADED === '1'
const OBS_DEMO = HEADED_DEMO && process.env.DEMO_DISABLE_FRAME_CAPTURE === '1'
const MOBILE_OBS_VIEWPORT_WIDTH = Number(process.env.DEMO_MOBILE_OBS_VIEWPORT_WIDTH || 502)
const MOBILE_VIEWPORT = OBS_DEMO
  ? { ...MOBILE_VISUAL_CONTRACT.viewport, width: MOBILE_OBS_VIEWPORT_WIDTH }
  : MOBILE_VISUAL_CONTRACT.viewport
const MOBILE_WINDOW_WIDTH = Number(
  process.env.DEMO_MOBILE_WINDOW_WIDTH || MOBILE_VIEWPORT.width,
)
const MOBILE_WINDOW_HEIGHT = Number(
  process.env.DEMO_MOBILE_WINDOW_HEIGHT || MOBILE_VIEWPORT.height + 120,
)

export default defineConfig({
  testDir: '../tests/js/e2e',
  testMatch: '**/demo.mobile.spec.js',
  outputDir: process.env.DEMO_PLAYWRIGHT_OUTPUT_DIR || '/tmp/darklab_shell-mobile-demo-output',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    // isMobile: false with an explicit mobile viewport gives full-height page
    // content without Chromium's simulated mobile keyboard/browser chrome. The
    // OBS headed path widens slightly by default because Chromium's desktop
    // toolbar enforces a wider minimum content area; matching that width avoids
    // gray browser background to the right of the page. The optional screenshot
    // fallback keeps the 430x932 iPhone-style visual contract.
    isMobile: false,
    browserName: 'chromium',
    headless: !HEADED_DEMO,
    viewport: MOBILE_VIEWPORT,
    deviceScaleFactor: MOBILE_VISUAL_CONTRACT.deviceScaleFactor,
    userAgent:
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    hasTouch: MOBILE_VISUAL_CONTRACT.hasTouch,
    baseURL: BASE_URL,
    launchOptions: HEADED_DEMO
      ? {
        args: [
          '--force-color-profile=srgb',
          `--window-size=${MOBILE_WINDOW_WIDTH},${MOBILE_WINDOW_HEIGHT}`,
        ],
      }
      : {},
    slowMo: 60,
    // Playwright video is disabled. The wrapper records through OBS; the spec
    // can still capture screenshot frames when DEMO_DISABLE_FRAME_CAPTURE is unset.
    video: { mode: 'off' },
  },
  projects: [{ name: 'demo-mobile' }],
})
