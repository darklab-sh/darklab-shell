/**
 * Mobile demo recording spec.
 *
 * Mirrors demo.spec.js but drives the mobile shell UI: uses the mobile
 * composer (#mobile-cmd / #mobile-run-btn), the hamburger menu for history
 * and theme access, and a device profile that triggers the server's mobile
 * template.
 *
 * Run via scripts/record_demo_mobile.sh rather than directly — the wrapper
 * handles health-checking the container, running this spec, and stitching the
 * captured frames into assets/darklab_shell_mobile_demo.mp4 via ffmpeg.
 *
 * This spec captures frames via page.screenshot() (which respects
 * deviceScaleFactor, giving 1290×2796 images) rather than Playwright's built-in
 * video recorder (which ignores deviceScaleFactor and captures at CSS pixel
 * resolution). Frames are written to /tmp/darklab_shell-mobile-demo-frames/ and
 * stitched by the wrapper script.
 *
 * Not part of the normal test suite. This file is only matched by
 * playwright.demo.mobile.config.js (testMatch: '** /demo.mobile.spec.js').
 */

import { readFileSync, mkdirSync, writeFileSync, rmSync } from 'fs'
import { dirname, resolve, join } from 'path'
import { fileURLToPath } from 'url'
import { test, expect } from '@playwright/test'
import { ensurePromptReady } from './helpers.js'
import { buildVisualHistoryPayload } from './visual_history_fixture.js'
import { assertVisualFlowGuardrails } from './visual_guardrails.js'
import { CAPTURE_SESSION_TOKEN } from '../../../config/playwright.visual.contracts.js'

const __dir = dirname(fileURLToPath(import.meta.url))
const KEYBOARD_SRC = `data:image/png;base64,${readFileSync(resolve(__dir, 'fixtures/ios-keyboard-dark.png')).toString('base64')}`

