import { vi } from 'vitest'
import { MemoryStorage, fromDomScript, fromDomScripts } from './helpers/extract.js'

const _noopFetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({ commands: [] }) })

/**
 * Load star functions with an injectable apiFetch mock. Each call returns a
 * fresh scope so tests stay isolated.
 */
function loadStarHelpers(mockApiFetch = _noopFetch) {
  const storage = new MemoryStorage()
  const fns = fromDomScript(
    'app/static/js/history.js',
    { localStorage: storage, APP_CONFIG: { recent_commands_limit: 20 }, apiFetch: mockApiFetch },
    '_getStarred', '_saveStarred', '_toggleStar', 'loadStarredFromServer'
  )
  return { ...fns, _storage: storage }
}

// ── _getStarred ───────────────────────────────────────────────────────────────
// Returns the in-memory cache when populated, else an empty Set. Never reads
// localStorage — a stale `starred` key from before stars moved server-side
// would otherwise mask the user's server-side stars during the brief window
// before loadStarredFromServer() resolves.

describe('_getStarred', () => {
  it('returns an empty Set when cache is null', () => {
    const { _getStarred } = loadStarHelpers()
    expect(_getStarred()).toEqual(new Set())
  })

  it('returns cache when cache is populated', () => {
    const { _getStarred, _saveStarred } = loadStarHelpers()
    _saveStarred(new Set(['alpha', 'beta']))
    expect(_getStarred()).toEqual(new Set(['alpha', 'beta']))
  })

  it('ignores localStorage even when the starred key is set', () => {
    const { _getStarred, _storage } = loadStarHelpers()
    _storage.setItem('starred', JSON.stringify(['from-storage']))
    expect(_getStarred()).toEqual(new Set())
  })

  it('ignores localStorage even after the cache has been populated', () => {
    const { _getStarred, _saveStarred, _storage } = loadStarHelpers()
    _storage.setItem('starred', JSON.stringify(['from-storage']))
    _saveStarred(new Set(['from-cache']))
    expect(_getStarred()).toEqual(new Set(['from-cache']))
  })
})

// ── _saveStarred ──────────────────────────────────────────────────────────────
// Updates the in-memory cache only — does not write to localStorage.

describe('_saveStarred', () => {
  it('updates the in-memory cache', () => {
    const { _getStarred, _saveStarred } = loadStarHelpers()
    _saveStarred(new Set(['alpha', 'beta']))
    expect(_getStarred()).toEqual(new Set(['alpha', 'beta']))
  })

  it('setting an empty Set makes _getStarred return an empty Set', () => {
    const { _getStarred, _saveStarred } = loadStarHelpers()
    _saveStarred(new Set(['x']))
    _saveStarred(new Set())
    expect(_getStarred()).toEqual(new Set())
  })

  it('round-trips correctly through _getStarred', () => {
    const { _getStarred, _saveStarred } = loadStarHelpers()
    _saveStarred(new Set(['cmd1', 'cmd2']))
    expect(_getStarred()).toEqual(new Set(['cmd1', 'cmd2']))
  })

  it('does not write to localStorage', () => {
    const { _saveStarred, _storage } = loadStarHelpers()
    _saveStarred(new Set(['cmd']))
    expect(_storage.getItem('starred')).toBeNull()
  })
})

// ── _toggleStar ───────────────────────────────────────────────────────────────

describe('_toggleStar', () => {
  it('adds a command that is not yet starred', () => {
    const { _toggleStar, _getStarred } = loadStarHelpers()
    _toggleStar('ls -la')
    expect(_getStarred().has('ls -la')).toBe(true)
  })

  it('removes a command that is already starred', () => {
    const { _toggleStar, _saveStarred, _getStarred } = loadStarHelpers()
    _saveStarred(new Set(['ls -la']))
    _toggleStar('ls -la')
    expect(_getStarred().has('ls -la')).toBe(false)
  })

  it('does not affect other starred commands when removing one', () => {
    const { _toggleStar, _saveStarred, _getStarred } = loadStarHelpers()
    _saveStarred(new Set(['cmd1', 'cmd2']))
    _toggleStar('cmd1')
    const s = _getStarred()
    expect(s.has('cmd1')).toBe(false)
    expect(s.has('cmd2')).toBe(true)
  })

  it('toggling the same command twice returns it to its original state', () => {
    const { _toggleStar, _saveStarred, _getStarred } = loadStarHelpers()
    _saveStarred(new Set(['cmd1']))
    _toggleStar('cmd1')
    _toggleStar('cmd1')
    expect(_getStarred().has('cmd1')).toBe(true)
  })

  it('calls POST when adding a star', () => {
    const calls = []
    const mock = (url, opts) => { calls.push({ url, method: opts?.method }); return Promise.resolve({ ok: true }) }
    const { _toggleStar } = loadStarHelpers(mock)
    _toggleStar('nmap target')
    expect(calls).toHaveLength(1)
    expect(calls[0]).toMatchObject({ url: '/session/starred', method: 'POST' })
  })

  it('calls DELETE when removing a star', () => {
    const calls = []
    const mock = (url, opts) => { calls.push({ url, method: opts?.method }); return Promise.resolve({ ok: true }) }
    const { _toggleStar, _saveStarred } = loadStarHelpers(mock)
    _saveStarred(new Set(['nmap target']))
    _toggleStar('nmap target')
    expect(calls).toHaveLength(1)
    expect(calls[0]).toMatchObject({ url: '/session/starred', method: 'DELETE' })
  })
})

// ── loadStarredFromServer ─────────────────────────────────────────────────────

describe('loadStarredFromServer', () => {
  it('populates the cache from the server response', async () => {
    const mock = () => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ commands: ['dig example.com', 'ping target'] }),
    })
    const { loadStarredFromServer, _getStarred } = loadStarHelpers(mock)
    await loadStarredFromServer()
    expect(_getStarred()).toEqual(new Set(['dig example.com', 'ping target']))
  })

  it('populates cache with an empty Set when server returns empty list', async () => {
    const mock = () => Promise.resolve({ ok: true, json: () => Promise.resolve({ commands: [] }) })
    const { loadStarredFromServer, _getStarred } = loadStarHelpers(mock)
    await loadStarredFromServer()
    expect(_getStarred()).toEqual(new Set())
  })

  it('leaves cache unchanged when server returns a non-ok response', async () => {
    const mock = () => Promise.resolve({ ok: false })
    const { loadStarredFromServer, _saveStarred, _getStarred } = loadStarHelpers(mock)
    _saveStarred(new Set(['pre-existing']))
    await loadStarredFromServer()
    expect(_getStarred()).toEqual(new Set(['pre-existing']))
  })

  it('does not throw when the fetch rejects', async () => {
    const mock = () => Promise.reject(new Error('network error'))
    const { loadStarredFromServer } = loadStarHelpers(mock)
    await expect(loadStarredFromServer()).resolves.toBeUndefined()
  })

  it('after load, _getStarred returns server data and localStorage is ignored', async () => {
    const mock = () => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ commands: ['server-cmd'] }),
    })
    const { loadStarredFromServer, _getStarred, _storage } = loadStarHelpers(mock)
    _storage.setItem('starred', JSON.stringify(['local-cmd']))
    await loadStarredFromServer()
    const starred = _getStarred()
    expect(starred.has('server-cmd')).toBe(true)
    expect(starred.has('local-cmd')).toBe(false)
  })
})

