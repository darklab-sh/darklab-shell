import { vi } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

function loadTabsFns({ maxTabs = 3, apiFetch = () => Promise.resolve({ json: () => Promise.resolve({ url: '/share/abc' }) }) } = {}) {
  const cmdInput = document.getElementById('cmd')
  const tabsBar = document.getElementById('tabs-bar')
  const tabPanels = document.getElementById('tab-panels')
  const newTabBtn = document.getElementById('new-tab-btn')
  const historyPanel = document.getElementById('history-panel')
  const clipboardWrites = []
  const shellPromptWrap = document.createElement('div')
  shellPromptWrap.className = 'shell-prompt-wrap'

  const navigator = {
    clipboard: {
      writeText: (text) => {
        clipboardWrites.push(text)
        return Promise.resolve()
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
    tabPanels,
    historyPanel,
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
    _getTabs: () => tabs,
    _getActiveTabId: () => activeTabId,
  }`)

  return { ...fns, clipboardWrites, newTabBtn, shellPromptWrap }
}

describe('tabs helpers', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <input id="cmd" />
      <button id="tabs-scroll-left"></button>
      <button id="tabs-scroll-right"></button>
      <button id="new-tab-btn"></button>
      <div id="history-panel"></div>
      <div id="tabs-bar"></div>
      <div id="tab-panels"></div>
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
    _getTabs()[0].command = 'ping example.com'

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
})
