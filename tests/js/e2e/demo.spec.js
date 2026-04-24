/**
 * Demo recording spec.
 *
 * Drives a curated sequence of interactions against a running container for
 * use as a README demo video. Run via scripts/record_demo.sh rather than
 * directly — the wrapper handles health-checking the container, running this
 * spec, and stitching the captured frames into assets/darklab_shell_demo.mp4 via ffmpeg.
 *
 * This spec captures frames via page.screenshot() (which respects
 * deviceScaleFactor, giving 3200×1800 images) rather than Playwright's built-in
 * video recorder (which ignores deviceScaleFactor and captures at CSS pixel
 * resolution). Frames are written to /tmp/darklab_shell-demo-frames/ and stitched
 * by the wrapper script.
 *
 * Not part of the normal test suite. This file is only matched by
 * playwright.demo.config.js (testMatch: '** /demo.spec.js').
 */

import { mkdirSync, writeFileSync, rmSync } from 'fs'
import { join } from 'path'
import { test, expect } from '@playwright/test'
import { ensurePromptReady } from './helpers.js'
import { buildVisualHistoryPayload } from './visual_history_fixture.js'
import { assertVisualFlowGuardrails } from './visual_guardrails.js'
import { CAPTURE_SESSION_TOKEN } from '../../../config/playwright.visual.contracts.js'

// Keystroke delay — intentionally closer to a real person than a script.
const TYPE_DELAY_MS = 62

function typingDelay(char, index, baseDelay) {
  const cadence = [0, 18, 7, 28, 11, 23, 5, 34, 14]
  let next = baseDelay + cadence[index % cadence.length]
  if (char === ' ') next += 74
  if (/[./:@-]/.test(char)) next += 32
  if (index > 0 && index % 11 === 0) next += 90
  return next
}

/**
 * Type a command into the active composer with a human-like keystroke delay.
 * Does not submit — call page.keyboard.press('Enter') afterward.
 */
async function typeSlowly(page, text, { delay = TYPE_DELAY_MS } = {}) {
  // Focus via evaluate rather than click — #cmd is the hidden backing input and
  // may sit below the visible viewport when the welcome screen is rendered, so
  // Playwright's click (which requires viewport visibility) retries forever.
  await page.evaluate(() => document.getElementById('cmd').focus())
  for (const [index, char] of [...text].entries()) {
    await page.keyboard.type(char)
    await page.waitForTimeout(typingDelay(char, index, delay))
  }
}

/**
 * Submit the typed command and wait for it to finish running.
 */
