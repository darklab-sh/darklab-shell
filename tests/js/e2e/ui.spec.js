// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { test, expect } from '@playwright/test'
import { spawnSync } from 'child_process'
import { existsSync, readFileSync, readdirSync } from 'fs'
import { join } from 'path'
import {
  ensurePromptReady,
  openRailAction,
  runCommand,
  waitForActiveOutputSettled,
  waitForHistoryRuns,
  browserSessionId,
  seedExternalHistoryRuns,
  seedProjectMonitoringFixture,
} from './helpers.js'

const PROJECT_LINK_RUN_COMMAND = 'dig projects.playwright.example +short'

async function expectAtlasInteractionReady(page, { timeout = 15_000 } = {}) {
  const overlay = page.locator('#atlas-overlay')
  await expect(overlay).toHaveClass(/\bopen\b/, { timeout })
  await expect(overlay).toHaveAttribute('data-interaction-ready', '1', { timeout })
  return overlay
}

async function confirmWorkspaceAction(page, actionId, { timeout = 15_000 } = {}) {
  const host = page.locator('#confirm-host')
  const action = host.locator(`[data-confirm-action-id="${actionId}"]`)
  await expect(action).toBeEnabled({ timeout })
  await Promise.all([
    host.waitFor({ state: 'hidden', timeout }),
    action.click(),
  ])
}

async function saveWorkspaceEditor(page, { timeout = 15_000 } = {}) {
  const saveResponse = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return response.request().method() === 'POST' && url.pathname === '/workspace/files'
  })
  await page.locator('#workspace-save-btn').click()
  expect((await saveResponse).ok()).toBe(true)
  await expect(page.locator('#workspace-editor')).not.toBeVisible({ timeout })
}

async function expectEntityMetadata(page, entityType, entityId, { labels = [], note = '' }, { timeout = 15_000 } = {}) {
  await expect.poll(async () => page.evaluate(async ({ entityType: type, entityId: id, expectedLabels }) => {
    const [labelsResp, noteResp] = await Promise.all([
      apiFetch(`/entities/${encodeURIComponent(type)}/${encodeURIComponent(id)}/labels`, { cache: 'no-store' }),
      apiFetch(`/entities/${encodeURIComponent(type)}/${encodeURIComponent(id)}/note`, { cache: 'no-store' }),
    ])
    const [labelsData, noteData] = await Promise.all([
      labelsResp.json(),
      noteResp.json(),
    ])
    const actualLabels = (labelsData.labels || []).map((label) => label.label)
    return {
      hasLabels: expectedLabels.every((label) => actualLabels.includes(label)),
      note: noteData.note?.body || '',
    }
  }, {
    entityType,
    entityId,
    expectedLabels: labels,
  }), { timeout }).toEqual({ hasLabels: true, note })
}

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
  throw new Error('Failed to find a Python executable with sqlite3 for the e2e evidence fixture')
}

function seedProjectEvidenceFixture(testInfo, { sessionId, projectId }) {
  const dataDir = e2eDataDirForProject(testInfo)
  const script = String.raw`
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import uuid

data_dir, session_id, project_id = sys.argv[1:4]
run_id = "run_e2e_" + uuid.uuid4().hex[:16]
artifact_id = "rfa_e2e_" + uuid.uuid4().hex[:16]
finding_id = "fnd_e2e_" + uuid.uuid4().hex[:16]
content = "artifact evidence from Playwright\n80/tcp open http\n"
workspace_name = "sess_" + hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
artifact_rel = "reports/evidence.txt"
artifact_path = Path(data_dir) / "workspaces" / workspace_name / artifact_rel
artifact_path.parent.mkdir(parents=True, exist_ok=True)
artifact_path.write_text(content, encoding="utf-8")
byte_size = len(content.encode("utf-8"))

conn = sqlite3.connect(str(Path(data_dir) / "history.db"))
try:
    conn.execute(
        "INSERT INTO runs (id, session_id, run_kind, command, started, finished, exit_code, "
        "output_preview, preview_truncated, output_line_count, full_output_available, full_output_truncated) "
        "VALUES (?, ?, 'external', ?, datetime('now'), datetime('now'), 0, ?, 0, 2, 1, 0)",
        (
            run_id,
            session_id,
            "nmap -oN reports/evidence.txt playwright.example",
            json.dumps(["80/tcp open http", "artifact evidence from Playwright"]),
        ),
    )
    conn.execute(
        "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
        "VALUES (?, ?, 'run', ?, 'active_project', datetime('now'))",
        ("pln_e2e_" + uuid.uuid4().hex[:16], project_id, run_id),
    )
    conn.execute(
        "INSERT INTO run_file_artifacts "
        "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, content_type, preview_type, created) "
        "VALUES (?, ?, ?, ?, 'evidence.txt', 'output', ?, 'workspace_flag', 'text/plain', 'text', datetime('now'))",
        (artifact_id, session_id, run_id, artifact_rel, byte_size),
    )
    conn.execute(
        "INSERT INTO findings "
        "(id, session_id, run_id, scope, title, raw_line, line_number, severity, fingerprint, review_state, created) "
        "VALUES (?, ?, ?, 'finding', '80/tcp open http', '80/tcp open http', 1, 'info', ?, 'new', datetime('now'))",
        (finding_id, session_id, run_id, "fp-" + finding_id),
    )
    conn.commit()
finally:
    conn.close()
print(json.dumps({"runId": run_id, "artifactId": artifact_id, "findingId": finding_id, "workspacePath": artifact_rel}))
`
  const result = spawnSync(pythonForE2EFixture(), ['-c', script, dataDir, sessionId, projectId], {
    cwd: process.cwd(),
    encoding: 'utf8',
  })
  if (result.status !== 0) {
    throw new Error(`Failed to seed project evidence fixture: ${result.error?.message || result.stderr || result.stdout || `exit ${result.status}`}`)
  }
  return JSON.parse(result.stdout)
}

function seedLargeProjectReportFixture(testInfo, { sessionId, projectId, count = 60 }) {
  const dataDir = e2eDataDirForProject(testInfo)
  const script = String.raw`
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import uuid

data_dir, session_id, project_id, raw_count = sys.argv[1:5]
count = int(raw_count)
workspace_name = "sess_" + hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
workspace_root = Path(data_dir) / "workspaces" / workspace_name
workspace_root.mkdir(parents=True, exist_ok=True)
conn = sqlite3.connect(str(Path(data_dir) / "history.db"))
run_ids = []
artifact_ids = []
finding_ids = []
target_ids = []
try:
    for index in range(count):
        suffix = f"{index:03d}"
        run_id = f"run_report_large_{uuid.uuid4().hex[:10]}_{suffix}"
        artifact_id = f"rfa_report_large_{uuid.uuid4().hex[:10]}_{suffix}"
        finding_id = f"fnd_report_large_{uuid.uuid4().hex[:10]}_{suffix}"
        target_id = f"ent_report_large_{uuid.uuid4().hex[:10]}_{suffix}"
        command = f"large-report-run-{suffix} --target report-target-{suffix}.example.test"
        artifact_rel = f"reports/large-evidence-{suffix}.txt"
        artifact_content = f"large evidence artifact {suffix}\nselector coverage artifact {suffix}\n"
        artifact_path = workspace_root / artifact_rel
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(artifact_content, encoding="utf-8")
        byte_size = len(artifact_content.encode("utf-8"))
        conn.execute(
            "INSERT INTO runs (id, session_id, run_kind, command, started, finished, exit_code, "
            "output_preview, preview_truncated, output_line_count, full_output_available, full_output_truncated) "
            "VALUES (?, ?, 'external', ?, datetime('now', ?), datetime('now', ?), 0, ?, 0, 2, 1, 0)",
            (
                run_id,
                session_id,
                command,
                f"+{index} seconds",
                f"+{index} seconds",
                json.dumps([command, f"large selector evidence {suffix}"]),
            ),
        )
        conn.execute(
            "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
            "VALUES (?, ?, 'run', ?, 'active_project', datetime('now', ?))",
            (f"pln_report_large_run_{uuid.uuid4().hex[:10]}_{suffix}", project_id, run_id, f"+{index} seconds"),
        )
        conn.execute(
            "INSERT INTO run_file_artifacts "
            "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, content_type, preview_type, created) "
            "VALUES (?, ?, ?, ?, ?, 'output', ?, 'workspace_flag', 'text/plain', 'text', datetime('now', ?))",
            (
                artifact_id,
                session_id,
                run_id,
                artifact_rel,
                f"large-evidence-{suffix}.txt",
                byte_size,
                f"+{index} seconds",
            ),
        )
        conn.execute(
            "INSERT INTO findings "
            "(id, session_id, run_id, scope, title, raw_line, line_number, severity, fingerprint, review_state, created) "
            "VALUES (?, ?, ?, 'finding', ?, ?, 1, 'info', ?, 'new', datetime('now', ?))",
            (
                finding_id,
                session_id,
                run_id,
                f"Large selector finding {suffix}",
                f"large selector finding evidence {suffix}",
                "fp-" + finding_id,
                f"+{index} seconds",
            ),
        )
        canonical_value = f"report-target-{suffix}.example.test"
        conn.execute(
            "INSERT INTO entities "
            "(id, session_id, type, canonical_value, signature_hash, first_seen_at, last_seen_at, created) "
            "VALUES (?, ?, 'domain', ?, ?, datetime('now', ?), datetime('now', ?), datetime('now', ?))",
            (
                target_id,
                session_id,
                canonical_value,
                "sig-" + target_id,
                f"+{index} seconds",
                f"+{index} seconds",
                f"+{index} seconds",
            ),
        )
        conn.execute(
            "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
            "VALUES (?, ?, 'atlas_entity', ?, 'manual', datetime('now', ?))",
            (f"pln_report_large_ent_{uuid.uuid4().hex[:10]}_{suffix}", project_id, target_id, f"+{index} seconds"),
        )
        run_ids.append(run_id)
        artifact_ids.append(artifact_id)
        finding_ids.append(finding_id)
        target_ids.append(target_id)
    conn.commit()
finally:
    conn.close()
print(json.dumps({
    "count": count,
    "runIds": run_ids,
    "artifactIds": artifact_ids,
    "findingIds": finding_ids,
    "targetIds": target_ids,
    "includedArtifactText": "large evidence artifact 059",
    "excludedArtifactText": "large evidence artifact 005",
    "artifactFilterQuery": "large-evidence",
}))
`
  const result = spawnSync(pythonForE2EFixture(), ['-c', script, dataDir, sessionId, projectId, String(count)], {
    cwd: process.cwd(),
    encoding: 'utf8',
  })
  if (result.status !== 0) {
    throw new Error(`Failed to seed large report fixture: ${result.error?.message || result.stderr || result.stdout || `exit ${result.status}`}`)
  }
  return JSON.parse(result.stdout)
}

function readReportArchiveText(zipPath) {
  const script = String.raw`
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1]) as archive:
    chunks = []
    for name in archive.namelist():
        if name.endswith((".html", ".md", ".json")):
            chunks.append(archive.read(name).decode("utf-8", errors="replace"))
print("\n".join(chunks))
`
  const result = spawnSync(pythonForE2EFixture(), ['-c', script, zipPath], {
    cwd: process.cwd(),
    encoding: 'utf8',
  })
  if (result.status !== 0) {
    throw new Error(`Failed to inspect report archive: ${result.error?.message || result.stderr || result.stdout || `exit ${result.status}`}`)
  }
  return result.stdout
}

function seedAutoPromoteAtlasEntity(testInfo, { sessionId }) {
  const dataDir = e2eDataDirForProject(testInfo)
  const script = String.raw`
from pathlib import Path
import json
import sqlite3
import sys
import uuid

data_dir, session_id = sys.argv[1:3]
run_id = "run_auto_promote_e2e_" + uuid.uuid4().hex[:16]
entity_id = "ent_auto_promote_e2e_" + uuid.uuid4().hex[:16]
entity_value = "portal.autopromote-e2e.example.com"
now = "2026-05-31 00:00:00"

conn = sqlite3.connect(str(Path(data_dir) / "history.db"))
try:
    conn.execute(
        "INSERT INTO runs (id, session_id, run_kind, command, started, finished, exit_code, "
        "output_preview, preview_truncated, output_line_count, full_output_available, full_output_truncated) "
        "VALUES (?, ?, 'external', ?, datetime('now'), datetime('now'), 0, ?, 0, 1, 0, 0)",
        (run_id, session_id, "nmap portal.autopromote-e2e.example.com", json.dumps(["portal.autopromote-e2e.example.com"])),
    )
    conn.execute(
        "INSERT INTO entities "
        "(id, session_id, type, canonical_value, signature_hash, first_seen_at, last_seen_at, created) "
        "VALUES (?, ?, 'domain', ?, ?, ?, ?, ?)",
        (entity_id, session_id, entity_value, "sig-" + entity_id, now, now, now),
    )
    conn.execute(
        "INSERT INTO entity_run_links (entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
        "VALUES (?, ?, ?, ?, 1)",
        (entity_id, run_id, now, now),
    )
    conn.commit()
finally:
    conn.close()
print(json.dumps({"entityId": entity_id, "entityValue": entity_value, "runId": run_id}))
`
  const result = spawnSync(pythonForE2EFixture(), ['-c', script, dataDir, sessionId], {
    cwd: process.cwd(),
    encoding: 'utf8',
  })
  if (result.status !== 0) {
    throw new Error(`Failed to seed auto-promote fixture: ${result.error?.message || result.stderr || result.stdout || `exit ${result.status}`}`)
  }
  return JSON.parse(result.stdout)
}

