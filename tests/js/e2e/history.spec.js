// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { test, expect } from '@playwright/test'
import { spawnSync } from 'child_process'
import { existsSync, readFileSync, readdirSync } from 'fs'
import { join } from 'path'
import {
  runCommand,
  openHistory,
  openHistoryWithEntries,
  waitForHistoryRuns,
  waitForHistoryCommands,
  closeHistory,
  createShareSnapshot,
  clickHistoryRunMenuAction,
  ensurePromptReady,
  browserSessionId,
  seedExternalHistoryRuns,
} from './helpers.js'

// Use fake shell commands — they bypass the allowlist and complete instantly.
const CMD_A = 'hostname'
const CMD_B = 'date'

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

let fixturePython = ''

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
  throw new Error('Failed to find a Python executable with sqlite3 for the e2e comparison fixture')
}

function seedHistoryCleanupFixture(testInfo, { sessionId }) {
  const dataDir = e2eDataDirForProject(testInfo)
  const script = String.raw`
import json
from pathlib import Path
import sqlite3
import sys
import uuid
sys.path.insert(0, str(Path.cwd() / "app"))
from services.atlas.materializer import materialize_run_entities
from services.projects.findings import record_run_findings

data_dir, session_id = sys.argv[1:3]
run_id = "run_cleanup_e2e_" + uuid.uuid4().hex[:16]
other_run_id = "run_cleanup_other_e2e_" + uuid.uuid4().hex[:16]
command = "nmap cleanup.playwright.example"
disposable_value = "disposable.cleanup.playwright.example"
kept_value = "CVE-2026-4242"
not_eligible_value = "192.0.2.42"
conn = sqlite3.connect(str(Path(data_dir) / "history.db"))
conn.row_factory = sqlite3.Row
try:
    conn.execute(
        "INSERT INTO runs (id, session_id, run_kind, command, started, finished, exit_code, "
        "output_preview, preview_truncated, output_line_count, full_output_available, full_output_truncated) "
        "VALUES (?, ?, 'external', ?, datetime('now'), datetime('now'), 0, ?, 0, 2, 0, 0)",
        (run_id, session_id, command, json.dumps([command, "cleanup fixture output"])),
    )
    conn.execute(
        "INSERT INTO runs (id, session_id, run_kind, command, started, finished, exit_code, "
        "output_preview, preview_truncated, output_line_count, full_output_available, full_output_truncated) "
        "VALUES (?, ?, 'external', ?, datetime('now', '-1 minute'), datetime('now', '-1 minute'), 0, ?, 0, 1, 0, 0)",
        (other_run_id, session_id, "nmap shared.cleanup.playwright.example", json.dumps([not_eligible_value])),
    )
    materialized = materialize_run_entities(
        conn,
        session_id,
        run_id,
        [{
            "text": " ".join((disposable_value, kept_value, not_eligible_value)),
            "entities": [
                {"type": "domain", "value": disposable_value, "canonical_value": disposable_value},
                {"type": "cve", "value": kept_value, "canonical_value": kept_value},
                {"type": "ip", "value": not_eligible_value, "canonical_value": not_eligible_value},
            ],
        }],
        seen_at="2026-07-10T12:00:00+00:00",
        command=command,
    )
    materialize_run_entities(
        conn,
        session_id,
        other_run_id,
        [{
            "text": not_eligible_value,
            "entities": [{"type": "ip", "value": not_eligible_value, "canonical_value": not_eligible_value}],
        }],
        seen_at="2026-07-10T12:01:00+00:00",
        command="nmap shared.cleanup.playwright.example",
    )
    entity_ids = {item["type"]: item["id"] for item in materialized}
    conn.execute(
        "INSERT INTO entity_labels (id, session_id, entity_type, entity_id, label, source, created) "
        "VALUES (?, ?, 'atlas_entity', ?, 'keep-e2e', 'manual', datetime('now'))",
        ("lbl_cleanup_e2e_" + uuid.uuid4().hex[:16], session_id, entity_ids["cve"]),
    )
    record_run_findings(conn, session_id, run_id, [{
        "text": "443/tcp open https on " + disposable_value,
        "signals": ["findings"],
        "line_index": 0,
        "entities": [{"type": "domain", "value": disposable_value, "canonical_value": disposable_value}],
    }])
    conn.commit()
finally:
    conn.close()
print(json.dumps({
    "runId": run_id,
    "command": command,
    "disposableValue": disposable_value,
    "keptValue": kept_value,
    "notEligibleValue": not_eligible_value,
}))
`
  const result = spawnSync(pythonForE2EFixture(), ['-c', script, dataDir, sessionId], {
    cwd: process.cwd(),
    encoding: 'utf8',
  })
  if (result.status !== 0) {
    throw new Error(`Failed to seed History cleanup fixture: ${result.error?.message || result.stderr || result.stdout || `exit ${result.status}`}`)
  }
  return JSON.parse(result.stdout)
}