async function waitForFinished(page, cmd, { timeoutMs = 30_000 } = {}) {
  await page.keyboard.press('Enter')
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
async function submitCommand(page) {
  await page.keyboard.press('Enter')
  // Brief pause so the running state is visible before we move on.
  await page.waitForTimeout(1_300)
}

/**
 * Select a theme by calling applyThemeSelection() directly in the page
 * context, bypassing any DOM click event.
 *
 * dispatchEvent('click') focuses the button element, which causes Chromium's
 * native focus-scroll management to reposition .theme-body — even when the
 * card is already fully in view — producing a visible jump in the recording.
 * Calling applyThemeSelection() directly has identical effect (theme applied,
 * theme-card-active toggled, selection persisted) without touching focus or
 * scroll.
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

async function openFirstWorkflowFromRail(page) {
  await page.waitForFunction(
    () => document.querySelectorAll('#rail-workflows-list .rail-item').length > 0,
    { timeout: 10_000 },
  )
  const workflowsClosed = await page.locator('#rail-section-workflows').evaluate((node) =>
    node.classList.contains('closed'),
  )
  if (workflowsClosed) await page.locator('#rail-workflows-header').click()
  const firstWorkflow = page.locator('#rail-workflows-list .rail-item').first()
  await firstWorkflow.hover()
  await page.waitForTimeout(360)
  await firstWorkflow.click()
  await page.locator('#workflows-overlay').waitFor({ state: 'visible' })
}

test('demo', async ({ page }) => {
  test.skip(!process.env.RUN_DEMO, 'set RUN_DEMO=1 to record the demo (use scripts/record_demo.sh)')
  test.setTimeout(300_000)

  await page.addInitScript((token) => {
    try {
      localStorage.setItem('session_token', token)
    } catch (_) {
      // Ignore storage failures in non-standard contexts.
    }
  }, process.env.DEMO_SESSION_TOKEN || CAPTURE_SESSION_TOKEN)

  // ── Frame capture setup ───────────────────────────────────────────────────
  const FRAMES_DIR = process.env.DEMO_FRAMES_DIR || '/tmp/darklab_shell-demo-frames'
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

  // Mock the history API so the drawer shows a full, realistic list regardless
  // of how many commands were actually run during this recording session.
  // DELETE requests are passed through so in-session runs are preserved.
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
  await expect(page.locator('.terminal-wrap')).toBeVisible()
  await assertVisualFlowGuardrails(page, {
    mode: 'desktop',
    requireSeededHistory: true,
    expectedSessionToken: process.env.DEMO_SESSION_TOKEN || CAPTURE_SESSION_TOKEN,
  })

  // Start the capture loop only after the terminal is visible so the first
  // captured frame shows real UI rather than the blank pre-navigation page.
  const TARGET_FPS = 15
  capture.loop = (async () => {
    while (!capture.done) {
      if (capture.paused) {
        await page.waitForTimeout(16)
        continue
      }
      const t0 = Date.now()
      try {
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

  // Fix tab-pill top clipping. Root cause: .tabs-bar has overflow-x:scroll, and
  // CSS §overflow mutual-override rule converts overflow-y:visible → overflow-y:auto
  // whenever overflow-x is non-visible. So every overflow-y:visible !important
  // injection was silently ignored — the computed value stayed "auto", making
  // tabs-bar a Y scroll container that clips the tab at margin-bottom:-1px.
  // Fix: override the overflow shorthand (both axes) to visible so the mutual
  // override rule has nothing to convert.
  await page.addStyleTag({
    content: '.tabs-bar { overflow: visible !important; }',
  })

  // Ensure we start on Darklab Obsidian regardless of any persisted preference.
  await page.evaluate(() => {
    if (typeof applyThemeSelection === 'function') applyThemeSelection('darklab_obsidian')
  })

  // Let the welcome animation play briefly before settling.
  await page.waitForTimeout(2_200)
  await ensurePromptReady(page, { cancelWelcome: false, timeout: 30_000 })
  await page.waitForTimeout(900)

  // ── Tab 1: ping — start and leave running ─────────────────────────────────
  await typeSlowly(page, 'ping -i 0.5 -c 50 darklab.sh')
  await page.waitForTimeout(800)
  await submitCommand(page)

  // Let a few lines of ping output accumulate before switching away.
  await page.waitForTimeout(3_200)

  // ── Tab 2: fast DNS lookups ───────────────────────────────────────────────
  await page.waitForTimeout(900)
  await page.locator('#new-tab-btn').click()
  await ensurePromptReady(page, { timeout: 10_000 })
  await page.waitForTimeout(900)

  await typeSlowly(page, 'nslookup -type=A darklab.sh')
  await page.waitForTimeout(700)
  await waitForFinished(page, 'nslookup -type=A darklab.sh')
  await page.waitForTimeout(1_600)

  await ensurePromptReady(page)
  await typeSlowly(page, 'dig @8.8.8.8 darklab.sh A')
  await page.waitForTimeout(700)
  await waitForFinished(page, 'dig @8.8.8.8 darklab.sh A')
  await page.waitForTimeout(1_700)

  // ── Switch back to tab 1 to show ping still running ───────────────────────
  await page.locator('.tab').first().hover()
  await page.waitForTimeout(700)
  await page.locator('.tab').first().click()
  await page.waitForTimeout(2_700)

  // ── History drawer ────────────────────────────────────────────────────────
  await page.locator('.rail-nav [data-action="history"]').hover()
  await page.waitForTimeout(800)
  await page.locator('.rail-nav [data-action="history"]').click()
  await page.locator('#history-panel').waitFor({ state: 'visible' })
  await page
    .locator('#history-list .history-entry')
    .first()
    .waitFor({ state: 'visible', timeout: 10_000 })
  // Pause so the viewer can read the top of the list before scrolling.
  await page.waitForTimeout(3_200)
  // Smooth scroll down then back up at a natural reading pace.
  await smoothScroll(page, '.history-panel-body', 570, { durationMs: 1_900 })
  await page.waitForTimeout(1_300)
  await smoothScroll(page, '.history-panel-body', 0, { durationMs: 1_450 })
  await page.waitForTimeout(1_200)

  await page.locator('#history-close').hover()
  await page.waitForTimeout(650)
  await page.locator('#history-close').click()
  await page.locator('#history-panel').waitFor({ state: 'hidden' })
  await page.waitForTimeout(1_000)

  // ── Guided workflows modal ────────────────────────────────────────────────
  await openFirstWorkflowFromRail(page)
  await page
    .locator('#workflows-modal .workflow-card')
    .first()
    .waitFor({ state: 'visible', timeout: 10_000 })
  await page.waitForTimeout(5_200)
  await smoothScroll(page, '#workflows-modal .workflows-body', 420, { durationMs: 1_700 })
  await page.waitForTimeout(1_600)
  await smoothScroll(page, '#workflows-modal .workflows-body', 0, { durationMs: 1_250 })
  await page.waitForTimeout(1_700)
  await page.locator('.workflows-close').hover()
  await page.waitForTimeout(700)
  await page.locator('.workflows-close').click()
  await page.locator('#workflows-overlay').waitFor({ state: 'hidden' })
  await page.waitForTimeout(1_100)

  // ── Theme switching ───────────────────────────────────────────────────────
  // Reset scrollTop on open so stale position never carries over. The browse
  // intentionally leaves time for the viewer to read the picker as a new scene.

  await page.locator('.rail-nav [data-action="theme"]').hover()
  await page.waitForTimeout(800)
  await page.locator('.rail-nav [data-action="theme"]').click()
  await page.locator('#theme-overlay').waitFor({ state: 'visible' })
  await page.locator('.theme-body').evaluate((el) => {
    el.scrollTop = 0
  })
  await page.waitForTimeout(3_400)
  // Compute actual card positions now that the grid is rendered.
  const charcoalTop = await centeredScrollTop(page, 'charcoal_violet')
  await smoothScroll(page, '.theme-body', 250, { durationMs: 1_650 }) // scrolling down
  await page.waitForTimeout(1_600)
  await smoothScroll(page, '.theme-body', Math.max(charcoalTop + 130, 620), { durationMs: 1_900 }) // past the card
  await page.waitForTimeout(1_600)
  await smoothScroll(page, '.theme-body', charcoalTop, { durationMs: 1_250 }) // settle on card
  await page.waitForTimeout(2_500) // hover — deciding
  await page.locator('[data-theme-name="charcoal_violet"]').hover()
  await page.waitForTimeout(900)
  await switchTheme(page, 'charcoal_violet')
  await page
    .locator('[data-theme-name="charcoal_violet"].theme-card-active')
    .waitFor({ state: 'attached', timeout: 5_000 })
  await freezeFrame(3_800) // see the selected card
  await page.locator('.theme-close').hover()
  await page.waitForTimeout(700)
  await page.locator('.theme-close').click()
  await page.locator('#theme-overlay').waitFor({ state: 'hidden' })
  await page.waitForTimeout(1_600)
  await page.locator('.tab').nth(1).hover()
  await page.waitForTimeout(700)
  await page.locator('.tab').nth(1).click()
  await page.waitForTimeout(1_000)
  await page.locator('.tab').first().hover()
  await page.waitForTimeout(700)
  await page.locator('.tab').first().click()
  await page.waitForTimeout(2_200)

  capture.done = true
  await capture.loop
})
