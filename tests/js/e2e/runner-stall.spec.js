import { test, expect } from '@playwright/test'
import { ensurePromptReady, makeTestIp } from './helpers.js'

const CMD = 'curl http://localhost:5001/health'
const QUIET_THEN_OUTPUT_CMD = 'ping -c 2 -i 1 darklab.sh'
const TEST_IP = makeTestIp(69)

test.describe('runner stall handling', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
  })

  async function openShellWithShortStallTimer(page) {
    await page.addInitScript(() => {
      const originalSetTimeout = window.setTimeout.bind(window)

      window.setTimeout = (fn, delay, ...args) => {
        return originalSetTimeout(fn, delay === 45000 ? 50 : delay, ...args)
      }
    })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  }

  test('a quiet SSE stream keeps the tab running while the backend run is active', async ({
    page,
  }) => {
    await page.addInitScript(() => {
      const originalFetch = window.fetch.bind(window)
      const encoder = new TextEncoder()

      window.fetch = async (input, init) => {
        const url = typeof input === 'string' ? input : input.url
        if (url.endsWith('/run') && init?.method === 'POST') {
          const body = new ReadableStream({
            start(controller) {
              controller.enqueue(
                encoder.encode('data: {"type":"started","run_id":"stall-test-run"}\n\n'),
              )
              // Leave the stream open so the client-side stall timer fires.
            },
          })

          return new Response(body, {
            status: 200,
            headers: { 'Content-Type': 'text/event-stream' },
          })
        }
        if (url.endsWith('/history/active')) {
          return new Response(JSON.stringify({
            runs: [{
              run_id: 'stall-test-run',
              pid: 4242,
              command: 'curl http://localhost:5001/health',
              started: '2026-01-01T00:00:00Z',
            }],
          }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }
        return originalFetch(input, init)
      }
    })

    await openShellWithShortStallTimer(page)
    await ensurePromptReady(page)
    await page.locator('#cmd').fill(CMD)
    await page.keyboard.press('Enter')

    const output = page.locator('.tab-panel.active .output')
    await expect(output).toContainText('stream quiet', { timeout: 5_000 })
    await expect(output).toContainText('process is still running')
    await expect(page.locator('.status-pill')).toHaveText('RUNNING')
    await expect(page.locator('#hud-actions [data-action="kill"]')).toBeVisible()
    await expect(page.locator('#run-btn')).toBeHidden()
    await expect(page.locator('#run-btn')).toHaveJSProperty('disabled', true)
  })

  test('a real quiet command recovers in the same tab when output resumes', async ({ page }) => {
    await openShellWithShortStallTimer(page)
    await ensurePromptReady(page)
    await page.locator('#cmd').fill(QUIET_THEN_OUTPUT_CMD)
    await page.keyboard.press('Enter')

    const output = page.locator('.tab-panel.active .output')
    await expect(output).toContainText('stream quiet', { timeout: 5_000 })
    await expect(output).toContainText('process is still running')
    await expect(output).toContainText('connection re-established', { timeout: 5_000 })
    await expect(output).toContainText('[process exited with code', { timeout: 10_000 })
    await expect(page.locator('.status-pill')).toHaveText('IDLE')
    await expect(page.locator('#hud-actions [data-action="kill"]')).toBeHidden()
  })
})
