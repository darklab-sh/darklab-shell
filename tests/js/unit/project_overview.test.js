// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { formatCompactPortLabel } from '../../../app/static/js/features/atlas/atlas_entity_row.js'
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
    [
      'app/static/js/features/findings/finding_risk.js',
      'app/static/js/features/projects/project_finding_changes.js',
      'app/static/js/features/projects/project_overview.js',
    ],
    { document, window },
    'globalThis.DarklabProjectOverview',
  )
}

function makeContext(projectWorkspaceRequest, overrides = {}) {
  const targetFilters = new Map()
  const runFilters = new Map()
  const hostFilters = new Map()
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
    openProjectAssessment: vi.fn(),
    setProjectEntityTab: vi.fn(),
    projectTargetFilterSet: vi.fn(projectId => setFor(targetFilters, projectId)),
    projectRunFilterSet: vi.fn(projectId => setFor(runFilters, projectId)),
    projectHostFilterSet: vi.fn(projectId => setFor(hostFilters, projectId)),
    projectFindingSeverityFilterSet: vi.fn(projectId => setFor(severityFilters, projectId)),
    projectFindingStatusFilterSet: vi.fn(projectId => setFor(statusFilters, projectId)),
    setProjectFindingOrphanFilter: vi.fn(),
    invalidateProjectFilteredFindings: vi.fn(),
    openProjectEntityInAtlas: vi.fn(),
    logClientError: vi.fn(),
    mobileView: vi.fn(() => 'desktop'),
    _sets: { targetFilters, runFilters, hostFilters, severityFilters, statusFilters },
    ...overrides,
  }
}

