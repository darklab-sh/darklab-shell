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
    await page.locator('.hud-actions [data-action="copy"]').click()
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

    await page.locator('.hud-actions [data-action="copy"]').click()

    await expect(page.locator('#permalink-toast')).toHaveClass(/show/, { timeout: 5_000 })
    await expect(page.locator('#permalink-toast')).toContainText(/copied/i)
    await expect(page.evaluate(() => window.__copyFallbackUsed)).resolves.toBe(true)
  })

  // ── Clear ─────────────────────────────────────────────────────────────────

  test('clear button removes all output from the active tab', async ({ page }) => {
    // Confirm there is output to start with
    await expect(page.locator('.tab-panel.active .output')).not.toBeEmpty()

    await page.locator('.hud-actions [data-action="clear"]').click()

    await expect(page.locator('.tab-panel.active .output .line')).toHaveCount(0)
    await expect(page.locator('.tab-panel.active .output .shell-prompt-wrap')).toBeVisible()
  })

  test('status reverts to idle after clearing output', async ({ page }) => {
    await page.locator('.hud-actions [data-action="clear"]').click()
    await expect(page.locator('.status-pill')).toHaveText('IDLE')
  })

  // ── Save .txt ─────────────────────────────────────────────────────────────

  test('save-txt button triggers a .txt file download', async ({ page }) => {
    await page.locator('.hud-actions [data-action="save-menu"]').click()
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('.hud-actions [data-action="save-txt"]').click(),
    ])

    expect(download.suggestedFilename()).toMatch(/\.txt$/)
  })

  // ── Save .html ────────────────────────────────────────────────────────────

  test('save-html button triggers a .html file download', async ({ page }) => {
    await page.locator('.hud-actions [data-action="save-menu"]').click()
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('.hud-actions [data-action="save-html"]').click(),
    ])

    expect(download.suggestedFilename()).toMatch(/\.html$/)
  })

  test('downloaded html file contains the command text', async ({ page }) => {
    await page.locator('.hud-actions [data-action="save-menu"]').click()
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('.hud-actions [data-action="save-html"]').click(),
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

  test('summarize appends a signal summary block for the active tab output', async ({ page }) => {
    await page.evaluate(() => {
      clearTab(activeTabId)
      appendLine('443/tcp open https', '', activeTabId, {
        signals: ['findings'],
        command_root: 'nmap',
        target: 'ip.darklab.sh',
      })
      appendLine('warning: retrying request', 'notice', activeTabId, {
        signals: ['warnings'],
        command_root: 'nmap',
        target: 'ip.darklab.sh',
      })
      appendLine('connection timed out', 'exit-fail', activeTabId, {
        signals: ['errors'],
        command_root: 'nmap',
        target: 'ip.darklab.sh',
      })
      appendLine('Nmap done: 1 IP address (1 host up) scanned in 1.23 seconds', '', activeTabId, {
        signals: ['summaries'],
        command_root: 'nmap',
        target: 'ip.darklab.sh',
      })
    })

    await page.locator('#search-summary-btn').click()

    const lines = page.locator('.tab-panel.active .output .line')
    await expect(lines.filter({ hasText: '[command findings]' })).toHaveCount(1)
    await expect(lines.filter({ hasText: 'findings (1)' })).toHaveCount(1)
    await expect(lines.filter({ hasText: '- 443/tcp open https' })).toHaveCount(1)
    await expect(lines.filter({ hasText: 'warnings (1)' })).toHaveCount(1)
    await expect(lines.filter({ hasText: 'errors (1)' })).toHaveCount(1)
    await expect(lines.filter({ hasText: 'summaries (1)' })).toHaveCount(1)
  })

  test('summarize stays disabled when there are no signals', async ({ page }) => {
    await page.evaluate(() => {
      clearTab(activeTabId)
      appendLine('plain output', '', activeTabId)
      appendLine('still plain output', '', activeTabId)
    })

    await expect(page.locator('#search-summary-btn')).toBeDisabled()
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
    // Cancel the welcome boot path before asserting the "no output" state.
    // The sibling describe block's beforeEach reaches this state via
    // runCommand(...) which internally calls ensurePromptReady, but this block
    // intentionally runs no command, so without an explicit settle the
    // welcome animation can still be mid-stream when the test clicks copy/save
    // — under parallel load the click has been observed to fire before the
    // HUD action handlers resolve the active tab, leaving the toast in its
    // initial markup state ("Link copied to clipboard", class="") instead of
    // updating to "No output to copy yet".
    await ensurePromptReady(page, { cancelWelcome: true })
  })

  test('copy button shows a toast when there is no output to copy', async ({ page }) => {
    await page.locator('.hud-actions [data-action="copy"]').click()
    await expect(page.locator('#permalink-toast')).toHaveClass(/show/, { timeout: 5_000 })
    await expect(page.locator('#permalink-toast')).toContainText('No output to copy yet')
  })

  test('save-txt button shows a toast when there is no output to export', async ({ page }) => {
    await page.locator('.hud-actions [data-action="save-menu"]').click()
    await page.locator('.hud-actions [data-action="save-txt"]').click()
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
    await page.evaluate(
      () =>
        new Promise((resolve) => {
          setTimeout(() => {
            requestAnimationFrame(() => resolve())
          }, 0)
        }),
    )

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
    await expect
      .poll(async () =>
        page.evaluate(() => {
          const tab = getTab(activeTabId)
          const btn = document.querySelector('.tab-panel.active .output-follow-btn')
          return {
            followOutput: !!tab && tab.followOutput,
            hidden: !!btn && btn.hidden,
            text: btn?.textContent || '',
          }
        }),
      )
      .toEqual({
        followOutput: false,
        hidden: false,
        text: 'jump to live',
      })
    await expect(followBtn).toBeVisible()

    await page.evaluate(() => {
      const btn = document.querySelector('.tab-panel.active .output-follow-btn')
      if (!(btn instanceof HTMLButtonElement)) throw new Error('follow button missing')
      btn.click()
    })
    await expect(followBtn).toBeHidden()

    await page.evaluate(
      () =>
        new Promise((resolve) => {
          setTabStatus(activeTabId, 'idle')
          requestAnimationFrame(() =>
            requestAnimationFrame(() => {
              const out = getOutput(activeTabId)
              const tab = getTab(activeTabId)
              tab.suppressOutputScrollTracking = true
              out.scrollTop = 0
              tab.followOutput = false
              tab.suppressOutputScrollTracking = false
              updateOutputFollowButton(activeTabId)
              resolve()
            }),
          )
        }),
    )

    await expect
      .poll(async () =>
        page.evaluate(() => {
          const tab = getTab(activeTabId)
          const out = getOutput(activeTabId)
          const btn = document.querySelector('.tab-panel.active .output-follow-btn')
          if (out && out.scrollTop !== 0) {
            tab.suppressOutputScrollTracking = true
            out.scrollTop = 0
            tab.followOutput = false
            tab.suppressOutputScrollTracking = false
            updateOutputFollowButton(activeTabId)
          }
          return {
            status: tab?.st || '',
            followOutput: !!tab && tab.followOutput,
            hidden: !!btn && btn.hidden,
            text: btn?.textContent || '',
          }
        }),
      )
      .toEqual({
        status: 'idle',
        followOutput: false,
        hidden: false,
        text: 'jump to bottom',
      })
    await expect(followBtn).toBeVisible()
    await expect(followBtn).toHaveText('jump to bottom')
  })
})

