/**
 * Mobile demo recording spec.
 *
 * Mirrors demo.spec.js but drives the mobile shell UI: uses the mobile
 * composer (#mobile-cmd / #mobile-run-btn), the hamburger menu for history
 * and theme access, and a device profile that triggers the server's mobile
 * template.
 *
 * Run via scripts/record_demo_mobile.sh rather than directly — the wrapper
 * health-checks the container, opens a headed Chromium window, arms OBS, and
 * then runs this spec.
 *
 * The normal OBS wrapper sets DEMO_DISABLE_FRAME_CAPTURE=1. If that flag is
 * unset, this spec can still capture screenshot frames for local experiments.
 *
 * Not part of the normal test suite. This file is only matched by
 * playwright.demo.mobile.config.js (testMatch: '** /demo.mobile.spec.js').
 */

import { existsSync, readFileSync, mkdirSync, writeFileSync, rmSync } from 'fs'
import { dirname, resolve, join } from 'path'
import { fileURLToPath } from 'url'
import { test, expect } from '@playwright/test'
import { ensurePromptReady } from './helpers.js'
import { buildVisualHistoryPayload } from './visual_history_fixture.js'
import { assertVisualFlowGuardrails } from './visual_guardrails.js'
import {
  CAPTURE_SESSION_TOKEN,
  MOBILE_VISUAL_CONTRACT,
} from '../../../config/playwright.visual.contracts.js'

const __dir = dirname(fileURLToPath(import.meta.url))
const KEYBOARD_SRC = `data:image/png;base64,${readFileSync(resolve(__dir, 'fixtures/ios-keyboard-dark.png')).toString('base64')}`

// Keystroke delay — intentionally closer to a real person than a script.
const TYPE_DELAY_MS = 68
const DEMO_OBS_CAPTURE = process.env.DEMO_DISABLE_FRAME_CAPTURE === '1'
const DEMO_TOP_SAFE_AREA_PX = Number(
  process.env.DEMO_MOBILE_TOP_SAFE_AREA_PX || (DEMO_OBS_CAPTURE ? 0 : 16),
)
const DEMO_BOTTOM_SAFE_AREA_PX = Number(process.env.DEMO_MOBILE_BOTTOM_SAFE_AREA_PX || 14)
const WORKSPACE_DEMO_CMD = 'curl -L -o response.html https://noc.darklab.sh'
const LONG_DEMO_CMD = 'ping -i 0.5 -c 300 darklab.sh'
const FFUF_TARGET_URL = 'https://tor-stats.darklab.sh/FUZZ'
const FFUF_WORDLIST =
  '/usr/share/wordlists/seclists/Discovery/Web-Content/DirBuster-2007_directory-list-2.3-small.txt'
const HIGH_CPU_DEMO_CMD = [
  `ffuf -u ${FFUF_TARGET_URL}`,
  `-w ${FFUF_WORDLIST}`,
].join(' ')
const DEMO_THEME_NAME = 'charcoal_lavender'
const DEMO_TIMEOUT_MS = Number(process.env.DEMO_TIMEOUT_MS || 600_000)
const MOBILE_OBS_VIEWPORT_WIDTH = Number(process.env.DEMO_MOBILE_OBS_VIEWPORT_WIDTH || 502)
const MOBILE_KEYBOARD_WIDTH = Number(
  process.env.DEMO_MOBILE_KEYBOARD_WIDTH || MOBILE_VISUAL_CONTRACT.viewport.width,
)
const MOBILE_KEYBOARD_GUTTER_COLOR = process.env.DEMO_MOBILE_KEYBOARD_GUTTER_COLOR || '#161617'
const DEMO_OBS_ARMING_FILE = process.env.DEMO_OBS_ARMING_FILE || ''

function typingDelay(char, index, baseDelay) {
  const cadence = [0, 20, 8, 30, 12, 25, 6, 36, 15]
  let next = baseDelay + cadence[index % cadence.length]
  if (char === ' ') next += 80
  if (/[./:@-]/.test(char)) next += 34
  if (index > 0 && index % 10 === 0) next += 100
  return next
}

/**
 * Type a command into the mobile composer with a human-like keystroke delay.
 *
 * Injects characters directly via the native HTMLInputElement value setter +
 * InputEvent dispatch — never calls .focus(). Focusing #mobile-cmd triggers
 * Chromium's mobile keyboard simulation, which renders a gray overlay above
 * all page content (above any z-index) and cannot be covered by CSS or JS.
 * By skipping focus entirely, the visual viewport never shrinks and the fake
 * keyboard overlay renders correctly at the bottom of the stable 844px frame.
 */
