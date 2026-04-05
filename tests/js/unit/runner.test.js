import { fromScript } from './helpers/extract.js'
import { fromDomScripts } from './helpers/extract.js'

const { _formatElapsed } = fromScript(
  'app/static/js/runner.js',
  '_formatElapsed',
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

function loadRunnerFns({
  tabs = [{ id: 'tab-1', st: 'running', runId: null, killed: false, pendingKill: false }],
  activeTabId = 'tab-1',
  cmdValue = '',
  appConfig = {},
  apiFetch = () => Promise.resolve(),
  createTab = () => 'tab-2',
  addToHistory = () => {},
  appendLine = () => {},
  welcomeOwnsTab = () => false,
  clearTab: clearTabOverride = null,
  showToast: showToastOverride = null,
} = {}) {
  document.body.innerHTML = `
    <input id="cmd" />
    <button id="run-btn"></button>
    <span id="status"></span>
    <span id="run-timer"></span>
    <div id="history-panel"></div>
    <button class="tab-kill-btn" data-tab="tab-1" style="display:inline-block"></button>
    <div class="tab" data-id="tab-1"><span class="tab-status idle"></span></div>
  `
  const cmdInput = document.getElementById('cmd')
  const runBtn = document.getElementById('run-btn')
  const status = document.getElementById('status')
  const runTimer = document.getElementById('run-timer')
  const historyPanel = document.getElementById('history-panel')
  cmdInput.value = cmdValue

  const setTabLabel = vi.fn()
  const setTabStatus = vi.fn((id, nextStatus) => {
    const tab = tabs.find(t => t.id === id)
    if (tab) tab.st = nextStatus
    const dot = document.querySelector(`.tab[data-id="${id}"] .tab-status`)
    if (dot) dot.className = `tab-status ${nextStatus}`
  })
  const clearTab = clearTabOverride || vi.fn()
  const cancelWelcome = vi.fn()
  const showToast = showToastOverride || vi.fn()

  const fns = fromDomScripts([
    'app/static/js/runner.js',
  ], {
    document,
    Map,
    tabs,
    activeTabId,
    cmdInput,
    runBtn,
    status,
    runTimer,
    historyPanel,
    APP_CONFIG: appConfig,
    _welcomeActive: false,
    _welcomeDone: false,
    searchBar: document.createElement('div'),
    addToHistory,
    setTabLabel,
    setTabStatus,
    appendLine,
    apiFetch,
    createTab,
    clearTab,
    cancelWelcome,
    welcomeOwnsTab,
    refreshHistoryPanel: () => {},
    showToast,
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
  }, `{
    setStatus,
    doKill,
    runCommand,
    _getPendingKillTabId: () => pendingKillTabId,
  }`)

  return {
    ...fns,
    tabs,
    cmdInput,
    runBtn,
    status,
    setTabLabel,
    clearTab,
    cancelWelcome,
    showToast,
  }
}

describe('runner helpers', () => {
  it('setStatus maps known states to status-pill text', () => {
    const { setStatus, status } = loadRunnerFns()

    setStatus('ok')

    expect(status.className).toBe('status-pill ok')
    expect(status.textContent).toBe('EXIT 0')
  })

  it('doKill sends /kill immediately when runId is already known', () => {
    const apiFetch = vi.fn(() => Promise.resolve())
    const { doKill, tabs, runBtn, status } = loadRunnerFns({
      tabs: [{ id: 'tab-1', st: 'running', runId: 'run-123', killed: false, pendingKill: false }],
      apiFetch,
    })

    doKill('tab-1')

    expect(apiFetch).toHaveBeenCalledWith('/kill', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }))
    expect(tabs[0].runId).toBeNull()
    expect(tabs[0].killed).toBe(true)
    expect(document.querySelector('.tab-status').className).toBe('tab-status killed')
    expect(document.querySelector('.tab-kill-btn').style.display).toBe('none')
    expect(status.className).toBe('status-pill killed')
    expect(runBtn.disabled).toBe(false)
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
    expect(appendLine).toHaveBeenNthCalledWith(1, 'ping google.com | cat /etc/passwd', 'prompt-echo', undefined)
    expect(appendLine).toHaveBeenNthCalledWith(2, '[denied] Shell operators (&&, |, ;, >, etc.) are not permitted.', 'denied')
    expect(status.className).toBe('status-pill fail')
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
    expect(appendLine).toHaveBeenNthCalledWith(2, '[denied] Access to /data and /tmp is not permitted.', 'denied')
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

    expect(apiFetch).toHaveBeenCalledWith('/run', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }))
    expect(appendLine).toHaveBeenLastCalledWith('\n[connection error] Unable to reach the server. Check that it is running and try again.', 'exit-fail', 'tab-1')
    expect(status.className).toBe('status-pill fail')
    expect(runBtn.disabled).toBe(false)
  })

  it('runCommand handles a 500 response as a friendly server error', async () => {
    const apiFetch = vi.fn(() => Promise.resolve({
      ok: false,
      status: 500,
      headers: { get: () => 'application/json' },
      json: () => Promise.resolve({ error: 'backend unavailable' }),
    }))
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

    expect(appendLine).toHaveBeenLastCalledWith('[server error] The server could not start the command. backend unavailable', 'exit-fail', 'tab-1')
    expect(status.className).toBe('status-pill fail')
    expect(runBtn.disabled).toBe(false)
  })

  it('runCommand handles a 403 response as a denied command', async () => {
    const apiFetch = vi.fn(() => Promise.resolve({
      status: 403,
      json: () => Promise.resolve({ error: 'not allowed' }),
    }))
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
    const apiFetch = vi.fn(() => Promise.resolve({
      status: 429,
      json: () => Promise.resolve({}),
    }))
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

    expect(appendLine).toHaveBeenLastCalledWith('[rate limited] Too many requests. Please wait a moment.', 'denied', 'tab-1')
    expect(status.className).toBe('status-pill fail')
    expect(runBtn.disabled).toBe(false)
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
    expect(apiFetch).toHaveBeenCalledWith('/run', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }))
  })

  it('runCommand handles a synthetic clear event by clearing the tab and suppressing the exit line', async () => {
    const appendLine = vi.fn()
    const clearTab = vi.fn()
    const apiFetch = vi.fn(() => Promise.resolve({
      ok: true,
      status: 200,
      body: {
        getReader: () => {
          let done = false
          return {
            read: () => {
              if (done) return Promise.resolve({ done: true, value: undefined })
              done = true
              const payload = [
                'data: {"type":"started","run_id":"run-clear"}',
                'data: {"type":"clear"}',
                'data: {"type":"exit","code":0,"elapsed":0.1}',
              ].join('\n\n') + '\n\n'
              return Promise.resolve({ done: false, value: new TextEncoder().encode(payload) })
            },
          }
        },
      },
    }))
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
    expect(appendLine).not.toHaveBeenCalledWith(expect.stringContaining('[process exited with code 0'), 'exit-ok', 'tab-1')
    expect(loaded.status.className).toBe('status-pill ok')
  })

  it('runCommand appends a count-aware preview truncation notice on exit', async () => {
    const appendLine = vi.fn()
    const apiFetch = vi.fn(() => Promise.resolve({
      ok: true,
      status: 200,
      body: {
        getReader: () => {
          let done = false
          return {
            read: () => {
              if (done) return Promise.resolve({ done: true, value: undefined })
              done = true
              const payload = [
                'data: {"type":"started","run_id":"run-man"}',
                'data: {"type":"output","text":"line 1"}',
                'data: {"type":"exit","code":0,"elapsed":0.1,"preview_truncated":true,"output_line_count":5104,"full_output_available":true}',
              ].join('\n\n') + '\n\n'
              return Promise.resolve({ done: false, value: new TextEncoder().encode(payload) })
            },
          }
        },
      },
    }))
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
      '[preview truncated — only the last 5000 lines are shown here, but the full output had 5104 lines. Use the permalink button below or in the history panel for complete results]',
      'notice',
      'tab-1',
    )
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

    expect(showToast).toHaveBeenCalledWith('Failed to send kill request; command may still be running')
    expect(appendLine).toHaveBeenCalledWith('[kill request failed] Unable to reach the server. Check that it is running and try again.', 'notice', 'tab-1')
  })
})
