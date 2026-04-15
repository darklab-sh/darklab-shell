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

  test('macOS Option+T opens a new tab without inserting a symbol into the prompt', async ({ page }) => {
    await expect(page.locator('.tab')).toHaveCount(1)

    await dispatchMacOptionKey(page, '#cmd', {
      key: '†',
      code: 'KeyT',
      altKey: true,
    })

    await expect(page.locator('.tab')).toHaveCount(2)
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('macOS Option+W closes the active tab without inserting a symbol into the prompt', async ({ page }) => {
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

  test('macOS Option+Shift+C copies active-tab output without inserting a symbol into the prompt', async ({ page }) => {
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

  test('macOS Option+P creates a permalink without inserting a symbol into the prompt', async ({ page }) => {
    await runCommand(page, CMD)

    await dispatchMacOptionKey(page, '#cmd', {
      key: 'π',
      code: 'KeyP',
      altKey: true,
    })

    await expect(page.locator('#share-redaction-overlay')).toBeVisible()
    await page.locator('#share-redaction-confirm').click()
    await expect(page.locator('#permalink-toast')).toHaveClass(/show/, { timeout: 5000 })
    await expect(page.locator('#permalink-toast')).toContainText(/link copied/i)
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('macOS Option+ArrowRight and Option+ArrowLeft cycle tabs', async ({ page }) => {
    await page.locator('#new-tab-btn').click()
    await page.locator('#new-tab-btn').click()
    await expect(page.locator('.tab')).toHaveCount(3)
    await expect(page.locator('.tab.active .tab-label')).toHaveText('tab 3')

    await dispatchMacOptionKey(page, '#cmd', {
      key: 'ArrowLeft',
      code: 'ArrowLeft',
      altKey: true,
    })
    await expect(page.locator('.tab.active .tab-label')).toHaveText('tab 2')

    await dispatchMacOptionKey(page, '#cmd', {
      key: 'ArrowRight',
      code: 'ArrowRight',
      altKey: true,
    })
    await expect(page.locator('.tab.active .tab-label')).toHaveText('tab 3')
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('macOS Option+digit jumps directly to a tab without inserting a symbol', async ({ page }) => {
    await page.locator('#new-tab-btn').click()
    await page.locator('#new-tab-btn').click()
    await expect(page.locator('.tab')).toHaveCount(3)

    await dispatchMacOptionKey(page, '#cmd', {
      key: '£',
      code: 'Digit3',
      altKey: true,
    })
    await expect(page.locator('.tab.active .tab-label')).toHaveText('tab 3')

    await dispatchMacOptionKey(page, '#cmd', {
      key: '¡',
      code: 'Digit1',
      altKey: true,
    })
    await expect(page.locator('.tab.active .tab-label')).toHaveText('tab 1')
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

  test('macOS Option+B and Option+F move by word without inserting symbols into the prompt', async ({ page }) => {
    const input = page.locator('#cmd')
    await input.fill('dig darklab.sh A')
    await input.evaluate(el => el.setSelectionRange(el.value.length, el.value.length))

    await dispatchMacOptionKey(page, '#cmd', {
      key: '∫',
      code: 'KeyB',
      altKey: true,
    })

    let selection = await input.evaluate(el => ({
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

    selection = await input.evaluate(el => ({
      value: el.value,
      start: el.selectionStart,
      end: el.selectionEnd,
    }))
    expect(selection.value).toBe('dig darklab.sh A')
    expect(selection.start).toBe(16)
    expect(selection.end).toBe(16)
  })

  test('desktop prompt cursor follows repeated caret moves while arrowing across the command', async ({ page }) => {
    const input = page.locator('#cmd')
    await input.fill('curl darklab.sh')
    await input.focus()

    const promptCaret = page.locator('#shell-prompt-text .shell-caret-char')

    for (const [pos, ch] of [[0, 'c'], [1, 'u'], [2, 'r'], [3, 'l']]) {
      await input.evaluate((el, nextPos) => el.setSelectionRange(nextPos, nextPos), pos)
      await page.evaluate(() => document.dispatchEvent(new Event('selectionchange')))
      await expect(promptCaret).toHaveText(ch)
    }
  })

  test('history and submit shortcuts still work after transcript text is selected', async ({ page }) => {
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
      { timeout: 15_000 }
    )
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
      { timeout: 15_000 }
    )
  })

  test('Tab in hist-search accepts the match into the input without running the command', async ({ page }) => {
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

  test('ArrowDown in hist-search navigates to the next match and fills the input', async ({ page }) => {
    await runCommand(page, 'hostname')
    await runCommand(page, 'dig darklab.sh A')
    await page.locator('#cmd').press('Control+r')
    // 'host' only matches 'hostname', not 'dig darklab.sh A'
    await page.locator('#cmd').type('host')
    await expect(page.locator('#hist-search-dropdown .hist-search-item')).toHaveCount(1)

    // Before ArrowDown, input has the typed query
    await expect(page.locator('#cmd')).toHaveValue('host')
    await page.locator('#cmd').press('ArrowDown')
    // Only one match, so ArrowDown clamps — input stays as the current match
    await expect(page.locator('#cmd')).toHaveValue('hostname')
  })

  test('Escape in hist-search closes the dropdown and restores the pre-search draft', async ({ page }) => {
    await runCommand(page, 'hostname')
    await page.locator('#cmd').fill('my draft')
    await page.locator('#cmd').press('Control+r')
    await page.locator('#cmd').type('host')
    await page.locator('#cmd').press('Escape')
    await expect(page.locator('#hist-search-dropdown')).toHaveClass(/u-hidden/)
    await expect(page.locator('#cmd')).toHaveValue('my draft')
  })

  test('Ctrl+C in hist-search closes the dropdown and keeps the typed query in the input', async ({ page }) => {
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
