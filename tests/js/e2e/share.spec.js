import { test, expect } from '@playwright/test'
import { runCommand, openHistoryWithEntries } from './helpers.js'

const CMD = 'curl http://localhost:5001/health'
const MOBILE = { width: 375, height: 812 }

test.describe('permalink / share', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': '203.0.113.61' })
    // Mock clipboard so writeText() resolves in headless Chromium without
    // requiring the clipboard-write permission grant.
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'clipboard', {
        value: {
          writeText: text => {
            window.__clipboardText = text
            return Promise.resolve()
          },
        },
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
    await page.locator('#new-tab-btn').click()
    await expect(page.locator('.tab.active')).toContainText('tab 2')
    await page.locator('.tab-panel.active [data-action="permalink"]').click()
    await expect(page.locator('#permalink-toast')).toHaveClass(/show/, { timeout: 5_000 })
    await expect(page.locator('#permalink-toast')).toContainText('No output')
  })

  test('permalink button falls back to execCommand when clipboard writeText rejects', async ({ page }) => {
    await runCommand(page, CMD)

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

    await page.locator('[data-action="permalink"]').click()
    await expect(page.locator('#permalink-toast')).toHaveClass(/show/, { timeout: 5_000 })
    await expect(page.locator('#permalink-toast')).toContainText('Link copied to clipboard')
    await expect(page.evaluate(() => window.__copyFallbackUsed)).resolves.toBe(true)
  })

  test('history entry permalink copies a single-run URL and the page renders JSON and HTML views', async ({ page }) => {
    await runCommand(page, CMD)

    await openHistoryWithEntries(page)
    await page.locator('.history-entry').first().locator('[data-action="permalink"]').click()

    const copied = await page.evaluate(() => window.__clipboardText)
    expect(copied).toMatch(/\/history\/[0-9a-f-]+$/)

    await page.goto(copied)
    await expect(page.locator('body')).toContainText(CMD, { timeout: 10_000 })

    await page.goto(`${copied}?json`)
    await expect(page.locator('body')).toContainText('"command":"curl http://localhost:5001/health"')
    await expect(page.locator('body')).toContainText('"exit_code":0')
  })

  test('fresh run permalink supports line-number and timestamp display toggles', async ({ page }) => {
    await runCommand(page, CMD)

    await openHistoryWithEntries(page)
    await page.locator('.history-entry').first().locator('[data-action="permalink"]').click()
    const copied = await page.evaluate(() => window.__clipboardText)

    await page.goto(copied)

    await expect(page.locator('#toggle-ln')).toHaveText('line numbers: off')
    await expect(page.locator('#toggle-ts')).toHaveText('timestamps: off')
    await expect(page.locator('#toggle-ts')).toBeEnabled()

    await page.locator('#toggle-ln').click()
    await expect(page.locator('#toggle-ln')).toHaveText('line numbers: on')
    await expect(page.locator('.perm-prefix').first()).toContainText('1')

    await page.locator('#toggle-ts').click()
    await expect(page.locator('#toggle-ts')).toHaveText('timestamps: elapsed')
    await expect
      .poll(async () => page.locator('.perm-prefix').allTextContents())
      .toContainEqual(expect.stringContaining('+'))
  })

  test('snapshot permalink supports line-number and timestamp display toggles', async ({ page }) => {
    await runCommand(page, CMD)

    const [shareResp] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/share') && r.request().method() === 'POST'),
      page.locator('[data-action="permalink"]').click(),
    ])
    const data = await shareResp.json()

    await page.goto(data.url)

    await expect(page.locator('#toggle-ln')).toHaveText('line numbers: off')
    await expect(page.locator('#toggle-ts')).toHaveText('timestamps: off')

    await page.locator('#toggle-ln').click()
    await expect(page.locator('#toggle-ln')).toHaveText('line numbers: on')
    await expect(page.locator('.perm-prefix').first()).toContainText('1')

    await page.locator('#toggle-ts').click()
    await expect(page.locator('#toggle-ts')).toHaveText('timestamps: elapsed')
    await expect
      .poll(async () => page.locator('.perm-prefix').allTextContents())
      .toContainEqual(expect.stringContaining('+'))
  })

  test('permalink exports use timestamped filenames for txt and html downloads', async ({ page }) => {
    await runCommand(page, CMD)

    const [shareResp] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/share') && r.request().method() === 'POST'),
      page.locator('[data-action="permalink"]').click(),
    ])
    const data = await shareResp.json()

    await page.goto(data.url)

    const [txtDownload] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('button:has-text("save .txt")').click(),
    ])
    expect(txtDownload.suggestedFilename()).toMatch(/^shell\.darklab\.sh-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.txt$/)

    const [htmlDownload] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('button:has-text("save .html")').click(),
    ])
    expect(htmlDownload.suggestedFilename()).toMatch(/^shell\.darklab\.sh-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.html$/)
  })

  test('permalink exports include prompt echo and current prefix display state', async ({ page }) => {
    await runCommand(page, CMD)

    const [shareResp] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/share') && r.request().method() === 'POST'),
      page.locator('[data-action="permalink"]').click(),
    ])
    const data = await shareResp.json()

    await page.goto(data.url)
    await page.locator('#toggle-ln').click()
    await page.locator('#toggle-ts').click()

    const [txtDownload] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('button:has-text("save .txt")').click(),
    ])
    const txtStream = await txtDownload.createReadStream()
    const txtChunks = []
    for await (const chunk of txtStream) txtChunks.push(chunk)
    const txt = Buffer.concat(txtChunks).toString('utf8')

    expect(txt).toContain('anon@shell.darklab.sh:~$ curl http://localhost:5001/health')
    expect(txt).toMatch(/1\s+anon@shell\.darklab\.sh:~\$ curl http:\/\/localhost:5001\/health/)
    expect(txt).toContain('+')

    const [htmlDownload] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('button:has-text("save .html")').click(),
    ])
    const htmlStream = await htmlDownload.createReadStream()
    const htmlChunks = []
    for await (const chunk of htmlStream) htmlChunks.push(chunk)
    const html = Buffer.concat(htmlChunks).toString('utf8')

    expect(html).toContain('prompt-prefix')
    expect(html).toContain('curl http://localhost:5001/health')
    expect(html).toContain('perm-prefix')
    expect(html).toContain('+')
  })

  test('mobile permalink page toast hides after copy', async ({ page }) => {
    await runCommand(page, CMD)

    const [shareResp] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/share') && r.request().method() === 'POST'),
      page.locator('[data-action="permalink"]').click(),
    ])
    const data = await shareResp.json()

    await page.setViewportSize(MOBILE)
    await page.goto(data.url)

    await page.locator('button:has-text("copy")').click()

    const toast = page.locator('#copy-toast')
    await expect(toast).toHaveText('Copied to clipboard')
    await expect(toast).toHaveClass(/show/, { timeout: 5_000 })
    await expect(toast).toBeHidden({ timeout: 5_000 })
  })
})
