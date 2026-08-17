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
  summary: {
    selected_target_count: 1,
    potential_covered_check_count: 2,
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
    const ctx = context(projectWorkspaceRequest)
    const manager = createProjectAssessmentBatchManager(ctx, { renderViews: vi.fn() })

    await manager.load('prj_batch_1', assessment.id, { render: false })
    let surface = render(manager)
    expect(surface.textContent).toContain('Safe checks are selected by default')
    expect(surface.textContent).toContain('Include standard checks')
    surface.querySelector('button.btn-primary').click()
    await vi.waitFor(() => expect(
      manager.stateFor('prj_batch_1', assessment.id).preview?.preview_id,
    ).toBe(preview.preview_id))

    const previewRequest = requests.find(item => item.url.endsWith('/batch-previews'))
    expect(JSON.parse(previewRequest.options.body)).toMatchObject({
      include_standard: false,
      item_limit: 128,
      max_parallel: 8,
      max_owner_parallel: 16,
      max_instance_parallel: 32,
    })
    surface = render(manager)
    expect(surface.textContent).toContain('2 of 2 shown')
    expect(surface.textContent).toContain('safe')
    expect(surface.textContent).toContain('standard · not selected')
    expect(surface.textContent).toContain('Already covered: 1')
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
            },
          },
        })
      }
      if (String(url).startsWith('/assessment-batch-previews/')) {
        return response({ items: previewItems, next_cursor: null })
      }
      throw new Error(`Unexpected request: ${url}`)
    })
    const manager = createProjectAssessmentBatchManager(
      context(projectWorkspaceRequest, { canRunCommands: vi.fn(() => false) }),
      { renderViews: vi.fn() },
    )
    await manager.load('prj_batch_1', assessment.id, { render: false })
    let surface = render(manager)
    surface.querySelector('button.btn-primary').click()
    await vi.waitFor(() => expect(
      manager.stateFor('prj_batch_1', assessment.id).preview?.preview_id,
    ).toBe(preview.preview_id))

    surface = render(manager)
    const standard = [...surface.querySelectorAll('label')]
      .find(label => label.textContent.includes('Include standard checks'))
    const standardInput = standard.querySelector('input')
    standardInput.checked = true
    standardInput.dispatchEvent(new Event('change', { bubbles: true }))
    await vi.waitFor(() => expect(
      manager.stateFor('prj_batch_1', assessment.id).previewDirty,
    ).toBe(true))
    surface = render(manager)
    expect(surface.textContent).toContain('Selection changed. Refresh the preview before starting.')
    expect([...surface.querySelectorAll('button')].find(button => button.textContent === 'Run assessment plan').disabled).toBe(true)
    expect(surface.textContent).toContain('Read-only: ask for operator access')

    const refresh = [...surface.querySelectorAll('button')]
      .find(button => button.textContent === 'Refresh preview')
    refresh.click()
    await vi.waitFor(() => expect(latestPreviewBody?.include_standard).toBe(true))
    await vi.waitFor(() => expect(manager.stateFor('prj_batch_1', assessment.id).previewing).toBe(false))
    expect(latestPreviewBody.include_standard).toBe(true)
    manager.invalidate()
  })

  it('requires a distinct confirmation before starting selected standard commands', async () => {
    const standardPreview = {
      ...preview,
      selected_item_count: 2,
      summary: {
        ...preview.summary,
        requires_standard_confirmation: true,
      },
    }
    let startBody = null
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (String(url).startsWith('/projects/prj_batch_1/assessment-batches?')) {
        return response({ batches: [] })
      }
      if (String(url).endsWith('/batch-previews')) return response({ preview: standardPreview })
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
    const manager = createProjectAssessmentBatchManager(ctx, { renderViews: vi.fn() })
    await manager.load('prj_batch_1', assessment.id, { render: false })
    const st = manager.stateFor('prj_batch_1', assessment.id)
    st.selection.includeStandard = true
    let surface = render(manager)
    surface.querySelector('button.btn-primary').click()
    await vi.waitFor(() => expect(st.preview?.preview_id).toBe(preview.preview_id))

    surface = render(manager)
    const start = [...surface.querySelectorAll('button')]
      .find(button => button.textContent === 'Run assessment plan')
    start.click()
    await vi.waitFor(() => expect(startBody).not.toBeNull())

    expect(startBody.standard_confirmed).toBe(true)
    expect(ctx.showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      confirmId: 'start_standard',
      tone: 'warning',
      refocusOnResolve: false,
    }))
    expect(ctx.showConfirm.mock.calls.at(-1)[0].body.text)
      .toBe('Run safe and standard assessment commands?')
    manager.invalidate()
  })

  it('restores an active monitor after reload, opens child runs, and requests truthful cancellation', async () => {
    const canceledBatch = {
      ...activeBatch,
      status: 'canceling',
      progress: { ...activeBatch.progress, status: 'canceling' },
    }
    const projectWorkspaceRequest = vi.fn(async (url) => {
      if (String(url).startsWith('/projects/prj_batch_1/assessment-batches?')) {
        return response({ batches: [activeBatch], has_more: false })
      }
      if (String(url).endsWith('/items?cursor=0&limit=100')) {
        return response({ items: [batchItem], next_cursor: null })
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
    })
    expect(ctx.showConfirm.mock.calls.at(-1)[0].body.text)
      .toBe('Retry failed or unfinished assessment commands?')
    expect(ctx.setProjectWorkspaceMessage)
      .toHaveBeenCalledWith('Assessment batch retry started.')
    surface = render(manager)
    expect(surface.textContent).toContain(`retry of ${terminalBatch.batch_id}`)
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
})
