/**
 * Shared helpers for Playwright e2e tests.
 */

// Use the RFC 2544 benchmarking range so the test suite never accidentally
// collides with a real routable address when synthesizing client IPs.
const TEST_IP_SEED = (Date.now() ^ process.pid) >>> 0

/**
 * Return a per-test-run deterministic test-network address so repeated suite
 * runs and parallel specs do not reuse the same rate-limit bucket.
 */
export function makeTestIp(offset = 0) {
  const value = (TEST_IP_SEED + Math.max(0, offset)) >>> 0
  const thirdOctet = (Math.floor(value / 254) % 254) + 1
  const fourthOctet = (value % 254) + 1
  return `198.18.${thirdOctet}.${fourthOctet}`
}

/**
 * Type a command into the input bar and press Enter, then wait for the
 * tab to show an exit status (exit-ok or exit-fail class on the status pill).
 */
export async function runCommand(page, cmd) {
  const input = page.locator('#cmd')
  await input.fill(cmd)
  await page.keyboard.press('Enter')
  // Wait for the status pill to leave the 'running' state
  await page.locator('.status-pill').filter({ hasNotText: 'RUNNING' }).waitFor({ timeout: 15_000 })
}

/**
 * Open the history panel and wait for the async fetch to populate entries.
 */
export async function openHistory(page) {
  await page.locator('#hist-btn').click()
  await page.locator('#history-panel').waitFor({ state: 'visible' })
  // refreshHistoryPanel() fires an async /history fetch after the panel opens.
  // Wait for at least one child (either a .history-entry or the "No runs" div).
  await page.locator('#history-list > *').first().waitFor({ state: 'visible' })
}

/**
 * Open the history panel and wait until at least one .history-entry is visible.
 *
 * The server writes a completed run to SQLite AFTER sending the SSE exit event,
 * so a /history fetch that races with the DB write returns an empty list.  If
 * the panel opens but shows "No runs yet.", close it and re-open it once to
 * retry the fetch — by then the commit will have landed.
 */
export async function openHistoryWithEntries(page) {
  // Wait for the server-backed history endpoint to contain real rows before
  // opening the drawer; this avoids racing SQLite persistence after a run ends.
  await waitForHistoryRuns(page, 1)
  await openHistory(page)
  await page.locator('#history-list .history-entry').first().waitFor({ state: 'visible', timeout: 10_000 })
}

export async function waitForHistoryRuns(page, minRuns) {
  await page.waitForFunction(async min => {
    try {
      const resp = await apiFetch('/history')
      const data = await resp.json()
      return data.runs && data.runs.length >= min
    } catch {
      return false
    }
  }, minRuns, { timeout: 20_000 })

  return page.evaluate(async () => {
    const resp = await apiFetch('/history')
    const data = await resp.json()
    return data.runs || []
  })
}

/**
 * Close the history panel using the in-panel close button (avoids pointer-event
 * conflicts when the panel overlays the toolbar #hist-btn).
 */
export async function closeHistory(page) {
  const panel = page.locator('#history-panel')
  const isOpen = await panel.evaluate(el => el.classList.contains('open'))
  if (isOpen) {
    await page.locator('#history-close').click()
    await panel.waitFor({ state: 'hidden' })
  }
}
