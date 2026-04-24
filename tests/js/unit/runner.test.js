import { fromScript, fromDomScript, fromDomScripts, MemoryStorage } from './helpers/extract.js'

const { _formatElapsed } = fromScript('app/static/js/runner.js', '_formatElapsed')
const { _isSyntheticGrepCommand } = fromScript('app/static/js/runner.js', '_isSyntheticGrepCommand')
const { _isSyntheticHeadCommand } = fromScript('app/static/js/runner.js', '_isSyntheticHeadCommand')
const { _isSyntheticTailCommand } = fromScript('app/static/js/runner.js', '_isSyntheticTailCommand')
const { _isSyntheticWcLineCountCommand } = fromScript(
  'app/static/js/runner.js',
  '_isSyntheticWcLineCountCommand',
)
const { _isSyntheticSortCommand } = fromScript('app/static/js/runner.js', '_isSyntheticSortCommand')
const { _isSyntheticUniqCommand } = fromScript('app/static/js/runner.js', '_isSyntheticUniqCommand')
const { _isSyntheticPostFilterCommand } = fromScript(
  'app/static/js/runner.js',
  '_isSyntheticPostFilterCommand',
)
const { _parseSyntheticPostFilterCommand, _applySyntheticPostFilterLines } = fromScript(
  'app/static/js/runner.js',
  '_parseSyntheticPostFilterCommand',
  '_applySyntheticPostFilterLines',
)

// ── _formatElapsed ────────────────────────────────────────────────────────────

describe('_formatElapsed', () => {
  it('formats zero seconds', () => {
    expect(_formatElapsed(0)).toBe('0.0s')
  })

  it('formats sub-minute durations with one decimal place', () => {
    expect(_formatElapsed(32.6)).toBe('32.6s')
    expect(_formatElapsed(59.9)).toBe('59.9s')
  })

  it('formats exactly 60 seconds as minutes', () => {
    expect(_formatElapsed(60)).toBe('1m 0.0s')
  })

  it('formats multi-minute durations without hours', () => {
    expect(_formatElapsed(125)).toBe('2m 5.0s')
  })

  it('formats exactly one hour', () => {
    expect(_formatElapsed(3600)).toBe('1h 0m 0.0s')
  })

  it('formats hour + minutes + seconds', () => {
    expect(_formatElapsed(3812.3)).toBe('1h 3m 32.3s')
  })
})

describe('stall recovery notices', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('restores the tab to running if stream activity resumes after a stall', () => {
    vi.useFakeTimers()
    const appendLine = vi.fn()
    const {
      _resetStalledTimeout,
      _recoverStalledRun,
      status,
      runBtn,
      tabs,
    } = loadRunnerFns({
      tabs: [{
        id: 'tab-1',
        st: 'running',
        runId: 'run-1',
        historyRunId: 'run-1',
        killed: false,
        pendingKill: false,
        runStart: Date.now() - 5_000,
      }],
      appendLine,
    })

    _resetStalledTimeout('tab-1')
    vi.advanceTimersByTime(45_000)

    expect(appendLine).toHaveBeenCalledWith(
      '[connection stalled — no stream activity arrived from the server for 45s]',
      'denied',
      'tab-1',
    )
    expect(status.textContent).toBe('IDLE')
    expect(tabs[0].st).toBe('fail')
    expect(runBtn.disabled).toBe(false)

    _recoverStalledRun('tab-1')

    expect(appendLine).toHaveBeenCalledWith(
      '[connection re-established — live output resumed]',
      'exit-ok',
      'tab-1',
    )
    expect(status.textContent).toBe('RUNNING')
    expect(tabs[0].st).toBe('running')
    expect(runBtn.disabled).toBe(true)
  })
})

describe('_isSyntheticGrepCommand', () => {
  it('accepts the narrow synthetic grep form', () => {
    expect(_isSyntheticGrepCommand('ping darklab.sh | grep ttl')).toBe(true)
    expect(_isSyntheticGrepCommand('ping darklab.sh | grep -iv ttl')).toBe(true)
    expect(_isSyntheticGrepCommand("ping darklab.sh | grep -E 'ttl|time'")).toBe(true)
  })

  it('accepts no-space pipe variants', () => {
    expect(_isSyntheticGrepCommand('ping darklab.sh|grep ttl')).toBe(true)
    expect(_isSyntheticGrepCommand('ping darklab.sh|grep -i ttl')).toBe(true)
  })

  it('accepts chained synthetic pipe helpers', () => {
    expect(_isSyntheticPostFilterCommand('ping darklab.sh | grep ttl | wc -l')).toBe(true)
    expect(_isSyntheticPostFilterCommand('ping darklab.sh | grep ttl | sort | uniq')).toBe(true)
  })

  it('rejects unsupported shell operator forms', () => {
    expect(_isSyntheticGrepCommand('ping darklab.sh | cat')).toBe(false)
    expect(_isSyntheticGrepCommand('ping darklab.sh | grep -n ttl')).toBe(false)
    expect(_isSyntheticGrepCommand('ping darklab.sh | grep ttl file.txt')).toBe(false)
    expect(_isSyntheticGrepCommand('ping darklab.sh || grep ttl')).toBe(false)
    expect(_isSyntheticPostFilterCommand('ping darklab.sh | grep ttl | cat')).toBe(false)
  })
})

describe('other synthetic post-filters', () => {
  it('accepts the narrow head/tail/wc forms', () => {
    expect(_isSyntheticHeadCommand('ping darklab.sh | head')).toBe(true)
    expect(_isSyntheticHeadCommand('ping darklab.sh | head -n 5')).toBe(true)
    expect(_isSyntheticHeadCommand('ping darklab.sh | head -5')).toBe(true)
    expect(_isSyntheticTailCommand('ping darklab.sh | tail')).toBe(true)
    expect(_isSyntheticTailCommand('ping darklab.sh | tail -n 5')).toBe(true)
    expect(_isSyntheticTailCommand('ping darklab.sh | tail -5')).toBe(true)
    expect(_isSyntheticWcLineCountCommand('ping darklab.sh | wc -l')).toBe(true)
  })

  it('accepts no-space pipe variants', () => {
    expect(_isSyntheticHeadCommand('ping darklab.sh|head')).toBe(true)
    expect(_isSyntheticHeadCommand('ping darklab.sh|head -n 5')).toBe(true)
    expect(_isSyntheticHeadCommand('ping darklab.sh|head -5')).toBe(true)
    expect(_isSyntheticTailCommand('ping darklab.sh|tail')).toBe(true)
    expect(_isSyntheticTailCommand('ping darklab.sh|tail -n 5')).toBe(true)
    expect(_isSyntheticTailCommand('ping darklab.sh|tail -5')).toBe(true)
    expect(_isSyntheticWcLineCountCommand('ping darklab.sh|wc -l')).toBe(true)
  })

  it('rejects unsupported forms', () => {
    expect(_isSyntheticHeadCommand('ping darklab.sh | head -abc')).toBe(false)
    expect(_isSyntheticTailCommand('ping darklab.sh | tail -n five')).toBe(false)
    expect(_isSyntheticWcLineCountCommand('ping darklab.sh | wc -c')).toBe(false)
  })
})

describe('sort and uniq synthetic post-filters', () => {
  it('accepts sort with no flags', () => {
    expect(_isSyntheticSortCommand('ping darklab.sh | sort')).toBe(true)
    expect(_isSyntheticSortCommand('ping darklab.sh|sort')).toBe(true)
  })

  it('accepts sort with valid flag combinations', () => {
    expect(_isSyntheticSortCommand('ping darklab.sh | sort -r')).toBe(true)
    expect(_isSyntheticSortCommand('ping darklab.sh | sort -n')).toBe(true)
    expect(_isSyntheticSortCommand('ping darklab.sh | sort -u')).toBe(true)
    expect(_isSyntheticSortCommand('ping darklab.sh | sort -rn')).toBe(true)
    expect(_isSyntheticSortCommand('ping darklab.sh | sort -ru')).toBe(true)
    expect(_isSyntheticSortCommand('ping darklab.sh | sort -nu')).toBe(true)
    expect(_isSyntheticSortCommand('ping darklab.sh | sort -rnu')).toBe(true)
  })

  it('rejects invalid sort flags', () => {
    expect(_isSyntheticSortCommand('ping darklab.sh | sort -x')).toBe(false)
    expect(_isSyntheticSortCommand('ping darklab.sh | sort -rk')).toBe(false)
    expect(_isSyntheticSortCommand('ping darklab.sh | sort -n 5')).toBe(false)
  })

  it('accepts uniq with no flags', () => {
    expect(_isSyntheticUniqCommand('ping darklab.sh | uniq')).toBe(true)
    expect(_isSyntheticUniqCommand('ping darklab.sh|uniq')).toBe(true)
  })

  it('accepts uniq -c', () => {
    expect(_isSyntheticUniqCommand('ping darklab.sh | uniq -c')).toBe(true)
    expect(_isSyntheticUniqCommand('ping darklab.sh|uniq -c')).toBe(true)
  })

  it('rejects unsupported uniq flags', () => {
    expect(_isSyntheticUniqCommand('ping darklab.sh | uniq -d')).toBe(false)
    expect(_isSyntheticUniqCommand('ping darklab.sh | uniq -u')).toBe(false)
  })
})

