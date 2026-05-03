import { test, expect } from '@playwright/test'
import { makeTestIp } from './helpers.js'

const TEST_IP = makeTestIp(68)

test.describe('rate limiting', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('firing more than 5 requests per second returns a 429', async ({ page }) => {
    // Fire 20 simultaneous POST /runs requests from within the page context so
    // they all share the same client IP and hit the per-IP rate limiter.
    // Using 20 (well above the 5/second limit) keeps the test reliable against
    // in-memory storage race conditions where a small burst might all slip
    // through a single counter-increment window.
    const statuses = await page.evaluate(async () => {
      const payload = JSON.stringify({ command: '' })
      const requests = Array.from({ length: 20 }, () =>
        new Promise((resolve) => {
          const controller = new AbortController()
          const timer = setTimeout(() => controller.abort(), 5_000)
          fetch('/runs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: payload,
            signal: controller.signal,
          })
            .then((r) => resolve(r.status))
            .catch((err) => resolve(`error:${err?.name || 'fetch'}`))
            .finally(() => clearTimeout(timer))
        }),
      )
      return Promise.all(requests)
    })

    expect(statuses.filter((status) => String(status).startsWith('error:'))).toEqual([])
    // At least one of the 20 simultaneous requests should have been rate-limited.
    expect(statuses).toContain(429)
  })
})
