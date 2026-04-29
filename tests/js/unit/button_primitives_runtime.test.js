import { describe, it, expect, vi } from 'vitest'
import { readFileSync } from 'fs'
import { resolve, dirname, join } from 'path'
import { fileURLToPath } from 'url'
import { MemoryStorage, fromDomScripts } from './helpers/extract.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const FIXTURE_PATH = join(REPO_ROOT, 'tests/js/fixtures/button_primitive_allowlist.json')

const FIXTURE = JSON.parse(readFileSync(FIXTURE_PATH, 'utf8'))
const ALLOWED = new Set(FIXTURE.allowed_primitive_classes)

function hasAllowedPrimitive(el) {
  return Array.from(el.classList).some((cls) => ALLOWED.has(cls))
}

function expectButtonPrimitives(container, label) {
  const violations = []
  for (const el of container.querySelectorAll('button, [role="button"]')) {
    if (hasAllowedPrimitive(el)) continue
    violations.push(`${el.tagName.toLowerCase()}${el.id ? `#${el.id}` : ''} → ${el.outerHTML.slice(0, 120).replace(/\s+/g, ' ')}`)
  }
  expect(violations, label).toEqual([])
}

function mountHistoryHarness() {
  document.body.innerHTML = `
    <div id="history-row"></div>
    <input id="cmd" />
    <div id="history-panel"></div>
    <div id="history-search-input"></div>
    <button id="history-mobile-filters-toggle"></button>
    <div id="history-advanced-filters"></div>
    <input id="history-root-input" />
    <div id="history-root-dropdown"></div>
    <select id="history-exit-filter"></select>
    <select id="history-date-filter"></select>
    <input id="history-starred-toggle" type="checkbox" />
    <button id="history-clear-filters"></button>
    <div id="history-active-filters"></div>
    <div id="history-list"></div>
    <div id="history-pagination" class="u-hidden">
      <div id="history-pagination-summary"></div>
      <div id="history-pagination-controls"></div>
    </div>
    <div id="history-load-overlay"></div>
    <div id="permalink-toast"></div>
    <div id="tabs-bar"></div>
    <div id="tab-panels"></div>
  `

  const historyPanel = document.getElementById('history-panel')
  const historyList = document.getElementById('history-list')
  const historyLoadOverlay = document.getElementById('history-load-overlay')
  const historySearchInput = document.getElementById('history-search-input')
  const historyMobileFiltersToggle = document.getElementById('history-mobile-filters-toggle')
  const historyAdvancedFilters = document.getElementById('history-advanced-filters')
  const historyRootInput = document.getElementById('history-root-input')
  const historyRootDropdown = document.getElementById('history-root-dropdown')
  const historyExitFilter = document.getElementById('history-exit-filter')
  const historyDateFilter = document.getElementById('history-date-filter')
  const historyStarredToggle = document.getElementById('history-starred-toggle')
  const historyClearFiltersBtn = document.getElementById('history-clear-filters')
  const historyActiveFilters = document.getElementById('history-active-filters')
  const historyPagination = document.getElementById('history-pagination')
  const historyPaginationSummary = document.getElementById('history-pagination-summary')
  const historyPaginationControls = document.getElementById('history-pagination-controls')
  const cmdInput = document.getElementById('cmd')
  window.open = vi.fn()
  const apiFetch = vi.fn((url) => {
    if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ runs: [], roots: [], total_count: 0, page_count: 0, has_prev: false, has_next: false }),
      })
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
  })

  const fns = fromDomScripts(
    ['app/static/js/history.js'],
    {
      document,
      window,
      localStorage: new MemoryStorage(),
      APP_CONFIG: { recent_commands_limit: 50, history_panel_limit: 8 },
      apiFetch,
      navigator: { clipboard: { writeText: () => Promise.resolve() } },
      location: { origin: 'https://example.test' },
      historyPanel,
      historyList,
      historyLoadOverlay,
      historySearchInput,
      historyMobileFiltersToggle,
      historyAdvancedFilters,
      historyRootInput,
      historyRootDropdown,
      historyExitFilter,
      historyDateFilter,
      historyStarredToggle,
      historyClearFiltersBtn,
      historyActiveFilters,
      historyPagination,
      historyPaginationSummary,
      historyPaginationControls,
      histRow: document.getElementById('history-row'),
      showConfirm: vi.fn(() => Promise.resolve(null)),
      cmdInput,
      tabs: [],
      activateTab: vi.fn(),
      createTab: vi.fn(),
      appendLine: vi.fn(),
      appendCommandEcho: vi.fn(),
      setTabStatus: vi.fn(),
      hideTabKillBtn: vi.fn(),
      showToast: vi.fn(),
      refreshHistoryPanel: () => {},
      renderHistory: () => {},
      hideHistoryPanel: vi.fn(),
      confirmHistAction: vi.fn(),
      executeHistAction: vi.fn(),
      useMobileTerminalViewportMode: () => false,
      setComposerValue: vi.fn(),
      refocusComposerAfterAction: vi.fn(),
    },
    '{ _historyRenderPagination, _historyPaging }',
  )

  return { ...fns, historyPaginationControls }
}

