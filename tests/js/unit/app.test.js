import { readFileSync } from 'fs'
import { resolve } from 'path'
import { MemoryStorage, fromDomScripts } from './helpers/extract.js'

// This harness recreates the browser-global environment expected by the classic
// script bundle so app.js can be tested without loading the full page.
async function loadAppFns({
  theme = null,
  themeRegistry = null,
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
  submitComposerCommand: submitComposerCommandOverride = vi.fn(),
  submitVisibleComposerCommand: submitVisibleComposerCommandOverride = vi.fn(),
  createTab: createTabOverride = vi.fn(() => 'tab-1'),
  closeTab: closeTabOverride = vi.fn(),
  activateTab: activateTabOverride = vi.fn(),
  permalinkTab: permalinkTabOverride = vi.fn(),
  copyTab: copyTabOverride = vi.fn(),
  clearTab: clearTabOverride = vi.fn(),
  cancelWelcome: cancelWelcomeOverride = vi.fn(),
  navigateCmdHistory: navigateCmdHistoryOverride = vi.fn(() => false),
  enterHistSearch: enterHistSearchOverride = vi.fn(),
  activeTabId = 'tab-1',
  acFiltered: acFilteredOverride = [],
  acSuggestions: acSuggestionsOverride = [],
  acIndex: acIndexOverride = -1,
  acShow: acShowOverride = () => {},
  acHide: acHideOverride = () => {},
  getOutput: getOutputOverride = null,
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
    <div id="mobile-shell" aria-hidden="true">
      <div id="mobile-shell-chrome"></div>
      <div id="mobile-shell-transcript"></div>
      <div id="mobile-shell-composer">
        <div id="mobile-composer-host">
          <div id="mobile-edit-bar">
            <button data-edit-action="home"></button>
            <button data-edit-action="left"></button>
            <button data-edit-action="right"></button>
            <button data-edit-action="end"></button>
            <button data-edit-action="delete-word"></button>
          </div>
          <div id="mobile-composer-row">
            <span class="mobile-prompt-label">$</span>
            <input id="mobile-cmd" />
            <button id="mobile-run-btn"></button>
          </div>
        </div>
      </div>
      <div id="mobile-shell-overlays">
        <div id="mobile-menu">
          <button data-action="ln"></button>
          <button data-action="ts"></button>
          <button data-action="search"></button>
          <button data-action="history"></button>
          <button data-action="options"></button>
          <button data-action="theme"></button>
          <button data-action="faq"></button>
        </div>
      </div>
    </div>
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
        <span class="prompt-prefix" data-mobile-label="$">anon@darklab:~$</span>
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
        <button id="search-close-btn"></button>
      </div>
      <div id="tab-panels"></div>
    <div id="faq-limits-text"></div>
    <div id="faq-allowed-text"></div>
    <div id="faq-overlay"></div>
    <button class="faq-close"></button>
    <div class="faq-body"></div>
    <div id="theme-overlay"></div>
    <button class="theme-close"></button>
    <div id="theme-modal"></div>
    <div id="theme-select" tabindex="-1"></div>
    <div id="options-overlay"></div>
    <button class="options-close"></button>
    <div id="options-modal"></div>
    <select id="options-ts-select">
      <option value="off">off</option>
      <option value="elapsed">elapsed</option>
      <option value="clock">clock</option>
      </select>
      <input id="options-ln-toggle" type="checkbox" />
      <div id="shell-input-row" data-mobile-label="$">
        <input id="cmd" />
      </div>
      <div id="history-panel"></div>
      <div id="history-list"></div>
      <div id="permalink-toast"></div>
      <div id="kill-overlay"></div>
      <div id="hist-del-overlay"></div>
      <div id="share-redaction-overlay"></div>
      <button id="share-redaction-cancel"></button>
      <button id="share-redaction-raw"></button>
      <button id="share-redaction-confirm"></button>
      <input id="share-redaction-remember-toggle" type="checkbox" />
      <div class="prompt-wrap"></div>
    </div>
  `

  const storage = new MemoryStorage()
  const sessionStore = new MemoryStorage()
  if (theme !== null) storage.setItem('theme', theme)
  for (const [name, value] of Object.entries(cookies)) {
    document.cookie = `${name}=${encodeURIComponent(value)}; path=/`
  }

  const apiFetch = apiFetchOverride || vi.fn((url) => {
    if (url === '/config') {
      return Promise.resolve({
        json: () => Promise.resolve({
          app_name: 'darklab shell',
          prompt_prefix: 'anon@darklab:~$',
          version: '9.9',
          project_readme: 'https://gitlab.com/darklab.sh/darklab-shell#darklab-shell',
          default_theme: 'darklab_obsidian.yaml',
          share_redaction_enabled: true,
          share_redaction_rules: [],
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
  const domBindings = {
    hamburgerBtn: document.getElementById('hamburger-btn'),
    faqBtn: document.getElementById('faq-btn'),
    faqCloseBtn: document.querySelector('.faq-close'),
    optionsBtn: document.getElementById('options-btn'),
    optionsCloseBtn: document.querySelector('.options-close'),
    themeCloseBtn: document.querySelector('.theme-close'),
    newTabBtn: document.getElementById('new-tab-btn'),
    searchToggleBtn: document.getElementById('search-toggle-btn'),
    histBtn: document.getElementById('hist-btn'),
    historyCloseBtn: document.getElementById('history-close'),
    histClearAllBtn: document.getElementById('hist-clear-all-btn'),
    histDelCancelBtn: document.getElementById('hist-del-cancel'),
    histDelNonfavBtn: document.getElementById('hist-del-nonfav'),
    histDelConfirmBtn: document.getElementById('hist-del-confirm'),
    shareRedactionCancelBtn: document.getElementById('share-redaction-cancel'),
    shareRedactionRawBtn: document.getElementById('share-redaction-raw'),
    shareRedactionConfirmBtn: document.getElementById('share-redaction-confirm'),
    shareRedactionRememberToggle: document.getElementById('share-redaction-remember-toggle'),
    killCancelBtn: document.getElementById('kill-cancel'),
    killConfirmBtn: document.getElementById('kill-confirm'),
    searchPrevBtn: document.getElementById('search-prev'),
    searchNextBtn: document.getElementById('search-next'),
    searchCloseBtn: document.getElementById('search-close-btn'),
    optionsTsSelect: document.getElementById('options-ts-select'),
    optionsLnToggle: document.getElementById('options-ln-toggle'),
    themeSelect: document.getElementById('theme-select'),
    tsBtn: document.getElementById('ts-btn'),
    lnBtn: document.getElementById('ln-btn'),
    themeBtn: document.getElementById('theme-btn'),
    headerTitle: document.querySelector('header h1'),
    faqBody: document.querySelector('.faq-body'),
    faqLimitsText: document.getElementById('faq-limits-text'),
    faqAllowedText: document.getElementById('faq-allowed-text'),
    status: document.getElementById('status'),
    histRow: document.getElementById('history-row'),
    tabsBar: document.getElementById('tabs-bar'),
    tabPanels: document.getElementById('tab-panels'),
    themeOverlay: document.getElementById('theme-overlay'),
    mobileShell: document.getElementById('mobile-shell'),
    mobileShellChrome: document.getElementById('mobile-shell-chrome'),
    mobileShellTranscript: document.getElementById('mobile-shell-transcript'),
    mobileShellComposer: document.getElementById('mobile-shell-composer'),
    mobileShellOverlays: document.getElementById('mobile-shell-overlays'),
    mobileComposerHost: document.getElementById('mobile-composer-host'),
    mobileComposerRow: document.getElementById('mobile-composer-row'),
    mobileEditBar: document.getElementById('mobile-edit-bar'),
    mobileCmdInput: document.getElementById('mobile-cmd'),
    mobileRunBtn: document.getElementById('mobile-run-btn'),
    mobileMenu: document.getElementById('mobile-menu'),
    searchBar: document.getElementById('search-bar'),
    searchInput: document.getElementById('search-input'),
    searchCount: document.getElementById('search-count'),
    historyPanel: document.getElementById('history-panel'),
    historyList: document.getElementById('history-list'),
    historyLoadOverlay: document.getElementById('history-load-overlay'),
    acDropdown,
    themeCloseBtn: document.querySelector('.theme-close'),
    killOverlay: document.getElementById('kill-overlay'),
    histDelOverlay: document.getElementById('hist-del-overlay'),
    shareRedactionOverlay: document.getElementById('share-redaction-overlay'),
    faqOverlay: document.getElementById('faq-overlay'),
    optionsOverlay: document.getElementById('options-overlay'),
    permalinkToast: document.getElementById('permalink-toast'),
    runTimer: document.getElementById('run-timer'),
    searchCaseBtn: document.getElementById('search-case-btn'),
    searchRegexBtn: document.getElementById('search-regex-btn'),
    shellPromptWrap: document.getElementById('shell-prompt-wrap'),
    shellPromptLine: document.getElementById('shell-prompt-line'),
    shellPromptText: document.getElementById('shell-prompt-text'),
    shellPromptCaret: document.getElementById('shell-prompt-caret'),
    shellInputRow: document.getElementById('shell-input-row'),
    runBtn: document.getElementById('run-btn'),
  }
  cmdInput.focus = vi.fn()
  cmdInput.blur = vi.fn()
  const shellPromptWrapEl = document.getElementById('shell-prompt-wrap')
  shellPromptWrapEl.scrollIntoView = vi.fn()
  const mobileComposerHostEl = document.getElementById('mobile-composer-host')
  mobileComposerHostEl.scrollIntoView = vi.fn()
  const mobileCmdInput = document.getElementById('mobile-cmd')
  cmdInput.focus = vi.fn()
  mobileCmdInput.focus = vi.fn()
  mobileCmdInput.blur = vi.fn()

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
    } else {
      Object.defineProperty(window.navigator, 'maxTouchPoints', {
        configurable: true,
        value: 0,
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

  if (themeRegistry !== null) window.ThemeRegistry = themeRegistry
  else delete window.ThemeRegistry

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
    'app/static/js/controller.js',
  ], {
    document,
    localStorage: storage,
    sessionStorage: sessionStore,
    apiFetch,
    APP_CONFIG: {},
    AnsiUp: FakeAnsiUp,
    ThemeRegistry: themeRegistry,
    ...domBindings,
    getOutput: getOutputOverride || (() => document.getElementById('history-list')),
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
    acSuggestions: acSuggestionsOverride,
    acFiltered: acFilteredOverride,
    acIndex: acIndexOverride,
    acShow: acShowOverride,
    acAccept: () => {},
    resetCmdHistoryNav: () => {},
    navigateCmdHistory: navigateCmdHistoryOverride,
    setupTabScrollControls: () => {},
    hydrateCmdHistory: () => {},
    mountShellPrompt: () => {},
    unmountShellPrompt: () => {},
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
    enterHistSearch: enterHistSearchOverride,
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
    mobileShellChrome: document.getElementById('mobile-shell-chrome'),
    mobileShellTranscript: document.getElementById('mobile-shell-transcript'),
    mobileShellComposer: document.getElementById('mobile-shell-composer'),
    mobileShellOverlays: document.getElementById('mobile-shell-overlays'),
    mobileComposerHost: document.getElementById('mobile-composer-host'),
    mobileComposerRow: document.getElementById('mobile-composer-row'),
    mobileEditBar: document.getElementById('mobile-edit-bar'),
    mobileMenu: document.getElementById('mobile-menu'),
    faqOverlay: document.getElementById('faq-overlay'),
    optionsOverlay: document.getElementById('options-overlay'),
    permalinkToast: document.getElementById('permalink-toast'),
    mobileComposerHostEl,
    acDropdown,
    requestWelcomeSettle: requestWelcomeSettleOverride,
    runCommand: runCommandOverride,
    submitComposerCommand: submitComposerCommandOverride,
    submitVisibleComposerCommand: submitVisibleComposerCommandOverride,
    doKill: doKillOverride,
    Event,
    setTimeout: (fn) => {
      fn()
      return 0
    },
  }, `{
    _setTsMode,
    _setLnMode,
    handleComposerInputChange,
    setComposerValue,
    moveCmdCaret,
    setCmdCaret,
    deleteCmdWordLeft,
    performMobileEditAction,
    syncMobileComposerKeyboardState,
    focusVisibleComposerInput,
    blurVisibleComposerInput,
    blurVisibleComposerInputIfMobile,
    _replayPromptShortcutAfterSelection,
    refocusTerminalInput,
    getVisibleComposerInput,
    getComposerValue,
    setRunButtonDisabled,
    confirmHistAction,
    executeHistAction,
    doKill,
    showKillOverlay,
    hideKillOverlay,
    isKillOverlayOpen,
    confirmPendingKill,
    closeKillOverlay,
    confirmPermalinkRedactionChoice,
    getRememberedShareRedactionChoice,
    resolveShareRedactionChoice,
    cancelShareRedactionChoice,
    isShareRedactionOverlayOpen,
    getComposerState,
    setComposerState,
    resetComposerState,
    syncShellPrompt,
    _getAcIndex: () => acIndex,
  }`, 'setTabs(tabs); setActiveTabId(activeTabId);')

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
    navigateCmdHistory: navigateCmdHistoryOverride,
    enterHistSearch: enterHistSearchOverride,
    interruptPromptLine: interruptPromptLineOverride,
    runCommand: runCommandOverride,
    submitComposerCommand: submitComposerCommandOverride,
    submitVisibleComposerCommand: submitVisibleComposerCommandOverride,
    logClientError,
    acDropdown,
    acHide: acHideOverride,
    shellPromptWrap: shellPromptWrapEl,
    showKillOverlay: fns.showKillOverlay,
    hideKillOverlay: fns.hideKillOverlay,
    isKillOverlayOpen: fns.isKillOverlayOpen,
    confirmPendingKill: fns.confirmPendingKill,
    closeKillOverlay: fns.closeKillOverlay,
    syncShellPrompt: fns.syncShellPrompt,
    sessionStorage: sessionStore,
    restoreViewport: () => {
      if (originalMatchMedia === undefined) delete window.matchMedia
      else Object.defineProperty(window, 'matchMedia', { configurable: true, value: originalMatchMedia })
      if (originalVisualViewport === undefined) delete window.visualViewport
      else Object.defineProperty(window, 'visualViewport', { configurable: true, value: originalVisualViewport })
      if (originalScrollTo === undefined) delete window.scrollTo
      else window.scrollTo = originalScrollTo
      if (originalMaxTouchPoints === undefined) delete window.navigator.maxTouchPoints
      else Object.defineProperty(window.navigator, 'maxTouchPoints', { configurable: true, value: originalMaxTouchPoints })
    },
  }
}

describe('app helpers', () => {
  beforeEach(() => {
    ;['pref_theme', 'pref_theme_name', 'pref_timestamps', 'pref_line_numbers'].forEach(name => {
      document.cookie = `${name}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`
    })
  })

  it('applies the saved theme at startup', async () => {
    await loadAppFns({
      theme: 'theme_light_blue',
      themeRegistry: {
        current: {
          name: 'theme_light_blue',
          label: 'Blue Paper',
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Blue Paper',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
        ],
      },
    })

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

  it('opens the theme selector from the theme button', async () => {
    await loadAppFns({
      themeRegistry: {
        current: {
          name: 'theme_light_blue',
          label: 'Blue Paper',
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Blue Paper',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
          {
            name: 'theme_light_olive',
            label: 'Olive Parchment',
            source: 'variant',
            vars: { '--bg': '#c0c0a8' },
          },
        ],
      },
    })

    document.getElementById('theme-btn').click()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(document.getElementById('theme-overlay').classList.contains('open')).toBe(true)
    expect(document.querySelector('#theme-select .theme-card-active')).toBe(document.activeElement)
  })

  it('populates the theme select from the registry and applies the selected theme', async () => {
    const themeRegistry = {
      current: {
        name: 'theme_light_blue',
        label: 'Blue Paper',
        source: 'variant',
        vars: { '--bg': '#9ab7d0' },
      },
      themes: [
        {
          name: 'theme_light_blue',
          label: 'Blue Paper',
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        {
          name: 'theme_light_olive',
          label: 'Olive Parchment',
          source: 'variant',
          vars: { '--bg': '#c0c0a8' },
        },
      ],
    }

    await loadAppFns({ themeRegistry })

    const themeSelect = document.getElementById('theme-select')
    expect(themeSelect).not.toBeNull()
    const themeCards = Array.from(themeSelect.querySelectorAll('[data-theme-name]'))
    expect(themeCards.map(card => card.dataset.themeName)).toEqual([
      'theme_light_blue',
      'theme_light_olive',
    ])
    expect(themeCards.map(card => card.querySelector('.theme-card-label')?.textContent)).toEqual([
      'Blue Paper',
      'Olive Parchment',
    ])

    themeSelect.querySelector('[data-theme-name="theme_light_blue"]').click()

    expect(document.body.dataset.theme).toBe('theme_light_blue')
    expect(document.cookie).toContain('pref_theme_name=theme_light_blue')

    themeSelect.querySelector('[data-theme-name="theme_light_olive"]').click()

    expect(document.body.dataset.theme).toBe('theme_light_olive')
    expect(document.cookie).toContain('pref_theme_name=theme_light_olive')
  })

  it('groups theme cards into labeled sections in the preview modal', async () => {
    await loadAppFns({
      themeRegistry: {
        current: {
          name: 'blue_paper',
          label: 'Blue Paper',
          group: 'Cool Light',
          sort: 50,
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'blue_paper',
            label: 'Blue Paper',
            group: 'Cool Light',
            sort: 50,
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
          {
            name: 'olive_grove',
            label: 'Olive Grove',
            group: 'Warm Light',
            sort: 20,
            source: 'variant',
            vars: { '--bg': '#c0c0a8' },
          },
          {
            name: 'rose_quartz',
            label: 'Rose Quartz',
            group: 'Warm Light',
            sort: 30,
            source: 'variant',
            vars: { '--bg': '#e6d7dc' },
          },
          {
            name: 'graphite',
            label: 'Graphite',
            group: 'Neutral Light',
            sort: 90,
            source: 'variant',
            vars: { '--bg': '#d0d0d0' },
          },
        ],
      },
    })

    const groupTitles = Array.from(document.querySelectorAll('#theme-select .theme-picker-group-title')).map(node => node.textContent)
    expect(groupTitles).toEqual(['Warm Light', 'Cool Light', 'Neutral Light'])
    const sectionGroups = Array.from(document.querySelectorAll('#theme-select .theme-picker-group')).map(node => node.dataset.themeGroup)
    expect(sectionGroups).toEqual(['Warm Light', 'Cool Light', 'Neutral Light'])
    expect(document.getElementById('theme-select')?.style.getPropertyValue('--theme-picker-columns')).toBe('2')
    expect(document.querySelectorAll('#theme-select [data-theme-name]').length).toBe(4)
  })

  it('falls back to the current/default theme when localStorage references a missing theme', async () => {
    await loadAppFns({
      theme: 'theme_missing',
      themeRegistry: {
        current: {
          name: 'theme_light_blue',
          label: 'Blue Paper',
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Blue Paper',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
          {
            name: 'theme_light_olive',
            label: 'Olive Parchment',
            source: 'variant',
            vars: { '--bg': '#c0c0a8' },
          },
        ],
      },
    })

    expect(document.body.dataset.theme).toBe('theme_light_blue')
    expect(document.querySelector('#theme-select .theme-card-active')?.dataset.themeName).toBe('theme_light_blue')
  })

  it('falls back to the baked-in dark palette when the configured default theme is missing', async () => {
    await loadAppFns({
      themeRegistry: {
        current: null,
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Blue Paper',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
          {
            name: 'theme_light_olive',
            label: 'Olive Parchment',
            source: 'variant',
            vars: { '--bg': '#c0c0a8' },
          },
        ],
      },
      apiFetch: vi.fn((url) => {
        if (url === '/config') {
          return Promise.resolve({
            json: () => Promise.resolve({
              app_name: 'darklab shell',
              prompt_prefix: 'anon@darklab:~$',
              version: '9.9',
              default_theme: 'theme_missing.yaml',
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
      }),
    })

    expect(document.body.dataset.theme).toBe('dark')
    expect(document.querySelector('#theme-select .theme-card-active')).toBeNull()
  })

  it('shows an empty state when no themes are registered and falls back to the baked-in dark palette', async () => {
    await loadAppFns({
      themeRegistry: {
        current: null,
        themes: [],
      },
    })

    expect(document.body.dataset.theme).toBe('dark')

    document.getElementById('theme-btn').click()
    expect(document.getElementById('theme-overlay').classList.contains('open')).toBe(true)
    expect(document.getElementById('theme-select').textContent).toContain('No themes available')
  })

  it('renders a single theme card and applies it when only one theme is available', async () => {
    await loadAppFns({
      themeRegistry: {
        current: {
          name: 'only_theme',
          label: 'Only Theme',
          filename: 'only_theme.yaml',
          source: 'variant',
          vars: { '--bg': '#ccd9e6' },
        },
        themes: [
          {
            name: 'only_theme',
            label: 'Only Theme',
            filename: 'only_theme.yaml',
            source: 'variant',
            vars: { '--bg': '#ccd9e6' },
          },
        ],
      },
    })

    const themeSelect = document.getElementById('theme-select')
    const themeCards = Array.from(themeSelect.querySelectorAll('[data-theme-name]'))
    expect(themeCards).toHaveLength(1)
    expect(themeCards[0].dataset.themeName).toBe('only_theme')
    expect(themeCards[0].querySelector('.theme-card-label')?.textContent).toBe('Only Theme')

    themeCards[0].click()
    expect(document.body.dataset.theme).toBe('only_theme')
    expect(document.cookie).toContain('pref_theme_name=only_theme')
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

  it('renders the shell prompt line from composer state instead of the stale hidden input', async () => {
    const { cmdInput, setComposerState, syncShellPrompt } = await loadAppFns()
    const shellPromptText = document.getElementById('shell-prompt-text')
    const shellPromptWrap = document.getElementById('shell-prompt-wrap')

    expect(shellPromptText.textContent).toBe('')
    expect(shellPromptWrap.classList.contains('shell-prompt-empty')).toBe(true)

    cmdInput.value = 'stale prompt'
    cmdInput.setSelectionRange(0, 0)
    setComposerState({
      value: 'ping darklab.sh',
      selectionStart: 'ping darklab.sh'.length,
      selectionEnd: 'ping darklab.sh'.length,
      activeInput: 'desktop',
    })
    syncShellPrompt()

    expect(shellPromptText.textContent).toBe('ping darklab.sh')
    expect(shellPromptWrap.classList.contains('shell-prompt-empty')).toBe(false)
  })

  it('manually inserts printable desktop keydown input once', async () => {
    const { cmdInput, setComposerState } = await loadAppFns()

    cmdInput.value = 'ab'
    cmdInput.setSelectionRange(2, 2)
    setComposerState({ value: 'ab', selectionStart: 2, selectionEnd: 2, activeInput: 'desktop' })
    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => cmdInput,
    })
    const ev = new KeyboardEvent('keydown', { key: 'c', bubbles: true, cancelable: true })
    cmdInput.dispatchEvent(ev)

    expect(ev.defaultPrevented).toBe(true)
    expect(cmdInput.value).toBe('abc')
    expect(cmdInput.selectionStart).toBe(3)
    expect(cmdInput.selectionEnd).toBe(3)
  })

  it.each([
    {
      key: 'ArrowDown',
      keydown: { key: 'ArrowDown' },
      expectAction: (helpers) => expect(helpers.navigateCmdHistory).toHaveBeenCalledWith(-1),
    },
    {
      key: 'Enter',
      keydown: { key: 'Enter' },
      expectAction: (helpers) => expect(helpers.submitComposerCommand).toHaveBeenCalledWith('ping darklab.sh', { dismissKeyboard: true }),
    },
    {
      key: 'Ctrl+R',
      keydown: { key: 'r', ctrlKey: true },
      expectAction: (helpers) => expect(helpers.enterHistSearch).toHaveBeenCalled(),
    },
  ])('replays %s after desktop output text is selected', async ({ keydown, expectAction }) => {
    const navigateCmdHistory = vi.fn(() => false)
    const enterHistSearch = vi.fn()
    const submitComposerCommand = vi.fn()
    const { cmdInput, _replayPromptShortcutAfterSelection, setComposerState } = await loadAppFns({
      navigateCmdHistory,
      enterHistSearch,
      submitComposerCommand,
    })

    const originalGetSelection = window.getSelection
    let activeElement = document.body
    const focusSpy = vi.fn(() => {
      activeElement = cmdInput
    })
    cmdInput.focus = focusSpy
    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => activeElement,
    })
    Object.defineProperty(window, 'getSelection', {
      configurable: true,
      value: () => ({ toString: () => 'highlighted output' }),
    })

    try {
      cmdInput.value = 'ping darklab.sh'
      setComposerState({
        value: 'ping darklab.sh',
        selectionStart: 'ping darklab.sh'.length,
        selectionEnd: 'ping darklab.sh'.length,
        activeInput: 'desktop',
      })
      const ev = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...keydown })
      const handled = _replayPromptShortcutAfterSelection(ev)

      expect(handled).toBe(true)
      expect(ev.defaultPrevented).toBe(true)
      expect(focusSpy).toHaveBeenCalled()
      expectAction({ navigateCmdHistory, enterHistSearch, submitComposerCommand })
    } finally {
      Object.defineProperty(window, 'getSelection', { configurable: true, value: originalGetSelection })
    }
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

  it('moves the cursor from composer state instead of stale DOM selection', async () => {
    const { moveCmdCaret, setComposerState } = await loadAppFns()
    const cmdInput = document.getElementById('cmd')

    cmdInput.value = 'abc'
    cmdInput.setSelectionRange(3, 3)
    setComposerState({ value: 'abc', selectionStart: 1, selectionEnd: 1, activeInput: 'desktop' })

    moveCmdCaret(1)

    expect(cmdInput.selectionStart).toBe(2)
    expect(cmdInput.selectionEnd).toBe(2)
    expect(cmdInput.value).toBe('abc')
  })

  it('tracks mobile keyboard state and keeps the prompt visible while typing', async () => {
    const { shellPromptWrap, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 768, offsetTop: 0 },
    })
    const header = document.querySelector('header')
    const status = document.getElementById('status')
    const runBtn = document.getElementById('run-btn')
    const terminalWrap = document.querySelector('.terminal-wrap')
    const mobileShell = document.getElementById('mobile-shell')
    const mobileShellChrome = document.getElementById('mobile-shell-chrome')
    const mobileShellTranscript = document.getElementById('mobile-shell-transcript')
    const mobileShellComposer = document.getElementById('mobile-shell-composer')
    const mobileShellOverlays = document.getElementById('mobile-shell-overlays')
    const mobileComposerHost = document.getElementById('mobile-composer-host')
    const mobileComposerRow = document.getElementById('mobile-composer-row')
    const shellInputRow = document.getElementById('shell-input-row')
    const mobileCmdInput = document.getElementById('mobile-cmd')
    const mobileRunBtn = document.getElementById('mobile-run-btn')
    const histRow = document.getElementById('history-row')
    const terminalBar = document.querySelector('.terminal-bar')
    const searchBar = document.getElementById('search-bar')
    const tabPanels = document.getElementById('tab-panels')
    const historyPanel = document.getElementById('history-panel')
    const faqOverlay = document.getElementById('faq-overlay')
    const optionsOverlay = document.getElementById('options-overlay')

    document.body.classList.add('mobile-terminal-mode')
    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => mobileCmdInput,
    })
    window.visualViewport.height = 500
    mobileCmdInput.dispatchEvent(new Event('focus'))
    mobileCmdInput.value = 'curl'
    mobileCmdInput.dispatchEvent(new Event('input'))
    window.dispatchEvent(new Event('resize'))
    await new Promise(resolve => setTimeout(resolve, 10))

    expect(document.body.classList.contains('mobile-terminal-mode')).toBe(true)
    expect(document.body.classList.contains('mobile-keyboard-open')).toBe(true)
    expect(document.documentElement.style.getPropertyValue('--mobile-keyboard-offset')).toBe('268px')
    expect(terminalWrap.hidden).toBe(true)
    expect(mobileShell.hidden).toBe(false)
    expect(runBtn.hidden).toBe(true)
    expect(mobileComposerHost.getAttribute('aria-hidden')).toBe('false')
    expect(shellPromptWrap.getAttribute('aria-hidden')).toBe('true')
    expect(mobileComposerRow.hidden).toBe(false)
    expect(mobileShell.contains(histRow)).toBe(true)
    expect(mobileShell.contains(terminalBar)).toBe(true)
    expect(mobileShell.contains(searchBar)).toBe(true)
    expect(mobileShell.contains(tabPanels)).toBe(true)
    expect(mobileShell.contains(mobileComposerHost)).toBe(true)
    expect(mobileShell.contains(mobileShellChrome)).toBe(true)
    expect(mobileShell.contains(mobileShellTranscript)).toBe(true)
    expect(mobileShell.contains(mobileShellComposer)).toBe(true)
    expect(mobileShell.contains(mobileShellOverlays)).toBe(true)
    expect(header.contains(status)).toBe(true)
    expect(header.contains(document.getElementById('run-timer'))).toBe(true)
    expect(mobileShellChrome.contains(histRow)).toBe(true)
    expect(mobileShellChrome.contains(terminalBar)).toBe(true)
    expect(mobileShellChrome.contains(searchBar)).toBe(true)
    expect(mobileShellTranscript.contains(tabPanels)).toBe(true)
    expect(mobileShellComposer.contains(mobileComposerHost)).toBe(true)
    expect(mobileShellOverlays.contains(historyPanel)).toBe(true)
    expect(mobileShellOverlays.contains(faqOverlay)).toBe(true)
    expect(mobileShellOverlays.contains(optionsOverlay)).toBe(true)
    expect(mobileComposerRow.contains(mobileCmdInput)).toBe(true)
    expect(mobileComposerRow.contains(mobileRunBtn)).toBe(true)
    expect(mobileComposerRow.contains(shellInputRow)).toBe(false)
    expect(runBtn.hidden).toBe(true)
    expect(shellInputRow.hidden).toBe(true)
    expect(shellInputRow.getAttribute('aria-hidden')).toBe('true')
    expect(mobileComposerRow.querySelector('.mobile-prompt-label')?.textContent).toBe('$')
    expect(shellPromptWrap.scrollIntoView).not.toHaveBeenCalled()

    restoreViewport()
  })

  it('keeps the simplified mobile shell node structure intact while the keyboard is open', async () => {
    const { restoreViewport } = await loadAppFns({
      mobileViewport: { height: 768, offsetTop: 0 },
    })
    try {
      const header = document.querySelector('header')
      const status = document.getElementById('status')
      const runTimer = document.getElementById('run-timer')
      const histRow = document.getElementById('history-row')
      const terminalBar = document.querySelector('.terminal-bar')
      const searchBar = document.getElementById('search-bar')
      const tabPanels = document.getElementById('tab-panels')
      const historyPanel = document.getElementById('history-panel')
      const faqOverlay = document.getElementById('faq-overlay')
      const optionsOverlay = document.getElementById('options-overlay')
      const mobileShell = document.getElementById('mobile-shell')
      const mobileShellChrome = document.getElementById('mobile-shell-chrome')
      const mobileShellTranscript = document.getElementById('mobile-shell-transcript')
      const mobileShellComposer = document.getElementById('mobile-shell-composer')
      const mobileShellOverlays = document.getElementById('mobile-shell-overlays')
      const mobileComposerHost = document.getElementById('mobile-composer-host')
      const mobileCmdInput = document.getElementById('mobile-cmd')

      document.body.classList.add('mobile-terminal-mode')
      Object.defineProperty(document, 'activeElement', {
        configurable: true,
        get: () => mobileCmdInput,
      })
      window.visualViewport.height = 500
      mobileCmdInput.dispatchEvent(new Event('focus'))

      expect(header.contains(status)).toBe(true)
      expect(header.contains(runTimer)).toBe(true)
      expect(mobileShell.contains(mobileShellChrome)).toBe(true)
      expect(mobileShell.contains(mobileShellTranscript)).toBe(true)
      expect(mobileShell.contains(mobileShellComposer)).toBe(true)
      expect(mobileShell.contains(mobileShellOverlays)).toBe(true)
      expect(mobileShellChrome.contains(histRow)).toBe(true)
      expect(mobileShellChrome.contains(terminalBar)).toBe(true)
      expect(mobileShellChrome.contains(searchBar)).toBe(true)
      expect(mobileShellTranscript.contains(tabPanels)).toBe(true)
      expect(mobileShellComposer.contains(mobileComposerHost)).toBe(true)
      expect(mobileShellOverlays.contains(historyPanel)).toBe(true)
      expect(mobileShellOverlays.contains(faqOverlay)).toBe(true)
      expect(mobileShellOverlays.contains(optionsOverlay)).toBe(true)
    } finally {
      restoreViewport()
    }
  })

  it('keeps the active output pinned to the bottom when the mobile keyboard opens', async () => {
    const output = document.createElement('div')
    let scrollTop = 0
    Object.defineProperty(output, 'scrollTop', {
      configurable: true,
      get: () => scrollTop,
      set: value => { scrollTop = value },
    })
    Object.defineProperty(output, 'scrollHeight', {
      configurable: true,
      get: () => 300,
    })
    const { restoreViewport } = await loadAppFns({
      mobileViewport: { height: 768, offsetTop: 0 },
      tabs: [{ id: 'tab-1', followOutput: true, suppressOutputScrollTracking: false, _outputFollowToken: 0 }],
      getOutput: () => output,
    })
    try {
      const mobileCmdInput = document.getElementById('mobile-cmd')
      document.body.classList.add('mobile-terminal-mode')
      Object.defineProperty(document, 'activeElement', {
        configurable: true,
        get: () => mobileCmdInput,
      })

      scrollTop = 12
      window.visualViewport.height = 500
      mobileCmdInput.dispatchEvent(new Event('focus'))

      expect(scrollTop).toBe(300)
    } finally {
      restoreViewport()
    }
  })

  it('keeps the mobile keyboard helper row visible when the viewport resize lands before focus', async () => {
    const { syncMobileComposerKeyboardState, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 768, offsetTop: 0 },
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')

    document.body.classList.add('mobile-terminal-mode')
    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => mobileCmdInput,
    })

    syncMobileComposerKeyboardState(0, { active: true })
    syncMobileComposerKeyboardState(268, { active: true })
    expect(document.body.classList.contains('mobile-keyboard-open')).toBe(false)
    expect(document.documentElement.style.getPropertyValue('--mobile-keyboard-offset')).toBe('268px')
    mobileCmdInput.dispatchEvent(new Event('focus'))
    expect(document.body.classList.contains('mobile-keyboard-open')).toBe(true)
    expect(document.getElementById('mobile-edit-bar').hidden).toBe(false)

    restoreViewport()
  })

  it('does not programmatically focus the mobile composer', async () => {
    const { refocusTerminalInput, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const cmdInput = document.getElementById('cmd')
    const mobileCmdInput = document.getElementById('mobile-cmd')
    document.body.classList.add('mobile-terminal-mode')

    expect(refocusTerminalInput()).toBeUndefined()

    expect(mobileCmdInput.focus).not.toHaveBeenCalled()
    expect(cmdInput.focus).not.toHaveBeenCalled()

    restoreViewport()
  })

  it('does not programmatically refocus the mobile composer when the user taps the input', async () => {
    const { getVisibleComposerInput, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    try {
      const visibleInput = getVisibleComposerInput()
      document.body.classList.add('mobile-terminal-mode')

      const ev = new Event('pointerdown', { bubbles: true, cancelable: true })
      Object.assign(ev, { pointerType: 'touch' })
      visibleInput.dispatchEvent(ev)

      expect(visibleInput.focus).not.toHaveBeenCalled()
    } finally {
      restoreViewport()
    }
  })

  it('does not programmatically focus the mobile composer when the user taps the lower composer area', async () => {
    const { restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    try {
      const mobileComposerHost = document.getElementById('mobile-composer-host')
      const mobileCmdInput = document.getElementById('mobile-cmd')
      document.body.classList.add('mobile-terminal-mode')

      const ev = new Event('pointerdown', { bubbles: true, cancelable: true })
      Object.assign(ev, { pointerType: 'touch' })
      mobileComposerHost.dispatchEvent(ev)

      expect(mobileCmdInput.focus).not.toHaveBeenCalled()
    } finally {
      restoreViewport()
    }
  })

  it('prefers the mobile composer as the visible input while mobile mode is active', async () => {
    const { getVisibleComposerInput, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')
    const cmdInput = document.getElementById('cmd')
    document.body.classList.add('mobile-terminal-mode')

    expect(getVisibleComposerInput()).toBe(mobileCmdInput)
    expect(getVisibleComposerInput()).not.toBe(cmdInput)

    restoreViewport()
  })

  it('does not focus the mobile composer through the shared focus helper', async () => {
    const { focusVisibleComposerInput, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')
    const cmdInput = document.getElementById('cmd')
    document.body.classList.add('mobile-terminal-mode')

    expect(focusVisibleComposerInput({ preventScroll: true })).toBe(false)
    expect(mobileCmdInput.focus).not.toHaveBeenCalled()
    expect(cmdInput.focus).not.toHaveBeenCalled()

    restoreViewport()
  })

  it('focuses the desktop composer through the shared visible helper', async () => {
    const { focusVisibleComposerInput } = await loadAppFns()
    const cmdInput = document.getElementById('cmd')
    document.body.classList.remove('mobile-terminal-mode')

    expect(focusVisibleComposerInput({ preventScroll: true })).toBe(true)
    expect(cmdInput.focus).toHaveBeenCalled()
  })

  it('blurs the visible mobile composer through the shared blur helper', async () => {
    const { blurVisibleComposerInput, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')
    document.body.classList.add('mobile-terminal-mode')

    expect(blurVisibleComposerInput()).toBe(true)
    expect(mobileCmdInput.blur).toHaveBeenCalled()

    restoreViewport()
  })

  it('blurs the mobile composer through the shared mobile blur helper', async () => {
    const { blurVisibleComposerInputIfMobile, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')
    document.body.classList.add('mobile-terminal-mode')

    expect(blurVisibleComposerInputIfMobile()).toBe(true)
    expect(mobileCmdInput.blur).toHaveBeenCalled()

    restoreViewport()
  })

  it('reads the visible mobile composer value through the shared accessor', async () => {
    const { getComposerValue, setComposerState, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')
    document.body.classList.add('mobile-terminal-mode')

    mobileCmdInput.value = 'curl darklab.sh'
    setComposerState({ value: 'curl darklab.sh', selectionStart: 15, selectionEnd: 15, activeInput: 'mobile' })

    expect(getComposerValue()).toBe('curl darklab.sh')

    restoreViewport()
  })

  it('syncs mobile composer input through the shared input handler', async () => {
    const acShow = vi.fn()
    const { restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
      acShow,
      acSuggestions: ['curl http://localhost:5001/health'],
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')
    const cmdInput = document.getElementById('cmd')
    document.body.classList.add('mobile-terminal-mode')

    mobileCmdInput.value = 'curl'
    mobileCmdInput.dispatchEvent(new Event('input', { bubbles: true }))

    expect(mobileCmdInput.value).toBe('curl')
    expect(cmdInput.value).toBe('')
    expect(acShow).toHaveBeenCalledWith(['curl http://localhost:5001/health'])

    restoreViewport()
  })

  it('exposes the shared composer input handler for visible mobile input changes', async () => {
    const acShow = vi.fn()
    const { handleComposerInputChange, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
      acShow,
      acSuggestions: ['curl http://localhost:5001/health'],
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')
    const cmdInput = document.getElementById('cmd')
    document.body.classList.add('mobile-terminal-mode')

    mobileCmdInput.value = 'curl'
    handleComposerInputChange(mobileCmdInput)

    expect(mobileCmdInput.value).toBe('curl')
    expect(cmdInput.value).toBe('')
    expect(acShow).toHaveBeenCalledWith(['curl http://localhost:5001/health'])

    restoreViewport()
  })

  it('publishes mobile focus and selection changes into composer state without mirroring the hidden input', async () => {
    const { getComposerState, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    try {
      const mobileCmdInput = document.getElementById('mobile-cmd')
      const cmdInput = document.getElementById('cmd')
      document.body.classList.add('mobile-terminal-mode')

      mobileCmdInput.value = 'curl'
      mobileCmdInput.setSelectionRange(4, 4)
      Object.defineProperty(document, 'activeElement', {
        configurable: true,
        get: () => mobileCmdInput,
      })

      mobileCmdInput.dispatchEvent(new Event('focus'))
      document.dispatchEvent(new Event('selectionchange'))

      expect(getComposerState()).toEqual({
        value: 'curl',
        selectionStart: 4,
        selectionEnd: 4,
        activeInput: 'mobile',
      })
      expect(cmdInput.value).toBe('')
    } finally {
      restoreViewport()
    }
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

  it('sets the document title from the server config', async () => {
    await loadAppFns()
    await Promise.resolve()
    await Promise.resolve()

    expect(document.title).toBe('darklab shell')
  })

  it('updates existing terminal-wordmark elements with app name and version after config loads', async () => {
    // loadAppFns resets document.body.innerHTML internally, so the wordmark must be
    // injected after setup but before the async config handler drains.
    await loadAppFns()
    const wordmark = document.createElement('a')
    wordmark.className = 'terminal-wordmark'
    wordmark.href = '#'
    document.body.appendChild(wordmark)

    await new Promise(resolve => setImmediate(resolve))

    expect(wordmark.textContent).toBe('darklab shell v9.9')
    expect(wordmark.getAttribute('href')).toBe('https://gitlab.com/darklab.sh/darklab-shell#darklab-shell')
  })

  it('keeps the mobile run button visible after the keyboard closes', async () => {
    const { restoreViewport } = await loadAppFns({
      mobileViewport: { height: 768, offsetTop: 0 },
    })
    const runBtn = document.getElementById('run-btn')
    const mobileCmdInput = document.getElementById('mobile-cmd')

    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => mobileCmdInput,
    })
    window.visualViewport.height = 500
    mobileCmdInput.dispatchEvent(new Event('focus'))
    expect(runBtn.hidden).toBe(true)

    Object.defineProperty(window, 'visualViewport', {
      configurable: true,
      value: {
        height: 768,
        offsetTop: 0,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      },
    })
    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => document.body,
    })
    mobileCmdInput.dispatchEvent(new Event('blur'))

    expect(document.body.classList.contains('mobile-terminal-mode')).toBe(true)
    expect(document.body.classList.contains('mobile-keyboard-open')).toBe(false)
    expect(runBtn.hidden).toBe(true)

    restoreViewport()
  })

  it('submits the visible mobile composer through the shared submit helper', async () => {
    const submitVisibleComposerCommand = vi.fn(() => true)
    const runCommand = vi.fn()
    const { restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
      submitVisibleComposerCommand,
      runCommand,
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')
    const mobileRunBtn = document.getElementById('mobile-run-btn')

    mobileCmdInput.dispatchEvent(new Event('focus'))
    mobileCmdInput.value = 'curl darklab.sh'
    mobileCmdInput.dispatchEvent(new Event('input'))
    mobileRunBtn.click()

    expect(submitVisibleComposerCommand).toHaveBeenCalledWith({ dismissKeyboard: true, focusAfterSubmit: false })
    expect(runCommand).not.toHaveBeenCalled()

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

  it('keeps the mobile composer host free of keyboard-height spacing in the simplified shell', () => {
    const css = readFileSync(resolve(process.cwd(), 'app/static/css/mobile.css'), 'utf8')
    const match = css.match(/body\.mobile-terminal-mode #mobile-composer-host\s*\{([\s\S]*?)\}/)

    expect(match).not.toBeNull()
    expect(match[1]).not.toMatch(/margin-bottom\s*:/)
  })

  it('keeps the themed mobile composer surfaces free of hard-coded dark colors', () => {
    const css = readFileSync(resolve(process.cwd(), 'app/static/css/mobile.css'), 'utf8')
    const shellMatch = css.match(/body\.mobile-terminal-mode #mobile-shell-composer\s*\{([\s\S]*?)\}/)
    const composerMatch = css.match(/body\.mobile-terminal-mode #mobile-shell-composer #mobile-composer\s*\{([\s\S]*?)\}/)

    expect(shellMatch).not.toBeNull()
    expect(shellMatch[1]).toMatch(/background:\s*var\(--theme-mobile-composer-host-bg\)/)
    expect(shellMatch[1]).not.toMatch(/rgba\(13,13,13/)

    expect(composerMatch).not.toBeNull()
    expect(composerMatch[1]).toMatch(/background:\s*var\(--theme-panel-bg\)/)
    expect(composerMatch[1]).toMatch(/border:\s*1px solid var\(--theme-panel-border\)/)
    expect(composerMatch[1]).toMatch(/box-shadow:\s*0 10px 30px var\(--theme-panel-shadow\)/)
    expect(composerMatch[1]).not.toMatch(/rgba\(13,13,13/)
  })

  it('disables both run buttons for an empty command and enables them once input is present', async () => {
    const { handleComposerInputChange, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    try {
      const runBtn = document.getElementById('run-btn')
      const mobileRunBtn = document.getElementById('mobile-run-btn')
      const mobileCmdInput = document.getElementById('mobile-cmd')
      document.body.classList.add('mobile-terminal-mode')

      expect(runBtn.disabled).toBe(true)
      expect(mobileRunBtn.disabled).toBe(true)

      mobileCmdInput.value = 'ping darklab.sh'
      mobileCmdInput.setSelectionRange(mobileCmdInput.value.length, mobileCmdInput.value.length)
      handleComposerInputChange(mobileCmdInput)

      expect(runBtn.disabled).toBe(false)
      expect(mobileRunBtn.disabled).toBe(false)

      mobileCmdInput.value = '   '
      mobileCmdInput.setSelectionRange(mobileCmdInput.value.length, mobileCmdInput.value.length)
      handleComposerInputChange(mobileCmdInput)

      expect(runBtn.disabled).toBe(true)
      expect(mobileRunBtn.disabled).toBe(true)
    } finally {
      restoreViewport()
    }
  })

  it('keeps both run buttons in sync for programmatic composer value changes', async () => {
    const { setComposerValue } = await loadAppFns()
    const runBtn = document.getElementById('run-btn')
    const mobileRunBtn = document.getElementById('mobile-run-btn')

    expect(runBtn.disabled).toBe(true)
    expect(mobileRunBtn.disabled).toBe(true)

    setComposerValue('ping darklab.sh', 15, 15, { dispatch: false })
    expect(runBtn.disabled).toBe(false)
    expect(mobileRunBtn.disabled).toBe(false)

    setComposerValue('   ', 3, 3, { dispatch: false })
    expect(runBtn.disabled).toBe(true)
    expect(mobileRunBtn.disabled).toBe(true)
  })

  it('closes transient ui while the mobile keyboard is open', async () => {
    const { restoreViewport } = await loadAppFns({
      mobileViewport: { height: 768, offsetTop: 0 },
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')

    document.getElementById('mobile-menu').classList.add('open')
    document.getElementById('history-panel').classList.add('open')

    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => mobileCmdInput,
    })
    window.visualViewport.height = 500
    mobileCmdInput.dispatchEvent(new Event('focus'))
    mobileCmdInput.value = 'curl'
    mobileCmdInput.dispatchEvent(new Event('input'))

    expect(document.getElementById('mobile-menu').classList.contains('open')).toBe(false)
    expect(document.getElementById('history-panel').classList.contains('open')).toBe(false)

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
          app_name: 'darklab shell',
          prompt_prefix: 'anon@darklab:~$',
          version: '9.9',
          default_theme: 'darklab_obsidian.yaml',
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

  it('hides autocomplete when the typed command exactly matches a suggestion', async () => {
    const acHide = vi.fn()
    const { cmdInput } = await loadAppFns({
      acSuggestions: ['man curl', 'curl http://localhost:5001/health'],
      acHide,
    })

    cmdInput.value = 'man curl'
    cmdInput.dispatchEvent(new Event('input'))

    expect(acHide).toHaveBeenCalled()
    expect(document.getElementById('ac-dropdown').style.display).toBe('none')
  })

  it('renders cursor and selection state from composer state', async () => {
    const { cmdInput, setComposerState, syncShellPrompt } = await loadAppFns()
    const shellPromptText = document.getElementById('shell-prompt-text')
    const shellPromptWrap = document.getElementById('shell-prompt-wrap')

    cmdInput.value = 'stale'
    cmdInput.setSelectionRange(0, 0)
    setComposerState({
      value: 'nothing',
      selectionStart: 3,
      selectionEnd: 3,
      activeInput: 'desktop',
    })
    syncShellPrompt()
    expect(shellPromptText.querySelector('.shell-caret-char')?.textContent).toBe('h')
    expect(shellPromptWrap.classList.contains('shell-prompt-has-selection')).toBe(false)

    setComposerState({
      selectionStart: 1,
      selectionEnd: 4,
    })
    syncShellPrompt()
    expect(shellPromptText.querySelector('.shell-prompt-selection')?.textContent).toBe('oth')
    expect(shellPromptWrap.classList.contains('shell-prompt-has-selection')).toBe(true)
  })

  it('supports ctrl+w to delete one word to the left', async () => {
    const { cmdInput, setComposerState } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.setSelectionRange(cmdInput.value.length, cmdInput.value.length)
    setComposerState({
      value: 'dig darklab.sh A',
      selectionStart: cmdInput.value.length,
      selectionEnd: cmdInput.value.length,
      activeInput: 'desktop',
    })
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'w', ctrlKey: true, bubbles: true }))

    expect(cmdInput.value).toBe('dig darklab.sh ')
  })

  it('supports ctrl+u to delete to the beginning of the line', async () => {
    const { cmdInput, setComposerState } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.setSelectionRange(12, 12)
    setComposerState({ value: 'dig darklab.sh A', selectionStart: 12, selectionEnd: 12, activeInput: 'desktop' })
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
    const { cmdInput, setComposerState } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.setSelectionRange(4, 4)
    setComposerState({ value: 'dig darklab.sh A', selectionStart: 4, selectionEnd: 4, activeInput: 'desktop' })
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true }))

    expect(cmdInput.value).toBe('dig ')
    expect(cmdInput.selectionStart).toBe(4)
    expect(cmdInput.selectionEnd).toBe(4)
  })

  it('supports ctrl+e to move to the end of the line', async () => {
    const { cmdInput, setComposerState } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.setSelectionRange(4, 4)
    setComposerState({
      value: 'dig darklab.sh A',
      selectionStart: 4,
      selectionEnd: 4,
      activeInput: 'desktop',
    })
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'e', ctrlKey: true, bubbles: true }))

    expect(cmdInput.selectionStart).toBe(cmdInput.value.length)
    expect(cmdInput.selectionEnd).toBe(cmdInput.value.length)
  })

  it('supports Alt+B and Alt+F to move by word', async () => {
    const { cmdInput, setComposerState } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.setSelectionRange(cmdInput.value.length, cmdInput.value.length)
    setComposerState({
      value: 'dig darklab.sh A',
      selectionStart: cmdInput.value.length,
      selectionEnd: cmdInput.value.length,
      activeInput: 'desktop',
    })
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
    const { cmdInput, setComposerState } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.setSelectionRange(cmdInput.value.length, cmdInput.value.length)
    setComposerState({
      value: 'dig darklab.sh A',
      selectionStart: cmdInput.value.length,
      selectionEnd: cmdInput.value.length,
      activeInput: 'desktop',
    })
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
    const { getVisibleComposerInput, setComposerState } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const press = (selector) => {
      document.querySelector(selector).dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))
    }

    document.body.classList.add('mobile-terminal-mode')
    const cmdInput = document.getElementById('cmd')
    const mobileCmdInput = document.getElementById('mobile-cmd')
    cmdInput.value = 'ping -c 4 example.com'
    mobileCmdInput.value = 'ping -c 4 example.com'
    cmdInput.setSelectionRange(cmdInput.value.length, cmdInput.value.length)
    mobileCmdInput.setSelectionRange(mobileCmdInput.value.length, mobileCmdInput.value.length)
    setComposerState({
      value: mobileCmdInput.value,
      selectionStart: mobileCmdInput.value.length,
      selectionEnd: mobileCmdInput.value.length,
      activeInput: 'mobile',
    })
    const visibleInput = getVisibleComposerInput()

    press('[data-edit-action="left"]')
    expect(visibleInput.selectionStart).toBe(visibleInput.value.length - 1)

    press('[data-edit-action="home"]')
    expect(visibleInput.selectionStart).toBe(0)

    press('[data-edit-action="right"]')
    expect(visibleInput.selectionStart).toBe(1)

    press('[data-edit-action="end"]')
    expect(visibleInput.selectionStart).toBe(visibleInput.value.length)

    press('[data-edit-action="delete-word"]')
    expect(visibleInput.value).toBe('ping -c 4 ')
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

  it('supports Ctrl+L to clear the active tab without dropping a running command', async () => {
    const clearTab = vi.fn()
    const cancelWelcome = vi.fn()
    const { cmdInput } = await loadAppFns({
      clearTab,
      cancelWelcome,
      tabs: [{ id: 'tab-1', st: 'running' }],
      activeTabId: 'tab-1',
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'l', ctrlKey: true, bubbles: true }))

    expect(cancelWelcome).toHaveBeenCalledWith('tab-1')
    expect(clearTab).toHaveBeenCalledWith('tab-1', { preserveRunState: true })
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

  it('ArrowDown/Up wrap around and navigate the same direction regardless of whether the list is above or below the prompt', async () => {
    const acFiltered = ['alpha', 'bravo', 'charlie']
    const { cmdInput, _getAcIndex, acDropdown } = await loadAppFns({
      acFiltered,
      acIndex: -1,
    })

    acDropdown.style.display = 'block'
    acDropdown.classList.add('ac-up')

    // ArrowUp from no selection (-1) wraps to the last item
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }))
    expect(_getAcIndex()).toBe(2)

    // ArrowUp from last wraps to first... actually moves up
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }))
    expect(_getAcIndex()).toBe(1)

    // ArrowDown always moves toward higher index (toward 'charlie'), regardless of ac-up
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }))
    expect(_getAcIndex()).toBe(2)

    // ArrowDown at the last item wraps to the first
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }))
    expect(_getAcIndex()).toBe(0)

    // ArrowUp at the first item wraps to the last
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }))
    expect(_getAcIndex()).toBe(2)
  })

  it('Tab key with a modifier does not trigger autocomplete accept or selection', async () => {
    const { cmdInput, _getAcIndex } = await loadAppFns({
      acFiltered: ['alpha', 'bravo'],
      acIndex: -1,
    })

    // Alt+Tab (the app tab-cycle shortcut) must not trigger autocomplete
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', altKey: true, bubbles: true }))
    expect(_getAcIndex()).toBe(-1)

    // Ctrl+Tab must not trigger autocomplete
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', ctrlKey: true, bubbles: true }))
    expect(_getAcIndex()).toBe(-1)

    // Meta+Tab must not trigger autocomplete
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', metaKey: true, bubbles: true }))
    expect(_getAcIndex()).toBe(-1)

    // Plain Tab (no modifier) still triggers autocomplete selection
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(_getAcIndex()).toBe(0)
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

  it('does not refocus the mobile composer when closing the kill confirmation modal', async () => {
    const doKill = vi.fn()
    const { getVisibleComposerInput, showKillOverlay, isKillOverlayOpen, confirmPendingKill, closeKillOverlay } = await loadAppFns({
      doKill,
      pendingKillTabId: 'tab-1',
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const visibleInput = getVisibleComposerInput()
    visibleInput.focus.mockClear()

    showKillOverlay()
    expect(isKillOverlayOpen()).toBe(true)
    confirmPendingKill()
    expect(doKill).toHaveBeenCalledWith('tab-1')
    expect(isKillOverlayOpen()).toBe(false)
    expect(visibleInput.focus).not.toHaveBeenCalled()

    visibleInput.focus.mockClear()
    showKillOverlay()
    closeKillOverlay()
    expect(isKillOverlayOpen()).toBe(false)
    expect(visibleInput.focus).not.toHaveBeenCalled()
  })

  it('wires the share redaction modal buttons, remember choice, and backdrop correctly', async () => {
    const {
      confirmPermalinkRedactionChoice,
      isShareRedactionOverlayOpen,
      getRememberedShareRedactionChoice,
      sessionStorage,
    } = await loadAppFns()
    const shareRedactionOverlay = document.getElementById('share-redaction-overlay')
    const rememberToggle = document.getElementById('share-redaction-remember-toggle')

    const redactedChoice = confirmPermalinkRedactionChoice()
    expect(isShareRedactionOverlayOpen()).toBe(true)
    rememberToggle.checked = true
    document.getElementById('share-redaction-confirm').click()
    await expect(redactedChoice).resolves.toBe('redacted')
    expect(shareRedactionOverlay.style.display).toBe('none')
    expect(getRememberedShareRedactionChoice()).toBe('redacted')
    expect(sessionStorage.getItem('share_redaction_choice')).toBe('redacted')

    await expect(confirmPermalinkRedactionChoice()).resolves.toBe('redacted')
    expect(shareRedactionOverlay.style.display).toBe('none')

    sessionStorage.removeItem('share_redaction_choice')
    const rawChoice = confirmPermalinkRedactionChoice()
    expect(isShareRedactionOverlayOpen()).toBe(true)
    document.getElementById('share-redaction-raw').click()
    await expect(rawChoice).resolves.toBe('raw')
    expect(getRememberedShareRedactionChoice()).toBe(null)

    const cancelChoice = confirmPermalinkRedactionChoice()
    shareRedactionOverlay.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await expect(cancelChoice).resolves.toBe(null)
    expect(shareRedactionOverlay.style.display).toBe('none')
  })

  it('wires search controls and Escape dismissal correctly', async () => {
    const { runSearch, clearSearch, navigateSearch, cmdInput } = await loadAppFns()
    const searchBar = document.getElementById('search-bar')
    const searchInput = document.getElementById('search-input')

    cmdInput.focus.mockClear()
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
    await new Promise(resolve => setTimeout(resolve, 10))
    expect(searchBar.style.display).toBe('none')
    expect(clearSearch).toHaveBeenCalled()

    searchBar.style.display = 'none'
    cmdInput.focus.mockClear()
    document.getElementById('search-toggle-btn').click()
    document.getElementById('search-toggle-btn').click()
    expect(clearSearch).toHaveBeenCalledTimes(3)
    expect(searchBar.style.display).toBe('none')
  })

  it('refocuses the visible mobile composer after closing search with Escape', async () => {
    const { getVisibleComposerInput, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const searchBar = document.getElementById('search-bar')
    const searchInput = document.getElementById('search-input')
    const visibleInput = getVisibleComposerInput()

    document.getElementById('search-toggle-btn').click()
    expect(searchBar.style.display).toBe('flex')

    searchInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))

    expect(searchBar.style.display).toBe('none')
    expect(visibleInput.focus).not.toHaveBeenCalled()

    restoreViewport()
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

  it('closes the theme overlay and refocuses the terminal on Escape', async () => {
    await loadAppFns({
      mobileTouch: false,
      themeRegistry: {
        current: {
          name: 'theme_light_blue',
          label: 'Blue Paper',
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Blue Paper',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
        ],
      },
    })
    const themeOverlay = document.getElementById('theme-overlay')

    document.getElementById('theme-btn').click()
    expect(themeOverlay.classList.contains('open')).toBe(true)

    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(themeOverlay.classList.contains('open')).toBe(false)
  })

  it('does not refocus the mobile composer when closing options', async () => {
    const { getVisibleComposerInput } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const overlay = document.getElementById('options-overlay')
    const visibleInput = getVisibleComposerInput()
    visibleInput.focus.mockClear()

    document.getElementById('options-btn').click()
    expect(overlay.classList.contains('open')).toBe(true)

    document.querySelector('.options-close').click()
    expect(overlay.classList.contains('open')).toBe(false)
    expect(visibleInput.focus).not.toHaveBeenCalled()

    document.querySelector('#mobile-menu [data-action="options"]').click()
    expect(overlay.classList.contains('open')).toBe(true)

    overlay.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(overlay.classList.contains('open')).toBe(false)
  })

  it('blurs the visible mobile composer when opening options', async () => {
    const { getVisibleComposerInput, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const overlay = document.getElementById('options-overlay')
    const visibleInput = getVisibleComposerInput()
    document.body.classList.add('mobile-terminal-mode')

    document.getElementById('options-btn').click()

    expect(overlay.classList.contains('open')).toBe(true)
    expect(visibleInput.blur).toHaveBeenCalled()

    restoreViewport()
  })

  it('persists options changes through cookies and syncs quick-toggle state', async () => {
    await loadAppFns({
      themeRegistry: {
        current: {
          name: 'theme_light_blue',
          label: 'Blue Paper',
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Blue Paper',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
          {
            name: 'theme_light_olive',
            label: 'Olive Parchment',
            source: 'variant',
            vars: { '--bg': '#c0c0a8' },
          },
        ],
      },
    })

    document.getElementById('theme-btn').click()
    document.getElementById('theme-select').querySelector('[data-theme-name="theme_light_olive"]').click()
    document.getElementById('theme-overlay').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    document.getElementById('options-btn').click()
    document.getElementById('options-ts-select').value = 'elapsed'
    document.getElementById('options-ts-select').dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('options-ln-toggle').checked = true
    document.getElementById('options-ln-toggle').dispatchEvent(new Event('change', { bubbles: true }))

    expect(document.body.classList.contains('ts-elapsed')).toBe(true)
    expect(document.body.classList.contains('ln-on')).toBe(true)
    expect(document.getElementById('ts-btn').textContent).toBe('timestamps: elapsed')
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers: on')
    expect(document.cookie).toContain('pref_theme_name=theme_light_olive')
    expect(document.cookie).toContain('pref_timestamps=elapsed')
    expect(document.cookie).toContain('pref_line_numbers=on')
  })

  it('renders backend-driven FAQ items with HTML answers and dynamic sections', async () => {
    const apiFetch = vi.fn((url) => {
    if (url === '/config') {
      return Promise.resolve({
        json: () => Promise.resolve({
          app_name: 'darklab shell',
          prompt_prefix: 'anon@darklab:~$',
          version: '9.9',
          default_theme: 'darklab_obsidian.yaml',
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

  it('loads FAQ command chips into the visible mobile composer and refocuses it', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/config') {
        return Promise.resolve({
        json: () => Promise.resolve({
          app_name: 'darklab shell',
          prompt_prefix: 'anon@darklab:~$',
          version: '9.9',
            default_theme: 'darklab_obsidian.yaml',
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
            commands: ['curl'],
            groups: [{ name: 'Network', commands: ['curl'] }],
          }),
        })
      }
      if (url === '/faq') {
        return Promise.resolve({
          json: () => Promise.resolve({
            items: [
              { question: 'Allowed?', answer: 'allowlist', ui_kind: 'allowed_commands' },
            ],
          }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })

    await loadAppFns({ apiFetch, mobileViewport: { height: 500, offsetTop: 0 } })
    await new Promise(resolve => setImmediate(resolve))

    const mobileCmdInput = document.getElementById('mobile-cmd')
    const faqBtn = document.getElementById('faq-btn')
    const chip = document.querySelector('.allowed-chip')

    faqBtn.click()
    expect(mobileCmdInput.blur).toHaveBeenCalled()

    chip.click()

    expect(mobileCmdInput.value).toBe('curl ')
    expect(mobileCmdInput.focus).not.toHaveBeenCalled()
  })

  it('loads custom FAQ chips into the prompt with the same command-chip behavior', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/config') {
        return Promise.resolve({
          json: () => Promise.resolve({
            app_name: 'darklab shell',
            prompt_prefix: 'anon@darklab:~$',
            version: '9.9',
            default_theme: 'darklab_obsidian.yaml',
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
            commands: ['curl'],
            groups: [{ name: 'Network', commands: ['curl'] }],
          }),
        })
      }
      if (url === '/faq') {
        return Promise.resolve({
          json: () => Promise.resolve({
            items: [
              {
                question: 'Styled custom FAQ?',
                answer: 'Use [[cmd:ping -c 1 127.0.0.1|ping chip]] and **bold**.',
                answer_html: 'Use <span class="allowed-chip faq-chip" data-faq-command="ping -c 1 127.0.0.1" role="button" tabindex="0">ping chip</span> and <strong>bold</strong>.',
              },
            ],
          }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })

    await loadAppFns({ apiFetch, mobileViewport: { height: 500, offsetTop: 0 } })
    await new Promise(resolve => setImmediate(resolve))

    const chip = document.querySelector('.faq-item .faq-chip[data-faq-command="ping -c 1 127.0.0.1"]')
    expect(chip).not.toBeNull()

    chip.click()

    expect(document.getElementById('mobile-cmd').value).toBe('ping -c 1 127.0.0.1 ')
    expect(document.getElementById('faq-overlay').classList.contains('open')).toBe(false)
  })
})
