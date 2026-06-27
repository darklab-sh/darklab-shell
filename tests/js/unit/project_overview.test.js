// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

function apiResponse(payload = {}, { ok = true, status = ok ? 200 : 500 } = {}) {
  return {
    ok,
    status,
    json: vi.fn(async () => payload),
  }
}

function loadOverviewModule() {
  return fromDomScripts(
    ['app/static/js/features/projects/project_overview.js'],
    { document, window },
    'globalThis.DarklabProjectOverview',
  )
}

function makeContext(projectWorkspaceRequest, overrides = {}) {
  const targetFilters = new Map()
  const runFilters = new Map()
  const severityFilters = new Map()
  const statusFilters = new Map()
  const setFor = (source, projectId) => {
    const key = String(projectId || '')
    if (!source.has(key)) source.set(key, new Set())
    return source.get(key)
  }
  return {
    projectWorkspaceRequest,
    projectResponseError: vi.fn(async (_resp, fallback) => new Error(fallback)),
    formatDate: vi.fn(value => String(value || '').replace('T', ' ')),
    makeProjectButton: vi.fn((label, action, projectId, role = 'secondary') => {
      const btn = document.createElement('button')
      btn.type = 'button'
      btn.className = `btn btn-${role}`
      btn.textContent = label
      btn.dataset.projectAction = action
      btn.dataset.projectId = projectId
      return btn
    }),
    bindProjectRuntimePressable: vi.fn(),
    emptyProjectPanel: vi.fn((text) => {
      const panel = document.createElement('div')
      panel.className = 'project-empty'
      panel.textContent = text
      return panel
    }),
    renderProjectExplorer: vi.fn(),
    renderProjectMobileDetail: vi.fn(),
    setProjectWorkspaceTab: vi.fn(),
    projectTargetFilterSet: vi.fn(projectId => setFor(targetFilters, projectId)),
    projectRunFilterSet: vi.fn(projectId => setFor(runFilters, projectId)),
    projectFindingSeverityFilterSet: vi.fn(projectId => setFor(severityFilters, projectId)),
    projectFindingStatusFilterSet: vi.fn(projectId => setFor(statusFilters, projectId)),
    setProjectFindingOrphanFilter: vi.fn(),
    invalidateProjectFilteredFindings: vi.fn(),
    logClientError: vi.fn(),
    mobileView: vi.fn(() => 'desktop'),
    _sets: { targetFilters, runFilters, severityFilters, statusFilters },
    ...overrides,
  }
}

const overviewPayload = {
  payload_version: 1,
  project: { id: 'prj_1', name: 'Client edge' },
  rollups: {
    target_count: 1,
    open_port_count: 2,
    service_count: 2,
    provider_count: 1,
    recent_change_state: 'windowed',
    certificate_statuses: {
      expired: 0,
      expiring_14d: 0,
      expiring_30d: 1,
      healthy: 0,
      unknown: 0,
    },
    finding_severities: {
      critical: 0,
      high: 1,
      medium: 0,
      low: 0,
      info: 0,
    },
  },
  recent_changes: [{
    fire_id: 'fire_1',
    state: 'changed',
    target_ids: ['ent_1'],
  }],
  targets: [{
    entity_id: 'ent_1',
    id: 'ent_1',
    type: 'domain',
    value: 'api.example.com',
    display_label: 'domain:api.example.com',
    target_review_state: 'confirmed',
    source_flags: {
      has_intel: true,
      has_stale_intel: true,
      has_findings: true,
      has_recent_changes: true,
    },
    open_ports: [80, 443],
    services: ['http', 'https'],
    certificate: {
      status: 'expiring_30d',
      expires_at: '2026-07-14T00:00:00+00:00',
      days_until_expiry: 20,
      last_checked_at: '2026-06-24T00:00:00+00:00',
    },
    top_finding_severity: 'high',
    finding_counts: {
      by_review_state: { new: 1 },
      suppressed: 0,
    },
    intel_summary: {
      providers_with_data: ['censys'],
      highlights: [{ label: 'Censys saw https on 443' }],
    },
    recent_change_markers: [{ fire_id: 'fire_1' }],
    deep_link_hints: {
      entities: { target_id: 'ent_1' },
      findings: { target_id: 'ent_1', orphan_filter: 'all', severity: 'high' },
    },
  }],
}

