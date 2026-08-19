// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { test, expect } from '@playwright/test'
import {
  browserSessionId,
  ensurePromptReady,
  openRailAction,
  seedProjectMonitoringFixture,
} from './helpers.js'

async function issueAndActivateSessionToken(page) {
  const token = await page.evaluate(async () => {
    const response = await apiFetch('/session/token/generate')
    if (!response.ok) throw new Error(`session token create failed: ${response.status}`)
    return (await response.json()).session_token
  })
  await page.evaluate((sessionToken) => localStorage.setItem('session_token', sessionToken), token)
  await page.reload({ waitUntil: 'domcontentloaded' })
  await ensurePromptReady(page, { timeout: 30_000 })
  await expect.poll(() => page.evaluate(() => SESSION_ID), { timeout: 15_000 }).toBe(token)
}

async function createAndSelectTeam(page, suffix) {
  await page.evaluate(() => window.DarklabTeamScope.refreshTeamScopes())
  const team = await page.evaluate(async ({ teamSuffix }) => {
    const response = await apiFetch('/session/teams', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: `Assessment Team ${teamSuffix}`,
        slug: `assessment-team-${teamSuffix}`,
        display_name: 'Assessment owner',
      }),
    })
    if (!response.ok) throw new Error(`team create failed: ${response.status}`)
    return (await response.json()).team
  }, { teamSuffix: suffix })
  await page.evaluate(async (teamId) => {
    await window.DarklabTeamScope.refreshTeamScopes()
    window.DarklabTeamScope.setActiveTeamId(teamId)
  }, team.id)
  await expect(page.locator('#team-scope-label')).toHaveText(team.name)
  return team
}

async function createAssessmentProject(page, name, target = { type: 'ip', value: '127.0.0.1' }) {
  return page.evaluate(async ({ projectName, projectTarget }) => {
    const create = await apiFetch('/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: projectName }),
    })
    if (!create.ok) throw new Error(`project create failed: ${create.status}`)
    const project = (await create.json()).project
    const activate = await apiFetch('/projects/active', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: project.id }),
    })
    if (!activate.ok) throw new Error(`project activate failed: ${activate.status}`)
    const target = await apiFetch(`/projects/${encodeURIComponent(project.id)}/targets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(projectTarget),
    })
    if (!target.ok) throw new Error(`project target create failed: ${target.status}`)
    return { project, target: (await target.json()).target }
  }, { projectName: name, projectTarget: target })
}

async function addAssessmentTargets(page, projectId, targets) {
  await page.evaluate(async ({ id, projectTargets }) => {
    for (const projectTarget of projectTargets) {
      const response = await apiFetch(`/projects/${encodeURIComponent(id)}/targets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(projectTarget),
      })
      if (!response.ok) throw new Error(`project target create failed: ${response.status}`)
    }
  }, { id: projectId, projectTargets: targets })
}

async function openAssessment(page) {
  await page.locator('.rail-nav [data-action="projects"]').click()
  await expect(page.locator('#project-workspace-overlay')).toHaveClass(/\bopen\b/)
  await expect(page.locator('#project-workspace-body')).not.toContainText('Loading projects...')
  const tab = page.locator('[data-project-tab="assessment"]')
  await tab.click()
  await expect(tab).toHaveClass(/\bis-active\b/)
  await expect(page.locator('#project-explorer-body')).not.toContainText('Loading project assessments...')
}

async function startAssessmentCycle(page, assessment, profileKey, profileLabel) {
  await assessment.locator('.project-assessment-start-form select').selectOption(profileKey)
  const started = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return response.request().method() === 'POST' && /\/projects\/[^/]+\/assessments$/.test(url.pathname)
  })
  await assessment.locator('.project-assessment-start-form button[type="submit"]').click()
  expect((await started).status()).toBe(201)
  await expect(assessment.locator('.project-assessment-cycle')).toContainText(profileLabel)
}

async function startNetworkAssessment(page, name) {
  const created = await createAssessmentProject(page, name)
  await openAssessment(page)
  const assessment = page.locator('#project-explorer-body .project-assessment-root')
  await startAssessmentCycle(page, assessment, 'network', 'Network assessment')
  return { ...created, assessment }
}

async function confirmAssessmentAction(page, actionId) {
  const confirm = page.locator('#confirm-host')
  await expect(confirm).toBeVisible()
  await confirm.locator(`[data-confirm-action-id="${actionId}"]`).click()
}

