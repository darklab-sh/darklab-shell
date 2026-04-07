import { vi } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

function touchPointerEvent(type, init) {
  const event = new Event(type, { bubbles: true, cancelable: true })
  Object.assign(event, init)
  return event
}

function loadTabsFns({
  maxTabs = 3,
  apiFetch = () => Promise.resolve({ json: () => Promise.resolve({ url: '/share/abc' }) }),
  welcomeBootPending = undefined,
  clipboardWrite = () => Promise.resolve(),
} = {}) {
  const cmdInput = document.getElementById('cmd')
  cmdInput.focus = vi.fn()
  const tabsBar = document.getElementById('tabs-bar')
  const tabsScrollLeftBtn = document.getElementById('tabs-scroll-left')
  const tabsScrollRightBtn = document.getElementById('tabs-scroll-right')
  const tabPanels = document.getElementById('tab-panels')
  const mobileComposerHost = document.getElementById('mobile-composer-host')
  const mobileComposerRow = document.getElementById('mobile-composer-row')
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
    historyPanel,
    mobileComposerHost,
    mobileComposerRow,
    newTabBtn,
    resetCmdHistoryNav: () => {},
    ...(welcomeBootPending === undefined ? {} : { _welcomeBootPending: welcomeBootPending }),
    APP_CONFIG: { max_tabs: maxTabs, app_name: 'shell.darklab.sh' },
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
    ansi_up: { ansi_to_html: (s) => `<em>${s}</em>` },
    shellPromptWrap,
  }, `{
    updateNewTabBtn,
    updateTabScrollButtons,
    createTab,
    activateTab,
    startTabRename,
    mountShellPrompt,
    closeTab,
    setTabStatus,
    setTabLabel,
    copyTab,
    saveTab,
    permalinkTab,
    _getTabs: () => getTabs(),
    _getActiveTabId: () => getActiveTabId(),
  }`)

  return { ...fns, clipboardWrites, newTabBtn, shellPromptWrap }
}

function loadTabsAndOutputFns({
  maxTabs = 3,
  apiFetch = () => Promise.resolve({ json: () => Promise.resolve({ url: '/share/abc' }) }),
  clipboardWrite = () => Promise.resolve(),
} = {}) {
  const cmdInput = document.getElementById('cmd')
  cmdInput.focus = vi.fn()
  const tabsBar = document.getElementById('tabs-bar')
  const tabsScrollLeftBtn = document.getElementById('tabs-scroll-left')
  const tabsScrollRightBtn = document.getElementById('tabs-scroll-right')
  const tabPanels = document.getElementById('tab-panels')
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
    historyPanel,
    mobileComposerHost,
    mobileComposerRow,
    newTabBtn,
    resetCmdHistoryNav: () => {},
    APP_CONFIG: { max_tabs: maxTabs, max_output_lines: 100, app_name: 'shell.darklab.sh' },
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
  }`)

  return { ...fns, shellPromptWrap }
}

describe('tabs helpers', () => {
  beforeEach(() => {
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

  it('closeTab resets the last remaining tab instead of removing it', () => {
    const { createTab, closeTab, _getTabs } = loadTabsFns()
    const id = createTab('first label')
    const tab = _getTabs()[0]
    tab.runId = 'run-1'
    tab.runStart = 123
    tab.exitCode = 9
    tab.killed = true
    tab.pendingKill = true

    closeTab(id)

    expect(_getTabs()).toHaveLength(1)
    expect(_getTabs()[0].runId).toBeNull()
    expect(_getTabs()[0].runStart).toBeNull()
    expect(_getTabs()[0].exitCode).toBeNull()
    expect(_getTabs()[0].killed).toBe(false)
    expect(_getTabs()[0].pendingKill).toBe(false)
    expect(document.querySelector('.tab-label').textContent).toBe('tab 1')
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
