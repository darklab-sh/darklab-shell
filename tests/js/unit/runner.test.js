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
  apiFetch = () => Promise.resolve(),
  createTab = () => 'tab-2',
  addToHistory = () => {},
  appendLine = () => {},
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
  const clearTab = vi.fn()
  const cancelWelcome = vi.fn()

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
    APP_CONFIG: {},
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
    refreshHistoryPanel: () => {},
    showToast: () => {},
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
    expect(appendLine).toHaveBeenNthCalledWith(1, '\n$ ping google.com | cat /etc/passwd\n', '')
    expect(appendLine).toHaveBeenNthCalledWith(2, '[denied] Shell operators (&&, |, ;, >, etc.) are not permitted.', 'denied')
    expect(status.className).toBe('status-pill fail')
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
    expect(appendLine).toHaveBeenNthCalledWith(1, '\n$ curl /tmp/file\n', '')
    expect(appendLine).toHaveBeenNthCalledWith(2, '[denied] Access to /data and /tmp is not permitted.', 'denied')
    expect(status.className).toBe('status-pill fail')
  })
})