test.describe('output search scopes', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
    await ensurePromptReady(page, { cancelWelcome: true })
    await page.evaluate(() => {
      clearTab(activeTabId)
      appendLine('noise line', '', activeTabId)
      appendLine('warning: API returned a retry-after header', 'notice', activeTabId, {
        signals: ['warnings'],
        command_root: 'nmap',
        target: 'ip.darklab.sh',
      })
      appendLine('warning: host seems down; retrying with TCP probe', 'notice', activeTabId, {
        signals: ['warnings'],
        command_root: 'nmap',
        target: 'ip.darklab.sh',
      })
      appendLine('443/tcp open https', '', activeTabId, {
        signals: ['findings'],
        command_root: 'nmap',
        target: 'ip.darklab.sh',
      })
      appendLine('connection timed out', 'exit-fail', activeTabId, {
        signals: ['errors'],
        command_root: 'nmap',
        target: 'ip.darklab.sh',
      })
      appendLine('connection refused', 'exit-fail', activeTabId, {
        signals: ['errors'],
        command_root: 'nmap',
        target: 'ip.darklab.sh',
      })
      appendLine('verify return code: 0 (ok)', '', activeTabId, {
        signals: ['findings'],
        command_root: 'nmap',
        target: 'ip.darklab.sh',
      })
      appendLine('Nmap done: 1 IP address (1 host up) scanned in 2.31 seconds', '', activeTabId, {
        signals: ['summaries'],
        command_root: 'nmap',
        target: 'ip.darklab.sh',
      })
    })
  })

  test('scoped search jumps between warnings and errors', async ({ page }) => {
    await expect(page.locator('#search-toggle-btn')).toHaveText('⌕ search • 2 findings')
    await expect(page.locator('#search-signal-summary')).toContainText('2F')
    await expect(page.locator('#search-signal-summary')).toContainText('2W')
    await expect(page.locator('#search-signal-summary')).toContainText('2E')
    await expect(page.locator('#search-signal-summary')).toContainText('1S')
    await page.locator('#search-toggle-btn').click()

    await expect(page.locator('[data-search-scope="findings"]')).toHaveAttribute('aria-pressed', 'true')
    await expect(page.locator('#search-input')).toBeDisabled()
    await expect(page.locator('#search-count')).toHaveText('1 / 2')
    await expect(page.locator('.tab-panel.active .line.search-signal-hl.current')).toContainText('443/tcp open https')

    await page.locator('[data-search-scope="warnings"]').click()

    await expect(page.locator('#search-count')).toHaveText('1 / 2')
    await expect(page.locator('.tab-panel.active .line.search-signal-hl')).toHaveCount(2)
    await expect(page.locator('.tab-panel.active .line.search-signal-hl.current')).toContainText('warning:')
    await expect(page.locator('#search-input')).toBeDisabled()

    await page.locator('[data-search-scope="errors"]').click()

    await expect(page.locator('#search-count')).toHaveText('1 / 2')
    await expect(page.locator('.tab-panel.active .line.search-signal-hl.current')).toContainText('timed out')

    await page.locator('[data-search-scope="summaries"]').click()

    await expect(page.locator('#search-count')).toHaveText('1 / 1')
    await expect(page.locator('.tab-panel.active .line.search-signal-hl.current')).toContainText('Nmap done:')

    await page.keyboard.press('Escape')
    await page.locator('[data-search-signal-scope="warnings"]').click()
    await expect(page.locator('[data-search-scope="warnings"]')).toHaveAttribute('aria-pressed', 'true')
    await expect(page.locator('#search-count')).toHaveText('1 / 2')
    await expect(page.locator('.tab-panel.active .line.search-signal-hl.current')).toContainText('retry-after')

    await page.locator('[data-search-signal-scope="warnings"]').click()
    await expect(page.locator('#search-count')).toHaveText('2 / 2')
    await expect(page.locator('.tab-panel.active .line.search-signal-hl.current')).toContainText('retrying with TCP probe')

    await page.locator('[data-search-signal-scope="errors"]').click()
    await expect(page.locator('#search-count')).toHaveText('1 / 2')
    await expect(page.locator('.tab-panel.active .line.search-signal-hl.current')).toContainText('timed out')

    await page.locator('[data-search-signal-scope="errors"]').click()
    await expect(page.locator('#search-count')).toHaveText('2 / 2')
    await expect(page.locator('.tab-panel.active .line.search-signal-hl.current')).toContainText('refused')
  })
})