describe('client-side synthetic post-filters', () => {
  it('parses the base command and grep stage for client-side built-ins', () => {
    const parsed = _parseSyntheticPostFilterCommand('theme list | grep -i blue')

    expect(parsed.baseCommand).toBe('theme list')
    expect(parsed.stages).toEqual([
      { kind: 'grep', pattern: 'blue', ignoreCase: true, invertMatch: false, extended: false },
    ])
  })

  it('applies chained synthetic helpers to captured client-side output', () => {
    const parsed = _parseSyntheticPostFilterCommand('theme list | grep light | sort -r | head -n 2')
    const lines = _applySyntheticPostFilterLines([
      { text: 'theme_dark_amber', cls: 'fake-help-row' },
      { text: 'theme_light_blue', cls: 'fake-help-row' },
      { text: 'theme_light_olive', cls: 'fake-help-row' },
      { text: 'theme_dark_green', cls: 'fake-help-row' },
    ], parsed)

    expect(lines.map(line => line.text)).toEqual([
      'theme_light_olive',
      'theme_light_blue',
    ])
  })
})

describe('client-side UI command pipe helpers', () => {
  it('filters terminal-native theme output through the same pipe helpers as older built-ins', async () => {
    const appendLine = vi.fn()
    const { submitCommand } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      appendLine,
      runnerInitCode: `
        async function handleThemeCommand(cmd, tabId) {
          appendCommandEcho(cmd, tabId);
          appendLine('theme_dark_amber', 'fake-help-row', tabId);
          appendLine('theme_light_blue', 'fake-help-row', tabId);
          appendLine('theme_light_olive', 'fake-help-row', tabId);
        }
      `,
    })

    await submitCommand('theme list | grep light | wc -l')
    await vi.waitFor(() => expect(appendLine).toHaveBeenCalledWith('2', '', 'tab-1'))

    expect(appendLine).toHaveBeenCalledWith('theme list | grep light | wc -l', 'prompt-echo', 'tab-1')
    expect(appendLine).not.toHaveBeenCalledWith('theme_light_blue', 'fake-help-row', 'tab-1')
  })

  it('filters terminal-native config output through chained pipe helpers', async () => {
    const appendLine = vi.fn()
    const { submitCommand } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      appendLine,
      runnerInitCode: `
        async function handleConfigCommand(cmd, tabId) {
          appendCommandEcho(cmd, tabId);
          appendLine('line-numbers        off', 'fake-kv', tabId);
          appendLine('timestamps          off', 'fake-kv', tabId);
          appendLine('welcome             static', 'fake-kv', tabId);
        }
      `,
    })

    await submitCommand('config list | tail -n 2 | head -n 1')
    await vi.waitFor(() =>
      expect(appendLine).toHaveBeenCalledWith('timestamps          off', 'fake-kv', 'tab-1'),
    )

    expect(appendLine).toHaveBeenCalledWith('config list | tail -n 2 | head -n 1', 'prompt-echo', 'tab-1')
    expect(appendLine).not.toHaveBeenCalledWith('line-numbers        off', 'fake-kv', 'tab-1')
  })

  it('persists terminal-native built-ins to server-backed history', async () => {
    const appendLine = vi.fn()
    const addToRecentPreview = vi.fn()
    const apiFetch = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ ok: true, run_id: 'client-run-1' }),
    }))
    const { submitCommand } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      appendLine,
      addToRecentPreview,
      apiFetch,
      runnerInitCode: `
        async function handleThemeCommand(cmd, tabId) {
          appendCommandEcho(cmd, tabId);
          appendLine('Available themes:', 'fake-section', tabId);
          appendLine('Dark themes:', 'fake-section', tabId);
        }
      `,
    })

    await submitCommand('theme list')
    await vi.waitFor(() => expect(apiFetch).toHaveBeenCalledWith(
      '/run/client',
      expect.objectContaining({ method: 'POST' }),
    ))
    const payload = JSON.parse(apiFetch.mock.calls[0][1].body)

    expect(addToRecentPreview).toHaveBeenCalledWith('theme list')
    expect(payload).toEqual({
      command: 'theme list',
      exit_code: 0,
      lines: [
        { text: 'Available themes:', cls: 'fake-section' },
        { text: 'Dark themes:', cls: 'fake-section' },
      ],
    })
  })

  it('clears stale failed tab and HUD state after a successful client-side built-in', async () => {
    const appendLine = vi.fn()
    const { submitCommand, tabs, status } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'fail', exitCode: 2, runId: null, killed: false, pendingKill: false }],
      appendLine,
      runnerInitCode: `
        async function handleThemeCommand(cmd, tabId) {
          appendCommandEcho(cmd, tabId);
          appendLine('current theme      Darklab Obsidian', 'fake-kv', tabId);
          setStatus('ok');
        }
      `,
    })
    status.className = 'status-pill fail'
    status.textContent = 'IDLE'

    await submitCommand('theme current')
    await vi.waitFor(() => expect(tabs[0].st).toBe('ok'))

    expect(tabs[0].exitCode).toBe(0)
    expect(status.className).toBe('status-pill ok')
    expect(status.textContent).toBe('IDLE')
  })
})

function loadRunnerFns({
  tabs = [{ id: 'tab-1', st: 'running', runId: null, killed: false, pendingKill: false }],
  activeTabId = 'tab-1',
  cmdValue = '',
  appConfig = {},
  apiFetch = () => Promise.resolve(),
  createTab = () => 'tab-2',
  addToHistory = () => {},
  addToRecentPreview = () => {},
  appendLine = () => {},
  appendCommandEcho = () => {},
  getComposerValue: getComposerValueOverride = null,
  getVisibleComposerInput: getVisibleComposerInputOverride = null,
  welcomeActive = false,
  welcomeOwnsTab = () => false,
  clearTab: clearTabOverride = null,
  showToast: showToastOverride = null,
  confirmClearSessionToken: confirmClearSessionTokenOverride = null,
  setComposerPromptMode: setComposerPromptModeOverride = null,
  copyTextToClipboard: copyTextToClipboardOverride = vi.fn(() => Promise.resolve()),
  updateSessionId: updateSessionIdOverride = vi.fn(),
  reloadSessionHistory: reloadSessionHistoryOverride = vi.fn(() => Promise.resolve()),
  hydrateCmdHistory: hydrateCmdHistoryOverride = vi.fn(),
  sessionId = 'session-old',
  localStorageEntries = {},
  dismissMobileKeyboardAfterSubmit = () => {},
  maybeMountDeferredPrompt = vi.fn(),
  restoreHistoryRunIntoTab = vi.fn(() => Promise.resolve('tab-1')),
  getRunNotifyPreference: getRunNotifyPreferenceOverride = () => 'off',
  Notification: NotificationOverride = undefined,
  handleThemeCommand: handleThemeCommandOverride = undefined,
  handleConfigCommand: handleConfigCommandOverride = undefined,
  runnerInitCode = '',
} = {}) {
  const normalizedTabs = tabs.map((tab) => ({
    rawLines: [],
    previewTruncated: false,
    fullOutputAvailable: false,
    fullOutputLoaded: false,
    historyRunId: null,
    currentRunStartIndex: null,
    ...tab,
  }))

  document.body.innerHTML = `
    <input id="cmd" />
    <button id="run-btn"></button>
    <span id="status"></span>
    <span id="run-timer"></span>
    <div id="mobile-shell" aria-hidden="true">
      <div id="mobile-shell-composer">
        <div id="mobile-composer-host">
          <div id="mobile-composer-row">
            <input id="mobile-cmd" autocomplete="off" autocapitalize="none" autocorrect="off" spellcheck="false" inputmode="text" />
            <button id="mobile-run-btn"></button>
          </div>
        </div>
      </div>
    </div>
    <div id="history-panel"></div>
    <div id="tabs-bar">
      <div class="tab" data-id="tab-1"><span class="tab-status idle"></span></div>
    </div>
    <div id="tab-panels">
      <div class="tab-panel" data-id="tab-1">
        <button class="tab-kill-btn" data-tab="tab-1" style="display:inline-block"></button>
      </div>
    </div>
  `
  const cmdInput = document.getElementById('cmd')
  const runBtn = document.getElementById('run-btn')
  const status = document.getElementById('status')
  const runTimer = document.getElementById('run-timer')
  const historyPanel = document.getElementById('history-panel')
  const tabsBar = document.getElementById('tabs-bar')
  const tabPanels = document.getElementById('tab-panels')
  const storage = new MemoryStorage()
  const sessionStore = new MemoryStorage()
  Object.entries(localStorageEntries).forEach(([key, value]) => storage.setItem(key, value))
  cmdInput.value = cmdValue
  Object.defineProperty(cmdInput, 'focus', { configurable: true, value: vi.fn() })
  cmdInput.blur = vi.fn()

  const setTabLabel = vi.fn()
  const setTabStatus = vi.fn((id, nextStatus) => {
    const tab = normalizedTabs.find((t) => t.id === id)
    if (tab) tab.st = nextStatus
    const dot = document.querySelector(`.tab[data-id="${id}"] .tab-status`)
    if (dot) dot.className = `tab-status ${nextStatus}`
  })
  const clearTab = clearTabOverride || vi.fn()
  const activateTab = vi.fn((id) => {
    const tab = normalizedTabs.find((t) => t.id === id)
    if (tab) {
      activeTabId = id
      status.className = 'status-pill running'
      status.textContent = 'RUNNING'
    }
  })
  const cancelWelcome = vi.fn()
  const showToast = showToastOverride || vi.fn()

  const fns = fromDomScripts(
    ['app/static/js/runner.js'],
    {
      document,
      Map,
      tabs: normalizedTabs,
      activeTabId,
      cmdInput,
      runBtn,
      status,
      runTimer,
      historyPanel,
      tabsBar,
      tabPanels,
      mobileCmdInput: document.getElementById('mobile-cmd'),
      mobileRunBtn: document.getElementById('mobile-run-btn'),
      syncRunButtonDisabled: undefined,
      APP_CONFIG: appConfig,
      _welcomeActive: welcomeActive,
      _welcomeDone: false,
      searchBar: document.createElement('div'),
      addToHistory,
      addToRecentPreview,
      setTabLabel,
      setTabStatus,
      activateTab,
      appendLine,
      appendCommandEcho,
      apiFetch,
      localStorage: storage,
      sessionStorage: sessionStore,
      SESSION_ID: sessionId,
      maskSessionToken: (token) => {
        if (typeof token !== 'string' || !token) return '(none)'
        if (token.startsWith('tok_')) return `tok_${token.slice(4, 8)}••••`
        return `${token.slice(0, 8)}••••••••`
      },
      copyTextToClipboard: copyTextToClipboardOverride,
      updateSessionId: updateSessionIdOverride,
      reloadSessionHistory: reloadSessionHistoryOverride,
      hydrateCmdHistory: hydrateCmdHistoryOverride,
      createTab,
      clearTab,
      cancelWelcome,
      welcomeOwnsTab,
      requestWelcomeSettle: () => {},
      refreshHistoryPanel: () => {},
      showToast,
      ...(confirmClearSessionTokenOverride
        ? { confirmClearSessionToken: confirmClearSessionTokenOverride }
        : {}),
      ...(setComposerPromptModeOverride
        ? { setComposerPromptMode: setComposerPromptModeOverride }
        : {}),
      dismissMobileKeyboardAfterSubmit,
      _maybeMountDeferredPrompt: maybeMountDeferredPrompt,
      restoreHistoryRunIntoTab,
      getComposerValue: getComposerValueOverride || (() => cmdValue),
      ...(getVisibleComposerInputOverride
        ? { getVisibleComposerInput: getVisibleComposerInputOverride }
        : {}),
      describeFetchError: (err, context = 'server') => {
        const message = err && err.message ? err.message : 'unknown network error'
        if (message === 'Failed to fetch' || message === 'network down') {
          return `Unable to reach the ${context}. Check that it is running and try again.`
        }
        return `Request to the ${context} failed: ${message}`
      },
      logClientError: () => {},
      clearTimeout,
      setTimeout,
      Event,
      getRunNotifyPreference: getRunNotifyPreferenceOverride,
      ...(handleThemeCommandOverride ? { handleThemeCommand: handleThemeCommandOverride } : {}),
      ...(handleConfigCommandOverride ? { handleConfigCommand: handleConfigCommandOverride } : {}),
      ...(NotificationOverride !== undefined ? { Notification: NotificationOverride } : {}),
    },
    `{
    setStatus,
    doKill,
    _maybeNotify,
    submitCommand,
    submitComposerCommand,
    submitVisibleComposerCommand,
    interruptPromptLine,
    hasPendingTerminalConfirm,
    cancelPendingTerminalConfirm,
    runCommand,
    restoreActiveRunsAfterReload,
    pollActiveRunsAfterReload,
    syncActiveRunTimer,
    _resetStalledTimeout,
    _clearStalledTimeout,
    _recoverStalledRun,
    _getPendingKillTabId: () => pendingKillTabId,
    }`,
    `${runnerInitCode}\nsetTabs(tabs); setActiveTabId(activeTabId);`,
  )

  return {
    ...fns,
    tabs: normalizedTabs,
    cmdInput,
    runBtn,
    status,
    storage,
    setTabLabel,
    clearTab,
    cancelWelcome,
    showToast,
    interruptPromptLine: fns.interruptPromptLine,
    hasPendingTerminalConfirm: fns.hasPendingTerminalConfirm,
    cancelPendingTerminalConfirm: fns.cancelPendingTerminalConfirm,
    maybeMountDeferredPrompt,
    restoreHistoryRunIntoTab,
  }
}

