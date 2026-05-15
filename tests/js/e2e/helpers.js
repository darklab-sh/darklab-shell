/**
 * Shared helpers for Playwright e2e tests.
 */

import { spawnSync } from 'child_process'
import { existsSync, readFileSync, readdirSync } from 'fs'
import { join } from 'path'

// Use the RFC 2544 benchmarking range so the test suite never accidentally
// collides with a real routable address when synthesizing client IPs.
const TEST_IP_SEED = (Date.now() ^ process.pid) >>> 0

let fixturePython = ''

function e2eDataDirForProject(testInfo) {
  const logDir = process.env.PW_E2E_SERVER_LOG_DIR || ''
  if (!logDir) throw new Error('PW_E2E_SERVER_LOG_DIR is not set')
  const slot = testInfo.project.name.match(/w\d+$/)?.[0]
  if (!slot) throw new Error(`Cannot determine e2e server slot from ${testInfo.project.name}`)
  const logName = readdirSync(logDir).find((name) => name.startsWith(`${slot}-`) && name.endsWith('.log'))
  if (!logName) throw new Error(`Cannot find e2e server log for ${slot}`)
  const log = readFileSync(join(logDir, logName), 'utf8')
  const dataDir = log.match(/^\[e2e-server\] data_dir=(.+)$/m)?.[1]
  if (!dataDir) throw new Error(`Cannot find data_dir in ${logName}`)
  return dataDir
}

function pythonForE2EFixture() {
  if (fixturePython) return fixturePython
  const candidates = [
    process.env.PYTHON,
    '.venv/bin/python3',
    'python3',
    'python',
  ].filter(Boolean)
  for (const candidate of candidates) {
    if (candidate.includes('/') && !existsSync(candidate)) continue
    const probe = spawnSync(candidate, ['-c', 'import sqlite3'], {
      cwd: process.cwd(),
      encoding: 'utf8',
    })
    if (probe.status === 0) {
      fixturePython = candidate
      return candidate
    }
  }
  throw new Error('Failed to find a Python executable with sqlite3 for the e2e run fixture')
}

export async function browserSessionId(page) {
  return page.evaluate(() => (
    typeof SESSION_ID === 'string' && SESSION_ID
      ? SESSION_ID
      : localStorage.getItem('session_id')
  ))
}

export function seedExternalHistoryRuns(testInfo, { sessionId, commands }) {
  const dataDir = e2eDataDirForProject(testInfo)
  const script = String.raw`
import json
from pathlib import Path
import sqlite3
import sys
import uuid

data_dir, session_id, commands_json = sys.argv[1:4]
commands = json.loads(commands_json)
created = []

def preview(command, lines):
    return json.dumps([
        {"text": "$ " + command, "cls": "prompt-echo", "line_index": 0},
        *[
            {"text": text, "cls": "", "line_index": index + 1}
            for index, text in enumerate(lines)
        ],
        {"text": "[process exited with code 0]", "cls": "exit-ok", "line_index": len(lines) + 1},
    ])

conn = sqlite3.connect(str(Path(data_dir) / "history.db"))
try:
    for index, command in enumerate(commands):
        run_id = "run_ext_e2e_" + uuid.uuid4().hex[:16]
        lines = [
            "external fixture output",
            "command: " + command,
        ]
        time_modifier = f"-{index} seconds"
        conn.execute(
            "INSERT INTO runs (id, session_id, run_kind, command, started, finished, exit_code, "
            "output_preview, preview_truncated, output_line_count, full_output_available, full_output_truncated) "
            "VALUES (?, ?, 'external', ?, datetime('now', ?), datetime('now', ?), 0, ?, 0, ?, 0, 0)",
            (run_id, session_id, command, time_modifier, time_modifier, preview(command, lines), len(lines) + 2),
        )
        created.append({"id": run_id, "command": command})
    conn.commit()
finally:
    conn.close()
print(json.dumps(created))
`
  const result = spawnSync(
    pythonForE2EFixture(),
    ['-c', script, dataDir, sessionId, JSON.stringify(commands)],
    {
      cwd: process.cwd(),
      encoding: 'utf8',
    },
  )
  if (result.status !== 0) {
    throw new Error(`Failed to seed external history runs: ${result.error?.message || result.stderr || result.stdout || `exit ${result.status}`}`)
  }
  return JSON.parse(result.stdout)
}

