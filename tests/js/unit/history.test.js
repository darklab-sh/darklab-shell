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
      setComposerState: (next) => {
        if (Object.prototype.hasOwnProperty.call(next, 'value')) cmdInput.value = String(next.value ?? '');
        if (Object.prototype.hasOwnProperty.call(next, 'selectionStart') || Object.prototype.hasOwnProperty.call(next, 'selectionEnd')) {
          const start = typeof next.selectionStart === 'number' ? next.selectionStart : cmdInput.value.length;
          const end = typeof next.selectionEnd === 'number' ? next.selectionEnd : start;
          cmdInput.setSelectionRange(start, end);
        }
      },
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
    setComposerState({ value: 'typed now', selectionStart: 9, selectionEnd: 9, activeInput: 'desktop' })
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
      useMobileTerminalViewportMode: () => false,
    }, `({
      hydrateCmdHistory,
    })`)

    const originalRect = window.HTMLElement.prototype.getBoundingClientRect
    window.HTMLElement.prototype.getBoundingClientRect = function getBoundingClientRect() {
      if (!this.classList?.contains('hist-chip')) return { top: 0 }
      const regularChipCount = document.querySelectorAll('.hist-chip:not(.hist-chip-overflow)').length
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
      expect(visibleChips.map(chip => chip.textContent)).toEqual(['☆one', '☆two', '+ more'])
    } finally {
      window.HTMLElement.prototype.getBoundingClientRect = originalRect
    }
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
        localStorage: new MemoryStorage(),
        APP_CONFIG: { recent_commands_limit: 8 },
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
        hideHistoryPanel: vi.fn(() => {
          historyPanel.classList.remove('open')
          if (typeof cmdInput.focus === 'function') cmdInput.focus()
        }),
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
    const cmdInput = document.getElementById('cmd')
    cmdInput.focus = vi.fn()

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
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(cmdInput.focus).toHaveBeenCalled()

    entry.querySelector('[data-action="permalink"]').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(clipboard.writeText).toHaveBeenCalledTimes(2)
    await Promise.resolve()
    await Promise.resolve()
    await new Promise(resolve => setImmediate(resolve))

    expect(document.execCommand).toHaveBeenCalledTimes(2)
    expect(document.getElementById('permalink-toast').textContent).toBe('Link copied to clipboard')
    document.execCommand = originalExecCommand
  })

  it('closes the history panel when a history action button is clicked', async () => {
    const { refreshHistoryPanel } = loadHistoryPanel()
    const historyPanel = document.getElementById('history-panel')
    historyPanel.classList.add('open')

    refreshHistoryPanel()
    await new Promise(resolve => setImmediate(resolve))

    const entry = document.querySelector('#history-list .history-entry')
    entry.querySelector('[data-action="star"]').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(historyPanel.classList.contains('open')).toBe(false)

    historyPanel.classList.add('open')
    entry.querySelector('[data-action="copy"]').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(historyPanel.classList.contains('open')).toBe(false)

    historyPanel.classList.add('open')
    entry.querySelector('[data-action="permalink"]').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(historyPanel.classList.contains('open')).toBe(false)

    historyPanel.classList.add('open')
    entry.querySelector('[data-action="delete"]').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(historyPanel.classList.contains('open')).toBe(false)
  })

  it('refreshHistoryPanel labels the history permalink action as permalink', async () => {
    const { refreshHistoryPanel } = loadHistoryPanel()

    refreshHistoryPanel()
    await new Promise(resolve => setImmediate(resolve))

    const btn = document.querySelector('#history-list .history-entry [data-action="permalink"]')
    expect(btn.textContent).toBe('permalink')
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

    return fromDomScripts([
      'app/static/js/history.js',
    ], {
      document,
      localStorage: new MemoryStorage(),
      APP_CONFIG: { recent_commands_limit: 20 },
      histRow,
      cmdInput,
      historyPanel,
      histSearchDropdown,
      shellPromptWrap: document.createElement('div'),
      acHide: vi.fn(),
      refreshHistoryPanel: vi.fn(),
      useMobileTerminalViewportMode: () => false,
      setComposerValue: (val, start = null, end = null, opts = {}) => {
        cmdInput.value = String(val ?? '')
        if (opts.dispatch !== false) cmdInput.dispatchEvent(new Event('input'))
      },
      getComposerValue: () => cmdInput.value,
      submitComposerCommand,
    }, `{
      hydrateCmdHistory,
      enterHistSearch,
      exitHistSearch,
      handleHistSearchInput,
      handleHistSearchKey,
      isHistSearchMode,
      resetCmdHistoryNav,
      _submitComposerCommand: submitComposerCommand,
    }`)
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
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, exitHistSearch, isHistSearchMode } = loadHistSearch()
    hydrateCmdHistory([
      { command: 'dig darklab.sh A' },
      { command: 'nmap -sV darklab.sh' },
    ])
    const cmdInput = document.getElementById('cmd')

    enterHistSearch()
    handleHistSearchInput('nmap')
    exitHistSearch(true)

    expect(isHistSearchMode()).toBe(false)
    expect(cmdInput.value).toBe('nmap -sV darklab.sh')
    expect(document.getElementById('hist-search-dropdown').classList.contains('u-hidden')).toBe(true)
  })

  it('exitHistSearch(false) cancels and restores the pre-draft', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, exitHistSearch } = loadHistSearch()
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])
    const cmdInput = document.getElementById('cmd')
    cmdInput.value = 'my draft'

    enterHistSearch()
    handleHistSearchInput('dig')
    exitHistSearch(false)

    expect(cmdInput.value).toBe('my draft')
  })

  it('handleHistSearchKey Escape cancels search and returns true', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchKey, isHistSearchMode } = loadHistSearch()
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])
    const cmdInput = document.getElementById('cmd')
    cmdInput.value = 'pre'

    enterHistSearch()
    const e = Object.assign(new Event('keydown', { cancelable: true }), { key: 'Escape', ctrlKey: false, metaKey: false, altKey: false })
    const handled = handleHistSearchKey(e)

    expect(handled).toBe(true)
    expect(isHistSearchMode()).toBe(false)
    expect(cmdInput.value).toBe('pre')
  })

  it('handleHistSearchKey Enter accepts the match, exits search, and runs the command', () => {
    const submitComposerCommand = vi.fn()
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, handleHistSearchKey, isHistSearchMode } = loadHistSearch({ submitComposerCommand })
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])
    const cmdInput = document.getElementById('cmd')

    enterHistSearch()
    cmdInput.value = 'dig'
    handleHistSearchInput('dig')
    const e = Object.assign(new Event('keydown', { cancelable: true }), { key: 'Enter', ctrlKey: false, metaKey: false, altKey: false })
    const handled = handleHistSearchKey(e)

    expect(handled).toBe(true)
    expect(isHistSearchMode()).toBe(false)
    expect(cmdInput.value).toBe('dig darklab.sh A')
    expect(submitComposerCommand).toHaveBeenCalledWith('dig darklab.sh A', { dismissKeyboard: true })
  })

  it('handleHistSearchKey Enter with no matches keeps typed query and runs it', () => {
    const submitComposerCommand = vi.fn()
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, handleHistSearchKey, isHistSearchMode } = loadHistSearch({ submitComposerCommand })
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])
    const cmdInput = document.getElementById('cmd')

    enterHistSearch()
    cmdInput.value = 'xyz'
    handleHistSearchInput('xyz')
    const e = Object.assign(new Event('keydown', { cancelable: true }), { key: 'Enter', ctrlKey: false, metaKey: false, altKey: false })
    handleHistSearchKey(e)

    expect(isHistSearchMode()).toBe(false)
    expect(cmdInput.value).toBe('xyz')
    expect(submitComposerCommand).toHaveBeenCalledWith('xyz', { dismissKeyboard: true })
  })

  it('handleHistSearchKey Tab accepts the match without running the command', () => {
    const submitComposerCommand = vi.fn()
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, handleHistSearchKey, isHistSearchMode } = loadHistSearch({ submitComposerCommand })
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])
    const cmdInput = document.getElementById('cmd')

    enterHistSearch()
    cmdInput.value = 'dig'
    handleHistSearchInput('dig')
    const e = Object.assign(new Event('keydown', { cancelable: true }), { key: 'Tab', ctrlKey: false, metaKey: false, altKey: false })
    const handled = handleHistSearchKey(e)

    expect(handled).toBe(true)
    expect(isHistSearchMode()).toBe(false)
    expect(cmdInput.value).toBe('dig darklab.sh A')
    expect(submitComposerCommand).not.toHaveBeenCalled()
  })

  it('handleHistSearchKey ArrowDown navigates to the next match and fills the input', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, handleHistSearchKey } = loadHistSearch()
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

    const down = Object.assign(new Event('keydown', { cancelable: true }), { key: 'ArrowDown', ctrlKey: false, metaKey: false, altKey: false })
    const handled = handleHistSearchKey(down)

    expect(handled).toBe(true)
    // ArrowDown from index 0 moves to index 1
    expect(cmdInput.value).toBe('dig darklab.sh MX')
  })

  it('handleHistSearchKey ArrowUp navigates to the previous match', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, handleHistSearchKey } = loadHistSearch()
    hydrateCmdHistory([
      { command: 'dig darklab.sh A' },
      { command: 'dig darklab.sh MX' },
    ])
    const cmdInput = document.getElementById('cmd')

    enterHistSearch()
    cmdInput.value = 'dig'
    handleHistSearchInput('dig')

    const down = Object.assign(new Event('keydown', { cancelable: true }), { key: 'ArrowDown', ctrlKey: false, metaKey: false, altKey: false })
    handleHistSearchKey(down)
    expect(cmdInput.value).toBe('dig darklab.sh MX')

    const up = Object.assign(new Event('keydown', { cancelable: true }), { key: 'ArrowUp', ctrlKey: false, metaKey: false, altKey: false })
    const handled = handleHistSearchKey(up)

    expect(handled).toBe(true)
    expect(cmdInput.value).toBe('dig darklab.sh A')
  })

  it('handleHistSearchKey Ctrl+R cycles to the next match', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, handleHistSearchKey } = loadHistSearch()
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

    const e = Object.assign(new Event('keydown', { cancelable: true }), { key: 'r', ctrlKey: true, metaKey: false, altKey: false })
    handleHistSearchKey(e)

    expect(cmdInput.value).toBe('dig darklab.sh MX')
  })

  it('handleHistSearchKey returns false for printable characters to allow input to proceed', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchKey } = loadHistSearch()
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])

    enterHistSearch()
    const e = Object.assign(new Event('keydown', { cancelable: true }), { key: 'a', ctrlKey: false, metaKey: false, altKey: false })
    expect(handleHistSearchKey(e)).toBe(false)
  })

  it('handleHistSearchKey Ctrl+C exits search keeping the typed query in input (not restoring pre-draft)', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, handleHistSearchKey, isHistSearchMode } = loadHistSearch()
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])
    const cmdInput = document.getElementById('cmd')
    cmdInput.value = 'pre-draft'

    enterHistSearch()
    // Simulate user typing 'di': browser sets cmdInput.value before the input event fires
    cmdInput.value = 'di'
    handleHistSearchInput('di')

    const e = Object.assign(new Event('keydown', { cancelable: true }), { key: 'c', ctrlKey: true, metaKey: false, altKey: false })
    const handled = handleHistSearchKey(e)

    expect(handled).toBe(true)
    expect(isHistSearchMode()).toBe(false)
    // keepCurrent: typed query stays in input, pre-draft is NOT restored
    expect(cmdInput.value).toBe('di')
  })

  it('handleHistSearchKey ArrowDown wraps from the last match back to the first', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, handleHistSearchKey } = loadHistSearch()
    hydrateCmdHistory([
      { command: 'dig darklab.sh A' },
      { command: 'dig darklab.sh MX' },
    ])
    const cmdInput = document.getElementById('cmd')

    enterHistSearch()
    cmdInput.value = 'dig'
    handleHistSearchInput('dig')

    const down = Object.assign(new Event('keydown', { cancelable: true }), { key: 'ArrowDown', ctrlKey: false, metaKey: false, altKey: false })
    handleHistSearchKey(down)
    expect(cmdInput.value).toBe('dig darklab.sh MX')

    // ArrowDown at the last item wraps back to the first
    handleHistSearchKey(down)
    expect(cmdInput.value).toBe('dig darklab.sh A')
  })

  it('handleHistSearchKey ArrowUp wraps from the first match back to the last', () => {
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, handleHistSearchKey } = loadHistSearch()
    hydrateCmdHistory([
      { command: 'dig darklab.sh A' },
      { command: 'dig darklab.sh MX' },
    ])
    const cmdInput = document.getElementById('cmd')

    enterHistSearch()
    cmdInput.value = 'dig'
    handleHistSearchInput('dig')
    // index starts at 0 (first match); ArrowUp wraps to the last match
    const up = Object.assign(new Event('keydown', { cancelable: true }), { key: 'ArrowUp', ctrlKey: false, metaKey: false, altKey: false })
    const handled = handleHistSearchKey(up)

    expect(handled).toBe(true)
    expect(cmdInput.value).toBe('dig darklab.sh MX')
  })

  it('handleHistSearchKey Tab with no matches exits keeping the typed query in input', () => {
    const submitComposerCommand = vi.fn()
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, handleHistSearchKey, isHistSearchMode } = loadHistSearch({ submitComposerCommand })
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])
    const cmdInput = document.getElementById('cmd')
    cmdInput.value = 'xyz-pre'

    enterHistSearch()
    cmdInput.value = 'xyz'
    handleHistSearchInput('xyz') // no matches

    const e = Object.assign(new Event('keydown', { cancelable: true }), { key: 'Tab', ctrlKey: false, metaKey: false, altKey: false })
    const handled = handleHistSearchKey(e)

    expect(handled).toBe(true)
    expect(isHistSearchMode()).toBe(false)
    // keepCurrent path: typed query stays, pre-draft is NOT restored
    expect(cmdInput.value).toBe('xyz')
    expect(submitComposerCommand).not.toHaveBeenCalled()
  })

  it('handleHistSearchKey Enter after ArrowDown runs the navigated-to match', () => {
    const submitComposerCommand = vi.fn()
    const { hydrateCmdHistory, enterHistSearch, handleHistSearchInput, handleHistSearchKey, isHistSearchMode } = loadHistSearch({ submitComposerCommand })
    hydrateCmdHistory([
      { command: 'dig darklab.sh A' },
      { command: 'dig darklab.sh MX' },
    ])
    const cmdInput = document.getElementById('cmd')

    enterHistSearch()
    cmdInput.value = 'dig'
    handleHistSearchInput('dig')

    const down = Object.assign(new Event('keydown', { cancelable: true }), { key: 'ArrowDown', ctrlKey: false, metaKey: false, altKey: false })
    handleHistSearchKey(down) // moves to index 1 → 'dig darklab.sh MX'

    const enter = Object.assign(new Event('keydown', { cancelable: true }), { key: 'Enter', ctrlKey: false, metaKey: false, altKey: false })
    handleHistSearchKey(enter)

    expect(isHistSearchMode()).toBe(false)
    expect(cmdInput.value).toBe('dig darklab.sh MX')
    expect(submitComposerCommand).toHaveBeenCalledWith('dig darklab.sh MX', { dismissKeyboard: true })
  })

  it('resetCmdHistoryNav exits hist search mode if active', () => {
    const { hydrateCmdHistory, enterHistSearch, resetCmdHistoryNav, isHistSearchMode } = loadHistSearch()
    hydrateCmdHistory([{ command: 'dig darklab.sh A' }])

    enterHistSearch()
    expect(isHistSearchMode()).toBe(true)
    resetCmdHistoryNav()
    expect(isHistSearchMode()).toBe(false)
  })
})
