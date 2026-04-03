import { test, expect } from '@playwright/test'
import { runCommand } from './helpers.js'

const CMD = 'curl http://localhost:5001/health'

test.describe('permalink / share', () => {
  test.beforeEach(async ({ page }) => {
    // Mock clipboard so writeText() resolves in headless Chromium without
    // requiring the clipboard-write permission grant.
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText: () => Promise.resolve() },
        configurable: true,
      })
    })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('permalink button shows the "copied" toast after a successful run', async ({ page }) => {
    await runCommand(page, CMD)

    // Intercept the POST /share response so we can capture the share URL
    const [shareResp] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/share') && r.request().method() === 'POST'),
      page.locator('[data-action="permalink"]').click(),
    ])
    expect(shareResp.status()).toBe(200)

    // Toast should appear with the "copied" message
    await expect(page.locator('#permalink-toast')).toHaveClass(/show/, { timeout: 5_000 })
  })

  test('navigating to a share URL renders the command output', async ({ page }) => {
    await runCommand(page, CMD)

    // Click permalink and capture the share URL from the server response
    const [shareResp] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/share') && r.request().method() === 'POST'),
      page.locator('[data-action="permalink"]').click(),
    ])
    const data = await shareResp.json()

    // Navigate to the permalink page
    await page.goto(data.url)

    // The permalink page should display the command that was run
    await expect(page.locator('body')).toContainText('curl http://localhost:5001/health', { timeout: 10_000 })
  })

  test('permalink button on a fresh tab shows "No output" toast', async ({ page }) => {
    // Do NOT run any command — the tab has no output
    await page.locator('[data-action="permalink"]').click()
    await expect(page.locator('#permalink-toast')).toHaveClass(/show/, { timeout: 5_000 })
    await expect(page.locator('#permalink-toast')).toContainText('No output')
  })
})
