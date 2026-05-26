import { test, expect } from '@playwright/test'
import { makeTestIp } from './helpers.js'

const TEST_IP = makeTestIp(68)

test.describe('rate limiting', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('firing more than the e2e per-second limit returns a 429', async ({ request }) => {
    // Fire simultaneous POST /runs requests through Playwright's API client
    // so they all share the same client IP and hit the per-IP rate limiter
    // without browser connection-pool queuing or in-page abort timers.
    // The e2e server raises the default limit so unrelated tests do not trip
    // over shared limiter state. This spec intentionally exceeds that higher
    // ceiling to keep backend limiter coverage explicit.
    // Using 150 (well above the 25/second e2e limit) keeps the test reliable against
    // in-memory storage race conditions where a small burst might all slip
    // through a single counter-increment window.
    const statuses = await Promise.all(
      Array.from({ length: 150 }, () =>
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
    // At least one of the simultaneous requests should have been rate-limited.
    expect(statuses).toContain(429)
  })
})
