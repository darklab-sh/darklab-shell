// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryStorage, fromDomScripts } from './helpers/extract.js'

const ENTITY = {
  id: 'ent_ip',
  type: 'ip',
  canonical_value: '107.178.109.44',
  occurrence_count: 2,
  run_count: 1,
  project_link_count: 0,
  project_links: [],
  labels: [{ label: 'edge' }],
  note: null,
  first_seen_at: '2026-05-15T00:00:00Z',
  last_seen_at: '2026-05-15T00:01:00Z',
}

const PORT_ENTITY = {
  id: 'ent_port',
  type: 'port',
  canonical_value: 'example.com:443/tcp',
  host_entity_id: 'ent_domain',
  attributes: { service: 'https', version: 'nginx' },
  occurrence_count: 1,
  run_count: 1,
  project_link_count: 0,
  project_links: [],
  labels: [{ label: 'service' }],
  note: null,
  first_seen_at: '2026-05-15T00:00:00Z',
  last_seen_at: '2026-05-15T00:01:00Z',
}

const URL_ENTITY = {
  id: 'ent_url',
  type: 'url',
  canonical_value: 'https://107.178.109.44/login',
  host_entity_id: 'ent_ip',
  occurrence_count: 1,
  run_count: 1,
  project_link_count: 0,
  project_links: [],
  labels: [],
  note: null,
  first_seen_at: '2026-05-15T00:03:00Z',
  last_seen_at: '2026-05-15T00:03:00Z',
}

const FINDING = {
  id: 'fnd_1',
  title: '443/tcp open https',
  raw_line: '443/tcp open https',
  review_state: 'new',
  status: 'new',
  severity: 'medium',
  tool_root: 'nmap',
  entity_id: 'ent_ip',
  entity_type: 'ip',
  entity_value: '107.178.109.44',
  run_id: 'run1',
  run_command: 'nmap 107.178.109.44',
  occurrence_count: 1,
  last_seen_at: '2026-05-15T00:01:00Z',
}

const RELATED_URL_FINDING = {
  ...FINDING,
  id: 'fnd_url_1',
  title: 'Login page exposes a critical issue',
  raw_line: 'critical issue on /login',
  severity: 'critical',
  entity_id: URL_ENTITY.id,
  entity_type: URL_ENTITY.type,
  entity_value: URL_ENTITY.canonical_value,
}

function findingRollup(overrides = {}) {
  return {
    applicable: true,
    total: 0,
    all_total: 0,
    suppressed: 0,
    occurrence_count: 0,
    latest_activity_at: '',
    by_severity: { critical: 0, high: 0, medium: 0, low: 0, info: 0, unknown: 0 },
    by_review_state: { new: 0, needs_followup: 0, important: 0, reviewed: 0, false_positive: 0 },
    by_verification_state: {
      not_started: 0,
      ready_to_verify: 0,
      verified: 0,
      needs_retest: 0,
      not_applicable: 0,
    },
    by_suppression: { visible: 0, suppressed: 0 },
    sample: [],
    navigation_hint: {},
    ...overrides,
  }
}

function lookupDetail(entity = ENTITY) {
  return {
    entity,
    parent_host: null,
    runs: [{ run_id: 'run1', command: `nmap ${entity.canonical_value}`, occurrence_count: 1 }],
    related_urls: [],
    related_ports: [],
    import_sources: [],
    findings: [FINDING],
    intel_snapshots: [],
    intel_summary: { status: 'empty', providers_with_data: [], highlights: [] },
    finding_summary: {
      direct: findingRollup({ total: 1, all_total: 1, occurrence_count: 1, sample: [FINDING] }),
      related_urls: findingRollup(),
      related_ports: findingRollup(),
      combined: findingRollup({ total: 1, all_total: 1, occurrence_count: 1, sample: [FINDING] }),
    },
    detail_limits: {
      runs: { limit: 50, offset: 0, shown: 1, total: 1, has_more: false },
      findings: { bucket: 'direct', limit: 50, offset: 0, shown: 1, total: 1, has_more: false },
      related_urls: { limit: 25, offset: 0, shown: 0, total: 0, has_more: false },
      related_ports: { limit: 25, offset: 0, shown: 0, total: 0, has_more: false },
    },
  }
}

function jsonResponse(data) {
  return {
    ok: true,
    status: 200,
    json: () => Promise.resolve(data),
  }
}

function errorResponse(status, data) {
  return {
    ok: false,
    status,
    json: () => Promise.resolve(data),
  }
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })
  return { promise, resolve, reject }
}

async function flushPromises(count = 8) {
  for (let index = 0; index < count; index += 1) {
    await Promise.resolve()
  }
}

function setupAtlasDom() {
  document.body.innerHTML = `
    <input id="cmd" />
    <div id="atlas-overlay" class="mobile-sheet-overlay u-hidden" aria-hidden="true">
      <section id="atlas-surface" class="atlas-surface mobile-sheet-surface">
        <button type="button" class="atlas-close">close</button>
        <div id="atlas-subtitle"></div>
        <div id="atlas-tabs" class="atlas-tabs tab-strip"></div>
        <section id="atlas-quick-lookup" class="u-hidden">
          <div id="atlas-lookup-form-view">
            <form id="atlas-lookup-form">
              <input id="atlas-lookup-input" />
              <select id="atlas-lookup-mode">
                <option value="auto">Auto</option>
                <option value="hostname">Hostname</option>
                <option value="ip">IP</option>
                <option value="url">URL</option>
              </select>
              <span id="atlas-lookup-scope"></span>
              <button type="submit">look up</button>
              <span id="atlas-lookup-status" class="u-hidden"></span>
              <button id="atlas-lookup-resume" class="u-hidden" type="button">resume</button>
            </form>
          </div>
          <div id="atlas-lookup-outcome-view" class="u-hidden">
            <span id="atlas-lookup-outcome-title"></span>
            <p id="atlas-lookup-outcome-body"></p>
            <div id="atlas-lookup-outcome-context" class="u-hidden"></div>
            <div id="atlas-lookup-outcome-candidates" class="u-hidden"></div>
            <div id="atlas-lookup-outcome-actions">
              <button id="atlas-lookup-outcome-new" class="btn btn-primary btn-compact" type="button">new lookup</button>
            </div>
          </div>
          <div id="atlas-lookup-profile-view" class="u-hidden">
            <button id="atlas-lookup-profile-new" type="button">new lookup</button>
            <button id="atlas-lookup-open-atlas" type="button">open atlas</button>
            <span id="atlas-lookup-profile-scope"></span>
            <div id="atlas-lookup-profile"></div>
          </div>
        </section>
        <input id="atlas-search" />
        <input id="atlas-run-filter-search" />
        <select id="atlas-run-filter-select" class="form-select form-control-compact"></select>
        <div id="atlas-run-filter-chip" class="atlas-run-filter-chip u-hidden"></div>
        <select id="atlas-project-filter-select" class="form-select form-control-compact"></select>
        <div id="atlas-project-filter-chip" class="atlas-project-filter-chip u-hidden"></div>
        <select id="atlas-finding-status-filter" class="form-select form-control-compact u-hidden"></select>
        <select id="atlas-orphan-filter" class="form-select form-control-compact"></select>
        <select id="atlas-suppression-filter" class="form-select form-control-compact"></select>
        <div class="atlas-saved-view-select-cell">
          <select id="atlas-saved-view-select" class="form-select form-control-compact atlas-saved-view-select"></select>
        </div>
        <button id="atlas-saved-view-save" type="button">save</button>
        <button id="atlas-saved-view-update" type="button">update</button>
        <button id="atlas-saved-view-delete" type="button">delete</button>
        <button id="atlas-saved-view-create-rule" type="button">create rule</button>
        <div id="atlas-export-wrap" class="atlas-export-wrap save-menu-wrap save-menu-down">
          <button id="atlas-export-menu-btn" type="button" aria-expanded="false">export</button>
          <div id="atlas-export-menu" class="atlas-export-menu save-menu dropdown-surface">
            <button id="atlas-export-csv-btn" type="button">csv</button>
            <button id="atlas-export-jsonl-btn" type="button">jsonl</button>
          </div>
        </div>
        <button id="atlas-import-btn" type="button">import</button>
        <button id="atlas-refresh-btn" type="button">refresh</button>
        <button id="atlas-findings-board-btn" type="button">board</button>
        <button id="atlas-clear-filters-btn" type="button">clear filters</button>
        <div class="atlas-shell">
          <div id="atlas-finding-bulk-row" class="u-hidden">
            <div class="atlas-bulk-action-row">
              <div class="atlas-bulk-selection-controls">
                <label><input id="atlas-select-toggle" type="checkbox">select</label>
                <button id="atlas-finding-select-all" type="button">select all</button>
                <button id="atlas-finding-clear-selection" type="button">clear</button>
                <span id="atlas-finding-selection-summary"></span>
              </div>
              <div class="atlas-bulk-mutation-controls">
                <select id="atlas-finding-bulk-status" class="form-select form-control-compact"></select>
                <button id="atlas-finding-bulk-apply" type="button">apply</button>
                <button id="atlas-bulk-suppression" type="button">suppress</button>
                <button id="atlas-bulk-delete" type="button">delete</button>
              </div>
            </div>
          </div>
          <div id="atlas-list"></div>
          <div id="atlas-pagination" class="u-hidden">
            <span id="atlas-pagination-summary"></span>
            <button id="atlas-prev-btn" type="button">previous</button>
            <button id="atlas-next-btn" type="button">next</button>
          </div>
          <aside id="atlas-detail"></aside>
          <div id="atlas-mobile-root" class="u-hidden">
            <div id="atlas-mobile-list-view"></div>
            <div id="atlas-mobile-entity-view"></div>
            <div id="atlas-mobile-finding-view"></div>
            <div id="atlas-mobile-tabs"></div>
            <div id="atlas-mobile-tools"></div>
            <div id="atlas-mobile-bulk-bar"></div>
            <div id="atlas-mobile-list"></div>
            <div id="atlas-mobile-pagination"></div>
            <div id="atlas-mobile-entity-topbar"></div>
            <div id="atlas-mobile-entity-body"></div>
            <div id="atlas-mobile-entity-footer"></div>
            <div id="atlas-mobile-finding-topbar"></div>
            <div id="atlas-mobile-finding-body"></div>
            <div id="atlas-mobile-finding-footer"></div>
          </div>
        </div>
        <div id="atlas-import-overlay" class="modal-overlay mobile-sheet-overlay atlas-import-overlay u-hidden" aria-hidden="true">
          <form id="atlas-import-modal" class="modal-card mobile-sheet-surface atlas-import-modal" tabindex="-1">
            <button id="atlas-import-close" type="button">close import</button>
            <select id="atlas-import-format">
              <option value="nuclei_jsonl">Nuclei JSONL</option>
              <option value="nessus_xml">Nessus XML</option>
            </select>
            <input id="atlas-import-name" />
            <input id="atlas-import-file" type="file" />
            <button id="atlas-import-preview-btn" type="submit">preview</button>
            <span id="atlas-import-status"></span>
            <section id="atlas-import-preview" class="u-hidden"></section>
            <button id="atlas-import-cancel" type="button">cancel</button>
            <button id="atlas-import-apply" type="button">apply</button>
          </form>
        </div>
        <div id="finding-triage-overlay" class="modal-overlay mobile-sheet-overlay finding-triage-overlay u-hidden" aria-hidden="true">
          <div id="finding-triage-modal" class="modal-card modal-card-compact mobile-sheet-surface finding-triage-modal">
            <button type="button" id="finding-triage-close"></button>
            <div id="finding-triage-subtitle"></div>
            <div id="finding-triage-message" class="u-hidden"></div>
            <form id="finding-triage-form">
              <textarea id="finding-triage-remediation"></textarea>
              <textarea id="finding-triage-verification-steps"></textarea>
              <select id="finding-triage-status" class="form-select form-control-compact">
                <option value="not_started">Not started</option>
                <option value="ready_to_verify">Ready to verify</option>
                <option value="verified">Verified</option>
                <option value="needs_retest">Needs retest</option>
                <option value="not_applicable">Not applicable</option>
              </select>
              <textarea id="finding-triage-verification-notes"></textarea>
              <button type="button" id="finding-triage-cancel"></button>
              <button type="submit" id="finding-triage-save"></button>
            </form>
          </div>
        </div>
      </section>
    </div>
  `
}