describe('runner helpers', () => {
  it('setStatus shows RUNNING only while running and IDLE otherwise', () => {
    const { setStatus, status } = loadRunnerFns()

    setStatus('running')
    expect(status.className).toBe('status-pill running')
    expect(status.textContent).toBe('RUNNING')

    setStatus('ok')
    expect(status.className).toBe('status-pill ok')
    expect(status.textContent).toBe('IDLE')

    setStatus('fail')
    expect(status.className).toBe('status-pill fail')
    expect(status.textContent).toBe('IDLE')

    setStatus('killed')
    expect(status.className).toBe('status-pill killed')
    expect(status.textContent).toBe('IDLE')
  })

  it('doKill sends /kill immediately when runId is already known', () => {
    const apiFetch = vi.fn(() => Promise.resolve())
    const maybeMountDeferredPrompt = vi.fn()
    const { doKill, tabs, runBtn, status } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'running', runId: 'run-123', killed: false, pendingKill: false }],
      apiFetch,
      maybeMountDeferredPrompt,
    })

    doKill('tab-1')

    expect(apiFetch).toHaveBeenCalledWith(
      '/kill',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    expect(tabs[0].runId).toBeNull()
    expect(tabs[0].killed).toBe(true)
    expect(document.querySelector('.tab-status').className).toBe('tab-status killed')
    expect(document.querySelector('.tab-kill-btn').style.display).toBe('none')
    expect(document.querySelector('.tab-kill-btn').hidden).toBe(true)
    expect(status.className).toBe('status-pill killed')
    expect(runBtn.disabled).toBe(false)
    expect(maybeMountDeferredPrompt).toHaveBeenCalledWith('tab-1')
  })

  it('restoreActiveRunsAfterReload marks restored tabs as running placeholders', () => {
    const appendLine = vi.fn()
    const createTab = vi.fn(() => 'tab-2')
    const setTabLabel = vi.fn()
    const now = Date.now()
    vi.useFakeTimers()
    vi.setSystemTime(new Date(now))
    const { restoreActiveRunsAfterReload, tabs, status } = loadRunnerFns({
      tabs: [
        { id: 'tab-1', st: 'idle', runId: null, rawLines: [], pendingKill: false, killed: false },
      ],
      appendLine,
      createTab,
    })

    restoreActiveRunsAfterReload([
      { run_id: 'run-1', command: 'ping darklab.sh', started: '2026-01-01T00:00:00Z' },
    ])

    expect(tabs[0].historyRunId).toBe('run-1')
    expect(tabs[0].reconnectedRun).toBe(true)
    expect(tabs[0].st).toBe('running')
    expect(appendLine).toHaveBeenCalledWith('ping darklab.sh', 'prompt-echo', 'tab-1')
    expect(document.querySelector('.tab-kill-btn').hidden).toBe(false)
    expect(status.className).toBe('status-pill running')
    vi.useRealTimers()
  })

  it('restoreActiveRunsAfterReload does not overwrite a restored non-running tab', () => {
    const appendLine = vi.fn()
    const createTab = vi.fn(() => 'tab-2')
    const { restoreActiveRunsAfterReload, tabs } = loadRunnerFns({
      tabs: [
        {
          id: 'tab-1',
          st: 'idle',
          runId: null,
          rawLines: [{ text: '$ dig darklab.sh', cls: 'prompt-echo' }],
          draftInput: 'dig darklab.sh',
          command: 'dig darklab.sh',
          historyRunId: 'run-old',
          renamed: true,
          pendingKill: false,
          killed: false,
        },
      ],
      appendLine,
      createTab,
    })

    restoreActiveRunsAfterReload([
      { run_id: 'run-1', command: 'ping darklab.sh', started: '2026-01-01T00:00:00Z' },
    ])

    expect(createTab).toHaveBeenCalledWith()
    expect(tabs[0].historyRunId).toBe('run-old')
  })

  it('pollActiveRunsAfterReload restores a completed reconnected run through history', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/history/active') {
        return Promise.resolve({ json: () => Promise.resolve({ runs: [] }) })
      }
      if (url === '/history/run-123?json&preview=1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: 'run-123', command: 'ping darklab.sh', exit_code: 0 }),
        })
      }
      return Promise.reject(new Error(`unexpected ${url}`))
    })
    const restoreHistoryRunIntoTab = vi.fn(() => Promise.resolve('tab-1'))
    const { pollActiveRunsAfterReload, tabs } = loadRunnerFns({
      tabs: [
        {
          id: 'tab-1',
          st: 'running',
          runId: 'run-123',
          historyRunId: 'run-123',
          reconnectedRun: true,
          rawLines: [],
          pendingKill: false,
          killed: false,
        },
      ],
      apiFetch,
      restoreHistoryRunIntoTab,
    })

    await pollActiveRunsAfterReload()

    expect(apiFetch).toHaveBeenCalledWith('/history/active')
    expect(apiFetch).toHaveBeenCalledWith('/history/run-123?json&preview=1')
    expect(restoreHistoryRunIntoTab).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'run-123' }),
      { targetTabId: 'tab-1', hidePanelOnSuccess: false },
    )
    expect(tabs[0].reconnectedRun).toBe(false)
  })

  it('doKill marks pendingKill when runId is not yet available', () => {
    const apiFetch = vi.fn(() => Promise.resolve())
    const { doKill, tabs } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'running', runId: null, killed: false, pendingKill: false }],
      apiFetch,
    })

    doKill('tab-1')

    expect(apiFetch).not.toHaveBeenCalled()
    expect(tabs[0].pendingKill).toBe(true)
    expect(tabs[0].killed).toBe(true)
  })

  it('runCommand blocks shell operators client-side before calling the API', () => {
    const apiFetch = vi.fn(() => Promise.resolve())
    const appendLine = vi.fn()
    const { runCommand, status } = loadRunnerFns({
      cmdValue: 'ping google.com | cat /etc/passwd',
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch,
      appendLine,
    })

    runCommand()

    expect(apiFetch).not.toHaveBeenCalled()
    expect(appendLine).toHaveBeenNthCalledWith(
      1,
      'ping google.com | cat /etc/passwd',
      'prompt-echo',
      undefined,
    )
    expect(appendLine).toHaveBeenNthCalledWith(
      2,
      '[denied] Shell operators (&&, |, ;, >, etc.) are not permitted.',
      'denied',
    )
    expect(status.className).toBe('status-pill fail')
  })

  it('runCommand allows the narrow synthetic grep form through to the API', () => {
    const apiFetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        body: { getReader: () => ({ read: vi.fn(() => Promise.resolve({ done: true })) }) },
      }),
    )
    const appendLine = vi.fn()
    const { runCommand, status } = loadRunnerFns({
      cmdValue: 'ping darklab.sh | grep ttl',
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch,
      appendLine,
    })

    runCommand()

    expect(apiFetch).toHaveBeenCalled()
    expect(appendLine).not.toHaveBeenCalledWith(
      '[denied] Shell operators (&&, |, ;, >, etc.) are not permitted.',
      'denied',
    )
    expect(status.className).not.toBe('status-pill fail')
  })

  it('adds commands to the preview recents even when they exit non-zero', async () => {
    let readCount = 0
    const addToRecentPreview = vi.fn()
    const apiFetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        body: {
          getReader: () => ({
            read: vi.fn(() => {
              readCount += 1
              if (readCount === 1) {
                return Promise.resolve({
                  done: false,
                  value: new TextEncoder().encode(
                    'data: {"type":"started","run_id":"run-1"}\n\n' +
                    'data: {"type":"exit","code":0,"elapsed":"0.1"}\n\n',
                  ),
                })
              }
              return Promise.resolve({ done: true })
            }),
          }),
        },
      }),
    )
    const { runCommand } = loadRunnerFns({
      cmdValue: 'ping -c 1 darklab.sh',
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch,
      addToRecentPreview,
    })

    runCommand()
    await Promise.resolve()
    await Promise.resolve()

    expect(addToRecentPreview).toHaveBeenCalledWith('ping -c 1 darklab.sh')

    readCount = 0
    addToRecentPreview.mockClear()
    const failedFetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        body: {
          getReader: () => ({
            read: vi.fn(() => {
              readCount += 1
              if (readCount === 1) {
                return Promise.resolve({
                  done: false,
                  value: new TextEncoder().encode(
                    'data: {"type":"started","run_id":"run-2"}\n\n' +
                    'data: {"type":"exit","code":1,"elapsed":"0.1"}\n\n',
                  ),
                })
              }
              return Promise.resolve({ done: true })
            }),
          }),
        },
      }),
    )
    const failedHarness = loadRunnerFns({
      cmdValue: 'ping -c 1 nope.darklab',
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch: failedFetch,
      addToRecentPreview,
    })

    failedHarness.runCommand()
    await Promise.resolve()
    await Promise.resolve()

    expect(addToRecentPreview).toHaveBeenCalledWith('ping -c 1 nope.darklab')
  })

  it('does not add unsupported fake commands to the preview recents', async () => {
    let readCount = 0
    const addToRecentPreview = vi.fn()
    const apiFetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        body: {
          getReader: () => ({
            read: vi.fn(() => {
              readCount += 1
              if (readCount === 1) {
                return Promise.resolve({
                  done: false,
                  value: new TextEncoder().encode(
                    'data: {"type":"started","run_id":"run-3"}\n\n' +
                    'data: {"type":"output","text":"Unsupported fake command: pign darklab.sh"}\n\n' +
                    'data: {"type":"exit","code":1,"elapsed":"0.1"}\n\n',
                  ),
                })
              }
              return Promise.resolve({ done: true })
            }),
          }),
        },
      }),
    )
    const { runCommand } = loadRunnerFns({
      cmdValue: 'pign darklab.sh',
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch,
      addToRecentPreview,
    })

    runCommand()
    await Promise.resolve()
    await Promise.resolve()

    expect(addToRecentPreview).not.toHaveBeenCalled()
  })

  it('runCommand allows other synthetic post-filters through to the API', () => {
    const apiFetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        body: { getReader: () => ({ read: vi.fn(() => Promise.resolve({ done: true })) }) },
      }),
    )
    const appendLine = vi.fn()
    const { runCommand, status } = loadRunnerFns({
      cmdValue: 'ping darklab.sh | tail -n 5',
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch,
      appendLine,
    })

    runCommand()

    expect(apiFetch).toHaveBeenCalled()
    expect(appendLine).not.toHaveBeenCalledWith(
      '[denied] Shell operators (&&, |, ;, >, etc.) are not permitted.',
      'denied',
    )
    expect(status.className).not.toBe('status-pill fail')
  })

  it('runCommand allows exact special built-in commands with shell punctuation through to the API', () => {
    const apiFetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        body: { getReader: () => ({ read: vi.fn(() => Promise.resolve({ done: true })) }) },
      }),
    )
    const appendLine = vi.fn()
    const { runCommand, status } = loadRunnerFns({
      cmdValue: ':(){ :|:& };:',
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch,
      appendLine,
    })

    runCommand()

    expect(apiFetch).toHaveBeenCalled()
    expect(appendLine).not.toHaveBeenCalledWith(
      '[denied] Shell operators (&&, |, ;, >, etc.) are not permitted.',
      'denied',
    )
    expect(status.className).not.toBe('status-pill fail')
  })

  it('runCommand on blank or whitespace input creates a new empty prompt line', () => {
    const apiFetch = vi.fn(() => Promise.resolve())
    const appendLine = vi.fn()
    const { runCommand, cmdInput, status } = loadRunnerFns({
      cmdValue: '   ',
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch,
      appendLine,
    })

    runCommand()

    expect(apiFetch).not.toHaveBeenCalled()
    expect(appendLine).toHaveBeenCalledWith('', 'prompt-echo', 'tab-1')
    expect(cmdInput.value).toBe('')
    expect(status.className).toBe('status-pill idle')
  })

  it('runCommand on blank input while a command is running does not append a prompt line', () => {
    const apiFetch = vi.fn(() => Promise.resolve())
    const appendLine = vi.fn()
    const { runCommand, cmdInput, status } = loadRunnerFns({
      cmdValue: '',
      tabs: [{ id: 'tab-1', st: 'running', runId: 'r1', killed: false, pendingKill: false }],
      apiFetch,
      appendLine,
    })

    runCommand()

    expect(apiFetch).not.toHaveBeenCalled()
    expect(appendLine).not.toHaveBeenCalled()
  })

  it('runCommand blocks direct /tmp and /data paths client-side before calling the API', () => {
    const apiFetch = vi.fn(() => Promise.resolve())
    const appendLine = vi.fn()
    const { runCommand, status } = loadRunnerFns({
      cmdValue: 'curl /tmp/file',
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch,
      appendLine,
    })

    runCommand()

    expect(apiFetch).not.toHaveBeenCalled()
    expect(appendLine).toHaveBeenNthCalledWith(1, 'curl /tmp/file', 'prompt-echo', undefined)
    expect(appendLine).toHaveBeenNthCalledWith(
      2,
      '[denied] Access to /data and /tmp is not permitted.',
      'denied',
    )
    expect(status.className).toBe('status-pill fail')
  })

  it('runCommand shows a fetch error when the /run request rejects', async () => {
    const apiFetch = vi.fn(() => Promise.reject(new Error('Failed to fetch')))
    const appendLine = vi.fn()
    const { runCommand, status, runBtn } = loadRunnerFns({
      cmdValue: 'echo hello',
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch,
      appendLine,
    })

    runCommand()
    await Promise.resolve()
    await Promise.resolve()

    expect(apiFetch).toHaveBeenCalledWith(
      '/run',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    expect(appendLine).toHaveBeenLastCalledWith(
      '[connection error] Unable to reach the server. Check that it is running and try again.',
      'exit-fail',
      'tab-1',
    )
    expect(status.className).toBe('status-pill fail')
    expect(runBtn.disabled).toBe(false)
  })

  it('runCommand handles a 500 response as a friendly server error', async () => {
    const apiFetch = vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 500,
        headers: { get: () => 'application/json' },
        json: () => Promise.resolve({ error: 'backend unavailable' }),
      }),
    )
    const appendLine = vi.fn()
    const { runCommand, status, runBtn } = loadRunnerFns({
      cmdValue: 'echo hello',
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch,
      appendLine,
    })

    runCommand()
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()

    expect(appendLine).toHaveBeenLastCalledWith(
      '[server error] The server could not start the command. backend unavailable',
      'exit-fail',
      'tab-1',
    )
    expect(status.className).toBe('status-pill fail')
    expect(runBtn.disabled).toBe(false)
  })

  it('runCommand handles a 403 response as a denied command', async () => {
    const apiFetch = vi.fn(() =>
      Promise.resolve({
        status: 403,
        json: () => Promise.resolve({ error: 'not allowed' }),
      }),
    )
    const appendLine = vi.fn()
    const { runCommand, status, runBtn } = loadRunnerFns({
      cmdValue: 'echo hello',
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch,
      appendLine,
    })

    runCommand()
    await Promise.resolve()
    await Promise.resolve()

    expect(appendLine).toHaveBeenLastCalledWith('[denied] not allowed', 'denied', 'tab-1')
    expect(status.className).toBe('status-pill fail')
    expect(runBtn.disabled).toBe(false)
  })

  it('runCommand handles a 429 response as rate limited', async () => {
    const apiFetch = vi.fn(() =>
      Promise.resolve({
        status: 429,
        json: () => Promise.resolve({}),
      }),
    )
    const appendLine = vi.fn()
    const { runCommand, status, runBtn } = loadRunnerFns({
      cmdValue: 'echo hello',
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch,
      appendLine,
    })

    runCommand()
    await Promise.resolve()
    await Promise.resolve()

    expect(appendLine).toHaveBeenLastCalledWith(
      '[rate limited] Too many requests. Please wait a moment.',
      'denied',
      'tab-1',
    )
    expect(status.className).toBe('status-pill fail')
    expect(runBtn.disabled).toBe(false)
  })

  it('runCommand dismisses the mobile keyboard after a successful submit', () => {
    const dismissMobileKeyboardAfterSubmit = vi.fn()
    const apiFetch = vi.fn(() => Promise.reject(new Error('Failed to fetch')))
    const { runCommand } = loadRunnerFns({
      cmdValue: 'curl http://localhost:5001/health',
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch,
      dismissMobileKeyboardAfterSubmit,
    })

    runCommand()

    expect(dismissMobileKeyboardAfterSubmit).toHaveBeenCalled()
  })

  it('runCommand cancels and clears welcome output when the active tab owns welcome', async () => {
    const apiFetch = vi.fn(() => Promise.reject(new Error('Failed to fetch')))
    const appendLine = vi.fn()
    const welcomeOwnsTab = vi.fn(() => true)
    const { runCommand, cancelWelcome, clearTab } = loadRunnerFns({
      cmdValue: 'echo hello',
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch,
      appendLine,
      welcomeOwnsTab,
    })

    runCommand()
    await Promise.resolve()
    await Promise.resolve()

    expect(welcomeOwnsTab).toHaveBeenCalledWith('tab-1')
    expect(cancelWelcome).toHaveBeenCalledWith('tab-1')
    expect(clearTab).toHaveBeenCalledWith('tab-1')
    expect(apiFetch).toHaveBeenCalledWith(
      '/run',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })

  it('runCommand handles a synthetic clear event by clearing the tab and suppressing the exit line', async () => {
    const appendLine = vi.fn()
    const clearTab = vi.fn()
    const apiFetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        body: {
          getReader: () => {
            let done = false
            return {
              read: () => {
                if (done) return Promise.resolve({ done: true, value: undefined })
                done = true
                const payload =
                  [
                    'data: {"type":"started","run_id":"run-clear"}',
                    'data: {"type":"clear"}',
                    'data: {"type":"exit","code":0,"elapsed":0.1}',
                  ].join('\n\n') + '\n\n'
                return Promise.resolve({ done: false, value: new TextEncoder().encode(payload) })
              },
            }
          },
        },
      }),
    )
    const loaded = loadRunnerFns({
      cmdValue: 'clear',
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch,
      appendLine,
      clearTab,
    })

    loaded.runCommand()
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()

    expect(clearTab).toHaveBeenCalledWith('tab-1')
    expect(appendLine).not.toHaveBeenCalledWith(
      expect.stringContaining('[process exited with code 0'),
      'exit-ok',
      'tab-1',
    )
    expect(loaded.status.className).toBe('status-pill ok')
  })

  it('runCommand appends a count-aware preview truncation notice on exit', async () => {
    const appendLine = vi.fn()
    const apiFetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        body: {
          getReader: () => {
            let done = false
            return {
              read: () => {
                if (done) return Promise.resolve({ done: true, value: undefined })
                done = true
                const payload =
                  [
                    'data: {"type":"started","run_id":"run-man"}',
                    'data: {"type":"output","text":"line 1"}',
                    'data: {"type":"exit","code":0,"elapsed":0.1,"preview_truncated":true,"output_line_count":5104,"full_output_available":true}',
                  ].join('\n\n') + '\n\n'
                return Promise.resolve({ done: false, value: new TextEncoder().encode(payload) })
              },
            }
          },
        },
      }),
    )
    const loaded = loadRunnerFns({
      cmdValue: 'man curl',
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      appConfig: { max_output_lines: 5000 },
      apiFetch,
      appendLine,
    })

    loaded.runCommand()
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()

    expect(appendLine).toHaveBeenCalledWith(
      "[preview truncated — only the last 5000 lines are shown here, but the full output had 5104 lines. To view the full output, use either permalink button now; after another command, use this command's history permalink]",
      'notice',
      'tab-1',
    )
    expect(loaded.tabs[0].historyRunId).toBe('run-man')
  })

  it('runCommand preserves output classes from streamed events', async () => {
    const appendLine = vi.fn()
    const apiFetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        body: {
          getReader: () => {
            let done = false
            return {
              read: () => {
                if (done) return Promise.resolve({ done: true, value: undefined })
                done = true
                const payload =
                  [
                    'data: {"type":"started","run_id":"run-faq"}',
                    'data: {"type":"output","text":"Q  Example question\\n","cls":"fake-faq-q"}',
                    'data: {"type":"output","text":"A  Example answer\\n","cls":"fake-faq-a"}',
                    'data: {"type":"exit","code":0,"elapsed":0.1}',
                  ].join('\n\n') + '\n\n'
                return Promise.resolve({ done: false, value: new TextEncoder().encode(payload) })
              },
            }
          },
        },
      }),
    )
    const loaded = loadRunnerFns({
      cmdValue: 'faq',
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch,
      appendLine,
    })

    loaded.runCommand()
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()

    expect(appendLine).toHaveBeenCalledWith('Q  Example question', 'fake-faq-q', 'tab-1')
    expect(appendLine).toHaveBeenCalledWith('A  Example answer', 'fake-faq-a', 'tab-1')
  })

  it('doKill shows a notice when the kill request fails', async () => {
    const apiFetch = vi.fn(() => Promise.reject(new Error('Failed to fetch')))
    const appendLine = vi.fn()
    const { doKill, showToast } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'running', runId: 'run-123', killed: false, pendingKill: false }],
      apiFetch,
      appendLine,
    })

    doKill('tab-1')
    await Promise.resolve()
    await Promise.resolve()

    expect(showToast).toHaveBeenCalledWith(
      'Failed to send kill request; command may still be running',
    )
    expect(appendLine).toHaveBeenCalledWith(
      '[kill request failed] Unable to reach the server. Check that it is running and try again.',
      'notice',
      'tab-1',
    )
  })
})

