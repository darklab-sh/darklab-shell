// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Shared helpers for Playwright e2e tests.
 */

import { spawnSync } from 'child_process'
import { existsSync, readFileSync, readdirSync } from 'fs'
import { join } from 'path'
import { expect } from '@playwright/test'

// Use the RFC 2544 benchmarking range so the test suite never accidentally
// collides with a real routable address when synthesizing client IPs.
const TEST_IP_SEED = (Date.now() ^ process.pid) >>> 0

let fixturePython = ''

function e2eDataDirForProject(testInfo) {
  const logDir = process.env.PW_E2E_SERVER_LOG_DIR || ''
  if (!logDir) throw new Error('PW_E2E_SERVER_LOG_DIR is not set')
  const slot = testInfo.project.name.match(/w\d+$/)?.[0]
  const logNames = readdirSync(logDir).filter((name) => name.endsWith('.log'))
  const logName = slot
    ? logNames.find((name) => name.startsWith(`${slot}-`))
    : logNames.find((name) => name.startsWith(`${testInfo.project.name}-`))
      || (logNames.length === 1 ? logNames[0] : '')
  if (!logName) throw new Error(`Cannot find e2e server log for ${slot || testInfo.project.name}`)
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
  await waitForE2ETestHooks(page)
  return page.evaluate(() => {
    if (typeof window.getSessionId === 'function') return window.getSessionId()
    if (typeof window.SESSION_ID === 'string' && window.SESSION_ID) return window.SESSION_ID
    return localStorage.getItem('session_id')
  })
}