function loadAtlas({
  activeProject = null,
  apiFetchImpl = null,
  apiFetchInterceptor = null,
  showConfirmImpl = vi.fn(() => Promise.resolve('cancel')),
  openProjectAutoPromoteRuleFromAtlasImpl = vi.fn(() => Promise.resolve(true)),
  openProjectWorkspaceByIdImpl = vi.fn(() => Promise.resolve(true)),
  closeMajorOverlaysImpl = vi.fn(),
  useRealSelectEnhancer = false,
  activeTeamScopeCanImpl = () => true,
  teamScopeDeniedMessageImpl = action => `View-only team members can't ${action}. Switch to Personal or ask for operator access.`,
} = {}) {
  const showToast = vi.fn()
  const logClientError = vi.fn()
  const syncAppSelect = vi.fn()
  const enhanceAppSelects = vi.fn()
  const downloadBlobAsAttachment = vi.fn()
  const copyTextToClipboard = vi.fn(() => Promise.resolve(true))
  const setComposerValue = vi.fn((value) => {
    const input = document.getElementById('cmd')
    if (input) input.value = String(value || '')
  })
  const storage = new MemoryStorage()
  const projectEvents = []
  const apiFetch = apiFetchImpl || vi.fn((url, options = {}) => {
    const target = String(url)
    if (typeof apiFetchInterceptor === 'function') {
      const intercepted = apiFetchInterceptor(url, options)
      if (intercepted) return intercepted
    }
    if (target === '/atlas' || target.startsWith('/atlas?')) {
      return Promise.resolve(jsonResponse({
        total: 1,
        counts: { ip: 1, domain: 0, hash: 0, cve: 0, url: 0 },
        findings: 1,
      }))
    }
    if (target === '/atlas/views') {
      return Promise.resolve(jsonResponse({ views: [] }))
    }
    if (target.startsWith('/atlas/runs?')) {
      return Promise.resolve(jsonResponse({
        runs: [{
          id: 'run1',
          run_id: 'run1',
          command: 'nmap 107.178.109.44',
          entity_count: 1,
          finding_count: 1,
        }],
        limit: 30,
      }))
    }
    if (target.startsWith('/projects?')) {
      return Promise.resolve(jsonResponse({
        projects: [
          { id: 'prj_1', name: 'Case Alpha', slug: 'case-alpha', status: 'active' },
          { id: 'prj_2', name: 'Case Beta', slug: 'case-beta', status: 'active' },
        ],
        limit: 30,
      }))
    }
    if (target.startsWith('/atlas/findings?')) {
      return Promise.resolve(jsonResponse({
        findings: [FINDING],
        total: 1,
        limit: 50,
        offset: 0,
        counts: { new: 1, reviewed: 0, important: 0, false_positive: 0, needs_followup: 0 },
      }))
    }
    if (target === '/findings/fnd_1/review' && options.method === 'PUT') {
      return Promise.resolve(jsonResponse({ ok: true, finding: { ...FINDING, review_state: 'reviewed', status: 'reviewed' } }))
    }
    if (target === '/findings/fnd_1/triage' && !options.method) {
      return Promise.resolve(jsonResponse({
        triage: {
          remediation: 'Retest the exposed service.',
          verification_steps: '',
          verification_status: 'not_started',
          verification_notes: '',
        },
      }))
    }
    if (target === '/findings/fnd_1/triage' && options.method === 'PUT') {
      const payload = JSON.parse(options.body)
      return Promise.resolve(jsonResponse({ ok: true, triage: payload }))
    }
    if (target === '/atlas/findings/review' && options.method === 'POST') {
      return Promise.resolve(jsonResponse({ ok: true, counts: { updated: 1, not_found: 0 }, results: [] }))
    }
    if (target === '/atlas/findings/suppression' && options.method === 'POST') {
      return Promise.resolve(jsonResponse({ ok: true, suppressed: true, counts: { updated: 1, not_found: 0 }, results: [] }))
    }
    if (target === '/atlas/findings/fnd_1/suppression' && options.method === 'PUT') {
      return Promise.resolve(jsonResponse({ ok: true, finding_id: 'fnd_1', suppressed: true }))
    }
    if (target === '/atlas/entities/ent_ip/suppression' && options.method === 'PUT') {
      return Promise.resolve(jsonResponse({ ok: true, entity_id: 'ent_ip', suppressed: true }))
    }
    if (target.startsWith('/atlas/entities?')) {
      if (target.includes('type=port')) {
        return Promise.resolve(jsonResponse({
          entities: [PORT_ENTITY],
          total: 1,
          limit: 50,
          offset: 0,
        }))
      }
      if (target.includes('type=url')) {
        return Promise.resolve(jsonResponse({
          entities: [URL_ENTITY],
          total: 1,
          limit: 50,
          offset: 0,
        }))
      }
      return Promise.resolve(jsonResponse({
        entities: [ENTITY],
        total: 1,
        limit: 50,
        offset: 0,
      }))
    }
    if (target.startsWith('/atlas/entities/export?')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        headers: { get: () => 'attachment; filename=darklab-atlas-entities.csv' },
        blob: () => Promise.resolve(new Blob(['id,type\nent_ip,ip\n'], { type: 'text/csv' })),
      })
    }
    if (target === '/atlas/imports/preview' && options.method === 'POST') {
      return Promise.resolve(jsonResponse({
        ok: true,
        draft_id: 'impd_1',
        row_set_digest: 'digest_1',
        counts: {
          rows: 2,
          entity_valid: 1,
          finding_valid: 1,
          new: 2,
          updated: 0,
          warnings: 1,
          project_target_candidates: 1,
        },
        samples: {
          entities: [{ kind: 'domain', canonical_value: 'example.com' }],
          findings: [{ severity: 'high', title: 'Missing security header' }],
        },
        warnings: [{ row_number: 2, code: 'missing_field', message: 'Skipped empty value' }],
        apply_options: {
          import_entities: { available: true, requires: ['mutate_projects'] },
          import_findings: { available: true, requires: ['triage_findings'] },
          link_to_project: { available: true, requires: ['mutate_projects'] },
          create_project_targets: { available: true, requires: ['mutate_projects'] },
        },
      }))
    }
    if (target === '/atlas/imports/apply' && options.method === 'POST') {
      return Promise.resolve(jsonResponse({
        ok: true,
        batch_id: 'impb_1',
        counts: {
          entities_created: 1,
          entities_updated: 0,
          findings_created: 1,
          findings_updated: 0,
          project_links_added: 1,
          project_links_existing: 0,
          project_targets_created: 1,
          project_targets_existing: 0,
        },
      }))
    }
    if (target === '/atlas/entities/ent_ip' || target.startsWith('/atlas/entities/ent_ip?')) {
      const params = new URL(target, 'https://example.test').searchParams
      const relatedUrlsOffset = Number(params.get('related_urls_offset') || 0)
      const relatedPortsOffset = Number(params.get('related_ports_offset') || 0)
      const projectId = String(params.get('project_id') || '')
      const findingBucket = String(params.get('finding_bucket') || 'direct')
      const bucketFindings = {
        direct: [FINDING],
        related_urls: [RELATED_URL_FINDING],
        related_ports: [],
        combined: [FINDING, RELATED_URL_FINDING],
      }[findingBucket] || [FINDING]
      return Promise.resolve(jsonResponse({
        entity: {
          ...ENTITY,
          project_link_count: 1,
          project_links: [{ project_id: 'prj_linked', project_name: 'Linked Case' }],
        },
        import_sources: [{
          batch_id: 'impb_1',
          source_tool: 'Nuclei JSONL',
          import_name: 'Nuclei JSONL',
          occurrence_count: 1,
          created_record: true,
          last_observed_at: '2026-05-15T00:03:00Z',
        }],
        intel_snapshots: [{
          provider: 'Shodan',
          status: 'ok',
          summary: '2 open ports',
          data: {
            providers: {
              shodan: {
                ports: [80, 443],
                hostnames: ['edge.darklab.sh'],
                cves: ['CVE-2026-0001'],
                services: [
                  { port: 443, transport: 'tcp', product: 'nginx' },
                ],
              },
            },
          },
          fetched_at: '2026-05-15T00:02:00Z',
        }],
        intel_summary: {
          status: 'available',
          freshness: 'stale',
          snapshot_count: 1,
          provider_count: 1,
          providers_with_data: ['shodan'],
          highlight_count: 3,
          highlights: [
            {
              label: 'Open ports',
              value: '80, 443',
              provider: 'shodan',
              provider_label: 'Shodan',
              tone: 'neutral',
            },
            {
              label: 'CVEs',
              value: 'CVE-2026-0001',
              provider: 'shodan',
              provider_label: 'Shodan',
              tone: 'warning',
            },
            {
              label: 'ASN',
              value: 'AS15169 Google LLC',
              provider: 'censys',
              provider_label: 'Censys',
              tone: 'neutral',
            },
          ],
          last_refresh_at: '2026-05-15T00:02:00Z',
          updated_at: '2026-05-15T00:02:00Z',
        },
        overview: {
          observed: {
            state: 'observed',
            source_run_count: 55,
            occurrence_count: 2,
            first_seen_at: '2026-05-15T00:00:00Z',
            last_seen_at: '2026-05-15T00:02:00Z',
            app_ports: [{
              port: 443,
              proto: 'tcp',
              service: 'https',
              version: 'nginx',
              banner_available: true,
              banner: 'nginx TLS listener',
              occurrence_count: 4,
              last_seen_at: '2026-05-15T00:02:00Z',
              source_run_count: 2,
            }],
            app_port_count: 1,
            app_ports_truncated: false,
            app_services: ['https (nginx)'],
            app_evidence: {
              applicable: true,
              coverage_state: 'app_ports_found',
              scan_run_count: 3,
              last_observed_at: '2026-05-15T00:02:00Z',
              port_entity_count: 2,
              app_port_count: 2,
              app_port_run_count: 2,
              project_entity_port_count: 1,
              command_roots: ['nmap', 'naabu'],
              host_entity_id: '',
              scope_note: '',
              coverage_caveat: '',
            },
            project_monitoring: projectId ? {
              applicable: true,
              project_id: projectId,
              project_name: 'Linked Case',
              state: 'changed',
              watcher_count: 1,
              counts: { active: 0, changed: 1, failed: 0, quiet: 0, paused: 0 },
              latest_change_at: '2026-05-15T00:02:00Z',
              recent_changes: [{
                fire_id: 'fire_1',
                watcher_id: 'watcher_1',
                watcher_label: 'Watch edge ports',
                fire_kind: 'changed',
                created: '2026-05-15T00:02:00Z',
                severity: 'high',
                classifier: 'ports',
                label: 'New open port 80/tcp',
              }],
              links: { project_monitoring: `/projects/${projectId}/monitoring` },
            } : {
              applicable: false,
              project_id: '',
              project_name: '',
              state: 'not_applicable',
              watcher_count: 0,
              counts: { active: 0, changed: 0, failed: 0, quiet: 0, paused: 0 },
              latest_change_at: '',
              recent_changes: [],
              links: {},
            },
          },
          intel: {
            status: 'available',
            freshness: 'stale',
            snapshot_count: 1,
            provider_count: 1,
            providers_with_data: ['shodan'],
            last_refresh_at: '2026-05-15T00:02:00Z',
            highlight_count: 3,
            highlights: [
              {
                label: 'Open ports',
                value: '80, 443',
                provider: 'shodan',
                provider_label: 'Shodan',
                tone: 'neutral',
              },
              {
                label: 'CVEs',
                value: 'CVE-2026-0001',
                provider: 'shodan',
                provider_label: 'Shodan',
                tone: 'warning',
              },
              {
                label: 'ASN',
                value: 'AS15169 Google LLC',
                provider: 'censys',
                provider_label: 'Censys',
                tone: 'neutral',
              },
            ],
            provider_ports: [80, 443],
            provider_services: ['http', 'https'],
            certificate: {
              status: 'healthy',
              expires_at: '2026-12-01T00:00:00Z',
              days_until_expiry: 200,
              last_checked_at: '2026-05-15T00:02:00Z',
            },
            port_provenance: {
              app: [{ port: 443, proto: 'tcp' }],
              provider: [80, 443],
              divergence: { app_only: [], provider_only: [80], has_drift: true },
            },
            summary: {},
          },
        },
        runs: [{
          run_id: 'run1',
          command: 'shodan host 107.178.109.44',
          occurrence_count: 2,
          last_seen_at: '2026-05-15T00:01:00Z',
        }],
        related_urls: [URL_ENTITY],
        related_ports: [{ ...PORT_ENTITY, host_entity_id: ENTITY.id }],
        findings: bucketFindings,
        finding_summary: {
          direct: findingRollup({
            total: 1,
            all_total: 1,
            occurrence_count: 1,
            by_severity: { critical: 0, high: 0, medium: 1, low: 0, info: 0, unknown: 0 },
            by_review_state: { new: 1, needs_followup: 0, important: 0, reviewed: 0, false_positive: 0 },
            by_verification_state: {
              not_started: 1,
              ready_to_verify: 0,
              verified: 0,
              needs_retest: 0,
              not_applicable: 0,
            },
            by_suppression: { visible: 1, suppressed: 0 },
            sample: [FINDING],
          }),
          related_urls: findingRollup({
            total: 1,
            all_total: 1,
            occurrence_count: 1,
            by_severity: { critical: 1, high: 0, medium: 0, low: 0, info: 0, unknown: 0 },
            by_suppression: { visible: 1, suppressed: 0 },
          }),
          related_ports: findingRollup(),
          combined: findingRollup({
            total: 2,
            all_total: 2,
            occurrence_count: 2,
            by_severity: { critical: 1, high: 0, medium: 1, low: 0, info: 0, unknown: 0 },
            by_suppression: { visible: 2, suppressed: 0 },
          }),
        },
        detail_limits: {
          related_urls: {
            limit: 25,
            offset: relatedUrlsOffset,
            shown: 1,
            total: 26,
            has_more: relatedUrlsOffset === 0,
          },
          related_ports: {
            limit: 25,
            offset: relatedPortsOffset,
            shown: 1,
            total: 26,
            has_more: relatedPortsOffset === 0,
          },
          runs: { limit: 50, offset: 0, shown: 1, total: 55, has_more: true },
          findings: {
            bucket: findingBucket,
            limit: 50,
            offset: 0,
            shown: bucketFindings.length,
            total: bucketFindings.length,
            has_more: false,
          },
        },
      }))
    }
    if (target === '/atlas/entities/ent_url' || target.startsWith('/atlas/entities/ent_url?')) {
      return Promise.resolve(jsonResponse({
        entity: URL_ENTITY,
        parent_host: ENTITY,
        import_sources: [],
        intel_snapshots: [],
        intel_summary: { status: 'unsupported', providers_with_data: [], highlights: [] },
        overview: {
          observed: {
            app_ports: [{
              port: 443,
              proto: 'tcp',
              service: 'https',
              version: 'nginx',
              banner_available: false,
              occurrence_count: 4,
              last_seen_at: '2026-05-15T00:02:00Z',
              source_run_count: 2,
            }],
            app_port_count: 1,
            app_ports_truncated: false,
            app_services: ['https (nginx)'],
            app_evidence: {
              applicable: true,
              coverage_state: 'app_ports_found',
              scan_run_count: 3,
              last_observed_at: '2026-05-15T00:02:00Z',
              app_port_count: 1,
              command_roots: ['nmap'],
              host_entity_id: ENTITY.id,
              scope_note: 'App scan coverage and ports are tracked on the parent host, not this URL.',
            },
          },
        },
        runs: [{
          run_id: 'run-url',
          command: 'curl https://107.178.109.44/login',
          occurrence_count: 1,
          last_seen_at: '2026-05-15T00:03:00Z',
        }],
        related_urls: [],
        related_ports: [],
        findings: [],
        finding_summary: {
          direct: findingRollup(),
          related_urls: findingRollup({ applicable: false }),
          related_ports: findingRollup({ applicable: false }),
          combined: findingRollup({ applicable: false }),
        },
        detail_limits: {
          related_urls: { limit: 25, offset: 0, shown: 0, total: 0, has_more: false },
          related_ports: { limit: 25, offset: 0, shown: 0, total: 0, has_more: false },
          runs: { limit: 50, offset: 0, shown: 1, total: 1, has_more: false },
          findings: { limit: 50, offset: 0, shown: 0, total: 0, has_more: false },
        },
      }))
    }
    if (target === '/atlas/entities/ent_port' || target.startsWith('/atlas/entities/ent_port?')) {
      return Promise.resolve(jsonResponse({
        entity: PORT_ENTITY,
        parent_host: {
          ...ENTITY,
          id: 'ent_domain',
          type: 'domain',
          canonical_value: 'example.com',
        },
        import_sources: [],
        intel_snapshots: [],
        intel_summary: { status: 'unsupported', providers_with_data: [], highlights: [] },
        runs: [{
          run_id: 'run-port',
          command: 'nmap example.com',
          occurrence_count: 1,
          last_seen_at: '2026-05-15T00:01:00Z',
        }],
        findings: [{
          ...FINDING,
          entity_id: PORT_ENTITY.id,
          entity_type: PORT_ENTITY.type,
          entity_value: PORT_ENTITY.canonical_value,
        }],
        finding_summary: {
          direct: findingRollup({
            total: 1,
            all_total: 1,
            occurrence_count: 1,
            by_severity: { critical: 0, high: 0, medium: 1, low: 0, info: 0, unknown: 0 },
            sample: [FINDING],
          }),
          related_urls: findingRollup({ applicable: false }),
          related_ports: findingRollup({ applicable: false }),
          combined: findingRollup({ applicable: false }),
        },
        detail_limits: {
          runs: { limit: 50, offset: 0, shown: 1, total: 1, has_more: false },
          findings: { limit: 50, offset: 0, shown: 1, total: 1, has_more: false },
        },
      }))
    }
    if (target === '/atlas/entities/ent_ip/refresh_intel' && options.method === 'POST') {
      return Promise.resolve(jsonResponse({
        ok: true,
        refresh: { configured_count: 1, success_count: 1 },
      }))
    }
    if (target === '/atlas/entities/ent_ip/project_links' && options.method === 'POST') {
      return Promise.resolve(jsonResponse({ ok: true }))
    }
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: 'not found' }) })
  })

  const atlasFns = fromDomScripts(
      [
        'app/static/js/ui/ui_entity_metadata.js',
        'app/static/js/features/findings/finding_triage_editor.js',
        'app/static/js/features/atlas/atlas_bridge.js',
        'app/static/js/features/atlas/atlas_tabs.js',
        'app/static/js/features/atlas/atlas_entity_row.js',
        'app/static/js/features/atlas/atlas_entity_detail.js',
        'app/static/js/features/atlas/atlas_quick_lookup_mode.js',
        'app/static/js/features/findings/findings_board_bridge.js',
        'app/static/js/features/atlas/atlas_overlay.js',
        'app/static/js/features/atlas/atlas_mobile_bridge.js',
        'app/static/js/features/atlas/atlas_mobile.js',
      ],
      {
        document,
        window,
        apiFetch,
        fetch: apiFetch,
        showToast,
        logClientError,
        showConfirm: showConfirmImpl,
        syncAppSelect,
        enhanceAppSelects,
        useRealSelectEnhancer,
        localStorage: storage,
        URLSearchParams,
        setTimeout,
        clearTimeout,
        getActiveProjectContext: () => activeProject,
        refreshActiveProjectContext: vi.fn(() => Promise.resolve(activeProject)),
        emitUiEvent: (name, detail = {}) => {
          projectEvents.push({ name, detail })
          document.dispatchEvent(new CustomEvent(name, { detail }))
          return true
        },
        refocusComposerAfterAction: vi.fn(),
        setComposerValue,
        copyTextToClipboard,
        openProjectAutoPromoteRuleFromAtlas: openProjectAutoPromoteRuleFromAtlasImpl,
        openProjectWorkspaceById: openProjectWorkspaceByIdImpl,
        closeMajorOverlays: closeMajorOverlaysImpl,
        downloadBlobAsAttachment,
        activeTeamScopeCan: activeTeamScopeCanImpl,
        teamScopeDeniedMessage: teamScopeDeniedMessageImpl,
      },
      `{
        apiFetch,
        showToast,
        logClientError,
        downloadBlobAsAttachment,
        DarklabAtlasOverlay: exportedDarklabAtlasOverlay,
        openAtlas: exportedOpenAtlas,
        openAtlasQuickLookup: exportedOpenAtlasQuickLookup,
        closeAtlas: exportedCloseAtlas,
        isAtlasOverlayOpen: exportedIsAtlasOverlayOpen,
        cycleAtlasTab: exportedCycleAtlasTab,
      }`,
      `
        window.apiFetch = apiFetch;
        window.showToast = showToast;
        window.logClientError = logClientError;
        window.showConfirm = showConfirm;
        if (!useRealSelectEnhancer) {
          window.syncAppSelect = syncAppSelect;
          window.enhanceAppSelects = enhanceAppSelects;
        }
        window.emitUiEvent = emitUiEvent;
        window.closeMajorOverlays = closeMajorOverlays;
        window.getActiveProjectContext = getActiveProjectContext;
        window.refreshActiveProjectContext = refreshActiveProjectContext;
        window.refocusComposerAfterAction = refocusComposerAfterAction;
        window.setComposerValue = setComposerValue;
        window.copyTextToClipboard = copyTextToClipboard;
        window.openProjectAutoPromoteRuleFromAtlas = openProjectAutoPromoteRuleFromAtlas;
        window.openProjectWorkspaceById = openProjectWorkspaceById;
        window.downloadBlobAsAttachment = downloadBlobAsAttachment;
        window.activeTeamScopeCan = activeTeamScopeCan;
        window.teamScopeDeniedMessage = teamScopeDeniedMessage;
      `,
    )
  Object.assign(window, {
    DarklabAtlasOverlay: atlasFns.DarklabAtlasOverlay,
    openAtlas: atlasFns.openAtlas,
    openAtlasQuickLookup: atlasFns.openAtlasQuickLookup,
    closeAtlas: atlasFns.closeAtlas,
    isAtlasOverlayOpen: atlasFns.isAtlasOverlayOpen,
    cycleAtlasTab: atlasFns.cycleAtlasTab,
  })

  return {
    ...atlasFns,
    apiFetch,
    showConfirm: showConfirmImpl,
    showToast,
    logClientError,
    openProjectAutoPromoteRuleFromAtlas: openProjectAutoPromoteRuleFromAtlasImpl,
    openProjectWorkspaceById: openProjectWorkspaceByIdImpl,
    closeMajorOverlays: closeMajorOverlaysImpl,
    syncAppSelect,
    enhanceAppSelects,
    downloadBlobAsAttachment,
    copyTextToClipboard,
    setComposerValue,
    projectEvents,
    storage,
  }
}

function setAtlasImportFile(contents = '{"template-id":"ssl/header"}\n', name = 'nuclei.jsonl', type = 'application/jsonl') {
  const fileInput = document.getElementById('atlas-import-file')
  Object.defineProperty(fileInput, 'files', {
    value: [new File([contents], name, { type })],
    configurable: true,
  })
  return fileInput
}

function submitAtlasImportPreview() {
  document.getElementById('atlas-import-modal')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
}