describe('submitCommand return contract', () => {
  it('returns true on empty input (blank Enter)', () => {
    const { submitCommand } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
    })
    expect(submitCommand('   ')).toBe(true)
  })

  it("returns 'settle' on empty input during active welcome", () => {
    const { submitCommand } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      welcomeActive: true,
      welcomeOwnsTab: () => true,
    })
    expect(submitCommand('')).toBe('settle')
  })

  it('returns false when shell operators are rejected', () => {
    const { submitCommand } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch: vi.fn(() => Promise.resolve()),
    })
    expect(submitCommand('ping x | cat /etc/passwd')).toBe(false)
  })

  it('returns false when /tmp path is denied', () => {
    const { submitCommand } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch: vi.fn(() => Promise.resolve()),
    })
    expect(submitCommand('cat /tmp/secret')).toBe(false)
  })

  it('returns true when a valid command is submitted', () => {
    const { submitCommand } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      apiFetch: vi.fn(() => Promise.resolve()),
    })
    expect(submitCommand('ping darklab.sh')).toBe(true)
  })

  it('submitComposerCommand clears the input and dismisses the keyboard after submit', () => {
    const dismissMobileKeyboardAfterSubmit = vi.fn()
    const { submitComposerCommand, cmdInput } = loadRunnerFns({
      cmdValue: 'ping darklab.sh',
      apiFetch: vi.fn(() => Promise.resolve()),
      dismissMobileKeyboardAfterSubmit,
    })

    submitComposerCommand('ping darklab.sh', { dismissKeyboard: true })

    expect(cmdInput.value).toBe('')
    expect(cmdInput.focus).toHaveBeenCalled()
    expect(dismissMobileKeyboardAfterSubmit).toHaveBeenCalled()
  })

  it('submitComposerCommand can skip refocusing after a mobile submit', () => {
    const dismissMobileKeyboardAfterSubmit = vi.fn()
    const { submitComposerCommand, cmdInput } = loadRunnerFns({
      cmdValue: 'ping darklab.sh',
      apiFetch: vi.fn(() => Promise.resolve()),
      dismissMobileKeyboardAfterSubmit,
    })

    submitComposerCommand('ping darklab.sh', { dismissKeyboard: true, focusAfterSubmit: false })

    expect(cmdInput.value).toBe('')
    expect(cmdInput.focus).not.toHaveBeenCalled()
    expect(dismissMobileKeyboardAfterSubmit).toHaveBeenCalled()
  })

  it('submitVisibleComposerCommand reads the visible composer value and submits it', () => {
    const apiFetch = vi.fn(() => Promise.resolve())
    const { submitVisibleComposerCommand } = loadRunnerFns({
      apiFetch,
      getComposerValue: () => 'curl darklab.sh',
    })

    submitVisibleComposerCommand({ dismissKeyboard: true, focusAfterSubmit: false })

    expect(apiFetch).toHaveBeenCalledWith(
      '/run',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: 'curl darklab.sh' }),
      }),
    )
  })

  it('submitVisibleComposerCommand can submit an explicit raw command', () => {
    const apiFetch = vi.fn(() => Promise.resolve())
    const { submitVisibleComposerCommand } = loadRunnerFns({
      apiFetch,
      getComposerValue: () => 'ignored',
    })

    submitVisibleComposerCommand({
      rawCmd: 'curl explicit.sh',
      dismissKeyboard: true,
      focusAfterSubmit: false,
    })

    expect(apiFetch).toHaveBeenCalledWith(
      '/run',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: 'curl explicit.sh' }),
      }),
    )
  })

  it('interruptPromptLine refocuses the visible mobile composer when present', () => {
    const visibleInput = { focus: vi.fn() }
    const { interruptPromptLine, cmdInput } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      getVisibleComposerInput: () => visibleInput,
    })

    expect(interruptPromptLine('tab-1')).toBe(true)
    expect(visibleInput.focus).toHaveBeenCalled()
    expect(cmdInput.focus).not.toHaveBeenCalled()
  })

  it('returns false when the tab limit is reached', () => {
    const { submitCommand } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'running', runId: null, killed: false, pendingKill: false }],
      apiFetch: vi.fn(() => Promise.resolve()),
      createTab: () => null, // signals tab limit reached
    })
    expect(submitCommand('ping darklab.sh')).toBe(false)
  })
})

