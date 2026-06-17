// app/static/js/core/state.js
var APP_STATE_API = (function initSharedState(global) {
  if (global?.APP_STATE_API && typeof global.APP_STATE_API.getState === "function") {
    return global.APP_STATE_API;
  }
  const defaults = {
    tabs: [],
    activeTabId: null,
    acSuggestions: [],
    acContextRegistry: {},
    acWordlists: [],
    acSpecialCommands: [],
    acBuiltinCommandRoots: [],
    sessionVariables: [],
    acFiltered: [],
    acIndex: -1,
    acSuppressInputOnce: false,
    searchMatches: [],
    searchMatchIdx: -1,
    searchCaseSensitive: false,
    searchRegexMode: false,
    searchScope: "text",
    searchDiscoverabilityPrompted: false,
    searchSignalCounts: null,
    cmdHistory: [],
    recentPreviewHistory: [],
    _cmdHistoryNavIndex: -1,
    _cmdHistoryNavDraft: "",
    _suspendCmdHistoryNavReset: false,
    pendingHistAction: null,
    _welcomeActive: false,
    _welcomeDone: false,
    _welcomeTabId: null,
    _welcomeBanner: null,
    _welcomeLiveLine: null,
    _welcomeHintNode: null,
    _welcomeStatusNodes: [],
    _welcomePlan: null,
    _welcomeNextBlockIndex: 0,
    _welcomeSettleRequested: false,
    _welcomePromptAfterSettle: false,
    _welcomeBootPending: true,
    _composerValue: "",
    _composerSelectionStart: 0,
    _composerSelectionEnd: 0,
    _composerActiveInput: "desktop",
    _mobileKeyboardOffsetBaseline: null,
    _mobileViewportClosedHeight: null,
    _mobileKeyboardLastOpenOffset: 0,
    timerInterval: null,
    timerStart: null,
    pendingKillTabId: null
  };
  const state = global.APP_STATE && typeof global.APP_STATE === "object" ? global.APP_STATE : {};
  const cloneDefaultValue = (value) => {
    if (Array.isArray(value)) return value.slice();
    if (value && typeof value === "object") return { ...value };
    return value;
  };
  Object.entries(defaults).forEach(([key, value]) => {
    if (!Object.prototype.hasOwnProperty.call(state, key)) state[key] = cloneDefaultValue(value);
  });
  const getAppState2 = () => state;
  const getComposerState2 = () => ({
    value: state._composerValue,
    selectionStart: state._composerSelectionStart,
    selectionEnd: state._composerSelectionEnd,
    activeInput: state._composerActiveInput
  });
  const setComposerState2 = (next = {}) => {
    if (Object.prototype.hasOwnProperty.call(next, "value")) {
      state._composerValue = String(next.value ?? "");
    }
    if (Object.prototype.hasOwnProperty.call(next, "selectionStart")) {
      state._composerSelectionStart = Math.max(0, Number(next.selectionStart) || 0);
    }
    if (Object.prototype.hasOwnProperty.call(next, "selectionEnd")) {
      state._composerSelectionEnd = Math.max(0, Number(next.selectionEnd) || 0);
    }
    if (Object.prototype.hasOwnProperty.call(next, "activeInput")) {
      state._composerActiveInput = next.activeInput === "mobile" ? "mobile" : "desktop";
    }
    return getComposerState2();
  };
  const resetComposerState = () => {
    state._composerValue = defaults._composerValue;
    state._composerSelectionStart = defaults._composerSelectionStart;
    state._composerSelectionEnd = defaults._composerSelectionEnd;
    state._composerActiveInput = defaults._composerActiveInput;
    return getComposerState2();
  };
  const resetAppState = () => {
    Object.entries(defaults).forEach(([key, value]) => {
      state[key] = cloneDefaultValue(value);
    });
    return state;
  };
  const getTabs2 = () => state.tabs;
  const setTabs2 = (v) => {
    state.tabs = v;
  };
  const getActiveTabId2 = () => state.activeTabId;
  const setActiveTabId2 = (v) => {
    state.activeTabId = v;
  };
  const getActiveTab2 = () => state.tabs.find((t) => t.id === state.activeTabId);
  const getTab2 = (id) => state.tabs.find((t) => t.id === id);
  const getAutocompleteState2 = () => ({
    filtered: state.acFiltered,
    index: state.acIndex,
    suppressInputOnce: state.acSuppressInputOnce
  });
  const setAutocompleteState2 = (next = {}) => {
    if (Object.prototype.hasOwnProperty.call(next, "filtered")) {
      state.acFiltered = Array.isArray(next.filtered) ? next.filtered : [];
    }
    if (Object.prototype.hasOwnProperty.call(next, "index")) {
      state.acIndex = Number.isFinite(Number(next.index)) ? Number(next.index) : -1;
    }
    if (Object.prototype.hasOwnProperty.call(next, "suppressInputOnce")) {
      state.acSuppressInputOnce = !!next.suppressInputOnce;
    }
    return getAutocompleteState2();
  };
  const getWelcomeState2 = () => ({
    active: state._welcomeActive,
    done: state._welcomeDone,
    tabId: state._welcomeTabId,
    settleRequested: state._welcomeSettleRequested,
    promptAfterSettle: state._welcomePromptAfterSettle,
    bootPending: state._welcomeBootPending
  });
  const setWelcomeState2 = (next = {}) => {
    if (Object.prototype.hasOwnProperty.call(next, "active")) {
      state._welcomeActive = !!next.active;
    }
    if (Object.prototype.hasOwnProperty.call(next, "done")) {
      state._welcomeDone = !!next.done;
    }
    if (Object.prototype.hasOwnProperty.call(next, "tabId")) {
      state._welcomeTabId = next.tabId == null ? null : String(next.tabId);
    }
    if (Object.prototype.hasOwnProperty.call(next, "settleRequested")) {
      state._welcomeSettleRequested = !!next.settleRequested;
    }
    if (Object.prototype.hasOwnProperty.call(next, "promptAfterSettle")) {
      state._welcomePromptAfterSettle = !!next.promptAfterSettle;
    }
    if (Object.prototype.hasOwnProperty.call(next, "bootPending")) {
      state._welcomeBootPending = !!next.bootPending;
    }
    return getWelcomeState2();
  };
  const api = {
    getState: getAppState2,
    reset: resetAppState,
    getTabs: getTabs2,
    setTabs: setTabs2,
    getActiveTabId: getActiveTabId2,
    setActiveTabId: setActiveTabId2,
    getActiveTab: getActiveTab2,
    getTab: getTab2,
    getComposerState: getComposerState2,
    setComposerState: setComposerState2,
    resetComposerState,
    getAutocompleteState: getAutocompleteState2,
    setAutocompleteState: setAutocompleteState2,
    getWelcomeState: getWelcomeState2,
    setWelcomeState: setWelcomeState2
  };
  const emitUiEvent2 = (name, detail = {}) => {
    if (typeof document === "undefined" || typeof document.dispatchEvent !== "function") return false;
    if (typeof document.createEvent === "function") {
      const event = document.createEvent("CustomEvent");
      event.initCustomEvent(name, false, false, detail);
      document.dispatchEvent(event);
      return true;
    }
    const EventCtor = document.defaultView?.CustomEvent || global.CustomEvent || (typeof CustomEvent === "function" ? CustomEvent : null);
    if (!EventCtor) return false;
    document.dispatchEvent(new EventCtor(name, { detail }));
    return true;
  };
  const onUiEvent2 = (name, handler, options) => {
    if (typeof document === "undefined" || typeof document.addEventListener !== "function" || typeof handler !== "function") {
      return () => {
      };
    }
    document.addEventListener(name, handler, options);
    return () => document.removeEventListener(name, handler, options);
  };
  if (global) {
    const publicApi = {
      APP_STATE_API: api,
      APP_STATE: state,
      getAppState: api.getState,
      resetAppState: api.reset,
      getTabs: api.getTabs,
      setTabs: api.setTabs,
      getActiveTabId: api.getActiveTabId,
      setActiveTabId: api.setActiveTabId,
      getActiveTab: api.getActiveTab,
      getTab: api.getTab,
      getComposerState: api.getComposerState,
      setComposerState: api.setComposerState,
      resetComposerState: api.resetComposerState,
      getAutocompleteState: api.getAutocompleteState,
      setAutocompleteState: api.setAutocompleteState,
      getWelcomeState: api.getWelcomeState,
      setWelcomeState: api.setWelcomeState,
      emitUiEvent: emitUiEvent2,
      onUiEvent: onUiEvent2
    };
    Object.assign(global, publicApi);
    if (typeof window !== "undefined" && window !== global) {
      Object.assign(window, publicApi);
    }
  }
  return api;
})(globalThis);
var getAppState = (...args) => APP_STATE_API.getState(...args);
var getTabs = (...args) => APP_STATE_API.getTabs(...args);
var setTabs = (...args) => APP_STATE_API.setTabs(...args);
var getActiveTabId = (...args) => APP_STATE_API.getActiveTabId(...args);
var setActiveTabId = (...args) => APP_STATE_API.setActiveTabId(...args);
var getActiveTab = (...args) => APP_STATE_API.getActiveTab(...args);
var getTab = (...args) => APP_STATE_API.getTab(...args);
var getComposerState = (...args) => APP_STATE_API.getComposerState(...args);
var setComposerState = (...args) => APP_STATE_API.setComposerState(...args);
var getAutocompleteState = (...args) => APP_STATE_API.getAutocompleteState(...args);
var setAutocompleteState = (...args) => APP_STATE_API.setAutocompleteState(...args);
var getWelcomeState = (...args) => APP_STATE_API.getWelcomeState(...args);
var setWelcomeState = (...args) => APP_STATE_API.setWelcomeState(...args);
var emitUiEvent = (...args) => typeof globalThis.emitUiEvent === "function" ? globalThis.emitUiEvent(...args) : false;
var onUiEvent = (...args) => typeof globalThis.onUiEvent === "function" ? globalThis.onUiEvent(...args) : () => {
};

