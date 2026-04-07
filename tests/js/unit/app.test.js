import { MemoryStorage, fromDomScripts } from './helpers/extract.js'

async function loadAppFns({
  theme = null,
  cookies = {},
  apiFetch: apiFetchOverride = null,
  doKill: doKillOverride = vi.fn(),
  pendingKillTabId = null,
  requestWelcomeSettle: requestWelcomeSettleOverride = vi.fn(),
  tabs: tabsOverride = [],
  confirmKill: confirmKillOverride = vi.fn(),
  interruptPromptLine: interruptPromptLineOverride = vi.fn(),
  welcomeActive = false,
  welcomeOwnsTab: welcomeOwnsTabOverride = () => false,
  runCommand: runCommandOverride = vi.fn(),
  createTab: createTabOverride = vi.fn(() => 'tab-1'),
  closeTab: closeTabOverride = vi.fn(),
  activateTab: activateTabOverride = vi.fn(),
  permalinkTab: permalinkTabOverride = vi.fn(),
  copyTab: copyTabOverride = vi.fn(),
  clearTab: clearTabOverride = vi.fn(),
  cancelWelcome: cancelWelcomeOverride = vi.fn(),
  activeTabId = 'tab-1',
  acFiltered: acFilteredOverride = [],
  acIndex: acIndexOverride = -1,
  acShow: acShowOverride = () => {},
  acHide: acHideOverride = () => {},
  mobileViewport = null,
  mobileTouch = true,
} = {}) {
  document.body.className = ''
  document.body.innerHTML = `
    <header><h1></h1></header>
    <button id="ts-btn"></button>
    <button id="theme-btn"></button>
    <button id="options-btn"></button>
    <button id="faq-btn"></button>
    <button id="hamburger-btn"></button>
    <button id="new-tab-btn"></button>
    <button id="search-toggle-btn"></button>
    <button id="hist-btn"></button>
    <button id="ln-btn"></button>
    <button id="history-close"></button>
    <button id="hist-clear-all-btn"></button>
    <button id="hist-del-cancel"></button>
    <button id="hist-del-nonfav"></button>
    <button id="hist-del-confirm"></button>
    <button id="kill-cancel"></button>
    <button id="kill-confirm"></button>
    <div id="version-label"></div>
    <div id="motd"></div>
    <div id="motd-wrap"></div>
    <div id="mobile-shell" aria-hidden="true"></div>
    <div class="terminal-wrap">
      <div id="history-row" class="history-row" style="display:none">
        <span class="history-label">Recent:</span>
      </div>
      <div class="terminal-bar">
        <span class="dot dot-r"></span>
        <span class="dot dot-y"></span>
        <span class="dot dot-g"></span>
        <button id="tabs-scroll-left"></button>
        <div class="tabs-bar" id="tabs-bar"></div>
        <button id="tabs-scroll-right"></button>
        <div class="terminal-bar-btns"></div>
        <span id="status"></span>
        <span id="run-timer"></span>
      </div>
      <div id="shell-prompt-wrap" class="prompt-wrap shell-prompt-wrap">
        <span class="prompt-prefix" data-mobile-label="$">anon@shell.darklab.sh:~$</span>
        <div id="shell-prompt-line">
          <span id="shell-prompt-text" class="shell-prompt-text"></span>
          <span id="shell-prompt-caret"></span>
          <span id="shell-prompt-ghost" class="shell-prompt-ghost"></span>
        </div>
        <div id="ac-dropdown" style="display:none"></div>
        <button id="run-btn" aria-label="Run command">Run</button>
      </div>
      <div class="search-bar" id="search-bar" style="display:none">
        <input id="search-input" type="text" placeholder="Search output…" autocomplete="off" aria-label="Search output">
        <div class="search-toggles">
          <button id="search-case-btn"></button>
          <button id="search-regex-btn"></button>
        </div>
        <span class="search-count" id="search-count"></span>
        <div class="search-nav">
          <button id="search-prev"></button>
          <button id="search-next"></button>
        </div>
      </div>
      <div id="tab-panels"></div>
    <div id="mobile-composer-host">
        <div id="mobile-edit-bar">
          <button data-edit-action="home"></button>
          <button data-edit-action="left"></button>
          <button data-edit-action="right"></button>
          <button data-edit-action="end"></button>
          <button data-edit-action="delete-word"></button>
        </div>
        <div id="mobile-composer-row">
          <button id="mobile-run-btn"></button>
        </div>
      </div>
      <div id="faq-limits-text"></div>
      <div id="faq-allowed-text"></div>
      <div id="mobile-menu">
        <button data-action="ln"></button>
        <button data-action="ts"></button>
        <button data-action="search"></button>
        <button data-action="history"></button>
        <button data-action="options"></button>
        <button data-action="theme"></button>
        <button data-action="faq"></button>
      </div>
      <div id="faq-overlay"></div>
      <button class="faq-close"></button>
      <div class="faq-body"></div>
      <div id="options-overlay"></div>
      <button class="options-close"></button>
      <div id="options-modal"></div>
      <select id="options-ts-select">
        <option value="off">off</option>
        <option value="elapsed">elapsed</option>
        <option value="clock">clock</option>
      </select>
      <input id="options-ln-toggle" type="checkbox" />
      <label><input type="radio" name="theme-pref" value="dark" /></label>
      <label><input type="radio" name="theme-pref" value="light" /></label>
      <div id="shell-input-row" data-mobile-label="$">
        <input id="cmd" />
      </div>
      <div id="history-panel"></div>
      <div id="history-list"></div>
      <div id="kill-overlay"></div>
      <div id="hist-del-overlay"></div>
      <div class="prompt-wrap"></div>
    </div>
  `

  const storage = new MemoryStorage()
  if (theme !== null) storage.setItem('theme', theme)
  for (const [name, value] of Object.entries(cookies)) {
    document.cookie = `${name}=${encodeURIComponent(value)}; path=/`
  }

  const apiFetch = apiFetchOverride || vi.fn((url) => {
    if (url === '/config') {
      return Promise.resolve({
        json: () => Promise.resolve({
          app_name: 'shell.darklab.sh',
          version: '9.9',
          default_theme: 'dark',
          motd: '',
          command_timeout_seconds: 0,
          max_output_lines: 0,
          permalink_retention_days: 0,
        }),
      })
    }
    if (url === '/allowed-commands') {
      return Promise.resolve({ json: () => Promise.resolve({ restricted: false, commands: [], groups: [] }) })
    }
    if (url === '/faq') {
      return Promise.resolve({ json: () => Promise.resolve({ items: [] }) })
    }
    return Promise.resolve({ json: () => Promise.resolve({}) })
  })

  const runSearch = vi.fn()
  const clearSearch = vi.fn()
  const navigateSearch = vi.fn()
  const logClientError = vi.fn()
  const cmdInput = document.getElementById('cmd')
  const acDropdown = document.getElementById('ac-dropdown')
  cmdInput.focus = vi.fn()
  cmdInput.blur = vi.fn()
  const shellPromptWrapEl = document.getElementById('shell-prompt-wrap')
  shellPromptWrapEl.scrollIntoView = vi.fn()
  const mobileComposerHostEl = document.getElementById('mobile-composer-host')
  mobileComposerHostEl.scrollIntoView = vi.fn()

  const originalMatchMedia = window.matchMedia
  const originalVisualViewport = window.visualViewport
  const originalScrollTo = window.scrollTo
  const originalMaxTouchPoints = navigator.maxTouchPoints
  window.scrollTo = vi.fn()
  if (mobileViewport) {
    const matchMediaMock = vi.fn(query => {
      const q = String(query || '')
      const maxWidth = /max-width:\s*900px/.test(q)
      const coarse = /pointer:\s*coarse/.test(q)
      return {
        matches: mobileTouch ? (maxWidth || coarse) : maxWidth,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }
    })
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: matchMediaMock,
    })
    if (mobileTouch) {
      Object.defineProperty(window.navigator, 'maxTouchPoints', {
        configurable: true,
        value: 5,
      })
    }
    Object.defineProperty(window, 'visualViewport', {
      configurable: true,
      value: {
        height: mobileViewport.height,
        offsetTop: mobileViewport.offsetTop ?? 0,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      },
    })
  }

  class FakeAnsiUp {
    constructor() {
      this.use_classes = false
    }

    ansi_to_html(text) {
      return text
    }
  }

  const fns = fromDomScripts([
    'app/static/js/output.js',
    'app/static/js/app.js',
  ], {
    document,
    localStorage: storage,
    apiFetch,
    APP_CONFIG: {},
    AnsiUp: FakeAnsiUp,
    getOutput: () => document.getElementById('history-list'),
    renderMotd: (text) => text,
    updateNewTabBtn: () => {},
    createTab: createTabOverride,
    runWelcome: () => {},
    closeFaq: () => {},
    openFaq: () => {},
    cmdInput,
    runBtn: document.getElementById('run-btn'),
    shellInputRow: document.getElementById('shell-input-row'),
    searchBar: document.getElementById('search-bar'),
    searchInput: document.getElementById('search-input'),
    searchCaseBtn: document.getElementById('search-case-btn'),
    searchRegexBtn: document.getElementById('search-regex-btn'),
    historyPanel: document.getElementById('history-panel'),
    runSearch,
    clearSearch,
    refreshHistoryPanel: () => {},
    navigateSearch,
    searchCaseSensitive: false,
    searchRegexMode: false,
    confirmHistAction: vi.fn(),
    executeHistAction: vi.fn(),
    histDelOverlay: document.getElementById('hist-del-overlay'),
    killOverlay: document.getElementById('kill-overlay'),
    pendingHistAction: null,
    pendingKillTabId,
    acHide: acHideOverride,
    acSuggestions: [],
    acFiltered: acFilteredOverride,
    acIndex: acIndexOverride,
    acShow: acShowOverride,
    acAccept: () => {},
    resetCmdHistoryNav: () => {},
    navigateCmdHistory: () => false,
    logClientError,
    tabs: tabsOverride,
    activeTabId,
    confirmKill: confirmKillOverride,
    closeTab: closeTabOverride,
    activateTab: activateTabOverride,
    permalinkTab: permalinkTabOverride,
    copyTab: copyTabOverride,
    clearTab: clearTabOverride,
    cancelWelcome: cancelWelcomeOverride,
    interruptPromptLine: interruptPromptLineOverride,
    _welcomeActive: welcomeActive,
    welcomeOwnsTab: welcomeOwnsTabOverride,
    shellPromptWrap: shellPromptWrapEl,
    shellPromptText: document.getElementById('shell-prompt-text'),
    shellPromptCaret: document.getElementById('shell-prompt-caret'),
    terminalWrap: document.querySelector('.terminal-wrap'),
    terminalBar: document.querySelector('.terminal-bar'),
    histRow: document.getElementById('history-row'),
    tabPanels: document.getElementById('tab-panels'),
    mobileShell: document.getElementById('mobile-shell'),
    mobileComposerHost: document.getElementById('mobile-composer-host'),
    mobileComposerRow: document.getElementById('mobile-composer-row'),
    mobileEditBar: document.getElementById('mobile-edit-bar'),
    mobileComposerHostEl,
    acDropdown,
    requestWelcomeSettle: requestWelcomeSettleOverride,
    runCommand: runCommandOverride,
    doKill: doKillOverride,
    Event,
    setTimeout: (fn) => {
      fn()
      return 0
    },
  }, `{
    _setTsMode,
    _setLnMode,
    setRunButtonDisabled,
    confirmHistAction,
    executeHistAction,
    doKill,
    _getAcIndex: () => acIndex,
  }`)

  await Promise.resolve()
  await Promise.resolve()

    return {
    ...fns,
    storage,
    apiFetch,
    runSearch,
    clearSearch,
    navigateSearch,
    cmdInput,
    requestWelcomeSettle: requestWelcomeSettleOverride,
    confirmKill: confirmKillOverride,
    createTab: createTabOverride,
    closeTab: closeTabOverride,
    activateTab: activateTabOverride,
    permalinkTab: permalinkTabOverride,
    copyTab: copyTabOverride,
    clearTab: clearTabOverride,
    cancelWelcome: cancelWelcomeOverride,
    interruptPromptLine: interruptPromptLineOverride,
    runCommand: runCommandOverride,
    logClientError,
    acDropdown,
    acHide: acHideOverride,
    shellPromptWrap: shellPromptWrapEl,
    restoreViewport: () => {
      if (originalMatchMedia === undefined) delete window.matchMedia
      else Object.defineProperty(window, 'matchMedia', { configurable: true, value: originalMatchMedia })
      if (originalVisualViewport === undefined) delete window.visualViewport
      else Object.defineProperty(window, 'visualViewport', { configurable: true, value: originalVisualViewport })
      if (originalScrollTo === undefined) delete window.scrollTo
      else window.scrollTo = originalScrollTo
      if (mobileTouch) {
        if (originalMaxTouchPoints === undefined) delete window.navigator.maxTouchPoints
        else Object.defineProperty(window.navigator, 'maxTouchPoints', { configurable: true, value: originalMaxTouchPoints })
      }
    },
  }
}

