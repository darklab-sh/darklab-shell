import { test, expect } from '@playwright/test'

test.describe('rate limiting', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('firing more than 5 requests per second returns a 429', async ({ page }) => {
    // Fire 6 simultaneous POST /run requests from within the page context so
    // they share the same session cookie and hit the per-session rate limiter.
    const statuses = await page.evaluate(async () => {
      const payload = JSON.stringify({ command: 'curl http://localhost:5001/health' })
      const requests = Array.from({ length: 6 }, () =>
        fetch('/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: payload,
        }).then(r => r.status),
      )
      return Promise.all(requests)
    })

    // At least one of the 6 simultaneous requests should have been rate-limited
    expect(statuses).toContain(429)
  })
})
