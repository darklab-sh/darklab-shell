import { test, expect } from '@playwright/test'
import { spawnSync } from 'child_process'
import { existsSync, readFileSync, readdirSync } from 'fs'
import { join } from 'path'
import {
  browserSessionId,
  closeHistory,
  clickHistoryRunMenuAction,
  openHistoryWithEntries,
} from './helpers.js'

const COMPARE_PANE_SCROLL_TEST_HEIGHT = '48px'

function e2eDataDirForProject(testInfo) {
  const logDir = process.env.PW_E2E_SERVER_LOG_DIR || ''
  if (!logDir) throw new Error('PW_E2E_SERVER_LOG_DIR is not set')
  const slot = testInfo.project.name.match(/w\d+$/)?.[0]
  if (!slot) throw new Error(`Cannot determine e2e server slot from ${testInfo.project.name}`)
  const logName = readdirSync(logDir).find(name => name.startsWith(`${slot}-`) && name.endsWith('.log'))
  if (!logName) throw new Error(`Cannot find e2e server log for ${slot}`)
  const log = readFileSync(join(logDir, logName), 'utf8')
  const dataDir = log.match(/^\[e2e-server\] data_dir=(.+)$/m)?.[1]
  if (!dataDir) throw new Error(`Cannot find data_dir in ${logName}`)
  return dataDir
}

let fixturePython = ''

