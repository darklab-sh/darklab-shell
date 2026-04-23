import { defineConfig } from '@playwright/test'
import { MOBILE_VISUAL_CONTRACT } from './playwright.visual.contracts.js'

const BASE_URL = process.env.DEMO_BASE_URL || 'http://localhost:8888'

export default defineConfig({
  testDir: '../tests/js/e2e',
  testMatch: '**/demo.mobile.spec.js',
  outputDir: process.env.DEMO_PLAYWRIGHT_OUTPUT_DIR || '/tmp/darklab_shell-mobile-demo-output',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    // isMobile: false with an explicit 430×932 viewport gives full-height page
    // content — no Chromium mobile browser chrome reservation and no gray bar
    // at the bottom of the recording. The iPhone 15 UA makes the server serve
    // the mobile template; hasTouch enables touch events; deviceScaleFactor: 3
    // matches real iPhone 15 pixel density. With isMobile: false, svh == vh ==
    // 932px (no simulated browser chrome), so 88svh renders correctly tall —
    // matching the real-device history panel height without any CSS overrides.
    isMobile: false,
    browserName: 'chromium',
    viewport: MOBILE_VISUAL_CONTRACT.viewport,
    deviceScaleFactor: MOBILE_VISUAL_CONTRACT.deviceScaleFactor,
    userAgent:
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    hasTouch: MOBILE_VISUAL_CONTRACT.hasTouch,
    baseURL: BASE_URL,
    slowMo: 60,
    // Video recording disabled — the spec captures frames via page.screenshot()
    // (which respects deviceScaleFactor, giving 1290×2796 images) and stitches
    // them into a video with ffmpeg. Built-in video recording ignores
    // deviceScaleFactor and always captures at CSS pixel dimensions (430×932).
    video: { mode: 'off' },
  },
  projects: [{ name: 'demo-mobile' }],
})