test.describe('theme selector', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await ensurePromptReady(page)
  })

  test('clicking the theme button opens the theme selector', async ({ page }) => {
    await openRailAction(page, 'theme')
    await expect(page.locator('#theme-overlay')).toHaveClass(/open/)
    await expect(page.locator('#theme-overlay')).toHaveCSS('align-items', 'stretch')
    await expect(page.locator('#theme-overlay')).toHaveCSS('justify-content', 'flex-end')
    await expect(page.locator('#theme-select .theme-card-active')).toBeVisible()
  })

  test('selecting a theme applies it from the selector', async ({ page }) => {
    await openRailAction(page, 'theme')
    const optionLabels = await page
      .locator('#theme-select .theme-card-label')
      .evaluateAll((labels) => labels.map((label) => label.textContent))
    expect(optionLabels).toContain('Darklab Obsidian')
    expect(optionLabels).toContain('Charcoal Steel')
    const groupLabels = await page
      .locator('#theme-select .theme-picker-group-title')
      .evaluateAll((labels) => labels.map((label) => label.textContent))
    expect(groupLabels).toEqual([
      'Dark Neon',
      'Dark Neutral',
      'Dark Mid-tone',
      'Warm Light',
      'Cool Light',
      'Neutral Mid-tone',
      'Neutral Light',
    ])
    await page.locator('#theme-select [data-theme-name="charcoal_steel"]').click()
    await expect(page.locator('body')).toHaveAttribute('data-theme', 'charcoal_steel')

    await page.locator('#theme-select [data-theme-name="cobalt_obsidian"]').click()
    await expect(page.locator('body')).toHaveAttribute('data-theme', 'cobalt_obsidian')
  })

  test('falls back to the configured default theme when localStorage references a missing theme', async ({
    page,
  }) => {
    await page.evaluate(() => {
      localStorage.setItem('theme', 'theme_missing.yaml')
    })

    await page.reload()
    await page.locator('#cmd').waitFor()

    await expect(page.locator('body')).toHaveAttribute('data-theme', 'darklab_obsidian')
  })
})

test.describe('FAQ modal', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/allowed-commands', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          restricted: true,
          commands: ['ping', 'traceroute'],
          groups: [
            {
              name: 'Networking',
              commands: ['ping', 'traceroute'],
            },
          ],
        }),
      })
    })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('FAQ button opens the overlay', async ({ page }) => {
    await expect(page.locator('#faq-overlay')).not.toHaveClass(/open/)
    await openRailAction(page, 'faq')
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)
  })

  test('close button inside the FAQ modal closes it', async ({ page }) => {
    await openRailAction(page, 'faq')
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)

    await page.locator('.faq-close').click()
    await expect(page.locator('#faq-overlay')).not.toHaveClass(/open/)
  })

  test('clicking the overlay backdrop closes the FAQ modal', async ({ page }) => {
    await openRailAction(page, 'faq')
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)

    // Click on the overlay element itself (outside the modal content box)
    await page.locator('#faq-overlay').click({ position: { x: 10, y: 10 } })
    await expect(page.locator('#faq-overlay')).not.toHaveClass(/open/)
  })

  test('renders backend-driven FAQ content and command registry pointer', async ({ page }) => {
    await openRailAction(page, 'faq')
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)

    await expect(page.locator('.faq-q')).toContainText([
      'What is this?',
      'What commands are allowed?',
    ])
    await expect(
      page.locator('.faq-a a[href*="gitlab.com/darklab.sh/darklab_shell"]').first(),
    ).toBeVisible()
    const tourButton = page.locator('.faq-tour-open')
    await expect(tourButton).toBeVisible()
    await tourButton.click()
    await expect(page.locator('#tour-overlay')).toHaveClass(/open/)
    await expect(page.locator('#tour-chapter-title')).toContainText('Running commands')
    await expect(page.locator('#faq-overlay')).not.toHaveClass(/open/)
    await page.keyboard.press('Escape')
    await expect(page.locator('#tour-overlay')).not.toHaveClass(/open/)
    await expect(page.locator('#faq-overlay')).not.toHaveClass(/open/)
    await expect(page.locator('#cmd')).toBeFocused()

    await openRailAction(page, 'faq')
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)

    // The allowed-commands section is inside a collapsed accordion — expand it first
    await page.locator('.faq-q').filter({ hasText: 'What commands are allowed?' }).click()
    await expect(page.locator('#faq-allowed-text')).toBeVisible()
    await expect(page.locator('#faq-allowed-text')).toContainText('Open the Command Registry')

    await page.locator('#faq-allowed-text').getByRole('button', { name: 'Open Command Registry' }).click()
    await expect(page.locator('#command-registry-overlay')).toHaveClass(/open/)
    await expect(page.locator('#command-registry-body')).toContainText('curl', { timeout: 30_000 })
  })
})

test.describe('Status Monitor', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await ensurePromptReady(page)
  })

  test('desktop rail opens the idle Status Monitor modal', async ({ page }) => {
    await page.locator('#rail-more-btn').click()
    await expect(page.locator('#rail-more-menu [data-action="status-monitor"] .rail-nav-label')).toHaveText('status')
    await page.keyboard.press('Escape')

    await openRailAction(page, 'status-monitor')

    await expect(page.locator('#status-monitor')).toBeVisible()
    await expect(page.locator('#status-monitor')).toHaveClass(/\bstatus-monitor-modal\b/)
    await expect(page.locator('#status-monitor-title')).toHaveText('Status Monitor')
    await expect(page.locator('.status-monitor-summary')).toContainText('0 active')
    await expect(page.locator('.status-monitor-summary')).toContainText('uptime')
    await expect(page.locator('.status-monitor-section-title').filter({ hasText: 'System' })).toBeVisible()
    await expect(page.locator('.status-monitor-runs-section')).toBeVisible()
    await expect(page.locator('.status-monitor-showcase > .status-monitor-runs-section')).toBeVisible()

    await page.keyboard.press('Escape')
    await expect(page.locator('#status-monitor')).toBeHidden()
  })

  test('desktop Status Monitor loads dashboard endpoints together without route stubs', async ({ page }) => {
    const endpointPaths = ['/status', '/workspace/files', '/history/stats', '/history/insights']
    const responses = endpointPaths.map((path) => page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'GET' && url.pathname === path
    }))

    await openRailAction(page, 'status-monitor')
    await expect(page.locator('#status-monitor')).toBeVisible()

    const observed = await Promise.all(responses)
    expect(Object.fromEntries(observed.map((response) => [
      new URL(response.url()).pathname,
      response.ok(),
    ]))).toEqual(Object.fromEntries(endpointPaths.map((path) => [path, true])))
    await expect(page.locator('.status-monitor-section-title').filter({ hasText: 'System' })).toBeVisible()
    await expect(page.locator('.status-monitor-section-title').filter({ hasText: 'Resources' })).toBeVisible()
    await expect(page.locator('.status-monitor-section-title').filter({ hasText: 'Session' })).toBeVisible()
    await expect(page.locator('.status-monitor-showcase-grid')).toBeVisible()
  })

  test('active rows sit under the pulse strip with wide telemetry', async ({ page }) => {
    await page.route('**/history/active**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          runs: [
            {
              run_id: 'status-monitor-active-row',
              pid: 4242,
              command: 'ping -c 1000 127.0.0.1',
              started: new Date(Date.now() - 45_000).toISOString(),
              owner_tab_id: 'tab-1',
              has_live_owner: true,
              owned_by_this_client: true,
              resource_usage: {
                cpu_seconds: 12.5,
                memory_bytes: 12582912,
              },
            },
          ],
        }),
      })
    })

    await openRailAction(page, 'status-monitor')
    await expect(page.locator('#status-monitor')).toBeVisible()

    const showcase = page.locator('.status-monitor-showcase')
    await expect(showcase.locator(':scope > .status-monitor-pulse-strip')).toBeVisible()
    await expect(showcase.locator(':scope > .status-monitor-runs-section')).toBeVisible()
    await expect(showcase.locator(':scope > .status-monitor-showcase-grid')).toBeVisible()
    await expect(showcase.locator(':scope > .status-monitor-runs-section').locator('.status-monitor-command')).toContainText('ping -c 1000')
    await expect(showcase.locator('.status-monitor-meta-chip').filter({ hasText: 'started here' })).toBeVisible()
    await expect(showcase.locator('.status-monitor-spark-panel')).toContainText('CPU/MEM 60s')
    await expect(showcase.locator('.status-monitor-spark-values')).toHaveCount(0)
    await expect(showcase.locator('.status-monitor-meter-mem')).toContainText('12 MB')
    await expect(showcase.locator('.status-monitor-meter-rail')).toBeVisible()

    const showcaseOrder = await showcase.evaluate((el) => (
      [...el.children].slice(0, 3).map(child => [...child.classList][0])
    ))
    expect(showcaseOrder).toEqual([
      'status-monitor-pulse-strip',
      'status-monitor-section',
      'status-monitor-showcase-grid',
    ])
  })

  test('visual cards open filtered history and restore constellation runs', async ({ page }) => {
    test.setTimeout(60_000)
    const command = 'ping -c 1 -W 1 192.0.2.1'
    await runCommand(page, command)
    await waitForHistoryRuns(page, 1)
    await expect.poll(async () => page.evaluate(async () => {
      const resp = await apiFetch('/history/insights')
      const data = await resp.json()
      return (data.command_mix || []).map(item => item.root)
    })).toContain('ping')

    const insightsResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return url.pathname === '/history/insights'
    })
    await openRailAction(page, 'status-monitor')
    await expect(page.locator('#status-monitor')).toBeVisible()
    expect((await insightsResponse).ok()).toBe(true)

    const tile = page.getByRole('button', { name: /^ping: \d+ run\(s\),/ }).first()
    await expect(tile).toBeVisible({ timeout: 15_000 })
    await tile.click()

    await expect(page.locator('#history-panel')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#history-root-input')).toHaveValue('ping')
    await expect(page.locator('#history-list .history-entry').first()).toContainText(command)
    await expect.poll(() => page.evaluate(() => window.getSelection()?.toString() || '')).toBe('')

    await page.locator('#history-close').click()
    await expect(page.locator('#history-panel')).not.toHaveClass(/\bopen\b/)

    await openRailAction(page, 'status-monitor')
    await expect(page.locator('#status-monitor')).toBeVisible()
    await page.locator('#status-monitor .status-monitor-star-node[aria-label^="ping "]').first().click()

    await expect(page.locator('#status-monitor')).toBeHidden()
    await page.waitForFunction((expectedCommand) => {
      const tab = typeof getActiveTab === 'function' ? getActiveTab() : null
      return !!tab && tab.command === expectedCommand && !!tab.historyRunId
    }, command)
    await expect(page.locator('.tab-panel.active .output')).toContainText('[history')
  })
})

