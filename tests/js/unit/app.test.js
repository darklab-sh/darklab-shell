import { readFileSync, readdirSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'
import yaml from 'js-yaml'
import { MemoryStorage, fromDomScripts } from './helpers/extract.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const THEME_META_KEYS = new Set(['label', 'group', 'sort'])
const THEME_BASE_KEYS = new Set([
  'bg',
  'surface',
  'border',
  'border_bright',
  'border_soft',
  'text',
  'muted',
  'green',
  'green_dim',
  'green_glow',
  'amber',
  'red',
  'blue',
  'terminal_font_size',
  'terminal_line_height',
])

// This harness recreates the browser-global environment expected by the classic
// script bundle so app.js can be tested without loading the full page.
async function loadAppFns({
  theme = null,
  themeRegistry = null,
  cookies = {},
  apiFetch: apiFetchOverride = null,
  showConfirm: showConfirmOverride = null,
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
  openWorkspace: openWorkspaceOverride = vi.fn(),
  openRunMonitor: openRunMonitorOverride = vi.fn(() => Promise.resolve(false)),
  activeTabId = 'tab-1',
  acFiltered: acFilteredOverride = [],
  acSuggestions: acSuggestionsOverride = [],
  acContextRegistry: acContextRegistryOverride = {},
  getAutocompleteMatches: getAutocompleteMatchesOverride = null,
  acIndex: acIndexOverride = -1,
  acShow: acShowOverride = () => {},
  acHide: acHideOverride = () => {},
  acExpandSharedPrefix: acExpandSharedPrefixOverride = () => false,
  getOutput: getOutputOverride = null,
  mobileViewport = null,
  mobileTouch = true,
  Notification: NotificationOverride = undefined,
  showToast: showToastOverride = vi.fn(),
  updateSessionId: updateSessionIdOverride = vi.fn(),
  copyTextToClipboard: copyTextToClipboardOverride = vi.fn(() => Promise.resolve()),
  reloadSessionHistory: reloadSessionHistoryOverride = vi.fn(() => Promise.resolve()),
  seedLocalStorageStarsToServer: seedLocalStorageStarsToServerOverride = vi.fn(() => Promise.resolve()),
  hydrateCmdHistory: hydrateCmdHistoryOverride = vi.fn(),
  hasPendingTerminalConfirm: hasPendingTerminalConfirmOverride = vi.fn(() => false),
  cancelPendingTerminalConfirm: cancelPendingTerminalConfirmOverride = vi.fn(() => false),
  getWorkspaceAutocompleteFileHints: getWorkspaceAutocompleteFileHintsOverride = vi.fn(() => []),
  sessionVariables: sessionVariablesOverride = [],
  appConfig = { workspace_enabled: true },
  sessionId = 'session-old',
} = {}) {
  document.body.className = ''
  document.body.innerHTML = `
    <header><h1></h1></header>
    <button id="ts-btn"></button>
    <button id="hamburger-btn"></button>
    <button id="new-tab-btn"></button>
    <button id="search-toggle-btn"></button>
    <button id="ln-btn"></button>
    <button id="history-close"></button>
    <button id="hist-clear-all-btn"></button>
    <nav class="rail-nav" id="rail-nav">
      <button class="rail-nav-item" data-action="options" type="button"></button>
      <button class="rail-nav-item" data-action="history" type="button"></button>
      <button class="rail-nav-item" data-action="theme" type="button"></button>
      <button class="rail-nav-item" data-action="faq" type="button"></button>
      <a class="rail-nav-item u-hidden" data-action="diag" id="rail-diag-btn" href="/diag"></a>
    </nav>
    <div id="mobile-shell" aria-hidden="true">
      <div id="mobile-shell-chrome"></div>
      <div id="mobile-shell-transcript"></div>
      <div id="mobile-shell-composer">
        <div id="mobile-composer-host">
          <div id="mobile-composer-row">
            <span class="mobile-prompt-label">$</span>
            <input id="mobile-cmd" autocomplete="off" autocapitalize="none" autocorrect="off" spellcheck="false" inputmode="text" />
            <button id="mobile-run-btn"></button>
          </div>
        </div>
      </div>
      <div id="mobile-shell-overlays">
        <div id="mobile-menu-sheet" class="menu-sheet u-hidden">
          <button data-menu-action="ln"></button>
          <button data-menu-action="ts-toggle" aria-expanded="false" aria-controls="mobile-menu-ts-submenu"></button>
          <div id="mobile-menu-ts-submenu" class="menu-submenu u-hidden">
            <button data-menu-action="ts-set" data-ts-mode="off"></button>
            <button data-menu-action="ts-set" data-ts-mode="elapsed"></button>
            <button data-menu-action="ts-set" data-ts-mode="clock"></button>
          </div>
          <button data-menu-action="search"></button>
          <button data-menu-action="clear"></button>
          <button data-menu-action="history"></button>
          <button data-menu-action="options"></button>
          <button data-menu-action="theme"></button>
          <button data-menu-action="faq"></button>
        </div>
      </div>
    </div>
    <div class="terminal-wrap">
      <div id="history-row" class="history-row" style="display:none">
        <span class="history-label">Recent:</span>
      </div>
      <div class="terminal-bar">
        <button id="tabs-scroll-left"></button>
        <div class="tabs-bar" id="tabs-bar"></div>
        <button id="tabs-scroll-right"></button>
        <span id="status"></span>
        <span id="run-timer"></span>
      </div>
      <div id="shell-prompt-wrap" class="prompt-wrap shell-prompt-wrap">
        <span class="prompt-prefix" data-mobile-label="$">anon@darklab:~$</span>
        <div id="shell-prompt-line">
          <span id="shell-prompt-text" class="shell-prompt-text"></span>
          <span id="shell-prompt-caret"></span>
        </div>
        <div id="ac-dropdown" style="display:none"></div>
        <button id="run-btn" aria-label="Run command">Run</button>
      </div>
      <div class="search-bar" id="search-bar" style="display:none">
        <input id="search-input" type="text" placeholder="Search output…" autocomplete="off" autocapitalize="none" autocorrect="off" spellcheck="false" inputmode="text" aria-label="Search output">
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
    <span id="options-session-token-status"></span>
    <button id="options-session-token-generate-btn"></button>
    <button id="options-session-token-set-btn"></button>
    <button id="options-session-token-rotate-btn"></button>
    <button id="options-session-token-clear-btn"></button>
    <button id="options-session-token-copy-btn"></button>
    <div id="options-session-token-msg"></div>
    <div id="workflows-overlay"></div>
    <button class="workflows-close"></button>
    <select id="options-ts-select">
      <option value="off">off</option>
      <option value="elapsed">elapsed</option>
      <option value="clock">clock</option>
      </select>
      <input id="options-ln-toggle" type="checkbox" />
      <select id="options-welcome-select">
        <option value="animated">animated</option>
        <option value="disable_animation">disable_animation</option>
        <option value="remove">remove</option>
      </select>
      <select id="options-share-redaction-select">
        <option value="unset">unset</option>
        <option value="redacted">redacted</option>
        <option value="raw">raw</option>
      </select>
      <input id="options-notify-toggle" type="checkbox" />
      <select id="options-hud-clock-select">
        <option value="utc">utc</option>
        <option value="local">local</option>
      </select>
      <div id="shell-input-row" data-mobile-label="$">
        <input id="cmd" />
      </div>
      <div id="history-panel"></div>
      <div id="history-list"></div>
      <div id="permalink-toast"></div>
      <div class="prompt-wrap"></div>
    </div>
  `

  const storage = new MemoryStorage()
  const sessionStore = new MemoryStorage()
  const tabsState = tabsOverride
  let activeTabState = activeTabId
  if (theme !== null) storage.setItem('theme', theme)
  for (const [name, value] of Object.entries(cookies)) {
    document.cookie = `${name}=${encodeURIComponent(value)}; path=/`
  }

  const apiFetch =
    apiFetchOverride ||
    vi.fn((url) => {
      if (url === '/config') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
              prompt_prefix: 'anon@darklab:~$',
              version: '9.9',
              project_readme: 'https://gitlab.com/darklab.sh/darklab_shell',
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
        return Promise.resolve({
          json: () => Promise.resolve({ restricted: false, commands: [], groups: [] }),
        })
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
  const appendLine = vi.fn()
  const appendCommandEcho = vi.fn()
  const setStatus = vi.fn()
  const recordSuccessfulLocalCommand = vi.fn()
  const getTab = vi.fn((id) => tabsState.find((tab) => tab && tab.id === id) || null)
  const getActiveTab = vi.fn(
    () => tabsState.find((tab) => tab && tab.id === activeTabState) || null,
  )
  const setTabs = vi.fn((nextTabs) => {
    tabsState.splice(0, tabsState.length, ...nextTabs)
  })
  const setActiveTabId = vi.fn((id) => {
    activeTabState = id
  })
  const cmdInput = document.getElementById('cmd')
  const acDropdown = document.getElementById('ac-dropdown')
  const domBindings = {
    hamburgerBtn: document.getElementById('hamburger-btn'),
    faqCloseBtn: document.querySelector('.faq-close'),
    optionsCloseBtn: document.querySelector('.options-close'),
    themeCloseBtn: document.querySelector('.theme-close'),
    newTabBtn: document.getElementById('new-tab-btn'),
    searchToggleBtn: document.getElementById('search-toggle-btn'),
    historyCloseBtn: document.getElementById('history-close'),
    histClearAllBtn: document.getElementById('hist-clear-all-btn'),
    searchPrevBtn: document.getElementById('search-prev'),
    searchNextBtn: document.getElementById('search-next'),
    searchCloseBtn: document.getElementById('search-close-btn'),
    optionsTsSelect: document.getElementById('options-ts-select'),
    optionsLnToggle: document.getElementById('options-ln-toggle'),
    optionsWelcomeSelect: document.getElementById('options-welcome-select'),
    optionsShareRedactionSelect: document.getElementById('options-share-redaction-select'),
    optionsNotifyToggle: document.getElementById('options-notify-toggle'),
    optionsHudClockSelect: document.getElementById('options-hud-clock-select'),
    themeSelect: document.getElementById('theme-select'),
    tsBtn: document.getElementById('ts-btn'),
    lnBtn: document.getElementById('ln-btn'),
    headerTitle: document.querySelector('header h1'),
    faqBody: document.querySelector('.faq-body'),
    status: document.getElementById('status'),
    histRow: document.getElementById('history-row'),
    tabsBar: document.getElementById('tabs-bar'),
    tabPanels: document.getElementById('tab-panels'),
    themeOverlay: document.getElementById('theme-overlay'),
    mobileShell: document.getElementById('mobile-shell'),
    mobileShellChrome: document.getElementById('mobile-shell-chrome'),
    mobileShellTranscript: document.getElementById('mobile-shell-transcript'),
    mobileShellOverlays: document.getElementById('mobile-shell-overlays'),
    mobileComposerHost: document.getElementById('mobile-composer-host'),
    mobileComposerRow: document.getElementById('mobile-composer-row'),
    mobileCmdInput: document.getElementById('mobile-cmd'),
    mobileRunBtn: document.getElementById('mobile-run-btn'),
    mobileMenu: document.getElementById('mobile-menu-sheet'),
    searchBar: document.getElementById('search-bar'),
    searchInput: document.getElementById('search-input'),
    searchCount: document.getElementById('search-count'),
    historyPanel: document.getElementById('history-panel'),
    historyList: document.getElementById('history-list'),
    historyLoadOverlay: document.getElementById('history-load-overlay'),
    acDropdown,
    faqOverlay: document.getElementById('faq-overlay'),
    optionsOverlay: document.getElementById('options-overlay'),
    workflowsOverlay: document.getElementById('workflows-overlay'),
    workflowsCloseBtn: document.querySelector('.workflows-close'),
    permalinkToast: document.getElementById('permalink-toast'),
    runTimer: document.getElementById('run-timer'),
    searchCaseBtn: document.getElementById('search-case-btn'),
    searchRegexBtn: document.getElementById('search-regex-btn'),
    shellPromptWrap: document.getElementById('shell-prompt-wrap'),
    shellPromptText: document.getElementById('shell-prompt-text'),
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
  mobileCmdInput.focus = vi.fn()
  mobileCmdInput.blur = vi.fn()

  const originalMatchMedia = window.matchMedia
  const originalVisualViewport = window.visualViewport
  const originalScrollTo = window.scrollTo
  const originalMaxTouchPoints = navigator.maxTouchPoints
  window.scrollTo = vi.fn()
  if (mobileViewport) {
    const matchMediaMock = vi.fn((query) => {
      const q = String(query || '')
      const maxWidth = /max-width:\s*900px/.test(q)
      const coarse = /pointer:\s*coarse/.test(q)
      return {
        matches: mobileTouch ? maxWidth || coarse : maxWidth,
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

  const fns = fromDomScripts(
    ['app/static/js/output.js', 'app/static/js/app.js', 'app/static/js/controller.js'],
    {
      document,
      localStorage: storage,
      sessionStorage: sessionStore,
      apiFetch,
      APP_CONFIG: appConfig,
      AnsiUp: FakeAnsiUp,
      showConfirm: showConfirmOverride || vi.fn(() => Promise.resolve(null)),
      isConfirmOpen: vi.fn(() => false),
      cancelConfirm: vi.fn(),
      ThemeRegistry: themeRegistry,
      SESSION_ID: sessionId,
      updateSessionId: updateSessionIdOverride,
      copyTextToClipboard: copyTextToClipboardOverride,
      reloadSessionHistory: reloadSessionHistoryOverride,
      _seedLocalStorageStarsToServer: seedLocalStorageStarsToServerOverride,
      hasPendingTerminalConfirm: hasPendingTerminalConfirmOverride,
      cancelPendingTerminalConfirm: cancelPendingTerminalConfirmOverride,
      sessionVariables: sessionVariablesOverride,
      getWorkspaceAutocompleteFileHints: getWorkspaceAutocompleteFileHintsOverride,
      ...domBindings,
      getOutput: getOutputOverride || (() => document.getElementById('history-list')),
      renderMotd: (text) => text,
      updateNewTabBtn: () => {},
      createTab: createTabOverride,
      runWelcome: () => {},
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
      pendingHistAction: null,
      pendingKillTabId,
      acHide: acHideOverride,
      acSuggestions: acSuggestionsOverride,
      acContextRegistry: acContextRegistryOverride,
      getAutocompleteMatches: getAutocompleteMatchesOverride,
      acFiltered: acFilteredOverride,
      acIndex: acIndexOverride,
      acShow: acShowOverride,
      acAccept: () => {},
      acExpandSharedPrefix: acExpandSharedPrefixOverride,
      resetCmdHistoryNav: () => {},
      navigateCmdHistory: navigateCmdHistoryOverride,
      setupTabScrollControls: () => {},
      hydrateCmdHistory: hydrateCmdHistoryOverride,
      mountShellPrompt: () => {},
      unmountShellPrompt: () => {},
      logClientError,
      appendLine,
      appendCommandEcho,
      setStatus,
      _recordSuccessfulLocalCommand: recordSuccessfulLocalCommand,
      tabs: tabsState,
      activeTabId: activeTabState,
      getTab,
      getActiveTab,
      setTabs,
      setActiveTabId,
      confirmKill: confirmKillOverride,
      closeTab: closeTabOverride,
      activateTab: activateTabOverride,
      permalinkTab: permalinkTabOverride,
      copyTab: copyTabOverride,
      clearTab: clearTabOverride,
      cancelWelcome: cancelWelcomeOverride,
      enterHistSearch: enterHistSearchOverride,
      openWorkspace: openWorkspaceOverride,
      openRunMonitor: openRunMonitorOverride,
      interruptPromptLine: interruptPromptLineOverride,
      _welcomeActive: welcomeActive,
      welcomeOwnsTab: welcomeOwnsTabOverride,
      shellPromptWrap: shellPromptWrapEl,
      shellPromptText: document.getElementById('shell-prompt-text'),
      terminalWrap: document.querySelector('.terminal-wrap'),
      terminalBar: document.querySelector('.terminal-bar'),
      histRow: document.getElementById('history-row'),
      tabPanels: document.getElementById('tab-panels'),
      mobileShell: document.getElementById('mobile-shell'),
      mobileShellChrome: document.getElementById('mobile-shell-chrome'),
      mobileShellTranscript: document.getElementById('mobile-shell-transcript'),
      mobileShellOverlays: document.getElementById('mobile-shell-overlays'),
      mobileComposerHost: document.getElementById('mobile-composer-host'),
      mobileComposerRow: document.getElementById('mobile-composer-row'),
      mobileMenu: document.getElementById('mobile-menu-sheet'),
      faqOverlay: document.getElementById('faq-overlay'),
      optionsOverlay: document.getElementById('options-overlay'),
      workflowsOverlay: document.getElementById('workflows-overlay'),
      workflowsCloseBtn: document.querySelector('.workflows-close'),
      permalinkToast: document.getElementById('permalink-toast'),
      mobileComposerHostEl,
      acDropdown,
      loadStarredFromServer: () => Promise.resolve(),
      maskSessionToken: (t) => (t ? t.slice(0, 8) + '••••••••' : '(none)'),
      requestWelcomeSettle: requestWelcomeSettleOverride,
      runCommand: runCommandOverride,
      submitComposerCommand: submitComposerCommandOverride,
      submitVisibleComposerCommand: submitVisibleComposerCommandOverride,
      doKill: doKillOverride,
      Event,
      showToast: showToastOverride,
      ...(NotificationOverride !== undefined ? { Notification: NotificationOverride } : {}),
      setTimeout: (fn) => {
        fn()
        return 0
      },
    },
    `{
    _setTsMode,
    _setLnMode,
    handleComposerInputChange,
    setComposerValue,
    moveCmdCaret,
    handleComposerWordArrowShortcut,
    performMobileEditAction,
    syncMobileComposerKeyboardState,
    focusVisibleComposerInput,
    blurVisibleComposerInput,
    blurVisibleComposerInputIfMobile,
    _replayPromptShortcutAfterSelection,
    refocusComposerAfterAction,
    getVisibleComposerInput,
    getComposerValue,
    setRunButtonDisabled,
    persistTabSessionStateNow,
    schedulePersistTabSessionState,
    restoreTabSessionState,
    _getTabSessionStateKey: () => TAB_SESSION_STATE_KEY,
    confirmHistAction,
    executeHistAction,
    doKill,
    confirmPermalinkRedactionChoice,
    getWelcomeIntroPreference,
    getShareRedactionDefaultPreference,
    getRunNotifyPreference,
    getHudClockPreference,
    applyRunNotifyPreference,
    applyHudClockPreference,
    syncOptionsControls,
    handleThemeCommand,
    handleConfigCommand,
    getRuntimeAutocompleteContext,
    getRuntimeAutocompleteItems,
    openOptions,
    openThemeSelector,
    openFaq,
    getComposerState,
    setComposerState,
    setComposerPromptMode,
    resetComposerState,
    syncShellPrompt,
    _getAcIndex: () => acIndex,
    _getWelcomeBootPending: () => _welcomeBootPending,
  }`,
    'setTabs(tabs); setActiveTabId(activeTabId);',
  )

  await Promise.resolve()
  await Promise.resolve()

  return {
    ...fns,
    storage,
    tabs: tabsState,
    apiFetch,
    runSearch,
    clearSearch,
    navigateSearch,
    cmdInput,
    requestWelcomeSettle: requestWelcomeSettleOverride,
    showConfirm: showConfirmOverride,
    updateSessionId: updateSessionIdOverride,
    copyTextToClipboard: copyTextToClipboardOverride,
    reloadSessionHistory: reloadSessionHistoryOverride,
    seedLocalStorageStarsToServer: seedLocalStorageStarsToServerOverride,
    hydrateCmdHistory: hydrateCmdHistoryOverride,
    hasPendingTerminalConfirm: hasPendingTerminalConfirmOverride,
    cancelPendingTerminalConfirm: cancelPendingTerminalConfirmOverride,
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
    appendLine,
    appendCommandEcho,
    setStatus,
    recordSuccessfulLocalCommand,
    acDropdown,
    acHide: acHideOverride,
    shellPromptWrap: shellPromptWrapEl,
    syncShellPrompt: fns.syncShellPrompt,
    sessionStorage: sessionStore,
    getTab,
    getActiveTab,
    setTabs,
    setActiveTabId,
    restoreViewport: () => {
      if (originalMatchMedia === undefined) delete window.matchMedia
      else
        Object.defineProperty(window, 'matchMedia', {
          configurable: true,
          value: originalMatchMedia,
        })
      if (originalVisualViewport === undefined) delete window.visualViewport
      else
        Object.defineProperty(window, 'visualViewport', {
          configurable: true,
          value: originalVisualViewport,
        })
      if (originalScrollTo === undefined) delete window.scrollTo
      else window.scrollTo = originalScrollTo
      if (originalMaxTouchPoints === undefined) delete window.navigator.maxTouchPoints
      else
        Object.defineProperty(window.navigator, 'maxTouchPoints', {
          configurable: true,
          value: originalMaxTouchPoints,
        })
    },
  }
}

function builtInAutocompleteBase() {
  const hint = (value, description = '', insertValue = undefined) => {
    const item = { value, description }
    if (insertValue !== undefined) item.insertValue = insertValue
    return item
  }
  const emptyBuiltIn = description => ({
    description,
    flags: [],
    expects_value: [],
    arg_hints: { __positional__: [] },
    sequence_arg_hints: {},
    close_after: {},
    examples: [],
    subcommands: {},
    argument_limit: null,
  })
  return {
    commands: {
      ...emptyBuiltIn('built-in: list built-in and allowed external commands'),
      flags: [hint('--built-in', 'Show only built-in shell commands'), hint('--external', 'Show only allowed external commands')],
    },
    config: {
      ...emptyBuiltIn('built-in: show or update user options'),
      expects_value: ['get', 'set'],
      arg_hints: {
        list: [],
        get: [],
        set: [],
        __positional__: [hint('list', 'Show all current user config'), hint('get', 'Show one user config value', 'get '), hint('set', 'Set one user config value', 'set ')],
      },
    },
    theme: {
      ...emptyBuiltIn('built-in: show or apply the active shell theme'),
      expects_value: ['set'],
      arg_hints: {
        list: [],
        current: [],
        set: [],
        __positional__: [hint('list', 'Show available themes'), hint('current', 'Show the active theme'), hint('set', 'Apply a theme', 'set ')],
      },
    },
    var: {
      ...emptyBuiltIn('built-in: set, list, or unset session command variables'),
      expects_value: ['set', 'unset'],
      close_after: { list: 0, set: 2, unset: 1 },
      arg_hints: {
        list: [],
        set: [],
        unset: [],
        __positional__: [hint('list', 'Show session variables'), hint('set', 'Set a session variable', 'set '), hint('unset', 'Remove a session variable', 'unset ')],
      },
    },
    runs: {
      ...emptyBuiltIn('built-in: show active runs; use -v for details or --json for automation'),
      flags: [hint('-v'), hint('--verbose'), hint('--json')],
    },
    jobs: {
      ...emptyBuiltIn('built-in: alias for runs'),
      flags: [hint('-v'), hint('--verbose'), hint('--json')],
    },
    'session-token': {
      ...emptyBuiltIn('built-in: show or manage persistent session tokens'),
      expects_value: ['set', 'revoke'],
      arg_hints: {
        generate: [],
        copy: [],
        clear: [],
        rotate: [],
        list: [],
        set: [hint('<token>', 'Paste a tok_... token or UUID from another device')],
        revoke: [hint('<token>', 'tok_ token to permanently invalidate on the server')],
        __positional__: [
          hint('generate', 'Generate a new session token and save it to this browser'),
          hint('set <token>', 'Activate an existing session token from another device', 'set '),
          hint('copy', 'Copy the active session token to the clipboard'),
          hint('clear', 'Confirm before removing the active session token'),
          hint('rotate', 'Generate a new token and migrate all history to it'),
          hint('list', 'Show the active session token and its creation date'),
          hint('revoke <token>', 'Permanently invalidate a tok_ token on this server', 'revoke '),
        ],
      },
    },
    file: {
      ...emptyBuiltIn('built-in: list, view, create, edit, download, or remove session files'),
      feature_required: 'workspace',
      expects_value: ['show', 'add', 'edit', 'download', 'rm', 'delete'],
      arg_hints: {
        list: [],
        help: [],
        show: [],
        add: [hint('<file>', 'New session file name')],
        edit: [],
        download: [],
        rm: [],
        delete: [],
        __positional__: [
          hint('list', 'List current session files'),
          hint('show <file>', 'Print a session file in the terminal', 'show '),
          hint('add <file>', 'Open the Files editor for a new session file', 'add '),
          hint('edit <file>', 'Open the Files editor for an existing session file', 'edit '),
          hint('download <file>', 'Download a session file through the browser', 'download '),
          hint('delete <file>', 'Remove a session file from this session', 'delete '),
          hint('help', 'Show file command usage'),
        ],
      },
    },
    cat: { ...emptyBuiltIn('built-in: show a session file'), feature_required: 'workspace', argument_limit: 1 },
    ls: { ...emptyBuiltIn('built-in: list session files'), feature_required: 'workspace', argument_limit: 0 },
    rm: {
      ...emptyBuiltIn('built-in: remove a session file after confirmation'),
      feature_required: 'workspace',
      argument_limit: 1,
    },
    man: { ...emptyBuiltIn('built-in: show a real or built-in manual page'), argument_limit: 1 },
    which: { ...emptyBuiltIn('built-in: locate a built-in command or allowed runtime command'), argument_limit: 1 },
    type: { ...emptyBuiltIn('built-in: describe whether a command is built-in, installed, or missing'), argument_limit: 1 },
    status: emptyBuiltIn('built-in: show the current session summary, limits, and backend health'),
    whoami: emptyBuiltIn('built-in: describe this shell and link to the project README'),
  }
}

function shippedThemeRegistry() {
  const themeDir = resolve(REPO_ROOT, 'app/conf/themes')
  const themes = readdirSync(themeDir)
    .filter(name => name.endsWith('.yaml') && !name.endsWith('.local.yaml'))
    .sort()
    .map(filename => {
      const raw = yaml.load(readFileSync(resolve(themeDir, filename), 'utf8')) || {}
      const name = filename.replace(/\.yaml$/, '')
      const vars = {}
      Object.entries(raw).forEach(([key, value]) => {
        if (THEME_META_KEYS.has(key) || key === 'color_scheme') return
        const cssKey = String(key).replaceAll('_', '-')
        const cssValue = String(value)
        if (THEME_BASE_KEYS.has(key)) vars[`--${cssKey}`] = cssValue
        vars[`--theme-${cssKey}`] = cssValue
      })
      return {
        name,
        filename,
        label: raw.label || name,
        group: raw.group || 'Other',
        sort: Number.isInteger(raw.sort) ? raw.sort : null,
        color_scheme: raw.color_scheme === 'light' ? 'only light' : 'only dark',
        source: 'variant',
        vars,
      }
    })
  return { current: themes[0], themes }
}

describe('app helpers', () => {
  beforeEach(() => {
    ;[
      'pref_theme',
      'pref_theme_name',
      'pref_timestamps',
      'pref_line_numbers',
      'pref_welcome_intro',
      'pref_share_redaction_default',
    ].forEach((name) => {
      document.cookie = `${name}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`
    })
  })

  it('applies the saved theme at startup', async () => {
    await loadAppFns({
      theme: 'theme_light_blue',
      themeRegistry: {
        current: {
          name: 'theme_light_blue',
          label: 'Apricot Sand',
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
        ],
      },
    })
  })

  it('applies saved timestamp, line number, and HUD clock preferences from cookies at startup', async () => {
    const { getHudClockPreference } = await loadAppFns({
      cookies: { pref_timestamps: 'clock', pref_line_numbers: 'on', pref_hud_clock: 'local' },
    })

    expect(document.body.classList.contains('ts-clock')).toBe(true)
    expect(document.body.classList.contains('ln-on')).toBe(true)
    expect(document.getElementById('ts-btn').textContent).toBe('timestamps: clock')
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers: on')
    expect(document.getElementById('options-hud-clock-select').value).toBe('local')
    expect(getHudClockPreference()).toBe('local')
  })

  it('applies saved session preferences on startup over stale local cookies', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/session/preferences') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            preferences: {
              pref_theme_name: 'theme_light_blue',
              pref_timestamps: 'clock',
              pref_line_numbers: 'on',
              pref_welcome_intro: 'disable_animation',
              pref_share_redaction_default: 'redacted',
              pref_run_notify: 'off',
              pref_hud_clock: 'local',
            },
          }),
        })
      }
      if (url === '/config') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
              prompt_prefix: 'anon@darklab:~$',
              version: '9.9',
              project_readme: 'https://gitlab.com/darklab.sh/darklab_shell',
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
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })

    await loadAppFns({
      apiFetch,
      cookies: { pref_timestamps: 'off', pref_line_numbers: 'off', pref_hud_clock: 'utc' },
      themeRegistry: {
        current: {
          name: 'darklab_obsidian.yaml',
          label: 'Darklab Obsidian',
          source: 'variant',
          vars: { '--bg': '#111111' },
        },
        themes: [
          {
            name: 'darklab_obsidian.yaml',
            label: 'Darklab Obsidian',
            source: 'variant',
            vars: { '--bg': '#111111' },
          },
          {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
        ],
      },
    })
    await Promise.resolve()
    await Promise.resolve()

    expect(document.body.dataset.theme).toBe('theme_light_blue')
    expect(document.body.classList.contains('ts-clock')).toBe(true)
    expect(document.body.classList.contains('ln-on')).toBe(true)
    expect(document.getElementById('options-welcome-select').value).toBe('disable_animation')
    expect(document.getElementById('options-share-redaction-select').value).toBe('redacted')
    expect(document.getElementById('options-hud-clock-select').value).toBe('local')
  })

  it('switches the visible prompt into confirmation mode when requested', async () => {
    const { setComposerPromptMode } = await loadAppFns()
    const shellPromptWrap = document.getElementById('shell-prompt-wrap')
    const promptPrefix = shellPromptWrap.querySelector('.prompt-prefix')
    const mobilePromptLabel = document.querySelector('#mobile-composer-row .mobile-prompt-label')

    expect(promptPrefix.textContent).toBe('anon@darklab:~$')
    expect(mobilePromptLabel.textContent).toBe('$')

    setComposerPromptMode('confirm')
    expect(promptPrefix.textContent).toBe('[yes/no]:')
    expect(mobilePromptLabel.textContent).toBe('[yes/no]:')
    expect(shellPromptWrap.classList.contains('shell-prompt-confirm')).toBe(true)

    setComposerPromptMode(null)
    expect(promptPrefix.textContent).toBe('anon@darklab:~$')
    expect(mobilePromptLabel.textContent).toBe('$')
    expect(shellPromptWrap.classList.contains('shell-prompt-confirm')).toBe(false)
  })

  it('_setTsMode updates body classes and button labels', async () => {
    const { _setTsMode } = await loadAppFns()

    _setTsMode('elapsed')

    expect(document.body.classList.contains('ts-elapsed')).toBe(true)
    expect(document.body.classList.contains('ts-clock')).toBe(false)
    expect(document.getElementById('ts-btn').textContent).toBe('timestamps: elapsed')
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers: off')
  })

  it('_setLnMode updates body classes and button labels', async () => {
    const { _setLnMode } = await loadAppFns()

    _setLnMode('on')

    expect(document.body.classList.contains('ln-on')).toBe(true)
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers: on')

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
    document.querySelector('#mobile-menu-sheet [data-menu-action="ts-set"][data-ts-mode="elapsed"]').click()
    expect(cmdInput.focus).toHaveBeenCalled()

    cmdInput.focus.mockClear()
    document.querySelector('#mobile-menu-sheet [data-menu-action="ln"]').click()
    expect(cmdInput.focus).toHaveBeenCalled()
  })

  it('ts-toggle does not close the mobile sheet (disclosure in mobile_chrome.js owns the submenu toggle)', async () => {
    await loadAppFns()
    const sheet = document.getElementById('mobile-menu-sheet')
    const toggle = sheet.querySelector('[data-menu-action="ts-toggle"]')

    sheet.classList.remove('u-hidden')
    // Controller dispatch is a no-op for ts-toggle and skips hideMobileMenu
    // in the real button click path; the inline submenu's aria-expanded /
    // u-hidden lifecycle moved to bindDisclosure in mobile_chrome.js (covered
    // in ui_disclosure.test.js). What this test still guarantees is that the
    // ts-toggle click does not cascade into closing the parent sheet.
    toggle.click()
    expect(sheet.classList.contains('u-hidden')).toBe(false)
  })

  it('ts-set applies the selected mode and closes the sheet', async () => {
    const { _setTsMode } = await loadAppFns()
    _setTsMode('off')
    const sheet = document.getElementById('mobile-menu-sheet')
    sheet.classList.remove('u-hidden')

    document
      .querySelector('#mobile-menu-sheet [data-menu-action="ts-set"][data-ts-mode="clock"]')
      .click()

    expect(document.body.classList.contains('ts-clock')).toBe(true)
    expect(sheet.classList.contains('u-hidden')).toBe(true)
  })

  it('clear cancels welcome, clears the active tab preserving run state, and closes the sheet', async () => {
    const clearTabSpy = vi.fn()
    const cancelWelcomeSpy = vi.fn()
    await loadAppFns({
      clearTab: clearTabSpy,
      cancelWelcome: cancelWelcomeSpy,
      activeTabId: 'tab-1',
    })
    const sheet = document.getElementById('mobile-menu-sheet')
    sheet.classList.remove('u-hidden')

    document.querySelector('#mobile-menu-sheet [data-menu-action="clear"]').click()

    expect(cancelWelcomeSpy).toHaveBeenCalledWith('tab-1')
    expect(clearTabSpy).toHaveBeenCalledWith('tab-1', { preserveRunState: true })
    expect(sheet.classList.contains('u-hidden')).toBe(true)
  })

  it('opens the theme selector from the theme button', async () => {
    const { openThemeSelector } = await loadAppFns({
      themeRegistry: {
        current: {
          name: 'theme_light_blue',
          label: 'Apricot Sand',
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
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

    openThemeSelector()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(document.getElementById('theme-overlay').classList.contains('open')).toBe(true)
    expect(document.querySelector('#theme-select .theme-card-active')).toBe(document.activeElement)
  })

  it('populates the theme select from the registry and applies the selected theme', async () => {
    const themeRegistry = {
      current: {
        name: 'theme_light_blue',
        label: 'Apricot Sand',
        source: 'variant',
        vars: { '--bg': '#9ab7d0' },
      },
      themes: [
        {
          name: 'theme_light_blue',
          label: 'Apricot Sand',
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
    expect(themeCards.map((card) => card.dataset.themeName)).toEqual([
      'theme_light_blue',
      'theme_light_olive',
    ])
    expect(themeCards.map((card) => card.querySelector('.theme-card-label')?.textContent)).toEqual([
      'Apricot Sand',
      'Olive Parchment',
    ])

    themeSelect.querySelector('[data-theme-name="theme_light_blue"]').click()

    expect(document.body.dataset.theme).toBe('theme_light_blue')
    expect(document.cookie).toContain('pref_theme_name=theme_light_blue')

    themeSelect.querySelector('[data-theme-name="theme_light_olive"]').click()

    expect(document.body.dataset.theme).toBe('theme_light_olive')
    expect(document.cookie).toContain('pref_theme_name=theme_light_olive')
  })

  it('renders theme preview cards with the current desktop shell structure', async () => {
    await loadAppFns({
      themeRegistry: {
        current: {
          name: 'darklab_obsidian',
          label: 'Darklab Obsidian',
          source: 'variant',
          vars: {
            '--theme-chrome-bg': '#050505',
            '--theme-panel-bg': '#111111',
            '--theme-tab-active-bg': '#1a1a1a',
          },
        },
        themes: [
          {
            name: 'darklab_obsidian',
            label: 'Darklab Obsidian',
            source: 'variant',
            vars: {
              '--theme-chrome-bg': '#050505',
              '--theme-panel-bg': '#111111',
              '--theme-tab-active-bg': '#1a1a1a',
            },
          },
        ],
      },
    })

    const card = document.querySelector('#theme-select .theme-card')
    expect(card?.style.getPropertyValue('--theme-chrome-bg')).toBe('#050505')
    expect(card?.querySelector('.theme-card-preview-rail')).not.toBeNull()
    expect(card?.querySelector('.theme-card-preview-tab-active')).not.toBeNull()
    expect(card?.querySelector('.theme-card-preview-content')).not.toBeNull()
    expect(card?.querySelector('.theme-card-preview-hud')).not.toBeNull()
    expect(card?.querySelectorAll('.theme-card-preview-rail-section')).toHaveLength(3)
    expect(card?.querySelector('.theme-card-preview-modal')).not.toBeNull()
    expect(card?.querySelectorAll('.theme-card-preview-modal-button')).toHaveLength(2)
    expect(card?.querySelectorAll('.theme-card-preview-line')).toHaveLength(4)
    expect(card?.querySelector('.theme-card-preview-bar')).toBeNull()
    expect(card?.querySelector('.theme-card-preview-pill')).toBeNull()
    expect(card?.querySelector('.theme-card-preview-chip')).toBeNull()
    expect(card?.querySelector('.theme-card-preview-drawer')).toBeNull()
  })

  it('renders shipped theme preview cards with populated core surface tokens', async () => {
    const registry = shippedThemeRegistry()
    await loadAppFns({ themeRegistry: registry })

    const cards = Array.from(document.querySelectorAll('#theme-select .theme-card'))
    expect(cards).toHaveLength(registry.themes.length)

    cards.forEach(card => {
      const theme = registry.themes.find(item => item.name === card.dataset.themeName)
      expect(theme, `missing registry theme for ${card.dataset.themeName}`).toBeTruthy()
      ;[
        '--bg',
        '--surface',
        '--theme-panel-bg',
        '--theme-chrome-bg',
        '--theme-modal-bg',
        '--theme-tab-active-bg',
        '--theme-button-secondary-bg',
        '--theme-button-secondary-border',
        '--theme-dropdown-bg',
        '--theme-dropdown-border',
      ].forEach(token => {
        expect(card.style.getPropertyValue(token), `${theme.name} missing ${token}`).not.toBe('')
      })
      expect(card.querySelector('.theme-card-preview-rail')).not.toBeNull()
      expect(card.querySelector('.theme-card-preview-hud')).not.toBeNull()
      expect(card.querySelector('.theme-card-preview-content')).not.toBeNull()
      expect(card.querySelector('.theme-card-preview-modal')).not.toBeNull()
    })
  })

  it('applies a theme from the terminal theme command', async () => {
    const { handleThemeCommand, appendCommandEcho, setStatus, recordSuccessfulLocalCommand } =
      await loadAppFns({
        themeRegistry: {
          current: {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
          themes: [
            {
              name: 'theme_light_blue',
              label: 'Apricot Sand',
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

    await handleThemeCommand('theme set theme_light_olive', 'tab-1')

    expect(appendCommandEcho).toHaveBeenCalledWith('theme set theme_light_olive', 'tab-1')
    expect(document.body.dataset.theme).toBe('theme_light_olive')
    expect(document.cookie).toContain('pref_theme_name=theme_light_olive')
    expect(recordSuccessfulLocalCommand).toHaveBeenCalledWith('theme set theme_light_olive')
    expect(setStatus).toHaveBeenCalledWith('ok')
  })

  it('groups terminal theme list output by color scheme', async () => {
    const { handleThemeCommand, setStatus, recordSuccessfulLocalCommand } =
      await loadAppFns({
        themeRegistry: {
          current: {
            name: 'darklab_obsidian',
            label: 'Darklab Obsidian',
            color_scheme: 'only dark',
            source: 'variant',
            vars: { '--bg': '#111111' },
          },
          themes: [
            {
              name: 'darklab_obsidian',
              label: 'Darklab Obsidian',
              color_scheme: 'only dark',
              source: 'variant',
              vars: { '--bg': '#111111' },
            },
            {
              name: 'theme_light_blue',
              label: 'Apricot Sand',
              color_scheme: 'only light',
              source: 'variant',
              vars: { '--bg': '#9ab7d0' },
            },
            {
              name: 'theme_unknown',
              label: 'Unknown Scheme',
              source: 'variant',
              vars: { '--bg': '#999999' },
            },
          ],
        },
      })

    await handleThemeCommand('theme list', 'tab-1')

    const output = [...document.querySelectorAll('#history-list .line-content')]
      .map((line) => line.textContent)
    expect(output).toEqual([
      'current theme       Darklab Obsidian (current)',
      '',
      'Available themes:',
      'Dark themes:',
      '  * darklab_obsidian          Darklab Obsidian',
      'Light themes:',
      '    theme_light_blue          Apricot Sand',
      'Other themes:',
      '    theme_unknown             Unknown Scheme',
    ])
    expect(recordSuccessfulLocalCommand).toHaveBeenCalledWith('theme list')
    expect(setStatus).toHaveBeenCalledWith('ok')
  })

  it('requires explicit set before applying a theme from the terminal theme command', async () => {
    const { handleThemeCommand, appendCommandEcho, setStatus, recordSuccessfulLocalCommand } =
      await loadAppFns({
        themeRegistry: {
          current: {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
          themes: [
            {
              name: 'theme_light_blue',
              label: 'Apricot Sand',
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

    await handleThemeCommand('theme theme_light_olive', 'tab-1')

    expect(document.body.dataset.theme).toBe('theme_light_blue')
    expect(appendCommandEcho).toHaveBeenCalledWith('theme theme_light_olive', 'tab-1')
    expect(recordSuccessfulLocalCommand).not.toHaveBeenCalled()
    expect(setStatus).toHaveBeenCalledWith('fail')
  })

  it('updates user options from the terminal config command', async () => {
    const { handleConfigCommand, appendCommandEcho, setStatus, recordSuccessfulLocalCommand } =
      await loadAppFns({
        cookies: {
          pref_line_numbers: 'off',
          pref_timestamps: 'off',
          pref_welcome_intro: 'animated',
        },
      })

    await handleConfigCommand('config set line-numbers on', 'tab-1')
    await handleConfigCommand('config set welcome static', 'tab-1')

    expect(appendCommandEcho).toHaveBeenCalledWith('config set line-numbers on', 'tab-1')
    expect(document.body.classList.contains('ln-on')).toBe(true)
    expect(document.cookie).toContain('pref_line_numbers=on')
    expect(document.cookie).toContain('pref_welcome_intro=disable_animation')
    expect(recordSuccessfulLocalCommand).toHaveBeenCalledWith('config set line-numbers on')
    expect(recordSuccessfulLocalCommand).toHaveBeenCalledWith('config set welcome static')
    expect(setStatus).toHaveBeenCalledWith('ok')
  })

  it('requires explicit set before updating user options from the terminal config command', async () => {
    const { handleConfigCommand, appendCommandEcho, setStatus, recordSuccessfulLocalCommand } =
      await loadAppFns({
        cookies: {
          pref_line_numbers: 'off',
        },
      })

    await handleConfigCommand('config line-numbers on', 'tab-1')

    expect(document.body.classList.contains('ln-on')).toBe(false)
    expect(document.cookie).not.toContain('pref_line_numbers=on')
    expect(appendCommandEcho).toHaveBeenCalledWith('config line-numbers on', 'tab-1')
    expect(recordSuccessfulLocalCommand).not.toHaveBeenCalled()
    expect(setStatus).toHaveBeenCalledWith('fail')
  })

  it('keeps config command output pinned to the tail when the tab is already following', async () => {
    const output = document.createElement('div')
    let scrollTop = 0
    Object.defineProperty(output, 'scrollHeight', { configurable: true, get: () => 500 })
    Object.defineProperty(output, 'scrollTop', {
      configurable: true,
      get: () => scrollTop,
      set: (value) => {
        scrollTop = value
      },
    })
    const tab = { id: 'tab-1', followOutput: true, rawLines: [] }
    const { handleConfigCommand } = await loadAppFns({
      tabs: [tab],
      getOutput: () => output,
      cookies: {
        pref_welcome_intro: 'animated',
        pref_hud_clock: 'utc',
      },
    })

    await handleConfigCommand('config set welcome static', 'tab-1')
    scrollTop = 0
    await handleConfigCommand('config set hud-clock local', 'tab-1')

    expect(tab.followOutput).toBe(true)
    expect(scrollTop).toBe(500)
  })

  it('serves runtime autocomplete context for theme and config values', async () => {
    const { getRuntimeAutocompleteContext } = await loadAppFns({
      themeRegistry: {
        current: {
          name: 'theme_light_blue',
          label: 'Apricot Sand',
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
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
      sessionVariables: [
        { name: 'HOST', value: 'ip.darklab.sh' },
      ],
    })
    const context = getRuntimeAutocompleteContext(builtInAutocompleteBase())

    expect(context.theme.arg_hints.__positional__.map(item => item.value)).toEqual(['list', 'current', 'set'])
    expect(context.theme.arg_hints.set.map(item => item.value)).toContain('theme_light_olive')
    expect(context.theme.arg_hints.set.find(item => item.value === 'theme_light_blue')?.description)
      .toContain('(current)')
    expect(context.config.arg_hints.__positional__.map(item => item.value)).toEqual(['list', 'get', 'set'])
    expect(context.config.sequence_arg_hints['set line-numbers'].map(item => item.value)).toEqual(['on', 'off'])
    expect(context.var.arg_hints.__positional__.map(item => item.value)).toEqual(['list', 'set', 'unset'])
    expect(context.var.arg_hints.set.filter(item => item.value === 'HOST')).toEqual([
      { value: 'HOST', description: 'Current value: ip.darklab.sh' },
    ])
    expect(context.var.arg_hints.set.map(item => item.value)).toEqual(['HOST', 'PORT', 'IP_ADDR'])
    expect(context.var.sequence_arg_hints['set host'].map(item => item.value)).toEqual(['<value>'])
    expect(context.var.sequence_arg_hints['unset host']).toEqual([])
    expect(context.var.close_after).toEqual({ list: 0, set: 2, unset: 1 })
  })

  it('serves runtime autocomplete context for built-in command lookup helpers', async () => {
    const { getRuntimeAutocompleteContext } = await loadAppFns()

    const context = getRuntimeAutocompleteContext({
      ...builtInAutocompleteBase(),
      curl: {},
      nmap: {},
    })

    expect(context.commands.flags.map(item => item.value)).toEqual(['--built-in', '--external'])
    expect(context.runs.flags.map(item => item.value)).toEqual(['-v', '--verbose', '--json'])
    expect(context.jobs.flags.map(item => item.value)).toEqual(['-v', '--verbose', '--json'])
    expect(context['session-token'].arg_hints.__positional__.map(item => item.value)).toContain('set <token>')
    expect(context['session-token'].arg_hints.set[0].value).toBe('<token>')
    expect(context.file.arg_hints.__positional__.map(item => item.value)).toEqual([
      'list',
      'show <file>',
      'add <file>',
      'edit <file>',
      'download <file>',
      'delete <file>',
      'help',
    ])
    expect(context.status).toBeTruthy()
    expect(context.whoami).toBeTruthy()
    expect(context.man.arg_hints.__positional__.map(item => item.value)).toEqual(
      expect.arrayContaining(['commands', 'curl', 'nmap', 'status', 'whoami']),
    )
    expect(context.which.arg_hints.__positional__.map(item => item.value)).toEqual(
      expect.arrayContaining(['commands', 'curl', 'status']),
    )
    expect(context.type.arg_hints.__positional__.map(item => item.value)).toEqual(
      expect.arrayContaining(['commands', 'nmap', 'whoami']),
    )
  })

  it('serves loaded workspace files as file command autocomplete values', async () => {
    const { getRuntimeAutocompleteContext } = await loadAppFns({
      getWorkspaceAutocompleteFileHints: () => [
        { value: 'targets.txt', description: 'session file · 11 B' },
        { value: 'ffuf.json', description: 'session file · 2 KB' },
      ],
    })

    const context = getRuntimeAutocompleteContext(builtInAutocompleteBase())

    expect(context.file.arg_hints.show.map(item => item.value)).toEqual(['targets.txt', 'ffuf.json'])
    expect(context.file.arg_hints.edit.map(item => item.value)).toEqual(['targets.txt', 'ffuf.json'])
    expect(context.file.arg_hints.download.map(item => item.value)).toEqual(['targets.txt', 'ffuf.json'])
    expect(context.file.arg_hints.rm.map(item => item.description)).toEqual([
      'session file · 11 B',
      'session file · 2 KB',
    ])
    expect(context.cat.arg_hints.__positional__.map(item => item.value)).toEqual(['targets.txt', 'ffuf.json'])
    expect(context.rm.arg_hints.__positional__.map(item => item.value)).toEqual(['targets.txt', 'ffuf.json'])
  })

  it('hides workspace built-ins from runtime autocomplete when Files are disabled', async () => {
    const { getRuntimeAutocompleteContext } = await loadAppFns({
      appConfig: { workspace_enabled: false },
    })

    const context = getRuntimeAutocompleteContext({ ...builtInAutocompleteBase(), curl: {} })

    expect(context.file).toBeUndefined()
    expect(context.cat).toBeUndefined()
    expect(context.ls).toBeUndefined()
    expect(context.rm).toBeUndefined()
    expect(context.man.arg_hints.__positional__.map(item => item.value)).not.toContain('file')
  })

  it('keeps code-owned built-ins out of commands.yaml', () => {
    const commandsYaml = readFileSync(resolve(REPO_ROOT, 'app/conf/commands.yaml'), 'utf8')
    const yamlRoots = new Set(
      [...commandsYaml.matchAll(/^- root: ([a-z0-9_-]+)/gm)].map(match => match[1]),
    )
    const runtimeRoots = [
      'banner', 'cat', 'clear', 'commands', 'config', 'date', 'df', 'env', 'faq', 'fortune', 'free',
      'file', 'groups', 'help', 'history', 'hostname', 'id', 'ip', 'jobs', 'last', 'limits', 'ls', 'man',
      'ps', 'pwd', 'retention', 'rm', 'route', 'runs', 'session-token', 'shortcuts', 'stats', 'status', 'theme',
      'tty', 'type', 'uname', 'uptime', 'version', 'which', 'who', 'whoami',
    ]

    expect(runtimeRoots.filter(root => yamlRoots.has(root))).toEqual([])
  })

  it('groups theme cards into labeled sections in the preview modal', async () => {
    await loadAppFns({
      themeRegistry: {
        current: {
          name: 'apricot_sand',
          label: 'Apricot Sand',
          group: 'Warm Light',
          sort: 50,
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'apricot_sand',
            label: 'Apricot Sand',
            group: 'Warm Light',
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

    const groupTitles = Array.from(
      document.querySelectorAll('#theme-select .theme-picker-group-title'),
    ).map((node) => node.textContent)
    expect(groupTitles).toEqual(['Warm Light', 'Neutral Light'])
    const sectionGroups = Array.from(
      document.querySelectorAll('#theme-select .theme-picker-group'),
    ).map((node) => node.dataset.themeGroup)
    expect(sectionGroups).toEqual(['Warm Light', 'Neutral Light'])
    expect(
      document.getElementById('theme-select')?.style.getPropertyValue('--theme-picker-columns'),
    ).toBe('2')
    expect(document.querySelectorAll('#theme-select [data-theme-name]').length).toBe(4)
  })

  it('falls back to the current/default theme when localStorage references a missing theme', async () => {
    await loadAppFns({
      theme: 'theme_missing',
      themeRegistry: {
        current: {
          name: 'theme_light_blue',
          label: 'Apricot Sand',
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
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
    expect(document.querySelector('#theme-select .theme-card-active')?.dataset.themeName).toBe(
      'theme_light_blue',
    )
  })

  it('falls back to the baked-in dark palette when the configured default theme is missing', async () => {
    await loadAppFns({
      themeRegistry: {
        current: null,
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
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
            json: () =>
              Promise.resolve({
                app_name: 'darklab_shell',
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
          return Promise.resolve({
            json: () => Promise.resolve({ restricted: false, commands: [], groups: [] }),
          })
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
    const { openThemeSelector } = await loadAppFns({
      themeRegistry: {
        current: null,
        themes: [],
      },
    })

    expect(document.body.dataset.theme).toBe('dark')

    openThemeSelector()
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
    const { cmdInput, openFaq } = await loadAppFns()
    const faqOverlay = document.getElementById('faq-overlay')

    openFaq()
    expect(faqOverlay.classList.contains('open')).toBe(true)

    document.querySelector('.faq-close').click()
    expect(faqOverlay.classList.contains('open')).toBe(false)
    expect(cmdInput.focus).toHaveBeenCalled()

    cmdInput.focus.mockClear()
    openFaq()
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
      <button id="hamburger-btn"></button>
      <button id="new-tab-btn"></button>
      <button id="search-toggle-btn"></button>
      <button id="run-btn"></button>
      <button id="search-prev"></button>
      <button id="search-next"></button>
      <button id="ln-btn"></button>
      <button id="history-close"></button>
      <button id="hist-clear-all-btn"></button>
      <nav class="rail-nav" id="rail-nav">
        <button class="rail-nav-item" data-action="history" type="button"></button>
        <button class="rail-nav-item" data-action="theme" type="button"></button>
        <button class="rail-nav-item" data-action="faq" type="button"></button>
      </nav>
      <div id="faq-limits-text"></div>
      <div id="faq-allowed-text"></div>
      <div id="mobile-menu-sheet" class="menu-sheet u-hidden">
        <button data-menu-action="ln"></button>
        <button data-menu-action="ts-toggle" aria-expanded="false" aria-controls="mobile-menu-ts-submenu"></button>
        <div id="mobile-menu-ts-submenu" class="menu-submenu u-hidden">
          <button data-menu-action="ts-set" data-ts-mode="off"></button>
          <button data-menu-action="ts-set" data-ts-mode="elapsed"></button>
          <button data-menu-action="ts-set" data-ts-mode="clock"></button>
        </div>
        <button data-menu-action="search"></button>
        <button data-menu-action="history"></button>
        <button data-menu-action="theme"></button>
        <button data-menu-action="faq"></button>
      </div>
      <div id="faq-overlay"></div>
      <button class="faq-close"></button>
      <div class="faq-body"></div>
      <div id="workflows-overlay"></div>
      <input id="cmd" />
      <div id="history-panel"></div>
      <div id="history-list"></div>
      <div id="search-bar"></div>
      <input id="search-input" autocomplete="off" autocapitalize="none" autocorrect="off" spellcheck="false" inputmode="text" />
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
    expect(logClientError).toHaveBeenCalledWith(
      'failed to load /allowed-commands',
      expect.any(Error),
    )
    expect(logClientError).toHaveBeenCalledWith('failed to load /autocomplete', expect.any(Error))
    expect(storage.getItem('theme')).toBe('only_theme')
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

  it('persists only non-running tabs for session restore', async () => {
    const tabs = [
      {
        id: 'tab-1',
        label: 'tab 1',
        command: 'dig darklab.sh',
        renamed: false,
        draftInput: 'dig darklab.sh',
        st: 'idle',
        exitCode: null,
        historyRunId: '',
        previewTruncated: false,
        fullOutputAvailable: false,
        fullOutputLoaded: false,
        rawLines: [{ text: '$ dig darklab.sh', cls: 'prompt-echo', tsC: '', tsE: '' }],
        closing: false,
      },
      {
        id: 'tab-2',
        label: 'ping',
        command: 'ping darklab.sh',
        renamed: true,
        draftInput: '',
        st: 'running',
        exitCode: null,
        historyRunId: 'run-1',
        previewTruncated: false,
        fullOutputAvailable: false,
        fullOutputLoaded: false,
        rawLines: [{ text: '$ ping darklab.sh', cls: 'prompt-echo', tsC: '', tsE: '' }],
        closing: false,
      },
    ]
    const { persistTabSessionStateNow, sessionStorage, _getTabSessionStateKey } = await loadAppFns({
      tabs,
      activeTabId: 'tab-1',
    })

    persistTabSessionStateNow()

    const saved = JSON.parse(sessionStorage.getItem(_getTabSessionStateKey()))
    expect(saved.tabs).toHaveLength(1)
    expect(saved.tabs[0].label).toBe('tab 1')
    expect(saved.tabs[0].draftInput).toBe('')
  })

  it('persists output signal metadata for session restore', async () => {
    const tabs = [
      {
        id: 'tab-1',
        label: 'tab 1',
        command: 'host darklab.sh',
        renamed: false,
        draftInput: '',
        st: 'idle',
        exitCode: 0,
        historyRunId: 'run-1',
        previewTruncated: false,
        fullOutputAvailable: true,
        fullOutputLoaded: true,
        rawLines: [
          {
            text: 'darklab.sh has address 104.21.4.35',
            cls: '',
            tsC: '12:00:00',
            tsE: '+0.1s',
            signals: ['findings'],
            line_index: 0,
            command_root: 'host',
            target: 'darklab.sh',
          },
        ],
        closing: false,
      },
    ]
    const { persistTabSessionStateNow, sessionStorage, _getTabSessionStateKey } = await loadAppFns({
      tabs,
      activeTabId: 'tab-1',
    })

    persistTabSessionStateNow()

    const saved = JSON.parse(sessionStorage.getItem(_getTabSessionStateKey()))
    expect(saved.tabs[0].rawLines[0]).toMatchObject({
      text: 'darklab.sh has address 104.21.4.35',
      signals: ['findings'],
      line_index: 0,
      command_root: 'host',
      target: 'darklab.sh',
    })
  })

  it('restores saved non-running tabs and active draft state from session storage', async () => {
    const tabs = []
    let seq = 0
    const createTab = vi.fn((label) => {
      const id = `tab-${++seq}`
      tabs.push({
        id,
        label,
        command: '',
        renamed: false,
        draftInput: '',
        st: 'idle',
        exitCode: null,
        historyRunId: null,
        previewTruncated: false,
        fullOutputAvailable: false,
        fullOutputLoaded: false,
        rawLines: [],
        closing: false,
      })
      return id
    })
    const activateTab = vi.fn((id) => {
      tabs.forEach((tab) => {
        tab.active = tab.id === id
      })
    })
    const {
      restoreTabSessionState,
      sessionStorage,
      _getTabSessionStateKey,
      _getWelcomeBootPending,
      tabs: restoredTabs,
      getTab,
    } = await loadAppFns({
      tabs,
      createTab,
      activateTab,
      activeTabId: null,
    })

    sessionStorage.setItem(
      _getTabSessionStateKey(),
      JSON.stringify({
        version: 1,
        activeIndex: 1,
        tabs: [
          {
            label: 'tab 1',
            command: 'dig darklab.sh',
            renamed: false,
            draftInput: 'dig darklab.sh',
            st: 'idle',
            exitCode: null,
            historyRunId: '',
            previewTruncated: false,
            fullOutputAvailable: false,
            fullOutputLoaded: false,
            rawLines: [{ text: '$ dig darklab.sh', cls: 'prompt-echo', tsC: '', tsE: '' }],
          },
          {
            label: 'notes',
            command: '',
            renamed: true,
            draftInput: 'ffuf -u https://target/FUZZ',
            st: 'fail',
            exitCode: 1,
            historyRunId: 'run-2',
            previewTruncated: false,
            fullOutputAvailable: true,
            fullOutputLoaded: true,
            rawLines: [{ text: '[connection error]', cls: 'exit-fail', tsC: '', tsE: '' }],
          },
        ],
      }),
    )

    expect(restoreTabSessionState()).toBe(true)
    expect(_getWelcomeBootPending()).toBe(false)
    expect(restoredTabs).toHaveLength(2)
    expect(createTab).toHaveBeenCalledTimes(2)
    expect(getTab('tab-2')?.draftInput).toBe('ffuf -u https://target/FUZZ')
    expect(getTab('tab-2')?.renamed).toBe(true)
    expect(activateTab).toHaveBeenCalledWith('tab-2', { focusComposer: false })
  })

  it('preserves a non-active tab draft even when createTab activation would overwrite it during restore', async () => {
    const tabs = []
    let seq = 0
    let activeId = null
    const createTab = vi.fn((label) => {
      const id = `tab-${++seq}`
      tabs.push({
        id,
        label,
        command: '',
        renamed: false,
        draftInput: '',
        st: 'idle',
        exitCode: null,
        historyRunId: null,
        previewTruncated: false,
        fullOutputAvailable: false,
        fullOutputLoaded: false,
        rawLines: [],
        closing: false,
      })
      if (activeId) {
        const prev = tabs.find((tab) => tab.id === activeId)
        if (prev) prev.draftInput = ''
      }
      activeId = id
      return id
    })
    const activateTab = vi.fn((id) => {
      activeId = id
      tabs.forEach((tab) => {
        tab.active = tab.id === id
      })
    })
    const { restoreTabSessionState, sessionStorage, _getTabSessionStateKey, getTab } =
      await loadAppFns({
        tabs,
        createTab,
        activateTab,
        activeTabId: null,
      })

    sessionStorage.setItem(
      _getTabSessionStateKey(),
      JSON.stringify({
        version: 1,
        activeIndex: 1,
        tabs: [
          {
            label: 'tab 1',
            command: '',
            renamed: false,
            draftInput: 'dig darklab.sh',
            st: 'idle',
            exitCode: null,
            historyRunId: '',
            previewTruncated: false,
            fullOutputAvailable: false,
            fullOutputLoaded: false,
            rawLines: [],
          },
          {
            label: 'tab 2',
            command: '',
            renamed: false,
            draftInput: 'hostname',
            st: 'idle',
            exitCode: null,
            historyRunId: '',
            previewTruncated: false,
            fullOutputAvailable: false,
            fullOutputLoaded: false,
            rawLines: [],
          },
        ],
      }),
    )

    expect(restoreTabSessionState()).toBe(true)
    expect(getTab('tab-1')?.draftInput).toBe('dig darklab.sh')
    expect(getTab('tab-2')?.draftInput).toBe('hostname')
  })

  it('preserves the last created non-active tab draft when the final restored active tab is different', async () => {
    const tabs = []
    let seq = 0
    const createTab = vi.fn((label) => {
      const id = `tab-${++seq}`
      tabs.push({
        id,
        label,
        command: '',
        renamed: false,
        draftInput: '',
        st: 'idle',
        exitCode: null,
        historyRunId: null,
        previewTruncated: false,
        fullOutputAvailable: false,
        fullOutputLoaded: false,
        rawLines: [],
        closing: false,
      })
      return id
    })
    const { restoreTabSessionState, sessionStorage, _getTabSessionStateKey, getTab } =
      await loadAppFns({
        tabs,
        createTab,
        activeTabId: null,
      })

    sessionStorage.setItem(
      _getTabSessionStateKey(),
      JSON.stringify({
        version: 1,
        activeIndex: 0,
        tabs: [
          {
            label: 'tab 1',
            command: '',
            renamed: false,
            draftInput: 'alpha',
            st: 'idle',
            exitCode: null,
            historyRunId: '',
            previewTruncated: false,
            fullOutputAvailable: false,
            fullOutputLoaded: false,
            rawLines: [],
          },
          {
            label: 'tab 2',
            command: '',
            renamed: false,
            draftInput: 'beta',
            st: 'idle',
            exitCode: null,
            historyRunId: '',
            previewTruncated: false,
            fullOutputAvailable: false,
            fullOutputLoaded: false,
            rawLines: [],
          },
        ],
      }),
    )

    expect(restoreTabSessionState()).toBe(true)
    expect(getTab('tab-1')?.draftInput).toBe('alpha')
    expect(getTab('tab-2')?.draftInput).toBe('beta')
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

  it('ignores command history and autocomplete while a terminal confirmation is pending', async () => {
    const navigateCmdHistory = vi.fn(() => true)
    const acHide = vi.fn()
    const acShow = vi.fn()
    const hasPendingTerminalConfirm = vi.fn(() => true)
    const { cmdInput, _getAcIndex, _replayPromptShortcutAfterSelection } = await loadAppFns({
      navigateCmdHistory,
      acHide,
      acShow,
      acSuggestions: ['curl http://localhost:5001/health'],
      acFiltered: ['curl http://localhost:5001/health'],
      hasPendingTerminalConfirm,
    })

    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => cmdInput,
    })

    cmdInput.value = 'cur'
    cmdInput.setSelectionRange(3, 3)
    cmdInput.dispatchEvent(new Event('input', { bubbles: true }))
    expect(acShow).not.toHaveBeenCalled()
    expect(_getAcIndex()).toBe(-1)

    const tabEv = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true })
    cmdInput.dispatchEvent(tabEv)
    expect(tabEv.defaultPrevented).toBe(true)
    expect(cmdInput.value).toBe('cur')
    expect(_getAcIndex()).toBe(-1)

    for (const key of ['ArrowUp', 'ArrowDown']) {
      const ev = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })
      cmdInput.dispatchEvent(ev)
      expect(ev.defaultPrevented).toBe(true)
    }

    const originalGetSelection = window.getSelection
    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => document.body,
    })
    Object.defineProperty(window, 'getSelection', {
      configurable: true,
      value: () => ({ toString: () => 'selected output' }),
    })

    try {
      const replayEv = new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true, cancelable: true })
      expect(_replayPromptShortcutAfterSelection(replayEv)).toBe(true)
      expect(replayEv.defaultPrevented).toBe(true)
    } finally {
      Object.defineProperty(window, 'getSelection', {
        configurable: true,
        value: originalGetSelection,
      })
    }

    expect(hasPendingTerminalConfirm).toHaveBeenCalled()
    expect(acHide).toHaveBeenCalled()
    expect(acShow).not.toHaveBeenCalled()
    expect(navigateCmdHistory).not.toHaveBeenCalled()
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
      expectAction: (helpers) =>
        expect(helpers.submitComposerCommand).toHaveBeenCalledWith('ping darklab.sh', {
          dismissKeyboard: true,
        }),
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
      Object.defineProperty(window, 'getSelection', {
        configurable: true,
        value: originalGetSelection,
      })
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

    expect(mobileCmdInput.getAttribute('autocomplete')).toBe('off')
    expect(mobileCmdInput.getAttribute('autocapitalize')).toBe('none')
    expect(mobileCmdInput.getAttribute('autocorrect')).toBe('off')
    expect(mobileCmdInput.getAttribute('spellcheck')).toBe('false')
    expect(mobileCmdInput.getAttribute('inputmode')).toBe('text')

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
    await new Promise((resolve) => setTimeout(resolve, 10))

    expect(document.body.classList.contains('mobile-terminal-mode')).toBe(true)
    expect(document.body.classList.contains('mobile-keyboard-open')).toBe(true)
    expect(document.documentElement.style.getPropertyValue('--mobile-keyboard-offset')).toBe(
      '268px',
    )
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
      set: (value) => {
        scrollTop = value
      },
    })
    Object.defineProperty(output, 'scrollHeight', {
      configurable: true,
      get: () => 300,
    })
    const { restoreViewport } = await loadAppFns({
      mobileViewport: { height: 768, offsetTop: 0 },
      tabs: [
        {
          id: 'tab-1',
          followOutput: true,
          suppressOutputScrollTracking: false,
          _outputFollowToken: 0,
        },
      ],
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
    expect(document.documentElement.style.getPropertyValue('--mobile-keyboard-offset')).toBe(
      '268px',
    )
    mobileCmdInput.dispatchEvent(new Event('focus'))
    expect(document.body.classList.contains('mobile-keyboard-open')).toBe(true)
    restoreViewport()
  })

  it('does not programmatically focus the mobile composer', async () => {
    const { refocusComposerAfterAction, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const cmdInput = document.getElementById('cmd')
    const mobileCmdInput = document.getElementById('mobile-cmd')
    document.body.classList.add('mobile-terminal-mode')

    expect(refocusComposerAfterAction({ defer: true })).toBeUndefined()

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
    setComposerState({
      value: 'curl darklab.sh',
      selectionStart: 15,
      selectionEnd: 15,
      activeInput: 'mobile',
    })

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

    expect(document.title).toBe('darklab_shell')
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

    expect(submitVisibleComposerCommand).toHaveBeenCalledWith({
      dismissKeyboard: true,
      focusAfterSubmit: false,
    })
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
    const css = readFileSync(resolve(REPO_ROOT, 'app/static/css/mobile.css'), 'utf8')
    const match = css.match(/body\.mobile-terminal-mode #mobile-composer-host\s*\{([\s\S]*?)\}/)

    expect(match).not.toBeNull()
    expect(match[1]).not.toMatch(/margin-bottom\s*:/)
  })

  it('keeps the themed mobile composer surfaces free of hard-coded dark colors', () => {
    const css = readFileSync(resolve(REPO_ROOT, 'app/static/css/mobile.css'), 'utf8')
    const shellMatch = css.match(
      /body\.mobile-terminal-mode #mobile-shell-composer\s*\{([\s\S]*?)\}/,
    )
    const composerMatch = css.match(
      /body\.mobile-terminal-mode #mobile-shell-composer #mobile-composer\s*\{([\s\S]*?)\}/,
    )

    expect(shellMatch).not.toBeNull()
    expect(shellMatch[1]).toMatch(/background:\s*var\(--surface\)/)
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

    const menuSheet = document.getElementById('mobile-menu-sheet')
    menuSheet.classList.remove('u-hidden')
    document.getElementById('history-panel').classList.add('open')

    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => mobileCmdInput,
    })
    window.visualViewport.height = 500
    mobileCmdInput.dispatchEvent(new Event('focus'))
    mobileCmdInput.value = 'curl'
    mobileCmdInput.dispatchEvent(new Event('input'))

    expect(menuSheet.classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('history-panel').classList.contains('open')).toBe(false)

    restoreViewport()
  })

  it('matches autocomplete suggestions from the beginning of each command only', async () => {
    const acShow = vi.fn()
    const apiFetch = vi.fn((url) => {
      if (url === '/autocomplete') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              suggestions: ['curl http://localhost:5001/health', 'man curl', 'cat /etc/hosts'],
            }),
        })
      }
      if (url === '/config') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
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
        return Promise.resolve({
          json: () => Promise.resolve({ restricted: false, commands: [], groups: [], items: [] }),
        })
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

  it('prefers contextual autocomplete suggestions after the command root', async () => {
    const acShow = vi.fn()
    const { cmdInput } = await loadAppFns({
      getAutocompleteMatches: () => [
        { value: '-sV', description: 'Service detection', replaceStart: 5, replaceEnd: 6 },
        { value: '-Pn', description: 'Skip host discovery', replaceStart: 5, replaceEnd: 6 },
      ],
      acShow,
    })

    cmdInput.value = 'nmap -'
    cmdInput.setSelectionRange(6, 6)
    cmdInput.dispatchEvent(new Event('input'))

    expect(acShow).toHaveBeenCalled()
    const [items] = acShow.mock.calls.at(-1)
    expect(items.map((item) => item.value)).toEqual(['-sV', '-Pn'])
  })

  it('suppresses duplicate contextual flags that were already used in the command', async () => {
    const acShow = vi.fn()
    const { cmdInput } = await loadAppFns({
      getAutocompleteMatches: () => [
        { value: '-sV', description: 'Service detection', replaceStart: 9, replaceEnd: 10 },
      ],
      acShow,
    })

    cmdInput.value = 'nmap -Pn -'
    cmdInput.setSelectionRange(10, 10)
    cmdInput.dispatchEvent(new Event('input'))

    const [items] = acShow.mock.calls.at(-1)
    expect(items.map((item) => item.value)).toEqual(['-sV'])
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

  it('refreshes prompt rendering from the focused input before drawing the caret', async () => {
    const { cmdInput, setComposerState, syncShellPrompt } = await loadAppFns()
    const shellPromptText = document.getElementById('shell-prompt-text')
    const shellPromptWrap = document.getElementById('shell-prompt-wrap')

    setComposerState({
      value: 'stale text',
      selectionStart: 10,
      selectionEnd: 10,
      activeInput: 'desktop',
    })
    cmdInput.value = ''
    cmdInput.setSelectionRange(0, 0)
    const activeElementSpy = vi.spyOn(document, 'activeElement', 'get').mockReturnValue(cmdInput)

    syncShellPrompt()

    expect(shellPromptText.textContent).toBe('')
    expect(shellPromptWrap.classList.contains('shell-prompt-empty')).toBe(true)
    expect(shellPromptWrap.classList.contains('shell-prompt-has-value')).toBe(false)
    activeElementSpy.mockRestore()
  })

  it('supports ctrl+w to delete one word to the left', async () => {
    const { cmdInput, setComposerState } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.focus()
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
    setComposerState({
      value: 'dig darklab.sh A',
      selectionStart: 12,
      selectionEnd: 12,
      activeInput: 'desktop',
    })
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
    setComposerState({
      value: 'dig darklab.sh A',
      selectionStart: 4,
      selectionEnd: 4,
      activeInput: 'desktop',
    })
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
    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: '∫',
        code: 'KeyB',
        altKey: true,
        bubbles: true,
      }),
    )
    expect(cmdInput.selectionStart).toBe(15)

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'ƒ',
        code: 'KeyF',
        altKey: true,
        bubbles: true,
      }),
    )
    expect(cmdInput.selectionStart).toBe(16)
  })

  it('supports the mobile keyboard helper edit actions', async () => {
    const { getVisibleComposerInput, performMobileEditAction, setComposerState } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })

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

    performMobileEditAction('left')
    expect(visibleInput.selectionStart).toBe(visibleInput.value.length - 1)

    performMobileEditAction('home')
    expect(visibleInput.selectionStart).toBe(0)

    performMobileEditAction('word-right')
    expect(visibleInput.selectionStart).toBe(4)

    performMobileEditAction('right')
    expect(visibleInput.selectionStart).toBe(5)

    performMobileEditAction('word-left')
    expect(visibleInput.selectionStart).toBe(0)

    performMobileEditAction('end')
    expect(visibleInput.selectionStart).toBe(visibleInput.value.length)

    performMobileEditAction('delete-word')
    expect(visibleInput.value).toBe('ping -c 4 ')

    performMobileEditAction('delete-line')
    expect(visibleInput.value).toBe('')
    expect(visibleInput.selectionStart).toBe(0)
  })

  it('keeps the mobile composer scrolled to the caret when helper navigation moves through long input', async () => {
    const { getVisibleComposerInput, performMobileEditAction, setComposerState } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })

    document.body.classList.add('mobile-terminal-mode')
    const mobileCmdInput = document.getElementById('mobile-cmd')
    const longValue =
      'curl https://example.com/healthcheck/with/a/very/long/path?token=abcdef1234567890'
    mobileCmdInput.value = longValue
    mobileCmdInput.setSelectionRange(0, 0)
    mobileCmdInput.scrollLeft = 0
    Object.defineProperty(mobileCmdInput, 'clientWidth', { value: 140, configurable: true })
    setComposerState({
      value: longValue,
      selectionStart: 0,
      selectionEnd: 0,
      activeInput: 'mobile',
    })
    const visibleInput = getVisibleComposerInput()

    performMobileEditAction('end')
    expect(visibleInput.selectionStart).toBe(longValue.length)
    expect(visibleInput.scrollLeft).toBeGreaterThan(0)

    performMobileEditAction('home')
    expect(visibleInput.selectionStart).toBe(0)
    expect(visibleInput.scrollLeft).toBe(0)
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

  it('uses Ctrl+C to cancel a pending terminal confirmation before opening a fresh prompt', async () => {
    const interruptPromptLine = vi.fn()
    const cancelPendingTerminalConfirm = vi.fn(() => true)
    const hasPendingTerminalConfirm = vi.fn(() => true)
    const { cmdInput, confirmKill } = await loadAppFns({
      tabs: [{ id: 'tab-1', st: 'idle' }],
      interruptPromptLine,
      hasPendingTerminalConfirm,
      cancelPendingTerminalConfirm,
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'c', ctrlKey: true, bubbles: true }))

    expect(hasPendingTerminalConfirm).toHaveBeenCalled()
    expect(cancelPendingTerminalConfirm).toHaveBeenCalledWith('tab-1')
    expect(interruptPromptLine).not.toHaveBeenCalled()
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

    expect(createTab).toHaveBeenCalledWith('shell 2')
  })

  it('supports macOS Option+T to create a new tab via physical key code', async () => {
    const createTab = vi.fn(() => 'tab-2')
    const { cmdInput } = await loadAppFns({
      createTab,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })
    createTab.mockClear()

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: '†',
        code: 'KeyT',
        altKey: true,
        bubbles: true,
      }),
    )

    expect(createTab).toHaveBeenCalledWith('shell 2')
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

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: '∑',
        code: 'KeyW',
        altKey: true,
        bubbles: true,
      }),
    )

    expect(closeTab).toHaveBeenCalledWith('tab-1')
  })

  it('supports Alt+ArrowLeft and Alt+ArrowRight to move by word', async () => {
    const activateTab = vi.fn()
    const { cmdInput, getComposerState, handleComposerWordArrowShortcut, setComposerValue } = await loadAppFns({
      activateTab,
      activeTabId: 'tab-2',
      tabs: [
        { id: 'tab-1', st: 'idle' },
        { id: 'tab-2', st: 'idle' },
        { id: 'tab-3', st: 'idle' },
      ],
    })

    setComposerValue('dig darklab.sh A', 16, 16, { dispatch: false })
    cmdInput.focus()

    expect(handleComposerWordArrowShortcut({
      key: 'ArrowLeft',
      code: 'ArrowLeft',
      altKey: true,
      ctrlKey: false,
      metaKey: false,
      shiftKey: false,
      preventDefault: vi.fn(),
      stopPropagation: vi.fn(),
    })).toBe(true)
    expect(getComposerState().selectionStart).toBe(15)
    expect(getComposerState().selectionEnd).toBe(15)

    handleComposerWordArrowShortcut({
      key: 'ArrowLeft',
      code: 'ArrowLeft',
      altKey: true,
      ctrlKey: false,
      metaKey: false,
      shiftKey: false,
      preventDefault: vi.fn(),
      stopPropagation: vi.fn(),
    })
    expect(getComposerState().selectionStart).toBe(4)
    expect(getComposerState().selectionEnd).toBe(4)

    handleComposerWordArrowShortcut({
      key: 'ArrowRight',
      code: 'ArrowRight',
      altKey: true,
      ctrlKey: false,
      metaKey: false,
      shiftKey: false,
      preventDefault: vi.fn(),
      stopPropagation: vi.fn(),
    })
    expect(getComposerState().selectionStart).toBe(14)
    expect(getComposerState().selectionEnd).toBe(14)
    expect(activateTab).not.toHaveBeenCalled()
  })

  it('supports Shift+Alt+ArrowLeft and Shift+Alt+ArrowRight to cycle between tabs', async () => {
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

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowRight', code: 'ArrowRight', altKey: true, shiftKey: true, bubbles: true }),
    )
    expect(activateTab).toHaveBeenCalledWith('tab-3')

    activateTab.mockClear()
    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowLeft', code: 'ArrowLeft', altKey: true, shiftKey: true, bubbles: true }),
    )
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

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: '£',
        code: 'Digit3',
        altKey: true,
        bubbles: true,
      }),
    )

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

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'π',
        code: 'KeyP',
        altKey: true,
        bubbles: true,
      }),
    )

    expect(permalinkTab).toHaveBeenCalledWith('tab-1')
  })

  it('supports Alt+Shift+C to copy output for the active tab', async () => {
    const copyTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      copyTab,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'C',
        altKey: true,
        shiftKey: true,
        bubbles: true,
      }),
    )

    expect(copyTab).toHaveBeenCalledWith('tab-1')
  })

  it('supports macOS Option+Shift+C to copy output via physical key code', async () => {
    const copyTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      copyTab,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'Ç',
        code: 'KeyC',
        altKey: true,
        shiftKey: true,
        bubbles: true,
      }),
    )

    expect(copyTab).toHaveBeenCalledWith('tab-1')
  })

  it('supports Alt+R to open the run monitor from the terminal prompt', async () => {
    const openRunMonitor = vi.fn(() => Promise.resolve(true))
    const { cmdInput } = await loadAppFns({
      openRunMonitor,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'r', altKey: true, bubbles: true }))

    expect(openRunMonitor).toHaveBeenCalledWith({ source: 'shortcut' })
  })

  it('supports Alt+Shift+F to open the Files modal from the terminal prompt', async () => {
    const openWorkspace = vi.fn()
    const { cmdInput } = await loadAppFns({
      openWorkspace,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'F',
        code: 'KeyF',
        altKey: true,
        shiftKey: true,
        bubbles: true,
      }),
    )

    expect(openWorkspace).toHaveBeenCalled()
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

    searchInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 't', altKey: true, bubbles: true }),
    )
    searchInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowRight', altKey: true, bubbles: true }),
    )

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

    searchInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'p', altKey: true, bubbles: true }),
    )
    searchInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'C',
        altKey: true,
        shiftKey: true,
        bubbles: true,
      }),
    )
    searchInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'l', ctrlKey: true, bubbles: true }),
    )

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

  it('Tab expands the typed value to the longest shared autocomplete prefix before cycling', async () => {
    const { cmdInput, _getAcIndex } = await loadAppFns({
      acSuggestions: ['ping', 'ping -c 4', 'ping google.com'],
      acFiltered: ['ping', 'ping -c 4', 'ping google.com'],
      acIndex: -1,
      acExpandSharedPrefix: (items) => {
        if (items.join('|') !== 'ping|ping -c 4|ping google.com') return false
        document.getElementById('cmd').value = 'ping'
        return true
      },
    })

    cmdInput.value = 'pi'
    cmdInput.setSelectionRange(2, 2)
    cmdInput.dispatchEvent(new Event('input'))
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))

    expect(cmdInput.value).toBe('ping')
    expect(_getAcIndex()).toBe(-1)
  })

  it('Tab cycles autocomplete suggestions once the shared prefix is exhausted', async () => {
    const { cmdInput, _getAcIndex, acDropdown } = await loadAppFns({
      acSuggestions: ['ping -c 4', 'ping google.com', 'ping localhost'],
      acFiltered: ['ping -c 4', 'ping google.com', 'ping localhost'],
      acIndex: -1,
      acShow: () => {
        acDropdown.style.display = 'block'
      },
    })

    cmdInput.value = 'ping '
    cmdInput.setSelectionRange(5, 5)
    cmdInput.dispatchEvent(new Event('input'))

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(_getAcIndex()).toBe(0)
    expect(acDropdown.style.display).toBe('block')

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(_getAcIndex()).toBe(1)

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true }),
    )
    expect(_getAcIndex()).toBe(0)
  })

  it('Tab key with a modifier does not trigger autocomplete accept or selection', async () => {
    const { cmdInput, _getAcIndex } = await loadAppFns({
      acFiltered: ['alpha', 'bravo'],
      acIndex: -1,
    })

    // Alt+Tab (the app tab-cycle shortcut) must not trigger autocomplete
    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Tab', altKey: true, bubbles: true }),
    )
    expect(_getAcIndex()).toBe(-1)

    // Ctrl+Tab must not trigger autocomplete
    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Tab', ctrlKey: true, bubbles: true }),
    )
    expect(_getAcIndex()).toBe(-1)

    // Meta+Tab must not trigger autocomplete
    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Tab', metaKey: true, bubbles: true }),
    )
    expect(_getAcIndex()).toBe(-1)

    // Plain Tab (no modifier) still triggers autocomplete selection
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(_getAcIndex()).toBe(0)
  })

  it('routes hist-clear-all through confirmHistAction', async () => {
    // Modal wiring itself is covered by ui_confirm.test.js (the primitive)
    // and history.test.js (confirmHistAction's call to showConfirm). Here
    // we just verify the app bootstrap still connects the clear-all button.
    const { confirmHistAction } = await loadAppFns()
    confirmHistAction.mockClear()
    document.getElementById('hist-clear-all-btn').click()
    expect(confirmHistAction).toHaveBeenCalledWith('clear')
  })

  it('uses the persistent share redaction default before showing the modal prompt', async () => {
    const {
      confirmPermalinkRedactionChoice,
      getShareRedactionDefaultPreference,
    } = await loadAppFns({
      cookies: { pref_share_redaction_default: 'raw' },
    })

    // showConfirm is stubbed to resolve null (cancel) by loadAppFns; if the
    // preference short-circuit failed, this would resolve null instead of
    // 'raw'. The assertion implicitly verifies the modal was skipped.
    await expect(confirmPermalinkRedactionChoice()).resolves.toBe('raw')
    expect(getShareRedactionDefaultPreference()).toBe('raw')
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
    await new Promise((resolve) => setTimeout(resolve, 10))
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
    const { openFaq } = await loadAppFns()
    const faqOverlay = document.getElementById('faq-overlay')

    openFaq()
    expect(faqOverlay.classList.contains('open')).toBe(true)

    faqOverlay.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(faqOverlay.classList.contains('open')).toBe(false)

    openFaq()
    document.querySelector('.faq-close').click()
    expect(faqOverlay.classList.contains('open')).toBe(false)
  })

  it('closes the theme overlay and refocuses the terminal on Escape', async () => {
    const { openThemeSelector } = await loadAppFns({
      mobileTouch: false,
      themeRegistry: {
        current: {
          name: 'theme_light_blue',
          label: 'Apricot Sand',
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
        ],
      },
    })
    const themeOverlay = document.getElementById('theme-overlay')

    openThemeSelector()
    expect(themeOverlay.classList.contains('open')).toBe(true)

    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(themeOverlay.classList.contains('open')).toBe(false)
  })

  it('does not refocus the mobile composer when closing options', async () => {
    const { getVisibleComposerInput, openOptions } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const overlay = document.getElementById('options-overlay')
    const visibleInput = getVisibleComposerInput()
    visibleInput.focus.mockClear()

    openOptions()
    expect(overlay.classList.contains('open')).toBe(true)

    document.querySelector('.options-close').click()
    expect(overlay.classList.contains('open')).toBe(false)
    expect(visibleInput.focus).not.toHaveBeenCalled()

    document.querySelector('#mobile-menu-sheet [data-menu-action="options"]').click()
    expect(overlay.classList.contains('open')).toBe(true)

    overlay.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(overlay.classList.contains('open')).toBe(false)
  })

  it('blurs the visible mobile composer when opening options', async () => {
    const { getVisibleComposerInput, openOptions, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const overlay = document.getElementById('options-overlay')
    const visibleInput = getVisibleComposerInput()
    document.body.classList.add('mobile-terminal-mode')

    openOptions()

    expect(overlay.classList.contains('open')).toBe(true)
    expect(visibleInput.blur).toHaveBeenCalled()

    restoreViewport()
  })

  it('hides rotate/clear/copy session token buttons when no token is set — desktop open', async () => {
    const { openOptions } = await loadAppFns()  // no session_token in localStorage

    openOptions()

    expect(document.getElementById('options-session-token-rotate-btn').style.display).toBe('none')
    expect(document.getElementById('options-session-token-clear-btn').style.display).toBe('none')
    expect(document.getElementById('options-session-token-copy-btn').style.display).toBe('none')
  })

  it('hides rotate/clear/copy session token buttons when no token is set — mobile menu open', async () => {
    await loadAppFns()  // no session_token in localStorage

    document.querySelector('#mobile-menu-sheet [data-menu-action="options"]').click()

    expect(document.getElementById('options-session-token-rotate-btn').style.display).toBe('none')
    expect(document.getElementById('options-session-token-clear-btn').style.display).toBe('none')
    expect(document.getElementById('options-session-token-copy-btn').style.display).toBe('none')
  })

  it('shows rotate/clear/copy session token buttons when a token is active — mobile menu open', async () => {
    const { storage } = await loadAppFns()
    storage.setItem('session_token', 'tok_abcd1234efgh5678ijkl9012mnop3456')

    document.querySelector('#mobile-menu-sheet [data-menu-action="options"]').click()

    expect(document.getElementById('options-session-token-rotate-btn').style.display).toBe('')
    expect(document.getElementById('options-session-token-clear-btn').style.display).toBe('')
    expect(document.getElementById('options-session-token-copy-btn').style.display).toBe('')
  })

  it('aborts session-token set when the migration prompt is dismissed instead of applying the token', async () => {
    const updateSessionId = vi.fn()
    const showToast = vi.fn()
    const apiFetch = vi.fn((url, opts = {}) => {
      if (url === '/session/token/verify') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ exists: true }),
        })
      }
      if (url === '/session/run-count') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ count: 3 }),
        })
      }
      if (url === '/config') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
              prompt_prefix: 'anon@darklab:~$',
              version: '9.9',
              project_readme: 'https://gitlab.com/darklab.sh/darklab_shell',
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
        return Promise.resolve({
          json: () => Promise.resolve({ restricted: false, commands: [], groups: [] }),
        })
      }
      if (url === '/faq') {
        return Promise.resolve({ json: () => Promise.resolve({ items: [] }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const showConfirm = vi
      .fn()
      .mockImplementationOnce(async (opts) => {
        const input = opts.content.find((node) => node?.id === 'session-token-set-input')
        input.value = 'tok_existing1234567890abcdef1234567890'
        const apply = opts.actions.find((action) => action.id === 'apply')
        const ok = await apply.onActivate()
        return ok ? 'apply' : null
      })
      .mockResolvedValueOnce(null)

    const { storage } = await loadAppFns({
      apiFetch,
      showConfirm,
      showToast,
      updateSessionId,
      sessionId: 'session-old',
    })

    document.getElementById('options-session-token-set-btn').click()
    await vi.waitFor(() => expect(showConfirm).toHaveBeenCalledTimes(2))
    expect(showConfirm.mock.calls[1][0].actions.map((action) => action.id)).toEqual([
      'cancel',
      'skip',
      'yes',
    ])
    expect(storage.getItem('session_token')).toBeNull()
    expect(updateSessionId).not.toHaveBeenCalled()
    expect(showToast).not.toHaveBeenCalledWith('Session token applied')
  })

  it('applies session-token set on explicit skip without running migration', async () => {
    const updateSessionId = vi.fn()
    const showToast = vi.fn()
    const fetchSpy = vi.fn()
    const apiFetch = vi.fn((url, opts = {}) => {
      if (url === '/session/token/verify') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ exists: true }),
        })
      }
      if (url === '/session/run-count') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ count: 2 }),
        })
      }
      if (url === '/config') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
              prompt_prefix: 'anon@darklab:~$',
              version: '9.9',
              project_readme: 'https://gitlab.com/darklab.sh/darklab_shell',
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
        return Promise.resolve({
          json: () => Promise.resolve({ restricted: false, commands: [], groups: [] }),
        })
      }
      if (url === '/faq') {
        return Promise.resolve({ json: () => Promise.resolve({ items: [] }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const showConfirm = vi
      .fn()
      .mockImplementationOnce(async (opts) => {
        const input = opts.content.find((node) => node?.id === 'session-token-set-input')
        input.value = 'tok_existing1234567890abcdef1234567890'
        const apply = opts.actions.find((action) => action.id === 'apply')
        const ok = await apply.onActivate()
        return ok ? 'apply' : null
      })
      .mockResolvedValueOnce('skip')
    const originalFetch = global.fetch
    global.fetch = fetchSpy

    try {
      const { storage } = await loadAppFns({
        apiFetch,
        showConfirm,
        showToast,
        updateSessionId,
        sessionId: 'session-old',
      })

      document.getElementById('options-session-token-set-btn').click()
      await vi.waitFor(() =>
        expect(storage.getItem('session_token')).toBe('tok_existing1234567890abcdef1234567890'),
      )
      expect(updateSessionId).toHaveBeenCalledWith('tok_existing1234567890abcdef1234567890')
      expect(fetchSpy).not.toHaveBeenCalled()
      expect(showToast).toHaveBeenCalledWith('Session token applied')
    } finally {
      global.fetch = originalFetch
    }
  })

  it('opens the session-token set confirm without relying on a Node global binding', async () => {
    const showConfirm = vi.fn().mockResolvedValue(null)
    const originalGlobal = globalThis.global

    try {
      globalThis.global = undefined
      await loadAppFns({ showConfirm })
      document.getElementById('options-session-token-set-btn').click()
      await vi.waitFor(() => expect(showConfirm).toHaveBeenCalledTimes(1))
    } finally {
      globalThis.global = originalGlobal
    }
  })

  it('aborts generated-token activation when the migration prompt is dismissed', async () => {
    const updateSessionId = vi.fn()
    const showToast = vi.fn()
    const copyTextToClipboard = vi.fn(() => Promise.resolve())
    const apiFetch = vi.fn((url) => {
      if (url === '/session/token/generate') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ session_token: 'tok_generated1234567890abcdef1234567' }),
        })
      }
      if (url === '/session/run-count') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ count: 4 }),
        })
      }
      if (url === '/config') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
              prompt_prefix: 'anon@darklab:~$',
              version: '9.9',
              project_readme: 'https://gitlab.com/darklab.sh/darklab_shell',
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
        return Promise.resolve({
          json: () => Promise.resolve({ restricted: false, commands: [], groups: [] }),
        })
      }
      if (url === '/faq') {
        return Promise.resolve({ json: () => Promise.resolve({ items: [] }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const showConfirm = vi.fn().mockResolvedValue(null)

    const { storage } = await loadAppFns({
      apiFetch,
      showConfirm,
      showToast,
      updateSessionId,
      copyTextToClipboard,
      sessionId: 'session-old',
    })

    document.getElementById('options-session-token-generate-btn').click()
    await vi.waitFor(() => expect(showConfirm).toHaveBeenCalledTimes(1))
    expect(showConfirm.mock.calls[0][0].actions.map((action) => action.id)).toEqual([
      'cancel',
      'skip',
      'yes',
    ])
    expect(storage.getItem('session_token')).toBeNull()
    expect(updateSessionId).not.toHaveBeenCalled()
    expect(copyTextToClipboard).not.toHaveBeenCalled()
    expect(showToast).not.toHaveBeenCalledWith('Session token applied')
  })

  it('opens a destructive confirm before clearing the active session token', async () => {
    const showConfirm = vi.fn().mockResolvedValue(null)
    const { storage } = await loadAppFns({ showConfirm })
    storage.setItem('session_token', 'tok_abcd1234efgh5678ijkl9012mnop3456')

    document.getElementById('options-session-token-clear-btn').click()
    await vi.waitFor(() => expect(showConfirm).toHaveBeenCalledTimes(1))

    const confirmOpts = showConfirm.mock.calls[0][0]
    expect(confirmOpts.tone).toBe('danger')
    expect(confirmOpts.body.text).toBe('Clear the current session token from this browser?')
    expect(confirmOpts.body.note).toContain('will not be able to recover it from the app')
    expect(confirmOpts.actions.map((action) => action.id)).toEqual(['copy', 'cancel', 'clear'])
    expect(confirmOpts.actions.find((action) => action.id === 'cancel')).toMatchObject({ role: 'cancel' })
    expect(confirmOpts.actions.find((action) => action.id === 'clear')).toMatchObject({
      role: 'destructive',
      label: 'Clear token',
    })
  })

  it('lets the user copy the session token from the clear confirm without clearing it', async () => {
    const copyTextToClipboard = vi.fn(() => Promise.resolve())
    const showToast = vi.fn()
    const updateSessionId = vi.fn()
    const showConfirm = vi.fn().mockImplementation(async (opts) => {
      const copy = opts.actions.find((action) => action.id === 'copy')
      const keepOpen = await copy.onActivate()
      expect(keepOpen).toBe(false)
      return 'cancel'
    })
    const { storage } = await loadAppFns({
      showConfirm,
      copyTextToClipboard,
      showToast,
      updateSessionId,
    })
    storage.setItem('session_token', 'tok_abcd1234efgh5678ijkl9012mnop3456')

    document.getElementById('options-session-token-clear-btn').click()
    await vi.waitFor(() => expect(showConfirm).toHaveBeenCalledTimes(1))

    expect(copyTextToClipboard).toHaveBeenCalledWith('tok_abcd1234efgh5678ijkl9012mnop3456')
    expect(showToast).toHaveBeenCalledWith('Token copied to clipboard')
    expect(storage.getItem('session_token')).toBe('tok_abcd1234efgh5678ijkl9012mnop3456')
    expect(updateSessionId).not.toHaveBeenCalled()
  })

  it('clears the session token only after confirming the destructive action', async () => {
    const showConfirm = vi.fn().mockResolvedValue('clear')
    const showToast = vi.fn()
    const updateSessionId = vi.fn()
    const reloadSessionHistory = vi.fn(() => Promise.resolve())
    const hydrateCmdHistory = vi.fn()
    const { storage } = await loadAppFns({
      showConfirm,
      showToast,
      updateSessionId,
      reloadSessionHistory,
      hydrateCmdHistory,
      sessionId: 'session-old',
    })
    storage.setItem('session_token', 'tok_abcd1234efgh5678ijkl9012mnop3456')

    document.getElementById('options-session-token-clear-btn').click()
    await vi.waitFor(() => expect(storage.getItem('session_token')).toBeNull())

    expect(updateSessionId).toHaveBeenCalledWith('session-old')
    expect(hydrateCmdHistory).toHaveBeenCalledWith([])
    expect(reloadSessionHistory).toHaveBeenCalled()
    expect(document.getElementById('options-session-token-status').textContent).toBe(
      'No session token — anonymous session',
    )
    expect(showToast).toHaveBeenCalledWith('Session token cleared')
  })

  it('persists options changes through cookies and syncs quick-toggle state', async () => {
    const apiFetch = vi.fn((url, opts = {}) => {
      if (url === '/config') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
              prompt_prefix: 'anon@darklab:~$',
              version: '9.9',
              project_readme: 'https://gitlab.com/darklab.sh/darklab_shell',
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
      if (url === '/session/preferences' && (!opts.method || opts.method === 'GET')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ preferences: {} }) })
      }
      if (url === '/session/preferences' && opts.method === 'POST') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const { getWelcomeIntroPreference, getShareRedactionDefaultPreference, getHudClockPreference } = await loadAppFns({
      apiFetch,
      themeRegistry: {
        current: {
          name: 'theme_light_blue',
          label: 'Apricot Sand',
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
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

    document.querySelector('.rail-nav [data-action="theme"]').click()
    document
      .getElementById('theme-select')
      .querySelector('[data-theme-name="theme_light_olive"]')
      .click()
    document
      .getElementById('theme-overlay')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    document.querySelector('.rail-nav [data-action="options"]').click()
    document.getElementById('options-ts-select').value = 'elapsed'
    document
      .getElementById('options-ts-select')
      .dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('options-ln-toggle').checked = true
    document
      .getElementById('options-ln-toggle')
      .dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('options-welcome-select').value = 'disable_animation'
    document
      .getElementById('options-welcome-select')
      .dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('options-share-redaction-select').value = 'redacted'
    document
      .getElementById('options-share-redaction-select')
      .dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('options-hud-clock-select').value = 'local'
    document
      .getElementById('options-hud-clock-select')
      .dispatchEvent(new Event('change', { bubbles: true }))

    expect(document.body.classList.contains('ts-elapsed')).toBe(true)
    expect(document.body.classList.contains('ln-on')).toBe(true)
    expect(document.getElementById('ts-btn').textContent).toBe('timestamps: elapsed')
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers: on')
    expect(document.cookie).toContain('pref_theme_name=theme_light_olive')
    expect(document.cookie).toContain('pref_timestamps=elapsed')
    expect(document.cookie).toContain('pref_line_numbers=on')
    expect(document.cookie).toContain('pref_welcome_intro=disable_animation')
    expect(document.cookie).toContain('pref_share_redaction_default=redacted')
    expect(document.cookie).toContain('pref_hud_clock=local')
    expect(getWelcomeIntroPreference()).toBe('disable_animation')
    expect(getShareRedactionDefaultPreference()).toBe('redacted')
    expect(getHudClockPreference()).toBe('local')
    const postCalls = apiFetch.mock.calls.filter(([url, opts]) => url === '/session/preferences' && opts?.method === 'POST')
    expect(postCalls.length).toBeGreaterThan(0)
    const lastPayload = JSON.parse(postCalls.at(-1)[1].body)
    expect(lastPayload.preferences).toMatchObject({
      pref_theme_name: 'theme_light_olive',
      pref_timestamps: 'elapsed',
      pref_line_numbers: 'on',
      pref_welcome_intro: 'disable_animation',
      pref_share_redaction_default: 'redacted',
      pref_hud_clock: 'local',
    })
  })

  it('renders backend-driven FAQ items with HTML answers and dynamic sections', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/config') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
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
          json: () =>
            Promise.resolve({
              restricted: true,
              commands: ['ping', 'curl'],
              groups: [{ name: 'Network', commands: ['ping', 'curl'] }],
            }),
        })
      }
      if (url === '/faq') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              items: [
                {
                  question: 'What is this?',
                  answer: 'plain',
                  answer_html: 'Rich <strong>HTML</strong>',
                },
                { question: 'Allowed?', answer: 'allowlist', ui_kind: 'allowed_commands' },
                { question: 'Limits?', answer: 'limits', ui_kind: 'limits' },
              ],
            }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })

    await loadAppFns({ apiFetch })
    await new Promise((resolve) => setImmediate(resolve))

    const questions = [...document.querySelectorAll('.faq-q')].map((el) => el.textContent)
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
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
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
          json: () =>
            Promise.resolve({
              restricted: true,
              commands: ['curl'],
              groups: [{ name: 'Network', commands: ['curl'] }],
            }),
        })
      }
      if (url === '/faq') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              items: [{ question: 'Allowed?', answer: 'allowlist', ui_kind: 'allowed_commands' }],
            }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })

    const { openFaq } = await loadAppFns({ apiFetch, mobileViewport: { height: 500, offsetTop: 0 } })
    await new Promise((resolve) => setImmediate(resolve))

    const mobileCmdInput = document.getElementById('mobile-cmd')
    const chip = document.querySelector('.allowed-chip')

    openFaq()
    expect(mobileCmdInput.blur).toHaveBeenCalled()

    chip.click()

    expect(mobileCmdInput.value).toBe('curl ')
    expect(mobileCmdInput.focus).not.toHaveBeenCalled()
  })

  it('loads custom FAQ chips into the prompt with the same command-chip behavior', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/config') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
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
          json: () =>
            Promise.resolve({
              restricted: true,
              commands: ['curl'],
              groups: [{ name: 'Network', commands: ['curl'] }],
            }),
        })
      }
      if (url === '/faq') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              items: [
                {
                  question: 'Styled custom FAQ?',
                  answer: 'Use [[cmd:ping -c 1 127.0.0.1|ping chip]] and **bold**.',
                  answer_html:
                    'Use <span class="allowed-chip faq-chip" data-faq-command="ping -c 1 127.0.0.1" role="button" tabindex="0">ping chip</span> and <strong>bold</strong>.',
                },
              ],
            }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })

    await loadAppFns({ apiFetch, mobileViewport: { height: 500, offsetTop: 0 } })
    await new Promise((resolve) => setImmediate(resolve))

    const chip = document.querySelector(
      '.faq-item .faq-chip[data-faq-command="ping -c 1 127.0.0.1"]',
    )
    expect(chip).not.toBeNull()

    chip.click()

    expect(document.getElementById('mobile-cmd').value).toBe('ping -c 1 127.0.0.1 ')
    expect(document.getElementById('faq-overlay').classList.contains('open')).toBe(false)
  })
})

