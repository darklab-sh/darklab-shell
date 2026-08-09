// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'

const { openContextualFindingRecord, openFindingTriageEditor } = vi.hoisted(() => ({
  openContextualFindingRecord: vi.fn(async () => true),
  openFindingTriageEditor: vi.fn(async () => true),
}))

vi.mock('../../../app/static/js/features/findings/finding_record_context.js', () => ({
  openContextualFindingRecord,
}))

vi.mock('../../../app/static/js/features/findings/finding_triage_bridge.js', () => ({
  openFindingTriageEditor,
}))

import { DarklabProjectAssessment } from '../../../app/static/js/features/projects/project_assessment.js'
import { launchAssessmentAction } from '../../../app/static/js/features/projects/project_assessment_actions.js'

function apiResponse(payload = {}, { ok = true } = {}) {
  return { ok, json: vi.fn(async () => payload) }
}

function makeContext(projectWorkspaceRequest, overrides = {}) {
  return {
    projectWorkspaceRequest,
    projectResponseError: vi.fn(async (_resp, fallback) => new Error(fallback)),
    formatDate: vi.fn(value => String(value || '').replace('T', ' ')),
    bindProjectRuntimePressable: vi.fn((element, options = {}) => {
      if (typeof options.onActivate === 'function') {
        element.addEventListener('click', options.onActivate)
      }
      return element
    }),
    emptyProjectPanel: vi.fn((text) => {
      const panel = document.createElement('div')
      panel.className = 'project-empty'
      panel.textContent = text
      return panel
    }),
    enhanceAppSelects: vi.fn(),
    renderProjectExplorer: vi.fn(),
    renderProjectMobileDetail: vi.fn(),
    invalidateProjectFindings: vi.fn(),
    invalidateProjectOverview: vi.fn(),
    setProjectWorkspaceMessage: vi.fn(),
    showConfirm: vi.fn(async options => options.actions.at(-1).id),
    actionSheetContainer: vi.fn(() => document.body),
    logClientError: vi.fn(),
    mobileView: vi.fn(() => 'list'),
    canMutateProjects: vi.fn(() => true),
    canRunCommands: vi.fn(() => true),
    canManageSecrets: vi.fn(() => true),
    canTriageFindings: vi.fn(() => true),
    openSecretsOptions: vi.fn(),
    apiFetch: projectWorkspaceRequest,
    attachActiveRunFromMonitor: vi.fn(async () => true),
    closeProjectWorkspace: vi.fn(),
    openContextualFindingRecord,
    openFindingTriageEditor,
    ...overrides,
  }
}

const cycle = {
  id: 'asmt_1',
  title: 'Network review',
  profile_key: 'network',
  profile_version: '1.0.0',
  status: 'active',
  started_at: '2026-08-05T10:00:00+00:00',
}

const profiles = [{
  key: 'network',
  version: '1.0.0',
  label: 'Network assessment',
  purpose: 'Review exposed network services.',
  target_types: ['domain', 'ip'],
  check_count: 2,
}]

const httpProfile = {
  id: 'htp_1',
  project_id: 'prj_1',
  name: 'Authenticated member',
  role: 'member',
  base_url: 'https://example.com/',
  scope_roots: ['https://example.com/'],
  allowed_hosts: ['example.com'],
  headers: [],
  header_names: [],
  secret_refs: { bearer_token: { name: 'APP_BEARER_TOKEN', available: true } },
  file_refs: {},
  credential_use: ['bearer_token'],
  include_paths: ['/app'],
  exclude_paths: ['/logout'],
  rate_limit_per_second: 10,
  concurrency: 5,
  enabled: true,
  revision: 1,
  protected_references_visible: true,
  reference_counts: { secret_refs: 1, file_refs: 0, headers: 0 },
}

const detail = {
  assessment: {
    ...cycle,
    profile_snapshot: {
      checks: [
        { key: 'service_inventory', label: 'Service inventory', purpose: 'Record exposed services.' },
        { key: 'dns_inventory', label: 'DNS inventory', purpose: 'Review DNS records.' },
      ],
    },
  },
  rollup: {
    total_checks: 2,
    applicable_checks: 2,
    covered_checks: 1,
    checks_awaiting_review: 1,
    untested_checks: 0,
    excluded_checks: 0,
    unavailable_evidence_checks: 1,
  },
  category_rollups: [{
    category: 'discovery',
    total_checks: 2,
    applicable_checks: 2,
    covered_checks: 1,
  }],
  finding_worklist: {
    items: [{
      remediation_id: 'rmd_1',
      remediation_group_id: 'rmd_1',
      vulnerability_id: 'CVE-2026-10001',
      rule_identity: '',
      title: 'Internet-facing service is vulnerable',
      severity: 'critical',
      observation_count: 2,
      evidence_count: 2,
      last_seen_at: '2026-08-05T12:00:00+00:00',
      strongest_validation_method: 'active_confirmation',
      validation_methods: ['active_confirmation', 'version_inference'],
      observation_summaries: [
        {
          id: 'fnd_confirmed',
          title: 'Confirmed template match',
          severity: 'critical',
          validation_method: 'active_confirmation',
        },
        {
          id: 'fnd_inferred',
          title: 'Version match',
          severity: 'high',
          validation_method: 'version_inference',
        },
      ],
      priority_context: { confidence: ['high'], exposure: ['internet'], assets: [] },
      risk: {
        kev: { listed: true, freshness: 'current' },
        epss: { probability: 0.42, percentile: 0.97, freshness: 'current' },
        cvss: { score: 9.8, freshness: 'current' },
      },
    }],
    total: 12,
    limit: 10,
    offset: 0,
    has_more: true,
    priority: '',
    rollup: {
      total: 12,
      kev_listed: 1,
      epss_scored: 8,
      cvss_scored: 10,
      unscored: 2,
    },
    source_finding_count: 13,
  },
  checks: {
    checks: [
      {
        id: 'asmc_1',
        check_key: 'service_inventory',
        target_entity_id: 'ent_1',
        target_type: 'domain',
        target_value: 'example.com',
        policy_level: 'safe',
        recommended_action_key: 'command:nmap',
        state: 'covered',
        state_source: 'derived',
        evidence_count: 2,
        unavailable_evidence_count: 0,
      },
      {
        id: 'asmc_2',
        check_key: 'dns_inventory',
        target_entity_id: 'ent_1',
        target_type: 'domain',
        target_value: 'example.com',
        policy_level: 'safe',
        recommended_action_key: 'command:dnsrecon',
        state: 'needs_review',
        state_source: 'manual',
        evidence_count: 1,
        unavailable_evidence_count: 1,
      },
    ],
    total: 75,
    limit: 50,
    offset: 0,
    has_more: true,
  },
}

