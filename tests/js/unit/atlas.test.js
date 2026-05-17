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

function deferred() {
  let resolve
  let reject
  const promise = new Promise((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })
  return { promise, resolve, reject }
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
        <select id="atlas-finding-status-filter" class="form-select form-control-compact u-hidden"></select>
        <select id="atlas-orphan-filter" class="form-select form-control-compact"></select>
        <button id="atlas-export-csv-btn" type="button">csv</button>
        <button id="atlas-export-jsonl-btn" type="button">jsonl</button>
        <button id="atlas-refresh-btn" type="button">refresh</button>
        <div class="atlas-shell">
          <div id="atlas-finding-bulk-row" class="u-hidden">
            <label><input id="atlas-select-toggle" type="checkbox">select</label>
            <span id="atlas-finding-selection-summary"></span>
            <button id="atlas-finding-select-all" type="button">select all</button>
            <button id="atlas-finding-clear-selection" type="button">clear</button>
            <select id="atlas-finding-bulk-status" class="form-select form-control-compact"></select>
            <button id="atlas-finding-bulk-apply" type="button">apply</button>
            <button id="atlas-bulk-delete" type="button">delete</button>
          </div>
          <div id="atlas-list"></div>
          <div id="atlas-pagination" class="u-hidden">
            <span id="atlas-pagination-summary"></span>
            <button id="atlas-prev-btn" type="button">previous</button>
            <button id="atlas-next-btn" type="button">next</button>
          </div>
          <aside id="atlas-detail"></aside>
        </div>
      </section>
    </div>
  `
}

function loadAtlas({
  activeProject = null,
  apiFetchImpl = null,
  showConfirmImpl = vi.fn(() => Promise.resolve('cancel')),
  useRealSelectEnhancer = false,
} = {}) {
  const showToast = vi.fn()
  const syncAppSelect = vi.fn()
  const enhanceAppSelects = vi.fn()
  const downloadBlobAsAttachment = vi.fn()
  const storage = new MemoryStorage()
  const projectEvents = []
  const apiFetch = apiFetchImpl || vi.fn((url, options = {}) => {
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
    if (target === '/findings/fnd_1/review' && options.method === 'PUT') {
      return Promise.resolve(jsonResponse({ ok: true, finding: { ...FINDING, review_state: 'reviewed', status: 'reviewed' } }))
    }
    if (target === '/atlas/findings/review' && options.method === 'POST') {
      return Promise.resolve(jsonResponse({ ok: true, counts: { updated: 1, not_found: 0 }, results: [] }))
    }
    if (target.startsWith('/atlas/entities?')) {
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
    if (target === '/atlas/entities/ent_ip') {
      return Promise.resolve(jsonResponse({
        entity: ENTITY,
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
      }))
    }
    if (target === '/atlas/entities/ent_ip/project_links' && options.method === 'POST') {
      return Promise.resolve(jsonResponse({ ok: true }))
    }
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: 'not found' }) })
  })

  return {
    ...fromDomScripts(
      [
        'app/static/js/ui/ui_entity_metadata.js',
        'app/static/js/features/atlas/atlas_tabs.js',
        'app/static/js/features/atlas/atlas_entity_row.js',
        'app/static/js/features/atlas/atlas_entity_detail.js',
        'app/static/js/features/atlas/atlas_overlay.js',
      ],
      {
        document,
        window,
        apiFetch,
        fetch: apiFetch,
        showToast,
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
        downloadBlobAsAttachment,
      },
      `{
        apiFetch,
        showToast,
        downloadBlobAsAttachment,
        openAtlas: window.openAtlas,
        closeAtlas: window.closeAtlas,
        isAtlasOverlayOpen: window.isAtlasOverlayOpen,
        cycleAtlasTab: window.cycleAtlasTab,
      }`,
      `
        window.apiFetch = apiFetch;
        window.showToast = showToast;
        window.showConfirm = showConfirm;
        if (!useRealSelectEnhancer) {
          window.syncAppSelect = syncAppSelect;
          window.enhanceAppSelects = enhanceAppSelects;
        }
        window.emitUiEvent = emitUiEvent;
        window.getActiveProjectContext = getActiveProjectContext;
        window.refreshActiveProjectContext = refreshActiveProjectContext;
        window.refocusComposerAfterAction = refocusComposerAfterAction;
        window.downloadBlobAsAttachment = downloadBlobAsAttachment;
      `,
    ),
    apiFetch,
    showConfirm: showConfirmImpl,
    showToast,
    syncAppSelect,
    enhanceAppSelects,
    downloadBlobAsAttachment,
    projectEvents,
    storage,
  }
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

  it('syncs populated filter selects and enhances dynamic detail selects', async () => {
    const { openAtlas } = loadAtlas({ useRealSelectEnhancer: true })

    await openAtlas({ source: 'test' })

    const filter = document.getElementById('atlas-finding-status-filter')
    expect(filter.classList.contains('app-select-native')).toBe(true)
    expect(filter.nextElementSibling?.classList.contains('app-select')).toBe(true)
    expect(filter.nextElementSibling?.textContent).toContain('All findings')
    expect(filter.nextElementSibling?.querySelectorAll('.dropdown-item')).toHaveLength(6)

    const review = document.querySelector('#atlas-detail .atlas-finding-review')
    expect(review).not.toBeNull()
    expect(review.classList.contains('app-select-native')).toBe(true)
    expect(review.nextElementSibling?.classList.contains('app-select')).toBe(true)
    expect(review.nextElementSibling?.querySelector('.app-select-trigger')?.textContent).toContain('New')
    expect(review.nextElementSibling?.querySelectorAll('.dropdown-item')).toHaveLength(5)
  })

  it('opens as a first-class surface and renders entity detail', async () => {
    const { openAtlas, isAtlasOverlayOpen, apiFetch } = loadAtlas()

    await openAtlas({ source: 'test', tab: 'ip' })

    expect(isAtlasOverlayOpen()).toBe(true)
    expect(document.getElementById('atlas-overlay')?.classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('atlas-subtitle')?.textContent).toBe('1 entity · 1 finding')
    expect(document.getElementById('atlas-tabs')?.textContent).toContain('Hosts/IPs1')
    expect(document.getElementById('atlas-tabs')?.classList.contains('tab-strip')).toBe(true)
    expect(document.querySelector('[data-atlas-tab="ip"]')?.classList.contains('tab-strip-item')).toBe(true)
    expect(document.querySelector('[data-atlas-tab="ip"]')?.classList.contains('is-active')).toBe(true)
    expect(document.querySelector('[data-atlas-tab="ip"]')?.getAttribute('aria-pressed')).toBe('true')
    expect(document.getElementById('atlas-list')?.textContent).toContain('107.178.109.44')
    expect(document.getElementById('atlas-list')?.textContent).toContain('2 hits · 1 run')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Shodan')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Intel summary')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Open ports')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('80, 443')
    expect(document.querySelectorAll('.atlas-intel-highlight-provider')).toHaveLength(2)
    expect(document.querySelector('.atlas-intel-highlight-provider')?.textContent).toContain('CVE-2026-0001')
    const intelToggle = document.querySelector('.atlas-intel-card-toggle')
    expect(intelToggle?.classList.contains('btn')).toBe(true)
    expect(intelToggle?.classList.contains('btn-ghost')).toBe(true)
    expect(intelToggle?.getAttribute('aria-expanded')).toBe('false')
    expect(document.querySelector('.atlas-intel-card-body')?.classList.contains('u-hidden')).toBe(true)
    intelToggle?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(intelToggle?.getAttribute('aria-expanded')).toBe('true')
    expect(document.querySelector('.atlas-intel-card-body')?.classList.contains('u-hidden')).toBe(false)
    expect(document.querySelector('.atlas-intel-card-body')?.textContent).toContain('ports')
    expect(document.querySelector('.atlas-intel-card-body')?.textContent).toContain('nginx')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('shodan host 107.178.109.44')
    expect(document.querySelector('.atlas-shell')?.dataset.atlasMode).toBe('entity')
    expect(document.getElementById('atlas-finding-status-filter')?.classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('atlas-finding-bulk-row')?.classList.contains('u-hidden')).toBe(false)
    expect(apiFetch).toHaveBeenCalledWith('/atlas?orphan_filter=hide', { cache: 'no-store' })
    expect(apiFetch).toHaveBeenCalledWith('/atlas/entities/ent_ip', { cache: 'no-store' })
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
    expect(apiFetch).not.toHaveBeenCalledWith('/atlas/entities/ent_ip', { cache: 'no-store' })
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
      { source_run_id: 'run1', sibling_cleanup: { has_cleanup: true, entities: 1, findings: 1, curated_total: 2 } },
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
    const deleteBtn = () => [...document.querySelectorAll('#atlas-detail .atlas-detail-actions button')]
      .find(button => button.textContent === 'Delete')

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
    expect(curatedContent.textContent).toContain('2 curated items will be kept.')
  })

  it('applies the project filter when opened from a project', async () => {
    const { openAtlas, apiFetch } = loadAtlas()

    await openAtlas({ source: 'project-workspace', projectId: 'prj_1', projectName: 'Case Alpha' })

    expect(document.getElementById('atlas-subtitle')?.textContent).toBe('1 entity · 1 finding · Case Alpha')
    expect(apiFetch).toHaveBeenCalledWith(
      '/atlas/findings?limit=50&offset=0&project_id=prj_1&orphan_filter=hide',
      { cache: 'no-store' },
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
        '/atlas/entities?type=hash&limit=50&offset=0&orphan_filter=hide',
        { cache: 'no-store' },
      )
    })
    document.querySelector('[data-atlas-tab="domain"]')?.click()
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

    await openAtlas({ source: 'project-workspace', projectId: 'prj_1', projectName: 'Case Alpha', tab: 'ip' })
    const search = document.getElementById('atlas-search')
    search.value = '107.178'
    search.dispatchEvent(new Event('input', { bubbles: true }))
    document.getElementById('atlas-export-csv-btn')?.click()

    await vi.waitFor(() => expect(downloadBlobAsAttachment).toHaveBeenCalled())
    expect(apiFetch).toHaveBeenCalledWith(
      '/atlas/entities/export?format=csv&type=ip&q=107.178&project_id=prj_1&orphan_filter=hide',
      { cache: 'no-store' },
    )
    expect(downloadBlobAsAttachment).toHaveBeenCalledWith(
      expect.any(Blob),
      'darklab-atlas-entities.csv',
    )
    expect(showToast).toHaveBeenCalledWith('Atlas CSV export started', 'success')
  })
})