test.describe('project workspace modal', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await ensurePromptReady(page)
  })

  async function openProjectsModal(page) {
    await page.locator('.rail-nav [data-action="projects"]').click()
    await expect(page.locator('#project-workspace-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#project-workspace-body')).not.toContainText('Loading projects...')
  }

  async function readActiveProject(page) {
    return page.evaluate(async () => {
      const resp = await apiFetch('/projects/active', { cache: 'no-store' })
      return resp.json()
    })
  }

  async function waitForProjectTargetValue(page, projectId, value) {
    await expect.poll(async () => page.evaluate(async ({ id, targetValue }) => {
      const resp = await apiFetch(`/projects/${encodeURIComponent(id)}/summary`, { cache: 'no-store' })
      const data = await resp.json()
      return (data.targets || []).some((target) => target.value === targetValue)
    }, { id: projectId, targetValue: value }), { timeout: 15_000 }).toBe(true)
  }

  async function switchProjectTab(page, tabId) {
    const tab = page.locator(`[data-project-tab="${tabId}"]`)
    await tab.click()
    await expect(tab).toHaveClass(/\bis-active\b/, { timeout: 15_000 })
  }

  async function submitRunnerCommandWithProjectsOpen(page, cmd, { timeout = 45_000 } = {}) {
    const beforeLineCount = await page.evaluate(() => {
      const tab = typeof getActiveTab === 'function' ? getActiveTab() : null
      return Array.isArray(tab?.rawLines) ? tab.rawLines.length : 0
    })
    const submitted = await page.evaluate((command) => {
      if (typeof submitComposerCommand !== 'function') return 'missing'
      return submitComposerCommand(command, { dismissKeyboard: false, focusAfterSubmit: false })
    }, cmd)
    expect(submitted).toBe(true)
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

  async function expectProjectTargetEditorReady(page, submitText) {
    const editor = page.locator('#project-target-editor-overlay')
    await expect(editor).toHaveClass(/\bopen\b/)
    await expect(editor).toBeVisible()
    for (const selector of ['#project-target-type', '#project-target-value', '#project-target-label', '#project-target-notes']) {
      const field = editor.locator(selector)
      await field.scrollIntoViewIfNeeded()
      await expect(field).toBeVisible()
      await expect(field).toBeEnabled()
    }
    const submit = page.locator('#project-target-submit')
    await submit.scrollIntoViewIfNeeded()
    await expect(submit).toBeVisible()
    await expect(submit).toBeEnabled()
    if (submitText) await expect(submit).toHaveText(submitText)
    return editor
  }

  async function fillProjectTargetEditor(page, { value, labels, notes }) {
    const editor = page.locator('#project-target-editor-overlay')
    const valueInput = editor.locator('#project-target-value')
    const labelInput = editor.locator('#project-target-label')
    const notesInput = editor.locator('#project-target-notes')
    await valueInput.scrollIntoViewIfNeeded()
    await valueInput.fill(value)
    await labelInput.scrollIntoViewIfNeeded()
    await labelInput.fill(labels)
    await notesInput.scrollIntoViewIfNeeded()
    await expect(notesInput).toBeVisible()
    await notesInput.fill(notes)
  }

  async function createActiveProject(page, projectName) {
    await page.locator('#project-workspace-name').fill(projectName)
    const createResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname === '/projects'
    })
    const activeResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname === '/projects/active'
    })
    await page.locator('#project-workspace-create-form button[type="submit"]').click()
    const created = await createResponse
    expect(created.ok()).toBe(true)
    const createdProject = (await created.json()).project
    expect(createdProject?.name).toBe(projectName)
    expect((await activeResponse).ok()).toBe(true)
    await expect.poll(async () => {
      const active = await readActiveProject(page)
      return active.project?.name || ''
    }).toBe(projectName)
    await page.evaluate(async () => {
      if (typeof refreshProjectWorkspace === 'function') await refreshProjectWorkspace()
    })
    await expect(page.locator('.project-workspace-row.is-active').filter({ hasText: projectName })).toBeVisible({
      timeout: 15_000,
    })
    await expect(page.locator('#project-explorer-body')).toContainText(projectName, { timeout: 15_000 })
    const activeProject = await readActiveProject(page)
    expect(activeProject.project?.name).toBe(projectName)
    const projectId = activeProject.project?.id || createdProject?.id
    expect(projectId).toBeTruthy()
    return projectId
  }

  async function linkExternalRunToOpenProject(page, testInfo) {
    const sessionId = await browserSessionId(page)
    const [seededRun] = seedExternalHistoryRuns(testInfo, {
      sessionId,
      commands: [PROJECT_LINK_RUN_COMMAND],
    })
    await switchProjectTab(page, 'runs')
    const activeProject = await readActiveProject(page)
    const projectId = activeProject.project?.id || ''
    expect(projectId).toBeTruthy()
    await page.locator('[data-project-action="link-last-run"]').click()
    await expect(page.locator('#confirm-host')).toContainText('Add the last run to this project?')
    const [linkResponse] = await Promise.all([
      page.waitForResponse((response) => {
        const url = new URL(response.url())
        return response.request().method() === 'POST'
          && url.pathname === `/projects/${projectId}/links`
      }),
      page.locator('#confirm-host [data-confirm-action-id="add"]').click(),
    ])
    expect(linkResponse.ok()).toBe(true)
    await expect(page.locator('#permalink-toast')).toContainText('Last run linked to this project.')
    const runRow = page.locator('.project-explorer-item').filter({ hasText: seededRun.command }).first()
    await expect.poll(async () => page.evaluate(async ({ id, command }) => {
      const params = new URLSearchParams({ page_size: '25' })
      const resp = await apiFetch(`/projects/${encodeURIComponent(id)}/runs?${params.toString()}`, { cache: 'no-store' })
      if (!resp.ok) return false
      const data = await resp.json()
      const runs = Array.isArray(data.runs) ? data.runs : []
      return runs.some(run => String(run && run.command || '') === command)
    }, { id: projectId, command: seededRun.command })).toBe(true)
    await expect(runRow).toBeVisible()
    return { runRow, command: seededRun.command }
  }

  test('records project actions in the diagnostics audit viewer', async ({ page }, testInfo) => {
    test.setTimeout(60_000)
    await openProjectsModal(page)
    const projectId = await createActiveProject(page, `Playwright Audit ${Date.now()}`)
    await linkExternalRunToOpenProject(page, testInfo)

    await page.goto(`/diag/audit?event_type=project.link&project_id=${encodeURIComponent(projectId)}`)
    await expect(page.locator('body.diag-page')).toBeVisible()
    const auditRow = page.locator('.diag-audit-table tbody tr', {
      hasText: projectId,
    }).first()
    await expect(auditRow).toContainText('project.link', { timeout: 15_000 })
    await expect(auditRow).toContainText(`project:${projectId}`)
    await auditRow.locator('.diag-audit-details summary').click()
    await expect(auditRow.locator('.diag-audit-details pre')).toContainText('"event_type": "project.link"')
    await expect(auditRow.locator('.diag-audit-details pre')).toContainText('"source": "manual"')
    await expect(page.getByRole('link', { name: 'CSV' })).toHaveAttribute(
      'href',
      new RegExp(`/diag/audit/export\\?event_type=project\\.link&project_id=${projectId}`),
    )
    await expect(page.getByRole('link', { name: 'JSON' })).toHaveAttribute(
      'href',
      new RegExp(`/diag/audit/export\\?format=json&event_type=project\\.link&project_id=${projectId}`),
    )
  })

  test('opens Project Activity and filters project-link rows', async ({ page }, testInfo) => {
    test.setTimeout(60_000)
    await openProjectsModal(page)
    const projectId = await createActiveProject(page, `Playwright Activity ${Date.now()}`)
    await linkExternalRunToOpenProject(page, testInfo)

    await switchProjectTab(page, 'activity')
    const activityRoot = page.locator('[data-project-activity-root]')
    await expect(activityRoot).toBeVisible()
    await expect(activityRoot.locator('.project-activity-row').first()).toContainText('Project Link', { timeout: 15_000 })

    await activityRoot.locator('[data-project-activity-filter="event_type"]').fill('project.link')
    const filtered = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return url.pathname === `/projects/${projectId}/activity`
        && url.searchParams.get('event_type') === 'project.link'
    })
    await activityRoot.locator('[data-project-activity-action="apply"]').click()
    expect((await filtered).ok()).toBe(true)

    const row = activityRoot.locator('.project-activity-row').first()
    await expect(row).toContainText('Project Link')
    await expect(row).toContainText(`project:${projectId}`)
    await row.locator('.project-activity-details-toggle').click()
    await expect(row.locator('.project-activity-detail-list')).toContainText('source')
    await expect(row.locator('.project-activity-detail-list')).toContainText('manual')
  })

  test('opens Project Monitoring through the real Projects tab', async ({ page }, testInfo) => {
    test.setTimeout(60_000)
    await openProjectsModal(page)
    const projectId = await createActiveProject(page, `Playwright Monitoring ${Date.now()}`)
    const fixture = seedProjectMonitoringFixture(testInfo, {
      sessionId: await browserSessionId(page),
      projectId,
    })
    await page.evaluate(async () => {
      if (typeof refreshProjectWorkspace === 'function') await refreshProjectWorkspace()
    })

    const monitoringResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'GET'
        && url.pathname === `/projects/${projectId}/monitoring`
    })
    await switchProjectTab(page, 'monitoring')
    expect((await monitoringResponse).ok()).toBe(true)

    const root = page.locator(`[data-project-monitoring-root="${projectId}"]`)
    await expect(root).toBeVisible({ timeout: 15_000 })
    await expect(root.locator('.project-monitoring-count.is-changed')).toContainText('2')
    await expect(root).toContainText('Ports Browser Watch')
    await expect(root).toContainText('Deleted Current Watch')
    await expect(root).toContainText('New open port 443/tcp https')

    const availableFire = root.locator(`[data-project-monitoring-fire-id="${fixture.changedFireId}"]`).first()
    await expect(availableFire.locator('[data-project-monitoring-action="details"]').first()).toBeEnabled()
    await expect(availableFire.locator('[data-project-monitoring-action="compare"]').first()).toBeEnabled()

    const missingCurrentFire = root.locator(`[data-project-monitoring-fire-id="${fixture.deletedFireId}"]`).first()
    await expect(missingCurrentFire).toContainText('Deleted Current Watch')
    await expect(missingCurrentFire.locator('[data-project-monitoring-action="details"]').first()).toBeDisabled()
    await expect(missingCurrentFire.locator('[data-project-monitoring-action="compare"]').first()).toBeDisabled()
  })

  test('creates an active project, manages targets, and edits linked run metadata', async ({ page }, testInfo) => {
    test.setTimeout(60_000)
    await openProjectsModal(page)

    const projectName = `Playwright Projects ${Date.now()}`
    const projectId = await createActiveProject(page, projectName)

    await page.locator('#project-labels-input').fill('e2e, client')
    const labelsSaveResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'POST'
        && url.pathname === `/entities/project/${projectId}/labels`
    })
    await page.locator('#project-labels-save-btn').click()
    expect((await labelsSaveResponse).ok()).toBe(true)
    await expect(page.locator('.project-label-chips')).toContainText('e2e')
    await expect(page.locator('.project-label-chips')).toContainText('client')
    await page.locator('#project-notes-input').fill('Project notes from Playwright')
    await switchProjectTab(page, 'runs')
    await expect.poll(async () => page.evaluate(async (id) => {
      const resp = await apiFetch(`/projects/${encodeURIComponent(id)}`, { cache: 'no-store' })
      const data = await resp.json()
      return data.project?.note?.body || ''
    }, projectId)).toBe('Project notes from Playwright')

    await switchProjectTab(page, 'details')
    await page.locator('#project-explorer-body [data-project-action="new-target"]').click()
    await expectProjectTargetEditorReady(page, 'Add Target')
    await fillProjectTargetEditor(page, {
      value: 'playwright.example',
      labels: 'Primary target',
      notes: 'Scope confirmed in browser test',
    })
    const addTargetSubmit = page.locator('#project-target-submit')
    await addTargetSubmit.scrollIntoViewIfNeeded()
    await expect(addTargetSubmit).toBeVisible()
    await addTargetSubmit.click()
    await expect(page.locator('#project-target-editor-overlay')).not.toHaveClass(/\bopen\b/)
    const targetRow = page.locator('.project-target-row').filter({ hasText: 'playwright.example' })
    await expect(targetRow).toBeVisible()
    await expect(targetRow).toContainText('Primary target')
    await expect(targetRow).toContainText('note')

    await targetRow.locator('[data-project-action="edit-target"]').click()
    await expectProjectTargetEditorReady(page, 'Save Target')
    await expect(page.locator('#project-target-editor-title')).toHaveText('EDIT TARGET')
    await fillProjectTargetEditor(page, {
      value: 'projects.playwright.example',
      labels: 'Updated target',
      notes: 'Scope confirmed in browser test',
    })
    const targetUpdateResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'PUT'
        && url.pathname.startsWith(`/projects/${projectId}/targets/`)
    })
    await page.locator('#project-target-submit').click()
    expect((await targetUpdateResponse).ok()).toBe(true)
    await waitForProjectTargetValue(page, projectId, 'projects.playwright.example')
    await expect(page.locator('.project-target-row').filter({ hasText: 'projects.playwright.example' })).toBeVisible({
      timeout: 15_000,
    })

    const { runRow, command: linkedRunCommand } = await linkExternalRunToOpenProject(page, testInfo)
    await runRow.locator('[data-project-action="edit-run-metadata"]').click()
    await expect(page.locator('#project-entity-editor-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#project-entity-editor-title')).toHaveText('EDIT RUN')
    await page.locator('#project-entity-labels').fill('baseline, reviewed')
    await page.locator('#project-entity-note').fill('Run triaged from Playwright')
    await page.locator('#project-entity-submit').click()
    await expect(page.locator('#project-entity-editor-overlay')).not.toHaveClass(/\bopen\b/, { timeout: 15_000 })
    const runId = await runRow.locator('[data-project-action="edit-run-metadata"]').getAttribute('data-run-id')
    expect(runId).toBeTruthy()
    await expectEntityMetadata(page, 'run', runId, {
      labels: ['baseline', 'reviewed'],
      note: 'Run triaged from Playwright',
    })
    await expect(runRow).toContainText('reviewed', { timeout: 15_000 })
    await expect.poll(async () => runRow.textContent(), { timeout: 15_000 }).toMatch(
      /note|Run triaged from Playwright/,
    )

    await switchProjectTab(page, 'details')
    const updatedTargetRow = page.locator('.project-target-row').filter({ hasText: 'projects.playwright.example' })
    await updatedTargetRow.locator('[data-project-action="delete-target"]').click()
    await expect(page.locator('#confirm-host')).toBeVisible()
    await page.locator('#confirm-host [data-confirm-action-id="remove"]').click()
    await expect(page.locator('#confirm-host')).toBeHidden()
    await expect(updatedTargetRow).toHaveCount(0)

    const persisted = await page.evaluate(async (id) => {
      const [projectResp, labelsResp, summaryResp] = await Promise.all([
        apiFetch(`/projects/${encodeURIComponent(id)}`, { cache: 'no-store' }),
        apiFetch(`/entities/project/${encodeURIComponent(id)}/labels`, { cache: 'no-store' }),
        apiFetch(`/projects/${encodeURIComponent(id)}/summary`, { cache: 'no-store' }),
      ])
      const [projectData, labelsData, summaryData] = await Promise.all([
        projectResp.json(),
        labelsResp.json(),
        summaryResp.json(),
      ])
      return {
        notes: projectData.project?.note?.body,
        labels: (labelsData.labels || []).map((label) => label.label),
        targets: summaryData.targets || [],
        runs: summaryData.runs || [],
      }
    }, projectId)
    expect(persisted.notes).toBe('Project notes from Playwright')
    expect(persisted.labels).toEqual(expect.arrayContaining(['e2e', 'client']))
    expect(persisted.targets).toEqual([])
    expect(persisted.runs.some((run) => (
      run.command === linkedRunCommand
      && (run.labels || []).some((label) => label.label === 'reviewed')
      && run.note?.body === 'Run triaged from Playwright'
    ))).toBe(true)
  })

  test('creates, previews, applies, and shows an Atlas auto-promote rule', async ({ page }, testInfo) => {
    test.setTimeout(60_000)
    const sessionId = await browserSessionId(page)
    const fixture = seedAutoPromoteAtlasEntity(testInfo, { sessionId })
    await openProjectsModal(page)

    await createActiveProject(page, `Auto Promote ${Date.now()}`)
    await switchProjectTab(page, 'entities')
    await expect(page.locator('#project-explorer-body')).toContainText('No Atlas entities are linked')

    await page.locator('[data-project-action="toggle-project-auto-promote-rules"]').click()
    const panel = page.locator('#project-explorer-body .project-auto-promote-panel').last()
    await expect(panel).toBeVisible()
    const projectId = await readActiveProject(page).then(active => active.project?.id || '')
    expect(projectId).toBeTruthy()

    await panel.locator('[data-project-action="new-project-auto-promote-rule"]').click()
    const editor = panel.locator('.project-auto-promote-editor').last()
    await expect(editor).toBeVisible()
    await editor.locator('[data-project-auto-promote-field="name"]').fill('E2E owned domains')
    await editor.locator('[data-project-auto-promote-field="target_entity_kind"]').selectOption('domain')
    await editor.locator('[data-project-auto-promote-field="match_mode"]').selectOption('domain_suffix')
    await editor.locator('[data-project-auto-promote-field="pattern"]').fill('autopromote-e2e.example.com')

    await expect(editor.locator('.project-auto-promote-preview')).toContainText('Preview required before save.')

    const saveButton = editor.locator('[data-project-action="save-project-auto-promote-rule"]')
    await expect(saveButton).toBeEnabled()
    await saveButton.scrollIntoViewIfNeeded()
    await saveButton.click()
    await expect(page.locator('#permalink-toast')).toContainText('Preview the rule before saving.')

    const previewButton = editor.locator('[data-project-action="preview-project-auto-promote-rule"]')
    await expect(previewButton).toBeEnabled()
    await expect(previewButton).toHaveAttribute('data-project-id', projectId)
    await previewButton.scrollIntoViewIfNeeded()
    const previewResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'POST'
        && url.pathname === `/projects/${projectId}/auto-promote-rules/preview`
    })
    await previewButton.click()
    expect((await previewResponse).ok()).toBe(true)
    await expect(editor.locator('.project-auto-promote-preview')).toContainText('1 match')
    await expect(editor.locator('.project-auto-promote-preview')).toContainText('1 new')

    await expect(saveButton).toBeEnabled()
    await saveButton.scrollIntoViewIfNeeded()
    const createResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'POST'
        && url.pathname === `/projects/${projectId}/auto-promote-rules`
    })
    await saveButton.click()
    const created = await createResponse
    expect(created.ok()).toBe(true)
    const ruleId = (await created.json()).rule?.id || ''
    expect(ruleId).toBeTruthy()
    await expect(panel).toContainText('E2E owned domains')

    const applyResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'POST'
        && url.pathname === `/projects/${projectId}/auto-promote-rules/${ruleId}/apply`
    })
    await panel.locator(`[data-project-action="apply-project-auto-promote-rule"][data-rule-id="${ruleId}"]`).click()
    await expect(page.locator('#confirm-host')).toContainText('Apply "E2E owned domains"')
    await confirmWorkspaceAction(page, 'apply')
    expect((await applyResponse).ok()).toBe(true)

    await page.getByRole('tab', { name: /Domains\s*1/ }).click()
    await expect(page.locator('#project-explorer-body')).toContainText(fixture.entityValue)
    await expect(page.locator('#project-explorer-body')).toContainText('Auto-promoted: E2E owned domains')
  })

  test('refreshes an open project when a run stream auto-promotes an Atlas entity', async ({ page }) => {
    test.setTimeout(75_000)
    await openProjectsModal(page)

    const projectId = await createActiveProject(page, `Auto Promote Stream ${Date.now()}`)
    await switchProjectTab(page, 'entities')
    await expect(page.locator('#project-explorer-body')).toContainText('No Atlas entities are linked')

    const suffix = `stream-${Date.now()}.autopromote-e2e.example.com`
    const entityValue = `portal.${suffix}`
    const createdRule = await page.evaluate(async ({ id, pattern }) => {
      const resp = await apiFetch(`/projects/${encodeURIComponent(id)}/auto-promote-rules`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: 'E2E stream domains',
          enabled: true,
          apply_on_run: true,
          target_entity_kind: 'domain',
          match_mode: 'domain_suffix',
          pattern,
          filters: {},
        }),
      })
      const data = await resp.json().catch(() => ({}))
      return { ok: resp.ok, status: resp.status, data }
    }, { id: projectId, pattern: suffix })
    expect(createdRule).toMatchObject({ ok: true, status: 201 })
    expect(createdRule.data.rule?.id).toBeTruthy()

    await submitRunnerCommandWithProjectsOpen(page, `ping -c 1 ${entityValue}`)

    const output = page.locator('.tab-panel.active .output')
    await expect(output).toContainText('[project] auto-promoted 1 Atlas entity', { timeout: 45_000 })
    await expect(page.getByRole('tab', { name: /Domains\s*1/ })).toBeVisible({ timeout: 15_000 })
    await page.getByRole('tab', { name: /Domains\s*1/ }).click()
    await expect(page.locator('#project-explorer-body')).toContainText(entityValue, { timeout: 15_000 })
    await expect(page.locator('#project-explorer-body')).toContainText('Auto-promoted: E2E stream domains')
  })

  test('opens a prefilled Project auto-promote rule from Atlas', async ({ page }, testInfo) => {
    test.setTimeout(60_000)
    const sessionId = await browserSessionId(page)
    const fixture = seedAutoPromoteAtlasEntity(testInfo, { sessionId })
    await openProjectsModal(page)
    await createActiveProject(page, `Atlas Handoff ${Date.now()}`)
    await page.locator('.project-workspace-close').click()
    await expect(page.locator('#project-workspace-overlay')).not.toHaveClass(/\bopen\b/)

    await page.locator('.rail-nav [data-action="atlas"]').click()
    await expectAtlasInteractionReady(page)
    await page.locator('[data-atlas-tab="domain"]').click()
    await expect(page.locator('[data-atlas-tab="domain"]')).toHaveClass(/\bis-active\b/)
    await page.locator('#atlas-search').fill(fixture.entityValue)
    await expect(page.locator('#atlas-list')).toContainText(fixture.entityValue, { timeout: 15_000 })
    await expect(page.locator('#atlas-detail')).toContainText(fixture.entityValue, { timeout: 15_000 })

    await page.locator('#atlas-saved-view-create-rule').click()

    await expect(page.locator('#atlas-overlay')).not.toHaveClass(/\bopen\b/, { timeout: 15_000 })
    await expect(page.locator('#project-workspace-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('[data-project-tab="entities"]')).toHaveClass(/\bis-active\b/)
    const editor = page.locator('#project-explorer-body .project-auto-promote-editor').last()
    await expect(editor).toBeVisible()
    await expect(editor.locator('[data-project-auto-promote-field="name"]')).toHaveValue(
      `Atlas view: ${fixture.entityValue}`,
    )
    await expect(editor.locator('[data-project-auto-promote-field="target_entity_kind"]')).toHaveValue('domain')
    await expect(editor.locator('[data-project-auto-promote-field="match_mode"]')).toHaveValue('contains')
    await expect(editor.locator('[data-project-auto-promote-field="pattern"]')).toHaveValue(fixture.entityValue)
    await expect(editor.locator('[data-project-auto-promote-field="include_suppressed"]')).not.toBeChecked()
  })

  test('imports a small Nuclei JSONL file into Atlas from the browser', async ({ page }) => {
    test.setTimeout(60_000)
    const target = `import-${Date.now()}.atlas-e2e.test`
    const payload = `${JSON.stringify({
      'template-id': 'http/e2e-missing-header',
      'matched-at': `https://${target}/login`,
      info: {
        name: 'E2E Nuclei Header Missing',
        severity: 'medium',
        description: 'Header is missing in the uploaded report.',
      },
      'matcher-name': 'header',
    })}\n`

    await page.locator('.rail-nav [data-action="atlas"]').click()
    await expectAtlasInteractionReady(page)
    await page.locator('#atlas-import-btn').click()
    await expect(page.locator('#atlas-import-overlay')).toHaveClass(/\bopen\b/)
    await page.locator('#atlas-import-format').selectOption('nuclei_jsonl')
    await page.locator('#atlas-import-name').fill('Playwright Nuclei import')
    await page.locator('#atlas-import-file').setInputFiles({
      name: 'nuclei-e2e.jsonl',
      mimeType: 'application/jsonl',
      buffer: Buffer.from(payload, 'utf8'),
    })
    await page.locator('#atlas-import-preview-btn').click()
    await expect(page.locator('#atlas-import-status')).toContainText('Preview ready', { timeout: 15_000 })
    await expect(page.locator('#atlas-import-preview')).toContainText('E2E Nuclei Header Missing')
    await expect(page.locator('[data-atlas-import-option="import_findings"]')).toBeChecked()
    await page.locator('#atlas-import-apply').click()
    await expect(page.locator('#permalink-toast')).toContainText('Atlas import applied', { timeout: 15_000 })
    await expect(page.locator('#atlas-list')).toContainText('E2E Nuclei Header Missing', { timeout: 15_000 })
    await page.locator('#atlas-import-close').click()
    await expect(page.locator('#atlas-import-overlay')).not.toHaveClass(/\bopen\b/)
    const importedFinding = page.locator('.atlas-finding-queue-row', { hasText: 'E2E Nuclei Header Missing' }).first()
    await importedFinding.click()
    await expect(page.locator('#atlas-detail')).toContainText('Import sources', { timeout: 15_000 })
    await expect(page.locator('#atlas-detail')).toContainText('Playwright Nuclei import')
    await expect(page.locator('#atlas-detail')).toContainText('Also seen in Nuclei JSONL import')
  })

  test('creates, edits, downloads, and deletes a project evidence package', async ({ page }, testInfo) => {
    test.setTimeout(60_000)
    await openProjectsModal(page)
    const projectId = await createActiveProject(page, `Playwright Package ${Date.now()}`)
    await linkExternalRunToOpenProject(page, testInfo)

    await switchProjectTab(page, 'packages')
    const packagePresetsResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'GET' && url.pathname === '/projects/package-presets'
    })
    await page.locator('[data-project-action="package-wizard-open"]').click()
    const wizard = page.locator('#project-package-wizard-overlay')
    await expect(wizard).toHaveClass(/\bopen\b/)
    await expect(wizard.locator('.project-package-step.is-active')).toContainText('Preset')
    expect((await packagePresetsResponse).ok()).toBe(true)
    await page.locator('[data-project-package-field="labels"]').fill('handoff, e2e')
    await page.locator('[data-project-package-field="notes"]').fill('Package notes from Playwright')

    await page.locator('[data-project-action="package-wizard-next"]').click()
    await expect(wizard.locator('.project-package-step.is-active')).toContainText('Include')
    await expect(wizard).toContainText('Runs (1)')

    await page.locator('[data-project-action="package-wizard-next"]').click()
    await expect(wizard.locator('.project-package-step.is-active')).toContainText('Metadata')
    await page.locator('[data-project-package-field="name"]').fill('Browser evidence')
    await page.locator('[data-project-package-field="description"]').fill('Package created in a live browser')

    await page.locator('[data-project-action="package-wizard-next"]').click()
    await expect(wizard.locator('.project-package-step.is-active')).toContainText('Preview')
    await expect(page.locator('.project-package-preview-json')).toContainText('"runs": 1')
    await expect(page.locator('.project-package-preview-json')).toContainText('"transcript_run_ids"')

    await page.locator('[data-project-action="package-wizard-next"]').click()
    await expect(wizard).not.toHaveClass(/\bopen\b/)
    await expect(page.locator('#permalink-toast')).toContainText('Package created.')
    const packageRow = page.locator('.project-explorer-item').filter({ hasText: 'Browser evidence' }).first()
    await expect(packageRow).toBeVisible()
    await expect(packageRow).toContainText('handoff')
    await expect(packageRow).toContainText('source: manual')
    await expect(packageRow).toContainText('note')

    await packageRow.locator('[data-project-action="package-edit"]').click()
    await expect(page.locator('#project-entity-editor-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#project-entity-editor-title')).toHaveText('EDIT PACKAGE')
    await page.locator('#project-entity-labels').fill('handoff, approved')
    await page.locator('#project-entity-note').fill('Ready for handoff from Playwright')
    await page.locator('#project-entity-submit').click()
    await expect(page.locator('#project-entity-editor-overlay')).not.toHaveClass(/\bopen\b/)
    await expect(packageRow).toContainText('approved')
    await expect(packageRow).toContainText('note')

    await packageRow.locator('[data-project-action="package-manifest"]').click()
    await expect(page.locator('#project-package-manifest-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#project-package-manifest-summary')).toContainText('Provenance summary')
    await expect(page.locator('#project-package-manifest-summary')).toContainText('manual')
    await expect(page.locator('#project-package-manifest-json')).toContainText('"package_format_version": 2')
    await expect(page.locator('#project-package-manifest-json')).toContainText('"runs": 1')
    await page.locator('.project-package-manifest-close').click()
    await expect(page.locator('#project-package-manifest-overlay')).not.toHaveClass(/\bopen\b/)

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      packageRow.locator('[data-project-action="package-download"]').click(),
    ])
    expect(download.suggestedFilename()).toBe('browser-evidence.zip')

    await packageRow.locator('[data-project-action="package-delete"]').click()
    await expect(page.locator('#confirm-host')).toBeVisible()
    await page.locator('#confirm-host [data-confirm-action-id="delete"]').click()
    await expect(page.locator('#confirm-host')).toBeHidden()
    await expect(packageRow).toHaveCount(0)
    await expect(page.locator('#project-explorer-body')).toContainText('No evidence packages yet.')

    const packages = await page.evaluate(async (id) => {
      const resp = await apiFetch(`/projects/${encodeURIComponent(id)}/packages`, { cache: 'no-store' })
      const data = await resp.json()
      return data.packages || []
    }, projectId)
    expect(packages).toEqual([])
  })

  test('builds a project report preview and export archive', async ({ page }, testInfo) => {
    test.setTimeout(75_000)
    await openProjectsModal(page)
    const projectId = await createActiveProject(page, `Playwright Report ${Date.now()}`)
    const sessionId = await browserSessionId(page)
    seedProjectEvidenceFixture(testInfo, { sessionId, projectId })
    await page.evaluate(async () => {
      if (typeof refreshProjectWorkspace === 'function') await refreshProjectWorkspace()
    })

    await switchProjectTab(page, 'report')
    const reportRoot = page.locator('.project-report-root', {
      has: page.locator('[data-project-report-action="save"]'),
    }).first()
    const engagementName = reportRoot.locator('[data-project-report-metadata="engagement_name"]')
    await expect(engagementName).toBeVisible()
    await expect(reportRoot.locator('.project-report-selection-row')).toHaveCount(3, { timeout: 15_000 })
    await expect(
      reportRoot.getByText(/^Loading (runs|targets|findings|artifacts)\.\.\.$/),
    ).toHaveCount(0, { timeout: 15_000 })
    await engagementName.fill('Browser engagement report')
    await reportRoot.locator('[data-project-report-metadata="date_range"]').fill('2026-06-01 to 2026-06-05')
    await reportRoot.locator('[data-project-report-metadata="executive_summary"]').fill('Executive summary from Playwright.')
    await reportRoot.locator('[data-project-report-metadata="methodology"]').fill('Reviewed linked runs and artifacts.')
    await expect(engagementName).toHaveValue('Browser engagement report')

    const saveResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname === `/projects/${projectId}/report`
    })
    await reportRoot.locator('[data-project-report-action="save"]').click()
    const savedReportResponse = await saveResponse
    expect(savedReportResponse.ok()).toBe(true)
    expect(JSON.parse(savedReportResponse.request().postData() || '{}').draft.metadata.engagement_name)
      .toBe('Browser engagement report')
    await expect(reportRoot.locator('.project-report-message')).toContainText('Report draft saved.')

    await reportRoot.locator('[data-project-report-action="preview"]').click()
    const frame = reportRoot.frameLocator('.project-report-preview-frame')
    await expect(frame.locator('body')).toContainText('Browser engagement report', { timeout: 15_000 })
    await expect(frame.locator('body')).toContainText('Generated by darklab_shell')
    await expect(frame.locator('body')).toContainText('Executive summary from Playwright.')
    await expect(frame.locator('body')).toContainText('artifact evidence from Playwright')

    await page.evaluate(() => {
      window.__reportPrintCalled = false
      window.__reportPrintHtml = ''
      window.open = () => ({
        document: {
          open() {},
          write(html) { window.__reportPrintHtml = String(html || '') },
          close() {},
        },
        focus() {},
        print() { window.__reportPrintCalled = true },
      })
    })
    await reportRoot.locator('[data-project-report-action="print"]').click()
    await expect.poll(() => page.evaluate(() => window.__reportPrintCalled), { timeout: 15_000 }).toBe(true)
    await expect.poll(() => page.evaluate(() => window.__reportPrintHtml)).toContain('Browser engagement report')

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      reportRoot.locator('[data-project-report-action="export"]').click(),
    ])
    expect(download.suggestedFilename()).toMatch(/playwright-report-\d+-engagement-report\.zip/)
    await expect(reportRoot.locator('.project-report-message')).toContainText('Report download started.')
  })

  test('keeps large report selector paging, exclusions, draft reload, and exports stable', async ({ page }, testInfo) => {
    test.setTimeout(120_000)
    await openProjectsModal(page)
    const projectId = await createActiveProject(page, `Playwright Large Report ${Date.now()}`)
    const sessionId = await browserSessionId(page)
    const fixture = seedLargeProjectReportFixture(testInfo, { sessionId, projectId, count: 60 })
    await page.evaluate(async () => {
      if (typeof refreshProjectWorkspace === 'function') await refreshProjectWorkspace()
    })

    await switchProjectTab(page, 'report')
    const reportRoot = page.locator('.project-report-root', {
      has: page.locator('[data-project-report-action="save"]'),
    }).first()
    const editor = reportRoot.locator('.project-report-editor')
    const artifactsGroup = reportRoot.locator('.project-report-selection-group', {
      has: page.locator('h4', { hasText: 'Artifacts' }),
    }).first()
    const artifactFilter = artifactsGroup.locator('[data-project-report-selection-filter="q"]')
    const allArtifacts = artifactsGroup.locator('[data-project-report-action="selection-all"][data-selection-key="artifact_ids"]')
    const noArtifacts = artifactsGroup.locator('[data-project-report-action="selection-none"][data-selection-key="artifact_ids"]')
    const nextArtifacts = artifactsGroup.locator('[data-project-report-action="selection-next"][data-selection-key="artifact_ids"]')
    const prevArtifacts = artifactsGroup.locator('[data-project-report-action="selection-prev"][data-selection-key="artifact_ids"]')

    async function expectReportEditorStayedPut(before) {
      const scrollAnchorTolerance = 360
      await expect.poll(async () => editor.evaluate((node) => node.scrollTop), { timeout: 5_000 })
        .toBeGreaterThanOrEqual(Math.max(0, before - scrollAnchorTolerance))
    }

    async function clickAndKeepScroll(locator) {
      await expect(locator).toBeVisible({ timeout: 15_000 })
      await locator.click({ trial: true })
      const before = await editor.evaluate((node) => node.scrollTop)
      await locator.click()
      await expectReportEditorStayedPut(before)
    }

    await expect(artifactFilter).toBeVisible({ timeout: 20_000 })
    await expect(artifactsGroup.locator('.project-report-selection-row')).toHaveCount(50, { timeout: 15_000 })
    await expect(nextArtifacts).toBeEnabled()
    const filteredArtifactsResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.ok()
        && url.pathname === `/projects/${projectId}/artifacts`
        && url.searchParams.get('offset') === '0'
        && url.searchParams.get('q') === fixture.artifactFilterQuery
    })
    await artifactFilter.fill(fixture.artifactFilterQuery)
    await filteredArtifactsResponse
    await expect(artifactFilter).toHaveValue(fixture.artifactFilterQuery)
    await expect(artifactsGroup.locator('.project-report-selection-summary')).toContainText('1-50 of 60', { timeout: 15_000 })
    await expect(artifactsGroup).toContainText('large-evidence-059.txt')

    await clickAndKeepScroll(noArtifacts)
    await expect(artifactsGroup.locator('.project-report-selection-summary')).toContainText('0 selected')
    await clickAndKeepScroll(allArtifacts)
    await expect(artifactsGroup.locator('.project-report-selection-summary')).toContainText('60 selected')

    await clickAndKeepScroll(nextArtifacts)
    await expect(artifactsGroup.locator('.project-report-selection-summary')).toContainText('51-60 of 60', { timeout: 15_000 })
    const excludedRow = artifactsGroup.locator('.project-report-selection-row', { hasText: 'large-evidence-005.txt' })
    await expect(excludedRow).toBeVisible()
    const beforeToggle = await editor.evaluate((node) => node.scrollTop)
    await excludedRow.locator('[data-project-report-selection="artifact_ids"]').uncheck()
    await expectReportEditorStayedPut(beforeToggle)

    await clickAndKeepScroll(prevArtifacts)
    await expect(artifactsGroup.locator('.project-report-selection-summary')).toContainText('1-50 of 60', { timeout: 15_000 })

    await reportRoot.locator('[data-project-report-metadata="engagement_name"]').fill('Large browser selector report')
    const saveResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname === `/projects/${projectId}/report`
    })
    await reportRoot.locator('[data-project-report-action="save"]').click()
    const savedReportResponse = await saveResponse
    expect(savedReportResponse.ok()).toBe(true)
    const savedReportBody = JSON.parse(savedReportResponse.request().postData() || '{}')
    expect(savedReportBody.draft.selection_filters.artifact_ids.q).toBe(fixture.artifactFilterQuery)
    expect(savedReportBody.draft.selection_exclude_ids.artifact_ids).toHaveLength(1)
    await expect(reportRoot.locator('.project-report-message')).toContainText('Report draft saved.')

    await reportRoot.locator('[data-project-report-action="reload"]').click()
    await expect(artifactsGroup.locator('.project-report-selection-summary')).toContainText('59 selected', {
      timeout: 15_000,
    })
    await clickAndKeepScroll(nextArtifacts)
    await expect(excludedRow.locator('[data-project-report-selection="artifact_ids"]')).not.toBeChecked()

    await reportRoot.locator('[data-project-report-action="preview"]').click()
    const frame = reportRoot.frameLocator('.project-report-preview-frame')
    await expect(frame.locator('body')).toContainText('Large browser selector report', { timeout: 20_000 })
    await expect(frame.locator('body')).toContainText(fixture.includedArtifactText)
    await expect(frame.locator('body')).not.toContainText(fixture.excludedArtifactText)

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      reportRoot.locator('[data-project-report-action="export"]').click(),
    ])
    const archiveText = readReportArchiveText(await download.path())
    expect(archiveText).toContain(fixture.includedArtifactText)
    expect(archiveText).not.toContain(fixture.excludedArtifactText)
  })

  test('edits finding and artifact metadata and previews project artifacts', async ({ page }, testInfo) => {
    test.setTimeout(60_000)
    await openProjectsModal(page)
    const projectId = await createActiveProject(page, `Playwright Evidence ${Date.now()}`)
    const sessionId = await page.evaluate(() => (
      typeof SESSION_ID === 'string' && SESSION_ID
        ? SESSION_ID
        : localStorage.getItem('session_id')
    ))
    const fixture = seedProjectEvidenceFixture(testInfo, { sessionId, projectId })

    await page.locator('.project-workspace-close').click()
    await expect(page.locator('#project-workspace-overlay')).not.toHaveClass(/\bopen\b/)
    await openProjectsModal(page)

    await switchProjectTab(page, 'findings')
    const findingRow = page.locator('.project-explorer-item').filter({ hasText: '80/tcp open http' }).first()
    await expect(findingRow).toBeVisible()
    await expect(page.locator('#project-explorer-body')).not.toContainText('Loading project findings')
    await findingRow.locator('[data-project-action="edit-finding-metadata"]').click()
    await expect(page.locator('#project-entity-editor-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#project-entity-editor-title')).toHaveText('EDIT FINDING')
    await page.locator('#project-entity-labels').fill('finding, triaged')
    await page.locator('#project-entity-note').fill('Finding note from Playwright')
    await page.locator('#project-entity-submit').click()
    await expect(page.locator('#project-entity-editor-overlay')).not.toHaveClass(/\bopen\b/, { timeout: 15_000 })
    await expectEntityMetadata(page, 'finding', fixture.findingId, {
      labels: ['finding', 'triaged'],
      note: 'Finding note from Playwright',
    })
    await expect(findingRow).toContainText('triaged', { timeout: 15_000 })
    await expect(findingRow).toContainText('note')

    await switchProjectTab(page, 'artifacts')
    const artifactRow = page.locator('.project-explorer-item').filter({ hasText: 'evidence.txt' }).first()
    await expect(artifactRow).toBeVisible()
    await artifactRow.locator('[data-project-action="edit-artifact-metadata"]').click()
    await expect(page.locator('#project-entity-editor-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#project-entity-editor-title')).toHaveText('EDIT ARTIFACT')
    await page.locator('#project-entity-labels').fill('evidence, reviewed')
    await page.locator('#project-entity-note').fill('Artifact note from Playwright')
    await page.locator('#project-entity-submit').click()
    await expect(page.locator('#project-entity-editor-overlay')).not.toHaveClass(/\bopen\b/, { timeout: 15_000 })
    await expectEntityMetadata(page, 'run_file_artifact', fixture.artifactId, {
      labels: ['evidence', 'reviewed'],
      note: 'Artifact note from Playwright',
    })
    await expect(artifactRow).toContainText('reviewed', { timeout: 15_000 })
    await expect(artifactRow).toContainText('note')

    await artifactRow.locator('[data-project-action="artifact-preview"]').click()
    await expect(page.locator('#workspace-viewer-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#workspace-viewer-title')).toHaveText(fixture.workspacePath)
    await expect(page.locator('#workspace-viewer-text')).toContainText('artifact evidence from Playwright')
    await page.locator('#workspace-close-viewer-btn').click()
    await expect(page.locator('#workspace-viewer-overlay')).not.toHaveClass(/\bopen\b/)

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      artifactRow.locator('[data-project-action="artifact-download"]').click(),
    ])
    expect(download.suggestedFilename()).toBe('evidence.txt')

    const persisted = await page.evaluate(async ({ findingId, artifactId }) => {
      const [findingLabelsResp, findingNoteResp, artifactLabelsResp, artifactNoteResp] = await Promise.all([
        apiFetch(`/entities/finding/${encodeURIComponent(findingId)}/labels`, { cache: 'no-store' }),
        apiFetch(`/entities/finding/${encodeURIComponent(findingId)}/note`, { cache: 'no-store' }),
        apiFetch(`/entities/run_file_artifact/${encodeURIComponent(artifactId)}/labels`, { cache: 'no-store' }),
        apiFetch(`/entities/run_file_artifact/${encodeURIComponent(artifactId)}/note`, { cache: 'no-store' }),
      ])
      const [findingLabels, findingNote, artifactLabels, artifactNote] = await Promise.all([
        findingLabelsResp.json(),
        findingNoteResp.json(),
        artifactLabelsResp.json(),
        artifactNoteResp.json(),
      ])
      return {
        findingLabels: (findingLabels.labels || []).map((label) => label.label),
        findingNote: findingNote.note?.body || '',
        artifactLabels: (artifactLabels.labels || []).map((label) => label.label),
        artifactNote: artifactNote.note?.body || '',
      }
    }, fixture)
    expect(persisted.findingLabels).toEqual(expect.arrayContaining(['finding', 'triaged']))
    expect(persisted.findingNote).toBe('Finding note from Playwright')
    expect(persisted.artifactLabels).toEqual(expect.arrayContaining(['evidence', 'reviewed']))
    expect(persisted.artifactNote).toBe('Artifact note from Playwright')

    await switchProjectTab(page, 'runs')
    const evidenceRunRow = page.locator('.project-explorer-item').filter({ hasText: 'nmap -oN reports/evidence.txt' }).first()
    await expect(evidenceRunRow).toBeVisible()
    await expect(page.locator('#project-explorer-body')).not.toContainText('No linked runs yet.')
    await evidenceRunRow.locator('[data-project-action="filter-run-findings"]').click()
    await expect(page.locator('.project-explorer-tab.is-active')).toContainText('Findings')
    await expect(page.locator('[data-project-run-filter-clear]')).toContainText('run:')
    await expect.poll(async () => page.locator('#project-explorer-body').evaluate((body) => {
      const children = [...body.children].map((child) => child.className || '')
      return children.findIndex((className) => String(className).includes('project-explorer-tabs'))
        < children.findIndex((className) => String(className).includes('project-explorer-filter-panel'))
    })).toBe(true)
    await expect(page.locator('.project-explorer-item').filter({ hasText: '80/tcp open http' }).first()).toBeVisible()

    await switchProjectTab(page, 'runs')
    await page.locator('[data-project-filter-clear-all]').click()
    await expect(evidenceRunRow).toBeVisible()
    await evidenceRunRow.locator('[data-project-action="filter-run-artifacts"]').click()
    await expect(page.locator('.project-explorer-tab.is-active')).toContainText('Artifacts')
    await expect(page.locator('[data-project-run-filter-clear]')).toContainText('run:')
    await expect(page.locator('.project-explorer-item').filter({ hasText: 'evidence.txt' }).first()).toBeVisible()

    await switchProjectTab(page, 'runs')
    await page.locator('[data-project-filter-clear-all]').click()
    await evidenceRunRow.locator('[data-project-action="unlink-run"]').click()
    await expect(page.locator('#confirm-host')).toBeVisible()
    await page.locator('#confirm-host [data-confirm-action-id="remove"]').click()
    await expect(page.locator('#confirm-host')).toBeHidden()
    await expect(evidenceRunRow).toHaveCount(0)
    await expect(page.locator('#project-explorer-body')).toContainText('No linked runs yet.')
  })
})

test.describe('workspace modal', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('creates, views, edits, downloads, and consumes session files', async ({ page }) => {
    test.setTimeout(60_000)
    await expect(page.locator('.rail-nav [data-action="workspace"] .rail-nav-label')).toHaveText('files')
    await page.locator('.rail-nav [data-action="workspace"]').click()

    await expect(page.locator('#workspace-overlay')).toHaveClass(/open/)
    await expect(page.locator('#workspace-modal .faq-title')).toHaveText('FILES')
    await expect(page.locator('#workspace-summary')).toContainText('0 / 100 files')
    await expect(page.locator('#workspace-refresh-btn')).toHaveAttribute('aria-label', 'Refresh files')
    await expect(page.locator('#workspace-editor')).not.toBeVisible()
    await expect(page.locator('label[for="workspace-path-input"]')).toHaveText('File Name')

    await page.locator('#workspace-new-btn').click()
    await expect(page.locator('#workspace-editor')).toBeVisible()
    const pathInput = page.locator('#workspace-path-input')
    const textInput = page.locator('#workspace-text-input')
    await expect(pathInput).toBeVisible()
    await expect(textInput).toBeVisible()
    await pathInput.fill('targets.txt')
    await expect(pathInput).toHaveValue('targets.txt')
    await textInput.click()
    await textInput.fill('darklab.sh\n')
    await expect(textInput).toHaveValue('darklab.sh\n')
    await saveWorkspaceEditor(page)

    const row = page.locator('.workspace-file-row').filter({ hasText: 'targets.txt' })
    await expect(row).toBeVisible()
    await expect(page.locator('#workspace-summary')).toContainText('1 / 100 files')

    await row.locator('[data-workspace-action="view"]').click()
    await expect(page.locator('#workspace-viewer')).toBeVisible()
    await expect(page.locator('#workspace-viewer-title')).toHaveText('targets.txt')
    await expect(page.locator('#workspace-viewer-text .workspace-line-text').first()).toHaveText('darklab.sh')

    await page.locator('#workspace-close-viewer-btn').click()
    await expect(page.locator('#workspace-viewer')).not.toBeVisible()
    await row.locator('[data-workspace-action="edit"]').click()
    await expect(page.locator('#workspace-editor')).toBeVisible()
    await page.locator('#workspace-text-input').fill('darklab.sh\nip.darklab.sh\n')
    await saveWorkspaceEditor(page)
    await row.locator('[data-workspace-action="view"]').click()
    await expect(page.locator('#workspace-viewer-text')).toContainText('ip.darklab.sh')

    await page.locator('#workspace-close-viewer-btn').click()
    await expect(page.locator('#workspace-viewer')).not.toBeVisible()
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      row.locator('[data-workspace-action="download"]').click(),
    ])
    expect(download.suggestedFilename()).toBe('targets.txt')

    await page.locator('#workspace-new-folder-btn').click()
    await page.locator('#confirm-host .form-input').fill('moved')
    await confirmWorkspaceAction(page, 'create')
    await expect(page.locator('#workspace-breadcrumbs')).toContainText('Files/moved', {
      timeout: 15_000,
    })
    await page.locator('#workspace-breadcrumbs [data-workspace-dir=""]').click()
    await expect(page.locator('#workspace-breadcrumbs')).toHaveText('Files')

    await row.locator('[data-workspace-action="move"]').click()
    await page.locator('#confirm-host .form-input').fill('moved')
    await confirmWorkspaceAction(page, 'move')
    await expect(row).toHaveCount(0)
    await page.locator('.workspace-folder-row').filter({ hasText: 'moved' }).locator('.workspace-file-name').click()
    await expect(page.locator('.workspace-file-row').filter({ hasText: 'targets.txt' })).toBeVisible()

    await page.locator('.workspace-close').click()
    await expect(page.locator('#workspace-overlay')).not.toHaveClass(/open/)

    await runCommand(page, 'cat moved/targets.txt')
    await expect(page.locator('.tab-panel.active .output')).toContainText('darklab.sh')
    await expect(page.locator('.tab-panel.active .output')).toContainText('ip.darklab.sh')

    await runCommand(page, 'mv moved/targets.txt targets.txt')
    await expect(page.locator('.tab-panel.active .output')).toContainText('file: moved moved/targets.txt to targets.txt')
    await runCommand(page, 'cat targets.txt')
    await expect(page.locator('.tab-panel.active .output')).toContainText('darklab.sh')
  })

  test('navigates nested file output folders and exposes viewer actions', async ({ page }) => {
    test.setTimeout(90_000)
    await page.locator('.rail-nav [data-action="workspace"]').click()
    await expect(page.locator('#workspace-overlay')).toHaveClass(/open/)

    await page.locator('#workspace-new-folder-btn').click()
    await page.locator('#confirm-host .form-input').fill('reports')
    await confirmWorkspaceAction(page, 'create')
    await expect(page.locator('#workspace-breadcrumbs')).toContainText('Files/reports', {
      timeout: 15_000,
    })
    await expect(page.locator('.workspace-empty')).toHaveText('This folder is empty.')

    await page.locator('#workspace-new-btn').click()
    await expect(page.locator('#workspace-path-input')).toHaveValue('')
    await page.locator('#workspace-cancel-edit-btn').click()

    await page.locator('.workspace-folder-row').filter({ hasText: '..' }).locator('[data-workspace-action="open-folder"]').click()
    await expect(page.locator('#workspace-breadcrumbs')).toHaveText('Files')
    await expect(page.locator('.workspace-folder-row').filter({ hasText: 'reports' })).toBeVisible()

    await page.locator('.workspace-folder-row').filter({ hasText: 'reports' }).locator('.workspace-file-name').click()
    await expect(page.locator('#workspace-breadcrumbs')).toContainText('Files/reports')

    await page.locator('#workspace-breadcrumbs [data-workspace-dir=""]').click()
    await expect(page.locator('.workspace-folder-row').filter({ hasText: 'reports' })).toBeVisible()

    await page.locator('#workspace-new-btn').click()
    await page.locator('#workspace-path-input').fill('amass-viz/amass.html')
    await page.locator('#workspace-text-input').fill('<html>amass viz</html>\n')
    await saveWorkspaceEditor(page)

    const folder = page.locator('.workspace-folder-row').filter({ hasText: 'amass-viz' })
    await expect(folder).toBeVisible()
    await expect(page.locator('.workspace-file-row').filter({ hasText: 'amass.html' })).toHaveCount(0)

    await folder.locator('.workspace-file-name').click()
    await expect(page.locator('#workspace-breadcrumbs')).toContainText('Files/amass-viz')

    const file = page.locator('.workspace-file-row').filter({ hasText: 'amass.html' })
    await expect(file).toBeVisible()
    // Pre-locate and wait for the action button so the click doesn't burn the
    // test budget in its hidden auto-wait when the row renders before its
    // action buttons mount on slow CI runners.
    const viewBtn = file.locator('[data-workspace-action="view"]')
    await expect(viewBtn).toBeVisible({ timeout: 15_000 })
    await viewBtn.click()

    await expect(page.locator('#workspace-viewer')).toBeVisible()
    await expect(page.locator('#workspace-viewer-title')).toHaveText('amass-viz/amass.html')
    await expect(page.locator('#workspace-viewer-text')).toContainText('amass viz')
    await expect(page.locator('#workspace-viewer [data-workspace-viewer-action="edit"]')).toBeVisible()
    await expect(page.locator('#workspace-viewer [data-workspace-viewer-action="download"]')).toBeVisible()
    await expect(page.locator('#workspace-viewer [data-workspace-viewer-action="delete"]')).toBeVisible()

    await page.locator('#workspace-close-viewer-btn').click()
    await expect(page.locator('#workspace-viewer')).not.toBeVisible()
    await page.locator('#workspace-breadcrumbs [data-workspace-dir=""]').click()
    await expect(folder).toBeVisible()
  })
})

test.describe('workflows modal', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await ensurePromptReady(page)
  })

  async function openWorkflowsModal(page) {
    await page.keyboard.press('Alt+g')
    await expect(page.locator('#workflows-overlay')).toHaveClass(/\bopen\b/)
    const firstCard = page.locator('#workflows-overlay .workflow-card').first()
    await expect(firstCard).toBeVisible()
    await expect(firstCard.locator('.workflow-input-control')).toBeVisible()
    return firstCard
  }

  async function saveWorkflowEditorAndWait(page, method) {
    const saveResponse = page.waitForResponse((response) => (
      response.url().includes('/session/workflows')
      && response.request().method() === method
    ))
    const catalogRendered = page.evaluate(() => new Promise((resolve) => {
      if (typeof onUiEvent === 'function') {
        const off = onUiEvent('app:workflows-rendered', () => {
          off()
          resolve(true)
        })
        return
      }
      document.addEventListener('app:workflows-rendered', () => resolve(true), { once: true })
    }))
    await page.locator('#workflow-editor-save-btn').click()
    const response = await saveResponse
    expect(response.ok()).toBe(true)
    const data = await response.json()
    await catalogRendered
    await expect(page.locator('#workflow-editor-overlay')).not.toHaveClass(/\bopen\b/)
    return data.workflow || null
  }

  test('input-driven workflows render prefilled form fields and runnable rendered steps', async ({ page }) => {
    const firstCard = await openWorkflowsModal(page)
    const input = firstCard.locator('.workflow-input-control')
    await expect(input).toHaveCount(1)
    await expect(input).toHaveValue('darklab.sh')
    const firstStep = firstCard.locator('.workflow-step').first()
    await expect(firstStep.locator('.workflow-step-cmd')).toBeVisible()
    const runBtn = firstStep.locator('.workflow-step-run')
    await expect(runBtn).toBeVisible()
    await expect(runBtn).toHaveText('▶')
    await expect(runBtn).toBeEnabled()
    await expect(firstCard.locator('.workflow-run-all')).toBeEnabled()
    await expect(firstStep.locator('.workflow-step-cmd')).toContainText('dig darklab.sh A')
  })

  test('step layout is a two-row grid with chip on row 1 and note on row 2', async ({ page }) => {
    const firstCard = await openWorkflowsModal(page)
    const firstStep = firstCard.locator('.workflow-step').first()
    const layout = await firstStep.evaluate((el) => ({
      display: getComputedStyle(el).display,
      children: Array.from(el.children).map((c) => c.className),
    }))
    expect(layout.display).toBe('grid')
    expect(layout.children[0]).toContain('workflow-step-main')
    expect(layout.children[1]).toContain('workflow-step-note')
  })

  test('clearing a required workflow input disables step actions until the value is restored', async ({ page }) => {
    const firstCard = await openWorkflowsModal(page)
    const input = firstCard.locator('.workflow-input-control')
    const runBtn = firstCard.locator('.workflow-step').first().locator('.workflow-step-run')
    const runAllBtn = firstCard.locator('.workflow-run-all')
    await input.fill('')
    await expect(runBtn).toBeDisabled()
    await expect(runAllBtn).toBeDisabled()
    await expect(firstCard.locator('.workflow-step').first().locator('.workflow-step-cmd')).toContainText('{{domain}}')
    await input.fill('example.com')
    await expect(runBtn).toBeEnabled()
    await expect(runAllBtn).toBeEnabled()
  })

  test('editing workflow inputs rerenders steps and step run submits the rendered command', async ({ page }) => {
    const firstCard = await openWorkflowsModal(page)
    const input = firstCard.locator('.workflow-input-control')
    await input.fill('example.com')
    await expect(input).toHaveValue('example.com')
    const runBtn = firstCard.locator('.workflow-step').first().locator('.workflow-step-run')
    await expect(runBtn).toBeEnabled()
    const cmd = await runBtn.getAttribute('data-workflow-step-cmd')
    expect(cmd).toBe('dig example.com A')
    await runBtn.click()
    await expect(page.locator('#workflows-overlay')).not.toHaveClass(/\bopen\b/)
    await expect(page.locator('body')).toContainText(cmd)
  })

  test('rendered workflow chips load interpolated commands into the prompt', async ({ page }) => {
    const firstCard = await openWorkflowsModal(page)
    const input = firstCard.locator('.workflow-input-control')
    await input.fill('example.com')
    await expect(input).toHaveValue('example.com')
    const chip = firstCard.locator('.workflow-step').nth(1).locator('.workflow-step-cmd')
    await expect(chip).toContainText('dig example.com NS')
    await expect(chip).toHaveAttribute('data-faq-command', 'dig example.com NS')
    await chip.click()
    await expect(page.locator('#cmd')).toHaveValue('dig example.com NS ')
  })

  test('workflow inputs persist when the workflow modal is reopened', async ({ page }) => {
    const firstCard = await openWorkflowsModal(page)
    const input = firstCard.locator('.workflow-input-control')
    await input.fill('persist.example')
    await page.locator('.workflows-close').click()
    await expect(page.locator('#workflows-overlay')).not.toHaveClass(/\bopen\b/)
    await openWorkflowsModal(page)
    await expect(page.locator('.workflow-card').first().locator('.workflow-input-control')).toHaveValue('persist.example')
    await expect(page.locator('.workflow-card').first().locator('.workflow-step').first().locator('.workflow-step-cmd')).toContainText('dig persist.example A')
  })

  test('recent execution status can be canceled and restored after reopening', async ({ page }) => {
    let canceled = false
    let listReads = 0
    await page.route('**/workflow-executions?*', async (route) => {
      listReads += 1
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          executions: [{
            id: 'wfx_e2e_active',
            title: 'Resolve and scan',
            status: canceled ? 'canceled' : 'running',
            current_step_id: canceled ? '' : 'scan',
            created: '2026-07-12 10:00:00',
            finished: canceled ? '2026-07-12 10:00:05' : null,
            steps: [
              {
                step_id: 'resolve',
                status: 'succeeded',
                run_id: 'run-resolve',
                capture_names: ['resolved_ip'],
                selected_transition: 'scan',
                transition_reason: 'success',
              },
              {
                step_id: 'scan',
                status: canceled ? 'canceled' : 'running',
                run_id: canceled ? '' : 'run-scan',
                capture_names: [],
              },
            ],
          }],
        }),
      })
    })
    await page.route('**/workflow-executions/wfx_e2e_active/cancel', async (route) => {
      canceled = true
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ execution: { id: 'wfx_e2e_active', status: 'canceled' } }),
      })
    })

    await openWorkflowsModal(page)
    await page.locator('[data-workflows-view="executions"]').click()
    const execution = page.locator('[data-workflow-execution-id="wfx_e2e_active"]')
    await expect(execution).toContainText('Current step: scan')
    await expect(execution).toContainText('Captured: resolved_ip')
    await expect(execution).toContainText('to scan (success)')
    await expect(execution.getByRole('button', { name: 'Attach to run run-scan' })).toBeVisible()
    await execution.getByRole('button', { name: 'Cancel Resolve and scan' }).click()
    await page.getByRole('button', { name: 'Cancel execution' }).click()

    await expect(execution).toContainText('Canceled')
    await expect(execution.getByRole('button', { name: 'Cancel Resolve and scan' })).toHaveCount(0)
    await page.locator('.workflows-close').click()
    await openWorkflowsModal(page)
    await page.locator('[data-workflows-view="executions"]').click()
    await expect(page.locator('[data-workflow-execution-id="wfx_e2e_active"]')).toContainText('Canceled')
    expect(listReads).toBeGreaterThan(1)
  })

  test('runs a real capture-fed playbook and reopens its linked run', async ({ page }) => {
    const sessionId = await browserSessionId(page)
    const title = `Live capture playbook ${Date.now()}`
    const workflowResponse = await page.request.post('/session/workflows', {
      headers: { 'X-Session-ID': sessionId },
      data: {
        version: 2,
        id: `live_capture_${Date.now()}`,
        title,
        inputs: [],
        steps: [
          {
            id: 'read_help',
            cmd: 'help',
            captures: [{
              name: 'help_heading',
              source: 'first_nonempty_line',
              required: true,
            }],
            next: { success: 'inspect_help', failure: 'stop' },
          },
          {
            id: 'inspect_help',
            cmd: 'help {{help_heading}}',
            next: {
              codes: { 1: 'complete' },
              success: 'complete',
              failure: 'stop',
            },
          },
        ],
      },
    })
    expect(workflowResponse.ok()).toBe(true)
    await page.reload()

    await page.keyboard.press('Alt+g')
    await expect(page.locator('#workflows-overlay')).toHaveClass(/\bopen\b/)
    await page.locator('.workflow-catalog-item', { hasText: title }).click()
    const workflowCard = page.locator('.workflow-card', { hasText: title })
    await expect(workflowCard).toBeVisible()
    await workflowCard.locator('.workflow-run-all').click()
    await expect(page.locator('[data-workflows-view="executions"]')).toHaveAttribute('aria-selected', 'true')
    const execution = page.locator('[data-workflow-execution-id]', { hasText: title }).first()
    await expect(execution).toContainText('Completed', { timeout: 15_000 })
    await expect(execution).toContainText('Captured: help_heading')
    await expect(execution).toContainText('to inspect_help (success)')

    await page.locator('.workflows-close').click()
    await page.keyboard.press('Alt+g')
    await expect(page.locator('#workflows-overlay')).toHaveClass(/\bopen\b/)
    await page.locator('[data-workflows-view="executions"]').click()
    const restored = page.locator('[data-workflow-execution-id]', { hasText: title }).first()
    await expect(restored).toContainText('Completed')
    const openRun = restored.getByRole('button', { name: /Open run/ }).last()
    await expect(openRun).toBeVisible()
    await openRun.click()
    await expect(page.locator('#history-run-overlay')).toBeVisible()
    await expect(page.locator('#history-run-modal')).toContainText('RUN DETAILS')
  })

  test('authors and runs an exact exit-code branch through the workflow editor', async ({ page }) => {
    await openWorkflowsModal(page)
    const title = `Exact exit branch ${Date.now()}`
    await page.locator('#workflow-new-btn').click()
    await page.locator('#workflow-editor-title-input').fill(title)
    const firstStep = page.locator('[data-workflow-editor-step]').first()
    await firstStep.locator('.workflow-editor-step-command').fill('intel unsupported value')
    await page.locator('#workflow-editor-add-step').click()
    const matchedStep = page.locator('[data-workflow-editor-step]').nth(1)
    await matchedStep.locator('.workflow-editor-step-id').fill('matched')
    await matchedStep.locator('.workflow-editor-step-command').fill('help')
    await firstStep.locator('.workflow-editor-add-exit-code').click()
    const exactRoute = firstStep.locator('[data-workflow-editor-exit-code]').first()
    await exactRoute.locator('.workflow-editor-exit-code').fill('1')
    await exactRoute.locator('.workflow-editor-exit-code-destination').selectOption('matched')

    const createdWorkflow = await saveWorkflowEditorAndWait(page, 'POST')
    expect(createdWorkflow?.steps?.[0]?.next?.codes).toEqual({ 1: 'matched' })
    const workflowCard = page.locator(
      `#workflows-overlay .workflow-card[data-workflow-id="${createdWorkflow.id}"]`,
    )
    await expect(workflowCard).toBeVisible()
    await workflowCard.locator('.workflow-run-all').click()
    await expect(page.locator('[data-workflows-view="executions"]')).toHaveAttribute('aria-selected', 'true')
    const execution = page.locator('[data-workflow-execution-id]', { hasText: title }).first()
    await expect(execution).toContainText('Completed', { timeout: 15_000 })
    await expect(execution).toContainText('to matched (exit code:1)')
  })

  test('creates, edits, and deletes a user workflow from the workflows modal', async ({ page }) => {
    // Two save-and-render cycles plus modal open/close exceeds the default 30s
    // budget on slow CI runners; give the test enough headroom.
    test.setTimeout(60_000)
    await openWorkflowsModal(page)

    await expect(page.locator('#workflow-new-btn')).toHaveText('New Workflow')
    await page.locator('#workflow-new-btn').click()
    await expect(page.locator('#workflow-editor-overlay')).toHaveClass(/\bopen\b/)
    await page.locator('#workflow-editor-title-input').fill('Saved Whois')
    await page.locator('#workflow-editor-add-parameter').click()
    const parameter = page.locator('[data-workflow-editor-parameter]').first()
    await parameter.locator('.workflow-editor-parameter-id').fill('domain')
    await parameter.locator('.workflow-editor-parameter-label').fill('Domain')
    await parameter.locator('.workflow-editor-parameter-type').selectOption('domain')
    await parameter.locator('.workflow-editor-parameter-required').check()
    await parameter.locator('.workflow-editor-parameter-sensitive').check()
    const firstEditorStep = page.locator('[data-workflow-editor-step]').first()
    await firstEditorStep.locator('.workflow-editor-step-command').fill('whois {{domain}}')
    await firstEditorStep.locator('.workflow-editor-step-note').fill('Lookup registration')
    await firstEditorStep.locator('.workflow-editor-add-capture').click()
    await firstEditorStep.locator('.workflow-editor-capture-name').fill('registration_line')
    await firstEditorStep.locator('.workflow-editor-capture-required-input').check()
    await page.locator('#workflow-editor-add-step').click()
    const secondEditorStep = page.locator('[data-workflow-editor-step]').nth(1)
    await secondEditorStep.locator('.workflow-editor-step-id').fill('inspect')
    await secondEditorStep.locator('.workflow-editor-step-command').fill('printf %s {{registration_line}}')
    await firstEditorStep.locator('.workflow-editor-add-exit-code').click()
    const exactRoute = firstEditorStep.locator('[data-workflow-editor-exit-code]').first()
    await exactRoute.locator('.workflow-editor-exit-code').fill('2')
    await exactRoute.locator('.workflow-editor-exit-code-destination').selectOption('inspect')
    const createdWorkflow = await saveWorkflowEditorAndWait(page, 'POST')
    expect(createdWorkflow?.id).toBeTruthy()
    expect(createdWorkflow?.version).toBe(2)
    expect(createdWorkflow?.inputs?.[0]).toMatchObject({
      id: 'domain',
      type: 'domain',
      required: true,
      sensitive: true,
    })
    expect(createdWorkflow?.steps?.[0]).toMatchObject({
      id: 'step_1',
      captures: [{ name: 'registration_line', source: 'first_nonempty_line', required: true }],
      next: { codes: { 2: 'inspect' }, success: 'inspect', failure: 'stop' },
    })
    expect(createdWorkflow?.steps?.[1]).toMatchObject({
      id: 'inspect',
      next: { success: 'complete', failure: 'stop' },
    })

    const userCard = page.locator(
      `#workflows-overlay .workflow-card.is-user-workflow[data-workflow-id="${createdWorkflow.id}"]`,
    )
    await expect(userCard).toHaveClass(/\bis-user-workflow\b/)
    await expect(userCard.locator('.workflow-title')).toHaveText('Saved Whois')
    await expect(userCard.locator('.workflow-edit-btn')).toBeVisible()
    await expect(userCard.locator('.workflow-step-cmd').first()).toContainText('whois {{domain}}')

    const editorExecution = {
      id: 'wfx_editor_e2e',
      title: 'Saved Whois',
      status: 'running',
      current_step_id: 'step_1',
      created: '2026-07-13 12:00:00',
      steps: [],
    }
    await page.route('**/workflow-executions**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ executions: [editorExecution] }),
        })
        return
      }
      if (route.request().method() !== 'POST') return route.fallback()
      const request = route.request().postDataJSON()
      expect(request).toMatchObject({
        workflow_id: createdWorkflow.id,
        inputs: { domain: 'example.com' },
      })
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({
          execution: editorExecution,
          launch: null,
        }),
      })
    })
    await userCard.locator('[data-workflow-input-id="domain"]').fill('example.com')
    await userCard.locator('.workflow-run-all').click()
    await expect(page.locator('[data-workflows-view="executions"]')).toHaveAttribute('aria-selected', 'true')
    await expect(page.locator('[data-workflow-execution-id="wfx_editor_e2e"]')).toBeVisible()
    await expect(page.locator('.tab-panel.active .output')).not.toContainText('wfx_editor_e2e')

    await page.locator('[data-workflows-view="workflows"]').click()
    await userCard.locator('.workflow-edit-btn').click()
    await expect(page.locator('#workflow-editor-title')).toHaveText('EDIT WORKFLOW')
    await expect(page.locator('.workflow-editor-parameter-id').first()).toHaveValue('domain')
    await expect(page.locator('.workflow-editor-parameter-sensitive').first()).toBeChecked()
    await expect(page.locator('.workflow-editor-step-id').first()).toHaveValue('step_1')
    await expect(page.locator('.workflow-editor-capture-name').first()).toHaveValue('registration_line')
    await expect(page.locator('.workflow-editor-exit-code').first()).toHaveValue('2')
    await expect(page.locator('.workflow-editor-exit-code-destination').first()).toHaveValue('inspect')
    await page.locator('.workflow-editor-remove-exit-code').first().click()
    await page.locator('.workflow-editor-step-command').first().fill('dig {{domain}} A')
    const updatedWorkflow = await saveWorkflowEditorAndWait(page, 'PUT')
    expect(updatedWorkflow?.steps?.[0]?.next?.codes).toBeUndefined()

    await expect(userCard.locator('.workflow-step-cmd').first()).toContainText('dig {{domain}} A')

    const deleteResponse = page.waitForResponse((response) => (
      response.url().includes(`/session/workflows/${createdWorkflow.id}`)
      && response.request().method() === 'DELETE'
    ))
    await userCard.locator('.workflow-delete-btn').click()
    await expect(page.locator('#confirm-host')).toContainText('Delete workflow "Saved Whois"?')
    await page.locator('[data-confirm-action-id="delete"]').click()
    expect((await deleteResponse).ok()).toBe(true)
    await expect(page.locator('#workflows-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#workflows-overlay .workflow-card')).toBeVisible()
    await expect(page.locator('#workflows-panel-workflows')).not.toContainText('Saved Whois')
    await expect(page.locator('#rail-workflows-list .rail-item', { hasText: 'Saved Whois' })).toHaveCount(0)
  })

  test('rail workflow plus opens the new workflow editor without toggling the section', async ({ page }) => {
    const section = page.locator('#rail-section-workflows')
    if (await section.evaluate((node) => node.classList.contains('closed'))) {
      await page.locator('#rail-workflows-header').click()
    }
    await expect(section).not.toHaveClass(/\bclosed\b/)

    const newBtn = page.locator('#rail-workflow-new-btn')
    await expect(newBtn).toBeVisible()
    await expect(newBtn).toHaveText('+')
    await newBtn.click()

    await expect(page.locator('#workflow-editor-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#workflow-editor-title')).toHaveText('NEW WORKFLOW')
    await expect(section).not.toHaveClass(/\bclosed\b/)
  })

  test('run all executes rendered workflow steps sequentially in the same tab', async ({ page }) => {
    const postedCommands = []
    await page.route('**/runs', async (route) => {
      const payload = JSON.parse(route.request().postData() || '{}')
      const command = String(payload.command || '')
      postedCommands.push(command)
      const runId = `workflow-${postedCommands.length}`
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ run_id: runId, stream: `/runs/${runId}/stream` }),
      })
    })
    await page.route('**/runs/workflow-*/stream**', async (route) => {
      const runId = route.request().url().match(/\/runs\/([^/]+)\/stream/)?.[1] || 'workflow-1'
      const index = Number(runId.split('-').pop() || '1') - 1
      const command = postedCommands[index] || ''
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: [
          `data: {"type":"started","run_id":"${runId}"}\n\n`,
          `data: {"type":"output","text":"mock output for ${command}\\n"}\n\n`,
          'data: {"type":"exit","code":0,"elapsed":0.01}\n\n',
        ].join(''),
      })
    })

    await ensurePromptReady(page)
    await openWorkflowsModal(page)
    await page.locator('.workflow-catalog-item', { hasText: 'Subdomain HTTP Triage' }).click()
    const workflowCard = page.locator('.workflow-card', { hasText: 'Subdomain HTTP Triage' })
    await expect(workflowCard).toBeVisible()
    const input = workflowCard.locator('.workflow-input-control')
    await input.fill('example.com')
    await expect(input).toHaveValue('example.com')
    await expect(workflowCard.locator('.workflow-run-all')).toBeEnabled()
    await workflowCard.locator('.workflow-run-all').click()
    await expect(page.locator('#workflows-overlay')).not.toHaveClass(/\bopen\b/)
    await expect(page.locator('.tab')).toHaveCount(1)
    await expect(page.locator('body')).toContainText('[workflow] Running 3 steps sequentially in this tab.')
    await expect(page.locator('body')).toContainText('subfinder -d example.com -silent -o subdomains.txt')
    await expect(page.locator('body')).toContainText('httpx -l subdomains.txt -silent -o live-urls.txt')
    await expect(page.locator('body')).toContainText(
      'httpx -l live-urls.txt -status-code -title -tech-detect -o http-summary.txt',
    )
    await expect(page.locator('body')).toContainText('[workflow] Completed all queued steps.')
    await expect.poll(() => postedCommands).toEqual([
      'subfinder -d example.com -silent -o subdomains.txt',
      'httpx -l subdomains.txt -silent -o live-urls.txt',
      'httpx -l live-urls.txt -status-code -title -tech-detect -o http-summary.txt',
    ])
  })

  test('rail browse and workflow entries open one workspace with global executions', async ({ page }) => {
    const section = page.locator('#rail-section-workflows')
    if (await section.evaluate((node) => node.classList.contains('closed'))) {
      await page.locator('#rail-workflows-header').click()
    }
    const browseAll = page.locator('#rail-workflows-list .rail-workflows-browse-all')
    const railItems = page.locator('#rail-workflows-list .rail-item:not(.rail-workflows-browse-all)')
    await expect(browseAll).toBeVisible()
    await expect(railItems.first()).toBeVisible()
    const beforeCount = await railItems.count()
    expect(beforeCount).toBeGreaterThan(1)

    const scopedWorkflows = await page.evaluate(() => (
      (window.__workflowCatalogItems || []).slice(0, 2).map(item => ({
        id: item.id,
        title: item.title,
      }))
    ))
    expect(scopedWorkflows).toHaveLength(2)
    const executionReads = []
    await page.route('**/workflow-executions?*', async (route) => {
      const workflowId = new URL(route.request().url()).searchParams.get('workflow_id') || ''
      executionReads.push(workflowId)
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          executions: [{
            id: 'wfx_global_first',
            workflow_id: scopedWorkflows[0].id,
            title: scopedWorkflows[0].title,
            status: 'completed',
            created: '2026-07-13 10:00:00',
            finished: '2026-07-13 10:00:01',
            steps: [],
          }],
        }),
      })
    })

    await railItems.nth(1).click()
    await expect(page.locator('#workflows-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#workflows-modal .workflow-card')).toHaveCount(1)
    await expect(page.locator('.workflow-catalog-item')).toHaveCount(beforeCount)
    await expect(page.locator('.workflow-title')).toHaveText(scopedWorkflows[1].title)
    await expect(page.locator('[data-workflow-execution-id="wfx_global_first"]')).toBeHidden()

    await page.locator('.workflows-close').click()
    await browseAll.click()
    await page.locator('.workflow-catalog-item', { hasText: scopedWorkflows[0].title }).click()
    await expect(page.locator('.workflow-title')).toHaveText(scopedWorkflows[0].title)
    await page.locator('.workflows-close').click()

    await railItems.nth(1).click()
    await expect(page.locator('#workflows-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#workflows-modal .workflow-card')).toHaveCount(1)
    await expect(page.locator('.workflow-catalog-item')).toHaveCount(beforeCount)
    await expect(page.locator('.workflow-title')).toHaveText(scopedWorkflows[1].title)
    await expect(page.locator('#rail-workflows-list .rail-item:not(.rail-workflows-browse-all)')).toHaveCount(beforeCount)
    await page.locator('[data-workflows-view="executions"]').click()
    await expect(page.locator('[data-workflow-execution-id="wfx_global_first"]')).toBeVisible()
    expect(executionReads).toEqual([''])
  })
})

