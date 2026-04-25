import { test, expect } from '@playwright/test'
import { ensurePromptReady, runCommand, makeTestIp } from './helpers.js'

// Use allowed commands that complete quickly.
const CMD = 'hostname'
const CMD_B = 'date'
const LONG_CMD = 'ping -c 1000 darklab.sh'
const TEST_IP = makeTestIp(66)

test.describe('max tabs', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
    await ensurePromptReady(page)
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
    await ensurePromptReady(page)
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

  test('default labels restore after a command finishes running', async ({ page }) => {
    const label = page.locator('.tab').first().locator('.tab-label')

    await expect(label).toHaveText('shell 1')
    await runCommand(page, CMD)

    await expect(label).toHaveText('shell 1')
  })
})

test.describe('tab command recall', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
    await page.goto('/')
    // Wait for the app to be fully initialised
    await page.locator('#cmd').waitFor()
    await ensurePromptReady(page)
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
    const secondCmd = 'status'

    await page.route('**/run', async (route) => {
      const payload = JSON.parse(route.request().postData() || '{}')
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

      if (command === secondCmd) {
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

    await page.locator('#cmd').fill(secondCmd)
    await page.keyboard.press('Enter')

    await expect(page.locator('.tab-panel.active .output .line.exit-ok')).toBeVisible({
      timeout: 15_000,
    })
    await page.locator('.tab').first().click()
    await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })
  })

  test('a freshly created tab starts with an empty input', async ({ page }) => {
    await runCommand(page, CMD)
    await page.locator('#new-tab-btn').click()
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('reload restores non-running tabs, transcript preview, and the active draft', async ({
    page,
  }) => {
    const restoreCmd = 'hostname'
    await runCommand(page, restoreCmd)
    await expect(page.locator('.tab-panel.active .output')).toContainText(restoreCmd)

    await page.locator('#new-tab-btn').click()
    await page.locator('#cmd').fill('ffuf -u https://target/FUZZ')
    await expect(page.locator('#cmd')).toHaveValue('ffuf -u https://target/FUZZ')

    await page.reload()
    await page.locator('#cmd').waitFor()

    await expect(page.locator('.tab')).toHaveCount(2)
    await expect(page.locator('.welcome-banner')).toHaveCount(0)
    await expect(page.locator('#cmd')).toHaveValue('ffuf -u https://target/FUZZ')

    await page.locator('.tab').first().click()
    await expect(page.locator('.tab-panel.active .output')).toContainText(restoreCmd)
    await expect
      .poll(async () => page.locator('.tab-panel.active .output .line').count())
      .toBeGreaterThan(1)
  })

  test('reload restores a completed tab with a visible prompt and preserved prompt formatting', async ({
    page,
  }) => {
    const restoreCmd = 'status'
    await runCommand(page, restoreCmd)
    await expect(page.locator('.tab-panel.active .output .line.prompt-echo')).toContainText(
      restoreCmd,
    )

    await page.reload()
    await page.locator('#cmd').waitFor()

    const activeOutput = page.locator('.tab-panel.active .output')
    const promptEcho = page.locator('.tab-panel.active .output .line.prompt-echo').first()
    const livePrompt = page.locator('.tab-panel.active .output #shell-prompt-wrap')

    await expect(activeOutput).toContainText(restoreCmd)
    await expect(promptEcho.locator('.prompt-prefix')).toContainText('$')
    await expect(livePrompt).toBeVisible()

    await page.locator('#cmd').fill('hostname')
    await expect(page.locator('#cmd')).toHaveValue('hostname')
  })

  test('reload restores idle tabs and drafts alongside an active-run reconnect tab', async ({
    page,
  }) => {
    const idleCmd = 'status'
    const activeCmd = 'ping darklab.sh'
    let activeRunStarted = false

    await page.route('**/run', async (route) => {
      const body = route.request().postData() || '{}'
      const payload = JSON.parse(body)
      if ((payload.command || '') !== activeCmd) {
        await route.continue()
        return
      }
      activeRunStarted = true
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: [
          'data: {"type":"started","run_id":"tabs-reconnect-run"}\n\n',
          'data: {"type":"output","text":"long run started\\n"}\n\n',
        ].join(''),
      })
    })

    await page.route('**/history/active', async (route) => {
      if (!activeRunStarted) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ runs: [] }),
        })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          runs: [
            {
              run_id: 'tabs-reconnect-run',
              command: activeCmd,
              started: '2026-04-13T00:00:00Z',
            },
          ],
        }),
      })
    })

    await runCommand(page, idleCmd)
    await expect(page.locator('.tab-panel.active .output')).toContainText(idleCmd)

    await page.locator('#new-tab-btn').click()
    await page.locator('#cmd').fill(activeCmd)
    await page.keyboard.press('Enter')
    await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })
    await expect(page.locator('.tab-panel.active .output')).toContainText('long run started')

    await page.locator('#new-tab-btn').click()
    await page.locator('#cmd').fill('ffuf -u https://target/FUZZ')
    await expect(page.locator('#cmd')).toHaveValue('ffuf -u https://target/FUZZ')

    await page.reload()
    await page.locator('#cmd').waitFor()

    await expect(page.locator('.tab')).toHaveCount(3)
    await expect(page.locator('.welcome-banner')).toHaveCount(0)
    await expect(page.locator('.status-pill')).toHaveText('RUNNING')
    await expect(page.locator('.tab-panel.active .output')).toContainText(
      '[reconnected to active run started at',
    )
    await expect(page.locator('.tab-panel.active .output')).toContainText(activeCmd)

    await page.locator('.tab').nth(1).click()
    await expect(page.locator('#cmd')).toHaveValue('ffuf -u https://target/FUZZ')

    await page.locator('.tab').first().click()
    await expect(page.locator('.tab-panel.active .output')).toContainText(idleCmd)
    await expect(page.locator('.tab-panel.active .output')).toContainText('runs in session')
  })

  test('pressing Enter on a blank prompt appends a fresh prompt line', async ({ page }) => {
    // Wait for welcome blocks to finish rendering (_welcomeDone is set just before
    // the hint feed starts). Checking _welcomeDone rather than a visible hint element
    // avoids a race where the welcome animation (5 sampled commands + inter-block
    // delays) can take close to 15 s, making a toBeVisible timeout unreliable.
    await page.waitForFunction(
      () => {
        return typeof _welcomeDone !== 'undefined' && _welcomeDone === true
      },
      { timeout: 30000 },
    )
    const beforeCount = await page.locator('.tab-panel.active .output .line.prompt-echo').count()

    await ensurePromptReady(page)

    await page.locator('#cmd').press('Enter')

    await expect(page.locator('.tab-panel.active .output .line.prompt-echo')).toHaveCount(
      beforeCount + 1,
    )
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
    await expect(page.locator('.tab .tab-label')).toHaveText('shell 1')
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
    await ensurePromptReady(page)
  })

  test('drag reordering the active tab returns focus to the terminal input', async ({ page }) => {
    await page.locator('#new-tab-btn').click()
    await expect(page.locator('.tab')).toHaveCount(2)

    const secondTab = page.locator('.tab').nth(1)
    const firstTab = page.locator('.tab').first()
    await secondTab.click()
    await page.locator('#cmd').fill('')
    const secondBox = await secondTab.boundingBox()
    const firstBox = await firstTab.boundingBox()
    if (!secondBox || !firstBox) throw new Error('Tab bounding boxes were not available')

    await page.mouse.move(secondBox.x + secondBox.width / 2, secondBox.y + secondBox.height / 2)
    await page.mouse.down()
    await page.mouse.move(firstBox.x + 8, firstBox.y + firstBox.height / 2, { steps: 8 })
    await page.mouse.up()

    await expect(page.locator('#cmd')).toBeFocused()

    await page.keyboard.type('dig darklab.sh A')
    await expect(page.locator('#cmd')).toHaveValue('dig darklab.sh A')
  })

  test('touch dragging reorders tabs and clears mobile drag state on release', async ({ page }) => {
    await expect(page.locator('.tab')).toHaveCount(1)
    await page.locator('#new-tab-btn').click()
    await expect(page.locator('.tab')).toHaveCount(2)
    await page.locator('#new-tab-btn').click()
    await expect(page.locator('.tab')).toHaveCount(3)

    const firstTab = page.locator('.tab').nth(0)
    const thirdTab = page.locator('.tab').nth(2)
    const firstBox = await firstTab.boundingBox()
    const thirdBox = await thirdTab.boundingBox()
    if (!firstBox || !thirdBox) throw new Error('Tab bounding boxes were not available')

    await page.evaluate(
      ({ downX, downY }) => {
        const tab = document.querySelectorAll('.tab')[2]
        const start = new Event('touchstart', { bubbles: true, cancelable: true })
        Object.defineProperty(start, 'touches', {
          value: [{ identifier: 41, clientX: downX, clientY: downY }],
          configurable: true,
        })
        Object.defineProperty(start, 'changedTouches', {
          value: [{ identifier: 41, clientX: downX, clientY: downY }],
          configurable: true,
        })
        tab?.dispatchEvent(start)
      },
      {
        downX: thirdBox.x + thirdBox.width / 2,
        downY: thirdBox.y + thirdBox.height / 2,
      },
    )

    await page.waitForTimeout(220)

    await page.evaluate(
      ({ moveX, moveY }) => {
        const move = new Event('touchmove', { bubbles: true, cancelable: true })
        Object.defineProperty(move, 'touches', {
          value: [{ identifier: 41, clientX: moveX, clientY: moveY }],
          configurable: true,
        })
        Object.defineProperty(move, 'changedTouches', {
          value: [{ identifier: 41, clientX: moveX, clientY: moveY }],
          configurable: true,
        })
        document.dispatchEvent(move)
      },
      {
        moveX: firstBox.x + 8,
        moveY: firstBox.y + firstBox.height / 2,
      },
    )

    await page.evaluate(
      ({ upX, upY }) => {
        const end = new Event('touchend', { bubbles: true, cancelable: true })
        Object.defineProperty(end, 'touches', { value: [], configurable: true })
        Object.defineProperty(end, 'changedTouches', {
          value: [{ identifier: 41, clientX: upX, clientY: upY }],
          configurable: true,
        })
        document.dispatchEvent(end)
      },
      {
        upX: firstBox.x + 8,
        upY: firstBox.y + firstBox.height / 2,
      },
    )

    await expect(page.locator('#tabs-bar')).not.toHaveClass(/tabs-bar-touch-sorting/)
    await expect(page.locator('.tab').first()).toContainText('shell 3')
    await expect(page.locator('.tab-drop-before, .tab-drop-after')).toHaveCount(0)
    await expect(page.locator('#cmd')).toBeFocused()
  })
})
