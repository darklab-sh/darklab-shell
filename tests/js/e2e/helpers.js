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
 * Wait until the welcome boot path has either finished or claimed the tab,
 * then optionally cancel it or request an immediate settle and wait for the
 * prompt to become fully usable.
 */
export async function ensurePromptReady(page, { cancelWelcome = false, timeout = 15_000 } = {}) {
  await page.waitForFunction(
    () => {
      const active = typeof _welcomeActive !== 'undefined' ? _welcomeActive : false
      const bootPending = typeof _welcomeBootPending !== 'undefined' ? _welcomeBootPending : false
      const welcomeTabId = typeof _welcomeTabId !== 'undefined' ? _welcomeTabId : null
      const activeTab = typeof activeTabId !== 'undefined' ? activeTabId : null
      return (
        (active && welcomeTabId === activeTab) ||
        !bootPending ||
        (active && welcomeTabId !== activeTab)
      )
    },
    { timeout },
  )

  await page.evaluate(
    ({ cancel }) => {
      const tabId = typeof activeTabId !== 'undefined' ? activeTabId : null
      const welcomeTabId = typeof _welcomeTabId !== 'undefined' ? _welcomeTabId : null
      if (cancel) {
        if (typeof cancelWelcome === 'function') cancelWelcome(tabId)
        return
      }
      if (
        typeof requestWelcomeSettle === 'function' &&
        typeof _welcomeActive !== 'undefined' &&
        _welcomeActive &&
        welcomeTabId === tabId
      ) {
        requestWelcomeSettle(tabId)
      }
    },
    { cancel: cancelWelcome },
  )

  await page.waitForFunction(
    () => {
      const active = typeof _welcomeActive !== 'undefined' ? _welcomeActive : false
      const bootPending = typeof _welcomeBootPending !== 'undefined' ? _welcomeBootPending : false
      const welcomeTabId = typeof _welcomeTabId !== 'undefined' ? _welcomeTabId : null
      const activeTab = typeof activeTabId !== 'undefined' ? activeTabId : null
      return (!active && !bootPending) || (active && welcomeTabId !== activeTab)
    },
    { timeout },
  )

  await page.waitForFunction(
    () => {
      const mobileMode = document.body.classList.contains('mobile-terminal-mode')
      const target = mobileMode
        ? document.getElementById('mobile-cmd')
        : document.getElementById('cmd')
      if (!(target instanceof HTMLElement)) return false
      const style = window.getComputedStyle(target)
      return style.display !== 'none' && style.visibility !== 'hidden'
    },
    { timeout },
  )

  // Wait for the /autocomplete fetch to populate the context registry.
  // setComposerValueForTest calls getAutocompleteMatches synchronously, so if
  // the registry is still empty it returns no items and immediately hides the
  // dropdown — leaving expect.poll with nothing to poll.
  // Note: acSuggestions (flat suggestions) was removed; the registry is the
  // sole signal that the autocomplete fetch has completed.
  await page.waitForFunction(
    () => {
      return typeof acContextRegistry !== 'undefined' && Object.keys(acContextRegistry).length > 0
    },
    { timeout },
  )
}

/**
 * Type a command into the input bar and press Enter, then wait for the
 * tab to show an exit status (exit-ok or exit-fail class on the status pill).
 */
export async function runCommand(page, cmd) {
  await ensurePromptReady(page)
  const input = page.locator('#cmd')
  await input.fill(cmd)
  await page.keyboard.press('Enter')
  await page.waitForFunction(
    (expectedCmd) => {
      const tab = typeof getActiveTab === 'function' ? getActiveTab() : null
      return !!tab && tab.command === expectedCmd && tab.st !== 'running'
    },
    cmd,
    { timeout: 15_000 },
  )
}

/**
 * Set a composer value through the app's shared input-change path so
 * autocomplete and shared prompt state update deterministically.
 */
export async function setComposerValueForTest(page, value, { mobile = false } = {}) {
  await page.evaluate(
    ({ nextValue, useMobile }) => {
      const input = useMobile
        ? document.getElementById('mobile-cmd')
        : document.getElementById('cmd')
      if (!(input instanceof HTMLInputElement)) return
      input.focus()
      input.value = nextValue
      input.setSelectionRange(nextValue.length, nextValue.length)
      if (typeof handleComposerInputChange === 'function') {
        handleComposerInputChange(input)
      } else {
        input.dispatchEvent(new Event('input', { bubbles: true }))
      }
      if (typeof getAutocompleteMatches === 'function') {
        const matches = getAutocompleteMatches(nextValue, nextValue.length).slice(0, 12)
        if (matches.length && typeof acShow === 'function') acShow(matches)
        else if (typeof acHide === 'function') acHide()
      }
    },
    { nextValue: value, useMobile: mobile },
  )
}

/**
 * Open the history panel and wait for the async fetch to populate entries.
 */
export async function openHistory(page) {
  const panel = page.locator('#history-panel')
  const isOpen = await panel.evaluate((node) => node.classList.contains('open')).catch(() => false)
  if (!isOpen) {
    await page.locator('#hist-btn').click()
    await panel.waitFor({ state: 'visible' })
  }
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
  await page
    .locator('#history-list .history-entry')
    .first()
    .waitFor({ state: 'visible', timeout: 10_000 })
}

export async function waitForHistoryRuns(page, minRuns) {
  await page.waitForFunction(
    async (min) => {
      try {
        const resp = await apiFetch('/history')
        const data = await resp.json()
        return data.runs && data.runs.length >= min
      } catch {
        return false
      }
    },
    minRuns,
    { timeout: 20_000 },
  )

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
  const isOpen = await panel.evaluate((el) => el.classList.contains('open'))
  if (isOpen) {
    await page.locator('#history-close').click()
    await panel.waitFor({ state: 'hidden' })
  }
}

/**
 * Create a snapshot permalink from the active tab, handling the share-time
 * redaction confirmation modal before waiting for the POST /share response.
 */
export async function createShareSnapshot(page, { choice = 'redacted' } = {}) {
  const responsePromise = page.waitForResponse(
    (r) => r.url().includes('/share') && r.request().method() === 'POST',
  )

  await page.locator('[data-action="permalink"]').click()
  await page.locator('#share-redaction-overlay').waitFor({ state: 'visible' })

  if (choice === 'raw') {
    await page.locator('#share-redaction-raw').click()
  } else {
    await page.locator('#share-redaction-confirm').click()
  }

  return responsePromise
}