// app/static/js/core/dom.js
var cmdInput = document.getElementById("cmd");
var runBtn = document.getElementById("run-btn");
var shellPromptWrap = document.getElementById("shell-prompt-wrap");
var shellPromptText = document.getElementById("shell-prompt-text");
var shellInputRow = document.getElementById("shell-input-row");
var terminalWrap = document.querySelector(".terminal-wrap");
var terminalBar = document.querySelector(".terminal-bar");
var hamburgerBtn = document.getElementById("hamburger-btn");
var workflowsCloseBtn = document.querySelector(".workflows-close");
var faqCloseBtn = document.querySelector(".faq-close");
var optionsCloseBtn = document.querySelector(".options-close");
var themeCloseBtn = document.querySelector(".theme-close");
var newTabBtn = document.getElementById("new-tab-btn");
var searchToggleBtn = document.getElementById("search-toggle-btn");
var searchSignalSummary = document.getElementById("search-signal-summary");
var searchSummaryBtn = document.getElementById("search-summary-btn");
var historyCloseBtn = document.getElementById("history-close");
var workspaceCloseBtn = document.querySelector(".workspace-close");
var histClearAllBtn = document.getElementById("hist-clear-all-btn");
var tabsScrollLeftBtn = document.getElementById("tabs-scroll-left");
var tabsScrollRightBtn = document.getElementById("tabs-scroll-right");
var searchPrevBtn = document.getElementById("search-prev");
var searchNextBtn = document.getElementById("search-next");
var searchCloseBtn = document.getElementById("search-close-btn");
var optionsTabs = document.getElementById("options-tabs");
var optionsTsSelect = document.getElementById("options-ts-select");
var optionsLnToggle = document.getElementById("options-ln-toggle");
var optionsWelcomeSelect = document.getElementById("options-welcome-select");
var optionsShareRedactionSelect = document.getElementById("options-share-redaction-select");
var optionsNotifyToggle = document.getElementById("options-notify-toggle");
var optionsCommandOutcomeSummariesToggle = document.getElementById("options-command-outcome-summaries-toggle");
var optionsProjectAutoLinkExternalRunsToggle = document.getElementById("options-project-auto-link-external-runs-toggle");
var optionsProjectAutoLinkRunEntitiesToggle = document.getElementById("options-project-auto-link-run-entities-toggle");
var optionsHudClockSelect = document.getElementById("options-hud-clock-select");
var optionsCompareViewModeSelect = document.getElementById("options-compare-view-mode-select");
var optionsCompareContextSelect = document.getElementById("options-compare-context-select");
var optionsPromptUsernameInput = document.getElementById("options-prompt-username-input");
var optionsPromptUsernameError = document.getElementById("options-prompt-username-error");
var themeSelect = document.getElementById("theme-select");
var tsBtn = document.getElementById("ts-btn");
var lnBtn = document.getElementById("ln-btn");
var headerTitle = document.getElementById("header-title");
var mobileHeaderActions = document.getElementById("mobile-header-actions");
var faqBody = document.querySelector(".faq-body");
var status = document.getElementById("status");
var histRow = document.getElementById("history-row");
var tabsBar = document.getElementById("tabs-bar");
var tabbarChrome = document.getElementById("tabbar-chrome");
var tabbarChromeToggle = document.getElementById("tabbar-chrome-toggle");
var tabPanels = document.getElementById("tab-panels");
var mobileShell = document.getElementById("mobile-shell");
var mobileShellChrome = document.getElementById("mobile-shell-chrome");
var mobileShellTranscript = document.getElementById("mobile-shell-transcript");
var mobileShellOverlays = document.getElementById("mobile-shell-overlays");
var mobileComposerHost = document.getElementById("mobile-composer-host");
var mobileComposerRow = document.getElementById("mobile-composer-row");
var mobileCmdInput = document.getElementById("mobile-cmd");
var mobileRunBtn = document.getElementById("mobile-run-btn");
var mobileMenu = document.getElementById("mobile-menu-sheet");
var searchBar = document.getElementById("search-bar");
var searchInput = document.getElementById("search-input");
var searchCount = document.getElementById("search-count");
var searchScopeButtons = Array.from(document.querySelectorAll("[data-search-scope]"));
var historyPanel = document.getElementById("history-panel");
var workspaceOverlay = document.getElementById("workspace-overlay");
var workspaceModal = document.getElementById("workspace-modal");
var workspaceSummary = document.getElementById("workspace-summary");
var workspaceMessage = document.getElementById("workspace-message");
var workspaceBreadcrumbs = document.getElementById("workspace-breadcrumbs");
var workspaceFileList = document.getElementById("workspace-file-list");
var workspaceViewerOverlay = document.getElementById("workspace-viewer-overlay");
var workspaceViewer = document.getElementById("workspace-viewer");
var workspaceViewerTitle = document.getElementById("workspace-viewer-title");
var workspaceViewerControls = document.getElementById("workspace-viewer-controls");
var workspaceViewerText = document.getElementById("workspace-viewer-text");
var workspaceViewerRefreshBtn = document.getElementById("workspace-viewer-refresh-btn");
var workspaceViewerAutoRefreshToggle = document.getElementById("workspace-viewer-auto-refresh-toggle");
var workspaceViewerAutoRefreshLabel = document.getElementById("workspace-viewer-auto-refresh-label");
var workspaceEditorOverlay = document.getElementById("workspace-editor-overlay");
var workspaceEditor = document.getElementById("workspace-editor");
var workspaceEditorTitle = document.getElementById("workspace-editor-title");
var workspacePathInput = document.getElementById("workspace-path-input");
var workspaceLabelsInput = document.getElementById("workspace-labels-input");
var workspaceNotesInput = document.getElementById("workspace-notes-input");
var workspaceTextInput = document.getElementById("workspace-text-input");
var workspaceRefreshBtn = document.getElementById("workspace-refresh-btn");
var workspaceNewBtn = document.getElementById("workspace-new-btn");
var workspaceNewFolderBtn = document.getElementById("workspace-new-folder-btn");
var workspaceSaveBtn = document.getElementById("workspace-save-btn");
var workspaceCancelEditBtn = document.getElementById("workspace-cancel-edit-btn");
var workspaceCloseViewerBtn = document.getElementById("workspace-close-viewer-btn");
var historyList = document.getElementById("history-list");
var historyBulkToolbar = document.getElementById("history-bulk-toolbar");
var historyLoadOverlay = document.getElementById("history-load-overlay");
var historySearchInput = document.getElementById("history-search-input");
var historyMobileFiltersToggle = document.getElementById("history-mobile-filters-toggle");
var historyTypeFilter = document.getElementById("history-type-filter");
var historyRootInput = document.getElementById("history-root-input");
var historyRootDropdown = document.getElementById("history-root-dropdown");
var historySignalFilter = document.getElementById("history-signal-filter");
var historyKindFilter = document.getElementById("history-kind-filter");
var historyEntityInput = document.getElementById("history-entity-input");
var historyEntityTypeFilter = document.getElementById("history-entity-type-filter");
var historyExitFilter = document.getElementById("history-exit-filter");
var historyDateFilter = document.getElementById("history-date-filter");
var historyProjectFilter = document.getElementById("history-project-filter");
var historyStarredToggle = document.getElementById("history-starred-toggle");
var historyClearFiltersBtn = document.getElementById("history-clear-filters");
var historyActiveFilters = document.getElementById("history-active-filters");
var historyPagination = document.getElementById("history-pagination");
var historyPaginationSummary = document.getElementById("history-pagination-summary");
var historyPaginationControls = document.getElementById("history-pagination-controls");
var acDropdown = document.getElementById("ac-dropdown");
var histSearchDropdown = document.getElementById("hist-search-dropdown");
var workflowsOverlay = document.getElementById("workflows-overlay");
var faqOverlay = document.getElementById("faq-overlay");
var commandRegistryOverlay = document.getElementById("command-registry-overlay");
var commandRegistryBody = document.getElementById("command-registry-body");
var commandRegistrySearch = document.getElementById("command-registry-search");
var commandRegistryCategories = document.getElementById("command-registry-categories");
var commandRegistrySubtitle = document.getElementById("command-registry-subtitle");
var commandRegistryCloseBtn = document.querySelector(".command-registry-close");
var commandCatalogOverlay = document.getElementById("command-catalog-overlay");
var commandCatalogBody = document.getElementById("command-catalog-body");
var commandCatalogCloseBtn = document.querySelector(".command-catalog-close");
var shortcutsOverlay = document.getElementById("shortcuts-overlay");
var themeOverlay = document.getElementById("theme-overlay");
var optionsOverlay = document.getElementById("options-overlay");
var permalinkToast = document.getElementById("permalink-toast");
var runTimer = document.getElementById("run-timer");
var searchCaseBtn = document.getElementById("search-case-btn");
var searchRegexBtn = document.getElementById("search-regex-btn");

// app/static/js/features/history/history_panel_bridge.js
var HISTORY_PANEL_BRIDGE_GLOBAL = typeof window !== "undefined" ? window : globalThis;
var historyPanelHandlers = HISTORY_PANEL_BRIDGE_GLOBAL.__darklabHistoryPanelHandlers || {
  openHistoryWithFilters: null,
  refreshHistoryPanel: null,
  renderHistory: null,
  resetHistoryMobileFilters: null,
  resetHistorySelectionOnClose: null
};
HISTORY_PANEL_BRIDGE_GLOBAL.__darklabHistoryPanelHandlers = historyPanelHandlers;
function setHistoryPanelHandlers(handlers = {}) {
  Object.keys(historyPanelHandlers).forEach((name) => {
    if (typeof handlers[name] === "function" && typeof historyPanelHandlers[name] !== "function") {
      historyPanelHandlers[name] = handlers[name];
    }
  });
}
function hasHistoryPanelHandler(name) {
  return typeof historyPanelHandlers[name] === "function";
}
function openHistoryWithFilters(...args) {
  return typeof historyPanelHandlers.openHistoryWithFilters === "function" ? historyPanelHandlers.openHistoryWithFilters(...args) : void 0;
}
function refreshHistoryPanel(...args) {
  return typeof historyPanelHandlers.refreshHistoryPanel === "function" ? historyPanelHandlers.refreshHistoryPanel(...args) : void 0;
}
function renderHistory(...args) {
  return typeof historyPanelHandlers.renderHistory === "function" ? historyPanelHandlers.renderHistory(...args) : void 0;
}
function resetHistoryMobileFilters(...args) {
  return typeof historyPanelHandlers.resetHistoryMobileFilters === "function" ? historyPanelHandlers.resetHistoryMobileFilters(...args) : void 0;
}
function resetHistorySelectionOnClose(...args) {
  return typeof historyPanelHandlers.resetHistorySelectionOnClose === "function" ? historyPanelHandlers.resetHistorySelectionOnClose(...args) : void 0;
}

// app/static/js/features/terminal/composer_prompt_bridge.js
var composerPromptHandlers = {
  getComposerPromptMode: null,
  hidePromptUsernameSavedIndicator: null,
  setComposerPromptMode: null,
  showPromptUsernameSavedIndicator: null,
  syncShellPrompt: null
};
function setComposerPromptHandlers(handlers = {}) {
  Object.keys(composerPromptHandlers).forEach((name) => {
    if (typeof handlers[name] === "function") composerPromptHandlers[name] = handlers[name];
  });
}
function hasComposerPromptHandler(name) {
  return typeof composerPromptHandlers[name] === "function";
}
function getComposerPromptMode() {
  return typeof composerPromptHandlers.getComposerPromptMode === "function" ? composerPromptHandlers.getComposerPromptMode() : null;
}
function hidePromptUsernameSavedIndicator(...args) {
  return typeof composerPromptHandlers.hidePromptUsernameSavedIndicator === "function" ? composerPromptHandlers.hidePromptUsernameSavedIndicator(...args) : void 0;
}
function showPromptUsernameSavedIndicator(...args) {
  return typeof composerPromptHandlers.showPromptUsernameSavedIndicator === "function" ? composerPromptHandlers.showPromptUsernameSavedIndicator(...args) : void 0;
}
function setComposerPromptMode(...args) {
  return typeof composerPromptHandlers.setComposerPromptMode === "function" ? composerPromptHandlers.setComposerPromptMode(...args) : void 0;
}
function syncShellPrompt(...args) {
  return typeof composerPromptHandlers.syncShellPrompt === "function" ? composerPromptHandlers.syncShellPrompt(...args) : void 0;
}

