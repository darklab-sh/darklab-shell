import { test, expect } from '@playwright/test'
import { spawnSync } from 'child_process'
import { existsSync, readFileSync, readdirSync } from 'fs'
import { join } from 'path'
import {
  runCommand,
  openHistory,
  openHistoryWithEntries,
  waitForHistoryRuns,
  closeHistory,
  createShareSnapshot,
  clickHistoryRunMenuAction,
  ensurePromptReady,
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
left_id = "run_cmp_left_" + uuid.uuid4().hex[:16]
right_id = "run_cmp_right_" + uuid.uuid4().hex[:16]
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

def preview(lines):
    return json.dumps([
        {"text": "$ " + command, "cls": "prompt-echo", "line_index": 0},
        *[
            {"text": text, "cls": "", "line_index": index + 1}
            for index, text in enumerate(lines)
        ],
        {"text": "[process exited with code 0]", "cls": "exit-ok", "line_index": len(lines) + 1},
    ])

left_lines = common_lines + ["8080/tcp open http-proxy old-build"]
right_lines = common_lines + ["8080/tcp open http-proxy new-build", long_line]

conn = sqlite3.connect(str(Path(data_dir) / "history.db"))
try:
    conn.execute(
        "INSERT INTO runs (id, session_id, command, started, finished, exit_code, "
        "output_preview, preview_truncated, output_line_count, full_output_available, full_output_truncated) "
        "VALUES (?, ?, ?, datetime('now'), datetime('now'), 0, ?, 0, ?, 0, 0)",
        (left_id, session_id, command, preview(left_lines), len(left_lines) + 2),
    )
    conn.execute(
        "INSERT INTO runs (id, session_id, command, started, finished, exit_code, "
        "output_preview, preview_truncated, output_line_count, full_output_available, full_output_truncated) "
        "VALUES (?, ?, ?, datetime('now', '-1 minute'), datetime('now', '-1 minute'), 0, ?, 0, ?, 0, 0)",
        (right_id, session_id, command, preview(right_lines), len(right_lines) + 2),
    )
    conn.commit()
finally:
    conn.close()
print(json.dumps({
    "leftRunId": left_id,
    "rightRunId": right_id,
    "command": command,
    "commonFoldedText": common_lines[3],
    "leftChangedText": "old-build",
    "rightChangedText": "new-build",
    "longLineEnd": "LONG-LINE-END",
}))
`
  const result = spawnSync(pythonForE2EFixture(), ['-c', script, dataDir, sessionId], {
    cwd: process.cwd(),
    encoding: 'utf8',
  })
  if (result.status !== 0) {
    throw new Error(`Failed to seed comparison fixture: ${result.error?.message || result.stderr || result.stdout || `exit ${result.status}`}`)
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
    const created = await createdResp.json()
    const project = created.project
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

async function forceComparePaneOverflow(page) {
  await page.locator('.history-compare-pane').evaluateAll((panes) => {
    panes.forEach((pane) => {
      pane.style.maxHeight = '90px'
      pane.style.overflowY = 'auto'
    })
  })
}

async function expectSplitCompareRendered(page, fixture, { projectId = '' } = {}) {
  const overlay = page.locator('#history-compare-overlay')
  await expect(overlay).toHaveClass(/\bopen\b/)
  await expect(overlay.locator('.history-compare-pane')).toHaveCount(2)
  await expect(overlay.locator('#history-compare-subtitle')).toContainText('8 unchanged')
  await expect(overlay.locator('#history-compare-subtitle')).toContainText('1 changed')
  await expect(overlay.locator('#history-compare-subtitle')).toContainText('1 added')
  await expect(overlay.locator('.history-compare-pane[data-side="a"]')).toContainText(fixture.leftChangedText)
  await expect(overlay.locator('.history-compare-pane[data-side="b"]')).toContainText(fixture.rightChangedText)

  await forceComparePaneOverflow(page)
  const leftPane = overlay.locator('.history-compare-pane[data-side="a"]')
  const rightPane = overlay.locator('.history-compare-pane[data-side="b"]')
  await leftPane.evaluate((node) => {
    node.scrollTop = 48
    node.dispatchEvent(new Event('scroll'))
  })
  await expect.poll(() => rightPane.evaluate((node) => node.scrollTop)).toBe(48)

  const foldButton = overlay.getByRole('button', { name: /Show 2 unchanged line/ }).first()
  await expect(foldButton).toBeVisible()
  const lazyResponse = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return url.pathname === '/history/compare/lines'
      && (!projectId || url.searchParams.get('project_id') === projectId)
  })
  await foldButton.click()
  expect((await lazyResponse).ok()).toBe(true)
  await expect(overlay.locator('.history-compare-pane[data-side="a"]')).toContainText(fixture.commonFoldedText)

  const expander = overlay.locator('.history-compare-line-expander').first()
  await expect(expander).toBeVisible()
  await expander.click()
  await expect(overlay.locator('.history-compare-pane[data-side="b"]')).toContainText(fixture.longLineEnd)
}

test.describe('history drawer', () => {
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

    // All chips should be gone
    await expect(page.locator('.hist-chip')).toHaveCount(0)
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
    await expect(output).toContainText(
      'Use `commands --built-in` or `commands --external` to filter that catalog.',
    )
    await expect(output).toContainText(
      'Use `commands info <command>` to see examples, flags, and subcommands for a supported command.',
    )
    await expect(output).toContainText(
      'Autocomplete appears as you type; press Tab to accept or cycle suggestions.',
    )
    await expect(output).not.toContainText('Help and discovery:')
    await expect(output).not.toContainText('README:')
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

  test('history bulk select can add remove and delete visible runs', async ({ page }) => {
    test.setTimeout(60_000)
    await runCommand(page, CMD_A)
    await waitForHistoryRuns(page, 1)
    await runCommand(page, CMD_B)
    const runs = await waitForHistoryRuns(page, 2)
    const selectedRunIds = runs
      .filter(run => [CMD_A, CMD_B].includes(run.command))
      .map(run => String(run.id))
      .sort()
    expect(selectedRunIds).toHaveLength(2)
    const project = await createActiveProject(page, `Bulk History ${Date.now()}`)

    await openHistoryWithEntries(page)
    const bulkToolbar = page.locator('#history-bulk-toolbar')
    await bulkToolbar.locator('.history-bulk-toggle input').check()
    await expect(page.locator('#history-list [data-action="select-run"]')).toHaveCount(2)
    await page.locator('#history-list .history-entry').filter({ hasText: CMD_A }).click()
    await page.locator('#history-list .history-entry').filter({ hasText: CMD_B }).click()
    await expect(bulkToolbar.locator('.history-bulk-count')).toHaveText('2 selected')

    await bulkToolbar.locator('[data-action="history-bulk-menu"]').click()
    await activateHistoryBulkMenuItem(page, 'bulk-add-active-project')
    await expect(page.locator('#permalink-toast')).toContainText('Added 2 runs')
    await expect.poll(() => projectRunLinkIds(page, project.id)).toEqual(selectedRunIds)

    await ensureHistoryBulkSelectMode(page)
    await expect(bulkToolbar.locator('.history-bulk-count')).toHaveText('0 selected')
    await page.locator('#history-list .history-entry').filter({ hasText: CMD_A }).click()
    await page.locator('#history-list .history-entry').filter({ hasText: CMD_B }).click()
    await bulkToolbar.locator('[data-action="history-bulk-menu"]').click()
    await activateHistoryBulkMenuItem(page, 'bulk-remove-project')
    await expect(page.locator('#confirm-host')).toBeVisible()
    await expect(page.locator('#confirm-host')).toContainText('Remove 2 selected runs from project')
    await page.locator('#confirm-host [data-confirm-action-id="remove"]').click()
    await expect(page.locator('#permalink-toast')).toContainText('Removed 2 runs')
    await expect.poll(() => projectRunLinkIds(page, project.id)).toEqual([])

    await ensureHistoryBulkSelectMode(page)
    await page.locator('#history-list .history-entry').filter({ hasText: CMD_A }).click()
    await page.locator('#history-list .history-entry').filter({ hasText: CMD_B }).click()
    await bulkToolbar.locator('[data-action="history-bulk-menu"]').click()
    await activateHistoryBulkMenuItem(page, 'bulk-delete')
    await expect(page.locator('#confirm-host')).toContainText('Delete 2 selected runs?')
    await page.locator('#confirm-host [data-confirm-action-id="delete"]').click()
    await expect(page.locator('#permalink-toast')).toContainText('Deleted 2 runs')
    await expect.poll(async () => (await page.evaluate(async () => {
      const resp = await apiFetch('/history?page_size=20&type=runs')
      const data = await resp.json()
      return (data.runs || []).filter(run => ['hostname', 'date'].includes(run.command)).length
    }))).toBe(0)
  })

  test('run comparison split view works from history and project entry points', async ({ page }, testInfo) => {
    test.setTimeout(60_000)
    const sessionId = await page.evaluate(() => (
      typeof SESSION_ID === 'string' && SESSION_ID
        ? SESSION_ID
        : localStorage.getItem('session_id')
    ))
    const fixture = seedCompareFixture(testInfo, { sessionId })

    await openHistoryWithEntries(page)
    const sourceRow = page.locator('.history-entry').filter({ hasText: fixture.command }).first()
    await expect(sourceRow).toBeVisible()
    await clickHistoryRunMenuAction(sourceRow, 'compare')
    const compareOverlay = page.locator('#history-compare-overlay')
    await expect(compareOverlay).toHaveClass(/\bopen\b/)
    await expect(compareOverlay.locator('.history-compare-primary')).toBeVisible()
    await compareOverlay.locator('.history-compare-primary').click()
    await expectSplitCompareRendered(page, fixture)
    const historyCompareText = await compareOverlay.locator('.history-compare-split').textContent()
    const historyCountsText = await compareOverlay.locator('#history-compare-subtitle').textContent()

    await page.locator('.history-compare-close').click()
    await expect(compareOverlay).not.toHaveClass(/\bopen\b/)
    await closeHistory(page)

    const project = await createProjectWithLinkedRuns(
      page,
      `Compare Project ${Date.now()}`,
      [fixture.leftRunId, fixture.rightRunId],
    )
    await page.locator('.rail-nav [data-action="projects"]').click()
    await expect(page.locator('#project-workspace-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#project-workspace-body')).not.toContainText('Loading projects...')
    await page.locator('[data-project-tab="runs"]').click()
    await expect(page.locator('#project-explorer-body')).toContainText(fixture.command)

    await page.locator('[data-project-action="compare-runs"]').click()
    await expect(compareOverlay).toHaveClass(/\bopen\b/)
    await expectSplitCompareRendered(page, fixture, { projectId: project.id })
    await expect(compareOverlay.locator('.history-compare-split')).toContainText(fixture.leftChangedText)
    await expect(compareOverlay.locator('.history-compare-split')).toContainText(fixture.rightChangedText)
    expect(await compareOverlay.locator('#history-compare-subtitle').textContent()).toBe(historyCountsText)
    expect(await compareOverlay.locator('.history-compare-split').textContent()).toBe(historyCompareText)
  })
})
