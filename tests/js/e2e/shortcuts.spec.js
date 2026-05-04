import { test, expect } from '@playwright/test'
import { ensurePromptReady, runCommand, makeTestIp, waitForHistoryRuns } from './helpers.js'

const CMD = 'curl http://localhost:5001/health'
const TEST_IP = makeTestIp(70)
const HIST_SEARCH_IP = makeTestIp(71)

async function dispatchMacOptionKey(page, selector, init) {
  await page.locator(selector).evaluate((el, eventInit) => {
    el.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, ...eventInit }))
  }, init)
}

test.describe('keyboard shortcuts', () => {
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
    await ensurePromptReady(page)
  })

  test('macOS Option+T opens a new tab without inserting a symbol into the prompt', async ({
    page,
  }) => {
    await expect(page.locator('.tab')).toHaveCount(1)

    await dispatchMacOptionKey(page, '#cmd', {
      key: '†',
      code: 'KeyT',
      altKey: true,
    })

    await expect(page.locator('.tab')).toHaveCount(2)
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('macOS Option+W closes the active tab without inserting a symbol into the prompt', async ({
    page,
  }) => {
    await page.locator('#new-tab-btn').click()
    await expect(page.locator('.tab')).toHaveCount(2)
    await page.locator('.tab').nth(1).click()

    await dispatchMacOptionKey(page, '#cmd', {
      key: '∑',
      code: 'KeyW',
      altKey: true,
    })

    await expect(page.locator('.tab')).toHaveCount(1)
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('macOS Option+Shift+C copies active-tab output without inserting a symbol into the prompt', async ({
    page,
  }) => {
    await runCommand(page, CMD)

    await dispatchMacOptionKey(page, '#cmd', {
      key: 'Ç',
      code: 'KeyC',
      altKey: true,
      shiftKey: true,
    })

    await expect(page.locator('#permalink-toast')).toHaveClass(/show/, { timeout: 5000 })
    await expect(page.locator('#permalink-toast')).toContainText(/copied/i)
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('macOS Option+P creates a permalink without inserting a symbol into the prompt', async ({
    page,
  }) => {
    await runCommand(page, CMD)

    await dispatchMacOptionKey(page, '#cmd', {
      key: 'π',
      code: 'KeyP',
      altKey: true,
    })

    await expect(page.locator('#confirm-host')).toBeVisible()
    await page.locator('#confirm-host [data-confirm-action-id="redacted"]').click()
    await expect(page.locator('#permalink-toast')).toHaveClass(/show/, { timeout: 5000 })
    await expect(page.locator('#permalink-toast')).toContainText(/link copied/i)
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('macOS Option+ArrowRight and Option+ArrowLeft move by word', async ({ page }) => {
    await page.locator('#new-tab-btn').click()
    await page.locator('#new-tab-btn').click()
    await expect(page.locator('.tab')).toHaveCount(3)
    await expect(page.locator('.tab.active .tab-label')).toHaveText('shell 3')

    const input = page.locator('#cmd')
    await input.fill('dig darklab.sh A')
    await input.evaluate((el) => el.setSelectionRange(el.value.length, el.value.length))

    await dispatchMacOptionKey(page, '#cmd', {
      key: 'ArrowLeft',
      code: 'ArrowLeft',
      altKey: true,
    })
    let selection = await input.evaluate((el) => ({
      value: el.value,
      start: el.selectionStart,
      end: el.selectionEnd,
    }))
    expect(selection.value).toBe('dig darklab.sh A')
    expect(selection.start).toBe(15)
    expect(selection.end).toBe(15)
    await expect(page.locator('.tab.active .tab-label')).toHaveText('shell 3')

    await dispatchMacOptionKey(page, '#cmd', {
      key: 'ArrowLeft',
      code: 'ArrowLeft',
      altKey: true,
    })
    selection = await input.evaluate((el) => ({
      value: el.value,
      start: el.selectionStart,
      end: el.selectionEnd,
    }))
    expect(selection.start).toBe(4)
    expect(selection.end).toBe(4)

    await dispatchMacOptionKey(page, '#cmd', {
      key: 'ArrowRight',
      code: 'ArrowRight',
      altKey: true,
    })
    selection = await input.evaluate((el) => ({
      value: el.value,
      start: el.selectionStart,
      end: el.selectionEnd,
    }))
    expect(selection.start).toBe(14)
    expect(selection.end).toBe(14)
    await expect(page.locator('.tab.active .tab-label')).toHaveText('shell 3')
  })

  test('macOS Shift+Option+ArrowRight and Shift+Option+ArrowLeft cycle tabs', async ({ page }) => {
    await page.locator('#new-tab-btn').click()
    await page.locator('#new-tab-btn').click()
    await expect(page.locator('.tab')).toHaveCount(3)
    await expect(page.locator('.tab.active .tab-label')).toHaveText('shell 3')

    await dispatchMacOptionKey(page, '#cmd', {
      key: 'ArrowLeft',
      code: 'ArrowLeft',
      altKey: true,
      shiftKey: true,
    })
    await expect(page.locator('.tab.active .tab-label')).toHaveText('shell 2')

    await dispatchMacOptionKey(page, '#cmd', {
      key: 'ArrowRight',
      code: 'ArrowRight',
      altKey: true,
      shiftKey: true,
    })
    await expect(page.locator('.tab.active .tab-label')).toHaveText('shell 3')
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('macOS Option+digit jumps directly to a tab without inserting a symbol', async ({
    page,
  }) => {
    await page.locator('#new-tab-btn').click()
    await page.locator('#new-tab-btn').click()
    await expect(page.locator('.tab')).toHaveCount(3)

    await dispatchMacOptionKey(page, '#cmd', {
      key: '£',
      code: 'Digit3',
      altKey: true,
    })
    await expect(page.locator('.tab.active .tab-label')).toHaveText('shell 3')

    await dispatchMacOptionKey(page, '#cmd', {
      key: '¡',
      code: 'Digit1',
      altKey: true,
    })
    await expect(page.locator('.tab.active .tab-label')).toHaveText('shell 1')
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('Ctrl+L clears the active tab output in the browser', async ({ page }) => {
    await runCommand(page, CMD)
    await expect(page.locator('.tab-panel.active .output')).not.toBeEmpty()

    await page.locator('#cmd').press('Control+l')

    await expect(page.locator('.tab-panel.active .output .line')).toHaveCount(0)
    await expect(page.locator('.tab-panel.active .output .shell-prompt-wrap')).toBeVisible()
    await expect(page.locator('.status-pill')).toHaveText('IDLE')
  })

  test('macOS Option+B and Option+F move by word without inserting symbols into the prompt', async ({
    page,
  }) => {
    const input = page.locator('#cmd')
    await input.fill('dig darklab.sh A')
    await input.evaluate((el) => el.setSelectionRange(el.value.length, el.value.length))

    await dispatchMacOptionKey(page, '#cmd', {
      key: '∫',
      code: 'KeyB',
      altKey: true,
    })

    let selection = await input.evaluate((el) => ({
      value: el.value,
      start: el.selectionStart,
      end: el.selectionEnd,
    }))
    expect(selection.value).toBe('dig darklab.sh A')
    expect(selection.start).toBe(15)
    expect(selection.end).toBe(15)

    await dispatchMacOptionKey(page, '#cmd', {
      key: 'ƒ',
      code: 'KeyF',
      altKey: true,
    })

    selection = await input.evaluate((el) => ({
      value: el.value,
      start: el.selectionStart,
      end: el.selectionEnd,
    }))
    expect(selection.value).toBe('dig darklab.sh A')
    expect(selection.start).toBe(16)
    expect(selection.end).toBe(16)
  })

  test('desktop prompt cursor follows repeated caret moves while arrowing across the command', async ({
    page,
  }) => {
    const input = page.locator('#cmd')
    await input.fill('curl darklab.sh')
    await input.focus()

    const promptCaret = page.locator('#shell-prompt-text .shell-caret-char')

    for (const [pos, ch] of [
      [0, 'c'],
      [1, 'u'],
      [2, 'r'],
      [3, 'l'],
    ]) {
      await input.evaluate((el, nextPos) => el.setSelectionRange(nextPos, nextPos), pos)
      await page.evaluate(() => document.dispatchEvent(new Event('selectionchange')))
      await expect(promptCaret).toHaveText(ch)
    }
  })

  test('history and submit shortcuts still work after transcript text is selected', async ({
    page,
  }) => {
    await runCommand(page, 'hostname')
    const lineCountBefore = await page.locator('.tab-panel.active .output .line').count()

    await page.evaluate(() => {
      const firstLine = document.querySelector('.tab-panel.active .output .line')
      const searchBtn = document.getElementById('search-toggle-btn')
      if (!firstLine || !searchBtn) throw new Error('selection setup failed')
      const selection = window.getSelection()
      const range = document.createRange()
      range.selectNodeContents(firstLine)
      selection.removeAllRanges()
      selection.addRange(range)
      searchBtn.focus()
    })

    await page.keyboard.press('ArrowUp')
    await expect(page.locator('#cmd')).toHaveValue('hostname')

    await page.keyboard.press('Enter')
    await page.waitForFunction(
      (before) => document.querySelectorAll('.tab-panel.active .output .line').length > before,
      lineCountBefore,
      { timeout: 15_000 },
    )
  })

  test('paste routes to the prompt after copying selected transcript text', async ({
    page,
  }) => {
    await runCommand(page, 'hostname')

    await page.evaluate(() => {
      const firstLine = document.querySelector('.tab-panel.active .output .line')
      const searchBtn = document.getElementById('search-toggle-btn')
      if (!firstLine || !searchBtn) throw new Error('selection setup failed')
      const selection = window.getSelection()
      const range = document.createRange()
      range.selectNodeContents(firstLine)
      selection.removeAllRanges()
      selection.addRange(range)
      searchBtn.focus()
    })

    await page.evaluate(() => {
      const event = new Event('paste', { bubbles: true, cancelable: true })
      Object.defineProperty(event, 'clipboardData', {
        value: {
          getData: (type) => (type === 'text/plain' || type === 'text' ? 'host darklab.sh' : ''),
        },
      })
      document.dispatchEvent(event)
    })

    await expect(page.locator('#cmd')).toHaveValue('host darklab.sh')
    await expect(page.locator('#cmd')).toBeFocused()
  })
})

test.describe('Ctrl+R reverse-history search', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': HIST_SEARCH_IP })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('Ctrl+R opens the hist-search dropdown after a command has been run', async ({ page }) => {
    await runCommand(page, 'hostname')
    await page.locator('#cmd').press('Control+r')
    await expect(page.locator('#hist-search-dropdown')).not.toHaveClass(/u-hidden/)
  })

  test('typing while hist-search is open filters matches in the dropdown', async ({ page }) => {
    await runCommand(page, 'hostname')
    await page.locator('#cmd').press('Control+r')
    await page.locator('#cmd').type('host')
    await expect(page.locator('#hist-search-dropdown .hist-search-item')).toHaveCount(1)
    await expect(page.locator('#hist-search-dropdown .hist-search-item')).toContainText('hostname')
  })

  test('Enter in hist-search accepts the match and runs the command', async ({ page }) => {
    await runCommand(page, 'hostname')
    const linesBefore = await page.locator('.tab-panel.active .output .line').count()
    await page.locator('#cmd').press('Control+r')
    await page.locator('#cmd').type('host')
    await page.locator('#cmd').press('Enter')
    // dropdown should close and new output lines should appear from the second run
    await expect(page.locator('#hist-search-dropdown')).toHaveClass(/u-hidden/)
    await page.waitForFunction(
      (before) => document.querySelectorAll('.tab-panel.active .output .line').length > before,
      linesBefore,
      { timeout: 15_000 },
    )
  })

  test('Tab in hist-search accepts the match into the input without running the command', async ({
    page,
  }) => {
    await runCommand(page, 'hostname')
    // Ensure the run is committed server-side so the debounced fetch finds it
    await waitForHistoryRuns(page, 1)
    const linesBefore = await page.locator('.tab-panel.active .output .line').count()
    await page.locator('#cmd').press('Control+r')
    await page.locator('#cmd').type('host')
    // Wait for the dropdown to show the match before accepting with Tab
    await expect(page.locator('#hist-search-dropdown .hist-search-item')).toContainText('hostname')
    await page.locator('#cmd').press('Tab')
    // dropdown should close, input should have the accepted value
    await expect(page.locator('#hist-search-dropdown')).toHaveClass(/u-hidden/)
    await expect(page.locator('#cmd')).toHaveValue('hostname')
    // command should not have run — line count stays the same
    const linesAfter = await page.locator('.tab-panel.active .output .line').count()
    expect(linesAfter).toBe(linesBefore)
  })

  test('ArrowDown in hist-search navigates to the next match and fills the input', async ({
    page,
  }) => {
    await runCommand(page, 'hostname')
    await runCommand(page, 'whoami')
    await waitForHistoryRuns(page, 2)
    await page.locator('#cmd').press('Control+r')
    // 'host' only matches 'hostname', not the other seeded history row.
    await page.locator('#cmd').type('host')
    await expect(page.locator('#hist-search-dropdown .hist-search-item')).toHaveCount(1)

    // Before ArrowDown, input has the typed query
    await expect(page.locator('#cmd')).toHaveValue('host')
    await page.locator('#cmd').press('ArrowDown')
    // Only one match, so ArrowDown clamps — input stays as the current match
    await expect(page.locator('#cmd')).toHaveValue('hostname')
  })

  test('Escape in hist-search closes the dropdown and restores the pre-search draft', async ({
    page,
  }) => {
    await runCommand(page, 'hostname')
    await page.locator('#cmd').fill('my draft')
    await page.locator('#cmd').press('Control+r')
    await page.locator('#cmd').type('host')
    await page.locator('#cmd').press('Escape')
    await expect(page.locator('#hist-search-dropdown')).toHaveClass(/u-hidden/)
    await expect(page.locator('#cmd')).toHaveValue('my draft')
  })

  test('Ctrl+C in hist-search closes the dropdown and keeps the typed query in the input', async ({
    page,
  }) => {
    await runCommand(page, 'hostname')
    await page.locator('#cmd').fill('my draft')
    await page.locator('#cmd').press('Control+r')
    await page.locator('#cmd').type('host')
    await page.locator('#cmd').press('Control+c')
    await expect(page.locator('#hist-search-dropdown')).toHaveClass(/u-hidden/)
    // keepCurrent: typed query stays, pre-draft is NOT restored
    await expect(page.locator('#cmd')).toHaveValue('host')
  })
})

test.describe('? keyboard-shortcuts overlay', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': makeTestIp(73) })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
    await ensurePromptReady(page)
  })

  test('? opens the overlay when no input is focused', async ({ page }) => {
    await page.locator('#cmd').evaluate(el => el.blur())
    await page.keyboard.press('?')
    await expect(page.locator('#shortcuts-overlay')).toHaveClass(/\bopen\b/)
    const rowCount = await page.locator('#shortcuts-list .shortcut-key').count()
    expect(rowCount).toBeGreaterThan(10)
    // Self-documenting: the overlay lists its own `?` trigger.
    await expect(page.locator('#shortcuts-list')).toContainText('?')
  })

  test('Escape closes the overlay', async ({ page }) => {
    await page.locator('#cmd').evaluate(el => el.blur())
    await page.keyboard.press('?')
    await expect(page.locator('#shortcuts-overlay')).toHaveClass(/\bopen\b/)
    await page.keyboard.press('Escape')
    await expect(page.locator('#shortcuts-overlay')).not.toHaveClass(/\bopen\b/)
  })

  test('? opens the overlay from the empty command prompt', async ({ page }) => {
    await page.locator('#cmd').focus()
    await expect(page.locator('#cmd')).toHaveValue('')
    await page.keyboard.press('?')
    await expect(page.locator('#shortcuts-overlay')).toHaveClass(/\bopen\b/)
    // The `?` character should NOT have been inserted into the prompt.
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('? types normally when the command prompt already has text', async ({ page }) => {
    await page.locator('#cmd').focus()
    await page.locator('#cmd').type('curl ')
    await page.keyboard.press('?')
    await expect(page.locator('#shortcuts-overlay')).not.toHaveClass(/\bopen\b/)
    await expect(page.locator('#cmd')).toHaveValue('curl ?')
  })

  test('? opens after word-jump shortcuts and deleting the prompt', async ({ page }) => {
    const input = page.locator('#cmd')
    const overlay = page.locator('#shortcuts-overlay')

    async function resetPrompt() {
      await input.focus()
      await input.fill('dig darklab.sh A')
      await input.evaluate((el) => el.setSelectionRange(el.value.length, el.value.length))
    }

    await resetPrompt()
    await dispatchMacOptionKey(page, '#cmd', {
      key: 'ArrowLeft',
      code: 'ArrowLeft',
      altKey: true,
    })
    await dispatchMacOptionKey(page, '#cmd', {
      key: 'ArrowRight',
      code: 'ArrowRight',
      altKey: true,
    })
    for (let i = 0; i < 16; i += 1) await page.keyboard.press('Backspace')
    await expect(input).toHaveValue('')
    await expect(page.locator('#shell-prompt-wrap')).toHaveClass(/\bshell-prompt-empty\b/)
    await expect(page.locator('#shell-prompt-wrap')).not.toHaveClass(/\bshell-prompt-has-value\b/)
    await page.keyboard.press('?')
    await expect(overlay).toHaveClass(/\bopen\b/)
    await page.keyboard.press('Escape')

    await resetPrompt()
    await dispatchMacOptionKey(page, '#cmd', {
      key: '∫',
      code: 'KeyB',
      altKey: true,
    })
    await dispatchMacOptionKey(page, '#cmd', {
      key: 'ƒ',
      code: 'KeyF',
      altKey: true,
    })
    await input.press('Control+u')
    await expect(input).toHaveValue('')
    await page.keyboard.press('?')
    await expect(overlay).toHaveClass(/\bopen\b/)
  })

  test('overlay and shortcuts built-in share the same source', async ({ page }) => {
    // Built-in command output
    await runCommand(page, 'shortcuts')
    const termText = await page.locator('.tab-panel.active .output').innerText()
    // Overlay payload (grouped into sections)
    const overlay = await page.evaluate(async () => {
      const resp = await fetch('/shortcuts')
      const data = await resp.json()
      const keys = []
      for (const section of data.sections || []) {
        for (const item of section.items || []) keys.push(item.key)
      }
      return { sectionTitles: (data.sections || []).map(s => s.title), keys }
    })
    // Section headers appear in both surfaces.
    for (const title of overlay.sectionTitles) {
      expect(termText).toContain(`${title}:`)
    }
    // Every overlay key appears in the terminal output (both render from the
    // same source of truth).
    for (const key of overlay.keys) {
      expect(termText).toContain(key)
    }
  })
})

test.describe('desktop chrome keyboard shortcuts', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': makeTestIp(74) })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
    await ensurePromptReady(page)
    // Keep the composer focused — that's the real-world default, and chords
    // must fire without the Option glyph leaking into the prompt on macOS.
    await page.locator('#cmd').focus()
  })

  test('Alt+H toggles the history drawer from the composer', async ({ page }) => {
    await dispatchMacOptionKey(page, '#cmd', { key: '˙', code: 'KeyH', altKey: true })
    await expect(page.locator('#history-panel')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#cmd')).toHaveValue('')
    await dispatchMacOptionKey(page, '#cmd', { key: '˙', code: 'KeyH', altKey: true })
    await expect(page.locator('#history-panel')).not.toHaveClass(/\bopen\b/)
  })

  test('Alt+, opens the options panel from the composer', async ({ page }) => {
    await dispatchMacOptionKey(page, '#cmd', { key: '≤', code: 'Comma', altKey: true })
    await expect(page.locator('#options-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('Alt+Shift+T opens the theme selector from the composer', async ({ page }) => {
    await dispatchMacOptionKey(page, '#cmd', { key: 'ˇ', code: 'KeyT', altKey: true, shiftKey: true })
    await expect(page.locator('#theme-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('Alt+G opens the workflows overlay from the composer', async ({ page }) => {
    await dispatchMacOptionKey(page, '#cmd', { key: '©', code: 'KeyG', altKey: true })
    await expect(page.locator('#workflows-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('Alt+S toggles the transcript search bar from the composer', async ({ page }) => {
    await expect(page.locator('#search-bar')).not.toBeVisible()
    await dispatchMacOptionKey(page, '#cmd', { key: 'ß', code: 'KeyS', altKey: true })
    await expect(page.locator('#search-bar')).toBeVisible()
    await expect(page.locator('#cmd')).toHaveValue('')
    await dispatchMacOptionKey(page, '#cmd', { key: 'ß', code: 'KeyS', altKey: true })
    await expect(page.locator('#search-bar')).not.toBeVisible()
  })

  test('Alt+M toggles the Status Monitor from the composer', async ({ page }) => {
    await page.route('**/history/active', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runs: [{
          run_id: 'run-shortcut-1',
          pid: 4242,
          started: new Date().toISOString(),
          command: 'sleep 60',
        }],
      }),
    }))

    await dispatchMacOptionKey(page, '#cmd', { key: 'µ', code: 'KeyM', altKey: true })
    await expect(page.locator('#status-monitor')).toBeVisible()
    await expect(page.locator('#status-monitor')).toContainText('sleep 60')
    await expect(page.locator('#cmd')).toHaveValue('')
    await dispatchMacOptionKey(page, '#cmd', { key: 'µ', code: 'KeyM', altKey: true })
    await expect(page.locator('#status-monitor')).toBeHidden()
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('Alt+Shift+F opens the Files modal from the composer', async ({ page }) => {
    await dispatchMacOptionKey(page, '#cmd', { key: 'Ï', code: 'KeyF', altKey: true, shiftKey: true })
    await expect(page.locator('#workspace-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('Alt+\\ toggles the rail collapsed state from the composer', async ({ page }) => {
    const rail = page.locator('#rail')
    const startsCollapsed = await rail.evaluate(el => el.classList.contains('rail-collapsed'))
    await dispatchMacOptionKey(page, '#cmd', { key: '«', code: 'Backslash', altKey: true })
    if (startsCollapsed) {
      await expect(rail).not.toHaveClass(/\brail-collapsed\b/)
    } else {
      await expect(rail).toHaveClass(/\brail-collapsed\b/)
    }
    await expect(page.locator('#cmd')).toHaveValue('')
    await dispatchMacOptionKey(page, '#cmd', { key: '«', code: 'Backslash', altKey: true })
    if (startsCollapsed) {
      await expect(rail).toHaveClass(/\brail-collapsed\b/)
    } else {
      await expect(rail).not.toHaveClass(/\brail-collapsed\b/)
    }
  })

  test('Alt+/ toggles the FAQ overlay from the composer', async ({ page }) => {
    const faq = page.locator('#faq-overlay')
    await expect(faq).not.toHaveClass(/\bopen\b/)
    await dispatchMacOptionKey(page, '#cmd', { key: '÷', code: 'Slash', altKey: true })
    await expect(faq).toHaveClass(/\bopen\b/)
    await expect(page.locator('#cmd')).toHaveValue('')
    await dispatchMacOptionKey(page, '#cmd', { key: '÷', code: 'Slash', altKey: true })
    await expect(faq).not.toHaveClass(/\bopen\b/)
  })
})