// app/static/js/features/mobile/mobile_shell_layout_bridge.js
var mobileShellLayoutHandlers = {
  dismissMobileKeyboardAfterSubmit: null,
  getMobileKeyboardOffset: null,
  isMobileKeyboardOpen: null,
  syncMobileViewportState: null,
  useMobileTerminalViewportMode: null
};
function setMobileShellLayoutHandlers(handlers = {}) {
  Object.keys(mobileShellLayoutHandlers).forEach((name) => {
    if (typeof handlers[name] === "function") mobileShellLayoutHandlers[name] = handlers[name];
  });
}
function hasMobileShellLayoutHandler(name) {
  return typeof mobileShellLayoutHandlers[name] === "function";
}
function dismissMobileKeyboardAfterSubmit(...args) {
  return typeof mobileShellLayoutHandlers.dismissMobileKeyboardAfterSubmit === "function" ? mobileShellLayoutHandlers.dismissMobileKeyboardAfterSubmit(...args) : void 0;
}
function getMobileKeyboardOffset(...args) {
  return typeof mobileShellLayoutHandlers.getMobileKeyboardOffset === "function" ? mobileShellLayoutHandlers.getMobileKeyboardOffset(...args) : 0;
}
function isMobileKeyboardOpen(...args) {
  return typeof mobileShellLayoutHandlers.isMobileKeyboardOpen === "function" ? !!mobileShellLayoutHandlers.isMobileKeyboardOpen(...args) : false;
}
function syncMobileViewportState(...args) {
  return typeof mobileShellLayoutHandlers.syncMobileViewportState === "function" ? mobileShellLayoutHandlers.syncMobileViewportState(...args) : void 0;
}
function useMobileTerminalViewportMode(...args) {
  return typeof mobileShellLayoutHandlers.useMobileTerminalViewportMode === "function" ? !!mobileShellLayoutHandlers.useMobileTerminalViewportMode(...args) : false;
}

