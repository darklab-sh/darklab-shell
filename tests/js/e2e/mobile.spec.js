import { test, expect } from '@playwright/test'
import {
  createShareSnapshot,
  ensurePromptReady,
  setComposerValueForTest,
  waitForActiveOutputSettled,
  waitForHistoryRuns,
  browserSessionId,
  seedExternalHistoryRuns,
} from './helpers.js'

const MOBILE = { width: 375, height: 812 }
const LONG_CMD = 'ping -c 4 8.8.8.8'

// Use a full mobile-like emulation so the mobile shell code sees the same
// viewport and touch signals as real mobile browsers.
test.use({ hasTouch: true, isMobile: true })

async function runCommandMobile(page, cmd) {
  await page.waitForFunction(
    () => {
      const activeTab = typeof getActiveTab === 'function' ? getActiveTab() : null
      const input = document.getElementById('mobile-cmd')
      if (!activeTab || !(input instanceof HTMLInputElement)) return false
      const style = window.getComputedStyle(input)
      return style.display !== 'none' && style.visibility !== 'hidden'
    },
    { timeout: 15_000 },
  )
  await page.locator('#mobile-cmd').focus()
  await simulateMobileKeyboard(page)
  await setComposerValueForTest(page, cmd, { mobile: true, waitForAutocomplete: false })
  const runBtn = page.locator('#mobile-run-btn')
  await expect(runBtn).toBeEnabled({ timeout: 5_000 })
  await runBtn.click()
  await page.locator('.status-pill').filter({ hasNotText: 'RUNNING' }).waitFor({ timeout: 15_000 })
}