// ── _seedLocalStorageStarsToServer ────────────────────────────────────────────

function loadSeedFns({
  localStarred = [],
  apiFetch = vi.fn(() => Promise.resolve({ ok: true })),
  loadStarredFromServer = vi.fn(() => Promise.resolve()),
} = {}) {
  const storage = new MemoryStorage()
  if (localStarred.length) {
    storage.setItem('starred', JSON.stringify(localStarred))
  }
  const fns = fromDomScript(
    'app/static/js/runner.js',
    { localStorage: storage, apiFetch, loadStarredFromServer },
    '_seedLocalStorageStarsToServer',
  )
  return { ...fns, _storage: storage, apiFetch, loadStarredFromServer }
}

describe('_seedLocalStorageStarsToServer', () => {
  it('skips the seed and clears the key when localStorage has no starred entry', async () => {
    const { _seedLocalStorageStarsToServer, apiFetch, loadStarredFromServer, _storage } =
      loadSeedFns()

    await _seedLocalStorageStarsToServer()

    expect(apiFetch).not.toHaveBeenCalled()
    expect(loadStarredFromServer).not.toHaveBeenCalled()
    expect(_storage.getItem('starred')).toBeNull()
  })

  it('skips the seed and clears the stale empty array', async () => {
    // Empty arrays are the typical legacy leftover from before stars went
    // server-side; they must be removed so they do not linger in localStorage.
    const { _seedLocalStorageStarsToServer, apiFetch, _storage } = loadSeedFns({ localStarred: [] })

    await _seedLocalStorageStarsToServer()

    expect(apiFetch).not.toHaveBeenCalled()
    expect(_storage.getItem('starred')).toBeNull()
  })

  it('POSTs each starred command to /session/starred', async () => {
    const { _seedLocalStorageStarsToServer, apiFetch } = loadSeedFns({
      localStarred: ['ping darklab.sh', 'dig darklab.sh A'],
    })

    await _seedLocalStorageStarsToServer()

    expect(apiFetch).toHaveBeenCalledTimes(2)
    expect(apiFetch).toHaveBeenCalledWith('/session/starred', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'ping darklab.sh' }),
    })
    expect(apiFetch).toHaveBeenCalledWith('/session/starred', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'dig darklab.sh A' }),
    })
  })

  it('removes the starred key from localStorage after seeding', async () => {
    const { _seedLocalStorageStarsToServer, _storage } = loadSeedFns({
      localStarred: ['hostname'],
    })

    await _seedLocalStorageStarsToServer()

    expect(_storage.getItem('starred')).toBeNull()
  })

  it('calls loadStarredFromServer after seeding', async () => {
    const { _seedLocalStorageStarsToServer, loadStarredFromServer } = loadSeedFns({
      localStarred: ['hostname'],
    })

    await _seedLocalStorageStarsToServer()

    expect(loadStarredFromServer).toHaveBeenCalledTimes(1)
  })

  it('handles invalid localStorage JSON as empty and clears the key', async () => {
    const storage = new MemoryStorage()
    storage.setItem('starred', 'not-json{{{')
    const apiFetch = vi.fn()
    const fns = fromDomScript(
      'app/static/js/runner.js',
      { localStorage: storage, apiFetch, loadStarredFromServer: vi.fn() },
      '_seedLocalStorageStarsToServer',
    )

    await fns._seedLocalStorageStarsToServer()

    expect(apiFetch).not.toHaveBeenCalled()
    expect(storage.getItem('starred')).toBeNull()
  })

  it('retains failed commands in localStorage and removes only successful ones', async () => {
    const apiFetch = vi.fn()
      .mockResolvedValueOnce({ ok: true })   // ping succeeds
      .mockResolvedValueOnce({ ok: false, status: 500 }) // dig fails
    const { _seedLocalStorageStarsToServer, _storage } = loadSeedFns({
      localStarred: ['ping darklab.sh', 'dig darklab.sh A'],
      apiFetch,
    })

    await _seedLocalStorageStarsToServer()

    const remaining = JSON.parse(_storage.getItem('starred'))
    expect(remaining).toEqual(['dig darklab.sh A'])
  })

  it('retains all commands when every POST fails', async () => {
    const apiFetch = vi.fn().mockResolvedValue({ ok: false, status: 503 })
    const { _seedLocalStorageStarsToServer, _storage } = loadSeedFns({
      localStarred: ['ping darklab.sh', 'dig darklab.sh A'],
      apiFetch,
    })

    await _seedLocalStorageStarsToServer()

    const remaining = JSON.parse(_storage.getItem('starred'))
    expect(remaining).toHaveLength(2)
  })

  it('removes the key only when all POSTs succeed', async () => {
    const apiFetch = vi.fn().mockResolvedValue({ ok: true })
    const { _seedLocalStorageStarsToServer, _storage } = loadSeedFns({
      localStarred: ['ping darklab.sh', 'dig darklab.sh A'],
      apiFetch,
    })

    await _seedLocalStorageStarsToServer()

    expect(_storage.getItem('starred')).toBeNull()
  })
})