function responseFor(url, options = {}) {
  if (options.method === 'POST') {
    return apiResponse({ assessment: { ...cycle, id: 'asmt_new' } })
  }
  if (url.endsWith('/http-profiles')) return apiResponse({ profiles: [], total: 0 })
  if (/\/assessments\/[^?]+/.test(url)) return apiResponse(detail)
  return apiResponse({ assessments: [cycle], profiles, total: 1, limit: 100, offset: 0, has_more: false })
}

describe('project assessment controller', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    openContextualFindingRecord.mockClear()
    openFindingTriageEditor.mockClear()
    document.body.replaceChildren()
  })

  it('renders the same truthful coverage and target worklist on desktop and mobile', async () => {
    const projectWorkspaceRequest = vi.fn(async (url, options) => responseFor(url, options))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)

    await controller.load('prj_1', { render: false })
    const desktop = document.createElement('div')
    controller.renderAssessment(desktop, 'prj_1')
    const mobile = controller.renderMobileAssessmentTab('prj_1')

    for (const surface of [desktop, mobile]) {
      expect(surface.textContent).toContain('Network review')
      expect(surface.textContent).toContain('1Coveredof 2 applicable')
      expect(surface.textContent).toContain('1Awaiting review')
      expect(surface.textContent).toContain('1Evidence unavailablesaved source was removed')
      expect(surface.querySelector('.project-assessment-target-list')?.classList.contains('nice-scroll')).toBe(true)
      const disclosure = surface.querySelector('.project-assessment-target-toggle')
      expect(disclosure?.getAttribute('aria-expanded')).toBe('false')
      expect(surface.querySelector('.project-assessment-target-body')?.classList.contains('u-hidden')).toBe(true)
      disclosure.click()
      expect(disclosure.getAttribute('aria-expanded')).toBe('true')
      expect(surface.textContent).toContain('Service inventory')
      expect(surface.textContent).toContain('Needs review')
      expect(surface.textContent).toContain('Manual decision')
    }
    expect(mobile.classList.contains('is-mobile')).toBe(true)
    mobile.querySelector('.project-assessment-mobile-actions button').click()
    expect([...document.querySelectorAll('.action-sheet-item')].map(button => button.textContent)).toEqual([
      'Complete cycle',
      'Archive cycle',
    ])
    expect(ctx.enhanceAppSelects).toHaveBeenCalledTimes(2)
  })

  it('manages reusable HTTP profiles in the shared desktop and mobile Assessment surface', async () => {
    let savedProfiles = [httpProfile]
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (url.endsWith('/http-profiles')) {
        if (options.method === 'POST') {
          const payload = JSON.parse(options.body)
          savedProfiles = [{ ...httpProfile, id: 'htp_new', ...payload }]
          return apiResponse({ profile: savedProfiles[0] })
        }
        return apiResponse({ profiles: savedProfiles, total: savedProfiles.length })
      }
      return responseFor(url, options)
    })
    const showConfirm = vi.fn(async (options) => {
      if (options.body?.text === 'Create an HTTP assessment profile') {
        const fields = [...options.content.querySelectorAll('.project-http-profile-field')]
        const control = label => fields.find(field => field.textContent.startsWith(label))?.querySelector('input, textarea')
        control('Profile name').value = 'Admin role'
        control('Authentication role').value = 'admin'
        control('Base URL').value = 'https://example.com/'
        control('Allowed Project hosts').value = 'example.com'
        control('Bearer token Secret').value = 'APP_ADMIN_TOKEN'
        expect(await options.actions.find(action => action.id === 'save').onActivate()).toBe(true)
        return 'save'
      }
      return options.actions.at(-1).id
    })
    const ctx = makeContext(projectWorkspaceRequest, { showConfirm })
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })

    const desktop = document.createElement('div')
    controller.renderAssessment(desktop, 'prj_1')
    const mobile = controller.renderMobileAssessmentTab('prj_1')
    for (const surface of [desktop, mobile]) {
      expect(surface.querySelector('.project-http-profiles')?.textContent).toContain('Authenticated member')
      expect(surface.querySelector('.project-http-profiles')?.textContent).toContain('Credentials ready')
      expect(surface.querySelector('.project-http-profiles')?.textContent).toContain('bearer token')
    }
    desktop.querySelector('.project-http-profile-header-actions .btn-secondary').click()
    expect(ctx.openSecretsOptions).toHaveBeenCalledTimes(1)
    desktop.querySelector('.project-http-profile-header-actions .btn-primary').click()
    await vi.waitFor(() => expect(projectWorkspaceRequest).toHaveBeenCalledWith(
      '/projects/prj_1/http-profiles',
      expect.objectContaining({ method: 'POST' }),
    ))
    const createBody = JSON.parse(projectWorkspaceRequest.mock.calls.find(([, options]) => options?.method === 'POST')[1].body)
    expect(createBody).toMatchObject({
      name: 'Admin role',
      role: 'admin',
      allowed_hosts: ['example.com'],
      secret_refs: { bearer_token: 'APP_ADMIN_TOKEN' },
    })
    await vi.waitFor(() => expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('HTTP profile created.'))
  })

  it('keeps protected HTTP profile references hidden and actions read-only without Secret permission', async () => {
    const publicProfile = {
      ...httpProfile,
      protected_references_visible: false,
      headers: undefined,
      secret_refs: undefined,
      file_refs: undefined,
    }
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (url.endsWith('/http-profiles')) return apiResponse({ profiles: [publicProfile], total: 1 })
      return responseFor(url, options)
    })
    const controller = DarklabProjectAssessment.createProjectAssessmentController(makeContext(
      projectWorkspaceRequest,
      { canManageSecrets: vi.fn(() => false) },
    ))
    await controller.load('prj_1', { render: false })
    const desktop = document.createElement('div')
    controller.renderAssessment(desktop, 'prj_1')

    const section = desktop.querySelector('.project-http-profiles')
    expect(section.textContent).toContain('Reference access required')
    expect(section.textContent).toContain('1 protected reference')
    expect(section.textContent).not.toContain('APP_BEARER_TOKEN')
    expect([...section.querySelectorAll('.project-http-profile-header-actions .btn')]
      .every(button => button.disabled)).toBe(true)
    expect([...section.querySelectorAll('.project-http-profile-actions .btn')]
      .every(button => button.disabled)).toBe(true)
  })

  it('creates a target-scoped finding from an assessment check on desktop and mobile', async () => {
    const projectWorkspaceRequest = vi.fn(async (url, options) => responseFor(url, options))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })

    const desktop = document.createElement('div')
    controller.renderAssessment(desktop, 'prj_1')
    const mobile = controller.renderMobileAssessmentTab('prj_1')
    desktop.querySelector('.project-assessment-target-toggle')?.click()
    ;[...desktop.querySelectorAll('.project-assessment-check-row .btn')]
      .find(button => button.textContent === 'Create finding')?.click()
    await Promise.resolve()
    mobile.querySelector('.project-assessment-target-toggle')?.click()
    mobile.querySelector('.project-assessment-check-row .btn')?.click()
    ;[...document.querySelectorAll('.action-sheet-item')]
      .find(button => button.textContent === 'Create finding')?.click()
    await Promise.resolve()

    expect(openContextualFindingRecord).toHaveBeenCalledTimes(2)
    expect(openContextualFindingRecord.mock.calls[0][0]).toEqual(expect.objectContaining({
      projectId: 'prj_1',
      targetId: 'ent_1',
      canEdit: true,
      defaults: expect.objectContaining({
        title: 'Service inventory: example.com',
        summary: 'Record exposed services.',
      }),
      evidence: [{
        evidence_type: 'assessment_check',
        evidence_id: 'asmc_1',
        label: 'Service inventory',
      }],
    }))
    await openContextualFindingRecord.mock.calls[0][0].onSaved()
    expect(ctx.invalidateProjectFindings).toHaveBeenCalledWith('prj_1')
    expect(ctx.invalidateProjectOverview).toHaveBeenCalledWith('prj_1')

    const viewer = DarklabProjectAssessment.createProjectAssessmentController(makeContext(
      projectWorkspaceRequest,
      { canTriageFindings: vi.fn(() => false) },
    ))
    await viewer.load('prj_view', { render: false })
    const viewerSurface = document.createElement('div')
    viewer.renderAssessment(viewerSurface, 'prj_view')
    viewerSurface.querySelector('.project-assessment-target-toggle')?.click()
    const viewerCreate = [...viewerSurface.querySelectorAll('.project-assessment-check-row .btn')]
      .find(button => button.textContent === 'Create finding')
    expect(viewerCreate.disabled).toBe(true)
    expect(viewerCreate.title).toContain('View-only')
  })

  it('previews reviewed Nuclei bounds before handing its run to the terminal', async () => {
    const nucleiDetail = {
      ...detail,
      assessment: {
        ...detail.assessment,
        profile_snapshot: {
          checks: [
            { key: 'service_inventory', label: 'Vulnerability templates', purpose: 'Review known exposures.' },
            detail.assessment.profile_snapshot.checks[1],
          ],
        },
      },
      checks: {
        ...detail.checks,
        checks: [
          {
            ...detail.checks.checks[0],
            policy_level: 'standard',
            recommended_action_key: 'command:nuclei',
          },
          detail.checks.checks[1],
        ],
      },
    }
    const projectWorkspaceRequest = vi.fn(async (url, options) => {
      if (/\/assessments\/[^?]+/.test(url)) return apiResponse(nucleiDetail)
      return responseFor(url, options)
    })
    const actionPath = '/projects/prj_1/assessments/asmt_1/checks/asmc_1/recommended-action'
    const plan = {
      action: { id: 'nuclei', key: 'command:nuclei', kind: 'command' },
      target: { entity_id: 'ent_1', type: 'domain', value: 'example.com' },
      http_profile: { name: '', credential_use: 'none' },
      policy_level: 'standard',
      scope: { target_count: 1, fan_out: 1 },
      bounds: {
        summary: 'One approved target using the reviewed template profile.',
        credential_use: 'none',
      },
      nuclei_profile: {
        label: 'Standard vulnerability review',
        template_source: 'managed_cache',
        template_snapshot: {
          state: 'ready',
          source_label: 'Managed local cache',
          release_version: 'v10.4.3',
          content_digest: `sha256:${'b'.repeat(64)}`,
          manifest_entry_count: 11997,
        },
        template_families: ['Exposure', 'Misconfiguration', 'Known CVEs', 'Technology', 'Network services', 'TLS', 'API'],
        excluded_tags: ['intrusive', 'oast', 'dast'],
        excluded_protocols: ['code', 'javascript', 'file', 'headless'],
        update_policy: 'explicit_only',
      },
      display_command: 'nuclei -u https://example.com -tags exposure,misconfig,cve,tech,network,ssl,api',
      launchable: true,
      unavailable_reason: '',
      plan_digest: 'a'.repeat(64),
    }
    const apiFetch = vi.fn(async (url, options = {}) => {
      expect(url).toBe(actionPath)
      if (options.method === 'POST') {
        return apiResponse({
          run: {
            run_id: 'run_assessment',
            run_type: 'external',
            status: 'running',
            command: plan.display_command,
            stream: '/runs/run_assessment/stream',
          },
          plan,
        })
      }
      return apiResponse({ plan })
    })
    const attachActiveRunFromMonitor = vi.fn(async () => true)
    const ctx = makeContext(projectWorkspaceRequest, { apiFetch, attachActiveRunFromMonitor })
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })
    await controller.setFilter('prj_1', 'category', 'discovery')
    const container = document.createElement('div')
    document.body.appendChild(container)
    controller.renderAssessment(container, 'prj_1')
    container.querySelector('.project-assessment-target-toggle')?.click()
    const runButton = [...container.querySelectorAll('.project-assessment-check-row .btn')]
      .find(button => button.textContent === 'Run Nuclei')
    runButton.click()

    await vi.waitFor(() => expect(attachActiveRunFromMonitor).toHaveBeenCalledWith(
      expect.objectContaining({ run_id: 'run_assessment' }),
    ))
    expect(apiFetch).toHaveBeenNthCalledWith(1, actionPath, { cache: 'no-store' })
    expect(apiFetch).toHaveBeenNthCalledWith(2, actionPath, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmed: true, plan_digest: 'a'.repeat(64) }),
    })
    expect(ctx.showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      content: expect.any(HTMLElement),
      refocusOnResolve: false,
      tone: 'warning',
    }))
    const confirmation = ctx.showConfirm.mock.calls[0][0]
    expect(confirmation.content.textContent).toContain(plan.display_command)
    expect(confirmation.content.textContent).toContain('Nuclei profileStandard vulnerability review')
    expect(confirmation.content.textContent).toContain('Template sourceManaged local cache')
    expect(confirmation.content.textContent).toContain('Template versionv10.4.3')
    expect(confirmation.content.textContent).toContain(`Template revisionsha256:${'b'.repeat(64)}`)
    expect(confirmation.content.textContent).toContain('Template cacheready · 11,997 manifest entries')
    expect(confirmation.content.textContent).toContain('Template familiesExposure, Misconfiguration, Known CVEs')
    expect(confirmation.content.textContent).toContain('Excluded templatesintrusive, oast, dast, code')
    expect(confirmation.content.textContent).toContain('Template updatesExplicit action only')
    expect(confirmation.body.note).toContain('Reviewed validators may also create linked findings')
    expect(confirmation.body.note).toContain('no run closes findings automatically')
    expect(ctx.closeProjectWorkspace).toHaveBeenCalledWith({ refocus: false })
    expect(controller.stateFor('prj_1').category).toBe('discovery')
  })

  it('shows saved-evidence Nuclei recommendations without starting a run', async () => {
    const recommendedDetail = {
      ...detail,
      assessment: {
        ...detail.assessment,
        profile_snapshot: {
          checks: [{
            key: 'vulnerability_templates',
            label: 'Web vulnerability templates',
            purpose: 'Apply reviewed templates to this target.',
          }],
        },
      },
      checks: {
        ...detail.checks,
        checks: [{
          ...detail.checks.checks[0],
          check_key: 'vulnerability_templates',
          policy_level: 'standard',
          recommended_action_key: 'command:nuclei',
          nuclei_recommendation: {
            recommended: true,
            profile_key: 'standard',
            reason_codes: ['inferred_cve', 'detected_technology'],
            summary: 'The standard Nuclei profile is recommended from saved evidence: 1 version-based CVE candidate, 2 detected technologies. Review its exact bounds before starting a run.',
            source_truncated: false,
            launch_mode: 'manual_confirmation_only',
            auto_launch: false,
          },
        }],
        total: 1,
        has_more: false,
      },
    }
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (/\/assessments\/[^?]+/.test(url)) return apiResponse(recommendedDetail)
      return responseFor(url, options)
    })
    const apiFetch = vi.fn()
    const controller = DarklabProjectAssessment.createProjectAssessmentController(makeContext(
      projectWorkspaceRequest,
      { apiFetch },
    ))
    await controller.load('prj_1', { render: false })
    const desktop = document.createElement('div')
    controller.renderAssessment(desktop, 'prj_1')
    const mobile = controller.renderMobileAssessmentTab('prj_1')
    desktop.querySelector('.project-assessment-target-toggle')?.click()
    mobile.querySelector('.project-assessment-target-toggle')?.click()

    for (const surface of [desktop, mobile]) {
      const recommendation = surface.querySelector('.project-assessment-check-recommendation')
      expect(recommendation?.textContent).toContain('Recommended from saved evidence')
      expect(recommendation?.textContent).toContain('1 version-based CVE candidate')
      expect(recommendation?.textContent).toContain('Review its exact bounds')
    }
    expect(apiFetch).not.toHaveBeenCalled()
  })

  it('shows conservative service suggestions on desktop and mobile without launching', async () => {
    const serviceDetail = {
      ...detail,
      checks: {
        ...detail.checks,
        checks: [{
          ...detail.checks.checks[0],
          service_action_recommendations: {
            actions: [{
              key: 'https_profile',
              label: 'Review HTTPS surface',
              rationale: 'The service identified an HTTPS endpoint.',
              command: 'command:httpx',
              policy_level: 'standard',
              target_types: ['domain', 'ip', 'url'],
              required_features: ['confirmed_project_target', 'httpx'],
              expected_evidence: ['atlas_service_entity', 'http_metadata', 'tls_metadata'],
              unsupported_conditions: [
                'ambiguous_service',
                'conflicting_service_evidence',
                'port_only_inference',
              ],
              service: 'https',
              port: 443,
              proto: 'tcp',
              version: 'nginx 1.26',
              launch_mode: 'assessment_action_only',
              auto_launch: false,
            }],
            action_count: 1,
            evidence_count: 2,
            needs_review_count: 1,
            unsupported_count: 0,
            source_truncated: false,
            launch_mode: 'assessment_action_only',
            auto_launch: false,
          },
        }],
      },
    }
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (/\/assessments\/[^?]+/.test(url)) return apiResponse(serviceDetail)
      return responseFor(url, options)
    })
    const apiFetch = vi.fn()
    const controller = DarklabProjectAssessment.createProjectAssessmentController(makeContext(
      projectWorkspaceRequest,
      { apiFetch },
    ))
    await controller.load('prj_1', { render: false })
    const desktop = document.createElement('div')
    controller.renderAssessment(desktop, 'prj_1')
    const mobile = controller.renderMobileAssessmentTab('prj_1')
    desktop.querySelector('.project-assessment-target-toggle')?.click()
    mobile.querySelector('.project-assessment-target-toggle')?.click()

    for (const surface of [desktop, mobile]) {
      const recommendation = surface.querySelector('.project-assessment-service-recommendations')
      expect(recommendation?.textContent).toContain('Suggested next actions')
      expect(recommendation?.textContent).toContain('Review HTTPS surface')
      expect(recommendation?.textContent).toContain('443/tcp · https · nginx 1.26')
      expect(recommendation?.textContent).toContain('1 saved port needs service review')
      expect(recommendation?.querySelector('button')).toBeNull()
    }
    expect(apiFetch).not.toHaveBeenCalled()
  })

  it('requires a fresh explicit warning before starting intrusive Nuclei', async () => {
    const plan = {
      action: { id: 'nuclei', key: 'command:nuclei', kind: 'command' },
      target: { entity_id: 'ent_1', type: 'url', value: 'https://example.com' },
      http_profile: { name: '', credential_use: 'none' },
      policy_level: 'intrusive',
      scope: { target_count: 1, fan_out: 1 },
      bounds: { summary: 'One approved target.', credential_use: 'none' },
      display_command: 'nuclei -u https://example.com -headless -dast -fuzz-aggression low',
      launchable: true,
      plan_digest: 'f'.repeat(64),
    }
    const apiFetch = vi.fn(async (_url, options = {}) => (
      options.method === 'POST'
        ? apiResponse({ run: { run_id: 'run_intrusive_nuclei' }, plan })
        : apiResponse({ plan })
    ))
    const showConfirm = vi.fn(async options => options.actions.at(-1).id)
    const attachActiveRunFromMonitor = vi.fn(async () => true)
    const launched = await launchAssessmentAction(makeContext(apiFetch, {
      apiFetch,
      showConfirm,
      attachActiveRunFromMonitor,
    }), {
      projectId: 'prj_1',
      assessmentId: 'asmt_1',
      check: { id: 'asmc_intrusive', recommended_action_key: 'command:nuclei' },
      httpProfiles: [],
    })

    expect(launched).toBe(true)
    const confirmation = showConfirm.mock.calls[0][0]
    expect(confirmation.body.text).toBe('Start intrusive Nuclei profile?')
    expect(confirmation.body.note).toContain('fresh confirmation')
    expect(confirmation.body.note).toContain('headless and low-aggression DAST')
    expect(confirmation.body.note).toContain('denial-of-service templates stay excluded')
    expect(confirmation.tone).toBe('warning')
    expect(confirmation.actions.at(-1).label).toBe('Start intrusive scan')
    expect(attachActiveRunFromMonitor).toHaveBeenCalledWith(
      expect.objectContaining({ run_id: 'run_intrusive_nuclei' }),
    )
  })

  it('chooses reviewed saved parameter evidence before launching XSS validation', async () => {
    const xssDetail = {
      ...detail,
      checks: {
        ...detail.checks,
        checks: [{ ...detail.checks.checks[0], recommended_action_key: 'command:dalfox' }],
        total: 1,
      },
    }
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (/\/assessments\/[^?]+/.test(url)) return apiResponse(xssDetail)
      return responseFor(url, options)
    })
    const actionPath = '/projects/prj_1/assessments/asmt_1/checks/asmc_1/recommended-action'
    const evidence = {
      source_run_id: 'run_discovery',
      observation_id: 'obs_reviewed',
      parameter: 'q',
      location: 'Query',
      tool_version: 'v3.1.2',
    }
    const chooser = {
      launchable: false,
      unavailable_reason: 'Choose one saved query-parameter observation.',
      evidence_selection: {
        required: true,
        selected: null,
        options: [evidence],
      },
    }
    const plan = {
      action: { id: 'dalfox', key: 'command:dalfox', kind: 'command' },
      target: { entity_id: 'ent_1', type: 'url', value: 'https://example.com/?q=one' },
      http_profile: { name: '', credential_use: 'none' },
      policy_level: 'intrusive',
      scope: { target_count: 1, fan_out: 1 },
      bounds: { summary: 'One reviewed query parameter.', credential_use: 'none' },
      display_command: 'dalfox https://example.com/?q=one --param q:query --skip-discovery',
      launchable: true,
      evidence_selection: { required: true, selected: evidence, options: [evidence] },
      plan_digest: 'c'.repeat(64),
    }
    const selectedPath = `${actionPath}?source_run_id=run_discovery&parameter_observation_id=obs_reviewed`
    const apiFetch = vi.fn(async (url, options = {}) => {
      if (options.method === 'POST') {
        return apiResponse({ run: { run_id: 'run_xss' }, plan })
      }
      return apiResponse({ plan: url === selectedPath ? plan : chooser })
    })
    const showConfirm = vi.fn(async (options) => {
      if (options.body?.text === 'Choose the saved parameter to validate.') {
        expect(options.content.querySelector('select').getAttribute('aria-label'))
          .toBe('Saved parameter evidence for XSS validation')
        expect(options.content.textContent).toContain('q · Query · v3.1.2')
        return 'continue'
      }
      expect(options.tone).toBe('warning')
      expect(options.content.textContent).toContain('--param q:query')
      return 'run'
    })
    const attachActiveRunFromMonitor = vi.fn(async () => true)
    const ctx = makeContext(projectWorkspaceRequest, {
      apiFetch,
      showConfirm,
      attachActiveRunFromMonitor,
    })
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    document.body.appendChild(container)
    controller.renderAssessment(container, 'prj_1')
    container.querySelector('.project-assessment-target-toggle').click()
    ;[...container.querySelectorAll('.project-assessment-check-row .btn')]
      .find(button => button.textContent === 'Run Dalfox').click()

    await vi.waitFor(() => expect(attachActiveRunFromMonitor).toHaveBeenCalled())
    expect(apiFetch).toHaveBeenNthCalledWith(1, actionPath, { cache: 'no-store' })
    expect(apiFetch).toHaveBeenNthCalledWith(2, selectedPath, { cache: 'no-store' })
    expect(apiFetch).toHaveBeenNthCalledWith(3, actionPath, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        confirmed: true,
        plan_digest: 'c'.repeat(64),
        source_run_id: 'run_discovery',
        parameter_observation_id: 'obs_reviewed',
      }),
    })
  })

  it('chooses a saved OpenAPI artifact before launching API negative testing', async () => {
    const apiDetail = {
      ...detail,
      checks: {
        ...detail.checks,
        checks: [{ ...detail.checks.checks[0], recommended_action_key: 'command:schemathesis' }],
        total: 1,
      },
    }
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (/\/assessments\/[^?]+/.test(url)) return apiResponse(apiDetail)
      return responseFor(url, options)
    })
    const actionPath = '/projects/prj_1/assessments/asmt_1/checks/asmc_1/recommended-action'
    const artifact = {
      artifact_id: 'rfa_1234567890abcdef',
      run_id: 'run_openapi',
      name: 'openapi.json',
      byte_size: 2048,
    }
    const chooser = {
      launchable: false,
      unavailable_reason: 'Choose one saved OpenAPI JSON artifact.',
      artifact_selection: { required: true, selected: null, options: [artifact] },
    }
    const selected = {
      ...artifact,
      openapi_version: '3.1.0',
      operation_count: 2,
      schema_sha256: 'd'.repeat(64),
    }
    const plan = {
      action: { id: 'schemathesis', key: 'command:schemathesis', kind: 'command' },
      target: { entity_id: 'ent_1', type: 'url', value: 'https://api.example.com/' },
      http_profile: { name: '', credential_use: 'none' },
      policy_level: 'standard',
      scope: { target_count: 1, fan_out: 1 },
      bounds: { summary: 'Two reviewed GET/HEAD operations.', credential_use: 'none' },
      display_command: 'schemathesis run [protected-schema] --url https://api.example.com/',
      launchable: true,
      artifact_selection: { required: true, selected, options: [artifact] },
      plan_digest: 'e'.repeat(64),
    }
    const selectedPath = `${actionPath}?schema_artifact_id=rfa_1234567890abcdef`
    const apiFetch = vi.fn(async (url, options = {}) => {
      if (options.method === 'POST') {
        return apiResponse({ run: { run_id: 'run_schemathesis' }, plan })
      }
      return apiResponse({ plan: url === selectedPath ? plan : chooser })
    })
    const showConfirm = vi.fn(async (options) => {
      if (options.body?.text === 'Choose the saved API contract to test.') {
        expect(options.content.querySelector('select').getAttribute('aria-label'))
          .toBe('Saved OpenAPI JSON for API negative testing')
        expect(options.content.textContent).toContain('openapi.json · 2,048 bytes · run_openapi')
        return 'continue'
      }
      expect(options.tone).toBe('warning')
      expect(options.content.textContent).toContain('OpenAPI schemaopenapi.json')
      expect(options.content.textContent).toContain('Read operations2')
      return 'run'
    })
    const attachActiveRunFromMonitor = vi.fn(async () => true)
    const ctx = makeContext(projectWorkspaceRequest, {
      apiFetch,
      showConfirm,
      attachActiveRunFromMonitor,
    })
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    document.body.appendChild(container)
    controller.renderAssessment(container, 'prj_1')
    container.querySelector('.project-assessment-target-toggle').click()
    ;[...container.querySelectorAll('.project-assessment-check-row .btn')]
      .find(button => button.textContent === 'Run Schemathesis').click()

    await vi.waitFor(() => expect(attachActiveRunFromMonitor).toHaveBeenCalled())
    expect(apiFetch).toHaveBeenNthCalledWith(1, actionPath, { cache: 'no-store' })
    expect(apiFetch).toHaveBeenNthCalledWith(2, selectedPath, { cache: 'no-store' })
    expect(apiFetch).toHaveBeenNthCalledWith(3, actionPath, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        confirmed: true,
        plan_digest: 'e'.repeat(64),
        schema_artifact_id: 'rfa_1234567890abcdef',
      }),
    })
  })

  it('selects an available HTTP role before previewing and launching a protected assessment action', async () => {
    const protectedDetail = {
      ...detail,
      checks: {
        ...detail.checks,
        checks: [{ ...detail.checks.checks[0], recommended_action_key: 'command:dalfox' }],
        total: 1,
      },
    }
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (url.endsWith('/http-profiles')) {
        return apiResponse({
          profiles: [
            httpProfile,
            { ...httpProfile, id: 'htp_disabled', name: 'Disabled admin', enabled: false },
            {
              ...httpProfile,
              id: 'htp_missing',
              name: 'Missing token',
              secret_refs: { bearer_token: { name: 'MISSING_TOKEN', available: false } },
            },
          ],
          total: 3,
        })
      }
      if (/\/assessments\/[^?]+/.test(url)) return apiResponse(protectedDetail)
      return responseFor(url, options)
    })
    const actionPath = '/projects/prj_1/assessments/asmt_1/checks/asmc_1/recommended-action'
    const plan = {
      action: { id: 'dalfox', key: 'command:dalfox', kind: 'command' },
      target: { entity_id: 'ent_1', type: 'domain', value: 'example.com' },
      http_profile: { name: 'Authenticated member', role: 'member', credential_use: ['bearer_token'] },
      policy_level: 'safe',
      scope: { target_count: 1, fan_out: 1 },
      bounds: { summary: 'One approved web target.', credential_use: 'protected_http_profile' },
      display_command: 'dalfox https://example.com/ --only-discovery --config [protected]',
      launchable: true,
      plan_digest: 'b'.repeat(64),
    }
    const apiFetch = vi.fn(async (url, options = {}) => {
      if (options.method === 'POST') return apiResponse({ run: { run_id: 'run_dalfox' }, plan })
      return apiResponse({ plan })
    })
    const showConfirm = vi.fn(async (options) => {
      if (options.body?.text === 'Choose the web role for this run.') {
        const choices = [...options.content.querySelectorAll('option')]
        expect(choices.find(option => option.value === 'htp_disabled').disabled).toBe(true)
        expect(choices.find(option => option.value === 'htp_missing').disabled).toBe(true)
        options.content.querySelector('select').value = 'htp_1'
        return 'continue'
      }
      expect(options.content.textContent).toContain('Profile rolemember')
      expect(options.content.textContent).toContain('Credentialsbearer token')
      return 'run'
    })
    const attachActiveRunFromMonitor = vi.fn(async () => true)
    const ctx = makeContext(projectWorkspaceRequest, {
      apiFetch,
      showConfirm,
      attachActiveRunFromMonitor,
    })
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    document.body.appendChild(container)
    controller.renderAssessment(container, 'prj_1')
    container.querySelector('.project-assessment-target-toggle').click()
    ;[...container.querySelectorAll('.project-assessment-check-row .btn')]
      .find(button => button.textContent === 'Run Dalfox').click()

    await vi.waitFor(() => expect(attachActiveRunFromMonitor).toHaveBeenCalled())
    expect(apiFetch).toHaveBeenNthCalledWith(
      1,
      `${actionPath}?http_profile_id=htp_1`,
      { cache: 'no-store' },
    )
    expect(apiFetch).toHaveBeenNthCalledWith(2, actionPath, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmed: true, plan_digest: 'b'.repeat(64), http_profile_id: 'htp_1' }),
    })
  })

  it('uses a touch-sized action sheet for saved check actions on mobile', async () => {
    const projectWorkspaceRequest = vi.fn(async (url, options) => responseFor(url, options))
    const controller = DarklabProjectAssessment.createProjectAssessmentController(makeContext(
      projectWorkspaceRequest,
      { canRunCommands: vi.fn(() => false) },
    ))
    await controller.load('prj_1', { render: false })
    const mobile = controller.renderMobileAssessmentTab('prj_1')
    document.body.appendChild(mobile)
    mobile.querySelector('.project-assessment-target-toggle')?.click()
    const actions = mobile.querySelector('.project-assessment-check-row .btn')
    expect(actions.textContent).toBe('Check actions')
    actions.click()

    const items = [...document.querySelectorAll('.action-sheet-item')]
    expect(items.map(button => button.textContent)).toEqual(['Run Nmap', 'Create finding'])
    expect(items[0].disabled).toBe(true)
    expect(items[1].disabled).toBe(false)
  })

  it('renders remediation-level cycle deltas with direct current and earlier finding links', async () => {
    const findingDeltas = {
      comparison: {
        status: 'partial',
        total_checks: 2,
        comparable_checks: 1,
        no_baseline_checks: 0,
        incomparable_checks: 1,
      },
      rollup: {
        new: 1,
        persistent: 1,
        not_observed: 1,
        regressed: 1,
        incomparable: 1,
        total: 5,
      },
      items: [{
        remediation_id: 'rmd_1',
        vulnerability_id: 'CVE-2026-10001',
        rule_identity: 'template:nuclei-test',
        state: 'persistent',
        reasons: ['Observed in both cycles under the same compatible check contract.'],
        checks: [{ target_value: 'example.com' }],
        current_observations: [{ observation_id: 'obs_current' }],
        previous_observations: [{ observation_id: 'obs_previous' }],
        current_findings: [{ id: 'fnd_current', title: 'Current template match', severity: 'high' }],
        previous_findings: [{ id: 'fnd_previous', title: 'Earlier template match', severity: 'high' }],
      }],
      item_limit: 100,
      truncated: false,
    }
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (/\/assessments\/[^?]+/.test(url)) return apiResponse({ ...detail, finding_deltas: findingDeltas })
      return responseFor(url, options)
    })
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })

    const desktop = document.createElement('div')
    controller.renderAssessment(desktop, 'prj_1')
    const mobile = controller.renderMobileAssessmentTab('prj_1')
    for (const surface of [desktop, mobile]) {
      expect(surface.textContent).toContain('Finding changes')
      expect(surface.textContent).toContain('Some checks have a compatible earlier baseline')
      expect(surface.textContent).toContain('CVE-2026-10001')
      expect(surface.textContent).toContain('1 current observation')
      const buttons = [...surface.querySelectorAll('.project-assessment-delta-evidence .btn')]
      expect(buttons.map(button => button.textContent)).toEqual([
        'Current template match',
        'Earlier template match',
      ])
      buttons.forEach(button => button.click())
    }
    await vi.waitFor(() => expect(openFindingTriageEditor).toHaveBeenCalledTimes(4))
    expect(openFindingTriageEditor).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'fnd_current' }),
      expect.objectContaining({ projectId: 'prj_1', canEdit: true }),
    )
    expect(mobile.querySelector('.project-assessment-delta-evidence .btn')?.getBoundingClientRect).toBeDefined()
  })

  it('renders and filters a remediation-level fix-first worklist on desktop and mobile', async () => {
    const projectWorkspaceRequest = vi.fn(async (url, options) => responseFor(url, options))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })

    const desktop = document.createElement('div')
    controller.renderAssessment(desktop, 'prj_1')
    const mobile = controller.renderMobileAssessmentTab('prj_1')
    for (const surface of [desktop, mobile]) {
      const worklist = surface.querySelector('.project-assessment-risk')
      expect(worklist?.textContent).toContain('Fix first')
      expect(worklist?.textContent).toContain('CISA KEV · 1')
      expect(worklist?.textContent).toContain('CVE-2026-10001')
      expect(worklist?.textContent).toContain('EPSS 42.0%')
      expect(worklist?.textContent).toContain('CVSS 9.8')
      expect(worklist?.textContent).toContain('Actively confirmed')
      expect(worklist?.textContent).toContain('last seen')
      const observations = worklist.querySelector('.project-assessment-risk-observation-toggle')
      expect(observations.getAttribute('aria-expanded')).toBe('false')
      observations.click()
      expect(observations.getAttribute('aria-expanded')).toBe('true')
      expect(worklist.textContent).toContain('Confirmed template match')
      expect(worklist.textContent).toContain('Version match')
    }

    desktop.querySelectorAll('.project-assessment-risk-observation .btn')[0].click()
    await vi.waitFor(() => expect(openFindingTriageEditor).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'fnd_confirmed' }),
      expect.objectContaining({ projectId: 'prj_1' }),
    ))
    await controller.setFindingFilter('prj_1', 'kev')
    await controller.setFindingPage('prj_1', 10)
    const focusedUrl = projectWorkspaceRequest.mock.calls.map(([url]) => url).at(-1)
    expect(focusedUrl).toContain('finding_priority=kev')
    expect(focusedUrl).toContain('finding_offset=10')
    expect(controller.stateFor('prj_1').category).toBe('')
    expect(controller.stateFor('prj_1').offset).toBe(0)
  })

  it('preserves cycle filters, paging, disclosure, and scroll state per project', async () => {
    const projectWorkspaceRequest = vi.fn(async (url, options) => responseFor(url, options))
    const controller = DarklabProjectAssessment.createProjectAssessmentController(
      makeContext(projectWorkspaceRequest),
    )
    await controller.load('prj_1', { render: false })
    await controller.setFilter('prj_1', 'category', 'discovery')
    await controller.setFilter('prj_1', 'state', 'needs_review')
    await controller.setPage('prj_1', 50)
    await controller.setFindingFilter('prj_1', 'epss')
    await controller.setFindingPage('prj_1', 10)

    const detailUrls = projectWorkspaceRequest.mock.calls
      .map(([url]) => url)
      .filter(url => url.includes('/assessments/asmt_1?'))
    expect(detailUrls.at(-1)).toContain('limit=50&offset=50')
    expect(detailUrls.at(-1)).toContain('category=discovery')
    expect(detailUrls.at(-1)).toContain('state=needs_review')
    expect(detailUrls.at(-1)).toContain('finding_priority=epss')
    expect(detailUrls.at(-1)).toContain('finding_offset=10')

    const container = document.createElement('div')
    controller.renderAssessment(container, 'prj_1')
    container.querySelector('.project-assessment-target-toggle').click()
    const list = container.querySelector('.project-assessment-target-list')
    list.scrollTop = 137
    list.dispatchEvent(new Event('scroll'))
    controller.renderAssessment(container, 'prj_1')

    const state = controller.stateFor('prj_1')
    expect(state.category).toBe('discovery')
    expect(state.checkState).toBe('needs_review')
    expect(state.offset).toBe(50)
    expect(state.findingPriority).toBe('epss')
    expect(state.findingOffset).toBe(10)
    expect(state.checksScrollTop).toBe(137)
    expect(container.querySelector('.project-assessment-target-list').scrollTop).toBe(137)
    expect(container.querySelector('.project-assessment-target-toggle').getAttribute('aria-expanded')).toBe('true')

    controller.invalidate('prj_1')
    expect(state.loaded).toBe(false)
    expect(state.detail).toBeNull()
    expect(state.category).toBe('discovery')
    expect(state.checkState).toBe('needs_review')
    expect(state.offset).toBe(50)
    expect(state.findingPriority).toBe('epss')
    expect(state.findingOffset).toBe(10)
    expect(state.checksScrollTop).toBe(137)
    expect(state.expandedTargets.has('domain:ent_1')).toBe(true)
  })

  it('focuses an exact cycle and filter set when another Project surface links into Assessment', async () => {
    const earlier = { ...cycle, id: 'asmt_old', status: 'completed', title: 'Earlier review' }
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (url.includes('/assessments/asmt_old?')) {
        return apiResponse({ ...detail, assessment: { ...detail.assessment, ...earlier } })
      }
      if (/\/assessments\/[^?]+/.test(url)) return apiResponse(detail)
      return apiResponse({ assessments: [cycle, earlier], profiles, total: 2 })
    })
    const controller = DarklabProjectAssessment.createProjectAssessmentController(
      makeContext(projectWorkspaceRequest),
    )
    await controller.load('prj_1', { render: false })
    controller.stateFor('prj_1').findingOffset = 10

    await controller.focusCycle('prj_1', 'asmt_old', {
      category: 'discovery',
      state: 'needs_review',
      priority: 'kev',
    })

    const state = controller.stateFor('prj_1')
    expect(state.selectedId).toBe('asmt_old')
    expect(state.category).toBe('discovery')
    expect(state.checkState).toBe('needs_review')
    expect(state.findingPriority).toBe('kev')
    expect(state.findingOffset).toBe(0)
    expect(state.offset).toBe(0)
    const focusedUrl = projectWorkspaceRequest.mock.calls.map(([url]) => url).at(-1)
    expect(focusedUrl).toContain('/assessments/asmt_old?')
    expect(focusedUrl).toContain('category=discovery')
    expect(focusedUrl).toContain('state=needs_review')
    expect(focusedUrl).toContain('finding_priority=kev')
  })

  it('starts a profile-driven cycle and keeps the action read-only for viewers', async () => {
    let cycles = []
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (options.method === 'POST') {
        cycles = [{ ...cycle, id: 'asmt_new' }]
        return apiResponse({ assessment: cycles[0] })
      }
      if (/\/assessments\/[^?]+/.test(url)) {
        return apiResponse({ ...detail, assessment: { ...detail.assessment, id: 'asmt_new' } })
      }
      return apiResponse({ assessments: cycles, profiles, total: cycles.length, limit: 100, offset: 0, has_more: false })
    })
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderAssessment(container, 'prj_1')
    expect(container.querySelector('button[type="submit"]').disabled).toBe(false)

    await controller.createCycle('prj_1', 'network')
    expect(projectWorkspaceRequest).toHaveBeenCalledWith('/projects/prj_1/assessments', {
      method: 'POST',
      body: JSON.stringify({ profile_key: 'network' }),
    })
    expect(controller.stateFor('prj_1').selectedId).toBe('asmt_new')
    expect(ctx.invalidateProjectOverview).toHaveBeenCalledWith('prj_1')
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('Assessment cycle started.')

    const viewerRequest = vi.fn(async () => apiResponse({ assessments: [], profiles, total: 0 }))
    const viewer = DarklabProjectAssessment.createProjectAssessmentController(makeContext(viewerRequest, {
      canMutateProjects: vi.fn(() => false),
    }))
    await viewer.load('prj_view', { render: false })
    const viewerContainer = document.createElement('div')
    viewer.renderAssessment(viewerContainer, 'prj_view')
    expect(viewerContainer.querySelector('button[type="submit"]').disabled).toBe(true)
    expect(viewerContainer.querySelector('button[type="submit"]').title).toContain('View-only')

    const viewerCycle = DarklabProjectAssessment.createProjectAssessmentController(makeContext(
      vi.fn(async (url, options) => responseFor(url, options)),
      { canMutateProjects: vi.fn(() => false) },
    ))
    await viewerCycle.load('prj_view_cycle', { render: false })
    const viewerCycleContainer = document.createElement('div')
    viewerCycle.renderAssessment(viewerCycleContainer, 'prj_view_cycle')
    const lifecycleButtons = [...viewerCycleContainer.querySelectorAll('.project-assessment-cycle-actions button')]
    expect(lifecycleButtons.map(button => button.textContent)).toEqual(['Complete cycle', 'Archive cycle'])
    expect(lifecycleButtons.every(button => button.disabled && button.title.includes('View-only'))).toBe(true)
  })

  it('confirms forward-only lifecycle changes and previews archived-cycle deletion', async () => {
    let current = { ...cycle }
    let deleted = false
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (url.endsWith('/delete-preview')) {
        return apiResponse({
          preview: {
            can_delete: true,
            will_delete: { checks: 2, evidence_links: 3 },
          },
        })
      }
      if (options.method === 'PATCH') {
        current = { ...current, status: JSON.parse(options.body).status }
        return apiResponse({ assessment: current })
      }
      if (options.method === 'DELETE') {
        deleted = true
        return apiResponse({ ok: true })
      }
      if (/\/assessments\/[^?]+/.test(url)) {
        return apiResponse({ ...detail, assessment: { ...detail.assessment, ...current } })
      }
      return apiResponse({
        assessments: deleted ? [] : [current],
        profiles,
        total: deleted ? 0 : 1,
        limit: 100,
        offset: 0,
        has_more: false,
      })
    })
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })

    expect(await controller.transitionCycle('prj_1', 'completed')).toBe(true)
    expect(current.status).toBe('completed')
    expect(ctx.invalidateProjectOverview).toHaveBeenCalledWith('prj_1')
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('Assessment cycle completed.')

    expect(await controller.transitionCycle('prj_1', 'archived')).toBe(true)
    expect(current.status).toBe('archived')
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('Assessment cycle archived.')

    expect(await controller.deleteCycle('prj_1')).toBe(true)
    expect(deleted).toBe(true)
    expect(ctx.showConfirm.mock.calls.at(-1)[0].body.note).toContain('2 saved checks and 3 evidence links')
    expect(ctx.showConfirm.mock.calls.at(-1)[0].body.note).toContain('Source runs, findings, entities, and files stay intact.')
    expect(controller.stateFor('prj_1').assessments).toEqual([])
    expect(ctx.invalidateProjectOverview).toHaveBeenCalledTimes(3)
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('Assessment cycle deleted.')
  })

  it('cancels lifecycle transitions without sending a mutation', async () => {
    const projectWorkspaceRequest = vi.fn(async (url, options) => responseFor(url, options))
    const ctx = makeContext(projectWorkspaceRequest, {
      showConfirm: vi.fn(async () => 'cancel'),
    })
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })

    expect(await controller.transitionCycle('prj_1', 'completed')).toBe(false)
    expect(projectWorkspaceRequest.mock.calls.some(([, options]) => options?.method === 'PATCH')).toBe(false)
  })
})