async function typeSlowly(page, text, { delay = TYPE_DELAY_MS } = {}) {
  for (const [index, char] of [...text].entries()) {
    await page.evaluate((c) => {
      const input = document.getElementById('mobile-cmd')
      if (!input) return
      const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        'value',
      ).set
      nativeSetter.call(input, (input.value || '') + c)
      input.dispatchEvent(
        new InputEvent('input', {
          bubbles: true,
          cancelable: true,
          data: c,
          inputType: 'insertText',
        }),
      )
    }, char)
    await page.waitForTimeout(typingDelay(char, index, delay))
  }
}

async function insertTextInstant(page, text) {
  await page.evaluate((value) => {
    const input = document.getElementById('mobile-cmd')
    if (!input) return
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value',
    ).set
    nativeSetter.call(input, (input.value || '') + value)
    input.dispatchEvent(
      new InputEvent('input', {
        bubbles: true,
        cancelable: true,
        data: value,
        inputType: 'insertText',
      }),
    )
  }, text)
}

async function waitForObsArmingSignal(page) {
  if (!DEMO_OBS_ARMING_FILE) return
  await page.setContent(`<!doctype html>
    <html>
      <head>
        <title>darklab_shell</title>
        <style>
          html, body {
            width: 100%;
            height: 100%;
            margin: 0;
            background: #0d0d0d;
            color: #39ff14;
            font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
          }
          body {
            display: grid;
            place-items: center;
          }
          main {
            max-width: 360px;
            text-align: center;
            letter-spacing: 0.08em;
          }
          h1 {
            margin: 0 0 18px;
            font-size: 28px;
            font-weight: 500;
          }
          p {
            margin: 0;
            color: #7a7a7a;
            font-size: 13px;
            line-height: 1.45;
          }
        </style>
      </head>
      <body>
        <main>
          <h1>darklab_shell</h1>
          <p>select this Chromium window in OBS, then press Enter in the terminal</p>
        </main>
      </body>
    </html>`)
  await page.bringToFront()
  mkdirSync(dirname(DEMO_OBS_ARMING_FILE), { recursive: true })
  writeFileSync(`${DEMO_OBS_ARMING_FILE}.ready`, 'ready\n')
  while (!existsSync(DEMO_OBS_ARMING_FILE)) {
    await page.waitForTimeout(250)
  }
}

async function waitForAutocompleteText(page, text, { timeoutMs = 10_000 } = {}) {
  const dropdown = page.locator('#ac-dropdown')
  await expect
    .poll(async () => ({
      hidden: await dropdown.evaluate((node) => node.classList.contains('u-hidden')),
      text: (await dropdown.textContent()) || '',
    }), { timeout: timeoutMs })
    .toEqual(
      expect.objectContaining({
        hidden: false,
        text: expect.stringContaining(text),
      }),
    )
}

async function selectAutocompleteWithArrowDowns(page, targetValue, arrowPresses = 2) {
  await page.waitForFunction(
    (target) => {
      const valueFor = (item) => {
        if (item && typeof item === 'object') return String(item.insertValue || item.value || item.label || '')
        return String(item || '')
      }
      return Array.isArray(acFiltered) && acFiltered.some((item) => valueFor(item) === target)
    },
    targetValue,
    { timeout: 10_000 },
  )

  await page.evaluate(
    ({ target, presses }) => {
      const valueFor = (item) => {
        if (item && typeof item === 'object') return String(item.insertValue || item.value || item.label || '')
        return String(item || '')
      }
      const index = Array.isArray(acFiltered)
        ? acFiltered.findIndex((item) => valueFor(item) === target)
        : -1
      if (index < 0) throw new Error(`Autocomplete target not found: ${target}`)
      acIndex = index - presses
      if (typeof acShow === 'function') acShow(acFiltered)
    },
    { target: targetValue, presses: arrowPresses },
  )

  for (let i = 0; i < arrowPresses; i++) {
    await page.evaluate(() => {
      if (!Array.isArray(acFiltered) || !acFiltered.length) return
      acIndex = (acIndex + 1) % acFiltered.length
      if (typeof acShow === 'function') acShow(acFiltered)
    })
    await page.waitForTimeout(320)
  }
  await expect(page.locator('#ac-dropdown .ac-item.ac-active').first()).toContainText(
    'DirBuster-2007_directory-list-2.3-small.txt',
  )
  await page.waitForTimeout(450)
  await page.evaluate((target) => {
    const valueFor = (item) => {
      if (item && typeof item === 'object') return String(item.insertValue || item.value || item.label || '')
      return String(item || '')
    }
    const item = Array.isArray(acFiltered)
      ? acFiltered.find((entry) => valueFor(entry) === target)
      : null
    if (!item) throw new Error(`Autocomplete target not found: ${target}`)
    const currentValue = typeof getComposerValue === 'function'
      ? getComposerValue()
      : document.getElementById('mobile-cmd')?.value || ''
    const insertValue = String(item.insertValue || item.value || item.label || '')
    const replaceStart = Number(item.replaceStart)
    const replaceEnd = Number(item.replaceEnd)
    const next = Number.isFinite(replaceStart) && Number.isFinite(replaceEnd)
      ? currentValue.slice(0, replaceStart) + insertValue + currentValue.slice(replaceEnd)
      : insertValue
    if (typeof acHide === 'function') acHide()
    if (typeof setComposerValue === 'function') setComposerValue(next, next.length, next.length)
  }, targetValue)
}

