import { test, expect } from '@playwright/test'
import { runCommand } from './helpers.js'

const CMD = 'curl http://localhost:5001/health'

test.describe('output actions', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText: () => Promise.resolve() },
        configurable: true,
      })
    })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
    await runCommand(page, CMD)
  })

  // ── Copy ──────────────────────────────────────────────────────────────────

  test('copy button shows the "Copied" toast', async ({ page }) => {
    await page.locator('[data-action="copy"]').click()
    await expect(page.locator('#permalink-toast')).toHaveClass(/show/, { timeout: 5_000 })
    await expect(page.locator('#permalink-toast')).toContainText(/copied/i)
  })

  test('copy button shows a failure toast when clipboard writeText rejects', async ({ page }) => {
    await page.evaluate(() => {
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText: () => Promise.reject(new Error('clipboard denied')) },
        configurable: true,
      })
    })

    await page.locator('[data-action="copy"]').click()

    await expect(page.locator('#permalink-toast')).toHaveClass(/show/, { timeout: 5_000 })
    await expect(page.locator('#permalink-toast')).toContainText('Failed to copy')
  })

  // ── Clear ─────────────────────────────────────────────────────────────────

  test('clear button removes all output from the active tab', async ({ page }) => {
    // Confirm there is output to start with
    await expect(page.locator('.tab-panel.active .output')).not.toBeEmpty()

    await page.locator('[data-action="clear"]').click()

    await expect(page.locator('.tab-panel.active .output')).toBeEmpty()
  })

  test('status reverts to idle after clearing output', async ({ page }) => {
    await page.locator('[data-action="clear"]').click()
    await expect(page.locator('.status-pill')).toHaveText('IDLE')
  })

  // ── Save .txt ─────────────────────────────────────────────────────────────

  test('save-txt button triggers a .txt file download', async ({ page }) => {
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('[data-action="save"]').click(),
    ])

    expect(download.suggestedFilename()).toMatch(/\.txt$/)
  })

  // ── Save .html ────────────────────────────────────────────────────────────

  test('save-html button triggers a .html file download', async ({ page }) => {
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('[data-action="html"]').click(),
    ])

    expect(download.suggestedFilename()).toMatch(/\.html$/)
  })

  test('downloaded html file contains the command text', async ({ page }) => {
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('[data-action="html"]').click(),
    ])

    const stream = await download.createReadStream()
    const chunks = []
    for await (const chunk of stream) chunks.push(chunk)
    const html = Buffer.concat(chunks).toString('utf8')

    expect(html).toContain('curl http://localhost:5001/health')
  })
})
