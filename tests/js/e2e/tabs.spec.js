import { test, expect } from '@playwright/test'
import { runCommand, makeTestIp } from './helpers.js'

// Use allowed commands that complete quickly.
const CMD   = 'curl http://localhost:5001/health'
const CMD_B = 'curl http://localhost:5001/config'
const LONG_CMD = 'ping -c 1000 127.0.0.1'
const TEST_IP = makeTestIp(66)

test.describe('max tabs', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
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
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
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
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
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

  test('running a command in one tab does not block another tab from running', async ({ page }) => {
    await page.route('**/run', async route => {
      const body = route.request().postData() || '{}'
      const payload = JSON.parse(body)
      const command = payload.command || ''

      if (command === LONG_CMD) {
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: [
            'data: {"type":"started","run_id":"tabs-long-run"}\n\n',
            'data: {"type":"output","text":"long run started\\n"}\n\n',
          ].join(''),
        })
        return
      }

      if (command === CMD_B) {
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: [
            'data: {"type":"started","run_id":"tabs-second-run"}\n\n',
            'data: {"type":"output","text":"second tab output\\n"}\n\n',
            'data: {"type":"exit","code":0,"elapsed":0.1}\n\n',
          ].join(''),
        })
        return
      }

      await route.continue()
    })

    await page.locator('#cmd').fill(LONG_CMD)
    await page.keyboard.press('Enter')
    await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })

    await page.locator('#new-tab-btn').click()
    await expect(page.locator('#cmd')).toHaveValue('')

    await page.locator('#cmd').fill(CMD_B)
    await page.keyboard.press('Enter')

    await expect(page.locator('.tab-panel.active .output .line.exit-ok')).toBeVisible({ timeout: 15_000 })
    await page.locator('.tab').first().click()
    await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })
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
      if (typeof requestWelcomeSettle === 'function') requestWelcomeSettle()
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
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
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
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
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

  test('touch dragging reorders tabs and clears mobile drag state on release', async ({ page }) => {
    await page.locator('#new-tab-btn').click()
    await page.locator('#new-tab-btn').click()

    const firstTab = page.locator('.tab').nth(0)
    const thirdTab = page.locator('.tab').nth(2)
    const firstBox = await firstTab.boundingBox()
    const thirdBox = await thirdTab.boundingBox()
    if (!firstBox || !thirdBox) throw new Error('Tab bounding boxes were not available')

    await page.evaluate(({ downX, downY }) => {
      const tab = document.querySelectorAll('.tab')[2]
      tab?.dispatchEvent(new PointerEvent('pointerdown', {
        bubbles: true,
        cancelable: true,
        pointerId: 41,
        pointerType: 'touch',
        clientX: downX,
        clientY: downY,
      }))
    }, {
      downX: thirdBox.x + (thirdBox.width / 2),
      downY: thirdBox.y + (thirdBox.height / 2),
    })

    await page.evaluate(({ moveX, moveY }) => {
      document.dispatchEvent(new PointerEvent('pointermove', {
        bubbles: true,
        cancelable: true,
        pointerId: 41,
        pointerType: 'touch',
        clientX: moveX,
        clientY: moveY,
      }))
    }, {
      moveX: firstBox.x + 8,
      moveY: firstBox.y + (firstBox.height / 2),
    })

    await expect(page.locator('#tabs-bar')).toHaveClass(/tabs-bar-touch-sorting/)
    await expect(page.locator('.tab').nth(0)).toHaveClass(/tab-touch-dragging/)
    await expect(page.locator('.tab').nth(1)).toHaveClass(/tab-drop-before/)

    await page.evaluate(({ upX, upY }) => {
      document.dispatchEvent(new PointerEvent('pointerup', {
        bubbles: true,
        cancelable: true,
        pointerId: 41,
        pointerType: 'touch',
        clientX: upX,
        clientY: upY,
      }))
    }, {
      upX: firstBox.x + 8,
      upY: firstBox.y + (firstBox.height / 2),
    })

    await expect(page.locator('#tabs-bar')).not.toHaveClass(/tabs-bar-touch-sorting/)
    await expect(page.locator('.tab').first()).toContainText('tab 3')
    await expect(page.locator('.tab-drop-before, .tab-drop-after')).toHaveCount(0)
    await expect(page.locator('#cmd')).toBeFocused()
  })
})
