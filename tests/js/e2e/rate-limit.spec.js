import { test, expect } from '@playwright/test'
import { makeTestIp } from './helpers.js'

const TEST_IP = makeTestIp(68)

test.describe('rate limiting', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('firing more than 5 requests per second returns a 429', async ({ request }) => {
    // Fire 20 simultaneous POST /runs requests through Playwright's API client
    // so they all share the same client IP and hit the per-IP rate limiter
    // without browser connection-pool queuing or in-page abort timers.
    // Using 20 (well above the 5/second limit) keeps the test reliable against
    // in-memory storage race conditions where a small burst might all slip
    // through a single counter-increment window.
    const statuses = await Promise.all(
      Array.from({ length: 20 }, () =>
        request.post('/runs', {
          headers: { 'X-Forwarded-For': TEST_IP },
          data: { command: '' },
          timeout: 20_000,
        })
          .then((resp) => resp.status())
          .catch((err) => `error:${err?.name || err?.message || 'request'}`),
      ),
    )

    expect(statuses.filter((status) => String(status).startsWith('error:'))).toEqual([])
    // At least one of the 20 simultaneous requests should have been rate-limited.
    expect(statuses).toContain(429)
  })
})
