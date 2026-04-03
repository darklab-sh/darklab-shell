import { defineConfig, devices } from '@playwright/test'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'
import { existsSync } from 'fs'

const __dirname = dirname(fileURLToPath(import.meta.url))

// Use the project venv if present (local dev), otherwise fall back to system
// python3 (CI environments where dependencies are installed globally).
const python = existsSync(resolve(__dirname, '.venv/bin/python'))
  ? '../.venv/bin/python'
  : 'python3'

export default defineConfig({
  testDir: './tests/js/e2e',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:5001',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: `FLASK_APP=app.py ${python} -m flask run --port 5001`,
    cwd: resolve(__dirname, 'app'),
    port: 5001,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
})