// app/static/js/ui/ui_helpers.js
(function initSharedUiHelpers(global) {
  const uiFn = (name) => {
    const fn = global && global[name];
    return typeof fn === "function" ? fn : null;
  };
  const syncShellPromptFromBridge = () => {
    const syncPrompt = typeof hasComposerPromptHandler === "function" && hasComposerPromptHandler("syncShellPrompt") ? syncShellPrompt : uiFn("syncShellPrompt");
    if (typeof syncPrompt === "function") syncPrompt();
  };
  const useMobileTerminalViewportModeFromBridge = () => {
    if (typeof hasMobileShellLayoutHandler === "function" && hasMobileShellLayoutHandler("useMobileTerminalViewportMode")) {
      return useMobileTerminalViewportMode();
    }
    const useMobile = uiFn("useMobileTerminalViewportMode");
    return !!(useMobile && useMobile());
  };
  const getMobileKeyboardOffsetFromBridge = () => {
    if (typeof hasMobileShellLayoutHandler === "function" && hasMobileShellLayoutHandler("getMobileKeyboardOffset")) {
      return getMobileKeyboardOffset();
    }
    const getOffset = uiFn("getMobileKeyboardOffset");
    return typeof getOffset === "function" ? getOffset() : 0;
  };
  const isMobileKeyboardOpenFromBridge = (offset = null) => {
    if (typeof hasMobileShellLayoutHandler === "function" && hasMobileShellLayoutHandler("isMobileKeyboardOpen")) {
      return isMobileKeyboardOpen(offset);
    }
    const isKeyboardOpen = uiFn("isMobileKeyboardOpen");
    return typeof isKeyboardOpen === "function" ? !!isKeyboardOpen(offset) : false;
  };
  const syncMobileViewportStateFromBridge = () => {
    if (typeof hasMobileShellLayoutHandler === "function" && hasMobileShellLayoutHandler("syncMobileViewportState")) {
      syncMobileViewportState();
      return;
    }
    uiFn("syncMobileViewportState")?.();
  };
  const uiValue = (name) => global ? global[name] : void 0;
  const uiEl = (imported, name) => imported || uiValue(name) || null;
  const emitUi = (name, detail) => {
    const emit = typeof emitUiEvent === "function" && emitUiEvent || uiFn("emitUiEvent");
    if (emit) emit(name, detail);
  };
  const activeTab = () => {
    if (typeof getActiveTab === "function") return getActiveTab();
    const getActive = uiFn("getActiveTab");
    return getActive ? getActive() : null;
  };
  const activeTabId = () => {
    if (typeof getActiveTabId === "function") return getActiveTabId();
    const getActiveId = uiFn("getActiveTabId");
    return getActiveId ? getActiveId() : uiValue("activeTabId") || null;
  };
  const setComposerStateValue = (next) => {
    const setComposer = typeof setComposerState === "function" && setComposerState || uiFn("setComposerState");
    return setComposer ? setComposer(next) : null;
  };
  const readAppState = typeof getAppState !== "undefined" && getAppState || uiFn("getAppState");
  const readComposerState = typeof getComposerState !== "undefined" && getComposerState || uiFn("getComposerState");
  const state = typeof readAppState === "function" ? readAppState() : {};
  let _mobileKeyboardVisibilityTimer = null;
  const readAutocompleteState = () => {
    const getAutocomplete = typeof getAutocompleteState !== "undefined" && getAutocompleteState || uiFn("getAutocompleteState");
    const apiState = typeof getAutocomplete === "function" ? getAutocomplete() : {};
    return {
      filtered: Array.isArray(apiState.filtered) ? apiState.filtered : [],
      index: apiState.index ?? -1,
      suppressInputOnce: !!apiState.suppressInputOnce
    };
  };
  const writeAutocompleteState = (next = {}) => {
    const setAutocomplete = typeof setAutocompleteState !== "undefined" && setAutocompleteState || uiFn("setAutocompleteState");
    if (typeof setAutocomplete === "function") setAutocomplete(next);
    return readAutocompleteState();
  };
  const getMobileMenuEl = () => uiEl(mobileMenu, "mobileMenu");
  const isMobileTerminalViewportActive = () => !!(useMobileTerminalViewportModeFromBridge() && document.body && document.body.classList && document.body.classList.contains("mobile-terminal-mode"));
  let _setComposerValueInProgress = false;
  const _baseSetComposerState = typeof global.setComposerState === "function" ? global.setComposerState : null;
  function _syncComposerInputsFromState() {
    if (_setComposerValueInProgress || typeof readComposerState !== "function") return;
    const composer = readComposerState();
    if (!composer) return;
    const value = typeof composer.value === "string" ? composer.value : "";
    const start = typeof composer.selectionStart === "number" ? Math.max(0, Math.min(composer.selectionStart, value.length)) : value.length;
    const end = typeof composer.selectionEnd === "number" ? Math.max(0, Math.min(composer.selectionEnd, value.length)) : start;
    const inputs = global.getComposerInputs();
    const target = composer.activeInput === "mobile" ? inputs.mobile : inputs.desktop;
    if (target) {
      if (target.value !== value) target.value = value;
      if (typeof target.setSelectionRange === "function" && (document.activeElement === target || target === global.getVisibleComposerInput())) {
        target.setSelectionRange(start, end);
        _syncComposerCaretVisibility(target, start, end);
      }
    }
    if (typeof global.syncRunButtonDisabled === "function") global.syncRunButtonDisabled();
  }
  if (_baseSetComposerState) {
    const appStateApi = uiValue("APP_STATE_API");
    if (appStateApi) {
      appStateApi.setComposerState = (next) => global.setComposerState(next);
    }
  }
  function _estimateComposerTextWidth(input, text) {
    if (!input || typeof window === "undefined" || typeof window.getComputedStyle !== "function") return 0;
    const style = window.getComputedStyle(input);
    const fontSize = parseFloat(style.fontSize || "16") || 16;
    const rawLetterSpacing = parseFloat(style.letterSpacing || "0");
    const letterSpacing = Number.isFinite(rawLetterSpacing) ? rawLetterSpacing : 0;
    const len = String(text || "").length;
    if (!len) return 0;
    return len * (fontSize * 0.62) + Math.max(0, len - 1) * letterSpacing;
  }
  function _syncComposerCaretVisibility(input, start, end) {
    if (!input || typeof input.scrollLeft !== "number") return;
    if (typeof input.clientWidth !== "number" || input.clientWidth <= 0) return;
    const value = typeof input.value === "string" ? input.value : "";
    const caret = Math.max(0, Math.min(typeof end === "number" ? end : start, value.length));
    const anchor = Math.max(0, Math.min(typeof start === "number" ? start : caret, value.length));
    if (caret === 0 && anchor === 0) {
      input.scrollLeft = 0;
      return;
    }
    const style = typeof window !== "undefined" && typeof window.getComputedStyle === "function" ? window.getComputedStyle(input) : null;
    const paddingLeft = style ? parseFloat(style.paddingLeft || "0") || 0 : 0;
    const paddingRight = style ? parseFloat(style.paddingRight || "0") || 0 : 0;
    const viewport = Math.max(24, input.clientWidth - paddingLeft - paddingRight);
    const caretX = _estimateComposerTextWidth(input, value.slice(0, caret));
    const leftEdge = input.scrollLeft;
    const rightEdge = leftEdge + viewport;
    const gutter = 12;
    if (caretX < leftEdge + gutter) {
      input.scrollLeft = Math.max(0, Math.round(caretX - gutter));
      return;
    }
    if (caretX > rightEdge - gutter) {
      input.scrollLeft = Math.max(0, Math.round(caretX - viewport + gutter));
    }
  }
  const getComposerInputs2 = () => ({
    desktop: uiEl(cmdInput, "cmdInput"),
    mobile: uiEl(mobileCmdInput, "mobileCmdInput")
  });
  const getVisibleComposerInput2 = () => {
    const { desktop, mobile } = getComposerInputs2();
    const mobileShellActive = !!(typeof document !== "undefined" && document.body && document.body.classList && document.body.classList.contains("mobile-terminal-mode"));
    if (mobileShellActive && mobile) return mobile;
    return desktop;
  };
  const getActiveComposerInput2 = () => {
    const { desktop, mobile } = getComposerInputs2();
    const visible = getVisibleComposerInput2();
    if (visible) return visible;
    const composer = typeof readComposerState === "function" ? readComposerState() : null;
    if (composer?.activeInput === "mobile" && mobile) return mobile;
    if (composer?.activeInput === "desktop" && desktop) return desktop;
    return desktop || mobile || null;
  };
  const getComposerValue2 = () => {
    if (typeof readComposerState === "function") {
      const composer = readComposerState();
      if (composer && typeof composer.value === "string") return composer.value;
    }
    const input = getVisibleComposerInput2();
    return input ? input.value : "";
  };
  const applyMobileTextInputDefaults2 = (input) => {
    if (!input || typeof input.setAttribute !== "function") return;
    input.setAttribute("autocomplete", "off");
    input.setAttribute("autocapitalize", "none");
    input.setAttribute("autocorrect", "off");
    input.setAttribute("spellcheck", "false");
    input.setAttribute("inputmode", "text");
  };
  const normalizeComposerSmartPeriod = (sourceInput) => {
    if (!sourceInput || typeof sourceInput.value !== "string") return false;
    const composer = typeof readComposerState === "function" ? readComposerState() : null;
    if (!composer || typeof composer.value !== "string") return false;
    const prevValue = composer.value;
    const prevStart = typeof composer.selectionStart === "number" ? composer.selectionStart : prevValue.length;
    const prevEnd = typeof composer.selectionEnd === "number" ? composer.selectionEnd : prevStart;
    if (prevStart !== prevEnd || prevStart < 1 || prevValue[prevStart - 1] !== " ") return false;
    const smartPeriodValue = `${prevValue.slice(0, prevStart - 1)}. ${prevValue.slice(prevStart)}`;
    if (sourceInput.value !== smartPeriodValue) return false;
    const normalizedValue = `${prevValue.slice(0, prevStart)} ${prevValue.slice(prevStart)}`;
    const nextCaret = prevStart + 1;
    sourceInput.value = normalizedValue;
    if (typeof sourceInput.setSelectionRange === "function") {
      sourceInput.setSelectionRange(nextCaret, nextCaret);
    }
    return true;
  };
  const focusElement2 = (el, { preventScroll = false } = {}) => {
    if (!el || typeof el.focus !== "function") return false;
    try {
      if (preventScroll) el.focus({ preventScroll: true });
      else el.focus();
    } catch (_) {
      el.focus();
    }
    return true;
  };
  const blurActiveElement2 = () => {
    if (typeof document === "undefined") return false;
    const active = document.activeElement;
    if (!active || typeof active.blur !== "function") return false;
    active.blur();
    return true;
  };
  const focusComposerInput2 = (input = null, { preventScroll = false } = {}) => {
    const target = input || getVisibleComposerInput2();
    return focusElement2(target, { preventScroll });
  };
  const focusVisibleComposerInput2 = ({ preventScroll = false } = {}) => {
    if (isMobileTerminalViewportActive()) return false;
    return focusComposerInput2(getVisibleComposerInput2(), { preventScroll });
  };
  const getMobileKeyboardOffsetBaseline2 = () => state._mobileKeyboardOffsetBaseline;
  const getMobileViewportClosedHeight2 = () => state._mobileViewportClosedHeight;
  const setMobileViewportClosedHeight = (value) => {
    state._mobileViewportClosedHeight = typeof value === "number" ? value : null;
    return state._mobileViewportClosedHeight;
  };
  const blurVisibleComposerInput2 = () => {
    const target = getVisibleComposerInput2();
    if (!target || typeof target.blur !== "function") return false;
    target.blur();
    return true;
  };
  const blurVisibleComposerInputIfMobile2 = () => {
    if (!useMobileTerminalViewportModeFromBridge()) return false;
    return blurVisibleComposerInput2();
  };
  const focusAnyComposerInput2 = ({ preventScroll = false } = {}) => focusVisibleComposerInput2({ preventScroll });
  const syncMobileComposerKeyboardState2 = (offset = null, { active = true, open = null } = {}) => {
    if (typeof document === "undefined" || !document.body || !document.body.classList) return false;
    const requestedOffset = typeof offset === "number" ? offset : 0;
    const requestedOpen = typeof open === "boolean" ? open : document.body.classList.contains("mobile-keyboard-open");
    const lastOpenOffset = state._mobileKeyboardLastOpenOffset || 0;
    const nextOffset = requestedOpen && requestedOffset <= 0 && lastOpenOffset > 0 ? lastOpenOffset : requestedOffset;
    document.documentElement?.style?.setProperty("--mobile-keyboard-offset", `${nextOffset}px`);
    if (!active) {
      state._mobileKeyboardOffsetBaseline = nextOffset;
      if (_mobileKeyboardVisibilityTimer) {
        clearTimeout(_mobileKeyboardVisibilityTimer);
        _mobileKeyboardVisibilityTimer = null;
      }
      document.body.classList.remove("mobile-keyboard-open");
      emitUi("app:mobile-keyboard-state", { open: false });
      return false;
    }
    if (typeof state._mobileKeyboardOffsetBaseline !== "number") {
      state._mobileKeyboardOffsetBaseline = nextOffset;
    }
    const nextOpen = requestedOpen;
    if (nextOpen && nextOffset > 0) state._mobileKeyboardLastOpenOffset = nextOffset;
    if (!nextOpen) state._mobileKeyboardOffsetBaseline = nextOffset;
    document.body.classList.toggle("mobile-keyboard-open", nextOpen);
    emitUi("app:mobile-keyboard-state", { open: !!nextOpen });
    return nextOpen;
  };
  const setMobileKeyboardOpenState = (open, { delay = 0 } = {}) => {
    if (typeof document === "undefined" || !document.body || !document.body.classList) return false;
    if (_mobileKeyboardVisibilityTimer) {
      clearTimeout(_mobileKeyboardVisibilityTimer);
      _mobileKeyboardVisibilityTimer = null;
    }
    const applyOpen = () => {
      const wasKeyboardOpen = document.body.classList.contains("mobile-keyboard-open");
      document.body.classList.toggle("mobile-keyboard-open", !!open);
      if (open && !wasKeyboardOpen) {
        const hideMobile = uiFn("hideMobileMenu") || hideMobileMenu2;
        const isHistoryOpen = uiFn("isHistoryPanelOpen") || isHistoryPanelOpen2;
        const hideHistory = uiFn("hideHistoryPanel") || hideHistoryPanel2;
        const hideAutocomplete = uiFn("acHide");
        if (hideMobile) hideMobile();
        if (isHistoryOpen && isHistoryOpen() && hideHistory) hideHistory();
        if (hideAutocomplete) hideAutocomplete();
      }
      emitUi("app:mobile-keyboard-state", { open: !!open });
      return !!open;
    };
    if (open) return applyOpen();
    const closeDelay = Math.max(0, Number(delay) || 0);
    if (closeDelay === 0) return applyOpen();
    _mobileKeyboardVisibilityTimer = setTimeout(() => {
      _mobileKeyboardVisibilityTimer = null;
      const mobileInput = getVisibleComposerInput2();
      const keyboardStillOpen = !!(mobileInput && document.activeElement === mobileInput && isMobileKeyboardOpenFromBridge(getMobileKeyboardOffsetFromBridge()));
      if (keyboardStillOpen) return;
      document.body.classList.remove("mobile-keyboard-open");
      emitUi("app:mobile-keyboard-state", { open: false });
      if (typeof window !== "undefined" && document.documentElement) {
        const h = window.innerHeight || 0;
        if (h > 0) document.documentElement.style.setProperty("--mobile-viewport-height", `${h}px`);
        syncMobileComposerKeyboardState2(0, { open: false });
      }
    }, closeDelay);
    return false;
  };
  const isActiveTabRunning2 = () => {
    const active = activeTab();
    return !!(active && active.st === "running");
  };
  const setComposerValue2 = (value, start = null, end = null, { dispatch = true, exclude = null, allowDuringRun = false } = {}) => {
    const nextValue = String(value ?? "");
    if (!allowDuringRun && nextValue.trim() && isActiveTabRunning2()) {
      const hideAutocomplete = uiFn("acHide");
      if (hideAutocomplete) hideAutocomplete();
      if (typeof global.syncRunButtonDisabled === "function") global.syncRunButtonDisabled();
      return getComposerValue2();
    }
    const nextStart = typeof start === "number" ? start : nextValue.length;
    const nextEnd = typeof end === "number" ? end : nextStart;
    const target = getActiveComposerInput2();
    if (typeof setComposerStateValue === "function") {
      _setComposerValueInProgress = true;
      try {
        setComposerStateValue({
          value: nextValue,
          selectionStart: nextStart,
          selectionEnd: nextEnd,
          activeInput: typeof document !== "undefined" && document.body && document.body.classList && document.body.classList.contains("mobile-terminal-mode") ? "mobile" : "desktop"
        });
      } finally {
        _setComposerValueInProgress = false;
      }
    }
    if (target && target !== exclude) {
      target.value = nextValue;
      if (typeof target.setSelectionRange === "function") {
        target.setSelectionRange(nextStart, nextEnd);
      }
      _syncComposerCaretVisibility(target, nextStart, nextEnd);
    }
    if (dispatch && target && target !== exclude) {
      target.dispatchEvent(new Event("input"));
    }
    if (typeof global.syncRunButtonDisabled === "function") global.syncRunButtonDisabled();
    return nextValue;
  };
  const syncComposerSelection2 = (start = null, end = null, { input = null } = {}) => {
    const target = input || getActiveComposerInput2();
    const composer = typeof readComposerState === "function" ? readComposerState() : null;
    const value = composer && typeof composer.value === "string" ? composer.value : target && typeof target.value === "string" ? target.value : "";
    const len = value.length;
    const nextStart = typeof start === "number" ? Math.max(0, Math.min(start, len)) : len;
    const nextEnd = typeof end === "number" ? Math.max(0, Math.min(end, len)) : nextStart;
    const orderedStart = Math.min(nextStart, nextEnd);
    const orderedEnd = Math.max(nextStart, nextEnd);
    setComposerStateValue({
      selectionStart: orderedStart,
      selectionEnd: orderedEnd,
      activeInput: typeof document !== "undefined" && document.body && document.body.classList && document.body.classList.contains("mobile-terminal-mode") ? "mobile" : "desktop"
    });
    if (target && typeof target.setSelectionRange === "function") {
      target.setSelectionRange(orderedStart, orderedEnd);
    }
    _syncComposerCaretVisibility(target, orderedStart, orderedEnd);
    return { start: orderedStart, end: orderedEnd };
  };
  const syncFocusedComposerState2 = (input = null) => {
    const target = input || getActiveComposerInput2();
    if (!target || typeof target.value !== "string") return null;
    const value = target.value;
    const start = typeof target.selectionStart === "number" ? target.selectionStart : value.length;
    const end = typeof target.selectionEnd === "number" ? target.selectionEnd : start;
    setComposerStateValue({
      value,
      selectionStart: start,
      selectionEnd: end,
      activeInput: target === getComposerInputs2().mobile ? "mobile" : "desktop"
    });
    return { value, start, end, input: target };
  };
  const handleComposerInputChange2 = (sourceInput) => {
    if (!sourceInput) return;
    const _activeTab = activeTab();
    if (_activeTab && _activeTab.st === "running") {
      sourceInput.value = "";
      setComposerValue2("", 0, 0, { dispatch: false, exclude: sourceInput, allowDuringRun: true });
      uiFn("acHide")?.();
      syncShellPromptFromBridge();
      return;
    }
    normalizeComposerSmartPeriod(sourceInput);
    if (_activeTab) _activeTab.followOutput = true;
    const _out = typeof document !== "undefined" ? document.querySelector(".tab-panel.active .output") : null;
    if (_out) _out.scrollTop = _out.scrollHeight;
    syncShellPromptFromBridge();
    syncMobileViewportStateFromBridge();
    const value = sourceInput.value;
    const start = typeof sourceInput.selectionStart === "number" ? sourceInput.selectionStart : value.length;
    const end = typeof sourceInput.selectionEnd === "number" ? sourceInput.selectionEnd : value.length;
    setComposerValue2(value, start, end, { dispatch: false, exclude: sourceInput });
    if (state && state._suspendCmdHistoryNavReset) state._suspendCmdHistoryNavReset = false;
    else uiFn("resetCmdHistoryNav")?.();
    if (value.length > 0) uiFn("requestWelcomeSettle")?.(activeTabId());
    const autocomplete = readAutocompleteState();
    if (autocomplete.suppressInputOnce) {
      writeAutocompleteState({ suppressInputOnce: false });
      uiFn("acHide")?.();
      return;
    }
    if (uiFn("hasPendingTerminalConfirm")?.()) {
      writeAutocompleteState({ index: -1, filtered: [] });
      uiFn("acHide")?.();
      return;
    }
    writeAutocompleteState({ index: -1 });
    if (!value.trim()) {
      uiFn("acHide")?.();
      return;
    }
    const getMatches = uiFn("getAutocompleteMatches");
    const usedContextMatcher = !!getMatches;
    const contextMatches = usedContextMatcher ? getMatches(value, start) : [];
    const limitMatches = uiFn("limitAutocompleteMatchesForDisplay");
    const suggestions = Array.isArray(uiValue("acSuggestions")) ? uiValue("acSuggestions") : [];
    const filtered = usedContextMatcher ? limitMatches ? limitMatches(contextMatches, 12) : contextMatches.slice(0, 12) : suggestions.filter((s) => s.toLowerCase().startsWith(value.toLowerCase())).slice(0, 12);
    writeAutocompleteState({ filtered });
    if (!filtered.length) {
      uiFn("acHide")?.();
      return;
    }
    if (!usedContextMatcher) {
      const q = value.trim().toLowerCase();
      if (filtered.some((s) => String(s || "").toLowerCase() === q)) {
        uiFn("acHide")?.();
        return;
      }
    }
    uiFn("acShow")?.(filtered);
  };
  function _isVisibleModalOverlay(el) {
    if (!el || !el.classList) return false;
    if (el.id === "history-panel" || el.id === "history-load-overlay") return false;
    const isOverlay = el.classList.contains("modal-overlay") || el.classList.contains("mobile-sheet-overlay") || el.id === "shortcuts-overlay" || el.id === "theme-overlay" || el.classList.contains("status-monitor-scrim");
    if (!isOverlay) return false;
    if (el.classList.contains("u-hidden")) return false;
    return el.classList.contains("open") || el.style && el.style.display && el.style.display !== "none";
  }
  function _syncModalOverlayState() {
    if (!global.document || !global.document.body) return false;
    const overlays = global.document.querySelectorAll(
      ".modal-overlay, .mobile-sheet-overlay, #shortcuts-overlay, #theme-overlay, .status-monitor-scrim"
    );
    const active = Array.prototype.some.call(overlays, _isVisibleModalOverlay);
    global.document.body.classList.toggle("modal-overlay-active", active);
    return active;
  }
  function _doRefocusComposer(preventScroll) {
    const isMobileMode = useMobileTerminalViewportModeFromBridge();
    if (isMobileMode) return false;
    const isConfirmOpen = uiFn("isConfirmOpen");
    if (isConfirmOpen && isConfirmOpen()) return false;
    const focusPty = uiFn("focusActiveInteractivePty");
    if (focusPty && focusPty({ preventScroll })) {
      return true;
    }
    const getVisible = uiFn("getVisibleComposerInput") || global.getVisibleComposerInput;
    const focusComposer = uiFn("focusComposerInput") || global.focusComposerInput;
    const target = getVisible ? getVisible() : null;
    if (target && focusComposer && focusComposer(target, { preventScroll })) {
      return true;
    }
    const focusAny = uiFn("focusAnyComposerInput") || global.focusAnyComposerInput;
    if (focusAny && focusAny({ preventScroll })) return true;
    return false;
  }
  const historyPanelEl = () => uiEl(historyPanel, "historyPanel");
  const workflowsOverlayEl = () => uiEl(workflowsOverlay, "workflowsOverlay");
  const faqOverlayEl = () => uiEl(faqOverlay, "faqOverlay");
  const shortcutsOverlayEl = () => uiEl(shortcutsOverlay, "shortcutsOverlay");
  const themeOverlayEl = () => uiEl(themeOverlay, "themeOverlay");
  const optionsOverlayEl = () => uiEl(optionsOverlay, "optionsOverlay");
  const historyLoadOverlayEl = () => uiEl(historyLoadOverlay, "historyLoadOverlay");
  const searchBarEl = () => uiEl(searchBar, "searchBar");
  const histRowEl = () => uiEl(histRow, "histRow");
  const runTimerEl = () => uiEl(runTimer, "runTimer");
  const runBtnEl = () => uiEl(runBtn, "runBtn");
  const mobileRunBtnEl = () => uiEl(mobileRunBtn, "mobileRunBtn");
  const tabPanelsEl = () => uiEl(tabPanels, "tabPanels");
  const getWorkspaceOverlay = () => uiEl(workspaceOverlay, "workspaceOverlay");
  const refocusComposerAfterAction2 = ({ preventScroll = true, defer = false } = {}) => {
    if (defer) {
      setTimeout(() => {
        _doRefocusComposer(preventScroll);
      }, 0);
      return void 0;
    }
    return _doRefocusComposer(preventScroll);
  };
  const togglePanelOverlay2 = (el, force = null) => {
    if (!el || !el.classList) return false;
    const next = force === null ? !el.classList.contains("open") : !!force;
    el.classList.toggle("open", next);
    return next;
  };
  const isPanelOverlayOpen2 = (el) => !!(el && el.classList && el.classList.contains("open"));
  const showPanelOverlay2 = (el) => {
    if (el && el.classList) el.classList.add("open");
    if (el && el.dataset) el.dataset.interactionReady = "0";
    _syncModalOverlayState();
  };
  const hidePanelOverlay2 = (el) => {
    if (el && el.classList) el.classList.remove("open");
    if (el && el.dataset) delete el.dataset.interactionReady;
    _syncModalOverlayState();
  };
  const showModalOverlay2 = (el, display = "flex") => {
    if (el && el.style) el.style.display = display;
    _syncModalOverlayState();
  };
  const hideModalOverlay2 = (el) => {
    if (el && el.style) el.style.display = "none";
    _syncModalOverlayState();
  };
  const markInteractionSurfaceReady2 = (surface, overlay, card = null) => {
    if (overlay && overlay.dataset) overlay.dataset.interactionReady = "1";
    if (card && card.dataset) card.dataset.interactionReady = "1";
    emitUi("app:interaction-surface-ready", {
      surface: surface || "",
      overlayId: overlay && overlay.id ? overlay.id : "",
      cardId: card && card.id ? card.id : "",
      activeElementId: document.activeElement && document.activeElement.id ? document.activeElement.id : "",
      focusTrapBound: !!(card && card.dataset && card.dataset.focusTrapBound === "1")
    });
  };
  const showHistoryPanel = () => showPanelOverlay2(historyPanelEl());
  const hideHistoryPanel2 = () => {
    if (typeof hasHistoryPanelHandler === "function" && hasHistoryPanelHandler("resetHistorySelectionOnClose") && typeof resetHistorySelectionOnClose === "function") {
      resetHistorySelectionOnClose();
    } else {
      uiFn("resetHistorySelectionOnClose")?.();
    }
    hidePanelOverlay2(historyPanelEl());
    refocusComposerAfterAction2({ preventScroll: true });
  };
  const isHistoryPanelOpen2 = () => isPanelOverlayOpen2(historyPanelEl());
  const showWorkflowsOverlay2 = () => showPanelOverlay2(workflowsOverlayEl());
  const hideWorkflowsOverlay2 = () => hidePanelOverlay2(workflowsOverlayEl());
  const isWorkflowsOverlayOpen2 = () => isPanelOverlayOpen2(workflowsOverlayEl());
  const showFaqOverlay2 = () => showPanelOverlay2(faqOverlayEl());
  const hideFaqOverlay2 = () => hidePanelOverlay2(faqOverlayEl());
  const isFaqOverlayOpen2 = () => isPanelOverlayOpen2(faqOverlayEl());
  const showShortcutsOverlay2 = () => {
    const el = shortcutsOverlayEl();
    if (el) el.setAttribute("aria-hidden", "false");
    showPanelOverlay2(el);
  };
  const hideShortcutsOverlay2 = () => {
    const el = shortcutsOverlayEl();
    if (el) el.setAttribute("aria-hidden", "true");
    hidePanelOverlay2(el);
  };
  const isShortcutsOverlayOpen2 = () => isPanelOverlayOpen2(shortcutsOverlayEl());
  const showThemeOverlay = () => showPanelOverlay2(themeOverlayEl());
  const hideThemeOverlay2 = () => hidePanelOverlay2(themeOverlayEl());
  const isThemeOverlayOpen2 = () => isPanelOverlayOpen2(themeOverlayEl());
  const showOptionsOverlay = () => showPanelOverlay2(optionsOverlayEl());
  const hideOptionsOverlay2 = () => hidePanelOverlay2(optionsOverlayEl());
  const isOptionsOverlayOpen2 = () => isPanelOverlayOpen2(optionsOverlayEl());
  const showWorkspaceOverlay2 = () => showPanelOverlay2(getWorkspaceOverlay());
  const hideWorkspaceOverlay2 = () => hidePanelOverlay2(getWorkspaceOverlay());
  const isWorkspaceOverlayOpen2 = () => isPanelOverlayOpen2(getWorkspaceOverlay());
  const showHistoryLoadOverlay = () => {
    const el = historyLoadOverlayEl();
    if (el && el.classList) el.classList.add("open");
    if (el) el.setAttribute("aria-hidden", "false");
  };
  const hideHistoryLoadOverlay = () => {
    const el = historyLoadOverlayEl();
    if (el && el.classList) el.classList.remove("open");
    if (el) el.setAttribute("aria-hidden", "true");
  };
  if (searchBarEl() && searchBarEl().style) searchBarEl().style.display = "none";
  const showSearchBar2 = () => {
    const el = searchBarEl();
    if (el && el.style) el.style.display = "flex";
  };
  const hideSearchBar2 = () => {
    const el = searchBarEl();
    if (el && el.style) el.style.display = "none";
    refocusComposerAfterAction2({ preventScroll: true });
  };
  const isSearchBarOpen2 = () => {
    const el = searchBarEl();
    return !!(el && el.style && el.style.display === "flex");
  };
  const showHistoryRow = () => {
    const el = histRowEl();
    if (el && el.style) el.style.display = "flex";
  };
  const hideHistoryRow = () => {
    const el = histRowEl();
    if (el && el.style) el.style.display = "none";
  };
  const showRunTimer = () => {
    const el = runTimerEl();
    if (el && el.style) el.style.display = "inline";
  };
  const hideRunTimer = () => {
    const el = runTimerEl();
    if (el && el.style) el.style.display = "none";
    if (el) el.textContent = "";
  };
  const setRunButtonDisabled = (disabled) => {
    const next = !!disabled;
    const desktop = runBtnEl();
    const mobile = mobileRunBtnEl();
    if (desktop) desktop.disabled = next;
    if (mobile) mobile.disabled = next;
  };
  const syncRunButtonDisabled2 = () => {
    const active = activeTab();
    const composerValue = String(getComposerValue2() || "");
    const disabled = !!(active && active.st === "running") || !composerValue.trim();
    const desktop = runBtnEl();
    const mobile = mobileRunBtnEl();
    if (desktop) desktop.disabled = disabled;
    if (mobile) mobile.disabled = disabled;
    return disabled;
  };
  const isRunButtonDisabled = () => {
    const desktop = runBtnEl();
    const mobile = mobileRunBtnEl();
    return !!(desktop && desktop.disabled || mobile && mobile.disabled);
  };
  const syncTerminalActionLayout = (tabId) => {
    const tabPanels2 = tabPanelsEl();
    const btn = tabPanels2 ? tabPanels2.querySelector(`.tab-kill-btn[data-tab="${tabId}"]`) : null;
    const actions = btn && btn.parentElement && btn.parentElement.classList && btn.parentElement.classList.contains("terminal-actions") ? btn.parentElement : null;
    if (!actions) return;
    const hasVisibleKill = !!(btn.style ? btn.style.display !== "none" : !btn.hidden);
    actions.classList.toggle("terminal-actions-has-visible-kill", hasVisibleKill);
  };
  const showTabKillBtn2 = (tabId) => {
    const tabPanels2 = tabPanelsEl();
    const btn = tabPanels2 ? tabPanels2.querySelector(`.tab-kill-btn[data-tab="${tabId}"]`) : null;
    if (btn) {
      btn.hidden = false;
      if (btn.style) btn.style.display = "inline-block";
    }
    syncTerminalActionLayout(tabId);
    emitUi("app:tab-kill-visibility-changed", { tabId, visible: true });
  };
  const hideTabKillBtn2 = (tabId) => {
    const tabPanels2 = tabPanelsEl();
    const btn = tabPanels2 ? tabPanels2.querySelector(`.tab-kill-btn[data-tab="${tabId}"]`) : null;
    if (btn) {
      btn.hidden = true;
      if (btn.style) btn.style.display = "none";
    }
    syncTerminalActionLayout(tabId);
    emitUi("app:tab-kill-visibility-changed", { tabId, visible: false });
  };
  const showMobileMenu2 = () => {
    const mobileMenu2 = getMobileMenuEl();
    if (mobileMenu2 && mobileMenu2.classList) mobileMenu2.classList.remove("u-hidden");
    emitUi("app:mobile-menu-show");
  };
  const hideMobileMenu2 = () => {
    const mobileMenu2 = getMobileMenuEl();
    if (mobileMenu2 && mobileMenu2.classList) mobileMenu2.classList.add("u-hidden");
    emitUi("app:mobile-menu-hide");
  };
  const isMobileMenuOpen2 = () => {
    const mobileMenu2 = getMobileMenuEl();
    return !!(mobileMenu2 && mobileMenu2.classList && !mobileMenu2.classList.contains("u-hidden"));
  };
  const showAcDropdown2 = () => {
    const el = uiEl(acDropdown, "acDropdown");
    if (!el) return;
    if (el.classList) el.classList.remove("u-hidden");
    if (el.style) el.style.display = "block";
  };
  const hideAcDropdown2 = () => {
    const el = uiEl(acDropdown, "acDropdown");
    if (!el) return;
    if (el.classList) el.classList.add("u-hidden");
    if (el.style) el.style.display = "none";
  };
  const isAcDropdownOpen2 = () => {
    const el = uiEl(acDropdown, "acDropdown");
    return !!(el && el.style && el.style.display !== "none");
  };
  const setVisibilityState2 = (el, hidden, ariaHidden = null) => {
    if (!el) return;
    el.hidden = !!hidden;
    if (typeof el.setAttribute === "function") {
      if (ariaHidden === null || typeof ariaHidden === "undefined") {
        if (typeof el.removeAttribute === "function") el.removeAttribute("aria-hidden");
      } else {
        el.setAttribute("aria-hidden", String(ariaHidden));
      }
    }
  };
  const _appSelects = /* @__PURE__ */ new Map();
  function _viewportBounds() {
    const vv = global.visualViewport;
    if (vv && Number.isFinite(vv.width) && Number.isFinite(vv.height)) {
      return {
        top: Number(vv.offsetTop) || 0,
        left: Number(vv.offsetLeft) || 0,
        width: Number(vv.width) || 0,
        height: Number(vv.height) || 0
      };
    }
    const docEl = document.documentElement || {};
    return {
      top: 0,
      left: 0,
      width: global.innerWidth || docEl.clientWidth || 0,
      height: global.innerHeight || docEl.clientHeight || 0
    };
  }
  function _clampNumber(value, min, max) {
    if (max < min) return min;
    return Math.min(Math.max(value, min), max);
  }
  function _portalAppSelectMenu(wrap, trigger, menu) {
    if (wrap.dataset.portalMenu !== "true") return;
    const rect = trigger.getBoundingClientRect();
    const viewport = _viewportBounds();
    const margin = 8;
    const gap = 0;
    const viewportTop = viewport.top;
    const viewportLeft = viewport.left;
    const viewportBottom = viewport.top + viewport.height;
    const viewportRight = viewport.left + viewport.width;
    const spaceBelow = Math.max(0, viewportBottom - rect.bottom - gap - margin);
    const spaceAbove = Math.max(0, rect.top - viewportTop - gap - margin);
    const desiredHeight = 240;
    const openAbove = spaceBelow < desiredHeight && spaceAbove > spaceBelow;
    const availableHeight = openAbove ? spaceAbove : spaceBelow;
    const maxHeight = Math.min(320, Math.max(48, availableHeight));
    const width = Math.min(rect.width, Math.max(0, viewport.width - margin * 2));
    const left = _clampNumber(rect.left, viewportLeft + margin, viewportRight - width - margin);
    if (menu.dataset.appSelectPortaled !== "true") {
      menu._portalReturnTo = wrap;
      menu.dataset.appSelectPortaled = "true";
      document.body.appendChild(menu);
    }
    menu.style.display = "flex";
    menu.style.flexDirection = "column";
    menu.style.position = "fixed";
    menu.style.bottom = "auto";
    menu.style.right = "auto";
    menu.style.left = left + "px";
    menu.style.width = width + "px";
    menu.style.zIndex = "10000";
    menu.style.maxHeight = maxHeight + "px";
    menu.style.overflowY = "auto";
    const renderedHeight = menu.getBoundingClientRect?.().height || menu.offsetHeight || 0;
    const contentHeight = menu.scrollHeight || renderedHeight || maxHeight;
    const menuHeight = Math.min(maxHeight, Math.max(48, contentHeight));
    const top = openAbove ? Math.max(rect.top - gap - menuHeight, viewportTop + margin) : _clampNumber(rect.bottom + gap, viewportTop + margin, viewportBottom - menuHeight - margin);
    menu.style.top = top + "px";
    menu.classList.toggle("dropdown-up", openAbove);
  }
  function _shouldPortalAppSelect(select) {
    if (!select || typeof select.closest !== "function") return false;
    if (select.dataset.portalMenu === "true") return true;
    return !!select.closest(
      '.mobile-sheet-surface, .bottom-sheet, .modal, [role="dialog"], [aria-modal="true"]'
    );
  }
  function _unportalAppSelectMenu(menu) {
    if (!menu || menu.dataset.appSelectPortaled !== "true") return;
    const returnTo = menu._portalReturnTo;
    delete menu.dataset.appSelectPortaled;
    delete menu._portalReturnTo;
    menu.style.display = "";
    menu.style.flexDirection = "";
    menu.style.position = "";
    menu.style.bottom = "";
    menu.style.right = "";
    menu.style.left = "";
    menu.style.top = "";
    menu.style.width = "";
    menu.style.zIndex = "";
    menu.style.maxHeight = "";
    menu.style.overflowY = "";
    menu.classList.remove("dropdown-up");
    if (returnTo) returnTo.appendChild(menu);
  }
  function _closeAppSelects(exceptWrap = null) {
    _appSelects.forEach(({ wrap, trigger, menu }) => {
      if (wrap === exceptWrap) return;
      if (wrap.classList.contains("open")) _unportalAppSelectMenu(menu);
      wrap.classList.remove("open");
      trigger.setAttribute("aria-expanded", "false");
    });
  }
  function _syncAppSelect(select) {
    const state2 = _appSelects.get(select);
    if (!state2) return;
    const currentOptions = Array.from(select.options);
    const menuOptionsChanged = currentOptions.length !== state2.options.length || currentOptions.some((option, index) => {
      const btn = state2.options[index];
      return !btn || btn.dataset.value !== option.value || btn.textContent !== option.textContent || btn.disabled !== option.disabled;
    });
    if (menuOptionsChanged) {
      state2.menu.replaceChildren();
      state2.options = currentOptions.map((option) => _buildAppSelectOption(select, option, state2.menu));
    }
    const selected = select.options[select.selectedIndex] || select.options[0] || null;
    state2.valueEl.textContent = selected ? selected.textContent : "";
    state2.trigger.disabled = !!select.disabled;
    state2.wrap.classList.toggle("disabled", !!select.disabled);
    state2.options.forEach((btn) => {
      const active = btn.dataset.value === select.value;
      btn.setAttribute("aria-selected", active ? "true" : "false");
      btn.classList.toggle("active", active);
      btn.classList.toggle("dropdown-item-active", active);
    });
  }
  function _buildAppSelectOption(select, option, menu) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "dropdown-item dropdown-item-touch";
    btn.setAttribute("role", "option");
    btn.dataset.value = option.value;
    btn.textContent = option.textContent;
    btn.disabled = option.disabled;
    btn.addEventListener("click", () => {
      if (select.value !== option.value) {
        select.value = option.value;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
      _closeAppSelects();
      _syncAppSelect(select);
    });
    menu.appendChild(btn);
    return btn;
  }
  function _enhanceAppSelect(select) {
    if (!select || _appSelects.has(select)) return;
    if (select.dataset.appSelectEnhanced === "true") {
      const staleWrap = select.nextElementSibling;
      if (staleWrap && staleWrap.classList?.contains("app-select")) {
        const trigger2 = staleWrap.querySelector(".app-select-trigger");
        const valueEl2 = staleWrap.querySelector(".app-select-value");
        const menu2 = staleWrap.querySelector(".app-select-menu");
        if (trigger2 && valueEl2 && menu2) {
          if (_shouldPortalAppSelect(select)) staleWrap.dataset.portalMenu = "true";
          _appSelects.set(select, {
            wrap: staleWrap,
            trigger: trigger2,
            valueEl: valueEl2,
            menu: menu2,
            options: Array.from(menu2.querySelectorAll('[role="option"]'))
          });
          _syncAppSelect(select);
          return;
        }
        staleWrap.remove();
      }
      select.classList.remove("app-select-native");
      delete select.dataset.appSelectEnhanced;
    }
    const wrap = document.createElement("div");
    wrap.className = "app-select";
    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "app-select-trigger control-row form-control-compact";
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");
    const label = select.getAttribute("aria-label");
    if (label) trigger.setAttribute("aria-label", label);
    const valueEl = document.createElement("span");
    valueEl.className = "app-select-value";
    const caret = document.createElement("span");
    caret.className = "app-select-caret";
    caret.setAttribute("aria-hidden", "true");
    caret.textContent = "▾";
    trigger.append(valueEl, caret);
    const menu = document.createElement("div");
    menu.className = "app-select-menu dropdown-surface";
    menu.setAttribute("role", "listbox");
    if (label) menu.setAttribute("aria-label", label);
    const options = Array.from(select.options).map((option) => _buildAppSelectOption(select, option, menu));
    wrap.append(trigger, menu);
    select.insertAdjacentElement("afterend", wrap);
    select.classList.add("app-select-native");
    select.dataset.appSelectEnhanced = "true";
    if (_shouldPortalAppSelect(select)) wrap.dataset.portalMenu = "true";
    _appSelects.set(select, { wrap, trigger, valueEl, menu, options });
    trigger.addEventListener("click", () => {
      if (select.disabled) return;
      const open = wrap.classList.contains("open");
      _closeAppSelects(open ? null : wrap);
      wrap.classList.toggle("open", !open);
      trigger.setAttribute("aria-expanded", !open ? "true" : "false");
      if (!open) _portalAppSelectMenu(wrap, trigger, menu);
      else _unportalAppSelectMenu(menu);
    });
    trigger.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        _closeAppSelects();
        return;
      }
      if (!["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) return;
      event.preventDefault();
      const enabledOptions = options.filter((btn) => !btn.disabled);
      if (!enabledOptions.length) return;
      const currentIndex = Math.max(0, enabledOptions.findIndex((btn) => btn.dataset.value === select.value));
      const delta = event.key === "ArrowUp" ? -1 : 1;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        const next = enabledOptions[(currentIndex + delta + enabledOptions.length) % enabledOptions.length];
        select.value = next.dataset.value;
        select.dispatchEvent(new Event("change", { bubbles: true }));
        _syncAppSelect(select);
        return;
      }
      wrap.classList.add("open");
      trigger.setAttribute("aria-expanded", "true");
      _portalAppSelectMenu(wrap, trigger, menu);
    });
    select.addEventListener("change", () => _syncAppSelect(select));
    _syncAppSelect(select);
  }
  const APP_SELECT_SELECTOR = "select.form-select, .history-panel-filters select";
  function _enhanceAppSelectTree(root) {
    if (!root || typeof root.querySelectorAll !== "function") return;
    if (typeof root.matches === "function" && root.matches(APP_SELECT_SELECTOR)) {
      _enhanceAppSelect(root);
    }
    root.querySelectorAll(APP_SELECT_SELECTOR).forEach(_enhanceAppSelect);
  }
  function enhanceAppSelects2(root = document) {
    if (!root || typeof root.querySelectorAll !== "function") return;
    _enhanceAppSelectTree(root);
  }
  const syncAppSelect2 = (select) => _syncAppSelect(select);
  const closeAppSelects2 = (exceptWrap = null) => _closeAppSelects(exceptWrap);
  const portalDropdownMenu2 = (wrap, trigger, menu) => _portalAppSelectMenu(wrap, trigger, menu);
  const unportalDropdownMenu2 = (menu) => _unportalAppSelectMenu(menu);
  function observeAppSelects() {
    if (typeof MutationObserver === "undefined" || !document.body || document.body.nodeType !== 1) return;
    if (global.__darklabAppSelectObserver && typeof global.__darklabAppSelectObserver.disconnect === "function") {
      global.__darklabAppSelectObserver.disconnect();
    }
    const observer = new MutationObserver((records) => {
      records.forEach((record) => {
        if (record.type === "attributes") {
          _enhanceAppSelectTree(record.target);
          return;
        }
        record.addedNodes.forEach((node) => _enhanceAppSelectTree(node));
      });
    });
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class"]
    });
  }
  observeAppSelects();
  enhanceAppSelects2();
  if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
    document.addEventListener("click", (event) => {
      const target = event.target;
      if (target && typeof target.closest === "function" && target.closest(".app-select")) return;
      _closeAppSelects();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") _closeAppSelects();
    });
  }
  const publicApi = {
    applyMobileTextInputDefaults: applyMobileTextInputDefaults2,
    blurActiveElement: blurActiveElement2,
    blurVisibleComposerInput: blurVisibleComposerInput2,
    blurVisibleComposerInputIfMobile: blurVisibleComposerInputIfMobile2,
    closeAppSelects: closeAppSelects2,
    enhanceAppSelects: enhanceAppSelects2,
    focusAnyComposerInput: focusAnyComposerInput2,
    focusComposerInput: focusComposerInput2,
    focusElement: focusElement2,
    focusVisibleComposerInput: focusVisibleComposerInput2,
    getActiveComposerInput: getActiveComposerInput2,
    getComposerInputs: getComposerInputs2,
    getComposerValue: getComposerValue2,
    getMobileKeyboardOffsetBaseline: getMobileKeyboardOffsetBaseline2,
    getMobileViewportClosedHeight: getMobileViewportClosedHeight2,
    getVisibleComposerInput: getVisibleComposerInput2,
    handleComposerInputChange: handleComposerInputChange2,
    hideAcDropdown: hideAcDropdown2,
    hideFaqOverlay: hideFaqOverlay2,
    hideHistoryPanel: hideHistoryPanel2,
    hideModalOverlay: hideModalOverlay2,
    hideMobileMenu: hideMobileMenu2,
    hideOptionsOverlay: hideOptionsOverlay2,
    hidePanelOverlay: hidePanelOverlay2,
    hideSearchBar: hideSearchBar2,
    hideShortcutsOverlay: hideShortcutsOverlay2,
    hideTabKillBtn: hideTabKillBtn2,
    hideThemeOverlay: hideThemeOverlay2,
    hideWorkflowsOverlay: hideWorkflowsOverlay2,
    hideWorkspaceOverlay: hideWorkspaceOverlay2,
    isAcDropdownOpen: isAcDropdownOpen2,
    isActiveTabRunning: isActiveTabRunning2,
    isFaqOverlayOpen: isFaqOverlayOpen2,
    isHistoryPanelOpen: isHistoryPanelOpen2,
    isMobileMenuOpen: isMobileMenuOpen2,
    isOptionsOverlayOpen: isOptionsOverlayOpen2,
    isPanelOverlayOpen: isPanelOverlayOpen2,
    isSearchBarOpen: isSearchBarOpen2,
    isShortcutsOverlayOpen: isShortcutsOverlayOpen2,
    isThemeOverlayOpen: isThemeOverlayOpen2,
    isWorkflowsOverlayOpen: isWorkflowsOverlayOpen2,
    isWorkspaceOverlayOpen: isWorkspaceOverlayOpen2,
    markInteractionSurfaceReady: markInteractionSurfaceReady2,
    normalizeComposerSmartPeriod,
    portalDropdownMenu: portalDropdownMenu2,
    refocusComposerAfterAction: refocusComposerAfterAction2,
    setComposerValue: setComposerValue2,
    setRunButtonDisabled,
    setMobileKeyboardOpenState,
    setMobileViewportClosedHeight,
    setVisibilityState: setVisibilityState2,
    showAcDropdown: showAcDropdown2,
    showFaqOverlay: showFaqOverlay2,
    showHistoryLoadOverlay,
    hideHistoryLoadOverlay,
    showHistoryPanel,
    showHistoryRow,
    showModalOverlay: showModalOverlay2,
    showMobileMenu: showMobileMenu2,
    showPanelOverlay: showPanelOverlay2,
    showRunTimer,
    showSearchBar: showSearchBar2,
    showShortcutsOverlay: showShortcutsOverlay2,
    showTabKillBtn: showTabKillBtn2,
    showThemeOverlay,
    showOptionsOverlay,
    showWorkflowsOverlay: showWorkflowsOverlay2,
    showWorkspaceOverlay: showWorkspaceOverlay2,
    syncAppSelect: syncAppSelect2,
    syncComposerSelection: syncComposerSelection2,
    syncFocusedComposerState: syncFocusedComposerState2,
    syncMobileComposerKeyboardState: syncMobileComposerKeyboardState2,
    syncModalOverlayState: _syncModalOverlayState,
    syncRunButtonDisabled: syncRunButtonDisabled2,
    hideHistoryRow,
    hideRunTimer,
    isRunButtonDisabled,
    togglePanelOverlay: togglePanelOverlay2,
    unportalDropdownMenu: unportalDropdownMenu2
  };
  Object.assign(global, publicApi);
  if (typeof window !== "undefined" && window !== global) {
    Object.assign(window, publicApi);
  }
})(globalThis);
var applyMobileTextInputDefaults = globalThis.applyMobileTextInputDefaults;
var blurActiveElement = globalThis.blurActiveElement;
var blurVisibleComposerInput = globalThis.blurVisibleComposerInput;
var blurVisibleComposerInputIfMobile = globalThis.blurVisibleComposerInputIfMobile;
var closeAppSelects = globalThis.closeAppSelects;
var enhanceAppSelects = globalThis.enhanceAppSelects;
var focusAnyComposerInput = globalThis.focusAnyComposerInput;
var focusComposerInput = globalThis.focusComposerInput;
var focusElement = globalThis.focusElement;
var focusVisibleComposerInput = globalThis.focusVisibleComposerInput;
var getActiveComposerInput = globalThis.getActiveComposerInput;
var getComposerInputs = globalThis.getComposerInputs;
var getComposerValue = globalThis.getComposerValue;
var getMobileKeyboardOffsetBaseline = globalThis.getMobileKeyboardOffsetBaseline;
var getMobileViewportClosedHeight = globalThis.getMobileViewportClosedHeight;
var getVisibleComposerInput = globalThis.getVisibleComposerInput;
var handleComposerInputChange = globalThis.handleComposerInputChange;
var hideAcDropdown = globalThis.hideAcDropdown;
var hideFaqOverlay = globalThis.hideFaqOverlay;
var hideModalOverlay = globalThis.hideModalOverlay;
var hideHistoryPanel = globalThis.hideHistoryPanel;
var hideOptionsOverlay = globalThis.hideOptionsOverlay;
var hidePanelOverlay = globalThis.hidePanelOverlay;
var hideSearchBar = globalThis.hideSearchBar;
var hideShortcutsOverlay = globalThis.hideShortcutsOverlay;
var hideTabKillBtn = globalThis.hideTabKillBtn;
var hideThemeOverlay = globalThis.hideThemeOverlay;
var hideWorkflowsOverlay = globalThis.hideWorkflowsOverlay;
var hideWorkspaceOverlay = globalThis.hideWorkspaceOverlay;
var isAcDropdownOpen = globalThis.isAcDropdownOpen;
var isActiveTabRunning = globalThis.isActiveTabRunning;
var isFaqOverlayOpen = globalThis.isFaqOverlayOpen;
var isHistoryPanelOpen = globalThis.isHistoryPanelOpen;
var isOptionsOverlayOpen = globalThis.isOptionsOverlayOpen;
var isPanelOverlayOpen = globalThis.isPanelOverlayOpen;
var isSearchBarOpen = globalThis.isSearchBarOpen;
var isShortcutsOverlayOpen = globalThis.isShortcutsOverlayOpen;
var isThemeOverlayOpen = globalThis.isThemeOverlayOpen;
var isWorkflowsOverlayOpen = globalThis.isWorkflowsOverlayOpen;
var isWorkspaceOverlayOpen = globalThis.isWorkspaceOverlayOpen;
var showMobileMenu = globalThis.showMobileMenu;
var hideMobileMenu = globalThis.hideMobileMenu;
var isMobileMenuOpen = globalThis.isMobileMenuOpen;
var markInteractionSurfaceReady = globalThis.markInteractionSurfaceReady;
var portalDropdownMenu = globalThis.portalDropdownMenu;
var refocusComposerAfterAction = globalThis.refocusComposerAfterAction;
var setComposerValue = globalThis.setComposerValue;
var exportedSetMobileKeyboardOpenState = globalThis.setMobileKeyboardOpenState;
var exportedSetMobileViewportClosedHeight = globalThis.setMobileViewportClosedHeight;
var setVisibilityState = globalThis.setVisibilityState;
var showAcDropdown = globalThis.showAcDropdown;
var showFaqOverlay = globalThis.showFaqOverlay;
var showModalOverlay = globalThis.showModalOverlay;
var showPanelOverlay = globalThis.showPanelOverlay;
var showSearchBar = globalThis.showSearchBar;
var showShortcutsOverlay = globalThis.showShortcutsOverlay;
var showTabKillBtn = globalThis.showTabKillBtn;
var showWorkflowsOverlay = globalThis.showWorkflowsOverlay;
var showWorkspaceOverlay = globalThis.showWorkspaceOverlay;
var syncAppSelect = globalThis.syncAppSelect;
var syncComposerSelection = globalThis.syncComposerSelection;
var syncFocusedComposerState = globalThis.syncFocusedComposerState;
var syncMobileComposerKeyboardState = globalThis.syncMobileComposerKeyboardState;
var syncModalOverlayState = globalThis.syncModalOverlayState;
var syncRunButtonDisabled = globalThis.syncRunButtonDisabled;
var togglePanelOverlay = globalThis.togglePanelOverlay;
var unportalDropdownMenu = globalThis.unportalDropdownMenu;