// ── _sessionTokenSet verify-failure behavior ──────────────────────────────────

function loadTokenSetFns({ apiFetch = vi.fn() } = {}) {
  const storage = new MemoryStorage()
  storage.setItem('session_id', 'uuid-base-session')
  const appendLine = vi.fn()
  const setStatus = vi.fn()
  const appendPromptNewline = vi.fn()
  const fns = fromDomScript(
    'app/static/js/runner.js',
    {
      localStorage: storage,
      apiFetch,
      appendLine,
      setStatus,
      appendPromptNewline,
      updateSessionId: vi.fn(),
      logClientError: vi.fn(),
      reloadSessionHistory: vi.fn(() => Promise.resolve()),
      _seedLocalStorageStarsToServer: vi.fn(() => Promise.resolve()),
      // session.js globals needed by the non-verify code paths in _sessionTokenSet
      SESSION_ID: 'uuid-base-session',
      maskSessionToken: (t) => (t ? t.slice(0, 8) + '••••' : '(none)'),
    },
    '_sessionTokenSet',
  )
  return { ...fns, appendLine, setStatus, appendPromptNewline, _storage: storage }
}

describe('_sessionTokenSet verify failure behavior', () => {
  it('blocks token activation when /session/token/verify returns non-OK', async () => {
    const apiFetch = vi.fn().mockResolvedValue({ ok: false, status: 500 })
    const { _sessionTokenSet, appendLine, _storage } = loadTokenSetFns({ apiFetch })

    await _sessionTokenSet('tok_abcd1234efgh5678ijkl9012mnop3456', 'tab-1')

    expect(appendLine).toHaveBeenCalledWith(
      expect.stringContaining('token verification failed'),
      'exit-fail',
      'tab-1',
    )
    expect(_storage.getItem('session_token')).toBeNull()
  })

  it('blocks token activation when /session/token/verify throws a network error', async () => {
    const apiFetch = vi.fn().mockRejectedValue(new Error('Failed to fetch'))
    const { _sessionTokenSet, appendLine, _storage } = loadTokenSetFns({ apiFetch })

    await _sessionTokenSet('tok_abcd1234efgh5678ijkl9012mnop3456', 'tab-1')

    expect(appendLine).toHaveBeenCalledWith(
      expect.stringContaining('server is unreachable'),
      'exit-fail',
      'tab-1',
    )
    expect(_storage.getItem('session_token')).toBeNull()
  })

  it('blocks token activation when verify returns ok but exists is false', async () => {
    const apiFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ok: true, exists: false }),
    })
    const { _sessionTokenSet, appendLine, _storage } = loadTokenSetFns({ apiFetch })

    await _sessionTokenSet('tok_abcd1234efgh5678ijkl9012mnop3456', 'tab-1')

    expect(appendLine).toHaveBeenCalledWith(
      expect.stringContaining('not issued by this server'),
      'exit-fail',
      'tab-1',
    )
    expect(_storage.getItem('session_token')).toBeNull()
  })

  it('skips verify entirely for UUID-format tokens', async () => {
    // UUIDs are anonymous sessions — no tok_ prefix, so /session/token/verify
    // must not be called regardless of how apiFetch is configured.
    const apiFetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ runs: [] }) })
    const { _sessionTokenSet } = loadTokenSetFns({ apiFetch })

    await _sessionTokenSet('a1b2c3d4-1234-4abc-8def-1234567890ab', 'tab-1')

    const verifyCalls = apiFetch.mock.calls.filter(([url]) => url === '/session/token/verify')
    expect(verifyCalls).toHaveLength(0)
  })

  it('defers the success copy until after the migration answer is accepted', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/session/token/verify') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ exists: true }),
        })
      }
      if (url === '/session/run-count') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ count: 1 }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const { _sessionTokenSet, appendLine, _storage } = loadTokenSetFns({ apiFetch })

    await _sessionTokenSet('tok_abcd1234efgh5678ijkl9012mnop3456', 'tab-1')

    expect(appendLine).toHaveBeenCalledWith(
      'you have 1 run(s) in your current session. migrate history to this session token?',
      '',
      'tab-1',
    )
    expect(appendLine).not.toHaveBeenCalledWith(
      expect.stringContaining('session token set:'),
      '',
      'tab-1',
    )
    expect(_storage.getItem('session_token')).toBeNull()
  })
})

