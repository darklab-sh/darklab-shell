import { vi } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

function touchPointerEvent(type, init) {
  const event = new Event(type, { bubbles: true, cancelable: true })
  Object.assign(event, init)
  return event
}

function loadTabsFns({
  maxTabs = 3,
  maxOutputLines = 100,
  apiFetch = () => Promise.resolve({ json: () => Promise.resolve({ url: '/share/abc' }) }),
  welcomeBootPending = undefined,
  clipboardWrite = () => Promise.resolve(),
  doKill = vi.fn(),
  acFiltered: acFilteredOverride = [],
  acHide: acHideOverride = () => {},
} = {}) {
  const cmdInput = document.getElementById('cmd')
  cmdInput.focus = vi.fn()
  const tabsBar = document.getElementById('tabs-bar')
  const tabsScrollLeftBtn = document.getElementById('tabs-scroll-left')
  const tabsScrollRightBtn = document.getElementById('tabs-scroll-right')
  const tabPanels = document.getElementById('tab-panels')
  const runBtn = document.getElementById('run-btn')
  const mobileComposerHost = document.getElementById('mobile-composer-host')
  const mobileComposerRow = document.getElementById('mobile-composer-row')
  const mobileCmdInput = document.getElementById('mobile-cmd')
  const newTabBtn = document.getElementById('new-tab-btn')
  const historyPanel = document.getElementById('history-panel')
  const clipboardWrites = []
  const shellPromptWrap = document.createElement('div')
  shellPromptWrap.className = 'shell-prompt-wrap'

  const navigator = {
    clipboard: {
      writeText: (text) => {
        clipboardWrites.push(text)
        return clipboardWrite(text)
      },
    },
  }

  const fns = fromDomScripts([
    'app/static/js/utils.js',
    'app/static/js/tabs.js',
  ], {
    document,
    cmdInput,
    tabsBar,
    tabsScrollLeftBtn,
    tabsScrollRightBtn,
    tabPanels,
    runBtn,
    historyPanel,
    mobileComposerHost,
    mobileComposerRow,
    mobileCmdInput,
    newTabBtn,
    resetCmdHistoryNav: () => {},
    ...(welcomeBootPending === undefined ? {} : { _welcomeBootPending: welcomeBootPending }),
    APP_CONFIG: { max_tabs: maxTabs, max_output_lines: maxOutputLines, app_name: 'darklab shell' },
    setStatus: () => {},
    clearSearch: () => {},
    confirmKill: () => {},
    doKill,
    cancelWelcome: () => {},
    apiFetch,
    location: { origin: 'https://example.test' },
    navigator,
    URL: {
      createObjectURL: () => 'blob:mock',
      revokeObjectURL: () => {},
    },
    Blob,
    ansi_up: { ansi_to_html: (s) => `<em>${s}</em>` },
    shellPromptWrap,
    setComposerValue: (val, start = null, end = null, opts = {}) => {
      cmdInput.value = String(val ?? '')
      if (opts.dispatch !== false) cmdInput.dispatchEvent(new Event('input'))
    },
    getComposerValue: () => cmdInput.value,
    isHistSearchMode: () => false,
    exitHistSearch: () => {},
    acHide: acHideOverride,
    acFiltered: acFilteredOverride,
  }, `{
    updateNewTabBtn,
    updateTabScrollButtons,
    createTab,
    activateTab,
    startTabRename,
    mountShellPrompt,
    closeTab,
    clearTab,
    setTabStatus,
    setTabLabel,
    copyTab,
    saveTab,
    exportTabHtml,
    permalinkTab,
    _getTabs: () => getTabs(),
    _getActiveTabId: () => getActiveTabId(),
    _getAcFiltered: () => acFiltered,
  }`)

  return { ...fns, clipboardWrites, newTabBtn, shellPromptWrap, doKill }
}