export function seedExternalHistoryRuns(testInfo, { sessionId, commands }) {
  if (!sessionId) {
    throw new Error('Cannot seed external history runs without a browser session id')
  }
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

export function seedProjectMonitoringFixture(testInfo, { sessionId, projectId }) {
  const dataDir = e2eDataDirForProject(testInfo)
  const script = String.raw`
import json
from pathlib import Path
import sqlite3
import sys
import uuid

data_dir, session_id, project_id = sys.argv[1:4]
suffix = uuid.uuid4().hex[:16]
baseline_run_id = "run_mon_base_" + suffix
current_run_id = "run_mon_current_" + suffix
deleted_run_id = "run_mon_deleted_" + suffix
changed_watcher_id = "wtr_mon_changed_" + suffix
deleted_watcher_id = "wtr_mon_deleted_" + suffix
changed_fire_id = "wtf_mon_changed_" + suffix
deleted_fire_id = "wtf_mon_deleted_" + suffix
now = "2026-06-15T12:00:00+00:00"

def output_preview(command, lines):
    return json.dumps([
        {"text": "$ " + command, "cls": "prompt-echo", "line_index": 0},
        *[
            {"text": text, "cls": "", "line_index": index + 1}
            for index, text in enumerate(lines)
        ],
        {"text": "[process exited with code 0]", "cls": "exit-ok", "line_index": len(lines) + 1},
    ])

def insert_run(conn, run_id, command, lines, started):
    conn.execute(
        "INSERT INTO runs (id, session_id, run_kind, command, started, finished, exit_code, "
        "output_preview, preview_truncated, output_line_count, full_output_available, full_output_truncated) "
        "VALUES (?, ?, 'external', ?, ?, ?, 0, ?, 0, ?, 0, 0)",
        (run_id, session_id, command, started, started, output_preview(command, lines), len(lines) + 2),
    )

def insert_schedule(conn, schedule_id, watcher_id, command, cadence, enabled):
    conn.execute(
        "INSERT INTO schedules "
        "(id, session_token, owner_kind, owner_id, kind, command_text, cron_expr, cadence_preset, timezone, "
        "enabled, next_run_at, label, created, updated) "
        "VALUES (?, ?, 'watcher', ?, 'command', ?, '0 * * * *', ?, 'UTC', ?, ?, ?, ?, ?)",
        (schedule_id, session_id, watcher_id, command, cadence, enabled, "2026-06-15T13:00:00+00:00", command, now, now),
    )

def insert_watcher(conn, watcher_id, schedule_id, label, command, baseline_run_id, last_run_id, summary, cadence):
    conn.execute(
        "INSERT INTO watchers "
        "(id, session_token, project_id, label, command_text, schedule_id, baseline_run_id, last_run_id, "
        "last_diff_summary_json, state, state_reason, options_json, policy_json, consecutive_changed, created, updated) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'changed', 'diff_detected', ?, ?, 1, ?, ?)",
        (
            watcher_id,
            session_id,
            project_id,
            label,
            command,
            schedule_id,
            baseline_run_id,
            last_run_id,
            json.dumps(summary),
            json.dumps({"suppress_removals": False, "notify_metadata_changes": False}),
            json.dumps({"ignore_line_patterns": [], "alert_after_repeated_changes": 1, "alert_signal_classes": []}),
            now,
            now,
        ),
    )

def insert_fire(conn, fire_id, watcher_id, run_id, baseline_run_id, summary, created):
    conn.execute(
        "INSERT INTO watcher_fires "
        "(id, watcher_id, baseline_run_id, run_id, diff_summary_json, diff_kind, truncated, "
        "notification_event_ids_json, state_at_fire, state_reason, fire_kind, ack_state, created) "
        "VALUES (?, ?, ?, ?, ?, 'signal', 0, '[]', 'changed', 'diff_detected', 'changed', 'new', ?)",
        (fire_id, watcher_id, baseline_run_id, run_id, json.dumps(summary), created),
    )

changed_summary = {
    "classifier": "ports",
    "added_port_count": 1,
    "added_ports": [{"key": "443/tcp", "state": "open", "service": "https"}],
}
deleted_summary = {
    "classifier": "ports",
    "changed_port_count": 1,
    "changed_ports": [{
        "before": {"key": "443/tcp", "state": "closed", "service": "https"},
        "after": {"key": "443/tcp", "state": "open", "service": "https"},
    }],
}
conn = sqlite3.connect(str(Path(data_dir) / "history.db"))
try:
    insert_run(conn, baseline_run_id, "nmap -sV darklab.sh --baseline", ["80/tcp open http"], "2026-06-15T11:00:00+00:00")
    insert_run(conn, current_run_id, "nmap -sV darklab.sh", ["80/tcp open http", "443/tcp open https"], now)
    insert_schedule(conn, "sch_" + changed_watcher_id, changed_watcher_id, "nmap -sV darklab.sh", "hourly", 1)
    insert_schedule(conn, "sch_" + deleted_watcher_id, deleted_watcher_id, "nmap -sV deleted.darklab.sh", "daily", 1)
    insert_watcher(
        conn,
        changed_watcher_id,
        "sch_" + changed_watcher_id,
        "Ports Browser Watch",
        "nmap -sV darklab.sh",
        baseline_run_id,
        current_run_id,
        changed_summary,
        "hourly",
    )
    insert_watcher(
        conn,
        deleted_watcher_id,
        "sch_" + deleted_watcher_id,
        "Deleted Current Watch",
        "nmap -sV deleted.darklab.sh",
        baseline_run_id,
        deleted_run_id,
        deleted_summary,
        "daily",
    )
    insert_fire(conn, changed_fire_id, changed_watcher_id, current_run_id, baseline_run_id, changed_summary, now)
    insert_fire(conn, deleted_fire_id, deleted_watcher_id, deleted_run_id, baseline_run_id, deleted_summary, "2026-06-15T11:55:00+00:00")
    conn.commit()
finally:
    conn.close()
print(json.dumps({
    "baselineRunId": baseline_run_id,
    "currentRunId": current_run_id,
    "deletedRunId": deleted_run_id,
    "changedWatcherId": changed_watcher_id,
    "deletedWatcherId": deleted_watcher_id,
    "changedFireId": changed_fire_id,
    "deletedFireId": deleted_fire_id,
}))
`
  const result = spawnSync(
    pythonForE2EFixture(),
    ['-c', script, dataDir, sessionId, projectId],
    {
      cwd: process.cwd(),
      encoding: 'utf8',
    },
  )
  if (result.status !== 0) {
    throw new Error(`Failed to seed project monitoring fixture: ${result.error?.message || result.stderr || result.stdout || `exit ${result.status}`}`)
  }
  return JSON.parse(result.stdout)
}

export function seedProjectOverviewFixture(testInfo, { sessionId, projectId, targetId, targetValue }) {
  const dataDir = e2eDataDirForProject(testInfo)
  const script = String.raw`
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys
import uuid
sys.path.insert(0, str(Path.cwd() / "app"))
from services.atlas.materializer import materialize_run_entities

data_dir, session_id, project_id, target_id, target_value = sys.argv[1:6]
now = datetime.now(timezone.utc).replace(microsecond=0)
expires_at = now + timedelta(days=21)
conn = sqlite3.connect(str(Path(data_dir) / "history.db"))
conn.row_factory = sqlite3.Row
try:
    run_id = "run_e2e_overview_ports_" + uuid.uuid4().hex[:16]
    conn.execute(
        "INSERT INTO runs (id, session_id, run_kind, command, started, finished, exit_code, "
        "output_preview, preview_truncated, output_line_count, full_output_available, full_output_truncated) "
        "VALUES (?, ?, 'external', ?, ?, ?, 0, ?, 0, 3, 0, 0)",
        (
            run_id,
            session_id,
            "nmap -sV " + target_value,
            now.isoformat(),
            now.isoformat(),
            json.dumps([
                {"text": "$ nmap -sV " + target_value, "cls": "prompt-echo", "line_index": 0},
                {"text": "8443/tcp open https-alt Example edge", "cls": "", "line_index": 1},
                {"text": "[process exited with code 0]", "cls": "exit-ok", "line_index": 2},
            ]),
        ),
    )
    materialized = materialize_run_entities(
        conn,
        session_id,
        run_id,
        [{
            "text": "8443/tcp open https-alt Example edge on " + target_value,
            "entities": [
                {"type": "domain", "value": target_value, "canonical_value": target_value},
                {
                    "type": "port",
                    "value": target_value + ":8443/tcp",
                    "canonical_value": target_value + ":8443/tcp",
                    "attributes": {"service": "https-alt", "version": "Example edge"},
                },
            ],
        }],
        seen_at=now.isoformat(),
        command="nmap -sV " + target_value,
    )
    port_ids = [item["id"] for item in materialized if item.get("type") == "port"]
    link_rows = [
        ("run", run_id),
        *[("atlas_entity", port_id) for port_id in port_ids],
    ]
    for entity_type, entity_id in link_rows:
        conn.execute(
            "INSERT OR IGNORE INTO project_links (id, project_id, entity_type, entity_id, source, created) "
            "VALUES (?, ?, ?, ?, 'e2e', ?)",
            (
                "pl_e2e_overview_" + entity_type + "_" + entity_id,
                project_id,
                entity_type,
                entity_id,
                now.isoformat(),
            ),
        )
    conn.execute(
        "INSERT OR REPLACE INTO entity_intel_snapshots "
        "(id, session_id, entity_id, provider, status, summary, data_json, fetched_at, expires_at) "
        "VALUES (?, ?, ?, 'tls_certificate', 'ok', ?, ?, ?, ?)",
        (
            "snap_e2e_overview_" + target_id,
            session_id,
            target_id,
            "TLS certificate summary",
            json.dumps({
                "providers": {
                    "tls_certificate": {
                        "ports": [443],
                        "services": ["https"],
                        "certificate": {"not_after": expires_at.isoformat()},
                    },
                },
                "summary": {"has_intel": True, "providers_with_data": ["tls_certificate"]},
            }),
            now.isoformat(),
            expires_at.isoformat(),
        ),
    )
    conn.execute(
        "INSERT OR REPLACE INTO findings "
        "(id, session_id, entity_id, target_id, subject_key, signature_hash, severity, status, title, created, last_seen_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'high', 'new', ?, ?, ?)",
        (
            "finding_e2e_overview_" + target_id,
            session_id,
            target_id,
            target_id,
            "overview:" + target_value,
            "sig_e2e_overview_" + target_id,
            "Real Overview filtered finding",
            now.isoformat(),
            now.isoformat(),
        ),
    )
    conn.commit()
finally:
    conn.close()
print(json.dumps({"targetId": target_id, "runId": run_id, "portIds": port_ids}))
`
  const result = spawnSync(
    pythonForE2EFixture(),
    ['-c', script, dataDir, sessionId, projectId, targetId, targetValue],
    {
      cwd: process.cwd(),
      encoding: 'utf8',
    },
  )
  if (result.status !== 0) {
    throw new Error(`Failed to seed project overview fixture: ${result.error?.message || result.stderr || result.stdout || `exit ${result.status}`}`)
  }
  return JSON.parse(result.stdout)
}

export function seedProjectActivityFixture(testInfo, { sessionId, projectId }) {
  const dataDir = e2eDataDirForProject(testInfo)
  const script = String.raw`
import json
import hashlib
from pathlib import Path
import sqlite3
import sys
import uuid

data_dir, session_id, project_id = sys.argv[1:4]
event_id = "aud_capture_" + uuid.uuid4().hex[:16]
session_hash = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
details = {"source": "capture", "review_state": "confirmed", "target": "capture.darklab.sh"}

conn = sqlite3.connect(str(Path(data_dir) / "history.db"))
try:
    conn.execute(
        "INSERT INTO audit_events "
        "(id, owner_session_hash, actor_session_hash, actor_session_label, actor_role, actor_display_name, "
        "event_type, target_type, target_id, project_id, correlation_id, details_version, created, details) "
        "VALUES (?, ?, ?, 'capture session', 'owner', 'Capture Reviewer', "
        "'finding.review_change', 'finding', ?, ?, ?, 1, '2026-06-06T12:00:00+00:00', ?)",
        (
            event_id,
            session_hash,
            session_hash,
            "finding_capture_" + uuid.uuid4().hex[:8],
            project_id,
            "corr_capture_" + uuid.uuid4().hex[:12],
            json.dumps(details),
        ),
    )
    conn.commit()
finally:
    conn.close()
print(json.dumps({"eventId": event_id}))
`
  const result = spawnSync(
    pythonForE2EFixture(),
    ['-c', script, dataDir, sessionId, projectId],
    {
      cwd: process.cwd(),
      encoding: 'utf8',
    },
  )
  if (result.status !== 0) {
    throw new Error(`Failed to seed project activity fixture: ${result.error?.message || result.stderr || result.stdout || `exit ${result.status}`}`)
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

async function waitForE2ETestHooks(page, { timeout = 15_000 } = {}) {
  await page.waitForFunction(
    async () => {
      if (navigator.webdriver !== true) return true
      if (typeof window.apiFetch === 'function' && typeof window.clearTab === 'function') {
        return true
      }
      const ready = window.__darklabE2ETestHooksReady
      if (ready && typeof ready.then === 'function') {
        await ready.catch(() => false)
      }
      return typeof window.apiFetch === 'function' && typeof window.clearTab === 'function'
    },
    undefined,
    { timeout },
  )
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
  await waitForE2ETestHooks(page, { timeout })

  await page.waitForFunction(
    () => {
      const activeTab = typeof window.APP_STATE_API?.getActiveTab === 'function'
        ? window.APP_STATE_API.getActiveTab()
        : null
      const input = document.getElementById('cmd')
      return !!activeTab && input instanceof HTMLInputElement
    },
    undefined,
    { timeout },
  )

  await page.evaluate(
    ({ cancel }) => {
      const tabId = typeof window.APP_STATE_API?.getActiveTabId === 'function'
        ? window.APP_STATE_API.getActiveTabId()
        : null
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
      const activeTab = typeof window.APP_STATE_API?.getActiveTabId === 'function'
        ? window.APP_STATE_API.getActiveTabId()
        : null
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

  await page.waitForFunction(
    () => (
      typeof window.DarklabRunner?.submitVisibleComposerCommand === 'function' &&
      typeof window.DarklabRunner?.hasRunnerHandler === 'function' &&
      window.DarklabRunner.hasRunnerHandler('submitVisibleComposerCommand')
    ),
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
    const tab = typeof window.APP_STATE_API?.getActiveTab === 'function'
      ? window.APP_STATE_API.getActiveTab()
      : null
    return Array.isArray(tab?.rawLines) ? tab.rawLines.length : 0
  })
  await input.focus()
  await setComposerValueForTest(page, cmd, { waitForAutocomplete: false })
  await input.press('Enter')
  await page.waitForFunction(
    ({ expectedCmd, previousLineCount }) => {
      const tab = typeof window.APP_STATE_API?.getActiveTab === 'function'
        ? window.APP_STATE_API.getActiveTab()
        : null
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
      const tabId = typeof window.APP_STATE_API?.getActiveTabId === 'function'
        ? window.APP_STATE_API.getActiveTabId()
        : null
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
        const rawMatches = getAutocompleteMatches(nextValue, nextValue.length)
        const matches = typeof limitAutocompleteMatchesForDisplay === 'function'
          ? limitAutocompleteMatchesForDisplay(rawMatches, 12)
          : rawMatches.slice(0, 12)
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

export async function waitForHistoryCommands(page, commands) {
  await page.waitForFunction(
    async (expectedCommands) => {
      try {
        const resp = await apiFetch('/history?page_size=100&type=runs')
        const data = await resp.json()
        const runs = data.runs || []
        window.__e2eLastHistoryRuns = runs
        return expectedCommands.every((command) => (
          runs.some((run) => run.command === command)
        ))
      } catch {
        return false
      }
    },
    commands,
    { timeout: 20_000 },
  )

  return page.evaluate(() => window.__e2eLastHistoryRuns || [])
}

export async function openRailAction(page, action) {
  const primary = page.locator(`.rail-nav > [data-action="${action}"]`)
  if (await primary.isVisible().catch(() => false)) {
    await primary.click()
    return
  }
  const more = page.locator('#rail-more-btn')
  await more.click()
  await expect(page.locator('#rail-more-menu')).toBeVisible()
  await page.locator(`#rail-more-menu [data-action="${action}"]`).click()
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
