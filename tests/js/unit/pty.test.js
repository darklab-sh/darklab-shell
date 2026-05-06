import { fromScript } from './helpers/extract.js'

const {
  _createPtyTerminalSession,
  _ptyFinalize,
  _ptyInstallKeyboardHandlers,
  _xtermGlobalsAvailable,
  focusActiveInteractivePty,
  isInteractivePtyCommand,
} = fromScript(
  'app/static/js/pty.js',
  '_createPtyTerminalSession',
  '_ptyFinalize',
  '_ptyInstallKeyboardHandlers',
  '_xtermGlobalsAvailable',
  'focusActiveInteractivePty',
  'isInteractivePtyCommand',
)

describe('interactive PTY terminal', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    globalThis.tabs = []
    globalThis.activeTabId = null
    delete globalThis.Terminal
    delete globalThis.FitAddon
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
    delete globalThis.confirmKill
  })

  it('detects the reserved mtr interactive command form', () => {
    expect(isInteractivePtyCommand('mtr --interactive darklab.sh')).toBe(true)
    expect(isInteractivePtyCommand('mtr darklab.sh')).toBe(false)
    expect(isInteractivePtyCommand('ping --interactive darklab.sh')).toBe(false)
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

  it('opens kill confirmation instead of sending Ctrl+C to the PTY', () => {
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
    })).toBe(false)
    expect(confirmKill).toHaveBeenCalledWith('tab-1')
    expect(preventDefault).toHaveBeenCalledTimes(1)
    expect(stopPropagation).toHaveBeenCalledTimes(1)

    expect(keyHandler({
      type: 'keydown',
      key: 'c',
      ctrlKey: true,
      altKey: false,
      metaKey: false,
      shiftKey: true,
    })).toBe(true)
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
})
