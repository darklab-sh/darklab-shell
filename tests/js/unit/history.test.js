import { vi } from 'vitest'
import { MemoryStorage, fromScript, fromDomScripts } from './helpers/extract.js'

// Re-extract before each test so each test gets a fresh MemoryStorage instance.
// Extraction is cheap (one file read + new Function call).
let _getStarred, _saveStarred, _toggleStar, store

beforeEach(() => {
  ;({ _getStarred, _saveStarred, _toggleStar, _storage: store } = fromScript(
    'app/static/js/history.js',
    '_getStarred',
    '_saveStarred',
    '_toggleStar',
  ))
})

// ── _getStarred ───────────────────────────────────────────────────────────────

describe('_getStarred', () => {
  it('returns an empty Set when no starred key exists', () => {
    expect(_getStarred()).toEqual(new Set())
  })

  it('returns a Set of the stored command strings', () => {
    store.setItem('starred', JSON.stringify(['foo', 'bar']))
    expect(_getStarred()).toEqual(new Set(['foo', 'bar']))
  })

  it('returns an empty Set when the stored value is invalid JSON', () => {
    store.setItem('starred', 'not-json{{{')
    expect(_getStarred()).toEqual(new Set())
  })

  it('returns an empty Set when the stored value is an empty array', () => {
    store.setItem('starred', '[]')
    expect(_getStarred()).toEqual(new Set())
  })

  it('returns an empty Set when the stored value is a non-array JSON value', () => {
    store.setItem('starred', JSON.stringify({ command: 'ls -la' }))
    expect(_getStarred()).toEqual(new Set())
  })
})

// ── _saveStarred ──────────────────────────────────────────────────────────────

describe('_saveStarred', () => {
  it('persists a Set to localStorage as a JSON array', () => {
    _saveStarred(new Set(['alpha', 'beta']))
    const stored = JSON.parse(store.getItem('starred'))
    expect(stored).toHaveLength(2)
    expect(stored).toEqual(expect.arrayContaining(['alpha', 'beta']))
  })

  it('persists an empty Set as an empty JSON array', () => {
    _saveStarred(new Set())
    expect(store.getItem('starred')).toBe('[]')
  })

  it('round-trips correctly through _getStarred', () => {
    _saveStarred(new Set(['cmd1', 'cmd2']))
    expect(_getStarred()).toEqual(new Set(['cmd1', 'cmd2']))
  })

  it('overwrites malformed stored data with a clean JSON array', () => {
    store.setItem('starred', 'not-json{{{')
    _saveStarred(new Set(['fixed']))
    expect(_getStarred()).toEqual(new Set(['fixed']))
  })
})

// ── _toggleStar ───────────────────────────────────────────────────────────────

describe('_toggleStar', () => {
  it('adds a command that is not yet starred', () => {
    _toggleStar('ls -la')
    expect(_getStarred().has('ls -la')).toBe(true)
  })

  it('removes a command that is already starred', () => {
    _saveStarred(new Set(['ls -la']))
    _toggleStar('ls -la')
    expect(_getStarred().has('ls -la')).toBe(false)
  })

  it('does not affect other starred commands when removing one', () => {
    _saveStarred(new Set(['cmd1', 'cmd2']))
    _toggleStar('cmd1')
    const s = _getStarred()
    expect(s.has('cmd1')).toBe(false)
    expect(s.has('cmd2')).toBe(true)
  })

  it('toggling the same command twice returns it to its original state', () => {
    _saveStarred(new Set(['cmd1']))
    _toggleStar('cmd1')
    _toggleStar('cmd1')
    expect(_getStarred().has('cmd1')).toBe(true)
  })

  it('ignores duplicate command strings in the stored set representation', () => {
    _saveStarred(new Set(['cmd1', 'cmd1']))
    expect(_getStarred()).toEqual(new Set(['cmd1']))
  })
})

