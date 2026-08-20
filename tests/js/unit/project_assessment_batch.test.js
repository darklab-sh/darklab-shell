// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createProjectAssessmentBatchManager } from '../../../app/static/js/features/projects/project_assessment_batch.js'

const assessment = {
  id: 'asmt_batch_1',
  title: 'Network assessment',
  status: 'active',
}

const detail = {
  target_rollups: [{
    target_entity_id: 'ent_batch_1',
    target_type: 'domain',
    target_value: 'batch.example.test',
    total_checks: 4,
  }],
  category_rollups: [{
    category: 'discovery',
    applicable_checks: 4,
  }],
}

const preview = {
  preview_id: 'abp_batch_1',
  project_id: 'prj_batch_1',
  assessment_id: assessment.id,
  source_batch_id: '',
  plan_digest: 'a'.repeat(64),
  selected_item_count: 1,
  candidate_item_count: 2,
  potential_covered_check_count: 2,
  concurrency: { batch: 8, target: 1, owner: 16, instance: 32 },
  summary: {
    selected_target_count: 1,
    potential_covered_check_count: 2,
    fan_out: 1,
    explicit_request_limit_item_count: 1,
    tool_bounded_request_item_count: 0,
    maximum_item_duration_bound_seconds: 600,
    credential_classification: 'none',
    estimated_min_seconds: 10,
    estimated_max_seconds: 40,
    estimate_label: 'Planning estimate, not a completion promise.',
    requires_standard_confirmation: false,
    reason_counts: { already_covered: 1 },
    target_review_hints: [{
      target_entity_id: 'ent_batch_1',
      hints: [{ reason: 'This confirmed target came from discovery.' }],
    }],
  },
}

const previewItems = [{
  item_index: 0,
  selected: true,
  policy_level: 'safe',
  action: { id: 'nmap' },
  target: { entity_id: 'ent_batch_1', type: 'domain', value: 'batch.example.test' },
  display_command: 'nmap -sT -sV batch.example.test',
  bounds: { summary: 'One approved target with a ten-minute host timeout.' },
  duration_bound_seconds: 600,
  check_mappings: [{ check_id: 'chk_1' }, { check_id: 'chk_2' }],
}, {
  item_index: 1,
  selected: false,
  policy_level: 'standard',
  action: { id: 'nmap' },
  target: { entity_id: 'ent_batch_1', type: 'domain', value: 'batch.example.test' },
  display_command: 'nmap -sT -sV --script safe batch.example.test',
  bounds: { summary: 'One approved target.' },
  duration_bound_seconds: 600,
  check_mappings: [{ check_id: 'chk_3' }],
}]

const activeBatch = {
  schema_version: 1,
  batch_id: 'wfx_batch_1',
  assessment_id: assessment.id,
  project_id: 'prj_batch_1',
  status: 'running',
  item_count: 1,
  created: '2026-08-17T10:00:00Z',
  progress: {
    total: 1,
    pending: 0,
    launching: 0,
    running: 1,
    succeeded: 0,
    failed: 0,
    unavailable: 0,
    canceled: 0,
    skipped: 0,
    could_not_cancel: 0,
    settled: 0,
  },
}

const batchItem = {
  item_index: 0,
  action_id: 'nmap',
  target: { entity_id: 'ent_batch_1', type: 'domain', value: 'batch.example.test' },
  policy_level: 'safe',
  display_command: 'nmap -sT -sV batch.example.test',
  check_count: 2,
  attempt: 1,
  status: 'running',
  run_id: 'run_batch_1',
}

function response(payload, ok = true) {
  return { ok, status: ok ? 200 : 400, json: vi.fn(async () => payload) }
}

function context(projectWorkspaceRequest, overrides = {}) {
  return {
    projectWorkspaceRequest,
    projectResponseError: vi.fn(async (_resp, fallback) => new Error(fallback)),
    bindProjectRuntimePressable: vi.fn((button, options = {}) => {
      if (options.onActivate) button.addEventListener('click', options.onActivate)
      return button
    }),
    emptyProjectPanel: vi.fn((text) => {
      const panel = document.createElement('div')
      panel.textContent = text
      return panel
    }),
    renderProjectExplorer: vi.fn(),
    renderProjectMobileDetail: vi.fn(),
    setProjectWorkspaceMessage: vi.fn(),
    showConfirm: vi.fn(async options => options.confirmId),
    openHistoryRunDetails: vi.fn(),
    formatDate: vi.fn(value => String(value || '')),
    assessmentBatchLimits: vi.fn(() => ({
      item_limit: 128,
      max_parallel: 8,
      max_owner_parallel: 16,
      max_instance_parallel: 32,
    })),
    canRunCommands: vi.fn(() => true),
    logClientError: vi.fn(),
    ...overrides,
  }
}

function render(manager) {
  const root = document.createElement('div')
  root.appendChild(manager.renderSection('prj_batch_1', assessment, detail))
  return root
}