const overviewPayload = {
  payload_version: 1,
  project: { id: 'prj_1', name: 'Client edge' },
  active_assessment: {
    id: 'asmt_1',
    title: 'Network assessment',
    profile_key: 'network',
    profile_version: '1.0.0',
    status: 'active',
    started_at: '2026-06-24T12:00:00+00:00',
    updated_at: '2026-06-24T15:00:00+00:00',
    rollup: {
      total_checks: 9,
      applicable_checks: 8,
      covered_checks: 4,
      checks_awaiting_review: 2,
      untested_checks: 2,
      excluded_checks: 1,
      unavailable_evidence_checks: 1,
    },
    fix_first: {
      items: [{
        remediation_id: 'rmd_1',
        vulnerability_id: 'CVE-2026-10001',
        title: 'Internet-facing vulnerable service',
        risk: {
          kev: { listed: true, freshness: 'current' },
          epss: { probability: 0.42, percentile: 0.97, freshness: 'current' },
          cvss: { score: 9.8, freshness: 'current' },
        },
      }, {
        remediation_id: 'rmd_2',
        rule_identity: 'rule-without-risk-data',
        title: 'Finding without stored public risk data',
      }],
      total: 4,
      limit: 3,
      offset: 0,
      has_more: true,
      priority: '',
      rollup: {
        total: 4,
        kev_listed: 1,
        epss_scored: 3,
        cvss_scored: 4,
        unscored: 0,
      },
      source_finding_count: 5,
    },
  },
  assessment_finding_changes: {
    assessment: {
      id: 'asmt_1',
      title: 'Network assessment',
      status: 'active',
    },
    comparison: {
      status: 'partial',
      total_checks: 4,
      comparable_checks: 3,
      no_baseline_checks: 1,
      incomparable_checks: 0,
    },
    rollup: {
      regressed: 1,
      new: 2,
      persistent: 3,
      not_observed: 1,
      incomparable: 1,
      total: 8,
    },
    items: [],
    item_limit: 5,
    truncated: true,
  },
  rollups: {
    target_count: 1,
    open_port_count: 2,
    service_count: 2,
    provider_count: 1,
    app_port_count: 2,
    port_divergence_target_count: 1,
    app_scan_target_count: 1,
    app_port_target_count: 1,
    scanned_no_ports_seen_count: 0,
    unscanned_target_count: 0,
    awaiting_verification_target_count: 1,
    needs_followup_target_count: 1,
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
  operational_tempo: {
    last_run_at: '2026-06-24T13:00:00+00:00',
    last_run_id: 'run_7',
    runs_last_7d: 3,
    last_finding_triaged_at: '2026-06-24T14:00:00+00:00',
    last_finding_triaged_id: 'finding_1',
    last_artifact_at: '2026-06-24T15:00:00+00:00',
    last_artifact_id: 'artifact_1',
  },
  recent_activity: [{
    id: 'audit_1',
    created: '2026-06-24T14:00:00+00:00',
    event_type: 'finding.triage.updated',
    target_type: 'finding',
    target_id: 'ent_1',
    summary: 'label: High finding triaged',
    deep_link: {
      tab: 'findings',
      target_type: 'finding',
      target_id: 'ent_1',
    },
  }],
  coverage_gaps: {
    untouched_targets: [],
    awaiting_verification: [{
      entity_id: 'ent_1',
      display_label: 'domain:api.example.com',
      reason: 'awaiting_verification',
      detail: '3 findings awaiting verification.',
      deep_link: {
        tab: 'findings',
        hints: { target_id: 'ent_1', orphan_filter: 'all', severity: 'high' },
      },
    }],
    needs_followup: [{
      entity_id: 'ent_1',
      display_label: 'domain:api.example.com',
      reason: 'needs_followup',
      detail: '2 findings need review or follow-up.',
      deep_link: {
        tab: 'findings',
        hints: { target_id: 'ent_1', orphan_filter: 'all', severity: 'high' },
      },
    }],
  },
  deliverables_status: {
    last_package_at: '2026-06-24T16:00:00+00:00',
    last_package_id: 'pkg_1',
    last_package_name: 'Executive handoff',
    last_package_build_at: '2026-06-24T16:30:00+00:00',
    last_package_build_job_id: 'pkg_job_1',
    last_report_saved_at: '2026-06-24T17:00:00+00:00',
    last_report_id: 'rpt_1',
    last_report_exported_at: '2026-06-24T17:30:00+00:00',
    last_report_export_job_id: 'rpt_job_1',
    latest_finding_activity_at: '2026-06-24T14:00:00+00:00',
    report_freshness: 'fresh',
  },
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
      has_app_scan_evidence: true,
      has_app_ports: true,
      has_recent_changes: true,
    },
    app_evidence: {
      coverage_state: 'app_ports_found',
      scan_run_count: 1,
      last_observed_at: '2026-06-24T00:00:00+00:00',
      port_entity_count: 2,
      app_port_run_count: 1,
      project_entity_port_count: 1,
      command_roots: ['nmap'],
      host_entity_id: '',
      scope_note: '',
      coverage_caveat: '',
    },
    app_ports: [
      { port: 443, proto: 'tcp', service: 'https', version: 'nginx' },
      { port: 8443, proto: 'tcp', service: 'https-alt', version: '' },
    ],
    app_port_count: 2,
    app_services: ['https (nginx)', 'https-alt'],
    port_provenance: {
      app: [
        { port: 443, proto: 'tcp', service: 'https', version: 'nginx' },
        { port: 8443, proto: 'tcp', service: 'https-alt', version: '' },
      ],
      provider: [80, 443],
      divergence: {
        app_only: [8443],
        provider_only: [80],
        has_drift: true,
      },
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
      by_review_state: {
        new: 1,
        reviewed: 2,
        important: 1,
        needs_followup: 1,
        false_positive: 1,
      },
      by_verification_state: {
        not_started: 1,
        ready_to_verify: 1,
        verified: 2,
        needs_retest: 1,
        not_applicable: 1,
      },
      suppressed: 1,
    },
    intel_summary: {
      freshness: 'stale',
      last_refresh_at: '2026-06-24T00:00:00+00:00',
      providers_with_data: ['censys'],
      highlights: [{ label: 'Censys saw https on 443' }],
    },
    recent_change_markers: [{ fire_id: 'fire_1' }],
    deep_link_hints: {
      entities: { target_id: 'ent_1' },
      findings: { target_id: 'ent_1', orphan_filter: 'all', severity: 'high' },
      ports: { entity_type: 'port', host_entity_id: 'ent_1' },
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
    const summary = container.querySelector('.project-overview-summary')
    const summaryText = summary?.textContent || ''
    expect([...summary?.querySelectorAll('.project-overview-summary-heading') || []].map(node => node.textContent))
      .toEqual(['Coverage', 'Evidence', 'Risk/work'])
    expect(summaryText).toContain('Targets')
    expect(summaryText).toContain('cached providers')
    expect(summaryText).toContain('App-native ports')
    expect(summaryText).toContain('Cached provider ports')
    expect(summaryText).toContain('Provider/app drift')
    expect(summaryText).toContain('App scan coverage')
    expect(summaryText).toContain('Verification gaps')
    expect(summaryText).toContain('High-risk targets')
    const caveatText = container.querySelector('.project-overview-provider-caveat')?.textContent || ''
    expect(caveatText).toContain('Cached provider data')
    expect(caveatText).toContain('App-captured ports and services are shown first')
    const rootChildren = [...container.querySelector('.project-overview-root').children]
    expect(rootChildren.findIndex(node => node.classList.contains('project-overview-progress')))
      .toBeLessThan(rootChildren.findIndex(node => node.classList.contains('project-overview-target-section')))
    const progressText = container.querySelector('.project-overview-progress')?.textContent || ''
    expect(progressText).toContain('Triage')
    expect(progressText).toContain('New')
    expect(progressText).toContain('Reviewed')
    expect(progressText).toContain('Important/follow-up')
    expect(progressText).toContain('False positive: 1')
    expect(progressText).toContain('Suppressed: 1')
    expect(progressText).toContain('Verification')
    expect(progressText).toContain('Not started')
    expect(progressText).toContain('Ready')
    expect(progressText).toContain('Verified')
    expect(progressText).toContain('Needs retest')
    expect(progressText).toContain('Not applicable: 1')
    const assessmentText = container.querySelector('.project-overview-assessment')?.textContent || ''
    expect(assessmentText).toContain('Network assessment')
    expect(assessmentText).toContain('Active assessment · network · profile 1.0.0')
    expect(assessmentText).toContain('4 of 8')
    expect(assessmentText).toContain('Awaiting review')
    expect(assessmentText).toContain('Untested')
    expect(assessmentText).toContain('Excluded')
    expect(assessmentText).toContain('Fix first')
    expect(assessmentText).toContain('4 remediation groups · 1 CISA KEV')
    expect(assessmentText).toContain('CVE-2026-10001')
    expect(assessmentText).toContain('EPSS 42.0%')
    expect(assessmentText).toContain('EPSS 97.0th percentile')
    expect(assessmentText).toContain('No stored KEV, EPSS, or NVD data')
    expect(assessmentText).not.toContain('No stored public exploit signal')
    expect(assessmentText).toContain('1 check references saved evidence that can no longer be opened')
    container.querySelector('[data-project-overview-assessment="asmt_1"]').click()
    expect(ctx.openProjectAssessment).toHaveBeenCalledWith('prj_1', { assessmentId: 'asmt_1' })
    const findingChanges = container.querySelector('.project-finding-changes-summary')
    expect(findingChanges?.textContent).toContain('Finding changes')
    expect(findingChanges?.textContent).toContain('3 of 4 checks comparable')
    expect(findingChanges?.textContent).toContain('Regressed: 1')
    expect(findingChanges?.textContent).toContain('New: 2')
    expect(findingChanges?.textContent).toContain('distinct remediation groups')
    findingChanges?.querySelector('[data-project-finding-changes-assessment="asmt_1"]')?.click()
    expect(ctx.openProjectAssessment).toHaveBeenLastCalledWith('prj_1', { assessmentId: 'asmt_1' })
    const fixFirstButtons = [...container.querySelectorAll('.project-overview-assessment-fix-first-actions .btn')]
    expect(fixFirstButtons.map(button => button.textContent)).toEqual(['Open fix-first', 'Show CISA KEV'])
    fixFirstButtons[0].click()
    expect(ctx.openProjectAssessment).toHaveBeenLastCalledWith('prj_1', {
      assessmentId: 'asmt_1',
      priority: '',
    })
    fixFirstButtons[1].click()
    expect(ctx.openProjectAssessment).toHaveBeenLastCalledWith('prj_1', {
      assessmentId: 'asmt_1',
      priority: 'kev',
    })
    const tempoText = container.querySelector('.project-overview-tempo')?.textContent || ''
    expect(tempoText).toContain('Last run')
    expect(tempoText).toContain('2026-06-24 13:00:00+00:00')
    expect(tempoText).toContain('Runs 7d')
    expect(tempoText).toContain('3')
    expect(tempoText).toContain('Last triage')
    expect(tempoText).toContain('Last artifact')
    expect(tempoText).toContain('Finding Triage Updated')
    expect(tempoText).toContain('label: High finding triaged')
    const gapText = container.querySelector('.project-overview-gaps')?.textContent || ''
    expect(gapText).toContain('Awaiting verification: 1')
    expect(gapText).toContain('domain:api.example.com')
    expect(gapText).toContain('3 findings awaiting verification')
    expect(gapText).toContain('Needs follow-up: 1')
    expect(gapText).toContain('2 findings need review or follow-up')
    const deliverablesText = container.querySelector('.project-overview-deliverables')?.textContent || ''
    expect(deliverablesText).toContain('Last package')
    expect(deliverablesText).toContain('2026-06-24 16:00:00+00:00')
    expect(deliverablesText).toContain('Executive handoff')
    expect(deliverablesText).toContain('Package build')
    expect(deliverablesText).toContain('pkg_job_1')
    expect(deliverablesText).toContain('Report saved')
    expect(deliverablesText).toContain('rpt_1')
    expect(deliverablesText).toContain('Report exported')
    expect(deliverablesText).toContain('rpt_job_1')
    expect(deliverablesText).toContain('Report fresh')
    expect(deliverablesText).toContain('Latest finding activity 2026-06-24 14:00:00+00:00')
    const summaryCards = [...container.querySelectorAll('.project-overview-summary-card')]
    const recentCard = summaryCards.find(card => card.textContent.includes('Recent changes'))
    expect(recentCard?.textContent).toContain('Windowed')
    expect(recentCard?.classList.contains('is-windowed')).toBe(false)
    expect(container.querySelector('.project-overview-target-title')?.textContent).toBe('api.example.com')
    const firstRow = container.querySelector('.project-overview-target-row')
    expect(firstRow?.classList.contains('has-severity-amber')).toBe(true)
    const headerText = container.querySelector('.project-overview-target-header-badges')?.textContent || ''
    expect(headerText).toContain('High')
    expect(headerText).toContain('1 new')
    const detailRows = [...container.querySelectorAll('.project-overview-target-detail')]
    const portsDetail = detailRows.find(row => row.querySelector('.project-overview-target-detail-label')?.textContent === 'Ports: ')
    expect(portsDetail).toBeTruthy()
    expect(portsDetail.querySelector('.project-overview-port-badge-list')).toBeTruthy()
    expect(portsDetail.querySelector('.project-overview-target-value-muted')).toBeNull()
    const detailText = detailRows.map(node => node.textContent).join('\n')
    expect(detailText).toContain('Provider: 80, 443 · http, https')
    expect(detailText).toContain('Intel: stale · checked 2026-06-24 00:00:00+00:00')
    expect(detailText).toContain('Scan: App ports found: 2 ports from 1 app run')
    expect(detailText).toContain('Findings: 1 new · 3 awaiting verification · 1 false positive · 1 suppressed')
    const portChips = [...container.querySelectorAll('.project-overview-port-badge')]
    expect(portChips.map(chip => chip.textContent)).toEqual(
      overviewPayload.targets[0].app_ports.map(formatCompactPortLabel),
    )
    expect(portChips.every(chip => chip.classList.contains('badge'))).toBe(true)
    expect(portChips.every(chip => chip.classList.contains('badge-tone-muted'))).toBe(true)
    expect(portChips[0]?.getAttribute('title')).toBe('443/tcp https (nginx)')
    const chipText = container.querySelector('.project-overview-target-chips')?.textContent || ''
    expect(chipText).toContain('Cert: <=30d')
    expect(chipText).toContain('App ports')
    expect(chipText).toContain('Provider/app drift')
    expect(chipText).toContain('Intel: Stale')
    expect(container.querySelector('.project-overview-severity-badge')?.getAttribute('title'))
      .toBe('Highest actionable finding severity for this target')
    expect(container.querySelector('.project-overview-highlights')?.textContent).toContain('Censys saw https on 443')

    container.querySelector('[data-project-overview-profile="ent_1"]').click()
    expect(ctx.openProjectEntityInAtlas).toHaveBeenCalledWith(
      'prj_1',
      overviewPayload,
      {
        id: 'ent_1',
        type: 'domain',
        canonical_value: 'api.example.com',
      },
    )

    container.querySelector('[data-project-overview-activity="findings"]').click()
    expect(ctx.setProjectWorkspaceTab).toHaveBeenLastCalledWith('findings')
    expect([...ctx._sets.targetFilters.get('prj_1')]).toEqual([])

    container.querySelector('[data-project-overview-gap="findings"]').click()
    expect(ctx.setProjectWorkspaceTab).toHaveBeenLastCalledWith('findings')
    expect([...ctx._sets.targetFilters.get('prj_1')]).toEqual(['ent_1'])
    expect([...ctx._sets.severityFilters.get('prj_1')]).toEqual(['high'])
    expect(ctx.setProjectFindingOrphanFilter).toHaveBeenLastCalledWith('prj_1', 'all')
  })

  it('omits the assessment card when the Project has no active cycle', async () => {
    const overviewApi = loadOverviewModule()
    const payload = JSON.parse(JSON.stringify(overviewPayload))
    payload.active_assessment = null
    const controller = overviewApi.createProjectOverviewController(makeContext(
      vi.fn(async () => apiResponse(payload)),
    ))

    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderOverview(container, 'prj_1', {})

    expect(container.querySelector('.project-overview-assessment')).toBeNull()
  })

  it('previews long target lists so aggregate panels stay reachable', async () => {
    const overviewApi = loadOverviewModule()
    const longPayload = JSON.parse(JSON.stringify(overviewPayload))
    longPayload.rollups.target_count = 8
    longPayload.targets = Array.from({ length: 8 }, (_item, index) => ({
      ...longPayload.targets[0],
      id: `ent_${index + 1}`,
      entity_id: `ent_${index + 1}`,
      value: `api-${index + 1}.example.com`,
      display_label: `domain:api-${index + 1}.example.com`,
      ...(index >= 6 ? {
        top_finding_severity: '',
        app_ports: [],
        app_port_count: 0,
        app_services: [],
        open_ports: [],
        services: [],
        source_flags: {
          has_intel: false,
          has_stale_intel: false,
          has_findings: false,
          has_app_scan_evidence: false,
          has_app_ports: false,
          has_recent_changes: false,
        },
        app_evidence: {
          coverage_state: 'not_scanned',
          scan_run_count: 0,
          app_port_run_count: 0,
          port_entity_count: 0,
          command_roots: [],
          host_entity_id: '',
          scope_note: '',
          coverage_caveat: '',
        },
        certificate: { status: 'unknown', expires_at: '', days_until_expiry: null, last_checked_at: '' },
        finding_counts: { by_review_state: {}, by_verification_state: {}, suppressed: 0 },
        port_provenance: { app: [], provider: [], divergence: { app_only: [], provider_only: [], has_drift: false } },
        intel_summary: { providers_with_data: [], highlights: [] },
      } : {}),
    }))
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(longPayload))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = overviewApi.createProjectOverviewController(ctx)
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')

    controller.renderOverview(container, 'prj_1', {})

    expect(container.querySelectorAll('.project-overview-target-row')).toHaveLength(6)
    const orderedChildren = [...container.querySelector('.project-overview-root').children]
    expect(orderedChildren.findIndex(node => node.classList.contains('project-overview-progress')))
      .toBeLessThan(orderedChildren.findIndex(node => node.classList.contains('project-overview-target-section')))
    expect(orderedChildren.findIndex(node => node.classList.contains('project-overview-gaps')))
      .toBeLessThan(orderedChildren.findIndex(node => node.classList.contains('project-overview-target-section')))
    expect(container.querySelector('.project-overview-target-list')?.textContent).not.toContain('api-8.example.com')
    expect(container.querySelector('.project-overview-target-count')?.textContent).toBe('8 targets')
    const showAll = container.querySelector('[data-project-overview-action="toggle-targets"]')
    expect(showAll?.textContent).toBe('Show all 8 targets')
    expect(showAll?.hasAttribute('data-project-action')).toBe(false)

    showAll.click()
    expect(ctx.renderProjectExplorer).toHaveBeenCalled()
    controller.renderOverview(container, 'prj_1', {})

    expect(container.querySelectorAll('.project-overview-target-row')).toHaveLength(8)
    expect(container.querySelector('.project-overview-target-list')?.textContent).toContain('api-8.example.com')
    const expandedChildren = [...container.querySelector('.project-overview-root').children]
    expect(expandedChildren.findIndex(node => node.classList.contains('project-overview-progress')))
      .toBeLessThan(expandedChildren.findIndex(node => node.classList.contains('project-overview-target-section')))
    const showFewer = container.querySelector('[data-project-overview-action="toggle-targets"]')
    expect(showFewer?.textContent).toBe('Show fewer targets')

    const hideEmpty = container.querySelector('[data-project-overview-action="toggle-empty-targets"]')
    expect(hideEmpty?.classList.contains('toggle-btn')).toBe(true)
    expect(hideEmpty?.getAttribute('aria-pressed')).toBe('false')
    hideEmpty.click()
    expect(ctx.renderProjectExplorer).toHaveBeenCalled()
    controller.renderOverview(container, 'prj_1', {})

    expect(container.querySelector('[data-project-overview-action="toggle-empty-targets"]')?.getAttribute('aria-pressed')).toBe('true')
    expect(container.querySelector('.project-overview-target-count')?.textContent).toBe('Showing 6 of 8 targets')
    expect(container.querySelectorAll('.project-overview-target-row')).toHaveLength(6)
    expect(container.querySelector('.project-overview-target-list')?.textContent).not.toContain('api-8.example.com')
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
        app_scan_target_count: 0,
        app_port_target_count: 0,
        scanned_no_ports_seen_count: 0,
        unscanned_target_count: 0,
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
          has_app_scan_evidence: true,
          has_recent_changes: false,
        },
        app_evidence: {
          coverage_state: 'scanned_no_ports_seen',
          scan_run_count: 1,
          last_observed_at: '2026-06-24T00:00:00+00:00',
          port_entity_count: 0,
          command_roots: ['nmap'],
          coverage_caveat: 'No app-captured ports were surfaced by the observed scan runs; this does not prove no ports exist.',
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
    const scannedChip = chips.find(chip => chip.textContent.includes('Scanned'))
    expect(chips.find(chip => chip.textContent.includes('Cert: Unknown'))).toBeUndefined()
    expect(chips.find(chip => chip.textContent.includes('Intel: None'))).toBeUndefined()
    expect(scannedChip?.classList.contains('badge-tone-cyan')).toBe(true)
    expect(scannedChip?.getAttribute('title')).toContain('does not prove no ports exist')
    expect([...container.querySelectorAll('.project-overview-target-detail')]
      .map(node => node.textContent)
      .join('\n')).not.toContain('Intel: none')
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

    const portsButton = [...container.querySelectorAll('[data-project-overview-action="entities"]')]
      .find(button => button.textContent === 'Ports')
    portsButton.click()
    expect(ctx.setProjectWorkspaceTab).toHaveBeenLastCalledWith('entities')
    expect(ctx.setProjectEntityTab).toHaveBeenCalledWith('port')
    expect([...ctx._sets.targetFilters.get('prj_1')]).toEqual([])
    expect([...ctx._sets.hostFilters.get('prj_1')]).toEqual(['ent_1'])
    const portNavLog = ctx.logClientError.mock.calls.find(([message]) => (
      message.includes('PROJECT_OVERVIEW_NAVIGATION_APPLIED')
      && message.includes('"destination_tab":"entities"')
      && message.includes('"entity_type":"port"')
      && message.includes('"host_filter_count":1')
    ))
    expect(portNavLog?.[1]).toBeNull()
    expect(portNavLog?.[2]).toEqual({
      event: 'PROJECT_OVERVIEW_NAVIGATION_APPLIED',
      level: 'debug',
      page: 'project_overview',
      phase: 'navigate',
      selection_key: 'project:prj_1',
      status: 0,
    })

    const degradedCtx = makeContext(projectWorkspaceRequest, { setProjectEntityTab: undefined })
    const degradedController = overviewApi.createProjectOverviewController(degradedCtx)
    await degradedController.load('prj_1', { render: false })
    const degradedContainer = document.createElement('div')
    degradedController.renderOverview(degradedContainer, 'prj_1', {})
    const degradedPortsButton = [...degradedContainer.querySelectorAll('[data-project-overview-action="entities"]')]
      .find(button => button.textContent === 'Ports')
    degradedPortsButton.click()
    const degradedLog = degradedCtx.logClientError.mock.calls.find(([message]) => (
      message.includes('PROJECT_OVERVIEW_NAVIGATION_DEGRADED')
      && message.includes('"destination_tab":"entities"')
      && message.includes('"entity_type":"port"')
      && message.includes('"has_host_filter":true')
    ))
    expect(degradedLog?.[1]).toBeNull()
    expect(degradedLog?.[2]).toEqual({
      event: 'PROJECT_OVERVIEW_NAVIGATION_DEGRADED',
      level: 'warn',
      page: 'project_overview',
      phase: 'navigate',
      selection_key: 'project:prj_1',
      status: 0,
    })
  })

  it('hides the Ports action when Overview app ports are not project-linked', async () => {
    const overviewApi = loadOverviewModule()
    const payload = {
      ...overviewPayload,
      targets: [{
        ...overviewPayload.targets[0],
        deep_link_hints: {
          entities: { target_id: 'ent_1' },
          findings: { target_id: 'ent_1', orphan_filter: 'all', severity: 'high' },
        },
      }],
    }
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(payload))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = overviewApi.createProjectOverviewController(ctx)
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderOverview(container, 'prj_1', {})

    const portsButton = [...container.querySelectorAll('[data-project-overview-action="entities"]')]
      .find(button => button.textContent === 'Ports')
    expect(portsButton).toBeUndefined()
    expect(container.textContent).toContain('443/tcp https (nginx)')
    expect(container.textContent).toContain('Provider/app drift')
  })

  it('uses app port run counts when positive port evidence has no scan coverage', async () => {
    const overviewApi = loadOverviewModule()
    const payload = {
      ...overviewPayload,
      targets: [{
        ...overviewPayload.targets[0],
        app_evidence: {
          ...overviewPayload.targets[0].app_evidence,
          scan_run_count: 0,
          app_port_run_count: 1,
          port_entity_count: 0,
        },
      }],
    }
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(payload))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = overviewApi.createProjectOverviewController(ctx)
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderOverview(container, 'prj_1', {})
    const detailText = [...container.querySelectorAll('.project-overview-target-detail')]
      .map(node => node.textContent)
      .join('\n')

    expect(detailText).toContain('Scan: App ports found: 2 ports from 1 app run')
    expect(detailText).not.toContain('0 runs')
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
