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
  run_links: [{ run_id: 'run1', command: 'nmap 107.178.109.44' }],
}

const FINDING = {
  id: 'fnd_1',
  title: '443/tcp open https',
  raw_line: '443/tcp open https',
  review_state: 'new',
  status: 'new',
  severity: 'medium',
  entity_id: 'ent_ip',
  entity_type: 'ip',
  entity_value: '107.178.109.44',
  run_id: 'run1',
  run_command: 'nmap 107.178.109.44',
  occurrence_count: 1,
}

const TABS = [
  { id: 'findings', label: 'Findings' },
  { id: 'ip', label: 'Hosts/IPs' },
  { id: 'domain', label: 'Domains' },
]

function setupMobileAtlasDom() {
  document.body.className = 'mobile-terminal-mode'
  document.body.innerHTML = `
    <div id="atlas-mobile-root" class="atlas-mobile-root u-hidden">
      <div id="atlas-mobile-list-view" class="atlas-mobile-list-view">
        <div class="atlas-mobile-tabs-wrap">
          <div id="atlas-mobile-tabs" class="atlas-mobile-tabs tab-strip" role="tablist"></div>
        </div>
        <div id="atlas-mobile-tools" class="atlas-mobile-tools"></div>
        <div id="atlas-mobile-bulk-bar" class="atlas-mobile-bulk-bar u-hidden"></div>
        <div id="atlas-mobile-list" class="atlas-mobile-list"></div>
        <div id="atlas-mobile-pagination" class="atlas-mobile-pagination u-hidden"></div>
      </div>
      <div id="atlas-mobile-entity-view" class="atlas-mobile-detail-view u-hidden">
        <div id="atlas-mobile-entity-topbar" class="atlas-mobile-detail-topbar"></div>
        <div id="atlas-mobile-entity-body" class="atlas-mobile-detail-body"></div>
        <div id="atlas-mobile-entity-footer" class="atlas-mobile-detail-footer"></div>
      </div>
      <div id="atlas-mobile-finding-view" class="atlas-mobile-detail-view u-hidden">
        <div id="atlas-mobile-finding-topbar" class="atlas-mobile-detail-topbar"></div>
        <div id="atlas-mobile-finding-body" class="atlas-mobile-detail-body"></div>
        <div id="atlas-mobile-finding-footer" class="atlas-mobile-detail-footer"></div>
      </div>
    </div>
  `
}