describe('project overview controller', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    document.body.replaceChildren()
    delete globalThis.DarklabProjectOverview
  })

  it('loads and renders bounded target overview rows with rollups', async () => {
    const overviewApi = loadOverviewModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(overviewPayload))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = overviewApi.createProjectOverviewController(ctx)

    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderOverview(container, 'prj_1', {})

    expect(projectWorkspaceRequest).toHaveBeenCalledWith(
      '/projects/prj_1/overview',
      { cache: 'no-store' },
    )
    expect(container.querySelector('.project-overview-summary-grid')?.textContent).toContain('Targets')
    expect(container.querySelector('.project-overview-summary-grid')?.textContent).toContain('High-risk targets')
    const summaryCards = [...container.querySelectorAll('.project-overview-summary-card')]
    const recentCard = summaryCards.find(card => card.textContent.includes('Recent changes'))
    expect(recentCard?.textContent).toContain('Windowed')
    expect(recentCard?.classList.contains('is-windowed')).toBe(false)
    expect(container.querySelector('.project-overview-target-title')?.textContent).toBe('api.example.com')
    expect(container.querySelector('.project-overview-target-detail')?.textContent).toContain('80, 443')
    const chipText = container.querySelector('.project-overview-target-chips')?.textContent || ''
    expect(chipText).toContain('Finding: High')
    expect(chipText).toContain('Cert: <=30d')
    expect(chipText).toContain('Intel: Stale')
    expect(container.querySelector('.project-overview-chip')?.getAttribute('title'))
      .toBe('Highest actionable finding severity for this target')
    expect(container.querySelector('.project-overview-highlights')?.textContent).toContain('Censys saw https on 443')
  })

  it('renders the empty target state from an empty overview payload', async () => {
    const overviewApi = loadOverviewModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse({
      payload_version: 1,
      project: { id: 'prj_empty', name: 'Empty overview' },
      rollups: {
        target_count: 0,
        open_port_count: 0,
        service_count: 0,
        provider_count: 0,
        recent_change_state: 'not-monitored',
        certificate_statuses: {},
        finding_severities: {},
      },
      recent_changes: [],
      targets: [],
    }))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = overviewApi.createProjectOverviewController(ctx)
    await controller.load('prj_empty', { render: false })
    const container = document.createElement('div')

    controller.renderOverview(container, 'prj_empty', {})

    expect(container.querySelector('.project-overview-root')).toBeTruthy()
    expect(container.querySelector('.project-empty')?.textContent).toBe('No project targets yet.')
    expect(container.querySelector('.project-overview-target-row')).toBeNull()
  })

  it('renders unknown certificate, no-intel, and not-monitored states neutrally', async () => {
    const overviewApi = loadOverviewModule()
    const degradedPayload = {
      ...overviewPayload,
      rollups: {
        ...overviewPayload.rollups,
        provider_count: 0,
        recent_change_state: 'not-monitored',
        certificate_statuses: { unknown: 1 },
        finding_severities: {},
      },
      recent_changes: [],
      targets: [{
        ...overviewPayload.targets[0],
        source_flags: {
          has_intel: false,
          has_stale_intel: false,
          has_findings: false,
          has_recent_changes: false,
        },
        certificate: {
          status: 'unknown',
          expires_at: '',
          days_until_expiry: null,
          last_checked_at: '',
        },
        top_finding_severity: '',
        finding_counts: { by_review_state: {}, suppressed: 0 },
        intel_summary: { providers_with_data: [], highlights: [] },
        recent_change_markers: [],
      }],
    }
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(degradedPayload))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = overviewApi.createProjectOverviewController(ctx)
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')

    controller.renderOverview(container, 'prj_1', {})

    const recentState = container.querySelector('.project-overview-recent-state')
    expect(recentState?.textContent).toContain('Not monitored')
    expect(recentState?.textContent).toContain('No monitoring window')
    expect(recentState?.querySelector('.badge')?.classList.contains('badge-tone-muted')).toBe(true)
    const chips = [...container.querySelectorAll('.project-overview-chip')]
    const certChip = chips.find(chip => chip.textContent.includes('Cert: Unknown'))
    const intelChip = chips.find(chip => chip.textContent.includes('Intel: None'))
    expect(certChip?.classList.contains('badge-tone-muted')).toBe(true)
    expect(certChip?.getAttribute('title')).toBe('No usable certificate expiry data found for this target')
    expect(intelChip?.classList.contains('badge-tone-muted')).toBe(true)
    expect(intelChip?.getAttribute('title')).toBe('No cached provider data for this target')
    expect(container.querySelector('.project-overview-highlights')).toBeNull()
  })

  it('uses existing Project filters when target actions open Entities and Findings', async () => {
    const overviewApi = loadOverviewModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(overviewPayload))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = overviewApi.createProjectOverviewController(ctx)
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderOverview(container, 'prj_1', {})

    container.querySelector('[data-project-overview-action="entities"]').click()
    expect(ctx.setProjectWorkspaceTab).toHaveBeenLastCalledWith('entities')
    expect([...ctx._sets.targetFilters.get('prj_1')]).toEqual(['ent_1'])

    container.querySelector('[data-project-overview-action="findings"]').click()
    expect(ctx.setProjectWorkspaceTab).toHaveBeenLastCalledWith('findings')
    expect([...ctx._sets.targetFilters.get('prj_1')]).toEqual(['ent_1'])
    expect([...ctx._sets.severityFilters.get('prj_1')]).toEqual(['high'])
    expect(ctx.setProjectFindingOrphanFilter).toHaveBeenCalledWith('prj_1', 'all')
    expect(ctx.invalidateProjectFilteredFindings).toHaveBeenCalledWith('prj_1')
  })

  it('clears stale filters when Findings hints only include a target', async () => {
    const overviewApi = loadOverviewModule()
    const targetOnlyPayload = {
      ...overviewPayload,
      targets: [{
        ...overviewPayload.targets[0],
        deep_link_hints: {
          entities: { target_id: 'ent_1' },
          findings: { target_id: 'ent_1' },
        },
      }],
    }
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(targetOnlyPayload))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = overviewApi.createProjectOverviewController(ctx)
    await controller.load('prj_1', { render: false })
    ctx.projectTargetFilterSet('prj_1').add('old_target')
    ctx.projectRunFilterSet('prj_1').add('old_run')
    ctx.projectFindingSeverityFilterSet('prj_1').add('critical')
    ctx.projectFindingStatusFilterSet('prj_1').add('false_positive')
    const container = document.createElement('div')
    controller.renderOverview(container, 'prj_1', {})

    container.querySelector('[data-project-overview-action="findings"]').click()

    expect([...ctx._sets.targetFilters.get('prj_1')]).toEqual(['ent_1'])
    expect([...ctx._sets.runFilters.get('prj_1')]).toEqual([])
    expect([...ctx._sets.severityFilters.get('prj_1')]).toEqual([])
    expect([...ctx._sets.statusFilters.get('prj_1')]).toEqual([])
    expect(ctx.setProjectFindingOrphanFilter).toHaveBeenCalledWith('prj_1', 'hide')
    expect(ctx.invalidateProjectFilteredFindings).toHaveBeenCalledWith('prj_1')
    expect(ctx.setProjectWorkspaceTab).toHaveBeenLastCalledWith('findings')
  })

  it('applies run and review-state hints through existing filter sets', async () => {
    const overviewApi = loadOverviewModule()
    const hintedPayload = {
      ...overviewPayload,
      targets: [{
        ...overviewPayload.targets[0],
        deep_link_hints: {
          entities: { target_id: 'ent_1', run_id: 'run_7' },
          findings: {
            target_id: 'ent_1',
            run_id: 'run_7',
            review_state: 'needs_followup',
            severity: 'medium',
            orphan_filter: 'all',
          },
        },
      }],
    }
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(hintedPayload))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = overviewApi.createProjectOverviewController(ctx)
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderOverview(container, 'prj_1', {})

    container.querySelector('[data-project-overview-action="entities"]').click()
    expect([...ctx._sets.targetFilters.get('prj_1')]).toEqual(['ent_1'])
    expect([...ctx._sets.runFilters.get('prj_1')]).toEqual(['run_7'])
    expect(ctx.setProjectWorkspaceTab).toHaveBeenLastCalledWith('entities')

    container.querySelector('[data-project-overview-action="findings"]').click()
    expect([...ctx._sets.targetFilters.get('prj_1')]).toEqual(['ent_1'])
    expect([...ctx._sets.runFilters.get('prj_1')]).toEqual(['run_7'])
    expect([...ctx._sets.severityFilters.get('prj_1')]).toEqual(['medium'])
    expect([...ctx._sets.statusFilters.get('prj_1')]).toEqual(['needs_followup'])
    expect(ctx.setProjectFindingOrphanFilter).toHaveBeenCalledWith('prj_1', 'all')
    expect(ctx.invalidateProjectFilteredFindings).toHaveBeenCalledWith('prj_1')
    expect(ctx.setProjectWorkspaceTab).toHaveBeenLastCalledWith('findings')
  })

  it('settles into an error state after overview load failures without retry looping', async () => {
    const overviewApi = loadOverviewModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse({ error: 'boom' }, { ok: false, status: 503 }))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = overviewApi.createProjectOverviewController(ctx)
    const container = document.createElement('div')

    controller.renderOverview(container, 'prj_1', {})
    expect(container.textContent).toBe('Loading project overview...')
    await vi.waitFor(() => {
      expect(ctx.logClientError).toHaveBeenCalledTimes(1)
    })
    controller.renderOverview(container, 'prj_1', {})
    controller.renderOverview(container, 'prj_1', {})

    expect(container.textContent).toBe('Could not load project overview.')
    expect(projectWorkspaceRequest).toHaveBeenCalledTimes(1)
    expect(ctx.logClientError).toHaveBeenCalledTimes(1)
    const loadLog = ctx.logClientError.mock.calls[0]
    expect(loadLog[0]).toContain('PROJECT_OVERVIEW_CLIENT_LOAD_FAILED')
    expect(loadLog[0]).toContain('"phase":"load"')
    expect(loadLog[0]).toContain('"selection_key":"project:prj_1"')
    expect(loadLog[0]).toContain('"status":503')
    expect(loadLog[0]).toContain('"level":"error"')
    expect(loadLog[2]).toEqual({
      event: 'PROJECT_OVERVIEW_CLIENT_LOAD_FAILED',
      level: 'error',
      page: 'project_overview',
      phase: 'load',
      selection_key: 'project:prj_1',
      status: 503,
    })
  })

  it('logs unexpected render-triggered load rejections', async () => {
    const overviewApi = loadOverviewModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(overviewPayload))
    const renderFailure = new Error('render callback failed')
    const ctx = makeContext(projectWorkspaceRequest, {
      renderProjectExplorer: vi.fn(() => {
        throw renderFailure
      }),
    })
    const controller = overviewApi.createProjectOverviewController(ctx)
    const container = document.createElement('div')

    controller.renderOverview(container, 'prj_1', {})

    await vi.waitFor(() => {
      expect(ctx.logClientError).toHaveBeenCalledTimes(1)
    })
    const loadLog = ctx.logClientError.mock.calls[0]
    expect(loadLog[0]).toContain('PROJECT_OVERVIEW_CLIENT_RENDER_LOAD_FAILED')
    expect(loadLog[0]).toContain('"phase":"render-load"')
    expect(loadLog[0]).toContain('"selection_key":"project:prj_1"')
    expect(loadLog[1]).toBe(renderFailure)
    expect(loadLog[2]).toEqual({
      event: 'PROJECT_OVERVIEW_CLIENT_RENDER_LOAD_FAILED',
      level: 'error',
      page: 'project_overview',
      phase: 'render-load',
      selection_key: 'project:prj_1',
      status: 0,
    })
  })

  it('renders mobile overview rows and re-renders mobile detail when actions use hints', async () => {
    const overviewApi = loadOverviewModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(overviewPayload))
    const ctx = makeContext(projectWorkspaceRequest, { mobileView: vi.fn(() => 'detail') })
    const controller = overviewApi.createProjectOverviewController(ctx)
    await controller.load('prj_1', { render: false })

    const panel = controller.renderMobileOverviewTab('prj_1', {})
    expect(panel.querySelector('.project-overview-root')?.classList.contains('is-mobile')).toBe(true)
    expect(panel.querySelector('.project-overview-target-row')?.classList.contains('is-mobile')).toBe(true)
    expect(panel.querySelector('.project-overview-target-actions')?.textContent).toContain('Entities')

    panel.querySelector('[data-project-overview-action="entities"]').click()
    expect(ctx.setProjectWorkspaceTab).toHaveBeenLastCalledWith('entities')
    expect([...ctx._sets.targetFilters.get('prj_1')]).toEqual(['ent_1'])
    expect(ctx.renderProjectMobileDetail).toHaveBeenCalled()
    expect(ctx.renderProjectExplorer).not.toHaveBeenCalled()
  })

  it('applies Findings hints from mobile overview rows', async () => {
    const overviewApi = loadOverviewModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(overviewPayload))
    const ctx = makeContext(projectWorkspaceRequest, { mobileView: vi.fn(() => 'detail') })
    const controller = overviewApi.createProjectOverviewController(ctx)
    await controller.load('prj_1', { render: false })

    const panel = controller.renderMobileOverviewTab('prj_1', {})
    panel.querySelector('[data-project-overview-action="findings"]').click()

    expect(ctx.setProjectWorkspaceTab).toHaveBeenLastCalledWith('findings')
    expect([...ctx._sets.targetFilters.get('prj_1')]).toEqual(['ent_1'])
    expect([...ctx._sets.severityFilters.get('prj_1')]).toEqual(['high'])
    expect(ctx.setProjectFindingOrphanFilter).toHaveBeenCalledWith('prj_1', 'all')
    expect(ctx.invalidateProjectFilteredFindings).toHaveBeenCalledWith('prj_1')
    expect(ctx.renderProjectMobileDetail).toHaveBeenCalled()
    expect(ctx.renderProjectExplorer).not.toHaveBeenCalled()
  })
})