function pythonForE2EFixture() {
  if (fixturePython) return fixturePython
  const candidates = [process.env.PYTHON, '.venv/bin/python3', 'python3', 'python'].filter(Boolean)
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

function seedCompareFixture(testInfo, { sessionId }) {
  const dataDir = e2eDataDirForProject(testInfo)
  const script = String.raw`
import json
from pathlib import Path
import sqlite3
import sys
import uuid

data_dir, session_id = sys.argv[1:3]
command = "nmap -p 80,443 compare.playwright.example"
baseline_id = "run_cmp_baseline_" + uuid.uuid4().hex[:16]
current_id = "run_cmp_current_" + uuid.uuid4().hex[:16]
execution_id = "wfx_cmp_" + uuid.uuid4().hex[:16]
long_line = "compare-long-line-" + ("x" * 4200) + "-LONG-LINE-END"
common_lines = [
    "22/tcp filtered ssh",
    "53/tcp open domain",
    "80/tcp open http",
    "111/tcp filtered rpcbind",
    "135/tcp filtered msrpc",
    "139/tcp filtered netbios-ssn",
    "443/tcp open https",
    "445/tcp filtered microsoft-ds",
]

def preview(lines, finding_indexes=()):
    entries = [{"text": "$ " + command, "cls": "prompt-echo", "line_index": 0}]
    for index, text in enumerate(lines):
        item = {"text": text, "cls": "", "line_index": index + 1}
        if index in finding_indexes:
            item["signals"] = ["findings"]
        entries.append(item)
    entries.append({
        "text": "[process exited with code 0]",
        "cls": "exit-ok",
        "line_index": len(lines) + 1,
    })
    return json.dumps(entries)

baseline_lines = common_lines + [
    "8080/tcp open http-proxy old-build",
    "[low] shared severity finding",
    "[medium] removed finding",
]
current_lines = common_lines + [
    "8080/tcp open http-proxy new-build",
    long_line,
    "[high] shared severity finding",
    "[critical] added finding",
]

conn = sqlite3.connect(str(Path(data_dir) / "history.db"))
try:
    conn.execute(
        "INSERT INTO runs (id, session_id, run_kind, command, started, finished, exit_code, "
        "output_preview, preview_truncated, output_line_count, full_output_available, full_output_truncated) "
        "VALUES (?, ?, 'external', ?, datetime('now', '-2 minutes'), datetime('now', '-2 minutes'), "
        "0, ?, 0, ?, 0, 0)",
        (baseline_id, session_id, command, preview(baseline_lines, (9, 10)), len(baseline_lines) + 2),
    )
    conn.execute(
        "INSERT INTO runs (id, session_id, run_kind, command, started, finished, exit_code, "
        "output_preview, preview_truncated, output_line_count, full_output_available, full_output_truncated) "
        "VALUES (?, ?, 'external', ?, datetime('now', '-1 minute'), datetime('now', '-1 minute'), "
        "0, ?, 0, ?, 0, 0)",
        (current_id, session_id, command, preview(current_lines, (10, 11)), len(current_lines) + 2),
    )
    shared_finding_id = "fnd_cmp_shared_" + uuid.uuid4().hex[:16]
    added_finding_id = "fnd_cmp_added_" + uuid.uuid4().hex[:16]
    removed_finding_id = "fnd_cmp_removed_" + uuid.uuid4().hex[:16]
    conn.execute(
        "INSERT INTO findings "
        "(id, session_id, run_id, scope, line_number, severity, tool_root, kind, subject_key, "
        "fingerprint, title, raw_line, created) "
        "VALUES (?, ?, ?, 'finding', 11, 'high', 'nmap', 'finding', 'service:shared', ?, ?, ?, datetime('now'))",
        (
            shared_finding_id,
            session_id,
            current_id,
            shared_finding_id,
            "shared severity finding",
            "[high] shared severity finding",
        ),
    )
    conn.execute(
        "UPDATE findings_occurrences SET observed_severity = 'high', comparison_key = 'cmp:e2e-shared' "
        "WHERE finding_id = ? AND run_id = ?",
        (shared_finding_id, current_id),
    )
    conn.execute(
        "INSERT INTO findings_occurrences "
        "(finding_id, run_id, line_number, snippet, seen_at, observed_severity, comparison_key) "
        "VALUES (?, ?, 10, '[low] shared severity finding', datetime('now', '-2 minutes'), "
        "'low', 'cmp:e2e-shared')",
        (shared_finding_id, baseline_id),
    )
    conn.execute(
        "INSERT INTO findings "
        "(id, session_id, run_id, scope, line_number, severity, tool_root, kind, subject_key, "
        "fingerprint, title, raw_line, created) "
        "VALUES (?, ?, ?, 'finding', 12, 'critical', 'nmap', 'finding', 'service:added', ?, ?, ?, datetime('now'))",
        (
            added_finding_id,
            session_id,
            current_id,
            added_finding_id,
            "added finding",
            "[critical] added finding",
        ),
    )
    conn.execute(
        "INSERT INTO findings "
        "(id, session_id, run_id, scope, line_number, severity, tool_root, kind, subject_key, "
        "fingerprint, title, raw_line, created) "
        "VALUES (?, ?, ?, 'finding', 11, 'medium', 'nmap', 'finding', 'service:removed', ?, ?, ?, "
        "datetime('now', '-2 minutes'))",
        (
            removed_finding_id,
            session_id,
            baseline_id,
            removed_finding_id,
            "removed finding",
            "[medium] removed finding",
        ),
    )
    conn.execute(
        "INSERT INTO workflow_executions "
        "(id, session_id, workflow_id, workflow_source, title, status, current_step_id, created, updated) "
        "VALUES (?, ?, 'workflow-compare', 'user', 'Comparison playbook', 'completed', 'scan', "
        "datetime('now', '-1 minute'), datetime('now', '-1 minute'))",
        (execution_id, session_id),
    )
    conn.executemany(
        "INSERT INTO workflow_execution_steps "
        "(id, execution_id, step_id, step_index, run_id, status, exit_code, created, started, finished) "
        "VALUES (?, ?, ?, ?, ?, 'completed', 0, datetime('now', '-1 minute'), "
        "datetime('now', '-1 minute'), datetime('now', '-1 minute'))",
        [
            ("wfs_cmp_" + uuid.uuid4().hex[:16], execution_id, "baseline-scan", 0, baseline_id),
            ("wfs_cmp_" + uuid.uuid4().hex[:16], execution_id, "scan", 1, current_id),
        ],
    )
    conn.commit()
finally:
    conn.close()
print(json.dumps({
    "baselineRunId": baseline_id,
    "currentRunId": current_id,
    "executionId": execution_id,
    "command": command,
    "commonFoldedText": common_lines[3],
    "baselineChangedText": "old-build",
    "currentChangedText": "new-build",
    "longLineEnd": "LONG-LINE-END",
    "sharedFindingText": "shared severity finding",
}))
`
  const result = spawnSync(pythonForE2EFixture(), ['-c', script, dataDir, sessionId], {
    cwd: process.cwd(),
    encoding: 'utf8',
  })
  if (result.status !== 0) {
    throw new Error(
      `Failed to seed comparison fixture: ${result.error?.message || result.stderr || result.stdout || `exit ${result.status}`}`,
    )
  }
  return JSON.parse(result.stdout)
}

async function createProjectWithLinkedRuns(page, name, runIds) {
  return page.evaluate(async ({ projectName, linkedRunIds }) => {
    const createdResp = await apiFetch('/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: projectName }),
    })
    if (!createdResp.ok) throw new Error(`Failed to create project: ${createdResp.status}`)
    const { project } = await createdResp.json()
    const activeResp = await apiFetch('/projects/active', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: project.id }),
    })
    if (!activeResp.ok) throw new Error(`Failed to set active project: ${activeResp.status}`)
    for (const runId of linkedRunIds) {
      const linkResp = await apiFetch(`/projects/${encodeURIComponent(project.id)}/links`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entity_type: 'run', entity_id: runId, source: 'manual' }),
      })
      if (!linkResp.ok) throw new Error(`Failed to link project run: ${linkResp.status}`)
    }
    return project
  }, { projectName: name, linkedRunIds: runIds })
}