describe('command history hydration', () => {
  function loadHistoryHelpers({ emitUiEvent = vi.fn(), apiFetch = null } = {}) {
    document.body.innerHTML = `
      <div id="history-row"><span class="history-label">Recent:</span></div>
      <input id="cmd" />
      <div id="history-panel"></div>
    `

    const histRow = document.getElementById('history-row')
    const cmdInput = document.getElementById('cmd')
    const historyPanel = document.getElementById('history-panel')
    const activeTab = {
      commandHistory: [],
      historyNavIndex: -1,
      historyNavDraft: '',
    }

    return fromDomScripts(
      ['app/static/js/history.js'],
      {
        document,
        localStorage: new MemoryStorage(),
        APP_CONFIG: { recent_commands_limit: 3 },
        apiFetch: apiFetch || (() => Promise.resolve({ ok: true, json: () => Promise.resolve({ commands: [] }) })),
        histRow,
        cmdInput,
        historyPanel,
        refreshHistoryPanel: vi.fn(),
        useMobileTerminalViewportMode: () => false,
        getActiveTab: () => activeTab,
        emitUiEvent,
        setComposerState: (next) => {
          if (Object.prototype.hasOwnProperty.call(next, 'value'))
            cmdInput.value = String(next.value ?? '')
          if (
            Object.prototype.hasOwnProperty.call(next, 'selectionStart') ||
            Object.prototype.hasOwnProperty.call(next, 'selectionEnd')
          ) {
            const start =
              typeof next.selectionStart === 'number' ? next.selectionStart : cmdInput.value.length
            const end = typeof next.selectionEnd === 'number' ? next.selectionEnd : start
            cmdInput.setSelectionRange(start, end)
          }
        },
      },
      `{
      reloadSessionHistory,
      hydrateCmdHistory,
      addToHistory,
      navigateCmdHistory,
      resetCmdHistoryNav,
      renderHistory,
      getCmdHistory: () => cmdHistory.slice(),
      getTabCommandHistory: () => getActiveTab().commandHistory.slice(),
      getRecentPreviewHistory: () => recentPreviewHistory.slice(),
      emitUiEvent,
    }`,
    )
  }

  it('hydrates unique recent commands from server history as fallback recall', () => {
    const { hydrateCmdHistory, navigateCmdHistory, getCmdHistory, getRecentPreviewHistory } = loadHistoryHelpers()
    const cmdInput = document.getElementById('cmd')

    hydrateCmdHistory([
      { command: 'dig darklab.sh A', exit_code: 0 },
      { command: 'curl -I https://darklab.sh', exit_code: 7 },
      { command: 'dig darklab.sh A', exit_code: 0 },
      { command: 'ping -c 4 darklab.sh', exit_code: 0 },
    ])

    expect(getCmdHistory()).toEqual([
      'dig darklab.sh A',
      'curl -I https://darklab.sh',
      'ping -c 4 darklab.sh',
    ])
    expect(getRecentPreviewHistory()).toEqual([
      'dig darklab.sh A',
      'curl -I https://darklab.sh',
      'ping -c 4 darklab.sh',
    ])

    expect(navigateCmdHistory(1)).toBe(true)
    expect(cmdInput.value).toBe('dig darklab.sh A')
    expect(navigateCmdHistory(1)).toBe(true)
    expect(cmdInput.value).toBe('curl -I https://darklab.sh')
  })

  it('adds commands to both global recents and active tab recall', () => {
    const { addToHistory, navigateCmdHistory, getCmdHistory, getTabCommandHistory } = loadHistoryHelpers()
    const cmdInput = document.getElementById('cmd')

    addToHistory('dig darklab.sh A')
    addToHistory('curl -I https://darklab.sh')

    expect(getCmdHistory()).toEqual(['curl -I https://darklab.sh', 'dig darklab.sh A'])
    expect(getTabCommandHistory()).toEqual(['curl -I https://darklab.sh', 'dig darklab.sh A'])

    expect(navigateCmdHistory(1)).toBe(true)
    expect(cmdInput.value).toBe('curl -I https://darklab.sh')
  })

  it('prefers active tab recall before falling back to global recents', () => {
    const { hydrateCmdHistory, addToHistory, navigateCmdHistory } = loadHistoryHelpers()
    const cmdInput = document.getElementById('cmd')

    hydrateCmdHistory([
      { command: 'whoami' },
      { command: 'status' },
    ])
    addToHistory('dig darklab.sh A')

    expect(navigateCmdHistory(1)).toBe(true)
    expect(cmdInput.value).toBe('dig darklab.sh A')
    expect(navigateCmdHistory(1)).toBe(true)
    expect(cmdInput.value).toBe('whoami')
    expect(navigateCmdHistory(1)).toBe(true)
    expect(cmdInput.value).toBe('status')
    expect(navigateCmdHistory(-1)).toBe(true)
    expect(cmdInput.value).toBe('whoami')
  })

  it('reloads command history from the distinct-command endpoint', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/session/starred') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ commands: [] }) })
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          runs: [
            { command: 'dig darklab.sh A' },
            { command: 'curl -I https://darklab.sh' },
          ],
        }),
      })
    })
    const { reloadSessionHistory, getCmdHistory, getRecentPreviewHistory } = loadHistoryHelpers({ apiFetch })

    await reloadSessionHistory()

    expect(apiFetch).toHaveBeenCalledWith('/history/commands?limit=3')
    expect(getCmdHistory()).toEqual(['dig darklab.sh A', 'curl -I https://darklab.sh'])
    expect(getRecentPreviewHistory()).toEqual(['dig darklab.sh A', 'curl -I https://darklab.sh'])
  })

  it('restores the typed draft after navigating through hydrated history', () => {
    const { addToHistory, navigateCmdHistory } = loadHistoryHelpers()
    const cmdInput = document.getElementById('cmd')

    addToHistory('curl -I https://darklab.sh')
    addToHistory('dig darklab.sh A')

    cmdInput.value = 'pin'
    setComposerState({ value: 'pin', selectionStart: 3, selectionEnd: 3, activeInput: 'desktop' })
    expect(navigateCmdHistory(1)).toBe(true)
    expect(cmdInput.value).toBe('dig darklab.sh A')
    expect(navigateCmdHistory(1)).toBe(true)
    expect(cmdInput.value).toBe('curl -I https://darklab.sh')
    expect(navigateCmdHistory(-1)).toBe(true)
    expect(cmdInput.value).toBe('dig darklab.sh A')
    expect(navigateCmdHistory(-1)).toBe(true)
    expect(cmdInput.value).toBe('pin')
  })

  it('emits a history-rendered event when hydrated history becomes empty', () => {
    const emitUiEvent = vi.fn()
    const { hydrateCmdHistory } = loadHistoryHelpers({ emitUiEvent })

    hydrateCmdHistory([{ command: 'ping darklab.sh', exit_code: 0 }])
    emitUiEvent.mockClear()

    hydrateCmdHistory([])

    expect(emitUiEvent).toHaveBeenCalledWith('app:history-rendered', {
      cmdHistory: [],
      recentPreviewHistory: [],
    })
  })

  it('resetCmdHistoryNav clears navigation state after the user types', () => {
    const { addToHistory, navigateCmdHistory, resetCmdHistoryNav } = loadHistoryHelpers()
    const cmdInput = document.getElementById('cmd')

    addToHistory('curl -I https://darklab.sh')
    addToHistory('dig darklab.sh A')

    expect(navigateCmdHistory(1)).toBe(true)
    expect(cmdInput.value).toBe('dig darklab.sh A')

    cmdInput.value = 'typed now'
    setComposerState({
      value: 'typed now',
      selectionStart: 9,
      selectionEnd: 9,
      activeInput: 'desktop',
    })
    resetCmdHistoryNav()

    expect(navigateCmdHistory(-1)).toBe(false)
    expect(navigateCmdHistory(1)).toBe(true)
    expect(cmdInput.value).toBe('dig darklab.sh A')
  })

  it('limits visible recent chips on mobile and appends an overflow chip', () => {
    document.body.innerHTML = `
      <div id="history-row"><span class="history-label">Recent:</span></div>
      <input id="cmd" />
      <div id="history-panel"></div>
    `

    const helpers = fromDomScripts(
      ['app/static/js/history.js'],
      {
        document,
        localStorage: new MemoryStorage(),
        APP_CONFIG: { recent_commands_limit: 50, history_panel_limit: 8 },
        histRow: document.getElementById('history-row'),
        cmdInput: document.getElementById('cmd'),
        historyPanel: document.getElementById('history-panel'),
        refreshHistoryPanel: vi.fn(),
        useMobileTerminalViewportMode: () => true,
      },
      `({
      hydrateCmdHistory,
    })`,
    )

    helpers.hydrateCmdHistory([
      { command: 'one' },
      { command: 'two' },
      { command: 'three' },
      { command: 'four' },
    ])

    const chips = [...document.querySelectorAll('.hist-chip')]
    expect(chips).toHaveLength(4)
    expect(chips[0].querySelector('span:last-child')?.textContent).toBe('one')
    expect(chips[1].querySelector('span:last-child')?.textContent).toBe('two')
    expect(chips[2].querySelector('span:last-child')?.textContent).toBe('three')
    expect(chips[3].textContent).toBe('+ more')
  })

  it('drops one more desktop chip if the overflow chip itself wraps', () => {
    document.body.innerHTML = `
      <div id="history-row"><span class="history-label">Recent:</span></div>
      <input id="cmd" />
      <div id="history-panel"></div>
    `

    const helpers = fromDomScripts(
      ['app/static/js/history.js'],
      {
        document,
        localStorage: new MemoryStorage(),
        APP_CONFIG: { recent_commands_limit: 50 },
        histRow: document.getElementById('history-row'),
        cmdInput: document.getElementById('cmd'),
        historyPanel: document.getElementById('history-panel'),
        refreshHistoryPanel: vi.fn(),
        useMobileTerminalViewportMode: () => false,
      },
      `({
      hydrateCmdHistory,
    })`,
    )

    const originalRect = window.HTMLElement.prototype.getBoundingClientRect
    window.HTMLElement.prototype.getBoundingClientRect = function getBoundingClientRect() {
      if (!this.classList?.contains('hist-chip')) return { top: 0 }
      const regularChipCount = document.querySelectorAll(
        '.hist-chip:not(.hist-chip-overflow)',
      ).length
      if (this.classList.contains('hist-chip-overflow')) {
        return { top: regularChipCount > 2 ? 26 : 10 }
      }
      return { top: this.textContent === '☆four' ? 26 : 10 }
    }

    try {
      helpers.hydrateCmdHistory([
        { command: 'one' },
        { command: 'two' },
        { command: 'three' },
        { command: 'four' },
      ])

      const visibleChips = [...document.querySelectorAll('.hist-chip')]
      expect(visibleChips.map((chip) => chip.textContent)).toEqual(['☆one', '☆two', '+ more'])
    } finally {
      window.HTMLElement.prototype.getBoundingClientRect = originalRect
    }
  })
})