// ── Run notification preference ───────────────────────────────────────────────

describe('getRunNotifyPreference', () => {
  it('returns off when no cookie is set', async () => {
    const { getRunNotifyPreference } = await loadAppFns({})
    expect(getRunNotifyPreference()).toBe('off')
  })

  it('returns on when cookie is set to on', async () => {
    const { getRunNotifyPreference } = await loadAppFns({
      cookies: { pref_run_notify: 'on' },
    })
    expect(getRunNotifyPreference()).toBe('on')
  })

  it('returns off for any value other than on', async () => {
    const { getRunNotifyPreference } = await loadAppFns({
      cookies: { pref_run_notify: 'yes' },
    })
    expect(getRunNotifyPreference()).toBe('off')
  })
})

describe('applyRunNotifyPreference', () => {
  it('saves on and syncs toggle when permission is already granted', async () => {
    class MockNotification {}
    MockNotification.permission = 'granted'
    const { applyRunNotifyPreference, getRunNotifyPreference } = await loadAppFns({
      Notification: MockNotification,
    })
    await applyRunNotifyPreference('on')
    expect(getRunNotifyPreference()).toBe('on')
    expect(document.getElementById('options-notify-toggle').checked).toBe(true)
  })

  it('requests permission when it is default and saves on if granted', async () => {
    class MockNotification {}
    MockNotification.permission = 'default'
    MockNotification.requestPermission = vi.fn().mockResolvedValue('granted')
    const { applyRunNotifyPreference, getRunNotifyPreference } = await loadAppFns({
      Notification: MockNotification,
    })
    await applyRunNotifyPreference('on')
    expect(MockNotification.requestPermission).toHaveBeenCalledOnce()
    expect(getRunNotifyPreference()).toBe('on')
  })

  it('falls back to off and unchecks toggle when permission request is denied', async () => {
    class MockNotification {}
    MockNotification.permission = 'default'
    MockNotification.requestPermission = vi.fn().mockResolvedValue('denied')
    const { applyRunNotifyPreference, getRunNotifyPreference } = await loadAppFns({
      Notification: MockNotification,
    })
    await applyRunNotifyPreference('on')
    expect(getRunNotifyPreference()).toBe('off')
    expect(document.getElementById('options-notify-toggle').checked).toBe(false)
  })

  it('falls back to off and shows toast when permission is already denied by browser', async () => {
    const showToast = vi.fn()
    class MockNotification {}
    MockNotification.permission = 'denied'
    const { applyRunNotifyPreference, getRunNotifyPreference } = await loadAppFns({
      Notification: MockNotification,
      showToast,
    })
    await applyRunNotifyPreference('on')
    expect(getRunNotifyPreference()).toBe('off')
    expect(showToast).toHaveBeenCalledWith(expect.stringContaining('blocked'))
  })

  it('saves off and unchecks toggle when mode is off', async () => {
    const { applyRunNotifyPreference, getRunNotifyPreference } = await loadAppFns({
      cookies: { pref_run_notify: 'on' },
    })
    await applyRunNotifyPreference('off')
    expect(getRunNotifyPreference()).toBe('off')
    expect(document.getElementById('options-notify-toggle').checked).toBe(false)
  })
})

describe('syncOptionsControls notify toggle', () => {
  it('reflects off preference as unchecked toggle', async () => {
    const { syncOptionsControls } = await loadAppFns({})
    syncOptionsControls()
    expect(document.getElementById('options-notify-toggle').checked).toBe(false)
  })

  it('reflects on preference as checked toggle', async () => {
    const { syncOptionsControls } = await loadAppFns({
      cookies: { pref_run_notify: 'on' },
    })
    syncOptionsControls()
    expect(document.getElementById('options-notify-toggle').checked).toBe(true)
  })
})
