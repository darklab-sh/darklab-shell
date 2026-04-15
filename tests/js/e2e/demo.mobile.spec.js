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
 * captured frames into docs/demo-mobile.webm via ffmpeg.
 *
 * This spec captures frames via page.screenshot() (which respects
 * deviceScaleFactor, giving 1179×2556 images) rather than Playwright's built-in
 * video recorder (which ignores deviceScaleFactor and captures at CSS pixel
 * resolution). Frames are written to test-results/demo-mobile-frames/ and
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

const __dir = dirname(fileURLToPath(import.meta.url))
const KEYBOARD_SRC = `data:image/png;base64,${readFileSync(resolve(__dir, 'fixtures/ios-keyboard-dark.png')).toString('base64')}`

// Keystroke delay — human-like typing without being tedious to watch.
const TYPE_DELAY_MS = 52

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
  for (const char of text) {
    await page.evaluate((c) => {
      const input = document.getElementById('mobile-cmd')
      if (!input) return
      const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value',
      ).set
      nativeSetter.call(input, (input.value || '') + c)
      input.dispatchEvent(new InputEvent('input', {
        bubbles: true, cancelable: true, data: c, inputType: 'insertText',
      }))
    }, char)
    await page.waitForTimeout(delay)
  }
}

/**
 * Submit the typed command and wait for it to finish running.
 */
async function waitForFinished(page, cmd, { timeoutMs = 30_000 } = {}) {
  await page.locator('#mobile-run-btn').click()
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
  })
}

/**
 * Switch to a named theme by clicking its card inside the already-open theme
 * overlay, then pause briefly so the color change is visible in the recording.
 */
async function switchTheme(page, themeName, { pauseMs = 2_000 } = {}) {
  await page.locator(`[data-theme-name="${themeName}"]`).click()
  await page.waitForTimeout(pauseMs)
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
    el.style.cssText = 'position:fixed;bottom:0;left:0;width:100%;height:272px;z-index:100;pointer-events:none'
    const img = document.createElement('img')
    img.src = src
    img.style.cssText = 'width:100%;height:100%;display:block;object-fit:fill'
    el.appendChild(img)
    document.body.appendChild(el)
  }, KEYBOARD_SRC)
}

