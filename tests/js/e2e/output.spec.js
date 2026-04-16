import { test, expect } from '@playwright/test'
import { ensurePromptReady, runCommand, makeTestIp } from './helpers.js'

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
    await page.locator('[data-action="save-menu"]').click()
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('[data-action="save-txt"]').click(),
    ])

    expect(download.suggestedFilename()).toMatch(/\.txt$/)
  })

  // ── Save .html ────────────────────────────────────────────────────────────

  test('save-html button triggers a .html file download', async ({ page }) => {
    await page.locator('[data-action="save-menu"]').click()
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('[data-action="save-html"]').click(),
    ])

    expect(download.suggestedFilename()).toMatch(/\.html$/)
  })

  test('downloaded html file contains the command text', async ({ page }) => {
    await page.locator('[data-action="save-menu"]').click()
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('[data-action="save-html"]').click(),
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
    await page.locator('[data-action="save-menu"]').click()
    await page.locator('[data-action="save-txt"]').click()
    await expect(page.locator('#permalink-toast')).toHaveClass(/show/, { timeout: 5_000 })
    await expect(page.locator('#permalink-toast')).toContainText('No output to export')
  })
})

test.describe('output follow helper', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
    await ensurePromptReady(page, { cancelWelcome: true })
    await page.evaluate(() => {
      clearTab(activeTabId)
      for (let i = 0; i < 600; i += 1) appendLine(`line ${i} ${'x'.repeat(60)}`, '', activeTabId)
    })
  })

  test('shows only when scrolled off tail and swaps from live to bottom state', async ({
    page,
  }) => {
    const followBtn = page.locator('.tab-panel.active .output-follow-btn')

    await expect(followBtn).toBeHidden()
    await page.waitForFunction(() => {
      const out = getOutput(activeTabId)
      const tab = getTab(activeTabId)
      const pending =
        typeof _pendingOutputBatches !== 'undefined' ? _pendingOutputBatches.get(activeTabId) : null
      return (
        !!out &&
        !!tab &&
        Array.isArray(tab.rawLines) &&
        tab.rawLines.length === 600 &&
        (!pending || (!pending.scheduled && pending.items.length === 0)) &&
        out.scrollHeight > out.clientHeight + 50
      )
    })

    await page.evaluate(() => {
      const out = getOutput(activeTabId)
      const tab = getTab(activeTabId)
      setTabStatus(activeTabId, 'running')
      out.scrollTop = 0
      tab.followOutput = false
      updateOutputFollowButton(activeTabId)
    })

    await page.waitForFunction(
      () => {
        const tab = getTab(activeTabId)
        const btn = document.querySelector('.tab-panel.active .output-follow-btn')
        return (
          !!tab &&
          tab.st === 'running' &&
          !tab.followOutput &&
          !!btn &&
          !btn.hidden &&
          btn.textContent === 'jump to live'
        )
      },
      { timeout: 5000 },
    )
    await expect(followBtn).toBeVisible()
    await expect(followBtn).toHaveText('jump to live')

    await page.evaluate(() => {
      const btn = document.querySelector('.tab-panel.active .output-follow-btn')
      if (!(btn instanceof HTMLButtonElement)) throw new Error('follow button missing')
      btn.click()
    })
    await expect(followBtn).toBeHidden()

    await page.evaluate(() => {
      const out = getOutput(activeTabId)
      const tab = getTab(activeTabId)
      setTabStatus(activeTabId, 'idle')
      out.scrollTop = 0
      tab.followOutput = false
      updateOutputFollowButton(activeTabId)
    })

    await page.waitForFunction(() => {
      const tab = getTab(activeTabId)
      const btn = document.querySelector('.tab-panel.active .output-follow-btn')
      return (
        !!tab && tab.st === 'idle' && !!btn && !btn.hidden && btn.textContent === 'jump to bottom'
      )
    })
    await expect(followBtn).toBeVisible()
    await expect(followBtn).toHaveText('jump to bottom')
  })
})