describe('command history hydration', () => {
  function loadHistoryHelpers() {
    document.body.innerHTML = `
      <div id="history-row"><span class="history-label">Recent:</span></div>
      <input id="cmd" />
      <div id="history-panel"></div>
    `

    const histRow = document.getElementById('history-row')
    const cmdInput = document.getElementById('cmd')
    const historyPanel = document.getElementById('history-panel')

    return fromDomScripts([
      'app/static/js/history.js',
    ], {
      document,
      localStorage: new MemoryStorage(),
      APP_CONFIG: { recent_commands_limit: 3 },
      histRow,
      cmdInput,
      historyPanel,
      refreshHistoryPanel: vi.fn(),
      useMobileTerminalViewportMode: () => false,
    }, `{
      hydrateCmdHistory,
      navigateCmdHistory,
      resetCmdHistoryNav,
      renderHistory,
      getCmdHistory: () => cmdHistory.slice(),
    }`)
  }

  it('hydrates unique recent commands from server history and enables navigation', () => {
    const { hydrateCmdHistory, navigateCmdHistory, getCmdHistory } = loadHistoryHelpers()
    const cmdInput = document.getElementById('cmd')

    hydrateCmdHistory([
      { command: 'dig darklab.sh A' },
      { command: 'curl -I https://darklab.sh' },
      { command: 'dig darklab.sh A' },
      { command: 'ping -c 4 darklab.sh' },
    ])

    expect(getCmdHistory()).toEqual([
      'dig darklab.sh A',
      'curl -I https://darklab.sh',
      'ping -c 4 darklab.sh',
    ])

    expect(navigateCmdHistory(1)).toBe(true)
    expect(cmdInput.value).toBe('dig darklab.sh A')
    expect(navigateCmdHistory(-1)).toBe(true)
    expect(cmdInput.value).toBe('')
  })

  it('restores the typed draft after navigating through hydrated history', () => {
    const { hydrateCmdHistory, navigateCmdHistory } = loadHistoryHelpers()
    const cmdInput = document.getElementById('cmd')

    hydrateCmdHistory([
      { command: 'dig darklab.sh A' },
      { command: 'curl -I https://darklab.sh' },
    ])

    cmdInput.value = 'pin'
    expect(navigateCmdHistory(1)).toBe(true)
    expect(cmdInput.value).toBe('dig darklab.sh A')
    expect(navigateCmdHistory(1)).toBe(true)
    expect(cmdInput.value).toBe('curl -I https://darklab.sh')
    expect(navigateCmdHistory(-1)).toBe(true)
    expect(cmdInput.value).toBe('dig darklab.sh A')
    expect(navigateCmdHistory(-1)).toBe(true)
    expect(cmdInput.value).toBe('pin')
  })

  it('resetCmdHistoryNav clears navigation state after the user types', () => {
    const { hydrateCmdHistory, navigateCmdHistory, resetCmdHistoryNav } = loadHistoryHelpers()
    const cmdInput = document.getElementById('cmd')

    hydrateCmdHistory([
      { command: 'dig darklab.sh A' },
      { command: 'curl -I https://darklab.sh' },
    ])

    expect(navigateCmdHistory(1)).toBe(true)
    expect(cmdInput.value).toBe('dig darklab.sh A')

    cmdInput.value = 'typed now'
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

    const helpers = fromDomScripts([
      'app/static/js/history.js',
    ], {
      document,
      localStorage: new MemoryStorage(),
      APP_CONFIG: { recent_commands_limit: 8 },
      histRow: document.getElementById('history-row'),
      cmdInput: document.getElementById('cmd'),
      historyPanel: document.getElementById('history-panel'),
      refreshHistoryPanel: vi.fn(),
      useMobileTerminalViewportMode: () => true,
    }, `({
      hydrateCmdHistory,
    })`)

    helpers.hydrateCmdHistory([
      { command: 'one' },
      { command: 'two' },
      { command: 'three' },
      { command: 'four' },
    ])

    const chips = [...document.querySelectorAll('.hist-chip')]
    expect(chips).toHaveLength(4)
    expect(chips[0].querySelector('.chip-star')?.textContent).toBe('☆')
    expect(chips[0].querySelector('span:last-child')?.textContent).toBe('one')
    expect(chips[1].querySelector('span:last-child')?.textContent).toBe('two')
    expect(chips[2].querySelector('span:last-child')?.textContent).toBe('three')
    expect(chips[3].textContent).toBe('+1 more')
  })
})