describe('Atlas overlay', () => {
  beforeEach(() => {
    setupAtlasDom()
  })

  it('opens Quick Lookup as an Atlas-owned mode without loading list data', async () => {
    const detail = lookupDetail()
    const { openAtlasQuickLookup, apiFetch, logClientError } = loadAtlas({
      apiFetchInterceptor: (url, options = {}) => {
        if (String(url) !== '/atlas/lookup') return null
        expect(options.method).toBe('POST')
        return Promise.resolve(jsonResponse({
          requested_type: 'auto',
          detected_type: 'ip',
          canonical_value: ENTITY.canonical_value,
          project_id: '',
          match_state: 'found',
          detail,
          candidates: [],
          candidates_truncated: false,
          parent_host_candidate: null,
        }))
      },
    })

    await openAtlasQuickLookup({ value: ENTITY.canonical_value, mode: 'auto', submit: true })
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-lookup-profile')?.textContent).toContain(ENTITY.canonical_value)
    })

    expect(document.getElementById('atlas-surface')?.classList.contains('is-atlas-lookup')).toBe(true)
    expect(document.getElementById('atlas-quick-lookup')?.classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('atlas-lookup-form-view')?.classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('atlas-lookup-profile-view')?.classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('atlas-lookup-profile')?.textContent).toContain('Overview')
    document.querySelector('#atlas-lookup-profile [data-atlas-profile-view="evidence"]')?.click()
    expect(document.getElementById('atlas-lookup-profile')?.textContent).toContain('Source runs')
    expect(document.querySelector(
      '#atlas-lookup-profile [data-atlas-profile-view="evidence"]',
    )?.getAttribute('aria-selected')).toBe('true')
    expect(document.getElementById('atlas-subtitle')?.textContent).toBe('Quick lookup · Personal')
    expect(apiFetch).toHaveBeenCalledWith('/atlas/lookup', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ mode: 'auto', value: ENTITY.canonical_value }),
    }))
    expect(apiFetch.mock.calls.some(([url]) => String(url).startsWith('/atlas?'))).toBe(false)
    expect(apiFetch.mock.calls.some(([url]) => String(url) === '/atlas/views')).toBe(false)
    expect(apiFetch.mock.calls.some(([url]) => String(url).startsWith('/atlas/runs?'))).toBe(false)
    expect(apiFetch.mock.calls.some(([url]) => String(url).startsWith('/projects?'))).toBe(false)
    const lifecycleEvents = logClientError.mock.calls
      .filter(([, , details]) => details?.level === 'debug')
    expect(lifecycleEvents.map(([, , details]) => details.event)).toEqual([
      'ATLAS_QUICK_LOOKUP_REQUEST_STARTED',
      'ATLAS_QUICK_LOOKUP_REQUEST_SETTLED',
    ])
    expect(lifecycleEvents[0][2]).toEqual(expect.objectContaining({
      lookup_mode: 'auto',
      scope_kind: 'personal',
      project_scoped: false,
      request_seq: expect.any(Number),
    }))
    expect(lifecycleEvents[1][2]).toEqual(expect.objectContaining({
      detected_type: 'ip',
      match_state: 'found',
      candidate_count: 0,
      parent_candidate: false,
      duration_ms: expect.any(Number),
    }))
    expect(JSON.stringify(lifecycleEvents)).not.toContain(ENTITY.canonical_value)

    document.getElementById('atlas-lookup-profile-new')?.click()
    expect(document.getElementById('atlas-lookup-form-view')?.classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('atlas-lookup-resume')?.classList.contains('u-hidden')).toBe(false)
    document.getElementById('atlas-lookup-resume')?.click()
    expect(document.getElementById('atlas-lookup-profile-view')?.classList.contains('u-hidden')).toBe(false)
  })

  it('closes Quick Lookup when a shell entry point triggers the active surface again', async () => {
    const detail = lookupDetail()
    const { openAtlasQuickLookup, apiFetch } = loadAtlas({
      apiFetchInterceptor: (url) => {
        if (String(url) !== '/atlas/lookup') return null
        return Promise.resolve(jsonResponse({
          requested_type: 'ip',
          detected_type: 'ip',
          canonical_value: ENTITY.canonical_value,
          project_id: '',
          match_state: 'found',
          detail,
          candidates: [],
          candidates_truncated: false,
          parent_host_candidate: null,
        }))
      },
    })

    await openAtlasQuickLookup({ value: ENTITY.canonical_value, mode: 'ip', submit: true })
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-lookup-profile')?.textContent)
        .toContain(ENTITY.canonical_value)
    })

    const result = await openAtlasQuickLookup({ source: 'shortcut', toggle: true })

    expect(result).toBe(false)
    expect(document.getElementById('atlas-overlay')?.classList.contains('open')).toBe(false)
    expect(apiFetch.mock.calls.filter(([url]) => String(url) === '/atlas/lookup')).toHaveLength(1)
  })

  it('validates lookup input locally and lets a corrected request retry in place', async () => {
    let lookupCalls = 0
    const { openAtlasQuickLookup, apiFetch, logClientError } = loadAtlas({
      apiFetchInterceptor: (url) => {
        if (String(url) !== '/atlas/lookup') return null
        lookupCalls += 1
        if (lookupCalls === 1) {
          return Promise.resolve(errorResponse(400, {
            error: 'invalid_lookup_value',
            message: 'Enter a valid hostname without a URL path.',
          }))
        }
        return Promise.resolve(jsonResponse({
          requested_type: 'hostname',
          detected_type: 'domain',
          canonical_value: 'corrected.example',
          project_id: '',
          match_state: 'found',
          detail: lookupDetail({
            ...ENTITY,
            id: 'ent_corrected',
            type: 'domain',
            canonical_value: 'corrected.example',
          }),
          candidates: [],
          candidates_truncated: false,
          parent_host_candidate: null,
        }))
      },
    })

    await openAtlasQuickLookup()
    document.getElementById('atlas-lookup-form')?.dispatchEvent(
      new Event('submit', { bubbles: true, cancelable: true }),
    )
    expect(document.getElementById('atlas-lookup-status')?.textContent)
      .toContain('Enter a hostname, IP address, or absolute HTTP(S) URL')
    expect(apiFetch.mock.calls.some(([url]) => String(url) === '/atlas/lookup')).toBe(false)

    const input = document.getElementById('atlas-lookup-input')
    input.value = 'invalid.example/path'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    document.getElementById('atlas-lookup-mode').value = 'hostname'
    document.getElementById('atlas-lookup-form')?.dispatchEvent(
      new Event('submit', { bubbles: true, cancelable: true }),
    )
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-lookup-status')?.textContent)
        .toContain('Enter a valid hostname without a URL path')
    })
    expect(logClientError.mock.calls.some(([, , details]) => details?.level !== 'debug')).toBe(false)

    input.value = 'corrected.example'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    document.getElementById('atlas-lookup-form')?.dispatchEvent(
      new Event('submit', { bubbles: true, cancelable: true }),
    )
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-lookup-profile')?.textContent)
        .toContain('corrected.example')
    })
    expect(lookupCalls).toBe(2)
  })

  it('resumes the previous profile after replacement failure and ignores stale failures', async () => {
    const replacementFailure = deferred()
    const staleFailure = deferred()
    const detailFor = (canonicalValue, id) => lookupDetail({
      ...ENTITY,
      id,
      type: 'domain',
      canonical_value: canonicalValue,
    })
    const { openAtlasQuickLookup } = loadAtlas({
      apiFetchInterceptor: (url, options = {}) => {
        if (String(url) !== '/atlas/lookup') return null
        const value = String(JSON.parse(options.body || '{}').value || '')
        if (value === 'replacement-failure.example') return replacementFailure.promise
        if (value === 'stale-failure.example') return staleFailure.promise
        return Promise.resolve(jsonResponse({
          requested_type: 'hostname',
          detected_type: 'domain',
          canonical_value: value,
          project_id: '',
          match_state: 'found',
          detail: detailFor(value, `ent_${value.split('.')[0]}`),
          candidates: [],
          candidates_truncated: false,
          parent_host_candidate: null,
        }))
      },
    })

    await openAtlasQuickLookup({
      value: 'original-profile.example',
      mode: 'hostname',
      submit: true,
    })
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-lookup-profile')?.textContent)
        .toContain('original-profile.example')
    })

    document.getElementById('atlas-lookup-profile-new')?.click()
    const input = document.getElementById('atlas-lookup-input')
    input.value = 'replacement-failure.example'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    document.getElementById('atlas-lookup-mode').value = 'hostname'
    document.getElementById('atlas-lookup-form')?.dispatchEvent(
      new Event('submit', { bubbles: true, cancelable: true }),
    )
    replacementFailure.reject(new Error('temporary replacement failure'))
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-lookup-status')?.textContent)
        .toContain('temporary replacement failure')
      expect(document.getElementById('atlas-lookup-resume')?.classList.contains('u-hidden'))
        .toBe(false)
    })
    document.getElementById('atlas-lookup-resume')?.click()
    expect(document.getElementById('atlas-lookup-profile')?.textContent)
      .toContain('original-profile.example')

    document.getElementById('atlas-lookup-profile-new')?.click()
    const staleSubmission = openAtlasQuickLookup({
      value: 'stale-failure.example',
      mode: 'hostname',
      submit: true,
    })
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-lookup-status')?.textContent)
        .toContain('Looking for stale-failure.example')
    })
    await openAtlasQuickLookup({
      value: 'newer-success.example',
      mode: 'hostname',
      submit: true,
    })
    staleFailure.reject(new Error('late stale failure'))
    await staleSubmission

    expect(document.getElementById('atlas-lookup-profile')?.textContent)
      .toContain('newer-success.example')
    expect(document.getElementById('atlas-lookup-status')?.textContent)
      .not.toContain('late stale failure')
  })

  it('cancels an owner-scoped lookup and reruns it when the active scope changes', async () => {
    const firstLookup = deferred()
    let firstSignal = null
    let lookupCalls = 0
    const detail = lookupDetail()
    const { openAtlasQuickLookup, apiFetch, logClientError } = loadAtlas({
      apiFetchInterceptor: (url, options = {}) => {
        if (String(url) !== '/atlas/lookup') return null
        lookupCalls += 1
        if (lookupCalls === 1) {
          firstSignal = options.signal
          return firstLookup.promise
        }
        return Promise.resolve(jsonResponse({
          requested_type: 'ip',
          detected_type: 'ip',
          canonical_value: ENTITY.canonical_value,
          project_id: '',
          match_state: 'found',
          detail,
          candidates: [],
          candidates_truncated: false,
          parent_host_candidate: null,
        }))
      },
    })

    const opening = openAtlasQuickLookup({ value: ENTITY.canonical_value, mode: 'ip', submit: true })
    await vi.waitFor(() => expect(firstSignal).not.toBeNull())
    document.dispatchEvent(new CustomEvent('app:scope-changed', {
      detail: { team_id: 'team_next', label: 'Next team' },
    }))

    await vi.waitFor(() => {
      expect(lookupCalls).toBe(2)
      expect(document.getElementById('atlas-lookup-profile')?.textContent)
        .toContain(ENTITY.canonical_value)
    })
    expect(firstSignal?.aborted).toBe(true)
    expect(apiFetch.mock.calls.filter(([url]) => String(url) === '/atlas/lookup')).toHaveLength(2)
    expect(apiFetch.mock.calls.some(([url]) => String(url).startsWith('/atlas?'))).toBe(false)
    expect(logClientError.mock.calls.some(([, , details]) => (
      details?.event === 'ATLAS_QUICK_LOOKUP_REQUEST_DISCARDED'
      && details?.reason === 'scope_changed'
    ))).toBe(true)

    firstLookup.resolve(jsonResponse({
      requested_type: 'ip',
      detected_type: 'ip',
      canonical_value: ENTITY.canonical_value,
      project_id: '',
      match_state: 'not_found',
      detail: null,
      candidates: [],
      candidates_truncated: false,
      parent_host_candidate: null,
    }))
    await opening
    expect(document.getElementById('atlas-lookup-profile')?.textContent)
      .toContain(ENTITY.canonical_value)
  })

  it('reruns the submitted lookup instead of an unsent draft when scope changes', async () => {
    const lookupBodies = []
    const detail = lookupDetail()
    const { openAtlasQuickLookup } = loadAtlas({
      apiFetchInterceptor: (url, options = {}) => {
        if (String(url) !== '/atlas/lookup') return null
        lookupBodies.push(JSON.parse(String(options.body || '{}')))
        return Promise.resolve(jsonResponse({
          requested_type: 'ip',
          detected_type: 'ip',
          canonical_value: ENTITY.canonical_value,
          project_id: '',
          match_state: 'found',
          detail,
          candidates: [],
          candidates_truncated: false,
          parent_host_candidate: null,
        }))
      },
    })

    await openAtlasQuickLookup({ value: ENTITY.canonical_value, mode: 'ip', submit: true })
    document.getElementById('atlas-lookup-profile-new')?.click()

    const input = document.getElementById('atlas-lookup-input')
    input.value = 'https://draft.example/path'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    const modeSelect = document.getElementById('atlas-lookup-mode')
    modeSelect.value = 'url'
    modeSelect.dispatchEvent(new Event('change', { bubbles: true }))

    document.dispatchEvent(new CustomEvent('app:scope-changed', {
      detail: { team_id: 'team_next', label: 'Next team' },
    }))

    await vi.waitFor(() => expect(lookupBodies).toHaveLength(2))
    expect(lookupBodies).toEqual([
      { mode: 'ip', value: ENTITY.canonical_value },
      { mode: 'ip', value: ENTITY.canonical_value },
    ])
    expect(input.value).toBe(ENTITY.canonical_value)
    expect(modeSelect.value).toBe('ip')
  })

  it('invalidates the previous profile before a scope rerun and cannot resume it after failure', async () => {
    const scopeLookup = deferred()
    let lookupCalls = 0
    const detail = lookupDetail()
    const { openAtlasQuickLookup } = loadAtlas({
      apiFetchInterceptor: (url) => {
        if (String(url) !== '/atlas/lookup') return null
        lookupCalls += 1
        if (lookupCalls === 2) return scopeLookup.promise
        return Promise.resolve(jsonResponse({
          requested_type: 'ip',
          detected_type: 'ip',
          canonical_value: ENTITY.canonical_value,
          project_id: '',
          match_state: 'found',
          detail,
          candidates: [],
          candidates_truncated: false,
          parent_host_candidate: null,
        }))
      },
    })

    await openAtlasQuickLookup({ value: ENTITY.canonical_value, mode: 'ip', submit: true })
    const profileHost = document.getElementById('atlas-lookup-profile')
    const profileView = document.getElementById('atlas-lookup-profile-view')
    const formView = document.getElementById('atlas-lookup-form-view')
    const resumeButton = document.getElementById('atlas-lookup-resume')
    expect(profileHost.textContent).toContain(ENTITY.canonical_value)

    document.dispatchEvent(new CustomEvent('app:scope-changed', {
      detail: { team_id: 'team_next', label: 'Next team' },
    }))

    await vi.waitFor(() => expect(lookupCalls).toBe(2))
    expect(profileView.classList.contains('u-hidden')).toBe(true)
    expect(formView.classList.contains('u-hidden')).toBe(false)
    expect(profileHost.textContent).toBe('')
    expect(document.getElementById('atlas-lookup-status')?.textContent)
      .toContain(`Looking for ${ENTITY.canonical_value}`)
    expect(resumeButton.classList.contains('u-hidden')).toBe(true)
    expect(resumeButton.disabled).toBe(true)

    scopeLookup.resolve(errorResponse(503, { message: 'The new scope could not be searched.' }))
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-lookup-status')?.textContent)
        .toContain('The new scope could not be searched.')
    })
    expect(profileHost.textContent).toBe('')
    expect(profileView.classList.contains('u-hidden')).toBe(true)
    expect(resumeButton.classList.contains('u-hidden')).toBe(true)
    expect(resumeButton.disabled).toBe(true)
  })

  it('carries a project-scoped Quick Lookup result into ordinary Atlas profile mode', async () => {
    const detail = lookupDetail()
    const { openAtlasQuickLookup, apiFetch } = loadAtlas({
      apiFetchInterceptor: (url) => {
        if (String(url) !== '/atlas/lookup') return null
        return Promise.resolve(jsonResponse({
          requested_type: 'ip',
          detected_type: 'ip',
          canonical_value: ENTITY.canonical_value,
          project_id: 'prj_1',
          match_state: 'found',
          detail,
          candidates: [],
          candidates_truncated: false,
          parent_host_candidate: null,
        }))
      },
    })

    await openAtlasQuickLookup({
      value: ENTITY.canonical_value,
      mode: 'ip',
      projectId: 'prj_1',
      projectName: 'Case Alpha',
      submit: true,
    })
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-lookup-profile')?.textContent).toContain(ENTITY.canonical_value)
    })
    expect(document.getElementById('atlas-lookup-scope')?.textContent).toBe('Project · Case Alpha')
    expect(JSON.parse(apiFetch.mock.calls.find(([url]) => url === '/atlas/lookup')[1].body)).toEqual({
      mode: 'ip',
      value: ENTITY.canonical_value,
      project_id: 'prj_1',
    })

    document.getElementById('atlas-lookup-open-atlas')?.click()
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-surface')?.classList.contains('is-atlas-lookup')).toBe(false)
    })
    expect(document.querySelector('.atlas-shell')?.getAttribute('data-atlas-mode')).toBe('profile')
    expect(document.getElementById('atlas-search')?.value).toBe(ENTITY.canonical_value)
    expect(apiFetch.mock.calls.some(([url]) => String(url).startsWith('/atlas?'))).toBe(true)
    expect(apiFetch.mock.calls.some(([url]) => String(url).includes('project_id=prj_1'))).toBe(true)
  })

  it('explains a missing saved entity and offers only explicit next steps', async () => {
    const { openAtlasQuickLookup, apiFetch } = loadAtlas({
      apiFetchInterceptor: (url) => {
        if (String(url) !== '/atlas/lookup') return null
        return Promise.resolve(jsonResponse({
          requested_type: 'hostname',
          detected_type: 'domain',
          canonical_value: 'missing.example',
          project_id: '',
          match_state: 'not_found',
          detail: null,
          candidates: [],
          candidates_truncated: false,
          parent_host_candidate: null,
        }))
      },
    })

    await openAtlasQuickLookup({ value: 'missing.example', mode: 'hostname', submit: true })

    expect(document.getElementById('atlas-lookup-outcome-title')?.textContent).toBe('No saved Atlas entity')
    expect(document.getElementById('atlas-lookup-outcome-body')?.textContent).toContain('does not mean the value itself is invalid')
    expect(document.getElementById('atlas-lookup-outcome-context')?.textContent).toContain('missing.example')
    expect(document.getElementById('atlas-lookup-outcome-actions')?.textContent).toContain('Search Atlas')
    expect(document.getElementById('atlas-lookup-outcome-actions')?.textContent).toContain('Switch scope')
    expect(document.getElementById('atlas-lookup-outcome-actions')?.textContent).toContain('Prefill nmap scan')
    expect(apiFetch.mock.calls.some(([url]) => String(url).startsWith('/runs'))).toBe(false)
    expect(Array.from(document.querySelectorAll('#atlas-lookup-outcome-actions button')).every(button => (
      button.classList.contains('btn') && button.classList.contains('btn-compact')
    ))).toBe(true)

    Array.from(document.querySelectorAll('#atlas-lookup-outcome-actions button'))
      .find(button => button.textContent === 'Prefill nmap scan')
      ?.click()
    expect(document.getElementById('cmd')?.value).toBe("nmap -sV -- 'missing.example'")
    expect(document.getElementById('atlas-overlay')?.classList.contains('u-hidden')).toBe(true)
    expect(apiFetch.mock.calls.some(([url]) => String(url).startsWith('/runs'))).toBe(false)
  })

  it('keeps option-shaped lookup values behind the nmap end-of-options marker', async () => {
    const { openAtlasQuickLookup } = loadAtlas({
      apiFetchInterceptor: (url) => {
        if (String(url) !== '/atlas/lookup') return null
        return Promise.resolve(jsonResponse({
          requested_type: 'hostname',
          detected_type: 'domain',
          canonical_value: '--script',
          project_id: '',
          match_state: 'not_found',
          detail: null,
          candidates: [],
          candidates_truncated: false,
          parent_host_candidate: null,
        }))
      },
    })

    await openAtlasQuickLookup({ value: '--script', mode: 'hostname', submit: true })

    Array.from(document.querySelectorAll('#atlas-lookup-outcome-actions button'))
      .find(button => button.textContent === 'Prefill nmap scan')
      ?.click()
    expect(document.getElementById('cmd')?.value).toBe("nmap -sV -- '--script'")
  })

  it('requires an explicit bounded choice for an ambiguous saved entity', async () => {
    const {
      openAtlasQuickLookup,
      apiFetch,
      copyTextToClipboard,
      showToast,
    } = loadAtlas({
      apiFetchInterceptor: (url) => {
        if (String(url) !== '/atlas/lookup') return null
        return Promise.resolve(jsonResponse({
          requested_type: 'ip',
          detected_type: 'ip',
          canonical_value: ENTITY.canonical_value,
          project_id: '',
          match_state: 'ambiguous',
          detail: null,
          candidates: [{
            entity_id: ENTITY.id,
            type: 'ip',
            canonical_value: ENTITY.canonical_value,
            provenance: 'compatibility_visible',
            first_seen_at: ENTITY.first_seen_at,
            last_seen_at: ENTITY.last_seen_at,
            occurrence_count: 2,
            suppressed: true,
          }],
          candidates_truncated: true,
          parent_host_candidate: null,
        }))
      },
    })

    await openAtlasQuickLookup({ value: ENTITY.canonical_value, mode: 'ip', submit: true })

    expect(document.getElementById('atlas-lookup-outcome-title')?.textContent)
      .toBe('More than one saved entity matched')
    expect(document.getElementById('atlas-lookup-outcome-candidates')?.textContent)
      .toContain('Compatibility-visible record')
    expect(document.getElementById('atlas-lookup-outcome-candidates')?.textContent).toContain('Suppressed')
    expect(document.getElementById('atlas-lookup-outcome-candidates')?.textContent)
      .toContain('Only the first bounded set of matches is shown')
    expect(document.getElementById('atlas-lookup-profile-view')?.classList.contains('u-hidden')).toBe(true)
    expect(Array.from(document.querySelectorAll('#atlas-lookup-outcome-candidates button')).every(button => (
      button.classList.contains('btn') && button.classList.contains('panel-row')
    ))).toBe(true)

    document.querySelector('#atlas-lookup-outcome-candidates .atlas-lookup-candidate')?.click()
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-lookup-profile')?.textContent).toContain(ENTITY.canonical_value)
    })
    expect(apiFetch).toHaveBeenCalledWith(
      `/atlas/entities/${ENTITY.id}`,
      expect.objectContaining({ cache: 'no-store' }),
    )
    expect(document.getElementById('atlas-lookup-profile')?.textContent).toContain('Copy value')
    expect(document.getElementById('atlas-lookup-profile')?.textContent).toContain('First seen')
    expect(document.getElementById('atlas-lookup-profile')?.textContent).toContain('1 project link')
    expect(apiFetch.mock.calls.some(([url]) => String(url).includes('/refresh_intel'))).toBe(false)

    const profileActions = Array.from(document.querySelectorAll(
      '#atlas-lookup-profile .atlas-detail-actions button',
    ))
    profileActions.find(button => button.textContent === 'Copy value')?.click()
    await vi.waitFor(() => {
      expect(copyTextToClipboard).toHaveBeenCalledWith(ENTITY.canonical_value)
    })
    expect(showToast).toHaveBeenCalledWith('Entity copied', 'success')

    profileActions.find(button => button.textContent === 'Refresh intel')?.click()
    await vi.waitFor(() => {
      expect(apiFetch.mock.calls.some(([url, options]) => (
        String(url) === `/atlas/entities/${ENTITY.id}/refresh_intel`
          && options?.method === 'POST'
      ))).toBe(true)
    })
  })

  it('preserves the chosen ambiguous entity ID when opening ordinary Atlas', async () => {
    const firstEntity = { ...ENTITY, id: 'ent_ip_first' }
    const chosenEntity = { ...ENTITY, id: 'ent_ip_chosen' }
    const chosenDetail = lookupDetail(chosenEntity)
    const { openAtlasQuickLookup, apiFetch } = loadAtlas({
      apiFetchInterceptor: (url) => {
        const target = String(url)
        if (target === '/atlas/lookup') {
          return Promise.resolve(jsonResponse({
            requested_type: 'ip',
            detected_type: 'ip',
            canonical_value: ENTITY.canonical_value,
            project_id: '',
            match_state: 'ambiguous',
            detail: null,
            candidates: [firstEntity, chosenEntity].map((entity, index) => ({
              entity_id: entity.id,
              type: entity.type,
              canonical_value: entity.canonical_value,
              provenance: index === 0 ? 'personal' : 'compatibility_visible',
            })),
            candidates_truncated: false,
            parent_host_candidate: null,
          }))
        }
        if (target === `/atlas/entities/${chosenEntity.id}`) {
          return Promise.resolve(jsonResponse(chosenDetail))
        }
        if (target.startsWith('/atlas/entities?')) {
          return Promise.resolve(jsonResponse({
            entities: [firstEntity, chosenEntity],
            total: 2,
            limit: 50,
            offset: 0,
          }))
        }
        return null
      },
    })

    await openAtlasQuickLookup({ value: ENTITY.canonical_value, mode: 'ip', submit: true })
    const candidates = document.querySelectorAll(
      '#atlas-lookup-outcome-candidates .atlas-lookup-candidate',
    )
    candidates[1]?.click()
    await vi.waitFor(() => {
      expect(window.DarklabAtlasOverlay.state.detail?.entity?.id).toBe(chosenEntity.id)
    })

    document.getElementById('atlas-lookup-open-atlas')?.click()
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-surface')?.classList.contains('is-atlas-lookup')).toBe(false)
      expect(window.DarklabAtlasOverlay.state.detail?.entity?.id).toBe(chosenEntity.id)
    })

    expect(window.DarklabAtlasOverlay.state.selectedId).toBe(chosenEntity.id)
    expect(window.DarklabAtlasOverlay.state.entityProfileMode).toBe(true)
    expect(document.querySelector('.atlas-shell')?.dataset.atlasMode).toBe('profile')
    expect(apiFetch.mock.calls.filter(([url]) => (
      String(url) === `/atlas/entities/${chosenEntity.id}`
    ))).toHaveLength(2)
  })

  it('keeps a suppressed orphan-source result selected when opening ordinary Atlas', async () => {
    const orphanEntity = {
      ...ENTITY,
      id: 'ent_ip_orphan',
      run_count: 0,
      suppressed: true,
      suppressed_reason: 'operator cleanup',
    }
    const orphanDetail = {
      ...lookupDetail(orphanEntity),
      runs: [],
      detail_limits: {
        ...lookupDetail(orphanEntity).detail_limits,
        runs: { limit: 50, offset: 0, shown: 0, total: 0, has_more: false },
      },
    }
    const { openAtlasQuickLookup, apiFetch } = loadAtlas({
      apiFetchInterceptor: (url) => {
        const target = String(url)
        if (target === '/atlas/lookup') {
          return Promise.resolve(jsonResponse({
            requested_type: 'ip',
            detected_type: 'ip',
            canonical_value: orphanEntity.canonical_value,
            project_id: '',
            match_state: 'found',
            detail: orphanDetail,
            candidates: [],
            candidates_truncated: false,
            parent_host_candidate: null,
          }))
        }
        if (target === `/atlas/entities/${orphanEntity.id}`) {
          return Promise.resolve(jsonResponse(orphanDetail))
        }
        if (target.startsWith('/atlas/entities?')) {
          const includesHidden = target.includes('orphan_filter=all')
            && target.includes('suppression_filter=all')
          return Promise.resolve(jsonResponse({
            entities: includesHidden ? [orphanEntity] : [],
            total: includesHidden ? 1 : 0,
            limit: 50,
            offset: 0,
          }))
        }
        return null
      },
    })

    await openAtlasQuickLookup({ value: orphanEntity.canonical_value, mode: 'ip', submit: true })
    document.getElementById('atlas-lookup-open-atlas')?.click()
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-surface')?.classList.contains('is-atlas-lookup')).toBe(false)
      expect(window.DarklabAtlasOverlay.state.detail?.entity?.id).toBe(orphanEntity.id)
    })

    expect(window.DarklabAtlasOverlay.state.selectedId).toBe(orphanEntity.id)
    expect(window.DarklabAtlasOverlay.state.entityProfileMode).toBe(true)
    expect(document.querySelector('.atlas-shell')?.dataset.atlasMode).toBe('profile')
    expect(apiFetch.mock.calls.some(([url]) => (
      String(url).startsWith('/atlas/entities?')
        && String(url).includes('orphan_filter=all')
        && String(url).includes('suppression_filter=all')
    ))).toBe(true)
  })

  it('keeps New lookup at the form when an ambiguous candidate load becomes stale', async () => {
    const detailLoad = deferred()
    let detailSignal = null
    const { openAtlasQuickLookup } = loadAtlas({
      apiFetchInterceptor: (url, options = {}) => {
        if (String(url) === '/atlas/lookup') {
          return Promise.resolve(jsonResponse({
            requested_type: 'ip',
            detected_type: 'ip',
            canonical_value: ENTITY.canonical_value,
            project_id: '',
            match_state: 'ambiguous',
            detail: null,
            candidates: [{
              entity_id: ENTITY.id,
              type: 'ip',
              canonical_value: ENTITY.canonical_value,
              provenance: 'personal',
            }],
            candidates_truncated: false,
            parent_host_candidate: null,
          }))
        }
        if (String(url) === `/atlas/entities/${ENTITY.id}`) {
          detailSignal = options.signal
          return detailLoad.promise
        }
        return null
      },
    })

    await openAtlasQuickLookup({ value: ENTITY.canonical_value, mode: 'ip', submit: true })
    document.querySelector('#atlas-lookup-outcome-candidates .atlas-lookup-candidate')?.click()
    await vi.waitFor(() => expect(detailSignal).not.toBeNull())
    document.getElementById('atlas-lookup-outcome-new')?.click()

    expect(detailSignal?.aborted).toBe(true)
    detailLoad.resolve(jsonResponse(lookupDetail()))
    await Promise.resolve()
    await Promise.resolve()
    expect(document.getElementById('atlas-lookup-form-view')?.classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('atlas-lookup-profile-view')?.classList.contains('u-hidden')).toBe(true)
  })

  it('keeps an unmatched URL visible while opening its known parent host', async () => {
    const requestedUrl = 'https://107.178.109.44/admin?next=%2F'
    const { openAtlasQuickLookup } = loadAtlas({
      apiFetchInterceptor: (url) => {
        if (String(url) !== '/atlas/lookup') return null
        return Promise.resolve(jsonResponse({
          requested_type: 'url',
          detected_type: 'url',
          canonical_value: requestedUrl,
          project_id: '',
          match_state: 'not_found',
          detail: null,
          candidates: [],
          candidates_truncated: false,
          parent_host_candidate: {
            detected_type: 'ip',
            canonical_value: ENTITY.canonical_value,
            match_state: 'found',
            entity: {
              entity_id: ENTITY.id,
              type: 'ip',
              canonical_value: ENTITY.canonical_value,
              provenance: 'personal',
              first_seen_at: ENTITY.first_seen_at,
              last_seen_at: ENTITY.last_seen_at,
              occurrence_count: 2,
              suppressed: false,
            },
            candidates: [],
            candidates_truncated: false,
          },
        }))
      },
    })

    await openAtlasQuickLookup({ value: requestedUrl, mode: 'url', submit: true })

    expect(document.getElementById('atlas-lookup-outcome-title')?.textContent)
      .toBe('No saved record for this URL')
    expect(document.getElementById('atlas-lookup-outcome-context')?.textContent).toContain(requestedUrl)
    expect(document.getElementById('atlas-lookup-outcome-candidates')?.textContent)
      .toContain('Open known parent host')

    document.querySelector('#atlas-lookup-outcome-candidates .atlas-lookup-candidate')?.click()
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-lookup-profile')?.textContent).toContain(ENTITY.canonical_value)
    })
    expect(document.getElementById('atlas-lookup-profile-scope')?.textContent)
      .toBe(`Known parent for ${requestedUrl} · Personal`)
  })

  it('returns from a linked Project to the exact Quick Lookup profile and stack', async () => {
    const requestedUrl = 'https://107.178.109.44/not-saved?next=%2F'
    const urlDetail = {
      ...lookupDetail(URL_ENTITY),
      entity: {
        ...URL_ENTITY,
        project_link_count: 1,
        project_links: [{ project_id: 'prj_linked', project_name: 'Linked Case' }],
      },
      parent_host: ENTITY,
    }
    const {
      openAtlas,
      openAtlasQuickLookup,
      apiFetch,
      openProjectWorkspaceById,
    } = loadAtlas({
      apiFetchInterceptor: (url) => {
        const target = String(url)
        if (target === '/atlas/lookup') {
          return Promise.resolve(jsonResponse({
            requested_type: 'url',
            detected_type: 'url',
            canonical_value: requestedUrl,
            project_id: '',
            match_state: 'not_found',
            detail: null,
            candidates: [],
            candidates_truncated: false,
            parent_host_candidate: {
              detected_type: 'ip',
              canonical_value: ENTITY.canonical_value,
              match_state: 'found',
              entity: {
                entity_id: ENTITY.id,
                type: ENTITY.type,
                canonical_value: ENTITY.canonical_value,
                provenance: 'personal',
              },
              candidates: [],
              candidates_truncated: false,
            },
          }))
        }
        if (target === `/atlas/entities/${URL_ENTITY.id}`) {
          return Promise.resolve(jsonResponse(urlDetail))
        }
        return null
      },
    })

    await openAtlasQuickLookup({ value: requestedUrl, mode: 'url', submit: true })
    document.querySelector('#atlas-lookup-outcome-candidates .atlas-lookup-candidate')?.click()
    await vi.waitFor(() => {
      expect(document.querySelector('#atlas-lookup-profile .atlas-related-url-open')).not.toBeNull()
    })
    document.querySelector('#atlas-lookup-profile .atlas-related-url-open')
      ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await vi.waitFor(() => {
      expect(document.querySelector(
        '#atlas-lookup-profile .atlas-project-link-actions button',
      )).not.toBeNull()
    })

    const openProject = [...document.querySelectorAll(
      '#atlas-lookup-profile .atlas-project-link-actions button',
    )].find(button => button.textContent === 'Open Project')
    openProject?.click()
    await flushPromises()

    expect(openProjectWorkspaceById).toHaveBeenCalledTimes(1)
    const returnToAtlas = openProjectWorkspaceById.mock.calls[0][1].returnToAtlas
    expect(returnToAtlas).toEqual(expect.objectContaining({
      source: 'project-return',
      launchMode: 'lookup',
      lookupReturnState: expect.objectContaining({
        lookup: expect.objectContaining({
          root: 'profile',
          submittedRawValue: requestedUrl,
          launchScope: expect.objectContaining({ kind: 'personal', label: 'Personal' }),
          result: expect.objectContaining({
            lookup_origin: {
              kind: 'url_parent',
              detected_type: 'url',
              canonical_value: requestedUrl,
            },
          }),
        }),
        atlas: expect.objectContaining({
          selectedId: URL_ENTITY.id,
          entityProfileView: 'overview',
          entityProfileFindingBucket: 'direct',
        }),
      }),
    }))
    expect(returnToAtlas.lookupReturnState.atlas.entityProfileStack).toHaveLength(1)

    const lookupRequestsBeforeReturn = apiFetch.mock.calls
      .filter(([url]) => String(url) === '/atlas/lookup')
      .length
    const urlDetailRequestsBeforeReturn = apiFetch.mock.calls
      .filter(([url]) => String(url) === `/atlas/entities/${URL_ENTITY.id}`)
      .length
    await openAtlas(returnToAtlas)

    expect(document.getElementById('atlas-surface')?.classList.contains('is-atlas-lookup')).toBe(true)
    expect(document.querySelector('.atlas-shell')?.dataset.atlasMode).toBe('lookup')
    expect(window.DarklabAtlasOverlay.state.selectedId).toBe(URL_ENTITY.id)
    expect(window.DarklabAtlasOverlay.state.entityProfileView).toBe('overview')
    expect(window.DarklabAtlasOverlay.state.entityProfileFindingBucket).toBe('direct')
    expect(window.DarklabAtlasOverlay.state.entityProfileStack).toHaveLength(1)
    expect(document.getElementById('atlas-lookup-profile-scope')?.textContent)
      .toBe(`Known parent for ${requestedUrl} · Personal`)
    expect(document.querySelector('#atlas-lookup-profile .atlas-profile-back')?.textContent)
      .toContain('Back to previous entity')
    expect(document.querySelector(
      '#atlas-lookup-profile [data-atlas-profile-view="overview"]',
    )?.getAttribute('aria-selected')).toBe('true')
    expect(apiFetch.mock.calls.filter(([url]) => String(url) === '/atlas/lookup'))
      .toHaveLength(lookupRequestsBeforeReturn)
    expect(apiFetch.mock.calls.filter(([url]) => String(url) === `/atlas/entities/${URL_ENTITY.id}`))
      .toHaveLength(urlDetailRequestsBeforeReturn)
  })

  it('pages every Quick Lookup profile collection and restores Back navigation on desktop and mobile', async () => {
    for (const mobile of [false, true]) {
      setupAtlasDom()
      document.body.classList.toggle('mobile-terminal-mode', mobile)
      const relatedPortFinding = {
        ...FINDING,
        id: 'fnd_port_1',
        title: 'Related port exposes a service issue',
        entity_id: PORT_ENTITY.id,
        entity_type: PORT_ENTITY.type,
        entity_value: PORT_ENTITY.canonical_value,
      }
      const detailRequests = []
      const pagedDetail = (params = new URLSearchParams()) => {
        const runsOffset = Number(params.get('runs_offset') || 0)
        const findingsOffset = Number(params.get('findings_offset') || 0)
        const relatedUrlsOffset = Number(params.get('related_urls_offset') || 0)
        const relatedPortsOffset = Number(params.get('related_ports_offset') || 0)
        const findingBucket = String(params.get('finding_bucket') || 'direct')
        const bucketFindings = {
          direct: [FINDING],
          related_urls: [RELATED_URL_FINDING],
          related_ports: [relatedPortFinding],
          combined: [FINDING],
        }[findingBucket]
        return {
          ...lookupDetail(),
          runs: [{
            run_id: `run-page-${runsOffset}`,
            command: `nmap page ${runsOffset + 1}`,
            occurrence_count: 1,
          }],
          related_urls: [{
            ...URL_ENTITY,
            canonical_value: `${URL_ENTITY.canonical_value}?page=${relatedUrlsOffset + 1}`,
          }],
          related_ports: [{
            ...PORT_ENTITY,
            canonical_value: `example.com:${443 + relatedPortsOffset}/tcp`,
            host_entity_id: ENTITY.id,
          }],
          findings: bucketFindings.map(finding => ({
            ...finding,
            title: `${finding.title} · page ${findingsOffset + 1}`,
          })),
          finding_summary: {
            direct: findingRollup({ total: 2, all_total: 2, sample: [FINDING] }),
            related_urls: findingRollup({
              total: 2,
              all_total: 2,
              sample: [RELATED_URL_FINDING],
            }),
            related_ports: findingRollup({
              total: 2,
              all_total: 2,
              sample: [relatedPortFinding],
            }),
            combined: findingRollup({
              total: 6,
              all_total: 6,
              sample: [FINDING, RELATED_URL_FINDING, relatedPortFinding],
            }),
          },
          detail_limits: {
            runs: {
              limit: 1,
              offset: runsOffset,
              shown: 1,
              total: 2,
              has_more: runsOffset === 0,
            },
            findings: {
              bucket: findingBucket,
              limit: 1,
              offset: findingsOffset,
              shown: 1,
              total: 2,
              has_more: findingsOffset === 0,
            },
            related_urls: {
              limit: 1,
              offset: relatedUrlsOffset,
              shown: 1,
              total: 2,
              has_more: relatedUrlsOffset === 0,
            },
            related_ports: {
              limit: 1,
              offset: relatedPortsOffset,
              shown: 1,
              total: 2,
              has_more: relatedPortsOffset === 0,
            },
          },
        }
      }
      const initialDetail = pagedDetail()
      const { openAtlasQuickLookup } = loadAtlas({
        apiFetchInterceptor: (url) => {
          const target = String(url)
          if (target === '/atlas/lookup') {
            return Promise.resolve(jsonResponse({
              requested_type: 'ip',
              detected_type: 'ip',
              canonical_value: ENTITY.canonical_value,
              project_id: '',
              match_state: 'found',
              detail: initialDetail,
              candidates: [],
              candidates_truncated: false,
              parent_host_candidate: null,
            }))
          }
          if (target === `/atlas/entities/${ENTITY.id}` || target.startsWith(`/atlas/entities/${ENTITY.id}?`)) {
            detailRequests.push(target)
            return Promise.resolve(jsonResponse(
              pagedDetail(new URL(target, 'https://example.test').searchParams),
            ))
          }
          return null
        },
      })

      await openAtlasQuickLookup({ value: ENTITY.canonical_value, mode: 'ip', submit: true })
      const profileHost = document.getElementById('atlas-lookup-profile')
      await vi.waitFor(() => {
        expect(profileHost?.querySelector('.atlas-related-url-open')).not.toBeNull()
      })
      const replaceProfileChildren = profileHost.replaceChildren.bind(profileHost)
      profileHost.replaceChildren = (...children) => {
        profileHost.scrollTop = 0
        return replaceProfileChildren(...children)
      }

      if (!mobile) {
        for (const bucket of ['direct', 'related_urls', 'related_ports', 'combined']) {
          const requestCount = detailRequests.length
          let bucketButton = null
          await vi.waitFor(() => {
            bucketButton = profileHost.querySelector(`[data-atlas-finding-bucket="${bucket}"]`)
            expect(bucketButton).not.toBeNull()
          })
          bucketButton.click()
          await vi.waitFor(() => {
            expect(detailRequests.length).toBe(requestCount + 1)
            const params = new URL(detailRequests.at(-1), 'https://example.test').searchParams
            expect(params.get('finding_bucket')).toBe(bucket === 'direct' ? null : bucket)
            expect(window.DarklabAtlasOverlay.state.entityProfileFindingBucket).toBe(bucket)
            const bucketTitles = {
              direct: FINDING.title,
              related_urls: RELATED_URL_FINDING.title,
              related_ports: relatedPortFinding.title,
              combined: FINDING.title,
            }
            expect(profileHost.textContent).toContain(`${bucketTitles[bucket]} · page 1`)
          })
          if (bucket !== 'combined') {
            profileHost.querySelector('[data-atlas-profile-view="overview"]')?.click()
          }
        }

        const findingsRequestCount = detailRequests.length
        let nextFindingPage = null
        await vi.waitFor(() => {
          nextFindingPage = [...profileHost.querySelectorAll(
            '.atlas-finding-list .atlas-detail-pager button',
          )].find(button => button.textContent === 'Next')
          expect(nextFindingPage).toBeTruthy()
        })
        nextFindingPage.click()
        await vi.waitFor(() => {
          expect(detailRequests.length).toBe(findingsRequestCount + 1)
          const params = new URL(detailRequests.at(-1), 'https://example.test').searchParams
          expect(params.get('finding_bucket')).toBe('combined')
          expect(params.get('findings_offset')).toBe('1')
          expect(profileHost.textContent).toContain(`${FINDING.title} · page 2`)
        })

        let evidenceTab = null
        await vi.waitFor(() => {
          evidenceTab = profileHost.querySelector('[data-atlas-profile-view="evidence"]')
          expect(evidenceTab).toBeTruthy()
        })
        evidenceTab.click()
        const runsRequestCount = detailRequests.length
        let nextRunsPage = null
        await vi.waitFor(() => {
          nextRunsPage = [...profileHost.querySelectorAll(
            '.atlas-source-list .atlas-detail-pager button',
          )].find(button => button.textContent === 'Next')
          expect(nextRunsPage).toBeTruthy()
        })
        nextRunsPage.click()
        await vi.waitFor(() => {
          expect(detailRequests.length).toBe(runsRequestCount + 1)
          const params = new URL(detailRequests.at(-1), 'https://example.test').searchParams
          expect(params.get('runs_offset')).toBe('1')
          expect(profileHost.textContent).toContain('nmap page 2')
        })
        let overviewTab = null
        await vi.waitFor(() => {
          overviewTab = profileHost.querySelector('[data-atlas-profile-view="overview"]')
          expect(overviewTab).toBeTruthy()
        })
        overviewTab.click()
      }

      profileHost.scrollTop = 143
      const relatedUrlRequestCount = detailRequests.length
      let nextRelatedUrlPage = null
      await vi.waitFor(() => {
        nextRelatedUrlPage = [...profileHost.querySelectorAll(
          '.atlas-related-url-list .atlas-detail-pager button',
        )].find(button => button.textContent === 'Next')
        expect(nextRelatedUrlPage).toBeTruthy()
      })
      nextRelatedUrlPage.click()
      await vi.waitFor(() => {
        expect(detailRequests.length).toBe(relatedUrlRequestCount + 1)
        const params = new URL(detailRequests.at(-1), 'https://example.test').searchParams
        expect(params.get('related_urls_offset')).toBe('1')
        expect(profileHost.textContent).toContain(`${URL_ENTITY.canonical_value}?page=2`)
        expect(profileHost.scrollTop).toBe(143)
      })

      if (!mobile) {
        const relatedPortRequestCount = detailRequests.length
        let nextRelatedPortPage = null
        await vi.waitFor(() => {
          nextRelatedPortPage = [...profileHost.querySelectorAll(
            '.atlas-related-port-list .atlas-detail-pager button',
          )].find(button => button.textContent === 'Next')
          expect(nextRelatedPortPage).toBeTruthy()
        })
        nextRelatedPortPage.click()
        await vi.waitFor(() => {
          expect(detailRequests.length).toBe(relatedPortRequestCount + 1)
          const params = new URL(detailRequests.at(-1), 'https://example.test').searchParams
          expect(params.get('related_ports_offset')).toBe('1')
          expect(profileHost.textContent).toContain('example.com:444/tcp')
        })
      }

      let relatedUrlButton = null
      await vi.waitFor(() => {
        relatedUrlButton = profileHost.querySelector('.atlas-related-url-open')
        expect(relatedUrlButton).toBeTruthy()
      })
      profileHost.scrollTop = 211
      relatedUrlButton.click()
      await vi.waitFor(() => {
        expect(window.DarklabAtlasOverlay.state.selectedId).toBe(URL_ENTITY.id)
        expect(profileHost.textContent).toContain(URL_ENTITY.canonical_value)
        expect(profileHost.querySelector('.atlas-profile-back')).not.toBeNull()
      })
      profileHost.querySelector('.atlas-profile-back')?.click()
      await vi.waitFor(() => {
        expect(window.DarklabAtlasOverlay.state.selectedId).toBe(ENTITY.id)
        expect(profileHost.scrollTop).toBe(211)
        expect(document.activeElement).toBe(profileHost.querySelector('.atlas-profile-back'))
      })

      profileHost.querySelector('[data-atlas-profile-view="findings"]')?.click()
      const findingRow = profileHost.querySelector('button.atlas-finding-row')
      expect(findingRow).not.toBeNull()
      profileHost.scrollTop = 249
      findingRow.click()
      expect(profileHost.scrollTop).toBe(0)
      profileHost.querySelector('.atlas-detail-back')?.click()
      await vi.waitFor(() => {
        const restoredFinding = profileHost.querySelector('[data-finding-id="fnd_1"]')
        expect(profileHost.scrollTop).toBe(249)
        expect(document.activeElement).toBe(restoredFinding)
      })

      profileHost.querySelector('.atlas-profile-back')?.click()
      await vi.waitFor(() => {
        expect(document.getElementById('atlas-lookup-form-view')?.classList.contains('u-hidden'))
          .toBe(false)
        expect(document.activeElement).toBe(document.getElementById('atlas-lookup-input'))
      })
    }
    document.body.classList.remove('mobile-terminal-mode')
  }, 10_000)

  it('opens an explicit ordinary Atlas search from a no-record state', async () => {
    const { openAtlasQuickLookup, apiFetch } = loadAtlas({
      apiFetchInterceptor: (url) => {
        if (String(url) !== '/atlas/lookup') return null
        return Promise.resolve(jsonResponse({
          requested_type: 'hostname',
          detected_type: 'domain',
          canonical_value: 'missing.example',
          project_id: '',
          match_state: 'not_found',
          detail: null,
          candidates: [],
          candidates_truncated: false,
          parent_host_candidate: null,
        }))
      },
    })

    await openAtlasQuickLookup({ value: 'missing.example', mode: 'hostname', submit: true })
    Array.from(document.querySelectorAll('#atlas-lookup-outcome-actions button'))
      .find(button => button.textContent === 'Search Atlas')
      ?.click()
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-surface')?.classList.contains('is-atlas-lookup')).toBe(false)
    })

    expect(document.getElementById('atlas-search')?.value).toBe('missing.example')
    expect(apiFetch.mock.calls.some(([url]) => String(url).includes('type=domain'))).toBe(true)
    expect(apiFetch.mock.calls.some(([url]) => (
      String(url).includes('orphan_filter=all') && String(url).includes('suppression_filter=all')
    ))).toBe(true)
  })

  it('opens to the Findings tab by default', async () => {
    const { openAtlas } = loadAtlas()

    await openAtlas({ source: 'test' })

    expect(document.querySelector('[data-atlas-tab="findings"]')?.classList.contains('is-active')).toBe(true)
    expect(document.querySelector('[data-atlas-tab="findings"]')?.getAttribute('aria-pressed')).toBe('true')
    expect(document.querySelector('.atlas-shell')?.dataset.atlasMode).toBe('findings')
    expect(document.getElementById('atlas-list')?.textContent).toContain('443/tcp open https')
  })

  it('saves and applies named Atlas views', async () => {
    let views = []
    const apiFetch = vi.fn((url, options = {}) => {
      const target = String(url)
      if (target === '/atlas/views' && options.method === 'POST') {
        const payload = JSON.parse(options.body)
        views = [{ id: 'atv_1111111111111111', updated_at: '2026-05-18T00:00:00Z', ...payload }]
        return Promise.resolve(jsonResponse({ ok: true, view: views[0], views }))
      }
      if (target === '/atlas/views') return Promise.resolve(jsonResponse({ views }))
      if (target.startsWith('/projects?')) {
        return Promise.resolve(jsonResponse({
          projects: [{ id: 'prj_keep', name: 'Keep Scope', slug: 'keep-scope', status: 'active' }],
          limit: 30,
        }))
      }
      if (target === '/atlas' || target.startsWith('/atlas?')) {
        return Promise.resolve(jsonResponse({
          total: 1,
          counts: { ip: 1, domain: 0, hash: 0, cve: 0, url: 0 },
          findings: 1,
        }))
      }
      if (target.startsWith('/atlas/findings?')) {
        return Promise.resolve(jsonResponse({
          findings: [FINDING],
          total: 1,
          limit: 50,
          offset: 0,
          counts: { new: 1, reviewed: 0, important: 0, false_positive: 0, needs_followup: 0 },
        }))
      }
      if (target === '/atlas/entities/ent_ip') {
        return Promise.resolve(jsonResponse({ entity: ENTITY, runs: [], findings: [], detail_limits: {} }))
      }
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: 'not found' }) })
    })
    const showConfirm = vi.fn((options = {}) => {
      const input = options.content?.querySelector?.('input')
      if (input) input.value = 'High signal'
      return Promise.resolve('save')
    })
    const openProjectAutoPromoteRuleFromAtlas = vi.fn(() => Promise.resolve(true))
    const { openAtlas } = loadAtlas({
      apiFetchImpl: apiFetch,
      showConfirmImpl: showConfirm,
      openProjectAutoPromoteRuleFromAtlasImpl: openProjectAutoPromoteRuleFromAtlas,
    })

    await openAtlas({ source: 'test', projectId: 'prj_keep', projectName: 'Keep Scope' })
    window.DarklabAtlasOverlay.setActiveAtlasTab('ip')
    window.DarklabAtlasOverlay.state.query = '107.178'
    window.DarklabAtlasOverlay.state.findingStatus = 'important'
    window.DarklabAtlasOverlay.state.orphanFilter = 'only'
    window.DarklabAtlasOverlay.state.suppressionFilter = 'only'
    window.DarklabAtlasOverlay.state.runId = 'run1'
    window.DarklabAtlasOverlay.state.runLabel = 'nmap 107.178.109.44'
    document.getElementById('atlas-saved-view-create-rule').click()

    await vi.waitFor(() => expect(openProjectAutoPromoteRuleFromAtlas).toHaveBeenCalled())
    expect(openProjectAutoPromoteRuleFromAtlas).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Atlas view: 107.178',
      project_id: 'prj_keep',
      project_name: 'Keep Scope',
      target_entity_kind: 'ip',
      match_mode: 'contains',
      pattern: '107.178',
      filters: expect.objectContaining({
        source_run_ids: ['run1'],
        include_suppressed: true,
      }),
    }))
    window.DarklabAtlasOverlay.setActiveAtlasTab('findings')
    document.getElementById('atlas-saved-view-save').click()

    await vi.waitFor(() => expect(apiFetch).toHaveBeenCalledWith('/atlas/views', expect.objectContaining({ method: 'POST' })))
    const savedBody = JSON.parse(apiFetch.mock.calls.find(([url, options]) => url === '/atlas/views' && options.method === 'POST')[1].body)
    expect(savedBody).toMatchObject({
      name: 'High signal',
      tab: 'findings',
      filters: {
        query: '107.178',
        orphan_filter: 'only',
        suppression_filter: 'only',
        finding_status: 'important',
        run_id: 'run1',
        run_label: 'nmap 107.178.109.44',
      },
    })

    const select = document.getElementById('atlas-saved-view-select')
    views[0] = { ...views[0], tab: 'ip' }
    window.DarklabAtlasOverlay.state.savedViews[0] = views[0]
    select.value = 'atv_1111111111111111'
    window.DarklabAtlasOverlay.applySavedView(select.value)

    await vi.waitFor(() => expect(document.getElementById('atlas-search').value).toBe('107.178'))
    expect(window.DarklabAtlasOverlay.state.activeTab).toBe('findings')
    expect(document.querySelector('[data-atlas-tab="findings"]')?.classList.contains('is-active')).toBe(true)
    expect(window.DarklabAtlasOverlay.state.findingStatus).toBe('important')
    expect(window.DarklabAtlasOverlay.state.runId).toBe('run1')
    await vi.waitFor(() => {
      expect(apiFetch.mock.calls.some(([url]) => String(url).includes('review_state=important'))).toBe(true)
    })

    window.DarklabAtlasOverlay.state.offset = 50
    window.DarklabAtlasOverlay.state.selectedFindingIds.add('fnd_1')
    document.getElementById('atlas-clear-filters-btn').click()

    await vi.waitFor(() => expect(window.DarklabAtlasOverlay.state.query).toBe(''))
    expect(document.getElementById('atlas-search').value).toBe('')
    expect(window.DarklabAtlasOverlay.state.findingStatus).toBe('')
    expect(window.DarklabAtlasOverlay.state.orphanFilter).toBe('hide')
    expect(window.DarklabAtlasOverlay.state.suppressionFilter).toBe('hide')
    expect(window.DarklabAtlasOverlay.state.runId).toBe('')
    expect(window.DarklabAtlasOverlay.state.selectedSavedViewId).toBe('')
    expect(window.DarklabAtlasOverlay.state.projectId).toBe('')
    expect(document.getElementById('atlas-project-filter-chip')?.classList.contains('u-hidden')).toBe(true)
    expect(window.DarklabAtlasOverlay.state.offset).toBe(0)
    expect(window.DarklabAtlasOverlay.state.selectedFindingIds.size).toBe(0)
    expect(document.getElementById('atlas-saved-view-select').value).toBe('')
    expect(document.getElementById('atlas-saved-view-update').disabled).toBe(true)
    await vi.waitFor(() => {
      const clearedRequest = apiFetch.mock.calls.some(([url]) => {
        const target = String(url)
        return target.startsWith('/atlas/findings?')
          && !target.includes('project_id=')
          && target.includes('orphan_filter=hide')
          && target.includes('suppression_filter=hide')
          && !target.includes('run_id=')
          && !target.includes('review_state=')
          && !target.includes('q=')
      })
      expect(clearedRequest).toBe(true)
    })
  })

  it('syncs populated filter selects and enhances dynamic detail selects', async () => {
    const { openAtlas } = loadAtlas({ useRealSelectEnhancer: true })

    await openAtlas({ source: 'test' })

    const filter = document.getElementById('atlas-finding-status-filter')
    expect(filter.classList.contains('app-select-native')).toBe(true)
    expect(filter.nextElementSibling?.classList.contains('app-select')).toBe(true)
    expect(filter.options[0]?.textContent).toContain('All findings')
    expect(filter.options).toHaveLength(6)
    const savedViewCell = document.querySelector('.atlas-saved-view-select-cell')
    const savedViewSelect = document.getElementById('atlas-saved-view-select')
    expect(savedViewSelect.parentElement).toBe(savedViewCell)
    expect(savedViewSelect.nextElementSibling?.classList.contains('app-select')).toBe(true)
    expect(savedViewSelect.options[0]?.textContent).toContain('Saved views')

    const review = document.querySelector('#atlas-detail .atlas-finding-review')
    expect(review).not.toBeNull()
    expect(review.classList.contains('app-select-native')).toBe(true)
    expect(review.nextElementSibling?.classList.contains('app-select')).toBe(true)
    expect(review.options[0]?.textContent).toContain('New')
    expect(review.nextElementSibling?.querySelectorAll('.dropdown-item')).toHaveLength(5)
  })

  it('opens as a first-class surface and renders entity detail', async () => {
    const {
      openAtlas,
      isAtlasOverlayOpen,
      apiFetch,
      showToast,
      openProjectWorkspaceById,
    } = loadAtlas()

    await openAtlas({ source: 'test', tab: 'ip' })

    expect(isAtlasOverlayOpen()).toBe(true)
    expect(document.getElementById('atlas-overlay')?.classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('atlas-subtitle')?.textContent).toBe('1 entity · 1 finding')
    expect(document.getElementById('atlas-tabs')?.textContent).toContain('IPs(1)')
    expect(document.getElementById('atlas-tabs')?.classList.contains('tab-strip')).toBe(true)
    expect(document.querySelector('[data-atlas-tab="ip"]')?.classList.contains('tab-strip-item')).toBe(true)
    expect(document.querySelector('[data-atlas-tab="ip"]')?.classList.contains('is-active')).toBe(true)
    expect(document.querySelector('[data-atlas-tab="ip"]')?.getAttribute('aria-pressed')).toBe('true')
    expect(document.getElementById('atlas-list')?.textContent).toContain('107.178.109.44')
    expect(document.getElementById('atlas-list')?.textContent).toContain('2 hits · 1 run')
    const rowSuppression = document.querySelector('.atlas-row-suppression-action')
    expect(rowSuppression?.classList.contains('btn-icon-only')).toBe(true)
    expect(rowSuppression?.getAttribute('aria-label')).toBe('Suppress entity')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Shodan')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('External intelligence')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Open ports')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('80, 443')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Freshness: Stale')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('1 provider')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Provider only: 80')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Created by Nuclei JSONL import')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Related URLs')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('https://107.178.109.44/login')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Related ports')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('example.com:443/tcp')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Scan coverage')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('App-captured ports found')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('nmap, naabu')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('App-captured ports')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('443/tcp · https (nginx)')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('nginx TLS listener')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Findings and work')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('On this entity')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('On related URLs')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('1 critical/high')
    const groupTitles = [...document.querySelectorAll('#atlas-detail .atlas-detail-group-title')]
      .map(element => element.textContent)
    expect(groupTitles).toEqual([
      'Observed by darklab_shell',
      'Findings and work',
      'Relationships',
      'Evidence',
      'Metadata',
      'External intelligence',
    ])
    const observedSectionTitles = [...document.querySelectorAll(
      '#atlas-detail .atlas-detail-group:first-of-type .atlas-detail-section-title',
    )].map(element => element.textContent)
    expect(observedSectionTitles).toEqual([
      'Summary',
      'Scan coverage',
    ])
    const evidenceGroup = [...document.querySelectorAll('#atlas-detail .atlas-detail-group')]
      .find(group => group.querySelector('.atlas-detail-group-title')?.textContent === 'Evidence')
    expect(evidenceGroup).toBeTruthy()
    const evidenceSectionTitles = [...(evidenceGroup?.querySelectorAll('.atlas-detail-section-title') || [])]
      .map(element => element.textContent)
    expect(evidenceSectionTitles).toEqual([
      'App-captured ports',
      'Source runs',
      'Import sources',
    ])
    const findingRow = document.querySelector('#atlas-detail button.atlas-finding-row.selection-row')
    expect(findingRow?.classList.contains('btn')).toBe(false)
    expect(findingRow?.classList.contains('panel-row-clickable')).toBe(true)
    expect(document.querySelector('[data-atlas-finding-bucket="direct"]')?.textContent).toContain('1 new')
    const relatedPortRow = document.querySelector('#atlas-detail button.atlas-related-port-row')
    expect(relatedPortRow?.classList.contains('panel-row-clickable')).toBe(true)
    expect(relatedPortRow?.querySelector('button')).toBeNull()
    expect(document.getElementById('atlas-detail')?.textContent).toContain('View all 26 related ports')
    expect(document.querySelector('#atlas-detail .atlas-source-run-open')?.textContent)
      .toContain('shodan host 107.178.109.44')
    expect(document.querySelector('#atlas-detail .atlas-source-list .atlas-detail-action-menu')).toBeNull()
    const detail = document.getElementById('atlas-detail')
    detail.scrollTop = 137
    findingRow?.click()
    expect(detail.textContent).toContain('443/tcp open https')
    expect(detail.querySelector('.atlas-detail-back')?.textContent).toContain('Back to entity')
    expect(detail.scrollTop).toBe(0)
    detail.querySelector('.atlas-detail-back')?.click()
    expect(detail.querySelectorAll('.atlas-detail-group-title')).toHaveLength(6)
    expect(detail.scrollTop).toBe(137)
    const openProject = [...detail.querySelectorAll('.atlas-project-link-actions button')]
      .find(button => button.textContent === 'Open Project')
    openProject?.click()
    await flushPromises()
    expect(openProjectWorkspaceById).toHaveBeenCalledWith('prj_linked', {
      returnToAtlas: expect.objectContaining({
        source: 'project-return',
        tab: 'ip',
        entityValue: ENTITY.canonical_value,
        forceView: 'detail',
        profileView: 'overview',
        findingBucket: 'direct',
      }),
    })
    expect(document.querySelectorAll('.atlas-intel-highlight-provider')).toHaveLength(2)
    expect(document.querySelector('.atlas-intel-highlight-provider')?.textContent).toContain('CVE-2026-0001')
    const intelToggle = document.querySelector('.atlas-intel-card-toggle')
    expect(intelToggle?.classList.contains('btn')).toBe(true)
    expect(intelToggle?.classList.contains('btn-ghost')).toBe(true)
    expect(intelToggle?.getAttribute('aria-expanded')).toBe('false')
    expect(document.querySelector('.atlas-intel-card-body')?.classList.contains('u-hidden')).toBe(true)
    expect(document.querySelector('.atlas-intel-card-body')?.textContent).not.toContain('ports')
    intelToggle?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(intelToggle?.getAttribute('aria-expanded')).toBe('true')
    expect(document.querySelector('.atlas-intel-card-body')?.classList.contains('u-hidden')).toBe(false)
    expect(document.querySelector('.atlas-intel-card-body')?.textContent).toContain('ports')
    expect(document.querySelector('.atlas-intel-card-body')?.textContent).toContain('nginx')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('shodan host 107.178.109.44')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('View all 55 source runs')
    expect(document.querySelector('.atlas-shell')?.dataset.atlasMode).toBe('entity')
    expect(document.querySelector('#atlas-detail .atlas-detail-action-menu-trigger')?.textContent).toBe('Actions')
    expect(document.querySelector('#atlas-detail .atlas-detail-action-menu-list')?.textContent).toContain('Suppress entity')
    const list = document.getElementById('atlas-list')
    list.scrollTop = 93
    detail.scrollTop = 63
    document.querySelector('#atlas-detail .atlas-view-profile')?.click()
    expect(document.querySelector('.atlas-shell')?.dataset.atlasMode).toBe('profile')
    expect(document.querySelector('#atlas-detail .atlas-profile-back')?.textContent).toContain('Back to results')
    expect(document.querySelector('#atlas-detail .atlas-profile-tabs')?.getAttribute('role')).toBe('tablist')
    expect(document.querySelector('#atlas-detail [data-atlas-profile-view="overview"]')?.getAttribute('aria-selected')).toBe('true')
    expect(document.querySelectorAll('#atlas-detail .atlas-detail-group-title')[0]?.textContent).toBe('Overview')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Relationships')
    expect(document.getElementById('atlas-detail')?.textContent).not.toContain('Source runs')

    const entityListLoadsBeforeBucket = apiFetch.mock.calls
      .filter(([url]) => String(url).startsWith('/atlas/entities?type='))
      .length
    document.querySelector('#atlas-detail [data-atlas-finding-bucket="related_urls"]')?.click()
    await flushPromises()
    expect(apiFetch).toHaveBeenCalledWith(
      '/atlas/entities/ent_ip?finding_bucket=related_urls',
      expect.objectContaining({ cache: 'no-store' }),
    )
    expect(document.querySelector('#atlas-detail [data-atlas-profile-view="findings"]')?.getAttribute('aria-selected')).toBe('true')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Findings on related URLs')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Login page exposes a critical issue')
    expect(apiFetch.mock.calls.filter(([url]) => String(url).startsWith('/atlas/entities?type=')))
      .toHaveLength(entityListLoadsBeforeBucket)

    document.querySelector('#atlas-detail [data-atlas-finding-bucket="direct"]')?.click()
    await flushPromises()
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Direct findings')
    const profileFindingRow = document.querySelector('#atlas-detail button.atlas-finding-row.selection-row')
    profileFindingRow?.click()
    const listLoadsBeforeReview = apiFetch.mock.calls
      .filter(([url]) => String(url).startsWith('/atlas/entities?type='))
      .length
    const directDetailLoadsBeforeReview = apiFetch.mock.calls
      .filter(([url]) => String(url) === '/atlas/entities/ent_ip')
      .length
    const profileReview = document.querySelector('#atlas-detail .atlas-finding-review')
    profileReview.value = 'reviewed'
    profileReview.dispatchEvent(new Event('change', { bubbles: true }))
    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Finding updated', 'success'))
    expect(apiFetch.mock.calls.filter(([url]) => String(url).startsWith('/atlas/entities?type=')))
      .toHaveLength(listLoadsBeforeReview)
    expect(apiFetch.mock.calls.filter(([url]) => String(url) === '/atlas/entities/ent_ip'))
      .toHaveLength(directDetailLoadsBeforeReview + 1)
    document.querySelector('#atlas-detail .atlas-detail-back')?.click()
    expect(document.querySelector('#atlas-detail [data-atlas-profile-view="findings"]')?.getAttribute('aria-selected')).toBe('true')

    document.querySelector('#atlas-detail [data-atlas-profile-view="intel"]')?.click()
    const evidenceAction = [...document.querySelectorAll('#atlas-detail .atlas-intel-profile-actions button')]
      .find(button => button.textContent === 'View app evidence')
    evidenceAction?.click()
    expect(document.querySelector('#atlas-detail [data-atlas-profile-view="evidence"]')?.getAttribute('aria-selected')).toBe('true')
    document.querySelector('#atlas-detail [data-atlas-profile-view="intel"]')?.click()
    const providerAction = [...document.querySelectorAll('#atlas-detail .atlas-intel-profile-actions button')]
      .find(button => button.textContent === 'View provider data')
    providerAction?.click()
    expect(document.querySelector('#atlas-detail [data-atlas-profile-view="intel"]')?.getAttribute('aria-selected')).toBe('true')

    document.querySelector('#atlas-detail [data-atlas-profile-view="overview"]')?.click()
    const parentDetailLoadsBeforeRoundTrip = apiFetch.mock.calls
      .filter(([url]) => String(url) === '/atlas/entities/ent_ip')
      .length
    document.querySelector('#atlas-detail .atlas-related-url-open')
      ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()
    expect(document.querySelector('#atlas-detail .atlas-profile-back')?.textContent)
      .toContain('Back to previous entity')
    expect(document.getElementById('atlas-detail')?.textContent).toContain(URL_ENTITY.canonical_value)
    document.querySelector('#atlas-detail .atlas-profile-back')?.click()
    expect(document.querySelector('.atlas-shell')?.dataset.atlasMode).toBe('profile')
    expect(document.getElementById('atlas-detail')?.textContent).toContain(ENTITY.canonical_value)
    expect(document.querySelector('#atlas-detail [data-atlas-profile-view="overview"]')?.getAttribute('aria-selected')).toBe('true')
    expect(apiFetch.mock.calls.filter(([url]) => String(url) === '/atlas/entities/ent_ip'))
      .toHaveLength(parentDetailLoadsBeforeRoundTrip)
    detail.scrollTop = 211
    document.querySelector('.atlas-related-url-list .atlas-detail-pager button:last-child')
      ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()
    expect(detail.scrollTop).toBe(211)
    expect(apiFetch).toHaveBeenCalledWith(
      '/atlas/entities/ent_ip?related_urls_offset=25',
      expect.objectContaining({ cache: 'no-store' }),
    )
    expect(document.querySelector('.atlas-related-url-list .atlas-detail-pager')?.textContent)
      .toContain('26-26 of 26 related URLs')

    document.querySelector('#atlas-detail [data-atlas-profile-view="evidence"]')?.click()
    expect(document.querySelector('#atlas-detail [data-atlas-profile-view="evidence"]')?.getAttribute('aria-selected')).toBe('true')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Scan coverage')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Source runs')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('1-1 of 55 source runs')
    expect(document.querySelector('#atlas-detail .atlas-source-list .atlas-detail-action-menu-list')?.textContent)
      .toContain('Clean from Atlas')
    expect(document.getElementById('atlas-detail')?.textContent).not.toContain('Relationships')
    document.querySelector('#atlas-detail [data-atlas-profile-view="findings"]')?.click()
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Direct findings')
    document.querySelector('#atlas-detail [data-atlas-profile-view="intel"]')?.click()
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Cached provider data')
    const detailLoadsBeforeResultsBack = apiFetch.mock.calls
      .filter(([url]) => String(url) === '/atlas/entities/ent_ip')
      .length
    document.querySelector('#atlas-detail .atlas-profile-back')?.click()
    await Promise.resolve()
    expect(document.querySelector('.atlas-shell')?.dataset.atlasMode).toBe('entity')
    expect(list.scrollTop).toBe(93)
    expect(detail.scrollTop).toBe(63)
    expect(document.querySelector('[data-entity-id="ent_ip"]')?.getAttribute('aria-current')).toBe('true')
    expect(apiFetch.mock.calls.filter(([url]) => String(url) === '/atlas/entities/ent_ip'))
      .toHaveLength(detailLoadsBeforeResultsBack)
    document.querySelector('#atlas-detail .atlas-detail-actions button')?.click()
    const refreshOverlay = document.querySelector('.atlas-intel-refresh-overlay')
    expect(refreshOverlay?.classList.contains('u-hidden')).toBe(false)
    expect(refreshOverlay?.textContent).toContain('Refreshing intel')
    expect(refreshOverlay?.textContent).toContain('107.178.109.44')
    expect(document.querySelector('#atlas-detail .atlas-detail-actions button')?.textContent).toBe('Refreshing...')
    expect(document.querySelector('#atlas-detail .atlas-detail-actions button')?.disabled).toBe(true)
    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Intel refreshed from 1 provider', 'success'))
    expect(refreshOverlay?.classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('atlas-finding-status-filter')?.classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('atlas-finding-bulk-row')?.classList.contains('u-hidden')).toBe(false)
    expect(apiFetch).toHaveBeenCalledWith(
      '/atlas?orphan_filter=hide&suppression_filter=hide',
      expect.objectContaining({ cache: 'no-store' }),
    )
    expect(apiFetch).toHaveBeenCalledWith('/atlas/entities/ent_ip', expect.objectContaining({ cache: 'no-store' }))
    document.querySelector('#atlas-detail .atlas-related-url-open')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()
    expect(apiFetch).toHaveBeenCalledWith(
      '/atlas/entities?type=url&limit=50&offset=0&orphan_filter=hide&suppression_filter=hide',
      expect.objectContaining({ cache: 'no-store' }),
    )
    expect(apiFetch).toHaveBeenCalledWith('/atlas/entities/ent_url', expect.objectContaining({ cache: 'no-store' }))
    expect(document.getElementById('atlas-detail')?.textContent).toContain('curl https://107.178.109.44/login')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Parent host')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('107.178.109.44')
    expect(document.getElementById('atlas-detail')?.textContent)
      .toContain('App-captured ports (parent host)')
    expect([...document.querySelectorAll('#atlas-detail .atlas-detail-group-title')]
      .map(element => element.textContent)).toEqual([
      'Observed by darklab_shell',
      'Findings and work',
      'Relationships',
      'Evidence',
      'Metadata',
      'External intelligence',
    ])
    const urlRelationshipGroup = [...document.querySelectorAll('#atlas-detail .atlas-detail-group')]
      .find(group => group.querySelector('.atlas-detail-group-title')?.textContent === 'Relationships')
    expect([...(urlRelationshipGroup?.querySelectorAll('.atlas-detail-section-title') || [])]
      .map(element => element.textContent)).toEqual(['Parent host', 'Projects'])
    const urlEvidenceGroup = [...document.querySelectorAll('#atlas-detail .atlas-detail-group')]
      .find(group => group.querySelector('.atlas-detail-group-title')?.textContent === 'Evidence')
    expect([...(urlEvidenceGroup?.querySelectorAll('.atlas-detail-section-title') || [])]
      .map(element => element.textContent)).toEqual([
      'App-captured ports (parent host)',
      'Source runs',
      'Import sources',
    ])
    expect(document.querySelectorAll('#atlas-detail .atlas-finding-summary-card')).toHaveLength(1)
    expect(document.querySelector('#atlas-detail .atlas-finding-summary-card')?.textContent)
      .toContain('On this entity')
    await openAtlas({ source: 'test', tab: 'ip', projectId: 'prj_linked', projectName: 'Linked Case' })
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-detail')?.textContent).toContain('Project monitoring')
    })
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Watch edge ports')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('New open port 80/tcp')
    expect(apiFetch).toHaveBeenCalledWith(
      '/atlas/entities/ent_ip?project_id=prj_linked',
      expect.objectContaining({ cache: 'no-store' }),
    )
  }, 10_000)

  it('does not close its own fallback shell while finishing either Atlas entry mode', async () => {
    const closeMajorOverlays = vi.fn()
    const { openAtlas, openAtlasQuickLookup } = loadAtlas({ closeMajorOverlaysImpl: closeMajorOverlays })

    await openAtlas({ source: 'test' })

    expect(closeMajorOverlays).toHaveBeenCalledWith({ skipAtlas: true })

    closeMajorOverlays.mockClear()
    await openAtlasQuickLookup({ source: 'test' })

    expect(closeMajorOverlays).toHaveBeenCalledWith({ skipAtlas: true })
  })

  it('previews and applies an Atlas import from a project-scoped Atlas surface', async () => {
    const { openAtlas, apiFetch, showToast, projectEvents } = loadAtlas()

    await openAtlas({ source: 'test', tab: 'findings', projectId: 'proj_1', projectName: 'Evidence' })
    document.getElementById('atlas-import-btn')?.click()

    const fileInput = document.getElementById('atlas-import-file')
    const formatSelect = document.getElementById('atlas-import-format')
    expect(fileInput?.getAttribute('accept')).toContain('.jsonl')
    formatSelect.value = 'nessus_xml'
    formatSelect.dispatchEvent(new Event('change', { bubbles: true }))
    expect(fileInput?.getAttribute('accept')).toContain('.nessus')
    formatSelect.value = 'nuclei_jsonl'
    formatSelect.dispatchEvent(new Event('change', { bubbles: true }))
    expect(fileInput?.getAttribute('accept')).toContain('.jsonl')
    Object.defineProperty(fileInput, 'files', {
      value: [new File(['{"template-id":"ssl/header"}\n'], 'nuclei.jsonl', { type: 'application/jsonl' })],
      configurable: true,
    })
    document.getElementById('atlas-import-modal')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))

    await vi.waitFor(() => expect(apiFetch).toHaveBeenCalledWith(
      '/atlas/imports/preview',
      expect.objectContaining({ method: 'POST' }),
    ))
    const previewCall = apiFetch.mock.calls.find(([url]) => url === '/atlas/imports/preview')
    expect(previewCall?.[1].body.get('format_id')).toBe('nuclei_jsonl')
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-import-preview')?.textContent).toContain('Missing security header')
    })
    expect(document.getElementById('atlas-import-preview')?.textContent).toContain('Skipped empty value')
    expect(document.querySelector('.atlas-import-warning-row')?.textContent).toContain('Row 2')
    expect(document.querySelector('[data-atlas-import-option="import_entities"]')?.disabled).toBe(false)
    expect(document.querySelector('[data-atlas-import-option="import_findings"]')?.disabled).toBe(false)
    expect(document.querySelector('[data-atlas-import-option="link_to_project"]')?.disabled).toBe(false)
    expect(document.querySelector('[data-atlas-import-option="create_project_targets"]')?.disabled).toBe(false)
    expect(document.querySelector('[data-atlas-import-option="create_project_targets"]')?.checked).toBe(false)
    expect(document.querySelector('[data-atlas-import-option="create_project_targets"]')?.closest('label')?.textContent)
      .toContain('creates or reuses Atlas entities')
    const importOptionLabel = document.querySelector('[data-atlas-import-option="import_entities"]')?.closest('label')
    expect(importOptionLabel?.classList.contains('form-check')).toBe(true)
    expect(importOptionLabel?.classList.contains('control-row')).toBe(false)

    document.querySelector('[data-atlas-import-option="link_to_project"]').checked = true
    document.getElementById('atlas-import-apply')?.click()

    await vi.waitFor(() => expect(apiFetch).toHaveBeenCalledWith(
      '/atlas/imports/apply',
      expect.objectContaining({ method: 'POST' }),
    ))
    const applyCall = apiFetch.mock.calls.find(([url]) => url === '/atlas/imports/apply')
    const applyBody = JSON.parse(applyCall?.[1].body)
    expect(applyBody).toMatchObject({
      draft_id: 'impd_1',
      row_set_digest: 'digest_1',
      project_id: 'proj_1',
      options: {
        import_entities: true,
        import_findings: true,
        link_to_project: true,
      },
    })
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-import-preview')?.textContent).toContain('1 entity created')
    })
    expect(document.getElementById('atlas-import-preview')?.textContent).toContain('1 project link added')
    expect(document.getElementById('atlas-import-preview')?.textContent).toContain('1 project target created')
    expect(showToast).toHaveBeenCalledWith('Atlas import applied', 'success')
    expect(projectEvents.some(event => event.name === 'app:project-workspace-changed')).toBe(true)
  })

  it('requires a file before previewing an Atlas import', async () => {
    const { openAtlas, apiFetch, showToast } = loadAtlas()

    await openAtlas({ source: 'test', tab: 'findings' })
    document.getElementById('atlas-import-btn')?.click()
    submitAtlasImportPreview()

    expect(showToast).toHaveBeenCalledWith('Choose a file to import', 'error')
    expect(apiFetch.mock.calls.some(([url]) => url === '/atlas/imports/preview')).toBe(false)
    expect(document.getElementById('atlas-import-apply')?.disabled).toBe(true)
  })

  it('disables unavailable Atlas import apply options after preview', async () => {
    const { openAtlas } = loadAtlas({
      apiFetchInterceptor: (url, options = {}) => {
        if (String(url) === '/atlas/imports/preview' && options.method === 'POST') {
          return Promise.resolve(jsonResponse({
            ok: true,
            draft_id: 'impd_disabled',
            row_set_digest: 'digest_disabled',
            counts: { rows: 1, entity_valid: 0, finding_valid: 0, new: 0, updated: 0, warnings: 0 },
            samples: { entities: [], findings: [] },
            warnings: [],
            apply_options: {
              import_entities: { available: false, requires: ['mutate_projects'] },
              import_findings: { available: false, requires: ['triage_findings'] },
              link_to_project: { available: false, requires: ['mutate_projects'] },
              create_project_targets: { available: false, requires: ['mutate_projects'] },
            },
          }))
        }
        return undefined
      },
    })

    await openAtlas({ source: 'test', tab: 'findings', projectId: 'proj_1', projectName: 'Evidence' })
    document.getElementById('atlas-import-btn')?.click()
    setAtlasImportFile()
    submitAtlasImportPreview()

    await vi.waitFor(() => {
      expect(document.getElementById('atlas-import-status')?.textContent).toContain('Preview ready')
    })
    ;['import_entities', 'import_findings', 'link_to_project', 'create_project_targets'].forEach((key) => {
      const checkbox = document.querySelector(`[data-atlas-import-option="${key}"]`)
      expect(checkbox?.disabled).toBe(true)
      expect(checkbox?.checked).toBe(false)
    })
    expect(document.getElementById('atlas-import-apply')?.disabled).toBe(true)
  })

  it('can retry an Atlas import preview after a handled preview rejection', async () => {
    let previewAttempts = 0
    const { openAtlas, showToast } = loadAtlas({
      apiFetchInterceptor: (url, options = {}) => {
        if (String(url) === '/atlas/imports/preview' && options.method === 'POST') {
          previewAttempts += 1
          if (previewAttempts === 1) {
            return Promise.resolve(errorResponse(400, { message: 'Unsupported import format' }))
          }
        }
        return undefined
      },
    })

    await openAtlas({ source: 'test', tab: 'findings' })
    document.getElementById('atlas-import-btn')?.click()
    setAtlasImportFile('not jsonl', 'bad.txt', 'text/plain')
    submitAtlasImportPreview()

    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Unsupported import format', 'error'))
    expect(document.getElementById('atlas-import-status')?.textContent).toBe('')

    setAtlasImportFile()
    submitAtlasImportPreview()

    await vi.waitFor(() => {
      expect(document.getElementById('atlas-import-preview')?.textContent).toContain('Missing security header')
    })
    expect(previewAttempts).toBe(2)
    expect(document.getElementById('atlas-import-status')?.textContent).toContain('Preview ready')
  })

  it('does not log expected Atlas import preview rejections as client errors', async () => {
    const { openAtlas, logClientError, showToast } = loadAtlas({
      apiFetchInterceptor: (url, options = {}) => {
        if (String(url) === '/atlas/imports/preview' && options.method === 'POST') {
          return Promise.resolve(errorResponse(400, { message: 'Unsupported import format' }))
        }
        return undefined
      },
    })

    await openAtlas({ source: 'test', tab: 'findings' })
    document.getElementById('atlas-import-btn')?.click()
    setAtlasImportFile('not jsonl', 'bad.txt', 'text/plain')
    submitAtlasImportPreview()

    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Unsupported import format', 'error'))
    expect(logClientError).not.toHaveBeenCalled()
  })

  it('logs Atlas import preview runtime failures as client errors', async () => {
    const networkError = new Error('network down')
    const { openAtlas, logClientError, showToast } = loadAtlas({
      apiFetchInterceptor: (url, options = {}) => {
        if (String(url) === '/atlas/imports/preview' && options.method === 'POST') {
          return Promise.reject(networkError)
        }
        return undefined
      },
    })

    await openAtlas({ source: 'test', tab: 'findings' })
    document.getElementById('atlas-import-btn')?.click()
    setAtlasImportFile()
    submitAtlasImportPreview()

    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('network down', 'error'))
    expect(logClientError).toHaveBeenCalledWith('failed to preview atlas import', networkError)
  })

  it('does not log expected Atlas import apply rejections as client errors', async () => {
    for (const [status, message] of [
      [403, 'You need permission to import Atlas findings'],
      [409, 'Import preview expired'],
    ]) {
      setupAtlasDom()
      const { openAtlas, logClientError, showToast } = loadAtlas({
        apiFetchInterceptor: (url, options = {}) => {
          if (String(url) === '/atlas/imports/apply' && options.method === 'POST') {
            return Promise.resolve(errorResponse(status, { message }))
          }
          return undefined
        },
      })

      await openAtlas({ source: 'test', tab: 'findings' })
      document.getElementById('atlas-import-btn')?.click()
      setAtlasImportFile()
      submitAtlasImportPreview()
      await vi.waitFor(() => {
        expect(document.getElementById('atlas-import-preview')?.textContent).toContain('Missing security header')
      })

      document.getElementById('atlas-import-apply')?.click()

      await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith(message, 'error'))
      expect(logClientError).not.toHaveBeenCalled()
    }
  })

  it('cycles Atlas tabs forward and backward for modal keyboard shortcuts', async () => {
    const { openAtlas, cycleAtlasTab } = loadAtlas()

    await openAtlas({ source: 'test' })

    expect(document.querySelector('[data-atlas-tab="findings"]')?.classList.contains('is-active')).toBe(true)
    expect(cycleAtlasTab(1)).toBe(true)
    await Promise.resolve()
    expect(document.querySelector('[data-atlas-tab="ip"]')?.classList.contains('is-active')).toBe(true)
    expect(document.activeElement?.matches('[data-atlas-tab]')).toBe(false)
    expect(cycleAtlasTab(-1)).toBe(true)
    await Promise.resolve()
    expect(document.querySelector('[data-atlas-tab="findings"]')?.classList.contains('is-active')).toBe(true)
    expect(document.activeElement?.matches('[data-atlas-tab]')).toBe(false)
  })

  it('renders an empty Atlas without warning when no saved runs have entities', async () => {
    const apiFetch = vi.fn((url) => {
      const target = String(url)
      if (target === '/atlas' || target.startsWith('/atlas?')) {
        return Promise.resolve(jsonResponse({
          total: 0,
          counts: { ip: 0, domain: 0, hash: 0, cve: 0, url: 0 },
          findings: 0,
        }))
      }
      if (target === '/atlas/views') {
        return Promise.resolve(jsonResponse({ views: [] }))
      }
      if (target.startsWith('/atlas/entities?')) {
        return Promise.resolve(jsonResponse({ entities: [], total: 0, limit: 50, offset: 0 }))
      }
      if (target.startsWith('/atlas/findings?')) {
        return Promise.resolve(jsonResponse({
          findings: [],
          total: 0,
          limit: 50,
          offset: 0,
          counts: { new: 0, reviewed: 0, important: 0, false_positive: 0, needs_followup: 0 },
        }))
      }
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: 'not found' }) })
    })
    const { openAtlas, showToast } = loadAtlas({ apiFetchImpl: apiFetch })

    await openAtlas({ source: 'test' })

    expect(document.getElementById('atlas-subtitle')?.textContent).toBe('0 entities · 0 findings')
    expect(document.getElementById('atlas-list')?.textContent).toContain('No findings queued')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Select a finding')
    expect(showToast).not.toHaveBeenCalled()
    expect(apiFetch).not.toHaveBeenCalledWith('/atlas/entities/ent_ip', expect.objectContaining({ cache: 'no-store' }))
  })

  it('adds the selected entity to the active project without leaving the surface', async () => {
    const { openAtlas, isAtlasOverlayOpen, apiFetch, showToast, projectEvents, storage } = loadAtlas({
      activeProject: { id: 'prj_1', name: 'Case Alpha' },
    })

    await openAtlas({ source: 'test', tab: 'ip', forceView: 'detail' })
    document.querySelector('#atlas-detail .atlas-detail-actions button:nth-child(2)')?.click()
    await Promise.resolve()
    await Promise.resolve()

    expect(apiFetch).toHaveBeenCalledWith(
      '/atlas/entities/ent_ip/project_links',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ project_id: 'prj_1' }),
      }),
    )
    expect(showToast).toHaveBeenCalledWith('Added to active project', 'success')
    expect(projectEvents).toEqual(expect.arrayContaining([
      expect.objectContaining({
        name: 'app:project-workspace-changed',
        detail: expect.objectContaining({ reason: 'atlas_entity_linked', project_id: 'prj_1' }),
      }),
      expect.objectContaining({
        name: 'app:project-workspace-mutated',
        detail: expect.objectContaining({ reason: 'atlas_entity_linked', project_id: 'prj_1' }),
      }),
    ]))
    expect(JSON.parse(storage.getItem('darklab_project_workspace_changed'))).toEqual(expect.objectContaining({
      reason: 'atlas_entity_linked',
      project_id: 'prj_1',
    }))
    expect(isAtlasOverlayOpen()).toBe(true)
  })

  it('only offers same-run Atlas cleanup on delete when removable siblings exist', async () => {
    const showConfirm = vi.fn(() => Promise.resolve('cancel'))
    const previews = [
      { source_run_id: 'run1', sibling_cleanup: { has_cleanup: false, entities: 0, findings: 0, curated_total: 0 } },
      {
        source_run_id: 'run1',
        sibling_cleanup: {
          has_cleanup: true,
          entities: 1,
          findings: 1,
          curated_total: 0,
          cleanup_reasons: {
            buckets: {
              disposable: { entities: 1, findings: 1, total: 2 },
              kept_by_default: { entities: 0, findings: 0, total: 0 },
              not_eligible: { entities: 0, findings: 0, total: 0 },
            },
            reasons: [
              { bucket: 'disposable', code: 'source_run_removed', label: 'source run removed', entities: 0, findings: 1, total: 1 },
            ],
          },
        },
      },
      {
        source_run_id: 'run1',
        sibling_cleanup: {
          has_cleanup: true,
          entities: 1,
          findings: 1,
          curated_entities: 1,
          curated_findings: 1,
          curated_total: 2,
          cleanup_reasons: {
            buckets: {
              disposable: { entities: 1, findings: 1, total: 2 },
              kept_by_default: { entities: 1, findings: 1, total: 2 },
              not_eligible: { entities: 0, findings: 0, total: 0 },
            },
	            reasons: [
	              { bucket: 'kept_by_default', code: 'entity_project_link', label: 'linked to a Project', entities: 1, findings: 0, total: 1 },
	              { bucket: 'kept_by_default', code: 'finding_review_state', label: 'reviewed finding', entities: 0, findings: 1, total: 1 },
	            ],
	            samples: {
	              kept_by_default: {
	                entities: {
	                  items: [{
	                    bucket: 'kept_by_default',
	                    kind: 'entities',
	                    display_value: '107.178.109.44',
	                    item_type: 'ip',
	                    reasons: [{ code: 'entity_project_link', label: 'linked to a Project' }],
	                  }],
	                  omitted: 0,
	                },
	                findings: {
	                  items: [{
	                    bucket: 'kept_by_default',
	                    kind: 'findings',
	                    display_value: 'Reviewed finding',
	                    reasons: [{ code: 'finding_review_state', label: 'reviewed finding' }],
	                  }],
	                  omitted: 0,
	                },
	              },
	            },
	          },
	        },
	      },
    ]
    const apiFetch = vi.fn((url) => {
      const target = String(url)
      if (target === '/atlas' || target.startsWith('/atlas?')) {
        return Promise.resolve(jsonResponse({
          total: 1,
          counts: { ip: 1, domain: 0, hash: 0, cve: 0, url: 0 },
          findings: 0,
        }))
      }
      if (target.startsWith('/atlas/entities?')) {
        return Promise.resolve(jsonResponse({ entities: [ENTITY], total: 1, limit: 50, offset: 0 }))
      }
      if (target === '/atlas/entities/ent_ip') {
        return Promise.resolve(jsonResponse({
          entity: ENTITY,
          intel_snapshots: [],
          intel_summary: { status: 'none', providers_with_data: [], highlights: [] },
          runs: [{ run_id: 'run1', command: 'nmap 107.178.109.44', occurrence_count: 1 }],
          findings: [],
        }))
      }
      if (target === '/atlas/entities/ent_ip/delete-preview') {
        return Promise.resolve(jsonResponse({ preview: previews.shift() }))
      }
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: 'not found' }) })
    })
    const { openAtlas } = loadAtlas({ apiFetchImpl: apiFetch, showConfirmImpl: showConfirm })

    await openAtlas({ source: 'test', tab: 'ip', forceView: 'detail' })
    const deleteBtn = () => {
      document.querySelector('#atlas-detail .atlas-detail-action-menu-trigger')
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      return [...document.querySelectorAll('#atlas-detail .atlas-detail-action-menu-list button')]
        .find(button => button.textContent === 'Delete entity')
    }

    deleteBtn()?.click()
    await Promise.resolve()
    await Promise.resolve()
    expect(showConfirm.mock.calls[0][0].content).toBeNull()

    deleteBtn()?.click()
    await Promise.resolve()
    await Promise.resolve()
    const noCuratedContent = showConfirm.mock.calls[1][0].content
    expect(noCuratedContent.querySelector('input[type="checkbox"]')).not.toBeNull()
    expect(noCuratedContent.textContent).toContain('Also remove 1 finding and 1 entity from Atlas')
    expect(noCuratedContent.textContent).toContain('Reason: source run removed.')
    expect(noCuratedContent.textContent).not.toContain('will be kept')

    deleteBtn()?.click()
    await Promise.resolve()
    await Promise.resolve()
    const curatedContent = showConfirm.mock.calls[2][0].content
    expect(curatedContent.querySelector('input[type="checkbox"]')).not.toBeNull()
	    expect(curatedContent.textContent).toContain('Also delete single-source Atlas items kept by default')
	    expect(curatedContent.textContent).toContain('1 finding kept by default and 1 entity kept by default will be kept unless this is checked.')
	    expect(curatedContent.textContent).toContain('Reasons: linked to a Project, reviewed finding.')
	    const sampleDetails = curatedContent.querySelector('[data-cleanup-samples]')
	    expect(sampleDetails).not.toBeNull()
	    expect(sampleDetails.querySelector('.cleanup-sample-toggle')?.getAttribute('aria-expanded')).toBe('false')
	    expect(sampleDetails.textContent).toContain('107.178.109.44')
	    expect(sampleDetails.textContent).toContain('Reviewed finding')
	    expect([...sampleDetails.querySelectorAll('.badge')].map(badge => badge.textContent))
	      .toEqual(expect.arrayContaining(['ip', 'linked to a Project', 'reviewed finding']))
	  })

  it('disables Atlas delete actions and opens read-only triage when active team scope cannot triage findings', async () => {
    const showConfirm = vi.fn(() => Promise.resolve('delete'))
    const { openAtlas, apiFetch, showToast } = loadAtlas({
      showConfirmImpl: showConfirm,
      activeTeamScopeCanImpl: capability => capability !== 'triage_findings',
    })

    await openAtlas({ source: 'test', tab: 'ip' })
    document.querySelector('.atlas-entity-row')?.click()
    await flushPromises()
    document.querySelector('#atlas-detail .atlas-detail-action-menu-trigger')
      ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    const detailButtons = [...document.querySelectorAll('#atlas-detail .atlas-detail-action-menu-list button')]
    const suppressButton = detailButtons.find(button => button.textContent === 'Suppress entity')
    const deleteButton = detailButtons.find(button => button.textContent === 'Delete entity')

    expect(document.querySelector('.atlas-row-suppression-action')?.disabled).toBe(true)
    expect(suppressButton?.disabled).toBe(true)
    expect(deleteButton?.disabled).toBe(true)
    suppressButton?.click()
    deleteButton?.click()
    await Promise.resolve()

    expect(showConfirm).not.toHaveBeenCalled()
    document.getElementById('atlas-select-toggle').checked = true
    document.getElementById('atlas-select-toggle').dispatchEvent(new Event('change', { bubbles: true }))
    document.querySelector('.atlas-entity-row')?.click()
    expect(document.getElementById('atlas-bulk-delete')?.disabled).toBe(true)
    document.getElementById('atlas-bulk-delete')?.click()
    expect(showToast).not.toHaveBeenCalledWith(expect.stringContaining('Failed to delete'), expect.anything())

    await openAtlas({ source: 'test', tab: 'findings' })
    await flushPromises()
    const triageButton = [...document.querySelectorAll('#atlas-detail .atlas-detail-actions button')]
      .find(button => button.textContent === 'Triage')
    expect(triageButton?.disabled).toBe(false)
    triageButton?.click()
    await flushPromises()

    expect(document.getElementById('finding-triage-overlay').classList.contains('open')).toBe(true)
    expect(document.getElementById('finding-triage-remediation').value).toBe('Retest the exposed service.')
    expect(document.getElementById('finding-triage-remediation').disabled).toBe(true)
    expect(document.getElementById('finding-triage-status').disabled).toBe(true)
    expect(document.getElementById('finding-triage-save').disabled).toBe(true)
    expect(document.getElementById('finding-triage-message').textContent).toContain('read these details')

    const putCallsBefore = apiFetch.mock.calls
      .filter(([url, options]) => url === '/findings/fnd_1/triage' && options?.method === 'PUT').length
    document.getElementById('finding-triage-form')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()
    const putCallsAfter = apiFetch.mock.calls
      .filter(([url, options]) => url === '/findings/fnd_1/triage' && options?.method === 'PUT').length
    expect(putCallsAfter).toBe(putCallsBefore)
  })

  it('applies the project filter when opened from a project', async () => {
    const { openAtlas, apiFetch } = loadAtlas()

    await openAtlas({ source: 'project-workspace', projectId: 'prj_1', projectName: 'Case Alpha' })

    expect(document.getElementById('atlas-subtitle')?.textContent).toBe('1 entity · 1 finding · Case Alpha')
    expect(document.getElementById('atlas-project-filter-select')?.value).toBe('prj_1')
    expect(document.getElementById('atlas-project-filter-chip')?.textContent).toContain('Project: Case Alpha')
    expect(apiFetch).toHaveBeenCalledWith(
      '/atlas?orphan_filter=hide&suppression_filter=hide&project_id=prj_1',
      expect.objectContaining({ cache: 'no-store' }),
    )
    expect(apiFetch).toHaveBeenCalledWith(
      '/atlas/findings?limit=50&offset=0&project_id=prj_1&orphan_filter=hide&suppression_filter=hide',
      expect.objectContaining({ cache: 'no-store' }),
    )

    const projectSelect = document.getElementById('atlas-project-filter-select')
    projectSelect.value = 'prj_2'
    projectSelect.dispatchEvent(new Event('change', { bubbles: true }))
    await flushPromises()

    expect(window.DarklabAtlasOverlay.state.projectId).toBe('prj_2')
    expect(window.DarklabAtlasOverlay.state.projectName).toBe('Case Beta')
    expect(document.getElementById('atlas-project-filter-chip')?.textContent).toContain('Project: Case Beta')
    expect(apiFetch.mock.calls.some(([url]) => (
      String(url) === '/atlas?orphan_filter=hide&suppression_filter=hide&project_id=prj_2'
    ))).toBe(true)

    document.querySelector('#atlas-project-filter-chip button')?.click()
    await flushPromises()

    expect(window.DarklabAtlasOverlay.state.projectId).toBe('')
    expect(document.getElementById('atlas-project-filter-chip')?.classList.contains('u-hidden')).toBe(true)
    expect(apiFetch.mock.calls.some(([url]) => (
      String(url) === '/atlas?orphan_filter=hide&suppression_filter=hide'
    ))).toBe(true)
  })

  it('selects a requested finding when opened from a project finding row', async () => {
    const { openAtlas, apiFetch } = loadAtlas()

    await openAtlas({
      source: 'project-workspace',
      tab: 'findings',
      projectId: 'prj_1',
      projectName: 'Case Alpha',
      findingId: 'fnd_1',
    })

    expect(window.DarklabAtlasOverlay.state.activeTab).toBe('findings')
    expect(window.DarklabAtlasOverlay.state.projectId).toBe('prj_1')
    expect(window.DarklabAtlasOverlay.state.selectedFindingId).toBe('fnd_1')
    expect(apiFetch).toHaveBeenCalledWith(
      '/atlas/findings?limit=50&offset=0&project_id=prj_1&orphan_filter=hide&suppression_filter=hide',
      expect.objectContaining({ cache: 'no-store' }),
    )
  })

  it('opens Findings scoped to a run and clears the run filter chip', async () => {
    const { openAtlas, apiFetch } = loadAtlas()

    await openAtlas({
      source: 'run-details',
      tab: 'findings',
      runId: 'run1',
      runLabel: 'nmap 107.178.109.44',
    })

    expect(document.getElementById('atlas-run-filter-chip')?.textContent).toContain('Run: nmap 107.178.1...')
    expect(document.getElementById('atlas-tabs')?.textContent).toContain('Findings(1/1)')
    expect(apiFetch).toHaveBeenCalledWith(
      '/atlas?orphan_filter=hide&suppression_filter=hide&run_id=run1',
      expect.objectContaining({ cache: 'no-store' }),
    )
    expect(apiFetch).toHaveBeenCalledWith(
      '/atlas?orphan_filter=hide&suppression_filter=hide',
      expect.objectContaining({ cache: 'no-store' }),
    )
    expect(apiFetch).toHaveBeenCalledWith(
      '/atlas/findings?limit=50&offset=0&run_id=run1&orphan_filter=hide&suppression_filter=hide',
      expect.objectContaining({ cache: 'no-store' }),
    )

    document.querySelector('[data-atlas-tab="ip"]')?.click()
    await flushPromises()

    expect(document.getElementById('atlas-run-filter-chip')?.textContent).toContain('Run: nmap 107.178.1...')
    expect(document.getElementById('atlas-tabs')?.textContent).toContain('IPs(1/1)')
    expect(apiFetch).toHaveBeenCalledWith(
      '/atlas/entities?type=ip&limit=50&offset=0&run_id=run1&orphan_filter=hide&suppression_filter=hide',
      expect.objectContaining({ cache: 'no-store' }),
    )

    document.querySelector('#atlas-run-filter-chip button')?.click()
    await flushPromises()

    expect(document.getElementById('atlas-run-filter-chip')?.classList.contains('u-hidden')).toBe(true)
    expect(apiFetch.mock.calls.some(([url]) => (
      String(url) === '/atlas/entities?type=ip&limit=50&offset=0&orphan_filter=hide&suppression_filter=hide'
    ))).toBe(true)
  })

  it('applies a source-run filter from the Atlas run selector', async () => {
    const { openAtlas, apiFetch } = loadAtlas()

    await openAtlas({ source: 'test', tab: 'findings' })

    await vi.waitFor(() => {
      expect([...document.getElementById('atlas-run-filter-select').options].some(option => option.value === 'run1')).toBe(true)
    })
    const select = document.getElementById('atlas-run-filter-select')
    select.value = 'run1'
    select.dispatchEvent(new Event('change', { bubbles: true }))
    await flushPromises()

    expect(document.getElementById('atlas-run-filter-chip')?.textContent).toContain('Run: nmap 107.178.1...')
    expect(apiFetch).toHaveBeenCalledWith(
      '/atlas?orphan_filter=hide&suppression_filter=hide&run_id=run1',
      expect.objectContaining({ cache: 'no-store' }),
    )
    expect(apiFetch).toHaveBeenCalledWith(
      '/atlas/findings?limit=50&offset=0&run_id=run1&orphan_filter=hide&suppression_filter=hide',
      expect.objectContaining({ cache: 'no-store' }),
    )
  })

  it('enables entity pagination while the auto-selected detail loads', async () => {
    let detailRequested = false
    const apiFetch = vi.fn((url) => {
      const target = String(url)
      if (target === '/atlas' || target.startsWith('/atlas?')) {
        return Promise.resolve(jsonResponse({
          total: 51,
          counts: { ip: 0, domain: 51, hash: 0, cve: 0, url: 0 },
          findings: 0,
        }))
      }
      if (target.startsWith('/atlas/entities?')) {
        const entities = Array.from({ length: 50 }, (_, index) => ({
          ...ENTITY,
          id: index === 0 ? 'ent_domain' : `ent_domain_${index}`,
          type: 'domain',
          canonical_value: index === 0 ? 'darklab.sh' : `host-${index}.darklab.sh`,
        }))
        return Promise.resolve(jsonResponse({
          entities,
          total: 51,
          limit: 50,
          offset: 0,
          has_more: true,
          total_exact: false,
        }))
      }
      if (target === '/atlas/entities/ent_domain') {
        detailRequested = true
        return new Promise(() => {})
      }
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: 'not found' }) })
    })
    const { openAtlas } = loadAtlas({ apiFetchImpl: apiFetch })

    void openAtlas({ source: 'test', tab: 'domain' })

    await vi.waitFor(() => {
      expect(document.getElementById('atlas-pagination-summary')?.textContent).toBe('1-50 of 51+')
    })
    expect(detailRequested).toBe(true)
    expect(document.getElementById('atlas-next-btn')?.disabled).toBe(false)
  })

  it('clears entity pagination and keeps hash and CVE details type-appropriate', async () => {
    const apiFetch = vi.fn((url) => {
      const target = String(url)
      if (target === '/atlas' || target.startsWith('/atlas?')) {
        return Promise.resolve(jsonResponse({
          total: 467,
          counts: { ip: 0, domain: 30, hash: 436, cve: 1, url: 0 },
          findings: 0,
        }))
      }
      if (target.startsWith('/atlas/entities?type=hash')) {
        return Promise.resolve(jsonResponse({
          entities: [{ ...ENTITY, id: 'ent_hash', type: 'hash', canonical_value: 'a'.repeat(64) }],
          total: 436,
          limit: 50,
          offset: 0,
        }))
      }
      if (target.startsWith('/atlas/entities?type=domain')) {
        return Promise.resolve(jsonResponse({
          entities: [{ ...ENTITY, id: 'ent_domain', type: 'domain', canonical_value: 'darklab.sh' }],
          total: 30,
          limit: 50,
          offset: 0,
        }))
      }
      if (target.startsWith('/atlas/entities?type=cve')) {
        return Promise.resolve(jsonResponse({
          entities: [{ ...ENTITY, id: 'ent_cve', type: 'cve', canonical_value: 'CVE-2026-0001' }],
          total: 1,
          limit: 50,
          offset: 0,
        }))
      }
      if (target === '/atlas/entities/ent_hash' || target === '/atlas/entities/ent_cve') {
        const entity = target.endsWith('ent_hash')
          ? { ...ENTITY, id: 'ent_hash', type: 'hash', canonical_value: 'a'.repeat(64) }
          : { ...ENTITY, id: 'ent_cve', type: 'cve', canonical_value: 'CVE-2026-0001' }
        return Promise.resolve(jsonResponse({
          entity,
          import_sources: [],
          intel_snapshots: [],
          intel_summary: { status: 'none', providers_with_data: [], highlights: [] },
          overview: {
            observed: {
              app_ports: [],
              app_port_count: 0,
              app_ports_truncated: false,
              app_services: [],
              app_evidence: {
                applicable: false,
                coverage_state: 'not_applicable',
                scan_run_count: 0,
                app_port_count: 0,
                command_roots: [],
              },
            },
          },
          runs: [],
          findings: [],
          finding_summary: {
            direct: findingRollup(),
            related_urls: findingRollup({ applicable: false }),
            related_ports: findingRollup({ applicable: false }),
            combined: findingRollup({ applicable: false }),
          },
          detail_limits: {
            runs: { limit: 50, offset: 0, shown: 0, total: 0, has_more: false },
            findings: { limit: 50, offset: 0, shown: 0, total: 0, has_more: false },
          },
        }))
      }
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: 'not found' }) })
    })
    const { openAtlas } = loadAtlas({ apiFetchImpl: apiFetch })

    await openAtlas({ source: 'test', tab: 'hash' })
    expect(document.getElementById('atlas-pagination-summary')?.textContent).toBe('1-50 of 436')
    expect([...document.querySelectorAll('#atlas-detail .atlas-detail-group-title')]
      .map(element => element.textContent)).toEqual([
      'Observed by darklab_shell',
      'Findings and work',
      'Relationships',
      'Evidence',
      'Metadata',
      'External intelligence',
    ])
    expect(document.querySelectorAll('#atlas-detail .atlas-finding-summary-card')).toHaveLength(1)
    expect(document.getElementById('atlas-detail')?.textContent).not.toContain('Scan coverage')
    expect(document.getElementById('atlas-detail')?.textContent).not.toContain('Parent host')
    expect(document.getElementById('atlas-detail')?.textContent).not.toContain('Related URLs')
    expect(document.getElementById('atlas-detail')?.textContent).not.toContain('Related ports')

    document.querySelector('[data-atlas-tab="cve"]')?.click()

    await vi.waitFor(() => {
      expect(document.getElementById('atlas-list')?.textContent).toContain('CVE-2026-0001')
    })
    expect(document.getElementById('atlas-pagination')?.classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('atlas-pagination-summary')?.textContent).toBe('')
    expect(document.getElementById('atlas-next-btn')?.disabled).toBe(true)
    expect(document.querySelectorAll('#atlas-detail .atlas-finding-summary-card')).toHaveLength(1)
    expect(document.getElementById('atlas-detail')?.textContent).not.toContain('Scan coverage')
    expect(document.getElementById('atlas-detail')?.textContent).not.toContain('Parent host')
    expect(document.getElementById('atlas-detail')?.textContent).not.toContain('Related URLs')
    expect(document.getElementById('atlas-detail')?.textContent).not.toContain('Related ports')
  })

  it('ignores stale entity list responses after switching tabs', async () => {
    const hashList = deferred()
    const apiFetch = vi.fn((url) => {
      const target = String(url)
      if (target === '/atlas' || target.startsWith('/atlas?')) {
        return Promise.resolve(jsonResponse({
          total: 466,
          counts: { ip: 0, domain: 30, hash: 436, cve: 0, url: 0 },
          findings: 0,
        }))
      }
      if (target.startsWith('/atlas/entities?type=hash')) return hashList.promise
      if (target.startsWith('/atlas/entities?type=domain')) {
        return Promise.resolve(jsonResponse({
          entities: [{ ...ENTITY, id: 'ent_domain', type: 'domain', canonical_value: 'darklab.sh' }],
          total: 30,
          limit: 50,
          offset: 0,
        }))
      }
      if (target === '/atlas/entities/ent_domain') {
        return Promise.resolve(jsonResponse({
          entity: { ...ENTITY, id: 'ent_domain', type: 'domain', canonical_value: 'darklab.sh' },
          intel_snapshots: [],
          intel_summary: { status: 'none', providers_with_data: [], highlights: [] },
          overview: {
            observed: {
              app_ports: [],
              app_port_count: 0,
              app_ports_truncated: false,
              app_services: [],
              app_evidence: {
                applicable: true,
                coverage_state: 'not_scanned',
                scan_run_count: 0,
                app_port_count: 0,
                command_roots: [],
              },
            },
          },
          runs: [],
          findings: [],
        }))
      }
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: 'not found' }) })
    })
    const { openAtlas } = loadAtlas({ apiFetchImpl: apiFetch })

    void openAtlas({ source: 'test', tab: 'hash' })
    await vi.waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith(
        '/atlas/entities?type=hash&limit=50&offset=0&orphan_filter=hide&suppression_filter=hide',
        expect.objectContaining({ cache: 'no-store' }),
      )
    })
    const hashListCall = apiFetch.mock.calls.find(([url]) => (
      String(url).startsWith('/atlas/entities?type=hash')
    ))
    document.querySelector('[data-atlas-tab="domain"]')?.click()
    expect(hashListCall?.[1]?.signal?.aborted).toBe(true)
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-list')?.textContent).toContain('darklab.sh')
    })
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-detail')?.textContent)
        .toContain('Run a port scan for this host to add app-captured port and service evidence.')
      expect(document.getElementById('atlas-detail')?.textContent)
        .toContain('No cached provider data. Use Refresh intel to check configured providers.')
    })

    hashList.resolve(jsonResponse({
      entities: [{ ...ENTITY, id: 'ent_hash', type: 'hash', canonical_value: 'a'.repeat(64) }],
      total: 436,
      limit: 50,
      offset: 0,
    }))
    await Promise.resolve()
    await Promise.resolve()

    expect(document.querySelector('[data-atlas-tab="domain"]')?.classList.contains('is-active')).toBe(true)
    expect(document.getElementById('atlas-list')?.textContent).toContain('darklab.sh')
    expect(document.getElementById('atlas-pagination-summary')?.textContent).toBe('')
  })

  it('renders the Findings tab and updates review state', async () => {
    const { openAtlas, apiFetch, showToast, syncAppSelect } = loadAtlas()

    await openAtlas({ source: 'test', tab: 'findings' })

    expect(document.getElementById('atlas-list')?.textContent).toContain('443/tcp open https')
    expect(document.querySelector('.atlas-row-suppression-action')?.getAttribute('aria-label')).toBe('Suppress finding')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Evidence')
    expect(document.querySelector('.atlas-shell')?.dataset.atlasMode).toBe('findings')
    expect([...document.getElementById('atlas-finding-status-filter').options].map(option => option.textContent)).toEqual([
      'All findings',
      'New',
      'Reviewed',
      'Important',
      'False positive',
      'Follow-up',
    ])
    expect([...document.getElementById('atlas-finding-bulk-status').options].map(option => option.textContent)).toEqual([
      'New',
      'Reviewed',
      'Important',
      'False positive',
      'Follow-up',
    ])
    expect([...document.getElementById('atlas-suppression-filter').options].map(option => option.textContent)).toEqual([
      'Visible rows',
      'Show all',
      'Only suppressed',
    ])
    expect(syncAppSelect).toHaveBeenCalledWith(document.getElementById('atlas-finding-status-filter'))
    expect(syncAppSelect).toHaveBeenCalledWith(document.getElementById('atlas-finding-bulk-status'))
    document.querySelector('#atlas-detail .atlas-finding-review').value = 'reviewed'
    document.querySelector('#atlas-detail .atlas-finding-review')
      ?.dispatchEvent(new Event('change', { bubbles: true }))
    await Promise.resolve()
    await Promise.resolve()

    expect(apiFetch).toHaveBeenCalledWith('/findings/fnd_1/review', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ review_state: 'reviewed' }),
    }))
    expect(showToast).toHaveBeenCalledWith('Finding updated', 'success')

    document.querySelector('#atlas-detail .atlas-detail-action-menu-trigger')
      ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    const suppressFindingItem = [...document.querySelectorAll('#atlas-detail .atlas-detail-action-menu-list [role="menuitem"]')]
      .find(button => button.textContent === 'Suppress finding')
    suppressFindingItem?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    await Promise.resolve()

    expect(apiFetch).toHaveBeenCalledWith('/atlas/findings/fnd_1/suppression', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ suppressed: true }),
    }))
  })

  it('suppresses selected Atlas findings without deleting them', async () => {
    const { openAtlas, apiFetch, showToast } = loadAtlas()

    await openAtlas({ source: 'test', tab: 'findings' })
    document.getElementById('atlas-select-toggle').checked = true
    document.getElementById('atlas-select-toggle').dispatchEvent(new Event('change', { bubbles: true }))
    document.querySelector('.atlas-finding-select')?.click()
    document.getElementById('atlas-bulk-suppression')?.click()
    await Promise.resolve()
    await Promise.resolve()

    expect(apiFetch).toHaveBeenCalledWith('/atlas/findings/suppression', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ finding_ids: ['fnd_1'], suppressed: true }),
    }))
    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Suppressed 1 rows', 'success'))
  })

  it('bulk-updates selected Atlas findings', async () => {
    const { openAtlas, apiFetch, showToast } = loadAtlas()

    await openAtlas({ source: 'test', tab: 'findings' })
    expect(document.querySelector('.atlas-finding-select')).toBeNull()
    document.getElementById('atlas-select-toggle').checked = true
    document.getElementById('atlas-select-toggle').dispatchEvent(new Event('change', { bubbles: true }))
    document.querySelector('.atlas-finding-select')?.click()
    document.getElementById('atlas-finding-bulk-status').value = 'important'
    document.getElementById('atlas-finding-bulk-apply')?.click()
    await Promise.resolve()
    await Promise.resolve()

    expect(apiFetch).toHaveBeenCalledWith('/atlas/findings/review', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ finding_ids: ['fnd_1'], review_state: 'important' }),
    }))
    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Updated 1 findings', 'success'))
  })

  it('bulk-deletes selected Atlas entities from entity tabs', async () => {
    const showConfirm = vi.fn(() => Promise.resolve('delete'))
    const apiFetch = vi.fn((url, options = {}) => {
      const target = String(url)
      if (target === '/atlas' || target.startsWith('/atlas?')) {
        return Promise.resolve(jsonResponse({
          total: 1,
          counts: { ip: 1, domain: 0, hash: 0, cve: 0, url: 0 },
          findings: 1,
        }))
      }
      if (target.startsWith('/atlas/entities?')) {
        return Promise.resolve(jsonResponse({ entities: [ENTITY], total: 1, limit: 50, offset: 0 }))
      }
      if (target === '/atlas/entities/ent_ip') {
        return Promise.resolve(jsonResponse({
          entity: ENTITY,
          intel_snapshots: [],
          intel_summary: { status: 'none', providers_with_data: [], highlights: [] },
          runs: [],
          findings: [FINDING],
        }))
      }
      if (target === '/atlas/entities/bulk-delete' && options.method === 'POST') {
        return Promise.resolve(jsonResponse({
          ok: true,
          counts: { deleted: 1, findings_deleted: 1, not_found: 0 },
          results: [{ entity_id: 'ent_ip', status: 'deleted' }],
        }))
      }
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: 'not found' }) })
    })
    const { openAtlas, showToast } = loadAtlas({ apiFetchImpl: apiFetch, showConfirmImpl: showConfirm })

    await openAtlas({ source: 'test', tab: 'ip' })
    document.getElementById('atlas-select-toggle').checked = true
    document.getElementById('atlas-select-toggle').dispatchEvent(new Event('change', { bubbles: true }))
    const entityDetailCallsBeforeSelect = apiFetch.mock.calls
      .filter(([url]) => String(url) === '/atlas/entities/ent_ip').length
    const entityRow = document.querySelector('.atlas-entity-row')
    expect(entityRow?.tagName).toBe('DIV')
    entityRow?.click()
    expect(document.querySelector('.atlas-row-select')?.checked).toBe(true)
    expect(document.querySelector('.atlas-entity-row')?.classList.contains('is-selected')).toBe(true)
    expect(document.querySelector('.atlas-entity-row')?.classList.contains('selection-row')).toBe(true)
    expect(apiFetch.mock.calls.filter(([url]) => String(url) === '/atlas/entities/ent_ip')).toHaveLength(
      entityDetailCallsBeforeSelect,
    )
    document.getElementById('atlas-bulk-delete')?.click()
    document.getElementById('atlas-bulk-delete')?.click()
    await Promise.resolve()
    await Promise.resolve()

    expect(showConfirm).toHaveBeenCalledTimes(1)
    expect(showConfirm.mock.calls[0][0].body).toEqual(expect.objectContaining({
      text: 'Delete 1 Atlas entity?',
      note: 'This removes the selected entities and any findings attached to them. This cannot be undone.',
    }))
    expect(apiFetch).toHaveBeenCalledWith('/atlas/entities/bulk-delete', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ entity_ids: ['ent_ip'] }),
    }))
    expect(apiFetch.mock.calls.filter(([url]) => String(url) === '/atlas/entities/bulk-delete')).toHaveLength(1)
    await vi.waitFor(() => {
      expect(showToast).toHaveBeenCalledWith('Deleted 1 entity - 1 attached finding removed', 'success')
    })
  })

  it('bulk-deletes selected Atlas findings from the Findings tab', async () => {
    const showConfirm = vi.fn(() => Promise.resolve('delete'))
    const apiFetch = vi.fn((url, options = {}) => {
      const target = String(url)
      if (target === '/atlas' || target.startsWith('/atlas?')) {
        return Promise.resolve(jsonResponse({
          total: 1,
          counts: { ip: 1, domain: 0, hash: 0, cve: 0, url: 0 },
          findings: 1,
        }))
      }
      if (target.startsWith('/atlas/findings?')) {
        return Promise.resolve(jsonResponse({
          findings: [FINDING],
          total: 1,
          limit: 50,
          offset: 0,
          counts: { new: 1, reviewed: 0, important: 0, false_positive: 0, needs_followup: 0 },
        }))
      }
      if (target === '/atlas/findings/bulk-delete' && options.method === 'POST') {
        return Promise.resolve(jsonResponse({
          ok: true,
          counts: { deleted: 1, not_found: 0 },
          results: [{ finding_id: 'fnd_1', status: 'deleted' }],
        }))
      }
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: 'not found' }) })
    })
    const { openAtlas, showToast } = loadAtlas({ apiFetchImpl: apiFetch, showConfirmImpl: showConfirm })

    await openAtlas({ source: 'test', tab: 'findings' })
    document.getElementById('atlas-select-toggle').checked = true
    document.getElementById('atlas-select-toggle').dispatchEvent(new Event('change', { bubbles: true }))
    const selectedFindingBeforeClick = document.getElementById('atlas-detail')?.textContent
    const findingRow = document.querySelector('.atlas-finding-queue-row')
    expect(findingRow?.tagName).toBe('DIV')
    findingRow?.click()
    expect(document.querySelector('.atlas-finding-select')?.checked).toBe(true)
    expect(document.querySelector('.atlas-finding-queue-row')?.classList.contains('is-selected')).toBe(true)
    expect(document.querySelector('.atlas-finding-queue-row')?.classList.contains('selection-row')).toBe(true)
    expect(document.getElementById('atlas-detail')?.textContent).toBe(selectedFindingBeforeClick)
    document.getElementById('atlas-bulk-delete')?.click()
    await Promise.resolve()
    await Promise.resolve()

    expect(showConfirm.mock.calls[0][0].body).toEqual(expect.objectContaining({
      text: 'Delete 1 Atlas finding?',
      note: 'This removes the selected findings and cannot be undone.',
    }))
    expect(apiFetch).toHaveBeenCalledWith('/atlas/findings/bulk-delete', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ finding_ids: ['fnd_1'] }),
    }))
    await vi.waitFor(() => {
      expect(showToast).toHaveBeenCalledWith('Deleted 1 finding', 'success')
    })
  })

  it('renders app-first port details across desktop and mobile profiles', async () => {
    const { openAtlas } = loadAtlas()

    await openAtlas({
      source: 'project-workspace',
      projectId: 'prj_1',
      projectName: 'Case Alpha',
      tab: 'port',
      forceView: 'detail',
    })
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-detail')?.textContent).toContain('example.com:443/tcp')
    })
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Prototcp')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Servicehttps')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Versionnginx')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Parent host')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('example.com')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('On this entity')
    expect(document.getElementById('atlas-detail')?.textContent).not.toContain('On related URLs')
    expect([...document.querySelectorAll('#atlas-detail .atlas-detail-group-title')]
      .map(element => element.textContent)).toEqual([
      'Observed by darklab_shell',
      'Findings and work',
      'Relationships',
      'Evidence',
      'Metadata',
      'External intelligence',
    ])
    const portRelationshipGroup = [...document.querySelectorAll('#atlas-detail .atlas-detail-group')]
      .find(group => group.querySelector('.atlas-detail-group-title')?.textContent === 'Relationships')
    expect([...(portRelationshipGroup?.querySelectorAll('.atlas-detail-section-title') || [])]
      .map(element => element.textContent)).toEqual(['Parent host', 'Projects'])
    const portEvidenceGroup = [...document.querySelectorAll('#atlas-detail .atlas-detail-group')]
      .find(group => group.querySelector('.atlas-detail-group-title')?.textContent === 'Evidence')
    expect([...(portEvidenceGroup?.querySelectorAll('.atlas-detail-section-title') || [])]
      .map(element => element.textContent)).toEqual(['Source runs', 'Import sources'])
    expect(document.querySelectorAll('#atlas-detail .atlas-finding-summary-card')).toHaveLength(1)
    expect(document.getElementById('atlas-detail')?.textContent)
      .toContain('No cached provider data for port entities. Open the parent host to review provider data.')
    expect(document.querySelector('#atlas-detail .atlas-open-intel-parent')?.textContent).toBe('Open parent host')
    expect(document.querySelector('#atlas-detail .atlas-detail-actions')?.textContent).not.toContain('Refresh intel')

    document.body.classList.add('mobile-terminal-mode')
    await openAtlas({
      source: 'project-workspace',
      projectId: 'prj_1',
      projectName: 'Case Alpha',
      tab: 'port',
      forceView: 'detail',
    })
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-mobile-entity-body')?.textContent).toContain('example.com:443/tcp')
    })
    expect(document.getElementById('atlas-mobile-entity-body')?.textContent).toContain('Servicehttps')
    expect(document.getElementById('atlas-mobile-entity-body')?.textContent).toContain('Versionnginx')
    expect(document.getElementById('atlas-mobile-entity-body')?.textContent).toContain('Parent host')
    expect(document.getElementById('atlas-mobile-entity-body')?.textContent).toContain('example.com')
    expect(document.getElementById('atlas-mobile-entity-body')?.textContent).toContain('On this entity')
    expect(document.getElementById('atlas-mobile-entity-body')?.textContent).not.toContain('On related URLs')
    expect(document.getElementById('atlas-mobile-entity-body')?.textContent)
      .toContain('No cached provider data for port entities. Open the parent host to review provider data.')
    expect(document.querySelector('#atlas-mobile-entity-body .atlas-open-intel-parent')?.textContent)
      .toBe('Open parent host')
    expect(document.getElementById('atlas-mobile-entity-footer')?.textContent).not.toContain('Refresh intel')
    const mobileEntityBody = document.getElementById('atlas-mobile-entity-body')
    mobileEntityBody.scrollTop = 88
    mobileEntityBody.querySelector('button.atlas-finding-row')?.click()
    expect(document.getElementById('atlas-mobile-entity-topbar')?.textContent).toContain('443/tcp open https')
    expect(mobileEntityBody.textContent).toContain('Evidence')
    expect(document.getElementById('atlas-mobile-entity-footer')?.textContent).toContain('Triage')
    expect(mobileEntityBody.scrollTop).toBe(0)
    document.querySelector('#atlas-mobile-entity-topbar .atlas-mobile-back-btn')?.click()
    expect(mobileEntityBody.textContent).toContain('example.com:443/tcp')
    expect(mobileEntityBody.scrollTop).toBe(88)
    expect(document.getElementById('atlas-mobile-entity-footer')?.textContent).toContain('View profile')
    document.querySelector('#atlas-mobile-entity-footer .atlas-mobile-view-profile')?.click()
    expect(mobileEntityBody.scrollTop).toBe(0)
    expect(mobileEntityBody.querySelector('.atlas-profile-tabs')?.getAttribute('role')).toBe('tablist')
    mobileEntityBody.querySelector('[data-atlas-profile-view="evidence"]')?.click()
    expect(mobileEntityBody.textContent).toContain('Source runs')
    expect(document.getElementById('atlas-mobile-entity-footer')?.textContent).not.toContain('View profile')
    expect(document.querySelector('#atlas-mobile-entity-topbar .atlas-mobile-back-btn')?.getAttribute('aria-label'))
      .toBe('Back to Atlas results')
    document.querySelector('#atlas-mobile-entity-topbar .atlas-mobile-back-btn')?.click()
    expect(document.getElementById('atlas-mobile-list-view')?.classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('atlas-mobile-entity-view')?.classList.contains('u-hidden')).toBe(true)
    document.body.classList.remove('mobile-terminal-mode')
  }, 10_000)

  it('exports filtered entity rows without leaving the Atlas surface', async () => {
    const { openAtlas, apiFetch, downloadBlobAsAttachment, showToast } = loadAtlas()

    await openAtlas({
      source: 'project-workspace',
      projectId: 'prj_1',
      projectName: 'Case Alpha',
      tab: 'port',
      forceView: 'detail',
    })
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-detail')?.textContent).toContain('example.com:443/tcp')
    })
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Prototcp')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Servicehttps')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Versionnginx')
    expect(document.querySelector('#atlas-detail .atlas-detail-actions')?.textContent).not.toContain('Refresh intel')
    document.querySelector('#atlas-detail .atlas-detail-action-menu-trigger')?.click()
    expect(document.querySelector('#atlas-detail .atlas-detail-action-menu-list')?.style.position).toBe('')
    expect(document.querySelector('#atlas-detail .atlas-detail-action-menu-list')?.style.left).not.toBe('')
    expect(document.querySelector('#atlas-detail .atlas-detail-action-menu-list')?.style.top).not.toBe('')
    expect(document.querySelector('#atlas-detail .atlas-detail-action-menu-trigger')?.getAttribute('aria-expanded')).toBe('true')
    document.getElementById('atlas-detail')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    expect(document.querySelector('#atlas-detail .atlas-detail-action-menu-trigger')?.getAttribute('aria-expanded')).toBe('false')
    expect(document.querySelector('#atlas-detail .atlas-detail-action-menu')?.classList.contains('open')).toBe(false)
    expect(apiFetch.mock.calls.some(([url]) => String(url).includes('/refresh_intel'))).toBe(false)

    document.body.classList.add('mobile-terminal-mode')
    await openAtlas({
      source: 'project-workspace',
      projectId: 'prj_1',
      projectName: 'Case Alpha',
      tab: 'port',
      forceView: 'detail',
    })
    await vi.waitFor(() => {
      expect(document.getElementById('atlas-mobile-entity-body')?.textContent).toContain('example.com:443/tcp')
    })
    expect(document.getElementById('atlas-mobile-entity-body')?.textContent).toContain('Servicehttps')
    expect(document.getElementById('atlas-mobile-entity-body')?.textContent).toContain('Versionnginx')
    expect(document.getElementById('atlas-mobile-entity-footer')?.textContent).not.toContain('Refresh intel')
    document.body.classList.remove('mobile-terminal-mode')

    const search = document.getElementById('atlas-search')
    search.value = '443'
    search.dispatchEvent(new Event('input', { bubbles: true }))
    document.getElementById('atlas-export-menu-btn')?.click()
    expect(document.getElementById('atlas-export-menu')?.parentElement).toBe(document.body)
    expect(document.getElementById('atlas-export-menu-btn')?.getAttribute('aria-expanded')).toBe('true')
    document.getElementById('atlas-export-csv-btn')?.click()

    await vi.waitFor(() => expect(downloadBlobAsAttachment).toHaveBeenCalled())
    expect(document.getElementById('atlas-export-menu')?.parentElement).toBe(document.getElementById('atlas-export-wrap'))
    expect(document.getElementById('atlas-export-menu-btn')?.getAttribute('aria-expanded')).toBe('false')
    expect(apiFetch).toHaveBeenCalledWith(
      '/atlas/entities/export?format=csv&type=port&q=443&project_id=prj_1&orphan_filter=hide&suppression_filter=hide',
      expect.objectContaining({ cache: 'no-store' }),
    )
    expect(downloadBlobAsAttachment).toHaveBeenCalledWith(
      expect.any(Blob),
      'darklab-atlas-entities.csv',
    )
    expect(showToast).toHaveBeenCalledWith('Atlas CSV export started', 'success')
  })
})
