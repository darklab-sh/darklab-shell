/**
 * Demo recording spec.
 *
 * Drives a curated sequence of interactions against a running container for
 * use as a README demo video. Run via scripts/record_demo.sh rather than
 * directly — the wrapper health-checks the container, opens a headed Chromium
 * window, arms OBS, and then runs this spec.
 *
 * The normal OBS wrapper sets DEMO_DISABLE_FRAME_CAPTURE=1. If that flag is
 * unset, this spec can still capture screenshot frames for local experiments.
 *
 * Not part of the normal test suite. This file is only matched by
 * playwright.demo.config.js (testMatch: '** /demo.spec.js').
 */

import { existsSync, mkdirSync, writeFileSync, rmSync } from 'fs'
import { dirname, join } from 'path'
import { test, expect } from '@playwright/test'
import { ensurePromptReady } from './helpers.js'
import { buildVisualHistoryPayload } from './visual_history_fixture.js'
import { assertVisualFlowGuardrails } from './visual_guardrails.js'
import { CAPTURE_SESSION_TOKEN } from '../../../config/playwright.visual.contracts.js'

// Keystroke delay — intentionally closer to a real person than a script.
const TYPE_DELAY_MS = 62
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
const DEMO_OBS_ARMING_FILE = process.env.DEMO_OBS_ARMING_FILE || ''

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
            text-align: center;
            letter-spacing: 0.08em;
          }
          h1 {
            margin: 0 0 18px;
            font-size: 34px;
            font-weight: 500;
          }
          p {
            margin: 0;
            color: #7a7a7a;
            font-size: 14px;
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
    await page.keyboard.press('ArrowDown')
    await page.waitForTimeout(320)
  }
  await expect(page.locator('#ac-dropdown .ac-item.ac-active').first()).toContainText(
    'DirBuster-2007_directory-list-2.3-small.txt',
  )
  await page.waitForTimeout(450)
  await page.keyboard.press('Enter')
}

