// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'
import { DarklabProjectMonitoring as esmProjectMonitoring } from '../../../app/static/js/features/projects/project_monitoring.js'
import {
  setHistoryRunModalStateHandlers,
} from '../../../app/static/js/features/history/history_run_modal_state_bridge.js'
import {
  setHistoryCompareHandlers,
} from '../../../app/static/js/features/run-comparison/history_compare_bridge.js'

function apiResponse(payload = {}, { ok = true } = {}) {
  return {
    ok,
    json: vi.fn(async () => payload),
  }
}

function loadMonitoringModule() {
  globalThis.__darklabExtractPreferGlobalThis = true
  globalThis.openHistoryRunDetails = vi.fn()
  globalThis.fetchAndRenderHistoryComparison = vi.fn()
  return fromDomScripts(
    ['app/static/js/features/projects/project_monitoring.js'],
    { document, window },
    'globalThis.DarklabProjectMonitoring',
  )
}

function makeContext(projectWorkspaceRequest, overrides = {}) {
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
    emptyProjectPanel: vi.fn((text) => {
      const panel = document.createElement('div')
      panel.className = 'project-empty'
      panel.textContent = text
      return panel
    }),
    logClientError: vi.fn(),
    renderProjectExplorer: vi.fn(),
    renderProjectMobileDetail: vi.fn(),
    setProjectWorkspaceMessage: vi.fn(),
    mobileView: vi.fn(() => 'desktop'),
    ...overrides,
  }
}