async function createActiveProject(page, name) {
  return page.evaluate(async ({ projectName }) => {
    const createdResp = await apiFetch('/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: projectName }),
    })
    if (!createdResp.ok) throw new Error(`Failed to create project: ${createdResp.status}`)
    const created = await createdResp.json()
    const project = created.project
    const activeResp = await apiFetch('/projects/active', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: project.id }),
    })
    if (!activeResp.ok) throw new Error(`Failed to set active project: ${activeResp.status}`)
    if (typeof refreshActiveProjectContext === 'function') {
      await refreshActiveProjectContext()
    }
    return project
  }, { projectName: name })
}

async function projectRunLinkIds(page, projectId) {
  return page.evaluate(async ({ id }) => {
    const resp = await apiFetch(`/projects/${encodeURIComponent(id)}/links`, { cache: 'no-store' })
    if (!resp.ok) throw new Error(`Failed to load project links: ${resp.status}`)
    const data = await resp.json()
    return (Array.isArray(data.links) ? data.links : [])
      .filter(link => link && link.entity_type === 'run')
      .map(link => String(link.entity_id || ''))
      .sort()
  }, { id: projectId })
}

async function activateHistoryBulkMenuItem(page, action) {
  const item = page.locator(`#history-bulk-toolbar [data-action="${action}"]`)
  await expect(item).toBeVisible()
  await item.dispatchEvent('click')
}

async function ensureHistoryBulkSelectMode(page) {
  await page.evaluate(async () => {
    if (typeof showHistoryPanel === 'function') showHistoryPanel()
    if (typeof refreshHistoryPanel === 'function') await refreshHistoryPanel()
  })
  await expect(page.locator('#history-panel')).toHaveClass(/\bopen\b/)
  await page.locator('#history-list .history-entry').first().waitFor({ state: 'visible' })
  const toggle = page.locator('#history-bulk-toolbar .history-bulk-toggle input')
  if (!(await toggle.isChecked())) {
    await toggle.check()
  }
}

async function selectVisibleHistoryRuns(page, commands) {
  for (const command of commands) {
    const checkbox = page
      .locator('#history-list .history-entry')
      .filter({ hasText: command })
      .first()
      .locator('[data-action="select-run"]')
    await expect(checkbox).toBeEnabled()
    await checkbox.check()
    await expect(checkbox).toBeChecked()
  }
}