async function installSafeAssessmentLaunchFixture(page) {
  let launched = false
  await page.route('**/projects/*/assessments**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (url.pathname.endsWith('/recommended-action') && request.method() === 'POST') {
      launched = true
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          run: {
            run_id: 'run_assessment_playwright',
            command: 'ping -c 4 -W 2 127.0.0.1',
            status: 'running',
          },
        }),
      })
      return
    }
    const response = await route.fetch()
    if (!launched || request.method() !== 'GET' || !response.ok()) {
      await route.fulfill({ response })
      return
    }
    const payload = await response.json()
    const evidence = {
      id: 'aev_assessment_playwright',
      check_id: 'asmc_assessment_playwright',
      check_key: 'host_reachability',
      target_type: 'ip',
      target_value: '127.0.0.1',
      evidence_type: 'run',
      evidence_id: 'run_assessment_playwright',
      source_state: 'available',
      observed_at: '2026-08-10T04:41:15Z',
      linked_by: 'derived',
    }
    if (/\/assessments$/.test(url.pathname)) {
      const assessment = payload.assessments?.[0]
      if (assessment?.rollup) {
        assessment.rollup.covered_checks = 1
        assessment.rollup.untested_checks = 1
      }
    } else if (/\/assessments\/[^/]+$/.test(url.pathname)) {
      payload.rollup.covered_checks = 1
      payload.rollup.untested_checks = 1
      const check = payload.checks?.checks?.find((item) => item.check_key === 'host_reachability')
      if (check) {
        evidence.check_id = check.id
        check.state = 'covered'
        check.state_source = 'derived'
        check.evidence_count = 1
        check.evidence_previews = {
          evidence: [evidence],
          total: 1,
          limit: 3,
          offset: 0,
          has_more: false,
        }
      }
      payload.recent_evidence = {
        evidence: [evidence],
        total: 1,
        limit: 20,
        offset: 0,
        has_more: false,
      }
      const target = payload.target_rollups?.find((item) => item.target_value === '127.0.0.1')
      if (target) {
        target.covered_checks = 1
        target.untested_checks = 1
      }
    }
    await route.fulfill({
      response,
      contentType: 'application/json',
      body: JSON.stringify(payload),
    })
  })
}