test.describe('options modal', () => {
  // The HUD clock "local" mode formats using the browser's local timezone.
  // CI runners are typically in UTC, which makes `not.toContainText('UTC')`
  // fail even after switching to local mode (local = UTC on that machine).
  // Pin a non-UTC zone so the assertion is environment-independent.
  test.use({ timezoneId: 'America/New_York' })

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('persists theme, timestamps, line number, and HUD clock preferences across reload', async ({
    page,
  }) => {
    await openRailAction(page, 'theme')
    await expect(page.locator('#theme-overlay')).toHaveClass(/open/)
    await page.locator('#theme-select [data-theme-name="apricot_sand"]').click()
    await page.locator('.theme-close').click()

    await openRailAction(page, 'options')
    await expect(page.locator('#options-overlay')).toHaveClass(/open/)
    await page.locator('#options-ts-select').selectOption('elapsed')
    await page.locator('#options-ln-toggle').check()
    await Promise.all([
      page.waitForResponse((response) => {
        if (!response.url().endsWith('/session/preferences')) return false
        if (response.request().method() !== 'POST') return false
        try {
          const payload = JSON.parse(response.request().postData() || '{}')
          return payload?.preferences?.pref_hud_clock === 'local'
            && payload?.preferences?.pref_line_numbers === 'on'
        } catch {
          return false
        }
      }),
      page.locator('#options-hud-clock-select').selectOption('local'),
    ])
    await page.locator('.options-close').click()

    await expect(page.locator('body')).toHaveAttribute('data-theme', 'apricot_sand')
    await expect(page.locator('#ts-btn')).toHaveText('timestamps: elapsed')
    await expect(page.locator('#ln-btn')).toHaveText('line numbers')
    await expect(page.locator('#hud-clock')).not.toContainText('UTC')
    await expect(page.locator('#hud-clock')).toHaveAttribute('title', /local time/i)

    await page.reload()
    await page.locator('#cmd').waitFor()

    await expect(page.locator('body')).toHaveAttribute('data-theme', 'apricot_sand')
    await expect(page.locator('#ts-btn')).toHaveText('timestamps: elapsed')
    await expect(page.locator('#ln-btn')).toHaveText('line numbers')
    await expect(page.locator('#hud-clock')).not.toContainText('UTC')
    await expect(page.locator('#hud-clock')).toHaveAttribute('title', /local time/i)
  })

  test('persists the selected Options tab and keeps secrets out of preferences', async ({ page }) => {
    await openRailAction(page, 'options')
    await expect(page.locator('#options-overlay')).toHaveClass(/open/)

    await page.locator('[data-options-tab="secrets"]').click()
    await expect(page.locator('[data-options-tab="secrets"]')).toHaveAttribute('aria-selected', 'true')
    await expect(page.locator('#options-panel-secrets')).toBeVisible()
    await page.locator('.options-close').click()
    await expect(page.locator('#options-overlay')).not.toHaveClass(/open/)

    await openRailAction(page, 'options')
    await expect(page.locator('[data-options-tab="secrets"]')).toHaveAttribute('aria-selected', 'true')
    await expect(page.locator('#options-panel-secrets')).toBeVisible()

    await page.locator('[data-options-tab="preferences"]').click()
    await expect(page.locator('[data-options-tab="preferences"]')).toHaveAttribute('aria-selected', 'true')
    await expect(page.locator('#options-panel-preferences')).not.toContainText('SHODAN_API_KEY')

    await page.locator('[data-options-tab="secrets"]').click()
    await page.locator('#options-secret-new-btn').click()
    const confirmHost = page.locator('#confirm-host')
    await expect(confirmHost).toBeVisible()
    await confirmHost.locator('.options-secret-field').filter({ hasText: 'Secret' }).locator('select').selectOption('SHODAN_API_KEY')
    await confirmHost.locator('.options-secret-field').filter({ hasText: 'API key or token' }).locator('input').fill('playwright-shodan-key')
    await confirmHost.locator('[data-confirm-action-id="save"]').click()
    await expect(confirmHost).toBeHidden()
    await expect(page.locator('#options-secrets-list')).toContainText('SHODAN_API_KEY')
    await expect(page.locator('#options-panel-preferences')).not.toContainText('SHODAN_API_KEY')

    await page.locator('.options-close').click()
    await openRailAction(page, 'options')
    await expect(page.locator('[data-options-tab="secrets"]')).toHaveAttribute('aria-selected', 'true')
    await expect(page.locator('#options-secrets-list')).toContainText('SHODAN_API_KEY')
  })
})