describe('session-token clear', () => {
  it('opens a terminal yes/no confirmation before clearing the token', async () => {
    const appendLine = vi.fn()
    const setComposerPromptMode = vi.fn()
    const { submitCommand, status } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      appendLine,
      setComposerPromptMode,
      localStorageEntries: { session_token: 'tok_abcd1234efgh5678ijkl9012mnop3456' },
    })

    await submitCommand('session-token clear')

    expect(appendLine).toHaveBeenNthCalledWith(1, 'session-token clear', 'prompt-echo', 'tab-1')
    expect(appendLine).toHaveBeenNthCalledWith(
      2,
      'warning: clearing the active session token removes it from this browser',
      'notice',
      'tab-1',
    )
    expect(appendLine).toHaveBeenNthCalledWith(
      3,
      "run 'session-token copy' first if you want to save the current token before clearing it",
      'notice',
      'tab-1',
    )
    expect(appendLine).toHaveBeenNthCalledWith(
      4,
      'clear the active session token and revert to an anonymous session?',
      '',
      'tab-1',
    )
    expect(setComposerPromptMode).toHaveBeenCalledWith('confirm')
    expect(status.className).toBe('status-pill idle')
  })

  it('clears the token only after answering yes to the terminal confirmation', async () => {
    const appendLine = vi.fn()
    const setComposerPromptMode = vi.fn()
    const updateSessionId = vi.fn()
    const reloadSessionHistory = vi.fn(() => Promise.resolve())
    const hydrateCmdHistory = vi.fn()
    const { submitCommand, status, storage, tabs } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'fail', exitCode: 2, runId: null, killed: false, pendingKill: false }],
      appendLine,
      setComposerPromptMode,
      updateSessionId,
      reloadSessionHistory,
      hydrateCmdHistory,
      sessionId: 'session-old',
      localStorageEntries: {
        session_token: 'tok_abcd1234efgh5678ijkl9012mnop3456',
        session_id: 'uuid-base-session',
      },
    })

    await submitCommand('session-token clear')
    await submitCommand('yes')
    await vi.waitFor(() => expect(storage.getItem('session_token')).toBeNull())

    expect(updateSessionId).toHaveBeenCalledWith('uuid-base-session')
    expect(hydrateCmdHistory).toHaveBeenCalledWith([])
    expect(reloadSessionHistory).toHaveBeenCalled()
    expect(appendLine).toHaveBeenCalledWith('yes', 'prompt-echo', 'tab-1')
    expect(appendLine).toHaveBeenCalledWith(
      'session token cleared — reverted to anonymous session (uuid-bas••••••••)',
      '',
      'tab-1',
    )
    expect(appendLine).toHaveBeenCalledWith(
      'your session token data remains in the server database',
      '',
      'tab-1',
    )
    expect(setComposerPromptMode).toHaveBeenLastCalledWith(null)
    await vi.waitFor(() => expect(tabs[0].st).toBe('ok'))
    expect(status.className).toBe('status-pill ok')
    expect(tabs[0].exitCode).toBe(0)
  })

  it('leaves the session token untouched when the user answers no', async () => {
    const appendLine = vi.fn()
    const setComposerPromptMode = vi.fn()
    const updateSessionId = vi.fn()
    const { submitCommand, status, storage } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      appendLine,
      setComposerPromptMode,
      updateSessionId,
      localStorageEntries: { session_token: 'tok_abcd1234efgh5678ijkl9012mnop3456' },
    })

    await submitCommand('session-token clear')
    await submitCommand('no')
    await vi.waitFor(() =>
      expect(appendLine).toHaveBeenCalledWith('Session token clear canceled.', '', 'tab-1'),
    )

    expect(storage.getItem('session_token')).toBe('tok_abcd1234efgh5678ijkl9012mnop3456')
    expect(updateSessionId).not.toHaveBeenCalled()
    expect(setComposerPromptMode).toHaveBeenLastCalledWith(null)
    expect(status.className).toBe('status-pill ok')
  })

  it('treats Ctrl+C as no and cancels the clear confirmation', async () => {
    const appendLine = vi.fn()
    const setComposerPromptMode = vi.fn()
    const updateSessionId = vi.fn()
    const { submitCommand, cancelPendingTerminalConfirm, status, storage } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      appendLine,
      setComposerPromptMode,
      updateSessionId,
      localStorageEntries: { session_token: 'tok_abcd1234efgh5678ijkl9012mnop3456' },
    })

    await submitCommand('session-token clear')
    expect(cancelPendingTerminalConfirm()).toBe(true)
    await vi.waitFor(() =>
      expect(appendLine).toHaveBeenCalledWith('Session token clear canceled.', '', 'tab-1'),
    )

    expect(storage.getItem('session_token')).toBe('tok_abcd1234efgh5678ijkl9012mnop3456')
    expect(updateSessionId).not.toHaveBeenCalled()
    expect(setComposerPromptMode).toHaveBeenLastCalledWith(null)
    expect(status.className).toBe('status-pill ok')
  })
})

describe('session-token copy', () => {
  it('copies the active token to the clipboard from the terminal', async () => {
    const appendLine = vi.fn()
    const copyTextToClipboard = vi.fn(() => Promise.resolve())
    const addToRecentPreview = vi.fn()
    const { submitCommand, status } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      appendLine,
      copyTextToClipboard,
      addToRecentPreview,
      localStorageEntries: { session_token: 'tok_abcd1234efgh5678ijkl9012mnop3456' },
    })

    await submitCommand('session-token copy')

    expect(copyTextToClipboard).toHaveBeenCalledWith('tok_abcd1234efgh5678ijkl9012mnop3456')
    await vi.waitFor(() =>
      expect(appendLine).toHaveBeenCalledWith(
        'session token copied to clipboard: tok_abcd••••',
        '',
        'tab-1',
      ),
    )
    expect(addToRecentPreview).toHaveBeenCalledWith('session-token copy')
    expect(status.className).toBe('status-pill ok')
  })

  it('shows an error when clipboard copy fails', async () => {
    const appendLine = vi.fn()
    const copyTextToClipboard = vi.fn(() => Promise.reject(new Error('Clipboard unavailable')))
    const { submitCommand, status } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      appendLine,
      copyTextToClipboard,
      localStorageEntries: { session_token: 'tok_abcd1234efgh5678ijkl9012mnop3456' },
    })

    await submitCommand('session-token copy')
    await vi.waitFor(() =>
      expect(appendLine).toHaveBeenCalledWith(
        '[error] failed to copy the session token to clipboard',
        'exit-fail',
        'tab-1',
      ),
    )

    expect(status.className).toBe('status-pill fail')
  })
})

describe('session-token pipe helpers', () => {
  it('filters client-side session-token output through the built-in pipe helpers', async () => {
    const appendLine = vi.fn()
    const apiFetch = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({
        token: 'tok_abcd1234efgh5678ijkl9012mnop3456',
        created: '2026-04-22T12:00:00',
      }),
    }))
    const { submitCommand } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      appendLine,
      apiFetch,
      localStorageEntries: { session_token: 'tok_abcd1234efgh5678ijkl9012mnop3456' },
    })

    await submitCommand('session-token list | grep status')
    await vi.waitFor(() =>
      expect(appendLine).toHaveBeenCalledWith('status          active', 'fake-kv', 'tab-1'),
    )

    expect(appendLine).toHaveBeenCalledWith(
      'session-token list | grep status',
      'prompt-echo',
      'tab-1',
    )
    expect(appendLine).not.toHaveBeenCalledWith(
      expect.stringContaining('session token'),
      expect.anything(),
      expect.anything(),
    )
  })
})

