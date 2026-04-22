import { defineConfig } from '@playwright/test'
import { DESKTOP_VISUAL_CONTRACT } from './playwright.visual.contracts.js'

const BASE_URL = process.env.DEMO_BASE_URL || 'http://localhost:8888'

export default defineConfig({
  testDir: '../tests/js/e2e',
  testMatch: '**/demo.spec.js',
  outputDir: '../test-results/demo-output',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    browserName: 'chromium',
    baseURL: BASE_URL,
    viewport: DESKTOP_VISUAL_CONTRACT.viewport,
    // deviceScaleFactor: 2 makes page.screenshot() return 3200×1800 images —
    // genuinely crisp on Retina displays. The built-in video recorder ignores
    // this and always captures at CSS pixel dimensions (1600×900).
    deviceScaleFactor: DESKTOP_VISUAL_CONTRACT.deviceScaleFactor,
    slowMo: 60,
    // Video recording disabled — the spec captures frames via page.screenshot()
    // and the shell script stitches them with ffmpeg + VideoToolbox on macOS.
    video: { mode: 'off' },
  },
  projects: [{ name: 'demo' }],
})