/**
 * Return a per-test-run deterministic test-network address for specs that
 * explicitly exercise per-IP behavior.
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
export async function ensurePromptReady(
  page,
  { cancelWelcome = false, timeout = 15_000, waitForAutocomplete = false } = {},
) {
  await page.waitForFunction(
    () => {
      const activeTab = typeof getActiveTab === 'function' ? getActiveTab() : null
      const input = document.getElementById('cmd')
      return !!activeTab && input instanceof HTMLInputElement
    },
    undefined,
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
      return !bootPending || (active && welcomeTabId !== activeTab)
    },
    undefined,
    { timeout: Math.min(timeout, 3_000) },
  ).catch(() => {})

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
    undefined,
    { timeout },
  )

  if (waitForAutocomplete) {
    await ensureAutocompleteReady(page, { timeout })
  }
}

export async function ensureAutocompleteReady(page, { timeout = 15_000 } = {}) {
  // Wait for the /autocomplete fetch to populate the context registry.
  // setComposerValueForTest calls getAutocompleteMatches synchronously, so if
  // the registry is still empty it returns no items and immediately hides the
  // dropdown — leaving expect.poll with nothing to poll.
  // Note: acSuggestions (flat suggestions) was removed; the registry is the
  // sole signal that the autocomplete fetch has completed.
  await page.waitForFunction(
    async () => {
      if (typeof acContextRegistry !== 'undefined' && Object.keys(acContextRegistry).length > 0) {
        return true
      }
      if (
        typeof apiFetch !== 'function' ||
        window.__e2eAutocompleteRecoveryPending
      ) {
        return false
      }
      window.__e2eAutocompleteRecoveryPending = true
      try {
        const resp = await apiFetch('/autocomplete')
        if (!resp.ok) return false
        const data = await resp.json()
        acSuggestions = data.suggestions || []
        acContextRegistry = data.context || {}
        acWordlists = Array.isArray(data.wordlists) ? data.wordlists : []
        acSpecialCommands = data.special_commands || []
        acBuiltinCommandRoots = data.builtin_command_roots || []
        if (typeof loadSessionVariables === 'function') loadSessionVariables().catch(() => {})
        if (typeof loadRecentValues === 'function') loadRecentValues().catch(() => {})
        if (typeof loadProjectAutocompleteTargets === 'function') {
          loadProjectAutocompleteTargets().catch(() => {})
        }
        if (typeof scheduleSearchDiscoverabilityRefresh === 'function') {
          scheduleSearchDiscoverabilityRefresh()
        } else if (typeof refreshSearchDiscoverabilityUi === 'function') {
          refreshSearchDiscoverabilityUi()
        }
        return Object.keys(acContextRegistry).length > 0
      } catch {
        return false
      } finally {
        window.__e2eAutocompleteRecoveryPending = false
      }
    },
    undefined,
    { timeout },
  )
}

/**
 * Type a command into the input bar and press Enter, then wait for the
 * tab to show an exit status (exit-ok or exit-fail class on the status pill).
 */
export async function runCommand(page, cmd, { timeout = 30_000 } = {}) {
  await ensurePromptReady(page, { timeout })
  const input = page.locator('#cmd')
  await input.waitFor({ state: 'visible', timeout })
  const beforeLineCount = await page.evaluate(() => {
    const tab = typeof getActiveTab === 'function' ? getActiveTab() : null
    return Array.isArray(tab?.rawLines) ? tab.rawLines.length : 0
  })
  await input.focus()
  await setComposerValueForTest(page, cmd, { waitForAutocomplete: false })
  await input.press('Enter')
  await page.waitForFunction(
    ({ expectedCmd, previousLineCount }) => {
      const tab = typeof getActiveTab === 'function' ? getActiveTab() : null
      if (!tab || tab.st === 'running') return false
      const rawLines = Array.isArray(tab.rawLines) ? tab.rawLines : []
      const output = document.querySelector('.tab-panel.active .output')
      const text = output ? output.textContent || '' : ''
      const sawNewLine = rawLines.length > previousLineCount
      const sawEcho = text.includes(`$${expectedCmd}`) || text.includes(`$ ${expectedCmd}`)
      if (tab.command === expectedCmd && sawNewLine) return true
      return sawNewLine && sawEcho
    },
    { expectedCmd: cmd, previousLineCount: beforeLineCount },
    { timeout },
  )
  await waitForActiveOutputSettled(page, { timeout })
}

