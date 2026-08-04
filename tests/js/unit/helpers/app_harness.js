// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { vi } from 'vitest'
import { MemoryStorage, fromDomScripts } from './extract.js'
import { bindFocusTrap } from '../../../../app/static/js/ui/ui_focus_trap.js'

const BASE_MATCH_MEDIA = window.matchMedia
const BASE_VISUAL_VIEWPORT = window.visualViewport
const BASE_MAX_TOUCH_POINTS = navigator.maxTouchPoints

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
  bindOutsideClickClose: bindOutsideClickCloseOverride = undefined,
  bindMobileSheet: bindMobileSheetOverride = undefined,
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
  closeWorkspace: closeWorkspaceOverride = vi.fn(),
  isWorkspaceOverlayOpen: isWorkspaceOverlayOpenOverride = vi.fn(() => false),
  isSchedulesOverlayOpen: isSchedulesOverlayOpenOverride = vi.fn(() => false),
  openSchedulesModal: openSchedulesModalOverride = vi.fn(),
  closeSchedulesModal: closeSchedulesModalOverride = vi.fn(),
  isWatchersOverlayOpen: isWatchersOverlayOpenOverride = vi.fn(() => false),
  openWatchersModal: openWatchersModalOverride = vi.fn(),
  closeWatchersModal: closeWatchersModalOverride = vi.fn(),
  openStatusMonitor: openStatusMonitorOverride = vi.fn(() => Promise.resolve(false)),
  closeStatusMonitor: closeStatusMonitorOverride = vi.fn(),
  isStatusMonitorOpen: isStatusMonitorOpenOverride = vi.fn(() => false),
  openProjectWorkspace: openProjectWorkspaceOverride = vi.fn(() => Promise.resolve(false)),
  closeProjectWorkspace: closeProjectWorkspaceOverride = vi.fn(),
  isProjectWorkspaceOpen: isProjectWorkspaceOpenOverride = vi.fn(() => false),
  cycleProjectWorkspaceTab: cycleProjectWorkspaceTabOverride = vi.fn(() => false),
  openAtlas: openAtlasOverride = vi.fn(() => Promise.resolve(false)),
  openAtlasQuickLookup: openAtlasQuickLookupOverride = vi.fn(() => Promise.resolve(false)),
  openAtlasQuickLookupFromSurface: openAtlasQuickLookupFromSurfaceOverride = null,
  isAtlasOverlayOpen: isAtlasOverlayOpenOverride = vi.fn(() => false),
  cycleAtlasTab: cycleAtlasTabOverride = vi.fn(() => false),
  isHistoryRunOverlayOpen: isHistoryRunOverlayOpenOverride = vi.fn(() => false),
  cycleHistoryRunOverlayTab: cycleHistoryRunOverlayTabOverride = vi.fn(() => false),
  openTourModal: openTourModalOverride = vi.fn(() => true),
  activeTabId = 'tab-1',
  welcomeDone = false,
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
  localStorageEntries = {},
  showToast: showToastOverride = vi.fn(),
  updateSessionId: updateSessionIdOverride = vi.fn(),
  copyTextToClipboard: copyTextToClipboardOverride = vi.fn(() => Promise.resolve()),
  reloadSessionHistory: reloadSessionHistoryOverride = vi.fn(() => Promise.resolve()),
  loadRecentValues: loadRecentValuesOverride = undefined,
  refreshWorkspaceFileCache: refreshWorkspaceFileCacheOverride = undefined,
  refreshActiveRuns: refreshActiveRunsOverride = undefined,
  refreshActiveProjectContext: refreshActiveProjectContextOverride = undefined,
  refreshStatusMonitor: refreshStatusMonitorOverride = undefined,
  invalidateOptionsSecrets: invalidateOptionsSecretsOverride = undefined,
  seedLocalStorageStarsToServer: seedLocalStorageStarsToServerOverride = vi.fn(() => Promise.resolve()),
  setTimeout: setTimeoutOverride = (fn) => {
    fn()
    return 0
  },
  clearTimeout: clearTimeoutOverride = () => {},
  hydrateCmdHistory: hydrateCmdHistoryOverride = vi.fn(),
  hasPendingTerminalConfirm: hasPendingTerminalConfirmOverride = vi.fn(() => false),
  cancelPendingTerminalConfirm: cancelPendingTerminalConfirmOverride = vi.fn(() => false),
  getWorkspaceAutocompleteFileHints: getWorkspaceAutocompleteFileHintsOverride = vi.fn(() => []),
  getWorkspaceAutocompleteDirectoryHints: getWorkspaceAutocompleteDirectoryHintsOverride = vi.fn(() => []),
  readProjectTargets: readProjectTargetsOverride = vi.fn(() => []),
  readRecentValues: readRecentValuesOverride = vi.fn(() => ({})),
  getWorkspaceDirectoryEntries: getWorkspaceDirectoryEntriesOverride = undefined,
  workspaceCwd: workspaceCwdOverride = '',
  sessionVariables: sessionVariablesOverride = [],
  appConfig = { workspace_enabled: true },
  sessionId = 'session-old',
} = {}) {
  delete document.activeElement
  document.body.removeAttribute('data-theme')
  document.body.removeAttribute('data-theme-scheme')
  ;[
    'activateOptionsTab',
    'cycleOptionsTab',
    'applyLineNumberPreference',
    'applyProjectAutoLinkExternalRunsPreference',
    'applyProjectAutoLinkRunEntitiesPreference',
    'applyCommandOutcomeSummariesPreference',
    'applyCompareViewModePreference',
    'applyCompareContextPreference',
    'applyPromptUsernamePreference',
    'setComposerPromptMode',
    'syncShellPrompt',
    'applyShareRedactionDefaultPreference',
    'applyWelcomeIntroPreference',
    'getPreference',
    'getProjectAutoLinkExternalRunsPreference',
    'getProjectAutoLinkRunEntitiesPreference',
    'getCommandOutcomeSummariesPreference',
    'getPromptUsernamePreference',
    'getCompareViewModePreference',
    'getCompareContextPreference',
    'getWelcomeIntroPreference',
    'getShareRedactionDefaultPreference',
    'syncOptionsControls',
    'DarklabTeamScope',
    '__darklabCommandRegistryBridge',
    'getAllowedCommandsFaqData',
    'setAllowedCommandsFaqData',
    'openCommandRegistry',
    'closeCommandRegistry',
    'isCommandRegistryOverlayOpen',
  ].forEach((name) => {
    try { delete window[name] } catch (_) {}
    try { delete globalThis[name] } catch (_) {}
  })
  if (!mobileViewport) {
    if (BASE_MATCH_MEDIA === undefined) delete window.matchMedia
    else window.matchMedia = BASE_MATCH_MEDIA
    if (BASE_VISUAL_VIEWPORT === undefined) delete window.visualViewport
    else Object.defineProperty(window, 'visualViewport', { configurable: true, value: BASE_VISUAL_VIEWPORT })
    if (BASE_MAX_TOUCH_POINTS === undefined) delete window.navigator.maxTouchPoints
    else Object.defineProperty(window.navigator, 'maxTouchPoints', { configurable: true, value: BASE_MAX_TOUCH_POINTS })
  }
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
      <button class="rail-nav-item" data-action="command-registry" type="button"></button>
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
          <button class="mobile-scope-row" data-menu-action="scope"><span id="mobile-team-scope-label">Personal</span></button>
          <button data-menu-action="atlas"></button>
          <button data-menu-action="quick-lookup"></button>
          <button data-menu-action="status-monitor"></button>
          <button data-menu-action="command-registry"></button>
          <button data-menu-action="options"></button>
          <button data-menu-action="theme"></button>
          <button data-menu-action="faq"></button>
        </div>
      </div>
    </div>
    <div class="terminal-wrap">
      <button id="team-scope-trigger" type="button"><span id="team-scope-label">Personal</span></button>
      <div id="team-scope-overlay" class="u-hidden" aria-hidden="true" inert>
        <section id="team-scope-modal">
          <button class="team-scope-close" type="button"></button>
          <div class="sheet-grab gesture-handle" role="button" tabindex="0" aria-label="Close scope selector"></div>
          <div id="team-scope-current"></div>
          <div id="team-scope-status" class="team-scope-status u-hidden" role="status" aria-live="polite"></div>
          <div id="team-scope-list"></div>
        </section>
      </div>
      <div id="team-scope-announcer" class="team-scope-announcer" role="status" aria-live="polite" aria-atomic="true"></div>
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
    <div id="command-registry-overlay" class="u-hidden">
      <div id="command-registry-modal">
        <span id="command-registry-title"></span>
        <div id="command-registry-subtitle"></div>
        <button class="command-registry-close"></button>
        <input id="command-registry-search" />
        <button id="command-registry-categories-scroll-left" class="tabs-scroll-btn u-hidden"></button>
        <div id="command-registry-categories"></div>
        <button id="command-registry-categories-scroll-right" class="tabs-scroll-btn u-hidden"></button>
        <div id="command-registry-body"></div>
      </div>
    </div>
    <div id="command-catalog-overlay" class="u-hidden">
      <div id="command-catalog-modal">
        <span id="command-catalog-title"></span>
        <button class="command-catalog-close"></button>
        <div id="command-catalog-body"></div>
      </div>
    </div>
    <div id="project-workspace-overlay" class="u-hidden">
      <div id="project-workspace-modal">
        <button class="project-workspace-close"></button>
      </div>
    </div>
    <div id="atlas-import-overlay" class="u-hidden">
      <form id="atlas-import-modal">
        <button id="atlas-import-close" type="button"></button>
      </form>
    </div>
    <div id="project-target-editor-overlay" class="u-hidden">
      <div id="project-target-editor-modal">
        <button class="project-target-editor-close"></button>
      </div>
    </div>
    <div id="project-package-manifest-overlay" class="u-hidden">
      <div id="project-package-manifest-modal">
        <button class="project-package-manifest-close"></button>
        <div id="project-package-manifest-summary"></div>
        <pre id="project-package-manifest-json"></pre>
      </div>
    </div>
    <div id="project-package-wizard-overlay" class="u-hidden">
      <div id="project-package-wizard-modal">
        <button class="project-package-wizard-close"></button>
      </div>
    </div>
    <div id="project-entity-editor-overlay" class="u-hidden">
      <div id="project-entity-editor-modal">
        <button class="project-entity-editor-close"></button>
      </div>
    </div>
    <div id="finding-triage-overlay" class="u-hidden">
      <div id="finding-triage-modal">
        <button id="finding-triage-close"></button>
      </div>
    </div>
    <div id="schedules-overlay" class="u-hidden">
      <div id="schedules-modal">
        <button class="schedules-close"></button>
      </div>
    </div>
    <div id="watchers-overlay" class="u-hidden">
      <div id="watchers-modal">
        <button class="watchers-close"></button>
      </div>
    </div>
    <div id="theme-overlay"></div>
    <button class="theme-close"></button>
    <div id="theme-modal"></div>
    <div id="theme-select" tabindex="-1"></div>
    <div id="options-overlay">
      <button class="options-close"></button>
      <div id="options-modal">
        <div id="options-tabs" role="tablist">
          <button id="options-tab-preferences" data-options-tab="preferences" class="is-active" role="tab" aria-selected="true" aria-controls="options-panel-preferences">Preferences</button>
          <button id="options-tab-secrets" data-options-tab="secrets" role="tab" aria-selected="false" aria-controls="options-panel-secrets">Secrets</button>
          <button id="options-tab-teams" data-options-tab="teams" role="tab" aria-selected="false" aria-controls="options-panel-teams">Teams</button>
          <button id="options-tab-notifications" data-options-tab="notifications" role="tab" aria-selected="false" aria-controls="options-panel-notifications">Notifications</button>
        </div>
        <div id="options-panel-preferences" data-options-panel="preferences" role="tabpanel" aria-labelledby="options-tab-preferences">
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
          <label class="options-desktop-only">
            <input id="options-notify-toggle" type="checkbox" />
          </label>
          <input id="options-command-outcome-summaries-toggle" type="checkbox" />
          <input id="options-project-auto-link-external-runs-toggle" type="checkbox" />
          <input id="options-project-auto-link-run-entities-toggle" type="checkbox" />
          <label class="options-desktop-only">
            <select id="options-hud-clock-select">
              <option value="utc">utc</option>
              <option value="local">local</option>
            </select>
          </label>
          <select id="options-compare-view-mode-select">
            <option value="auto">auto</option>
            <option value="side_by_side">side_by_side</option>
            <option value="unified">unified</option>
            <option value="changes_only">changes_only</option>
            <option value="findings_only">findings_only</option>
          </select>
          <select id="options-compare-context-select">
            <option value="3">3</option>
            <option value="10">10</option>
            <option value="all">all</option>
          </select>
          <input id="options-prompt-username-input" autocomplete="off" autocapitalize="none" autocorrect="off" spellcheck="false" inputmode="text" aria-label="Prompt name" data-bwignore="true" data-1p-ignore="true" data-lpignore="true" />
          <div id="options-prompt-username-error" class="u-hidden"></div>
          <span id="options-session-token-status"></span>
          <button id="options-session-token-generate-btn"></button>
          <button id="options-session-token-set-btn"></button>
          <button id="options-session-token-rotate-btn"></button>
          <button id="options-session-token-clear-btn"></button>
          <button id="options-session-token-copy-btn"></button>
          <div id="options-session-token-msg"></div>
        </div>
        <div id="options-panel-secrets" data-options-panel="secrets" role="tabpanel" aria-labelledby="options-tab-secrets" hidden>
          <button id="options-provider-status-btn"></button>
          <button id="options-secret-new-btn"></button>
          <button id="options-secrets-refresh-btn"></button>
          <div id="options-secrets-msg"></div>
          <div id="options-secrets-list"></div>
        </div>
        <div id="options-panel-teams" data-options-panel="teams" role="tabpanel" aria-labelledby="options-tab-teams" hidden>
          <button id="options-teams-refresh-btn"></button>
          <button id="options-team-create-btn"></button>
          <button id="options-team-join-btn"></button>
          <button id="options-team-recover-btn"></button>
          <div id="options-teams-msg"></div>
          <div id="options-team-form"></div>
          <div id="options-teams-list" class="options-team-list"></div>
          <div id="options-team-detail"></div>
        </div>
        <div id="options-panel-notifications" data-options-panel="notifications" role="tabpanel" aria-labelledby="options-tab-notifications" hidden>
          <button id="options-notification-refresh-btn"></button>
          <button id="options-notification-new-btn"></button>
          <div id="options-notification-msg"></div>
          <div id="options-notification-list"></div>
        </div>
      </div>
    </div>
    <div id="provider-status-overlay" class="u-hidden" aria-hidden="true">
      <div id="provider-status-modal">
        <button type="button" class="provider-status-close"></button>
        <div id="provider-status-body"></div>
      </div>
    </div>
    <div id="workflows-overlay"></div>
    <button class="workflows-close"></button>
    <button id="workflow-new-btn"></button>
    <button id="rail-workflow-new-btn"></button>
    <div id="workflow-editor-overlay" class="u-hidden" aria-hidden="true">
      <form id="workflow-editor-form">
        <span id="workflow-editor-title"></span>
        <button type="button" class="workflow-editor-close"></button>
        <label data-workflow-field="title">
          <input id="workflow-editor-title-input" />
          <span class="form-error u-hidden"></span>
        </label>
        <input id="workflow-editor-description-input" />
        <button type="button" id="workflow-editor-add-parameter"></button>
        <div id="workflow-editor-parameters"></div>
        <div data-workflow-field="steps">
          <button type="button" id="workflow-editor-add-step"></button>
          <div id="workflow-editor-steps"></div>
          <span class="form-error u-hidden"></span>
        </div>
        <div id="workflow-editor-msg"></div>
        <button type="submit" id="workflow-editor-save-btn"></button>
      </form>
    </div>
      <div id="shell-input-row" data-mobile-label="$">
        <input id="cmd" autocomplete="new-password" autocapitalize="none" autocorrect="off" spellcheck="false" inputmode="none" />
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
  for (const [key, value] of Object.entries(localStorageEntries || {})) {
    storage.setItem(key, value)
  }
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
              project_source: 'https://gitlab.com/darklab.sh/darklab_shell',
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
      if (url === '/commands/catalog') {
        return Promise.resolve({
          json: () => Promise.resolve({ restricted: false, commands: [], groups: [] }),
        })
      }
      if (url === '/faq') {
        return Promise.resolve({ json: () => Promise.resolve({ items: [] }) })
      }
      if (url === '/session/secrets') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ secrets: [] }) })
      }
      if (url === '/session/teams') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ teams: [] }) })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })

  const runSearch = vi.fn()
  const clearSearch = vi.fn()
  const navigateSearch = vi.fn()
  const logClientError = vi.fn()
  const openAtlasQuickLookupFromSurface = openAtlasQuickLookupFromSurfaceOverride || vi.fn(
    source => openAtlasQuickLookupOverride({ source, toggle: true }),
  )
  const appendLine = vi.fn()
  const appendCommandEcho = vi.fn()
  const setStatus = vi.fn()
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
    optionsTabs: document.getElementById('options-tabs'),
    optionsTsSelect: document.getElementById('options-ts-select'),
    optionsLnToggle: document.getElementById('options-ln-toggle'),
    optionsWelcomeSelect: document.getElementById('options-welcome-select'),
    optionsShareRedactionSelect: document.getElementById('options-share-redaction-select'),
    optionsNotifyToggle: document.getElementById('options-notify-toggle'),
    optionsCommandOutcomeSummariesToggle: document.getElementById('options-command-outcome-summaries-toggle'),
    optionsProjectAutoLinkExternalRunsToggle: document.getElementById('options-project-auto-link-external-runs-toggle'),
    optionsProjectAutoLinkRunEntitiesToggle: document.getElementById('options-project-auto-link-run-entities-toggle'),
    optionsHudClockSelect: document.getElementById('options-hud-clock-select'),
    optionsCompareViewModeSelect: document.getElementById('options-compare-view-mode-select'),
    optionsCompareContextSelect: document.getElementById('options-compare-context-select'),
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
    commandRegistryOverlay: document.getElementById('command-registry-overlay'),
    commandRegistryBody: document.getElementById('command-registry-body'),
    commandRegistrySearch: document.getElementById('command-registry-search'),
    commandRegistryCategories: document.getElementById('command-registry-categories'),
    commandRegistrySubtitle: document.getElementById('command-registry-subtitle'),
    commandRegistryCloseBtn: document.querySelector('.command-registry-close'),
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
  const originalDocumentActiveElement = Object.getOwnPropertyDescriptor(document, 'activeElement')
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
  window.APP_CONFIG = appConfig
  window.DarklabConfig = {
    getAppConfig: () => appConfig,
    setAppConfig: (config) => {
      if (config === appConfig) {
        window.APP_CONFIG = appConfig
        return appConfig
      }
      Object.keys(appConfig).forEach((key) => {
        delete appConfig[key]
      })
      Object.assign(appConfig, config && typeof config === 'object' && !Array.isArray(config) ? config : {})
      window.APP_CONFIG = appConfig
      return appConfig
    },
  }

  class FakeAnsiUp {
    constructor() {
      this.use_classes = false
    }

    ansi_to_html(text) {
      return text
    }
  }

  const setAutocompleteCatalog = vi.fn((data = {}) => {
    const suggestions = Array.isArray(data.suggestions) ? data.suggestions : []
    const contextRegistry = data.contexts && typeof data.contexts === 'object' && !Array.isArray(data.contexts)
      ? data.contexts
      : {}
    window.acSuggestions = suggestions
    window.acContextRegistry = contextRegistry
    if (window.APP_STATE_API && typeof window.APP_STATE_API.getState === 'function') {
      const state = window.APP_STATE_API.getState()
      state.acSuggestions = suggestions
      state.acContextRegistry = contextRegistry
    }
  })

  const fns = fromDomScripts(
    [
      'app/static/js/core/output_core.js',
      'app/static/js/runtime_bridge.js',
      'app/static/js/output_bridge.js',
      'app/static/js/output.js',
      'app/static/js/core/app_preferences_core.js',
      'app/static/js/features/team_scope.js',
      'app/static/js/features/theme/theme.js',
      'app/static/js/features/terminal/composer_prompt_bridge.js',
      'app/static/js/features/preferences/preferences.js',
      'app/static/js/features/preferences/session_token_bridge.js',
      'app/static/js/features/preferences/secrets_bridge.js',
      'app/static/js/features/tabs/share_redaction_bridge.js',
      'app/static/js/ui/overlay_actions_bridge.js',
      'app/static/js/features/mobile/mobile_shell_layout_bridge.js',
      'app/static/js/features/history/history_panel_bridge.js',
      'app/static/js/app.js',
      'app/static/js/features/mobile/mobile_shell_layout.js',
      'app/static/js/features/tabs/tab_session_state.js',
      'app/static/js/features/preferences/secrets_panel.js',
      'app/static/js/features/preferences/teams_panel.js',
      'app/static/js/features/preferences/session_token_controls.js',
      'app/static/js/ui/ui_helpers.js',
      'app/static/js/features/command-registry/command_registry_bridge.js',
      'app/static/js/features/command-registry/faq_helpers.js',
      'app/static/js/features/command-registry/command_registry.js',
      'app/static/js/features/terminal/composer_editing.js',
      'app/static/js/features/terminal/local_commands.js',
      'app/static/js/features/terminal/mobile_composer_keyboard.js',
      'app/static/js/features/workflows/workflows_bridge.js',
      'app/static/js/features/autocomplete/runtime_context.js',
      'app/static/js/features/tour/tour_cli.js',
      'app/static/js/features/workflows/workflow_catalog.js',
      'app/static/js/features/workflows/workflow_executions.js',
      'app/static/js/features/workflows/workflow_editor.js',
      'app/static/js/features/workflows/workflow_parameters.js',
      'app/static/js/features/workflows/workflows.js',
      'app/static/js/features/mobile/mobile_menu_actions.js',
      'app/static/js/features/shortcuts/global_shortcuts.js',
      'app/static/js/features/shortcuts/shortcuts_key_handler.js',
      'app/static/js/controller.js',
      'app/static/js/features/terminal/composer_controller.js',
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
      getSessionId: () => sessionId,
      updateSessionId: updateSessionIdOverride,
      copyTextToClipboard: copyTextToClipboardOverride,
      reloadSessionHistory: reloadSessionHistoryOverride,
      loadRecentValues: loadRecentValuesOverride || vi.fn(() => Promise.resolve(null)),
      flushRecentValues: vi.fn(() => Promise.resolve(null)),
      refreshWorkspaceFileCache: refreshWorkspaceFileCacheOverride || vi.fn(() => Promise.resolve(null)),
      ...(refreshActiveRunsOverride ? { refreshActiveRuns: refreshActiveRunsOverride } : {}),
      ...(refreshActiveProjectContextOverride ? { refreshActiveProjectContext: refreshActiveProjectContextOverride } : {}),
      ...(refreshStatusMonitorOverride ? { refreshStatusMonitor: refreshStatusMonitorOverride } : {}),
      ...(invalidateOptionsSecretsOverride ? { invalidateOptionsSecrets: invalidateOptionsSecretsOverride } : {}),
      _seedLocalStorageStarsToServer: seedLocalStorageStarsToServerOverride,
      hasPendingTerminalConfirm: hasPendingTerminalConfirmOverride,
      cancelPendingTerminalConfirm: cancelPendingTerminalConfirmOverride,
      sessionVariables: sessionVariablesOverride,
      getWorkspaceAutocompleteFileHints: getWorkspaceAutocompleteFileHintsOverride,
      getWorkspaceAutocompleteDirectoryHints: getWorkspaceAutocompleteDirectoryHintsOverride,
      _readProjectTargets: readProjectTargetsOverride,
      _readRecentValues: readRecentValuesOverride,
      ...(getWorkspaceDirectoryEntriesOverride ? { getWorkspaceDirectoryEntries: getWorkspaceDirectoryEntriesOverride } : {}),
      _workspaceCwd: () => (
        typeof workspaceCwdOverride === 'function'
          ? workspaceCwdOverride()
          : workspaceCwdOverride
      ),
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
      refocusComposerAfterAction: vi.fn(() => {
        if (!document.body.classList.contains('mobile-terminal-mode')) cmdInput.focus()
      }),
      navigateSearch,
      searchCaseSensitive: false,
      searchRegexMode: false,
      historyClearContext: vi.fn(() => ({
        deleteUrl: '/history',
        previewUrl: '/history/delete-preview',
        filtered: false,
      })),
      confirmHistAction: vi.fn(),
      executeHistAction: vi.fn(),
      pendingHistAction: null,
      pendingKillTabId,
      acHide: acHideOverride,
      acSuggestions: acSuggestionsOverride,
      acContextRegistry: acContextRegistryOverride,
      setAutocompleteCatalog,
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
      closeWorkspace: closeWorkspaceOverride,
      isWorkspaceOverlayOpen: isWorkspaceOverlayOpenOverride,
      isSchedulesOverlayOpen: isSchedulesOverlayOpenOverride,
      openSchedulesModal: openSchedulesModalOverride,
      closeSchedulesModal: closeSchedulesModalOverride,
      isWatchersOverlayOpen: isWatchersOverlayOpenOverride,
      openWatchersModal: openWatchersModalOverride,
      closeWatchersModal: closeWatchersModalOverride,
      openStatusMonitor: openStatusMonitorOverride,
      closeStatusMonitor: closeStatusMonitorOverride,
      isStatusMonitorOpen: isStatusMonitorOpenOverride,
      openProjectWorkspace: openProjectWorkspaceOverride,
      closeProjectWorkspace: closeProjectWorkspaceOverride,
      isProjectWorkspaceOpen: isProjectWorkspaceOpenOverride,
      cycleProjectWorkspaceTab: cycleProjectWorkspaceTabOverride,
      openAtlas: openAtlasOverride,
      openAtlasQuickLookup: openAtlasQuickLookupOverride,
      openAtlasQuickLookupFromSurface,
      isAtlasOverlayOpen: isAtlasOverlayOpenOverride,
      cycleAtlasTab: cycleAtlasTabOverride,
      isHistoryRunOverlayOpen: isHistoryRunOverlayOpenOverride,
      cycleHistoryRunOverlayTab: cycleHistoryRunOverlayTabOverride,
      openTourModal: openTourModalOverride,
      bindOutsideClickClose: bindOutsideClickCloseOverride,
      bindFocusTrap,
      interruptPromptLine: interruptPromptLineOverride,
      _welcomeActive: welcomeActive,
      _welcomeDone: welcomeDone,
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
      bindMobileSheet: bindMobileSheetOverride,
      ...(NotificationOverride !== undefined ? { Notification: NotificationOverride } : {}),
      setTimeout: setTimeoutOverride,
      clearTimeout: clearTimeoutOverride,
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
    setTabSessionRestoreInProgress,
    _getTabSessionStateKey: () => TAB_SESSION_STATE_KEY,
    confirmHistAction,
    executeHistAction,
    doKill,
    confirmPermalinkRedactionChoice,
    getWelcomeIntroPreference,
    getShareRedactionDefaultPreference,
    getProjectAutoLinkExternalRunsPreference,
    getProjectAutoLinkRunEntitiesPreference,
    getRunNotifyPreference,
    getCommandOutcomeSummariesPreference,
    getHudClockPreference,
    getPromptUsernamePreference,
    getCompareViewModePreference,
    getCompareContextPreference,
    getOptionsModalLastTabPreference,
    getTourSeenVersionPreference,
    getPreference,
    recordTourOpened,
    applyLineNumberPreference,
    applyRunNotifyPreference,
    applyShareRedactionDefaultPreference,
    applyWelcomeIntroPreference,
    applyProjectAutoLinkExternalRunsPreference,
    applyProjectAutoLinkRunEntitiesPreference,
    applyCommandOutcomeSummariesPreference,
    applyCompareViewModePreference,
    applyCompareContextPreference,
    applyProjectAutoLinkExternalRunsPreference,
    applyProjectAutoLinkRunEntitiesPreference,
    applyHudClockPreference,
    applyCompareViewModePreference,
    applyCompareContextPreference,
    applyPromptUsernamePreference,
    DarklabTeamScope,
    openTeamScopeSelector,
    activateOptionsTab,
    cycleOptionsTab,
    syncOptionsControls,
    refreshOptionsSecrets,
    invalidateOptionsSecrets,
    openSecretEditor,
    deleteOptionsSecret,
    handleSecretCommand,
    refreshOptionsTeams: exportedRefreshOptionsTeams,
    _savedThemeName,
    _resolveThemeEntry,
    applyThemeSelection,
    renderThemeSelectionOptions,
    syncThemeSelectionControls,
    handleThemeCommand,
    handleConfigCommand,
    handleTourCommand,
    handleTabShortcut,
    renderWorkflowItems,
    workflowInputSourceOptions,
    renderWorkflowExecutionsSection,
    createWorkflowExecutionController,
    formatWorkflowExecutionElapsed,
    refreshWorkflowExecutions,
    reloadWorkflowCatalog,
    ensureWorkflowCatalogLoaded,
    openWorkflowEditor,
    closeWorkflowEditor,
    payloadFromEditor,
    handleWorkflowTerminalCommand,
    getRuntimeAutocompleteContext,
    getWorkspaceAutocompletePathHints,
    getRuntimeAutocompleteItems,
    openOptions,
    openThemeSelector,
    openFaq,
    activateFaqCommandChip,
    openCommandRegistry,
    getComposerState,
    setComposerState,
    setComposerPromptMode,
    resetComposerState,
    syncShellPrompt,
    _getAcIndex: () => (typeof getAutocompleteState === 'function' ? getAutocompleteState().index : acIndex),
    _getWelcomeBootPending: () => _welcomeBootPending,
    _getTabSessionRestoreInProgress: () => _tabSessionRestoreInProgress,
  }`,
    `APP_STATE_API.setTabs(tabs); APP_STATE_API.setActiveTabId(activeTabId);
     APP_STATE_API.getState().sessionVariables = sessionVariables;
     window.getTabs = getTabs;
     window.setTabs = setTabs;
     window.getTab = getTab;
     window.getActiveTab = getActiveTab;
     window.getActiveTabId = getActiveTabId;
     window.setActiveTabId = setActiveTabId;
     window.setWelcomeState = setWelcomeState;
     window.appendCommandEcho = appendCommandEcho;
     window.setStatus = setStatus;
     window.apiFetch = apiFetch;
     window.logClientError = logClientError;
     window.SESSION_ID = SESSION_ID;
     window.getSessionId = getSessionId;
     window.__darklabRuntimeHandlers = {
       ...(window.__darklabRuntimeHandlers || {}),
       apiFetch: __darklabExtractGlobals.apiFetch,
       getSessionId: __darklabExtractGlobals.getSessionId,
       logClientError: __darklabExtractGlobals.logClientError,
       openStatusMonitor: typeof __darklabExtractGlobals.openStatusMonitor === 'function'
         ? __darklabExtractGlobals.openStatusMonitor
         : null,
       refreshStatusMonitor: typeof __darklabExtractGlobals.refreshStatusMonitor === 'function'
         ? __darklabExtractGlobals.refreshStatusMonitor
         : null,
     };
     window.showConfirm = showConfirm;
     window.showToast = showToast;
     if (typeof bindOutsideClickClose === 'function') window.bindOutsideClickClose = bindOutsideClickClose;
     if (typeof bindFocusTrap === 'function') window.bindFocusTrap = bindFocusTrap;
     window.updateSessionId = updateSessionId;
     window.copyTextToClipboard = copyTextToClipboard;
     window.reloadSessionHistory = reloadSessionHistory;
     window.createTab = createTab;
     window.activateTab = activateTab;
     window.cancelWelcome = cancelWelcome;
     window.getOutput = getOutput;
     window.isActiveTabRunning = () => false;
     window.openStatusMonitor = __darklabExtractGlobals.openStatusMonitor;
     window.closeStatusMonitor = __darklabExtractGlobals.closeStatusMonitor;
     window.isStatusMonitorOpen = __darklabExtractGlobals.isStatusMonitorOpen;
     window.openProjectWorkspace = __darklabExtractGlobals.openProjectWorkspace;
     window.closeProjectWorkspace = __darklabExtractGlobals.closeProjectWorkspace;
     window.isProjectWorkspaceOpen = __darklabExtractGlobals.isProjectWorkspaceOpen;
     window.cycleProjectWorkspaceTab = __darklabExtractGlobals.cycleProjectWorkspaceTab;
     if (typeof openAtlas === 'function') window.openAtlas = openAtlas;
     if (typeof isAtlasOverlayOpen === 'function') window.isAtlasOverlayOpen = isAtlasOverlayOpen;
     if (typeof cycleAtlasTab === 'function') window.cycleAtlasTab = cycleAtlasTab;
     window.openCommandRegistry = openCommandRegistry;
     window.openThemeSelector = openThemeSelector;
     window.openWorkflows = openWorkflows;
     window.openSchedulesModal = __darklabExtractGlobals.openSchedulesModal;
     window.closeSchedulesModal = __darklabExtractGlobals.closeSchedulesModal;
     window.isSchedulesOverlayOpen = __darklabExtractGlobals.isSchedulesOverlayOpen;
     window.openWatchersModal = __darklabExtractGlobals.openWatchersModal;
     window.closeWatchersModal = __darklabExtractGlobals.closeWatchersModal;
     window.isWatchersOverlayOpen = __darklabExtractGlobals.isWatchersOverlayOpen;
     if (typeof openFindingsBoard === 'function') window.openFindingsBoard = openFindingsBoard;
     window.openWorkspace = __darklabExtractGlobals.openWorkspace;
     window.closeWorkspace = __darklabExtractGlobals.closeWorkspace;
     window.isWorkspaceOverlayOpen = __darklabExtractGlobals.isWorkspaceOverlayOpen;
     window.openFaq = openFaq;
     window.openOptions = openOptions;
     if (typeof getComposerInputs === 'function') window.getComposerInputs = getComposerInputs;
     if (typeof getVisibleComposerInput === 'function') window.getVisibleComposerInput = getVisibleComposerInput;
     if (typeof getActiveComposerInput === 'function') window.getActiveComposerInput = getActiveComposerInput;
     if (typeof getComposerValue === 'function') window.getComposerValue = getComposerValue;
     if (typeof setComposerValue === 'function') window.setComposerValue = setComposerValue;
     window.submitVisibleComposerCommand = submitVisibleComposerCommand;
     window.faqBody = faqBody;
     window.commandRegistryOverlay = commandRegistryOverlay;
     window.commandRegistryBody = commandRegistryBody;
     window.commandRegistrySearch = commandRegistrySearch;
     window.commandRegistryCategories = commandRegistryCategories;
     window.commandRegistrySubtitle = commandRegistrySubtitle;
     window.commandCatalogOverlay = commandCatalogOverlay;
     window.commandCatalogBody = commandCatalogBody;
     window._closeMajorOverlays = _closeMajorOverlays;
     window.acShow = acShow;
     window.acHide = acHide;
     window.setAutocompleteCatalog = __darklabExtractGlobals.setAutocompleteCatalog;
     window.getAutocompleteMatches = getAutocompleteMatches;
     if (typeof limitAutocompleteMatchesForDisplay === 'function') window.limitAutocompleteMatchesForDisplay = limitAutocompleteMatchesForDisplay;
     window.openTourModal = openTourModal;
     window.loadRecentValues = loadRecentValues;
     window.flushRecentValues = flushRecentValues;
     window.hydrateCmdHistory = hydrateCmdHistory;
     window.refreshWorkspaceFileCache = refreshWorkspaceFileCache;
     window.refreshWorkspaceFiles = refreshWorkspaceFileCache;
     window.getWorkspaceAutocompleteFileHints = getWorkspaceAutocompleteFileHints;
     window.getWorkspaceAutocompleteDirectoryHints = getWorkspaceAutocompleteDirectoryHints;
     if (typeof getWorkspaceDirectoryEntries === 'function') window.getWorkspaceDirectoryEntries = getWorkspaceDirectoryEntries;
     window._workspaceCwd = _workspaceCwd;
     if (typeof refreshActiveProjectContext === 'function') window.refreshActiveProjectContext = refreshActiveProjectContext;
     if (typeof refreshActiveRuns === 'function') window.refreshActiveRuns = refreshActiveRuns;
     if (typeof refreshStatusMonitor === 'function') window.refreshStatusMonitor = refreshStatusMonitor;
     window._seedLocalStorageStarsToServer = _seedLocalStorageStarsToServer;
     if (typeof bindMobileSheet === 'function') window.bindMobileSheet = bindMobileSheet;`,
  )

  await Promise.resolve()
  await Promise.resolve()

  Object.assign(window, {
    openStatusMonitor: openStatusMonitorOverride,
    closeStatusMonitor: closeStatusMonitorOverride,
    isStatusMonitorOpen: isStatusMonitorOpenOverride,
    openProjectWorkspace: openProjectWorkspaceOverride,
    closeProjectWorkspace: closeProjectWorkspaceOverride,
    isProjectWorkspaceOpen: isProjectWorkspaceOpenOverride,
    cycleProjectWorkspaceTab: cycleProjectWorkspaceTabOverride,
    openAtlas: openAtlasOverride,
    openAtlasQuickLookup: openAtlasQuickLookupOverride,
    openAtlasQuickLookupFromSurface,
    openSchedulesModal: openSchedulesModalOverride,
    closeSchedulesModal: closeSchedulesModalOverride,
    isSchedulesOverlayOpen: isSchedulesOverlayOpenOverride,
    openWatchersModal: openWatchersModalOverride,
    closeWatchersModal: closeWatchersModalOverride,
    isWatchersOverlayOpen: isWatchersOverlayOpenOverride,
    openWorkspace: openWorkspaceOverride,
    closeWorkspace: closeWorkspaceOverride,
    isWorkspaceOverlayOpen: isWorkspaceOverlayOpenOverride,
    _readProjectTargets: readProjectTargetsOverride,
    _readRecentValues: readRecentValuesOverride,
  })

  if (typeof fns.activateFaqCommandChip === 'function') {
    window.activateFaqCommandChip = fns.activateFaqCommandChip
  }

  Object.assign(window, {
    activateOptionsTab: fns.activateOptionsTab,
    cycleOptionsTab: fns.cycleOptionsTab,
    applyLineNumberPreference: fns.applyLineNumberPreference,
    applyProjectAutoLinkExternalRunsPreference: fns.applyProjectAutoLinkExternalRunsPreference,
    applyProjectAutoLinkRunEntitiesPreference: fns.applyProjectAutoLinkRunEntitiesPreference,
    applyCommandOutcomeSummariesPreference: fns.applyCommandOutcomeSummariesPreference,
    applyCompareViewModePreference: fns.applyCompareViewModePreference,
    applyCompareContextPreference: fns.applyCompareContextPreference,
    applyPromptUsernamePreference: fns.applyPromptUsernamePreference,
    setComposerPromptMode: fns.setComposerPromptMode,
    syncShellPrompt: fns.syncShellPrompt,
    applyShareRedactionDefaultPreference: fns.applyShareRedactionDefaultPreference,
    applyWelcomeIntroPreference: fns.applyWelcomeIntroPreference,
    getPreference: fns.getPreference,
    getProjectAutoLinkExternalRunsPreference: fns.getProjectAutoLinkExternalRunsPreference,
    getProjectAutoLinkRunEntitiesPreference: fns.getProjectAutoLinkRunEntitiesPreference,
    getCommandOutcomeSummariesPreference: fns.getCommandOutcomeSummariesPreference,
    getPromptUsernamePreference: fns.getPromptUsernamePreference,
    getCompareViewModePreference: fns.getCompareViewModePreference,
    getCompareContextPreference: fns.getCompareContextPreference,
    getWelcomeIntroPreference: fns.getWelcomeIntroPreference,
    getShareRedactionDefaultPreference: fns.getShareRedactionDefaultPreference,
    syncOptionsControls: fns.syncOptionsControls,
    refreshOptionsTeams: fns.refreshOptionsTeams,
    _savedThemeName: fns._savedThemeName,
    _resolveThemeEntry: fns._resolveThemeEntry,
    applyThemeSelection: fns.applyThemeSelection,
    renderThemeSelectionOptions: fns.renderThemeSelectionOptions,
    syncThemeSelectionControls: fns.syncThemeSelectionControls,
  })

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
    bindOutsideClickClose: bindOutsideClickCloseOverride,
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
    openTourModal: openTourModalOverride,
    openAtlas: openAtlasOverride,
    openAtlasQuickLookup: openAtlasQuickLookupOverride,
    openAtlasQuickLookupFromSurface,
    logClientError,
    appendLine,
    appendCommandEcho,
    setStatus,
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
      if (originalDocumentActiveElement) {
        Object.defineProperty(document, 'activeElement', originalDocumentActiveElement)
      } else {
        delete document.activeElement
      }
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