describe('history panel actions', () => {
  function loadHistoryPanel({ clipboardImpl, apiFetchImpl } = {}) {
    document.body.innerHTML = `
      <div id="history-panel"></div>
      <div id="history-list"></div>
      <div id="history-load-overlay"></div>
      <div id="hist-del-overlay"></div>
      <div id="hist-del-msg"></div>
      <button id="hist-del-nonfav"></button>
      <button id="hist-del-confirm"></button>
      <div id="permalink-toast"></div>
      <div id="tabs-bar"></div>
      <div id="tab-panels"></div>
      <input id="cmd" />
    `

    const apiFetch = apiFetchImpl || vi.fn((url) => {
      if (url === '/history') {
        return Promise.resolve({
          json: () => Promise.resolve({
            runs: [
              { id: 'run-1', command: 'ping darklab.sh', started: '2026-01-01T00:00:00Z', exit_code: 0 },
            ],
          }),
        })
      }
      if (url === '/history/run-1?json&preview=1') {
        return Promise.resolve({
          json: () => Promise.resolve({
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
    const createTab = vi.fn(() => 'tab-2')
    const activateTab = vi.fn()
    const appendLine = vi.fn()
    const tabs = [{ id: 'tab-1', command: '', rawLines: [], st: 'idle' }]
    const historyPanel = document.getElementById('history-panel')
    const historyList = document.getElementById('history-list')
    const historyLoadOverlay = document.getElementById('history-load-overlay')
    const histDelOverlay = document.getElementById('hist-del-overlay')
    const histDelMsg = document.getElementById('hist-del-msg')
    const histDelConfirmBtn = document.getElementById('hist-del-confirm')
    const cmdInput = document.getElementById('cmd')
    const location = { origin: 'https://example.test' }
    const windowOpen = vi.fn()

    return {
      ...fromDomScripts([
        'app/static/js/utils.js',
        'app/static/js/history.js',
      ], {
        document,
        apiFetch,
        navigator: { clipboard },
        location,
        historyPanel,
        historyList,
        historyLoadOverlay,
        histRow: document.createElement('div'),
        histDelOverlay,
        histDelMsg,
        histDelConfirmBtn,
        cmdInput,
        tabs,
        activateTab,
        createTab,
        appendLine,
        showToast,
        window: { open: windowOpen },
        _getStarred,
        _saveStarred,
        refreshHistoryPanel: () => {},
        renderHistory: () => {},
        confirmHistAction: () => {},
        executeHistAction: () => {},
      }, `{
        refreshHistoryPanel,
        executeHistAction,
        confirmHistAction,
      }`),
      apiFetch,
      clipboard,
      windowOpen,
      appendLine,
      showToast,
    }
  }

  it('refreshHistoryPanel copy actions fall back to execCommand when clipboard writes reject', async () => {
    const clipboard = {
      writeText: vi.fn(() => Promise.reject(new Error('clipboard denied'))),
    }
    const originalExecCommand = document.execCommand
    document.execCommand = vi.fn(() => true)
    const { refreshHistoryPanel } = loadHistoryPanel({ clipboardImpl: clipboard })

    refreshHistoryPanel()
    await new Promise(resolve => setImmediate(resolve))
    const entry = document.querySelector('#history-list .history-entry')
    entry.querySelector('[data-action="copy"]').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(clipboard.writeText).toHaveBeenCalledTimes(1)
    await Promise.resolve()
    await Promise.resolve()
    await new Promise(resolve => setImmediate(resolve))

    expect(document.execCommand).toHaveBeenCalledWith('copy')
    expect(document.getElementById('permalink-toast').textContent).toBe('Command copied to clipboard')

    entry.querySelector('[data-action="permalink"]').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(clipboard.writeText).toHaveBeenCalledTimes(2)
    await Promise.resolve()
    await Promise.resolve()
    await new Promise(resolve => setImmediate(resolve))

    expect(document.execCommand).toHaveBeenCalledTimes(2)
    expect(document.getElementById('permalink-toast').textContent).toBe('Link copied to clipboard')
    document.execCommand = originalExecCommand
  })

  it('executeHistAction shows a failure toast when deleting a run fails', async () => {
    const apiFetch = vi.fn((url, options = {}) => {
      if (url === '/history') {
        return Promise.resolve({
          json: () => Promise.resolve({
            runs: [
              { id: 'run-1', command: 'ping darklab.sh', started: '2026-01-01T00:00:00Z', exit_code: 0 },
            ],
          }),
        })
      }
      if (url === '/history/run-1' && options.method === 'DELETE') {
        return Promise.reject(new Error('delete failed'))
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel, executeHistAction, confirmHistAction } = loadHistoryPanel({ apiFetchImpl: apiFetch })

    refreshHistoryPanel()
    await new Promise(resolve => setImmediate(resolve))

    confirmHistAction('delete', 'run-1', 'ping darklab.sh')
    executeHistAction('delete')
    await Promise.resolve()
    await Promise.resolve()
    await new Promise(resolve => setImmediate(resolve))

    expect(document.getElementById('permalink-toast').textContent).toBe('Failed to delete run')
    expect(document.querySelectorAll('#history-list .history-entry')).toHaveLength(1)
  })

  it('executeHistAction shows a failure toast when clearing non-favorite history fails', async () => {
    const apiFetch = vi.fn((url, options = {}) => {
      if (url === '/history' && (!options.method || options.method === 'GET')) {
        return Promise.resolve({
          json: () => Promise.resolve({
            runs: [
              { id: 'run-1', command: 'ping darklab.sh', started: '2026-01-01T00:00:00Z', exit_code: 0 },
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
    await new Promise(resolve => setImmediate(resolve))

    executeHistAction('clear-nonfav')
    await Promise.resolve()
    await Promise.resolve()
    await new Promise(resolve => setImmediate(resolve))

    expect(document.getElementById('permalink-toast').textContent).toBe('Failed to clear history')
    expect(document.querySelectorAll('#history-list .history-entry')).toHaveLength(1)
  })

  it('shows and clears the history loading overlay while a run is being restored', async () => {
    let resolveRun
    const apiFetch = vi.fn((url) => {
      if (url === '/history') {
        return Promise.resolve({
          json: () => Promise.resolve({
            runs: [
              { id: 'run-1', command: 'ping darklab.sh', started: '2026-01-01T00:00:00Z', exit_code: 0 },
            ],
          }),
        })
      }
      if (url === '/history/run-1?json&preview=1') {
        return new Promise((resolve) => {
          resolveRun = () => resolve({
            json: () => Promise.resolve({
              command: 'ping darklab.sh',
              output: ['ok'],
              exit_code: 0,
            }),
          })
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel, appendLine } = loadHistoryPanel({ apiFetchImpl: apiFetch })

    refreshHistoryPanel()
    await new Promise(resolve => setImmediate(resolve))

    document.querySelector('.history-entry').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(document.getElementById('history-load-overlay').classList.contains('open')).toBe(true)

    resolveRun()
    await new Promise(resolve => setImmediate(resolve))
    await new Promise(resolve => setImmediate(resolve))

    expect(document.getElementById('history-load-overlay').classList.contains('open')).toBe(false)
  })

  it('restores the full history payload when full output is available', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/history') {
        return Promise.resolve({
          json: () => Promise.resolve({
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
          json: () => Promise.resolve({
            command: 'ping darklab.sh',
            output: ['ok line 1', 'ok line 2'],
            exit_code: 0,
            full_output_available: true,
          }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })
    const { refreshHistoryPanel, appendLine } = loadHistoryPanel({ apiFetchImpl: apiFetch })

    refreshHistoryPanel()
    await new Promise(resolve => setImmediate(resolve))

    document.querySelector('.history-entry').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await new Promise(resolve => setImmediate(resolve))
    await new Promise(resolve => setImmediate(resolve))

    expect(apiFetch).toHaveBeenCalledWith('/history/run-1?json')
    expect(document.getElementById('history-load-overlay').classList.contains('open')).toBe(false)
    expect(appendLine).toHaveBeenCalledWith('$ ping darklab.sh', '', 'tab-2')
    expect(appendLine).toHaveBeenCalledWith('ok line 1', '', 'tab-2')
    expect(appendLine).not.toHaveBeenCalledWith(expect.stringContaining('preview truncated'), 'notice', 'tab-2')
  })

  it('clears the history loading overlay and shows a failure toast when a restore fetch fails', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/history') {
        return Promise.resolve({
          json: () => Promise.resolve({
            runs: [
              { id: 'run-1', command: 'ping darklab.sh', started: '2026-01-01T00:00:00Z', exit_code: 0 },
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
    await new Promise(resolve => setImmediate(resolve))

    document.querySelector('.history-entry').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
    await Promise.resolve()
    await new Promise(resolve => setImmediate(resolve))

    expect(document.getElementById('history-load-overlay').classList.contains('open')).toBe(false)
    expect(document.getElementById('permalink-toast').textContent).toBe('Failed to load run')
  })

})