async function typeFfufDemoCommand(page) {
  await typeSlowly(page, 'ffuf -u ')
  await page.waitForTimeout(350)

  // Insert the URL all at once so it reads like a paste, then continue typing.
  await insertTextInstant(page, FFUF_TARGET_URL)
  await page.waitForTimeout(650)
  await typeSlowly(page, ' -w ')
  await waitForAutocompleteText(page, 'wordlist')
  await page.waitForTimeout(750)

  await typeSlowly(page, 'DirBuster')
  await waitForAutocompleteText(page, 'DirBuster-2007_directory-list-2.3-small.txt')
  await page.waitForTimeout(550)
  await selectAutocompleteWithArrowDowns(page, FFUF_WORDLIST, 2)
  await expect(page.locator('#mobile-cmd')).toHaveValue(HIGH_CPU_DEMO_CMD)
}

/**
 * Submit the typed command and wait for it to finish running.
 */
async function waitForFinished(page, cmd, { timeoutMs = 30_000 } = {}) {
  await page.locator('#mobile-run-btn').click()
  await page.waitForFunction(
    (expectedCmd) => {
      const tab = typeof getActiveTab === 'function' ? getActiveTab() : null
      return !!tab && tab.command === expectedCmd && tab.st !== 'running'
    },
    cmd,
    { timeout: timeoutMs },
  )
}

/**
 * Submit the typed command without waiting for it to finish. Used for
 * long-running commands like ping where we want to show live output and then
 * switch away while it is still running.
 */
async function submitCommand(page, { pauseMs = 1_200 } = {}) {
  await page.locator('#mobile-run-btn').click()
  await page.waitForTimeout(pauseMs)
}

async function waitForActiveRun(page, cmd, { timeoutMs = 15_000 } = {}) {
  await page.waitForFunction(
    (expectedCmd) => {
      const tab = typeof getActiveTab === 'function' ? getActiveTab() : null
      return !!tab && tab.command === expectedCmd && tab.st === 'running' && !!tab.runId
    },
    cmd,
    { timeout: timeoutMs },
  )
}

async function killActiveTabRun(page) {
  const killBtn = page.locator('#mobile-kill-btn')
  await killBtn.waitFor({ state: 'visible', timeout: 10_000 })
  await killBtn.click()
  await page.locator('#confirm-host').waitFor({ state: 'visible', timeout: 10_000 })
  await page.waitForTimeout(850)
  await page.locator('#confirm-host [data-confirm-action-id="confirm"]').click()
  await page.locator('#confirm-host').waitFor({ state: 'hidden', timeout: 10_000 })
  await page.waitForFunction(
    () => {
      const tab = typeof getActiveTab === 'function' ? getActiveTab() : null
      return !!tab && tab.st !== 'running'
    },
    { timeout: 12_000 },
  )
  await page.waitForTimeout(1_200)
}

async function killActiveRunFromStatusMonitor(page) {
  const killBtn = page.locator('.status-monitor-action-btn-kill').first()
  await killBtn.waitFor({ state: 'visible', timeout: 10_000 })
  await killBtn.click()
  await page.locator('#confirm-host').waitFor({ state: 'visible', timeout: 10_000 })
  await page.waitForTimeout(850)
  // The demo mocks /history/active while the Status Monitor is open so the
  // telemetry card has rich data. Drop that mock before confirming the kill;
  // otherwise the stream-close handler can briefly believe the killed run is
  // still active and auto-restore its saved history transcript.
  await page.unroute('**/history/active').catch(() => {})
  await page.locator('#confirm-host [data-confirm-action-id="kill"]').click()
  await page.locator('#confirm-host').waitFor({ state: 'hidden', timeout: 10_000 })
  await page.waitForFunction(
    () => {
      const tab = typeof getActiveTab === 'function' ? getActiveTab() : null
      return !!tab && tab.st !== 'running' && !tab.reconnectedRun
    },
    { timeout: 12_000 },
  )
  await page.waitForTimeout(1_200)
}

