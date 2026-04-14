import { test, expect } from '@playwright/test'
import {
  createShareSnapshot,
  ensurePromptReady,
  makeTestIp,
  setComposerValueForTest,
  waitForHistoryRuns,
} from './helpers.js'

const MOBILE = { width: 375, height: 812 }
const LONG_CMD = 'ping -c 4 8.8.8.8'

// Use a full mobile-like emulation so the mobile shell code sees the same
// viewport and touch signals as real mobile browsers.
test.use({ hasTouch: true, isMobile: true })

// Browser specs share the same backend rate limiter, so derive a stable test-
// scoped IP from the file/title instead of reusing one bucket for the suite.
function testScopedIp(testInfo, baseOffset = 0) {
  const key = `${testInfo.file}:${testInfo.title}`
  let sum = 0
  for (const ch of key) sum = (sum + ch.charCodeAt(0)) % 200
  return makeTestIp(baseOffset + sum)
}

async function runCommandMobile(page, cmd) {
  await openMobileKeyboard(page)
  await page.locator('#mobile-cmd').pressSequentially(cmd)
  await expect(page.locator('#mobile-run-btn')).toBeEnabled()
  await page.locator('#mobile-run-btn').click()
  await page.locator('.status-pill').filter({ hasNotText: 'RUNNING' }).waitFor({ timeout: 15_000 })
}

async function openMobileKeyboard(page) {
  await page.locator('#mobile-cmd').focus()
  await page.evaluate(() => {
    const vv = window.visualViewport
    if (!vv) return
    try {
      Object.defineProperty(vv, 'height', {
        configurable: true,
        value: 500,
      })
    } catch (_) {}
    window.dispatchEvent(new Event('resize'))
  })
}