test.describe('history drawer', () => {
  test.describe.configure({ timeout: 60_000 })

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    // Clear any localStorage state left over from a previous test run and reload
    await page.evaluate(() => localStorage.clear())
    await page.reload()
    await page.locator('#cmd').waitFor()
  })

  test('clicking a history entry opens run details and keeps the drawer open', async ({
    page,
  }) => {
    await runCommand(page, CMD_A)

    // Navigate away by opening a new tab (clears the input)
    await page.locator('#new-tab-btn').click()
    await expect(page.locator('#cmd')).toHaveValue('')
    const tabCountBefore = await page.locator('.tab').count()

    await openHistoryWithEntries(page)
    await page.locator('.history-entry').first().click()

    await expect(page.locator('#history-run-overlay')).toHaveClass(/open/)
    await expect(page.locator('#history-run-subtitle')).toContainText(CMD_A)
    await expect(page.locator('#history-panel')).toHaveClass(/open/)
    await expect(page.locator('#cmd')).toHaveValue('')
    await expect(page.locator('.tab')).toHaveCount(tabCountBefore)

    await page.locator('[data-history-run-tab="findings"]').click()
    await expect(page.locator('#history-run-body')).toContainText(/No structured findings|Loading findings/)
  })

  test('Run Details AI workflow renders summary and validated next commands', async ({ page }) => {
    const runId = 'run-ai-e2e'
    const command = 'nmap -sV darklab.sh'
    const historyRun = {
      id: runId,
      type: 'run',
      run_kind: 'external',
      command,
      started: '2026-05-25T00:00:00Z',
      finished: '2026-05-25T00:00:02Z',
      exit_code: 0,
      output_line_count: 3,
      full_output_available: true,
      full_output_truncated: false,
    }
    let summaryPosts = 0
    let nextCommandPosts = 0

    await page.route(/https?:\/\/[^/]+\/(?:atlas|entities|history|projects|runs)(?:\/|\?|$)/, async (route) => {
      const request = route.request()
      const url = new URL(request.url())
      const json = async (body, status = 200) => {
        await route.fulfill({
          status,
          contentType: 'application/json',
          body: JSON.stringify(body),
        })
      }

      if (url.pathname === '/history' && request.method() === 'GET') {
        await json({
          items: [historyRun],
          runs: [historyRun],
          roots: ['nmap'],
          page: 1,
          page_size: 50,
          page_count: 1,
          total_count: 1,
          has_prev: false,
          has_next: false,
        })
        return
      }
      if (url.pathname === `/history/${runId}` && request.method() === 'GET') {
        await json({
          ...historyRun,
          output_entries: [
            { text: 'Nmap scan report for darklab.sh', cls: '' },
            { text: '443/tcp open https', cls: '' },
            { text: 'Nmap done: 1 IP address (1 host up) scanned in 2.00 seconds', cls: '' },
          ],
          output_summary: {
            kinds: { output: 3 },
            signals: { findings: 1 },
            signal_toc: [
              { line_number: 2, signal: 'findings', text: '443/tcp open https' },
            ],
          },
        })
        return
      }
      if (url.pathname === '/projects/active') {
        await json({ project: null })
        return
      }
      if (url.pathname === `/entities/run/${runId}/findings`) {
        await json({
          findings: [],
          limit: 50,
          offset: 0,
          total: 0,
          has_more: false,
          occurrence_total: 0,
        })
        return
      }
      if (url.pathname === '/atlas') {
        await json({ total: 1, counts: { ip: 1 } })
        return
      }
      if (url.pathname === '/atlas/entities') {
        await json({
          entities: [
            {
              id: 'ent-run-details-ip-e2e',
              type: 'ip',
              canonical_value: '203.0.113.44',
              occurrence_count: 40,
              run_count: 5,
              project_link_count: 1,
            },
          ],
          limit: 50,
          offset: 0,
          total: 1,
          has_more: false,
        })
        return
      }
      if (url.pathname === `/runs/${runId}/ai-assists` && request.method() === 'GET') {
        await json({ assists: [] })
        return
      }
      if (url.pathname === `/runs/${runId}/ai-summary` && request.method() === 'POST') {
        summaryPosts += 1
        await json({
          assist: {
            id: 'ai-summary-e2e',
            run_id: runId,
            variant: 'summary',
            status: 'completed',
            payload: {
              summary: 'HTTPS is open on darklab.sh.',
              key_findings: ['443/tcp open https'],
              next_steps_hint: 'Inspect TLS details.',
            },
          },
        })
        return
      }
      if (url.pathname === `/runs/${runId}/ai-next-commands` && request.method() === 'POST') {
        nextCommandPosts += 1
        await json({
          assist: {
            id: 'ai-next-e2e',
            run_id: runId,
            variant: 'next_commands',
            status: 'completed',
            payload: {
              suggestions: [
                {
                  command: 'sslscan darklab.sh',
                  reason: 'Inspect certificate and TLS settings.',
                  risk_label: 'low',
                  target: 'darklab.sh',
                  target_allowed: true,
                  validation_result: 'accepted',
                  rejection_reason: '',
                },
                {
                  command: 'nmap -sV --script=http-vuln -p 318 darklab.sh',
                  reason: 'Model draft used an absent port.',
                  risk_label: 'medium',
                  target: 'darklab.sh',
                  target_allowed: true,
                  validation_result: 'rejected',
                  rejection_reason: 'port_absent',
                },
              ],
            },
          },
        })
        return
      }
      await json({ error: 'not found' }, 404)
    })

    const aiEnabledConfig = await page.evaluate(() => ({
      ...window.APP_CONFIG,
      ai_enabled: true,
      ai_feature_summary: true,
      ai_feature_next_commands: true,
      ai_feature_run_suggestions: true,
    }))
    await page.route(/https?:\/\/[^/]+\/config(?:\?|$)/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(aiEnabledConfig),
      })
    })
    await page.reload()
    await page.locator('#cmd').waitFor()
    await page.waitForFunction(() => (
      window.APP_CONFIG
      && window.APP_CONFIG.ai_enabled === true
      && window.APP_CONFIG.ai_feature_summary === true
      && window.APP_CONFIG.ai_feature_next_commands === true
    ))

    await page.evaluate(() => {
      window.__copiedAiSuggestion = ''
      window.__ranAiSuggestions = []
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: {
          writeText: async (text) => {
            window.__copiedAiSuggestion = String(text || '')
          },
        },
      })
      window.DarklabRunner.setRunnerHandlers({
        submitComposerCommand: (cmd, options) => {
        window.__ranAiSuggestions.push({ cmd, options })
        return 'settle'
        },
      })
    })

    await openHistory(page)
    await page.locator('.history-entry').first().click()

    const overlay = page.locator('#history-run-overlay')
    const body = page.locator('#history-run-body')
    await expect(overlay).toHaveClass(/\bopen\b/)
    await expect(page.locator('#history-run-subtitle')).toContainText(command)
    await expect(body).toContainText('No AI summary has been generated for this run.')
    await expect(body).toContainText('No AI next-command suggestions have been generated for this run.')

    await page.locator('[data-history-run-tab="entities"]').click()
    const entityRow = page.locator('[data-history-run-entity-id="ent-run-details-ip-e2e"]')
    await expect(entityRow).toBeVisible()
    await expect(entityRow.locator('.atlas-entity-value')).toHaveText('203.0.113.44')
    await expect(entityRow.locator('.atlas-entity-badges')).toContainText('1 projects')
    const entityLayout = await entityRow.evaluate((row) => {
      const main = row.querySelector('.atlas-entity-main')
      const badges = row.querySelector('.atlas-entity-badges')
      const rowRect = row.getBoundingClientRect()
      const mainRect = main?.getBoundingClientRect()
      const badgeRect = badges?.getBoundingClientRect()
      const styles = getComputedStyle(row)
      return {
        display: styles.display,
        alignItems: styles.alignItems,
        mainRight: mainRect?.right || 0,
        badgeLeft: badgeRect?.left || 0,
        badgeTop: badgeRect?.top || 0,
        rowBottom: rowRect.bottom,
      }
    })
    expect(entityLayout.display).toBe('flex')
    expect(entityLayout.alignItems).toBe('center')
    expect(entityLayout.badgeLeft).toBeGreaterThan(entityLayout.mainRight - 1)
    expect(entityLayout.badgeTop).toBeLessThan(entityLayout.rowBottom)
    await expect.poll(() => page.evaluate(() => (
      [...document.styleSheets].some(sheet => String(sheet.href || '').includes('/static/css/features/atlas.css'))
    ))).toBe(false)
    await page.locator('[data-history-run-tab="summary"]').click()

    await page.locator('[data-history-run-action="ai-summary"]').click()
    await expect(body).toContainText('HTTPS is open on darklab.sh.')
    await expect(body).toContainText('443/tcp open https')
    await expect(body).toContainText('Inspect TLS details.')

    await page.locator('[data-history-run-action="ai-next-commands"]').click()
    await expect(body).toContainText('sslscan darklab.sh')
    await expect(body).toContainText('Inspect certificate and TLS settings.')
    await expect(body).toContainText('nmap -sV --script=http-vuln -p 318 darklab.sh')
    await expect(body).toContainText('Rejected: port_absent')
    await expect(page.locator('[data-history-run-copy-suggestion]')).toHaveCount(1)
    await expect(page.locator('[data-history-run-run-suggestion]')).toHaveCount(1)

    await page.locator('[data-history-run-copy-suggestion]').click()
    await expect.poll(() => page.evaluate(() => window.__copiedAiSuggestion)).toBe('sslscan darklab.sh')

    await page.locator('[data-history-run-run-suggestion]').click()
    await expect.poll(() => page.evaluate(() => window.__ranAiSuggestions)).toEqual([
      {
        cmd: 'sslscan darklab.sh',
        options: { dismissKeyboard: true, focusAfterSubmit: true },
      },
    ])
    await expect(overlay).not.toHaveClass(/\bopen\b/)
    expect(summaryPosts).toBe(1)
    expect(nextCommandPosts).toBe(1)
  })

  test('the history restore button loads output into a tab without touching the composer', async ({
    page,
  }) => {
    await runCommand(page, CMD_A)

    await page.locator('#new-tab-btn').click()
    await expect(page.locator('#cmd')).toHaveValue('')

    await openHistoryWithEntries(page)
    await page.locator('.history-entry').first().locator('[data-action="restore"]').click()

    await expect(page.locator('#cmd')).toHaveValue('')
    await expect(page.locator('.tab-panel.active .output')).toContainText(CMD_A)
  })

  test('the history restore button switches to an existing tab instead of duplicating it', async ({
    page,
  }) => {
    await runCommand(page, CMD_A)
    const initialTabCount = await page.locator('.tab').count()

    await openHistoryWithEntries(page)
    await page.locator('.history-entry').first().locator('[data-action="restore"]').click()

    await expect(page.locator('.tab')).toHaveCount(initialTabCount)
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('deleting a starred entry removes it from the chip bar', async ({ page }) => {
    await runCommand(page, CMD_A)

    // Star the run from the history panel
    await openHistoryWithEntries(page)
    await page.locator('.history-entry').first().locator('[data-action="star"]').click()

    // Confirm the chip is now starred
    await closeHistory(page)
    await expect(page.locator('.hist-chip.starred')).toHaveCount(1)

    // Delete the run from the history panel
    await openHistory(page)
    await page.locator('.history-entry').first().locator('[data-action="delete"]').click()
    // Confirm deletion in the modal
    await page.locator('#confirm-host [data-confirm-action-id="one"]').click()

    // The starred chip should be gone
    await expect(page.locator('.hist-chip.starred')).toHaveCount(0)
    await expect(page.locator('.hist-chip')).toHaveCount(0)
  })

  test('run cleanup confirmation uses live preview defaults samples and selected flags', async ({ page }, testInfo) => {
    const sessionId = await browserSessionId(page)
    const fixture = seedHistoryCleanupFixture(testInfo, { sessionId })
    await waitForHistoryCommands(page, [fixture.command])
    await openHistory(page)
    const runRow = page.locator('.history-entry').filter({ hasText: fixture.command }).first()
    await expect(runRow).toBeVisible()

    await runRow.locator('[data-action="delete"]').click()
    const confirmHost = page.locator('#confirm-host')
    await expect(confirmHost).toBeVisible()
    const disposableCheckbox = confirmHost.locator('[data-history-atlas-cleanup]')
    const curatedCheckbox = confirmHost.locator('[data-history-atlas-cleanup-curated]')
    await expect(disposableCheckbox).toBeVisible()
    await expect(curatedCheckbox).toBeVisible()
    await expect(disposableCheckbox).not.toBeChecked()
    await expect(curatedCheckbox).not.toBeChecked()
    await expect(confirmHost).toContainText('only sourced by this run')
    await expect(confirmHost).toContainText('kept by default')
    await expect(confirmHost).toContainText('not eligible for this cleanup')
    await expect(confirmHost).toContainText('labeled')
    await expect(confirmHost).toContainText('seen elsewhere')

    const sampleToggle = confirmHost.locator('.cleanup-sample-toggle')
    const samplePanel = confirmHost.locator('.cleanup-sample-panel')
    await expect(sampleToggle).toHaveAttribute('aria-expanded', 'false')
    await expect(samplePanel).toBeHidden()
    await sampleToggle.click()
    await expect(sampleToggle).toHaveAttribute('aria-expanded', 'true')
    await expect(samplePanel).toBeVisible()
    await expect(samplePanel).toContainText('Kept by default entities')
    await expect(samplePanel).toContainText('Not eligible entities')
    await expect(samplePanel).toContainText(fixture.keptValue)
    await expect(samplePanel).toContainText(fixture.notEligibleValue)

    await disposableCheckbox.check()
    await expect(curatedCheckbox).not.toBeChecked()
    const deleteResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'DELETE' && url.pathname === `/history/${fixture.runId}`
    })
    await confirmHost.locator('[data-confirm-action-id="one"]').click()
    const deleteResponse = await deleteResponsePromise
    expect(deleteResponse.ok()).toBe(true)
    const deleteUrl = new URL(deleteResponse.url())
    expect(deleteUrl.searchParams.get('prune_atlas')).toBe('1')
    expect(deleteUrl.searchParams.has('prune_curated_atlas')).toBe(false)
    expect((await deleteResponse.json()).atlas_cleanup).toEqual({ entities: 1, findings: 1 })
    await expect(confirmHost).toBeHidden()
    await expect(runRow).toHaveCount(0)

    const atlasState = await page.evaluate(async () => {
      const [domainsResp, cvesResp, ipsResp, summaryResp] = await Promise.all([
        apiFetch('/atlas/entities?type=domain&orphan_filter=all', { cache: 'no-store' }),
        apiFetch('/atlas/entities?type=cve&orphan_filter=all', { cache: 'no-store' }),
        apiFetch('/atlas/entities?type=ip&orphan_filter=all', { cache: 'no-store' }),
        apiFetch('/atlas?orphan_filter=all', { cache: 'no-store' }),
      ])
      const [domains, cves, ips, summary] = await Promise.all([
        domainsResp.json(), cvesResp.json(), ipsResp.json(), summaryResp.json(),
      ])
      return {
        domains: domains.total,
        cves: cves.total,
        ips: ips.total,
        findings: summary.findings,
      }
    })
    expect(atlasState).toEqual({ domains: 0, cves: 1, ips: 1, findings: 0 })
  })

  test('toggling the history star keeps the desktop drawer open', async ({ page }) => {
    await runCommand(page, CMD_A)

    await openHistoryWithEntries(page)
    const firstEntry = page.locator('.history-entry').first()
    await firstEntry.locator('[data-action="star"]').click()

    await expect(page.locator('#history-panel')).toHaveClass(/open/)
    await expect(firstEntry).toHaveClass(/starred/)
  })

  test('clear all history removes all chips including starred ones', async ({ page }) => {
    await runCommand(page, CMD_A)
    await waitForHistoryRuns(page, 1)
    await runCommand(page, CMD_B)
    await waitForHistoryRuns(page, 2)

    // Star both runs
    await openHistoryWithEntries(page)
    let entries = page.locator('.history-entry')
    await entries.nth(0).locator('[data-action="star"]').click()
    entries = page.locator('.history-entry')
    await entries.nth(1).locator('[data-action="star"]').click()
    await closeHistory(page)

    await expect(page.locator('.hist-chip')).toHaveCount(2)

    // Open the history panel to access the clear-all button (it lives inside the panel)
    await openHistory(page)
    await page.locator('#hist-clear-all-btn').click()
    await page.keyboard.press('Escape')
    await expect(page.locator('#confirm-host')).toBeHidden()
    await page.locator('#hist-clear-all-btn').click()
    await page.locator('#confirm-host [data-confirm-action-id="all"]').click()
    await page.locator('#confirm-host').waitFor({ state: 'hidden' })
    await expect.poll(async () => page.evaluate(() => (
      Array.isArray(cmdHistory) ? cmdHistory.length : 0
    ))).toBe(0)

    // All chips should be gone
    await expect(page.locator('#history-row .hist-chip')).toHaveCount(0)
  })

  test('clicking outside the drawer closes the history panel', async ({ page }) => {
    await runCommand(page, CMD_A)

    await openHistory(page)
    await expect(page.locator('#history-panel')).toHaveClass(/open/)

    await page.locator('.terminal-wrap').click({ position: { x: 12, y: 12 } })

    await expect(page.locator('#history-panel')).not.toHaveClass(/open/)
  })

  test('pressing Escape closes the history panel', async ({ page }) => {
    await runCommand(page, CMD_A)

    await openHistory(page)
    await expect(page.locator('#history-panel')).toHaveClass(/open/)

    await page.keyboard.press('Escape')

    await expect(page.locator('#history-panel')).not.toHaveClass(/open/)
  })

  test('Delete Non-Favorites keeps starred runs and removes the rest', async ({ page }) => {
    test.setTimeout(60_000)
    await runCommand(page, CMD_A)
    await waitForHistoryRuns(page, 1)
    await runCommand(page, CMD_B)
    await waitForHistoryRuns(page, 2)

    await openHistoryWithEntries(page)
    const entries = page.locator('.history-entry')
    await entries.nth(0).locator('[data-action="star"]').click()
    await closeHistory(page)

    await openHistory(page)
    await page.locator('#hist-clear-all-btn').click()
    await expect(page.locator('#confirm-host [data-confirm-action-id="nonfav"]')).toBeVisible()
    await page.locator('#confirm-host [data-confirm-action-id="nonfav"]').click()

    await expect(page.locator('.hist-chip.starred')).toHaveCount(1)
    await expect(page.locator('.hist-chip')).toHaveCount(1)
    await expect(page.locator('.history-entry')).toHaveCount(1)
    await expect(page.locator('.history-entry.starred')).toHaveCount(1)
  })

  test('starred commands are remembered across page reload', async ({ page }) => {
    test.setTimeout(60_000)
    await runCommand(page, CMD_A)

    // Star the run from the history panel
    await openHistoryWithEntries(page)
    await page.locator('.history-entry').first().locator('[data-action="star"]').click()
    await closeHistory(page)

    // Set up the response waiter before reload so it captures the /session/starred
    // request that loadStarredFromServer() makes on page initialization.
    const starredResponse = page.waitForResponse(
      resp => resp.url().includes('/session/starred') && resp.status() === 200,
    )

    // Reload without clearing localStorage — session_id is preserved, so starred
    // commands are still in the server DB for this session.
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.locator('#cmd').waitFor()
    await starredResponse
    // The reload re-fires the welcome boot path; wait for it to settle before
    // touching the rail so slow runners don't race the welcome animation.
    await ensurePromptReady(page)

    // History panel entries should reflect the server-side starred state.
    await openHistoryWithEntries(page)
    await expect(page.locator('.history-entry.starred')).toHaveCount(1)
  })

  test('loading a synthetic tail run from history restores the filtered transcript', async ({
    page,
  }) => {
    await runCommand(page, 'help | tail -n 3')

    await page.locator('#new-tab-btn').click()
    await expect(page.locator('#cmd')).toHaveValue('')

    await openHistoryWithEntries(page)
    await page.locator('.history-entry').first().locator('[data-action="restore"]').click()

    const output = page.locator('.tab-panel.active .output')
    // help's last three lines (tail -n 3): commands info, commands search, autocomplete hint.
    await expect(output).toContainText(
      'Use `commands info <command>` to see examples, flags, and subcommands for a supported command.',
    )
    await expect(output).toContainText(
      'Use `commands search <term>` to find commands by name, description, category, or guidance notes.',
    )
    await expect(output).toContainText(
      'Autocomplete appears as you type; press Tab to accept or cycle suggestions.',
    )
    await expect(output).not.toContainText('Help and discovery:')
    await expect(output).not.toContainText('README:')
    await expect(output).not.toContainText(
      'Use `commands --built-in` or `commands --external` to filter that catalog.',
    )
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('history drawer can filter to snapshots and shows snapshot actions', async ({ page }) => {
    await runCommand(page, CMD_A)
    await createShareSnapshot(page)

    await openHistory(page)
    await page.locator('#history-type-filter').selectOption('snapshots')

    const entry = page.locator('#history-list .history-entry').first()
    await expect(entry).toBeVisible()
    await expect(entry.locator('.history-entry-kind-snapshot')).toHaveText('SNAPSHOT')
    await expect(entry.locator('.history-entry-cmd')).toContainText(CMD_A)
    await expect(entry.locator('[data-action="open"]')).toHaveText('open')
    await expect(entry.locator('[data-action="link"]')).toHaveText('copy link')
    await expect(entry.locator('[data-action="delete"]')).toHaveText('delete')

    await entry.locator('[data-action="link"]').click()
    await expect(page.locator('#permalink-toast')).toContainText('Link copied to clipboard')
    await expect(page.locator('#history-panel')).not.toHaveClass(/open/)
  })

  test('history bulk select can export add remove and delete visible runs', async ({ page }, testInfo) => {
    test.setTimeout(60_000)
    const bulkCommands = [
      'dig bulk-a.playwright.example +short',
      'nmap -sT -p 80 bulk-b.playwright.example',
    ]
    const sessionId = await browserSessionId(page)
    seedExternalHistoryRuns(testInfo, { sessionId, commands: bulkCommands })
    const runs = await waitForHistoryCommands(page, bulkCommands)
    const selectedRunIds = runs
      .filter(run => bulkCommands.includes(run.command))
      .map(run => String(run.id))
      .sort()
    expect(selectedRunIds).toHaveLength(2)
    const project = await createActiveProject(page, `Bulk History ${Date.now()}`)

    await openHistoryWithEntries(page)
    const bulkToolbar = page.locator('#history-bulk-toolbar')
    await bulkToolbar.locator('.history-bulk-toggle input').check()
    await expect(page.locator('#history-list [data-action="select-run"]')).toHaveCount(2)
    await selectVisibleHistoryRuns(page, bulkCommands)
    await expect(bulkToolbar.locator('.history-bulk-count')).toHaveText('2 selected')

    await bulkToolbar.locator('[data-action="history-bulk-menu"]').click()
    const downloadPromise = page.waitForEvent('download')
    await activateHistoryBulkMenuItem(page, 'bulk-export-jsonl')
    const download = await downloadPromise
    expect(download.suggestedFilename()).toMatch(/^darklab-history-\d{8}-\d{6}\.jsonl$/)
    await expect(page.locator('#permalink-toast')).toContainText('History JSONL export started')
    await expect(bulkToolbar.locator('.history-bulk-count')).toHaveText('2 selected')

    await bulkToolbar.locator('[data-action="history-bulk-menu"]').click()
    await activateHistoryBulkMenuItem(page, 'bulk-add-active-project')
    await expect(page.locator('#confirm-host')).toContainText(`Add 2 selected runs to ${project.name}?`)
    await page.locator('#confirm-host [data-confirm-action-id="add"]').click()
    await expect(page.locator('#permalink-toast')).toContainText('Added 2 runs')
    await expect.poll(() => projectRunLinkIds(page, project.id)).toEqual(selectedRunIds)

    await ensureHistoryBulkSelectMode(page)
    await expect(bulkToolbar.locator('.history-bulk-count')).toHaveText('0 selected')
    await selectVisibleHistoryRuns(page, bulkCommands)
    await expect(bulkToolbar.locator('.history-bulk-count')).toHaveText('2 selected')
    await bulkToolbar.locator('[data-action="history-bulk-menu"]').click()
    await activateHistoryBulkMenuItem(page, 'bulk-remove-project')
    await expect(page.locator('#confirm-host')).toBeVisible()
    await expect(page.locator('#confirm-host')).toContainText('Remove 2 selected runs from all linked projects?')
    await expect(page.locator('#confirm-host')).toContainText('This removes 2 project links and leaves the run history intact.')
    await page.locator('#confirm-host [data-confirm-action-id="remove"]').click()
    await expect(page.locator('#permalink-toast')).toContainText('Removed 2 project links')
    await expect.poll(() => projectRunLinkIds(page, project.id)).toEqual([])

    await ensureHistoryBulkSelectMode(page)
    await selectVisibleHistoryRuns(page, bulkCommands)
    await expect(bulkToolbar.locator('.history-bulk-count')).toHaveText('2 selected')
    await bulkToolbar.locator('[data-action="history-bulk-menu"]').click()
    await activateHistoryBulkMenuItem(page, 'bulk-delete')
    await expect(page.locator('#confirm-host')).toContainText('Delete 2 selected runs?')
    await page.locator('#confirm-host [data-confirm-action-id="delete"]').click()
    await expect(page.locator('#permalink-toast')).toContainText('Deleted 2 runs')
    await expect.poll(async () => (await page.evaluate(async () => {
      const resp = await apiFetch('/history?page_size=20&type=runs')
      const data = await resp.json()
      return data.runs || []
    })).filter(run => bulkCommands.includes(run.command)).length).toBe(0)
  })

})