async function simulateMobileKeyboard(page) {
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

async function openMobileKeyboard(page) {
  await page.locator('#mobile-cmd').focus()
  await simulateMobileKeyboard(page)
}

async function openMobileProjects(page) {
  await page.locator('#hamburger-btn').click()
  await page.locator('#mobile-menu-sheet [data-menu-action="projects"]').click()
  await expect(page.locator('#project-workspace-overlay')).toHaveClass(/\bopen\b/)
  await expect(page.locator('#project-mobile-root')).toBeVisible()
  await expect(page.locator('#project-mobile-body')).not.toContainText('Loading projects...')
}

async function createMobileProject(page, name) {
  await page.locator('#project-mobile-new-btn').click()
  await expect(page.locator('#project-mobile-create-form')).toBeVisible()
  await page.locator('#project-mobile-name').fill(name)
  await page.locator('#project-mobile-create-form button[type="submit"]').click()
  const row = page.locator('.project-mobile-row').filter({ hasText: name }).first()
  await expect(row).toBeVisible({ timeout: 15_000 })
  return row
}

async function openFullMobileHistoryPanel(page) {
  await page.locator('#hamburger-btn').click()
  await page.locator('#mobile-menu-sheet [data-menu-action="history"]').click()
  const panel = page.locator('#history-panel')
  await expect(panel).toHaveClass(/\bopen\b/)
  await page.evaluate(async () => {
    if (typeof refreshHistoryPanel === 'function') await refreshHistoryPanel()
  })
  await page.locator('#history-list .history-entry').first().waitFor({ state: 'visible' })
}

// The e2e server (run_e2e_server.sh) writes a test config.local.yaml that adds
// 127.0.0.0/8 to diagnostics_allowed_cidrs, so Playwright's loopback connection
// reaches /diag without any extra header manipulation.
test.describe('diagnostics page on mobile', () => {
  test('back button is visible at mobile viewport width', async ({ page }) => {
    await page.setViewportSize(MOBILE)
    await page.goto('/diag')
    await expect(page.locator('.diag-back-btn')).toBeVisible()
  })

  test('back button navigates back to the shell', async ({ page }) => {
    await page.setViewportSize(MOBILE)
    await page.goto('/diag')
    await page.locator('.diag-back-btn').click()
    await expect(page.locator('header h1')).toBeVisible()
    await expect(page.locator('#hamburger-btn')).toBeVisible()
  })

  test('storage breakdown renders table sizing diagnostics', async ({ page }) => {
    await page.setViewportSize(MOBILE)
    await page.goto('/diag')
    const storage = page.locator('.diag-section.s-storage')
    await expect(storage).toContainText('Storage breakdown')
    await expect(storage.locator('.diag-storage-table tbody tr').first()).toBeVisible()
  })

  // Verify parity at the shell's mobile-mode threshold (900px + touch).
  // A touch device at 850px gets the mobile shell, so the diag back button
  // must also appear. The breakpoint was previously 760px which missed this.
  test('back button is visible at 850px touch viewport (shell threshold)', async ({ page }) => {
    await page.setViewportSize({ width: 850, height: 900 })
    await page.goto('/diag')
    await expect(page.locator('.diag-back-btn')).toBeVisible()
  })
})

test.describe('diagnostics page on desktop at threshold width', () => {
  // Override the file-level hasTouch/isMobile so the CSS sees pointer:fine.
  // A non-touch browser at 850px stays in the desktop shell, so the diag
  // page must not show the mobile back button.
  test.use({ hasTouch: false, isMobile: false })

  test('back button is hidden at 850px non-touch viewport', async ({ page }) => {
    await page.setViewportSize({ width: 850, height: 900 })
    await page.goto('/diag')
    await expect(page.locator('.diag-back-btn')).toBeHidden()
  })
})

test.describe('mobile menu', () => {
test.beforeEach(async ({ page }) => {
  await page.setViewportSize(MOBILE)
    await page.goto('/')
    await page.evaluate(() => window.dispatchEvent(new Event('resize')))
    await expect
      .poll(async () =>
        page.evaluate(() => document.body.classList.contains('mobile-terminal-mode')),
      )
      .toBe(true)
    await page.locator('#mobile-cmd').waitFor({ state: 'attached' })
  })

  test('mobile startup uses the mobile welcome and keeps the composer visible', async ({
    page,
  }) => {
    await expect(page.locator('.welcome-banner')).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('.welcome-ascii-art')).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('.welcome-status-loaded')).toHaveCount(5, { timeout: 15_000 })
    await expect(page.locator('.welcome-command')).toHaveCount(0)
    await expect(page.locator('.welcome-section-header')).toContainText('Helpful hints', {
      timeout: 15_000,
    })
    await expect(page.locator('.line.welcome-hint')).toBeVisible({ timeout: 15_000 })
    // Desktop run button stays hidden; the mobile helper row stays hidden until the keyboard opens
    await expect(page.locator('#run-btn')).toBeHidden()
    await expect(page.locator('#mobile-kb-helper')).toBeHidden()
    await expect(page.locator('#mobile-composer')).toBeVisible()
    await expect(page.locator('#mobile-shell-transcript')).toBeVisible()
    await expect(
      page.locator('#mobile-shell-transcript .tab-panels, #mobile-shell-transcript #tab-panels'),
    ).toHaveCount(1)
    await expect(page.locator('header .status-pill')).toBeVisible()
    // Composer must stay within the viewport
    const composerBox = await page.locator('#mobile-composer').boundingBox()
    expect(composerBox).not.toBeNull()
    expect(composerBox.y + composerBox.height).toBeLessThanOrEqual(MOBILE.height)
  })

  test('mobile keyboard helper appears when the mobile command input is focused', async ({ page }) => {
    await openMobileKeyboard(page)
    await expect(page.locator('#mobile-kb-helper')).toBeVisible()
  })

  test('tapping the mobile command input opens the keyboard without jumping the page', async ({
    page,
  }) => {
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
    await expect(page.locator('#mobile-kb-helper')).toBeVisible()
    await expect
      .poll(async () => page.evaluate(() => window.scrollY))
      .toBeLessThanOrEqual(startScrollY + 12)
  })

  test('reloading on mobile restores the active output pane at the bottom', async ({ page }) => {
    // Wait for the welcome boot path to settle before running `help`. Without
    // this, under heavy parallel test load the welcome animation can still be
    // actively appending lines to the output pane when the test polls
    // scrollHeight — and the poll window expires before the help output fully
    // renders, leaving scrollHeight ≤ clientHeight + 40 for the full 5s.
    await ensurePromptReady(page)
    await runCommandMobile(page, 'commands')

    const output = page.locator('.tab-panel.active .output')
    await expect(output.locator('.exit-ok').last()).toContainText(
      /\[process exited with code 0(?: in [\d.]+s)?\]/,
      { timeout: 15_000 },
    )
    await expect
      .poll(async () => output.evaluate((el) => el.scrollHeight > el.clientHeight))
      .toBe(true)

    await expect
      .poll(async () =>
        output.evaluate((el) => {
          const activeId = window.activeTabId
          const activeTab = Array.isArray(window.tabs)
            ? window.tabs.find((tab) => tab && tab.id === activeId)
            : null
          if (activeTab) {
            activeTab.followOutput = false
            activeTab.suppressOutputScrollTracking = false
            activeTab.outputUserScrollUntil = Date.now() + 1000
            activeTab._outputFollowToken = (activeTab._outputFollowToken || 0) + 1
          }
          el.scrollTop = 0
          el.dispatchEvent(new Event('scroll'))
          const remaining = el.scrollHeight - (el.scrollTop + el.clientHeight)
          return Math.max(0, Math.round(remaining))
        }),
      )
      .toBeGreaterThan(100)

    await waitForActiveOutputSettled(page, { timeout: 15_000 })
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 15_000 })
    await ensurePromptReady(page, { timeout: 15_000 })
    await page.evaluate(() => window.dispatchEvent(new Event('resize')))
    await expect
      .poll(async () =>
        page.evaluate(() => document.body.classList.contains('mobile-terminal-mode')),
      )
      .toBe(true)

    await expect
      .poll(async () =>
        output.evaluate((el) => {
          const remaining = el.scrollHeight - (el.scrollTop + el.clientHeight)
          return Math.max(0, Math.round(remaining))
        }),
      )
      .toBeLessThanOrEqual(16)
  })

  test('mobile autocomplete accepts a suggestion by tap and keeps the mobile composer focused', async ({
    page,
  }) => {
    await ensurePromptReady(page, { waitForAutocomplete: true })
    await openMobileKeyboard(page)
    const input = page.locator('#mobile-cmd')
    await setComposerValueForTest(page, 'nmap -', { mobile: true })

    const dropdown = page.locator('#ac-dropdown')
    await expect
      .poll(async () => ({
        hidden: await dropdown.evaluate((node) => node.classList.contains('u-hidden')),
        text: (await dropdown.textContent()) || '',
      }))
      .toEqual(
        expect.objectContaining({
          hidden: false,
          text: expect.stringContaining('-sT'),
        }),
      )

    await dropdown.locator('.ac-item', { hasText: '-sT' }).tap()

    await expect(input).toHaveValue('nmap -sT')
    await expect(input).toBeFocused()
    await expect(dropdown).toBeHidden()
  })

  test('mobile autocomplete opens above the keyboard helper row', async ({ page }) => {
    await ensurePromptReady(page, { waitForAutocomplete: true })
    await openMobileKeyboard(page)
    await expect(page.locator('#mobile-kb-helper')).toBeVisible()
    await setComposerValueForTest(page, 'nmap -', { mobile: true })

    const dropdown = page.locator('#ac-dropdown')
    await expect
      .poll(async () => ({
        hidden: await dropdown.evaluate((node) => node.classList.contains('u-hidden')),
        text: (await dropdown.textContent()) || '',
      }))
      .toEqual(
        expect.objectContaining({
          hidden: false,
          text: expect.stringContaining('-sT'),
        }),
      )

    const gap = await page.evaluate(() => {
      const menu = document.getElementById('ac-dropdown')?.getBoundingClientRect()
      const helper = document.getElementById('mobile-kb-helper')?.getBoundingClientRect()
      if (!menu || !helper) return null
      return Math.round(helper.top - menu.bottom)
    })
    expect(gap).not.toBeNull()
    expect(gap).toBeGreaterThanOrEqual(2)

    const rowHeights = await dropdown.locator('.ac-item').evaluateAll((items) =>
      items.slice(0, 5).map((item) => Math.round(item.getBoundingClientRect().height)),
    )
    expect(rowHeights.length).toBeGreaterThanOrEqual(5)
    expect(Math.max(...rowHeights)).toBeLessThanOrEqual(42)
  })

  test('mobile contextual autocomplete shows value hints after accepting a value-taking flag', async ({
    page,
  }) => {
    await ensurePromptReady(page, { waitForAutocomplete: true })
    await openMobileKeyboard(page)
    const input = page.locator('#mobile-cmd')
    await setComposerValueForTest(page, 'curl -', { mobile: true })

    const dropdown = page.locator('#ac-dropdown')
    await expect
      .poll(async () => ({
        hidden: await dropdown.evaluate((node) => node.classList.contains('u-hidden')),
        text: (await dropdown.textContent()) || '',
      }))
      .toEqual(
        expect.objectContaining({
          hidden: false,
          text: expect.stringContaining('-o'),
        }),
      )
    await dropdown.locator('.ac-item', { hasText: '-o' }).tap()

    await expect(input).toHaveValue('curl -o')
    await input.press('Space')

    await expect
      .poll(async () => ({
        hidden: await dropdown.evaluate((node) => node.classList.contains('u-hidden')),
        text: (await dropdown.textContent()) || '',
      }))
      .toEqual(
        expect.objectContaining({
          hidden: false,
          text: expect.stringContaining('/dev/null'),
        }),
      )
  })

  test('clicking the mobile transcript closes the keyboard and helper row', async ({ page }) => {
    await openMobileKeyboard(page)
    await expect(page.locator('#mobile-kb-helper')).toBeVisible()

    await page.locator('#mobile-shell-transcript').tap()
    await expect(page.locator('#mobile-kb-helper')).toBeHidden()
  })

  test('mobile tab action buttons still work while the keyboard is open', async ({ page }) => {
    await openMobileKeyboard(page)
    await expect(page.locator('#mobile-kb-helper')).toBeVisible()

    const startScrollY = await page.evaluate(() => window.scrollY)
    await runCommandMobile(page, 'hostname')
    await createShareSnapshot(page)
    await expect(page.locator('.tab-panel.active [data-action="permalink"]')).not.toBeFocused()
    await page.locator('.tab-panel.active [data-action="copy"]').click()
    await expect(page.locator('.tab-panel.active [data-action="copy"]')).not.toBeFocused()
    // Clear lives in the hamburger menu on mobile — the per-tab clear
    // button is hidden under `body.mobile-terminal-mode`, so exercising
    // clear with the keyboard open goes through the menu.
    await page.locator('#hamburger-btn').click()
    await expect(page.locator('#mobile-menu-sheet')).not.toHaveClass(/u-hidden/)
    await page.locator('#mobile-menu-sheet [data-menu-action="clear"]').click()

    await expect(page.locator('.tab-panel.active .output .line')).toHaveCount(0)
    await expect(page.locator('#mobile-kb-helper')).toBeHidden()
    await expect(page.locator('#mobile-menu-sheet')).toHaveClass(/u-hidden/)
    await expect
      .poll(async () => page.evaluate(() => window.scrollY))
      .toBeLessThanOrEqual(startScrollY + 12)
  })

  test('creating a new mobile tab does not force composer focus', async ({ page }) => {
    const startScrollY = await page.evaluate(() => window.scrollY)
    await page.locator('#new-tab-btn').click()

    await expect(page.locator('#mobile-cmd')).not.toBeFocused()
    await expect(page.locator('#mobile-kb-helper')).toBeHidden()
    await expect
      .poll(async () => page.evaluate(() => window.scrollY))
      .toBeLessThanOrEqual(startScrollY + 12)
  })

  test('closing a mobile tab after output returns to the active tab without jumping the page', async ({
    page,
  }) => {
    await runCommandMobile(page, 'hostname')
    await page.locator('#new-tab-btn').click()
    await runCommandMobile(page, 'date')
    await page.locator('.tab').nth(1).locator('.tab-close').click()

    await expect(page.locator('#mobile-cmd')).not.toBeFocused()
    await expect(page.locator('#mobile-kb-helper')).toBeHidden()
    await expect.poll(async () => page.evaluate(() => window.scrollY)).toBeLessThanOrEqual(12)
  })

  test('closing a mobile tab does not leave the close button focused', async ({ page }) => {
    await ensurePromptReady(page)
    await page.locator('#new-tab-btn').click()
    await runCommandMobile(page, 'hostname')

    const closeBtn = page.locator('.tab').nth(1).locator('.tab-close')
    await closeBtn.click()

    await expect(page.locator('.tab')).toHaveCount(1)
    await expect
      .poll(async () =>
        page.evaluate(() => document.activeElement?.classList?.contains('tab-close') || false),
      )
      .toBe(false)
  })

  test('closing the only mobile tab does not leave the reset close button focused', async ({
    page,
  }) => {
    await runCommandMobile(page, 'hostname')

    const closeBtn = page.locator('.tab').first().locator('.tab-close')
    await closeBtn.click()

    await expect(page.locator('.tab')).toHaveCount(1)
    await expect
      .poll(async () =>
        page.evaluate(() => document.activeElement?.classList?.contains('tab-close') || false),
      )
      .toBe(false)
  })

  test('mobile tabs bar can overflow and scroll horizontally', async ({ page }) => {
    await ensurePromptReady(page)
    for (let i = 0; i < 6; i++) {
      await page.locator('#new-tab-btn').click()
    }

    const tabsBar = page.locator('.terminal-bar .tabs-bar')
    const metrics = await tabsBar.evaluate((el) => ({
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
    }))
    expect(metrics.scrollWidth).toBeGreaterThan(metrics.clientWidth)
    await tabsBar.evaluate((el) => {
      el.scrollLeft = el.scrollWidth
    })
    await expect.poll(async () => tabsBar.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0)
  })

  test('hamburger button is visible and legacy desktop header button DOM is absent at mobile width', async ({
    page,
  }) => {
    await expect(page.locator('#hamburger-btn')).toBeVisible()
    await expect(page.locator('#header-btns')).toHaveCount(0)
  })

  test('clicking the hamburger opens the mobile menu', async ({ page }) => {
    await page.locator('#hamburger-btn').click()
    await expect(page.locator('#mobile-menu-sheet')).toBeVisible()
  })

  test('mobile menu FAQ and options open overlays in the mobile shell', async ({ page }) => {
    await page.locator('#hamburger-btn').click()
    await page.locator('#mobile-menu-sheet [data-menu-action="faq"]').click()
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)

    await page.locator('#faq-overlay').click({ position: { x: 10, y: 10 } })
    await expect(page.locator('#faq-overlay')).not.toHaveClass(/open/)

    await page.locator('#hamburger-btn').click()
    await page.locator('#mobile-menu-sheet [data-menu-action="options"]').click()
    await expect(page.locator('#options-overlay')).toHaveClass(/open/)

    await page.locator('#options-overlay').click({ position: { x: 10, y: 10 } })
    await expect(page.locator('#options-overlay')).not.toHaveClass(/open/)
  })

  test('mobile menu contains history and theme action buttons', async ({ page }) => {
    await page.locator('#hamburger-btn').click()
    const menu = page.locator('#mobile-menu-sheet')
    await expect(menu.locator('[data-menu-action="history"]')).toBeVisible()
    await expect(menu.locator('[data-menu-action="status-monitor"] .menu-item-label')).toHaveText('status')
    await expect(menu.locator('[data-menu-action="workspace"] .menu-item-label')).toHaveText('files')
    await expect(menu.locator('[data-menu-action="theme"]')).toBeVisible()
  })

  test('mobile menu opens the idle Status Monitor sheet', async ({ page }) => {
    await page.locator('#hamburger-btn').click()
    await page.locator('#mobile-menu-sheet [data-menu-action="status-monitor"]').click()

    await expect(page.locator('#mobile-menu-sheet')).toBeHidden()
    await expect(page.locator('#status-monitor')).toBeVisible()
    await expect(page.locator('#status-monitor > .sheet-grab.gesture-handle')).toBeVisible()
    await expect(page.locator('#status-monitor-title')).toHaveText('Status Monitor')
    await expect(page.locator('.status-monitor-summary')).toContainText('0 active')
    await expect(page.locator('.status-monitor-summary')).toContainText('uptime')
    await expect(page.locator('.status-monitor-close')).toBeHidden()
  })

  test('mobile Files create inputs use mobile-safe text defaults', async ({ page }) => {
    await page.locator('#hamburger-btn').click()
    await page.locator('#mobile-menu-sheet [data-menu-action="workspace"]').click()
    await expect(page.locator('#workspace-overlay')).toHaveClass(/open/)

    await page.locator('#workspace-new-btn').click()
    const fileName = page.locator('#workspace-path-input')
    const fileContents = page.locator('#workspace-text-input')
    for (const field of [fileName, fileContents]) {
      await expect(field).toHaveAttribute('autocomplete', 'off')
      await expect(field).toHaveAttribute('autocapitalize', 'none')
      await expect(field).toHaveAttribute('autocorrect', 'off')
      await expect(field).toHaveAttribute('spellcheck', 'false')
      await expect(field).toHaveAttribute('inputmode', 'text')
      await expect
        .poll(async () => field.evaluate((el) => window.getComputedStyle(el).fontSize))
        .toBe('16px')
    }

    await page.locator('#workspace-cancel-edit-btn').click()
    await expect(page.locator('#workspace-editor')).not.toBeVisible()

    await page.locator('#workspace-new-folder-btn').click()
    const folderName = page.locator('#confirm-host .workspace-folder-form input')
    await expect(folderName).toHaveAttribute('autocomplete', 'off')
    await expect(folderName).toHaveAttribute('autocapitalize', 'none')
    await expect(folderName).toHaveAttribute('autocorrect', 'off')
    await expect(folderName).toHaveAttribute('spellcheck', 'false')
    await expect(folderName).toHaveAttribute('inputmode', 'text')
    await expect
      .poll(async () => folderName.evaluate((el) => window.getComputedStyle(el).fontSize))
      .toBe('16px')
  })

  test('timestamps menu expands inline and applies the selected mode', async ({ page }) => {
    await page.locator('#hamburger-btn').click()
    const sheet = page.locator('#mobile-menu-sheet')
    const toggle = sheet.locator('[data-menu-action="ts-toggle"]')
    const submenu = page.locator('#mobile-menu-ts-submenu')

    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await expect(submenu).toBeHidden()

    await toggle.click()
    await expect(sheet).toBeVisible()
    await expect(submenu).toBeVisible()
    await expect(toggle).toHaveAttribute('aria-expanded', 'true')

    await submenu.locator('[data-ts-mode="elapsed"]').click()
    await expect(sheet).toBeHidden()
    await expect(page.locator('body')).toHaveClass(/ts-elapsed/)

    await page.locator('#hamburger-btn').click()
    await expect(submenu).toBeHidden()
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await toggle.click()
    await expect(submenu.locator('[data-ts-mode="elapsed"]')).toHaveAttribute('aria-pressed', 'true')
    await expect(submenu.locator('[data-ts-mode="off"]')).toHaveAttribute('aria-pressed', 'false')
  })

  test('mobile theme selector opens full screen with evenly sized grouped sections', async ({
    page,
  }) => {
    await page.locator('#hamburger-btn').click()
    await page.locator('#mobile-menu-sheet [data-menu-action="theme"]').click()

    await expect(page.locator('#theme-overlay')).toHaveClass(/open/)
    await expect(page.locator('#theme-modal')).toBeVisible()

    const viewport = page.viewportSize()
    const modalBox = await page.locator('#theme-modal').boundingBox()
    expect(modalBox).not.toBeNull()
    expect(modalBox.width).toBeGreaterThanOrEqual(viewport.width * 0.95)
    expect(modalBox.height).toBeGreaterThanOrEqual(viewport.height * 0.95)

    const mobileColumns = await page
      .locator('#theme-select')
      .evaluate((el) => el.style.getPropertyValue('--theme-picker-columns-mobile'))
    expect(mobileColumns).toBe('2')

    const gridWidths = await page
      .locator('#theme-select .theme-picker-group-grid')
      .evaluateAll((nodes) => nodes.map((node) => Math.round(node.getBoundingClientRect().width)))
    expect(new Set(gridWidths).size).toBe(1)

    await page.locator('#theme-overlay .theme-close').click()
    await expect(page.locator('#theme-overlay')).not.toHaveClass(/open/)
  })

  test('selecting a theme on mobile applies the shell palette, not just the modal preview', async ({
    page,
  }) => {
    await page.locator('#hamburger-btn').click()
    await page.locator('#mobile-menu-sheet [data-menu-action="theme"]').click()

    await page.locator('#theme-select [data-theme-name="apricot_sand"]').click()
    await expect(page.locator('body')).toHaveAttribute('data-theme', 'apricot_sand')

    const shellColors = await page.evaluate(() => {
      const root = getComputedStyle(document.documentElement)
      return {
        bg: root.getPropertyValue('--bg').trim(),
        surface: root.getPropertyValue('--surface').trim(),
        terminalBar: root.getPropertyValue('--theme-terminal-bar-bg').trim(),
        panel: root.getPropertyValue('--theme-panel-bg').trim(),
      }
    })

    expect(shellColors.bg).toBe('#fbf2e8')
    expect(shellColors.surface).toBe('#fffaf3')
    expect(shellColors.terminalBar).toBe('#e7d2b9')
    expect(shellColors.panel).toBe('#f1e3d0')
  })

  test('clicking outside the menu closes it', async ({ page }) => {
    await page.locator('#hamburger-btn').click()
    await expect(page.locator('#mobile-menu-sheet')).toBeVisible()

    // Tap the scrim (the canonical "outside the sheet" surface). The scrim is
    // `position: fixed; inset: 0` so its bounding-box center is the viewport
    // center, which sits behind the bottom-anchored menu sheet (z-index 101 >
    // scrim's 100). A bare `.click()` targets that center and Playwright
    // flags it as intercepted — repeatedly, because expander hover inside
    // the sheet keeps mutating which element is under the pointer — until
    // the 30s actionability timeout. Click near the top-left corner where
    // the scrim is guaranteed to be unobstructed.
    await page.locator('#mobile-menu-sheet-scrim').click({ position: { x: 10, y: 10 } })
    await expect(page.locator('#mobile-menu-sheet')).toBeHidden()
  })

  test('tapping the sticky header dismisses the mobile menu sheet', async ({ page }) => {
    // The mobile-terminal header sits at z-index 90; the menu-sheet scrim must
    // be layered above it (z-index 100) so tapping the header band lands on
    // the scrim and closes the sheet via bindDismissible. A previous iteration
    // of the layering left the header above the scrim, silently breaking the
    // "tap outside to close" affordance for every mobile sheet.
    await page.locator('#hamburger-btn').click()
    await expect(page.locator('#mobile-menu-sheet')).toBeVisible()

    // Tap at a coordinate that lives inside the header's bounding box (top
    // 10px of the viewport) — before the fix this hit the header and no-op'd.
    await page.mouse.click(40, 10)
    await expect(page.locator('#mobile-menu-sheet')).toBeHidden()
  })

  test('workflows sheet reopens at full height after an interrupted drag', async ({ page }) => {
    // Regression: dragging the workflows sheet grab and then closing the sheet
    // via the X button (an external path that bypasses mobile_sheet.js's
    // pointerup bookkeeping) used to leave `transform: translateY(...)` inline
    // on #workflows-modal. The leaked transform followed the modal into its
    // next open, pinning it near the bottom of the viewport with only the
    // header visible and making the grab and close button unreachable.
    // bindMobileSheet now watches the sheet's visibility and scrubs any stale
    // inline styles the moment the sheet becomes hidden.
    await page.waitForFunction(() => {
      const body = document.querySelector('#workflows-modal .workflows-body')
      return body && body.children.length > 0
    }, { timeout: 5000 })

    await page.locator('#hamburger-btn').click()
    await page.locator('#mobile-menu-sheet [data-menu-action="workflows"]').click()
    await expect(page.locator('#workflows-modal')).toBeVisible()

    // Start a synthetic drag on the grab that moves the sheet 40px down.
    const grabBox = await page.locator('#workflows-modal > .sheet-grab').boundingBox()
    const cx = grabBox.x + grabBox.width / 2
    const cy = grabBox.y + grabBox.height / 2
    await page.evaluate(({ cx, cy }) => {
      const grab = document.querySelector('#workflows-modal > .sheet-grab')
      grab.dispatchEvent(new PointerEvent('pointerdown', { pointerId: 77, clientX: cx, clientY: cy, button: 0, bubbles: true }))
      grab.dispatchEvent(new PointerEvent('pointermove', { pointerId: 77, clientX: cx, clientY: cy + 40, bubbles: true }))
    }, { cx, cy })
    await expect.poll(
      async () => page.locator('#workflows-modal').evaluate(el => el.style.transform || ''),
    ).toContain('translateY')

    // External close: dismiss via backdrop. The drag's pointerup never fires.
    await page.locator('#workflows-overlay').click({ position: { x: 10, y: 10 } })
    await expect(page.locator('#workflows-modal')).toBeHidden()

    // Inline transform must be scrubbed before the next open so the modal
    // opens at its normal height.
    const leakedStyle = await page.locator('#workflows-modal').evaluate(el => el.getAttribute('style') || '')
    expect(leakedStyle).not.toContain('translateY')

    // Reopen and confirm the modal renders at normal height, not pinned low.
    await page.locator('#hamburger-btn').click()
    await page.locator('#mobile-menu-sheet [data-menu-action="workflows"]').click()
    await expect(page.locator('#workflows-modal')).toBeVisible()
    const box = await page.locator('#workflows-modal').boundingBox()
    const viewport = page.viewportSize()
    // The sheet renders roughly 88svh tall; it must occupy the majority of
    // the viewport, not collapse to a sliver at the bottom.
    expect(box.height).toBeGreaterThan(viewport.height * 0.5)
  })

  test('mobile Projects creates, links, drills by count chip, and opens row actions', async ({ page }, testInfo) => {
    test.setTimeout(60_000)
    await ensurePromptReady(page)
    const [seededRun] = seedExternalHistoryRuns(testInfo, {
      sessionId: await browserSessionId(page),
      commands: ['dig mobile-project.playwright.example +short'],
    })

    await openMobileProjects(page)
    const projectName = `Mobile Project ${Date.now()}`
    let projectRow = await createMobileProject(page, projectName)

    await projectRow.locator('[data-project-mobile-action="open-project"]').click()
    await expect(page.locator('#project-mobile-detail-view')).toBeVisible()
    await expect(page.locator('#project-mobile-detail-topbar')).toContainText(projectName)

    await page.locator('[data-project-mobile-detail-tab="runs"]').click()
    await page.locator('#project-mobile-detail-body [data-project-action="link-last-run"]').first().click()
    await expect(page.locator('#confirm-host')).toContainText('Add the last run to this project?')
    await page.locator('#confirm-host [data-confirm-action-id="add"]').click()
    await expect(page.locator('#permalink-toast')).toContainText('Last run linked to this project.')
    await expect(page.locator('#project-mobile-detail-body .project-mobile-run-row')).toContainText(seededRun.command)

    await page.locator('[data-project-mobile-action="back-to-list"]').click()
    await expect(page.locator('#project-mobile-list-view')).toBeVisible()
    projectRow = page.locator('.project-mobile-row').filter({ hasText: projectName }).first()
    const runsChip = projectRow.locator('[data-project-mobile-tab="runs"]').filter({ hasText: /1 run/ })
    await expect(runsChip).toBeVisible({ timeout: 15_000 })
    await runsChip.click()

    await expect(page.locator('#project-mobile-detail-view')).toBeVisible()
    await expect(page.locator('[data-project-mobile-detail-tab="runs"]')).toHaveClass(/\bis-active\b/)
    await expect(page.locator('#project-mobile-detail-body .project-mobile-run-row')).toContainText(seededRun.command)

    await page.locator('#project-mobile-detail-body .project-mobile-run-row .project-mobile-row-menu-trigger').click()
    const actionSheet = page.locator('#action-sheet-overlay')
    await expect(actionSheet).toHaveClass(/\bopen\b/)
    await expect(actionSheet.locator('.sheet-grab.gesture-handle')).toBeVisible()
    await expect(actionSheet.locator('[data-project-action="edit-run-metadata"]')).toBeVisible()
    await expect(actionSheet.locator('[data-project-action="open-run"]')).toBeVisible()
    await expect(actionSheet.locator('[data-project-action="unlink-run"]')).toBeVisible()
    await actionSheet.click({ position: { x: 10, y: 10 } })
    await expect(actionSheet).not.toHaveClass(/\bopen\b/)

    await page.locator('[data-project-mobile-detail-tab="packages"]').click()
    await page.locator('#project-mobile-detail-body [data-project-action="package-wizard-open"]').first().click()
    await expect(page.locator('#project-package-wizard-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#project-package-wizard-modal > .sheet-grab.gesture-handle')).toBeVisible()
    const wizardFooter = page.locator('#project-package-wizard-overlay .project-package-wizard-footer')
    await expect(wizardFooter).toBeVisible()
    await page.evaluate(() => {
      const vv = window.visualViewport
      if (!vv) return
      try {
        Object.defineProperty(vv, 'height', {
          configurable: true,
          value: 500,
        })
      } catch (_) {}
      vv.dispatchEvent(new Event('resize'))
    })
    await expect(wizardFooter).toBeVisible()
  })

  test('mobile Projects can launch run comparison from the runs tab', async ({ page }, testInfo) => {
    test.setTimeout(60_000)
    await ensurePromptReady(page)
    const runs = seedExternalHistoryRuns(testInfo, {
      sessionId: await browserSessionId(page),
      commands: [
        'nmap -sT -p 80 mobile-compare.playwright.example',
        'nmap -sT -p 443 mobile-compare.playwright.example',
      ],
    })

    await openMobileProjects(page)
    const projectName = `Mobile Compare ${Date.now()}`
    const projectRow = await createMobileProject(page, projectName)
    const projectId = await projectRow.getAttribute('data-project-id')
    const runIds = runs.slice(0, 2).map(run => run.id)
    await page.evaluate(async ({ id, linkedRunIds }) => {
      for (const runId of linkedRunIds) {
        const resp = await apiFetch(`/projects/${encodeURIComponent(id)}/links`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ entity_type: 'run', entity_id: runId, source: 'manual' }),
        })
        if (!resp.ok) throw new Error(`Failed to link run: ${resp.status}`)
      }
    }, { id: projectId, linkedRunIds: runIds })
    await page.evaluate(() => refreshProjectWorkspace())

    await projectRow.locator('[data-project-mobile-action="open-project"]').click()
    await page.locator('[data-project-mobile-detail-tab="runs"]').click()
    await expect(page.locator('#project-mobile-detail-body .project-mobile-run-row')).toHaveCount(2)

    await page.locator('#project-mobile-detail-body [data-project-action="mobile-compare-runs"]').click()
    const compareSheet = page.locator('#project-mobile-compare-overlay')
    await expect(compareSheet).toHaveClass(/\bopen\b/)
    await compareSheet.locator('.project-mobile-compare-footer .btn-primary').click()
    await expect(compareSheet).toContainText('Compare against')
    await compareSheet.locator('.project-mobile-compare-footer .btn-primary').click()
    await expect(compareSheet).toContainText('Choose the baseline run')
    await compareSheet.locator('.project-mobile-compare-footer .btn-primary').click()

    const compareOverlay = page.locator('#history-compare-overlay')
    await expect(compareOverlay).toHaveClass(/\bopen\b/)
    await expect(page.locator('#project-workspace-overlay')).not.toHaveClass(/\bopen\b/)
    await expect(compareOverlay.locator('#history-compare-subtitle')).toContainText('changed')
    await expect(compareOverlay.locator('.history-compare-split')).toContainText('Run A')
    await expect
      .poll(() => compareOverlay.locator('.history-compare-split').evaluate((node) => node.getBoundingClientRect().height))
      .toBeGreaterThan(60)
    await expect
      .poll(() => compareOverlay.locator('.history-compare-pane').first().evaluate((node) => {
        const styles = getComputedStyle(node)
        return `${['auto', 'scroll'].includes(styles.overflowY)}:${styles.maxHeight}`
      }))
      .toBe('false:none')
    await expect
      .poll(() => compareOverlay.locator('.history-compare-pane-title').first().evaluate((node) => {
        return getComputedStyle(node).position
      }))
      .toBe('sticky')
    await expect(page.locator('#permalink-toast')).not.toContainText('Failed to compare runs')
  })

  test('mobile Projects shows retryable project summary errors', async ({ page }) => {
    await openMobileProjects(page)
    const projectName = `Mobile Retry ${Date.now()}`
    let failSummary = true
    await page.route('**/projects/*/summary', async (route) => {
      if (!failSummary) {
        await route.continue()
        return
      }
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'forced mobile summary failure' }),
      })
    })
    const projectRow = await createMobileProject(page, projectName)

    await projectRow.locator('[data-project-mobile-action="open-project"]').click()
    await expect(page.locator('#project-mobile-detail-body')).toContainText(
      'Could not load this project. It may have been deleted.',
    )
    await expect(page.locator('#project-mobile-detail-body [data-project-mobile-action="retry"]')).toBeVisible()

    failSummary = false
    await page.locator('#project-mobile-detail-body [data-project-mobile-action="retry"]').click()
    await expect(page.locator('#project-mobile-detail-body')).toContainText('Summary', { timeout: 15_000 })
    await expect(page.locator('#project-mobile-detail-topbar')).toContainText(projectName)
  })

  test('workflows sheet starts collapsed and wraps commands inside cards', async ({ page }) => {
    await page.setViewportSize(MOBILE)
    await page.goto('/')
    await page.waitForFunction(() => document.querySelectorAll('#workflows-modal .workflow-card').length > 0)

    await page.locator('#hamburger-btn').click()
    await page.locator('#mobile-menu-sheet [data-menu-action="workflows"]').click()
    await expect(page.locator('#workflows-modal')).toBeVisible()

    const cards = page.locator('#workflows-modal .workflow-card')
    await expect(cards.first()).toHaveClass(/\bis-collapsed\b/)
    await expect(cards.first().locator('.workflow-step').first()).toBeHidden()

    await cards.first().locator('.workflow-card-toggle').click()
    await expect(cards.first()).not.toHaveClass(/\bis-collapsed\b/)
    await expect(cards.first().locator('.workflow-step').first()).toBeVisible()

    await page.locator('#workflows-modal .workflow-card-toggle').evaluateAll(buttons => {
      buttons.forEach(button => {
        const card = button.closest('.workflow-card')
        if (card?.classList.contains('is-collapsed')) button.click()
      })
    })
    const overflowingChipCount = await page
      .locator('#workflows-modal .workflow-step-cmd')
      .evaluateAll(chips => chips.filter(chip => chip.scrollWidth > chip.clientWidth + 1).length)
    expect(overflowingChipCount).toBe(0)
  })

  test('mobile recent peek summarizes recent runs and opens the full history panel on tap', async ({
    page,
  }) => {
    const commands = [
      'banner chip-overflow-test-1',
      'banner chip-overflow-test-2',
      'banner chip-overflow-test-3',
      'banner chip-overflow-test-4',
    ]

    for (const command of commands) {
      await runCommandMobile(page, command)
    }
    await waitForHistoryRuns(page, commands.length)

    const peek = page.locator('#mobile-recent-peek')
    await expect(peek).toBeVisible()
    await expect(page.locator('#mobile-recent-peek-count')).toHaveText(`${commands.length}`)
    await expect(peek).toHaveAttribute('data-peek-mode', 'recents', { timeout: 5_000 })

    await peek.click()
    await expect(page.locator('#history-panel')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#mobile-recents-sheet')).not.toBeVisible()
    await expect(page.locator('#history-mobile-filters-toggle')).toBeVisible()
    await expect(page.locator('#history-search-input')).toBeHidden()
    await expect(page.locator('#history-bulk-toolbar')).toBeHidden()
    await page.locator('#history-mobile-filters-toggle').click()
    await expect(page.locator('#history-search-input')).toBeVisible()
    await expect(page.locator('#history-bulk-toolbar')).toBeVisible()
    const items = page.locator('#history-list .history-entry')
    await expect(items.first()).toBeVisible()
    await expect(items).toHaveCount(commands.length)
  })

  test('mobile full history opens run details from row tap', async ({ page }) => {
    const commands = ['hostname', 'date', 'uptime']

    for (const command of commands) {
      await runCommandMobile(page, command)
    }
    await waitForHistoryRuns(page, commands.length)
    await expect(page.locator('#mobile-recent-peek')).toHaveAttribute('data-peek-mode', 'recents', { timeout: 5_000 })
    await page.locator('#mobile-recent-peek').click()
    await expect(page.locator('#history-panel')).toHaveClass(/\bopen\b/)

    await page
      .locator('#history-list .history-entry')
      .filter({ hasText: 'hostname' })
      .first()
      .click()
    await expect(page.locator('#history-run-overlay')).toHaveClass(/open/)
    await expect(page.locator('#history-run-subtitle')).toContainText('hostname')
    await expect(page.locator('#mobile-cmd')).toHaveValue('')
  })

  test('mobile full history restore action loads the run into the active tab', async ({
    page,
  }) => {
    const commands = ['hostname', 'date']

    for (const command of commands) {
      await runCommandMobile(page, command)
    }
    await waitForHistoryRuns(page, commands.length)

    await page.locator('#new-tab-btn').click()
    await expect(page.locator('#cmd')).toHaveValue('')

    await expect(page.locator('#mobile-recent-peek')).toHaveAttribute('data-peek-mode', 'recents', { timeout: 5_000 })
    await page.locator('#mobile-recent-peek').click()
    await expect(page.locator('#history-panel')).toHaveClass(/\bopen\b/)

    await page
      .locator('#history-list .history-entry')
      .filter({ hasText: 'date' })
      .first()
      .locator('[data-action="restore"]')
      .click()
    await expect(page.locator('.tab-panel.active .output')).toContainText('date')
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('mobile full history rows render absolute time in the tooltip', async ({ page }) => {
    await runCommandMobile(page, 'hostname')
    await waitForHistoryRuns(page, 1)

    await expect(page.locator('#mobile-recent-peek')).toHaveAttribute('data-peek-mode', 'recents', { timeout: 5_000 })
    await page.locator('#mobile-recent-peek').click()
    await expect(page.locator('#history-panel')).toHaveClass(/\bopen\b/)

    const timeEl = page.locator('#history-list .history-entry').first().locator('.history-entry-meta span').nth(1)
    await expect(timeEl).not.toHaveText('')
    // Absolute time is surfaced via the title attribute for precise lookups on touch devices.
    const title = await timeEl.getAttribute('title')
    expect(title).toBeTruthy()
    expect(title.length).toBeGreaterThan(0)
  })

  test('mobile full history permalink action keeps the drawer open', async ({ page }) => {
    await runCommandMobile(page, 'hostname')
    await waitForHistoryRuns(page, 1)

    await expect(page.locator('#mobile-recent-peek')).toHaveAttribute('data-peek-mode', 'recents', { timeout: 5_000 })
    await page.locator('#mobile-recent-peek').click()
    await expect(page.locator('#history-panel')).toHaveClass(/\bopen\b/)

    const firstEntry = page.locator('#history-list .history-entry').first()
    await firstEntry.locator('[data-action="history-menu"]').click()
    await firstEntry.locator('.history-action-menu .dropdown-item', { hasText: 'permalink' }).click()
    await expect(page.locator('#history-panel')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#permalink-toast')).toContainText('Link copied to clipboard')
  })

  test('mobile full history select mode wraps toolbar and row tap selects without long-press side effects', async ({ page }) => {
    test.setTimeout(60_000)
    await runCommandMobile(page, 'hostname')
    await runCommandMobile(page, 'date')
    await waitForHistoryRuns(page, 2)

    await openFullMobileHistoryPanel(page)
    const toolbar = page.locator('#history-bulk-toolbar')
    await expect(page.locator('#mobile-recents-sheet')).not.toBeVisible()
    await expect(toolbar).toBeHidden()
    await page.locator('#history-mobile-filters-toggle').click()
    await expect(toolbar).toBeVisible()
    await expect(toolbar.locator('.history-bulk-toggle')).toBeVisible()
    await expect(toolbar.locator('.history-bulk-select-row')).toBeVisible()
    await toolbar.locator('.history-bulk-toggle').tap()
    await expect(page.locator('#history-list [data-action="select-run"]')).toHaveCount(2)
    await expect(page.locator('#history-list .history-entry').first()).toHaveClass(/\bhistory-entry-selecting\b/)

    await expect
      .poll(() => toolbar.evaluate((node) => {
        const box = node.getBoundingClientRect()
        const children = Array.from(node.children)
        const overflow = children.some((child) => {
          const childBox = child.getBoundingClientRect()
          return childBox.left < box.left - 1 || childBox.right > box.right + 1
        })
        return {
          flexDirection: getComputedStyle(node).flexDirection,
          overflow,
          height: Math.round(box.height),
        }
      }))
      .toEqual(expect.objectContaining({ flexDirection: 'column', overflow: false }))

    const firstRow = page.locator('#history-list .history-entry').filter({ hasText: 'hostname' }).first()
    await firstRow.locator('.history-entry-header').tap()
    await expect(toolbar.locator('.history-bulk-count')).toHaveText('1 selected')
    await expect(page.locator('#history-run-overlay.open')).toHaveCount(0)

    const secondRow = page.locator('#history-list .history-entry').filter({ hasText: 'date' }).first()
    await secondRow.evaluate(async (node) => {
      node.dispatchEvent(new PointerEvent('pointerdown', {
        pointerId: 41,
        pointerType: 'touch',
        bubbles: true,
        cancelable: true,
      }))
      await new Promise((resolve) => setTimeout(resolve, 650))
      node.dispatchEvent(new PointerEvent('pointerup', {
        pointerId: 41,
        pointerType: 'touch',
        bubbles: true,
        cancelable: true,
      }))
    })
    await expect(toolbar.locator('.history-bulk-count')).toHaveText('1 selected')
    await expect(page.locator('#history-run-overlay.open')).toHaveCount(0)
    await expect(page.locator('#history-list .history-action-menu-wrap.open')).toHaveCount(0)
  })

  test('mobile run button disables while a command is running', async ({ page }) => {
    let finishRun
    const releaseRun = new Promise((resolve) => {
      finishRun = resolve
    })
    await page.route('**/runs', async (route) => {
      const payload = JSON.parse(route.request().postData() || '{}')
      if (payload.command === LONG_CMD) {
        await route.fulfill({
          status: 202,
          contentType: 'application/json',
          body: JSON.stringify({ run_id: 'mobile-long-run', stream: '/runs/mobile-long-run/stream' }),
        })
        return
      }
      await route.continue()
    })
    await page.route('**/runs/mobile-long-run/stream**', async (route) => {
      await releaseRun
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: [
          'data: {"type":"started","run_id":"mobile-long-run"}\n\n',
          'data: {"type":"output","text":"mobile long run finished\\n"}\n\n',
          'data: {"type":"exit","code":0,"elapsed":0.1}\n\n',
        ].join(''),
      })
    })

    await ensurePromptReady(page)
    await setComposerValueForTest(page, LONG_CMD, { mobile: true })
    await expect(page.locator('#mobile-run-btn')).toBeEnabled()
    await page.locator('#mobile-run-btn').click()

    await expect(page.locator('#mobile-run-btn')).toBeDisabled()
    await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })

    finishRun()
    await expect(page.locator('.status-pill').filter({ hasNotText: 'RUNNING' })).toBeVisible({
      timeout: 15_000,
    })
    await expect(page.locator('#mobile-run-btn')).toBeDisabled()

    await page.locator('#mobile-cmd').fill('hostname')
    await expect(page.locator('#mobile-run-btn')).toBeEnabled()
  })

  test('mobile permalink copies via the fallback path when clipboard writeText is unavailable', async ({
    page,
  }) => {
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

  test('mobile keyboard helper moves the caret and deletes a word', async ({ page }) => {
    await ensurePromptReady(page)

    await openMobileKeyboard(page)
    await expect(page.locator('#mobile-kb-helper')).toBeVisible()

    await setComposerValueForTest(page, 'ping -c 4 example.com', { mobile: true })
    await expect(page.locator('#mobile-cmd')).toBeFocused()

    const fireKbAction = async (action) => {
      await page.locator(`#mobile-kb-helper [data-kb-action="${action}"]`).click()
    }

    await fireKbAction('left')
    await expect
      .poll(async () => page.locator('#mobile-cmd').evaluate((el) => el.selectionStart))
      .toBe(20)

    await fireKbAction('home')
    await expect
      .poll(async () => page.locator('#mobile-cmd').evaluate((el) => el.selectionStart))
      .toBe(0)

    await fireKbAction('word-right')
    await expect
      .poll(async () => page.locator('#mobile-cmd').evaluate((el) => el.selectionStart))
      .toBe(4)

    await fireKbAction('right')
    await expect
      .poll(async () => page.locator('#mobile-cmd').evaluate((el) => el.selectionStart))
      .toBe(5)

    await fireKbAction('word-left')
    await expect
      .poll(async () => page.locator('#mobile-cmd').evaluate((el) => el.selectionStart))
      .toBe(0)

    await fireKbAction('end')
    await expect
      .poll(async () => page.locator('#mobile-cmd').evaluate((el) => el.selectionStart))
      .toBe(21)

    await fireKbAction('delete-word')
    await expect(page.locator('#mobile-cmd')).toHaveValue('ping -c 4 example.')

    await fireKbAction('delete-line')
    await expect(page.locator('#mobile-cmd')).toHaveValue('')
    await expect
      .poll(async () => page.locator('#mobile-cmd').evaluate((el) => el.selectionStart))
      .toBe(0)
  })

  test('mobile output wraps inside the transcript when timestamps and line numbers are on', async ({ page }) => {
    await ensurePromptReady(page)

    await page.evaluate(() => {
      document.body.classList.add('ln-on', 'ts-clock')
      const out = document.querySelector('.tab-panel.active .output')
      if (!out) return
      out.style.setProperty('--output-prefix-width', '14ch')
      const line = document.createElement('span')
      line.id = 'overflow-probe'
      line.className = 'line stdout'
      line.dataset.prefix = '00:00:00 999'
      line.dataset.tsC = '00:00:00'
      const content = document.createElement('span')
      content.className = 'line-content'
      content.textContent =
        'starting scan at target.example.com 1.2.3.4 port 443 with many ' +
        'flags and a long trailing argument that should wrap instead of ' +
        'scrolling horizontally off the mobile viewport edge'
      line.appendChild(content)
      out.insertBefore(line, out.firstChild)
    })

    // Scoped to the injected probe line: the regression is that translateX
    // shifted paint without reducing the content's layout width, so the line's
    // content box would exceed the output viewport's right edge. With the fix
    // (padding-left on the parent), the content wraps within the content box.
    const fits = await page.locator('.tab-panel.active .output').evaluate((el) => {
      const outRight = el.getBoundingClientRect().right
      const content = el.querySelector('#overflow-probe .line-content')
      const box = content.getBoundingClientRect()
      return { outRight, contentRight: box.right, contentWidth: box.width }
    })
    expect(fits.contentRight).toBeLessThanOrEqual(fits.outRight + 1)
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

  test('mobile Atlas opens list/detail flow and select mode', async ({ page }) => {
    await page.route(/https?:\/\/[^/]+\/atlas(?:\?|\/|$)/, async (route) => {
      const url = new URL(route.request().url())
      const entity = {
        id: 'ent_mobile',
        session_id: 'mobile-session',
        type: 'ip',
        canonical_value: '107.178.109.44',
        first_seen_at: '2026-05-15T00:00:00Z',
        last_seen_at: '2026-05-15T00:01:00Z',
        occurrence_count: 2,
        created: '2026-05-15T00:00:00Z',
        run_count: 1,
        labels: [{ id: 'lbl_mobile', label: 'mobile', source: 'manual', created: '2026-05-15T00:01:00Z' }],
        note: null,
        project_links: [],
        project_link_count: 0,
        run_links: [{ run_id: 'run_mobile', command: 'nmap 107.178.109.44' }],
      }
      if (url.pathname === '/atlas') {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            total: 1,
            counts: { ip: 1, domain: 0, hash: 0, cve: 0, url: 0 },
            findings: 0,
          }),
        })
        return
      }
      if (url.pathname === '/atlas/entities/ent_mobile') {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            entity,
            intel_snapshots: [],
            intel_summary: { status: 'none', providers_with_data: [], highlights: [] },
            runs: [{ run_id: 'run_mobile', command: 'nmap 107.178.109.44', occurrence_count: 2 }],
            findings: [],
          }),
        })
        return
      }
      if (url.pathname === '/atlas/entities') {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ entities: [entity], total: 1, limit: 50, offset: 0 }),
        })
        return
      }
      if (url.pathname === '/atlas/findings') {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            findings: [],
            total: 0,
            limit: 50,
            offset: 0,
            counts: { new: 0, reviewed: 0, important: 0, false_positive: 0, needs_followup: 0 },
          }),
        })
        return
      }
      await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ error: 'not found' }) })
    })
    await page.setViewportSize(MOBILE)
    await page.goto('/')
    await page.evaluate(() => window.dispatchEvent(new Event('resize')))
    await expect
      .poll(async () =>
        page.evaluate(() => document.body.classList.contains('mobile-terminal-mode')),
      )
      .toBe(true)

    await page.locator('#hamburger-btn').click()
    await page.locator('#mobile-menu-sheet [data-menu-action="atlas"]').click()
    await expect(page.locator('#atlas-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#atlas-mobile-root')).toBeVisible()
    await page.locator('#atlas-mobile-tabs [data-atlas-mobile-tab="ip"]').click()
    const row = page.locator('#atlas-mobile-list .atlas-mobile-row').filter({ hasText: '107.178.109.44' })
    await expect(row).toBeVisible({ timeout: 15_000 })

    await row.click()
    await expect(page.locator('#atlas-mobile-entity-view')).toBeVisible()
    await expect(page.locator('#atlas-mobile-entity-topbar')).toContainText('107.178.109.44')
    await page.locator('#atlas-mobile-entity-topbar .atlas-mobile-back-btn').click()
    await expect(page.locator('#atlas-mobile-list-view')).toBeVisible()

    await page.locator('#atlas-mobile-tools .atlas-mobile-overflow-btn').click()
    await expect(page.locator('#action-sheet-overlay')).toHaveClass(/\bopen\b/)
    const selectModeAction = page.locator('#action-sheet .action-sheet-item').filter({ hasText: 'Select mode' })
    await expect.poll(
      async () => {
        const box = await selectModeAction.boundingBox()
        return Math.round(box?.height || 0)
      },
      { message: 'Atlas mobile action-sheet rows stay content-sized' },
    ).toBeLessThan(90)
    await selectModeAction.click()
    await expect(page.locator('#atlas-mobile-bulk-bar')).toBeVisible()
    await row.click()
    await expect(page.locator('#atlas-mobile-bulk-bar')).toContainText('1 selected')
  })
})
