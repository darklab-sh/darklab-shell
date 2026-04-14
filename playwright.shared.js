import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

export const __dirname = dirname(fileURLToPath(import.meta.url))
export const testDir = './tests/js/e2e'
const showWebServerLogs = !!process.env.PW_WEBSERVER_LOGS

export function buildIsolatedWebServer(port, slot) {
  return {
    command: `/bin/bash ${resolve(__dirname, 'scripts/playwright/run_e2e_server.sh')} ${port} ${slot}`,
    cwd: resolve(__dirname),
    url: `http://localhost:${port}/health`,
    reuseExistingServer: false,
    gracefulShutdown: { signal: 'SIGTERM', timeout: 5_000 },
    stdout: showWebServerLogs ? 'pipe' : 'ignore',
    stderr: showWebServerLogs ? 'pipe' : 'ignore',
    timeout: 30_000,
  }
}