beforeEach(() => {
  vi.useFakeTimers()
  document.body.replaceChildren()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('Project assessment batches', () => {
  it('focuses a batch outside the first history page by loading its exact id', async () => {
    const requestedBatch = {
      ...activeBatch,
      batch_id: 'abx_exact_history',
      status: 'completed',
      progress: { ...activeBatch.progress, running: 0, succeeded: 1, settled: 1 },
    }
    const projectWorkspaceRequest = vi.fn(async (url) => {
      const value = String(url)
      if (value.startsWith('/projects/prj_batch_1/assessment-batches?')) {
        return response({ batches: [], has_more: true })
      }
      if (value === '/assessment-batches/abx_exact_history') {
        return response({ batch: requestedBatch })
      }
      if (value.endsWith('/items?cursor=0&limit=100')) {
        return response({ items: [{ ...batchItem, status: 'succeeded' }], next_cursor: null })
      }
      if (value.includes('/events?')) {
        return response({ events: [], next_cursor: null, has_more: false })
      }
      throw new Error(`Unexpected request: ${url}`)
    })
    const manager = createProjectAssessmentBatchManager(
      context(projectWorkspaceRequest),
      { renderViews: vi.fn() },
    )

    expect(await manager.focusBatch(
      'prj_batch_1',
      assessment.id,
      requestedBatch.batch_id,
    )).toBe(true)
    const state = manager.stateFor('prj_batch_1', assessment.id)
    expect(state.selectedBatchId).toBe(requestedBatch.batch_id)
    expect(state.batch).toEqual(requestedBatch)
    expect(projectWorkspaceRequest).toHaveBeenCalledWith(
      '/assessment-batches/abx_exact_history',
      { cache: 'no-store' },
    )
    manager.invalidate()
  })

  it('does not offer a new plan on a terminal cycle without batch history', async () => {
    const projectWorkspaceRequest = vi.fn(async (url) => {
      if (String(url).startsWith('/projects/prj_batch_1/assessment-batches?')) {
        return response({ batches: [], has_more: false })
      }
      throw new Error(`Unexpected request: ${url}`)
    })
    const manager = createProjectAssessmentBatchManager(
      context(projectWorkspaceRequest),
      { renderViews: vi.fn() },
    )
    await manager.load('prj_batch_1', assessment.id, { render: false })

    expect(manager.renderSection(
      'prj_batch_1',
      { ...assessment, status: 'completed' },
      detail,
    )).toBeNull()
    manager.invalidate()
  })

  it('previews safe commands, marks standard work separately, and starts one confirmed batch', async () => {
    const requests = []
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      requests.push({ url: String(url), options })
      if (String(url).startsWith('/projects/prj_batch_1/assessment-batches?')) {
        return response({ batches: [], has_more: false })
      }
      if (String(url).endsWith('/batch-previews')) return response({ preview })
      if (String(url).startsWith('/assessment-batch-previews/')) {
        return response({ items: previewItems, next_cursor: null })
      }
      if (String(url).endsWith('/assessment-batches')) {
        return response({ batch: activeBatch, launch: { launched: 1 } })
      }
      if (String(url).endsWith('/items?cursor=0&limit=100')) {
        return response({ items: [batchItem], next_cursor: null })
      }
      if (String(url).endsWith('/events?cursor=0&limit=100')) {
        return response({ events: [], next_cursor: null, has_more: false })
      }
      throw new Error(`Unexpected request: ${url}`)
    })
    const ctx = context(projectWorkspaceRequest, {
      assessmentBatchLimits: vi.fn(() => ({
        item_limit: 512,
        max_parallel: 8,
        max_owner_parallel: 16,
        max_instance_parallel: 32,
      })),
    })
    const renderViews = vi.fn()
    const manager = createProjectAssessmentBatchManager(ctx, { renderViews })

    await manager.load('prj_batch_1', assessment.id, { render: false })
    const scrollHost = document.createElement('div')
    scrollHost.className = 'project-explorer-body'
    let surface = manager.renderSection('prj_batch_1', assessment, detail)
    scrollHost.appendChild(surface)
    document.body.appendChild(scrollHost)
    scrollHost.scrollTop = 61
    expect(surface.textContent).toContain('Safe checks are selected by default')
    expect(surface.textContent).toContain('Include standard checks')
    const commandLimit = [...surface.querySelectorAll('label')]
      .find(label => label.textContent.includes('Command limit'))
      .querySelector('select')
    expect([...commandLimit.options].map(option => option.value)).toEqual(['128', '256', '512'])
    commandLimit.value = '512'
    commandLimit.dispatchEvent(new Event('change', { bubbles: true }))
    surface.querySelector('button.btn-primary').click()
    expect(surface.textContent).toContain('Building preview…')
    expect(scrollHost.scrollTop).toBe(61)
    expect(document.querySelector('.project-assessment-batch')).toBe(surface)
    expect(renderViews).not.toHaveBeenCalled()
    await vi.waitFor(() => expect(
      manager.stateFor('prj_batch_1', assessment.id).preview?.preview_id,
    ).toBe(preview.preview_id))
    await vi.waitFor(() => expect(
      manager.stateFor('prj_batch_1', assessment.id).previewing,
    ).toBe(false))
    expect(scrollHost.scrollTop).toBe(61)

    const previewRequest = requests.find(item => item.url.endsWith('/batch-previews'))
    expect(JSON.parse(previewRequest.options.body)).toMatchObject({
      include_standard: false,
      item_limit: 512,
      max_parallel: 8,
      max_owner_parallel: 16,
      max_instance_parallel: 32,
    })
    const decision = surface.querySelector('.project-assessment-batch-decision')
    expect(decision.textContent).toContain('Ready to run')
    expect(decision.textContent).toContain('The reviewed plan can start now.')
    const commandToggle = [...surface.querySelectorAll('button')]
      .find(button => button.textContent.includes('Exact commands (2)'))
    const commandList = surface.querySelector('.project-assessment-batch-command-list')
    expect(commandToggle.getAttribute('aria-expanded')).toBe('false')
    expect(commandToggle.textContent).toContain('2 loaded · 1 selected')
    expect(commandList.classList.contains('u-hidden')).toBe(true)
    commandToggle.click()
    expect(commandToggle.getAttribute('aria-expanded')).toBe('true')
    expect(commandList.classList.contains('u-hidden')).toBe(false)
    expect(commandList.textContent).toContain('safe')
    expect(commandList.textContent).toContain('standard · not selected')
    const exclusionsToggle = [...surface.querySelectorAll('button')]
      .find(button => button.textContent.includes('Not included in this plan (1)'))
    expect(exclusionsToggle.getAttribute('aria-expanded')).toBe('false')
    exclusionsToggle.click()
    expect(surface.querySelector('.project-assessment-batch-exclusions').textContent)
      .toContain('Already covered: 1')
    expect(surface.textContent).toContain('Review scope')

    const start = [...surface.querySelectorAll('button')]
      .find(button => button.textContent === 'Run assessment plan')
    start.click()
    await vi.waitFor(() => expect(
      requests.some(item => item.url.endsWith('/assessment-batches')),
    ).toBe(true))
    await vi.waitFor(() => expect(manager.stateFor('prj_batch_1', assessment.id).starting).toBe(false))

    const startRequest = requests.find(item => item.url.endsWith('/assessment-batches'))
    expect(JSON.parse(startRequest.options.body)).toEqual({
      preview_id: preview.preview_id,
      plan_digest: preview.plan_digest,
      confirmed: true,
      nuclei_snapshot_confirmed: false,
      standard_confirmed: false,
    })
    expect(ctx.showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      confirmId: 'start',
      refocusOnResolve: false,
    }))
    surface = render(manager)
    expect(surface.textContent).toContain('Assessment batch')
    expect(surface.textContent).toContain('Running')
    expect(surface.textContent).toContain('Open run')
    manager.invalidate()
  })

  it('keeps preview available to viewers while disabling start and invalidating changed selections', async () => {
    let latestPreviewBody = null
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (String(url).startsWith('/projects/prj_batch_1/assessment-batches?')) {
        return response({ batches: [] })
      }
      if (String(url).endsWith('/batch-previews')) {
        latestPreviewBody = JSON.parse(options.body)
        const standard = latestPreviewBody.include_standard
        return response({
          preview: {
            ...preview,
            selected_item_count: standard ? 2 : 1,
            summary: {
              ...preview.summary,
              requires_standard_confirmation: standard,
              nuclei_preflight: {
                state: 'incompatible',
                source_label: 'Managed local cache',
                release_version: 'v10.4.7',
                content_digest: `sha256:${'1'.repeat(64)}`,
                manifest_entry_count: 100,
                refreshed_at: '2026-08-10T12:00:00Z',
                validation_state: 'failed',
                nuclei_version: 'v3.4.10',
                stale_after_seconds: 604800,
                reason_code: 'template_validation_failed',
                launchable: false,
                command_count: 1,
                refresh_enabled: true,
                operator_action: 'Ask an operator with Run commands access to update the managed templates.',
              },
            },
          },
        })
      }
      if (String(url).startsWith('/assessment-batch-previews/')) {
        return response({ items: previewItems, next_cursor: null })
      }
      throw new Error(`Unexpected request: ${url}`)
    })
    const renderViews = vi.fn()
    const manager = createProjectAssessmentBatchManager(
      context(projectWorkspaceRequest, { canRunCommands: vi.fn(() => false) }),
      { renderViews },
    )
    await manager.load('prj_batch_1', assessment.id, { render: false })
    let surface = render(manager)
    surface.querySelector('button.btn-primary').click()
    await vi.waitFor(() => expect(
      manager.stateFor('prj_batch_1', assessment.id).preview?.preview_id,
    ).toBe(preview.preview_id))

    renderViews.mockClear()
    const scrollHost = document.createElement('div')
    scrollHost.className = 'project-explorer-body'
    surface = manager.renderSection('prj_batch_1', assessment, detail)
    scrollHost.appendChild(surface)
    document.body.appendChild(scrollHost)
    const commandLimit = [...surface.querySelectorAll('label')]
      .find(label => label.textContent.includes('Command limit'))
      .querySelector('select')
    expect([...commandLimit.options].map(option => option.value)).toEqual(['128'])
    scrollHost.scrollTop = 73
    const standard = [...surface.querySelectorAll('label')]
      .find(label => label.textContent.includes('Include standard checks'))
    const standardInput = standard.querySelector('input')
    standardInput.focus()
    standardInput.checked = true
    standardInput.dispatchEvent(new Event('change', { bubbles: true }))
    await vi.waitFor(() => expect(
      manager.stateFor('prj_batch_1', assessment.id).previewDirty,
    ).toBe(true))
    expect(document.querySelector('.project-assessment-batch')).toBe(surface)
    expect(scrollHost.scrollTop).toBe(73)
    expect(surface.querySelector('[data-assessment-batch-focus-key="include-standard"]'))
      .toBe(document.activeElement)
    expect(renderViews).not.toHaveBeenCalled()
    expect(surface.textContent).toContain('Selection changed. Refresh the preview before starting.')
    expect(surface.textContent).toContain('Managed Nuclei template preflight')
    expect(surface.textContent).toContain("Nuclei work can't start")
    expect([...surface.querySelectorAll('button')].find(button => button.textContent === 'Run assessment plan').disabled).toBe(true)
    expect(surface.textContent).toContain('Ask an operator with Run commands access')
    expect(surface.textContent).not.toContain('Update templates and rebuild preview')

    const refresh = [...surface.querySelectorAll('button')]
      .find(button => button.textContent === 'Refresh preview')
    refresh.click()
    expect(surface.textContent).toContain('Building preview…')
    expect(scrollHost.scrollTop).toBe(73)
    await vi.waitFor(() => expect(latestPreviewBody?.include_standard).toBe(true))
    await vi.waitFor(() => expect(manager.stateFor('prj_batch_1', assessment.id).previewing).toBe(false))
    expect(latestPreviewBody.include_standard).toBe(true)
    expect(surface.textContent).toContain('Templates need attention')
    expect(surface.textContent).toContain('Nuclei template preflight must pass')
    expect(scrollHost.scrollTop).toBe(73)
    expect(renderViews).not.toHaveBeenCalled()
    manager.invalidate()
  })

  it('requires a distinct confirmation before starting selected standard commands', async () => {
    const standardPreview = {
      ...preview,
      selected_item_count: 2,
      summary: {
        ...preview.summary,
        requires_standard_confirmation: true,
        nuclei_preflight: {
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
          operator_action: 'Ask an operator with Run commands access to update the managed templates.',
        },
      },
    }
    const refreshedPreview = {
      ...standardPreview,
      preview_id: 'abp_batch_refreshed',
      plan_digest: 'b'.repeat(64),
      summary: {
        ...standardPreview.summary,
        nuclei_preflight: {
          ...standardPreview.summary.nuclei_preflight,
          state: 'ready',
          content_digest: `sha256:${'2'.repeat(64)}`,
          refreshed_at: '2026-08-19T12:00:00Z',
          reason_code: '',
        },
      },
    }
    let startBody = null
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (String(url).startsWith('/projects/prj_batch_1/assessment-batches?')) {
        return response({ batches: [] })
      }
      if (String(url).endsWith('/batch-previews')) return response({ preview: standardPreview })
      if (String(url).endsWith('/nuclei-templates/refresh')) {
        return response({ preview: refreshedPreview, refresh: { status: 'updated' } })
      }
      if (String(url).startsWith('/assessment-batch-previews/')) {
        return response({ items: previewItems.map(item => ({ ...item, selected: true })), next_cursor: null })
      }
      if (String(url).endsWith('/assessment-batches')) {
        startBody = JSON.parse(options.body)
        return response({ batch: activeBatch, launch: { launched: 1 } })
      }
      if (String(url).endsWith('/items?cursor=0&limit=100')) {
        return response({ items: [batchItem], next_cursor: null })
      }
      if (String(url).endsWith('/events?cursor=0&limit=100')) {
        return response({ events: [], has_more: false })
      }
      throw new Error(`Unexpected request: ${url}`)
    })
    const ctx = context(projectWorkspaceRequest)
    const renderViews = vi.fn()
    const manager = createProjectAssessmentBatchManager(ctx, { renderViews })
    await manager.load('prj_batch_1', assessment.id, { render: false })
    const st = manager.stateFor('prj_batch_1', assessment.id)
    st.selection.includeStandard = true
    let surface = render(manager)
    surface.querySelector('button.btn-primary').click()
    await vi.waitFor(() => expect(st.preview?.preview_id).toBe(preview.preview_id))

    renderViews.mockClear()
    const scrollHost = document.createElement('div')
    scrollHost.className = 'project-explorer-body'
    surface = manager.renderSection('prj_batch_1', assessment, detail)
    scrollHost.appendChild(surface)
    document.body.appendChild(scrollHost)
    scrollHost.scrollTop = 89
    expect(surface.textContent).toContain('Managed Nuclei template preflight')
    expect(surface.textContent).toContain('v10.4.7')
    const start = [...surface.querySelectorAll('button')]
      .find(button => button.textContent === 'Run assessment plan')
    start.click()
    await vi.waitFor(() => expect(st.preview?.preview_id).toBe('abp_batch_refreshed'))
    expect(document.querySelector('.project-assessment-batch')).toBe(surface)
    expect(scrollHost.scrollTop).toBe(89)
    expect(renderViews).not.toHaveBeenCalled()
    expect(startBody).toBeNull()
    expect(ctx.showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      confirmId: 'update_nuclei_templates',
      tone: 'warning',
      refocusOnResolve: false,
      actions: expect.arrayContaining([
        expect.objectContaining({ id: 'update_nuclei_templates', role: 'primary' }),
        expect.objectContaining({ id: 'continue_nuclei_snapshot' }),
        expect.objectContaining({ id: 'cancel' }),
      ]),
    }))
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith(
      'Managed Nuclei templates updated. Review the rebuilt plan before starting it.',
    )

    surface = render(manager)
    const refreshedStart = [...surface.querySelectorAll('button')]
      .find(button => button.textContent === 'Run assessment plan')
    expect(refreshedStart.disabled).toBe(false)
    expect([...surface.querySelectorAll('button')]
      .some(button => button.textContent === 'Update templates and rebuild preview')).toBe(false)

    manager.invalidate('prj_batch_1', { preserveDrafts: true })
    expect(st.preview?.preview_id).toBe('abp_batch_refreshed')
    expect(st.loaded).toBe(false)
    await manager.load('prj_batch_1', assessment.id, { render: false })
    surface = render(manager)
    const restoredStart = [...surface.querySelectorAll('button')]
      .find(button => button.textContent === 'Run assessment plan')
    expect(restoredStart.disabled).toBe(false)
    expect([...surface.querySelectorAll('button')]
      .some(button => button.textContent === 'Update templates and rebuild preview')).toBe(false)
    restoredStart.click()
    await vi.waitFor(() => expect(startBody).not.toBeNull())

    expect(startBody.standard_confirmed).toBe(true)
    expect(startBody.nuclei_snapshot_confirmed).toBe(false)
    expect(ctx.showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      confirmId: 'start_standard',
      tone: 'warning',
      refocusOnResolve: false,
    }))
    expect(ctx.showConfirm.mock.calls.at(-1)[0].body.text)
      .toBe('Run safe and standard assessment commands?')
    expect(ctx.showConfirm.mock.calls.at(-1)[0].body.note).toBe(
      '1 target; 2 commands; fan-out 1 with up to 8 concurrent; request bounds: 1 explicit-limit and 0 tool-bounded commands; maximum per-command time bound 600 seconds; credentials: none.',
    )
    manager.invalidate()
  })

  it('restores an active monitor after reload, opens child runs, and requests truthful cancellation', async () => {
    const partialBatch = {
      ...activeBatch,
      item_count: 5,
      progress: {
        ...activeBatch.progress,
        total: 5,
        running: 1,
        failed: 1,
        unavailable: 1,
        canceled: 1,
        could_not_cancel: 1,
        settled: 4,
      },
    }
    const partialItems = [
      batchItem,
      {
        ...batchItem,
        item_index: 1,
        status: 'failed',
        run_id: '',
        display_command: 'nmap -sT failed.example.test',
        execution_command: 'nmap --token private-execution-value failed.example.test',
        private_values: ['private-profile-value'],
      },
      { ...batchItem, item_index: 2, status: 'unavailable', run_id: '' },
      { ...batchItem, item_index: 3, status: 'canceled', run_id: '' },
      { ...batchItem, item_index: 4, status: 'could_not_cancel', run_id: '' },
    ]
    const canceledBatch = {
      ...partialBatch,
      status: 'canceling',
      progress: { ...partialBatch.progress, status: 'canceling' },
    }
    const projectWorkspaceRequest = vi.fn(async (url) => {
      if (String(url).startsWith('/projects/prj_batch_1/assessment-batches?')) {
        return response({ batches: [partialBatch], has_more: false })
      }
      if (String(url).endsWith('/items?cursor=0&limit=100')) {
        return response({ items: partialItems, next_cursor: null })
      }
      if (String(url).endsWith('/events?cursor=0&limit=100')) {
        return response({
          events: [{
            sequence: 1,
            event_type: 'item_run_bound',
            item_ordinal: 0,
            status: 'running',
            created: '2026-08-17T10:00:01Z',
          }],
          has_more: false,
        })
      }
      if (String(url).endsWith('/cancel')) {
        return response({ batch: canceledBatch, signal_failures: 0 })
      }
      throw new Error(`Unexpected request: ${url}`)
    })
    const ctx = context(projectWorkspaceRequest)
    const manager = createProjectAssessmentBatchManager(ctx, { renderViews: vi.fn() })
    await manager.load('prj_batch_1', assessment.id, { render: false })

    let surface = render(manager)
    const badgeFor = label => [...surface.querySelectorAll('.badge')]
      .find(item => item.textContent === label)
    expect(badgeFor('Running')?.classList.contains('badge-tone-amber')).toBe(true)
    expect(badgeFor('Failed')?.classList.contains('badge-tone-red')).toBe(true)
    expect(badgeFor('Unavailable')?.classList.contains('badge-tone-muted')).toBe(true)
    expect(badgeFor('Canceled')?.classList.contains('badge-tone-muted')).toBe(true)
    expect(badgeFor('Could not cancel')?.classList.contains('badge-tone-red')).toBe(true)
    expect(surface.textContent).toContain('4 / 5')
    expect(surface.textContent).not.toContain('private-execution-value')
    expect(surface.textContent).not.toContain('private-profile-value')
    expect(surface.textContent).toContain('Recent activity')
    expect(surface.textContent).toContain('Running · command 1')
    surface.querySelector('.project-assessment-batch-command .btn').click()
    expect(ctx.openHistoryRunDetails).toHaveBeenCalledWith({
      id: 'run_batch_1',
      command: batchItem.display_command,
    })

    const cancel = [...surface.querySelectorAll('button')]
      .find(button => button.textContent === 'Cancel batch')
    cancel.click()
    await vi.waitFor(() => expect(projectWorkspaceRequest).toHaveBeenCalledWith(
      '/projects/prj_batch_1/assessment-batches/wfx_batch_1/cancel',
      { method: 'POST', body: '{}' },
    ))
    await vi.waitFor(() => expect(manager.stateFor('prj_batch_1', assessment.id).canceling).toBe(false))
    surface = render(manager)
    expect(surface.textContent).toContain('Cancellation was requested')
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('Assessment batch cancellation requested.')
    manager.invalidate()
  })

  it('previews and starts a new immutable retry without replacing its source batch', async () => {
    const terminalBatch = {
      ...activeBatch,
      status: 'failed',
      progress: {
        ...activeBatch.progress,
        running: 0,
        failed: 1,
        settled: 1,
      },
    }
    const retryPreview = {
      ...preview,
      preview_id: 'abp_retry_1',
      source_batch_id: terminalBatch.batch_id,
      candidate_item_count: 1,
      selected_item_count: 1,
      summary: {
        ...preview.summary,
        source_batch_id: terminalBatch.batch_id,
        source_item_count: 1,
        source_retry_eligible_item_count: 1,
        source_succeeded_item_count: 0,
      },
    }
    const retryBatch = {
      ...activeBatch,
      batch_id: 'wfx_retry_1',
      source_batch_id: terminalBatch.batch_id,
    }
    const requests = []
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      const value = String(url)
      requests.push({ url: value, options })
      if (value.startsWith('/projects/prj_batch_1/assessment-batches?')) {
        return response({ batches: [terminalBatch], has_more: false })
      }
      if (value.endsWith('/items?cursor=0&limit=100')) {
        return response({ items: [batchItem], next_cursor: null })
      }
      if (value.endsWith('/events?cursor=0&limit=100')) {
        return response({ events: [], has_more: false })
      }
      if (value.endsWith('/retry-previews')) return response({ preview: retryPreview })
      if (value.startsWith('/assessment-batch-previews/')) {
        return response({ items: [previewItems[0]], next_cursor: null })
      }
      if (value.endsWith('/retry')) {
        return response({ batch: retryBatch, launch: { launched: 1 } })
      }
      throw new Error(`Unexpected request: ${url}`)
    })
    const ctx = context(projectWorkspaceRequest)
    const manager = createProjectAssessmentBatchManager(ctx, { renderViews: vi.fn() })
    await manager.load('prj_batch_1', assessment.id, { render: false })

    let surface = render(manager)
    expect(surface.textContent).toContain('Retry failed or unfinished')
    expect(surface.textContent).toContain('New assessment plan')
    const retryAction = [...surface.querySelectorAll('button')]
      .find(button => button.textContent === 'Retry failed or unfinished')
    retryAction.click()
    await vi.waitFor(() => expect(
      manager.stateFor('prj_batch_1', assessment.id).preview?.source_batch_id,
    ).toBe(terminalBatch.batch_id))

    surface = render(manager)
    expect(surface.textContent).toContain('Commands that already succeeded remain unchanged')
    const start = [...surface.querySelectorAll('button')]
      .find(button => button.textContent === 'Start retry')
    start.click()
    await vi.waitFor(() => expect(
      requests.some(item => item.url.endsWith(`/${terminalBatch.batch_id}/retry`)),
    ).toBe(true))
    const startRequest = requests.find(item => item.url.endsWith(`/${terminalBatch.batch_id}/retry`))
    expect(JSON.parse(startRequest.options.body)).toEqual({
      preview_id: retryPreview.preview_id,
      plan_digest: retryPreview.plan_digest,
      confirmed: true,
      standard_confirmed: false,
      nuclei_snapshot_confirmed: false,
    })
    expect(ctx.showConfirm.mock.calls.at(-1)[0].body.text)
      .toBe('Retry failed or unfinished assessment commands?')
    expect(ctx.setProjectWorkspaceMessage)
      .toHaveBeenCalledWith('Assessment batch retry started.')
    surface = render(manager)
    expect(surface.textContent).toContain(`retry of ${terminalBatch.batch_id}`)
    manager.invalidate()
  })

  it('collapses Nuclei template failures into an update-and-retry preview path', async () => {
    const terminalBatch = {
      ...activeBatch,
      status: 'failed',
      diagnostics: [{
        code: 'nuclei_template_loading_failed',
        level: 'error',
        title: "Nuclei couldn't load the managed templates",
        message: '3 Nuclei commands failed while loading or validating the managed template snapshot.',
        affected_command_count: 3,
        recommended_action: 'refresh_nuclei_templates_and_retry',
      }],
      progress: {
        ...activeBatch.progress,
        running: 0,
        failed: 3,
        settled: 3,
        total: 3,
      },
    }
    const nucleiPreflight = {
      state: 'ready',
      launchable: true,
      refresh_enabled: true,
      command_count: 3,
      release_version: 'v10.4.7',
      refreshed_at: '2026-08-18T12:00:00Z',
      validation_state: 'passed',
      nuclei_version: 'v3.4.10',
      content_digest: `sha256:${'1'.repeat(64)}`,
    }
    const retryPreview = {
      ...preview,
      preview_id: 'abp_retry_nuclei',
      source_batch_id: terminalBatch.batch_id,
      candidate_item_count: 3,
      selected_item_count: 3,
      summary: {
        ...preview.summary,
        nuclei_preflight: nucleiPreflight,
        source_batch_id: terminalBatch.batch_id,
        source_item_count: 3,
        source_retry_eligible_item_count: 3,
        source_succeeded_item_count: 0,
      },
    }
    const rebuiltPreview = {
      ...retryPreview,
      preview_id: 'abp_retry_nuclei_rebuilt',
      plan_digest: 'b'.repeat(64),
    }
    const requests = []
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      const value = String(url)
      requests.push({ url: value, options })
      if (value.startsWith('/projects/prj_batch_1/assessment-batches?')) {
        return response({ batches: [terminalBatch], has_more: false })
      }
      if (value.endsWith('/items?cursor=0&limit=100')) {
        return response({ items: [{ ...batchItem, action_id: 'nuclei', status: 'failed' }], next_cursor: null })
      }
      if (value.endsWith('/events?cursor=0&limit=100')) {
        return response({ events: [], has_more: false })
      }
      if (value.endsWith('/retry-previews')) return response({ preview: retryPreview })
      if (value.includes('/nuclei-templates/refresh')) {
        return response({ preview: rebuiltPreview, refresh: { status: 'updated' } })
      }
      if (value.startsWith('/assessment-batch-previews/')) {
        return response({ items: [previewItems[0]], next_cursor: null })
      }
      throw new Error(`Unexpected request: ${url}`)
    })
    const ctx = context(projectWorkspaceRequest)
    const manager = createProjectAssessmentBatchManager(ctx, { renderViews: vi.fn() })
    await manager.load('prj_batch_1', assessment.id, { render: false })

    let surface = render(manager)
    expect(surface.textContent).toContain("Nuclei couldn't load the managed templates")
    expect(surface.textContent).toContain('3 affected')
    const updateAndRetry = [...surface.querySelectorAll('button')]
      .find(button => button.textContent === 'Update templates and retry failed commands')
    updateAndRetry.click()
    await vi.waitFor(() => expect(
      manager.stateFor('prj_batch_1', assessment.id).preview?.preview_id,
    ).toBe(rebuiltPreview.preview_id))

    expect(requests.some(item => item.url.endsWith('/retry-previews'))).toBe(true)
    expect(requests.some(item => item.url.includes('/nuclei-templates/refresh'))).toBe(true)
    expect(requests.some(item => item.url.endsWith(`/${terminalBatch.batch_id}/retry`))).toBe(false)
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith(
      'Managed Nuclei templates updated. Review the rebuilt plan before starting it.',
    )
    surface = render(manager)
    expect(surface.textContent).toContain('Start retry')
    expect(surface.textContent).toContain('Commands that already succeeded remain unchanged')
    manager.invalidate()
  })

  it('refreshes every command page the user has loaded while polling', async () => {
    let refreshed = false
    const pageItems = (start, count) => Array.from({ length: count }, (_, offset) => ({
      ...batchItem,
      item_index: start + offset,
      status: refreshed ? 'succeeded' : 'running',
      run_id: `run_batch_${start + offset}`,
    }))
    const projectWorkspaceRequest = vi.fn(async (url) => {
      const value = String(url)
      if (value.startsWith('/projects/prj_batch_1/assessment-batches?')) {
        return response({ batches: [activeBatch], has_more: false })
      }
      if (value === '/assessment-batches/wfx_batch_1') {
        return response({ batch: activeBatch })
      }
      if (value.endsWith('/items?cursor=0&limit=100')) {
        return response({ items: pageItems(0, 100), next_cursor: 100 })
      }
      if (value.endsWith('/items?cursor=100&limit=100')) {
        return response({ items: pageItems(100, 1), next_cursor: null })
      }
      if (value.includes('/events?')) {
        return response({ events: [], next_cursor: null, has_more: false })
      }
      throw new Error(`Unexpected request: ${url}`)
    })
    const manager = createProjectAssessmentBatchManager(
      context(projectWorkspaceRequest),
      { renderViews: vi.fn() },
    )
    await manager.load('prj_batch_1', assessment.id, { render: false })

    let surface = render(manager)
    const loadMore = [...surface.querySelectorAll('button')]
      .find(button => button.textContent === 'Load more commands')
    loadMore.click()
    await vi.waitFor(() => expect(
      manager.stateFor('prj_batch_1', assessment.id).batchItems,
    ).toHaveLength(101))

    refreshed = true
    await vi.advanceTimersByTimeAsync(2500)
    await vi.waitFor(() => expect(
      manager.stateFor('prj_batch_1', assessment.id).batchItems.at(-1)?.status,
    ).toBe('succeeded'))
    expect(manager.stateFor('prj_batch_1', assessment.id).batchItems).toHaveLength(101)
    expect(projectWorkspaceRequest).toHaveBeenCalledWith(
      '/assessment-batches/wfx_batch_1/items?cursor=100&limit=100',
      { cache: 'no-store' },
    )
    manager.invalidate()
  })

  it('updates only the batch monitor while polling and preserves scroll and focus', async () => {
    let polled = false
    const completedBatch = {
      ...activeBatch,
      status: 'completed',
      progress: {
        ...activeBatch.progress,
        running: 0,
        succeeded: 1,
        settled: 1,
      },
    }
    const projectWorkspaceRequest = vi.fn(async (url) => {
      const value = String(url)
      if (value.startsWith('/projects/prj_batch_1/assessment-batches?')) {
        return response({ batches: [activeBatch], has_more: false })
      }
      if (value === '/assessment-batches/wfx_batch_1') {
        polled = true
        return response({ batch: completedBatch })
      }
      if (value.endsWith('/items?cursor=0&limit=100')) {
        return response({
          items: [{ ...batchItem, status: polled ? 'succeeded' : 'running' }],
          next_cursor: null,
        })
      }
      if (value.includes('/events?')) {
        return response({ events: [], next_cursor: null, has_more: false })
      }
      throw new Error(`Unexpected request: ${url}`)
    })
    const renderViews = vi.fn()
    const manager = createProjectAssessmentBatchManager(
      context(projectWorkspaceRequest),
      { renderViews },
    )
    await manager.load('prj_batch_1', assessment.id, { render: false })

    const scrollHost = document.createElement('div')
    scrollHost.className = 'project-explorer-body'
    const section = manager.renderSection('prj_batch_1', assessment, detail)
    scrollHost.appendChild(section)
    document.body.appendChild(scrollHost)
    scrollHost.scrollTop = 73
    const openRun = section.querySelector('[data-assessment-batch-focus-key^="open-run:"]')
    openRun.focus()

    await vi.advanceTimersByTimeAsync(2500)
    await vi.waitFor(() => expect(section.textContent).toContain('Completed'))

    expect(renderViews).not.toHaveBeenCalled()
    expect(document.querySelector('.project-assessment-batch')).toBe(section)
    expect(scrollHost.scrollTop).toBe(73)
    expect(document.activeElement?.dataset?.assessmentBatchFocusKey).toBe('open-run:run_batch_1')
    expect(section.textContent).toContain('Succeeded')
    manager.invalidate()
  })
})
