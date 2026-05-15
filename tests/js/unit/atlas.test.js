import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

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

function setupAtlasDom() {
  document.body.innerHTML = `
    <input id="cmd" />
    <div id="atlas-overlay" class="mobile-sheet-overlay u-hidden" aria-hidden="true">
      <section id="atlas-surface" class="atlas-surface mobile-sheet-surface">
        <button type="button" class="atlas-close">close</button>
        <div id="atlas-subtitle"></div>
        <div id="atlas-tabs"></div>
        <input id="atlas-search" />
        <select id="atlas-finding-status-filter" class="u-hidden"></select>
        <button id="atlas-refresh-btn" type="button">refresh</button>
        <div id="atlas-finding-bulk-row" class="u-hidden">
          <span id="atlas-finding-selection-summary"></span>
          <button id="atlas-finding-select-all" type="button">select all</button>
          <button id="atlas-finding-clear-selection" type="button">clear</button>
          <select id="atlas-finding-bulk-status"></select>
          <button id="atlas-finding-bulk-apply" type="button">apply</button>
        </div>
        <div id="atlas-list"></div>
        <div id="atlas-pagination" class="u-hidden">
          <span id="atlas-pagination-summary"></span>
          <button id="atlas-prev-btn" type="button">previous</button>
          <button id="atlas-next-btn" type="button">next</button>
        </div>
        <aside id="atlas-detail"></aside>
      </section>
    </div>
  `
}

function loadAtlas({
  activeProject = null,
  apiFetchImpl = null,
} = {}) {
  const showToast = vi.fn()
  const apiFetch = apiFetchImpl || vi.fn((url, options = {}) => {
    const target = String(url)
    if (target === '/atlas') {
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
    if (target === '/atlas/entities/ent_ip') {
      return Promise.resolve(jsonResponse({
        entity: ENTITY,
        intel_snapshots: [{
          provider: 'Shodan',
          status: 'ok',
          summary: '2 open ports',
          fetched_at: '2026-05-15T00:02:00Z',
        }],
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
        'app/static/js/features/atlas/atlas_entity_detail.js',
        'app/static/js/features/atlas/atlas_overlay.js',
      ],
      {
        document,
        window,
        apiFetch,
        fetch: apiFetch,
        showToast,
        URLSearchParams,
        setTimeout,
        clearTimeout,
        getActiveProjectContext: () => activeProject,
        refreshActiveProjectContext: vi.fn(() => Promise.resolve(activeProject)),
        refocusComposerAfterAction: vi.fn(),
      },
      `{
        apiFetch,
        showToast,
        openAtlas: window.openAtlas,
        closeAtlas: window.closeAtlas,
        isAtlasOverlayOpen: window.isAtlasOverlayOpen,
      }`,
      `
        window.apiFetch = apiFetch;
        window.showToast = showToast;
        window.getActiveProjectContext = getActiveProjectContext;
        window.refreshActiveProjectContext = refreshActiveProjectContext;
        window.refocusComposerAfterAction = refocusComposerAfterAction;
      `,
    ),
    apiFetch,
    showToast,
  }
}

describe('Atlas overlay', () => {
  beforeEach(() => {
    setupAtlasDom()
  })

  it('opens as a first-class surface and renders entity detail', async () => {
    const { openAtlas, isAtlasOverlayOpen, apiFetch } = loadAtlas()

    await openAtlas({ source: 'test' })

    expect(isAtlasOverlayOpen()).toBe(true)
    expect(document.getElementById('atlas-overlay')?.classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('atlas-subtitle')?.textContent).toBe('1 entity · 1 finding')
    expect(document.getElementById('atlas-tabs')?.textContent).toContain('Hosts/IPs1')
    expect(document.getElementById('atlas-list')?.textContent).toContain('107.178.109.44')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Shodan')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('shodan host 107.178.109.44')
    expect(apiFetch).toHaveBeenCalledWith('/atlas', { cache: 'no-store' })
    expect(apiFetch).toHaveBeenCalledWith('/atlas/entities/ent_ip', { cache: 'no-store' })
  })

  it('adds the selected entity to the active project without leaving the surface', async () => {
    const { openAtlas, isAtlasOverlayOpen, apiFetch, showToast } = loadAtlas({
      activeProject: { id: 'prj_1', name: 'Case Alpha' },
    })

    await openAtlas({ source: 'test' })
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
    expect(isAtlasOverlayOpen()).toBe(true)
  })

  it('applies the project filter when opened from a project', async () => {
    const { openAtlas, apiFetch } = loadAtlas()

    await openAtlas({ source: 'project-workspace', projectId: 'prj_1', projectName: 'Case Alpha' })

    expect(document.getElementById('atlas-subtitle')?.textContent).toBe('1 entity · 1 finding · Case Alpha')
    expect(apiFetch).toHaveBeenCalledWith(
      '/atlas/entities?type=ip&limit=50&offset=0&project_id=prj_1',
      { cache: 'no-store' },
    )
  })

  it('renders the Findings tab and updates review state', async () => {
    const { openAtlas, apiFetch, showToast } = loadAtlas()

    await openAtlas({ source: 'test', tab: 'findings' })

    expect(document.getElementById('atlas-list')?.textContent).toContain('443/tcp open https')
    expect(document.getElementById('atlas-detail')?.textContent).toContain('Evidence')
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
})