const monitoringPayload = {
  can_manage_digest_settings: true,
  counts: {
    active: 1,
    changed: 1,
    failed: 0,
    quiet: 1,
    paused: 0,
  },
  digest_settings: {
    enabled: true,
    cadence_preset: 'daily',
    channel_ids: ['ntc_ops'],
    quiet_no_change: false,
    risk_escalations_enabled: true,
    last_evaluated_at: '2026-06-15T11:30:00+00:00',
    last_sent_at: '2026-06-15T11:35:00+00:00',
    next_due_at: '2026-06-16T11:35:00+00:00',
    schedule_last_error: '',
    schedule_paused_reason: '',
    schedule_last_fire_at: '2026-06-15T11:30:00+00:00',
    schedule_last_fire_reason: 'digest skipped: no changes',
    schedule_last_fire_status: 'fired',
  },
  quiet_no_change_threshold: 3,
  notification_channels: [{
    id: 'ntc_ops',
    kind: 'slack',
    label: 'Ops Slack',
  }, {
    id: 'ntc_email',
    kind: 'email',
    label: 'Security Email',
  }],
  filter_options: {
    statuses: [
      { value: 'changed', label: 'changed' },
      { value: 'quiet', label: 'quiet' },
    ],
    severities: [
      { value: 'critical', label: 'critical' },
      { value: 'informational', label: 'informational' },
    ],
    classifiers: [
      { value: 'ports', label: 'ports' },
      { value: 'textual', label: 'textual' },
    ],
    cadences: [
      { value: 'daily', label: 'daily' },
      { value: 'hourly', label: 'hourly' },
    ],
    ack_states: [
      { value: 'new', label: 'new' },
      { value: 'resolved', label: 'resolved' },
    ],
    groups: [
      { value: 'ports', label: 'External perimeter/ports' },
      { value: 'tls', label: 'Certificates' },
      { value: 'web', label: 'Web checks' },
    ],
    targets: [
      { id: 'ent_darklab', type: 'domain', value: 'darklab.sh' },
    ],
  },
  monitors: [{
    id: 'wtr_1',
    label: 'Ports',
    command_text: 'nmap -sV darklab.sh',
    dashboard_state: 'changed',
    monitor_group: { key: 'ports', label: 'External perimeter/ports', command_root: 'nmap' },
    options: { suppress_removals: true, notify_metadata_changes: false },
    policy: {
      ignore_line_patterns: ['timing jitter'],
      alert_after_repeated_changes: 2,
      alert_signal_classes: ['ports'],
    },
    current_triage_state: 'new',
    current_triage_fire: {
      id: 'wtf_1',
      fire_kind: 'changed',
      created: '2026-06-15T12:00:00+00:00',
    },
    linked_targets: [{ id: 'ent_darklab', type: 'domain', value: 'darklab.sh' }],
    schedule: { cadence_preset: 'hourly', enabled: true, next_run_at: '2026-06-15T13:00:00+00:00' },
    baseline_run_id: 'run_base',
    baseline_run: { id: 'run_base', command: 'nmap -sV darklab.sh --baseline' },
    last_run_id: 'run_current',
    last_run: { id: 'run_current', command: 'nmap -sV darklab.sh' },
    latest_fire: {
      id: 'wtf_1',
      watcher_id: 'wtr_1',
      watcher_label: 'Ports',
      watcher_command: 'nmap -sV darklab.sh',
      fire_kind: 'changed',
      ack_state: 'new',
      ack_note: '',
      created: '2026-06-15T12:00:00+00:00',
      run_id: 'run_current',
      baseline_run_id: 'run_base',
      run_available: true,
      baseline_run_available: true,
      run: { id: 'run_current', command: 'nmap -sV darklab.sh' },
      baseline_run: { id: 'run_base', command: 'nmap -sV darklab.sh' },
      rollup: {
        classifier: 'ports',
        severity: 'critical',
        added: 1,
        removed: 0,
        changed: 0,
        truncated: false,
        top_signals: [{ kind: 'port_added', label: 'New open port 443/tcp https' }],
      },
      monitor_group: { key: 'ports', label: 'External perimeter/ports', command_root: 'nmap' },
      linked_targets: [{ id: 'ent_darklab', type: 'domain', value: 'darklab.sh' }],
    },
  }, {
    id: 'wtr_2',
    label: 'TLS',
    command_text: 'openssl s_client -connect darklab.sh:443',
    dashboard_state: 'quiet',
    monitor_group: { key: 'tls', label: 'Certificates', command_root: 'openssl' },
    options: { suppress_removals: false, notify_metadata_changes: true },
    policy: {
      ignore_line_patterns: [],
      alert_after_repeated_changes: 1,
      alert_signal_classes: [],
    },
    current_triage_state: 'resolved',
    linked_targets: [{ id: 'ent_darklab', type: 'domain', value: 'darklab.sh' }],
    schedule: { cadence_preset: 'daily', enabled: true },
    latest_fire: null,
  }],
  risk_events: [{
    id: 'rsk_1',
    cve_id: 'CVE-2026-10001',
    source: 'kev',
    transition_kind: 'kev_added',
    feed_version: '2026.06.15',
    old_value: 'false',
    new_value: 'true',
    model_changed: false,
    observation_count: 2,
    ack_state: 'new',
    ack_note: '',
    created: '2026-06-15T12:05:00+00:00',
  }],
  timeline: [{
    id: 'wtf_1',
    watcher_id: 'wtr_1',
    watcher_label: 'Ports',
    watcher_command: 'nmap -sV darklab.sh',
    fire_kind: 'changed',
    ack_state: 'new',
    ack_note: '',
    created: '2026-06-15T12:00:00+00:00',
    run_id: 'run_current',
    baseline_run_id: 'run_base',
    run_available: true,
    baseline_run_available: true,
    run: { id: 'run_current', command: 'nmap -sV darklab.sh' },
    baseline_run: { id: 'run_base', command: 'nmap -sV darklab.sh' },
    rollup: {
      classifier: 'ports',
      severity: 'critical',
      added: 1,
      removed: 0,
      changed: 0,
      truncated: false,
      top_signals: [{ kind: 'port_added', label: 'New open port 443/tcp https' }],
    },
    monitor_group: { key: 'ports', label: 'External perimeter/ports', command_root: 'nmap' },
    linked_targets: [{ id: 'ent_darklab', type: 'domain', value: 'darklab.sh' }],
  }, {
    id: 'wtf_2',
    watcher_id: 'wtr_2',
    watcher_label: 'Missing baseline',
    watcher_command: 'httpx https://darklab.sh',
    fire_kind: 'no_change',
    ack_state: 'resolved',
    ack_note: 'Looks fine',
    created: '2026-06-15T11:00:00+00:00',
    run_id: 'run_same',
    baseline_run_id: 'run_deleted',
    run_available: true,
    baseline_run_available: false,
    run: { id: 'run_same', command: 'httpx https://darklab.sh' },
    baseline_run: null,
    rollup: {
      classifier: 'textual',
      severity: 'informational',
      added: 0,
      removed: 0,
      changed: 0,
      truncated: false,
      top_signals: [],
    },
    monitor_group: { key: 'web', label: 'Web checks', command_root: 'httpx' },
    linked_targets: [{ id: 'ent_darklab', type: 'domain', value: 'darklab.sh' }],
  }, {
    id: 'wtf_3',
    watcher_id: 'wtr_1',
    watcher_label: 'Missing current',
    watcher_command: 'nmap -sV darklab.sh',
    fire_kind: 'changed',
    ack_state: 'new',
    ack_note: '',
    created: '2026-06-15T10:30:00+00:00',
    run_id: 'run_deleted_current',
    baseline_run_id: 'run_base',
    run_available: false,
    baseline_run_available: true,
    run: null,
    baseline_run: { id: 'run_base', command: 'nmap -sV darklab.sh --baseline' },
    rollup: {
      classifier: 'ports',
      severity: 'important',
      added: 0,
      removed: 0,
      changed: 1,
      truncated: false,
      top_signals: [{ kind: 'port_changed', label: 'Changed port 443/tcp https' }],
    },
    monitor_group: { key: 'ports', label: 'External perimeter/ports', command_root: 'nmap' },
    linked_targets: [{ id: 'ent_darklab', type: 'domain', value: 'darklab.sh' }],
  }],
}