function waitForComparison(page, fixture, projectId = '') {
  return page.waitForResponse(response => {
    const url = new URL(response.url())
    if (url.pathname !== '/history/compare') return false
    if (projectId) return url.searchParams.get('project_id') === projectId
    return url.searchParams.get('left') === fixture.baselineRunId
      && url.searchParams.get('right') === fixture.currentRunId
  })
}

async function startSuggestedComparison(page, fixture) {
  const responsePromise = waitForComparison(page, fixture)
  await page.locator('#history-compare-overlay .history-compare-primary').click()
  expect((await responsePromise).ok()).toBe(true)
}

async function closeComparison(page) {
  await page.locator('#history-compare-overlay .history-compare-close').click()
  await expect(page.locator('#history-compare-overlay')).not.toHaveClass(/\bopen\b/)
}

async function expectSplitPaneScrollSync(overlay) {
  const scrollState = await overlay.evaluate(async (overlayElement, height) => {
    const nextFrame = () => new Promise(resolve => requestAnimationFrame(resolve))
    await nextFrame()
    const left = overlayElement.querySelector('.history-compare-pane[data-side="a"]')
    const right = overlayElement.querySelector('.history-compare-pane[data-side="b"]')
    if (!left || !right) return { actual: 0, expected: 0, leftScrollable: false, rightScrollable: false }
    for (const pane of [left, right]) {
      pane.style.alignSelf = 'start'
      pane.style.minHeight = '0'
      pane.style.height = height
      pane.style.maxHeight = height
      pane.style.overflowY = 'auto'
      const spacer = document.createElement('div')
      spacer.dataset.e2eCompareScrollSpacer = '1'
      spacer.setAttribute('aria-hidden', 'true')
      spacer.style.flex = '0 0 160px'
      spacer.style.height = '160px'
      pane.appendChild(spacer)
    }
    const leftMax = Math.max(0, left.scrollHeight - left.clientHeight)
    const rightMax = Math.max(0, right.scrollHeight - right.clientHeight)
    const targetScrollTop = Math.min(48, Math.max(1, Math.min(leftMax, rightMax)))
    left.scrollTop = targetScrollTop
    left.dispatchEvent(new Event('scroll', { bubbles: true }))
    await nextFrame()
    await nextFrame()
    return {
      actual: right.scrollTop,
      expected: left.scrollTop,
      leftScrollable: leftMax > 0,
      rightScrollable: rightMax > 0,
    }
  }, COMPARE_PANE_SCROLL_TEST_HEIGHT)
  expect(scrollState.leftScrollable).toBe(true)
  expect(scrollState.rightScrollable).toBe(true)
  expect(scrollState.actual).toBe(scrollState.expected)
}

async function expectComparisonRendered(page, fixture) {
  const overlay = page.locator('#history-compare-overlay')
  await expect(overlay).toHaveClass(/\bopen\b/)
  await expect(overlay.locator('.history-compare-pane')).toHaveCount(2)
  await expect(overlay.locator('.history-compare-run-card').first()).toContainText('Baseline')
  await expect(overlay.locator('.history-compare-run-card').last()).toContainText('Current run')
  await expect(overlay.locator('.history-compare-run-card').last()).toContainText('Comparison playbook')
  await expect(overlay.locator('.history-compare-pane[data-side="a"]')).toContainText(
    fixture.baselineChangedText,
  )
  await expect(overlay.locator('.history-compare-pane[data-side="b"]')).toContainText(
    fixture.currentChangedText,
  )
}

test.beforeEach(async ({ page }) => {
  await page.goto('/')
  await page.evaluate(() => localStorage.clear())
  await page.reload()
  await page.locator('#cmd').waitFor({ state: 'attached' })
})

