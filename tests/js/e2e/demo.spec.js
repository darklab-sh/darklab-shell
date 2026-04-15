/**
 * Demo recording spec.
 *
 * Drives a curated sequence of interactions against a running container for
 * use as a README demo video. Run via scripts/record_demo.sh rather than
 * directly — the wrapper handles health-checking the container, running this
 * spec, and stitching the captured frames into docs/demo.mp4 via ffmpeg.
 *
 * This spec captures frames via page.screenshot() (which respects
 * deviceScaleFactor, giving 2560×1600 images) rather than Playwright's built-in
 * video recorder (which ignores deviceScaleFactor and captures at CSS pixel
 * resolution). Frames are written to test-results/demo-frames/ and stitched
 * by the wrapper script.
 *
 * Not part of the normal test suite. This file is only matched by
 * playwright.demo.config.js (testMatch: '** /demo.spec.js').
 */

import { mkdirSync, writeFileSync, rmSync } from 'fs'
import { dirname, resolve, join } from 'path'
import { fileURLToPath } from 'url'
import { test, expect } from '@playwright/test'
import { ensurePromptReady } from './helpers.js'

const __dir = dirname(fileURLToPath(import.meta.url))

// Keystroke delay — human-like typing without being tedious to watch.
const TYPE_DELAY_MS = 52

/**
 * Type a command into the active composer with a human-like keystroke delay.
 * Does not submit — call page.keyboard.press('Enter') afterward.
 */
async function typeSlowly(page, text, { delay = TYPE_DELAY_MS } = {}) {
  // Focus via evaluate rather than click — #cmd is the hidden backing input and
  // may sit below the visible viewport when the welcome screen is rendered, so
  // Playwright's click (which requires viewport visibility) retries forever.
  await page.evaluate(() => document.getElementById('cmd').focus())
  await page.keyboard.type(text, { delay })
}

/**
 * Submit the typed command and wait for it to finish running.
 */
