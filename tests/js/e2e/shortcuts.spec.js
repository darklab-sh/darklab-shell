import { test, expect } from '@playwright/test'
import { runCommand, makeTestIp } from './helpers.js'

const CMD = 'curl http://localhost:5001/health'
const TEST_IP = makeTestIp(70)

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
})