async function openFilesPanelWithResponseFile(page) {
  await page.locator('#hamburger-btn').click()
  await expect(page.locator('#mobile-menu-sheet')).toBeVisible()
  await page.waitForTimeout(750)
  await page.locator('#mobile-menu-sheet [data-menu-action="workspace"]').click()
  await expect(page.locator('#workspace-modal')).toBeVisible()
  const row = page.locator('.workspace-file-row', { hasText: 'response.html' }).first()
  await row.waitFor({ state: 'visible', timeout: 10_000 })
  await page.waitForTimeout(1_600)
  await row.locator('[data-workspace-action="view"]').click()
  await expect(page.locator('#workspace-viewer')).toBeVisible()
  await expect(page.locator('#workspace-viewer-title')).toHaveText('response.html')
  await page.waitForTimeout(3_300)
  await page.locator('#workspace-close-viewer-btn').click()
  await expect(page.locator('#workspace-viewer')).toHaveClass(/u-hidden/)
  await page.evaluate(() => {
    if (typeof closeWorkspace === 'function') closeWorkspace()
  })
  await expect(page.locator('#workspace-overlay')).not.toHaveClass(/open/)
  await page.waitForTimeout(1_000)
}

/**
 * Remove the keyboard overlay and restore the full transcript area.
 * Call after the run button is clicked — mimics the keyboard dismissing
 * on submit so the output fills the whole screen while the command runs.
 */
async function unmountKeyboard(page) {
  await page.evaluate(() => {
    document.getElementById('__fake-kb')?.remove()
    const shell = document.getElementById('mobile-shell')
    if (shell) shell.style.paddingBottom = ''
    window.getMobileKeyboardOffset = () => 0
    document.body.classList.remove('mobile-keyboard-open')
  })
}

/**
 * Dispatch a click on the target theme card.
 *
 * dispatchEvent('click') fires the card's click handler without Playwright's
 * auto-scroll-into-view so the scroll position set by smoothScroll is
 * preserved. Callers must scroll the card into full view beforehand via
 * centeredScrollTop().
 */
async function switchTheme(page, themeName) {
  await page.evaluate((name) => {
    if (typeof applyThemeSelection === 'function') applyThemeSelection(name)
  }, themeName)
}

/**
 * Return the scrollTop that centres the named theme card inside .theme-body.
 *
 * Uses getBoundingClientRect() so the result is correct regardless of the
 * container's current scroll position. Call after the overlay is open and
 * rendered; the layout must be stable before calling.
 */
async function centeredScrollTop(page, themeName) {
  const cardLocator = page.locator(`[data-theme-name="${themeName}"]`)
  await expect(cardLocator, `theme card ${themeName} should exist`).toHaveCount(1, { timeout: 10_000 })
  return cardLocator.evaluate((card) => {
    const container = card.closest('.theme-body')
    if (!container) return 0
    const cRect = container.getBoundingClientRect()
    const kRect = card.getBoundingClientRect()
    const cardTopInContent = kRect.top - cRect.top + container.scrollTop
    return Math.max(0, Math.round(cardTopInContent - cRect.height / 2 + kRect.height / 2))
  })
}

/**
 * Smoothly animate a scroll container to a target scrollTop position.
 *
 * One Playwright round-trip per step (~67 ms) so each step produces one
 * captured frame at 15 fps. Sine ease-in-out is used instead of cubic because
 * its peak derivative is π/2 ≈ 1.57 vs cubic's 3, cutting the maximum
 * per-frame pixel jump by ~48% and giving a more uniform, fluid feel.
 */
async function smoothScroll(page, selector, targetScrollTop, { durationMs = 1_500 } = {}) {
  const startScrollTop = await page.locator(selector).evaluate((el) => el.scrollTop)
  const delta = targetScrollTop - startScrollTop
  if (!delta) return
  const steps = Math.max(1, Math.round(durationMs / 67))
  for (let i = 1; i <= steps; i++) {
    const p = i / steps
    // Sine ease-in-out — shallower peak velocity than cubic, looks more uniform
    const ease = (1 - Math.cos(Math.PI * p)) / 2
    await page.locator(selector).evaluate(
      (el, pos) => {
        el.scrollTop = pos
      },
      Math.round(startScrollTop + delta * ease),
    )
    await page.waitForTimeout(67)
  }
}

