import { test, expect } from '@playwright/test'
import { runCommand } from './helpers.js'

const CMD = 'curl http://localhost:5001/health'

async function dispatchMacOptionKey(page, selector, init) {
  await page.locator(selector).evaluate((el, eventInit) => {
    el.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, ...eventInit }))
  }, init)
}

test.describe('keyboard shortcuts', () => {
  test.beforeEach(async ({ page }) => {
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
})
