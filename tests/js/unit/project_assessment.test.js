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
    openWorkspace: vi.fn(async () => true),
    openAtlas: vi.fn(async () => true),
    openHistoryRunDetails: vi.fn(),
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

const anonymousHttpProfile = {
  ...httpProfile,
  id: 'htp_zap',
  name: 'Anonymous web scope',
  role: 'anonymous',
  secret_refs: {},
  credential_use: [],
  include_paths: [],
  reference_counts: { secret_refs: 0, file_refs: 0, headers: 0, capture_rules: 0 },
}

const detail = {
  assessment: {
    ...cycle,
    profile_snapshot: {
      checks: [
        {
          key: 'service_inventory',
          label: 'Service inventory',
          purpose: 'Record exposed services.',
          evidence_rules: [{ evidence_types: ['run', 'atlas_entity'] }],
        },
        {
          key: 'dns_inventory',
          label: 'DNS inventory',
          purpose: 'Review DNS records.',
          evidence_rules: [{ evidence_types: ['run'] }],
        },
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
  target_rollups: [{
    target_entity_id: 'ent_1',
    target_type: 'domain',
    target_value: 'example.com',
    total_checks: 7,
    applicable_checks: 7,
    covered_checks: 5,
    checks_awaiting_review: 2,
    untested_checks: 0,
    excluded_checks: 0,
    unavailable_evidence_checks: 1,
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
        manual_evidence: {
          evidence: [],
          total: 0,
          limit: 20,
          offset: 0,
          has_more: false,
        },
        nmap_service_evidence: {
          observations: [{
            id: 'obs_1',
            run_id: 'run_nmap_1',
            target: '192.0.2.10:445/tcp',
            service: 'microsoft-ds',
            script_id: 'smb2-security-mode',
            evidence_kind: 'smb_signing',
            classification: 'informational',
            tool_version: '7.95',
            parser_version: 'nmap-xml-service-evidence-v1',
            fields: [{ path: ['message_signing'], value: 'disabled' }],
            fields_truncated: false,
            collection_truncated: false,
            observed_at: '2026-08-05T11:00:00+00:00',
          }],
          total: 1,
          limit: 20,
          offset: 0,
          has_more: false,
        },
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
        state_reason: 'Waiting for the approved maintenance window.',
        state_actor: { kind: 'team_member', member_id: 'tmem_operator' },
        state_changed_at: '2026-08-05T11:30:00+00:00',
        evidence_count: 1,
        unavailable_evidence_count: 1,
        manual_evidence: {
          evidence: [],
          total: 0,
          limit: 20,
          offset: 0,
          has_more: false,
        },
      },
    ],
    total: 75,
    limit: 50,
    offset: 0,
    has_more: true,
  },
}

const zapDetail = {
  ...detail,
  assessment: {
    ...detail.assessment,
    profile_snapshot: {
      checks: [
        { key: 'web_review', label: 'Web review', purpose: 'Review the live application.' },
        { key: 'admin_review', label: 'Admin review', purpose: 'Review the admin application.' },
      ],
    },
  },
  checks: {
    ...detail.checks,
    checks: [
      {
        ...detail.checks.checks[0],
        id: 'asmc_web',
        check_key: 'web_review',
        target_entity_id: 'ent_url_1',
        target_type: 'url',
        target_value: 'https://example.com/app',
        recommended_action_key: 'command:httpx',
        state: 'not_started',
      },
      {
        ...detail.checks.checks[1],
        id: 'asmc_admin',
        check_key: 'admin_review',
        target_entity_id: 'ent_url_2',
        target_type: 'url',
        target_value: 'https://example.com/admin',
        recommended_action_key: 'command:httpx',
        state: 'not_started',
      },
    ],
    total: 2,
    has_more: false,
  },
}

const oastEvidence = {
  source_run_id: 'run_parameter_discovery',
  observation_id: 'dpo_query_term',
  parameter: 'term',
  location: 'query',
  tool_version: 'Dalfox 2.12.0',
}

const oastDetail = {
  ...detail,
  assessment: {
    ...detail.assessment,
    profile_snapshot: {
      checks: [{
        key: 'blind_xss_validation',
        label: 'Blind XSS validation',
        purpose: 'Watch a private callback for server-side execution.',
      }],
    },
  },
  checks: {
    ...detail.checks,
    checks: [{
      ...detail.checks.checks[0],
      id: 'asmc_oast',
      assessment_id: 'asmt_1',
      check_key: 'blind_xss_validation',
      target_entity_id: 'ent_oast_url',
      target_type: 'url',
      target_value: 'https://example.com/search?term=one',
      policy_level: 'intrusive',
      recommended_action_key: 'oast_private_callback',
      state: 'not_started',
    }],
    total: 1,
    has_more: false,
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
    let currentDetail = structuredClone(detail)
    const checkStateUpdates = []
    const evidenceUpdates = []
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (options.method === 'POST' && url.endsWith('/assessments/asmt_1/checks/asmc_1/evidence')) {
        const payload = JSON.parse(options.body)
        evidenceUpdates.push({ method: 'POST', payload })
        const evidence = {
          id: 'aev_manual_1',
          evidence_type: payload.evidence_type,
          evidence_id: payload.evidence_id,
          source_state: 'available',
          linked_by: 'manual',
        }
        currentDetail.checks.checks[0].manual_evidence = {
          evidence: [evidence],
          total: 1,
          limit: 20,
          offset: 0,
          has_more: false,
        }
        return apiResponse({ ok: true, evidence, check: currentDetail.checks.checks[0] })
      }
      if (options.method === 'DELETE' && url.endsWith('/assessments/asmt_1/checks/asmc_1/evidence/aev_manual_1')) {
        evidenceUpdates.push({ method: 'DELETE', linkId: 'aev_manual_1' })
        currentDetail.checks.checks[0].manual_evidence = {
          evidence: [],
          total: 0,
          limit: 20,
          offset: 0,
          has_more: false,
        }
        return apiResponse({ ok: true, deleted: { id: 'aev_manual_1' }, check: currentDetail.checks.checks[0] })
      }
      if (options.method === 'PATCH' && url.endsWith('/assessments/asmt_1/checks/asmc_1')) {
        const payload = JSON.parse(options.body)
        checkStateUpdates.push(payload)
        const check = currentDetail.checks.checks[0]
        const cleared = payload.state === 'not_started'
        currentDetail = {
          ...currentDetail,
          checks: {
            ...currentDetail.checks,
            checks: [
              {
                ...check,
                state: cleared ? 'covered' : payload.state,
                state_source: cleared ? 'derived' : 'manual',
                state_reason: cleared ? 'Saved evidence covers this check.' : payload.reason,
              },
              ...currentDetail.checks.checks.slice(1),
            ],
          },
        }
        return apiResponse({
          ok: true,
          check: currentDetail.checks.checks[0],
          manual_override_cleared: cleared,
        })
      }
      if (/\/assessments\/[^?]+\?/.test(url)) return apiResponse(currentDetail)
      return responseFor(url, options)
    })
    const showConfirm = vi.fn(async (options) => {
      if (options.body?.text === 'Manage linked evidence') {
        const type = options.content.querySelector('[aria-label="Saved evidence type"]')
        const evidenceId = options.content.querySelector('input')
        const error = options.content.querySelector('[role="alert"]')
        expect(type.classList.contains('form-select')).toBe(true)
        expect(evidenceId.classList.contains('form-control')).toBe(true)
        expect(evidenceId.maxLength).toBe(512)
        const remove = options.actions.find(action => action.id === 'remove')
        if (remove) {
          const existing = options.content.querySelector('[aria-label="Existing manual evidence link"]')
          expect(existing.value).toBe('aev_manual_1')
          expect(await remove.onActivate()).toBe(true)
          return 'remove'
        }
        expect(await options.actions.find(action => action.id === 'link').onActivate()).toBe(false)
        expect(error.textContent).toContain('ID is required')
        type.value = 'run'
        evidenceId.value = 'run_manual_1'
        expect(await options.actions.find(action => action.id === 'link').onActivate()).toBe(true)
        return 'link'
      }
      if (options.body?.text === 'Set a manual check decision') {
        const state = options.content.querySelector('select')
        const reason = options.content.querySelector('textarea')
        const error = options.content.querySelector('[role="alert"]')
        expect(state.classList.contains('form-select')).toBe(true)
        expect(reason.classList.contains('form-control')).toBe(true)
        expect(reason.maxLength).toBe(1000)
        expect(await options.actions.find(action => action.id === 'save').onActivate()).toBe(false)
        expect(error.textContent).toContain('reason is required')
        state.value = 'blocked'
        reason.value = 'Waiting for the approved maintenance window.'
        expect(await options.actions.find(action => action.id === 'save').onActivate()).toBe(true)
        return 'save'
      }
      if (options.body?.text === 'Edit this manual check decision') {
        expect(options.content.querySelector('select').value).toBe('blocked')
        expect(options.content.querySelector('textarea').value).toBe('Waiting for the approved maintenance window.')
        expect(await options.actions.find(action => action.id === 'clear').onActivate()).toBe(true)
        return 'clear'
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
      expect(surface.textContent).toContain('Waiting for the approved maintenance window.')
      expect(surface.textContent).toContain('Recorded by team member tmem_operator')
      expect(surface.textContent).toContain('2026-08-05 11:30:00+00:00')
      expect(surface.textContent).toContain('domain · 7 checks')
      expect(surface.textContent).toContain('5 covered · 2 review')
      const serviceEvidence = surface.querySelector('.project-assessment-nmap-evidence')
      expect(serviceEvidence?.textContent).toContain('Nmap service evidence')
      expect(serviceEvidence?.textContent).toContain('192.0.2.10:445/tcp')
      expect(serviceEvidence?.textContent).toContain('Message Signingdisabled')
      expect(serviceEvidence?.textContent).toContain('Nmap 7.95')
      expect(serviceEvidence?.textContent).not.toContain('raw output')
    }
    expect(mobile.classList.contains('is-mobile')).toBe(true)
    expect(ctx.enhanceAppSelects).toHaveBeenCalledTimes(2)
    mobile.querySelector('.project-assessment-check-row .btn').click()
    expect([...document.querySelectorAll('.action-sheet-item')].map(button => button.textContent)).toEqual([
      'Set manual decision',
      'Manage evidence',
      'Run Nmap',
      'Create finding',
    ])
    ;[...document.querySelectorAll('.action-sheet-item')]
      .find(button => button.textContent === 'Manage evidence')
      .click()
    await vi.waitFor(() => expect(evidenceUpdates).toEqual([{
      method: 'POST',
      payload: { evidence_type: 'run', evidence_id: 'run_manual_1' },
    }]))
    await vi.waitFor(() => expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith(
      'Saved evidence linked to the assessment check.',
    ))

    controller.renderAssessment(desktop, 'prj_1')
    ;[...desktop.querySelector('.project-assessment-check-row').querySelectorAll('button')]
      .find(button => button.textContent === 'Manage evidence')
      .click()
    await vi.waitFor(() => expect(evidenceUpdates).toEqual([
      { method: 'POST', payload: { evidence_type: 'run', evidence_id: 'run_manual_1' } },
      { method: 'DELETE', linkId: 'aev_manual_1' },
    ]))
    await vi.waitFor(() => expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith(
      'Assessment evidence link removed. The saved source was kept.',
    ))

    mobile.querySelector('.project-assessment-check-row .btn').click()
    ;[...document.querySelectorAll('.action-sheet-item')]
      .find(button => button.textContent === 'Set manual decision')
      .click()
    await vi.waitFor(() => expect(checkStateUpdates).toEqual([{
      state: 'blocked',
      reason: 'Waiting for the approved maintenance window.',
    }]))
    expect(ctx.invalidateProjectOverview).toHaveBeenCalledWith('prj_1')
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('Manual check decision saved.')

    controller.renderAssessment(desktop, 'prj_1')
    const firstCheck = desktop.querySelector('.project-assessment-check-row')
    expect(firstCheck.textContent).toContain('Blocked')
    expect(firstCheck.textContent).toContain('Manual decision')
    ;[...firstCheck.querySelectorAll('button')]
      .find(button => button.textContent === 'Edit manual decision')
      .click()
    await vi.waitFor(() => expect(checkStateUpdates).toEqual([
      { state: 'blocked', reason: 'Waiting for the approved maintenance window.' },
      { state: 'not_started', reason: '' },
    ]))
    await vi.waitFor(() => expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith(
      'Manual decision cleared. Saved evidence now determines this check state.',
    ))

    mobile.querySelector('.project-assessment-mobile-actions button').click()
    expect([...document.querySelectorAll('.action-sheet-item')].map(button => button.textContent)).toEqual([
      'Complete cycle',
      'Archive cycle',
    ])
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
        const enabled = options.content.querySelector('.project-http-profile-enabled')
        expect(enabled?.tagName).toBe('LABEL')
        expect(enabled?.classList.contains('form-check')).toBe(true)
        expect(enabled?.classList.contains('control-row')).toBe(false)
        expect(enabled?.querySelector('input[type="checkbox"]')?.classList.contains('form-check')).toBe(false)
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

  it('reviews the exact ZAP plan before queueing the same bounded selection on desktop and mobile', async () => {
    const plan = {
      plan_digest: 'd'.repeat(64),
      plan_yaml: 'env:\n  contexts:\n    - name: darklab-anonymous\njobs:\n  - type: spider\n',
      summary: {
        policy_level: 'safe',
        authentication_role: 'anonymous',
        targets: ['https://example.com/app', 'https://example.com/admin'],
        include_rule_count: 2,
        exclusion_rule_count: 2,
        job_types: ['passiveScan-config', 'spider', 'passiveScan-wait', 'report'],
        job_timeout_seconds: 900,
        report_file: 'darklab-zap-report.json',
      },
    }
    const queuedJob = {
      id: 'zap_job_1',
      project_id: 'prj_1',
      assessment_id: 'asmt_1',
      check_id: 'asmc_web',
      status: 'queued',
      policy_level: 'safe',
      target_count: 2,
      cancelable: true,
      plan_summary: plan.summary,
    }
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (url.endsWith('/http-profiles')) {
        return apiResponse({ profiles: [httpProfile, anonymousHttpProfile], total: 2 })
      }
      if (url.endsWith('/zap-plan') && options.method === 'POST') return apiResponse({ plan })
      if (url.endsWith('/zap-jobs') && options.method === 'POST') return apiResponse({ job: queuedJob })
      if (url.endsWith('/zap-jobs')) return apiResponse({ jobs: [] })
      if (/\/assessments\/[^?]+/.test(url)) return apiResponse(zapDetail)
      return apiResponse({ assessments: [cycle], profiles, total: 1 })
    })
    const showConfirm = vi.fn(async (options) => {
      if (options.body?.text === 'Set up an external ZAP scan.') {
        const profileSelect = options.content.querySelector('[aria-label="HTTP profile for ZAP scan"]')
        const profileOptions = [...profileSelect.options]
        expect(profileOptions.find(option => option.value === httpProfile.id)?.disabled).toBe(true)
        expect(profileOptions.find(option => option.value === anonymousHttpProfile.id)?.disabled).toBe(false)
        options.content.querySelectorAll('input[type="checkbox"]').forEach(input => { input.checked = true })
        options.content.querySelector('[aria-label="Extra ZAP path exclusions"]').value = '/logout\n/app/private'
        expect(options.actions.find(action => action.id === 'review').onActivate()).toBe(true)
        return 'review'
      }
      if (options.body?.text === 'Queue this ZAP scan?') {
        expect(options.content.textContent).toContain('2 Project URLs')
        expect(options.content.textContent).toContain('passiveScan-config, spider, passiveScan-wait, report')
        expect(options.content.querySelector('.project-assessment-zap-yaml').textContent).toContain('darklab-anonymous')
        return 'queue'
      }
      return options.actions.at(-1).id
    })
    const ctx = makeContext(projectWorkspaceRequest, { showConfirm })
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })
    const desktop = document.createElement('div')
    controller.renderAssessment(desktop, 'prj_1')
    const mobile = controller.renderMobileAssessmentTab('prj_1')
    desktop.querySelector('.project-assessment-target-toggle')?.click()
    mobile.querySelector('.project-assessment-target-toggle')?.click()
    expect([...desktop.querySelectorAll('.project-assessment-check-row .btn')]
      .some(button => button.textContent === 'ZAP scan')).toBe(true)
    mobile.querySelector('.project-assessment-check-row .btn')?.click()
    const mobileZap = [...document.querySelectorAll('.action-sheet-item')]
      .find(button => button.textContent === 'ZAP scan')
    expect(mobileZap).toBeTruthy()
    mobileZap.click()

    await vi.waitFor(() => expect(projectWorkspaceRequest).toHaveBeenCalledWith(
      '/projects/prj_1/assessments/asmt_1/checks/asmc_web/zap-jobs',
      expect.objectContaining({ method: 'POST' }),
    ))
    const planCall = projectWorkspaceRequest.mock.calls.find(([url]) => url.endsWith('/zap-plan'))
    const submitCall = projectWorkspaceRequest.mock.calls.find(([, options]) => options?.method === 'POST'
      && JSON.parse(options.body || '{}').confirmed === true)
    const selection = {
      http_profile_id: 'htp_zap',
      policy_level: 'safe',
      scope_exclusions: ['/logout', '/app/private'],
      target_entity_ids: ['ent_url_1', 'ent_url_2'],
    }
    expect(JSON.parse(planCall[1].body)).toEqual(selection)
    expect(JSON.parse(submitCall[1].body)).toEqual({
      ...selection,
      confirmed: true,
      plan_digest: plan.plan_digest,
    })
    controller.renderAssessment(desktop, 'prj_1')
    expect(desktop.textContent).toContain('External ZAP scan')
    expect(desktop.textContent).toContain('The worker has this scan in its durable queue.')
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith(
      'ZAP scan queued. Progress will stay with this assessment check.',
    )
    controller.invalidate('prj_1')
  })

  it('recovers a running ZAP job, cancels it, and polls its durable final state', async () => {
    vi.useFakeTimers()
    const running = {
      id: 'zap_job_running',
      status: 'running',
      policy_level: 'safe',
      target_count: 1,
      cancelable: true,
      progress: { info_count: 2, warning_count: 1, error_count: 0, recent_messages: [] },
    }
    const cancelRequested = { ...running, status: 'cancel_requested' }
    const canceled = { ...running, status: 'canceled', cancelable: false }
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (url.endsWith('/http-profiles')) return apiResponse({ profiles: [anonymousHttpProfile], total: 1 })
      if (url.endsWith('/zap-jobs/zap_job_running') && options.method === 'DELETE') {
        return apiResponse({ job: cancelRequested })
      }
      if (url.endsWith('/zap-jobs/zap_job_running')) return apiResponse({ job: canceled })
      if (url.endsWith('/zap-jobs')) return apiResponse({ jobs: [running] })
      if (/\/assessments\/[^?]+/.test(url)) return apiResponse(zapDetail)
      return apiResponse({ assessments: [cycle], profiles, total: 1 })
    })
    const showConfirm = vi.fn(async options => (
      options.body?.text === 'Cancel this ZAP scan?' ? 'cancel_zap' : options.actions.at(-1).id
    ))
    const controller = DarklabProjectAssessment.createProjectAssessmentController(makeContext(
      projectWorkspaceRequest,
      { showConfirm },
    ))
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderAssessment(container, 'prj_1')
    container.querySelector('.project-assessment-target-toggle')?.click()
    ;[...container.querySelectorAll('.project-assessment-check-row .btn')]
      .find(button => button.textContent === 'ZAP scan')?.click()
    await vi.advanceTimersByTimeAsync(0)
    controller.renderAssessment(container, 'prj_1')
    expect(container.textContent).toContain('ZAP is running the reviewed plan.')
    expect(container.textContent).toContain('2 info · 1 warning')
    ;[...container.querySelectorAll('.project-assessment-zap-actions .btn')]
      .find(button => button.textContent === 'Cancel scan')?.click()
    await vi.advanceTimersByTimeAsync(0)
    expect(projectWorkspaceRequest).toHaveBeenCalledWith(
      '/projects/prj_1/assessments/asmt_1/checks/asmc_web/zap-jobs/zap_job_running',
      { method: 'DELETE' },
    )
    await vi.advanceTimersByTimeAsync(2000)
    controller.renderAssessment(container, 'prj_1')
    expect(container.textContent).toContain('The scan was canceled before an import draft was created.')
    expect(container.textContent).toContain('New ZAP scan')
    controller.invalidate('prj_1')
    vi.useRealTimers()
  })

  it('recovers a ready ZAP report and opens its visible Files handoff without applying Atlas', async () => {
    const ready = {
      id: 'zap_job_ready',
      status: 'ready',
      policy_level: 'safe',
      target_count: 1,
      cancelable: false,
      files_path: 'assessments/zap/zap_job_ready/darklab-zap-report.json',
      atlas_draft_id: 'aim_zap_job_ready',
    }
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (url.endsWith('/http-profiles')) return apiResponse({ profiles: [anonymousHttpProfile], total: 1 })
      if (url.endsWith('/zap-jobs')) return apiResponse({ jobs: [ready] })
      if (/\/assessments\/[^?]+/.test(url)) return apiResponse(zapDetail)
      return apiResponse({ assessments: [cycle], profiles, total: 1 })
    })
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderAssessment(container, 'prj_1')
    container.querySelector('.project-assessment-target-toggle')?.click()
    ;[...container.querySelectorAll('.project-assessment-check-row .btn')]
      .find(button => button.textContent === 'ZAP scan')?.click()
    await vi.waitFor(() => {
      expect(projectWorkspaceRequest).toHaveBeenCalledWith(
        '/projects/prj_1/assessments/asmt_1/checks/asmc_web/zap-jobs',
        { cache: 'no-store' },
      )
      controller.renderAssessment(container, 'prj_1')
      expect(container.textContent).toContain('Atlas import draft ready')
    })
    expect(container.textContent).toContain(ready.files_path)
    expect(container.textContent).not.toContain('Open Atlas findings')
    expect(container.textContent).toContain('Review Atlas import')
    expect(container.querySelector('.project-assessment-zap-status .badge')?.classList.contains('badge-tone-cyan')).toBe(true)
    ;[...container.querySelectorAll('.project-assessment-zap-actions .btn')]
      .find(button => button.textContent === 'Review Atlas import')?.click()
    await Promise.resolve()
    expect(ctx.openAtlas).toHaveBeenCalledWith({
      projectId: 'prj_1',
      projectName: '',
      tab: 'findings',
      source: 'project_assessment_zap',
      importDraftId: ready.atlas_draft_id,
    })
    ;[...container.querySelectorAll('.project-assessment-zap-actions .btn')]
      .find(button => button.textContent === 'Open Files')?.click()
    await Promise.resolve()
    expect(ctx.openWorkspace).toHaveBeenCalledTimes(1)
    controller.invalidate('prj_1')
  })

  it('recovers, prepares, polls, and freshly confirms a private OAST run without rendering its callback', async () => {
    const actionPath = '/projects/prj_1/assessments/asmt_1/checks/asmc_oast/recommended-action'
    const correlationPath = '/projects/prj_1/assessments/asmt_1/checks/asmc_oast/oast-correlations'
    const callbackUrl = 'https://private-callback.callbacks.example.test'
    const planFor = selected => ({
      action: { id: '', key: 'oast_private_callback', kind: '' },
      target: {
        entity_id: 'ent_oast_url',
        type: 'url',
        value: 'https://example.com/search?term=one',
      },
      http_profile: null,
      policy_level: 'intrusive',
      scope: { target_count: 1, fan_out: 1 },
      bounds: {
        summary: 'One reviewed URL and saved query parameter.',
        credential_use: 'none',
      },
      display_command: "dalfox url 'https://example.com/search?term=one' -p term --blind 'https://[private-oast-callback]'",
      launchable: false,
      unavailable_reason: selected ? 'Prepare a private callback before this reviewed action can start.' : 'Choose saved evidence.',
      plan_digest: selected ? 'b'.repeat(64) : 'a'.repeat(64),
      evidence_selection: {
        kind: 'dalfox_parameter_observation',
        required: true,
        overflow: false,
        options: [oastEvidence],
        selected: selected ? oastEvidence : null,
      },
      oast: {
        preparable: selected,
        callback_url: 'https://[private-oast-callback]',
        reservation_window_seconds: 900,
      },
    })
    const reserved = {
      id: 'ocr_private_1',
      project_id: 'prj_1',
      assessment_id: 'asmt_1',
      check_id: 'asmc_oast',
      action_key: 'oast_private_callback',
      run_id: '',
      status: 'reserved',
      provider_ready: false,
      callback_url: 'https://[private-oast-callback]',
      interaction_count: 0,
      duplicate_count: 0,
      rejected_count: 0,
      active_until: '2026-08-05T10:15:00+00:00',
      purge_at: '2026-08-12T10:15:00+00:00',
    }
    const ready = { ...reserved, provider_ready: true, callback_url: callbackUrl }
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (url.endsWith('/http-profiles')) return apiResponse({ profiles: [], total: 0 })
      if (url === actionPath || url.startsWith(`${actionPath}?`)) {
        return apiResponse({ plan: planFor(url.includes('parameter_observation_id=')) })
      }
      if (url === correlationPath && options.method === 'POST') {
        return apiResponse({ correlation: reserved })
      }
      if (url === correlationPath) return apiResponse({ correlations: [] })
      if (url === `${correlationPath}/${reserved.id}`) {
        return apiResponse({ correlation: ready })
      }
      if (url === `${correlationPath}/${reserved.id}/launch` && options.method === 'POST') {
        return apiResponse({
          correlation_id: reserved.id,
          run: {
            run_id: 'run_oast_1',
            run_type: 'external',
            status: 'running',
            command: planFor(true).display_command,
            started: '2026-08-05T10:02:00+00:00',
            stream: '/runs/run_oast_1/stream',
          },
          plan: planFor(true),
        })
      }
      if (/\/assessments\/[^?]+/.test(url)) return apiResponse(oastDetail)
      return apiResponse({ assessments: [cycle], profiles, total: 1 })
    })
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })
    await vi.waitFor(() => expect(projectWorkspaceRequest).toHaveBeenCalledWith(
      correlationPath,
      { cache: 'no-store' },
    ))
    const container = document.createElement('div')
    document.body.appendChild(container)
    controller.renderAssessment(container, 'prj_1')
    container.querySelector('.project-assessment-target-toggle')?.click()
    ;[...container.querySelectorAll('.project-assessment-check-row .btn')]
      .find(button => button.textContent === 'Prepare private callback')?.click()

    await vi.waitFor(() => expect(projectWorkspaceRequest).toHaveBeenCalledWith(
      correlationPath,
      expect.objectContaining({ method: 'POST' }),
    ))
    controller.renderAssessment(container, 'prj_1')
    container.querySelector('.project-assessment-target-toggle')?.click()
    expect(container.textContent).toContain('The private worker is preparing an app-owned callback')
    expect(container.textContent).toContain('Callback window ends')
    expect(container.textContent).not.toContain(callbackUrl)
    ;[...container.querySelectorAll('.project-assessment-oast-actions .btn')]
      .find(button => button.textContent === 'Refresh status')?.click()

    await vi.waitFor(() => expect(projectWorkspaceRequest).toHaveBeenCalledWith(
      `${correlationPath}/${reserved.id}`,
      { cache: 'no-store' },
    ))
    await vi.waitFor(() => expect(
      controller.oastStateFor('prj_1', 'asmt_1', 'asmc_oast').correlations[0]?.provider_ready,
    ).toBe(true))
    controller.renderAssessment(container, 'prj_1')
    container.querySelector('.project-assessment-target-toggle')?.click()
    expect(container.textContent).toContain('The private callback is ready')
    expect(container.textContent).not.toContain(callbackUrl)
    ;[...container.querySelectorAll('.project-assessment-oast-actions .btn')]
      .find(button => button.textContent === 'Review and start run')?.click()

    await vi.waitFor(() => expect(ctx.attachActiveRunFromMonitor).toHaveBeenCalledWith(
      expect.objectContaining({ run_id: 'run_oast_1' }),
    ))
    expect(ctx.closeProjectWorkspace).toHaveBeenCalledWith({ refocus: false })
    const reservationCall = projectWorkspaceRequest.mock.calls.find(([url, options]) => (
      url === correlationPath && options?.method === 'POST'
    ))
    expect(JSON.parse(reservationCall[1].body)).toEqual({
      confirmed: true,
      plan_digest: 'b'.repeat(64),
      source_run_id: oastEvidence.source_run_id,
      parameter_observation_id: oastEvidence.observation_id,
    })
    const launchCall = projectWorkspaceRequest.mock.calls.find(([url, options]) => (
      url.endsWith('/launch') && options?.method === 'POST'
    ))
    expect(JSON.parse(launchCall[1].body)).toEqual(JSON.parse(reservationCall[1].body))
    expect(JSON.stringify(ctx.showConfirm.mock.calls)).not.toContain(callbackUrl)
    expect(ctx.logClientError).not.toHaveBeenCalled()
    controller.invalidate('prj_1')
  })

  it('shows recovered private OAST interaction counts and retention with a Run Details handoff', async () => {
    const correlationPath = '/projects/prj_1/assessments/asmt_1/checks/asmc_oast/oast-correlations'
    const active = {
      id: 'ocr_active_1',
      project_id: 'prj_1',
      assessment_id: 'asmt_1',
      check_id: 'asmc_oast',
      action_key: 'oast_private_callback',
      run_id: 'run_oast_active',
      status: 'active',
      provider_ready: true,
      callback_url: 'https://must-not-render.callbacks.example.test',
      interaction_count: 2,
      duplicate_count: 1,
      rejected_count: 3,
      active_until: '2026-08-05T10:15:00+00:00',
      purge_at: '2026-08-12T10:15:00+00:00',
    }
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (url.endsWith('/http-profiles')) return apiResponse({ profiles: [], total: 0 })
      if (url === correlationPath) return apiResponse({ correlations: [active] })
      if (url === `${correlationPath}/${active.id}`) return apiResponse({ correlation: active })
      if (/\/assessments\/[^?]+/.test(url)) return apiResponse(oastDetail)
      return apiResponse({ assessments: [cycle], profiles, total: 1 })
    })
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })
    await vi.waitFor(() => expect(projectWorkspaceRequest).toHaveBeenCalledWith(
      correlationPath,
      { cache: 'no-store' },
    ))
    const container = document.createElement('div')
    controller.renderAssessment(container, 'prj_1')
    container.querySelector('.project-assessment-target-toggle')?.click()

    expect(container.textContent).toContain('2 accepted interactions attached the source run as assessment evidence')
    expect(container.textContent).toContain('2 accepted · 1 duplicate · 3 rejected')
    expect(container.textContent).toContain('Cleanup eligible')
    expect(container.textContent).not.toContain('must-not-render')
    ;[...container.querySelectorAll('.project-assessment-oast-actions .btn')]
      .find(button => button.textContent === 'Open Run Details')?.click()
    expect(ctx.openHistoryRunDetails).toHaveBeenCalledWith({ id: 'run_oast_active' })
    expect(ctx.closeProjectWorkspace).toHaveBeenCalledWith({ refocus: false })
    controller.invalidate('prj_1')
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
      expect(recommendation?.querySelector('.badge')?.classList.contains('badge-tone-cyan')).toBe(true)
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
            }, {
              key: 'smb_enumeration',
              label: 'Enumerate SMB safely',
              rationale: 'The service fingerprint explicitly identified SMB.',
              command: 'command:nmap',
              nmap_profile: {
                key: 'smb',
                label: 'SMB protocol and signing',
                selector_kind: 'scripts',
                selectors: ['smb-protocols', 'smb2-security-mode'],
              },
              service: 'smb',
              port: 445,
              proto: 'tcp',
              version: '',
              launch_mode: 'assessment_action_only',
              auto_launch: false,
            }],
            action_count: 2,
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
      expect(recommendation?.querySelector('.badge')?.classList.contains('badge-tone-cyan')).toBe(true)
      expect(recommendation?.textContent).toContain('Review HTTPS surface')
      expect(recommendation?.textContent).toContain('443/tcp · https · nginx 1.26')
      expect(recommendation?.textContent).toContain('445/tcp · smb')
      expect(recommendation?.textContent).toContain('Reviewed profile: SMB protocol and signing')
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
    expect(items.map(button => button.textContent)).toEqual([
      'Set manual decision',
      'Manage evidence',
      'Run Nmap',
      'Create finding',
    ])
    expect(items[0].disabled).toBe(false)
    expect(items[1].disabled).toBe(false)
    expect(items[2].disabled).toBe(true)
    expect(items[3].disabled).toBe(false)
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
      expect(observations.textContent).toBe('▸View 2 observations')
      observations.click()
      expect(observations.getAttribute('aria-expanded')).toBe('true')
      expect(observations.textContent).toBe('▾Hide 2 observations')
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
    let holdNextDetail = false
    let releaseDetail = null
    const projectWorkspaceRequest = vi.fn((url, options) => {
      const response = responseFor(url, options)
      if (holdNextDetail && url.includes('/assessments/asmt_1?')) {
        holdNextDetail = false
        return new Promise((resolve) => {
          releaseDetail = () => resolve(response)
        })
      }
      return Promise.resolve(response)
    })
    const controller = DarklabProjectAssessment.createProjectAssessmentController(
      makeContext(projectWorkspaceRequest),
    )
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    document.body.appendChild(container)

    holdNextDetail = true
    const checkRefresh = controller.setFilter('prj_1', 'category', 'discovery')
    controller.renderAssessment(container, 'prj_1')
    expect(container.textContent).toContain('Coverage')
    expect(container.querySelector('.project-assessment-risk-row')).not.toBeNull()
    expect(container.textContent).toContain('Loading assessment checks...')
    expect(container.textContent).not.toContain('Loading assessment coverage...')
    releaseDetail()
    await checkRefresh

    await controller.setFilter('prj_1', 'state', 'needs_review')
    await controller.setPage('prj_1', 50)
    holdNextDetail = true
    const findingRefresh = controller.setFindingFilter('prj_1', 'epss')
    controller.renderAssessment(container, 'prj_1')
    expect(container.textContent).toContain('Coverage')
    expect(container.querySelector('.project-assessment-target-list')).not.toBeNull()
    expect(container.textContent).toContain('Loading prioritized findings...')
    expect(container.textContent).not.toContain('Loading assessment coverage...')
    releaseDetail()
    await findingRefresh

    await controller.setFindingPage('prj_1', 10)

    const detailUrls = projectWorkspaceRequest.mock.calls
      .map(([url]) => url)
      .filter(url => url.includes('/assessments/asmt_1?'))
    expect(detailUrls.at(-1)).toContain('limit=50&offset=50')
    expect(detailUrls.at(-1)).toContain('category=discovery')
    expect(detailUrls.at(-1)).toContain('state=needs_review')
    expect(detailUrls.at(-1)).toContain('finding_priority=epss')
    expect(detailUrls.at(-1)).toContain('finding_offset=10')

    controller.renderAssessment(container, 'prj_1')
    container.querySelector('.project-assessment-target-toggle').click()
    const list = container.querySelector('.project-assessment-target-list')
    list.scrollTop = 137
    list.dispatchEvent(new Event('scroll'))
    controller.renderAssessment(container, 'prj_1')
    const restoredList = container.querySelector('.project-assessment-target-list')
    expect(restoredList.isConnected).toBe(true)
    expect(restoredList.scrollTop).toBe(0)
    await new Promise(resolve => requestAnimationFrame(resolve))
    expect(restoredList.isConnected).toBe(true)
    expect(restoredList.scrollTop).toBe(137)

    const state = controller.stateFor('prj_1')
    expect(state.category).toBe('discovery')
    expect(state.checkState).toBe('needs_review')
    expect(state.offset).toBe(50)
    expect(state.findingPriority).toBe('epss')
    expect(state.findingOffset).toBe(10)
    expect(state.checksScrollTop).toBe(137)
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
    ctx.renderProjectExplorer.mockImplementation(() => {
      controller.renderAssessment(container, 'prj_1')
    })
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
    expect(container.textContent).toContain('Network review')
    expect(container.textContent).not.toContain('Loading project assessments...')

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
    viewerCycleContainer.querySelector('.project-assessment-target-toggle').click()
    const manualDecisionButtons = [...viewerCycleContainer.querySelectorAll('.project-assessment-check-row button')]
      .filter(button => button.textContent.includes('manual decision'))
    expect(manualDecisionButtons).toHaveLength(2)
    expect(manualDecisionButtons.every(button => (
      button.disabled && button.title.includes('View-only')
    ))).toBe(true)
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
    const container = document.createElement('div')
    ctx.renderProjectExplorer.mockImplementation(() => {
      controller.renderAssessment(container, 'prj_1')
    })
    controller.renderAssessment(container, 'prj_1')

    expect(await controller.transitionCycle('prj_1', 'completed')).toBe(true)
    expect(current.status).toBe('completed')
    expect(ctx.invalidateProjectOverview).toHaveBeenCalledWith('prj_1')
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('Assessment cycle completed.')
    expect(container.textContent).toContain('Network review')
    expect(container.textContent).not.toContain('Loading project assessments...')

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

  it('renders the empty cycle state without waiting for an HTTP-profile refresh', async () => {
    let deleted = false
    let httpProfileLoads = 0
    let resolvePendingHttpProfiles
    const pendingHttpProfiles = new Promise((resolve) => {
      resolvePendingHttpProfiles = resolve
    })
    let controller
    const archived = { ...cycle, status: 'archived' }
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (url.endsWith('/http-profiles')) {
        httpProfileLoads += 1
        if (httpProfileLoads === 1) return apiResponse({ profiles: [], total: 0 })
        return pendingHttpProfiles
      }
      if (url.endsWith('/delete-preview')) {
        return apiResponse({
          preview: {
            can_delete: true,
            will_delete: { checks: 2, evidence_links: 0 },
          },
        })
      }
      if (options.method === 'DELETE') {
        deleted = true
        controller.httpProfileStateFor('prj_1').loaded = false
        return apiResponse({ ok: true })
      }
      if (/\/assessments\/[^?]+/.test(url)) {
        return apiResponse({ ...detail, assessment: { ...detail.assessment, ...archived } })
      }
      return apiResponse({
        assessments: deleted ? [] : [archived],
        profiles,
        total: deleted ? 0 : 1,
        limit: 100,
        offset: 0,
        has_more: false,
      })
    })
    const ctx = makeContext(projectWorkspaceRequest)
    controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })

    let deletionSettled = false
    const deletion = controller.deleteCycle('prj_1').then((result) => {
      deletionSettled = true
      return result
    })
    await vi.waitFor(() => expect(httpProfileLoads).toBe(2))
    await Promise.resolve()

    expect(deletionSettled).toBe(true)
    expect(await deletion).toBe(true)
    expect(controller.stateFor('prj_1').assessments).toEqual([])
    const surface = document.createElement('div')
    controller.renderAssessment(surface, 'prj_1')
    expect(surface.textContent).toContain('Start an assessment')
    expect(surface.textContent).not.toContain('Delete assessment')

    resolvePendingHttpProfiles(apiResponse({ profiles: [], total: 0 }))
  })

  it('rejects failed lifecycle mutation responses without claiming success', async () => {
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (options.method === 'PATCH') {
        return apiResponse({ error: 'assessment update rejected' }, { ok: false })
      }
      return responseFor(url, options)
    })
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })

    expect(await controller.transitionCycle('prj_1', 'completed')).toBe(false)
    expect(controller.stateFor('prj_1').assessments[0].status).toBe('active')
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith(
      'Could not update this assessment cycle.',
      { error: true },
    )
    expect(ctx.setProjectWorkspaceMessage).not.toHaveBeenCalledWith('Assessment cycle completed.')
  })

  it('supersedes a stale detail load when a lifecycle reload is forced', async () => {
    let current = { ...cycle }
    let detailCalls = 0
    let resolveFirstDetail
    const firstDetailResponse = new Promise((resolve) => {
      resolveFirstDetail = resolve
    })
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (url.endsWith('/http-profiles')) {
        return apiResponse({ error: 'Internal server error' }, { ok: false })
      }
      if (options.method === 'PATCH') {
        current = { ...current, status: JSON.parse(options.body).status }
        return apiResponse({ assessment: current })
      }
      if (/\/assessments\/[^?]+/.test(url)) {
        detailCalls += 1
        if (detailCalls === 1) return firstDetailResponse
        return apiResponse({
          ...detail,
          assessment: { ...detail.assessment, ...current },
        })
      }
      return apiResponse({
        assessments: [current],
        profiles,
        total: 1,
        limit: 100,
        offset: 0,
        has_more: false,
      })
    })
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    const initialLoad = controller.load('prj_1', { render: false })

    await vi.waitFor(() => expect(detailCalls).toBe(1))
    const surface = document.createElement('div')
    controller.renderAssessment(surface, 'prj_1')
    expect(surface.textContent).toContain('Complete cycle')

    const transition = controller.transitionCycle('prj_1', 'completed')
    await vi.waitFor(() => expect(detailCalls).toBe(2))
    expect(await transition).toBe(true)

    const state = controller.stateFor('prj_1')
    expect(state.loading).toBe(false)
    expect(state.detailLoading).toBe(false)
    expect(state.loaded).toBe(true)
    expect(state.detail.assessment.status).toBe('completed')
    controller.renderAssessment(surface, 'prj_1')
    expect(surface.textContent).not.toContain('Loading project assessments...')

    resolveFirstDetail(apiResponse(detail))
    expect(await initialLoad).toBe(false)
    expect(state.detail.assessment.status).toBe('completed')
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