export {
  APP_STATE_API,
  getAppState,
  getTabs,
  setTabs,
  getActiveTabId,
  setActiveTabId,
  getActiveTab,
  getTab,
  getComposerState,
  setComposerState,
  getAutocompleteState,
  setAutocompleteState,
  getWelcomeState,
  setWelcomeState,
  emitUiEvent,
  onUiEvent,
  cmdInput,
  runBtn,
  shellPromptWrap,
  shellPromptText,
  shellInputRow,
  terminalWrap,
  terminalBar,
  hamburgerBtn,
  workflowsCloseBtn,
  faqCloseBtn,
  optionsCloseBtn,
  themeCloseBtn,
  newTabBtn,
  searchToggleBtn,
  searchSignalSummary,
  searchSummaryBtn,
  historyCloseBtn,
  workspaceCloseBtn,
  histClearAllBtn,
  tabsScrollLeftBtn,
  tabsScrollRightBtn,
  searchPrevBtn,
  searchNextBtn,
  searchCloseBtn,
  optionsTabs,
  optionsTsSelect,
  optionsLnToggle,
  optionsWelcomeSelect,
  optionsShareRedactionSelect,
  optionsNotifyToggle,
  optionsCommandOutcomeSummariesToggle,
  optionsProjectAutoLinkExternalRunsToggle,
  optionsProjectAutoLinkRunEntitiesToggle,
  optionsHudClockSelect,
  optionsCompareViewModeSelect,
  optionsCompareContextSelect,
  optionsPromptUsernameInput,
  optionsPromptUsernameError,
  themeSelect,
  tsBtn,
  lnBtn,
  headerTitle,
  mobileHeaderActions,
  faqBody,
  status,
  histRow,
  tabsBar,
  tabbarChrome,
  tabbarChromeToggle,
  tabPanels,
  mobileShell,
  mobileShellChrome,
  mobileShellTranscript,
  mobileShellOverlays,
  mobileComposerHost,
  mobileComposerRow,
  mobileCmdInput,
  mobileRunBtn,
  mobileMenu,
  searchBar,
  searchInput,
  searchCount,
  searchScopeButtons,
  historyPanel,
  workspaceOverlay,
  workspaceModal,
  workspaceSummary,
  workspaceMessage,
  workspaceBreadcrumbs,
  workspaceFileList,
  workspaceViewerOverlay,
  workspaceViewer,
  workspaceViewerTitle,
  workspaceViewerControls,
  workspaceViewerText,
  workspaceViewerRefreshBtn,
  workspaceViewerAutoRefreshToggle,
  workspaceViewerAutoRefreshLabel,
  workspaceEditorOverlay,
  workspaceEditor,
  workspaceEditorTitle,
  workspacePathInput,
  workspaceLabelsInput,
  workspaceNotesInput,
  workspaceTextInput,
  workspaceRefreshBtn,
  workspaceNewBtn,
  workspaceNewFolderBtn,
  workspaceSaveBtn,
  workspaceCancelEditBtn,
  workspaceCloseViewerBtn,
  historyList,
  historyBulkToolbar,
  historyLoadOverlay,
  historySearchInput,
  historyMobileFiltersToggle,
  historyTypeFilter,
  historyRootInput,
  historyRootDropdown,
  historySignalFilter,
  historyKindFilter,
  historyEntityInput,
  historyEntityTypeFilter,
  historyExitFilter,
  historyDateFilter,
  historyProjectFilter,
  historyStarredToggle,
  historyClearFiltersBtn,
  historyActiveFilters,
  historyPagination,
  historyPaginationSummary,
  historyPaginationControls,
  acDropdown,
  histSearchDropdown,
  workflowsOverlay,
  faqOverlay,
  commandRegistryOverlay,
  commandRegistryBody,
  commandRegistrySearch,
  commandRegistryCategories,
  commandRegistrySubtitle,
  commandRegistryCloseBtn,
  commandCatalogOverlay,
  commandCatalogBody,
  commandCatalogCloseBtn,
  shortcutsOverlay,
  themeOverlay,
  optionsOverlay,
  permalinkToast,
  runTimer,
  searchCaseBtn,
  searchRegexBtn,
  setComposerPromptHandlers,
  hasComposerPromptHandler,
  getComposerPromptMode,
  hidePromptUsernameSavedIndicator,
  showPromptUsernameSavedIndicator,
  setComposerPromptMode,
  syncShellPrompt,
  setMobileShellLayoutHandlers,
  hasMobileShellLayoutHandler,
  dismissMobileKeyboardAfterSubmit,
  useMobileTerminalViewportMode,
  setHistoryPanelHandlers,
  hasHistoryPanelHandler,
  openHistoryWithFilters,
  refreshHistoryPanel,
  renderHistory,
  resetHistoryMobileFilters,
  applyMobileTextInputDefaults,
  blurActiveElement,
  blurVisibleComposerInputIfMobile,
  closeAppSelects,
  enhanceAppSelects,
  focusAnyComposerInput,
  focusElement,
  getComposerInputs,
  getComposerValue,
  getMobileKeyboardOffsetBaseline,
  getMobileViewportClosedHeight,
  getVisibleComposerInput,
  handleComposerInputChange,
  hideAcDropdown,
  hideFaqOverlay,
  hideModalOverlay,
  hideHistoryPanel,
  hideOptionsOverlay,
  hideSearchBar,
  hideShortcutsOverlay,
  hideTabKillBtn,
  hideThemeOverlay,
  hideWorkflowsOverlay,
  hideWorkspaceOverlay,
  isAcDropdownOpen,
  isActiveTabRunning,
  isFaqOverlayOpen,
  isHistoryPanelOpen,
  isOptionsOverlayOpen,
  isSearchBarOpen,
  isShortcutsOverlayOpen,
  isThemeOverlayOpen,
  isWorkflowsOverlayOpen,
  isWorkspaceOverlayOpen,
  showMobileMenu,
  hideMobileMenu,
  isMobileMenuOpen,
  markInteractionSurfaceReady,
  portalDropdownMenu,
  refocusComposerAfterAction,
  setComposerValue,
  exportedSetMobileKeyboardOpenState,
  exportedSetMobileViewportClosedHeight,
  setVisibilityState,
  showAcDropdown,
  showFaqOverlay,
  showModalOverlay,
  showPanelOverlay,
  showSearchBar,
  showShortcutsOverlay,
  showTabKillBtn,
  showWorkflowsOverlay,
  showWorkspaceOverlay,
  syncAppSelect,
  syncComposerSelection,
  syncFocusedComposerState,
  syncMobileComposerKeyboardState,
  syncModalOverlayState,
  syncRunButtonDisabled,
  togglePanelOverlay,
  unportalDropdownMenu
};