function loadTabsAndOutputFns({
  maxTabs = 3,
  maxOutputLines = 100,
  apiFetch = () => Promise.resolve({ json: () => Promise.resolve({ url: '/share/abc' }) }),
  clipboardWrite = () => Promise.resolve(),
} = {}) {
  const cmdInput = document.getElementById('cmd')
  cmdInput.focus = vi.fn()
  const tabsBar = document.getElementById('tabs-bar')
  const tabsScrollLeftBtn = document.getElementById('tabs-scroll-left')
  const tabsScrollRightBtn = document.getElementById('tabs-scroll-right')
  const tabPanels = document.getElementById('tab-panels')
  const runBtn = document.getElementById('run-btn')
  const mobileComposerHost = document.getElementById('mobile-composer-host')
  const mobileComposerRow = document.getElementById('mobile-composer-row')
  const newTabBtn = document.getElementById('new-tab-btn')
  const historyPanel = document.getElementById('history-panel')
  const shellPromptWrap = document.createElement('div')
  shellPromptWrap.className = 'shell-prompt-wrap'

  const navigator = {
    clipboard: {
      writeText: text => clipboardWrite(text),
    },
  }

  const fns = fromDomScripts([
    'app/static/js/utils.js',
    'app/static/js/output.js',
    'app/static/js/tabs.js',
  ], {
    document,
    AnsiUp: class {
      constructor() {
        this.use_classes = false
      }

      ansi_to_html(s) {
        return '<em>' + s + '</em>'
      }
    },
    cmdInput,
    tabsBar,
    tabsScrollLeftBtn,
    tabsScrollRightBtn,
    tabPanels,
    runBtn,
    historyPanel,
    mobileComposerHost,
    mobileComposerRow,
    newTabBtn,
    resetCmdHistoryNav: () => {},
    APP_CONFIG: { max_tabs: maxTabs, max_output_lines: maxOutputLines, app_name: 'darklab shell' },
    setStatus: () => {},
    clearSearch: () => {},
    confirmKill: () => {},
    cancelWelcome: () => {},
    apiFetch,
    location: { origin: 'https://example.test' },
    navigator,
    URL: {
      createObjectURL: () => 'blob:mock',
      revokeObjectURL: () => {},
    },
    Blob,
    shellPromptWrap,
    getOutput: id => document.getElementById(`output-${id}`),
  }, `{
    createTab,
    mountShellPrompt,
    _getTabs: () => getTabs(),
    _stickOutputToBottom,
    _maybeMountDeferredPrompt,
    _syncTabRawLines,
  }`)

  return { ...fns, shellPromptWrap }
}