describe('project monitoring controller', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    delete globalThis.DarklabProjectMonitoring
    delete window.DarklabProjectMonitoring
    delete globalThis.__darklabExtractPreferGlobalThis
    delete globalThis.openHistoryRunDetails
    delete globalThis.fetchAndRenderHistoryComparison
    delete globalThis.openWatchersModal
    delete globalThis.showConfirm
    delete window.showConfirm
    setHistoryRunModalStateHandlers({ openHistoryRunDetails: null })
    setHistoryCompareHandlers({ fetchAndRenderHistoryComparison: null })
  })

  afterEach(() => {
    vi.useRealTimers()
    setHistoryRunModalStateHandlers({ openHistoryRunDetails: null })
    setHistoryCompareHandlers({ fetchAndRenderHistoryComparison: null })
  })

  it('renders project monitoring counts monitors and disables missing-run comparisons', async () => {
    const monitoringApi = loadMonitoringModule()
    globalThis.openWatchersModal = vi.fn()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(monitoringPayload))
    const controller = monitoringApi.createProjectMonitoringController(makeContext(projectWorkspaceRequest))

    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderMonitoring(container, 'prj_1')

    expect(projectWorkspaceRequest).toHaveBeenCalledWith('/projects/prj_1/monitoring?fire_limit=8', { cache: 'no-store' })
    expect(container.textContent).toContain('Changed')
    expect(container.textContent).toContain('Digest Notifications')
    expect(container.textContent).toContain('CVE Risk Changes')
    expect(container.textContent).toContain('CVE-2026-10001')
    expect(container.textContent).toContain('Added to CISA KEV')
    expect(container.textContent).toContain('Ops Slack · slack')
    expect(container.textContent).toContain('Security Email · email')
    expect(container.textContent).toContain('last sent: 2026-06-15 11:35:00+00:00')
    expect(container.textContent).toContain('next due: 2026-06-16 11:35:00+00:00')
    expect(container.textContent).toContain('last result: digest skipped: no changes')
    const rootChildren = [...container.querySelector('[data-project-monitoring-root]').children]
    expect(rootChildren[0].classList.contains('project-monitoring-counts')).toBe(true)
    expect(rootChildren[1].classList.contains('project-monitoring-filters')).toBe(true)
    expect(rootChildren[2].classList.contains('project-monitoring-risk')).toBe(true)
    expect(rootChildren[3].classList.contains('project-monitoring-digest')).toBe(true)
    expect(container.textContent).toContain('Ports')
    expect(container.textContent).toContain('TLS')
    expect(container.textContent).toContain('Missing baseline')
    expect(container.textContent).toContain('Missing current')
    expect(container.textContent).toContain('External perimeter/ports')
    expect(container.textContent).toContain('Certificates')
    expect(container.textContent).toContain('Ignoring removals')
    expect(container.textContent).toContain('Metadata alerts off')
    expect(container.textContent).toContain('Alerts after 2 changes')
    expect(container.textContent).toContain('Ignoring 1 patterns')
    expect(container.textContent).toContain('Signals: ports')
    expect(container.textContent).toContain('All signals')
    expect(container.textContent).toContain('Critical')
    expect(container.textContent).toContain('New open port 443/tcp https')
    expect(container.querySelector('.project-monitoring-card-grid')).not.toBeNull()
    const disabledCompare = [...container.querySelectorAll('[data-project-monitoring-action="compare"]')]
      .find(button => button.dataset.baselineRunId === '')
    expect(disabledCompare.disabled).toBe(true)
    const missingCurrentRow = container.querySelector('[data-project-monitoring-fire-id="wtf_3"]')
    expect(missingCurrentRow.querySelector('[data-project-monitoring-action="details"]').disabled).toBe(true)
    expect(missingCurrentRow.querySelector('[data-project-monitoring-action="compare"]').disabled).toBe(true)
    expect(missingCurrentRow.querySelector('[data-project-monitoring-action="compare"]').dataset.baselineRunId)
      .toBe('run_base')
    const severityFilter = container.querySelector('[data-project-monitoring-filter="severity"]')
    severityFilter.value = 'critical'
    controller.handleChange({ target: severityFilter, preventDefault: vi.fn(), stopPropagation: vi.fn() })
    controller.renderMonitoring(container, 'prj_1')
    expect(container.textContent).toContain('Ports')
    expect(container.textContent).not.toContain('TLS')
  })

  it('labels NVD advisory and CVSS transitions without presenting them as scanner findings', async () => {
    const monitoringApi = loadMonitoringModule()
    const payload = {
      ...monitoringPayload,
      risk_events: [{
        ...monitoringPayload.risk_events[0],
        id: 'rsk_nvd_cvss',
        source: 'nvd',
        transition_kind: 'nvd_cvss_downgraded',
        old_value: '9.8',
        new_value: '8.7',
      }, {
        ...monitoringPayload.risk_events[0],
        id: 'rsk_nvd_status',
        source: 'nvd',
        transition_kind: 'nvd_reinstated',
        old_value: 'disputed',
        new_value: 'active',
      }],
    }
    const controller = monitoringApi.createProjectMonitoringController(makeContext(
      vi.fn(async () => apiResponse(payload)),
    ))

    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderMonitoring(container, 'prj_1')

    expect(container.textContent).toContain('NVD CVSS downgraded')
    expect(container.textContent).toContain('CVSS 9.8 → 8.7')
    expect(container.textContent).toContain('NVD advisory reinstated')
    expect(container.textContent).toContain('Disputed → Active')
    expect(container.textContent).not.toContain('Added to CISA KEV')
  })

  it('saves digest settings from the monitoring tab', async () => {
    const monitoringApi = loadMonitoringModule()
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (String(url).endsWith('/digest-settings')) {
        expect(options.method).toBe('PATCH')
        expect(JSON.parse(options.body)).toEqual({
          enabled: true,
          cadence_preset: 'weekly',
          channel_ids: ['ntc_ops', 'ntc_email'],
          quiet_no_change: true,
          risk_escalations_enabled: true,
        })
        return apiResponse({
          can_manage_digest_settings: true,
          digest_settings: {
            enabled: true,
            cadence_preset: 'weekly',
            channel_ids: ['ntc_ops', 'ntc_email'],
            quiet_no_change: true,
            risk_escalations_enabled: true,
            last_evaluated_at: '',
            last_sent_at: '',
          },
          notification_channels: monitoringPayload.notification_channels,
        })
      }
      return apiResponse(monitoringPayload)
    })
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = monitoringApi.createProjectMonitoringController(ctx)

    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderMonitoring(container, 'prj_1')
    expect(container.querySelector('.project-monitoring-digest-toggle').classList.contains('form-check')).toBe(true)
    expect(container.querySelector('.project-monitoring-digest-channel').classList.contains('form-check')).toBe(true)
    expect(container.querySelector('.project-monitoring-digest-channels').classList.contains('nice-scroll')).toBe(true)
    container.querySelector('[data-project-digest-field="cadence_preset"]').value = 'weekly'
    container.querySelector('[data-project-digest-field="quiet_no_change"]').checked = true
    container.querySelector('[data-project-digest-field="risk_escalations_enabled"]').checked = true
    container.querySelector('[data-project-digest-field="channel"][value="ntc_email"]').checked = true
    const save = container.querySelector('[data-project-monitoring-action="save-digest"]')

    await controller.handleClick({ target: save, preventDefault: vi.fn(), stopPropagation: vi.fn() })

    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('Digest settings saved.')
    expect(ctx.renderProjectExplorer).toHaveBeenCalled()
    expect(controller.stateFor('prj_1').digestSettings.cadence_preset).toBe('weekly')
  })

  it('updates a CVE risk acknowledgement from the shared monitoring triage controls', async () => {
    const monitoringApi = loadMonitoringModule()
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (String(url).includes('/monitoring/risk-events/')) {
        expect(options.method).toBe('PATCH')
        expect(JSON.parse(options.body)).toEqual({
          ack_state: 'needs_action',
          ack_note: 'Patch during the next maintenance window.',
        })
        return apiResponse({ ok: true })
      }
      return apiResponse(monitoringPayload)
    })
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = monitoringApi.createProjectMonitoringController(ctx)

    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderMonitoring(container, 'prj_1')
    container.querySelector('[data-project-monitoring-risk-note="rsk_1"]').value = 'Patch during the next maintenance window.'
    const action = container.querySelector('[data-project-monitoring-action="ack-risk"][data-ack-state="needs_action"]')

    await controller.handleClick({ target: action, preventDefault: vi.fn(), stopPropagation: vi.fn() })

    expect(projectWorkspaceRequest).toHaveBeenCalledWith(
      '/projects/prj_1/monitoring/risk-events/rsk_1',
      expect.objectContaining({ method: 'PATCH' }),
    )
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('CVE risk change updated.')
  })

  it('renders digest settings as read-only for team viewers', async () => {
    const monitoringApi = loadMonitoringModule()
    const readonlyPayload = {
      ...monitoringPayload,
      can_manage_digest_settings: false,
    }
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(readonlyPayload))
    const controller = monitoringApi.createProjectMonitoringController(makeContext(projectWorkspaceRequest))

    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderMonitoring(container, 'prj_1')

    expect(container.textContent).toContain('read-only')
    expect(container.querySelector('[data-project-monitoring-action="save-digest"]').disabled).toBe(true)
    expect([...container.querySelectorAll('[data-project-digest-field]')]
      .every(control => control.disabled)).toBe(true)
  })

  it('renders monitor timing and baseline run metadata on cards', async () => {
    const monitoringApi = loadMonitoringModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(monitoringPayload))
    const controller = monitoringApi.createProjectMonitoringController(makeContext(projectWorkspaceRequest))

    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderMonitoring(container, 'prj_1')

    const portsCard = [...container.querySelectorAll('.project-monitoring-card')]
      .find(card => card.textContent.includes('Ports'))
    expect(portsCard?.textContent).toContain('next run: 2026-06-15 13:00:00+00:00')
    expect(portsCard?.textContent).toContain('last run: nmap -sV darklab.sh')
    expect(portsCard?.textContent).toContain('last change: 2026-06-15 12:00:00+00:00')
    expect(portsCard?.textContent).toContain('current baseline: nmap -sV darklab.sh --baseline')
  })

  it('changed-since filters exclude monitors without fire timestamps', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-16T12:00:00Z'))
    const monitoringApi = loadMonitoringModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(monitoringPayload))
    const controller = monitoringApi.createProjectMonitoringController(makeContext(projectWorkspaceRequest))

    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderMonitoring(container, 'prj_1')
    const changedFilter = container.querySelector('[data-project-monitoring-filter="changed_since"]')
    changedFilter.value = '7'
    controller.handleChange({ target: changedFilter, preventDefault: vi.fn(), stopPropagation: vi.fn() })
    controller.renderMonitoring(container, 'prj_1')

    expect(container.textContent).toContain('Ports')
    expect(container.textContent).not.toContain('TLS')
    expect(container.querySelector('[data-project-monitoring-fire-id="wtf_1"]')).not.toBeNull()
    expect(container.querySelector('[data-project-monitoring-fire-id="wtf_2"]')).not.toBeNull()
  })

  it('maps dashboard status filters onto equivalent timeline fire kinds', async () => {
    const monitoringApi = loadMonitoringModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(monitoringPayload))
    const controller = monitoringApi.createProjectMonitoringController(makeContext(projectWorkspaceRequest))

    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderMonitoring(container, 'prj_1')
    const statusFilter = container.querySelector('[data-project-monitoring-filter="status"]')
    statusFilter.value = 'quiet'
    controller.handleChange({ target: statusFilter, preventDefault: vi.fn(), stopPropagation: vi.fn() })
    controller.renderMonitoring(container, 'prj_1')

    expect(container.textContent).toContain('TLS')
    expect(container.textContent).not.toContain('Ports')
    expect(container.querySelector('[data-project-monitoring-fire-id="wtf_2"]')).not.toBeNull()
    expect(container.querySelector('[data-project-monitoring-fire-id="wtf_1"]')).toBeNull()
  })

  it('renders monitoring metadata pills with badge primitives and semantic tones', async () => {
    const monitoringApi = loadMonitoringModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(monitoringPayload))
    const controller = monitoringApi.createProjectMonitoringController(makeContext(projectWorkspaceRequest))

    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderMonitoring(container, 'prj_1')

    const changedState = container.querySelector('.project-monitoring-pill.is-changed')
    expect(changedState?.classList.contains('badge')).toBe(true)
    expect(changedState?.classList.contains('badge-tone-amber')).toBe(true)

    const criticalSeverity = container.querySelector('.project-monitoring-severity.is-critical')
    expect(criticalSeverity?.classList.contains('badge')).toBe(true)
    expect(criticalSeverity?.classList.contains('badge-tone-red')).toBe(true)

    const newAck = container.querySelector('.project-monitoring-ack.is-new')
    expect(newAck?.classList.contains('badge')).toBe(true)
    expect(newAck?.classList.contains('badge-tone-muted')).toBe(true)

    const resolvedAck = container.querySelector('.project-monitoring-ack.is-resolved')
    expect(resolvedAck?.classList.contains('badge')).toBe(true)
    expect(resolvedAck?.classList.contains('badge-tone-green')).toBe(true)

    const noChangeFire = container.querySelector('.project-monitoring-fire-kind.is-no_change')
    expect(noChangeFire?.classList.contains('badge')).toBe(true)
    expect(noChangeFire?.classList.contains('badge-tone-green')).toBe(true)

    const policyChips = [...container.querySelectorAll('.project-monitoring-policy-chip')]
    expect(policyChips.length).toBeGreaterThan(0)
    expect(policyChips.every(chip => chip.classList.contains('badge'))).toBe(true)
    expect(policyChips.every(chip => chip.classList.contains('badge-tone-muted'))).toBe(true)
  })

  it('renders triage controls once and only for actionable timeline fires', async () => {
    const monitoringApi = loadMonitoringModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(monitoringPayload))
    const controller = monitoringApi.createProjectMonitoringController(makeContext(projectWorkspaceRequest))

    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderMonitoring(container, 'prj_1')

    const cardLatest = container.querySelector('.project-monitoring-card [data-project-monitoring-fire-id="wtf_1"]')
    expect(cardLatest?.querySelector('[data-project-monitoring-note]')).toBeNull()
    expect(container.querySelectorAll('[data-project-monitoring-note="wtf_1"]')).toHaveLength(1)
    expect(container.querySelectorAll('[data-project-monitoring-note="wtf_2"]')).toHaveLength(0)
    expect([...container.querySelectorAll('[data-project-monitoring-action="ack"]')]
      .filter(button => button.dataset.fireId === 'wtf_1')).toHaveLength(4)
    expect([...container.querySelectorAll('[data-project-monitoring-action="ack"]')]
      .filter(button => button.dataset.fireId === 'wtf_2')).toHaveLength(0)
    expect(container.querySelector('.project-monitoring-timeline')?.classList.contains('nice-scroll')).toBe(true)
  })

  it('requires the shared button factory for action buttons', async () => {
    const monitoringApi = loadMonitoringModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(monitoringPayload))
    const controller = monitoringApi.createProjectMonitoringController(
      makeContext(projectWorkspaceRequest, { makeProjectButton: undefined }),
    )

    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    expect(() => controller.renderMonitoring(container, 'prj_1'))
      .toThrow('Project Monitoring requires a shared project button factory.')
  })

  it('opens run details and compares available monitoring runs from action buttons', async () => {
    const monitoringApi = loadMonitoringModule()
    globalThis.openWatchersModal = vi.fn()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(monitoringPayload))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = monitoringApi.createProjectMonitoringController(ctx)
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderMonitoring(container, 'prj_1')

    const details = container.querySelector('[data-project-monitoring-action="details"][data-run-id="run_current"]')
    await controller.handleClick({ target: details, preventDefault: vi.fn(), stopPropagation: vi.fn() })
    expect(globalThis.openHistoryRunDetails).toHaveBeenCalledWith({ id: 'run_current' })

    const compare = container.querySelector('[data-project-monitoring-action="compare"][data-run-id="run_current"]')
    await controller.handleClick({ target: compare, preventDefault: vi.fn(), stopPropagation: vi.fn() })
    expect(globalThis.fetchAndRenderHistoryComparison).toHaveBeenCalledWith(
      'run_base',
      'run_current',
      { url: '/history/compare?left=run_base&right=run_current&project_id=prj_1' },
    )

    const settings = container.querySelector('[data-project-monitoring-action="settings"][data-watcher-id="wtr_1"]')
    await controller.handleClick({ target: settings, preventDefault: vi.fn(), stopPropagation: vi.fn() })
    expect(globalThis.openWatchersModal).toHaveBeenCalledWith({ watcherId: 'wtr_1' })

    const newMonitor = container.querySelector('[data-project-monitoring-action="new-monitor"]')
    await controller.handleClick({ target: newMonitor, preventDefault: vi.fn(), stopPropagation: vi.fn() })
    expect(globalThis.openWatchersModal).toHaveBeenCalledWith({ projectId: 'prj_1', newWatcher: true })
  })

  it('falls back to lazy globals when ESM bridge handlers are not registered', async () => {
    globalThis.openHistoryRunDetails = vi.fn()
    globalThis.fetchAndRenderHistoryComparison = vi.fn()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(monitoringPayload))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = esmProjectMonitoring.createProjectMonitoringController(ctx)
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderMonitoring(container, 'prj_1')

    const details = container.querySelector('[data-project-monitoring-action="details"][data-run-id="run_current"]')
    await controller.handleClick({ target: details, preventDefault: vi.fn(), stopPropagation: vi.fn() })
    expect(globalThis.openHistoryRunDetails).toHaveBeenCalledWith({ id: 'run_current' })
    expect(ctx.setProjectWorkspaceMessage).not.toHaveBeenCalledWith(
      'Run details are unavailable.',
      { error: true },
    )

    const compare = container.querySelector('[data-project-monitoring-action="compare"][data-run-id="run_current"]')
    await controller.handleClick({ target: compare, preventDefault: vi.fn(), stopPropagation: vi.fn() })
    expect(globalThis.fetchAndRenderHistoryComparison).toHaveBeenCalledWith(
      'run_base',
      'run_current',
      { url: '/history/compare?left=run_base&right=run_current&project_id=prj_1' },
    )
    expect(ctx.setProjectWorkspaceMessage).not.toHaveBeenCalledWith(
      'Run comparison is unavailable.',
      { error: true },
    )
  })

  it('reports unavailable actions when neither ESM bridges nor lazy globals are ready', async () => {
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(monitoringPayload))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = esmProjectMonitoring.createProjectMonitoringController(ctx)
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderMonitoring(container, 'prj_1')

    const details = container.querySelector('[data-project-monitoring-action="details"][data-run-id="run_current"]')
    await controller.handleClick({ target: details, preventDefault: vi.fn(), stopPropagation: vi.fn() })
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith(
      'Run details are unavailable.',
      { error: true },
    )

    const compare = container.querySelector('[data-project-monitoring-action="compare"][data-run-id="run_current"]')
    await controller.handleClick({ target: compare, preventDefault: vi.fn(), stopPropagation: vi.fn() })
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith(
      'Run comparison is unavailable.',
      { error: true },
    )
  })

  it('confirms before accepting a watcher baseline from monitoring', async () => {
    const monitoringApi = loadMonitoringModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(monitoringPayload))
    const showConfirm = vi.fn(async () => null)
    const ctx = makeContext(projectWorkspaceRequest, { showConfirm })
    const controller = monitoringApi.createProjectMonitoringController(ctx)
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderMonitoring(container, 'prj_1')

    const accept = container.querySelector('[data-project-monitoring-action="accept-baseline"]')
    await controller.handleClick({ target: accept, preventDefault: vi.fn(), stopPropagation: vi.fn() })

    expect(showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      tone: 'warning',
      actions: expect.arrayContaining([
        expect.objectContaining({ id: 'cancel', role: 'cancel' }),
        expect.objectContaining({ id: 'accept', label: 'Accept baseline' }),
      ]),
    }))
    expect(projectWorkspaceRequest.mock.calls
      .some(([url, options]) => String(url).includes('/accept-baseline') && options?.method === 'POST')).toBe(false)

    showConfirm.mockResolvedValueOnce('accept')
    await controller.handleClick({ target: accept, preventDefault: vi.fn(), stopPropagation: vi.fn() })

    expect(projectWorkspaceRequest).toHaveBeenCalledWith(
      '/watchers/wtr_1/accept-baseline',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ run_id: 'run_current' }),
      }),
    )
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('Baseline accepted.')
  })

  it('runs pause resume and run-now watcher actions from monitoring cards', async () => {
    const monitoringApi = loadMonitoringModule()
    const pausedPayload = JSON.parse(JSON.stringify(monitoringPayload))
    pausedPayload.monitors[1].dashboard_state = 'paused'
    pausedPayload.monitors[1].state = 'paused'
    pausedPayload.monitors[1].schedule.enabled = false
    let rejectRunNow = false
    const projectWorkspaceRequest = vi.fn(async (url) => {
      if (String(url).endsWith('/run-now')) {
        if (rejectRunNow) return apiResponse({ error: 'queue failed' }, { ok: false })
        return apiResponse({ ok: true })
      }
      if (String(url).startsWith('/watchers/')) return apiResponse({ ok: true })
      return apiResponse(pausedPayload)
    })
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = monitoringApi.createProjectMonitoringController(ctx)
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderMonitoring(container, 'prj_1')

    const pause = container.querySelector('[data-project-monitoring-action="pause"][data-watcher-id="wtr_1"]')
    await controller.handleClick({ target: pause, preventDefault: vi.fn(), stopPropagation: vi.fn() })
    expect(projectWorkspaceRequest).toHaveBeenCalledWith(
      '/watchers/wtr_1',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ pause: true, reason: 'operator paused' }),
      }),
    )
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('Monitor paused.')

    const resume = container.querySelector('[data-project-monitoring-action="resume"][data-watcher-id="wtr_2"]')
    await controller.handleClick({ target: resume, preventDefault: vi.fn(), stopPropagation: vi.fn() })
    expect(projectWorkspaceRequest).toHaveBeenCalledWith(
      '/watchers/wtr_2',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ resume: true }),
      }),
    )
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('Monitor resumed.')

    const runNow = container.querySelector('[data-project-monitoring-action="run-now"][data-watcher-id="wtr_1"]')
    await controller.handleClick({ target: runNow, preventDefault: vi.fn(), stopPropagation: vi.fn() })
    expect(projectWorkspaceRequest).toHaveBeenCalledWith(
      '/watchers/wtr_1/run-now',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('Monitor queued.')

    rejectRunNow = true
    await controller.handleClick({ target: runNow, preventDefault: vi.fn(), stopPropagation: vi.fn() })
    const actionLog = ctx.logClientError.mock.calls.at(-1)
    expect(actionLog[0]).toContain('PROJECT_MONITORING_CLIENT_ACTION_FAILED')
    expect(actionLog[0]).toContain('"phase":"run-now"')
    expect(actionLog[0]).toContain('"watcher_id":"wtr_1"')
    expect(actionLog[1]).toBeInstanceOf(Error)
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('Monitoring action failed.', { error: true })
  })

  it('resets monitoring filters and retries after load errors', async () => {
    const monitoringApi = loadMonitoringModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(monitoringPayload))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = monitoringApi.createProjectMonitoringController(ctx)
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderMonitoring(container, 'prj_1')
    const severityFilter = container.querySelector('[data-project-monitoring-filter="severity"]')
    severityFilter.value = 'critical'
    controller.handleChange({ target: severityFilter, preventDefault: vi.fn(), stopPropagation: vi.fn() })
    expect(controller.stateFor('prj_1').filters).toEqual({ severity: 'critical' })

    const reset = container.querySelector('[data-project-monitoring-action="reset-filters"]')
    await controller.handleClick({ target: reset, preventDefault: vi.fn(), stopPropagation: vi.fn() })
    expect(controller.stateFor('prj_1').filters).toEqual({})
    expect(ctx.renderProjectExplorer).toHaveBeenCalled()

    let failLoad = true
    const retryRequest = vi.fn(async () => {
      if (failLoad) return apiResponse({ error: 'denied' }, { ok: false })
      return apiResponse(monitoringPayload)
    })
    const retryContext = makeContext(retryRequest)
    const retryController = monitoringApi.createProjectMonitoringController(retryContext)
    await retryController.load('prj_retry', { render: false })
    const retryContainer = document.createElement('div')
    retryController.renderMonitoring(retryContainer, 'prj_retry')
    const retry = retryContainer.querySelector('[data-project-monitoring-action="retry"]')
    expect(retry).not.toBeNull()

    failLoad = false
    await retryController.handleClick({ target: retry, preventDefault: vi.fn(), stopPropagation: vi.fn() })
    expect(retryController.stateFor('prj_retry').loaded).toBe(true)
    expect(retryController.stateFor('prj_retry').error).toBe('')
  })

  it('updates monitoring fire triage state with the row note', async () => {
    const monitoringApi = loadMonitoringModule()
    let rejectAck = false
    const projectWorkspaceRequest = vi.fn(async (url) => {
      if (String(url).includes('/monitoring/fires/')) {
        if (rejectAck) return apiResponse({ error: 'nope' }, { ok: false })
        return apiResponse({ ok: true, fire: { id: 'wtf_1', ack_state: 'expected' } })
      }
      return apiResponse(monitoringPayload)
    })
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = monitoringApi.createProjectMonitoringController(ctx)
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderMonitoring(container, 'prj_1')

    const note = container.querySelector('[data-project-monitoring-note="wtf_1"]')
    note.value = 'Maintenance window'
    const expected = [...container.querySelectorAll('[data-project-monitoring-action="ack"]')]
      .find(button => button.dataset.fireId === 'wtf_1' && button.dataset.ackState === 'expected')
    await controller.handleClick({ target: expected, preventDefault: vi.fn(), stopPropagation: vi.fn() })

    expect(projectWorkspaceRequest).toHaveBeenCalledWith(
      '/projects/prj_1/monitoring/fires/wtf_1',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ ack_state: 'expected', ack_note: 'Maintenance window' }),
      }),
    )
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('Monitoring event updated.')

    rejectAck = true
    await controller.handleClick({ target: expected, preventDefault: vi.fn(), stopPropagation: vi.fn() })
    const actionLog = ctx.logClientError.mock.calls.at(-1)
    expect(actionLog[0]).toContain('PROJECT_MONITORING_CLIENT_ACTION_FAILED')
    expect(actionLog[0]).toContain('"phase":"ack"')
    expect(actionLog[0]).toContain('"selection_key":"project:prj_1"')
    expect(actionLog[0]).toContain('"fire_id":"wtf_1"')
    expect(actionLog[0]).toContain('"ack_state":"expected"')
    expect(actionLog[0]).toContain('"note_chars":18')
    expect(actionLog[0]).not.toContain('Maintenance window')
    expect(actionLog[1]).toBeInstanceOf(Error)

    const loadErrorRequest = vi.fn(async () => apiResponse({ error: 'denied' }, { ok: false }))
    const loadErrorContext = makeContext(loadErrorRequest)
    const loadErrorController = monitoringApi.createProjectMonitoringController(loadErrorContext)
    await loadErrorController.load('prj_denied', { render: false })
    const loadLog = loadErrorContext.logClientError.mock.calls.at(-1)
    expect(loadLog[0]).toContain('PROJECT_MONITORING_CLIENT_LOAD_FAILED')
    expect(loadLog[0]).toContain('"phase":"load"')
    expect(loadLog[0]).toContain('"selection_key":"project:prj_denied"')
    expect(loadLog[0]).toContain('"page":"project_monitoring"')
    expect(loadLog[1]).toBeInstanceOf(Error)
  })
})