test.describe('mobile menu', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': testScopedIp(testInfo, 101) })
    await page.setViewportSize(MOBILE)
    await page.goto('/')
    await page.evaluate(() => window.dispatchEvent(new Event('resize')))
    await expect.poll(async () => page.evaluate(() => document.body.classList.contains('mobile-terminal-mode'))).toBe(true)
    await page.locator('#mobile-cmd').waitFor({ state: 'attached' })
  })

  test('mobile startup uses the mobile welcome and keeps the composer visible', async ({ page }) => {
    await expect(page.locator('.welcome-banner')).toBeVisible()
    await expect(page.locator('.welcome-ascii-art')).toBeVisible()
    await expect(page.locator('.welcome-status-loaded')).toHaveCount(5, { timeout: 15_000 })
    await expect(page.locator('.welcome-command')).toHaveCount(0)
    await expect(page.locator('.welcome-section-header')).toContainText('Helpful hints')
    await expect(page.locator('.line.welcome-hint')).toBeVisible({ timeout: 15_000 })
    // Desktop run button stays hidden; the mobile helper row stays hidden until the keyboard opens
    await expect(page.locator('#run-btn')).toBeHidden()
    await expect(page.locator('#mobile-edit-bar')).toBeHidden()
    await expect(page.locator('#mobile-composer')).toBeVisible()
    await expect(page.locator('#mobile-shell-transcript')).toBeVisible()
    await expect(page.locator('#mobile-shell-transcript .tab-panels, #mobile-shell-transcript #tab-panels')).toHaveCount(1)
    await expect(page.locator('header .status-pill')).toBeVisible()
    // Composer must stay within the viewport
    const composerBox = await page.locator('#mobile-composer').boundingBox()
    expect(composerBox).not.toBeNull()
    expect(composerBox.y + composerBox.height).toBeLessThanOrEqual(MOBILE.height)
  })

  test('mobile edit bar appears when the mobile command input is focused', async ({ page }) => {
    await openMobileKeyboard(page)
    await expect(page.locator('#mobile-edit-bar')).toBeVisible()
  })

  test('tapping the mobile command input opens the keyboard without jumping the page', async ({ page }) => {
    const startScrollY = await page.evaluate(() => window.scrollY)
    await page.locator('#mobile-cmd').tap()
    await page.evaluate(() => {
      const vv = window.visualViewport
      if (!vv) return
      try {
        Object.defineProperty(vv, 'height', {
          configurable: true,
          value: 500,
        })
      } catch (_) {}
      window.dispatchEvent(new Event('resize'))
    })

    await expect(page.locator('#mobile-cmd')).toBeFocused()
    await expect(page.locator('#mobile-edit-bar')).toBeVisible()
    await expect.poll(async () => page.evaluate(() => window.scrollY)).toBeLessThanOrEqual(startScrollY + 12)
  })

  test('reloading on mobile restores the active output pane at the bottom', async ({ page }) => {
    await runCommandMobile(page, 'help')

    const output = page.locator('.tab-panel.active .output')
    await expect.poll(async () => output.evaluate(el => el.scrollHeight > el.clientHeight + 40)).toBe(true)

    await page.evaluate(async () => {
      const activeId = window.activeTabId
      const activeTab = Array.isArray(window.tabs)
        ? window.tabs.find(tab => tab && tab.id === activeId)
        : null
      if (activeTab) {
        activeTab.followOutput = false
        activeTab.suppressOutputScrollTracking = false
      }
      await new Promise(resolve => setTimeout(resolve, 32))
      const out = document.querySelector('.tab-panel.active .output')
      if (!out) return
      out.scrollTop = 0
      out.dispatchEvent(new Event('scroll'))
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    })
    await expect.poll(async () => output.evaluate(el => {
      const remaining = el.scrollHeight - (el.scrollTop + el.clientHeight)
      return Math.max(0, Math.round(remaining))
    })).toBeGreaterThan(100)

    await page.reload()
    await page.evaluate(() => window.dispatchEvent(new Event('resize')))
    await expect.poll(async () => page.evaluate(() => document.body.classList.contains('mobile-terminal-mode'))).toBe(true)

    await expect.poll(async () => output.evaluate(el => {
      const remaining = el.scrollHeight - (el.scrollTop + el.clientHeight)
      return Math.max(0, Math.round(remaining))
    })).toBeLessThanOrEqual(16)
  })

  test('mobile autocomplete accepts a suggestion by tap and keeps the mobile composer focused', async ({ page }) => {
    await ensurePromptReady(page)
    await openMobileKeyboard(page)
    const input = page.locator('#mobile-cmd')
    await setComposerValueForTest(page, 'nmap -', { mobile: true })

    const dropdown = page.locator('#ac-dropdown')
    await expect.poll(async () => ({
      hidden: await dropdown.evaluate(node => node.classList.contains('u-hidden')),
      text: (await dropdown.textContent()) || '',
    })).toEqual(expect.objectContaining({
      hidden: false,
      text: expect.stringContaining('-sT'),
    }))

    await dropdown.locator('.ac-item', { hasText: '-sT' }).tap()

    await expect(input).toHaveValue('nmap -sT')
    await expect(input).toBeFocused()
    await expect(dropdown).toBeHidden()
  })

  test('mobile contextual autocomplete shows value hints after accepting a value-taking flag', async ({ page }) => {
    await ensurePromptReady(page)
    await openMobileKeyboard(page)
    const input = page.locator('#mobile-cmd')
    await setComposerValueForTest(page, 'curl -', { mobile: true })

    const dropdown = page.locator('#ac-dropdown')
    await expect.poll(async () => ({
      hidden: await dropdown.evaluate(node => node.classList.contains('u-hidden')),
      text: (await dropdown.textContent()) || '',
    })).toEqual(expect.objectContaining({
      hidden: false,
      text: expect.stringContaining('-o'),
    }))
    await dropdown.locator('.ac-item', { hasText: '-o' }).tap()

    await expect(input).toHaveValue('curl -o')
    await input.press('Space')

    await expect.poll(async () => ({
      hidden: await dropdown.evaluate(node => node.classList.contains('u-hidden')),
      text: (await dropdown.textContent()) || '',
    })).toEqual(expect.objectContaining({
      hidden: false,
      text: expect.stringContaining('/dev/null'),
    }))
  })

  test('clicking the mobile transcript closes the keyboard and helper row', async ({ page }) => {
    await openMobileKeyboard(page)
    await expect(page.locator('#mobile-edit-bar')).toBeVisible()

    await page.locator('#mobile-shell-transcript').tap()
    await expect(page.locator('#mobile-edit-bar')).toBeHidden()
  })

  test('mobile tab action buttons still work while the keyboard is open', async ({ page }) => {
    await openMobileKeyboard(page)
    await expect(page.locator('#mobile-edit-bar')).toBeVisible()

    const startScrollY = await page.evaluate(() => window.scrollY)
    await runCommandMobile(page, 'hostname')
    await createShareSnapshot(page)
    await expect(page.locator('.tab-panel.active [data-action="permalink"]')).not.toBeFocused()
    await page.locator('.tab-panel.active [data-action="copy"]').click()
    await expect(page.locator('.tab-panel.active [data-action="copy"]')).not.toBeFocused()
    await page.locator('.tab-panel.active [data-action="clear"]').click()

    await expect(page.locator('.tab-panel.active .output .line')).toHaveCount(0)
    await expect(page.locator('#mobile-edit-bar')).toBeHidden()
    await expect(page.locator('.tab-panel.active [data-action="clear"]')).not.toBeFocused()
    await expect.poll(async () => page.evaluate(() => window.scrollY)).toBeLessThanOrEqual(startScrollY + 12)
  })

  test('creating a new mobile tab does not force composer focus', async ({ page }) => {
    const startScrollY = await page.evaluate(() => window.scrollY)
    await page.locator('#new-tab-btn').click()

    await expect(page.locator('#mobile-cmd')).not.toBeFocused()
    await expect(page.locator('#mobile-edit-bar')).toBeHidden()
    await expect.poll(async () => page.evaluate(() => window.scrollY)).toBeLessThanOrEqual(startScrollY + 12)
  })

  test('closing a mobile tab after output returns to the active tab without jumping the page', async ({ page }) => {
    await runCommandMobile(page, 'hostname')
    await page.locator('#new-tab-btn').click()
    await runCommandMobile(page, 'date')
    await page.locator('.tab').nth(1).locator('.tab-close').click()

    await expect(page.locator('#mobile-cmd')).not.toBeFocused()
    await expect(page.locator('#mobile-edit-bar')).toBeHidden()
    await expect.poll(async () => page.evaluate(() => window.scrollY)).toBeLessThanOrEqual(12)
  })

  test('closing a mobile tab does not leave the close button focused', async ({ page }) => {
    await page.locator('#new-tab-btn').click()
    await runCommandMobile(page, 'hostname')

    const closeBtn = page.locator('.tab').nth(1).locator('.tab-close')
    await closeBtn.click()

    await expect(page.locator('.tab')).toHaveCount(1)
    await expect.poll(async () => page.evaluate(() => document.activeElement?.classList?.contains('tab-close') || false)).toBe(false)
  })

  test('closing the only mobile tab does not leave the reset close button focused', async ({ page }) => {
    await runCommandMobile(page, 'hostname')

    const closeBtn = page.locator('.tab').first().locator('.tab-close')
    await closeBtn.click()

    await expect(page.locator('.tab')).toHaveCount(1)
    await expect.poll(async () => page.evaluate(() => document.activeElement?.classList?.contains('tab-close') || false)).toBe(false)
  })

  test('mobile tabs bar can overflow and scroll horizontally', async ({ page }) => {
    const overflowCmds = ['hostname', 'date', 'uptime', 'whoami', 'version', 'fortune']
    for (let i = 0; i < 6; i++) {
      await page.locator('#new-tab-btn').click()
      await runCommandMobile(page, overflowCmds[i])
    }

    const tabsBar = page.locator('.terminal-bar .tabs-bar')
    const metrics = await tabsBar.evaluate(el => ({ scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }))
    expect(metrics.scrollWidth).toBeGreaterThan(metrics.clientWidth)
    await tabsBar.evaluate(el => { el.scrollLeft = el.scrollWidth; })
    await expect.poll(async () => tabsBar.evaluate(el => el.scrollLeft)).toBeGreaterThan(0)
  })

  test('hamburger button is visible and desktop header buttons are hidden at mobile width', async ({ page }) => {
    await expect(page.locator('#hamburger-btn')).toBeVisible()
    await expect(page.locator('#header-btns')).toBeHidden()
  })

  test('clicking the hamburger opens the mobile menu', async ({ page }) => {
    await page.locator('#hamburger-btn').click()
    await expect(page.locator('#mobile-menu')).toHaveClass(/open/)
  })

  test('mobile menu FAQ and options open overlays in the mobile shell', async ({ page }) => {
    await page.locator('#hamburger-btn').click()
    await page.locator('#mobile-menu [data-action="faq"]').click()
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)

    await page.locator('#faq-overlay .faq-close').click()
    await expect(page.locator('#faq-overlay')).not.toHaveClass(/open/)

    await page.locator('#hamburger-btn').click()
    await page.locator('#mobile-menu [data-action="options"]').click()
    await expect(page.locator('#options-overlay')).toHaveClass(/open/)

    await page.locator('#options-overlay .options-close').click()
    await expect(page.locator('#options-overlay')).not.toHaveClass(/open/)
  })

  test('mobile menu contains history and theme action buttons', async ({ page }) => {
    await page.locator('#hamburger-btn').click()
    const menu = page.locator('#mobile-menu')
    await expect(menu.locator('[data-action="history"]')).toBeVisible()
    await expect(menu.locator('[data-action="theme"]')).toBeVisible()
  })

  test('mobile theme selector opens full screen with evenly sized grouped sections', async ({ page }) => {
    await page.locator('#hamburger-btn').click()
    await page.locator('#mobile-menu [data-action="theme"]').click()

    await expect(page.locator('#theme-overlay')).toHaveClass(/open/)
    await expect(page.locator('#theme-modal')).toBeVisible()

    const viewport = page.viewportSize()
    const modalBox = await page.locator('#theme-modal').boundingBox()
    expect(modalBox).not.toBeNull()
    expect(modalBox.width).toBeGreaterThanOrEqual(viewport.width * 0.95)
    expect(modalBox.height).toBeGreaterThanOrEqual(viewport.height * 0.95)

    const mobileColumns = await page.locator('#theme-select').evaluate(el => el.style.getPropertyValue('--theme-picker-columns-mobile'))
    expect(mobileColumns).toBe('2')

    const gridWidths = await page.locator('#theme-select .theme-picker-group-grid').evaluateAll(nodes => nodes.map(node => Math.round(node.getBoundingClientRect().width)))
    expect(new Set(gridWidths).size).toBe(1)

    await page.locator('#theme-overlay .theme-close').click()
    await expect(page.locator('#theme-overlay')).not.toHaveClass(/open/)
  })

  test('selecting a theme on mobile applies the shell palette, not just the modal preview', async ({ page }) => {
    await page.locator('#hamburger-btn').click()
    await page.locator('#mobile-menu [data-action="theme"]').click()

    await page.locator('#theme-select [data-theme-name="blue_paper"]').click()
    await expect(page.locator('body')).toHaveAttribute('data-theme', 'blue_paper')

    const shellColors = await page.evaluate(() => {
      const root = getComputedStyle(document.documentElement)
      return {
        bg: root.getPropertyValue('--bg').trim(),
        surface: root.getPropertyValue('--surface').trim(),
        terminalBar: root.getPropertyValue('--theme-terminal-bar-bg').trim(),
        panel: root.getPropertyValue('--theme-panel-bg').trim(),
      }
    })

    expect(shellColors.bg).toBe('#eef4fa')
    expect(shellColors.surface).toBe('#fbfdff')
    expect(shellColors.terminalBar).toBe('#d9e5f1')
    expect(shellColors.panel).toBe('#edf4fb')
  })

  test('clicking outside the menu closes it', async ({ page }) => {
    await page.locator('#hamburger-btn').click()
    await expect(page.locator('#mobile-menu')).toHaveClass(/open/)

    // Click somewhere neutral in the header area
    await page.locator('header').click()
    await expect(page.locator('#mobile-menu')).not.toHaveClass(/open/)
  })

  test('mobile recent chips collapse to one row and overflow opens history', async ({ page }) => {
    const commands = [
      'banner chip-overflow-test-1',
      'banner chip-overflow-test-2',
      'banner chip-overflow-test-3',
      'banner chip-overflow-test-4',
    ]

    for (const [index, command] of commands.entries()) {
      await runCommandMobile(page, command)
      if (index < commands.length - 1) await page.waitForTimeout(250)
    }

    const chips = page.locator('#history-row .hist-chip')
    await expect(chips).toHaveCount(4)
    await expect(page.locator('#history-row .hist-chip-overflow')).toContainText('+ more')
    await expect(chips.nth(0)).toContainText('test-4')
    await expect(chips.nth(1)).toContainText('test-3')
    await expect(chips.nth(2)).toContainText('test-2')

    await page.locator('#history-row .hist-chip-overflow').click()
    await expect(page.locator('#history-panel')).toHaveClass(/open/)
  })

  test('mobile recent chips can load a visible command back into the prompt', async ({ page }) => {
    const commands = [
      'hostname',
      'date',
      'uptime',
    ]

    for (const [index, command] of commands.entries()) {
      await runCommandMobile(page, command)
      if (index < commands.length - 1) await page.waitForTimeout(250)
    }

    const chip = page.locator('#history-row .hist-chip').first()
    const commandText = await chip.getAttribute('title')
    await chip.click()

    await expect(page.locator('#mobile-cmd')).toHaveValue(commandText || '')
    await expect(page.locator('#mobile-composer')).toBeVisible()
  })

  test('mobile history restore works from a newly created session via the mobile menu', async ({ page }) => {
    const commands = [
      'hostname',
      'date',
    ]

    for (const command of commands) {
      await runCommandMobile(page, command)
    }
    await waitForHistoryRuns(page, commands.length)

    await page.locator('#new-tab-btn').click()
    await expect(page.locator('#cmd')).toHaveValue('')

    await page.locator('#hamburger-btn').click()
    await page.locator('#mobile-menu [data-action="history"]').click()
    await expect(page.locator('#history-panel')).toHaveClass(/open/)

    await page.locator('.history-entry').first().click()
    await expect(page.locator('.tab-panel.active .output')).toContainText('date')
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('mobile history copy and permalink actions keep the drawer open', async ({ page }) => {
    await runCommandMobile(page, 'hostname')
    await waitForHistoryRuns(page, 1)

    await page.locator('#hamburger-btn').click()
    await page.locator('#mobile-menu [data-action="history"]').click()
    await expect(page.locator('#history-panel')).toHaveClass(/open/)

    const firstEntry = page.locator('.history-entry').first()
    await firstEntry.locator('[data-action="copy"]').click()
    await expect(page.locator('#history-panel')).toHaveClass(/open/)
    await expect(page.locator('#permalink-toast')).toContainText('Command copied to clipboard')

    await firstEntry.locator('[data-action="permalink"]').click()
    await expect(page.locator('#history-panel')).toHaveClass(/open/)
    await expect(page.locator('#permalink-toast')).toContainText('Link copied to clipboard')
  })

  test('mobile run button disables while a command is running', async ({ page }) => {
    await page.locator('#mobile-cmd').fill(LONG_CMD)
    await page.locator('#mobile-run-btn').click()

    await expect(page.locator('#mobile-run-btn')).toBeDisabled()
    await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })

    await expect(page.locator('.status-pill').filter({ hasNotText: 'RUNNING' })).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('#mobile-run-btn')).toBeDisabled()

    await page.locator('#mobile-cmd').fill('hostname')
    await expect(page.locator('#mobile-run-btn')).toBeEnabled()
  })

  test('mobile permalink copies via the fallback path when clipboard writeText is unavailable', async ({ page }) => {
    await runCommandMobile(page, 'hostname')

    await page.evaluate(() => {
      Object.defineProperty(navigator, 'clipboard', {
        value: {
          writeText: () => Promise.reject(new Error('clipboard denied')),
        },
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

    await createShareSnapshot(page)
    await expect(page.locator('#permalink-toast')).toHaveClass(/show/, { timeout: 5_000 })
    await expect(page.locator('#permalink-toast')).toContainText('Link copied to clipboard')
    await expect(page.evaluate(() => window.__copyFallbackUsed)).resolves.toBe(true)
  })

  test('mobile edit bar moves the caret and deletes a word', async ({ page }) => {
    // Show the edit bar (normally shown only when the keyboard is open)
    await page.evaluate(() => document.body.classList.add('mobile-keyboard-open'))

    await expect(page.locator('#mobile-edit-bar')).toBeVisible()

    await page.locator('#mobile-cmd').evaluate(el => {
      el.value = 'ping -c 4 example.com'
      el.focus()
      el.setSelectionRange(el.value.length, el.value.length)
      el.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await page.evaluate(() => {
      const val = 'ping -c 4 example.com'
      setComposerState({ value: val, selectionStart: val.length, selectionEnd: val.length, activeInput: 'mobile' })
    })

    await page.evaluate(() => {
      document.querySelector('[data-mobile-edit="left"]')
        .dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))
    })
    await expect.poll(async () => page.locator('#mobile-cmd').evaluate(el => el.selectionStart)).toBe(20)

    await page.evaluate(() => {
      document.querySelector('[data-mobile-edit="home"]')
        .dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))
    })
    await expect.poll(async () => page.locator('#mobile-cmd').evaluate(el => el.selectionStart)).toBe(0)

    await page.evaluate(() => {
      document.querySelector('[data-mobile-edit="word-right"]')
        .dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))
    })
    await expect.poll(async () => page.locator('#mobile-cmd').evaluate(el => el.selectionStart)).toBe(4)

    await page.evaluate(() => {
      document.querySelector('[data-mobile-edit="right"]')
        .dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))
    })
    await expect.poll(async () => page.locator('#mobile-cmd').evaluate(el => el.selectionStart)).toBe(5)

    await page.evaluate(() => {
      document.querySelector('[data-mobile-edit="word-left"]')
        .dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))
    })
    await expect.poll(async () => page.locator('#mobile-cmd').evaluate(el => el.selectionStart)).toBe(0)

    await page.evaluate(() => {
      document.querySelector('[data-mobile-edit="end"]')
        .dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))
    })
    await expect.poll(async () => page.locator('#mobile-cmd').evaluate(el => el.selectionStart)).toBe(21)

    await page.evaluate(() => {
      document.querySelector('[data-mobile-edit="delete-word"]')
        .dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))
    })
    await expect(page.locator('#mobile-cmd')).toHaveValue('ping -c 4 ')

    await page.evaluate(() => {
      document.querySelector('[data-mobile-edit="delete-line"]')
        .dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))
    })
    await expect(page.locator('#mobile-cmd')).toHaveValue('')
    await expect.poll(async () => page.locator('#mobile-cmd').evaluate(el => el.selectionStart)).toBe(0)
  })

  test('mobile long commands keep the composer usable', async ({ page }) => {
    // Simulate keyboard open by setting the CSS variable and class directly
    await page.evaluate(() => {
      document.documentElement.style.setProperty('--mobile-keyboard-offset', '280px')
      document.body.classList.add('mobile-keyboard-open')
    })

    const longCommand = `curl https://example.com/health?${'x'.repeat(120)}`
    await page.locator('#mobile-cmd').fill(longCommand)

    await expect(page.locator('#mobile-cmd')).toHaveValue(longCommand)
    await expect(page.locator('#mobile-composer')).toBeVisible()

    const composerBox = await page.locator('#mobile-composer').boundingBox()
    expect(composerBox).not.toBeNull()
    expect(composerBox.y + composerBox.height).toBeLessThanOrEqual(MOBILE.height)
  })
})