describe('tabs helpers', () => {
  beforeEach(() => {
    document.body.className = ''
    document.body.innerHTML = `
      <div id="shell-input-row" data-mobile-label="$">
        <input id="cmd" />
      </div>
      <button id="tabs-scroll-left"></button>
      <button id="tabs-scroll-right"></button>
      <button id="new-tab-btn"></button>
      <div id="history-panel"></div>
      <div id="tabs-bar"></div>
      <div id="tab-panels"></div>
      <div id="mobile-composer-host"></div>
      <div id="mobile-composer-row"></div>
      <input id="mobile-cmd" />
      <div id="permalink-toast"></div>
    `
    vi.spyOn(globalThis, 'setTimeout').mockImplementation(() => 0)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('updateNewTabBtn disables the button and sets a title at the tab limit', () => {
    const { createTab, updateNewTabBtn, newTabBtn } = loadTabsFns({ maxTabs: 1 })

    createTab('tab 1')
    updateNewTabBtn()

    expect(newTabBtn.disabled).toBe(true)
    expect(newTabBtn.title).toBe('Tab limit reached (max 1)')
  })

  it('createTab shows a toast and returns null when the tab limit is reached', () => {
    const { createTab } = loadTabsFns({ maxTabs: 1 })

    expect(createTab('tab 1')).not.toBeNull()
    expect(createTab('tab 2')).toBeNull()
    expect(document.getElementById('permalink-toast').textContent).toBe('Tab limit reached (max 1)')
  })

  it('activateTab resets the command input instead of repopulating from tab state', () => {
    const { createTab, activateTab, _getTabs } = loadTabsFns()
    const id = createTab('tab 1')
    const input = document.getElementById('cmd')
    input.value = 'keep-this'
    _getTabs()[0].command = 'ping darklab.sh'

    activateTab(id)

    expect(input.value).toBe('')
  })

  it('draftInput is initialized to empty string on new tab', () => {
    const { createTab, _getTabs } = loadTabsFns()
    createTab('tab 1')
    expect(_getTabs()[0].draftInput).toBe('')
  })

  it('activateTab saves the draft of the previous tab when switching', () => {
    const { createTab, activateTab, _getTabs } = loadTabsFns()
    const id1 = createTab('tab 1')
    const id2 = createTab('tab 2')
    const input = document.getElementById('cmd')

    activateTab(id1)
    input.value = 'nmap -sV darklab.sh'
    activateTab(id2)

    expect(_getTabs().find(t => t.id === id1).draftInput).toBe('nmap -sV darklab.sh')
  })

  it('activateTab restores the draft of the new tab when switching back', () => {
    const { createTab, activateTab, _getTabs } = loadTabsFns()
    const id1 = createTab('tab 1')
    const id2 = createTab('tab 2')
    const input = document.getElementById('cmd')

    activateTab(id1)
    input.value = 'dig darklab.sh A'
    activateTab(id2)
    input.value = 'curl -I https://darklab.sh'
    activateTab(id1)

    expect(input.value).toBe('dig darklab.sh A')
  })

  it('activateTab does not save draft for a running tab', () => {
    const { createTab, activateTab, _getTabs } = loadTabsFns()
    const id1 = createTab('tab 1')
    const id2 = createTab('tab 2')
    const input = document.getElementById('cmd')

    _getTabs().find(t => t.id === id1).st = 'running'
    activateTab(id1)
    input.value = 'should-not-be-saved'
    activateTab(id2)

    expect(_getTabs().find(t => t.id === id1).draftInput).toBe('')
  })

  it('activateTab clears acFiltered so stale suggestions from a previous tab do not persist', () => {
    const acHide = vi.fn()
    const { createTab, activateTab, _getAcFiltered } = loadTabsFns({
      acFiltered: ['whoami', 'whoami --help'],
      acHide,
    })
    const id1 = createTab('tab 1')
    const id2 = createTab('tab 2')

    activateTab(id1)

    expect(_getAcFiltered()).toEqual([])
    expect(acHide).toHaveBeenCalled()
  })

  it('closeTab resets the last remaining tab instead of removing it', () => {
    const { createTab, closeTab, _getTabs } = loadTabsFns()
    const id = createTab('first label')
    const tab = _getTabs()[0]
    const closeBtn = document.querySelector('.tab-close')
    closeBtn.blur = vi.fn()
    tab.runId = 'run-1'
    tab.runStart = 123
    tab.exitCode = 9
    tab.killed = true
    tab.pendingKill = true
    const activeElementSpy = vi.spyOn(document, 'activeElement', 'get').mockReturnValue(closeBtn)

    closeTab(id)

    expect(_getTabs()).toHaveLength(1)
    expect(_getTabs()[0].runId).toBeNull()
    expect(_getTabs()[0].runStart).toBeNull()
    expect(_getTabs()[0].exitCode).toBeNull()
    expect(_getTabs()[0].killed).toBe(false)
    expect(_getTabs()[0].pendingKill).toBe(false)
    expect(document.querySelector('.tab-label').textContent).toBe('tab 1')
    expect(closeBtn.blur).toHaveBeenCalled()
    activeElementSpy.mockRestore()
  })

  it('clearTab preserves a running tab state when asked to keep the run active', () => {
    const { createTab, clearTab, _getTabs, shellPromptWrap } = loadTabsFns()
    const id = createTab('tab 1')
    const tab = _getTabs()[0]
    const output = document.getElementById(`output-${id}`)
    output.innerHTML = '<div>before</div>'
    tab.st = 'running'
    tab.runId = 'run-1'
    tab.historyRunId = 'history-1'
    tab.followOutput = false

    clearTab(id, { preserveRunState: true })

    expect(output.innerHTML).toBe('')
    expect(tab.st).toBe('running')
    expect(tab.runId).toBe('run-1')
    expect(tab.historyRunId).toBe('history-1')
    expect(tab.followOutput).toBe(true)
    expect(document.querySelector(`.tab-panel[data-id="${id}"]`).contains(shellPromptWrap)).toBe(false)
  })

  it('clearTab clears the active un-ran composer input along with the tab output', () => {
    const { createTab, clearTab, _getTabs } = loadTabsFns()
    const id = createTab('tab 1')
    const tab = _getTabs()[0]
    const output = document.getElementById(`output-${id}`)
    const cmdInput = document.getElementById('cmd')
    const mobileCmdInput = document.getElementById('mobile-cmd')
    output.innerHTML = '<div>before</div>'
    cmdInput.value = 'pending command'
    mobileCmdInput.value = 'pending mobile command'
    tab.rawLines = [{ text: 'before', cls: '', tsC: '', tsE: '' }]

    clearTab(id)

    expect(output.innerHTML).toBe('')
    expect(tab.rawLines).toEqual([])
    expect(cmdInput.value).toBe('')

    document.body.classList.add('mobile-terminal-mode')
    cmdInput.value = 'desktop should stay untouched in mobile mode'
    mobileCmdInput.value = 'pending mobile command'

    clearTab(id)

    expect(cmdInput.value).toBe('desktop should stay untouched in mobile mode')
    expect(mobileCmdInput.value).toBe('pending mobile command')
  })

  it('closing a running tab kills it and activates a neighboring tab', () => {
    const { createTab, activateTab, closeTab, _getTabs, doKill } = loadTabsFns()
    const firstId = createTab('tab 1')
    const secondId = createTab('tab 2')

    activateTab(secondId)
    document.getElementById('cmd').focus.mockClear()
    const runningTab = _getTabs().find(tab => tab.id === secondId)
    runningTab.st = 'running'
    runningTab.runId = 'run-2'

    closeTab(secondId)

    expect(doKill).toHaveBeenCalledWith(secondId)
    expect(_getTabs().map(tab => tab.id)).toEqual([firstId, secondId])
    expect(_getTabs().find(tab => tab.id === secondId).closing).toBe(true)
    expect(document.querySelector('.tab.active').dataset.id).toBe(firstId)
    expect(document.getElementById('cmd').focus).not.toHaveBeenCalled()
  })

  it('closing the only running tab kills it and keeps the tab shell ready', () => {
    const { createTab, closeTab, _getTabs, doKill } = loadTabsFns()
    const id = createTab('tab 1')
    const runningTab = _getTabs()[0]
    runningTab.st = 'running'
    runningTab.runId = 'run-1'

    closeTab(id)

    expect(doKill).toHaveBeenCalledWith(id)
    expect(_getTabs()).toHaveLength(1)
    expect(_getTabs()[0].closing).toBe(true)
    expect(_getTabs()[0].st).toBe('running')
  })

  it('mountShellPrompt does not render prompt when tab is running even when forced', () => {
    const { createTab, mountShellPrompt, setTabStatus, shellPromptWrap } = loadTabsFns()
    const id = createTab('tab 1')
    const output = document.querySelector(`.tab-panel[data-id="${id}"] .output`)

    setTabStatus(id, 'running')
    mountShellPrompt(id, true)

    expect(output.contains(shellPromptWrap)).toBe(false)
  })

  it('mountShellPrompt keeps the desktop prompt mirror out of mobile mode', () => {
    const { createTab, mountShellPrompt, shellPromptWrap } = loadTabsFns()
    const id = createTab('tab 1')
    const output = document.querySelector(`.tab-panel[data-id="${id}"] .output`)
    const mobileComposerHost = document.getElementById('mobile-composer-host')
    const shellInputRow = document.getElementById('shell-input-row')
    const mobileComposerRow = document.getElementById('mobile-composer-row')

    document.body.classList.add('mobile-terminal-mode', 'mobile-keyboard-open')
    mountShellPrompt(id, true)

    expect(mobileComposerHost.contains(shellPromptWrap)).toBe(false)
    expect(output.contains(shellPromptWrap)).toBe(false)
    expect(mobileComposerRow.contains(shellInputRow)).toBe(false)
  })

  it('tracks whether the output should keep following the live tail', () => {
    const { createTab, _getTabs } = loadTabsFns()
    const id = createTab('tab 1')
    const tab = _getTabs()[0]
    const output = document.getElementById(`output-${id}`)

    let scrollTop = 0
    Object.defineProperty(output, 'clientHeight', { configurable: true, get: () => 100 })
    Object.defineProperty(output, 'scrollHeight', { configurable: true, get: () => 300 })
    Object.defineProperty(output, 'scrollTop', {
      configurable: true,
      get: () => scrollTop,
      set: value => { scrollTop = value },
    })

    output.dispatchEvent(new Event('scroll'))
    expect(tab.followOutput).toBe(false)

    scrollTop = 200
    output.dispatchEvent(new Event('scroll'))
    expect(tab.followOutput).toBe(true)
  })

  it('keeps follow-output enabled when the terminal scrolls itself to the bottom', () => {
    const { createTab, _getTabs, _stickOutputToBottom } = loadTabsAndOutputFns()
    const id = createTab('tab 1')
    const tab = _getTabs()[0]
    const output = document.getElementById(`output-${id}`)

    let scrollTop = 0
    Object.defineProperty(output, 'clientHeight', { configurable: true, get: () => 100 })
    Object.defineProperty(output, 'scrollHeight', { configurable: true, get: () => 300 })
    Object.defineProperty(output, 'scrollTop', {
      configurable: true,
      get: () => scrollTop,
      set: value => {
        scrollTop = value
        output.dispatchEvent(new Event('scroll'))
      },
    })

    _stickOutputToBottom(output, tab)

    expect(tab.suppressOutputScrollTracking).toBe(true)
    expect(tab.followOutput).toBe(true)
  })

  it('defers remounting the prompt until the output queue is drained', () => {
    const { createTab, mountShellPrompt, _maybeMountDeferredPrompt, _getTabs, shellPromptWrap } = loadTabsAndOutputFns()
    const id = createTab('tab 1')
    const tab = _getTabs()[0]
    tab.deferPromptMount = true

    mountShellPrompt(id)
    expect(shellPromptWrap.parentElement).not.toBe(document.getElementById(`output-${id}`))

    _maybeMountDeferredPrompt(id)
    expect(tab.deferPromptMount).toBe(false)
  })

  it('mountShellPrompt stays hidden during the desktop welcome boot', () => {
    const { createTab, mountShellPrompt, shellPromptWrap } = loadTabsFns({ welcomeBootPending: true })
    const id = createTab('tab 1')
    const output = document.querySelector(`.tab-panel[data-id="${id}"] .output`)

    mountShellPrompt(id)

    expect(output.contains(shellPromptWrap)).toBe(false)
  })

  it('keeps currentRunStartIndex aligned when old raw lines are pruned from the front', () => {
    const { createTab, _getTabs, _syncTabRawLines } = loadTabsAndOutputFns({ maxOutputLines: 3 })

    createTab('tab 1')
    const tab = _getTabs()[0]
    tab.currentRunStartIndex = 2

    _syncTabRawLines(tab, { text: 'one', cls: '', tsC: '', tsE: '' })
    _syncTabRawLines(tab, { text: 'two', cls: '', tsC: '', tsE: '' })
    _syncTabRawLines(tab, { text: 'three', cls: '', tsC: '', tsE: '' })
    _syncTabRawLines(tab, { text: 'four', cls: '', tsC: '', tsE: '' })

    expect(tab.rawLines.map(line => line.text)).toEqual(['two', 'three', 'four'])
    expect(tab.currentRunStartIndex).toBe(1)
  })

  it('setTabLabel truncates the rendered label but preserves the full label in state', () => {
    const { createTab, setTabLabel, _getTabs } = loadTabsFns()
    const id = createTab('tab 1')
    const label = 'abcdefghijklmnopqrstuvwxyz1234567890'

    setTabLabel(id, label)

    expect(document.querySelector('.tab-label').textContent).toBe('abcdefghijklmnopqrstuvwxyz…')
    expect(_getTabs()[0].label).toBe(label)
  })

  it('permalinkTab shows a toast when there is no output to share', () => {
    const { createTab, permalinkTab } = loadTabsFns()
    const id = createTab('tab 1')

    permalinkTab(id)

    expect(document.getElementById('permalink-toast').textContent).toBe('No output to share yet')
  })

  it('permalinkTab shows a failure toast when the share request rejects', async () => {
    const apiFetch = vi.fn(() => Promise.reject(new Error('share failed')))
    const { createTab, permalinkTab, _getTabs } = loadTabsFns({ apiFetch })
    const id = createTab('tab 1')
    _getTabs()[0].rawLines.push({ text: 'line 1', cls: '', tsC: '', tsE: '' })

    permalinkTab(id)
    await new Promise(resolve => setImmediate(resolve))

    expect(document.getElementById('permalink-toast').textContent).toBe('Failed to create permalink')
  })

  it('permalinkTab falls back to execCommand when clipboard writeText rejects', async () => {
    const apiFetch = vi.fn(() => Promise.resolve({ json: () => Promise.resolve({ url: '/share/abc' }) }))
    document.execCommand = vi.fn(() => true)
    const { createTab, permalinkTab, _getTabs } = loadTabsFns({
      apiFetch,
      clipboardWrite: () => Promise.reject(new Error('clipboard denied')),
    })
    const id = createTab('tab 1')
    _getTabs()[0].rawLines.push({ text: 'line 1', cls: '', tsC: '', tsE: '' })

    permalinkTab(id)
    await new Promise(resolve => setImmediate(resolve))
    await new Promise(resolve => setImmediate(resolve))

    expect(document.execCommand).toHaveBeenCalledWith('copy')
    expect(document.getElementById('permalink-toast').textContent).toBe('Link copied to clipboard')
    expect(document.getElementById('permalink-toast').classList.contains('toast-error')).toBe(false)
  })

  it('permalinkTab does not append a truncation warning for a tab with full output already loaded', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/history/run-1?json') {
        return Promise.resolve({
          json: () => Promise.resolve({
            output_entries: [
              { text: 'full line 1', cls: '', tsC: '', tsE: '' },
              { text: 'full line 2', cls: '', tsC: '', tsE: '' },
            ],
            output: ['full line 1', 'full line 2'],
          }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({ url: '/share/abc' }) })
    })
    const { createTab, permalinkTab, _getTabs } = loadTabsFns({ apiFetch })
    const id = createTab('tab 1')
    const tab = _getTabs()[0]
    const cmdInput = document.getElementById('cmd')
    tab.historyRunId = 'run-1'
    tab.fullOutputAvailable = true
    tab.previewTruncated = true
    tab.currentRunStartIndex = 2
    tab.rawLines.push({ text: '$ tab 1', cls: 'prompt-echo', tsC: '', tsE: '' })
    tab.rawLines.push({ text: '', cls: 'prompt-echo', tsC: '', tsE: '' })
    tab.rawLines.push({ text: 'preview line 1', cls: '', tsC: '', tsE: '' })
    tab.rawLines.push({ text: '[preview truncated — only the last 2000 lines are shown here, but the full output had 6386 lines. Use the run history permalink for the full output]', cls: 'notice', tsC: '', tsE: '' })
    tab.rawLines.push({ text: '[process exited with code 0 in 0.2s]', cls: 'exit-ok', tsC: '', tsE: '' })

    permalinkTab(id)
    await new Promise(resolve => setImmediate(resolve))
    await new Promise(resolve => setImmediate(resolve))

    expect(apiFetch).toHaveBeenCalledWith('/history/run-1?json')
    const shareCall = apiFetch.mock.calls.find(([url]) => url === '/share')
    expect(shareCall).toBeTruthy()
    const payload = JSON.parse(shareCall[1].body)
    expect(payload.content).toHaveLength(5)
    expect(payload.content.map(entry => entry.text)).toEqual([
      '$ tab 1',
      '',
      'full line 1',
      'full line 2',
      '[process exited with code 0 in 0.2s]',
    ])
    expect(payload.content.some(entry => String(entry.text || '').includes('tab output truncated'))).toBe(false)
    expect(payload.content.some(entry => String(entry.text || '').includes('preview truncated'))).toBe(false)
    expect(cmdInput.focus).toHaveBeenCalled()
  })

  it('copyTab shows a toast when there is no exportable output', () => {
    const { createTab, copyTab } = loadTabsFns()
    const id = createTab('tab 1')

    copyTab(id)

    expect(document.getElementById('permalink-toast').textContent).toBe('No output to copy yet')
  })

  it('refocuses the terminal input after copy, save, and html export actions', async () => {
    const { createTab, copyTab, saveTab, exportTabHtml, _getTabs } = loadTabsFns()
    const id = createTab('tab 1')
    const tab = _getTabs()[0]
    const cmdInput = document.getElementById('cmd')
    tab.rawLines.push({ text: 'line 1', cls: '', tsC: '', tsE: '' })

    copyTab(id)
    await new Promise(resolve => setImmediate(resolve))
    await new Promise(resolve => setImmediate(resolve))
    expect(cmdInput.focus).toHaveBeenCalled()

    cmdInput.focus.mockClear()
    saveTab(id)
    await new Promise(resolve => setImmediate(resolve))
    expect(cmdInput.focus).toHaveBeenCalled()

    cmdInput.focus.mockClear()
    window.ExportHtmlUtils = {
      escapeExportHtml: s => s,
      renderExportPromptEcho: s => s,
      fetchVendorFontFacesCss: () => Promise.resolve(''),
      buildTerminalExportHtml: () => '<html><body>export</body></html>',
      exportTimestamp: () => '2026-01-01-00-00-00',
    }
    await exportTabHtml(id)
    expect(cmdInput.focus).toHaveBeenCalled()
    delete window.ExportHtmlUtils
  })

  it('builds exported HTML styles from the injected theme vars object', () => {
    window.ThemeCssVars = {
      fallback: {
        '--bg': '#b8c4d0',
        '--surface': '#eef2f6',
        '--text': '#101820',
        '--green': '#2a5d18',
      },
    }

    const { buildTerminalExportStyles } = fromDomScripts([
      'app/static/js/export_html.js',
    ], {
      document,
    }, `ExportHtmlUtils`)

    const css = buildTerminalExportStyles('theme_light_blue')
    expect(css).toContain('--bg: #b8c4d0;')
    expect(css).toContain('--surface: #eef2f6;')
    expect(css).toContain('--text: #101820;')
    expect(css).toContain('--green: #2a5d18;')

    delete window.ThemeCssVars
  })

  it('saveTab shows a toast when there is only welcome output', () => {
    const { createTab, saveTab, _getTabs } = loadTabsFns()
    const id = createTab('tab 1')
    _getTabs()[0].rawLines.push({ text: '# Welcome hint', cls: 'welcome-hint', tsC: '', tsE: '' })

    saveTab(id)

    expect(document.getElementById('permalink-toast').textContent).toBe('No output to export')
  })

  it('startTabRename updates scroll buttons when the strip begins overflowing during edit', () => {
    const { createTab, startTabRename, updateTabScrollButtons } = loadTabsFns()
    const firstId = createTab('tab 1')
    createTab('tab 2')

    const tabsBar = document.getElementById('tabs-bar')
    const rightBtn = document.getElementById('tabs-scroll-right')
    Object.defineProperty(tabsBar, 'clientWidth', { configurable: true, get: () => 320 })
    Object.defineProperty(tabsBar, 'scrollLeft', { configurable: true, get: () => 0 })

    let scrollWidth = 320
    Object.defineProperty(tabsBar, 'scrollWidth', { configurable: true, get: () => scrollWidth })

    updateTabScrollButtons()
    expect(rightBtn.disabled).toBe(true)

    const labelEl = document.querySelector(`.tab[data-id="${firstId}"] .tab-label`)
    startTabRename(firstId, labelEl)
    scrollWidth = 480
    const input = document.querySelector('.tab-rename-input')
    input.value = 'this-is-a-very-long-tab-name'
    input.dispatchEvent(new Event('input', { bubbles: true }))

    expect(rightBtn.disabled).toBe(false)
  })

  it('refocuses the terminal input after clicking the left tab scroll button', () => {
    const { createTab } = loadTabsFns()
    createTab('tab 1')
    createTab('tab 2')

    const tabsBar = document.getElementById('tabs-bar')
    let scrollLeft = 120
    Object.defineProperty(tabsBar, 'clientWidth', { configurable: true, get: () => 200 })
    Object.defineProperty(tabsBar, 'scrollWidth', { configurable: true, get: () => 600 })
    Object.defineProperty(tabsBar, 'scrollLeft', { configurable: true, get: () => scrollLeft })
    tabsBar.scrollBy = vi.fn(({ left }) => {
      scrollLeft = Math.max(0, Math.min(400, scrollLeft + left))
    })

    const cmdInput = document.getElementById('cmd')
    document.getElementById('tabs-scroll-left').click()
    expect(cmdInput.focus).toHaveBeenCalled()
  })

  it('refocuses the terminal input after clicking the right tab scroll button', () => {
    const { createTab } = loadTabsFns()
    createTab('tab 1')
    createTab('tab 2')

    const tabsBar = document.getElementById('tabs-bar')
    let scrollLeft = 120
    Object.defineProperty(tabsBar, 'clientWidth', { configurable: true, get: () => 200 })
    Object.defineProperty(tabsBar, 'scrollWidth', { configurable: true, get: () => 600 })
    Object.defineProperty(tabsBar, 'scrollLeft', { configurable: true, get: () => scrollLeft })
    tabsBar.scrollBy = vi.fn(({ left }) => {
      scrollLeft = Math.max(0, Math.min(400, scrollLeft + left))
    })

    const cmdInput = document.getElementById('cmd')
    document.getElementById('tabs-scroll-right').click()
    expect(cmdInput.focus).toHaveBeenCalled()
  })

  it('reorders tabs through touch pointer dragging on mobile', () => {
    const { createTab, _getTabs } = loadTabsFns()
    const firstId = createTab('tab 1')
    const secondId = createTab('tab 2')
    const thirdId = createTab('tab 3')

    const tabs = [...document.querySelectorAll('.tab')]
    tabs.forEach((tab, index) => {
      const left = index * 100
      tab.getBoundingClientRect = () => ({
        left,
        right: left + 90,
        top: 0,
        bottom: 36,
        width: 90,
        height: 36,
      })
    })
    const tabsBar = document.getElementById('tabs-bar')
    tabsBar.getBoundingClientRect = () => ({
      left: 0,
      right: 320,
      top: 0,
      bottom: 40,
      width: 320,
      height: 40,
    })
    tabsBar.scrollBy = vi.fn()

    const dragged = document.querySelector(`.tab[data-id="${thirdId}"]`)
    dragged.dispatchEvent(touchPointerEvent('pointerdown', {
      pointerId: 7,
      pointerType: 'touch',
      clientX: 250,
      clientY: 12,
    }))
    document.dispatchEvent(touchPointerEvent('pointermove', {
      pointerId: 7,
      pointerType: 'touch',
      clientX: 20,
      clientY: 12,
    }))

    expect(dragged.classList.contains('tab-touch-dragging')).toBe(true)
    expect(document.getElementById('tabs-bar').classList.contains('tabs-bar-touch-sorting')).toBe(true)
    expect(document.querySelector(`.tab[data-id="${firstId}"]`)?.classList.contains('tab-drop-before')).toBe(true)

    document.dispatchEvent(touchPointerEvent('pointerup', {
      pointerId: 7,
      pointerType: 'touch',
      clientX: 20,
      clientY: 12,
    }))

    expect(_getTabs().map(tab => tab.id)).toEqual([thirdId, firstId, secondId])
    expect(document.querySelector('.tab')?.dataset.id).toBe(thirdId)
    expect(document.getElementById('cmd').focus).toHaveBeenCalled()
    expect(document.getElementById('tabs-bar').classList.contains('tabs-bar-touch-sorting')).toBe(false)
    expect(document.querySelector('.tab-drop-before, .tab-drop-after')).toBeNull()
  })
})
