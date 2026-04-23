import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

const configDir = dirname(fileURLToPath(import.meta.url))
const rootDir = resolve(configDir, '..')
// Export as __dirname so consumers (playwright.parallel.config.js) can use it
// for path resolution — points to the repo root, not this config/ directory.
export const __dirname = rootDir
export const testDir = resolve(rootDir, 'tests/js/e2e')
const showWebServerLogs = !!process.env.PW_WEBSERVER_LOGS

export function buildIsolatedWebServer(port, slot) {
  return {
    command: `/bin/bash ${resolve(rootDir, 'scripts/playwright/run_e2e_server.sh')} ${port} ${slot}`,
    cwd: rootDir,
    url: `http://localhost:${port}/health`,
    reuseExistingServer: false,
    gracefulShutdown: { signal: 'SIGTERM', timeout: 5_000 },
    stdout: showWebServerLogs ? 'pipe' : 'ignore',
    stderr: showWebServerLogs ? 'pipe' : 'ignore',
    timeout: 30_000,
  }
}