async function waitForStatusMonitorResourceValues(page) {
  await page.locator('#status-monitor').waitFor({ state: 'visible', timeout: 10_000 })
  await page.waitForTimeout(3_400)
  await page.evaluate(async () => {
    if (typeof window.refreshStatusMonitor === 'function') await window.refreshStatusMonitor()
  })
  await expect(page.locator('.status-monitor-meter-cpu').first()).toHaveAttribute('aria-label', /CPU (?!n\/a|collecting)/, {
    timeout: 10_000,
  })
  await expect(page.locator('.status-monitor-meter-mem').first()).toHaveAttribute('aria-label', /MEM (?!n\/a)/, {
    timeout: 10_000,
  })
}

async function prepareDemoStatusMonitorTelemetry(page, command) {
  let activePollCount = 0
  const tabRun = await page.evaluate(() => {
    const tab = typeof getActiveTab === 'function' ? getActiveTab() : null
    const rawStart = tab?.runStart
    let startMs = typeof rawStart === 'number' ? rawStart : Date.parse(String(rawStart || ''))
    if (!Number.isFinite(startMs)) startMs = Date.now() - 14_000
    return {
      runId: tab?.runId || 'demo-long-run',
      started: new Date(startMs).toISOString(),
    }
  })
  await page.unroute('**/history/active').catch(() => {})
  await page.route('**/history/active', route => {
    activePollCount += 1
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runs: [{
          run_id: tabRun.runId,
          pid: 4242,
          started: tabRun.started,
          command,
          resource_usage: {
            cpu_seconds: Math.min(42, 14 + activePollCount * 3.4),
            memory_bytes: 301989888 + activePollCount * 1024 * 1024 * 18,
            source: 'demo-mock',
          },
        }],
      }),
    })
  })
}

async function openMobileMenuAction(page, action) {
  await page.locator('#hamburger-btn').click()
  await expect(page.locator('#mobile-menu-sheet')).toBeVisible()
  await page.waitForTimeout(900)
  await page.locator(`#mobile-menu-sheet [data-menu-action="${action}"]`).click()
}

/**
 * Inject the keyboard overlay and shift the app into keyboard-open layout.
 * Call before typeSlowly(). The keyboard image keeps the phone UI width even
 * when the headed OBS viewport is wider.
 */
async function mountKeyboard(page) {
  await page.evaluate(({ gutterColor, src, visualWidth }) => {
    // #mobile-shell is a flex column with #mobile-shell-composer pushed to the
    // bottom via margin-top:auto. Adding padding-bottom reduces the content
    // area of the flex container so the composer lands 272px higher — exactly
    // as it would on a real device when the keyboard opens and the viewport
    // shrinks. The keyboard image then fills that vacated space.
    const shell = document.getElementById('mobile-shell')
    if (shell) shell.style.paddingBottom = '272px'

    const el = document.createElement('div')
    el.id = '__fake-kb'
    // z-index 100: visible above normal content but below modal overlays
    // (history panel, theme picker) so they render correctly over the keyboard.
    el.style.cssText =
      'position:fixed;bottom:0;left:0;width:100%;height:272px;z-index:100;pointer-events:none;' +
      `display:flex;justify-content:center;background:${gutterColor}`
    const img = document.createElement('img')
    img.src = src
    img.style.cssText = `width:${Math.min(visualWidth, window.innerWidth)}px;height:100%;display:block;object-fit:fill`
    el.appendChild(img)
    document.body.appendChild(el)

    // Activate mobile-keyboard-open so the keyboard helper bar (#mobile-kb-helper)
    // becomes visible. getMobileKeyboardOffset is patched to 272 so layout code
    // sees the correct offset. isMobileKeyboardOpen is patched to check for the
    // fake keyboard element — syncMobileViewportState calls isMobileKeyboardOpen
    // to decide whether to clear the class, and it normally returns false because
    // typeSlowly never focuses the input. Tying it to the element's existence
    // keeps mobile-keyboard-open set for exactly as long as the fake keyboard is
    // mounted, without needing a separate teardown step.
    window.getMobileKeyboardOffset = () => 272
    window.isMobileKeyboardOpen = () => !!document.getElementById('__fake-kb')
    document.body.classList.add('mobile-keyboard-open')
  }, {
    gutterColor: MOBILE_KEYBOARD_GUTTER_COLOR,
    src: KEYBOARD_SRC,
    visualWidth: MOBILE_KEYBOARD_WIDTH,
  })
}

