import { test, expect } from '@playwright/test'
import { runCommand, makeTestIp } from './helpers.js'

const CMD = 'curl http://localhost:5001/health'
const TEST_IP = makeTestIp(69)

test.describe('runner stall handling', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
    await page.addInitScript(() => {
      const originalFetch = window.fetch.bind(window)
      const originalSetTimeout = window.setTimeout.bind(window)
      const encoder = new TextEncoder()

      window.setTimeout = (fn, delay, ...args) => {
        return originalSetTimeout(fn, delay === 45000 ? 50 : delay, ...args)
      }

      window.fetch = async (input, init) => {
        const url = typeof input === 'string' ? input : input.url
        if (url.endsWith('/run') && init?.method === 'POST') {
          const body = new ReadableStream({
            start(controller) {
              controller.enqueue(encoder.encode(
                'data: {"type":"started","run_id":"stall-test-run"}\n\n',
              ))
              // Leave the stream open so the client-side stall timer fires.
            },
          })

          return new Response(body, {
            status: 200,
            headers: { 'Content-Type': 'text/event-stream' },
          })
        }
        return originalFetch(input, init)
      }
    })

    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('a stalled SSE stream shows the recovery notice and clears the running state', async ({ page }) => {
    await runCommand(page, CMD)

    const output = page.locator('.tab-panel.active .output')
    await expect(output).toContainText('connection stalled', { timeout: 5_000 })
    await expect(page.locator('.status-pill')).toHaveText('ERROR')
    await expect(page.locator('.tab-kill-btn')).toBeHidden()
    await expect(page.locator('#run-btn')).toBeHidden()
    await expect(page.locator('#run-btn')).toHaveJSProperty('disabled', true)

    await page.locator('#cmd').fill('hostname')
    await expect(page.locator('#run-btn')).toHaveJSProperty('disabled', false)
  })
})
