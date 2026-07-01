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
  useRealSelectEnhancer = false,
  activeTeamScopeCanImpl = () => true,
  teamScopeDeniedMessageImpl = action => `View-only team members can't ${action}. Switch to Personal or ask for operator access.`,
} = {}) {
  const showToast = vi.fn()
  const logClientError = vi.fn()
  const syncAppSelect = vi.fn()
  const enhanceAppSelects = vi.fn()
  const downloadBlobAsAttachment = vi.fn()
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
    if (target === '/atlas/entities/ent_ip') {
      return Promise.resolve(jsonResponse({
        entity: ENTITY,
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
          updated_at: '2026-05-15T00:02:00Z',
        },
        runs: [{
          run_id: 'run1',
          command: 'shodan host 107.178.109.44',
          occurrence_count: 2,
          last_seen_at: '2026-05-15T00:01:00Z',
        }],
        findings: [],
        detail_limits: {
          runs: { limit: 50, offset: 0, shown: 1, total: 55, has_more: true },
          findings: { limit: 50, offset: 0, shown: 0, total: 0, has_more: false },
        },
      }))
    }
    if (target === '/atlas/entities/ent_port') {
      return Promise.resolve(jsonResponse({
        entity: PORT_ENTITY,
        import_sources: [],
        intel_snapshots: [],
        intel_summary: { status: 'unsupported', providers_with_data: [], highlights: [] },
        runs: [{
          run_id: 'run-port',
          command: 'nmap example.com',
          occurrence_count: 1,
          last_seen_at: '2026-05-15T00:01:00Z',
        }],
        findings: [],
        detail_limits: {
          runs: { limit: 50, offset: 0, shown: 1, total: 1, has_more: false },
          findings: { limit: 50, offset: 0, shown: 0, total: 0, has_more: false },
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
        openProjectAutoPromoteRuleFromAtlas: openProjectAutoPromoteRuleFromAtlasImpl,
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
        window.getActiveProjectContext = getActiveProjectContext;
        window.refreshActiveProjectContext = refreshActiveProjectContext;
        window.refocusComposerAfterAction = refocusComposerAfterAction;
        window.openProjectAutoPromoteRuleFromAtlas = openProjectAutoPromoteRuleFromAtlas;
        window.downloadBlobAsAttachment = downloadBlobAsAttachment;
        window.activeTeamScopeCan = activeTeamScopeCan;
        window.teamScopeDeniedMessage = teamScopeDeniedMessage;
      `,
    )
  Object.assign(window, {
    DarklabAtlasOverlay: atlasFns.DarklabAtlasOverlay,
    openAtlas: atlasFns.openAtlas,
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
    syncAppSelect,
    enhanceAppSelects,
    downloadBlobAsAttachment,
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
    const { openAtlas, isAtlasOverlayOpen, apiFetch, showToast } = loadAtlas()

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
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Intel summary')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Open ports')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('80, 443')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Created by Nuclei JSONL import')
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
    expect(document.getElementById('atlas-detail')?.textContent).toContain('1-1 of 55 source runs')
    expect(document.querySelector('.atlas-shell')?.dataset.atlasMode).toBe('entity')
    expect(document.querySelector('#atlas-detail .atlas-detail-action-menu-trigger')?.textContent).toBe('Actions')
    expect(document.querySelector('#atlas-detail .atlas-detail-action-menu-list')?.textContent).toContain('Suppress entity')
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

    await openAtlas({ source: 'test', tab: 'ip' })
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
      { source_run_id: 'run1', sibling_cleanup: { has_cleanup: true, entities: 1, findings: 0, curated_total: 0 } },
      {
        source_run_id: 'run1',
        sibling_cleanup: {
          has_cleanup: true,
          entities: 1,
          findings: 1,
          curated_entities: 1,
          curated_findings: 1,
          curated_total: 2,
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

    await openAtlas({ source: 'test', tab: 'ip' })
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
    expect(noCuratedContent.textContent).toContain('This will remove 1 entity and 0 findings.')
    expect(noCuratedContent.textContent).not.toContain('will be kept')

    deleteBtn()?.click()
    await Promise.resolve()
    await Promise.resolve()
    const curatedContent = showConfirm.mock.calls[2][0].content
    expect(curatedContent.querySelector('input[type="checkbox"]')).not.toBeNull()
    expect(curatedContent.textContent).toContain('Also delete curated single-source Atlas items')
    expect(curatedContent.textContent).toContain('1 curated entity and 1 curated finding will be kept unless this is checked.')
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

  it('enables entity pagination once the list loads even when detail is still loading', async () => {
    let detailRequested = false
    const apiFetch = vi.fn((url) => {
      const target = String(url)
      if (target === '/atlas' || target.startsWith('/atlas?')) {
        return Promise.resolve(jsonResponse({
          total: 436,
          counts: { ip: 0, domain: 30, hash: 0, cve: 0, url: 0 },
          findings: 0,
        }))
      }
      if (target.startsWith('/atlas/entities?')) {
        return Promise.resolve(jsonResponse({
          entities: [{ ...ENTITY, id: 'ent_domain', type: 'domain', canonical_value: 'darklab.sh' }],
          total: 436,
          limit: 50,
          offset: 0,
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
      expect(document.getElementById('atlas-pagination-summary')?.textContent).toBe('1-50 of 436')
    })
    expect(detailRequested).toBe(true)
    expect(document.getElementById('atlas-next-btn')?.disabled).toBe(false)
  })

  it('clears entity pagination when switching from a large tab to a single-page tab', async () => {
    const apiFetch = vi.fn((url) => {
      const target = String(url)
      if (target === '/atlas' || target.startsWith('/atlas?')) {
        return Promise.resolve(jsonResponse({
          total: 466,
          counts: { ip: 0, domain: 30, hash: 436, cve: 0, url: 0 },
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
      if (target === '/atlas/entities/ent_hash' || target === '/atlas/entities/ent_domain') {
        const entity = target.endsWith('ent_hash')
          ? { ...ENTITY, id: 'ent_hash', type: 'hash', canonical_value: 'a'.repeat(64) }
          : { ...ENTITY, id: 'ent_domain', type: 'domain', canonical_value: 'darklab.sh' }
        return Promise.resolve(jsonResponse({
          entity,
          intel_snapshots: [],
          intel_summary: { status: 'none', providers_with_data: [], highlights: [] },
          runs: [],
          findings: [],
        }))
      }
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: 'not found' }) })
    })
    const { openAtlas } = loadAtlas({ apiFetchImpl: apiFetch })

    await openAtlas({ source: 'test', tab: 'hash' })
    expect(document.getElementById('atlas-pagination-summary')?.textContent).toBe('1-50 of 436')

    document.querySelector('[data-atlas-tab="domain"]')?.click()

    await vi.waitFor(() => {
      expect(document.getElementById('atlas-list')?.textContent).toContain('darklab.sh')
    })
    expect(document.getElementById('atlas-pagination')?.classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('atlas-pagination-summary')?.textContent).toBe('')
    expect(document.getElementById('atlas-next-btn')?.disabled).toBe(true)
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

  it('exports filtered entity rows without leaving the Atlas surface', async () => {
    const { openAtlas, apiFetch, downloadBlobAsAttachment, showToast } = loadAtlas()

    await openAtlas({ source: 'project-workspace', projectId: 'prj_1', projectName: 'Case Alpha', tab: 'port' })
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
    await openAtlas({ source: 'project-workspace', projectId: 'prj_1', projectName: 'Case Alpha', tab: 'port' })
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