test('demo-mobile', async ({ page }) => {
  test.skip(!process.env.RUN_DEMO, 'set RUN_DEMO=1 to record the demo (use scripts/record_demo_mobile.sh)')
  test.setTimeout(300_000)

  // ── Frame capture setup ───────────────────────────────────────────────────
  // page.screenshot() respects deviceScaleFactor (returns 1179×2556 for a
  // 393×852 viewport at deviceScaleFactor: 3). Playwright's built-in video
  // recorder does NOT — it always captures at CSS pixel dimensions. We run a
  // background screenshot loop concurrently with the demo and stitch the frames
  // into a video with ffmpeg after the test completes.
  //
  // The loop runs concurrently by exploiting the fact that every await in the
  // main demo (waitForTimeout, locator actions, etc.) yields the JS event loop,
  // giving the capture loop time to execute. page.screenshot() is safe to call
  // during most Playwright operations; errors are caught and the frame skipped.
  const FRAMES_DIR = resolve(__dir, '../../../test-results/demo-mobile-frames')
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

  // ── Boot ──────────────────────────────────────────────────────────────────
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  // With isMobile: false, Chromium does not simulate the mobile browser chrome
  // reservation — the full 393×852 CSS viewport is page content with no gray
  // bar. svh == vh == 852px in this mode, so the history panel's max-height:
  // 88svh renders correctly tall without any CSS overrides.
  //
  // typeSlowly() still injects characters via the native value setter +
  // InputEvent without .focus() — prevents Chromium's keyboard simulation
  // (which fires even in non-mobile mode on hasTouch devices). Patching
  // getMobileKeyboardOffset to 0 prevents the visualViewport listener from
  // spuriously triggering keyboard-open state.
  await page.evaluate(() => { window.getMobileKeyboardOffset = () => 0 })

  // Mock the history API so the drawer shows a realistic full list regardless
  // of how many commands were run during this recording session. Without this
  // the panel renders short because only 2 entries exist in the container DB.
  // DELETE requests are passed through so the in-session runs are preserved.
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

  await expect(page.locator('#mobile-composer')).toBeVisible()

  // Ensure we start on Darklab Obsidian regardless of any persisted preference.
  await page.evaluate(() => {
    if (typeof applyThemeSelection === 'function') applyThemeSelection('darklab_obsidian')
  })

  // Let the welcome animation play briefly before settling.
  await page.waitForTimeout(3_500)
  await ensurePromptReady(page, { cancelWelcome: false, timeout: 30_000 })
  await page.waitForTimeout(800)

  // ── Tab 1: ping — type, submit, keyboard closes, watch output fill screen ──
  await mountKeyboard(page)
  await page.waitForTimeout(300)
  await typeSlowly(page, 'ping -i 0.5 -c 50 darklab.sh')
  await page.waitForTimeout(400)
  // Short pause so the first output line is visible before dismissing —
  // gives a natural "command started, keyboard closes" feel.
  await submitCommand(page, { pauseMs: 150 })
  await unmountKeyboard(page)

  // Ping runs — full transcript visible, output lines accumulate.
  await page.waitForTimeout(4_500)

  // ── Tab 2: quick DNS lookup while ping still runs in tab 1 ────────────────
  await page.locator('#new-tab-btn').click()
  await ensurePromptReady(page, { timeout: 10_000 })
  await page.waitForTimeout(400)

  await mountKeyboard(page)
  await page.waitForTimeout(300)
  await typeSlowly(page, 'nslookup -type=A darklab.sh')
  await page.waitForTimeout(400)
  await waitForFinished(page, 'nslookup -type=A darklab.sh')
  await unmountKeyboard(page)

  // nslookup output fills the screen briefly.
  await page.waitForTimeout(1_500)

  // ── Switch back to tab 1 — show ping still scrolling ──────────────────────
  await page.locator('.tab').first().click()
  await page.waitForTimeout(3_000)

  // ── History drawer ────────────────────────────────────────────────────────
  await page.locator('#hamburger-btn').click()
  await expect(page.locator('#mobile-menu')).toHaveClass(/open/)
  await page.waitForTimeout(500)

  await page.locator('#mobile-menu [data-action="history"]').click()
  await expect(page.locator('#history-panel')).toHaveClass(/open/)
  await page.locator('#history-list .history-entry').first().waitFor({ state: 'visible', timeout: 10_000 })
  // Pause so the viewer can read the top of the list before scrolling.
  await page.waitForTimeout(2_000)
  // Scroll down incrementally — .history-panel-body is the overflow-y:auto
  // container; #history-list is an unstyled inner div with no overflow set.
  await page.locator('.history-panel-body').evaluate(el => { el.scrollTop += 85 })
  await page.waitForTimeout(650)
  await page.locator('.history-panel-body').evaluate(el => { el.scrollTop += 85 })
  await page.waitForTimeout(650)
  await page.locator('.history-panel-body').evaluate(el => { el.scrollTop += 85 })
  await page.waitForTimeout(650)
  await page.locator('.history-panel-body').evaluate(el => { el.scrollTop += 85 })
  await page.waitForTimeout(650)
  await page.locator('.history-panel-body').evaluate(el => { el.scrollTop += 85 })
  await page.waitForTimeout(1_000)
  // Scroll back up.
  await page.locator('.history-panel-body').evaluate(el => { el.scrollTop -= 140 })
  await page.waitForTimeout(600)
  await page.locator('.history-panel-body').evaluate(el => { el.scrollTop -= 140 })
  await page.waitForTimeout(600)
  await page.locator('.history-panel-body').evaluate(el => { el.scrollTop -= 140 })
  await page.waitForTimeout(900)

  await page.locator('#history-close').click()
  await expect(page.locator('#history-panel')).not.toHaveClass(/open/)
  await page.waitForTimeout(800)

  // ── Theme switching ───────────────────────────────────────────────────────
  // First theme: open picker → switch → close → admire the new look → switch tabs
  await page.locator('#hamburger-btn').click()
  await expect(page.locator('#mobile-menu')).toHaveClass(/open/)
  await page.waitForTimeout(500)

  await page.locator('#mobile-menu [data-action="theme"]').click()
  await expect(page.locator('#theme-overlay')).toHaveClass(/open/)
  await page.waitForTimeout(2_000)

  await switchTheme(page, 'charcoal_violet', { pauseMs: 7_000 })

  await page.locator('.theme-close').click()
  await expect(page.locator('#theme-overlay')).not.toHaveClass(/open/)
  // Linger on the main UI so the new theme is visible, then flip tabs briefly.
  await page.waitForTimeout(2_000)
  await page.locator('.tab').nth(1).click()
  await page.waitForTimeout(800)
  await page.locator('.tab').first().click()
  await page.waitForTimeout(1_200)

  // Second theme: same pattern
  await page.locator('#hamburger-btn').click()
  await expect(page.locator('#mobile-menu')).toHaveClass(/open/)
  await page.waitForTimeout(500)

  await page.locator('#mobile-menu [data-action="theme"]').click()
  await expect(page.locator('#theme-overlay')).toHaveClass(/open/)
  await page.waitForTimeout(2_000)

  await switchTheme(page, 'ember_obsidian', { pauseMs: 7_000 })
  // Return to the original theme so the recording ends on the best-looking frame.
  await switchTheme(page, 'darklab_obsidian', { pauseMs: 4_000 })

  await page.locator('.theme-close').click()
  await expect(page.locator('#theme-overlay')).not.toHaveClass(/open/)
  await page.waitForTimeout(2_000)

  // Stop the background capture loop and wait for it to flush the last frame.
  capture.done = true
  await captureLoop
})