describe('history panel actions', () => {
  function loadHistoryPanel({ clipboardImpl, apiFetchImpl, mobileMode = false } = {}) {
    document.body.innerHTML = `
      <div id="history-panel"></div>
      <input id="history-search-input" />
      <button id="history-mobile-filters-toggle"></button>
      <div id="history-advanced-filters"></div>
      <select id="history-type-filter">
        <option value="all">all</option>
        <option value="runs">runs</option>
        <option value="snapshots">snapshots</option>
      </select>
      <input id="history-root-input" />
      <div id="history-root-dropdown" class="u-hidden"></div>
      <select id="history-exit-filter">
        <option value="all">all</option>
        <option value="0">0</option>
        <option value="nonzero">nonzero</option>
        <option value="incomplete">incomplete</option>
      </select>
      <select id="history-date-filter">
        <option value="all">all</option>
        <option value="24h">24h</option>
        <option value="7d">7d</option>
        <option value="30d">30d</option>
      </select>
      <input id="history-starred-toggle" type="checkbox" />
      <button id="history-clear-filters"></button>
      <div id="history-active-filters" class="u-hidden"></div>
      <div id="history-list"></div>
      <div id="history-pagination" class="u-hidden">
        <div id="history-pagination-summary"></div>
        <div id="history-pagination-controls"></div>
      </div>
      <div id="history-load-overlay"></div>
      <div id="confirm-host" class="modal-overlay u-hidden">
        <div class="modal-card modal-card-compact" data-confirm-card>
          <div class="modal-copy" data-confirm-body></div>
          <div class="modal-confirm-content" data-confirm-content></div>
          <div class="modal-actions modal-actions-wrap" data-confirm-actions></div>
        </div>
      </div>
      <div id="permalink-toast"></div>
      <div id="tabs-bar"></div>
      <div id="tab-panels"></div>
      <input id="cmd" />
    `

    const apiFetch =
      apiFetchImpl ||
      vi.fn((url) => {
        if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
          return Promise.resolve({
            json: () =>
              Promise.resolve({
                roots: ['ping'],
                items: [
                  {
                    id: 'run-1',
                    type: 'run',
                    command: 'ping darklab.sh',
                    label: 'ping darklab.sh',
                    started: '2026-01-01T00:00:00Z',
                    created: '2026-01-01T00:00:00Z',
                    exit_code: 0,
                  },
                ],
                runs: [
                  {
                    id: 'run-1',
                    command: 'ping darklab.sh',
                    started: '2026-01-01T00:00:00Z',
                    exit_code: 0,
                  },
                ],
              }),
          })
        }
        if (url === '/history/run-1?json&preview=1') {
          return Promise.resolve({
            json: () =>
              Promise.resolve({
                command: 'ping darklab.sh',
                output: ['ok'],
                exit_code: 0,
              }),
          })
        }
        return Promise.resolve({ json: () => Promise.resolve({}) })
      })

    const clipboard = clipboardImpl || { writeText: () => Promise.resolve() }
    const showToast = vi.fn()
    let createdTabSeq = 1
    const createTab = vi.fn((label = '') => {
      createdTabSeq += 1
      const id = `tab-${createdTabSeq}`
      tabs.push({ id, command: '', rawLines: [], st: 'idle', label })
      return id
    })
    const activateTab = vi.fn()
    const appendLine = vi.fn()
    const appendCommandEcho = vi.fn()
    const bindDismissible = vi.fn()
    const refocusComposerAfterAction = vi.fn(() => false)
    const setTabStatus = vi.fn((id, st) => {
      const tab = tabs.find((t) => t.id === id)
      if (tab) tab.st = st
    })
    const hideTabKillBtn = vi.fn()
    const tabs = [{ id: 'tab-1', command: '', rawLines: [], st: 'idle' }]
    const historyPanel = document.getElementById('history-panel')
    const historyList = document.getElementById('history-list')
    const historyLoadOverlay = document.getElementById('history-load-overlay')
    const historySearchInput = document.getElementById('history-search-input')
    const historyMobileFiltersToggle = document.getElementById('history-mobile-filters-toggle')
    const historyAdvancedFilters = document.getElementById('history-advanced-filters')
    const historyTypeFilter = document.getElementById('history-type-filter')
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
    const location = { origin: 'https://example.test' }
    const windowOpen = vi.fn()

    return {
      ...fromDomScripts(
        ['app/static/js/utils.js', 'app/static/js/history.js'],
        {
          document,
          localStorage: new MemoryStorage(),
          APP_CONFIG: { recent_commands_limit: 50, history_panel_limit: 8 },
          apiFetch,
          navigator: { clipboard },
          location,
          historyPanel,
          historyList,
          historyLoadOverlay,
          historySearchInput,
          historyMobileFiltersToggle,
          historyAdvancedFilters,
          historyTypeFilter,
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
          histRow: document.createElement('div'),
          showConfirm: vi.fn(() => Promise.resolve(null)),
          cmdInput,
          tabs,
          getTab: id => tabs.find(t => t.id === id),
          activateTab,
          createTab,
          appendLine,
          appendCommandEcho,
          setTabStatus,
          hideTabKillBtn,
          showToast,
          window: { open: windowOpen },
          refreshHistoryPanel: () => {},
          renderHistory: () => {},
          hideHistoryPanel: vi.fn(() => {
            historyPanel.classList.remove('open')
            if (typeof cmdInput.focus === 'function') cmdInput.focus()
          }),
          confirmHistAction: () => {},
          executeHistAction: () => {},
          bindDismissible,
          useMobileTerminalViewportMode: () => mobileMode,
          setComposerValue: (val, start = null, end = null) => {
            cmdInput.value = String(val ?? '')
            if (typeof start === 'number') cmdInput.selectionStart = start
            if (typeof end === 'number') cmdInput.selectionEnd = end
          },
          refocusComposerAfterAction,
        },
      `{
        refreshHistoryPanel,
        executeHistAction,
        confirmHistAction,
        clearHistoryFilters,
        _buildHistoryRequestUrl,
        _setHistoryFilter,
        _historySetPage,
        _historyRelativeTime,
        resetHistoryMobileFilters,
        toggleHistoryMobileFilters,
        _saveStarred,
      }`,
      ),
      apiFetch,
      clipboard,
      windowOpen,
      createTab,
      activateTab,
      appendLine,
      appendCommandEcho,
      setTabStatus,
      hideTabKillBtn,
      showToast,
      bindDismissible,
      refocusComposerAfterAction,
    }
  }

  it('refreshHistoryPanel permalink action falls back to execCommand when clipboard writes reject', async () => {
    const clipboard = {
      writeText: vi.fn(() => Promise.reject(new Error('clipboard denied'))),
    }
    const originalExecCommand = document.execCommand
    document.execCommand = vi.fn(() => true)
    const { refreshHistoryPanel } = loadHistoryPanel({ clipboardImpl: clipboard })
    const cmdInput = document.getElementById('cmd')
    cmdInput.focus = vi.fn()

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    const entry = document.querySelector('#history-list .history-entry')

    entry
      .querySelector('[data-action="permalink"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(clipboard.writeText).toHaveBeenCalledTimes(1)
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))

    expect(document.execCommand).toHaveBeenCalledWith('copy')
    expect(document.getElementById('permalink-toast').textContent).toBe('Link copied to clipboard')
    document.execCommand = originalExecCommand
  })

  it('clicking a history entry row injects the command into the composer and closes the panel', async () => {
    const { refreshHistoryPanel } = loadHistoryPanel()
    const historyPanel = document.getElementById('history-panel')
    const cmdInput = document.getElementById('cmd')
    historyPanel.classList.add('open')

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    const entry = document.querySelector('#history-list .history-entry')
    entry.dispatchEvent(new MouseEvent('click', { bubbles: true }))

    expect(cmdInput.value).toBe('ping darklab.sh')
    expect(historyPanel.classList.contains('open')).toBe(false)
  })

  it('closes the history panel for permalink but keeps it open for star and delete', async () => {
    const { refreshHistoryPanel } = loadHistoryPanel()
    const historyPanel = document.getElementById('history-panel')
    historyPanel.classList.add('open')

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    const entry = document.querySelector('#history-list .history-entry')
    entry
      .querySelector('[data-action="star"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(historyPanel.classList.contains('open')).toBe(true)

    historyPanel.classList.add('open')
    entry
      .querySelector('[data-action="permalink"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(historyPanel.classList.contains('open')).toBe(false)

    // Delete opens a confirm modal over the panel (matching the "clear all"
    // button at the top of the panel); the panel stays open so the user has
    // context for what they're deleting and the modal owns focus + Tab trap.
    historyPanel.classList.add('open')
    entry
      .querySelector('[data-action="delete"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(historyPanel.classList.contains('open')).toBe(true)
  })

  it('keeps the history panel open on mobile for every row action (confirm modal overlays it)', async () => {
    const { refreshHistoryPanel } = loadHistoryPanel({ mobileMode: true })
    const historyPanel = document.getElementById('history-panel')
    historyPanel.classList.add('open')

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    const entry = document.querySelector('#history-list .history-entry')

    entry
      .querySelector('[data-action="star"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(historyPanel.classList.contains('open')).toBe(true)

    entry
      .querySelector('[data-action="permalink"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    await Promise.resolve()
    expect(historyPanel.classList.contains('open')).toBe(true)

    entry
      .querySelector('[data-action="delete"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(historyPanel.classList.contains('open')).toBe(true)
  })

  it('refreshHistoryPanel labels the history permalink action as permalink', async () => {
    const { refreshHistoryPanel } = loadHistoryPanel()

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    const btn = document.querySelector('#history-list .history-entry [data-action="permalink"]')
    expect(btn.textContent).toBe('permalink')
  })

  it('opens the run comparison launcher from a history row', async () => {
    const apiFetch = vi.fn((url) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              roots: ['nmap'],
              items: [
                {
                  id: 'run-new',
                  type: 'run',
                  command: 'nmap darklab.sh',
                  started: '2026-01-01T00:00:04Z',
                  exit_code: 0,
                  output_line_count: 2,
                },
              ],
              runs: [
                {
                  id: 'run-new',
                  command: 'nmap darklab.sh',
                  started: '2026-01-01T00:00:04Z',
                  exit_code: 0,
                  output_line_count: 2,
                },
              ],
            }),
        })
      }
      if (url === '/history/run-new/compare-candidates') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              source: {
                id: 'run-new',
                command: 'nmap darklab.sh',
                command_root: 'nmap',
                started: '2026-01-01T00:00:04Z',
                exit_code: 0,
                output_line_count: 2,
              },
              suggested: {
                id: 'run-old',
                command: 'nmap darklab.sh',
                started: '2026-01-01T00:00:01Z',
                exit_code: 0,
                output_line_count: 1,
                confidence_label: 'Exact command',
              },
              candidates: [
                {
                  id: 'run-old',
                  command: 'nmap darklab.sh',
                  started: '2026-01-01T00:00:01Z',
                  exit_code: 0,
                  output_line_count: 1,
                  confidence_label: 'Exact command',
                },
              ],
            }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({ items: [], runs: [] }) })
    })
    const { refreshHistoryPanel, bindDismissible, refocusComposerAfterAction } = loadHistoryPanel({ apiFetchImpl: apiFetch })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    document
      .querySelector('#history-list .history-entry [data-action="compare"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))

    expect(apiFetch).toHaveBeenCalledWith('/history/run-new/compare-candidates')
    expect(document.getElementById('history-compare-overlay').classList.contains('open')).toBe(true)
    expect(bindDismissible).toHaveBeenCalledWith(
      document.getElementById('history-compare-overlay'),
      expect.objectContaining({ level: 'modal' }),
    )
    expect(refocusComposerAfterAction).not.toHaveBeenCalled()
    expect(document.querySelector('.history-compare-primary')?.textContent).toBe(
      'Compare with suggested run',
    )
    expect(document.querySelector('.history-compare-run-card')?.textContent).toContain('nmap darklab.sh')
    bindDismissible.mock.calls[0][1].onClose()
    expect(document.getElementById('history-compare-overlay').classList.contains('open')).toBe(false)
  })

  it('replaces manual comparison choices when searching the compare launcher', async () => {
    const apiFetch = vi.fn((url) => {
      if (
        typeof url === 'string'
        && (url === '/history' || (url.startsWith('/history?') && !url.includes('page_size=20')))
      ) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              roots: ['nmap'],
              items: [
                {
                  id: 'run-new',
                  type: 'run',
                  command: 'nmap darklab.sh',
                  started: '2026-01-01T00:00:04Z',
                  exit_code: 0,
                },
              ],
              runs: [],
            }),
        })
      }
      if (url === '/history/run-new/compare-candidates') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              source: { id: 'run-new', command: 'nmap darklab.sh', command_root: 'nmap' },
              suggested: { id: 'run-old', command: 'nmap darklab.sh', confidence_label: 'Exact command' },
              candidates: [{ id: 'run-old', command: 'nmap darklab.sh', confidence_label: 'Exact command' }],
            }),
        })
      }
      if (typeof url === 'string' && url.includes('/history?') && url.includes('q=ssl') && url.includes('page=2')) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              items: [
                {
                  id: 'run-ssl-old',
                  type: 'run',
                  command: 'sslscan old.darklab.sh',
                  started: '2025-12-31T12:00:02Z',
                  exit_code: 0,
                },
              ],
              page: 2,
              has_next: false,
            }),
        })
      }
      if (typeof url === 'string' && url.includes('/history?') && url.includes('q=ssl')) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              items: [
                {
                  id: 'run-ssl',
                  type: 'run',
                  command: 'sslscan darklab.sh',
                  started: '2026-01-01T12:00:02Z',
                  exit_code: 0,
                },
              ],
              page: 1,
              has_next: true,
              runs: [],
            }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({ items: [], runs: [] }) })
    })
    const { refreshHistoryPanel } = loadHistoryPanel({ apiFetchImpl: apiFetch })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    document
      .querySelector('#history-list .history-entry [data-action="compare"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))

    const search = document.querySelector('.history-compare-search')
    search.focus()
    search.value = 'ssl'
    search.dispatchEvent(new Event('input', { bubbles: true }))
    await new Promise((resolve) => setTimeout(resolve, 150))
    await Promise.resolve()
    await Promise.resolve()

    const listText = document.querySelector('[data-compare-candidate-list="1"]')?.textContent || ''
    expect(apiFetch).toHaveBeenCalledWith('/history?type=runs&page_size=20&include_total=1&page=1&scope=command&q=ssl')
    expect(listText).toContain('sslscan darklab.sh')
    expect(listText).not.toContain('nmap darklab.sh')
    expect(document.querySelector('.history-compare-candidate-day')?.textContent).toBeTruthy()
    expect(document.activeElement).toBe(search)

    const dayToggle = document.querySelector('.history-compare-candidate-day')
    const dayRows = document.querySelector('.history-compare-candidate-group-rows')
    expect(dayToggle.getAttribute('aria-expanded')).toBe('true')
    expect(dayRows.hidden).toBe(false)
    dayToggle.click()
    expect(dayToggle.getAttribute('aria-expanded')).toBe('false')
    expect(dayRows.hidden).toBe(true)
    dayToggle.click()
    expect(dayRows.hidden).toBe(false)

    document.querySelector('.history-compare-load-more').click()
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))

    expect(apiFetch).toHaveBeenCalledWith('/history?type=runs&page_size=20&include_total=1&page=2&scope=command&q=ssl')
    expect(document.querySelector('[data-compare-candidate-list="1"]')?.textContent || '').toContain(
      'sslscan old.darklab.sh',
    )
  })

  it('renders changed added and removed lines after choosing a comparison candidate', async () => {
    const apiFetch = vi.fn((url) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              roots: ['nmap'],
              items: [
                {
                  id: 'run-new',
                  type: 'run',
                  command: 'nmap darklab.sh',
                  started: '2026-01-01T00:00:04Z',
                  exit_code: 0,
                },
              ],
              runs: [],
            }),
        })
      }
      if (url === '/history/run-new/compare-candidates') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              source: { id: 'run-new', command: 'nmap darklab.sh', command_root: 'nmap' },
              suggested: { id: 'run-old', command: 'nmap darklab.sh', confidence_label: 'Exact command' },
              candidates: [{ id: 'run-old', command: 'nmap darklab.sh', confidence_label: 'Exact command' }],
            }),
        })
      }
      if (url === '/history/compare?left=run-new&right=run-old') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              left: { id: 'run-new', command: 'nmap darklab.sh', exit_code: 0, output_line_count: 2 },
              right: { id: 'run-old', command: 'nmap darklab.sh', exit_code: 0, output_line_count: 2 },
              deltas: {
                exit_code_changed: false,
                exit_code: { left: 0, right: 0 },
                duration_seconds: { delta: 0 },
                output_lines: { delta: 0 },
                findings: { delta: 0 },
              },
              sections: {
                changed: [
                  {
                    removed: {
                      text: 'Starting Nmap at 2026-04-30 23:22 UTC',
                      segments: [
                        { text: 'Starting Nmap at 2026-04-30 23:' },
                        { text: '22', changed: true },
                        { text: ' UTC' },
                      ],
                    },
                    added: {
                      text: 'Starting Nmap at 2026-04-30 23:21 UTC',
                      segments: [
                        { text: 'Starting Nmap at 2026-04-30 23:' },
                        { text: '21', changed: true },
                        { text: ' UTC' },
                      ],
                    },
                  },
                ],
                added: [{ text: '443/tcp open https' }],
                removed: [{ text: '8080/tcp open http-proxy' }],
              },
              truncated: {},
            }),
        })
      }
      if (url === '/history/run-new?json&preview=1') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              id: 'run-new',
              command: 'nmap darklab.sh',
              output: ['new output'],
              exit_code: 0,
            }),
        })
      }
      if (url === '/history/run-old?json&preview=1') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              id: 'run-old',
              command: 'nmap darklab.sh',
              output: ['old output'],
              exit_code: 0,
            }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({ items: [], runs: [] }) })
    })
    const { refreshHistoryPanel, createTab, appendCommandEcho, appendLine, activateTab } =
      loadHistoryPanel({ apiFetchImpl: apiFetch })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    document
      .querySelector('#history-list .history-entry [data-action="compare"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))
    document.querySelector('.history-compare-primary').click()
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))

    expect(document.querySelector('#history-compare-body')?.textContent).toContain('Changed lines (1)')
    expect(document.querySelector('#history-compare-body')?.textContent).toContain('23:22 UTC')
    expect(document.querySelector('#history-compare-body')?.textContent).toContain('23:21 UTC')
    expect(document.querySelectorAll('.history-compare-line-delta')).toHaveLength(2)
    expect(document.querySelector('#history-compare-body')?.textContent).toContain('443/tcp open https')
    expect(document.querySelector('#history-compare-body')?.textContent).toContain('8080/tcp open http-proxy')

    const restoreBoth = [...document.querySelectorAll('.history-compare-actions button')]
      .find(button => button.textContent === 'Restore Both')
    restoreBoth.click()
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))

    expect(createTab).toHaveBeenCalledWith('A: nmap darklab.sh')
    expect(createTab).toHaveBeenCalledWith('B: nmap darklab.sh')
    expect(appendCommandEcho).toHaveBeenCalledWith('nmap darklab.sh', 'tab-2')
    expect(appendCommandEcho).toHaveBeenCalledWith('nmap darklab.sh', 'tab-3')
    expect(appendLine).toHaveBeenCalledWith('new output', '', 'tab-2')
    expect(appendLine).toHaveBeenCalledWith('old output', '', 'tab-3')
    expect(activateTab).toHaveBeenCalledWith('tab-3', { focusComposer: false })
    expect(document.getElementById('history-compare-overlay').classList.contains('open')).toBe(false)
  })

  it('includes the history type filter in the request URL when snapshots are selected', () => {
    const { _setHistoryFilter, _buildHistoryRequestUrl } = loadHistoryPanel()

    _setHistoryFilter('type', 'snapshots')

    expect(_buildHistoryRequestUrl()).toContain('type=snapshots')
  })

  it('renders snapshot rows with open and copy-link actions', async () => {
    const { refreshHistoryPanel } = loadHistoryPanel({
      apiFetchImpl: vi.fn(() =>
        Promise.resolve({
          json: () =>
            Promise.resolve({
              roots: [],
              items: [
                {
                  id: 'snap-1',
                  type: 'snapshot',
                  label: 'nmap baseline snapshot',
                  created: '2026-01-01T00:00:00Z',
                },
              ],
              runs: [],
            }),
        }),
      ),
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    const entry = document.querySelector('#history-list .history-entry')
    expect(entry.querySelector('.history-entry-cmd')?.textContent).toBe('nmap baseline snapshot')
    expect(entry.querySelector('[data-action="open"]')?.textContent).toBe('open')
    expect(entry.querySelector('[data-action="link"]')?.textContent).toBe('copy link')
  })

  it('shows a date in history metadata when the run is not from today', async () => {
    const RealDate = Date
    class MockDate extends RealDate {
      constructor(value) {
        super(value ?? '2026-01-02T12:00:00Z')
      }
      static now() {
        return new RealDate('2026-01-02T12:00:00Z').getTime()
      }
    }
    globalThis.Date = MockDate
    try {
      const { refreshHistoryPanel } = loadHistoryPanel({
        apiFetchImpl: vi.fn(() =>
          Promise.resolve({
            json: () =>
              Promise.resolve({
                runs: [
                  {
                    id: 'run-1',
                    command: 'ping darklab.sh',
                    started: '2026-01-01T00:00:00Z',
                    exit_code: 0,
                  },
                ],
              }),
          }),
        ),
      })

      refreshHistoryPanel()
      await new Promise((resolve) => setImmediate(resolve))

      expect(document.querySelector('.history-entry-date')).not.toBeNull()
    } finally {
      globalThis.Date = RealDate
    }
  })

  it('omits the date in history metadata for runs from the current day', async () => {
    const RealDate = Date
    class MockDate extends RealDate {
      constructor(value) {
        super(value ?? '2026-01-02T12:00:00Z')
      }
      static now() {
        return new RealDate('2026-01-02T12:00:00Z').getTime()
      }
    }
    globalThis.Date = MockDate
    try {
      const { refreshHistoryPanel } = loadHistoryPanel({
        apiFetchImpl: vi.fn(() =>
          Promise.resolve({
            json: () =>
              Promise.resolve({
                runs: [
                  {
                    id: 'run-1',
                    command: 'ping darklab.sh',
                    started: '2026-01-02T18:00:00Z',
                    exit_code: 0,
                  },
                ],
              }),
          }),
        ),
      })

      refreshHistoryPanel()
      await new Promise((resolve) => setImmediate(resolve))

      expect(document.querySelector('.history-entry-date')).toBeNull()
    } finally {
      globalThis.Date = RealDate
    }
  })

  it('_historyRelativeTime buckets recent diffs as just now / m / h / d and falls back to a short date', () => {
    const { _historyRelativeTime } = loadHistoryPanel()
    const now = new Date('2026-04-20T12:00:00Z')
    expect(_historyRelativeTime(new Date('2026-04-20T11:59:50Z'), now)).toBe('just now')
    expect(_historyRelativeTime(new Date('2026-04-20T11:57:00Z'), now)).toBe('3m ago')
    expect(_historyRelativeTime(new Date('2026-04-20T10:00:00Z'), now)).toBe('2h ago')
    expect(_historyRelativeTime(new Date('2026-04-18T12:00:00Z'), now)).toBe('2d ago')
    // Older than a week -> short date ("Apr 10" in en locales; just check shape.)
    const older = _historyRelativeTime(new Date('2026-04-10T12:00:00Z'), now)
    expect(older).not.toMatch(/ago|just now/)
    expect(older.length).toBeGreaterThan(0)
    expect(_historyRelativeTime('not a date', now)).toBe('')
    expect(_historyRelativeTime(new Date('invalid'), now)).toBe('')
  })

  it('desktop history rows keep absolute clock time and no tooltip on the time span', async () => {
    const { refreshHistoryPanel } = loadHistoryPanel({
      apiFetchImpl: vi.fn(() =>
        Promise.resolve({
          json: () =>
            Promise.resolve({
              runs: [
                {
                  id: 'run-1',
                  command: 'ping darklab.sh',
                  started: '2026-04-20T09:00:00Z',
                  exit_code: 0,
                },
              ],
            }),
        }),
      ),
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    const timeEl = document.querySelector('.history-entry-meta span')
    expect(timeEl.textContent).not.toMatch(/ago|just now/)
    expect(timeEl.title).toBe('')
  })

  it('refreshHistoryPanel sends the active server-side filters to /history', async () => {
    const { refreshHistoryPanel, apiFetch, _setHistoryFilter, _buildHistoryRequestUrl } =
      loadHistoryPanel()

    _setHistoryFilter('q', 'dig')
    _setHistoryFilter('commandRoot', 'nmap')
    _setHistoryFilter('exitCode', 'nonzero')
    _setHistoryFilter('dateRange', '7d')
    await new Promise((resolve) => setImmediate(resolve))

    expect(_buildHistoryRequestUrl()).toBe(
      '/history?page=1&page_size=8&include_total=1&q=dig&command_root=nmap&exit_code=nonzero&date_range=7d',
    )
    expect(apiFetch).toHaveBeenLastCalledWith(
      '/history?page=1&page_size=8&include_total=1&q=dig&command_root=nmap&exit_code=nonzero&date_range=7d',
    )
    expect(typeof refreshHistoryPanel).toBe('function')
  })

  it('refreshHistoryPanel renders pagination controls and advances to the next page', async () => {
    const apiFetch = vi.fn((url) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        const page = new URL(url, 'https://example.test').searchParams.get('page') || '1'
        if (page === '2') {
          return Promise.resolve({
            json: () =>
              Promise.resolve({
                page: 2,
                page_size: 8,
                total_count: 9,
                page_count: 2,
                has_prev: true,
                has_next: false,
                roots: ['dig', 'ping'],
                runs: [
                  {
                    id: 'run-2',
                    command: 'dig darklab.sh A',
                    started: '2026-01-01T00:01:00Z',
                    exit_code: 0,
                  },
                ],
              }),
          })
        }
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              page: 1,
              page_size: 8,
              total_count: 9,
              page_count: 2,
              has_prev: false,
              has_next: true,
              roots: ['dig', 'ping'],
              runs: [
                {
                  id: 'run-1',
                  command: 'ping darklab.sh',
                  started: '2026-01-01T00:00:00Z',
                  exit_code: 0,
                },
              ],
            }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })

    const { refreshHistoryPanel } = loadHistoryPanel({ apiFetchImpl: apiFetch })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    expect(document.getElementById('history-pagination-summary').textContent).toBe(
      'Showing 1-1 of 9 stored items',
    )
    expect(document.querySelector('#history-pagination-controls .history-pagination-status')?.textContent)
      .toBe('Page 1 of 2')

    document.querySelector('#history-pagination-controls [aria-label="Next page"]').click()
    await new Promise((resolve) => setImmediate(resolve))

    expect(apiFetch).toHaveBeenLastCalledWith(
      '/history?page=2&page_size=8&include_total=1',
    )
    expect(document.getElementById('history-pagination-summary').textContent).toBe(
      'Showing 9-9 of 9 stored items',
    )
    expect(document.querySelector('#history-pagination-controls .history-pagination-status')?.textContent)
      .toBe('Page 2 of 2')
    expect([...document.querySelectorAll('#history-list .history-entry-cmd')].map((el) => el.textContent))
      .toEqual(['dig darklab.sh A'])
  })

  it('populates command root suggestions from loaded history runs', async () => {
    const { refreshHistoryPanel } = loadHistoryPanel({
      apiFetchImpl: vi.fn(() =>
        Promise.resolve({
          json: () =>
            Promise.resolve({
              roots: ['curl', 'dig', 'ping'],
              runs: [
                {
                  id: 'run-1',
                  command: 'ping darklab.sh',
                  started: '2026-01-01T00:00:00Z',
                  exit_code: 0,
                },
                {
                  id: 'run-2',
                  command: 'dig darklab.sh A',
                  started: '2026-01-01T00:01:00Z',
                  exit_code: 0,
                },
                {
                  id: 'run-3',
                  command: 'ping -c 4 darklab.sh',
                  started: '2026-01-01T00:02:00Z',
                  exit_code: 0,
                },
              ],
            }),
        }),
      ),
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    const input = document.getElementById('history-root-input')
    input.value = 'd'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))

    const suggestions = [...document.querySelectorAll('#history-root-dropdown .ac-item')].map(
      (el) => el.textContent.trim(),
    )
    expect(suggestions).toEqual(['dig'])
  })

  it('keeps root suggestions stable when a refresh returns no roots while typing', async () => {
    const apiFetch = vi.fn(() =>
      Promise.resolve({
        json: () =>
          Promise.resolve({
            roots: [],
            runs: [],
          }),
      }),
    )
      .mockResolvedValueOnce({
        json: () =>
          Promise.resolve({
            roots: ['curl', 'dig', 'ping'],
            runs: [
              {
                id: 'run-1',
                command: 'dig darklab.sh A',
                started: '2026-01-01T00:00:00Z',
                exit_code: 0,
              },
            ],
          }),
      })
      .mockResolvedValueOnce({
        json: () =>
          Promise.resolve({
            roots: [],
            runs: [],
          }),
      })
    const { refreshHistoryPanel } = loadHistoryPanel({ apiFetchImpl: apiFetch })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    const input = document.getElementById('history-root-input')
    input.dispatchEvent(new Event('focus'))
    input.value = 'd'
    input.dispatchEvent(new Event('input', { bubbles: true }))

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    const suggestions = [...document.querySelectorAll('#history-root-dropdown .ac-item')].map(
      (el) => el.textContent.trim(),
    )
    expect(suggestions).toEqual(['dig'])
    expect(document.getElementById('history-root-dropdown').classList.contains('u-hidden')).toBe(
      false,
    )
  })

  it('keeps the root suggestion menu hidden until at least one character is typed', async () => {
    const { refreshHistoryPanel } = loadHistoryPanel({
      apiFetchImpl: vi.fn(() =>
        Promise.resolve({
          json: () =>
            Promise.resolve({
              roots: ['curl', 'dig', 'ping'],
              runs: [],
            }),
        }),
      ),
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    const input = document.getElementById('history-root-input')
    input.dispatchEvent(new Event('focus'))
    await new Promise((resolve) => setImmediate(resolve))

    expect(document.getElementById('history-root-dropdown').classList.contains('u-hidden')).toBe(
      true,
    )
  })

  it('hides the root suggestion menu when the only matching suggestion exactly matches the input', async () => {
    const { refreshHistoryPanel } = loadHistoryPanel({
      apiFetchImpl: vi.fn(() =>
        Promise.resolve({
          json: () =>
            Promise.resolve({
              roots: ['dig'],
              runs: [
                {
                  id: 'run-1',
                  command: 'dig darklab.sh A',
                  started: '2026-01-01T00:00:00Z',
                  exit_code: 0,
                },
              ],
            }),
        }),
      ),
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    const input = document.getElementById('history-root-input')
    input.value = 'dig'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))

    expect(document.getElementById('history-root-dropdown').classList.contains('u-hidden')).toBe(
      true,
    )
  })

  it('accepts a root suggestion with one mobile-style pointer interaction', async () => {
    const { refreshHistoryPanel } = loadHistoryPanel({
      apiFetchImpl: vi.fn(() =>
        Promise.resolve({
          json: () =>
            Promise.resolve({
              roots: ['dig', 'ping'],
              runs: [
                {
                  id: 'run-1',
                  command: 'dig darklab.sh A',
                  started: '2026-01-01T00:00:00Z',
                  exit_code: 0,
                },
              ],
            }),
        }),
      ),
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    const input = document.getElementById('history-root-input')
    input.value = 'di'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))

    document
      .querySelector('#history-root-dropdown .ac-item')
      .dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))
    await new Promise((resolve) => setImmediate(resolve))

    expect(input.value).toBe('dig')
    expect(document.getElementById('history-root-dropdown').classList.contains('u-hidden')).toBe(
      true,
    )
  })

  it('renders active filter chips for the current history filters', async () => {
    const { _setHistoryFilter } = loadHistoryPanel()

    _setHistoryFilter('q', 'dig')
    _setHistoryFilter('commandRoot', 'nmap')
    _setHistoryFilter('exitCode', 'nonzero')
    _setHistoryFilter('dateRange', '7d')
    _setHistoryFilter('starredOnly', true)
    await new Promise((resolve) => setImmediate(resolve))

    const chips = [
      ...document.querySelectorAll('#history-active-filters .history-active-filter-chip'),
    ].map((el) => el.textContent)
    expect(chips).toEqual([
      expect.stringContaining('search: dig'),
      expect.stringContaining('command: nmap'),
      expect.stringContaining('exit: non-zero'),
      expect.stringContaining('date: 7d'),
      expect.stringContaining('starred'),
    ])
    expect(document.getElementById('history-active-filters').classList.contains('u-hidden')).toBe(
      false,
    )
  })

  it('removes an individual filter when its active filter chip is cleared', async () => {
    const { _setHistoryFilter, _buildHistoryRequestUrl } = loadHistoryPanel()

    _setHistoryFilter('q', 'dig')
    _setHistoryFilter('commandRoot', 'nmap')
    await new Promise((resolve) => setImmediate(resolve))

    const removeBtn = [
      ...document.querySelectorAll('#history-active-filters .history-active-filter-chip'),
    ]
      .find((el) => el.textContent.includes('command: nmap'))
      ?.querySelector('.history-active-filter-remove')

    removeBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))

    expect(_buildHistoryRequestUrl()).toBe('/history?page=1&page_size=8&include_total=1&q=dig')
    expect(document.getElementById('history-root-input').value).toBe('')
  })

  it('keeps the history drawer open when removing an active filter chip', async () => {
    const { _setHistoryFilter } = loadHistoryPanel()
    const historyPanel = document.getElementById('history-panel')
    historyPanel.classList.add('open')

    _setHistoryFilter('q', 'dig')
    await new Promise((resolve) => setImmediate(resolve))

    document
      .querySelector('#history-active-filters .history-active-filter-remove')
      .dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    await new Promise((resolve) => setImmediate(resolve))

    expect(historyPanel.classList.contains('open')).toBe(true)
  })

  it('toggles the mobile advanced history filters section', () => {
    const { toggleHistoryMobileFilters } = loadHistoryPanel()
    const historyPanel = document.getElementById('history-panel')
    const toggleBtn = document.getElementById('history-mobile-filters-toggle')

    expect(historyPanel.classList.contains('mobile-history-filters-open')).toBe(false)
    expect(toggleBtn.getAttribute('aria-expanded')).toBe('false')

    toggleHistoryMobileFilters(true)
    expect(historyPanel.classList.contains('mobile-history-filters-open')).toBe(true)
    expect(toggleBtn.textContent).toBe('hide filters')
    expect(toggleBtn.getAttribute('aria-expanded')).toBe('true')

    toggleHistoryMobileFilters(false)
    expect(historyPanel.classList.contains('mobile-history-filters-open')).toBe(false)
    expect(toggleBtn.textContent).toBe('filters')
    expect(toggleBtn.getAttribute('aria-expanded')).toBe('false')
  })

  it('resetHistoryMobileFilters collapses the advanced mobile history filters', () => {
    const { toggleHistoryMobileFilters, resetHistoryMobileFilters } = loadHistoryPanel()
    const historyPanel = document.getElementById('history-panel')

    toggleHistoryMobileFilters(true)
    expect(historyPanel.classList.contains('mobile-history-filters-open')).toBe(true)

    resetHistoryMobileFilters()
    expect(historyPanel.classList.contains('mobile-history-filters-open')).toBe(false)
    expect(document.getElementById('history-mobile-filters-toggle').textContent).toBe('filters')
  })

  it('shows the active filter count in the mobile filters button label', async () => {
    const { _setHistoryFilter } = loadHistoryPanel()
    const toggleBtn = document.getElementById('history-mobile-filters-toggle')

    _setHistoryFilter('q', 'dig')
    _setHistoryFilter('dateRange', '7d')
    _setHistoryFilter('starredOnly', true)
    await new Promise((resolve) => setImmediate(resolve))

    expect(toggleBtn.textContent).toBe('filters (3)')
  })

  it('refreshHistoryPanel sends starred-only as a server-side filter', async () => {
    const apiFetch = vi.fn((url) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        expect(url).toContain('starred_only=1')
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              page: 1,
              page_size: 8,
              total_count: 1,
              page_count: 1,
              has_prev: false,
              has_next: false,
              roots: ['dig'],
              runs: [
                {
                  id: 'run-2',
                  command: 'dig darklab.sh A',
                  started: '2026-01-01T00:01:00Z',
                  exit_code: 0,
                },
              ],
            }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })
    const { _saveStarred } = loadHistoryPanel({ apiFetchImpl: apiFetch })

    _saveStarred(new Set(['dig darklab.sh A']))
    document.getElementById('history-starred-toggle').checked = true
    document
      .getElementById('history-starred-toggle')
      .dispatchEvent(new Event('change', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))

    const entries = [...document.querySelectorAll('#history-list .history-entry-cmd')].map(
      (el) => el.textContent,
    )
    expect(entries).toEqual(['dig darklab.sh A'])
    expect(document.getElementById('history-pagination-summary').textContent).toBe(
      'Showing 1-1 of 1 stored item',
    )
  })

  it('clearHistoryFilters resets the drawer controls and the request URL', async () => {
    const { _buildHistoryRequestUrl, clearHistoryFilters } = loadHistoryPanel()
    document.getElementById('history-search-input').value = 'curl'
    document
      .getElementById('history-search-input')
      .dispatchEvent(new Event('input', { bubbles: true }))
    document.getElementById('history-root-input').value = 'dig'
    document
      .getElementById('history-root-input')
      .dispatchEvent(new Event('input', { bubbles: true }))
    document.getElementById('history-exit-filter').value = '0'
    document
      .getElementById('history-exit-filter')
      .dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('history-date-filter').value = '24h'
    document
      .getElementById('history-date-filter')
      .dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('history-starred-toggle').checked = true
    document
      .getElementById('history-starred-toggle')
      .dispatchEvent(new Event('change', { bubbles: true }))
    await new Promise((resolve) => setTimeout(resolve, 140))

    clearHistoryFilters()

    expect(_buildHistoryRequestUrl()).toBe('/history?page=1&page_size=8&include_total=1')
    expect(document.getElementById('history-search-input').value).toBe('')
    expect(document.getElementById('history-root-input').value).toBe('')
    expect(document.getElementById('history-exit-filter').value).toBe('all')
    expect(document.getElementById('history-date-filter').value).toBe('all')
    expect(document.getElementById('history-starred-toggle').checked).toBe(false)
  })

  it('shows a filtered empty state when no runs match the active filters', async () => {
    const { refreshHistoryPanel } = loadHistoryPanel({
      apiFetchImpl: vi.fn(() =>
        Promise.resolve({
          json: () => Promise.resolve({ runs: [] }),
        }),
      ),
    })

    document.getElementById('history-search-input').value = 'nmap'
    document
      .getElementById('history-search-input')
      .dispatchEvent(new Event('input', { bubbles: true }))
    await new Promise((resolve) => setTimeout(resolve, 140))
    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    expect(document.querySelector('.history-empty-state-title')?.textContent).toBe(
      'No matching history items.',
    )
    expect(document.querySelector('.history-empty-state-detail')?.textContent).toContain(
      'Adjust or clear',
    )
  })

  it('executeHistAction shows a failure toast when deleting a run fails', async () => {
    const apiFetch = vi.fn((url, options = {}) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              runs: [
                {
                  id: 'run-1',
                  command: 'ping darklab.sh',
                  started: '2026-01-01T00:00:00Z',
                  exit_code: 0,
                },
              ],
            }),
        })
      }
      if (url === '/history/run-1' && options.method === 'DELETE') {
        return Promise.reject(new Error('delete failed'))
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel, executeHistAction, confirmHistAction } = loadHistoryPanel({
      apiFetchImpl: apiFetch,
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    confirmHistAction('delete', 'run-1', 'ping darklab.sh')
    executeHistAction('delete')
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))

    expect(document.getElementById('permalink-toast').textContent).toBe('Failed to delete run')
    expect(document.querySelectorAll('#history-list .history-entry')).toHaveLength(1)
  })

  it('executeHistAction shows a failure toast when clearing non-favorite history fails', async () => {
    const apiFetch = vi.fn((url, options = {}) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?')) && (!options.method || options.method === 'GET')) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              runs: [
                {
                  id: 'run-1',
                  command: 'ping darklab.sh',
                  started: '2026-01-01T00:00:00Z',
                  exit_code: 0,
                },
              ],
            }),
        })
      }
      if (url === '/history/run-1' && options.method === 'DELETE') {
        return Promise.reject(new Error('bulk delete failed'))
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel, executeHistAction } = loadHistoryPanel({ apiFetchImpl: apiFetch })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    executeHistAction('clear-nonfav')
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))

    expect(document.getElementById('permalink-toast').textContent).toBe('Failed to clear history')
    expect(document.querySelectorAll('#history-list .history-entry')).toHaveLength(1)
  })

  it('shows and clears the history loading overlay while a run is being restored', async () => {
    let resolveRun
    const apiFetch = vi.fn((url) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              runs: [
                {
                  id: 'run-1',
                  command: 'ping darklab.sh',
                  started: '2026-01-01T00:00:00Z',
                  exit_code: 0,
                },
              ],
            }),
        })
      }
      if (url === '/history/run-1?json&preview=1') {
        return new Promise((resolve) => {
          resolveRun = () =>
            resolve({
              json: () =>
                Promise.resolve({
                  command: 'ping darklab.sh',
                  output: ['ok'],
                  exit_code: 0,
                }),
            })
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel, appendLine, hideTabKillBtn, setTabStatus } = loadHistoryPanel({
      apiFetchImpl: apiFetch,
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    document
      .querySelector('.history-entry [data-action="restore"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(document.getElementById('history-load-overlay').classList.contains('open')).toBe(true)

    resolveRun()
    await new Promise((resolve) => setImmediate(resolve))
    await new Promise((resolve) => setImmediate(resolve))

    expect(document.getElementById('history-load-overlay').classList.contains('open')).toBe(false)
  })

  it('restores the full history payload when full output is available', async () => {
    const apiFetch = vi.fn((url) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              runs: [
                {
                  id: 'run-1',
                  command: 'ping darklab.sh',
                  started: '2026-01-01T00:00:00Z',
                  exit_code: 0,
                  full_output_available: true,
                },
              ],
            }),
        })
      }
      if (url === '/history/run-1?json') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              command: 'ping darklab.sh',
              output: ['ok line 1', 'ok line 2'],
              output_entries: [
                {
                  text: 'ok line 1',
                  cls: '',
                  signals: ['findings'],
                  line_index: 0,
                  command_root: 'ping',
                  target: 'darklab.sh',
                },
                { text: 'ok line 2', cls: '' },
              ],
              exit_code: 0,
              full_output_available: true,
            }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel, appendLine, appendCommandEcho, setTabStatus, hideTabKillBtn } =
      loadHistoryPanel({ apiFetchImpl: apiFetch })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    document
      .querySelector('.history-entry [data-action="restore"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))
    await new Promise((resolve) => setImmediate(resolve))

    expect(apiFetch).toHaveBeenCalledWith('/history/run-1?json')
    expect(document.getElementById('history-load-overlay').classList.contains('open')).toBe(false)
    expect(appendCommandEcho).toHaveBeenCalledWith('ping darklab.sh', 'tab-2')
    expect(appendLine).toHaveBeenCalledWith('ok line 1', '', 'tab-2', {
      signals: ['findings'],
      line_index: 0,
      command_root: 'ping',
      target: 'darklab.sh',
    })
    expect(appendLine).toHaveBeenCalledWith('ok line 2', '', 'tab-2')
    expect(appendLine).not.toHaveBeenCalledWith(
      expect.stringContaining('preview truncated'),
      'notice',
      'tab-2',
    )
    expect(setTabStatus).toHaveBeenCalledWith('tab-2', 'ok')
    expect(hideTabKillBtn).toHaveBeenCalledWith('tab-2')
  })

  it('clears the history loading overlay and shows a failure toast when a restore fetch fails', async () => {
    const apiFetch = vi.fn((url) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              runs: [
                {
                  id: 'run-1',
                  command: 'ping darklab.sh',
                  started: '2026-01-01T00:00:00Z',
                  exit_code: 0,
                },
              ],
            }),
        })
      }
      if (url === '/history/run-1?json&preview=1') {
        return Promise.reject(new Error('restore failed'))
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel } = loadHistoryPanel({ apiFetchImpl: apiFetch })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    document
      .querySelector('.history-entry [data-action="restore"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))

    expect(document.getElementById('history-load-overlay').classList.contains('open')).toBe(false)
    expect(document.getElementById('permalink-toast').textContent).toBe('Failed to load run')
  })
})