function mountMobileHarness() {
  document.body.className = 'mobile-terminal-mode'
  document.body.innerHTML = `
    <div id="mobile-shell">
      <div id="mobile-shell-chrome"></div>
      <div id="mobile-shell-transcript"></div>
      <div id="mobile-shell-composer">
        <div id="mobile-composer-host">
          <div id="mobile-composer-row">
            <input id="mobile-cmd" autocomplete="off" autocapitalize="none" autocorrect="off" spellcheck="false" inputmode="text" />
            <button id="mobile-run-btn"></button>
          </div>
        </div>
      </div>
      <div id="mobile-shell-overlays">
        <div id="mobile-menu-sheet" class="menu-sheet u-hidden">
          <button data-menu-action="history"></button>
        </div>
        <div id="mobile-menu-sheet-scrim"></div>
        <div id="mobile-recents-sheet" class="u-hidden">
          <div id="mobile-recents-sheet-scrim"></div>
          <button id="mobile-recents-clear"></button>
          <input id="mobile-recents-search" autocomplete="off" autocapitalize="none" autocorrect="off" spellcheck="false" inputmode="text" />
          <button id="mobile-recents-filters-toggle"></button>
          <div id="mobile-recents-filters-expanded"></div>
          <input id="mobile-recents-filter-root" autocomplete="off" autocapitalize="none" autocorrect="off" spellcheck="false" inputmode="text" />
          <div id="mobile-recents-chips"></div>
          <div id="mobile-recents-list"></div>
          <div id="mobile-recents-pagination" class="u-hidden">
            <div id="mobile-recents-pagination-summary"></div>
            <div id="mobile-recents-pagination-controls"></div>
          </div>
        </div>
      </div>
    </div>
    <div id="tabs-bar"></div>
    <div class="terminal-bar">
      <span id="status"></span>
      <span id="run-timer"></span>
    </div>
    <div id="mobile-recent-peek"></div>
  `

  const apiFetch = vi.fn((url) => {
    if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          page: 1,
          page_size: 8,
          total_count: 9,
          page_count: 2,
          has_prev: false,
          has_next: true,
          roots: ['ping'],
          runs: [
            { id: 'run-1', command: 'ping darklab.sh', started: '2026-01-01T00:00:00Z', exit_code: 0 },
          ],
        }),
      })
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
  })

  const globals = {
    document,
    window,
    localStorage: new MemoryStorage(),
    APP_CONFIG: { recent_commands_limit: 50, history_panel_limit: 8 },
    apiFetch,
    navigator: { clipboard: { writeText: () => Promise.resolve() } },
    location: { origin: 'https://example.test', search: '' },
    getTabs: () => [],
    getActiveTabId: () => null,
    activateTab: vi.fn(),
    setComposerValue: vi.fn(),
    confirmHistAction: vi.fn(),
    restoreHistoryRunIntoTab: vi.fn(() => Promise.resolve()),
    shareUrl: vi.fn(() => Promise.resolve()),
    showToast: vi.fn(),
    _toggleStar: vi.fn(),
  }

  window.apiFetch = apiFetch
  window.showToast = globals.showToast
  window.confirmHistAction = globals.confirmHistAction
  window.restoreHistoryRunIntoTab = globals.restoreHistoryRunIntoTab
  window.shareUrl = globals.shareUrl
  window.getTabs = globals.getTabs
  window.getActiveTabId = globals.getActiveTabId
  window.activateTab = globals.activateTab
  window.setComposerValue = globals.setComposerValue
  window._toggleStar = globals._toggleStar

  fromDomScripts(
    ['app/static/js/mobile_chrome.js'],
    globals,
    '{}',
  )

  return { apiFetch, mobileMenuHistoryBtn: document.querySelector('[data-menu-action="history"]') }
}

describe('runtime button primitive contract', () => {
  it('history pagination buttons render with allowed primitives', async () => {
    const { _historyRenderPagination, _historyPaging, historyPaginationControls } = mountHistoryHarness()

    await new Promise((resolve) => setImmediate(resolve))
    _historyPaging.page = 4
    _historyPaging.pageSize = 8
    _historyPaging.totalCount = 48
    _historyPaging.pageCount = 6
    _historyPaging.hasPrev = true
    _historyPaging.hasNext = true
    _historyRenderPagination(8)

    expectButtonPrimitives(historyPaginationControls, 'history pagination')
  })

  it('mobile recents pagination buttons render with allowed primitives', async () => {
    const { apiFetch, mobileMenuHistoryBtn } = mountMobileHarness()

  mobileMenuHistoryBtn.click()
  await new Promise((resolve) => setImmediate(resolve))
  await new Promise((resolve) => setImmediate(resolve))

  expect(apiFetch).toHaveBeenCalled()
  expect(document.getElementById('mobile-recents-search')?.getAttribute('autocomplete')).toBe('off')
  expect(document.getElementById('mobile-recents-search')?.getAttribute('autocapitalize')).toBe('none')
  expect(document.getElementById('mobile-recents-search')?.getAttribute('autocorrect')).toBe('off')
  expect(document.getElementById('mobile-recents-search')?.getAttribute('spellcheck')).toBe('false')
  expect(document.getElementById('mobile-recents-search')?.getAttribute('inputmode')).toBe('text')
  expect(document.getElementById('mobile-recents-filter-root')?.getAttribute('autocomplete')).toBe('off')
  expect(document.getElementById('mobile-recents-filter-root')?.getAttribute('autocapitalize')).toBe('none')
  expect(document.getElementById('mobile-recents-filter-root')?.getAttribute('autocorrect')).toBe('off')
  expect(document.getElementById('mobile-recents-filter-root')?.getAttribute('spellcheck')).toBe('false')
  expect(document.getElementById('mobile-recents-filter-root')?.getAttribute('inputmode')).toBe('text')
  expectButtonPrimitives(
    document.getElementById('mobile-recents-pagination-controls'),
    'mobile recents pagination',
  )
  })
})