test('demo-mobile', async ({ page }) => {
  test.skip(
    !process.env.RUN_DEMO,
    'set RUN_DEMO=1 to record the demo (use scripts/record_demo_mobile.sh)',
  )
  test.setTimeout(DEMO_TIMEOUT_MS)
  const captureFrames = process.env.DEMO_DISABLE_FRAME_CAPTURE !== '1'

  await page.addInitScript((token) => {
    try {
      localStorage.setItem('session_token', token)
    } catch (_) {
      // Ignore storage failures in non-standard contexts.
    }
  }, process.env.DEMO_SESSION_TOKEN || CAPTURE_SESSION_TOKEN)

  // ── Optional screenshot-frame fallback ────────────────────────────────────
  // The normal OBS wrapper disables this path. It remains useful for quick
  // local experiments when an OBS recording session is not available.
  //
  // The loop runs concurrently by exploiting the fact that every await in the
  // main demo (waitForTimeout, locator actions, etc.) yields the JS event loop,
  // giving the capture loop time to execute. page.screenshot() is safe to call
  // during most Playwright operations; errors are caught and the frame skipped.
  const FRAMES_DIR = process.env.DEMO_FRAMES_DIR || '/tmp/darklab_shell-mobile-demo-frames'
  if (captureFrames) {
    try {
      rmSync(FRAMES_DIR, { recursive: true })
    } catch {
      /* first run */
    }
    mkdirSync(FRAMES_DIR, { recursive: true })
  }

  // capture.loop is assigned after page.goto() so the loop never fires against
  // the blank pre-navigation page, which would produce a white first frame.
  // capture.paused is set by freezeFrame() while it's stamping duplicate frames.
  const capture = { done: false, paused: false, idx: 0, loop: null }

  await page.route('**/history**', async (route) => {
    if (route.request().method() !== 'GET') return route.continue()
    if (new URL(route.request().url()).pathname !== '/history') return route.continue()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildVisualHistoryPayload(route.request().url())),
    })
  })

  // ── Boot ──────────────────────────────────────────────────────────────────
  await waitForObsArmingSignal(page)
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.bringToFront()
  // With isMobile: false, Chromium does not simulate the mobile browser chrome
  // reservation — the full 430×932 CSS viewport is page content with no gray
  // bar. svh == vh == 932px in this mode, so the history panel's max-height:
  // 88svh renders correctly tall without any CSS overrides.
  //
  // typeSlowly() still injects characters via the native value setter +
  // InputEvent without .focus() — prevents Chromium's keyboard simulation
  // (which fires even in non-mobile mode on hasTouch devices). Patching
  // getMobileKeyboardOffset to 0 prevents the visualViewport listener from
  // spuriously triggering keyboard-open state.
  //
  // The recorder uses the full CSS viewport as page content, so add a small
  // capture-only safe area above the header. This prevents video encoders and
  // players from visually cropping the header against the very top edge.
  await page.evaluate(({ topSafeAreaPx, bottomSafeAreaPx }) => {
    window.getMobileKeyboardOffset = () => 0
    const style = document.createElement('style')
    style.id = '__demo-capture-css'
    style.textContent = `
      body.mobile-terminal-mode {
        padding-top: ${topSafeAreaPx}px !important;
        padding-bottom: ${bottomSafeAreaPx}px !important;
      }
      body.mobile-terminal-mode.mobile-keyboard-open #mobile-shell-composer #mobile-composer {
        border-bottom-left-radius: 0 !important;
        border-bottom-right-radius: 0 !important;
      }
    `
    document.head.appendChild(style)
  }, {
    topSafeAreaPx: DEMO_TOP_SAFE_AREA_PX,
    bottomSafeAreaPx: DEMO_BOTTOM_SAFE_AREA_PX,
  })

  await expect(page.locator('#mobile-composer')).toBeVisible()
  await assertVisualFlowGuardrails(page, {
    mode: 'mobile',
    requireSeededHistory: true,
    expectedSessionToken: process.env.DEMO_SESSION_TOKEN || CAPTURE_SESSION_TOKEN,
    expectedViewport: captureFrames
      ? null
      : { ...MOBILE_VISUAL_CONTRACT.viewport, width: MOBILE_OBS_VIEWPORT_WIDTH },
  })

  // Start the capture loop only after the UI is visible so the first captured
  // frame shows real content rather than the blank pre-navigation page.
  const TARGET_FPS = 15
  if (captureFrames) {
    capture.loop = (async () => {
      while (!capture.done && !page.isClosed()) {
        if (capture.paused) {
          try {
            await page.waitForTimeout(16)
          } catch {
            break
          }
          continue
        }
        const t0 = Date.now()
        try {
          // Anchor the capture to the top of the document — if anything scrolls
          // the page during the demo (keyboard layout shift, sheet animation),
          // the header would scroll out of frame and the captured screenshot
          // would miss it. scrollTo is cheap and idempotent.
          await page.evaluate(() => {
            window.scrollTo(0, 0)
          })
          const buf = await page.screenshot({ type: 'png' })
          writeFileSync(join(FRAMES_DIR, `frame_${String(capture.idx++).padStart(6, '0')}.png`), buf)
        } catch {
          /* page mid-navigation or closing — skip frame */
        }
        const elapsed = Date.now() - t0
        const remaining = Math.max(1, Math.round(1000 / TARGET_FPS) - elapsed)
        try {
          await page.waitForTimeout(remaining)
        } catch {
          break
        }
      }
    })()
  }

  /**
   * Freeze the current frame for exactly durationMs of video time.
   *
   * page.screenshot() takes ~300 ms on this machine, so a bare
   * waitForTimeout(2_000) only produces ~6 frames — 400 ms of video at 15 fps.
   * freezeFrame() takes ONE screenshot then stamps it N times (= durationMs /
   * frame_interval) so the video shows exactly the intended pause length. The
   * background capture loop is paused while stamping to avoid duplicate index
   * collisions.
  */
  const freezeFrame = async (durationMs) => {
    if (!captureFrames) {
      await page.waitForTimeout(durationMs)
      return
    }
    capture.paused = true
    try {
      await page.evaluate(() => {
        window.scrollTo(0, 0)
      })
      const buf = await page.screenshot({ type: 'png' })
      // Re-create the frames dir defensively — the capture loop swallows ENOENT
      // silently (incrementing capture.idx without writing), so the directory
      // could be missing by the time freezeFrame runs if something removed it.
      mkdirSync(FRAMES_DIR, { recursive: true })
      const frameInterval = Math.round(1000 / TARGET_FPS)
      const frameCount = Math.max(1, Math.round(durationMs / frameInterval))
      for (let i = 0; i < frameCount; i++) {
        writeFileSync(join(FRAMES_DIR, `frame_${String(capture.idx++).padStart(6, '0')}.png`), buf)
      }
    } finally {
      capture.paused = false
    }
  }

  // Ensure we start on Darklab Obsidian regardless of any persisted preference.
  await page.evaluate(() => {
    if (typeof applyThemeSelection === 'function') applyThemeSelection('darklab_obsidian')
  })

  // Let the welcome animation play briefly before settling.
  await page.waitForTimeout(2_200)
  await ensurePromptReady(page, { cancelWelcome: false, timeout: 30_000 })
  await page.waitForTimeout(900)
  // ── Tab 1: ping — type, submit, keyboard closes, watch output fill screen ──
  await mountKeyboard(page)
  await page.waitForTimeout(700)
  await typeSlowly(page, LONG_DEMO_CMD)
  await page.waitForTimeout(800)
  // Short pause so the first output line is visible before dismissing —
  // gives a natural "command started, keyboard closes" feel.
  await submitCommand(page, { pauseMs: 550 })
  await waitForActiveRun(page, LONG_DEMO_CMD)
  await unmountKeyboard(page)

  // Ping runs — full transcript visible, output lines accumulate.
  await page.waitForTimeout(3_000)

  // ── Tab 2: quick DNS lookup while ping still runs in tab 1 ────────────────
  await page.waitForTimeout(900)
  await page.locator('#new-tab-btn').click()
  await ensurePromptReady(page, { timeout: 10_000 })
  await page.waitForTimeout(800)

  await mountKeyboard(page)
  await page.waitForTimeout(700)
  await typeSlowly(page, 'nslookup -type=A darklab.sh')
  await page.waitForTimeout(800)
  await waitForFinished(page, 'nslookup -type=A darklab.sh')
  await unmountKeyboard(page)

  // nslookup output fills the screen briefly.
  await page.waitForTimeout(2_100)

  await mountKeyboard(page)
  await page.waitForTimeout(700)
  await typeSlowly(page, WORKSPACE_DEMO_CMD)
  await page.waitForTimeout(800)
  await waitForFinished(page, WORKSPACE_DEMO_CMD, { timeoutMs: 45_000 })
  await unmountKeyboard(page)
  await page.waitForTimeout(1_500)

  // ── Files panel: captured response file ──────────────────────────────────
  await openFilesPanelWithResponseFile(page)

  // ── Switch back to tab 1 — show ping still scrolling ──────────────────────
  await page.waitForTimeout(900)
  await page.locator('.tab').first().click()
  await page.waitForTimeout(1_000)

  // ── Tab 1: kill ping, then start a heavier ffuf run ───────────────────────
  await killActiveTabRun(page)
  await ensurePromptReady(page, { timeout: 10_000 })
  await page.waitForTimeout(800)
  await mountKeyboard(page)
  await page.waitForTimeout(700)
  await typeFfufDemoCommand(page)
  await page.waitForTimeout(800)
  await submitCommand(page, { pauseMs: 550 })
  await waitForActiveRun(page, HIGH_CPU_DEMO_CMD)
  await unmountKeyboard(page)

  // ── Status Monitor: active ffuf run telemetry ─────────────────────────────
  await prepareDemoStatusMonitorTelemetry(page, HIGH_CPU_DEMO_CMD)
  await page.waitForTimeout(900)
  await openMobileMenuAction(page, 'status-monitor')
  await expect(page.locator('#mobile-menu-sheet')).toBeHidden()
  await waitForStatusMonitorResourceValues(page)
  await page.waitForTimeout(5_000)
  await killActiveRunFromStatusMonitor(page)
  await page.waitForTimeout(1_000)
  await page.evaluate(() => {
    if (typeof closeStatusMonitor === 'function') closeStatusMonitor()
  })
  await page.locator('#status-monitor').waitFor({ state: 'hidden', timeout: 10_000 })
  await page.waitForTimeout(1_000)

  // ── History drawer ────────────────────────────────────────────────────────
  await page.waitForTimeout(900)
  await openMobileMenuAction(page, 'history')
  await expect(page.locator('#mobile-recents-sheet')).toBeVisible()
  await page
    .locator('#mobile-recents-list .sheet-item')
    .first()
    .waitFor({ state: 'visible', timeout: 10_000 })
  // Pause so the viewer can read the top of the list before scrolling.
  await page.waitForTimeout(3_200)
  // Smooth scroll down then back up at a natural reading pace.
  await smoothScroll(page, '#mobile-recents-list', 425, { durationMs: 1_700 })
  await page.waitForTimeout(1_250)
  await smoothScroll(page, '#mobile-recents-list', 0, { durationMs: 1_250 })
  await page.waitForTimeout(1_200)

  await page.locator('#mobile-recents-sheet .sheet-grab').click()
  await expect(page.locator('#mobile-recents-sheet')).toBeHidden()
  await page.waitForTimeout(1_100)

  // ── Theme switching ───────────────────────────────────────────────────────
  // Reset scrollTop on open so stale position never carries over. The browse
  // intentionally leaves time for the viewer to read the picker as a new scene.
  await page.waitForTimeout(900)
  await openMobileMenuAction(page, 'theme')
  await expect(page.locator('#theme-overlay')).toHaveClass(/open/)
  await page.locator('.theme-body').evaluate((el) => {
    el.scrollTop = 0
  })
  await page.waitForTimeout(3_400)
  // Compute actual card positions now that the grid is rendered.
  const charcoalTop = await centeredScrollTop(page, DEMO_THEME_NAME)
  await smoothScroll(page, '.theme-body', 210, { durationMs: 1_150 }) // quick peek
  await page.waitForTimeout(1_000)
  await smoothScroll(page, '.theme-body', Math.max(charcoalTop + 120, 570), { durationMs: 1_350 }) // past the card
  await page.waitForTimeout(1_000)
  await smoothScroll(page, '.theme-body', charcoalTop, { durationMs: 950 }) // settle on card
  await page.waitForTimeout(1_700) // deciding
  await switchTheme(page, DEMO_THEME_NAME)
  await page
    .locator(`[data-theme-name="${DEMO_THEME_NAME}"].theme-card-active`)
    .waitFor({ state: 'attached', timeout: 5_000 })
  await freezeFrame(1_200) // see the selected card

  await page.locator('.theme-close').click()
  await expect(page.locator('#theme-overlay')).not.toHaveClass(/open/)
  await page.waitForTimeout(1_000)
  await page.locator('.tab').nth(1).click()
  await page.waitForTimeout(1_000)

  // Stop the background capture loop and wait for it to flush the last frame.
  capture.done = true
  if (capture.loop) await capture.loop
})