// ── Ctrl+R reverse-history search ─────────────────────────────────────────────

describe('Ctrl+R reverse-history search', () => {
  function loadHistSearch({ submitComposerCommand: submitMock } = {}) {
    document.body.innerHTML = `
      <div id="history-row"><span class="history-label">Recent:</span></div>
      <input id="cmd" />
      <div id="history-panel"></div>
      <div id="hist-search-dropdown"></div>
    `
    const histRow = document.getElementById('history-row')
    const cmdInput = document.getElementById('cmd')
    const historyPanel = document.getElementById('history-panel')
    const histSearchDropdown = document.getElementById('hist-search-dropdown')
    const submitComposerCommand = submitMock ?? vi.fn()

    return fromDomScripts(
      ['app/static/js/history.js'],
      {
        document,
        localStorage: new MemoryStorage(),
        APP_CONFIG: { recent_commands_limit: 20 },
        histRow,
        cmdInput,
        historyPanel,
        histSearchDropdown,
        shellPromptWrap: document.createElement('div'),
        acHide: vi.fn(),
        apiFetch: vi.fn(() => Promise.resolve({ json: () => Promise.resolve({ runs: [] }) })),
        refreshHistoryPanel: vi.fn(),
        useMobileTerminalViewportMode: () => false,
        setComposerValue: (val, start = null, end = null, opts = {}) => {
          cmdInput.value = String(val ?? '')
          if (opts.dispatch !== false) cmdInput.dispatchEvent(new Event('input'))
        },
        getComposerValue: () => cmdInput.value,
        submitComposerCommand,
      },
      `{
      hydrateCmdHistory,
      enterHistSearch,
      exitHistSearch,
      handleHistSearchInput,
      handleHistSearchKey,
      isHistSearchMode,
      resetCmdHistoryNav,
      _submitComposerCommand: submitComposerCommand,
    }`,
    )
  }

  it('enterHistSearch activates search mode and shows the dropdown', () => {
    const { hydrateCmdHistory, enterHistSearch, isHistSearchMode } = loadHistSearch()
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }, { command: 'nmap -sV darklab.sh' }])
    const dropdown = document.getElementById('hist-search-dropdown')

    enterHistSearch()

    expect(isHistSearchMode()).toBe(true)
    expect(dropdown.classList.contains('u-hidden')).toBe(false)
  })

  it('enterHistSearch saves the current input as the pre-draft', () => {
    const { hydrateCmdHistory, enterHistSearch, exitHistSearch } = loadHistSearch()
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])
    const cmdInput = document.getElementById('cmd')
    cmdInput.value = 'partial-cmd'

    enterHistSearch()
    exitHistSearch(false)

    expect(cmdInput.value).toBe('partial-cmd')
  })

  it('handleHistSearchInput filters by substring and keeps query in input (match shown in dropdown only)', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput } = loadHistSearch()
    hydrateCmdHistory([
      { command: 'dig darklab.sh A' },
      { command: 'nmap -sV darklab.sh' },
      { command: 'curl -I https://darklab.sh' },
    ])
    const cmdInput = document.getElementById('cmd')

    enterHistSearch()
    // Simulate user typing 'nmap': browser sets cmdInput.value before the input event fires
    cmdInput.value = 'nmap'
    handleHistSearchInput('nmap')

    // Input should retain the typed query, not be replaced by the full match.
    // The match is surfaced in the dropdown only; Enter or Ctrl+R accepts it.
    expect(cmdInput.value).toBe('nmap')
  })

  it('exitHistSearch(true) accepts the currently selected match', () => {
    const {
      hydrateCmdHistory,
      enterHistSearch,
      handleHistSearchInput,
      exitHistSearch,
      isHistSearchMode,
    } = loadHistSearch()
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }, { command: 'nmap -sV darklab.sh' }])
    const cmdInput = document.getElementById('cmd')

    enterHistSearch()
    handleHistSearchInput('nmap')
    exitHistSearch(true)

    expect(isHistSearchMode()).toBe(false)
    expect(cmdInput.value).toBe('nmap -sV darklab.sh')
    expect(document.getElementById('hist-search-dropdown').classList.contains('u-hidden')).toBe(
      true,
    )
  })

  it('exitHistSearch(false) cancels and restores the pre-draft', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, exitHistSearch } =
      loadHistSearch()
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])
    const cmdInput = document.getElementById('cmd')
    cmdInput.value = 'my draft'

    enterHistSearch()
    handleHistSearchInput('dig')
    exitHistSearch(false)

    expect(cmdInput.value).toBe('my draft')
  })

  it('handleHistSearchKey Escape cancels search and returns true', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchKey, isHistSearchMode } =
      loadHistSearch()
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])
    const cmdInput = document.getElementById('cmd')
    cmdInput.value = 'pre'

    enterHistSearch()
    const e = Object.assign(new Event('keydown', { cancelable: true }), {
      key: 'Escape',
      ctrlKey: false,
      metaKey: false,
      altKey: false,
    })
    const handled = handleHistSearchKey(e)

    expect(handled).toBe(true)
    expect(isHistSearchMode()).toBe(false)
    expect(cmdInput.value).toBe('pre')
  })

  it('handleHistSearchKey Enter accepts the match, exits search, and runs the command', () => {
    const submitComposerCommand = vi.fn()
    const {
      hydrateCmdHistory,
      enterHistSearch,
      handleHistSearchInput,
      handleHistSearchKey,
      isHistSearchMode,
    } = loadHistSearch({ submitComposerCommand })
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])
    const cmdInput = document.getElementById('cmd')

    enterHistSearch()
    cmdInput.value = 'dig'
    handleHistSearchInput('dig')
    const e = Object.assign(new Event('keydown', { cancelable: true }), {
      key: 'Enter',
      ctrlKey: false,
      metaKey: false,
      altKey: false,
    })
    const handled = handleHistSearchKey(e)

    expect(handled).toBe(true)
    expect(isHistSearchMode()).toBe(false)
    expect(cmdInput.value).toBe('dig darklab.sh A')
    expect(submitComposerCommand).toHaveBeenCalledWith('dig darklab.sh A', {
      dismissKeyboard: true,
    })
  })

  it('handleHistSearchKey Enter with no matches keeps typed query and runs it', () => {
    const submitComposerCommand = vi.fn()
    const {
      hydrateCmdHistory,
      enterHistSearch,
      handleHistSearchInput,
      handleHistSearchKey,
      isHistSearchMode,
    } = loadHistSearch({ submitComposerCommand })
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])
    const cmdInput = document.getElementById('cmd')

    enterHistSearch()
    cmdInput.value = 'xyz'
    handleHistSearchInput('xyz')
    const e = Object.assign(new Event('keydown', { cancelable: true }), {
      key: 'Enter',
      ctrlKey: false,
      metaKey: false,
      altKey: false,
    })
    handleHistSearchKey(e)

    expect(isHistSearchMode()).toBe(false)
    expect(cmdInput.value).toBe('xyz')
    expect(submitComposerCommand).toHaveBeenCalledWith('xyz', { dismissKeyboard: true })
  })

  it('handleHistSearchKey Tab accepts the match without running the command', () => {
    const submitComposerCommand = vi.fn()
    const {
      hydrateCmdHistory,
      enterHistSearch,
      handleHistSearchInput,
      handleHistSearchKey,
      isHistSearchMode,
    } = loadHistSearch({ submitComposerCommand })
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])
    const cmdInput = document.getElementById('cmd')

    enterHistSearch()
    cmdInput.value = 'dig'
    handleHistSearchInput('dig')
    const e = Object.assign(new Event('keydown', { cancelable: true }), {
      key: 'Tab',
      ctrlKey: false,
      metaKey: false,
      altKey: false,
    })
    const handled = handleHistSearchKey(e)

    expect(handled).toBe(true)
    expect(isHistSearchMode()).toBe(false)
    expect(cmdInput.value).toBe('dig darklab.sh A')
    expect(submitComposerCommand).not.toHaveBeenCalled()
  })

  it('handleHistSearchKey ArrowDown navigates to the next match and fills the input', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, handleHistSearchKey } =
      loadHistSearch()
    hydrateCmdHistory([
      { command: 'dig darklab.sh A' },
      { command: 'dig darklab.sh MX' },
      { command: 'curl -I https://darklab.sh' },
    ])
    const cmdInput = document.getElementById('cmd')

    enterHistSearch()
    cmdInput.value = 'dig'
    handleHistSearchInput('dig')
    // index is now 0, input still shows 'dig'
    expect(cmdInput.value).toBe('dig')

    const down = Object.assign(new Event('keydown', { cancelable: true }), {
      key: 'ArrowDown',
      ctrlKey: false,
      metaKey: false,
      altKey: false,
    })
    const handled = handleHistSearchKey(down)

    expect(handled).toBe(true)
    // ArrowDown from index 0 moves to index 1
    expect(cmdInput.value).toBe('dig darklab.sh MX')
  })

  it('handleHistSearchKey ArrowUp navigates to the previous match', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, handleHistSearchKey } =
      loadHistSearch()
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }, { command: 'dig darklab.sh MX' }])
    const cmdInput = document.getElementById('cmd')

    enterHistSearch()
    cmdInput.value = 'dig'
    handleHistSearchInput('dig')

    const down = Object.assign(new Event('keydown', { cancelable: true }), {
      key: 'ArrowDown',
      ctrlKey: false,
      metaKey: false,
      altKey: false,
    })
    handleHistSearchKey(down)
    expect(cmdInput.value).toBe('dig darklab.sh MX')

    const up = Object.assign(new Event('keydown', { cancelable: true }), {
      key: 'ArrowUp',
      ctrlKey: false,
      metaKey: false,
      altKey: false,
    })
    const handled = handleHistSearchKey(up)

    expect(handled).toBe(true)
    expect(cmdInput.value).toBe('dig darklab.sh A')
  })

  it('handleHistSearchKey Ctrl+R cycles to the next match', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, handleHistSearchKey } =
      loadHistSearch()
    hydrateCmdHistory([
      { command: 'dig darklab.sh A' },
      { command: 'dig darklab.sh MX' },
      { command: 'curl -I https://darklab.sh' },
    ])
    const cmdInput = document.getElementById('cmd')

    enterHistSearch()
    // Simulate user typing 'dig': browser sets cmdInput.value before the input event fires
    cmdInput.value = 'dig'
    handleHistSearchInput('dig')
    // Input stays as the typed query until Ctrl+R or Enter accepts a match
    expect(cmdInput.value).toBe('dig')

    const e = Object.assign(new Event('keydown', { cancelable: true }), {
      key: 'r',
      ctrlKey: true,
      metaKey: false,
      altKey: false,
    })
    handleHistSearchKey(e)

    expect(cmdInput.value).toBe('dig darklab.sh MX')
  })

  it('handleHistSearchKey returns false for printable characters to allow input to proceed', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchKey } = loadHistSearch()
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])

    enterHistSearch()
    const e = Object.assign(new Event('keydown', { cancelable: true }), {
      key: 'a',
      ctrlKey: false,
      metaKey: false,
      altKey: false,
    })
    expect(handleHistSearchKey(e)).toBe(false)
  })

  it('handleHistSearchKey Ctrl+C exits search keeping the typed query in input (not restoring pre-draft)', () => {
    const {
      hydrateCmdHistory,
      enterHistSearch,
      handleHistSearchInput,
      handleHistSearchKey,
      isHistSearchMode,
    } = loadHistSearch()
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])
    const cmdInput = document.getElementById('cmd')
    cmdInput.value = 'pre-draft'

    enterHistSearch()
    // Simulate user typing 'di': browser sets cmdInput.value before the input event fires
    cmdInput.value = 'di'
    handleHistSearchInput('di')

    const e = Object.assign(new Event('keydown', { cancelable: true }), {
      key: 'c',
      ctrlKey: true,
      metaKey: false,
      altKey: false,
    })
    const handled = handleHistSearchKey(e)

    expect(handled).toBe(true)
    expect(isHistSearchMode()).toBe(false)
    // keepCurrent: typed query stays in input, pre-draft is NOT restored
    expect(cmdInput.value).toBe('di')
  })

  it('handleHistSearchKey ArrowDown wraps from the last match back to the first', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, handleHistSearchKey } =
      loadHistSearch()
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }, { command: 'dig darklab.sh MX' }])
    const cmdInput = document.getElementById('cmd')

    enterHistSearch()
    cmdInput.value = 'dig'
    handleHistSearchInput('dig')

    const down = Object.assign(new Event('keydown', { cancelable: true }), {
      key: 'ArrowDown',
      ctrlKey: false,
      metaKey: false,
      altKey: false,
    })
    handleHistSearchKey(down)
    expect(cmdInput.value).toBe('dig darklab.sh MX')

    // ArrowDown at the last item wraps back to the first
    handleHistSearchKey(down)
    expect(cmdInput.value).toBe('dig darklab.sh A')
  })

  it('handleHistSearchKey ArrowUp wraps from the first match back to the last', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, handleHistSearchKey } =
      loadHistSearch()
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }, { command: 'dig darklab.sh MX' }])
    const cmdInput = document.getElementById('cmd')

    enterHistSearch()
    cmdInput.value = 'dig'
    handleHistSearchInput('dig')
    // index starts at 0 (first match); ArrowUp wraps to the last match
    const up = Object.assign(new Event('keydown', { cancelable: true }), {
      key: 'ArrowUp',
      ctrlKey: false,
      metaKey: false,
      altKey: false,
    })
    const handled = handleHistSearchKey(up)

    expect(handled).toBe(true)
    expect(cmdInput.value).toBe('dig darklab.sh MX')
  })

  it('handleHistSearchKey Tab with no matches exits keeping the typed query in input', () => {
    const submitComposerCommand = vi.fn()
    const {
      hydrateCmdHistory,
      enterHistSearch,
      handleHistSearchInput,
      handleHistSearchKey,
      isHistSearchMode,
    } = loadHistSearch({ submitComposerCommand })
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])
    const cmdInput = document.getElementById('cmd')
    cmdInput.value = 'xyz-pre'

    enterHistSearch()
    cmdInput.value = 'xyz'
    handleHistSearchInput('xyz') // no matches

    const e = Object.assign(new Event('keydown', { cancelable: true }), {
      key: 'Tab',
      ctrlKey: false,
      metaKey: false,
      altKey: false,
    })
    const handled = handleHistSearchKey(e)

    expect(handled).toBe(true)
    expect(isHistSearchMode()).toBe(false)
    // keepCurrent path: typed query stays, pre-draft is NOT restored
    expect(cmdInput.value).toBe('xyz')
    expect(submitComposerCommand).not.toHaveBeenCalled()
  })

  it('handleHistSearchKey Enter after ArrowDown runs the navigated-to match', () => {
    const submitComposerCommand = vi.fn()
    const {
      hydrateCmdHistory,
      enterHistSearch,
      handleHistSearchInput,
      handleHistSearchKey,
      isHistSearchMode,
    } = loadHistSearch({ submitComposerCommand })
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }, { command: 'dig darklab.sh MX' }])
    const cmdInput = document.getElementById('cmd')

    enterHistSearch()
    cmdInput.value = 'dig'
    handleHistSearchInput('dig')

    const down = Object.assign(new Event('keydown', { cancelable: true }), {
      key: 'ArrowDown',
      ctrlKey: false,
      metaKey: false,
      altKey: false,
    })
    handleHistSearchKey(down) // moves to index 1 → 'dig darklab.sh MX'

    const enter = Object.assign(new Event('keydown', { cancelable: true }), {
      key: 'Enter',
      ctrlKey: false,
      metaKey: false,
      altKey: false,
    })
    handleHistSearchKey(enter)

    expect(isHistSearchMode()).toBe(false)
    expect(cmdInput.value).toBe('dig darklab.sh MX')
    expect(submitComposerCommand).toHaveBeenCalledWith('dig darklab.sh MX', {
      dismissKeyboard: true,
    })
  })

  it('resetCmdHistoryNav exits hist search mode if active', () => {
    const { hydrateCmdHistory, enterHistSearch, resetCmdHistoryNav, isHistSearchMode } =
      loadHistSearch()
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])

    enterHistSearch()
    expect(isHistSearchMode()).toBe(true)
    resetCmdHistoryNav()
    expect(isHistSearchMode()).toBe(false)
  })

  it('dropdown keeps cmdHistory matches when server fetch returns empty', async () => {
    // Regression: typing a character showed cmdHistory matches briefly, then
    // the server response (empty — e.g. stale route, rate limit, slow DB)
    // overwrote `_histSearchRuns = []` and the dropdown cleared to "(no matches)".
    // Client-side matches must not be dropped by an empty server response.
    document.body.innerHTML = `
      <div id="history-row"><span class="history-label">Recent:</span></div>
      <input id="cmd" />
      <div id="history-panel"></div>
      <div id="hist-search-dropdown"></div>
    `
    const cmdInput = document.getElementById('cmd')
    const dropdown = document.getElementById('hist-search-dropdown')
    let resolveFetch
    const fetchPromise = new Promise((resolve) => { resolveFetch = resolve })
    const apiFetch = vi.fn(() => fetchPromise)

    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput } = fromDomScripts(
      ['app/static/js/history.js'],
      {
        document,
        localStorage: new MemoryStorage(),
        APP_CONFIG: { recent_commands_limit: 20 },
        histRow: document.getElementById('history-row'),
        cmdInput,
        historyPanel: document.getElementById('history-panel'),
        histSearchDropdown: dropdown,
        shellPromptWrap: document.createElement('div'),
        acHide: vi.fn(),
        apiFetch,
        refreshHistoryPanel: vi.fn(),
        useMobileTerminalViewportMode: () => false,
        setComposerValue: (val) => { cmdInput.value = String(val ?? '') },
        getComposerValue: () => cmdInput.value,
        submitComposerCommand: vi.fn(),
      },
      `{ hydrateCmdHistory, enterHistSearch, handleHistSearchInput }`,
    )

    hydrateCmdHistory([
      { command: 'ping -c 4 darklab.sh' },
      { command: 'dig darklab.sh A' },
      { command: 'dnsenum --dnsserver 8.8.8.8 darklab.sh' },
    ])
    enterHistSearch()
    cmdInput.value = 'd'
    handleHistSearchInput('d')
    // Resolve the debounced fetch with an empty server response.
    vi.useFakeTimers()
    try {
      // Re-trigger after installing fake timers — the debounce ran on real timers.
      handleHistSearchInput('d')
      await vi.advanceTimersByTimeAsync(150)
    } finally {
      vi.useRealTimers()
    }
    resolveFetch({ json: () => Promise.resolve({ runs: [] }) })
    await fetchPromise
    await Promise.resolve()

    const items = dropdown.querySelectorAll('.hist-search-item')
    expect(items.length).toBeGreaterThanOrEqual(3)
    expect(dropdown.querySelector('.hist-search-empty')).toBeNull()
  })

  it('dropdown merges cmdHistory matches with unique server-only matches', async () => {
    // Server may surface older runs beyond the in-memory recents cap.
    // These should extend the cmdHistory list, deduped, not replace it.
    document.body.innerHTML = `
      <div id="history-row"><span class="history-label">Recent:</span></div>
      <input id="cmd" />
      <div id="history-panel"></div>
      <div id="hist-search-dropdown"></div>
    `
    const cmdInput = document.getElementById('cmd')
    const dropdown = document.getElementById('hist-search-dropdown')
    const apiFetch = vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({
        runs: [
          { command: 'dig darklab.sh A' },                  // dedup with cmdHistory
          { command: 'dnsenum darklab.sh' },                // server-only
        ],
      }),
    }))

    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput } = fromDomScripts(
      ['app/static/js/history.js'],
      {
        document,
        localStorage: new MemoryStorage(),
        APP_CONFIG: { recent_commands_limit: 20 },
        histRow: document.getElementById('history-row'),
        cmdInput,
        historyPanel: document.getElementById('history-panel'),
        histSearchDropdown: dropdown,
        shellPromptWrap: document.createElement('div'),
        acHide: vi.fn(),
        apiFetch,
        refreshHistoryPanel: vi.fn(),
        useMobileTerminalViewportMode: () => false,
        setComposerValue: (val) => { cmdInput.value = String(val ?? '') },
        getComposerValue: () => cmdInput.value,
        submitComposerCommand: vi.fn(),
      },
      `{ hydrateCmdHistory, enterHistSearch, handleHistSearchInput }`,
    )

    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])
    enterHistSearch()
    cmdInput.value = 'd'
    handleHistSearchInput('d')
    await new Promise((r) => setTimeout(r, 160))

    const items = [...dropdown.querySelectorAll('.hist-search-item')].map((el) => el.textContent)
    expect(items).toContain('dig darklab.sh A')
    expect(items).toContain('dnsenum darklab.sh')
    // Dedup — no duplicate dig entry.
    expect(items.filter((t) => t === 'dig darklab.sh A').length).toBe(1)
  })
})