async function typeFfufDemoCommand(page) {
  await typeSlowly(page, 'ffuf -u ')
  await page.waitForTimeout(350)

  // Insert the URL all at once so it reads like a paste, then continue typing.
  await page.keyboard.insertText(FFUF_TARGET_URL)
  await page.waitForTimeout(650)
  await typeSlowly(page, ' -w ')
  await waitForAutocompleteText(page, 'wordlist')
  await page.waitForTimeout(750)

  await typeSlowly(page, 'DirBuster')
  await waitForAutocompleteText(page, 'DirBuster-2007_directory-list-2.3-small.txt')
  await page.waitForTimeout(550)
  await selectAutocompleteWithArrowDowns(page, FFUF_WORDLIST, 2)
  await expect(page.locator('#cmd')).toHaveValue(HIGH_CPU_DEMO_CMD)
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
  const killBtn = page.locator('#hud-actions [data-action="kill"]')
  await killBtn.waitFor({ state: 'visible', timeout: 10_000 })
  await killBtn.hover()
  await page.waitForTimeout(650)
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
  await killBtn.hover()
  await page.waitForTimeout(650)
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

async function closeHistoryPanelForDemo(page) {
  const panel = page.locator('#history-panel')
  if (!(await panel.isVisible().catch(() => false))) return

  const closeBtn = page.locator('#history-close')
  const closeVisible = await closeBtn
    .waitFor({ state: 'visible', timeout: 1_500 })
    .then(() => true)
    .catch(() => false)

  if (closeVisible) {
    await closeBtn.hover()
    await page.waitForTimeout(650)
    await closeBtn.click()
  } else {
    await page.keyboard.press('Escape').catch(() => {})
    await page.waitForTimeout(350)
    if (await panel.isVisible().catch(() => false)) {
      await page.evaluate(() => {
        if (typeof hideHistoryPanel === 'function') hideHistoryPanel()
      })
    }
  }

  await panel.waitFor({ state: 'hidden', timeout: 10_000 })
}

async function openHistoryPanelForDemo(page) {
  await page.locator('.rail-nav [data-action="history"]').hover()
  await page.waitForTimeout(800)
  await page.evaluate(() => {
    if (!document.getElementById('demo-history-action-guard')) {
      const style = document.createElement('style')
      style.id = 'demo-history-action-guard'
      style.textContent = '#history-list [data-action] { pointer-events: none !important; }'
      document.head.appendChild(style)
    }
    if (typeof openHistoryWithFilters === 'function') {
      openHistoryWithFilters({ type: 'runs' })
    } else if (typeof toggleHistoryPanelSurface === 'function') {
      toggleHistoryPanelSurface(true)
    }
  })
  await page.locator('#history-panel').waitFor({ state: 'visible', timeout: 10_000 })
}

async function openFilesPanelWithResponseFile(page) {
  await page.locator('.rail-nav [data-action="workspace"]').hover()
  await page.waitForTimeout(700)
  await page.locator('.rail-nav [data-action="workspace"]').click()
  await page.locator('#workspace-modal').waitFor({ state: 'visible', timeout: 10_000 })
  const row = page.locator('.workspace-file-row', { hasText: 'response.html' }).first()
  await row.waitFor({ state: 'visible', timeout: 10_000 })
  await page.waitForTimeout(1_700)
  await row.locator('[data-workspace-action="view"]').click()
  await expect(page.locator('#workspace-viewer-title')).toHaveText('response.html')
  await page.waitForTimeout(3_600)
  await page.locator('#workspace-close-viewer-btn').hover()
  await page.waitForTimeout(600)
  await page.locator('#workspace-close-viewer-btn').click()
  await page.locator('#workspace-viewer-overlay').waitFor({ state: 'hidden', timeout: 10_000 })
  await page.waitForTimeout(700)
  await page.locator('.workspace-close').hover()
  await page.waitForTimeout(600)
  await page.locator('.workspace-close').click()
  await page.locator('#workspace-overlay').waitFor({ state: 'hidden' })
  await page.waitForTimeout(1_000)
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

test('demo', async ({ page }) => {
  test.skip(!process.env.RUN_DEMO, 'set RUN_DEMO=1 to record the demo (use scripts/record_demo.sh)')
  test.setTimeout(300_000)
  const captureFrames = process.env.DEMO_DISABLE_FRAME_CAPTURE !== '1'

  await page.addInitScript((token) => {
    try {
      localStorage.setItem('session_token', token)
    } catch (_) {
      // Ignore storage failures in non-standard contexts.
    }
  }, process.env.DEMO_SESSION_TOKEN || CAPTURE_SESSION_TOKEN)

  // ── Optional screenshot-frame fallback ────────────────────────────────────
  const FRAMES_DIR = process.env.DEMO_FRAMES_DIR || '/tmp/darklab_shell-demo-frames'
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
  const capture = { done: false, idx: 0, loop: null }

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
  await waitForObsArmingSignal(page)
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.bringToFront()
  await expect(page.locator('.terminal-wrap')).toBeVisible()
  await assertVisualFlowGuardrails(page, {
    mode: 'desktop',
    requireSeededHistory: true,
    expectedSessionToken: process.env.DEMO_SESSION_TOKEN || CAPTURE_SESSION_TOKEN,
  })

  // Start the capture loop only after the terminal is visible so the first
  // captured frame shows real UI rather than the blank pre-navigation page.
  const TARGET_FPS = 15
  if (captureFrames) {
    capture.loop = (async () => {
      const frameInterval = Math.round(1000 / TARGET_FPS)
      let nextFrameAt = Date.now()
      while (!capture.done) {
        if (page.isClosed()) break
        let buf = null
        try {
          buf = await page.screenshot({ type: 'png' })
        } catch {
          /* page mid-navigation or closing — skip frame */
        }
        if (buf) {
          // Keep the fallback frame sequence aligned to wall-clock time.
          // Screenshots at Retina resolution are slower than 15 fps on many
          // hosts, so duplicate the newest captured frame for any slots we
          // missed instead of compressing the scene into fast-forward.
          const capturedAt = Date.now()
          const frameSlots = Math.max(1, Math.floor((capturedAt - nextFrameAt) / frameInterval) + 1)
          nextFrameAt += frameSlots * frameInterval
          mkdirSync(FRAMES_DIR, { recursive: true })
          for (let i = 0; i < frameSlots; i++) {
            writeFileSync(join(FRAMES_DIR, `frame_${String(capture.idx++).padStart(6, '0')}.png`), buf)
          }
        } else {
          nextFrameAt += frameInterval
        }
        try {
          await page.waitForTimeout(Math.max(1, nextFrameAt - Date.now()))
        } catch {
          break
        }
      }
    })()
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
  await typeSlowly(page, LONG_DEMO_CMD)
  await page.waitForTimeout(800)
  await submitCommand(page)
  await waitForActiveRun(page, LONG_DEMO_CMD)

  // Let a few lines of ping output accumulate before switching away.
  await page.waitForTimeout(3_000)

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
  await typeSlowly(page, WORKSPACE_DEMO_CMD)
  await page.waitForTimeout(700)
  await waitForFinished(page, WORKSPACE_DEMO_CMD, { timeoutMs: 45_000 })
  await page.waitForTimeout(1_000)

  // ── Files panel: captured response file ──────────────────────────────────
  await openFilesPanelWithResponseFile(page)

  // ── Switch back to tab 1 to show ping still running ───────────────────────
  await page.locator('.tab').first().hover()
  await page.waitForTimeout(700)
  await page.locator('.tab').first().click()
  await page.waitForTimeout(1_000)

  // ── Tab 1: kill ping, then start a heavier ffuf run ───────────────────────
  await killActiveTabRun(page)
  await ensurePromptReady(page, { timeout: 10_000 })
  await page.waitForTimeout(800)
  await typeFfufDemoCommand(page)
  await page.waitForTimeout(800)
  await submitCommand(page)
  await waitForActiveRun(page, HIGH_CPU_DEMO_CMD)

  // ── Status Monitor: active ffuf run telemetry ─────────────────────────────
  await prepareDemoStatusMonitorTelemetry(page, HIGH_CPU_DEMO_CMD)
  await page.locator('#hud-status-cell').hover()
  await page.waitForTimeout(550)
  await page.locator('#hud-status-cell').click()
  await waitForStatusMonitorResourceValues(page)
  await page.waitForTimeout(5_000)
  await killActiveRunFromStatusMonitor(page)
  await page.waitForTimeout(1_000)
  await page.locator('.status-monitor-close').hover()
  await page.waitForTimeout(600)
  await page.locator('.status-monitor-close').click()
  await page.locator('#status-monitor').waitFor({ state: 'hidden', timeout: 10_000 })
  await page.waitForTimeout(1_000)

  // ── History drawer ────────────────────────────────────────────────────────
  await openHistoryPanelForDemo(page)
  await page
    .locator('#history-list .history-entry')
    .first()
    .waitFor({ state: 'visible', timeout: 10_000 })
  // Pause so the viewer can read the top of the list before scrolling.
  await page.waitForTimeout(2_000)
  // Smooth scroll down then back up at a natural reading pace.
  await smoothScroll(page, '.history-panel-body', 760, { durationMs: 3_400 })
  await page.waitForTimeout(1_300)
  await smoothScroll(page, '.history-panel-body', 0, { durationMs: 2_800 })
  await page.waitForTimeout(1_200)

  await closeHistoryPanelForDemo(page)
  await page.waitForTimeout(1_000)

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
  const charcoalTop = await centeredScrollTop(page, DEMO_THEME_NAME)
  await smoothScroll(page, '.theme-body', 250, { durationMs: 1_150 }) // scrolling down
  await page.waitForTimeout(1_000)
  await smoothScroll(page, '.theme-body', Math.max(charcoalTop + 130, 620), { durationMs: 1_350 }) // past the card
  await page.waitForTimeout(1_000)
  await smoothScroll(page, '.theme-body', charcoalTop, { durationMs: 950 }) // settle on card
  await page.waitForTimeout(1_700) // hover — deciding
  await page.locator(`[data-theme-name="${DEMO_THEME_NAME}"]`).hover()
  await page.waitForTimeout(900)
  await switchTheme(page, DEMO_THEME_NAME)
  await page
    .locator(`[data-theme-name="${DEMO_THEME_NAME}"].theme-card-active`)
    .waitFor({ state: 'attached', timeout: 5_000 })
  await page.waitForTimeout(1_200)
  await page.locator('.theme-close').hover()
  await page.waitForTimeout(700)
  await page.locator('.theme-close').click()
  await page.locator('#theme-overlay').waitFor({ state: 'hidden' })
  await page.waitForTimeout(1_000)
  await page.locator('.tab').nth(1).hover()
  await page.waitForTimeout(700)
  await page.locator('.tab').nth(1).click()
  await page.waitForTimeout(1_000)

  capture.done = true
  if (capture.loop) await capture.loop
})