describe('session-token set pending prompt', () => {
  it('prints success only after a skipped migration answer and does not store yes/no in command history', async () => {
    const addToHistory = vi.fn()
    const addToRecentPreview = vi.fn()
    const appendLine = vi.fn()
    const setComposerPromptMode = vi.fn()
    const updateSessionId = vi.fn()
    const reloadSessionHistory = vi.fn(() => Promise.resolve())
    const { submitCommand, storage } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      appendLine,
      addToHistory,
      addToRecentPreview,
      setComposerPromptMode,
      updateSessionId,
      reloadSessionHistory,
      sessionId: 'uuid-base-session',
      localStorageEntries: { session_id: 'uuid-base-session' },
      apiFetch: vi.fn((url) => {
        if (url === '/session/token/verify') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ exists: true }) })
        }
        if (url === '/session/run-count') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ count: 1 }) })
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
      }),
    })

    await submitCommand('session-token set tok_abcd1234efgh5678ijkl9012mnop3456')
    await vi.waitFor(() =>
      expect(appendLine).toHaveBeenCalledWith(
        'you have 1 run(s) in your current session. migrate history to this session token?',
        '',
        'tab-1',
      ),
    )

    expect(appendLine).toHaveBeenNthCalledWith(
      1,
      'session-token set tok_abcd1234efgh5678ijkl9012mnop3456',
      'prompt-echo',
      'tab-1',
    )
    expect(appendLine).toHaveBeenNthCalledWith(
      2,
      'you have 1 run(s) in your current session. migrate history to this session token?',
      '',
      'tab-1',
    )
    expect(appendLine).not.toHaveBeenCalledWith(
      expect.stringContaining('session token set:'),
      '',
      'tab-1',
    )
    expect(addToHistory).toHaveBeenCalledTimes(1)
    expect(addToHistory).toHaveBeenCalledWith('session-token set tok_abcd••••')
    expect(setComposerPromptMode).toHaveBeenCalledWith('confirm')

    await submitCommand('no')
    await vi.waitFor(() =>
      expect(storage.getItem('session_token')).toBe('tok_abcd1234efgh5678ijkl9012mnop3456'),
    )
    await vi.waitFor(() =>
      expect(appendLine).toHaveBeenCalledWith('session token set: tok_abcd••••', '', 'tab-1'),
    )

    expect(storage.getItem('session_token')).toBe('tok_abcd1234efgh5678ijkl9012mnop3456')
    expect(updateSessionId).toHaveBeenCalledWith('tok_abcd1234efgh5678ijkl9012mnop3456')
    expect(reloadSessionHistory).toHaveBeenCalled()
    expect(addToHistory).toHaveBeenCalledTimes(1)
    expect(addToRecentPreview).toHaveBeenCalledWith('session-token set tok_abcd••••')
    expect(appendLine).toHaveBeenCalledWith('no', 'prompt-echo', 'tab-1')
    expect(appendLine).toHaveBeenCalledWith('session token set: tok_abcd••••', '', 'tab-1')
    expect(appendLine).toHaveBeenCalledWith(
      'reload other tabs to apply the new session token',
      '',
      'tab-1',
    )
    expect(appendLine).toHaveBeenCalledWith('History migration skipped.', '', 'tab-1')
    expect(setComposerPromptMode).toHaveBeenLastCalledWith(null)
  })

  it('keeps the pending prompt open on invalid answers', async () => {
    const addToHistory = vi.fn()
    const appendLine = vi.fn()
    const setComposerPromptMode = vi.fn()
    const { submitCommand, storage } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      appendLine,
      addToHistory,
      setComposerPromptMode,
      localStorageEntries: { session_id: 'uuid-base-session' },
      apiFetch: vi.fn((url) => {
        if (url === '/session/token/verify') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ exists: true }) })
        }
        if (url === '/session/run-count') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ count: 1 }) })
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
      }),
    })

    await submitCommand('session-token set tok_abcd1234efgh5678ijkl9012mnop3456')
    await vi.waitFor(() =>
      expect(appendLine).toHaveBeenCalledWith(
        'you have 1 run(s) in your current session. migrate history to this session token?',
        '',
        'tab-1',
      ),
    )
    await submitCommand('maybe')

    expect(appendLine).toHaveBeenCalledWith('maybe', 'prompt-echo', 'tab-1')
    expect(appendLine).toHaveBeenCalledWith('please answer yes or no', 'notice', 'tab-1')
    expect(storage.getItem('session_token')).toBeNull()
    expect(addToHistory).toHaveBeenCalledTimes(1)
    expect(setComposerPromptMode).toHaveBeenCalledTimes(1)
    expect(setComposerPromptMode).toHaveBeenCalledWith('confirm')
  })

  it('treats Ctrl+C as cancel and aborts the session-token set flow', async () => {
    const addToHistory = vi.fn()
    const appendLine = vi.fn()
    const setComposerPromptMode = vi.fn()
    const updateSessionId = vi.fn()
    const reloadSessionHistory = vi.fn(() => Promise.resolve())
    const { submitCommand, cancelPendingTerminalConfirm, storage } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      appendLine,
      addToHistory,
      setComposerPromptMode,
      updateSessionId,
      reloadSessionHistory,
      sessionId: 'uuid-base-session',
      localStorageEntries: { session_id: 'uuid-base-session' },
      apiFetch: vi.fn((url) => {
        if (url === '/session/token/verify') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ exists: true }) })
        }
        if (url === '/session/run-count') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ count: 1 }) })
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
      }),
    })

    await submitCommand('session-token set tok_abcd1234efgh5678ijkl9012mnop3456')
    await vi.waitFor(() =>
      expect(appendLine).toHaveBeenCalledWith(
        'you have 1 run(s) in your current session. migrate history to this session token?',
        '',
        'tab-1',
      ),
    )
    expect(cancelPendingTerminalConfirm()).toBe(true)
    await vi.waitFor(() =>
      expect(appendLine).toHaveBeenCalledWith('Session token set canceled.', '', 'tab-1'),
    )

    expect(storage.getItem('session_token')).toBeNull()
    expect(updateSessionId).not.toHaveBeenCalled()
    expect(reloadSessionHistory).not.toHaveBeenCalled()
    expect(setComposerPromptMode).toHaveBeenLastCalledWith(null)
    expect(addToHistory).toHaveBeenCalledTimes(1)
  })

  it('uses the uncapped session run-count endpoint for migration prompts', async () => {
    const appendLine = vi.fn()
    const { submitCommand } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'idle', runId: null, killed: false, pendingKill: false }],
      appendLine,
      localStorageEntries: { session_id: 'uuid-base-session' },
      apiFetch: vi.fn((url) => {
        if (url === '/session/token/verify') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ exists: true }) })
        }
        if (url === '/session/run-count') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ count: 73 }) })
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
      }),
    })

    await submitCommand('session-token set tok_abcd1234efgh5678ijkl9012mnop3456')

    await vi.waitFor(() =>
      expect(appendLine).toHaveBeenCalledWith(
        'you have 73 run(s) in your current session. migrate history to this session token?',
        '',
        'tab-1',
      ),
    )
  })
})

// ── _maybeNotify ──────────────────────────────────────────────────────────────

describe('_maybeNotify', () => {
  function makeNotificationClass() {
    const instances = []
    class MockNotification {
      constructor(title, options) {
        this.title = title
        this.body = options?.body
        instances.push(this)
      }

      static get permission() {
        return MockNotification._permission
      }
    }
    MockNotification._permission = 'granted'
    MockNotification.instances = instances
    return MockNotification
  }

  it('does nothing when pref is off', () => {
    const MockNotification = makeNotificationClass()
    const { _maybeNotify } = loadRunnerFns({
      getRunNotifyPreference: () => 'off',
      Notification: MockNotification,
    })
    _maybeNotify('nmap -sV ip.darklab.sh', 0, '12.3s')
    expect(MockNotification.instances).toHaveLength(0)
  })

  it('does nothing when Notification is not available', () => {
    const { _maybeNotify } = loadRunnerFns({
      getRunNotifyPreference: () => 'on',
      // Notification intentionally omitted — simulates unsupported browser
    })
    // Should not throw
    expect(() => _maybeNotify('ping darklab.sh', 0, '1.0s')).not.toThrow()
  })

  it('does nothing when permission is not granted', () => {
    const MockNotification = makeNotificationClass()
    MockNotification._permission = 'default'
    const { _maybeNotify } = loadRunnerFns({
      getRunNotifyPreference: () => 'on',
      Notification: MockNotification,
    })
    _maybeNotify('nmap -sV ip.darklab.sh', 0, '12.3s')
    expect(MockNotification.instances).toHaveLength(0)
  })

  it('fires with command root as title and exit code + elapsed in body for exit 0', () => {
    const MockNotification = makeNotificationClass()
    const { _maybeNotify } = loadRunnerFns({
      getRunNotifyPreference: () => 'on',
      Notification: MockNotification,
    })
    _maybeNotify('nmap -sV ip.darklab.sh', 0, '12.3s')
    expect(MockNotification.instances).toHaveLength(1)
    expect(MockNotification.instances[0].title).toBe('$ nmap')
    expect(MockNotification.instances[0].body).toBe('exit 0 in 12.3s')
  })

  it('fires with non-zero exit code in body for failed run', () => {
    const MockNotification = makeNotificationClass()
    const { _maybeNotify } = loadRunnerFns({
      getRunNotifyPreference: () => 'on',
      Notification: MockNotification,
    })
    _maybeNotify('curl https://darklab.sh', 6, '3.0s')
    expect(MockNotification.instances).toHaveLength(1)
    expect(MockNotification.instances[0].body).toBe('exit 6 in 3.0s')
  })

  it('fires with killed status and elapsed in body when run is killed', () => {
    const MockNotification = makeNotificationClass()
    const { _maybeNotify } = loadRunnerFns({
      getRunNotifyPreference: () => 'on',
      Notification: MockNotification,
    })
    _maybeNotify('nmap -p- ip.darklab.sh', 'killed', '4.2s')
    expect(MockNotification.instances).toHaveLength(1)
    expect(MockNotification.instances[0].title).toBe('$ nmap')
    expect(MockNotification.instances[0].body).toBe('killed after 4.2s')
  })

  it('shows only the command root in the title, not arguments', () => {
    const MockNotification = makeNotificationClass()
    const { _maybeNotify } = loadRunnerFns({
      getRunNotifyPreference: () => 'on',
      Notification: MockNotification,
    })
    // Arguments may contain bearer tokens, API keys, or sensitive targets.
    _maybeNotify('curl -H "Authorization: Bearer secret" https://api.example.com', 0, '1.0s')
    expect(MockNotification.instances[0].title).toBe('$ curl')
  })
})
