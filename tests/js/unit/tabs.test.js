import { vi } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

// The tabs module owns a large amount of DOM state, so these tests build a
// minimal but realistic shell scaffold rather than mocking every interaction.
async function flushPromises(times = 4) {
  for (let i = 0; i < times; i += 1) await Promise.resolve()
}

function touchPointerEvent(type, init) {
  const event = new Event(type, { bubbles: true, cancelable: true })
  Object.assign(event, init)
  return event
}

function touchEvent(type, touches = [], changedTouches = touches) {
  const event = new Event(type, { bubbles: true, cancelable: true })
  Object.defineProperty(event, 'touches', { value: touches, configurable: true })
  Object.defineProperty(event, 'changedTouches', { value: changedTouches, configurable: true })
  return event
}

function loadTabsFns({
  maxTabs = 3,
  maxOutputLines = 100,
  version = undefined,
  projectReadme = undefined,
  shareRedactionEnabled = true,
  shareRedactionRules = [],
  confirmPermalinkRedactionChoice = () =>
    Promise.resolve(shareRedactionEnabled ? 'redacted' : 'raw'),
  apiFetch = () => Promise.resolve({ json: () => Promise.resolve({ url: '/share/abc' }) }),
  welcomeBootPending = undefined,
  clipboardWrite = () => Promise.resolve(),
  doKill = vi.fn(),
  showConfirm = undefined,
  detachRunStreamForTab = undefined,
  acFiltered: acFilteredOverride = [],
  acHide: acHideOverride = () => {},
  urlImpl = {
    createObjectURL: () => 'blob:mock',
    revokeObjectURL: () => {},
  },
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
  shellPromptWrap.id = 'shell-prompt-wrap'
  shellPromptWrap.className = 'shell-prompt-wrap'

  const navigator = {
    clipboard: {
      writeText: (text) => {
        clipboardWrites.push(text)
        return clipboardWrite(text)
      },
    },
  }

  const fns = fromDomScripts(
    ['app/static/js/utils.js', 'app/static/js/tabs.js'],
    {
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
      _tabSessionRestoreInProgress: false,
      ...(welcomeBootPending === undefined ? {} : { _welcomeBootPending: welcomeBootPending }),
      APP_CONFIG: {
        max_tabs: maxTabs,
        max_output_lines: maxOutputLines,
        app_name: 'darklab_shell',
        share_redaction_enabled: shareRedactionEnabled,
        share_redaction_rules: shareRedactionRules,
        ...(version !== undefined && { version }),
        ...(projectReadme !== undefined && { project_readme: projectReadme }),
      },
      setStatus: () => {},
      clearSearch: () => {},
      confirmKill: () => {},
      doKill,
      ...(showConfirm ? { showConfirm } : {}),
      ...(detachRunStreamForTab ? { detachRunStreamForTab } : {}),
      cancelWelcome: () => {},
      confirmPermalinkRedactionChoice,
      apiFetch,
      location: { origin: 'https://example.test' },
      navigator,
      URL: urlImpl,
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
    },
    `{
    updateNewTabBtn,
    updateTabScrollButtons,
    updateOutputFollowButton,
    createTab,
    activateTab,
    startTabRename,
    mountShellPrompt,
    closeTab,
    clearTab,
    setTabStatus,
    setTabLabel,
    setTabRunningCommand,
    createDefaultTabLabel,
    copyTab,
    saveTab,
    exportTabHtml,
    exportTabPdf,
    permalinkTab,
    _getTabs: () => getTabs(),
    _getActiveTabId: () => getActiveTabId(),
    _getAcFiltered: () => acFiltered,
  }`,
  )

  return { ...fns, clipboardWrites, newTabBtn, shellPromptWrap, doKill }
}

function loadTabsAndOutputFns({
  maxTabs = 3,
  maxOutputLines = 100,
  apiFetch = () => Promise.resolve({ json: () => Promise.resolve({ url: '/share/abc' }) }),
  clipboardWrite = () => Promise.resolve(),
  shareRedactionEnabled = true,
  shareRedactionRules = [],
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
  shellPromptWrap.id = 'shell-prompt-wrap'
  shellPromptWrap.className = 'shell-prompt-wrap'

  const navigator = {
    clipboard: {
      writeText: (text) => clipboardWrite(text),
    },
  }

  const fns = fromDomScripts(
    ['app/static/js/utils.js', 'app/static/js/output_core.js', 'app/static/js/output.js', 'app/static/js/tabs.js'],
    {
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
      _tabSessionRestoreInProgress: false,
      APP_CONFIG: {
        max_tabs: maxTabs,
        max_output_lines: maxOutputLines,
        app_name: 'darklab_shell',
        prompt_username: 'anon',
              prompt_domain: 'darklab.sh',
        share_redaction_enabled: shareRedactionEnabled,
        share_redaction_rules: shareRedactionRules,
      },
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
      getOutput: (id) => document.getElementById(`output-${id}`),
      _welcomeBootPending: false,
    },
    `{
    createTab,
    mountShellPrompt,
    closeTab,
    renderRestoredTabOutput,
    appendLine,
    _setLnMode,
    _getTabs: () => getTabs(),
    _stickOutputToBottom,
    _maybeMountDeferredPrompt,
    _syncTabRawLines,
  }`,
  )

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
    vi.useRealTimers()
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

  it('createTab labels the active-tab permalink action as share snapshot', () => {
    const { createTab } = loadTabsFns()

    const id = createTab('tab 1')
    const btn = document.querySelector(
      `#tab-panels .tab-panel[data-id="${id}"] [data-action="permalink"]`,
    )

    expect(btn.textContent).toBe('share snapshot')
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

    expect(_getTabs().find((t) => t.id === id1).draftInput).toBe('nmap -sV darklab.sh')
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

    _getTabs().find((t) => t.id === id1).st = 'running'
    activateTab(id1)
    input.value = 'should-not-be-saved'
    activateTab(id2)

    expect(_getTabs().find((t) => t.id === id1).draftInput).toBe('')
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
    expect(document.querySelector('.tab-label').textContent).toBe('shell 1')
    expect(closeBtn.blur).toHaveBeenCalled()
    activeElementSpy.mockRestore()
  })

  it('closeTab resets the preserved last tab line counter before the next command output', () => {
    const { createTab, closeTab, appendLine, _setLnMode, _getTabs, shellPromptWrap } = loadTabsAndOutputFns()
    const id = createTab('first label')
    const tab = _getTabs()[0]

    _setLnMode('on')
    appendLine('old one', '', id)
    appendLine('old two', '', id)
    tab.workspaceCwd = 'reports'
    tab.draftInput = 'stale draft'
    tab.commandHistory = ['cat old.txt']

    closeTab(id)

    const out = document.getElementById(`output-${id}`)
    expect(out.dataset.outputLineCounter).toBe('0')
    expect(tab._outputLineCounter).toBe(0)
    expect(tab.workspaceCwd).toBe('')
    expect(tab.draftInput).toBe('')
    expect(tab.commandHistory).toEqual([])
    expect(shellPromptWrap.dataset.lineNumber).toBe('1')

    appendLine('fresh one', '', id)

    const lines = out.getElementsByClassName('line')
    expect(lines).toHaveLength(1)
    expect(lines[0].dataset.lineNumber).toBe('1')
    expect(shellPromptWrap.dataset.lineNumber).toBe('2')
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
    expect(document.querySelector(`.tab-panel[data-id="${id}"]`).contains(shellPromptWrap)).toBe(
      false,
    )
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

  it('closing a running tab prompts before killing it and activates a neighboring tab', async () => {
    const showConfirm = vi.fn(() => Promise.resolve('kill'))
    const { createTab, activateTab, closeTab, _getTabs, doKill } = loadTabsFns({ showConfirm })
    const firstId = createTab('tab 1')
    const secondId = createTab('tab 2')

    activateTab(secondId)
    document.getElementById('cmd').focus.mockClear()
    const runningTab = _getTabs().find((tab) => tab.id === secondId)
    runningTab.st = 'running'
    runningTab.runId = 'run-2'

    closeTab(secondId)
    expect(showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      body: expect.objectContaining({
        text: 'Close this running tab?',
        note: expect.stringContaining('Keep running detaches this tab only'),
      }),
    }))
    await flushPromises()

    expect(doKill).toHaveBeenCalledWith(secondId)
    expect(_getTabs().map((tab) => tab.id)).toEqual([firstId, secondId])
    expect(_getTabs().find((tab) => tab.id === secondId).closing).toBe(true)
    expect(document.querySelector('.tab.active').dataset.id).toBe(firstId)
    expect(document.getElementById('cmd').focus).not.toHaveBeenCalled()
  })

  it('closing an attached running tab can detach it without killing the run', async () => {
    const showConfirm = vi.fn(() => Promise.resolve('detach'))
    const detachRunStreamForTab = vi.fn()
    const { createTab, activateTab, closeTab, _getTabs, doKill } = loadTabsFns({
      showConfirm,
      detachRunStreamForTab,
    })
    const firstId = createTab('tab 1')
    const secondId = createTab('attached run')

    activateTab(secondId)
    const attachedTab = _getTabs().find((tab) => tab.id === secondId)
    attachedTab.st = 'running'
    attachedTab.runId = 'run-other'
    attachedTab.historyRunId = 'run-other'
    attachedTab.attachMode = 'attached'

    closeTab(secondId)
    await flushPromises()

    expect(detachRunStreamForTab).toHaveBeenCalledWith(secondId)
    expect(doKill).not.toHaveBeenCalled()
    expect(_getTabs().map((tab) => tab.id)).toEqual([firstId])
    expect(document.querySelector(`[data-id="${secondId}"]`)).toBeNull()
    expect(document.querySelector('.tab.active').dataset.id).toBe(firstId)
  })

  it('closing the only running tab can detach it and keep the tab shell ready', async () => {
    const showConfirm = vi.fn(() => Promise.resolve('detach'))
    const detachRunStreamForTab = vi.fn()
    const { createTab, closeTab, _getTabs, doKill } = loadTabsFns({
      showConfirm,
      detachRunStreamForTab,
    })
    const id = createTab('tab 1')
    const runningTab = _getTabs()[0]
    runningTab.st = 'running'
    runningTab.runId = 'run-1'
    runningTab.historyRunId = 'run-1'

    closeTab(id)
    await flushPromises()

    expect(detachRunStreamForTab).toHaveBeenCalledWith(id)
    expect(doKill).not.toHaveBeenCalled()
    expect(_getTabs()).toHaveLength(1)
    expect(_getTabs()[0].closing).toBe(false)
    expect(_getTabs()[0].st).toBe('idle')
    expect(_getTabs()[0].runId).toBeNull()
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
      set: (value) => {
        scrollTop = value
      },
    })

    output.dispatchEvent(new Event('scroll'))
    expect(tab.followOutput).toBe(false)

    scrollTop = 200
    output.dispatchEvent(new Event('scroll'))
    expect(tab.followOutput).toBe(true)
  })

  it('does not treat a simple output tap as user scroll intent', () => {
    const { createTab, _getTabs } = loadTabsFns()
    const id = createTab('tab 1')
    const tab = _getTabs()[0]
    const output = document.getElementById(`output-${id}`)

    output.dispatchEvent(touchPointerEvent('pointerdown', { pointerType: 'touch' }))
    output.dispatchEvent(touchEvent('touchstart', [{ identifier: 1, clientX: 20, clientY: 20 }]))

    expect(tab.outputUserScrollUntil).toBe(0)

    output.dispatchEvent(touchPointerEvent('pointermove', { pointerType: 'touch' }))
    expect(tab.outputUserScrollUntil).toBeGreaterThan(Date.now() - 10)
  })

  it('shows a live jump button while output is streaming off the live tail', () => {
    const { createTab, _getTabs, setTabStatus, updateOutputFollowButton } = loadTabsFns()
    const id = createTab('tab 1')
    const tab = _getTabs()[0]
    const output = document.getElementById(`output-${id}`)
    const button = document.querySelector(`.tab-panel[data-id="${id}"] .output-follow-btn`)

    Object.defineProperty(output, 'clientHeight', { configurable: true, get: () => 100 })
    Object.defineProperty(output, 'scrollHeight', { configurable: true, get: () => 300 })
    Object.defineProperty(output, 'scrollTop', { configurable: true, get: () => 0 })
    tab.rawLines.push({ text: 'line 1', cls: '', tsC: '', tsE: '' })
    tab.followOutput = false
    setTabStatus(id, 'running')
    updateOutputFollowButton(id)

    expect(button.hidden).toBe(false)
    expect(button.textContent).toBe('jump to live')
    expect(button.classList.contains('is-live')).toBe(true)
    expect(button.title).toBe('Jump to the live output tail')
  })

  it('hides the jump button when the output is already pinned to the bottom', () => {
    const { createTab, _getTabs, updateOutputFollowButton } = loadTabsFns()
    const id = createTab('tab 1')
    const tab = _getTabs()[0]
    const output = document.getElementById(`output-${id}`)
    const button = document.querySelector(`.tab-panel[data-id="${id}"] .output-follow-btn`)

    Object.defineProperty(output, 'clientHeight', { configurable: true, get: () => 100 })
    Object.defineProperty(output, 'scrollHeight', { configurable: true, get: () => 300 })
    Object.defineProperty(output, 'scrollTop', { configurable: true, get: () => 200 })
    tab.rawLines.push({ text: 'line 1', cls: '', tsC: '', tsE: '' })
    tab.followOutput = false

    updateOutputFollowButton(id)

    expect(button.hidden).toBe(true)
    expect(tab.followOutput).toBe(true)
  })

  it('returns the output to the tail when the jump button is clicked', () => {
    const { createTab, _getTabs, updateOutputFollowButton } = loadTabsFns()
    const id = createTab('tab 1')
    const tab = _getTabs()[0]
    const output = document.getElementById(`output-${id}`)
    const button = document.querySelector(`.tab-panel[data-id="${id}"] .output-follow-btn`)

    let scrollTop = 0
    Object.defineProperty(output, 'scrollHeight', { configurable: true, get: () => 300 })
    Object.defineProperty(output, 'scrollTop', {
      configurable: true,
      get: () => scrollTop,
      set: (value) => {
        scrollTop = value
      },
    })
    tab.rawLines.push({ text: 'line 1', cls: '', tsC: '', tsE: '' })
    tab.followOutput = false
    updateOutputFollowButton(id)

    button.click()

    expect(tab.followOutput).toBe(true)
    expect(scrollTop).toBe(300)
    expect(button.hidden).toBe(true)
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
      set: (value) => {
        scrollTop = value
        output.dispatchEvent(new Event('scroll'))
      },
    })

    _stickOutputToBottom(output, tab)

    expect(tab.suppressOutputScrollTracking).toBe(true)
    expect(tab.followOutput).toBe(true)
  })

  it('defers remounting the prompt until the output queue is drained', () => {
    const { createTab, mountShellPrompt, _maybeMountDeferredPrompt, _getTabs, shellPromptWrap } =
      loadTabsAndOutputFns()
    const id = createTab('tab 1')
    const tab = _getTabs()[0]
    tab.deferPromptMount = true

    mountShellPrompt(id)
    expect(shellPromptWrap.parentElement).not.toBe(document.getElementById(`output-${id}`))

    _maybeMountDeferredPrompt(id)
    expect(tab.deferPromptMount).toBe(false)
  })

  it('mountShellPrompt stays hidden during the desktop welcome boot', () => {
    const { createTab, mountShellPrompt, shellPromptWrap } = loadTabsFns({
      welcomeBootPending: true,
    })
    const id = createTab('tab 1')
    const output = document.querySelector(`.tab-panel[data-id="${id}"] .output`)

    mountShellPrompt(id)

    expect(output.contains(shellPromptWrap)).toBe(false)
  })

  it('renderRestoredTabOutput rebuilds prompt-echo lines with the prompt prefix span', () => {
    const { createTab, renderRestoredTabOutput } = loadTabsAndOutputFns()
    const id = createTab('tab 1')

    renderRestoredTabOutput(id, [
      { text: 'anon@darklab:~$ dig darklab.sh', cls: 'prompt-echo', tsC: '', tsE: '' },
    ])

    const promptLine = document.querySelector(`#output-${id} .line.prompt-echo`)
    expect(promptLine?.querySelector('.prompt-prefix')?.textContent).toBe('anon@darklab.sh:~ $')
    expect(promptLine?.textContent).toBe('anon@darklab.sh:~ $dig darklab.sh')
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

    expect(tab.rawLines.map((line) => line.text)).toEqual(['two', 'three', 'four'])
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

  it('uses shell-number defaults for new tabs', () => {
    const { createTab, createDefaultTabLabel, _getTabs } = loadTabsFns()

    const id = createTab()
    const secondId = createTab()

    expect(id).toBeTruthy()
    expect(secondId).toBeTruthy()
    expect(createDefaultTabLabel(2)).toBe('shell 2')
    expect([...document.querySelectorAll('.tab-label')].map(el => el.textContent)).toEqual([
      'shell 1',
      'shell 2',
    ])
    expect(_getTabs()[0].label).toBe('shell 1')
    expect(_getTabs()[1].label).toBe('shell 2')
  })

  it('numbers new default tabs from the highest currently open shell label', () => {
    const { createTab, closeTab, _getTabs } = loadTabsFns({ maxTabs: 5 })

    const firstId = createTab()
    createTab()
    const thirdId = createTab()

    closeTab(firstId)
    closeTab(thirdId)
    createTab()

    expect(_getTabs().map(tab => tab.label)).toEqual(['shell 2', 'shell 3'])
    expect([...document.querySelectorAll('.tab-label')].map(el => el.textContent)).toEqual([
      'shell 2',
      'shell 3',
    ])
  })

  it('avoids duplicate default labels after restoring a non-first shell tab', () => {
    const { createTab, _getTabs } = loadTabsFns({ maxTabs: 5 })

    createTab('shell 2')
    createTab()

    expect(_getTabs().map(tab => tab.label)).toEqual(['shell 2', 'shell 3'])
  })

  it('shows commands temporarily while preserving the stable default label', () => {
    vi.restoreAllMocks()
    vi.useFakeTimers()
    const { createTab, setTabRunningCommand, setTabStatus, _getTabs } = loadTabsFns()
    const id = createTab('shell 1')

    setTabRunningCommand(id, 'ping darklab.sh')
    setTabStatus(id, 'running')
    expect(document.querySelector('.tab-label').textContent).toBe('shell 1')
    vi.advanceTimersByTime(499)
    expect(document.querySelector('.tab-label').textContent).toBe('shell 1')
    vi.advanceTimersByTime(1)
    expect(document.querySelector('.tab-label').textContent).toBe('ping darklab.sh')
    expect(_getTabs()[0].label).toBe('shell 1')

    setTabStatus(id, 'ok')
    expect(document.querySelector('.tab-label').textContent).toBe('shell 1')
    expect(_getTabs()[0].runningLabel).toBe('')

    setTabRunningCommand(id, 'dig darklab.sh')
    setTabStatus(id, 'running')
    vi.advanceTimersByTime(500)
    expect(document.querySelector('.tab-label').textContent).toBe('dig darklab.sh')
    expect(_getTabs()[0].label).toBe('shell 1')

    setTabStatus(id, 'ok')
    expect(document.querySelector('.tab-label').textContent).toBe('shell 1')
  })

  it('does not flash the command label when a run finishes before the delay', () => {
    vi.restoreAllMocks()
    vi.useFakeTimers()
    const { createTab, setTabRunningCommand, setTabStatus, _getTabs } = loadTabsFns()
    const id = createTab('shell 1')

    setTabRunningCommand(id, 'hostname')
    setTabStatus(id, 'running')
    expect(document.querySelector('.tab-label').textContent).toBe('shell 1')

    setTabStatus(id, 'ok')
    vi.advanceTimersByTime(500)

    expect(document.querySelector('.tab-label').textContent).toBe('shell 1')
    expect(_getTabs()[0].runningLabel).toBe('')
  })

  it('shows the running command temporarily without overwriting a user rename', () => {
    vi.restoreAllMocks()
    vi.useFakeTimers()
    const { createTab, setTabLabel, setTabRunningCommand, setTabStatus, _getTabs } = loadTabsFns()
    const id = createTab('shell 1')
    const tab = _getTabs()[0]
    setTabLabel(id, 'ops')
    tab.renamed = true

    setTabRunningCommand(id, 'nmap example.com')
    setTabStatus(id, 'running')
    expect(document.querySelector('.tab-label').textContent).toBe('ops')
    vi.advanceTimersByTime(500)
    expect(document.querySelector('.tab-label').textContent).toBe('nmap example.com')
    expect(tab.label).toBe('ops')

    setTabStatus(id, 'ok')
    expect(document.querySelector('.tab-label').textContent).toBe('ops')
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
    await new Promise((resolve) => setImmediate(resolve))

    expect(document.getElementById('permalink-toast').textContent).toBe(
      'Failed to create permalink',
    )
  })

  it('permalinkTab falls back to execCommand when clipboard writeText rejects', async () => {
    const apiFetch = vi.fn(() =>
      Promise.resolve({ json: () => Promise.resolve({ url: '/share/abc' }) }),
    )
    document.execCommand = vi.fn(() => true)
    const { createTab, permalinkTab, _getTabs } = loadTabsFns({
      apiFetch,
      clipboardWrite: () => Promise.reject(new Error('clipboard denied')),
    })
    const id = createTab('tab 1')
    _getTabs()[0].rawLines.push({ text: 'line 1', cls: '', tsC: '', tsE: '' })

    permalinkTab(id)
    await new Promise((resolve) => setImmediate(resolve))
    await new Promise((resolve) => setImmediate(resolve))

    expect(document.execCommand).toHaveBeenCalledWith('copy')
    expect(document.getElementById('permalink-toast').textContent).toBe('Link copied to clipboard')
    expect(document.getElementById('permalink-toast').classList.contains('toast-error')).toBe(false)
  })

  it('permalinkTab can bypass redaction when the confirmation chooses raw sharing', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/share')
        return Promise.resolve({ json: () => Promise.resolve({ url: '/share/abc' }) })
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })
    const confirmPermalinkRedactionChoice = vi.fn(() => Promise.resolve('raw'))
    const { createTab, permalinkTab, _getTabs } = loadTabsFns({
      apiFetch,
      confirmPermalinkRedactionChoice,
      shareRedactionRules: [
        { pattern: '\\b\\d{1,3}(?:\\.\\d{1,3}){3}\\b', replacement: '[ip-redacted]' },
      ],
    })
    const id = createTab('tab 1')
    _getTabs()[0].rawLines.push({ text: 'connected to 203.0.113.10', cls: '', tsC: '', tsE: '' })

    permalinkTab(id)
    await new Promise((resolve) => setImmediate(resolve))
    await new Promise((resolve) => setImmediate(resolve))

    expect(confirmPermalinkRedactionChoice).toHaveBeenCalledTimes(1)
    const shareCall = apiFetch.mock.calls.find(([url]) => url === '/share')
    const payload = JSON.parse(shareCall[1].body)
    expect(payload.apply_redaction).toBe(false)
    expect(payload.content[0].text).toBe('connected to 203.0.113.10')
  })

  it('permalinkTab cancels sharing when the redaction confirmation is dismissed', async () => {
    const apiFetch = vi.fn(() =>
      Promise.resolve({ json: () => Promise.resolve({ url: '/share/abc' }) }),
    )
    const confirmPermalinkRedactionChoice = vi.fn(() => Promise.resolve(null))
    const { createTab, permalinkTab, _getTabs } = loadTabsFns({
      apiFetch,
      confirmPermalinkRedactionChoice,
    })
    const id = createTab('tab 1')
    const cmdInput = document.getElementById('cmd')
    _getTabs()[0].rawLines.push({ text: 'line 1', cls: '', tsC: '', tsE: '' })

    permalinkTab(id)
    await new Promise((resolve) => setImmediate(resolve))

    expect(apiFetch).not.toHaveBeenCalledWith('/share', expect.anything())
    expect(cmdInput.focus).toHaveBeenCalled()
  })

  it('permalinkTab does not append a truncation warning for a tab with full output already loaded', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/history/run-1?json') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
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
    tab.rawLines.push({
      text: '[preview truncated — only the last 2000 lines are shown here, but the full output had 6386 lines. Use the run history permalink for the full output]',
      cls: 'notice',
      tsC: '',
      tsE: '',
    })
    tab.rawLines.push({
      text: '[process exited with code 0 in 0.2s]',
      cls: 'exit-ok',
      tsC: '',
      tsE: '',
    })

    permalinkTab(id)
    await new Promise((resolve) => setImmediate(resolve))
    await new Promise((resolve) => setImmediate(resolve))

    expect(apiFetch).toHaveBeenCalledWith('/history/run-1?json')
    const shareCall = apiFetch.mock.calls.find(([url]) => url === '/share')
    expect(shareCall).toBeTruthy()
    const payload = JSON.parse(shareCall[1].body)
    expect(payload.apply_redaction).toBe(true)
    expect(payload.content).toHaveLength(5)
    expect(payload.content.map((entry) => entry.text)).toEqual([
      '$ tab 1',
      '',
      'full line 1',
      'full line 2',
      '[process exited with code 0 in 0.2s]',
    ])
    expect(
      payload.content.some((entry) => String(entry.text || '').includes('tab output truncated')),
    ).toBe(false)
    expect(
      payload.content.some((entry) => String(entry.text || '').includes('preview truncated')),
    ).toBe(false)
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
    await new Promise((resolve) => setImmediate(resolve))
    await new Promise((resolve) => setImmediate(resolve))
    expect(cmdInput.focus).toHaveBeenCalled()

    cmdInput.focus.mockClear()
    saveTab(id)
    await new Promise((resolve) => setImmediate(resolve))
    expect(cmdInput.focus).toHaveBeenCalled()

    cmdInput.focus.mockClear()
    window.ExportHtmlUtils = {
      escapeExportHtml: (s) => s,
      renderExportPromptEcho: (s) => s,
      normalizeExportTranscriptLines: (lines) => lines,
      buildExportDocumentModel: ({ appName, title, label, createdText, runMeta, rawLines }) => ({
        appName,
        title,
        metaLine: `${label} · ${createdText}`,
        runMeta,
        rawLines,
      }),
      buildExportMetaLine: ({ label, createdText }) => `${label} · ${createdText}`,
      fetchVendorFontFacesCss: () => Promise.resolve(''),
      fetchTerminalExportCss: () => Promise.resolve(''),
      buildExportLinesHtml: (lines) => ({ linesHtml: lines.map(l => l.text).join(''), prefixWidth: 0 }),
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
        '--theme-panel-bg': '#edf4fb',
        '--theme-panel-border': '#b7c7d6',
        '--theme-terminal-bar-bg': '#d9e5f1',
      },
    }

    const { buildTerminalExportStyles } = fromDomScripts(
      ['app/static/js/export_html.js'],
      {
        document,
      },
      'ExportHtmlUtils',
    )

    const css = buildTerminalExportStyles('theme_light_blue')
    expect(css).toContain('--bg: #b8c4d0;')
    expect(css).toContain('--surface: #eef2f6;')
    expect(css).toContain('--text: #101820;')
    expect(css).toContain('--green: #2a5d18;')
    expect(css).toContain('--theme-panel-bg: #edf4fb;')
    expect(css).toContain('--theme-panel-border: #b7c7d6;')
    expect(css).toContain('--theme-terminal-bar-bg: #d9e5f1;')

    delete window.ThemeCssVars
  })

  it('builds exported HTML with color-scheme metadata and themed shell surfaces', () => {
    window.ThemeRegistry = {
      current: {
        color_scheme: 'light',
        vars: {
          '--bg': '#eef4fa',
          '--text': '#1a2732',
          '--theme-panel-bg': '#edf4fb',
          '--theme-panel-border': '#c1d2e1',
          '--theme-terminal-bar-bg': '#d9e5f1',
          '--theme-terminal-bar-border': '#b8cad9',
          '--theme-panel-shadow': 'rgba(20, 36, 52, 0.18)',
        },
      },
    }

    const { buildTerminalExportHtml } = fromDomScripts(
      ['app/static/js/export_html.js'],
      {
        document,
        window,
      },
      'ExportHtmlUtils',
    )

    const html = buildTerminalExportHtml({
      appName: 'darklab_shell',
      title: 'share export',
      metaHtml: '<span>meta</span>',
      linesHtml: '<span class="line">hello</span>',
      exportCss: '.export-header { background: var(--theme-terminal-bar-bg, var(--bg)); }',
    })

    expect(html).toContain('<meta name="color-scheme" content="light">')
    expect(html).toContain('--bg: #eef4fa;')
    expect(html).toContain('--theme-panel-bg: #edf4fb;')
    expect(html).toContain('.export-header { background: var(--theme-terminal-bar-bg, var(--bg)); }')
    expect(html).toContain('<h1 class="export-title">darklab_shell</h1>')

    delete window.ThemeRegistry
  })

  it('builds a shared export header model with canonical run-meta ordering', () => {
    const { buildExportHeaderModel } = fromDomScripts(
      ['app/static/js/export_html.js'],
      {
        document,
        window,
      },
      'ExportHtmlUtils',
    )

    const header = buildExportHeaderModel({
      appName: 'darklab_shell',
      metaLine: 'scan  ·  1/1/2026, 10:00:00 AM',
      runMeta: { exitCode: 0, duration: '1.2s', lines: '42 lines', version: '1.5' },
    })

    expect(header).toEqual({
      appName: 'darklab_shell',
      metaLine: 'scan  ·  1/1/2026, 10:00:00 AM',
      runMetaItems: [
        { kind: 'badge', tone: 'ok', text: 'exit 0' },
        { kind: 'item', text: '1.2s' },
        { kind: 'item', text: '42 lines' },
        { kind: 'item', text: 'v1.5' },
      ],
    })
  })

  it('renders export header html with the same title/meta/run-meta structure as permalink pages', () => {
    const { buildTerminalExportHeaderHtml } = fromDomScripts(
      ['app/static/js/export_html.js'],
      {
        document,
        window,
      },
      'ExportHtmlUtils',
    )

    const html = buildTerminalExportHeaderHtml({
      appName: 'darklab_shell',
      metaLine: 'scan  ·  1/1/2026, 10:00:00 AM',
      runMetaItems: [
        { kind: 'badge', tone: 'fail', text: 'exit 1' },
        { kind: 'item', text: '9 lines' },
      ],
    })

    expect(html).toContain('<header class="export-header">')
    expect(html).toContain('<h1 class="export-title">darklab_shell</h1>')
    expect(html).toContain('<div class="export-meta">scan  ·  1/1/2026, 10:00:00 AM</div>')
    expect(html).toContain('<div class="export-run-meta">')
    expect(html).toContain('meta-badge-fail')
    expect(html).toContain('exit 1')
    expect(html).toContain('9 lines')
  })

  it('saveTab shows a toast when there is only welcome output', () => {
    const { createTab, saveTab, _getTabs } = loadTabsFns()
    const id = createTab('tab 1')
    _getTabs()[0].rawLines.push({ text: '# Welcome hint', cls: 'welcome-hint', tsC: '', tsE: '' })

    saveTab(id)

    expect(document.getElementById('permalink-toast').textContent).toBe('No output to export')
  })

  it('saveTab does not apply redaction rules to exported text', async () => {
    let savedBlob = null
    const { createTab, saveTab, _getTabs } = loadTabsFns({
      shareRedactionRules: [{ pattern: 'Bearer\\s+\\S+', replacement: 'Bearer [redacted]' }],
      urlImpl: {
        createObjectURL: (blob) => {
          savedBlob = blob
          return 'blob:mock'
        },
        revokeObjectURL: () => {},
      },
    })
    const id = createTab('tab 1')
    _getTabs()[0].rawLines.push({ text: 'Authorization: Bearer abc123', cls: '', tsC: '', tsE: '' })

    saveTab(id)

    await expect(savedBlob.text()).resolves.toBe('Authorization: Bearer abc123')
  })

  it('exportTabHtml does not apply redaction rules to rendered HTML output', async () => {
    window.ExportHtmlUtils = {
      escapeExportHtml: (s) => s,
      renderExportPromptEcho: (s) => s,
      normalizeExportTranscriptLines: (lines) => lines,
      buildExportDocumentModel: ({ appName, title, label, createdText, runMeta, rawLines }) => ({
        appName,
        title,
        metaLine: `${label} · ${createdText}`,
        runMeta,
        rawLines,
      }),
      buildExportMetaLine: ({ label, createdText }) => `${label} · ${createdText}`,
      fetchVendorFontFacesCss: () => Promise.resolve(''),
      fetchTerminalExportCss: () => Promise.resolve(''),
      buildExportLinesHtml: (lines) => ({ linesHtml: lines.map(l => l.text).join(''), prefixWidth: 0 }),
      buildTerminalExportHtml: ({ linesHtml }) => linesHtml,
      exportTimestamp: () => '2026-01-01-00-00-00',
    }
    let savedBlob = null
    const { createTab, exportTabHtml, _getTabs } = loadTabsFns({
      shareRedactionRules: [{ pattern: 'token=\\w+', replacement: 'token=[redacted]' }],
      urlImpl: {
        createObjectURL: (blob) => {
          savedBlob = blob
          return 'blob:mock'
        },
        revokeObjectURL: () => {},
      },
    })
    const id = createTab('tab 1')
    _getTabs()[0].rawLines.push({ text: 'token=abc123', cls: '', tsC: '', tsE: '' })

    await exportTabHtml(id)

    const html = await savedBlob.text()
    expect(html).toContain('token=abc123')
    expect(html).not.toContain('token=[redacted]')
    delete window.ExportHtmlUtils
  })

  it('exportTabHtml shows a toast when the tab has no lines', async () => {
    window.ExportHtmlUtils = {
      buildExportDocumentModel: ({ appName, title, label, createdText, runMeta, rawLines }) => ({
        appName,
        title,
        metaLine: `${label} · ${createdText}`,
        runMeta,
        rawLines,
      }),
      buildExportMetaLine: ({ label, createdText }) => `${label} · ${createdText}`,
      fetchVendorFontFacesCss: () => Promise.resolve(''),
      fetchTerminalExportCss: () => Promise.resolve(''),
      buildExportLinesHtml: (lines) => ({ linesHtml: '', prefixWidth: 0 }),
      buildTerminalExportHtml: () => '',
      exportTimestamp: () => '2026-01-01-00-00-00',
    }
    const { createTab, exportTabHtml } = loadTabsFns()
    const id = createTab('tab 1')

    await exportTabHtml(id)

    expect(document.getElementById('permalink-toast').textContent).toBe('No output to export')
    delete window.ExportHtmlUtils
  })

  it('exportTabHtml shows a toast when ExportHtmlUtils is not loaded', async () => {
    delete window.ExportHtmlUtils
    const { createTab, exportTabHtml, _getTabs } = loadTabsFns()
    const id = createTab('tab 1')
    _getTabs()[0].rawLines.push({ text: 'hello', cls: '', tsC: '', tsE: '' })

    await exportTabHtml(id)

    expect(document.getElementById('permalink-toast').textContent).toBe('Failed to export html')
  })

  it('exportTabPdf shows a toast when the tab has no lines', () => {
    const { createTab, exportTabPdf } = loadTabsFns()
    const id = createTab('tab 1')

    exportTabPdf(id)

    expect(document.getElementById('permalink-toast').textContent).toBe('No output to export')
  })

  it('exportTabPdf shows a toast when jsPDF is not loaded', () => {
    delete window.jspdf
    const { createTab, exportTabPdf, _getTabs } = loadTabsFns()
    const id = createTab('tab 1')
    _getTabs()[0].rawLines.push({ text: 'hello', cls: '', tsC: '', tsE: '' })

    exportTabPdf(id)

    expect(document.getElementById('permalink-toast').textContent).toBe('PDF library not loaded')
  })

  it('permalinkTab applies configured redaction rules before creating a snapshot', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/share')
        return Promise.resolve({ json: () => Promise.resolve({ url: '/share/abc' }) })
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })
    const { createTab, permalinkTab, _getTabs } = loadTabsFns({
      apiFetch,
      shareRedactionRules: [
        { pattern: '\\b\\d{1,3}(?:\\.\\d{1,3}){3}\\b', replacement: '[ip-redacted]' },
      ],
    })
    const id = createTab('tab 1')
    _getTabs()[0].rawLines.push({ text: 'connected to 203.0.113.10', cls: '', tsC: '', tsE: '' })

    permalinkTab(id)
    await new Promise((resolve) => setImmediate(resolve))
    await new Promise((resolve) => setImmediate(resolve))

    const shareCall = apiFetch.mock.calls.find(([url]) => url === '/share')
    const payload = JSON.parse(shareCall[1].body)
    expect(payload.apply_redaction).toBe(true)
    expect(payload.content[0].text).toBe('connected to [ip-redacted]')
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
    vi.useFakeTimers()
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
    document.body.classList.add('mobile-terminal-mode')

    const dragged = document.querySelector(`.tab[data-id="${thirdId}"]`)
    dragged.dispatchEvent(touchEvent('touchstart', [{ identifier: 7, clientX: 250, clientY: 12 }]))
    vi.advanceTimersByTime(200)
    document.dispatchEvent(touchEvent('touchmove', [{ identifier: 7, clientX: 20, clientY: 12 }]))

    expect(dragged.classList.contains('tab-touch-dragging')).toBe(true)
    expect(document.getElementById('tabs-bar').classList.contains('tabs-bar-touch-sorting')).toBe(
      true,
    )
    expect(
      document.querySelector(`.tab[data-id="${firstId}"]`)?.classList.contains('tab-drop-before'),
    ).toBe(true)

    document.dispatchEvent(
      touchEvent('touchend', [], [{ identifier: 7, clientX: 20, clientY: 12 }]),
    )

    expect(_getTabs().map((tab) => tab.id)).toEqual([thirdId, firstId, secondId])
    expect(document.querySelector('.tab')?.dataset.id).toBe(thirdId)
    expect(document.getElementById('cmd').focus).toHaveBeenCalled()
    expect(document.getElementById('tabs-bar').classList.contains('tabs-bar-touch-sorting')).toBe(
      false,
    )
    expect(document.querySelector('.tab-drop-before, .tab-drop-after')).toBeNull()
    vi.useRealTimers()
  })

  it('reorders desktop tabs through pointer dragging', () => {
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

    const dragged = document.querySelector(`.tab[data-id="${thirdId}"]`)
    dragged.dispatchEvent(
      touchPointerEvent('pointerdown', {
        pointerId: 9,
        pointerType: 'mouse',
        button: 0,
        clientX: 250,
        clientY: 12,
      }),
    )
    document.dispatchEvent(
      touchPointerEvent('pointermove', {
        pointerId: 9,
        pointerType: 'mouse',
        clientX: 20,
        clientY: 12,
      }),
    )

    expect(dragged.classList.contains('tab-pointer-dragging')).toBe(true)
    expect(document.querySelector('.tab')?.dataset.id).toBe(thirdId)
    expect(
      document.querySelector(`.tab[data-id="${firstId}"]`)?.classList.contains('tab-drop-before'),
    ).toBe(true)

    document.dispatchEvent(
      touchPointerEvent('pointerup', {
        pointerId: 9,
        pointerType: 'mouse',
        clientX: 20,
        clientY: 12,
      }),
    )

    expect(_getTabs().map((tab) => tab.id)).toEqual([thirdId, firstId, secondId])
    expect(document.querySelector('.tab')?.dataset.id).toBe(thirdId)
    expect(document.querySelector('.tab-drop-before, .tab-drop-after')).toBeNull()
  })
})