async function installAssessmentBatchLifecycleFixture(page) {
  const state = {
    launched: false,
    canceling: false,
    retried: false,
    projectId: '',
    assessmentId: '',
    startBody: null,
    retryBody: null,
  }
  const batchId = 'wfx_assessment_batch_playwright'
  const retryBatchId = 'wfx_assessment_batch_retry_playwright'
  const retryPreviewId = 'abp_assessment_batch_retry_playwright'
  const batch = (id = batchId) => {
    const retry = id === retryBatchId
    const canceled = !retry && state.canceling
    return ({
    schema_version: 1,
    batch_id: id,
    project_id: state.projectId,
    assessment_id: state.assessmentId,
    source_batch_id: retry ? batchId : '',
    status: canceled ? 'canceled' : 'running',
    item_count: 1,
    created: '2026-08-17T10:00:00Z',
    progress: {
      total: 1,
      pending: 0,
      launching: 0,
      running: canceled ? 0 : 1,
      succeeded: 0,
      failed: 0,
      unavailable: 0,
      canceled: canceled ? 1 : 0,
      skipped: 0,
      could_not_cancel: 0,
      settled: canceled ? 1 : 0,
    },
  })
  }
  await page.route('**/history/active**', async (route) => {
    const activeBatch = state.launched && !state.canceling
      ? {
          ...batch(state.retried ? retryBatchId : batchId),
          project_name: 'Assessment batch project',
          active_commands: [{
            item_index: 0,
            action_id: 'ping',
            display_command: 'ping -c 4 -W 2 127.0.0.1',
            status: 'running',
            run_id: state.retried
              ? 'run_assessment_batch_retry_playwright'
              : 'run_assessment_batch_playwright',
            target: { type: 'ip', value: '127.0.0.1' },
          }],
        }
      : null
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runs: [],
        assessment_batches: {
          batches: activeBatch ? [activeBatch] : [],
          truncated: false,
        },
      }),
    })
  })
  await page.route(/\/(?:batch-previews|assessment-batch-previews|assessment-batches)(?:[/?]|$)/, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const startMatch = path.match(/\/projects\/([^/]+)\/assessments\/([^/]+)\/assessment-batches$/)
    if (startMatch && request.method() === 'POST') {
      state.projectId = decodeURIComponent(startMatch[1])
      state.assessmentId = decodeURIComponent(startMatch[2])
      state.startBody = request.postDataJSON()
      state.launched = true
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ batch: batch(), launch: { launched: 1 } }),
      })
      return
    }
    if (path.endsWith(`/assessment-batches/${batchId}/cancel`) && request.method() === 'POST') {
      state.canceling = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ batch: batch(), signal_failures: 0 }),
      })
      return
    }
    if (path.endsWith(`/assessment-batches/${batchId}/retry-previews`) && request.method() === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          preview: {
            schema_version: 1,
            preview_id: retryPreviewId,
            project_id: state.projectId,
            assessment_id: state.assessmentId,
            source_batch_id: batchId,
            profile: { key: 'network', version: '1' },
            selection: { include_standard: false, item_limit: 128 },
            summary: {
              selected_target_count: 1,
              estimated_min_seconds: 1,
              estimated_max_seconds: 10,
              potential_covered_check_count: 1,
              requires_standard_confirmation: false,
              reason_counts: {},
              source_batch_id: batchId,
              source_item_count: 1,
              source_retry_eligible_item_count: 1,
              source_succeeded_item_count: 0,
            },
            plan_digest: 'b'.repeat(64),
            candidate_item_count: 1,
            selected_item_count: 1,
            potential_covered_check_count: 1,
            safe_item_count: 1,
            standard_item_count: 0,
            concurrency: { batch: 8, target: 1, owner: 16, instance: 32 },
            created: '2026-08-17T10:01:00Z',
            expires_at: '2026-08-17T10:16:00Z',
          },
        }),
      })
      return
    }
    if (path.endsWith(`/assessment-batches/${batchId}/retry`) && request.method() === 'POST') {
      state.retryBody = request.postDataJSON()
      state.retried = true
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ batch: batch(retryBatchId), launch: { launched: 1 } }),
      })
      return
    }
    if (path.endsWith('/batch-previews') && request.method() === 'POST') {
      const response = await route.fetch()
      const payload = await response.json()
      payload.preview.summary.nuclei_preflight = {
        state: 'stale',
        source_label: 'Managed local cache',
        release_version: 'v10.4.7',
        content_digest: `sha256:${'1'.repeat(64)}`,
        manifest_entry_count: 100,
        refreshed_at: '2026-08-10T12:00:00Z',
        validation_state: 'passed',
        nuclei_version: 'v3.4.10',
        stale_after_seconds: 604800,
        reason_code: 'template_cache_stale',
        launchable: true,
        command_count: 1,
        refresh_enabled: true,
        operator_action: 'Update the managed templates when network access is available.',
      }
      await route.fulfill({
        response,
        contentType: 'application/json',
        body: JSON.stringify(payload),
      })
      return
    }
    if (/\/projects\/[^/]+\/assessment-batches$/.test(path) && request.method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          batches: state.retried ? [batch(retryBatchId)] : (state.launched ? [batch()] : []),
          next_cursor: null,
          has_more: false,
        }),
      })
      return
    }
    if ([batchId, retryBatchId].some(id => path === `/assessment-batches/${id}`)
        && request.method() === 'GET') {
      const id = path.endsWith(`/${retryBatchId}`) ? retryBatchId : batchId
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ batch: batch(id) }),
      })
      return
    }
    if ([batchId, retryBatchId].some(id => path === `/assessment-batches/${id}/items`)
        && request.method() === 'GET') {
      const retry = path.includes(retryBatchId)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [{
            item_index: 0,
            action_id: 'ping',
            target: { type: 'ip', value: '127.0.0.1' },
            policy_level: 'safe',
            display_command: 'ping -c 4 -W 2 127.0.0.1',
            check_count: 1,
            attempt: 1,
            status: retry ? 'running' : (state.canceling ? 'canceled' : 'running'),
            run_id: retry ? 'run_assessment_batch_retry_playwright' : 'run_assessment_batch_playwright',
          }],
          next_cursor: null,
          has_more: false,
        }),
      })
      return
    }
    if (path === `/assessment-batch-previews/${retryPreviewId}/items`
        && request.method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [{
            item_index: 0,
            selected: true,
            action: { id: 'ping' },
            target: { type: 'ip', value: '127.0.0.1' },
            policy_level: 'safe',
            display_command: 'ping -c 4 -W 2 127.0.0.1',
            check_mappings: [{ check_id: 'asmc_retry_playwright' }],
          }],
          next_cursor: null,
        }),
      })
      return
    }
    if ([batchId, retryBatchId].some(id => path === `/assessment-batches/${id}/events`)
        && request.method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          events: [{
            sequence: 1,
            event_type: 'item_run_bound',
            item_ordinal: 0,
            status: 'running',
            created: '2026-08-17T10:00:01Z',
          }],
          next_cursor: null,
          has_more: false,
        }),
      })
      return
    }
    await route.continue()
  })
  return state
}

