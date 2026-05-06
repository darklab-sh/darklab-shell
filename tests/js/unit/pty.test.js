import { MemoryStorage, fromDomScript, fromScript } from './helpers/extract.js'

const {
  _createPtyTerminalSession,
  _failInteractivePtyTab,
  _interactivePtyEnabled,
  _interactivePtyMobileUnsupported,
  _ptyFinalize,
  _ptyHandleStreamEndedWithoutExit,
  _ptyInputPayload,
  _ptyInstallKeyboardHandlers,
  _loadPtyScriptOnce,
  _ptyApplyLiveTheme,
  _ptyOpenModal,
  _ptySendInput,
  _ptyScopeModalToTab,
  _scheduleInteractivePtyAssetPreload,
  _xtermGlobalsAvailable,
  focusActiveInteractivePty,
  isInteractivePtyCommand,
  reopenInteractivePtyModal,
} = fromScript(
  'app/static/js/pty.js',
  '_createPtyTerminalSession',
  '_failInteractivePtyTab',
  '_interactivePtyEnabled',
  '_interactivePtyMobileUnsupported',
  '_ptyFinalize',
  '_ptyHandleStreamEndedWithoutExit',
  '_ptyInputPayload',
  '_ptyInstallKeyboardHandlers',
  '_loadPtyScriptOnce',
  '_ptyApplyLiveTheme',
  '_ptyOpenModal',
  '_ptySendInput',
  '_ptyScopeModalToTab',
  '_scheduleInteractivePtyAssetPreload',
  '_xtermGlobalsAvailable',
  'focusActiveInteractivePty',
  'isInteractivePtyCommand',
  'reopenInteractivePtyModal',
)