// Keystroke delay — intentionally closer to a real person than a script.
const TYPE_DELAY_MS = 68
const DEMO_TOP_SAFE_AREA_PX = 16

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
  return page.locator(`[data-theme-name="${themeName}"]`).evaluate((card) => {
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

/**
 * Inject the keyboard overlay and shift the app into keyboard-open layout.
 * Call before typeSlowly(). The keyboard image fills the bottom 272px and
 * padding-bottom on #mobile-shell pushes the composer above it.
 */
async function mountKeyboard(page) {
  await page.evaluate((src) => {
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
      'position:fixed;bottom:0;left:0;width:100%;height:272px;z-index:100;pointer-events:none'
    const img = document.createElement('img')
    img.src = src
    img.style.cssText = 'width:100%;height:100%;display:block;object-fit:fill'
    el.appendChild(img)
    document.body.appendChild(el)

    // Activate mobile-keyboard-open so the keyboard helper bar (#mobile-edit-bar)
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
  }, KEYBOARD_SRC)
}

test('demo-mobile', async ({ page }) => {
  test.skip(
    !process.env.RUN_DEMO,
    'set RUN_DEMO=1 to record the demo (use scripts/record_demo_mobile.sh)',
  )
  test.setTimeout(300_000)

  await page.addInitScript((token) => {
    try {
      localStorage.setItem('session_token', token)
    } catch (_) {
      // Ignore storage failures in non-standard contexts.
    }
  }, process.env.DEMO_SESSION_TOKEN || CAPTURE_SESSION_TOKEN)

  // ── Frame capture setup ───────────────────────────────────────────────────
  // page.screenshot() respects deviceScaleFactor (returns 1290×2796 for a
  // 430×932 viewport at deviceScaleFactor: 3). Playwright's built-in video
  // recorder does NOT — it always captures at CSS pixel dimensions. We run a
  // background screenshot loop concurrently with the demo and stitch the frames
  // into a video with ffmpeg after the test completes.
  //
  // The loop runs concurrently by exploiting the fact that every await in the
  // main demo (waitForTimeout, locator actions, etc.) yields the JS event loop,
  // giving the capture loop time to execute. page.screenshot() is safe to call
  // during most Playwright operations; errors are caught and the frame skipped.
  const FRAMES_DIR = process.env.DEMO_FRAMES_DIR || '/tmp/darklab_shell-mobile-demo-frames'
  try {
    rmSync(FRAMES_DIR, { recursive: true })
  } catch {
    /* first run */
  }
  mkdirSync(FRAMES_DIR, { recursive: true })

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
  await page.goto('/', { waitUntil: 'domcontentloaded' })
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
  await page.evaluate((topSafeAreaPx) => {
    window.getMobileKeyboardOffset = () => 0
    const style = document.createElement('style')
    style.id = '__demo-capture-css'
    style.textContent = `
      body.mobile-terminal-mode { padding-top: ${topSafeAreaPx}px !important; }
    `
    document.head.appendChild(style)
  }, DEMO_TOP_SAFE_AREA_PX)

  await expect(page.locator('#mobile-composer')).toBeVisible()
  await assertVisualFlowGuardrails(page, {
    mode: 'mobile',
    requireSeededHistory: true,
    expectedSessionToken: process.env.DEMO_SESSION_TOKEN || CAPTURE_SESSION_TOKEN,
  })

  // Start the capture loop only after the UI is visible so the first captured
  // frame shows real content rather than the blank pre-navigation page.
  const TARGET_FPS = 15
  capture.loop = (async () => {
    while (!capture.done) {
      if (capture.paused) {
        await page.waitForTimeout(16)
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
      await page.waitForTimeout(remaining)
    }
  })()

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
  await typeSlowly(page, 'ping -i 0.5 -c 50 darklab.sh')
  await page.waitForTimeout(800)
  // Short pause so the first output line is visible before dismissing —
  // gives a natural "command started, keyboard closes" feel.
  await submitCommand(page, { pauseMs: 550 })
  await unmountKeyboard(page)

  // Ping runs — full transcript visible, output lines accumulate.
  await page.waitForTimeout(3_500)

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

  // ── Switch back to tab 1 — show ping still scrolling ──────────────────────
  await page.waitForTimeout(900)
  await page.locator('.tab').first().click()
  await page.waitForTimeout(2_800)

  // ── History drawer ────────────────────────────────────────────────────────
  await page.waitForTimeout(900)
  await page.locator('#hamburger-btn').click()
  await expect(page.locator('#mobile-menu-sheet')).toBeVisible()
  await page.waitForTimeout(900)
  await page.locator('#mobile-menu-sheet [data-menu-action="history"]').click()
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

  // ── Guided workflows modal ────────────────────────────────────────────────
  await page.waitForTimeout(900)
  await page.locator('#hamburger-btn').click()
  await expect(page.locator('#mobile-menu-sheet')).toBeVisible()
  await page.waitForTimeout(900)

  await page.locator('#mobile-menu-sheet [data-menu-action="workflows"]').click()
  await expect(page.locator('#workflows-modal')).toBeVisible()
  await page
    .locator('#workflows-modal .workflow-card')
    .first()
    .waitFor({ state: 'visible', timeout: 10_000 })
  await page.waitForTimeout(5_000)
  await smoothScroll(page, '#workflows-modal .workflows-body', 520, { durationMs: 1_700 })
  await page.waitForTimeout(1_600)
  await smoothScroll(page, '#workflows-modal .workflows-body', 0, { durationMs: 1_250 })
  await page.waitForTimeout(1_700)
  await page.locator('#workflows-overlay').click({ position: { x: 10, y: 10 } })
  await expect(page.locator('#workflows-modal')).toBeHidden()
  await page.waitForTimeout(1_100)

  // ── Theme switching ───────────────────────────────────────────────────────
  // Reset scrollTop on open so stale position never carries over. The browse
  // intentionally leaves time for the viewer to read the picker as a new scene.
  await page.waitForTimeout(900)
  await page.locator('#hamburger-btn').click()
  await expect(page.locator('#mobile-menu-sheet')).toBeVisible()
  await page.waitForTimeout(900)

  await page.locator('#mobile-menu-sheet [data-menu-action="theme"]').click()
  await expect(page.locator('#theme-overlay')).toHaveClass(/open/)
  await page.locator('.theme-body').evaluate((el) => {
    el.scrollTop = 0
  })
  await page.waitForTimeout(3_200)
  // Compute actual card positions now that the grid is rendered.
  const charcoalTop = await centeredScrollTop(page, 'charcoal_violet')
  await smoothScroll(page, '.theme-body', 210, { durationMs: 1_350 }) // quick peek
  await page.waitForTimeout(1_500)
  await smoothScroll(page, '.theme-body', Math.max(charcoalTop + 120, 570), { durationMs: 1_700 }) // past the card
  await page.waitForTimeout(1_500)
  await smoothScroll(page, '.theme-body', charcoalTop, { durationMs: 1_150 }) // settle on card
  await page.waitForTimeout(2_400) // hover — deciding
  await switchTheme(page, 'charcoal_violet')
  await page
    .locator('[data-theme-name="charcoal_violet"].theme-card-active')
    .waitFor({ state: 'attached', timeout: 5_000 })
  await freezeFrame(3_600) // see the selected card

  await page.locator('.theme-close').click()
  await expect(page.locator('#theme-overlay')).not.toHaveClass(/open/)
  await page.waitForTimeout(1_600)
  await page.waitForTimeout(700)
  await page.locator('.tab').nth(1).click()
  await page.waitForTimeout(1_000)
  await page.waitForTimeout(700)
  await page.locator('.tab').first().click()
  await page.waitForTimeout(2_000)

  // Stop the background capture loop and wait for it to flush the last frame.
  capture.done = true
  await capture.loop
})
