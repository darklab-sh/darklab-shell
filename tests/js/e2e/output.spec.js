// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { test, expect } from '@playwright/test'
import { ensurePromptReady, runCommand } from './helpers.js'

const CMD = 'hostname'

async function appendEntityOutput(page, {
  display = 'IP.DARKLAB.SH',
  canonical = 'ip.darklab.sh',
} = {}) {
  await page.evaluate(({ displayValue, canonicalValue }) => {
    clearTab(activeTabId)
    const prefix = 'scan '
    appendLine(`${prefix}${displayValue}`, '', activeTabId, {
      command_root: 'nmap',
      target: canonicalValue,
      entities: [{
        type: 'domain',
        value: displayValue,
        canonical_value: canonicalValue,
        start: prefix.length,
        end: prefix.length + displayValue.length,
      }],
    })
  }, { displayValue: display, canonicalValue: canonical })
}

test.describe('output actions', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'clipboard', {
        value: {
          writeText: (value) => {
            window.__copiedEntity = value
            return Promise.resolve()
          },
        },
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
    const saveWrap = page.locator('.hud-actions .hud-save-wrap')
    await saveWrap.locator('[data-action="save-menu"]').click()
    await expect(saveWrap.locator('[data-action="save-html"]')).toBeVisible()
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      saveWrap.locator('[data-action="save-html"]').click(),
    ])

    expect(download.suggestedFilename()).toMatch(/\.html$/)
  })

  test('downloaded html file contains the command text', async ({ page }) => {
    const saveWrap = page.locator('.hud-actions .hud-save-wrap')
    await saveWrap.locator('[data-action="save-menu"]').click()
    await expect(saveWrap.locator('[data-action="save-html"]')).toBeVisible()
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      saveWrap.locator('[data-action="save-html"]').click(),
    ])

    const stream = await download.createReadStream()
    const chunks = []
    for await (const chunk of stream) chunks.push(chunk)
    const html = Buffer.concat(chunks).toString('utf8')

    expect(html).toContain(CMD)
    expect(html).toContain('data:font/woff2;base64,')
    expect(html).not.toContain('/vendor/fonts/')
    expect(html).not.toContain('fonts.googleapis.com')
    expect(html).not.toContain('fonts.gstatic.com')
  })

  test('summarize appends a signal summary block for the active tab output', async ({ page }) => {
    await page.evaluate(() => {
      clearTab(activeTabId)
      appendLine('443/tcp open https on ip.darklab.sh', '', activeTabId, {
        signals: ['findings'],
        command_root: 'nmap',
        target: 'ip.darklab.sh',
        entities: [{
          type: 'domain',
          value: 'ip.darklab.sh',
          canonical_value: 'ip.darklab.sh',
          start: 22,
          end: 35,
        }],
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

    const atlasToken = page.locator('.tab-panel.active .atlas-entity-token').first()
    await expect(atlasToken).toHaveText('ip.darklab.sh')
    const atlasTokenStyle = await atlasToken.evaluate((token) => {
      const style = window.getComputedStyle(token)
      return {
        display: style.display,
        borderTopWidth: style.borderTopWidth,
        borderTopLeftRadius: style.borderTopLeftRadius,
        backgroundColor: style.backgroundColor,
      }
    })
    expect(atlasTokenStyle).toMatchObject({
      display: 'inline',
      borderTopWidth: '0px',
      borderTopLeftRadius: '4px',
    })
    expect(atlasTokenStyle.backgroundColor).not.toBe('rgba(0, 0, 0, 0)')
    await expect(page.locator('link[href*="features/atlas.css"]')).toHaveCount(0)

    await page.locator('#search-summary-btn').click()

    const lines = page.locator('.tab-panel.active .output .line')
    await expect(lines.filter({ hasText: 'Command Findings:' })).toHaveCount(1)
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

  test('entity text stays selectable and deliberate activation opens the accessible action menu', async ({ page }) => {
    await appendEntityOutput(page)
    const token = page.locator('.tab-panel.active .atlas-entity-token')
    const menu = page.locator('.atlas-output-entity-menu')

    const selectedText = await token.evaluate((node) => {
      const selection = window.getSelection()
      const range = document.createRange()
      range.selectNodeContents(node)
      selection.removeAllRanges()
      selection.addRange(range)
      node.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
      return selection.toString()
    })
    expect(selectedText).toBe('IP.DARKLAB.SH')
    await expect(menu).toHaveCount(0)

    await token.click({ button: 'right' })
    await expect(menu).toHaveCount(0)
    await page.evaluate(() => window.getSelection()?.removeAllRanges())

    await token.click()
    await expect(menu).toBeVisible()
    await expect(menu.locator('[role="menuitem"]')).toHaveText([
      'Open in Atlas',
      'Copy to Clipboard',
      'Insert into command',
    ])
    await expect(token).toHaveAttribute('aria-expanded', 'true')
    await expect(token).toHaveAttribute('aria-controls', /atlas-output-entity-menu-/)
    const positions = await Promise.all([token.boundingBox(), menu.boundingBox()])
    expect(positions[0]).not.toBeNull()
    expect(positions[1]).not.toBeNull()
    expect(positions[1].x).toBeGreaterThanOrEqual(8)
    expect(positions[1].y).toBeGreaterThanOrEqual(8)

    await menu.locator('[data-output-entity-action="copy-value"]').click()
    await expect(menu).toHaveCount(0)
    await expect(page.locator('#permalink-toast')).toContainText('Entity copied')
    await expect(page.evaluate(() => window.__copiedEntity)).resolves.toBe('ip.darklab.sh')

    await token.focus()
    await token.press('Enter')
    await expect(menu).toBeVisible()
    await expect(menu.locator('[data-output-entity-action="open-atlas"]')).toBeFocused()
    await page.keyboard.press('End')
    await expect(menu.locator('[data-output-entity-action="insert-command"]')).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(menu).toHaveCount(0)
    await expect(token).toBeFocused()
    await expect(token).toHaveAttribute('aria-expanded', 'false')

    await token.click()
    await menu.locator('[data-output-entity-action="open-atlas"]').click()
    await expect(menu).toHaveCount(0)
    await expect(page.locator('#atlas-overlay')).toHaveClass(/\bopen\b/)
  })

  test('entity actions insert at the command selection without running it and close on shell typing', async ({ page }) => {
    await appendEntityOutput(page)
    const token = page.locator('.tab-panel.active .atlas-entity-token')
    const menu = page.locator('.atlas-output-entity-menu')
    const input = page.locator('#cmd')
    const lineCount = await page.locator('.tab-panel.active .output .line').count()

    await page.evaluate(() => setComposerValue('ping TARGET now', 5, 11))
    await token.click()
    await expect(menu).toBeVisible()
    // The insertion path itself is covered through a real tap below. Dispatch
    // here so Playwright's pre-click scroll-into-view step doesn't exercise the
    // separate scroll-to-dismiss contract before the fixed menu item activates.
    await menu.locator('[data-output-entity-action="insert-command"]').dispatchEvent('click')
    await expect(input).toHaveValue('ping ip.darklab.sh now')
    await expect(input).toBeFocused()
    await expect(page.locator('.tab-panel.active .output .line')).toHaveCount(lineCount)

    await token.click()
    await expect(menu).toBeVisible()
    await input.focus()
    await input.press('x')
    await expect(menu).toHaveCount(0)
  })
})

test.describe('mobile output entity actions', () => {
  test.use({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true,
  })

  test('tap opens a viewport-safe menu and inserts into the mobile composer', async ({ page }) => {
    await page.goto('/')
    await ensurePromptReady(page, { cancelWelcome: true })
    await expect.poll(
      () => page.evaluate(() => document.body.classList.contains('mobile-terminal-mode')),
    ).toBe(true)
    await appendEntityOutput(page)

    const token = page.locator('.tab-panel.active .atlas-entity-token')
    const menu = page.locator('.atlas-output-entity-menu')
    const input = page.locator('#mobile-cmd')
    await page.evaluate(() => setComposerValue('curl TARGET/path', 5, 11))

    await token.tap()
    await expect(menu).toBeVisible()
    const box = await menu.boundingBox()
    expect(box).not.toBeNull()
    expect(box.x).toBeGreaterThanOrEqual(8)
    expect(box.x + box.width).toBeLessThanOrEqual(382)
    expect(box.y).toBeGreaterThanOrEqual(8)
    expect(box.y + box.height).toBeLessThanOrEqual(836)

    await menu.locator('[data-output-entity-action="insert-command"]').tap()
    await expect(input).toHaveValue('curl ip.darklab.sh/path')
    await expect(input).toBeFocused()
    await expect(menu).toHaveCount(0)

    await token.tap()
    await expect(menu).toBeVisible()
    await input.tap()
    await input.press('x')
    await expect(menu).toHaveCount(0)
  })
})

test.describe('output actions with no exportable output', () => {
  test.beforeEach(async ({ page }) => {
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
      tab.outputUserScrollUntil = Date.now() + 1000
      out.scrollTop = 0
      tab.followOutput = false
      updateOutputFollowButton(activeTabId)
    })

    await expect
      .poll(async () =>
        page.evaluate(() => {
          const tab = getTab(activeTabId)
          const btn = document.querySelector('.tab-panel.active .output-follow-btn')
          return {
            status: tab?.st || '',
            followOutput: !!tab && tab.followOutput,
            hidden: !!btn && btn.hidden,
            text: btn?.textContent || '',
          }
        }),
      )
      .toEqual({
        status: 'running',
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
              tab.outputUserScrollUntil = Date.now() + 1000
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
    await expect(page.locator('#search-toggle-btn')).toHaveText('⌕ search')
    await expect(page.locator('#search-signal-summary')).toContainText('2F')
    await expect(page.locator('#search-signal-summary')).toContainText('2W')
    await expect(page.locator('#search-signal-summary')).toContainText('2E')
    await expect(page.locator('#search-signal-summary')).toContainText('1S')
    await page.locator('#search-toggle-btn').click()

    await expect(page.locator('[data-search-scope="text"]')).toHaveAttribute('aria-pressed', 'true')
    await expect(page.locator('#search-input')).toBeEnabled()
    await expect(page.locator('#search-input')).toBeFocused()
    await expect(page.locator('#search-count')).toHaveText('')
    await page.locator('[data-search-scope="findings"]').click()
    await expect(page.locator('#cmd')).toBeFocused()
    await expect(page.locator('#search-count')).toHaveText('1 / 2')
    await expect(page.locator('.tab-panel.active .line.search-signal-hl.current')).toContainText('443/tcp open https')

    await page.locator('[data-search-scope="warnings"]').click()

    await expect(page.locator('#cmd')).toBeFocused()
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
    await expect(page.locator('#cmd')).toBeFocused()
    await expect(page.locator('#search-count')).toHaveText('1 / 2')
    await expect(page.locator('.tab-panel.active .line.search-signal-hl.current')).toContainText('retry-after')

    await page.locator('[data-search-signal-scope="warnings"]').click()
    await expect(page.locator('#cmd')).toBeFocused()
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
