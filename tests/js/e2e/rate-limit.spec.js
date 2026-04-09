import { test, expect } from '@playwright/test'

test.describe('rate limiting', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('firing more than 5 requests per second returns a 429', async ({ page }) => {
    // Fire 20 simultaneous POST /run requests from within the page context so
    // they all share the same client IP and hit the per-IP rate limiter.
    // Using 20 (well above the 5/second limit) keeps the test reliable against
    // in-memory storage race conditions where a small burst might all slip
    // through a single counter-increment window.
    const statuses = await page.evaluate(async () => {
      const payload = JSON.stringify({ command: 'curl http://localhost:5001/health' })
      const requests = Array.from({ length: 20 }, () =>
        fetch('/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: payload,
        }).then(r => r.status),
      )
      return Promise.all(requests)
    })

    // At least one of the 20 simultaneous requests should have been rate-limited
    expect(statuses).toContain(429)
  })
})