async function waitForFinished(page, cmd, { timeoutMs = 30_000 } = {}) {
  await page.keyboard.press('Enter')
  await page.waitForFunction(
    expectedCmd => {
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
  await page.waitForTimeout(1_200)
}

/**
 * Switch to a named theme by clicking its card inside the already-open theme
 * modal, then pause briefly so the color change is visible in the recording.
 */
async function switchTheme(page, themeName, { pauseMs = 2_000 } = {}) {
  await page.locator(`[data-theme-name="${themeName}"]`).click()
  await page.waitForTimeout(pauseMs)
}

test('demo', async ({ page }) => {
  test.skip(!process.env.RUN_DEMO, 'set RUN_DEMO=1 to record the demo (use scripts/record_demo.sh)')
  test.setTimeout(300_000)

  // ── Frame capture setup ───────────────────────────────────────────────────
  const FRAMES_DIR = resolve(__dir, '../../../test-results/demo-frames')
  try { rmSync(FRAMES_DIR, { recursive: true }) } catch { /* first run */ }
  mkdirSync(FRAMES_DIR, { recursive: true })

  const capture = { done: false, idx: 0 }
  const TARGET_FPS = 10
  const captureLoop = (async () => {
    while (!capture.done) {
      const t0 = Date.now()
      try {
        const buf = await page.screenshot({ type: 'png' })
        writeFileSync(
          join(FRAMES_DIR, `frame_${String(capture.idx++).padStart(6, '0')}.png`),
          buf,
        )
      } catch { /* page mid-navigation or closing — skip frame */ }
      const elapsed = Date.now() - t0
      const remaining = Math.max(1, Math.round(1000 / TARGET_FPS) - elapsed)
      await page.waitForTimeout(remaining)
    }
  })()

  // Mock the history API so the drawer shows a full, realistic list regardless
  // of how many commands were actually run during this recording session.
  // DELETE requests are passed through so in-session runs are preserved.
  await page.route('**/history', async (route) => {
    if (route.request().method() !== 'GET') return route.continue()
    const now = Date.now()
    const mk = (id, cmd, exitCode, ageMs) => ({
      id, command: cmd, exit_code: exitCode,
      started: new Date(now - ageMs).toISOString(),
      full_output_available: false,
    })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runs: [
          mk(1,  'nslookup -type=A darklab.sh',              0,   2 * 60_000),
          mk(2,  'ping -i 0.5 -c 50 darklab.sh',             0,   5 * 60_000),
          mk(3,  'curl -s https://api.ipify.org',             0,   1 * 3_600_000),
          mk(4,  'dig @8.8.8.8 darklab.sh A',                0,   2 * 3_600_000),
          mk(5,  'host -t A darklab.sh',                     0,   3 * 3_600_000),
          mk(6,  'openssl s_client -connect darklab.sh:443', 0,   4 * 3_600_000),
          mk(7,  'whois darklab.sh',                         0,   5 * 3_600_000),
          mk(8,  'traceroute darklab.sh',                    0,   6 * 3_600_000),
          mk(9,  'nmap -p 80,443 darklab.sh',                0,  12 * 3_600_000),
          mk(10, 'curl -I https://darklab.sh',               0,  18 * 3_600_000),
          mk(11, 'mtr --report darklab.sh',                  0,  24 * 3_600_000),
          mk(12, 'dig +short darklab.sh MX',                 0,  30 * 3_600_000),
          mk(13, 'curl -sv https://darklab.sh 2>&1',         0,  36 * 3_600_000),
          mk(14, 'nmap -sV -p 22,80,443 darklab.sh',         0,  42 * 3_600_000),
          mk(15, 'dig darklab.sh NS',                        0,  48 * 3_600_000),
          mk(16, 'ping -c 10 darklab.sh',                    0,  54 * 3_600_000),
          mk(17, 'openssl s_client -connect darklab.sh:443 -showcerts', 0, 60 * 3_600_000),
          mk(18, 'host -t MX darklab.sh',                    0,  66 * 3_600_000),
          mk(19, 'curl -o /dev/null -w "%{http_code}" https://darklab.sh', 0, 72 * 3_600_000),
          mk(20, 'nslookup -type=MX darklab.sh',             0,  78 * 3_600_000),
          mk(21, 'traceroute -n darklab.sh',                 1,  84 * 3_600_000),
          mk(22, 'whois 104.21.0.1',                         0,  90 * 3_600_000),
        ],
        roots: ['curl', 'dig', 'host', 'mtr', 'nmap', 'nslookup', 'openssl', 'ping', 'traceroute', 'whois'],
      }),
    })
  })

  // ── Boot ──────────────────────────────────────────────────────────────────
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.terminal-wrap')).toBeVisible()
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
  await page.waitForTimeout(3_500)
  await ensurePromptReady(page, { cancelWelcome: false, timeout: 30_000 })
  await page.waitForTimeout(800)

  // ── Tab 1: ping — start and leave running ─────────────────────────────────
  await typeSlowly(page, 'ping -i 0.5 -c 50 darklab.sh')
  await page.waitForTimeout(400)
  await submitCommand(page)

  // Let a few lines of ping output accumulate before switching away.
  await page.waitForTimeout(3_000)

  // ── Tab 2: fast DNS / TLS commands ───────────────────────────────────────
  await page.locator('#new-tab-btn').click()
  await ensurePromptReady(page, { timeout: 10_000 })
  await page.waitForTimeout(500)

  await typeSlowly(page, 'nslookup -type=A darklab.sh')
  await page.waitForTimeout(400)
  await waitForFinished(page, 'nslookup -type=A darklab.sh')
  await page.waitForTimeout(1_200)

  await ensurePromptReady(page)
  await typeSlowly(page, 'dig @8.8.8.8 darklab.sh A')
  await page.waitForTimeout(400)
  await waitForFinished(page, 'dig @8.8.8.8 darklab.sh A')
  await page.waitForTimeout(1_200)

  await ensurePromptReady(page)
  await typeSlowly(page, 'host -t A darklab.sh')
  await page.waitForTimeout(400)
  await waitForFinished(page, 'host -t A darklab.sh')
  await page.waitForTimeout(1_200)

  await ensurePromptReady(page)
  await typeSlowly(page, 'openssl s_client -connect ip.darklab.sh:443 -showcerts')
  await page.waitForTimeout(400)
  await waitForFinished(page, 'openssl s_client -connect ip.darklab.sh:443 -showcerts', { timeoutMs: 15_000 })
  await page.waitForTimeout(1_500)

  // ── Switch back to tab 1 to show ping still running ───────────────────────
  await page.locator('.tab').first().click()
  await page.waitForTimeout(2_500)

  // ── History drawer ────────────────────────────────────────────────────────
  await page.locator('#hist-btn').click()
  await page.locator('#history-panel').waitFor({ state: 'visible' })
  await page.locator('#history-list .history-entry').first().waitFor({ state: 'visible', timeout: 10_000 })
  // Pause so the viewer can read the top of the list before scrolling.
  await page.waitForTimeout(2_200)
  // Scroll down incrementally through history entries — .history-panel-body is
  // the actual overflow-y:auto container; #history-list is an unstyled inner div.
  await page.locator('.history-panel-body').evaluate(el => { el.scrollTop += 95 })
  await page.waitForTimeout(700)
  await page.locator('.history-panel-body').evaluate(el => { el.scrollTop += 95 })
  await page.waitForTimeout(700)
  await page.locator('.history-panel-body').evaluate(el => { el.scrollTop += 95 })
  await page.waitForTimeout(700)
  await page.locator('.history-panel-body').evaluate(el => { el.scrollTop += 95 })
  await page.waitForTimeout(700)
  await page.locator('.history-panel-body').evaluate(el => { el.scrollTop += 95 })
  await page.waitForTimeout(700)
  await page.locator('.history-panel-body').evaluate(el => { el.scrollTop += 95 })
  await page.waitForTimeout(1_100)
  // Scroll back up.
  await page.locator('.history-panel-body').evaluate(el => { el.scrollTop -= 160 })
  await page.waitForTimeout(650)
  await page.locator('.history-panel-body').evaluate(el => { el.scrollTop -= 160 })
  await page.waitForTimeout(650)
  await page.locator('.history-panel-body').evaluate(el => { el.scrollTop -= 160 })
  await page.waitForTimeout(650)
  await page.locator('.history-panel-body').evaluate(el => { el.scrollTop -= 160 })
  await page.waitForTimeout(1_000)

  await page.locator('#history-close').click()
  await page.locator('#history-panel').waitFor({ state: 'hidden' })
  await page.waitForTimeout(800)

  // ── Theme switching ───────────────────────────────────────────────────────
  // Each theme: open overlay → pick theme → close overlay → linger on the
  // main UI so the color change is visible → briefly flip between tabs → reopen.
  await page.locator('#theme-btn').click()
  await page.locator('#theme-overlay').waitFor({ state: 'visible' })
  await page.waitForTimeout(2_500)
  await switchTheme(page, 'charcoal_violet', { pauseMs: 9_000 })
  await page.locator('.theme-close').click()
  await page.locator('#theme-overlay').waitFor({ state: 'hidden' })
  await page.waitForTimeout(2_500)
  await page.locator('.tab').nth(1).click()
  await page.waitForTimeout(900)
  await page.locator('.tab').first().click()
  await page.waitForTimeout(1_500)

  await page.locator('#theme-btn').click()
  await page.locator('#theme-overlay').waitFor({ state: 'visible' })
  await page.waitForTimeout(2_500)
  await switchTheme(page, 'ember_obsidian', { pauseMs: 9_000 })
  await page.locator('.theme-close').click()
  await page.locator('#theme-overlay').waitFor({ state: 'hidden' })
  await page.waitForTimeout(2_500)
  await page.locator('.tab').nth(1).click()
  await page.waitForTimeout(900)
  await page.locator('.tab').first().click()
  await page.waitForTimeout(1_500)

  await page.locator('#theme-btn').click()
  await page.locator('#theme-overlay').waitFor({ state: 'visible' })
  await page.waitForTimeout(2_500)
  await switchTheme(page, 'olive_grove', { pauseMs: 9_000 })
  // Return to the original theme so the recording ends on the best-looking frame.
  await switchTheme(page, 'darklab_obsidian', { pauseMs: 4_000 })
  await page.locator('.theme-close').click()
  await page.locator('#theme-overlay').waitFor({ state: 'hidden' })
  await page.waitForTimeout(2_000)

  capture.done = true
  await captureLoop
})