test.describe('project assessment qualification', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await ensurePromptReady(page)
  })

  test('starts a cycle, shows truthful empty coverage, and derives evidence from a safe run', async ({ page }) => {
    test.setTimeout(90_000)
    await installSafeAssessmentLaunchFixture(page)
    await createAssessmentProject(page, `Assessment Journey ${Date.now()}`)
    await openAssessment(page)

    const assessment = page.locator('#project-explorer-body .project-assessment-root')
    await expect(assessment).toContainText('Start an assessment')
    await assessment.locator('.project-assessment-start-form select').selectOption('network')
    const started = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && /\/projects\/[^/]+\/assessments$/.test(url.pathname)
    })
    await assessment.locator('.project-assessment-start-form button[type="submit"]').click()
    expect((await started).status()).toBe(201)

    await expect(assessment).toContainText('Network assessment')
    await expect(assessment).toContainText('0Coveredof 2 applicable')
    await expect(assessment).toContainText('2Untested')
    const categoryChip = assessment.locator('.project-assessment-category-list .chip').filter({
      hasText: 'discovery',
    })
    await expect(categoryChip).toHaveCSS('padding-left', '11px')
    await expect(categoryChip).toHaveCSS('padding-right', '11px')
    await categoryChip.click()
    const clearFilters = assessment.getByRole('button', { name: 'Clear filters' })
    await expect(assessment.locator('.project-assessment-check-filter-status'))
      .toHaveText('1 filter applied')
    await expect(clearFilters).toBeEnabled()
    await clearFilters.click()
    await expect(assessment.locator('.project-assessment-check-filter-status'))
      .toHaveText('No filters applied')
    await expect(clearFilters).toBeDisabled()
    await expect(assessment.getByRole('button', { name: 'All categories' }))
      .toHaveAttribute('aria-pressed', 'true')
    await assessment.locator('.project-assessment-target-toggle').click()
    const firstCheckRow = assessment.locator('.project-assessment-check-row').first()
    await expect(firstCheckRow).toHaveCSS('padding-top', '9px')
    await page.evaluate(() => {
      window.__darklabRunnerHandlers.attachActiveRunFromMonitor = async (run) => {
        window.__assessmentAttachedRun = run
        return true
      }
    })
    const runPing = assessment.getByRole('button', { name: 'Run Ping' })
    await expect(runPing).toBeVisible()
    await runPing.click()

    const confirm = page.locator('#confirm-host')
    await expect(confirm).toContainText('Start ping?')
    await expect(confirm).toContainText('ping -c 4 -W 2 127.0.0.1')
    const launch = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname.endsWith('/recommended-action')
    })
    await confirm.locator('[data-confirm-action-id="run"]').click()
    expect((await launch).status()).toBe(201)
    await expect(page.locator('#project-workspace-overlay')).not.toHaveClass(/\bopen\b/)
    await expect.poll(() => page.evaluate(() => window.__assessmentAttachedRun?.run_id || '')).toBe(
      'run_assessment_playwright',
    )

    await page.reload()
    await ensurePromptReady(page)
    await openAssessment(page)
    await expect(assessment).toContainText('1Coveredof 2 applicable')
    await expect(assessment).toContainText('1Untested')
    await expect(assessment.locator('.project-assessment-recent-evidence')).toContainText(
      'run_assessment_playwright',
    )
    await expect(assessment.locator('.project-assessment-recent-evidence')).toContainText(
      'Host reachability · ip · 127.0.0.1 · Matched automatically',
    )
  })

  test('previews starts restores and cancels a bounded assessment batch', async ({ page }) => {
    test.setTimeout(90_000)
    const fixture = await installAssessmentBatchLifecycleFixture(page)
    const { assessment } = await startNetworkAssessment(
      page,
      `Assessment Batch ${Date.now()}`,
    )
    const section = assessment.locator('.project-assessment-batch')
    await expect(section).toContainText('Safe checks are selected by default')
    const previewButton = section.getByRole('button', { name: 'Preview assessment plan' })
    await expect(previewButton).toBeEnabled()
    const targetChoice = section.locator('.project-assessment-batch-selector').first()
      .getByRole('checkbox').first()
    await targetChoice.focus()
    await targetChoice.press('Space')
    await expect(previewButton).toBeDisabled()
    await targetChoice.press('Space')
    await expect(previewButton).toBeEnabled()

    const previewResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname.endsWith('/batch-previews')
    })
    await previewButton.click()
    expect((await previewResponse).status()).toBe(201)
    await expect(section.locator('.project-assessment-batch-summary-grid')).toContainText('Commands')
    await expect(section.locator('.project-assessment-batch-command').first()).toBeVisible()
    await expect(section).toContainText('Planning estimate')
    await expect(section).toContainText('Managed Nuclei template preflight')
    await expect(section).toContainText('stale')
    await expect(section).toContainText('v10.4.7')

    await section.getByRole('button', { name: 'Run assessment plan' }).click()
    const confirm = page.locator('#confirm-host')
    await expect(confirm).toContainText('Continue with stale managed Nuclei templates?')
    await expect(confirm.getByRole('button', {
      name: 'Update templates and rebuild preview',
    })).toBeVisible()
    await confirmAssessmentAction(page, 'continue_nuclei_snapshot')
    await expect(confirm).toContainText('Run this assessment plan?')
    const startResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname.endsWith('/assessment-batches')
    })
    await confirmAssessmentAction(page, 'start')
    expect((await startResponse).status()).toBe(202)
    expect(fixture.startBody).toMatchObject({
      confirmed: true,
      nuclei_snapshot_confirmed: true,
      standard_confirmed: false,
    })
    await expect(section).toContainText('Assessment batch')
    await expect(section).toContainText('Running')
    await expect(section.getByRole('button', { name: 'Open run' })).toBeVisible()

    const explorerBody = page.locator('#project-explorer-body')
    const scrollBeforePoll = await explorerBody.evaluate((node) => {
      node.style.height = '220px'
      node.style.overflow = 'auto'
      node.scrollTop = node.scrollHeight
      return node.scrollTop
    })
    expect(scrollBeforePoll).toBeGreaterThan(0)
    await section.getByRole('button', { name: 'Open run' }).evaluate((node) => {
      node.focus({ preventScroll: true })
    })
    const polledBatch = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'GET'
        && url.pathname === '/assessment-batches/wfx_assessment_batch_playwright'
    })
    expect((await polledBatch).status()).toBe(200)
    await expect(section.getByRole('button', { name: 'Open run' })).toBeFocused()
    await expect.poll(() => explorerBody.evaluate(node => node.scrollTop)).toBe(scrollBeforePoll)

    await page.keyboard.press('Escape')
    await expect(page.locator('#project-workspace-overlay')).not.toHaveClass(/\bopen\b/)
    await openRailAction(page, 'status-monitor')
    const monitor = page.locator('#status-monitor')
    await expect(monitor).toBeVisible()
    await expect(monitor.locator('.status-monitor-assessment-section')).toContainText(
      'Assessment batch project',
    )
    await expect(monitor.locator('.status-monitor-assessment-section')).toContainText(
      'ping -c 4 -W 2 127.0.0.1',
    )
    await monitor.getByRole('button', { name: 'View batch' }).click()
    await expect(monitor).toBeHidden()
    await expect(page.locator('#project-workspace-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#project-explorer-body .project-assessment-batch')).toContainText(
      'wfx_assessment_batch_playwright',
    )

    await page.reload({ waitUntil: 'domcontentloaded' })
    await ensurePromptReady(page, { timeout: 30_000 })
    await openAssessment(page)
    const restored = page.locator('#project-explorer-body .project-assessment-batch')
    await expect(restored).toContainText('ping -c 4 -W 2 127.0.0.1')
    await expect(restored.getByRole('button', { name: 'Open run' })).toBeVisible()
    await expect(restored).toContainText('Recent activity')

    await restored.getByRole('button', { name: 'Cancel batch' }).click()
    await expect(page.locator('#confirm-host')).toContainText(
      'Active commands receive a cancellation request',
    )
    const cancelResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname.endsWith('/cancel')
    })
    await confirmAssessmentAction(page, 'cancel_batch')
    expect((await cancelResponse).status()).toBe(200)
    await expect(restored).toContainText('Canceled')

    const retryPreviewResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname.endsWith('/retry-previews')
    })
    await restored.getByRole('button', { name: 'Retry failed or unfinished' }).click()
    expect((await retryPreviewResponse).status()).toBe(201)
    await expect(restored).toContainText('Commands that already succeeded remain unchanged')
    await restored.getByRole('button', { name: 'Start retry' }).click()
    await expect(page.locator('#confirm-host')).toContainText(
      'Retry failed or unfinished assessment commands?',
    )
    const retryResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname.endsWith('/retry')
    })
    await confirmAssessmentAction(page, 'start_retry')
    expect((await retryResponse).status()).toBe(202)
    expect(fixture.retryBody).toMatchObject({
      preview_id: 'abp_assessment_batch_retry_playwright',
      confirmed: true,
      standard_confirmed: false,
    })
    await expect(restored).toContainText('retry of wfx_assessment_batch_playwright')
    await expect(restored.getByRole('button', { name: 'Open run' })).toBeVisible()
  })

  test('preserves focus through lifecycle and destructive confirmations', async ({ page }) => {
    test.setTimeout(90_000)
    const projectName = `Assessment Lifecycle ${Date.now()}`
    const created = await createAssessmentProject(page, projectName)
    await addAssessmentTargets(
      page,
      created.project.id,
      Array.from({ length: 11 }, (_, index) => ({ type: 'ip', value: `127.0.0.${index + 2}` })),
    )
    await openAssessment(page)
    const assessment = page.locator('#project-explorer-body .project-assessment-root')
    await assessment.locator('.project-assessment-start-form select').selectOption('network')
    await assessment.locator('.project-assessment-start-form button[type="submit"]').click()
    await expect(assessment).toContainText('Network assessment')

    const targetList = assessment.locator('.project-assessment-target-list')
    const firstTarget = targetList.locator('.project-assessment-target-toggle').first()
    await firstTarget.click()
    await expect(firstTarget).toHaveAttribute('aria-expanded', 'true')
    await expect.poll(() => targetList.evaluate(node => node.scrollHeight > node.clientHeight)).toBe(true)
    await targetList.evaluate((node) => {
      node.scrollTop = 120
      node.dispatchEvent(new Event('scroll'))
    })
    await expect.poll(() => targetList.evaluate(node => node.scrollTop)).toBe(120)

    const complete = assessment.getByRole('button', { name: 'Complete cycle' })
    await complete.focus()
    await complete.click()
    const confirm = page.locator('#confirm-host')
    await expect(confirm).toContainText('Complete cycle: Network assessment?')
    await confirmAssessmentAction(page, 'cancel')
    await expect(complete).toBeFocused()
    await complete.click()
    await confirmAssessmentAction(page, 'completed')
    await expect(assessment.locator('.project-assessment-cycle .badge')).toHaveText('completed')
    await expect(firstTarget).toHaveAttribute('aria-expanded', 'true')
    await expect.poll(() => targetList.evaluate(node => node.scrollTop)).toBe(120)

    await assessment.getByRole('button', { name: 'Archive cycle' }).click()
    await expect(confirm).toContainText('Archived cycles stay available for review')
    await confirmAssessmentAction(page, 'archived')
    await expect(assessment.locator('.project-assessment-cycle .badge')).toHaveText('archived')

    const deleteAssessment = assessment.getByRole('button', { name: 'Delete assessment' })
    await deleteAssessment.click()
    await expect(confirm).toContainText('Source runs, findings, entities, and files stay intact.')
    await confirmAssessmentAction(page, 'cancel')
    await expect(deleteAssessment).toBeFocused()

    await deleteAssessment.click()
    await confirmAssessmentAction(page, 'delete')
    await expect(assessment).toContainText('Start an assessment')
    await expect(assessment.locator('.project-assessment-cycle')).toHaveCount(0)
  })

  test('keeps missing HTTP credentials unavailable and restores the launch control', async ({ page }) => {
    test.setTimeout(90_000)
    await page.route('**/session/secrets', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          scope: 'personal',
          can_manage: true,
          secrets: [{
            name: 'PLAYWRIGHT_BASIC_PASSWORD',
            consumer_envs: ['PLAYWRIGHT_BASIC_PASSWORD', 'HTTP_PASSWORD'],
          }],
        }),
      })
    })
    await page.route('**/projects/*/http-profiles', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          profiles: [{
            id: 'htp_missing_playwright',
            name: 'Member role with missing token',
            role: 'member',
            base_url: 'http://127.0.0.1:1/',
            scope_roots: ['http://127.0.0.1:1/'],
            allowed_hosts: ['127.0.0.1'],
            headers: [],
            secret_refs: { bearer_token: { name: 'MISSING_TOKEN', available: false } },
            file_refs: {},
            credential_use: ['bearer_token'],
            include_paths: [],
            exclude_paths: [],
            rate_limit_per_second: 1,
            concurrency: 1,
            enabled: true,
            protected_references_visible: true,
            reference_counts: { secret_refs: 1, file_refs: 0, headers: 0 },
          }],
          total: 1,
        }),
      })
    })
    await createAssessmentProject(
      page,
      `Assessment Missing Secret ${Date.now()}`,
      { type: 'url', value: 'http://127.0.0.1:1/' },
    )
    await openAssessment(page)

    const assessment = page.locator('#project-explorer-body .project-assessment-root')
    await startAssessmentCycle(page, assessment, 'web', 'Web assessment')

    await page.setViewportSize({ width: 810, height: 766 })
    const newProfile = assessment.getByRole('button', { name: 'New HTTP profile' })
    await newProfile.click()
    const profileEditor = page.locator('#confirm-host .project-http-profile-editor')
    await expect(profileEditor).toBeVisible()
    const passwordSecret = profileEditor.getByLabel('Basic password Secret')
    await expect(passwordSecret).toHaveValue('')
    await expect(passwordSecret.locator('option')).toContainText([
      'Not set',
      'PLAYWRIGHT_BASIC_PASSWORD — HTTP_PASSWORD',
    ])
    await passwordSecret.selectOption('PLAYWRIGHT_BASIC_PASSWORD')
    await expect(passwordSecret).toHaveValue('PLAYWRIGHT_BASIC_PASSWORD')
    await expect(profileEditor).toContainText(
      'Basic authentication needs separate username and password Secrets.',
    )
    const profileLayout = await page.locator('#confirm-host').evaluate((host) => {
      const card = host.querySelector('[data-confirm-card]')?.getBoundingClientRect()
      const editor = host.querySelector('.project-http-profile-editor')?.getBoundingClientRect()
      if (!card || !editor) return null
      return {
        cardLeft: card.left,
        cardRight: card.right,
        editorLeft: editor.left,
        editorRight: editor.right,
      }
    })
    expect(profileLayout).not.toBeNull()
    expect(profileLayout.editorLeft).toBeGreaterThanOrEqual(profileLayout.cardLeft)
    expect(profileLayout.editorRight).toBeLessThanOrEqual(profileLayout.cardRight)
    await confirmAssessmentAction(page, 'cancel')
    await expect(profileEditor).toBeHidden()

    await assessment.locator('.project-assessment-target-toggle').click()
    const runHttpx = assessment.getByRole('button', { name: 'Run Httpx' })
    await runHttpx.click()

    const confirm = page.locator('#confirm-host')
    await expect(confirm).toContainText('Choose the web role for this run.')
    const missingOption = confirm.locator('option', { hasText: 'Member role with missing token' })
    await expect(missingOption).toContainText('missing Secret')
    await expect(missingOption).toHaveAttribute('disabled', '')
    // Assessment data can finish refreshing while the role picker is open.
    // Model that rerender so focus restoration must find the live replacement
    // instead of relying on the detached button that opened the dialog.
    await runHttpx.evaluate((button) => button.replaceWith(button.cloneNode(true)))
    await confirmAssessmentAction(page, 'cancel')
    await expect(runHttpx).toBeFocused()
  })

  test('switches personal and team scope while archived team assessments stay read-only', async ({ page }) => {
    test.setTimeout(120_000)
    await issueAndActivateSessionToken(page)
    const suffix = Date.now().toString(36)
    const team = await createAndSelectTeam(page, suffix)
    const projectName = `Archived Team Assessment ${suffix}`
    const { project, assessment } = await startNetworkAssessment(page, projectName)
    await expect(assessment.getByRole('button', { name: 'Run Ping' })).toBeEnabled()

    const archived = await page.evaluate(async (teamId) => {
      const response = await apiFetch(`/session/teams/${encodeURIComponent(teamId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'archived' }),
      })
      if (!response.ok) throw new Error(`team archive failed: ${response.status}`)
      await window.DarklabTeamScope.refreshTeamScopes()
      return window.DarklabTeamScope.getActiveTeam()
    }, team.id)
    expect(archived.status).toBe('archived')

    await page.locator('[data-project-tab="details"]').click()
    await page.locator('[data-project-tab="assessment"]').click()
    await expect(assessment.getByRole('button', { name: 'Run Ping' })).toBeDisabled()
    await expect(assessment.getByRole('button', { name: 'Complete cycle' })).toBeDisabled()
    await expect(assessment.getByRole('button', { name: 'Archive cycle' })).toBeDisabled()

    const personalProjects = await page.evaluate(async () => {
      window.DarklabTeamScope.setActiveTeamId('')
      const response = await apiFetch('/projects', { cache: 'no-store' })
      if (!response.ok) throw new Error(`personal project list failed: ${response.status}`)
      return (await response.json()).projects || []
    })
    await expect(page.locator('#team-scope-label')).toHaveText('Personal')
    expect(personalProjects.some((item) => item.id === project.id)).toBe(false)

    await page.evaluate((teamId) => window.DarklabTeamScope.setActiveTeamId(teamId), team.id)
    await expect(page.locator('#team-scope-label')).toHaveText(team.name)
    const teamProjects = await page.evaluate(async () => {
      const response = await apiFetch('/projects?include_archived=1', { cache: 'no-store' })
      if (!response.ok) throw new Error(`team project list failed: ${response.status}`)
      return (await response.json()).projects || []
    })
    expect(teamProjects.some((item) => item.id === project.id)).toBe(true)
  })

  test.describe('mobile assessment lifecycle', () => {
    test.use({
      hasTouch: true,
      isMobile: true,
      viewport: { width: 390, height: 844 },
    })

    test('archives and deletes a cycle through the shared action sheet', async ({ page }, testInfo) => {
      test.setTimeout(90_000)
      const projectName = `Mobile Assessment ${Date.now()}`
      const { project } = await createAssessmentProject(page, projectName)
      const monitoring = seedProjectMonitoringFixture(testInfo, {
        sessionId: await browserSessionId(page),
        projectId: project.id,
      })
      await page.locator('#hamburger-btn').click()
      await page.locator('#mobile-menu-sheet [data-menu-action="projects"]').click()
      await expect(page.locator('#project-mobile-root')).toBeVisible()
      const projectRow = page.locator('.project-mobile-row').filter({ hasText: projectName }).first()
      await projectRow.locator('[data-project-mobile-action="open-project"]').click()
      await page.locator('[data-project-mobile-detail-tab="assessment"]').click()
      const assessment = page.locator('#project-mobile-detail-body .project-assessment-root')
      await assessment.locator('.project-assessment-start-form select').selectOption('network')
      await assessment.locator('.project-assessment-start-form button[type="submit"]').click()
      await expect(assessment).toContainText('Network assessment')

      const batchPlan = assessment.locator('.project-assessment-batch')
      await expect(batchPlan.getByRole('button', { name: 'Preview assessment plan' })).toBeVisible()
      const selectorLayout = await batchPlan.locator('.project-assessment-batch-selector').evaluateAll(
        (selectors) => selectors.slice(0, 2).map((selector) => {
          const box = selector.getBoundingClientRect()
          return { top: box.top, right: box.right, bottom: box.bottom }
        }),
      )
      expect(selectorLayout).toHaveLength(2)
      expect(selectorLayout[1].top).toBeGreaterThanOrEqual(selectorLayout[0].bottom - 1)
      expect(selectorLayout.every(item => item.right <= page.viewportSize().width + 1)).toBe(true)

      const cycleActions = assessment.getByRole('button', { name: 'Cycle actions' })
      const sheet = page.locator('#action-sheet-overlay')
      await cycleActions.click()
      await expect(sheet).toHaveClass(/\bopen\b/)
      await sheet.getByRole('button', { name: 'Archive cycle' }).click()
      await confirmAssessmentAction(page, 'archived')
      await expect(assessment.locator('.project-assessment-cycle .badge')).toHaveText('archived')

      await cycleActions.click()
      await sheet.getByRole('button', { name: 'Delete assessment' }).click()
      await expect(page.locator('#confirm-host')).toContainText(
        'Source runs, findings, entities, and files stay intact.',
      )
      await confirmAssessmentAction(page, 'delete')
      await expect(assessment).toContainText('Start an assessment')

      const monitoringResponse = page.waitForResponse((response) => {
        const url = new URL(response.url())
        return response.request().method() === 'GET'
          && url.pathname === `/projects/${project.id}/monitoring`
      })
      await page.locator('[data-project-mobile-detail-tab="monitoring"]').click()
      expect((await monitoringResponse).ok()).toBe(true)

      const monitoringRoot = page.locator(
        `#project-mobile-detail-body [data-project-monitoring-root="${project.id}"].is-mobile`,
      )
      await expect(monitoringRoot).toBeVisible({ timeout: 15_000 })
      const riskRow = monitoringRoot.locator(
        `[data-project-monitoring-risk-id="${monitoring.riskEventId}"]`,
      )
      await expect(riskRow).toContainText('CVE-2026-10001')
      await expect(riskRow).toContainText('Added to CISA KEV')
      const watcherRow = monitoringRoot.locator(
        `[data-project-monitoring-fire-id="${monitoring.changedFireId}"]`,
      ).first()
      await expect(watcherRow).toContainText('New')

      await riskRow.locator('[data-project-monitoring-risk-note]').fill('Reviewed on mobile.')
      const acknowledgeResponse = page.waitForResponse((response) => {
        const url = new URL(response.url())
        return response.request().method() === 'PATCH'
          && url.pathname === `/projects/${project.id}/monitoring/risk-events/${monitoring.riskEventId}`
      })
      await riskRow.locator(
        '[data-project-monitoring-action="ack-risk"][data-ack-state="acknowledged"]',
      ).click()
      expect((await acknowledgeResponse).ok()).toBe(true)
      await expect(monitoringRoot.locator(
        `[data-project-monitoring-risk-id="${monitoring.riskEventId}"]`,
      )).toContainText('Acknowledged')
      await expect(monitoringRoot.locator(
        `[data-project-monitoring-fire-id="${monitoring.changedFireId}"]`,
      ).first()).toContainText('New')
    })
  })
})
