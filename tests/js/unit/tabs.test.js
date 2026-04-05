import { vi } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

function loadTabsFns({ maxTabs = 3, apiFetch = () => Promise.resolve({ json: () => Promise.resolve({ url: '/share/abc' }) }) } = {}) {
  const cmdInput = document.getElementById('cmd')
  const tabsBar = document.getElementById('tabs-bar')
  const tabPanels = document.getElementById('tab-panels')
  const newTabBtn = document.getElementById('new-tab-btn')
  const historyPanel = document.getElementById('history-panel')
  const clipboardWrites = []

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
  }, `{
    updateNewTabBtn,
    createTab,
    activateTab,
    closeTab,
    setTabLabel,
    permalinkTab,
    _getTabs: () => tabs,
    _getActiveTabId: () => activeTabId,
  }`)

  return { ...fns, clipboardWrites, newTabBtn }
}

describe('tabs helpers', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <input id="cmd" />
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

  it('activateTab restores the tab command into the input and emits an input event', () => {
    const { createTab, activateTab, _getTabs } = loadTabsFns()
    const id = createTab('tab 1')
    const input = document.getElementById('cmd')
    const inputSpy = vi.fn()
    input.addEventListener('input', inputSpy)
    _getTabs()[0].command = 'ping example.com'

    activateTab(id)

    expect(input.value).toBe('ping example.com')
    expect(inputSpy).toHaveBeenCalledTimes(1)
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
})
