import { test, expect } from '@playwright/test'
import { runCommand } from './helpers.js'

// Use allowed commands that complete quickly.
const CMD   = 'curl http://localhost:5001/health'
const CMD_B = 'curl http://localhost:5001/config'

test.describe('max tabs', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('new-tab button is disabled after reaching the max-tabs limit', async ({ page }) => {
    // Read the configured limit from the running app
    const maxTabs = await page.evaluate(() => window.APP_CONFIG?.max_tabs ?? 8)

    // We already have 1 tab open; click until we hit the limit
    for (let i = 1; i < maxTabs; i++) {
      await page.locator('#new-tab-btn').click()
    }

    await expect(page.locator('#new-tab-btn')).toBeDisabled()
  })
})

test.describe('tab renaming', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('double-clicking a tab label lets the user rename it', async ({ page }) => {
    const label = page.locator('.tab').first().locator('.tab-label')

    await label.dblclick()
    const input = page.locator('.tab-rename-input')
    await input.waitFor({ state: 'visible' })

    await input.fill('my-tab')
    await input.press('Enter')

    await expect(label).toHaveText('my-tab')
  })

  test('pressing Escape cancels the rename and restores the original label', async ({ page }) => {
    const label = page.locator('.tab').first().locator('.tab-label')
    const original = await label.textContent()

    await label.dblclick()
    const input = page.locator('.tab-rename-input')
    await input.waitFor({ state: 'visible' })

    await input.fill('should-not-save')
    await input.press('Escape')

    await expect(label).toHaveText(original)
  })

  test('renamed labels stay in place after running another command', async ({ page }) => {
    const label = page.locator('.tab').first().locator('.tab-label')

    await label.dblclick()
    const input = page.locator('.tab-rename-input')
    await input.waitFor({ state: 'visible' })
    await input.fill('ops-tab')
    await input.press('Enter')
    await expect(label).toHaveText('ops-tab')

    await runCommand(page, CMD)

    await expect(label).toHaveText('ops-tab')
  })
})

test.describe('tab command recall', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    // Wait for the app to be fully initialised
    await page.locator('#cmd').waitFor()
  })

  test('input is empty on the initial tab', async ({ page }) => {
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('switching to a tab does not restore prior commands into input', async ({ page }) => {
    // Run a command on tab 1
    await runCommand(page, CMD)

    // Open a second tab
    await page.locator('#new-tab-btn').click()
    await expect(page.locator('#cmd')).toHaveValue('')

    // Run a different command on tab 2
    await runCommand(page, CMD_B)

    // Switch back to tab 1 (first tab in the bar)
    await page.locator('.tab').first().click()

    // Input stays neutral across tab switches
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('a freshly created tab starts with an empty input', async ({ page }) => {
    await runCommand(page, CMD)
    await page.locator('#new-tab-btn').click()
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('pressing Enter on a blank prompt appends a fresh prompt line', async ({ page }) => {
    await expect(page.locator('.line.welcome-hint')).toBeVisible({ timeout: 15000 })
    const beforeCount = await page.locator('.tab-panel.active .output .line.prompt-echo').count()

    await page.evaluate(() => {
      if (typeof requestWelcomeSettle === 'function') requestWelcomeSettle('tab-1')
    })
    await page.waitForFunction(() => {
      return typeof _welcomeActive !== 'undefined' ? _welcomeActive === false : true
    })

    await page.locator('#cmd').press('Enter')

    await expect(page.locator('.tab-panel.active .output .line.prompt-echo')).toHaveCount(beforeCount + 1)
    await expect(page.locator('#cmd')).toHaveValue('')
    await expect(page.locator('.status-pill')).toHaveText('IDLE')
  })
})

test.describe('tab closing', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('closing the only tab resets it instead of removing it', async ({ page }) => {
    await runCommand(page, CMD)

    await page.locator('.tab').first().locator('.tab-close').click()

    await expect(page.locator('.tab')).toHaveCount(1)
    await expect(page.locator('.tab .tab-label')).toHaveText('tab 1')
    await expect(page.locator('.tab-panel .output .line')).toHaveCount(0)
    await expect(page.locator('.tab-panel .output .shell-prompt-wrap')).toBeVisible()
    await expect(page.locator('#cmd')).toHaveValue('')
    await expect(page.locator('.status-pill')).toHaveText('IDLE')
  })
})

test.describe('tab strip interactions', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('drag reordering the active tab returns focus to the terminal input', async ({ page }) => {
    await page.locator('#new-tab-btn').click()

    const secondTab = page.locator('.tab').nth(1)
    await secondTab.click()
    await page.locator('#cmd').fill('')

    await secondTab.dragTo(page.locator('.tab').first())

    await expect(page.locator('#cmd')).toBeFocused()

    await page.keyboard.type('dig darklab.sh A')
    await expect(page.locator('#cmd')).toHaveValue('dig darklab.sh A')
  })
})