test.describe('run comparison launch paths', () => {
  test.describe.configure({ timeout: 90_000 })

  test('opens chronological comparison from History, Project, HUD, and Findings', async ({ page }, testInfo) => {
    const sessionId = await browserSessionId(page)
    const fixture = seedCompareFixture(testInfo, { sessionId })

    await openHistoryWithEntries(page)
    const currentRow = page.locator('.history-entry').filter({ hasText: fixture.command }).first()
    await clickHistoryRunMenuAction(currentRow, 'compare')
    await expect(page.locator('#history-compare-overlay .history-compare-primary')).toBeVisible()
    await startSuggestedComparison(page, fixture)
    await expectComparisonRendered(page, fixture)
    const compareModal = page.locator('#history-compare-modal')
    await page.locator('#cmd').focus()
    await compareModal.dispatchEvent('keydown', { key: 'Tab' })
    await expect.poll(() => page.evaluate(() => (
      document.getElementById('history-compare-modal')?.contains(document.activeElement)
    ))).toBe(true)
    await page.locator('#cmd').focus()
    await compareModal.dispatchEvent('keydown', { key: 'Tab', shiftKey: true })
    await expect.poll(() => page.evaluate(() => (
      document.getElementById('history-compare-modal')?.contains(document.activeElement)
    ))).toBe(true)
    await expectSplitPaneScrollSync(page.locator('#history-compare-overlay'))

    const rightPane = page.locator('#history-compare-overlay .history-compare-pane[data-side="b"]')
    const foldButton = rightPane.getByRole('button', { name: /Show 2 unchanged line/ }).first()
    await expect(foldButton).toBeVisible()
    await foldButton.click()
    await expect(rightPane).toContainText(fixture.commonFoldedText)
    const expander = page.locator('#history-compare-overlay .history-compare-line-expander').first()
    await expander.click()
    await expect(rightPane).toContainText(fixture.longLineEnd)
    const findingAnchors = page.locator(
      '#history-compare-overlay .history-compare-finding-change-link',
    )
    await expect(findingAnchors).toHaveCount(2)
    await expect(findingAnchors.first()).toHaveText('Baseline: low')
    await expect(findingAnchors.last()).toHaveText('Current: high')
    await findingAnchors.first().click()
    await expect(page.locator(
      '#history-compare-overlay .history-compare-pane[data-side="a"] .history-compare-line-pulse',
    )).toContainText(fixture.sharedFindingText)
    await findingAnchors.last().click()
    await expect(page.locator(
      '#history-compare-overlay .history-compare-pane[data-side="b"] .history-compare-line-pulse',
    )).toContainText(fixture.sharedFindingText)
    const playbookButtons = page.locator('#history-compare-overlay').getByRole('button', { name: 'View playbook' })
    await expect(playbookButtons).toHaveCount(2)
    await playbookButtons.last().click()
    await expect(page.locator('#history-compare-overlay')).not.toHaveClass(/\bopen\b/)
    await expect(page.locator('#workflows-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('[data-workflows-view="executions"]')).toHaveAttribute('aria-selected', 'true')
    await expect(page.locator(`[data-workflow-execution-id="${fixture.executionId}"]`))
      .toContainText('Comparison playbook')
    await page.locator('#workflows-overlay .workflows-close').click()

    await openHistoryWithEntries(page)
    const reopenedCurrentRow = page.locator('.history-entry').filter({ hasText: fixture.command }).first()
    await clickHistoryRunMenuAction(reopenedCurrentRow, 'compare')
    await startSuggestedComparison(page, fixture)
    await page.locator('#history-compare-overlay').getByRole('button', { name: 'View playbook' }).first().click()
    await expect(page.locator('#history-compare-overlay')).not.toHaveClass(/\bopen\b/)
    await expect(page.locator('#workflows-overlay')).toHaveClass(/\bopen\b/)
    await page.locator('#workflows-overlay .workflows-close').click()
    await closeHistory(page)

    const project = await createProjectWithLinkedRuns(
      page,
      `Compare Project ${Date.now()}`,
      [fixture.currentRunId, fixture.baselineRunId],
    )
    await page.locator('.rail-nav [data-action="projects"]').click()
    await expect(page.locator('#project-workspace-overlay')).toHaveClass(/\bopen\b/)
    await page.locator('[data-project-tab="runs"]').click()
    await expect(page.locator('#project-explorer-body')).toContainText(fixture.command)
    const projectResponse = waitForComparison(page, fixture, project.id)
    await page.locator('[data-project-action="compare-runs"]').click()
    const projectCompareResponse = await projectResponse
    expect(projectCompareResponse.ok()).toBe(true)
    const projectComparePayload = await projectCompareResponse.json()
    expect(projectComparePayload.left_run_id).toBe(fixture.baselineRunId)
    expect(projectComparePayload.right_run_id).toBe(fixture.currentRunId)
    await expectComparisonRendered(page, fixture)
    await closeComparison(page)
    await page.locator('#project-workspace-overlay .project-workspace-close').click()

    await openHistoryWithEntries(page)
    await page
      .locator('.history-entry')
      .filter({ hasText: fixture.command })
      .first()
      .locator('[data-action="restore"]')
      .click()
    await expect(page.locator('.tab-panel.active .output')).toContainText(fixture.currentChangedText)
    await closeHistory(page)

    const hudCompare = page.locator('#hud-actions [data-action="compare"]')
    await expect(hudCompare).toBeVisible()
    await hudCompare.click()
    await startSuggestedComparison(page, fixture)
    await expectComparisonRendered(page, fixture)
    await closeComparison(page)
    await expect(hudCompare).toBeFocused()

    const findingsCompare = page.locator('[data-search-compare-findings="1"]')
    await expect(findingsCompare).toBeVisible()
    await expect(findingsCompare).toHaveAttribute('aria-label', 'Compare findings with previous run')
    await findingsCompare.click()
    await startSuggestedComparison(page, fixture)
    await expect(page.locator('.history-compare-view-select')).toHaveValue('findings_only')
    await expect(page.locator('#history-compare-subtitle')).toHaveText('Changed, added, and removed findings')
    await expect(page.locator('.history-compare-split')).toHaveCount(0)
    await expect(page.locator('.history-compare-nav')).toHaveCount(0)
    await expect(page.locator('.history-compare-metric-label')).toHaveText([
      'Changed findings',
      'Added findings',
      'Removed findings',
    ])
    await expect(page.locator('.history-compare-metric-value')).toHaveText(['1', '1', '1'])
    await expect(page.locator('.history-compare-changed-findings')).toContainText('Baseline: low')
    await expect(page.locator('.history-compare-changed-findings')).toContainText('Current: high')
    await expect(page.locator('.history-compare-object-section').filter({ hasText: 'Added findings (1)' }))
      .toContainText('added finding')
    await expect(page.locator('.history-compare-object-section').filter({ hasText: 'Removed findings (1)' }))
      .toContainText('removed finding')
    await closeComparison(page)
    await expect(findingsCompare).toBeFocused()
  })
})

test.describe('mobile run comparison launch path', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })
  test.describe.configure({ timeout: 60_000 })

  test('opens comparison for the restored active run from the hamburger menu', async ({ page }, testInfo) => {
    await page.evaluate(() => window.dispatchEvent(new Event('resize')))
    await expect.poll(() => page.evaluate(() => (
      document.body.classList.contains('mobile-terminal-mode')
    ))).toBe(true)
    await page.locator('#mobile-cmd').waitFor({ state: 'attached' })
    const sessionId = await browserSessionId(page)
    const fixture = seedCompareFixture(testInfo, { sessionId })
    await openHistoryWithEntries(page)
    await page
      .locator('.history-entry')
      .filter({ hasText: fixture.command })
      .first()
      .locator('[data-action="restore"]')
      .click()
    await expect(page.locator('.tab-panel.active .output')).toContainText(fixture.currentChangedText)

    await page.locator('#hamburger-btn').click()
    const mobileCompare = page.locator('#mobile-menu-sheet [data-menu-action="compare-active"]')
    await expect(mobileCompare).toBeVisible()
    await mobileCompare.click()
    await expect(page.locator('#mobile-menu-sheet')).toHaveClass(/u-hidden/)
    await startSuggestedComparison(page, fixture)
    await expect(page.locator('#history-compare-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('.history-compare-run-card').first()).toContainText('Baseline')
    await expect(page.locator('.history-compare-run-card').last()).toContainText('Current run')
    await page.keyboard.press('Escape')
    await expect(page.locator('#history-compare-overlay')).not.toHaveClass(/\bopen\b/)
    await expect(page.locator('#hamburger-btn')).toBeFocused()
  })
})
