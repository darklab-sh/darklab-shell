// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

function apiResponse(payload = {}, { ok = true } = {}) {
  return {
    ok,
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
    expect(container.querySelector('.project-overview-summary-grid')?.textContent).toContain('Finding signal')
    expect(container.querySelector('.project-overview-target-title')?.textContent).toBe('api.example.com')
    expect(container.querySelector('.project-overview-target-detail')?.textContent).toContain('80, 443')
    const chipText = container.querySelector('.project-overview-target-chips')?.textContent || ''
    expect(chipText).toContain('Finding: High')
    expect(chipText).toContain('Cert: <=30d')
    expect(container.querySelector('.project-overview-chip')?.getAttribute('title'))
      .toBe('Highest actionable finding severity for this target')
    expect(container.querySelector('.project-overview-highlights')?.textContent).toContain('Censys saw https on 443')
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
})