function createController(overrides = {}) {
  let renderer = null
  const state = {
    activeTab: 'ip',
    summary: { counts: { ip: 1, domain: 1200, hash: 0, cve: 0, url: 0 }, findings: 1 },
    entities: [{ ...ENTITY }],
    findings: [{ ...FINDING }],
    selectedId: '',
    selectedFindingId: '',
    selectedEntityIds: new Set(),
    selectedFindingIds: new Set(),
    detail: null,
    detailLoading: false,
    loading: false,
    selectMode: false,
    query: '',
    findingStatus: '',
    orphanFilter: 'hide',
    offset: 0,
    limit: 50,
    total: 1,
    ...overrides.state,
  }
  const controller = {
    state,
    tabsApi: {
      tabs: TABS,
      countForTab: (tab, summary) => {
        if (tab.id === 'findings') return summary.findings || 0
        return summary.counts?.[tab.id] || 0
      },
    },
    findingStates: [
      ['new', 'New'],
      ['reviewed', 'Reviewed'],
      ['important', 'Important'],
      ['false_positive', 'False positive'],
      ['needs_followup', 'Follow-up'],
    ],
    detailApi: {
      renderDetail: (host, detail) => {
        host.replaceChildren()
        const el = document.createElement('div')
        el.textContent = `entity detail ${detail.entity?.canonical_value || ''}`
        host.appendChild(el)
      },
      renderFindingDetail: (host, finding) => {
        host.replaceChildren()
        const el = document.createElement('div')
        el.textContent = `finding detail ${finding.title || ''}`
        host.appendChild(el)
      },
      reviewStateSelect: (value, onChange) => {
        const select = document.createElement('select')
        select.className = 'form-select form-control-compact'
        ;['new', 'reviewed', 'important'].forEach((stateValue) => {
          const option = document.createElement('option')
          option.value = stateValue
          option.textContent = stateValue
          select.appendChild(option)
        })
        select.value = value
        select.addEventListener('change', () => onChange(select.value))
        return select
      },
    },
    rowMessage: (text) => {
      const row = document.createElement('div')
      row.className = 'atlas-empty'
      row.textContent = text
      return row
    },
    currentTab: () => TABS.find(tab => tab.id === state.activeTab) || TABS[0],
    text: (value, fallback = '') => String(value || fallback || ''),
    countLabel: (count, singular, plural) => `${count} ${count === 1 ? singular : plural}`,
    badge: (text) => {
      const badge = document.createElement('span')
      badge.className = 'badge'
      badge.textContent = text
      return badge
    },
    registerMobileRenderer: (fn) => { renderer = fn },
    setActiveAtlasTab: vi.fn((tabId) => {
      state.activeTab = tabId
      state.selectedId = ''
      state.selectedFindingId = ''
      state.selectedEntityIds.clear()
      state.selectedFindingIds.clear()
      renderer?.(state)
    }),
    refreshAtlas: vi.fn(() => Promise.resolve()),
    setSelectMode: vi.fn((enabled) => {
      state.selectMode = !!enabled
      state.selectedEntityIds.clear()
      state.selectedFindingIds.clear()
      renderer?.(state)
    }),
    selectEntity: vi.fn((id) => {
      state.selectedId = String(id)
      state.detail = { entity: state.entities.find(entity => String(entity.id) === String(id)) || ENTITY }
      renderer?.(state)
    }),
    selectFinding: vi.fn((id) => {
      state.selectedFindingId = String(id)
      renderer?.(state)
    }),
    toggleItemSelection: vi.fn((item, explicit = null) => {
      const selected = state.activeTab === 'findings' ? state.selectedFindingIds : state.selectedEntityIds
      const id = String(item.id || '')
      const shouldSelect = explicit === null ? !selected.has(id) : !!explicit
      if (shouldSelect) selected.add(id)
      else selected.delete(id)
      renderer?.(state)
    }),
    selectAllVisibleItems: vi.fn(() => {
      const selected = state.activeTab === 'findings' ? state.selectedFindingIds : state.selectedEntityIds
      const visible = state.activeTab === 'findings' ? state.findings : state.entities
      visible.forEach(item => selected.add(String(item.id || '')))
      renderer?.(state)
    }),
    bulkUpdateFindings: vi.fn(),
    bulkDeleteSelectedItems: vi.fn(),
    exportEntities: vi.fn(),
    openSourceRun: vi.fn(),
    updateFindingReviewState: vi.fn(),
    openEntityFromFinding: vi.fn((finding) => {
      state.activeTab = finding.entity_type || 'ip'
      state.selectedId = finding.entity_id || ''
      state.detail = { entity: ENTITY }
      renderer?.(state)
    }),
    confirmDeleteEntity: vi.fn(),
    confirmDeleteFinding: vi.fn(),
    refreshIntel: vi.fn(),
    addToActiveProject: vi.fn(),
    removeProjectLink: vi.fn(),
    saveMetadata: vi.fn(),
    ...overrides.controller,
  }
  return { controller, render: () => renderer?.(state), state }
}

function loadMobileAtlas(controller) {
  return fromDomScripts(
    [
      'app/static/js/ui/ui_action_sheet.js',
      'app/static/js/features/atlas/atlas_mobile.js',
    ],
    {
      document,
      window,
      setTimeout,
      clearTimeout,
      Date,
      MutationObserver,
      CustomEvent,
      getActiveProjectContext: vi.fn(() => ({ id: 'prj_1', name: 'Case Alpha' })),
      showToast: vi.fn(),
      openEntityMetadataEditor: vi.fn(),
      copyTextToClipboard: vi.fn(() => Promise.resolve()),
      controller,
    },
    `{
      mobile: window.DarklabAtlasMobile,
      openActionSheet: window.openActionSheet,
      closeActionSheet: window.closeActionSheet,
      controller: window.DarklabAtlasOverlay,
    }`,
    `window.DarklabAtlasOverlay = controller;`,
  )
}

