import { test, expect } from '@playwright/test'
import { spawnSync } from 'child_process'
import { existsSync, readFileSync, readdirSync } from 'fs'
import { join } from 'path'
import {
  ensurePromptReady,
  runCommand,
  waitForHistoryRuns,
  browserSessionId,
  seedExternalHistoryRuns,
} from './helpers.js'

const PROJECT_LINK_RUN_COMMAND = 'dig projects.playwright.example +short'

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

test.describe('theme selector', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await ensurePromptReady(page)
  })

  test('clicking the theme button opens the theme selector', async ({ page }) => {
    await page.locator('.rail-nav [data-action="theme"]').click()
    await expect(page.locator('#theme-overlay')).toHaveClass(/open/)
    await expect(page.locator('#theme-select .theme-card-active')).toBeVisible()
  })

  test('selecting a theme applies it from the selector', async ({ page }) => {
    await page.locator('.rail-nav [data-action="theme"]').click()
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
    await page.locator('.rail-nav [data-action="faq"]').click()
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)
  })

  test('close button inside the FAQ modal closes it', async ({ page }) => {
    await page.locator('.rail-nav [data-action="faq"]').click()
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)

    await page.locator('.faq-close').click()
    await expect(page.locator('#faq-overlay')).not.toHaveClass(/open/)
  })

  test('clicking the overlay backdrop closes the FAQ modal', async ({ page }) => {
    await page.locator('.rail-nav [data-action="faq"]').click()
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)

    // Click on the overlay element itself (outside the modal content box)
    await page.locator('#faq-overlay').click({ position: { x: 10, y: 10 } })
    await expect(page.locator('#faq-overlay')).not.toHaveClass(/open/)
  })

  test('renders backend-driven FAQ content and command registry pointer', async ({ page }) => {
    await page.locator('.rail-nav [data-action="faq"]').click()
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

    await page.locator('.rail-nav [data-action="faq"]').click()
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
    await expect(page.locator('.rail-nav [data-action="status-monitor"] .rail-nav-label')).toHaveText('status')

    await page.locator('.rail-nav [data-action="status-monitor"]').click()

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

    await page.locator('.rail-nav [data-action="status-monitor"]').click()
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
    await page.route('**/history/active', async (route) => {
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

    await page.locator('.rail-nav [data-action="status-monitor"]').click()
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
    const command = 'ping -c 1 darklab.sh'
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
    await page.locator('.rail-nav [data-action="status-monitor"]').click()
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

    await page.locator('.rail-nav [data-action="status-monitor"]').click()
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
    await page.locator('[data-project-action="link-last-run"]').click()
    await expect(page.locator('#confirm-host')).toContainText('Add the last run to this project?')
    await page.locator('#confirm-host [data-confirm-action-id="add"]').click()
    await expect(page.locator('#permalink-toast')).toContainText('Last run linked to this project.')
    const runRow = page.locator('.project-explorer-item').filter({ hasText: seededRun.command }).first()
    await expect(runRow).toBeVisible()
    return { runRow, command: seededRun.command }
  }

  test('creates an active project, manages targets, and edits linked run metadata', async ({ page }, testInfo) => {
    test.setTimeout(60_000)
    await openProjectsModal(page)

    const projectName = `Playwright Projects ${Date.now()}`
    const projectId = await createActiveProject(page, projectName)

    await page.locator('#project-labels-input').fill('e2e, client')
    await page.locator('#project-labels-save-btn').click()
    await expect(page.locator('#project-labels-save-status')).toBeVisible()
    await expect(page.locator('.project-label-chips')).toContainText('e2e')
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

  test('creates, edits, downloads, and deletes a project evidence package', async ({ page }, testInfo) => {
    test.setTimeout(60_000)
    await openProjectsModal(page)
    const projectId = await createActiveProject(page, `Playwright Package ${Date.now()}`)
    await linkExternalRunToOpenProject(page, testInfo)

    await switchProjectTab(page, 'packages')
    await page.locator('[data-project-action="package-wizard-open"]').click()
    const wizard = page.locator('#project-package-wizard-overlay')
    await expect(wizard).toHaveClass(/\bopen\b/)
    await expect(wizard.locator('.project-package-step.is-active')).toContainText('Preset')
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
    await expect(page.locator('#project-package-manifest-json')).toContainText('"package_format_version": 1')
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
    await evidenceRunRow.locator('[data-project-action="filter-run-findings"]').click()
    await expect(page.locator('.project-explorer-tab.is-active')).toContainText('Findings')
    await expect(page.locator('[data-project-run-filter-clear]')).toContainText('run:')
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

  test('creates and edits a user workflow from the workflows modal', async ({ page }) => {
    // Two save-and-render cycles plus modal open/close exceeds the default 30s
    // budget on slow CI runners; give the test enough headroom.
    test.setTimeout(60_000)
    await openWorkflowsModal(page)

    await expect(page.locator('#workflow-new-btn')).toHaveText('New Workflow')
    await page.locator('#workflow-new-btn').click()
    await expect(page.locator('#workflow-editor-overlay')).toHaveClass(/\bopen\b/)
    await page.locator('#workflow-editor-title-input').fill('Saved Whois')
    await page.locator('.workflow-editor-step-command').first().fill('whois {{domain}}')
    await page.locator('.workflow-editor-step-note').first().fill('Lookup registration')
    const createdWorkflow = await saveWorkflowEditorAndWait(page, 'POST')
    expect(createdWorkflow?.id).toBeTruthy()

    const userCard = page.locator(
      `#workflows-overlay .workflow-card.is-user-workflow[data-workflow-id="${createdWorkflow.id}"]`,
    )
    await expect(userCard).toHaveClass(/\bis-user-workflow\b/)
    await expect(userCard.locator('.workflow-title')).toHaveText('Saved Whois')
    await expect(userCard.locator('.workflow-edit-btn')).toBeVisible()
    await expect(userCard.locator('.workflow-step-cmd').first()).toContainText('whois {{domain}}')

    await userCard.locator('.workflow-edit-btn').click()
    await expect(page.locator('#workflow-editor-title')).toHaveText('EDIT WORKFLOW')
    await page.locator('.workflow-editor-step-command').first().fill('dig {{domain}} A')
    await saveWorkflowEditorAndWait(page, 'PUT')

    await expect(userCard.locator('.workflow-step-cmd').first()).toContainText('dig {{domain}} A')
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
    await expect(page.locator('body')).toContainText('pd-httpx -l subdomains.txt -silent -o live-urls.txt')
    await expect(page.locator('body')).toContainText(
      'pd-httpx -l live-urls.txt -status-code -title -tech-detect -o http-summary.txt',
    )
    await expect(page.locator('body')).toContainText('[workflow] Completed all queued steps.')
    await expect.poll(() => postedCommands).toEqual([
      'subfinder -d example.com -silent -o subdomains.txt',
      'pd-httpx -l subdomains.txt -silent -o live-urls.txt',
      'pd-httpx -l live-urls.txt -status-code -title -tech-detect -o http-summary.txt',
    ])
  })

  test('clicking a rail workflow opens the scoped modal without collapsing the rail list', async ({ page }) => {
    const section = page.locator('#rail-section-workflows')
    if (await section.evaluate((node) => node.classList.contains('closed'))) {
      await page.locator('#rail-workflows-header').click()
    }
    const railItems = page.locator('#rail-workflows-list .rail-item')
    await expect(railItems.first()).toBeVisible()
    const beforeCount = await railItems.count()
    expect(beforeCount).toBeGreaterThan(1)

    await railItems.first().click()

    await expect(page.locator('#workflows-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#workflows-modal .workflow-card')).toHaveCount(1)
    await expect(page.locator('#rail-workflows-list .rail-item')).toHaveCount(beforeCount)
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
    await page.locator('.rail-nav [data-action="theme"]').click()
    await expect(page.locator('#theme-overlay')).toHaveClass(/open/)
    await page.locator('#theme-select [data-theme-name="apricot_sand"]').click()
    await page.locator('.theme-close').click()

    await page.locator('.rail-nav [data-action="options"]').click()
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
        } catch {
          return false
        }
      }),
      page.locator('#options-hud-clock-select').selectOption('local'),
    ])
    await page.locator('.options-close').click()

    await expect(page.locator('body')).toHaveAttribute('data-theme', 'apricot_sand')
    await expect(page.locator('#ts-btn')).toHaveText('timestamps: elapsed')
    await expect(page.locator('#ln-btn')).toHaveText('line numbers: on')
    await expect(page.locator('#hud-clock')).not.toContainText('UTC')
    await expect(page.locator('#hud-clock')).toHaveAttribute('title', /local time/i)

    await page.reload()
    await page.locator('#cmd').waitFor()

    await expect(page.locator('body')).toHaveAttribute('data-theme', 'apricot_sand')
    await expect(page.locator('#ts-btn')).toHaveText('timestamps: elapsed')
    await expect(page.locator('#ln-btn')).toHaveText('line numbers: on')
    await expect(page.locator('#hud-clock')).not.toContainText('UTC')
    await expect(page.locator('#hud-clock')).toHaveAttribute('title', /local time/i)
  })

  test('persists the selected Options tab and keeps secrets out of preferences', async ({ page }) => {
    await page.locator('.rail-nav [data-action="options"]').click()
    await expect(page.locator('#options-overlay')).toHaveClass(/open/)

    await page.locator('[data-options-tab="secrets"]').click()
    await expect(page.locator('[data-options-tab="secrets"]')).toHaveAttribute('aria-selected', 'true')
    await expect(page.locator('#options-panel-secrets')).toBeVisible()
    await page.locator('.options-close').click()
    await expect(page.locator('#options-overlay')).not.toHaveClass(/open/)

    await page.locator('.rail-nav [data-action="options"]').click()
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
    await page.locator('.rail-nav [data-action="options"]').click()
    await expect(page.locator('[data-options-tab="secrets"]')).toHaveAttribute('aria-selected', 'true')
    await expect(page.locator('#options-secrets-list')).toContainText('SHODAN_API_KEY')
  })
})