describe('app helpers', () => {
  beforeEach(() => {
    ;['pref_theme', 'pref_timestamps', 'pref_line_numbers'].forEach(name => {
      document.cookie = `${name}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`
    })
  })

  it('applies the saved light theme at startup', async () => {
    await loadAppFns({ theme: 'light' })

    expect(document.body.classList.contains('light')).toBe(true)
  })

  it('applies saved timestamp and line number preferences from cookies at startup', async () => {
    await loadAppFns({ cookies: { pref_timestamps: 'clock', pref_line_numbers: 'on' } })

    expect(document.body.classList.contains('ts-clock')).toBe(true)
    expect(document.body.classList.contains('ln-on')).toBe(true)
    expect(document.getElementById('ts-btn').textContent).toBe('timestamps: clock')
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers: on')
  })

  it('_setTsMode updates body classes and button labels', async () => {
    const { _setTsMode } = await loadAppFns()

    _setTsMode('elapsed')

    expect(document.body.classList.contains('ts-elapsed')).toBe(true)
    expect(document.body.classList.contains('ts-clock')).toBe(false)
    expect(document.getElementById('ts-btn').textContent).toBe('timestamps: elapsed')
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers: off')
    expect(document.querySelector('#mobile-menu [data-action="ts"]').textContent).toBe('timestamps: elapsed')
  })

  it('_setLnMode updates body classes and button labels', async () => {
    const { _setLnMode } = await loadAppFns()

    _setLnMode('on')

    expect(document.body.classList.contains('ln-on')).toBe(true)
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers: on')
    expect(document.querySelector('#mobile-menu [data-action="ln"]').textContent).toBe('line numbers: on')

    _setLnMode('off')

    expect(document.body.classList.contains('ln-on')).toBe(false)
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers: off')
  })

  it('allows timestamps and line numbers to be enabled at the same time', async () => {
    const { _setLnMode, _setTsMode } = await loadAppFns()

    _setLnMode('on')
    _setTsMode('elapsed')

    expect(document.body.classList.contains('ln-on')).toBe(true)
    expect(document.body.classList.contains('ts-elapsed')).toBe(true)
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers: on')
    expect(document.getElementById('ts-btn').textContent).toBe('timestamps: elapsed')
  })

  it('refocuses the terminal input after toggling timestamps and line numbers', async () => {
    const { cmdInput } = await loadAppFns()

    document.getElementById('ts-btn').click()
    expect(cmdInput.focus).toHaveBeenCalled()

    cmdInput.focus.mockClear()
    document.getElementById('ln-btn').click()
    expect(cmdInput.focus).toHaveBeenCalled()

    cmdInput.focus.mockClear()
    document.querySelector('#mobile-menu [data-action="ts"]').click()
    expect(cmdInput.focus).toHaveBeenCalled()

    cmdInput.focus.mockClear()
    document.querySelector('#mobile-menu [data-action="ln"]').click()
    expect(cmdInput.focus).toHaveBeenCalled()
  })

  it('refocuses the terminal input after toggling theme', async () => {
    const { cmdInput } = await loadAppFns()

    document.getElementById('theme-btn').click()
    expect(cmdInput.focus).toHaveBeenCalled()

    cmdInput.focus.mockClear()
    document.querySelector('#mobile-menu [data-action="theme"]').click()
    expect(cmdInput.focus).toHaveBeenCalled()
  })

  it('refocuses the terminal input after closing the FAQ modal', async () => {
    const { cmdInput } = await loadAppFns()
    const faqOverlay = document.getElementById('faq-overlay')

    document.getElementById('faq-btn').click()
    expect(faqOverlay.classList.contains('open')).toBe(true)

    document.querySelector('.faq-close').click()
    expect(faqOverlay.classList.contains('open')).toBe(false)
    expect(cmdInput.focus).toHaveBeenCalled()

    cmdInput.focus.mockClear()
    document.getElementById('faq-btn').click()
    faqOverlay.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(faqOverlay.classList.contains('open')).toBe(false)
    expect(cmdInput.focus).toHaveBeenCalled()
  })

  it('_setTsMode marks the timestamps button inactive in off mode', async () => {
    const { _setTsMode } = await loadAppFns()
    const tsBtn = document.getElementById('ts-btn')

    _setTsMode('off')

    expect(tsBtn.classList.contains('active')).toBe(false)
    expect(tsBtn.textContent).toBe('timestamps: off')
  })

  it('bootstraps cleanly when config and allowed-commands fetches fail', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/config' || url === '/allowed-commands' || url === '/autocomplete') {
        return Promise.reject(new Error('network down'))
      }
      if (url === '/faq') {
        return Promise.resolve({ json: () => Promise.resolve({ items: [] }) })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })

    document.body.innerHTML = `
      <header><h1></h1></header>
      <button id="ts-btn"></button>
      <button id="theme-btn"></button>
      <button id="faq-btn"></button>
      <button id="hamburger-btn"></button>
      <button id="new-tab-btn"></button>
      <button id="search-toggle-btn"></button>
      <button id="run-btn"></button>
      <button id="search-prev"></button>
      <button id="search-next"></button>
      <button id="hist-btn"></button>
      <button id="ln-btn"></button>
      <button id="history-close"></button>
      <button id="hist-clear-all-btn"></button>
      <button id="hist-del-cancel"></button>
      <button id="hist-del-nonfav"></button>
      <button id="hist-del-confirm"></button>
      <button id="kill-cancel"></button>
      <button id="kill-confirm"></button>
      <div id="version-label"></div>
      <div id="motd"></div>
      <div id="motd-wrap"></div>
      <div id="faq-limits-text"></div>
      <div id="faq-allowed-text"></div>
      <div id="mobile-menu">
        <button data-action="ln"></button>
        <button data-action="ts"></button>
        <button data-action="search"></button>
        <button data-action="history"></button>
        <button data-action="theme"></button>
        <button data-action="faq"></button>
      </div>
      <div id="faq-overlay"></div>
      <button class="faq-close"></button>
      <div class="faq-body"></div>
      <input id="cmd" />
      <div id="history-panel"></div>
      <div id="history-list"></div>
      <div id="kill-overlay"></div>
      <div id="hist-del-overlay"></div>
      <div id="search-bar"></div>
      <input id="search-input" />
      <span id="search-count"></span>
      <button id="search-case-btn"></button>
      <button id="search-regex-btn"></button>
      <div class="prompt-wrap"></div>
    `

    const { storage, logClientError } = await loadAppFns({ apiFetch })
    await Promise.resolve()
    await Promise.resolve()

    expect(apiFetch).toHaveBeenCalledWith('/config')
    expect(apiFetch).toHaveBeenCalledWith('/allowed-commands')
    expect(apiFetch).toHaveBeenCalledWith('/autocomplete')
    expect(logClientError).toHaveBeenCalledWith('failed to load /config', expect.any(Error))
    expect(logClientError).toHaveBeenCalledWith('failed to load /allowed-commands', expect.any(Error))
    expect(logClientError).toHaveBeenCalledWith('failed to load /autocomplete', expect.any(Error))
    expect(document.body.classList.contains('light')).toBe(false)
    expect(storage.getItem('theme')).toBeNull()
  })

  it('settles the welcome intro immediately when the user types into the active welcome tab', async () => {
    const requestWelcomeSettle = vi.fn()
    const { cmdInput } = await loadAppFns({ requestWelcomeSettle })

    cmdInput.value = 'dig '
    cmdInput.dispatchEvent(new Event('input', { bubbles: true }))

    expect(requestWelcomeSettle).toHaveBeenCalledWith('tab-1')
  })

  it('settles welcome immediately when Enter is pressed during welcome playback', async () => {
    const requestWelcomeSettle = vi.fn()
    const welcomeOwnsTab = vi.fn(() => true)
    const { cmdInput } = await loadAppFns({
      requestWelcomeSettle,
      welcomeActive: true,
      welcomeOwnsTab,
    })

    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))

    expect(welcomeOwnsTab).toHaveBeenCalledWith('tab-1')
    expect(requestWelcomeSettle).toHaveBeenCalledWith('tab-1')
    expect(cmdInput.focus).toHaveBeenCalled()
  })

  it('does not run command when Enter is pressed in cmd input during welcome playback', async () => {
    const requestWelcomeSettle = vi.fn()
    const welcomeOwnsTab = vi.fn(() => true)
    const runCommand = vi.fn()
    const { cmdInput } = await loadAppFns({
      requestWelcomeSettle,
      welcomeActive: true,
      welcomeOwnsTab,
      runCommand,
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))

    expect(requestWelcomeSettle).toHaveBeenCalledWith('tab-1')
    expect(runCommand).not.toHaveBeenCalled()
  })

  it('mirrors the hidden command input into the shell prompt line', async () => {
    const { cmdInput } = await loadAppFns()
    const shellPromptText = document.getElementById('shell-prompt-text')
    const shellPromptWrap = document.getElementById('shell-prompt-wrap')

    expect(shellPromptText.textContent).toBe('')
    expect(shellPromptWrap.classList.contains('shell-prompt-empty')).toBe(true)

    cmdInput.value = 'ping darklab.sh'
    cmdInput.setSelectionRange(cmdInput.value.length, cmdInput.value.length)
    cmdInput.dispatchEvent(new Event('input'))

    expect(shellPromptText.textContent).toBe('ping darklab.sh')
    expect(shellPromptWrap.classList.contains('shell-prompt-empty')).toBe(false)
  })

  it('updates the visible cursor when the selection changes without typing', async () => {
    const { cmdInput } = await loadAppFns()
    const shellPromptText = document.getElementById('shell-prompt-text')

    cmdInput.value = 'curl darklab.sh'
    cmdInput.setSelectionRange(4, 4)
    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => cmdInput,
    })
    document.dispatchEvent(new Event('selectionchange'))

    expect(shellPromptText.textContent).toContain('curl')
    expect(shellPromptText.textContent).toContain('darklab.sh')
    expect(shellPromptText.querySelector('.shell-caret-char')?.textContent || '').toBe(' ')
  })

  it('tracks mobile keyboard state and keeps the prompt visible while typing', async () => {
    const { cmdInput, shellPromptWrap, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const runBtn = document.getElementById('run-btn')
    const terminalWrap = document.querySelector('.terminal-wrap')
    const mobileShell = document.getElementById('mobile-shell')
    const mobileComposerHost = document.getElementById('mobile-composer-host')
    const mobileComposerRow = document.getElementById('mobile-composer-row')
    const shellInputRow = document.getElementById('shell-input-row')
    const promptPrefix = shellInputRow
    const histRow = document.getElementById('history-row')
    const terminalBar = document.querySelector('.terminal-bar')
    const searchBar = document.getElementById('search-bar')
    const tabPanels = document.getElementById('tab-panels')

    cmdInput.dispatchEvent(new Event('focus'))
    cmdInput.value = 'curl'
    cmdInput.dispatchEvent(new Event('input'))

    expect(document.body.classList.contains('mobile-terminal-mode')).toBe(true)
    expect(document.body.classList.contains('mobile-keyboard-open')).toBe(true)
    expect(document.documentElement.style.getPropertyValue('--mobile-keyboard-offset')).toBe('268px')
    expect(terminalWrap.hidden).toBe(true)
    expect(mobileShell.hidden).toBe(false)
    expect(runBtn.hidden).toBe(false)
    expect(mobileComposerHost.getAttribute('aria-hidden')).toBe('false')
    expect(shellPromptWrap.getAttribute('aria-hidden')).toBe('true')
    expect(mobileComposerRow.hidden).toBe(false)
    expect(mobileShell.contains(histRow)).toBe(true)
    expect(mobileShell.contains(terminalBar)).toBe(true)
    expect(mobileShell.contains(searchBar)).toBe(true)
    expect(mobileShell.contains(tabPanels)).toBe(true)
    expect(mobileShell.contains(mobileComposerHost)).toBe(true)
    expect(mobileComposerRow.contains(shellInputRow)).toBe(true)
    expect(mobileComposerRow.contains(runBtn)).toBe(true)
    expect(shellInputRow.getAttribute('aria-hidden')).toBe(null)
    expect(promptPrefix.getAttribute('data-mobile-label')).toBe('$')
    expect(shellPromptWrap.scrollIntoView).not.toHaveBeenCalled()

    restoreViewport()
  })

  it('does not enter mobile mode on a narrow desktop viewport without touch support', async () => {
    const { cmdInput, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
      mobileTouch: false,
    })

    cmdInput.dispatchEvent(new Event('focus'))

    expect(document.body.classList.contains('mobile-terminal-mode')).toBe(false)
    expect(document.body.classList.contains('mobile-keyboard-open')).toBe(false)

    restoreViewport()
  })

  it('populates the version label from the server config', async () => {
    await loadAppFns()
    await Promise.resolve()
    await Promise.resolve()

    expect(document.getElementById('version-label').textContent).toBe('v9.9 · real-time')
  })

  it('keeps the mobile run button visible after the keyboard closes', async () => {
    const { cmdInput, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const runBtn = document.getElementById('run-btn')

    cmdInput.dispatchEvent(new Event('focus'))
    expect(runBtn.hidden).toBe(false)

    Object.defineProperty(window, 'visualViewport', {
      configurable: true,
      value: {
        height: 768,
        offsetTop: 0,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      },
    })
    cmdInput.dispatchEvent(new Event('blur'))

    expect(document.body.classList.contains('mobile-terminal-mode')).toBe(true)
    expect(document.body.classList.contains('mobile-keyboard-open')).toBe(false)
    expect(runBtn.hidden).toBe(false)

    restoreViewport()
  })

  it('keeps the desktop and mobile run buttons in sync when disabled', async () => {
    const { setRunButtonDisabled } = await loadAppFns()
    const runBtn = document.getElementById('run-btn')
    const mobileRunBtn = document.getElementById('mobile-run-btn')

    setRunButtonDisabled(true)
    expect(runBtn.disabled).toBe(true)
    expect(mobileRunBtn.disabled).toBe(true)

    setRunButtonDisabled(false)
    expect(runBtn.disabled).toBe(false)
    expect(mobileRunBtn.disabled).toBe(false)
  })

  it('closes transient ui while the mobile keyboard is open', async () => {
    const acHide = vi.fn()
    const { cmdInput, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
      acHide,
    })

    document.getElementById('mobile-menu').classList.add('open')
    document.getElementById('history-panel').classList.add('open')

    cmdInput.dispatchEvent(new Event('focus'))
    cmdInput.value = 'curl'
    cmdInput.dispatchEvent(new Event('input'))

    expect(document.getElementById('mobile-menu').classList.contains('open')).toBe(false)
    expect(document.getElementById('history-panel').classList.contains('open')).toBe(false)
    expect(acHide).toHaveBeenCalled()

    restoreViewport()
  })

  it('matches autocomplete suggestions from the beginning of each command only', async () => {
    const acShow = vi.fn()
    const apiFetch = vi.fn((url) => {
      if (url === '/autocomplete') {
        return Promise.resolve({
          json: () => Promise.resolve({
            suggestions: ['curl http://localhost:5001/health', 'man curl', 'cat /etc/hosts'],
          }),
        })
      }
    if (url === '/config') {
      return Promise.resolve({
        json: () => Promise.resolve({
          app_name: 'shell.darklab.sh',
          version: '9.9',
          default_theme: 'dark',
          motd: '',
          command_timeout_seconds: 0,
            max_output_lines: 0,
            permalink_retention_days: 0,
          }),
        })
      }
      if (url === '/allowed-commands' || url === '/faq') {
        return Promise.resolve({ json: () => Promise.resolve({ restricted: false, commands: [], groups: [], items: [] }) })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })
    const { cmdInput } = await loadAppFns({
      acShow,
      apiFetch,
    })
    await Promise.resolve()
    await Promise.resolve()

    cmdInput.value = 'cur'
    cmdInput.dispatchEvent(new Event('input'))

    expect(acShow).toHaveBeenCalledWith(['curl http://localhost:5001/health'])

    acShow.mockClear()
    cmdInput.value = 'man'
    cmdInput.dispatchEvent(new Event('input'))

    expect(acShow).toHaveBeenCalledWith(['man curl'])
  })

  it('renders cursor and selection state from the hidden input', async () => {
    const { cmdInput } = await loadAppFns()
    const shellPromptText = document.getElementById('shell-prompt-text')
    const shellPromptWrap = document.getElementById('shell-prompt-wrap')

    cmdInput.value = 'nothing'
    cmdInput.setSelectionRange(3, 3)
    cmdInput.dispatchEvent(new Event('keyup'))
    expect(shellPromptText.querySelector('.shell-caret-char')?.textContent).toBe('h')
    expect(shellPromptWrap.classList.contains('shell-prompt-has-selection')).toBe(false)

    cmdInput.setSelectionRange(1, 4)
    cmdInput.dispatchEvent(new Event('select'))
    expect(shellPromptText.querySelector('.shell-prompt-selection')?.textContent).toBe('oth')
    expect(shellPromptWrap.classList.contains('shell-prompt-has-selection')).toBe(true)
  })

  it('supports ctrl+w to delete one word to the left', async () => {
    const { cmdInput } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.setSelectionRange(cmdInput.value.length, cmdInput.value.length)
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'w', ctrlKey: true, bubbles: true }))

    expect(cmdInput.value).toBe('dig darklab.sh ')
  })

  it('supports ctrl+u to delete to the beginning of the line', async () => {
    const { cmdInput } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.setSelectionRange(12, 12)
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'u', ctrlKey: true, bubbles: true }))

    expect(cmdInput.value).toBe('sh A')
    expect(cmdInput.selectionStart).toBe(0)
    expect(cmdInput.selectionEnd).toBe(0)
  })

  it('supports ctrl+a to move to the beginning of the line', async () => {
    const { cmdInput } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.setSelectionRange(9, 9)
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', ctrlKey: true, bubbles: true }))

    expect(cmdInput.selectionStart).toBe(0)
    expect(cmdInput.selectionEnd).toBe(0)
  })

  it('supports ctrl+k to delete to the end of the line', async () => {
    const { cmdInput } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.setSelectionRange(4, 4)
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true }))

    expect(cmdInput.value).toBe('dig ')
    expect(cmdInput.selectionStart).toBe(4)
    expect(cmdInput.selectionEnd).toBe(4)
  })

  it('supports ctrl+e to move to the end of the line', async () => {
    const { cmdInput } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.setSelectionRange(4, 4)
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'e', ctrlKey: true, bubbles: true }))

    expect(cmdInput.selectionStart).toBe(cmdInput.value.length)
    expect(cmdInput.selectionEnd).toBe(cmdInput.value.length)
  })

  it('supports Alt+B and Alt+F to move by word', async () => {
    const { cmdInput } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.setSelectionRange(cmdInput.value.length, cmdInput.value.length)
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'b', altKey: true, bubbles: true }))
    expect(cmdInput.selectionStart).toBe(15)
    expect(cmdInput.selectionEnd).toBe(15)

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'b', altKey: true, bubbles: true }))
    expect(cmdInput.selectionStart).toBe(4)
    expect(cmdInput.selectionEnd).toBe(4)

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'f', altKey: true, bubbles: true }))
    expect(cmdInput.selectionStart).toBe(14)
    expect(cmdInput.selectionEnd).toBe(14)
  })

  it('supports macOS Option+B and Option+F word movement via physical key codes', async () => {
    const { cmdInput } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.setSelectionRange(cmdInput.value.length, cmdInput.value.length)
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', {
      key: '∫',
      code: 'KeyB',
      altKey: true,
      bubbles: true,
    }))
    expect(cmdInput.selectionStart).toBe(15)

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'ƒ',
      code: 'KeyF',
      altKey: true,
      bubbles: true,
    }))
    expect(cmdInput.selectionStart).toBe(16)
  })

  it('supports the mobile edit bar actions', async () => {
    const { cmdInput } = await loadAppFns()
    const press = (selector) => {
      document.querySelector(selector).dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))
    }

    cmdInput.value = 'ping -c 4 example.com'
    cmdInput.setSelectionRange(cmdInput.value.length, cmdInput.value.length)

    press('[data-edit-action="left"]')
    expect(cmdInput.selectionStart).toBe(cmdInput.value.length - 1)

    press('[data-edit-action="home"]')
    expect(cmdInput.selectionStart).toBe(0)

    press('[data-edit-action="right"]')
    expect(cmdInput.selectionStart).toBe(1)

    press('[data-edit-action="end"]')
    expect(cmdInput.selectionStart).toBe(cmdInput.value.length)

    press('[data-edit-action="delete-word"]')
    expect(cmdInput.value).toBe('ping -c 4 ')
  })

  it('uses Ctrl+C to open kill confirm when active tab is running', async () => {
    const confirmKill = vi.fn()
    const { cmdInput, interruptPromptLine } = await loadAppFns({
      tabs: [{ id: 'tab-1', st: 'running' }],
      confirmKill,
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'c', ctrlKey: true, bubbles: true }))

    expect(confirmKill).toHaveBeenCalledWith('tab-1')
    expect(interruptPromptLine).not.toHaveBeenCalled()
  })

  it('uses Ctrl+C to jump to a new prompt line when no command is running', async () => {
    const interruptPromptLine = vi.fn()
    const { cmdInput, confirmKill } = await loadAppFns({
      tabs: [{ id: 'tab-1', st: 'idle' }],
      interruptPromptLine,
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'c', ctrlKey: true, bubbles: true }))

    expect(interruptPromptLine).toHaveBeenCalledWith('tab-1')
    expect(confirmKill).not.toHaveBeenCalled()
  })

  it('supports Alt+T to create a new tab from the terminal prompt', async () => {
    const createTab = vi.fn(() => 'tab-2')
    const { cmdInput } = await loadAppFns({
      createTab,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })
    createTab.mockClear()

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 't', altKey: true, bubbles: true }))

    expect(createTab).toHaveBeenCalledWith('tab 2')
  })

  it('supports macOS Option+T to create a new tab via physical key code', async () => {
    const createTab = vi.fn(() => 'tab-2')
    const { cmdInput } = await loadAppFns({
      createTab,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })
    createTab.mockClear()

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', {
      key: '†',
      code: 'KeyT',
      altKey: true,
      bubbles: true,
    }))

    expect(createTab).toHaveBeenCalledWith('tab 2')
  })

  it('supports Alt+W to close the active tab', async () => {
    const closeTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      closeTab,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'w', altKey: true, bubbles: true }))

    expect(closeTab).toHaveBeenCalledWith('tab-1')
  })

  it('supports macOS Option+W to close the active tab via physical key code', async () => {
    const closeTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      closeTab,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', {
      key: '∑',
      code: 'KeyW',
      altKey: true,
      bubbles: true,
    }))

    expect(closeTab).toHaveBeenCalledWith('tab-1')
  })

  it('supports Alt+ArrowLeft and Alt+ArrowRight to cycle between tabs', async () => {
    const activateTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      activateTab,
      activeTabId: 'tab-2',
      tabs: [
        { id: 'tab-1', st: 'idle' },
        { id: 'tab-2', st: 'idle' },
        { id: 'tab-3', st: 'idle' },
      ],
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', altKey: true, bubbles: true }))
    expect(activateTab).toHaveBeenCalledWith('tab-3')

    activateTab.mockClear()
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', altKey: true, bubbles: true }))
    expect(activateTab).toHaveBeenCalledWith('tab-1')
  })

  it('supports Alt+digit to jump directly to a tab', async () => {
    const activateTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      activateTab,
      tabs: [
        { id: 'tab-1', st: 'idle' },
        { id: 'tab-2', st: 'idle' },
        { id: 'tab-3', st: 'idle' },
      ],
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: '3', altKey: true, bubbles: true }))

    expect(activateTab).toHaveBeenCalledWith('tab-3')
  })

  it('supports macOS Option+digit tab jumps via physical key code', async () => {
    const activateTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      activateTab,
      tabs: [
        { id: 'tab-1', st: 'idle' },
        { id: 'tab-2', st: 'idle' },
        { id: 'tab-3', st: 'idle' },
      ],
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', {
      key: '£',
      code: 'Digit3',
      altKey: true,
      bubbles: true,
    }))

    expect(activateTab).toHaveBeenCalledWith('tab-3')
  })

  it('supports Alt+P to create a permalink for the active tab', async () => {
    const permalinkTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      permalinkTab,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'p', altKey: true, bubbles: true }))

    expect(permalinkTab).toHaveBeenCalledWith('tab-1')
  })

  it('supports macOS Option+P to create a permalink via physical key code', async () => {
    const permalinkTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      permalinkTab,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'π',
      code: 'KeyP',
      altKey: true,
      bubbles: true,
    }))

    expect(permalinkTab).toHaveBeenCalledWith('tab-1')
  })

  it('supports Alt+Shift+C to copy output for the active tab', async () => {
    const copyTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      copyTab,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'C',
      altKey: true,
      shiftKey: true,
      bubbles: true,
    }))

    expect(copyTab).toHaveBeenCalledWith('tab-1')
  })

  it('supports macOS Option+Shift+C to copy output via physical key code', async () => {
    const copyTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      copyTab,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Ç',
      code: 'KeyC',
      altKey: true,
      shiftKey: true,
      bubbles: true,
    }))

    expect(copyTab).toHaveBeenCalledWith('tab-1')
  })

  it('supports Ctrl+L to clear the active tab', async () => {
    const clearTab = vi.fn()
    const cancelWelcome = vi.fn()
    const { cmdInput } = await loadAppFns({
      clearTab,
      cancelWelcome,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'l', ctrlKey: true, bubbles: true }))

    expect(cancelWelcome).toHaveBeenCalledWith('tab-1')
    expect(clearTab).toHaveBeenCalledWith('tab-1')
  })

  it('does not apply Alt-based tab shortcuts while typing in non-terminal inputs', async () => {
    const createTab = vi.fn(() => 'tab-2')
    const activateTab = vi.fn()
    await loadAppFns({
      createTab,
      activateTab,
      tabs: [
        { id: 'tab-1', st: 'idle' },
        { id: 'tab-2', st: 'idle' },
      ],
    })
    createTab.mockClear()
    activateTab.mockClear()
    const searchInput = document.getElementById('search-input')

    searchInput.dispatchEvent(new KeyboardEvent('keydown', { key: 't', altKey: true, bubbles: true }))
    searchInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', altKey: true, bubbles: true }))

    expect(createTab).not.toHaveBeenCalled()
    expect(activateTab).not.toHaveBeenCalled()
  })

  it('does not apply action shortcuts while typing in non-terminal inputs', async () => {
    const permalinkTab = vi.fn()
    const copyTab = vi.fn()
    const clearTab = vi.fn()
    await loadAppFns({
      permalinkTab,
      copyTab,
      clearTab,
      tabs: [
        { id: 'tab-1', st: 'idle' },
        { id: 'tab-2', st: 'idle' },
      ],
    })
    const searchInput = document.getElementById('search-input')

    searchInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'p', altKey: true, bubbles: true }))
    searchInput.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'C',
      altKey: true,
      shiftKey: true,
      bubbles: true,
    }))
    searchInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'l', ctrlKey: true, bubbles: true }))

    expect(permalinkTab).not.toHaveBeenCalled()
    expect(copyTab).not.toHaveBeenCalled()
    expect(clearTab).not.toHaveBeenCalled()
  })

  it('moves autocomplete selection in visual screen order when the list is above the prompt', async () => {
    const acFiltered = ['alpha', 'bravo', 'charlie']
    const { cmdInput, _getAcIndex, acDropdown } = await loadAppFns({
      acFiltered,
      acIndex: 2,
    })

    acDropdown.style.display = 'block'
    acDropdown.classList.add('ac-up')

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }))
    expect(_getAcIndex()).toBe(1)

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }))
    expect(_getAcIndex()).toBe(2)
  })

  it('wires the history delete modal buttons and backdrop correctly', async () => {
    const { confirmHistAction, executeHistAction } = await loadAppFns()
    const histDelOverlay = document.getElementById('hist-del-overlay')

    confirmHistAction.mockClear()
    executeHistAction.mockClear()

    document.getElementById('hist-clear-all-btn').click()
    expect(confirmHistAction).toHaveBeenCalledWith('clear')

    histDelOverlay.style.display = 'flex'
    document.getElementById('hist-del-cancel').click()
    expect(histDelOverlay.style.display).toBe('none')

    histDelOverlay.style.display = 'flex'
    document.getElementById('hist-del-nonfav').click()
    expect(histDelOverlay.style.display).toBe('none')
    expect(executeHistAction).toHaveBeenCalledWith('clear-nonfav')

    histDelOverlay.style.display = 'flex'
    document.getElementById('hist-del-confirm').click()
    expect(histDelOverlay.style.display).toBe('none')
    expect(executeHistAction).toHaveBeenCalled()

    histDelOverlay.style.display = 'flex'
    histDelOverlay.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(histDelOverlay.style.display).toBe('none')
  })

  it('wires the kill modal buttons and backdrop correctly', async () => {
    await loadAppFns()
    const killOverlay = document.getElementById('kill-overlay')

    killOverlay.style.display = 'flex'
    document.getElementById('kill-cancel').click()
    expect(killOverlay.style.display).toBe('none')

    const doKill = vi.fn()
    await loadAppFns({ doKill, pendingKillTabId: 'tab-1' })
    const killOverlay2 = document.getElementById('kill-overlay')

    killOverlay2.style.display = 'flex'
    document.getElementById('kill-confirm').click()
    expect(doKill).toHaveBeenCalledWith('tab-1')
    expect(killOverlay2.style.display).toBe('none')

    killOverlay2.style.display = 'flex'
    killOverlay2.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(killOverlay2.style.display).toBe('none')
  })

  it('supports Enter and Escape in the kill confirmation modal', async () => {
    const doKill = vi.fn()
    const { cmdInput } = await loadAppFns({ doKill, pendingKillTabId: 'tab-1' })
    const killOverlay = document.getElementById('kill-overlay')

    killOverlay.style.display = 'flex'
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    expect(doKill).toHaveBeenCalledWith('tab-1')
    expect(killOverlay.style.display).toBe('none')
    expect(cmdInput.focus).toHaveBeenCalled()

    cmdInput.focus.mockClear()
    killOverlay.style.display = 'flex'
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(killOverlay.style.display).toBe('none')
    expect(cmdInput.focus).toHaveBeenCalled()
  })

  it('wires search controls and Escape dismissal correctly', async () => {
    const { runSearch, clearSearch, navigateSearch, cmdInput } = await loadAppFns()
    const searchBar = document.getElementById('search-bar')
    const searchInput = document.getElementById('search-input')

    searchBar.style.display = 'none'
    document.getElementById('search-toggle-btn').click()
    expect(searchBar.style.display).toBe('flex')
    expect(runSearch).toHaveBeenCalledTimes(1)

    document.getElementById('search-prev').click()
    document.getElementById('search-next').click()
    expect(navigateSearch).toHaveBeenCalledWith(-1)
    expect(navigateSearch).toHaveBeenCalledWith(1)

    searchBar.style.display = 'flex'
    searchInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(searchBar.style.display).toBe('none')
    expect(clearSearch).toHaveBeenCalled()
    expect(cmdInput.focus).toHaveBeenCalled()

    searchBar.style.display = 'none'
    document.getElementById('search-toggle-btn').click()
    document.getElementById('search-toggle-btn').click()
    expect(clearSearch).toHaveBeenCalledTimes(3)
    expect(searchBar.style.display).toBe('none')
  })

  it('opens and closes the FAQ overlay through the wired controls', async () => {
    await loadAppFns()
    const faqOverlay = document.getElementById('faq-overlay')

    document.getElementById('faq-btn').click()
    expect(faqOverlay.classList.contains('open')).toBe(true)

    faqOverlay.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(faqOverlay.classList.contains('open')).toBe(false)

    document.getElementById('faq-btn').click()
    document.querySelector('.faq-close').click()
    expect(faqOverlay.classList.contains('open')).toBe(false)
  })

  it('opens and closes the options overlay through the wired controls', async () => {
    const { cmdInput } = await loadAppFns()
    const overlay = document.getElementById('options-overlay')

    document.getElementById('options-btn').click()
    expect(overlay.classList.contains('open')).toBe(true)

    document.querySelector('.options-close').click()
    expect(overlay.classList.contains('open')).toBe(false)
    expect(cmdInput.focus).toHaveBeenCalled()

    document.querySelector('#mobile-menu [data-action="options"]').click()
    expect(overlay.classList.contains('open')).toBe(true)

    overlay.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(overlay.classList.contains('open')).toBe(false)
  })

  it('persists options changes through cookies and syncs quick-toggle state', async () => {
    await loadAppFns()

    document.getElementById('options-btn').click()
    document.querySelector('input[name="theme-pref"][value="light"]').click()
    document.getElementById('options-ts-select').value = 'elapsed'
    document.getElementById('options-ts-select').dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('options-ln-toggle').checked = true
    document.getElementById('options-ln-toggle').dispatchEvent(new Event('change', { bubbles: true }))

    expect(document.body.classList.contains('light')).toBe(true)
    expect(document.body.classList.contains('ts-elapsed')).toBe(true)
    expect(document.body.classList.contains('ln-on')).toBe(true)
    expect(document.getElementById('ts-btn').textContent).toBe('timestamps: elapsed')
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers: on')
    expect(document.cookie).toContain('pref_theme=light')
    expect(document.cookie).toContain('pref_timestamps=elapsed')
    expect(document.cookie).toContain('pref_line_numbers=on')
  })

  it('renders backend-driven FAQ items with HTML answers and dynamic sections', async () => {
    const apiFetch = vi.fn((url) => {
    if (url === '/config') {
      return Promise.resolve({
        json: () => Promise.resolve({
          app_name: 'shell.darklab.sh',
          version: '9.9',
          default_theme: 'dark',
          motd: '',
          command_timeout_seconds: 120,
            max_output_lines: 5000,
            permalink_retention_days: 365,
          }),
        })
      }
      if (url === '/allowed-commands') {
        return Promise.resolve({
          json: () => Promise.resolve({
            restricted: true,
            commands: ['ping', 'curl'],
            groups: [{ name: 'Network', commands: ['ping', 'curl'] }],
          }),
        })
      }
      if (url === '/faq') {
        return Promise.resolve({
          json: () => Promise.resolve({
            items: [
              { question: 'What is this?', answer: 'plain', answer_html: 'Rich <strong>HTML</strong>' },
              { question: 'Allowed?', answer: 'allowlist', ui_kind: 'allowed_commands' },
              { question: 'Limits?', answer: 'limits', ui_kind: 'limits' },
            ],
          }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })

    await loadAppFns({ apiFetch })
    await new Promise(resolve => setImmediate(resolve))

    const questions = [...document.querySelectorAll('.faq-q')].map(el => el.textContent)
    expect(questions).toContain('What is this?')
    expect(document.querySelector('.faq-a strong')?.textContent).toBe('HTML')
    expect(document.getElementById('faq-allowed-text')?.textContent).toContain('Click any command')
    expect(document.getElementById('faq-limits-text')?.innerHTML).toContain('Command timeout')
    expect(document.querySelectorAll('.allowed-chip')).toHaveLength(2)
  })
})
