import { vi } from 'vitest'
import { MemoryStorage, fromDomScripts } from './extract.js'

// This harness recreates the browser-global environment expected by the classic
// script bundle so app.js can be tested without loading the full page.
export async function loadAppFns({
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
  openStatusMonitor: openStatusMonitorOverride = vi.fn(() => Promise.resolve(false)),
  closeStatusMonitor: closeStatusMonitorOverride = vi.fn(),
  isStatusMonitorOpen: isStatusMonitorOpenOverride = vi.fn(() => false),
  activeTabId = 'tab-1',
  acFiltered: acFilteredOverride = [],
  acSuggestions: acSuggestionsOverride = [],
  acContextRegistry: acContextRegistryOverride = {},
  getAutocompleteMatches: getAutocompleteMatchesOverride = null,
  acIndex: acIndexOverride = -1,
  acShow: acShowOverride = () => {},
  acAccept: acAcceptOverride = () => {},
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
  getWorkspaceAutocompleteDirectoryHints: getWorkspaceAutocompleteDirectoryHintsOverride = vi.fn(() => []),
  getWorkspaceDirectoryEntries: getWorkspaceDirectoryEntriesOverride = undefined,
  workspaceCwd: workspaceCwdOverride = '',
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
          <button data-menu-action="status-monitor"></button>
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
        <span class="prompt-prefix" data-mobile-label="$">anon@darklab:/ $</span>
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
    <div id="command-catalog-overlay" class="u-hidden">
      <div id="command-catalog-modal">
        <span id="command-catalog-title"></span>
        <button class="command-catalog-close"></button>
        <div id="command-catalog-body"></div>
      </div>
    </div>
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
      <input id="options-prompt-username-input" />
      <div id="options-prompt-username-error" class="u-hidden"></div>
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
              prompt_username: 'anon',
              prompt_domain: 'darklab.sh',
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
    optionsPromptUsernameInput: document.getElementById('options-prompt-username-input'),
    optionsPromptUsernameError: document.getElementById('options-prompt-username-error'),
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
    commandCatalogOverlay: document.getElementById('command-catalog-overlay'),
    commandCatalogBody: document.getElementById('command-catalog-body'),
    commandCatalogCloseBtn: document.querySelector('.command-catalog-close'),
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
    [
      'app/static/js/output_core.js',
      'app/static/js/output.js',
      'app/static/js/app_preferences_core.js',
      'app/static/js/app.js',
      'app/static/js/controller.js',
    ],
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
      getWorkspaceAutocompleteDirectoryHints: getWorkspaceAutocompleteDirectoryHintsOverride,
      ...(getWorkspaceDirectoryEntriesOverride ? { getWorkspaceDirectoryEntries: getWorkspaceDirectoryEntriesOverride } : {}),
      _workspaceCwd: () => workspaceCwdOverride,
      workspaceDisplayPath: (path = '') => {
        const normalized = String(path || '').split('/').filter(Boolean).join('/')
        return normalized ? `/${normalized}` : '/'
      },
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
      acAccept: acAcceptOverride,
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
      openStatusMonitor: openStatusMonitorOverride,
      closeStatusMonitor: closeStatusMonitorOverride,
      isStatusMonitorOpen: isStatusMonitorOpenOverride,
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
    getPromptUsernamePreference,
    applyRunNotifyPreference,
    applyHudClockPreference,
    applyPromptUsernamePreference,
    syncOptionsControls,
    handleThemeCommand,
    handleConfigCommand,
    renderWorkflowItems,
    reloadWorkflowCatalog,
    handleWorkflowTerminalCommand,
    getRuntimeAutocompleteContext,
    getWorkspaceAutocompletePathHints,
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
