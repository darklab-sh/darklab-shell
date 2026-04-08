import { test, expect } from '@playwright/test'

const MOBILE = { width: 375, height: 812 }
const LONG_CMD = 'ping -c 4 8.8.8.8'

// Use a full mobile-like emulation so the mobile shell code sees the same
// viewport and touch signals as real mobile browsers.
test.use({ hasTouch: true, isMobile: true })

async function runCommandMobile(page, cmd) {
  await page.locator('#mobile-cmd').fill(cmd)
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
  test.beforeEach(async ({ page }) => {
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

  test('mobile autocomplete accepts a suggestion by tap and keeps the mobile composer focused', async ({ page }) => {
    await page.locator('#mobile-cmd').fill('nmap')

    const dropdown = page.locator('#ac-dropdown')
    await expect(dropdown).toBeVisible()
    await expect(dropdown).toContainText('nmap -h')

    await dropdown.locator('.ac-item', { hasText: 'nmap -h' }).tap()

    await expect(page.locator('#mobile-cmd')).toHaveValue('nmap -h')
    await expect(page.locator('#mobile-cmd')).toBeFocused()
    await expect(dropdown).toBeHidden()
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
    await runCommandMobile(page, 'curl http://localhost:5001/health?mobile=actions')
    await page.locator('.tab-panel.active [data-action="permalink"]').click()
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
    await runCommandMobile(page, 'curl http://localhost:5001/health?mobile=close-scroll')
    await page.locator('#new-tab-btn').click()
    await page.locator('#mobile-cmd').fill('curl http://localhost:5001/health?mobile=close-scroll-2')
    await page.locator('#mobile-run-btn').click()
    await page.locator('.tab').nth(1).locator('.tab-close').click()

    await expect(page.locator('#mobile-cmd')).not.toBeFocused()
    await expect(page.locator('#mobile-edit-bar')).toBeHidden()
    await expect.poll(async () => page.evaluate(() => window.scrollY)).toBeLessThanOrEqual(12)
  })

  test('closing a mobile tab does not leave the close button focused', async ({ page }) => {
    await page.locator('#new-tab-btn').click()
    await runCommandMobile(page, 'curl http://localhost:5001/health?mobile=tab-close-focus')

    const closeBtn = page.locator('.tab').nth(1).locator('.tab-close')
    await closeBtn.click()

    await expect(page.locator('.tab')).toHaveCount(1)
    await expect.poll(async () => page.evaluate(() => document.activeElement?.classList?.contains('tab-close') || false)).toBe(false)
  })

  test('closing the only mobile tab does not leave the reset close button focused', async ({ page }) => {
    await runCommandMobile(page, 'curl http://localhost:5001/health?mobile=single-close-focus')

    const closeBtn = page.locator('.tab').first().locator('.tab-close')
    await closeBtn.click()

    await expect(page.locator('.tab')).toHaveCount(1)
    await expect.poll(async () => page.evaluate(() => document.activeElement?.classList?.contains('tab-close') || false)).toBe(false)
  })

  test('mobile tabs bar can overflow and scroll horizontally', async ({ page }) => {
    for (let i = 0; i < 6; i++) {
      await page.locator('#new-tab-btn').click()
      await runCommandMobile(page, `curl http://localhost:5001/health?mobile=overflow-${i}-${'x'.repeat(22)}`)
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

  test('clicking outside the menu closes it', async ({ page }) => {
    await page.locator('#hamburger-btn').click()
    await expect(page.locator('#mobile-menu')).toHaveClass(/open/)

    // Click somewhere neutral in the header area
    await page.locator('header').click()
    await expect(page.locator('#mobile-menu')).not.toHaveClass(/open/)
  })

  test('mobile recent chips collapse to one row and overflow opens history', async ({ page }) => {
    const commands = [
      'curl http://localhost:5001/health?mobile=1',
      'curl http://localhost:5001/health?mobile=2',
      'curl http://localhost:5001/health?mobile=3',
      'curl http://localhost:5001/health?mobile=4',
    ]

    for (const [index, command] of commands.entries()) {
      await runCommandMobile(page, command)
      if (index < commands.length - 1) await page.waitForTimeout(250)
    }

    const chips = page.locator('#history-row .hist-chip')
    await expect(chips).toHaveCount(4)
    await expect(page.locator('#history-row .hist-chip-overflow')).toContainText('+1 more')
    await expect(chips.nth(0)).toContainText('mobile=4')
    await expect(chips.nth(1)).toContainText('mobile=3')
    await expect(chips.nth(2)).toContainText('mobile=2')

    await page.locator('#history-row .hist-chip-overflow').click()
    await expect(page.locator('#history-panel')).toHaveClass(/open/)
  })

  test('mobile recent chips can load a visible command back into the prompt', async ({ page }) => {
    const commands = [
      'curl http://localhost:5001/health?mobile=1',
      'curl http://localhost:5001/health?mobile=2',
      'curl http://localhost:5001/health?mobile=3',
    ]

    for (const [index, command] of commands.entries()) {
      await runCommandMobile(page, command)
      if (index < commands.length - 1) await page.waitForTimeout(250)
    }

    const chip = page.locator('#history-row .hist-chip').first()
    const commandText = await chip.getAttribute('title')
    await chip.click()

    await expect(page.locator('#cmd')).toHaveValue(commandText || '')
    await expect(page.locator('#mobile-composer')).toBeVisible()
  })

  test('mobile history restore works from a newly created session via the mobile menu', async ({ page }) => {
    const commands = [
      'curl http://localhost:5001/health?mobile=history-1',
      'curl http://localhost:5001/health?mobile=history-2',
    ]

    for (const command of commands) {
      await runCommandMobile(page, command)
    }

    await page.locator('#new-tab-btn').click()
    await expect(page.locator('#cmd')).toHaveValue('')

    await page.locator('#hamburger-btn').click()
    await page.locator('#mobile-menu [data-action="history"]').click()
    await expect(page.locator('#history-panel')).toHaveClass(/open/)

    await page.locator('.history-entry').first().click()
    await expect(page.locator('.tab-panel.active .output')).toContainText('mobile=history-2')
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('mobile run button disables while a command is running', async ({ page }) => {
    await page.locator('#mobile-cmd').fill(LONG_CMD)
    await page.locator('#mobile-run-btn').click()

    await expect(page.locator('#mobile-run-btn')).toBeDisabled()
    await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })

    await expect(page.locator('.status-pill').filter({ hasNotText: 'RUNNING' })).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('#mobile-run-btn')).toBeEnabled()
  })

  test('mobile permalink copies via the fallback path when clipboard writeText is unavailable', async ({ page }) => {
    await runCommandMobile(page, 'curl http://localhost:5001/health?mobile=share')

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

    await page.locator('.tab-panel.active [data-action="permalink"]').click()
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
      document.querySelector('[data-mobile-edit="right"]')
        .dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))
    })
    await expect.poll(async () => page.locator('#mobile-cmd').evaluate(el => el.selectionStart)).toBe(1)

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
  })

  test('mobile long commands keep the composer usable', async ({ page }) => {
    // Simulate keyboard open by setting the CSS variable and class directly
    await page.evaluate(() => {
      document.documentElement.style.setProperty('--mobile-keyboard-offset', '280px')
      document.body.classList.add('mobile-keyboard-open')
    })

    const longCommand = `curl http://localhost:5001/health?${'x'.repeat(120)}`
    await page.locator('#mobile-cmd').fill(longCommand)

    await expect(page.locator('#mobile-cmd')).toHaveValue(longCommand)
    await expect(page.locator('#mobile-composer')).toBeVisible()

    const composerBox = await page.locator('#mobile-composer').boundingBox()
    expect(composerBox).not.toBeNull()
    expect(composerBox.y + composerBox.height).toBeLessThanOrEqual(MOBILE.height)
  })
})
