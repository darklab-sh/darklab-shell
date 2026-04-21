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

  it('rejects unsupported shell operator forms', () => {
    expect(_isSyntheticGrepCommand('ping darklab.sh | cat')).toBe(false)
    expect(_isSyntheticGrepCommand('ping darklab.sh | grep -n ttl')).toBe(false)
    expect(_isSyntheticGrepCommand('ping darklab.sh | grep ttl file.txt')).toBe(false)
    expect(_isSyntheticGrepCommand('ping darklab.sh || grep ttl')).toBe(false)
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
  dismissMobileKeyboardAfterSubmit = () => {},
  maybeMountDeferredPrompt = vi.fn(),
  restoreHistoryRunIntoTab = vi.fn(() => Promise.resolve('tab-1')),
  getRunNotifyPreference: getRunNotifyPreferenceOverride = () => 'off',
  Notification: NotificationOverride = undefined,
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
            <input id="mobile-cmd" />
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
      createTab,
      clearTab,
      cancelWelcome,
      welcomeOwnsTab,
      requestWelcomeSettle: () => {},
      refreshHistoryPanel: () => {},
      showToast,
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
    runCommand,
    restoreActiveRunsAfterReload,
    pollActiveRunsAfterReload,
    syncActiveRunTimer,
    _getPendingKillTabId: () => pendingKillTabId,
  }`,
    'setTabs(tabs); setActiveTabId(activeTabId);',
  )

  return {
    ...fns,
    tabs: normalizedTabs,
    cmdInput,
    runBtn,
    status,
    setTabLabel,
    clearTab,
    cancelWelcome,
    showToast,
    interruptPromptLine: fns.interruptPromptLine,
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

    expect(createTab).toHaveBeenCalledWith('ping darklab.sh')
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

  it('adds successful commands to the preview recents but not failed commands', async () => {
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