describe('Mobile Atlas controller', () => {
  beforeEach(() => {
    setupMobileAtlasDom()
  })

  it('renders mobile tabs and drills into entity detail with Back preserving the list', () => {
    const { controller, render } = createController()
    const { mobile } = loadMobileAtlas(controller)

    render()

    expect(document.body.classList.contains('atlas-mobile-ready')).toBe(true)
    expect(document.getElementById('atlas-mobile-root')?.classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('atlas-mobile-tabs')?.textContent).toContain('Hosts/IPs1')
    expect(document.getElementById('atlas-mobile-tabs')?.textContent).toContain('Domains999+')
    expect(document.getElementById('atlas-mobile-list')?.textContent).toContain('107.178.109.44')
    expect(mobile.currentView()).toBe('list')

    document.querySelector('.atlas-mobile-row')?.click()

    expect(controller.selectEntity).toHaveBeenCalledWith('ent_ip')
    expect(mobile.currentView()).toBe('entity')
    expect(document.getElementById('atlas-mobile-entity-body')?.textContent).toContain('entity detail 107.178.109.44')

    document.querySelector('#atlas-mobile-entity-topbar .atlas-mobile-back-btn')?.click()

    expect(mobile.currentView()).toBe('list')
    expect(document.getElementById('atlas-mobile-list')?.textContent).toContain('107.178.109.44')
  })

  it('syncs filter disclosure controls and clears selected rows before refreshing', () => {
    const { controller, render, state } = createController()
    loadMobileAtlas(controller)
    state.selectedEntityIds.add('ent_ip')

    render()
    document.querySelector('.atlas-mobile-filters-toggle')?.click()
    const orphan = document.querySelector('.atlas-mobile-orphan-filter')
    orphan.value = 'only'
    orphan.dispatchEvent(new Event('change', { bubbles: true }))

    expect(state.orphanFilter).toBe('only')
    expect(state.selectedEntityIds.size).toBe(0)
    expect(controller.refreshAtlas).toHaveBeenCalledWith({ resetOffset: true })

    render()
    expect(document.querySelector('.atlas-mobile-filters-toggle')?.textContent).toContain('Filters (1)')
    expect(document.querySelector('.atlas-mobile-orphan-chip')?.textContent).toContain('orphans only')

    document.querySelector('.atlas-mobile-orphan-chip')?.click()
    expect(state.orphanFilter).toBe('hide')
    expect(controller.refreshAtlas).toHaveBeenCalledWith({ resetOffset: true })
  })

  it('enters select mode from the action sheet and uses row taps for bulk selection', () => {
    const { controller, render, state } = createController()
    loadMobileAtlas(controller)

    render()
    document.querySelector('.atlas-mobile-overflow-btn')?.click()
    ;[...document.querySelectorAll('.action-sheet-item')]
      .find(button => button.textContent === 'Select mode')
      ?.click()

    expect(controller.setSelectMode).toHaveBeenCalledWith(true)
    expect(document.getElementById('atlas-mobile-bulk-bar')?.classList.contains('u-hidden')).toBe(false)

    document.querySelector('.atlas-mobile-row')?.click()

    expect(state.selectedEntityIds.has('ent_ip')).toBe(true)
    expect(controller.selectEntity).not.toHaveBeenCalled()

    document.querySelector('#atlas-mobile-bulk-bar .btn-danger')?.click()
    expect(controller.bulkDeleteSelectedItems).toHaveBeenCalledTimes(1)
  })

  it('opens finding detail and keeps review updates in the sticky footer', () => {
    const { controller, render } = createController({ state: { activeTab: 'findings' } })
    const { mobile } = loadMobileAtlas(controller)

    render()
    document.querySelector('.atlas-mobile-row')?.click()

    expect(controller.selectFinding).toHaveBeenCalledWith('fnd_1')
    expect(mobile.currentView()).toBe('finding')
    expect(document.getElementById('atlas-mobile-finding-body')?.textContent).toContain('finding detail')
    const review = document.querySelector('#atlas-mobile-finding-footer select')
    review.value = 'reviewed'
    review.dispatchEvent(new Event('change', { bubbles: true }))

    expect(controller.updateFindingReviewState).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'fnd_1' }),
      'reviewed',
    )
  })

  it('honors forceView detail requests once the selected entity is resolved', () => {
    const { controller, render, state } = createController({
      state: {
        selectedId: 'ent_ip',
        detail: { entity: ENTITY },
        requestedView: 'detail',
        requestedViewStarted: Date.now(),
      },
    })
    const { mobile } = loadMobileAtlas(controller)

    render()

    expect(mobile.currentView()).toBe('entity')
    expect(state.requestedView).toBe('')
  })
})