/**
 * Wait for client-side output batching to finish for the active tab.
 *
 * The SSE exit event can update the HUD before large output batches have
 * finished rendering. Tests that assert scroll position after high-volume
 * commands should wait for this so scrollHeight stops moving underneath them.
 */
export async function waitForActiveOutputSettled(page, { timeout = 15_000 } = {}) {
  await page.waitForFunction(
    () => {
      const tabId = typeof activeTabId !== 'undefined' ? activeTabId : null
      if (!tabId) return false
      const pending =
        typeof _pendingOutputBatches !== 'undefined' ? _pendingOutputBatches.get(tabId) : null
      return !pending || (!pending.scheduled && pending.items.length === 0)
    },
    undefined,
    { timeout },
  )

  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(resolve)))
}

/**
 * Set a composer value through the app's shared input-change path so
 * autocomplete and shared prompt state update deterministically.
 */
export async function setComposerValueForTest(
  page,
  value,
  { mobile = false, waitForAutocomplete = false } = {},
) {
  if (waitForAutocomplete) {
    await ensureAutocompleteReady(page)
  }
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
  await page.waitForFunction(
    () => typeof refreshHistoryPanel === 'function'
      && (typeof showHistoryPanel === 'function' || typeof toggleHistoryPanelSurface === 'function'),
    undefined,
    { timeout: 15_000 },
  )
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      await page.evaluate(async () => {
        if (typeof showHistoryPanel === 'function') showHistoryPanel()
        else if (typeof toggleHistoryPanelSurface === 'function') toggleHistoryPanelSurface(true)
        await refreshHistoryPanel()
      })
      break
    } catch (error) {
      if (attempt === 2) throw error
      await page.waitForTimeout(250)
    }
  }
  await panel.waitFor({ state: 'visible' })
  // refreshHistoryPanel() fires an async /history fetch after the panel opens.
  // Wait for at least one child (either a .history-entry or the "No runs" div).
  await page.waitForFunction(
    () => {
      const panelEl = document.getElementById('history-panel')
      const list = document.getElementById('history-list')
      if (!panelEl || !panelEl.classList.contains('open') || !list) return false
      return list.children.length > 0
    },
    undefined,
    { timeout: 15_000 },
  )
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

export async function clickHistoryRunMenuAction(entry, action) {
  const menu = entry.locator('.history-action-menu-wrap')
  await menu.locator('[data-action="history-menu"]').click()
  await menu.locator(`[data-action="${action}"]`).click()
}

export async function waitForHistoryRuns(page, minRuns) {
  await page.waitForFunction(
    async (min) => {
      try {
        const resp = await apiFetch('/history')
        const data = await resp.json()
        const runs = data.runs || []
        window.__e2eLastHistoryRuns = runs
        return runs.length >= min
      } catch {
        return false
      }
    },
    minRuns,
    { timeout: 20_000 },
  )

  return page.evaluate(() => window.__e2eLastHistoryRuns || [])
}

/**
 * Close the history panel using the in-panel close button (avoids pointer-event
 * conflicts when the panel overlays the rail history button).
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

  // Prefer the HUD button on desktop; fall back to the per-tab footer button
  // on mobile, where the HUD is hidden and the tab panel owns the action row.
  const hudBtn = page.locator('.hud-actions [data-action="permalink"]')
  const hudVisible = await hudBtn.isVisible().catch(() => false)
  if (hudVisible) {
    await hudBtn.click()
  } else {
    await page.locator('.tab-panel.active [data-action="permalink"]').click()
  }
  await page.locator('#confirm-host').waitFor({ state: 'visible' })

  if (choice === 'raw') {
    await page.locator('#confirm-host [data-confirm-action-id="raw"]').click()
  } else {
    await page.locator('#confirm-host [data-confirm-action-id="redacted"]').click()
  }

  return responsePromise
}
