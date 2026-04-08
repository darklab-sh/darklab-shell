import { test, expect } from '@playwright/test'
import { runCommand, makeTestIp } from './helpers.js'

const CMD = 'curl http://localhost:5001/health'
const TEST_IP = makeTestIp(65)

test.describe('output actions', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
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

  test('copy button falls back when clipboard writeText rejects', async ({ page }) => {
    await page.evaluate(() => {
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText: () => Promise.reject(new Error('clipboard denied')) },
        configurable: true,
      })
      Object.defineProperty(document, 'execCommand', {
        value: (cmd) => {
          window.__copyFallbackUsed = cmd === 'copy'
          return true
        },
        configurable: true,
      })
    })

    await page.locator('[data-action="copy"]').click()

    await expect(page.locator('#permalink-toast')).toHaveClass(/show/, { timeout: 5_000 })
    await expect(page.locator('#permalink-toast')).toContainText(/copied/i)
    await expect(page.evaluate(() => window.__copyFallbackUsed)).resolves.toBe(true)
  })

  // ── Clear ─────────────────────────────────────────────────────────────────

  test('clear button removes all output from the active tab', async ({ page }) => {
    // Confirm there is output to start with
    await expect(page.locator('.tab-panel.active .output')).not.toBeEmpty()

    await page.locator('[data-action="clear"]').click()

    await expect(page.locator('.tab-panel.active .output .line')).toHaveCount(0)
    await expect(page.locator('.tab-panel.active .output .shell-prompt-wrap')).toBeVisible()
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
    expect(html).toContain('data:font/ttf;base64,')
    expect(html).not.toContain('/vendor/fonts/')
    expect(html).not.toContain('fonts.googleapis.com')
    expect(html).not.toContain('fonts.gstatic.com')
  })
})

test.describe('output actions with no exportable output', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText: () => Promise.resolve() },
        configurable: true,
      })
    })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('copy button shows a toast when there is no output to copy', async ({ page }) => {
    await page.locator('[data-action="copy"]').click()
    await expect(page.locator('#permalink-toast')).toHaveClass(/show/, { timeout: 5_000 })
    await expect(page.locator('#permalink-toast')).toContainText('No output to copy yet')
  })

  test('save-txt button shows a toast when there is no output to export', async ({ page }) => {
    await page.locator('[data-action="save"]').click()
    await expect(page.locator('#permalink-toast')).toHaveClass(/show/, { timeout: 5_000 })
    await expect(page.locator('#permalink-toast')).toContainText('No output to export')
  })
})
