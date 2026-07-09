import { readFileSync } from 'fs'
import { resolve } from 'path'
import { vi } from 'vitest'
import { MemoryStorage, fromDomScripts } from './helpers/extract.js'

const HISTORY_CSS = readFileSync(resolve(process.cwd(), 'app/static/css/features/history.css'), 'utf8')
const _noopFetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({ commands: [] }) })
const HISTORY_SCRIPT_PATHS = [
  'app/static/js/core/history_core.js',
  'app/static/js/features/run-comparison/history_compare_core.js',
  'app/static/js/features/run-comparison/history_compare_overlay.js',
  'app/static/js/features/history/history_run_modal_state_bridge.js',
  'app/static/js/features/history/history_panel_bridge.js',
  'app/static/js/features/history/history_actions.js',
  'app/static/js/features/history/history_project_actions.js',
  'app/static/js/features/history/history_recall.js',
  'app/static/js/history.js',
  'app/static/js/features/history/history_links.js',
  'app/static/js/features/history/history_mutations.js',
  'app/static/js/features/history/history_rows.js',
  'app/static/js/features/history/history_restore.js',
  'app/static/js/features/history/history_run_details.js',
  'app/static/js/features/history/history_search.js',
  'app/static/js/features/run-comparison/history_compare_controls.js',
  'app/static/js/features/run-comparison/history_compare_navigation.js',
  'app/static/js/features/run-comparison/history_compare_renderer.js',
  'app/static/js/features/run-comparison/history_compare_launcher.js',
]
const HISTORY_WITH_UTILS_SCRIPT_PATHS = ['app/static/js/core/utils.js', ...HISTORY_SCRIPT_PATHS]

async function flushPromises(times = 4) {
  for (let index = 0; index < times; index += 1) {
    await Promise.resolve()
  }
}

async function flushFakeTimers(ms = 0) {
  await vi.advanceTimersByTimeAsync(ms)
  await flushPromises()
}

/**
 * Load star functions with an injectable apiFetch mock. Each call returns a
 * fresh scope so tests stay isolated.
 */