describe('interactive PTY terminal', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    globalThis.tabs = []
    globalThis.activeTabId = null
    delete globalThis.Terminal
    delete globalThis.FitAddon
    delete globalThis.APP_CONFIG
    delete globalThis.appendLine
    delete globalThis.appendLines
    delete globalThis.addToRecentPreview
    delete globalThis.apiFetch
    delete globalThis.emitUiEvent
    delete globalThis.setStatus
    delete globalThis.setTabStatus
    delete globalThis.stopTimer
    delete globalThis._setRunButtonDisabled
    delete globalThis.hideTabKillBtn
    delete globalThis.isHistoryPanelOpen
    delete globalThis.refreshHistoryPanel
    delete globalThis.refreshWorkspaceFileCache
    delete globalThis.refocusComposerAfterAction
    delete globalThis._previewTruncationNotice
    delete globalThis._maybeMountDeferredPrompt
    delete globalThis.getTab
    delete globalThis.getTabPanel
    delete globalThis.confirmKill
    delete globalThis._workspaceCwd
    delete globalThis.useMobileTerminalViewportMode
  })

  it('detects the reserved mtr interactive command form', () => {
    expect(isInteractivePtyCommand('mtr --interactive darklab.sh')).toBe(true)
    expect(isInteractivePtyCommand('mtr darklab.sh')).toBe(false)
    expect(isInteractivePtyCommand('ping --interactive darklab.sh')).toBe(false)
  })

  it('preloads xterm assets at boot when interactive PTY is enabled', () => {
    const scheduled = []
    const fakeDocument = {
      body: {},
      documentElement: {},
      head: { appendChild: vi.fn() },
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
      getElementById: vi.fn(),
      querySelector: vi.fn(() => null),
      querySelectorAll: vi.fn(() => []),
      createElement: vi.fn(() => ({})),
    }
    const fakeWindow = {
      setTimeout: vi.fn((callback) => {
        scheduled.push(callback)
        return 1
      }),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }

    const { _interactivePtyEnabled: enabled } = fromDomScript(
      'app/static/js/pty.js',
      {
        localStorage: new MemoryStorage(),
        APP_CONFIG: { interactive_pty_enabled: true },
        CustomEvent: class {},
        document: fakeDocument,
        window: fakeWindow,
      },
      '_interactivePtyEnabled',
    )

    expect(enabled()).toBe(true)
    expect(fakeWindow.setTimeout).toHaveBeenCalledTimes(1)
    expect(scheduled).toHaveLength(1)
  })

  it('does not schedule xterm preloading when interactive PTY is disabled', () => {
    expect(_interactivePtyEnabled()).toBe(false)
    expect(_scheduleInteractivePtyAssetPreload()).toBe(false)
  })

  it('replaces failed xterm script tags before retrying vendor asset loads', async () => {
    const failed = document.createElement('script')
    failed.src = '/vendor/xterm.js'
    failed.dataset.ptyLoadState = 'error'
    document.head.appendChild(failed)

    const promise = _loadPtyScriptOnce('/vendor/xterm.js', () => false)
    const replacement = document.querySelector('script[src="/vendor/xterm.js"]')

    expect(failed.isConnected).toBe(false)
    expect(replacement).not.toBe(failed)
    expect(replacement?.dataset.ptyLoadState).toBe('loading')
    replacement?.dispatchEvent(new Event('load'))
    await expect(promise).resolves.toBeUndefined()
  })

  it('detects mobile terminal mode as unsupported for interactive PTY shells', () => {
    expect(_interactivePtyMobileUnsupported()).toBe(false)
    document.body.classList.add('mobile-terminal-mode')
    expect(_interactivePtyMobileUnsupported()).toBe(true)
    document.body.classList.remove('mobile-terminal-mode')
    globalThis.useMobileTerminalViewportMode = vi.fn(() => true)
    expect(_interactivePtyMobileUnsupported()).toBe(true)
  })

  it('reports missing xterm globals before mounting a PTY terminal', () => {
    expect(_xtermGlobalsAvailable()).toBe(false)
    expect(() => _createPtyTerminalSession(document.createElement('div'))).toThrow(
      /terminal assets/i,
    )
  })

  it('creates an xterm terminal with the fit addon and opens it in the screen', () => {
    const opened = []
    const loadedAddons = []
    class FakeTerminal {
      constructor(options) {
        this.options = options
        this.rows = options.rows
        this.cols = options.cols
      }
      loadAddon(addon) {
        loadedAddons.push(addon)
      }
      open(screen) {
        opened.push(screen)
      }
    }
    class FakeFitAddon {
      fit() {}
    }
    globalThis.Terminal = FakeTerminal
    globalThis.FitAddon = { FitAddon: FakeFitAddon }

    const screen = document.createElement('div')
    const session = _createPtyTerminalSession(screen, 20, 90)

    expect(_xtermGlobalsAvailable()).toBe(true)
    expect(session.term).toBeInstanceOf(FakeTerminal)
    expect(session.fitAddon).toBeInstanceOf(FakeFitAddon)
    expect(session.term.options.rows).toBe(20)
    expect(session.term.options.cols).toBe(90)
    expect(session.term.options.lineHeight).toBeGreaterThanOrEqual(1.35)
    expect(opened).toEqual([screen])
    expect(loadedAddons).toHaveLength(1)
  })

  it('refreshes the live xterm theme when the app theme changes', () => {
    const refreshed = vi.fn()
    document.body.style.setProperty('--fg', '#112233')
    const session = {
      term: {
        options: { theme: { foreground: '#ffffff' } },
        rows: 4,
        refresh: refreshed,
      },
    }

    expect(_ptyApplyLiveTheme(session)).toBe(true)
    expect(session.term.options.theme.foreground).toBe('#112233')
    expect(refreshed).toHaveBeenCalledWith(0, 3)
  })

  it('keeps focus on the active PTY terminal while the PTY tab is running', () => {
    const focus = vi.fn()
    document.body.innerHTML = `
      <div class="tab-panel active" data-id="tab-1">
        <div class="pty-screen" data-pty-active="1" data-tab-id="tab-1" tabindex="0"></div>
      </div>
    `
    globalThis.tabs = [{
      id: 'tab-1',
      st: 'running',
      interactivePtyActive: true,
      ptyTerminal: { focus },
    }]
    globalThis.activeTabId = 'tab-1'
    globalThis.getTab = (tabId) => globalThis.tabs.find(tab => tab.id === tabId)

    expect(focusActiveInteractivePty()).toBe(true)
    expect(focus).toHaveBeenCalledTimes(1)
  })

  it('scopes the PTY modal overlay to the owning tab panel', () => {
    document.body.innerHTML = `
      <div id="tab-panels">
        <div class="tab-panel active" data-id="tab-1"></div>
        <div class="tab-panel" data-id="tab-2"></div>
      </div>
      <div id="pty-overlay" class="modal-overlay mobile-sheet-overlay pty-tab-overlay u-hidden">
        <div id="pty-modal"></div>
      </div>
    `

    expect(_ptyScopeModalToTab('tab-1')).toBe(true)
    expect(document.getElementById('pty-overlay').parentElement.dataset.id).toBe('tab-1')
    expect(document.querySelector('.tab-panel[data-id="tab-2"] #pty-overlay')).toBeNull()

    expect(_ptyScopeModalToTab('tab-2')).toBe(true)
    expect(document.getElementById('pty-overlay').parentElement.dataset.id).toBe('tab-2')
    expect(document.querySelector('.tab-panel[data-id="tab-1"] #pty-overlay')).toBeNull()
  })

  it('shows a running-tab indicator that can reopen the hidden live PTY modal', () => {
    const focus = vi.fn()
    const fit = vi.fn()
    class FakeTerminal {
      constructor(options) {
        this.options = options
        this.rows = options.rows
        this.cols = options.cols
      }
      loadAddon() {}
      open() {}
      focus() { focus() }
    }
    class FakeFitAddon {
      fit() { fit() }
    }
    globalThis.Terminal = FakeTerminal
    globalThis.FitAddon = { FitAddon: FakeFitAddon }
    document.body.innerHTML = `
      <div id="tab-panels">
        <div class="tab-panel active" data-id="tab-1">
          <div class="terminal-body">
            <div id="output-tab-1" class="output"></div>
            <div class="terminal-actions"></div>
          </div>
        </div>
      </div>
      <div id="pty-overlay" class="modal-overlay mobile-sheet-overlay pty-tab-overlay u-hidden" aria-hidden="true">
        <div id="pty-modal">
          <span id="pty-modal-command"></span>
          <span id="pty-modal-status" data-tone=""><span id="pty-modal-status-label"></span></span>
          <span id="pty-modal-elapsed"></span>
          <button id="pty-modal-hide"></button>
          <button class="pty-modal-close"></button>
          <button id="pty-modal-kill"></button>
          <section id="pty-modal-screen" class="pty-screen"></section>
        </div>
      </div>
    `
    globalThis.getTabPanel = (tabId) => document.querySelector(`.tab-panel[data-id="${tabId}"]`)

    const session = _ptyOpenModal('tab-1', 'mtr --interactive darklab.sh', 24, 100)
    session.runId = 'run-1'
    const overlay = document.getElementById('pty-overlay')
    document.getElementById('pty-modal-hide').disabled = false
    document.getElementById('pty-modal-hide').click()

    expect(document.querySelector('.pty-running-indicator')?.textContent).toContain('Interactive PTY running')
    expect(overlay.classList.contains('open')).toBe(false)
    expect(overlay.getAttribute('aria-hidden')).toBe('true')
    expect(reopenInteractivePtyModal('tab-1')).toBe(true)
    expect(overlay.classList.contains('open')).toBe(true)
    expect(overlay.getAttribute('aria-hidden')).toBe('false')
    expect(fit).toHaveBeenCalled()
  })

  it('preserves an existing PTY modal when a second PTY start is rejected', () => {
    const disposedTerms = []
    class FakeTerminal {
      constructor(options) {
        this.options = options
        this.rows = options.rows
        this.cols = options.cols
        this.dispose = vi.fn()
        disposedTerms.push(this)
      }
      loadAddon() {}
      open() {}
      focus() {}
      attachCustomKeyEventHandler() {}
      onData() {
        return { dispose: vi.fn() }
      }
    }
    class FakeFitAddon {
      fit() {}
    }
    globalThis.Terminal = FakeTerminal
    globalThis.FitAddon = { FitAddon: FakeFitAddon }
    document.body.innerHTML = `
      <div id="tab-panels">
        <div class="tab-panel" data-id="tab-1"></div>
        <div class="tab-panel active" data-id="tab-2"></div>
      </div>
      <div id="pty-overlay" class="modal-overlay mobile-sheet-overlay pty-tab-overlay u-hidden" aria-hidden="true">
        <div id="pty-modal">
          <span id="pty-modal-command"></span>
          <span id="pty-modal-status" data-tone=""><span id="pty-modal-status-label"></span></span>
          <span id="pty-modal-elapsed"></span>
          <button class="pty-modal-close"></button>
          <button id="pty-modal-kill"></button>
          <section id="pty-modal-screen" class="pty-screen"></section>
        </div>
      </div>
    `
    globalThis.tabs = [
      { id: 'tab-1', st: 'running', interactivePtyActive: true, ptyTerminal: null, rawLines: [] },
      { id: 'tab-2', st: 'idle', interactivePtyActive: false, ptyTerminal: null, rawLines: [] },
    ]
    globalThis.activeTabId = 'tab-2'
    globalThis.getTab = (tabId) => globalThis.tabs.find(tab => tab.id === tabId)
    globalThis.getTabPanel = (tabId) => document.querySelector(`.tab-panel[data-id="${tabId}"]`)
    globalThis.appendCommandEcho = vi.fn()
    globalThis.appendLine = vi.fn()
    globalThis.setStatus = vi.fn()
    globalThis.setTabStatus = vi.fn()
    globalThis._setRunButtonDisabled = vi.fn()
    globalThis.showTabKillBtn = vi.fn()
    globalThis.hideTabKillBtn = vi.fn()
    globalThis.startTimer = vi.fn()
    globalThis.stopTimer = vi.fn()
    globalThis.refocusComposerAfterAction = vi.fn()
    globalThis._workspaceCwd = vi.fn(() => '')

    const firstSession = _ptyOpenModal('tab-1', 'mtr --interactive darklab.sh', 24, 100)
    firstSession.runId = 'run-1'
    globalThis.tabs[0].ptyTerminal = firstSession.term

    _failInteractivePtyTab(
      'tab-2',
      '[server error] An interactive PTY is already running in this session.',
      null,
    )

    const overlay = document.getElementById('pty-overlay')
    expect(overlay.parentElement.dataset.id).toBe('tab-1')
    expect(overlay.classList.contains('open')).toBe(true)
    expect(document.getElementById('pty-modal-screen').dataset.tabId).toBe('tab-1')
    expect(firstSession.term.dispose).not.toHaveBeenCalled()
    expect(globalThis.appendLine).toHaveBeenCalledWith(
      '[server error] An interactive PTY is already running in this session.',
      'exit-fail',
      'tab-2',
    )
  })

  it('lets Ctrl+C flow through xterm as native PTY input', () => {
    let keyHandler = null
    const preventDefault = vi.fn()
    const stopPropagation = vi.fn()
    const confirmKill = vi.fn()
    globalThis.confirmKill = confirmKill

    _ptyInstallKeyboardHandlers({
      runId: 'run-1',
      tabId: 'tab-1',
      term: {
        attachCustomKeyEventHandler: vi.fn((handler) => {
          keyHandler = handler
        }),
      },
    })

    expect(typeof keyHandler).toBe('function')
    expect(keyHandler({
      type: 'keydown',
      key: 'c',
      ctrlKey: true,
      altKey: false,
      metaKey: false,
      shiftKey: false,
      preventDefault,
      stopPropagation,
    })).toBe(true)
    expect(confirmKill).not.toHaveBeenCalled()
    expect(preventDefault).not.toHaveBeenCalled()
    expect(stopPropagation).not.toHaveBeenCalled()

    expect(keyHandler({
      type: 'keydown',
      key: 'c',
      ctrlKey: true,
      altKey: false,
      metaKey: false,
      shiftKey: true,
    })).toBe(true)
  })

  it('truncates PTY input by UTF-8 byte length and reports truncation before posting', () => {
    const appendLine = vi.fn()
    const apiFetch = vi.fn(() => Promise.resolve({ ok: true }))
    globalThis.appendLine = appendLine
    globalThis.apiFetch = apiFetch

    const payload = _ptyInputPayload('a'.repeat(4095) + 'é')
    expect(new TextEncoder().encode(payload.text).length).toBe(4095)
    expect(payload.truncated).toBe(true)

    _ptySendInput('run-1', 'é'.repeat(3000), 'tab-1')

    const posted = JSON.parse(apiFetch.mock.calls[0][1].body)
    expect(new TextEncoder().encode(posted.data).length).toBeLessThanOrEqual(4096)
    expect(appendLine).toHaveBeenCalledWith(
      '[interactive PTY input truncated to 4096 bytes]',
      'notice',
      'tab-1',
    )
  })

  it('finalizes PTY tabs like normal completed runs', async () => {
    const disposed = vi.fn()
    const appendLine = vi.fn()
    const addToRecentPreview = vi.fn()
    const emitUiEvent = vi.fn()
    const refreshHistoryPanel = vi.fn()
    const refreshWorkspaceFileCache = vi.fn()
    const refocusComposerAfterAction = vi.fn()
    const maybeMountDeferredPrompt = vi.fn()
    globalThis.appendLine = appendLine
    globalThis.addToRecentPreview = addToRecentPreview
    globalThis.emitUiEvent = emitUiEvent
    globalThis.setStatus = vi.fn()
    globalThis.setTabStatus = vi.fn()
    globalThis.stopTimer = vi.fn()
    globalThis._setRunButtonDisabled = vi.fn()
    globalThis.hideTabKillBtn = vi.fn()
    globalThis.isHistoryPanelOpen = () => true
    globalThis.refreshHistoryPanel = refreshHistoryPanel
    globalThis.refreshWorkspaceFileCache = refreshWorkspaceFileCache
    globalThis.refocusComposerAfterAction = refocusComposerAfterAction
    globalThis._previewTruncationNotice = () => '[preview truncated]'
    globalThis._maybeMountDeferredPrompt = maybeMountDeferredPrompt
    globalThis.tabs = [{
      id: 'tab-1',
      command: 'mtr --interactive darklab.sh',
      runId: 'run-1',
      historyRunId: 'run-1',
      st: 'running',
      interactivePtyActive: true,
      ptyTerminal: {},
    }]
    globalThis.activeTabId = 'tab-1'
    globalThis.getTab = (tabId) => globalThis.tabs.find(tab => tab.id === tabId)

    const screen = document.createElement('div')
    screen.dataset.ptyActive = '1'
    const session = {
      screen,
      term: { options: { disableStdin: false } },
      resizeDisposable: { dispose: disposed },
    }

    await _ptyFinalize('tab-1', session, {
      code: 0,
      elapsed: 1.2,
      preview_truncated: true,
      output_line_count: 100,
      full_output_available: true,
    })

    const tab = globalThis.tabs[0]
    expect(tab.exitCode).toBe(0)
    expect(tab.runId).toBeNull()
    expect(tab.historyRunId).toBe('run-1')
    expect(tab.previewTruncated).toBe(true)
    expect(tab.fullOutputAvailable).toBe(true)
    expect(tab.fullOutputLoaded).toBe(false)
    expect(tab.interactivePtyActive).toBe(false)
    expect(session.term.options.disableStdin).toBe(true)
    expect(screen.dataset.ptyActive).toBe('0')
    expect(disposed).toHaveBeenCalledTimes(1)
    expect(appendLine).toHaveBeenCalledWith('[interactive PTY exited with code 0 in 1.2s]', 'exit-ok', 'tab-1')
    expect(addToRecentPreview).toHaveBeenCalledWith('mtr --interactive darklab.sh')
    expect(emitUiEvent).toHaveBeenCalledWith('app:last-exit-changed', { value: 0 })
    expect(refreshHistoryPanel).toHaveBeenCalledTimes(1)
    expect(refreshWorkspaceFileCache).toHaveBeenCalledTimes(1)
    expect(maybeMountDeferredPrompt).toHaveBeenCalledWith('tab-1')
    expect(refocusComposerAfterAction).toHaveBeenCalledWith({ preventScroll: true })
  })

  it('appends the saved PTY final frame before the exit status line', async () => {
    const calls = []
    const appendLines = vi.fn(async entries => {
      calls.push(['lines', entries.map(entry => ({
        text: entry.text,
        cls: entry.cls,
        metadata: entry.metadata,
      }))])
    })
    const appendLine = vi.fn((text, cls) => {
      calls.push(['line', text, cls])
    })
    globalThis.appendLines = appendLines
    globalThis.appendLine = appendLine
    globalThis.addToRecentPreview = vi.fn()
    globalThis.emitUiEvent = vi.fn()
    globalThis.setStatus = vi.fn()
    globalThis.setTabStatus = vi.fn()
    globalThis.stopTimer = vi.fn()
    globalThis._setRunButtonDisabled = vi.fn()
    globalThis.hideTabKillBtn = vi.fn()
    globalThis.isHistoryPanelOpen = () => false
    globalThis.refreshWorkspaceFileCache = vi.fn()
    globalThis.refocusComposerAfterAction = vi.fn()
    globalThis._maybeMountDeferredPrompt = vi.fn()
    globalThis.apiFetch = vi.fn(async url => {
      expect(url).toBe('/history/run-1?json&preview=1')
      return {
        ok: true,
        json: async () => ({
          output_entries: [
            { text: 'hop 1 ip.darklab.sh', cls: '', signals: ['ip.darklab.sh'] },
            { text: '', cls: 'pty-marker' },
            { text: 'final frame', cls: '', signals: ['final.darklab.sh'] },
          ],
          preview_notice: '[preview truncated]',
        }),
      }
    })
    globalThis.tabs = [{
      id: 'tab-1',
      command: 'mtr --interactive darklab.sh',
      runId: 'run-1',
      historyRunId: 'run-1',
      st: 'running',
      interactivePtyActive: true,
      ptyTerminal: {},
    }]
    globalThis.activeTabId = 'tab-1'
    globalThis.getTab = (tabId) => globalThis.tabs.find(tab => tab.id === tabId)

    await _ptyFinalize('tab-1', {
      runId: 'run-1',
      term: { options: { disableStdin: false } },
    }, { code: 0, elapsed: 0.4 })

    expect(appendLines).toHaveBeenCalledWith([
      {
        text: 'final frame',
        cls: '',
        metadata: { signals: ['final.darklab.sh'] },
      },
    ], 'tab-1')
    expect(calls.at(-1)).toEqual(['line', '[interactive PTY exited with code 0 in 0.4s]', 'exit-ok'])
  })

  it('marks a PTY tab detached when the stream ends without an exit event but the run is still active', async () => {
    const disposed = vi.fn()
    const appendLine = vi.fn()
    const showTabKillBtn = vi.fn()
    const startPollingActiveRunsAfterReload = vi.fn()
    globalThis.appendLine = appendLine
    globalThis.setStatus = vi.fn()
    globalThis.setTabStatus = vi.fn((tabId, status) => {
      const tab = globalThis.tabs.find(item => item.id === tabId)
      if (tab) tab.st = status === 'running' ? 'running' : status
    })
    globalThis._setRunButtonDisabled = vi.fn()
    globalThis.showTabKillBtn = showTabKillBtn
    globalThis.startPollingActiveRunsAfterReload = startPollingActiveRunsAfterReload
    globalThis.apiFetch = vi.fn(async url => {
      expect(url).toBe('/history/active')
      return {
        ok: true,
        json: async () => ({ runs: [{ run_id: 'run-1', run_type: 'pty' }] }),
      }
    })
    globalThis.tabs = [{
      id: 'tab-1',
      command: 'mtr --interactive darklab.sh',
      runId: 'run-1',
      historyRunId: '',
      st: 'running',
      interactivePtyActive: true,
      ptyTerminal: {},
    }]
    globalThis.activeTabId = 'tab-1'
    globalThis.getTab = (tabId) => globalThis.tabs.find(tab => tab.id === tabId)
    document.body.innerHTML = `
      <div class="tab-panel active" data-id="tab-1">
        <div class="terminal-body">
          <div id="output-tab-1" class="output"></div>
          <div class="terminal-actions"></div>
        </div>
      </div>
    `
    const screen = document.createElement('div')
    screen.dataset.ptyActive = '1'

    await _ptyHandleStreamEndedWithoutExit('tab-1', {
      runId: 'run-1',
      screen,
      term: { options: { disableStdin: false }, dispose: disposed },
    })

    const tab = globalThis.tabs[0]
    expect(tab.reconnectedRun).toBe(true)
    expect(tab.historyRunId).toBe('run-1')
    expect(tab.interactivePtyActive).toBe(false)
    expect(screen.dataset.ptyActive).toBe('0')
    expect(disposed).toHaveBeenCalledTimes(1)
    expect(showTabKillBtn).toHaveBeenCalledWith('tab-1')
    expect(startPollingActiveRunsAfterReload).toHaveBeenCalledTimes(1)
    expect(document.querySelector('.pty-running-indicator')?.textContent).toContain('Reattach unavailable')
    expect(appendLine).toHaveBeenCalledWith(
      '[interactive PTY stream detached - process is still running]',
      'notice',
      'tab-1',
    )
  })
})