function loadStarHelpers(mockApiFetch = _noopFetch) {
  const storage = new MemoryStorage()
  const fns = fromDomScripts(
    HISTORY_SCRIPT_PATHS,
    {
      localStorage: storage,
      APP_CONFIG: { recent_commands_limit: 20 },
      apiFetch: mockApiFetch,
      window: {
        APP_CONFIG: { recent_commands_limit: 20 },
        apiFetch: mockApiFetch,
      },
    },
    `({
      _getStarred,
      _saveStarred,
      _toggleStar,
      loadStarredFromServer,
    })`,
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
      id: 'tab-1',
      commandHistory: [],
      historyNavIndex: -1,
      historyNavDraft: '',
    }

    return fromDomScripts(
      HISTORY_SCRIPT_PATHS,
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
        activeTab,
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
      `window.APP_STATE_API.setTabs([activeTab]);
       window.APP_STATE_API.setActiveTabId(activeTab.id);
       window.APP_CONFIG = APP_CONFIG;
       window.apiFetch = apiFetch;
       window.renderHistory = renderHistory;
       window.useMobileTerminalViewportMode = useMobileTerminalViewportMode;`,
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
      HISTORY_SCRIPT_PATHS,
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
      `window.APP_CONFIG = APP_CONFIG;
       window.useMobileTerminalViewportMode = useMobileTerminalViewportMode;`,
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
      HISTORY_SCRIPT_PATHS,
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
      `window.APP_CONFIG = APP_CONFIG;
       window.useMobileTerminalViewportMode = useMobileTerminalViewportMode;`,
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
  function loadHistoryPanel({
    clipboardImpl,
    apiFetchImpl,
    mobileMode = false,
    appConfig = {},
    activeProject = null,
    showConfirmImpl = vi.fn(() => Promise.resolve(null)),
    openMetadataEditorImpl = vi.fn(),
    openAtlasImpl = vi.fn(() => Promise.resolve()),
    openWatchersModalImpl = vi.fn(() => Promise.resolve()),
    downloadBlobAsAttachmentImpl = vi.fn(),
    emitUiEvent = vi.fn(),
    submitComposerCommandImpl = vi.fn(() => true),
    activeTeamScopeCanImpl = () => true,
    teamScopeDeniedMessageImpl = action => `View-only team members can't ${action}. Switch to Personal or ask for operator access.`,
    scriptPaths = HISTORY_WITH_UTILS_SCRIPT_PATHS,
  } = {}) {
    document.body.innerHTML = `
      <div id="history-panel"></div>
      <input id="history-search-input" />
      <button id="history-mobile-filters-toggle"></button>
      <div id="history-advanced-filters"></div>
      <select id="history-type-filter">
        <option value="all">all</option>
        <option value="runs">runs</option>
        <option value="runs_builtin">built-in</option>
        <option value="runs_external">external</option>
        <option value="snapshots">snapshots</option>
      </select>
      <input id="history-root-input" />
      <div id="history-root-dropdown" class="u-hidden"></div>
      <select id="history-signal-filter">
        <option value="all">all</option>
        <option value="findings">findings</option>
        <option value="warnings">warnings</option>
        <option value="errors">errors</option>
        <option value="summaries">summaries</option>
      </select>
      <select id="history-kind-filter">
        <option value="all">all</option>
        <option value="error">error</option>
        <option value="warn">warn</option>
        <option value="notice">notice</option>
        <option value="info">info</option>
      </select>
      <input id="history-entity-input" />
      <select id="history-entity-type-filter">
        <option value="all">all</option>
        <option value="domain">domain</option>
        <option value="ip">ip</option>
        <option value="url">url</option>
        <option value="hash">hash</option>
        <option value="cve">cve</option>
      </select>
      <select id="history-exit-filter">
        <option value="all">all</option>
        <option value="0">0</option>
        <option value="nonzero">nonzero</option>
        <option value="-15">-15</option>
        <option value="incomplete">incomplete</option>
      </select>
      <select id="history-date-filter">
        <option value="all">all</option>
        <option value="24h">24h</option>
        <option value="7d">7d</option>
        <option value="30d">30d</option>
      </select>
      <select id="history-project-filter">
        <option value="all">all</option>
      </select>
      <input id="history-starred-toggle" type="checkbox" />
      <button id="history-clear-filters"></button>
      <div id="history-active-filters" class="u-hidden"></div>
      <div id="history-bulk-toolbar" class="u-hidden"></div>
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
        if (url === '/projects?include_archived=1') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ projects: [] }),
          })
        }
        if (url === '/history/run-1?json&preview=1') {
          const scheduleId = 'sch_c38d8b4eee00d435b91d1d7791e5ff70c'
          return Promise.resolve({
            json: () =>
              Promise.resolve({
                command: 'ping darklab.sh',
                schedule_id: scheduleId,
                scheduled: true,
                output: ['ok'],
                output_entries: [{ text: 'ok', cls: '' }],
                command_outcome_summary: {
                  title: 'Command outcome',
                  items: [{ label: 'Result', value: 'Finished cleanly' }],
                },
                exit_code: 0,
              }),
          })
        }
        if (url === '/history/run-1?json') {
          return Promise.resolve({
            json: () =>
              Promise.resolve({
                id: 'run-1',
                command: 'ping darklab.sh',
                output_entries: [{ text: 'full export line', cls: '' }],
                command_outcome_summary: {
                  title: 'Command outcome',
                  items: [{ label: 'Result', value: 'Finished cleanly' }],
                },
                exit_code: 0,
                started: '2026-01-01T00:00:00Z',
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
    const clearTab = vi.fn((id) => {
      const tab = tabs.find((t) => t.id === id)
      if (tab) tab.rawLines = []
    })
    const activateTab = vi.fn()
    const appendLine = vi.fn()
    const appendCommandEcho = vi.fn()
    const renderCommandOutcomeSummary = vi.fn()
    const hasPendingOutputBatch = vi.fn(() => false)
    const bindDismissible = vi.fn()
    const bindPressable = vi.fn((el, opts = {}) => {
      if (!el || typeof opts.onActivate !== 'function') return
      el.addEventListener('click', (event) => opts.onActivate(event))
    })
    const refocusComposerAfterAction = vi.fn(() => false)
    const setTabStatus = vi.fn((id, st) => {
      const tab = tabs.find((t) => t.id === id)
      if (tab) tab.st = st
    })
    const hideTabKillBtn = vi.fn()
    const tabs = [{ id: 'tab-1', command: '', rawLines: [], st: 'idle' }]
    const historyPanel = document.getElementById('history-panel')
    const isHistoryPanelOpen = () => historyPanel.classList.contains('open')
    const historyList = document.getElementById('history-list')
    const historyLoadOverlay = document.getElementById('history-load-overlay')
    const historySearchInput = document.getElementById('history-search-input')
    const historyMobileFiltersToggle = document.getElementById('history-mobile-filters-toggle')
    const historyAdvancedFilters = document.getElementById('history-advanced-filters')
    const historyTypeFilter = document.getElementById('history-type-filter')
    const historyRootInput = document.getElementById('history-root-input')
    const historyRootDropdown = document.getElementById('history-root-dropdown')
    const historySignalFilter = document.getElementById('history-signal-filter')
    const historyKindFilter = document.getElementById('history-kind-filter')
    const historyEntityInput = document.getElementById('history-entity-input')
    const historyEntityTypeFilter = document.getElementById('history-entity-type-filter')
    const historyExitFilter = document.getElementById('history-exit-filter')
    const historyDateFilter = document.getElementById('history-date-filter')
    const historyProjectFilter = document.getElementById('history-project-filter')
    const historyStarredToggle = document.getElementById('history-starred-toggle')
    const historyClearFiltersBtn = document.getElementById('history-clear-filters')
    const historyActiveFilters = document.getElementById('history-active-filters')
    const historyBulkToolbar = document.getElementById('history-bulk-toolbar')
    const historyPagination = document.getElementById('history-pagination')
    const historyPaginationSummary = document.getElementById('history-pagination-summary')
    const historyPaginationControls = document.getElementById('history-pagination-controls')
    const cmdInput = document.getElementById('cmd')
    const location = { origin: 'https://example.test' }
    const windowOpen = vi.fn()
    const harnessWindow = {
      open: windowOpen,
      downloadBlobAsAttachment: downloadBlobAsAttachmentImpl,
      APP_CONFIG: { recent_commands_limit: 50, history_panel_limit: 8, ...appConfig },
    }
    harnessWindow.apiFetch = apiFetch
    globalThis.openEntityMetadataEditor = openMetadataEditorImpl

    return {
      ...fromDomScripts(
        scriptPaths,
        {
          document,
          localStorage: new MemoryStorage(),
          APP_CONFIG: { recent_commands_limit: 50, history_panel_limit: 8, ...appConfig },
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
          historySignalFilter,
          historyKindFilter,
          historyEntityInput,
          historyEntityTypeFilter,
          historyExitFilter,
          historyDateFilter,
          historyProjectFilter,
          historyStarredToggle,
          historyClearFiltersBtn,
          historyActiveFilters,
          historyBulkToolbar,
          historyPagination,
          historyPaginationSummary,
          historyPaginationControls,
          histRow: document.createElement('div'),
          showConfirm: showConfirmImpl,
          getActiveProjectContext: () => activeProject,
          refreshActiveProjectContext: () => Promise.resolve(activeProject),
          getHistoryRunModalState: () => harnessWindow._historyRunModalState || null,
          refreshProjectWorkspace: vi.fn(() => Promise.resolve()),
          enhanceAppSelects: vi.fn(),
          cmdInput,
          tabs,
          getTab: id => tabs.find(t => t.id === id),
          getOutput: id => document.getElementById(`output-${id}`),
          activateTab,
          createTab,
          clearTab,
          appendLine,
          appendCommandEcho,
          renderCommandOutcomeSummary,
          hasPendingOutputBatch,
          setTabStatus,
          hideTabKillBtn,
          showToast,
          window: harnessWindow,
          refreshHistoryPanel: () => {},
          renderHistory: () => {},
          isHistoryPanelOpen,
          hideHistoryPanel: vi.fn(() => {
            historyPanel.classList.remove('open')
            if (typeof cmdInput.focus === 'function') cmdInput.focus()
          }),
          emitUiEvent,
          openAtlas: openAtlasImpl,
          openWatchersModal: openWatchersModalImpl,
          downloadBlobAsAttachment: downloadBlobAsAttachmentImpl,
          bindPressable,
          confirmHistAction: () => {},
          executeHistAction: () => {},
          bindDismissible,
          useMobileTerminalViewportMode: () => mobileMode,
          submitComposerCommand: submitComposerCommandImpl,
          setComposerValue: (val, start = null, end = null) => {
            cmdInput.value = String(val ?? '')
            if (typeof start === 'number') cmdInput.selectionStart = start
            if (typeof end === 'number') cmdInput.selectionEnd = end
          },
          refocusComposerAfterAction,
          activeTeamScopeCan: activeTeamScopeCanImpl,
          teamScopeDeniedMessage: teamScopeDeniedMessageImpl,
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
        _historyResetSelectionOnClose,
        _handleHistoryRunExport,
        _historyRunPrimary,
        _historyRunPlainExportText,
        _restoreBothHistoryCompareRuns,
        _highlightRestoredHistoryLine,
        resetHistoryMobileFilters,
        toggleHistoryMobileFilters,
        _saveStarred,
      }`,
      `if (typeof window === 'object' && window) {
        window.useMobileTerminalViewportMode = useMobileTerminalViewportMode;
        window.APP_CONFIG = APP_CONFIG;
        globalThis.APP_CONFIG = APP_CONFIG;
        window.getTabs = () => tabs;
        window.getTab = id => tabs.find(t => t.id === id);
        window.getOutput = getOutput;
        window.createTab = createTab;
        window.clearTab = clearTab;
        window.setTabStatus = setTabStatus;
        window.appendLine = appendLine;
        window.appendCommandEcho = appendCommandEcho;
        window._appendHistoryOutputLine = _appendHistoryOutputLine;
        window.renderCommandOutcomeSummary = renderCommandOutcomeSummary;
        window.hasPendingOutputBatch = hasPendingOutputBatch;
        window.hideTabKillBtn = hideTabKillBtn;
        window.hideHistoryPanel = hideHistoryPanel;
        window.showHistoryLoadOverlay = () => {
          historyLoadOverlay.classList.add('open');
          historyLoadOverlay.setAttribute('aria-hidden', 'false');
        };
        window.hideHistoryLoadOverlay = () => {
          historyLoadOverlay.classList.remove('open');
          historyLoadOverlay.setAttribute('aria-hidden', 'true');
        };
        window.refreshHistoryPanel = refreshHistoryPanel;
        window.isHistoryPanelOpen = isHistoryPanelOpen;
        window.showConfirm = showConfirm;
        window.getActiveProjectContext = getActiveProjectContext;
        window.refreshActiveProjectContext = refreshActiveProjectContext;
        window.refreshProjectWorkspace = refreshProjectWorkspace;
        window.enhanceAppSelects = enhanceAppSelects;
        window.syncAppSelect = syncAppSelect;
        window.bindDismissible = bindDismissible;
        window.emitUiEvent = emitUiEvent;
        window.openHistoryRunDetails = openHistoryRunDetails;
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
      submitComposerCommand: submitComposerCommandImpl,
      showToast,
      tabs,
      bindDismissible,
      bindPressable,
      refocusComposerAfterAction,
      showConfirm: showConfirmImpl,
      openMetadataEditor: openMetadataEditorImpl,
      openAtlas: openAtlasImpl,
      openWatchersModal: openWatchersModalImpl,
      downloadBlobAsAttachment: downloadBlobAsAttachmentImpl,
      emitUiEvent,
    }
  }

  it('centers restored finding highlights in the terminal output container', () => {
    const { _highlightRestoredHistoryLine, tabs } = loadHistoryPanel()
    const out = document.createElement('div')
    out.id = 'output-tab-1'
    out.scrollTop = 500
    Object.defineProperty(out, 'clientHeight', { value: 200, configurable: true })
    out.getBoundingClientRect = () => ({ top: 100, height: 200 })

    const line = document.createElement('span')
    line.className = 'line'
    line.dataset.lineIndex = '42'
    line.getBoundingClientRect = () => ({ top: 260, height: 20 })
    out.appendChild(line)
    document.body.appendChild(out)

    _highlightRestoredHistoryLine('tab-1', { lineIndex: 42 })

    expect(line.classList.contains('history-source-highlight')).toBe(true)
    expect(out.scrollTop).toBe(570)
    expect(tabs[0].followOutput).toBe(false)
  })

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

  it('clicking a history entry row opens run details without closing the panel', async () => {
    const clipboard = { writeText: vi.fn(() => Promise.resolve()) }
    const openAtlas = vi.fn(() => Promise.resolve())
    const {
      refreshHistoryPanel,
      apiFetch,
      _handleHistoryRunExport,
      _historyRunPrimary,
      _historyRunPlainExportText,
    } = loadHistoryPanel({
      clipboardImpl: clipboard,
      openAtlasImpl: openAtlas,
    })
    const historyPanel = document.getElementById('history-panel')
    const cmdInput = document.getElementById('cmd')
    historyPanel.classList.add('open')

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    const entry = document.querySelector('#history-list .history-entry')
    entry.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    await Promise.resolve()

    expect(cmdInput.value).toBe('')
    expect(historyPanel.classList.contains('open')).toBe(true)
    expect(document.getElementById('history-run-overlay').classList.contains('open')).toBe(true)
    expect(document.getElementById('history-run-subtitle').textContent).toBe('ping darklab.sh')
    const scheduleSummary = document.querySelector('.history-run-schedule-summary')
    expect(scheduleSummary?.textContent).toBe('Scheduled runView schedule')
    expect(scheduleSummary?.textContent).not.toContain('sch_c38d8b4eee00d435b91d1d7791e5ff70c')
    expect(scheduleSummary?.querySelector('[data-history-run-action="open-schedule"]')?.getAttribute('title'))
      .toBe('Open schedule sch_c38d8b4eee00d435b91d1d7791e5ff70c')
    expect([...document.querySelectorAll('.history-run-tab')].map(tab => tab.textContent)).toEqual([
      'Summary',
      'Output',
      'Findings',
      'Entities',
      'Artifacts',
    ])
    const runActions = [...document.querySelector('.history-run-actions').children].map(el => el.textContent)
    expect(runActions).toEqual([
      'Restore',
      'Delete',
      'Permalink',
      'Compare',
      'Atlas',
      'ActionsCopy commandSchedule this commandCreate watcher from this baselineEdit metadataOpen in AtlasAdd to active projectAdd to projectCopy run ID',
    ])
    document.querySelector('.history-run-action-menu-trigger').click()
    expect(document.querySelector('.history-run-action-menu-wrap').classList.contains('open')).toBe(true)
    document
      .querySelector('[data-history-run-action="copy-command"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    expect(clipboard.writeText).toHaveBeenCalledWith('ping darklab.sh')

    document.querySelector('.history-run-export-menu-trigger')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(document.querySelector('.history-run-export-menu-wrap').classList.contains('open')).toBe(true)
    expect(_historyRunPrimary().id).toBe('run-1')
    expect(_historyRunPlainExportText({ output_entries: [{ text: 'full export line', cls: '' }] }))
      .toBe('full export line')
    await _handleHistoryRunExport('txt')
    expect(apiFetch).toHaveBeenCalledWith('/history/run-1?json', { cache: 'no-store' })

    document.querySelector('.history-run-action-menu-trigger').click()
    document
      .querySelector('[data-history-run-action="open-atlas"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()

    expect(openAtlas).toHaveBeenCalledWith({
      source: 'run-details',
      tab: 'findings',
      runId: 'run-1',
      runLabel: 'ping darklab.sh',
    })

    document.querySelector('[data-history-run-tab="output"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(document.getElementById('history-run-body').textContent).toContain('Command outcome')
    expect(document.getElementById('history-run-body').textContent).toContain('ResultFinished cleanly')
    expect(_historyRunPlainExportText(_historyRunPrimary())).toContain('Command outcome')
  })

  it('opens the watchers modal from the Run Details baseline action', async () => {
    const openWatchersModal = vi.fn(() => Promise.resolve())
    const { refreshHistoryPanel } = loadHistoryPanel({ openWatchersModalImpl: openWatchersModal })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    document.querySelector('#history-list .history-entry')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    await Promise.resolve()

    document.querySelector('.history-run-action-menu-trigger').click()
    document
      .querySelector('[data-history-run-action="watch-command"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()

    expect(openWatchersModal).toHaveBeenCalledWith(expect.objectContaining({
      baselineRun: expect.objectContaining({
        command: 'ping darklab.sh',
      }),
    }))
  })

  it('renders Run Details AI summary actions when AI summaries are enabled', async () => {
    vi.useFakeTimers()
    let aiSummaryPosts = 0
    let aiNextPosts = 0
    let aiAssistReads = 0
    const clipboard = { writeText: vi.fn(() => Promise.resolve()) }
    const submitComposerCommand = vi.fn(() => false)
    const apiFetch = vi.fn((url, options = {}) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          json: () => Promise.resolve({
            roots: ['nmap'],
            items: [
              {
                id: 'run-ai',
                type: 'run',
                command: 'nmap darklab.sh',
                label: 'nmap darklab.sh',
                started: '2026-01-01T00:00:00Z',
                finished: '2026-01-01T00:00:02Z',
                exit_code: 0,
              },
              {
                id: 'run-builtin-ai',
                type: 'run',
                run_kind: 'builtin',
                command: 'help',
                label: 'help',
                started: '2026-01-01T00:01:00Z',
                finished: '2026-01-01T00:01:01Z',
                exit_code: 0,
              },
            ],
            runs: [],
          }),
        })
      }
      if (url === '/history/run-ai?json&preview=1') {
        return Promise.resolve({
          json: () => Promise.resolve({
            id: 'run-ai',
            command: 'nmap darklab.sh',
            started: '2026-01-01T00:00:00Z',
            finished: '2026-01-01T00:00:02Z',
            output_entries: [{ text: '443/tcp open https', cls: '' }],
            output_summary: {
              kinds: { output: 16 },
              signals: { findings: 14 },
              signal_toc: [
                { line_number: 3, signal: 'summaries', text: 'Host is up.' },
                { line_number: 4, signal: 'errors', text: 'Not shown: closed ports.' },
                ...Array.from({ length: 12 }, (_, index) => ({
                  line_number: index + 6,
                  signal: 'findings',
                  text: `${1000 + index}/tcp open test-service-${index}`,
                })),
              ],
            },
            exit_code: 0,
          }),
        })
      }
      if (url === '/history/run-builtin-ai?json&preview=1') {
        return Promise.resolve({
          json: () => Promise.resolve({
            id: 'run-builtin-ai',
            run_kind: 'builtin',
            command: 'help',
            started: '2026-01-01T00:01:00Z',
            finished: '2026-01-01T00:01:01Z',
            output_entries: [{ text: 'Built-in help output', cls: '' }],
            exit_code: 0,
          }),
        })
      }
      if (url === '/runs/run-ai/ai-assists' && (!options || !options.method)) {
        aiAssistReads += 1
        const completedSummaryRefresh = aiSummaryPosts >= 2 && aiAssistReads > 2
        const completedNextRefresh = aiNextPosts >= 1 && aiAssistReads > 1
        const assists = []
        if (completedSummaryRefresh) {
          assists.push({
            id: 'ai_2',
            run_id: 'run-ai',
            variant: 'summary',
            status: 'completed',
            payload: {
              summary: 'Refresh finished.',
              key_findings: ['443/tcp open https'],
              next_steps_hint: 'Done.',
            },
          })
        } else if (aiSummaryPosts >= 1) {
          assists.push({
            id: 'ai_1',
            run_id: 'run-ai',
            variant: 'summary',
            status: 'completed',
            payload: {
              summary: 'HTTPS is open on the target.',
              key_findings: ['443/tcp open https'],
              next_steps_hint: 'Inspect TLS details.',
            },
          })
        }
        if (completedNextRefresh) {
          const nextSuggestions = aiNextPosts >= 2
            ? [{
                command: 'nmap -sV --script=http-vuln -p 318 darklab.sh',
                reason: 'Model draft used an absent port.',
                risk_label: 'medium',
                target: 'darklab.sh',
                target_allowed: true,
                validation_result: 'rejected',
                rejection_reason: 'port_absent',
              }]
            : [
                {
                  command: 'sslscan darklab.sh',
                  reason: 'Inspect certificate and TLS settings.',
                  risk_label: 'low',
                  target: 'darklab.sh',
                  target_allowed: true,
                  validation_result: 'accepted',
                  rejection_reason: '',
                },
                {
                  command: 'nmap -sV --script=http-vuln -p 318 darklab.sh',
                  reason: 'Model draft used an absent port.',
                  risk_label: 'medium',
                  target: 'darklab.sh',
                  target_allowed: true,
                  validation_result: 'rejected',
                  rejection_reason: 'port_absent',
                },
              ]
          assists.push({
            id: aiNextPosts >= 2 ? 'ai_next_2' : 'ai_next_1',
            run_id: 'run-ai',
            variant: 'next_commands',
            status: 'completed',
            payload: {
              suggestions: nextSuggestions,
            },
          })
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ assists }),
        })
      }
      if (url === '/runs/run-ai/ai-summary' && options.method === 'POST') {
        aiSummaryPosts += 1
        const body = JSON.parse(options.body || '{}')
        if (aiSummaryPosts === 1) expect(body).toEqual({})
        if (aiSummaryPosts === 2) expect(body).toEqual({ force: true })
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            assist: {
              id: aiSummaryPosts === 1 ? 'ai_1' : 'ai_2',
              run_id: 'run-ai',
              variant: 'summary',
              status: aiSummaryPosts === 1 ? 'completed' : 'queued',
              payload: {
                summary: 'HTTPS is open on the target.',
                key_findings: ['443/tcp open https'],
                next_steps_hint: 'Inspect TLS details.',
              },
            },
          }),
        })
      }
      if (url === '/runs/run-ai/ai-next-commands' && options.method === 'POST') {
        aiNextPosts += 1
        if (aiNextPosts >= 3) {
          return Promise.resolve({
            ok: false,
            status: 429,
            json: () => Promise.resolve({
              error: 'ai_rate_limited',
              message: 'AI assists are limited to a few requests per session each hour.',
            }),
          })
        }
        const rejectedOnly = aiNextPosts >= 2
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            assist: {
              id: rejectedOnly ? 'ai_next_2' : 'ai_next_1',
              run_id: 'run-ai',
              variant: 'next_commands',
              status: rejectedOnly ? 'completed' : 'queued',
              payload: {
                suggestions: rejectedOnly ? [{
                  command: 'nmap -sV --script=http-vuln -p 318 darklab.sh',
                  reason: 'Model draft used an absent port.',
                  risk_label: 'medium',
                  target: 'darklab.sh',
                  target_allowed: true,
                  validation_result: 'rejected',
                  rejection_reason: 'port_absent',
                }] : [],
              },
            },
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    try {
      const { refreshHistoryPanel } = loadHistoryPanel({
        apiFetchImpl: apiFetch,
        clipboardImpl: clipboard,
        submitComposerCommandImpl: submitComposerCommand,
        appConfig: {
          ai_enabled: true,
          ai_feature_summary: true,
          ai_feature_next_commands: true,
          ai_feature_run_suggestions: true,
        },
      })

      refreshHistoryPanel()
      await flushFakeTimers()
      document.querySelector('#history-list .history-entry')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await flushPromises()

      expect(apiFetch).toHaveBeenCalledWith('/runs/run-ai/ai-assists', { cache: 'no-store' })
      expect(document.getElementById('history-run-body').textContent).toContain('No AI summary')

      document.querySelector('[data-history-run-action="ai-summary"]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await flushFakeTimers()

      expect(apiFetch).toHaveBeenCalledWith('/runs/run-ai/ai-summary', expect.objectContaining({ method: 'POST' }))
      expect(document.getElementById('history-run-body').textContent).toContain('HTTPS is open on the target.')
      expect(document.getElementById('history-run-body').textContent).toContain('443/tcp open https')
      expect(document.getElementById('history-run-body').textContent).toContain('Inspect TLS details.')

      document.querySelector('[data-history-run-action="ai-next-commands"]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await flushFakeTimers()

      expect(aiNextPosts).toBe(1)
      expect(document.getElementById('history-run-body').textContent).toContain('The AI worker has next-command suggestions queued.')
      expect(document.getElementById('history-run-body').textContent).toContain('Reading the signal map')
      await flushFakeTimers(2100)
      expect(document.getElementById('history-run-body').textContent).toContain('sslscan darklab.sh')
      expect(document.getElementById('history-run-body').textContent).toContain('Inspect certificate and TLS settings.')
      expect(document.getElementById('history-run-body').textContent).toContain('Blocked')
      expect(document.getElementById('history-run-body').textContent).toContain('Rejected: port_absent')
      expect(document.querySelectorAll('[data-history-run-copy-suggestion]')).toHaveLength(1)
      expect(document.querySelectorAll('[data-history-run-run-suggestion]')).toHaveLength(1)
      document.querySelector('[data-history-run-copy-suggestion]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await flushPromises()
      expect(clipboard.writeText).toHaveBeenCalledWith('sslscan darklab.sh')
      document.querySelector('[data-history-run-run-suggestion]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }))
      expect(submitComposerCommand).toHaveBeenCalledWith(
        'sslscan darklab.sh',
        { dismissKeyboard: true, focusAfterSubmit: true },
      )
      expect(document.getElementById('history-run-overlay').classList.contains('open')).toBe(true)

      document.querySelector('[data-history-run-action="ai-next-commands"]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await flushFakeTimers()

      expect(aiNextPosts).toBe(2)
      expect(document.getElementById('history-run-body').textContent).toContain('No safe command suggestions passed validation.')
      expect(document.getElementById('history-run-body').textContent).toContain('nmap -sV --script=http-vuln -p 318 darklab.sh')
      expect(document.getElementById('history-run-body').textContent).toContain('Rejected: port_absent')
      expect(document.querySelectorAll('[data-history-run-copy-suggestion]')).toHaveLength(0)
      expect(document.querySelectorAll('[data-history-run-run-suggestion]')).toHaveLength(0)

      document.querySelector('[data-history-run-action="ai-summary"]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await flushFakeTimers()

      expect(aiSummaryPosts).toBe(2)
      expect(document.getElementById('history-run-body').textContent).toContain('The AI worker has this run queued.')
      expect(document.getElementById('history-run-body').textContent).toContain('Thinking')
      expect(document.activeElement?.id).toBe('history-run-modal')

      await flushFakeTimers(2100)
      expect(apiFetch).toHaveBeenCalledWith('/runs/run-ai/ai-assists', { cache: 'no-store' })
      expect(document.getElementById('history-run-body').textContent).toContain('Refresh finished.')

      document.querySelector('[data-history-run-action="ai-next-commands"]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await flushFakeTimers()

      expect(aiNextPosts).toBe(3)
      expect(document.getElementById('history-run-body').textContent)
        .toContain('AI assists are limited to a few requests per session each hour.')
      expect(document.getElementById('history-run-body').textContent).toContain('Refresh finished.')
      expect(document.getElementById('history-run-body').textContent)
        .not.toContain('Could not start AI suggestions.')

      document.querySelector('[data-history-run-tab="output"]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }))
      expect(document.getElementById('history-run-body').textContent).toContain('1011/tcp open test-service-11')

      document.querySelectorAll('#history-list .history-entry')[1]
        .dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await flushFakeTimers()

      expect(document.getElementById('history-run-modal').textContent).toContain('help')
      expect(document.getElementById('history-run-body').textContent).not.toContain('AI summary')
      expect(document.getElementById('history-run-body').textContent).not.toContain('AI next commands')
      expect(document.querySelector('[data-history-run-action="ai-summary"]')).toBeNull()
      expect(document.querySelector('[data-history-run-action="ai-next-commands"]')).toBeNull()
      expect(apiFetch).not.toHaveBeenCalledWith('/runs/run-builtin-ai/ai-assists', { cache: 'no-store' })
    } finally {
      vi.useRealTimers()
    }
  })

  it('uses shared row primitives for fallback Run Details entity rows', async () => {
    const apiFetch = vi.fn((url) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              roots: ['nmap'],
              items: [
                {
                  id: 'run-entity',
                  type: 'run',
                  command: 'nmap darklab.sh',
                  label: 'nmap darklab.sh',
                  started: '2026-01-01T00:00:00Z',
                  created: '2026-01-01T00:00:00Z',
                  exit_code: 0,
                  atlas_entity_count: 1,
                },
              ],
              runs: [],
            }),
        })
      }
      if (url === '/history/run-entity?json&preview=1') {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              command: 'nmap darklab.sh',
              output: ['ok'],
              exit_code: 0,
              atlas_entity_count: 1,
            }),
        })
      }
      if (typeof url === 'string' && url.startsWith('/entities/run/run-entity/findings')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ findings: [], total: 0, limit: 50, offset: 0 }),
        })
      }
      if (typeof url === 'string' && url.startsWith('/atlas?')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ total: 1, counts: { ip: 1 } }),
        })
      }
      if (typeof url === 'string' && url.startsWith('/atlas/entities?')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              entities: [
                {
                  id: 'ent_1',
                  type: 'ip',
                  canonical_value: '192.0.2.10',
                  occurrence_count: 2,
                  run_count: 1,
                },
              ],
              total: 1,
              limit: 50,
              offset: 0,
              has_more: false,
            }),
        })
      }
      if (url === '/projects?include_archived=1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ projects: [] }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel } = loadHistoryPanel({ apiFetchImpl: apiFetch })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    delete window.apiFetch
    const entry = document.querySelector('#history-list .history-entry')
    entry.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await vi.waitFor(() => {
      expect(document.getElementById('history-run-overlay').classList.contains('open')).toBe(true)
    })

    document.querySelector('[data-history-run-tab="entities"]').click()
    await vi.waitFor(() => {
      expect(document.querySelector('[data-history-run-entity-id="ent_1"]')).not.toBeNull()
    })

    const row = document.querySelector('[data-history-run-entity-id="ent_1"]')
    const panel = document.querySelector('.history-run-entity-panel')
    const list = document.querySelector('.history-run-entity-list')
    expect(panel).not.toBeNull()
    expect(list).not.toBeNull()
    expect(document.getElementById('history-run-body').classList.contains('history-run-body-entities')).toBe(true)
    expect(list.classList.contains('nice-scroll')).toBe(true)
    expect(panel.contains(row)).toBe(true)
    expect(row.classList.contains('chrome-row')).toBe(true)
    expect(row.classList.contains('chrome-row-clickable')).toBe(true)
    expect(row.classList.contains('history-run-list-item')).toBe(false)
    expect(row.textContent).toContain('192.0.2.10')

    expect(HISTORY_CSS).toContain('.history-run-entity-list .atlas-entity-row')
    expect(HISTORY_CSS).toContain('display: flex;')
    expect(HISTORY_CSS).toContain('.history-run-entity-list .atlas-entity-main')
    expect(HISTORY_CSS).toContain('.history-run-entity-list .atlas-entity-value')
    expect(HISTORY_CSS).toContain('.history-run-entity-list .atlas-entity-badges')
  })

  it('shows remove from project in Run Details and can also unlink same-run entities', async () => {
    let linked = true
    const showConfirm = vi.fn((options = {}) => {
      const content = options.content
      expect(content.textContent).toContain('Also remove disposable same-run Atlas entities from this project')
      expect(content.textContent).toContain('This will unlink 1 entity found only in this run.')
      expect(content.textContent).toContain('2 related findings will no longer appear in this project.')
      expect(content.textContent).toContain('Also remove same-run Atlas entities kept by default from this project')
      expect(content.textContent).toContain('1 entity kept by default and 3 related findings will stay in this project unless this is checked.')
      expect(content.textContent).toContain('1 finding and 1 entity not eligible for this cleanup.')
      expect(content.textContent).toContain('Reasons: imported entity, seen elsewhere.')
      content.querySelector('[data-history-project-run-entities-scope="disposable"]').checked = true
      content.querySelector('[data-history-project-run-entities-scope="curated"]').checked = true
      return Promise.resolve('remove')
    })
    const apiFetch = vi.fn((url, options = {}) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            roots: ['nmap'],
            items: [{
              id: 'run-linked',
              type: 'run',
              command: 'nmap darklab.sh',
              label: 'nmap darklab.sh',
              started: '2026-01-01T00:00:00Z',
              created: '2026-01-01T00:00:00Z',
              exit_code: 0,
              project_links: linked ? [{
                id: 'link-active',
                project_id: 'project-active',
                entity_type: 'run',
                entity_id: 'run-linked',
                project: { id: 'project-active', name: 'Active scope', status: 'active' },
              }] : [],
            }],
            runs: [],
          }),
        })
      }
      if (url === '/history/run-linked?json&preview=1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            command: 'nmap darklab.sh',
            output: ['ok'],
            exit_code: 0,
          }),
        })
      }
      if (url === '/entities/run/run-linked/findings') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ findings: [] }) })
      }
      if (url === '/projects/project-active/summary') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ runs: linked ? [{ id: 'run-linked' }] : [] }) })
      }
      if (url === '/projects/project-active/links/run-entities/remove-preview') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            ok: true,
            preview: {
              available: 2,
              removable: 1,
              curated: 1,
              kept_curated: 1,
              removed: 0,
              removed_curated: 0,
              run_findings: 4,
              removable_findings: 2,
              curated_findings: 3,
              kept_curated_findings: 3,
              run_count: 1,
              cleanup_reasons: {
                buckets: {
                  disposable: { entities: 1, findings: 2, total: 3 },
                  kept_by_default: { entities: 1, findings: 3, total: 4 },
                  not_eligible: { entities: 1, findings: 1, total: 2 },
                },
                reasons: [
                  {
                    code: 'imported_entity',
                    bucket: 'not_eligible',
                    label: 'imported entity',
                    entities: 1,
                    findings: 0,
                    total: 1,
                  },
                  {
                    code: 'seen_in_other_runs',
                    bucket: 'not_eligible',
                    label: 'seen elsewhere',
                    entities: 0,
                    findings: 1,
                    total: 1,
                  },
                ],
              },
            },
          }),
        })
      }
      if (url === '/projects/project-active/links' && options.method === 'DELETE') {
        linked = false
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            ok: true,
            unlinked_entities: { removed: 2, removed_curated: 1, kept_curated: 0 },
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) })
    })
    const { refreshHistoryPanel } = loadHistoryPanel({
      apiFetchImpl: apiFetch,
      activeProject: { id: 'project-active', name: 'Active scope' },
      showConfirmImpl: showConfirm,
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    document.querySelector('#history-list .history-entry')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))

    expect([...document.querySelectorAll('.history-run-action-menu [data-history-run-action]')].map(el => el.dataset.historyRunAction))
      .toEqual([
        'copy-command',
        'schedule-command',
        'watch-command',
        'edit-metadata',
        'open-atlas',
        'remove-project',
        'copy-run-id',
      ])
    expect(document.querySelector('[data-history-run-action="add-active-project"]')).toBeNull()
    expect(document.querySelector('[data-history-run-action="add-project"]')).toBeNull()

    document.querySelector('[data-history-run-action="remove-project"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))

    expect(showConfirm).toHaveBeenCalled()
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-active/links', expect.objectContaining({
      method: 'DELETE',
      body: JSON.stringify({
        entity_type: 'run',
        entity_id: 'run-linked',
        include_entities: true,
        include_curated_entities: true,
      }),
    }))
    expect([...document.querySelectorAll('.history-run-action-menu [data-history-run-action]')].map(el => el.dataset.historyRunAction))
      .toContain('add-project')
  })

  it('uses Current Project attachment state for Run Details project actions when link metadata is missing', async () => {
    let linked = true
    const showConfirm = vi.fn((options = {}) => {
      const content = options.content
      const disposableCheckbox = content.querySelector('[data-history-project-run-entities-scope="disposable"]')
      const disposableLabel = disposableCheckbox.closest('label')
      const curatedCheckbox = content.querySelector('[data-history-project-run-entities-scope="curated"]')
      const curatedLabel = curatedCheckbox.closest('label')

      expect(content?.textContent || '').not.toContain('Also remove disposable same-run Atlas entities from this project')
      expect(disposableCheckbox.disabled).toBe(true)
      expect(disposableLabel.hidden).toBe(true)
      expect(disposableLabel.classList.contains('u-hidden')).toBe(true)
      expect(disposableLabel.textContent.trim()).toBe('')
      expect(content?.textContent || '').not.toContain('Also remove same-run Atlas entities kept by default from this project')
      expect(content?.textContent || '').toContain('Remove same-run Atlas entities kept by default from this project')
      expect(curatedCheckbox.disabled).toBe(false)
      expect(curatedLabel.hidden).toBe(false)
      expect(curatedLabel.classList.contains('u-hidden')).toBe(false)
      curatedCheckbox.checked = true
      return Promise.resolve('remove')
    })
    const apiFetch = vi.fn((url, options = {}) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            roots: ['katana'],
            items: [{
              id: 'run-active-linked',
              type: 'run',
              command: 'katana -u https://darklab.sh',
              label: 'katana -u https://darklab.sh',
              started: '2026-01-01T00:00:00Z',
              created: '2026-01-01T00:00:00Z',
              exit_code: 0,
              project_links: [],
            }],
            runs: [],
          }),
        })
      }
      if (url === '/history/run-active-linked?json&preview=1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            id: 'run-active-linked',
            command: 'katana -u https://darklab.sh',
            output: ['ok'],
            exit_code: 0,
          }),
        })
      }
      if (url === '/entities/run/run-active-linked/findings') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ findings: [] }) })
      }
      if (url === '/projects/project-active/summary') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ runs: linked ? [{ id: 'run-active-linked' }] : [] }) })
      }
      if (url === '/projects/project-active/links/run-entities/remove-preview') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            ok: true,
            preview: {
              available: 1,
              removable: 0,
              curated: 1,
              kept_curated: 1,
              removed: 0,
              removed_curated: 0,
              run_findings: 0,
              removable_findings: 0,
              curated_findings: 1,
              kept_curated_findings: 1,
              run_count: 1,
            },
          }),
        })
      }
      if (url === '/projects/project-active/links' && options.method === 'DELETE') {
        linked = false
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ ok: true, unlinked_entities: { removed: 0, kept_curated: 0 } }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) })
    })
    const { refreshHistoryPanel } = loadHistoryPanel({
      apiFetchImpl: apiFetch,
      activeProject: { id: 'project-active', name: 'Active scope' },
      showConfirmImpl: showConfirm,
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    document.querySelector('#history-list .history-entry')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))

    expect([...document.querySelectorAll('.history-run-action-menu [data-history-run-action]')].map(el => el.dataset.historyRunAction))
      .toEqual([
        'copy-command',
        'schedule-command',
        'watch-command',
        'edit-metadata',
        'open-atlas',
        'remove-project',
        'copy-run-id',
      ])
    expect(document.querySelector('[data-history-run-action="add-active-project"]')).toBeNull()
    expect(document.querySelector('[data-history-run-action="add-project"]')).toBeNull()

    document.querySelector('[data-history-run-action="remove-project"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))

    expect(apiFetch).toHaveBeenCalledWith('/projects/project-active/links', expect.objectContaining({
      method: 'DELETE',
      body: JSON.stringify({
        entity_type: 'run',
        entity_id: 'run-active-linked',
        include_entities: true,
        include_curated_entities: true,
      }),
    }))
  })

  it('loads structured run findings into the run details findings tab', async () => {
    const makeFinding = (index, occurrenceCount = 1) => ({
      id: `finding-${index}`,
      title: index === 1 ? 'Missing security header' : `Paged finding ${index}`,
      raw_line: index === 1 ? '[info] missing header' : `[info] finding ${index}`,
      severity: 'info',
      review_state: 'new',
      line_number: index - 1,
      scope: 'http',
      run_occurrence_count: occurrenceCount,
    })
    const apiFetch = vi.fn((url) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            roots: ['nuclei'],
            items: [{
              id: 'run-findings',
              type: 'run',
              command: 'nuclei -u https://darklab.sh',
              label: 'nuclei -u https://darklab.sh',
              started: '2026-01-01T00:00:00Z',
              created: '2026-01-01T00:00:00Z',
              exit_code: 0,
              finding_count: 60,
            }],
            runs: [],
          }),
        })
      }
      if (url === '/history/run-findings?json&preview=1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            id: 'run-findings',
            command: 'nuclei -u https://darklab.sh',
            output: ['finding line'],
            exit_code: 0,
            finding_count: 60,
          }),
        })
      }
      if (url === '/entities/run/run-findings/findings?limit=50&offset=0') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            findings: Array.from({ length: 50 }, (_, index) => makeFinding(index + 1, index === 0 ? 3 : 1)),
            total: 51,
            limit: 50,
            offset: 0,
            has_more: true,
            occurrence_total: 60,
          }),
        })
      }
      if (url === '/entities/run/run-findings/findings?limit=50&offset=50') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            findings: [makeFinding(51)],
            total: 51,
            limit: 50,
            offset: 50,
            has_more: false,
            occurrence_total: 60,
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel } = loadHistoryPanel({ apiFetchImpl: apiFetch })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    document.querySelector('#history-list .history-entry')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))
    await Promise.resolve()
    document.querySelector('[data-history-run-tab="findings"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))

    expect(apiFetch).toHaveBeenCalledWith('/entities/run/run-findings/findings?limit=50&offset=0', { cache: 'no-store' })
    expect(document.querySelector('[data-history-run-tab="findings"]').textContent).toBe('Findings (51)')
    expect(document.getElementById('history-run-body').textContent).toContain('Missing security header')
    expect(document.getElementById('history-run-body').textContent).toContain('[info] missing header')
    expect(document.getElementById('history-run-body').textContent).toContain('3 occurrences')
    expect(document.getElementById('history-run-body').textContent).toContain('1-50 of 51 findings')
    document.querySelector('[data-history-run-findings-page="next"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))
    expect(apiFetch).toHaveBeenCalledWith('/entities/run/run-findings/findings?limit=50&offset=50', { cache: 'no-store' })
    expect(document.getElementById('history-run-body').textContent).toContain('Paged finding 51')
    expect(document.getElementById('history-run-body').textContent).toContain('51-51 of 51 findings')
    document.querySelector('[data-history-run-tab="summary"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(document.getElementById('history-run-body').textContent).toContain('Findings / Occurrences51 / 60')
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

  it('keeps restore and delete visible and moves secondary run actions into an ordered menu', async () => {
    const { refreshHistoryPanel } = loadHistoryPanel()

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    const entry = document.querySelector('#history-list .history-entry')
    const visibleActions = [...entry.querySelector('.history-actions').children].map(el => el.textContent)
    expect(visibleActions).toEqual([
      'copy command',
      'restore',
      'delete',
      'moreeditopen in atlascreate watcher from this baselinepermalinkcompareadd to active projectadd to projectcopy run id',
    ])
    const menuActions = [...entry.querySelectorAll('.history-action-menu [data-action]')].map(el => el.dataset.action)
    expect(menuActions).toEqual([
      'edit-metadata',
      'open-atlas',
      'watch-command',
      'permalink',
      'compare',
      'add-active-project',
      'add-project',
      'copy-run-id',
    ])

    const builtinApiFetch = vi.fn((url) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        const item = {
          id: 'run-1',
          type: 'run',
          run_kind: 'builtin',
          command: 'history',
          label: 'history',
          started: '2026-01-01T00:00:00Z',
          created: '2026-01-01T00:00:00Z',
          exit_code: 0,
        }
        return Promise.resolve({
          json: () => Promise.resolve({ roots: ['history'], items: [item], runs: [item] }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel: refreshBuiltinHistoryPanel } = loadHistoryPanel({ apiFetchImpl: builtinApiFetch })
    refreshBuiltinHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    const builtinEntry = document.querySelector('#history-list .history-entry')
    const builtinMenuActions = [...builtinEntry.querySelectorAll('.history-action-menu [data-action]')]
      .map(el => el.dataset.action)
    expect(builtinMenuActions).toEqual([
      'edit-metadata',
      'permalink',
      'compare',
      'copy-run-id',
    ])
  })

  it('uses copy and restore as mobile history row primaries and moves the rest into the menu', async () => {
    const { refreshHistoryPanel } = loadHistoryPanel({ mobileMode: true })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    const entry = document.querySelector('#history-list .history-entry')
    const visibleActions = [...entry.querySelector('.history-actions').children].map(el => el.textContent)
    expect(visibleActions).toEqual([
      'copy command',
      'restore',
      'moreeditopen in atlascreate watcher from this baselinepermalinkcompareadd to active projectadd to projectcopy run iddelete',
    ])
    const menuActions = [...entry.querySelectorAll('.history-action-menu [data-action]')].map(el => el.dataset.action)
    expect(menuActions).toEqual([
      'edit-metadata',
      'open-atlas',
      'watch-command',
      'permalink',
      'compare',
      'add-active-project',
      'add-project',
      'copy-run-id',
      'delete',
    ])

    entry.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    await Promise.resolve()
    expect(document.getElementById('history-run-overlay').classList.contains('open')).toBe(true)
  })

  it('renders select mode checkboxes and toggles row selection without opening run details', async () => {
    const apiFetch = vi.fn((url) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            roots: ['nmap'],
            items: [
              {
                id: 'run-1',
                type: 'run',
                command: 'nmap darklab.sh',
                started: '2026-01-01T00:00:00Z',
                exit_code: 0,
              },
              {
                id: 'run-running',
                type: 'run',
                command: 'ping darklab.sh',
                started: '2026-01-01T00:00:05Z',
                exit_code: null,
              },
            ],
            runs: [],
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel } = loadHistoryPanel({ apiFetchImpl: apiFetch })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    expect(document.querySelectorAll('[data-action="select-run"]')).toHaveLength(0)
    const toggle = document.querySelector('.history-bulk-toggle input')
    expect(toggle).not.toBeNull()
    toggle.checked = true
    toggle.dispatchEvent(new Event('change', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))

    const rows = [...document.querySelectorAll('#history-list .history-entry')]
    const checkboxes = [...document.querySelectorAll('[data-action="select-run"]')]
    expect(checkboxes).toHaveLength(2)
    expect(checkboxes[0].disabled).toBe(false)
    expect(checkboxes[1].disabled).toBe(true)

    rows[0].dispatchEvent(new MouseEvent('click', { bubbles: true }))

    expect(checkboxes[0].checked).toBe(true)
    expect(document.querySelector('.history-bulk-count').textContent).toBe('1 selected')
    expect(document.getElementById('history-run-overlay')).toBeNull()
  })

  it('selects all visible completed runs, reports mixed state, and clears selection', async () => {
    const apiFetch = vi.fn((url) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            roots: ['dig'],
            items: [
              {
                id: 'run-1',
                type: 'run',
                command: 'dig darklab.sh A',
                started: '2026-01-01T00:00:00Z',
                exit_code: 0,
              },
              {
                id: 'run-2',
                type: 'run',
                command: 'dig darklab.sh MX',
                started: '2026-01-01T00:00:01Z',
                exit_code: 1,
              },
              {
                id: 'run-running',
                type: 'run',
                command: 'dig darklab.sh TXT',
                started: '2026-01-01T00:00:02Z',
                exit_code: null,
              },
            ],
            runs: [],
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel } = loadHistoryPanel({ apiFetchImpl: apiFetch })
    const historyFetchCount = () => apiFetch.mock.calls
      .filter(([url]) => typeof url === 'string' && (url === '/history' || url.startsWith('/history?')))
      .length

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    expect(historyFetchCount()).toBe(1)
    const toggle = document.querySelector('.history-bulk-toggle input')
    toggle.checked = true
    toggle.dispatchEvent(new Event('change', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))
    expect(historyFetchCount()).toBe(1)

    document.querySelector('#history-list .history-entry')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    const selectAll = [...document.querySelectorAll('#history-bulk-toolbar button')]
      .find(btn => btn.textContent === 'Select all')
    expect(selectAll.getAttribute('aria-pressed')).toBe('mixed')

    const documentClick = vi.fn()
    document.addEventListener('click', documentClick)
    selectAll.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    document.removeEventListener('click', documentClick)
    await new Promise((resolve) => setImmediate(resolve))
    expect(documentClick).not.toHaveBeenCalled()
    expect(historyFetchCount()).toBe(1)
    expect(document.querySelector('.history-bulk-count').textContent).toBe('2 selected')
    expect([...document.querySelectorAll('[data-action="select-run"]')].map(input => input.checked))
      .toEqual([true, true, false])

    document.querySelector('#history-bulk-toolbar button')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))
    expect(document.querySelector('.history-bulk-count').textContent).toBe('0 selected')
    expect([...document.querySelectorAll('[data-action="select-run"]')].map(input => input.checked))
      .toEqual([false, false, false])

    document.querySelector('#history-bulk-toolbar button')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))
    expect(document.querySelector('.history-bulk-count').textContent).toBe('2 selected')
    expect(document.querySelector('#history-bulk-toolbar button').textContent).toBe('Deselect all')

    document.querySelector('#history-bulk-toolbar button:nth-of-type(2)')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))
    expect(document.querySelector('.history-bulk-count').textContent).toBe('0 selected')
    expect([...document.querySelectorAll('[data-action="select-run"]')].map(input => input.checked))
      .toEqual([false, false, false])
    expect(historyFetchCount()).toBe(1)
  })

  it('keeps export enabled for mixed selections while disabling project bulk actions', async () => {
    const exportBlob = new Blob(['{"kind":"summary","items":2}\n'], { type: 'application/x-ndjson' })
    const downloadBlobAsAttachment = vi.fn()
    const apiFetch = vi.fn((url) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            roots: ['dig'],
            items: [
              {
                id: 'run-1',
                type: 'run',
                command: 'dig darklab.sh A',
                started: '2026-01-01T00:00:00Z',
                exit_code: 0,
              },
              {
                id: 'snap-1',
                type: 'snapshot',
                label: 'saved output',
                created: '2026-01-01T00:00:01Z',
              },
            ],
            runs: [],
          }),
        })
      }
      if (url === '/history/bulk-export') {
        return Promise.resolve({
          ok: true,
          headers: { get: () => 'attachment; filename="darklab-history-test.jsonl"' },
          blob: () => Promise.resolve(exportBlob),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel } = loadHistoryPanel({
      apiFetchImpl: apiFetch,
      downloadBlobAsAttachmentImpl: downloadBlobAsAttachment,
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    const toggle = document.querySelector('.history-bulk-toggle input')
    toggle.checked = true
    toggle.dispatchEvent(new Event('change', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))
    document.querySelector('#history-list .history-entry')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))

    expect(document.querySelector('[data-action="bulk-add-active-project"]').disabled).toBe(true)
    expect(document.querySelector('[data-action="bulk-add-active-project"]').title)
      .toBe('Select an active project first.')

    document.querySelectorAll('#history-list .history-entry')[1]
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))

    expect(document.querySelector('[data-action="bulk-add-project"]').disabled).toBe(true)
    expect(document.querySelector('[data-action="bulk-remove-project"]').disabled).toBe(true)
    expect(document.querySelector('[data-action="bulk-export-txt"]').disabled).toBe(false)
    expect(document.querySelector('[data-action="bulk-export-jsonl"]').disabled).toBe(false)
    expect(document.querySelector('[data-action="bulk-delete"]').disabled).toBe(false)

    document.querySelector('[data-action="bulk-export-jsonl"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await vi.waitFor(() => expect(downloadBlobAsAttachment).toHaveBeenCalled())
    const exportCall = apiFetch.mock.calls.find(([url]) => url === '/history/bulk-export')
    expect(JSON.parse(exportCall[1].body)).toEqual({
      run_ids: ['run-1'],
      snapshot_ids: ['snap-1'],
      format: 'jsonl',
    })
    expect(downloadBlobAsAttachment).toHaveBeenCalledWith(
      exportBlob,
      'darklab-history-test.jsonl',
      expect.objectContaining({ container: document.getElementById('history-panel') }),
    )
    expect(document.querySelector('.history-bulk-count').textContent).toBe('2 selected')
  })

  it('resets select mode and selection before the next history drawer open', async () => {
    const { refreshHistoryPanel, _historyResetSelectionOnClose } = loadHistoryPanel()

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    const toggle = document.querySelector('.history-bulk-toggle input')
    toggle.checked = true
    toggle.dispatchEvent(new Event('change', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))

    document.querySelector('#history-list .history-entry')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(document.querySelector('.history-bulk-count').textContent).toBe('1 selected')

    _historyResetSelectionOnClose()
    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    expect(document.querySelector('.history-bulk-toggle input').checked).toBe(false)
    expect(document.querySelector('.history-bulk-count').textContent).toBe('0 selected')
    expect(document.querySelectorAll('[data-action="select-run"]')).toHaveLength(0)
  })

  it('keeps row actions from toggling selection while select mode is enabled', async () => {
    const clipboard = { writeText: vi.fn(() => Promise.resolve()) }
    const { refreshHistoryPanel } = loadHistoryPanel({ clipboardImpl: clipboard })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    const toggle = document.querySelector('.history-bulk-toggle input')
    toggle.checked = true
    toggle.dispatchEvent(new Event('change', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))

    document.querySelector('#history-list .history-entry [data-action="copy-command"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()

    expect(clipboard.writeText).toHaveBeenCalledWith('ping darklab.sh')
    expect(document.querySelector('.history-bulk-count').textContent).toBe('0 selected')
    expect(document.querySelector('[data-action="select-run"]').checked).toBe(false)
    expect(document.getElementById('history-run-overlay')).toBeNull()
  })

  it('locks the bulk toolbar and selected rows while a bulk action is in flight', async () => {
    let resolveBulk
    const bulkPromise = new Promise((resolve) => { resolveBulk = resolve })
    const showConfirm = vi.fn(() => Promise.resolve('add'))
    const apiFetch = vi.fn((url, options = {}) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            roots: ['ping'],
            items: [{
              id: 'run-1',
              type: 'run',
              command: 'ping darklab.sh',
              started: '2026-01-01T00:00:00Z',
              exit_code: 0,
            }],
            runs: [],
          }),
        })
      }
      if (url === '/projects/project-active/links' && options.method === 'POST') {
        return bulkPromise
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel } = loadHistoryPanel({
      apiFetchImpl: apiFetch,
      activeProject: { id: 'project-active', name: 'Active scope' },
      showConfirmImpl: showConfirm,
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    const toggle = document.querySelector('.history-bulk-toggle input')
    toggle.checked = true
    toggle.dispatchEvent(new Event('change', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))
    document.querySelector('#history-list .history-entry')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(document.querySelector('.history-bulk-count').textContent).toBe('1 selected')

    const bulkAddActiveDocumentClick = vi.fn()
    document.addEventListener('click', bulkAddActiveDocumentClick)
    try {
      document.querySelector('[data-action="bulk-add-active-project"]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    } finally {
      document.removeEventListener('click', bulkAddActiveDocumentClick)
    }
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))

    expect(bulkAddActiveDocumentClick).not.toHaveBeenCalled()
    expect(document.querySelector('.history-bulk-toggle input').disabled).toBe(true)
    expect(document.querySelector('[data-action="history-bulk-menu"]').disabled).toBe(true)
    expect(document.querySelector('[data-action="select-run"]').disabled).toBe(true)

    document.querySelector('#history-list .history-entry')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(document.querySelector('.history-bulk-count').textContent).toBe('1 selected')

    resolveBulk({
      ok: true,
      json: () => Promise.resolve({ ok: true, counts: { added: 1 }, results: [{ run_id: 'run-1', status: 'added' }] }),
    })
    await new Promise((resolve) => setImmediate(resolve))
    await new Promise((resolve) => setImmediate(resolve))

    expect(document.querySelector('.history-bulk-toggle input').disabled).toBe(false)
    expect(document.querySelector('.history-bulk-count').textContent).toBe('0 selected')
  })

  it('bulk add uses the project picker with the active project first', async () => {
    const showConfirm = vi.fn(() => Promise.resolve('add'))
    const apiFetch = vi.fn((url, options = {}) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            roots: ['ping'],
            items: [{
              id: 'run-1',
              type: 'run',
              command: 'ping darklab.sh',
              started: '2026-01-01T00:00:00Z',
              exit_code: 0,
            }],
            runs: [],
          }),
        })
      }
      if (url === '/projects') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            projects: [
              { id: 'project-z', name: 'Zulu', status: 'active' },
              { id: 'project-active', name: 'Active scope', status: 'active' },
              { id: 'project-a', name: 'Alpha', status: 'active' },
            ],
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true, counts: { added: 1 }, results: [] }) })
    })
    const { refreshHistoryPanel } = loadHistoryPanel({
      apiFetchImpl: apiFetch,
      activeProject: { id: 'project-active', name: 'Active scope' },
      showConfirmImpl: showConfirm,
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    const toggle = document.querySelector('.history-bulk-toggle input')
    toggle.checked = true
    toggle.dispatchEvent(new Event('change', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))
    document.querySelector('#history-list .history-entry')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    document.querySelector('[data-action="bulk-add-project"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))
    await new Promise((resolve) => setImmediate(resolve))

    const confirmOptions = showConfirm.mock.calls[0][0]
    const pickerOptions = [...confirmOptions.content.querySelectorAll('option')].map(option => option.textContent)
    expect(confirmOptions.body).toBe('Add 1 selected run to project')
    expect(confirmOptions.refocusOnResolve).toBe(false)
    expect(pickerOptions).toEqual(['Active scope', 'Alpha', 'Zulu'])
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-active/links', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ entity_type: 'run', entity_ids: ['run-1'], source: 'manual' }),
    }))
  })

  it('shows a fallback toast when history refresh fails after a successful bulk action', async () => {
    let historyFetches = 0
    const showConfirm = vi.fn(() => Promise.resolve('delete'))
    const apiFetch = vi.fn((url, options = {}) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        historyFetches += 1
        if (historyFetches > 1) return Promise.reject(new Error('refresh failed'))
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            roots: ['ping'],
            items: [{
              id: 'run-1',
              type: 'run',
              command: 'ping darklab.sh',
              started: '2026-01-01T00:00:00Z',
              exit_code: 0,
            }],
            runs: [],
          }),
        })
      }
      if (url === '/history/bulk-delete' && options.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            ok: true,
            counts: { deleted: 1, not_found: 0, rejected: 0 },
            results: [{ run_id: 'run-1', status: 'deleted' }],
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel } = loadHistoryPanel({
      apiFetchImpl: apiFetch,
      showConfirmImpl: showConfirm,
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    const toggle = document.querySelector('.history-bulk-toggle input')
    toggle.checked = true
    toggle.dispatchEvent(new Event('change', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))
    document.querySelector('#history-list .history-entry')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(document.querySelector('.history-bulk-count').textContent).toBe('1 selected')
    expect(document.querySelector('[data-action="bulk-delete"]').disabled).toBe(false)
    document.querySelector('[data-action="bulk-delete"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    for (let index = 0; index < 20; index += 1) {
      await new Promise((resolve) => setImmediate(resolve))
      if (document.getElementById('permalink-toast').textContent) break
    }

    expect(apiFetch).toHaveBeenCalledWith('/history/bulk-delete', expect.objectContaining({
      method: 'POST',
    }))
    expect(document.getElementById('permalink-toast').textContent)
      .toBe('Bulk action finished, but history could not refresh. Refresh to see the latest state.')
  })

  it('bulk remove unlinks selected runs from every linked project without a picker', async () => {
    const showConfirm = vi.fn(() => Promise.resolve('remove'))
    const apiFetch = vi.fn((url, options = {}) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            roots: ['nmap'],
            items: [
              {
                id: 'run-1',
                type: 'run',
                command: 'nmap one',
                started: '2026-01-01T00:00:00Z',
                exit_code: 0,
                project_links: [
                  {
                    project_id: 'project-z',
                    project: { id: 'project-z', name: 'Zulu', status: 'active' },
                  },
                  {
                    project_id: 'project-a',
                    project: { id: 'project-a', name: 'Alpha', status: 'active' },
                  },
                ],
              },
              {
                id: 'run-2',
                type: 'run',
                command: 'nmap two',
                started: '2026-01-01T00:00:01Z',
                exit_code: 0,
                project_links: [{
                  project_id: 'project-a',
                  project: { id: 'project-a', name: 'Alpha', status: 'active' },
                }],
              },
            ],
            runs: [],
          }),
        })
      }
      if (typeof url === 'string' && url.startsWith('/projects/')) {
        const body = JSON.parse(options.body)
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            ok: true,
            counts: { removed: body.entity_ids.length },
            results: body.entity_ids.map(runId => ({ run_id: runId, status: 'removed' })),
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) })
    })
    const { refreshHistoryPanel } = loadHistoryPanel({
      apiFetchImpl: apiFetch,
      showConfirmImpl: showConfirm,
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    const toggle = document.querySelector('.history-bulk-toggle input')
    toggle.checked = true
    toggle.dispatchEvent(new Event('change', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))
    document.querySelectorAll('#history-list .history-entry').forEach((row) => {
      row.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    const bulkRemoveDocumentClick = vi.fn()
    document.addEventListener('click', bulkRemoveDocumentClick)
    try {
      document.querySelector('[data-action="bulk-remove-project"]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    } finally {
      document.removeEventListener('click', bulkRemoveDocumentClick)
    }
    await new Promise((resolve) => setImmediate(resolve))
    await new Promise((resolve) => setImmediate(resolve))

    expect(bulkRemoveDocumentClick).not.toHaveBeenCalled()
    expect(showConfirm).toHaveBeenCalled()
    expect(showConfirm.mock.calls[0][0]).toEqual(expect.objectContaining({
      body: expect.objectContaining({
        text: 'Remove 2 selected runs from all linked projects?',
        note: 'This removes 3 project links and leaves the run history intact.',
      }),
      refocusOnResolve: false,
    }))
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-a/links', expect.objectContaining({
      method: 'DELETE',
      body: JSON.stringify({ entity_type: 'run', entity_ids: ['run-1', 'run-2'], source: 'manual' }),
    }))
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-z/links', expect.objectContaining({
      method: 'DELETE',
      body: JSON.stringify({ entity_type: 'run', entity_ids: ['run-1'], source: 'manual' }),
    }))
  })

  it('bulk delete result messages include known reasons and generic fallback for unknown rejected reasons', async () => {
    const showConfirm = vi.fn(() => Promise.resolve('delete'))
    const apiFetch = vi.fn((url, options = {}) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            roots: ['ping'],
            items: [
              {
                id: 'run-1',
                type: 'run',
                command: 'ping one',
                started: '2026-01-01T00:00:00Z',
                exit_code: 0,
              },
              {
                id: 'run-2',
                type: 'run',
                command: 'ping two',
                started: '2026-01-01T00:00:01Z',
                exit_code: 0,
              },
              {
                id: 'run-3',
                type: 'run',
                command: 'ping three',
                started: '2026-01-01T00:00:02Z',
                exit_code: 0,
              },
            ],
            runs: [],
          }),
        })
      }
      if (url === '/history/bulk-delete' && options.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            ok: true,
            counts: { deleted: 1, rejected: 2 },
            results: [
              { run_id: 'run-1', status: 'deleted' },
              { run_id: 'run-2', status: 'rejected', reason: 'running' },
              { run_id: 'run-3', status: 'rejected', reason: 'future_reason' },
            ],
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel } = loadHistoryPanel({
      apiFetchImpl: apiFetch,
      showConfirmImpl: showConfirm,
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    const toggle = document.querySelector('.history-bulk-toggle input')
    toggle.checked = true
    toggle.dispatchEvent(new Event('change', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))
    document.querySelectorAll('#history-list .history-entry').forEach((row) => {
      row.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    document.querySelector('[data-action="bulk-delete"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))
    await new Promise((resolve) => setImmediate(resolve))
    await Promise.resolve()

    expect(showConfirm).toHaveBeenCalled()
    expect(showConfirm.mock.calls[0][0].refocusOnResolve).toBe(false)
    expect(apiFetch).toHaveBeenCalledWith('/history/bulk-delete', expect.objectContaining({
      method: 'POST',
    }))
    const toast = document.getElementById('permalink-toast')
    expect(toast.childNodes[0].textContent)
      .toBe('Deleted 1 run - 2 skipped - 1 still running - 1 skipped')
    expect(toast.querySelector('.toast-action-btn')?.textContent).toBe('dismiss')
  })

  it('only offers Atlas cleanup on run delete when there are removable candidates', async () => {
    const showConfirm = vi.fn(() => Promise.resolve('cancel'))
    const previews = [
      { has_cleanup: false, entities: 0, findings: 0, curated_total: 0 },
      { has_cleanup: true, entities: 1, findings: 0, curated_total: 0 },
      {
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
            not_eligible: { entities: 1, findings: 1, total: 2 },
          },
          reasons: [
            {
              code: 'entity_has_kept_findings',
              bucket: 'not_eligible',
              label: 'has kept findings',
              entities: 1,
              findings: 0,
              total: 1,
            },
            {
              code: 'imported_finding',
              bucket: 'not_eligible',
              label: 'imported finding',
              entities: 0,
              findings: 1,
              total: 1,
            },
          ],
        },
      },
    ]
    const apiFetch = vi.fn((url) => {
      if (typeof url === 'string' && url === '/history/run-1/atlas-cleanup-preview') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ cleanup: previews.shift() }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const { confirmHistAction } = loadHistoryPanel({
      apiFetchImpl: apiFetch,
      showConfirmImpl: showConfirm,
    })

    confirmHistAction('delete', 'run-1', 'nmap darklab.sh')
    await new Promise((resolve) => setImmediate(resolve))
    expect(showConfirm.mock.calls[0][0].content).toBeNull()

    confirmHistAction('delete', 'run-1', 'nmap darklab.sh')
    await new Promise((resolve) => setImmediate(resolve))
    const noCuratedContent = showConfirm.mock.calls[1][0].content
    const noCuratedCleanup = noCuratedContent.querySelector('[data-history-atlas-cleanup]')
    expect(noCuratedCleanup).not.toBeNull()
    expect(noCuratedCleanup.checked).toBe(false)
    expect(noCuratedContent.textContent).toContain('Also remove 0 findings and 1 entity from Atlas')
    expect(noCuratedContent.textContent).not.toContain('curated')

    confirmHistAction('delete', 'run-1', 'nmap darklab.sh')
    await new Promise((resolve) => setImmediate(resolve))
    const curatedContent = showConfirm.mock.calls[2][0].content
    const curatedCleanup = curatedContent.querySelector('[data-history-atlas-cleanup]')
    const curatedDefaultCleanup = curatedContent.querySelector('[data-history-atlas-cleanup-curated]')
    expect(curatedCleanup).not.toBeNull()
    expect(curatedCleanup.checked).toBe(false)
    expect(curatedDefaultCleanup).not.toBeNull()
    expect(curatedDefaultCleanup.checked).toBe(false)
    expect(curatedContent.textContent).toContain('Also delete single-source Atlas items kept by default')
    expect(curatedContent.textContent).toContain('1 finding kept by default and 1 entity kept by default will be kept unless this is checked.')
    expect(curatedContent.textContent).toContain('1 finding and 1 entity not eligible for this cleanup.')
    expect(curatedContent.textContent).toContain('Reasons: has kept findings, imported finding.')
  })

  it('shows run cleanup reason notes without destructive options when only not eligible items exist', async () => {
    const showConfirm = vi.fn(() => Promise.resolve('cancel'))
    const apiFetch = vi.fn((url) => {
      if (typeof url === 'string' && url === '/history/run-1/atlas-cleanup-preview') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            cleanup: {
              has_cleanup: true,
              entities: 3,
              findings: 2,
              curated_entities: 1,
              curated_findings: 1,
              curated_total: 2,
              cleanup_reasons: {
                buckets: {
                  disposable: { entities: 0, findings: 0, total: 0 },
                  kept_by_default: { entities: 0, findings: 0, total: 0 },
                  not_eligible: { entities: 1, findings: 1, total: 2 },
                },
                reasons: [
                  {
                    code: 'seen_in_other_runs',
                    bucket: 'not_eligible',
                    label: 'seen elsewhere',
                    entities: 1,
                    findings: 0,
                    total: 1,
                  },
                  {
                    code: 'imported_finding',
                    bucket: 'not_eligible',
                    label: 'imported finding',
                    entities: 0,
                    findings: 1,
                    total: 1,
                  },
                ],
              },
            },
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const { confirmHistAction } = loadHistoryPanel({
      apiFetchImpl: apiFetch,
      showConfirmImpl: showConfirm,
    })

    confirmHistAction('delete', 'run-1', 'nmap darklab.sh')
    await new Promise((resolve) => setImmediate(resolve))

    const content = showConfirm.mock.calls[0][0].content
    expect(content).not.toBeNull()
    expect(content.querySelector('[data-history-atlas-cleanup]')).toBeNull()
    expect(content.querySelector('[data-history-atlas-cleanup-curated]')).toBeNull()
    expect(content.textContent).toContain('1 finding and 1 entity not eligible for this cleanup.')
    expect(content.textContent).toContain('Reasons: seen elsewhere, imported finding.')
  })

  it('copies the run id and links runs to active or selected projects from the history menu', async () => {
    const showConfirm = vi.fn(() => Promise.resolve('add'))
    let activeLinked = false
    const apiFetch = vi.fn((url, options = {}) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              roots: ['ping'],
              items: [{
                id: 'run-1',
                type: 'run',
                command: 'ping darklab.sh',
                label: 'ping darklab.sh',
                started: '2026-01-01T00:00:00Z',
                created: '2026-01-01T00:00:00Z',
                exit_code: 0,
                project_links: activeLinked ? [{
                  id: 'link-active',
                  project_id: 'project-active',
                  entity_type: 'run',
                  entity_id: 'run-1',
                  project: { id: 'project-active', name: 'Active scope', status: 'active' },
                }] : [],
              }],
              runs: [],
            }),
        })
      }
      if (url === '/projects') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            projects: [
              { id: 'project-2', name: 'zulu.test', status: 'active' },
              { id: 'project-1', name: 'alpha.test', status: 'active' },
              { id: 'project-active', name: 'zeta active', status: 'active' },
            ],
          }),
        })
      }
      if (url === '/projects/project-active/links' && options.method === 'POST') {
        activeLinked = true
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            ok: true,
            link: {
              id: 'link-active',
              project_id: 'project-active',
              entity_type: 'run',
              entity_id: 'run-1',
              source: 'manual',
              created: '2026-01-01T00:00:01Z',
            },
          }),
        })
      }
      if (url === '/projects/project-active/links' && options.method === 'DELETE') {
        activeLinked = false
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ ok: true }),
        })
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ ok: true }),
      })
    })
    const clipboard = { writeText: vi.fn(() => Promise.resolve()) }
    const { refreshHistoryPanel, openWatchersModal } = loadHistoryPanel({
      apiFetchImpl: apiFetch,
      clipboardImpl: clipboard,
      activeProject: { id: 'project-active', name: 'Active scope' },
      showConfirmImpl: showConfirm,
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    const entry = document.querySelector('#history-list .history-entry')

    entry.querySelector('[data-action="copy-command"]').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    expect(clipboard.writeText).toHaveBeenCalledWith('ping darklab.sh')

    entry.querySelector('[data-action="copy-run-id"]').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    expect(clipboard.writeText).toHaveBeenCalledWith('run-1')

    entry.querySelector('[data-action="watch-command"]').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(openWatchersModal).toHaveBeenCalledWith({
      baselineRun: expect.objectContaining({ id: 'run-1', command: 'ping darklab.sh' }),
    })

    const documentClick = vi.fn()
    document.addEventListener('click', documentClick)
    try {
      entry.querySelector('[data-action="add-active-project"]').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    } finally {
      document.removeEventListener('click', documentClick)
    }
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))
    expect(documentClick).not.toHaveBeenCalled()
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-active/links', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ entity_type: 'run', entity_id: 'run-1', source: 'manual' }),
    }))
    expect(document.querySelector('#history-list .history-entry [data-action="remove-project"]').textContent).toBe('remove from project')

    apiFetch.mockClear()
    showConfirm.mockImplementationOnce(() => Promise.resolve('remove'))
    const removeDocumentClick = vi.fn()
    document.addEventListener('click', removeDocumentClick)
    try {
      document.querySelector('#history-list .history-entry [data-action="remove-project"]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    } finally {
      document.removeEventListener('click', removeDocumentClick)
    }
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))
    expect(removeDocumentClick).not.toHaveBeenCalled()
    expect(showConfirm.mock.calls.at(-1)[0].refocusOnResolve).toBe(false)
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-active/links', expect.objectContaining({
      method: 'DELETE',
      body: JSON.stringify({ entity_type: 'run', entity_id: 'run-1' }),
    }))
    expect(document.querySelector('#history-list .history-entry [data-action="add-active-project"]').textContent)
      .toBe('add to active project')

    apiFetch.mockClear()
    const addProjectDocumentClick = vi.fn()
    document.addEventListener('click', addProjectDocumentClick)
    try {
      document.querySelector('#history-list .history-entry [data-action="add-project"]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    } finally {
      document.removeEventListener('click', addProjectDocumentClick)
    }
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))
    expect(addProjectDocumentClick).not.toHaveBeenCalled()
    expect(showConfirm).toHaveBeenCalled()
    expect(showConfirm.mock.calls.at(-1)[0].refocusOnResolve).toBe(false)
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-active/links', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ entity_type: 'run', entity_id: 'run-1', source: 'manual' }),
    }))

    let linked = true
    const linkedApiFetch = vi.fn((url) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              roots: ['ping'],
              items: [{
                id: 'run-1',
                type: 'run',
                command: 'ping darklab.sh',
                label: 'ping darklab.sh',
                started: '2026-01-01T00:00:00Z',
                created: '2026-01-01T00:00:00Z',
                exit_code: 0,
                project_links: linked ? [{
                  id: 'link-1',
                  project_id: 'project-1',
                  entity_type: 'run',
                  entity_id: 'run-1',
                  project: { id: 'project-1', name: 'Linked Project', status: 'active' },
                }] : [],
              }],
              runs: [],
            }),
        })
      }
      if (url === '/projects/project-1/links') {
        linked = false
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ ok: true }),
      })
    })
    const linkedRemoveConfirm = vi.fn(() => Promise.resolve('remove'))
    const { refreshHistoryPanel: refreshLinkedHistoryPanel } = loadHistoryPanel({
      apiFetchImpl: linkedApiFetch,
      showConfirmImpl: linkedRemoveConfirm,
    })

    refreshLinkedHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    const linkedEntry = document.querySelector('#history-list .history-entry')
    const menuActions = [...linkedEntry.querySelectorAll('.history-action-menu [data-action]')].map(el => el.dataset.action)
    expect(menuActions).toEqual([
      'edit-metadata',
      'open-atlas',
      'watch-command',
      'permalink',
      'compare',
      'remove-project',
      'copy-run-id',
    ])
    expect(linkedEntry.querySelector('[data-action="remove-project"]').textContent).toBe('remove from project')
    expect(linkedEntry.querySelector('[data-action="add-active-project"]')).toBeNull()
    expect(linkedEntry.querySelector('[data-action="add-project"]')).toBeNull()

    linkedApiFetch.mockClear()
    linkedEntry.querySelector('[data-action="remove-project"]').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))
    expect(linkedRemoveConfirm).toHaveBeenCalled()
    expect(linkedRemoveConfirm.mock.calls[0][0].refocusOnResolve).toBe(false)
    expect(linkedApiFetch).toHaveBeenCalledWith('/projects/project-1/links', expect.objectContaining({
      method: 'DELETE',
      body: JSON.stringify({ entity_type: 'run', entity_id: 'run-1' }),
    }))
    expect(document.querySelector('#history-list .history-entry [data-action="add-project"]').textContent)
      .toBe('add to project')

    let multiLinked = true
    const removeConfirm = vi.fn(() => Promise.resolve('remove'))
    const multiLinkedApiFetch = vi.fn((url) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              roots: ['ping'],
              items: [{
                id: 'run-1',
                type: 'run',
                command: 'ping darklab.sh',
                label: 'ping darklab.sh',
                started: '2026-01-01T00:00:00Z',
                created: '2026-01-01T00:00:00Z',
                exit_code: 0,
                project_links: multiLinked ? [
                  {
                    id: 'link-a',
                    project_id: 'project-a',
                    entity_type: 'run',
                    entity_id: 'run-1',
                    project: { id: 'project-a', name: 'Alpha Project', status: 'active' },
                  },
                  {
                    id: 'link-z',
                    project_id: 'project-z',
                    entity_type: 'run',
                    entity_id: 'run-1',
                    project: { id: 'project-z', name: 'Zulu Project', status: 'active' },
                  },
                ] : [],
              }],
              runs: [],
            }),
        })
      }
      if (url === '/projects/project-a/links') {
        multiLinked = false
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ ok: true }),
      })
    })
    const { refreshHistoryPanel: refreshMultiLinkedHistoryPanel } = loadHistoryPanel({
      apiFetchImpl: multiLinkedApiFetch,
      showConfirmImpl: removeConfirm,
    })

    refreshMultiLinkedHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    const multiLinkedEntry = document.querySelector('#history-list .history-entry')
    const removeConfirmDocumentClick = vi.fn()
    document.addEventListener('click', removeConfirmDocumentClick)
    try {
      multiLinkedEntry.querySelector('[data-action="remove-project"]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    } finally {
      document.removeEventListener('click', removeConfirmDocumentClick)
    }
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))
    expect(removeConfirmDocumentClick).not.toHaveBeenCalled()
    expect(removeConfirm).toHaveBeenCalled()
    expect(removeConfirm.mock.calls[0][0].refocusOnResolve).toBe(false)
    expect(multiLinkedApiFetch).toHaveBeenCalledWith('/projects/project-a/links', expect.objectContaining({
      method: 'DELETE',
      body: JSON.stringify({ entity_type: 'run', entity_id: 'run-1' }),
    }))
  })

  it('renders SIGTERM-terminated runs as neutral history rows instead of failures', async () => {
    const apiFetch = vi.fn((url) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          json: () => Promise.resolve({
            roots: ['ping'],
            items: [
              {
                id: 'run-killed',
                type: 'run',
                command: 'ping darklab.sh',
                started: '2026-01-01T00:00:00Z',
                exit_code: -15,
              },
            ],
            runs: [
              {
                id: 'run-killed',
                command: 'ping darklab.sh',
                started: '2026-01-01T00:00:00Z',
                exit_code: -15,
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

    const exitEl = document.querySelector('#history-list .history-entry .history-entry-meta span:last-child')
    expect(exitEl?.textContent).toBe('terminated')
    expect(exitEl?.classList.contains('exit-neutral')).toBe(true)
    expect(exitEl?.classList.contains('exit-fail')).toBe(false)
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

  it('keeps the history drawer open when compare launcher is unavailable', async () => {
    const apiFetch = vi.fn((url) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              roots: ['nmap'],
              items: [{
                id: 'run-new',
                type: 'run',
                command: 'nmap darklab.sh',
                started: '2026-01-01T00:00:04Z',
                exit_code: 0,
              }],
              runs: [],
            }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({ items: [], runs: [] }) })
    })
    const scriptPaths = HISTORY_WITH_UTILS_SCRIPT_PATHS
      .filter(path => path !== 'app/static/js/features/run-comparison/history_compare_launcher.js')
    const unavailableCompare = vi.fn()
    unavailableCompare.hasHandler = () => false
    const originalCompare = window.openHistoryCompareLauncher
    const originalGlobalCompare = globalThis.openHistoryCompareLauncher
    try {
      window.openHistoryCompareLauncher = unavailableCompare
      globalThis.openHistoryCompareLauncher = unavailableCompare
      const { refreshHistoryPanel } = loadHistoryPanel({ apiFetchImpl: apiFetch, scriptPaths })
      const historyPanel = document.getElementById('history-panel')
      historyPanel.classList.add('open')

      refreshHistoryPanel()
      await new Promise((resolve) => setImmediate(resolve))
      document
        .querySelector('#history-list .history-entry [data-action="compare"]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()

      expect(unavailableCompare).not.toHaveBeenCalled()
      expect(apiFetch).not.toHaveBeenCalledWith('/history/run-new/compare-candidates')
      expect(document.getElementById('history-compare-overlay')).toBeNull()
      expect(historyPanel.classList.contains('open')).toBe(true)
    } finally {
      if (originalCompare) window.openHistoryCompareLauncher = originalCompare
      else delete window.openHistoryCompareLauncher
      if (originalGlobalCompare) globalThis.openHistoryCompareLauncher = originalGlobalCompare
      else delete globalThis.openHistoryCompareLauncher
    }
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
          ok: true,
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
              totals: {
                left_total_lines: 2,
                right_total_lines: 2,
                equal_line_count: 0,
                changed_line_count: 1,
                added_line_count: 1,
                removed_line_count: 1,
              },
              limits: { line_display_truncate: 4000 },
              density_buckets: [
                { start: 0, end: 1, equal: 0, changed: 1, added: 0, removed: 0 },
                { start: 1, end: 2, equal: 0, changed: 0, added: 1, removed: 0 },
                { start: 2, end: 3, equal: 0, changed: 0, added: 0, removed: 1 },
                { start: 3, end: 10, equal: 7, changed: 0, added: 0, removed: 0 },
                { start: 10, end: 11, equal: 0, changed: 0, added: 1, removed: 0 },
              ],
              hunks: [
                {
                  op: 'replace',
                  left: {
                    start: 0,
                    end: 1,
                    lines: [{ text: 'Starting Nmap at 2026-04-30 23:22 UTC' }],
                  },
                  right: {
                    start: 0,
                    end: 1,
                    lines: [{ text: 'Starting Nmap at 2026-04-30 23:21 UTC' }],
                  },
                  changed_pairs: [{
                    left_index: 0,
                    right_index: 0,
                    segments: {
                      left: [
                        { text: 'Starting Nmap at 2026-04-30 23:' },
                        { text: '22', changed: true },
                        { text: ' UTC' },
                      ],
                      right: [
                        { text: 'Starting Nmap at 2026-04-30 23:' },
                        { text: '21', changed: true },
                        { text: ' UTC' },
                      ],
                    },
                  }],
                  left_unpaired: [],
                  right_unpaired: [],
                },
                {
                  op: 'insert',
                  left: { start: 1, end: 1 },
                  right: {
                    start: 1,
                    end: 2,
                    lines: [{ text: '443/tcp open https' }],
                  },
                },
                {
                  op: 'delete',
                  left: {
                    start: 1,
                    end: 2,
                    lines: [{ text: '8080/tcp open http-proxy' }],
                  },
                  right: { start: 2, end: 2 },
                },
                {
                  op: 'equal',
                  left: { start: 2, end: 9 },
                  right: { start: 2, end: 9 },
                  context: {
                    leading: {
                      left: [{ text: 'same leading' }],
                      right: [{ text: 'same leading' }],
                    },
                    trailing: {
                      left: [{ text: 'same trailing' }],
                      right: [{ text: 'same trailing' }],
                    },
                    omitted: 5,
                  },
                },
                {
                  op: 'insert',
                  left: { start: 9, end: 9 },
                  right: {
                    start: 9,
                    end: 10,
                    lines: [{ text: 'new service after equal block' }],
                  },
                },
              ],
              objects: {
                findings: {
                  added: [{
                    title: 'open port 443',
                    raw_line: '443/tcp open https',
                    severity: 'high',
                    compare_line_index: 1,
                  }],
                  removed: [{
                    title: 'open port 8080',
                    raw_line: '8080/tcp open http-proxy',
                    review_state: 'new',
                    compare_line_index: 1,
                  }],
                },
                artifacts: {
                  added: [{ workspace_path: 'reports/new.json', kind: 'output', byte_size: 12, compare_line_index: 1 }],
                  removed: [{ workspace_path: 'reports/old.json', kind: 'output', byte_size: 10 }],
                },
              },
              derived_changes: {
                group_count: 2,
                changed_count: 5,
                truncated: false,
                groups: [
                  {
                    id: 'nmap_ports',
                    kind: 'ports',
                    title: 'Open ports and services',
                    display_target: 'darklab.sh',
                    added_count: 1,
                    removed_count: 1,
                    changed_count: 1,
                    added: [{
                      key: '443/tcp',
                      port: '443',
                      proto: 'tcp',
                      state: 'open',
                      service: 'https',
                      line: '443/tcp open https',
                      compare_line_index: 1,
                      compare_side: 'right',
                    }],
                    removed: [{
                      key: '8080/tcp',
                      port: '8080',
                      proto: 'tcp',
                      state: 'open',
                      service: 'http-proxy',
                      line: '8080/tcp open http-proxy',
                      compare_line_index: 1,
                      compare_side: 'left',
                    }],
                    changed: [{
                      key: '80/tcp',
                      before: {
                        key: '80/tcp',
                        port: '80',
                        proto: 'tcp',
                        state: 'open',
                        service: 'http',
                        service_text: 'http Apache httpd',
                        compare_line_index: 0,
                        compare_side: 'left',
                      },
                      after: {
                        key: '80/tcp',
                        port: '80',
                        proto: 'tcp',
                        state: 'open',
                        service: 'http',
                        service_text: 'http nginx',
                        compare_line_index: 0,
                        compare_side: 'right',
                      },
                    }],
                  },
                  {
                    id: 'web_urls',
                    kind: 'urls',
                    title: 'URLs and HTTP status',
                    display_target: 'darklab.sh',
                    added_count: 1,
                    removed_count: 0,
                    changed_count: 1,
                    added: [{
                      canonical_url: 'https://darklab.sh/admin',
                      status_code: 200,
                      title: 'Admin',
                      compare_line_index: 1,
                      compare_side: 'right',
                    }],
                    removed: [],
                    changed: [{
                      key: 'https://darklab.sh',
                      before: {
                        canonical_url: 'https://darklab.sh',
                        status_code: 200,
                        title: 'Old title',
                        compare_line_index: 0,
                        compare_side: 'left',
                      },
                      after: {
                        canonical_url: 'https://darklab.sh',
                        status_code: 301,
                        title: 'New title',
                        compare_line_index: 0,
                        compare_side: 'right',
                      },
                    }],
                  },
                ],
              },
              truncated: {},
            }),
        })
      }
      if (url.startsWith('/history/compare/lines?')) {
        const parsed = new URL(url, 'http://localhost')
        const start = Number(parsed.searchParams.get('start') || 0)
        const end = Number(parsed.searchParams.get('end') || 0)
        return Promise.resolve({
          json: () => Promise.resolve({
            lines: Array.from({ length: Math.max(0, end - start) }, (_, index) => ({
              text: `same hidden ${start + index}`,
            })),
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
    const { refreshHistoryPanel, createTab, appendCommandEcho, appendLine, activateTab, emitUiEvent } =
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

    expect(document.querySelector('#history-compare-subtitle')?.textContent)
      .toBe('2 lines · 0 unchanged · 1 changed · 1 added · 1 removed')
    expect(document.querySelector('#history-compare-body')?.textContent).toContain('23:22 UTC')
    expect(document.querySelector('#history-compare-body')?.textContent).toContain('23:21 UTC')
    expect(document.querySelectorAll('.history-compare-line-delta')).toHaveLength(2)
    expect(document.querySelector('#history-compare-body')?.textContent).toContain('443/tcp open https')
    expect(document.querySelector('#history-compare-body')?.textContent).toContain('8080/tcp open http-proxy')
    expect(document.querySelector('#history-compare-body')?.textContent).toContain('Added findings (1)')
    expect(document.querySelector('#history-compare-body')?.textContent).toContain('Removed findings (1)')
    expect(document.querySelector('#history-compare-body')?.textContent).toContain('Removed artifacts (1)')
    expect(document.querySelector('#history-compare-body')?.textContent).toContain('reports/new.json')
    expect(document.querySelector('#history-compare-body')?.textContent).toContain('Detected changes (5)')
    expect(document.querySelector('#history-compare-body')?.textContent).toContain('Open ports and services')
    expect(document.querySelector('#history-compare-body')?.textContent).toContain('URLs and HTTP status')
    expect(document.querySelector('#history-compare-body')?.textContent).toContain('80/tcp')
    expect(document.querySelector('#history-compare-body')?.textContent).toContain('80/tcp open http Apache httpd -> 80/tcp open http nginx')
    expect(document.querySelector('#history-compare-body')?.textContent).toContain('https://darklab.sh/admin')
    expect(document.querySelector('#history-compare-body')?.textContent).toContain('https://darklab.sh · 200 · Old title -> https://darklab.sh · 301 · New title')
    let insertedOutputRow = document.querySelector('.history-compare-pane[data-side="b"] .history-compare-row.is-insert')
    let pairedSpacer = document.querySelector(
      `.history-compare-pane[data-side="a"] .history-compare-row[data-compare-pair="${insertedOutputRow.dataset.comparePair}"]`,
    )
    expect(pairedSpacer.classList.contains('history-compare-row-spacer')).toBe(true)
    expect(document.querySelectorAll('.history-compare-minimap-segment')).toHaveLength(5)
    expect(document.querySelectorAll('.history-compare-minimap-segment.is-changed')).toHaveLength(1)
    expect(document.querySelectorAll('.history-compare-minimap-segment.is-added')).toHaveLength(2)
    expect(document.querySelectorAll('.history-compare-minimap-segment.is-removed')).toHaveLength(1)
    expect(document.querySelectorAll('.history-compare-finding-marker.is-high')).toHaveLength(1)
    expect(document.querySelectorAll('.history-compare-finding-marker.is-info')).toHaveLength(1)
    const foldButtons = [...document.querySelectorAll('.history-compare-fold')]
      .filter(button => button.textContent.includes('Show 5 unchanged'))
    expect(foldButtons).toHaveLength(2)
    foldButtons[1].click()
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))
    expect([...document.querySelectorAll('.history-compare-fold')]
      .filter(button => button.textContent.includes('Hide unchanged'))).toHaveLength(2)
    insertedOutputRow = document.querySelector('.history-compare-pane[data-side="b"] .history-compare-row.is-insert')
    pairedSpacer = document.querySelector(
      `.history-compare-pane[data-side="a"] .history-compare-row[data-compare-pair="${insertedOutputRow.dataset.comparePair}"]`,
    )

    const compareBody = document.querySelector('#history-compare-body')
    compareBody.scrollTop = 123
    const panes = [...document.querySelectorAll('.history-compare-pane')]
    panes.forEach(pane => {
      Object.defineProperty(pane, 'clientHeight', { configurable: true, value: 100 })
      pane.scrollTop = 0
      pane.getBoundingClientRect = () => ({ top: 0, height: 100 })
    })
    const compareRows = [...document.querySelectorAll('.history-compare-row[data-compare-line-index]')]
    compareRows.forEach(row => {
      row.scrollIntoView = vi.fn()
      row.getBoundingClientRect = () => ({
        top: 160 + (Number(row.dataset.compareLineIndex || 0) * 30),
        height: 44,
      })
    })

    const allCompareRows = [...document.querySelectorAll('.history-compare-row')]
    const clearOutputPulses = () => allCompareRows.forEach(row => row.classList.remove('history-compare-line-pulse'))
    clearOutputPulses()
    document.querySelector('.history-compare-minimap-segment.is-added').click()
    expect(compareBody.scrollTop).toBe(123)
    expect(compareRows.every(row => !row.scrollIntoView.mock.calls.length)).toBe(true)
    expect(panes.some(pane => pane.scrollTop > 0)).toBe(true)
    expect(insertedOutputRow.classList.contains('history-compare-line-pulse')).toBe(true)
    expect(pairedSpacer.classList.contains('history-compare-line-pulse')).toBe(true)
    expect(document.querySelector('.history-compare-row.is-equal')?.classList.contains('history-compare-line-pulse')).toBe(false)
    clearOutputPulses()
    const finalAddedSegment = [...document.querySelectorAll('.history-compare-minimap-segment.is-added')].at(-1)
    finalAddedSegment.click()
    const finalAddedRow = [...document.querySelectorAll('.history-compare-pane[data-side="b"] .history-compare-row.is-insert')]
      .find(row => row.textContent.includes('new service after equal block'))
    expect(finalAddedRow.classList.contains('history-compare-line-pulse')).toBe(true)
    clearOutputPulses()
    document.querySelector('.history-compare-nav-btn:last-child').click()
    expect(compareBody.scrollTop).toBe(123)
    expect(compareRows.every(row => !row.scrollIntoView.mock.calls.length)).toBe(true)
    const changedRows = [...document.querySelectorAll('.history-compare-row[data-compare-unit-tone="changed"]')]
    expect(changedRows).toHaveLength(2)
    expect(changedRows.every(row => row.classList.contains('history-compare-line-pulse'))).toBe(true)
    const nextChange = document.querySelector('.history-compare-nav-btn:last-child')
    const pulsedPair = () => document.querySelector('.history-compare-row.history-compare-line-pulse')?.dataset.comparePair || ''
    const visitedPairs = []
    for (let index = 0; index < 4; index += 1) {
      clearOutputPulses()
      nextChange.click()
      visitedPairs.push(pulsedPair())
    }
    expect(new Set(visitedPairs).size).toBe(4)
    clearOutputPulses()
    nextChange.click()
    expect(pulsedPair()).toBe(visitedPairs[0])

    const addedDerivedPortRow = [...document.querySelectorAll(
      '.history-compare-derived-row[data-derived-kind="ports"][data-compare-side="b"]',
    )].find(row => row.textContent.includes('443/tcp open https'))
    expect(addedDerivedPortRow.tagName).toBe('BUTTON')
    emitUiEvent.mockClear()
    addedDerivedPortRow.click()
    expect(emitUiEvent).toHaveBeenCalledWith('app:compare-anchor-scroll', {
      side: 'b',
      compare_line_index: 1,
    })

    const addedFindingRow = document.querySelector(
      '.history-compare-object-row[data-object-kind="finding"][data-compare-side="b"]',
    )
    expect(addedFindingRow.tagName).toBe('BUTTON')
    addedFindingRow.click()
    expect(emitUiEvent).toHaveBeenCalledWith('app:compare-anchor-scroll', {
      side: 'b',
      compare_line_index: 1,
    })
    expect(document.querySelectorAll('.history-compare-row.history-compare-line-pulse').length).toBeGreaterThan(0)

    const addedArtifactRow = document.querySelector(
      '.history-compare-object-row[data-object-kind="artifact"][data-compare-side="b"]',
    )
    const removedArtifactRow = document.querySelector(
      '.history-compare-object-row[data-object-kind="artifact"][data-compare-side="a"]',
    )
    expect(addedArtifactRow.tagName).toBe('BUTTON')
    expect(removedArtifactRow.tagName).toBe('DIV')

    emitUiEvent.mockClear()
    document.querySelector('.history-compare-finding-marker.is-high').click()
    expect(emitUiEvent).not.toHaveBeenCalledWith('app:compare-anchor-scroll', expect.anything())

    document.querySelector('.history-compare-actions-trigger').click()
    const restoreBoth = [...document.querySelectorAll('.history-compare-actions-menu .dropdown-item')]
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
  }, 10_000)

  it('preflights Restore Both tab capacity before creating either tab', async () => {
    const { _restoreBothHistoryCompareRuns, createTab } = loadHistoryPanel({
      appConfig: { max_tabs: 2 },
    })

    await expect(_restoreBothHistoryCompareRuns(
      { id: 'run-a', command: 'nmap darklab.sh' },
      { id: 'run-b', command: 'nmap darklab.sh' },
    )).rejects.toThrow('not enough tab capacity')

    expect(createTab).not.toHaveBeenCalled()
    expect(document.getElementById('permalink-toast').textContent).toBe(
      'Not enough tab capacity to restore both runs',
    )
  })

  it('includes the history type filter in the request URL when snapshots are selected', () => {
    const { _setHistoryFilter, _buildHistoryRequestUrl } = loadHistoryPanel()

    _setHistoryFilter('type', 'snapshots')

    expect(_buildHistoryRequestUrl()).toContain('type=snapshots')
  })

  it('includes run subtype filters in the request URL', () => {
    const { _setHistoryFilter, _buildHistoryRequestUrl } = loadHistoryPanel()

    _setHistoryFilter('type', 'runs_builtin')
    expect(_buildHistoryRequestUrl()).toContain('type=runs_builtin')

    _setHistoryFilter('type', 'runs_external')
    expect(_buildHistoryRequestUrl()).toContain('type=runs_external')
  })

  it('renders run metadata badges and opens the metadata editor from the run menu', async () => {
    const openMetadataEditor = vi.fn()
    const { refreshHistoryPanel } = loadHistoryPanel({
      openMetadataEditorImpl: openMetadataEditor,
      apiFetchImpl: vi.fn(() =>
        Promise.resolve({
          json: () =>
            Promise.resolve({
              roots: ['nmap'],
              items: [
                {
                  id: 'run-1',
                  type: 'run',
                  command: 'nmap darklab.sh',
                  label: 'nmap darklab.sh',
                  started: '2026-01-01T00:00:00Z',
                  created: '2026-01-01T00:00:00Z',
                  exit_code: 0,
                  labels: [{ label: 'baseline' }],
                  note: { body: 'review owner' },
                },
              ],
              runs: [],
            }),
        }),
      ),
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    expect(document.querySelector('.history-entry-label-badge')?.textContent).toBe('baseline')
    expect(document.querySelector('.history-entry-note-badge')?.textContent).toBe('note')

    document
      .querySelector('#history-list .history-entry [data-action="edit-metadata"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))

    expect(openMetadataEditor).toHaveBeenCalledWith(
      'run',
      expect.objectContaining({ id: 'run-1', command: 'nmap darklab.sh' }),
      expect.objectContaining({ onSaved: expect.any(Function) }),
    )
  })

  it('hides history metadata edit and delete actions for view-only team members', async () => {
    const { refreshHistoryPanel } = loadHistoryPanel({
      activeTeamScopeCanImpl: capability => capability !== 'manage_history',
      apiFetchImpl: vi.fn((url) => {
        if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
          return Promise.resolve({
            json: () =>
              Promise.resolve({
                roots: [],
                items: [
                  {
                    id: 'run-external',
                    type: 'run',
                    run_kind: 'external',
                    command: 'nmap darklab.sh',
                    label: 'nmap darklab.sh',
                    started: '2026-01-01T00:00:00Z',
                    created: '2026-01-01T00:00:00Z',
                    exit_code: 0,
                  },
                  {
                    id: 'run-builtin',
                    type: 'run',
                    run_kind: 'builtin',
                    command: 'theme list',
                    label: 'theme list',
                    started: '2026-01-01T00:00:00Z',
                    created: '2026-01-01T00:00:00Z',
                    exit_code: 0,
                  },
                  {
                    id: 'snap-viewer',
                    type: 'snapshot',
                    label: 'viewer snapshot',
                    created: '2026-01-01T00:00:00Z',
                  },
                ],
                runs: [],
              }),
          })
        }
        if (url === '/history/run-builtin?json&preview=1') {
          return Promise.resolve({
            json: () =>
              Promise.resolve({
                id: 'run-builtin',
                run_kind: 'builtin',
                command: 'theme list',
                output_entries: [{ text: 'theme output', cls: '' }],
                exit_code: 0,
                started: '2026-01-01T00:00:00Z',
              }),
          })
        }
        if (url === '/projects?include_archived=1') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ projects: [] }) })
        }
        return Promise.resolve({ json: () => Promise.resolve({}) })
      }),
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    const entries = document.querySelectorAll('#history-list .history-entry')
    expect(entries[0].querySelector('[data-action="edit-metadata"]')).toBeNull()
    expect(entries[0].querySelector('[data-action="delete"]')).toBeNull()
    expect(entries[0].querySelector('.history-action-menu')?.textContent).not.toContain('edit')
    expect(entries[0].querySelector('.history-action-menu')?.textContent).not.toContain('delete')
    expect(entries[1].querySelector('[data-action="delete"]')).toBeNull()
    expect(entries[2].querySelector('[data-action="edit-metadata"]')).toBeNull()
    expect(entries[2].querySelector('[data-action="delete"]')).toBeNull()

    entries[1].dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))
    await Promise.resolve()

    expect(document.querySelector('[data-history-run-action="edit-metadata"]')).toBeNull()
    expect(document.querySelector('.history-run-section-header')?.textContent).toBe('Metadata')
  })

  it('renders snapshot rows with open and copy-link actions', async () => {
    const openMetadataEditor = vi.fn()
    const { refreshHistoryPanel } = loadHistoryPanel({
      openMetadataEditorImpl: openMetadataEditor,
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
                  labels: [{ label: 'handoff' }],
                  note: { body: 'send to client' },
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
    expect(entry.querySelector('.history-entry-label-badge')?.textContent).toBe('handoff')
    expect(entry.querySelector('.history-entry-note-badge')?.textContent).toBe('note')
    expect(entry.querySelector('[data-action="open"]')?.textContent).toBe('open')
    expect(entry.querySelector('[data-action="link"]')?.textContent).toBe('copy link')
    expect(entry.querySelector('[data-action="edit-metadata"]')?.textContent).toBe('edit')

    entry
      .querySelector('[data-action="edit-metadata"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(openMetadataEditor).toHaveBeenCalledWith(
      'snapshot',
      expect.objectContaining({ id: 'snap-1', label: 'nmap baseline snapshot' }),
      expect.objectContaining({ onSaved: expect.any(Function) }),
    )
  })

  it('selects snapshot rows and bulk deletes them through the snapshot endpoint', async () => {
    const showConfirm = vi.fn(() => Promise.resolve('delete'))
    const apiFetch = vi.fn((url, options = {}) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
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
        })
      }
      if (url === '/share/bulk-delete' && options.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            ok: true,
            counts: { deleted: 1, not_found: 0, rejected: 0 },
            results: [{ snapshot_id: 'snap-1', status: 'deleted' }],
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel } = loadHistoryPanel({
      apiFetchImpl: apiFetch,
      showConfirmImpl: showConfirm,
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    const toggle = document.querySelector('.history-bulk-toggle input')
    toggle.checked = true
    toggle.dispatchEvent(new Event('change', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))
    document.querySelector('#history-list .history-entry')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    document.querySelector('[data-action="bulk-delete"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))

    expect(showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      body: expect.objectContaining({
        text: 'Delete 1 selected snapshot?',
      }),
      refocusOnResolve: false,
    }))
    expect(apiFetch).toHaveBeenCalledWith('/share/bulk-delete', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ snapshot_ids: ['snap-1'] }),
    }))
    expect(document.getElementById('permalink-toast').textContent).toContain('Deleted 1 snapshot')
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
                  finished: '2026-04-20T09:01:05Z',
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
    const metaItems = [...document.querySelectorAll('.history-entry-meta > span')]
    const elapsedIndex = metaItems.findIndex(el => el.classList.contains('history-entry-elapsed'))
    const exitIndex = metaItems.findIndex(el => el.classList.contains('exit-ok'))
    expect(metaItems[elapsedIndex]?.textContent).toBe('1m 5s')
    expect(elapsedIndex).toBeGreaterThan(0)
    expect(exitIndex).toBeGreaterThan(elapsedIndex)
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

  it('sends structured output filters from the history drawer controls', async () => {
    const { apiFetch, _buildHistoryRequestUrl } = loadHistoryPanel()

    document.getElementById('history-signal-filter').value = 'findings'
    document
      .getElementById('history-signal-filter')
      .dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('history-kind-filter').value = 'error'
    document
      .getElementById('history-kind-filter')
      .dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('history-entity-input').value = 'tor-stats.darklab.sh'
    document
      .getElementById('history-entity-input')
      .dispatchEvent(new Event('input', { bubbles: true }))
    document.getElementById('history-entity-type-filter').value = 'domain'
    document
      .getElementById('history-entity-type-filter')
      .dispatchEvent(new Event('change', { bubbles: true }))
    await new Promise((resolve) => setTimeout(resolve, 140))

    expect(_buildHistoryRequestUrl()).toBe(
      '/history?page=1&page_size=8&include_total=1&type=runs&signal=findings&kind=error&entity=tor-stats.darklab.sh&entity_type=domain',
    )
    expect(apiFetch).toHaveBeenLastCalledWith(
      '/history?page=1&page_size=8&include_total=1&type=runs&signal=findings&kind=error&entity=tor-stats.darklab.sh&entity_type=domain',
    )
    expect(document.getElementById('history-active-filters').textContent).toContain('signal: findings')
    expect(document.getElementById('history-active-filters').textContent).toContain('kind: error')
    expect(document.getElementById('history-active-filters').textContent).toContain('entity: tor-stats.darklab.sh')
    expect(document.getElementById('history-active-filters').textContent).toContain('entity_type: domain')
  })

  it('includes the selected project in history requests and active filter chips', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/projects?include_archived=1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            projects: [{ id: 'project-1', name: 'darklab.sh', status: 'active' }],
          }),
        })
      }
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          json: () => Promise.resolve({ roots: [], items: [], runs: [], total_count: 0 }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel, _setHistoryFilter, _buildHistoryRequestUrl } = loadHistoryPanel({
      apiFetchImpl: apiFetch,
    })

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))
    await new Promise((resolve) => setImmediate(resolve))
    document.getElementById('history-project-filter').value = 'project-1'
    _setHistoryFilter('projectId', 'project-1')
    await new Promise((resolve) => setImmediate(resolve))

    expect(_buildHistoryRequestUrl()).toBe(
      '/history?page=1&page_size=8&include_total=1&project_id=project-1',
    )
    expect(document.getElementById('history-active-filters').textContent).toContain('project: darklab.sh')
    expect(apiFetch).toHaveBeenLastCalledWith(
      '/history?page=1&page_size=8&include_total=1&project_id=project-1',
    )
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
    let historyCall = 0
    const apiFetch = vi.fn((url) => {
      if (url === '/projects?include_archived=1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ projects: [] }),
        })
      }
      historyCall += 1
      return Promise.resolve({
        json: () =>
          Promise.resolve(historyCall === 1
            ? {
                roots: ['curl', 'dig', 'ping'],
                runs: [
                  {
                    id: 'run-1',
                    command: 'dig darklab.sh A',
                    started: '2026-01-01T00:00:00Z',
                    exit_code: 0,
                  },
                ],
              }
            : {
                roots: [],
                runs: [],
              }),
      })
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
    _setHistoryFilter('exitCode', '-15')
    _setHistoryFilter('dateRange', '7d')
    _setHistoryFilter('starredOnly', true)
    await new Promise((resolve) => setImmediate(resolve))

    const chips = [
      ...document.querySelectorAll('#history-active-filters .history-active-filter-chip'),
    ].map((el) => el.textContent)
    expect(chips).toEqual([
      expect.stringContaining('search: dig'),
      expect.stringContaining('command: nmap'),
      expect.stringContaining('exit: terminated'),
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

  it('toggles the mobile history tools section', () => {
    const { toggleHistoryMobileFilters } = loadHistoryPanel()
    const historyPanel = document.getElementById('history-panel')
    const toggleBtn = document.getElementById('history-mobile-filters-toggle')

    expect(historyPanel.classList.contains('mobile-history-tools-open')).toBe(false)
    expect(toggleBtn.getAttribute('aria-expanded')).toBe('false')

    toggleHistoryMobileFilters(true)
    expect(historyPanel.classList.contains('mobile-history-tools-open')).toBe(true)
    expect(toggleBtn.textContent).toBe('hide history tools')
    expect(toggleBtn.getAttribute('aria-expanded')).toBe('true')

    toggleHistoryMobileFilters(false)
    expect(historyPanel.classList.contains('mobile-history-tools-open')).toBe(false)
    expect(toggleBtn.textContent).toBe('history tools')
    expect(toggleBtn.getAttribute('aria-expanded')).toBe('false')
  })

  it('resetHistoryMobileFilters collapses the mobile history tools', () => {
    const { toggleHistoryMobileFilters, resetHistoryMobileFilters } = loadHistoryPanel()
    const historyPanel = document.getElementById('history-panel')

    toggleHistoryMobileFilters(true)
    expect(historyPanel.classList.contains('mobile-history-tools-open')).toBe(true)

    resetHistoryMobileFilters()
    expect(historyPanel.classList.contains('mobile-history-tools-open')).toBe(false)
    expect(document.getElementById('history-mobile-filters-toggle').textContent).toBe('history tools')
  })

  it('shows the active filter count in the mobile history tools button label', async () => {
    const { _setHistoryFilter } = loadHistoryPanel()
    const toggleBtn = document.getElementById('history-mobile-filters-toggle')

    _setHistoryFilter('q', 'dig')
    _setHistoryFilter('dateRange', '7d')
    _setHistoryFilter('starredOnly', true)
    await new Promise((resolve) => setImmediate(resolve))

    expect(toggleBtn.textContent).toBe('history tools (3 filters)')
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
    document.getElementById('history-signal-filter').value = 'findings'
    document
      .getElementById('history-signal-filter')
      .dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('history-kind-filter').value = 'warn'
    document
      .getElementById('history-kind-filter')
      .dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('history-entity-input').value = 'darklab.sh'
    document
      .getElementById('history-entity-input')
      .dispatchEvent(new Event('input', { bubbles: true }))
    document.getElementById('history-entity-type-filter').value = 'domain'
    document
      .getElementById('history-entity-type-filter')
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
    expect(document.getElementById('history-signal-filter').value).toBe('all')
    expect(document.getElementById('history-kind-filter').value).toBe('all')
    expect(document.getElementById('history-entity-input').value).toBe('')
    expect(document.getElementById('history-entity-type-filter').value).toBe('all')
    expect(document.getElementById('history-exit-filter').value).toBe('all')
    expect(document.getElementById('history-project-filter').value).toBe('all')
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

  it('shows a team-scope denial when history delete is rejected by the server', async () => {
    const showConfirm = vi.fn(() => Promise.resolve('one'))
    const apiFetch = vi.fn((url, options = {}) => {
      if (url === '/history/run-1/atlas-cleanup-preview') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ cleanup: {} }) })
      }
      if (url === '/history/run-1' && options.method === 'DELETE') {
        return Promise.resolve({
          ok: false,
          status: 403,
          json: () => Promise.resolve({ error: 'team_forbidden' }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ runs: [] }) })
    })
    const { confirmHistAction } = loadHistoryPanel({ apiFetchImpl: apiFetch, showConfirmImpl: showConfirm })

    confirmHistAction('delete', 'run-1', 'ping darklab.sh')
    await new Promise((resolve) => setImmediate(resolve))
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setImmediate(resolve))

    expect(document.getElementById('permalink-toast').textContent)
      .toBe("View-only team members can't delete team history. Switch to Personal or ask for operator access.")
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

  it('restores a same-command history run into a new tab when run ids differ', async () => {
    const apiFetch = vi.fn((url) => {
      if (typeof url === 'string' && (url === '/history' || url.startsWith('/history?'))) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              runs: [
                {
                  id: 'run-new',
                  command: 'ping darklab.sh',
                  started: '2026-01-01T00:00:00Z',
                  exit_code: 0,
                },
              ],
            }),
        })
      }
      if (url === '/history/run-new?json&preview=1') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              id: 'run-new',
              command: 'ping darklab.sh',
              output: ['new output'],
              exit_code: 0,
            }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel, tabs, createTab, activateTab, appendCommandEcho, appendLine } =
      loadHistoryPanel({ apiFetchImpl: apiFetch })
    tabs[0].command = 'ping darklab.sh'
    tabs[0].historyRunId = 'run-old'

    refreshHistoryPanel()
    await new Promise((resolve) => setImmediate(resolve))

    document
      .querySelector('.history-entry [data-action="restore"]')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await new Promise((resolve) => setImmediate(resolve))
    await new Promise((resolve) => setImmediate(resolve))

    expect(activateTab).not.toHaveBeenCalledWith('tab-1')
    expect(createTab).toHaveBeenCalledWith('ping darklab.sh')
    expect(tabs[1].historyRunId).toBe('run-new')
    expect(appendCommandEcho).toHaveBeenCalledWith('ping darklab.sh', 'tab-2')
    expect(appendLine).toHaveBeenCalledWith('new output', '', 'tab-2')
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
      HISTORY_SCRIPT_PATHS,
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
      `window.apiFetch = apiFetch;
       window.cmdInput = cmdInput;
       window.histSearchDropdown = histSearchDropdown;
       window.shellPromptWrap = shellPromptWrap;
       window.acHide = acHide;
       window.setComposerValue = setComposerValue;
       window.getComposerValue = getComposerValue;
       window.useMobileTerminalViewportMode = useMobileTerminalViewportMode;`,
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
    // The match is surfaced in the dropdown only; Enter accepts it.
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

  it('handleHistSearchKey Enter accepts the match into the prompt without running it', () => {
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
    expect(submitComposerCommand).not.toHaveBeenCalled()
  })

  it('handleHistSearchKey Enter with no matches keeps typed query without running it', () => {
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
    expect(submitComposerCommand).not.toHaveBeenCalled()
  })

  it('handleHistSearchKey Tab moves through matches without changing the input', () => {
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
    const dropdown = document.getElementById('hist-search-dropdown')

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
    expect(isHistSearchMode()).toBe(true)
    expect(cmdInput.value).toBe('dig')
    expect(dropdown.querySelector('.hist-search-item.active').textContent).toBe('dig darklab.sh MX')
    expect(submitComposerCommand).not.toHaveBeenCalled()
  })

  it('handleHistSearchKey ArrowDown navigates to the next match without changing the input', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, handleHistSearchKey } =
      loadHistSearch()
    hydrateCmdHistory([
      { command: 'dig darklab.sh A' },
      { command: 'dig darklab.sh MX' },
      { command: 'curl -I https://darklab.sh' },
    ])
    const cmdInput = document.getElementById('cmd')
    const dropdown = document.getElementById('hist-search-dropdown')

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
    expect(cmdInput.value).toBe('dig')
    expect(dropdown.querySelector('.hist-search-item.active').textContent).toBe('dig darklab.sh MX')
  })

  it('handleHistSearchKey ArrowUp navigates to the previous match', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, handleHistSearchKey } =
      loadHistSearch()
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }, { command: 'dig darklab.sh MX' }])
    const cmdInput = document.getElementById('cmd')
    const dropdown = document.getElementById('hist-search-dropdown')

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
    expect(cmdInput.value).toBe('dig')
    expect(dropdown.querySelector('.hist-search-item.active').textContent).toBe('dig darklab.sh MX')

    const up = Object.assign(new Event('keydown', { cancelable: true }), {
      key: 'ArrowUp',
      ctrlKey: false,
      metaKey: false,
      altKey: false,
    })
    const handled = handleHistSearchKey(up)

    expect(handled).toBe(true)
    expect(cmdInput.value).toBe('dig')
    expect(dropdown.querySelector('.hist-search-item.active').textContent).toBe('dig darklab.sh A')
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
    // Input stays as the typed query until Enter accepts a match.
    expect(cmdInput.value).toBe('dig')

    const e = Object.assign(new Event('keydown', { cancelable: true }), {
      key: 'r',
      ctrlKey: true,
      metaKey: false,
      altKey: false,
    })
    handleHistSearchKey(e)

    expect(cmdInput.value).toBe('dig')
    expect(document.querySelector('.hist-search-item.active').textContent).toBe('dig darklab.sh MX')
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
    expect(cmdInput.value).toBe('dig')
    expect(document.querySelector('.hist-search-item.active').textContent).toBe('dig darklab.sh MX')

    // ArrowDown at the last item wraps back to the first
    handleHistSearchKey(down)
    expect(cmdInput.value).toBe('dig')
    expect(document.querySelector('.hist-search-item.active').textContent).toBe('dig darklab.sh A')
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
    expect(cmdInput.value).toBe('dig')
    expect(document.querySelector('.hist-search-item.active').textContent).toBe('dig darklab.sh MX')
  })

  it('handleHistSearchKey Tab with no matches leaves search open and keeps the typed query', () => {
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
    expect(isHistSearchMode()).toBe(true)
    expect(cmdInput.value).toBe('xyz')
    expect(submitComposerCommand).not.toHaveBeenCalled()
  })

  it('handleHistSearchKey Enter after ArrowDown accepts the navigated-to match without running it', () => {
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
    expect(submitComposerCommand).not.toHaveBeenCalled()
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
      HISTORY_SCRIPT_PATHS,
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
      `window.apiFetch = apiFetch;
       window.cmdInput = cmdInput;
       window.histSearchDropdown = histSearchDropdown;
       window.shellPromptWrap = shellPromptWrap;
       window.acHide = acHide;
       window.setComposerValue = setComposerValue;
       window.getComposerValue = getComposerValue;
       window.useMobileTerminalViewportMode = useMobileTerminalViewportMode;`,
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
      HISTORY_SCRIPT_PATHS,
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
      `window.apiFetch = apiFetch;
       window.cmdInput = cmdInput;
       window.histSearchDropdown = histSearchDropdown;
       window.shellPromptWrap = shellPromptWrap;
       window.acHide = acHide;
       window.setComposerValue = setComposerValue;
       window.getComposerValue = getComposerValue;
       window.useMobileTerminalViewportMode = useMobileTerminalViewportMode;`,
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
