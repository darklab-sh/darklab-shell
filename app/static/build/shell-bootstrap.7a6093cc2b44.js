import {
  _tsModes,
  activateRelativeTab,
  clearActiveShortcutTab,
  closeActiveShortcutTab,
  closeOptions,
  closeThemeSelector,
  copyActiveShortcutTab,
  createShortcutTab,
  findWordBoundaryLeft,
  findWordBoundaryRight,
  focusCommandInputFromGesture,
  getCmdSelection,
  handleComposerWordArrowShortcut,
  hidePromptUsernameSavedIndicator,
  isEditableTarget,
  isStatusMonitorShortcutOpen,
  openOptions,
  openThemeSelector,
  performMobileEditAction,
  permalinkActiveShortcutTab,
  replaceCmdRange,
  shouldIgnoreGlobalShortcutTarget
} from "./static-chunk-ts6si3fc.4579759c3973.js";
import "./static-chunk-ebgxhzia.8240f1614c32.js";
import {
  verificationStatusLabel,
  verificationStatusTone
} from "./static-chunk-ndtwds5q.291a7a432f16.js";
import {
  _historyAddRunToActiveProject,
  _historyAddRunToProject,
  _historyEditEntityMetadata,
  _historyRelativeTime,
  _historyResetSelectionOnClose,
  closeFaq,
  closeWorkflows,
  confirmHistAction,
  openFaq,
  openHistoryWithFilters,
  openWorkflows,
  refreshHistoryPanel as refreshHistoryPanel2,
  resetHistoryMobileFilters as resetHistoryMobileFilters2,
  restoreHistoryRunIntoTab as restoreHistoryRunIntoTab2,
  setControllerActionHandlers,
  toggleHistoryPanelSurface,
  toggleRailCollapsed
} from "./static-chunk-rjpbqpge.4b3f5ec190f6.js";
import {
  cycleHistoryRunOverlayTab,
  isHistoryRunOverlayOpen,
  openHistoryRunDetails,
  setHistoryRunModalStateHandlers
} from "./static-chunk-su3zfblw.dfaa45e2b263.js";
import {
  openHistoryCompareLauncher,
  setHistoryCompareHandlers
} from "./static-chunk-xbxp24ix.e021648f87bd.js";
import {
  DarklabEntityMetadata,
  DarklabOutputCore,
  DarklabRunOutputModel,
  _defaultThemeEntry,
  _findThemeEntry,
  _getStarred,
  _getThemeRegistry,
  _readRecentValues,
  _refreshFollowingOutputsAfterLayout,
  _savedThemeName,
  _seedLocalStorageStarsToServer,
  _toggleStar,
  acAccept,
  acHide,
  acIsHintOnly,
  acNextSelectableIndex,
  acSelectableIndexes,
  acSelectableItems,
  acShow,
  activateOptionsTab,
  activateTab,
  activeTeamScopeCan,
  apiFetch as apiFetch2,
  appendLine2 as appendLine,
  appendLines,
  applyCommandOutcomeSummariesPreference,
  applyCompareContextPreference,
  applyCompareViewModePreference,
  applyFaqHashTarget,
  applyHudClockPreference,
  applyLineNumberPreference,
  applyProjectAutoLinkExternalRunsPreference,
  applyProjectAutoLinkRunEntitiesPreference,
  applyPromptUsernamePreference,
  applyRunNotifyPreference,
  applyShareRedactionDefaultPreference,
  applyThemeSelection,
  applyTimestampPreference,
  applyWelcomeIntroPreference,
  bindOutsideClickClose,
  cancelPendingTerminalConfirm as cancelPendingTerminalConfirm2,
  clearFaqHash,
  clearSearch,
  clearTab,
  clearTab2,
  closeAtlas,
  closeCommandCatalogModal,
  closeCommandRegistry,
  closeMajorOverlays,
  closeProjectWorkspace,
  closeProviderStatusModal,
  closeWorkflowEditor,
  closeWorkspace,
  closeWorkspace2,
  confirmKill as confirmKill2,
  copyTab,
  createDefaultTabLabel,
  createTab,
  cycleAtlasTab,
  cycleOptionsTab,
  cycleProjectWorkspaceTab,
  ensureWorkflowCatalogLoaded,
  enterHistSearch,
  exportTabHtml,
  exportTabPdf,
  getActiveProjectContext,
  getAutocompleteMatches,
  getHudClockPreference,
  getLineNumberMode,
  getOutput,
  getPreference,
  getPromptUsernamePreference,
  getSessionId,
  getShareRedactionDefaultPreference,
  getTimestampMode,
  getWelcomeIntroPreference,
  handleHistSearchInput,
  handleHistSearchKey,
  hasPendingTerminalConfirm,
  hasSecretsHandler,
  hasWorkflowHandler,
  hideWorkspaceEditor,
  hideWorkspaceViewer,
  hydrateCmdHistory,
  interruptPromptLine as interruptPromptLine2,
  isAtlasOverlayOpen,
  isCommandCatalogOverlayOpen,
  isCommandRegistryOverlayOpen,
  isHistSearchMode,
  isProjectWorkspaceOpen,
  isProviderStatusModalOpen,
  limitAutocompleteMatchesForDisplay,
  loadProjectAutocompleteTargets,
  loadRecentValues,
  loadScheduleAutocompleteHints,
  loadSessionPreferences,
  loadSessionVariables,
  loadStarredFromServer,
  loadWatcherAutocompleteHints,
  logClientError as logClientError2,
  maskSessionToken2 as maskSessionToken,
  navigateCmdHistory,
  navigateSearch,
  openAtlas,
  openCommandRegistry,
  openProjectWorkspace,
  openTeamScopeSelector,
  openWorkflowEditor,
  openWorkspace,
  permalinkTab,
  persistTabSessionStateNow,
  prepareSearchBarForOpen,
  prepareSearchBarForScope,
  refreshActiveProjectContext,
  refreshProjectWorkspace,
  refreshSearchDiscoverabilityUi,
  refreshWorkspaceFileCache,
  renderAllowedCommandsFaq,
  renderCommandRegistry,
  renderFaqItems,
  renderFaqLimits,
  renderThemeSelectionOptions,
  renderWorkflowItems,
  requestWelcomeSettle as requestWelcomeSettle2,
  resetCmdHistoryNav,
  restoreActiveRunsAfterReload,
  restoreHistoryRunIntoTab,
  restoreTabSessionState,
  runCommand as runCommand2,
  runSearch,
  runWelcome,
  saveTab,
  schedulePersistTabSessionState,
  scheduleRunSearch,
  scheduleSearchDiscoverabilityRefresh,
  setAllowedCommandsFaqData,
  setAtlasHandlers,
  setAutocompleteCatalog,
  setCommandRegistryData,
  setCommandRegistryHandlers,
  setPreferenceCookie,
  setProjectContextHandlers,
  setProjectHudHandlers,
  setSearchScope,
  setSecretsHandlers,
  setTabLabel,
  setTabStatus,
  setWorkflowHandlers,
  setupTabScrollControls,
  submitComposerCommand as submitComposerCommand2,
  submitVisibleComposerCommand as submitVisibleComposerCommand2,
  summarizeCurrentOutputSignals,
  syncOptionsControls,
  syncPromptUsernameValidation,
  syncThemeSelectionControls,
  teamScopeDeniedMessage,
  updateNewTabBtn,
  updateOutputFollowButton,
  welcomeOwnsTab as welcomeOwnsTab2
} from "./static-chunk-uwev63xf.c0c06adb18e0.js";
import {
  copyTextToClipboard,
  downloadBlobAsAttachment,
  downloadUrlAsAttachment,
  shareUrl,
  showToast
} from "./static-chunk-poi5czx6.3f5c94749765.js";
import {
  bindDisclosure
} from "./static-chunk-zpenfczu.1862ffb66041.js";
import {
  bindDismissible,
  bindFocusTrap,
  bindMobileSheet,
  bindPressable,
  closeTopmostDismissible,
  isConfirmOpen,
  showConfirm
} from "./static-chunk-4m44pm74.0a8001fa1d52.js";
import {
  _bindMobileComposerInteractions,
  _mobileUiLayoutRefs,
  _uiOverlayRefs,
  getMobileKeyboardOffset,
  isMobileKeyboardOpen,
  syncMobileViewportState,
  useMobileTerminalViewportMode
} from "./static-chunk-2bgb52uq.a327269283bb.js";
import {
  blurVisibleComposerInputIfMobile,
  cancelPendingTerminalConfirm,
  cancelWelcome,
  cmdInput,
  commandCatalogCloseBtn,
  commandCatalogOverlay,
  commandRegistryCloseBtn,
  confirmKill,
  emitUiEvent,
  enhanceAppSelects,
  exportedNormalizeComposerSmartPeriod,
  exportedSetMobileKeyboardOpenState,
  exportedSetMobileViewportClosedHeight,
  faqCloseBtn,
  faqOverlay,
  focusElement,
  getActiveTab,
  getActiveTabId,
  getAppState,
  getAutocompleteState,
  getComposerInputs,
  getComposerState,
  getComposerValue,
  getTab,
  getTabs,
  getVisibleComposerInput,
  getWelcomeState,
  handleComposerInputChange,
  hasComposerPromptHandler,
  headerTitle,
  hideFaqOverlay,
  hideHistoryPanel,
  hideMobileMenu,
  hideSearchBar,
  hideShortcutsOverlay,
  hideWorkflowsOverlay,
  hideWorkspaceOverlay,
  histClearAllBtn,
  historyCloseBtn,
  historyPanel,
  interruptPromptLine,
  isAcDropdownOpen,
  isActiveTabRunning,
  isFaqOverlayOpen,
  isHistoryPanelOpen,
  isMobileMenuOpen,
  isOptionsOverlayOpen,
  isSearchBarOpen,
  isShortcutsOverlayOpen,
  isThemeOverlayOpen,
  isWorkflowsOverlayOpen,
  isWorkspaceOverlayOpen,
  lnBtn,
  markInteractionSurfaceReady,
  mobileCmdInput,
  mobileMenu,
  mobileRunBtn,
  mobileShellTranscript,
  newTabBtn,
  onUiEvent,
  optionsCloseBtn,
  optionsCommandOutcomeSummariesToggle,
  optionsCompareContextSelect,
  optionsCompareViewModeSelect,
  optionsHudClockSelect,
  optionsLnToggle,
  optionsNotifyToggle,
  optionsProjectAutoLinkExternalRunsToggle,
  optionsProjectAutoLinkRunEntitiesToggle,
  optionsPromptUsernameInput,
  optionsShareRedactionSelect,
  optionsTabs,
  optionsTsSelect,
  optionsWelcomeSelect,
  refocusComposerAfterAction,
  refreshHistoryPanel,
  requestWelcomeSettle,
  resetHistoryMobileFilters,
  runBtn,
  runCommand,
  searchCaseBtn,
  searchCloseBtn,
  searchInput,
  searchNextBtn,
  searchPrevBtn,
  searchRegexBtn,
  searchScopeButtons,
  searchSummaryBtn,
  searchToggleBtn,
  setAutocompleteState,
  setComposerState,
  setComposerValue,
  setWelcomeState,
  shellPromptWrap,
  shortcutsOverlay,
  showFaqOverlay,
  showMobileMenu,
  showPanelOverlay,
  showSearchBar,
  showShortcutsOverlay,
  showWorkflowsOverlay,
  submitComposerCommand,
  submitVisibleComposerCommand,
  syncComposerSelection,
  syncFocusedComposerState,
  syncMobileComposerKeyboardState,
  syncRunButtonDisabled,
  syncShellPrompt,
  themeCloseBtn,
  togglePanelOverlay,
  tsBtn,
  welcomeOwnsTab,
  workflowsCloseBtn,
  workflowsOverlay,
  workspaceCancelEditBtn,
  workspaceCloseBtn,
  workspaceCloseViewerBtn,
  workspaceEditorOverlay,
  workspaceFileList,
  workspaceViewerOverlay
} from "./static-chunk-yo5cjr7d.b86e0c93eff0.js";
import {
  getAppConfig
} from "./static-chunk-gwztcp24.e58b5ff85d88.js";
import {
  apiFetch,
  hasRuntimeHandler,
  logClientError,
  openStatusMonitor,
  setRuntimeHandlers
} from "./static-chunk-2kxtimik.c9801087c7a7.js";

// app/static/js/core/lazy_assets.js
var exportedLoadAtlasOverlay = null;
var exportedLoadCommandRegistry = null;
var exportedLoadFindingsBoard = null;
var exportedLoadMobileRunningIndicator = null;
var exportedLoadSchedulesModal = null;
var exportedLoadWatchersModal = null;
(function() {
  const _lazyAssetPromises = {};
  const _lazyAssetLoadedLogged = /* @__PURE__ */ new Set();
  const _lazyModuleAssetMeta = typeof WeakMap === "function" ? /* @__PURE__ */ new WeakMap() : null;
  let _lazyAssetConfigInvalidLogged = false;
  function _logLazyAssetConfigInvalid(err) {
    if (_lazyAssetConfigInvalidLogged || typeof logClientError !== "function") return;
    _lazyAssetConfigInvalidLogged = true;
    logClientError("lazy asset config invalid", err, {
      event: "LAZY_ASSET_CONFIG_INVALID",
      level: "warning",
      source: "lazy-assets-json"
    });
  }
  function _lazyAssetConfig() {
    let urls = {};
    if (typeof document !== "undefined") {
      const node = document.getElementById("lazy-assets-json");
      if (node && node.textContent) {
        try {
          const parsed = JSON.parse(node.textContent);
          if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) urls = parsed;
        } catch (err) {
          _logLazyAssetConfigInvalid(err);
          urls = {};
        }
      }
    }
    const appConfig = typeof getAppConfig === "function" ? getAppConfig() : {};
    const appConfigUrls = appConfig && appConfig.lazy_asset_urls;
    if (appConfigUrls && typeof appConfigUrls === "object" && !Array.isArray(appConfigUrls)) {
      urls = { ...urls, ...appConfigUrls };
    }
    return urls;
  }
  function _normalizeLazyAssetEntry(value) {
    if (typeof value === "string" && value) return { url: value, type: "classic" };
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const url = typeof value.url === "string" ? value.url : "";
      const type = value.type === "module" ? "module" : "classic";
      if (url) return { url, type };
    }
    return { url: "", type: "classic" };
  }
  function _lazyAssetEntry(name) {
    const configured = _lazyAssetConfig()[name];
    const normalized = _normalizeLazyAssetEntry(configured);
    if (normalized.url) return normalized;
    if (name === "export_pdf") return { url: "/static/js/export_pdf.js", type: "module" };
    if (name === "atlas_tabs") return { url: "/static/js/features/atlas/atlas_tabs.js", type: "module" };
    if (name === "atlas_entity_row") return { url: "/static/js/features/atlas/atlas_entity_row.js", type: "module" };
    if (name === "atlas_entity_detail") return { url: "/static/js/features/atlas/atlas_entity_detail.js", type: "module" };
    if (name === "atlas_overlay") return { url: "/static/js/features/atlas/atlas_overlay.js", type: "module" };
    if (name === "atlas_mobile") return { url: "/static/js/features/atlas/atlas_mobile.js", type: "module" };
    if (name === "findings_board") return { url: "/static/js/features/findings/findings_board_modal.js", type: "module" };
    if (name === "project_activity") return { url: "/static/js/features/projects/project_activity.js", type: "module" };
    if (name === "project_overview") return { url: "/static/js/features/projects/project_overview.js", type: "module" };
    if (name === "project_monitoring") return { url: "/static/js/features/projects/project_monitoring.js", type: "module" };
    if (name === "project_artifacts") return { url: "/static/js/features/projects/project_artifacts.js", type: "module" };
    if (name === "project_details") return { url: "/static/js/features/projects/project_details.js", type: "module" };
    if (name === "project_list") return { url: "/static/js/features/projects/project_list.js", type: "module" };
    if (name === "project_navigation") return { url: "/static/js/features/projects/project_navigation.js", type: "module" };
    if (name === "project_entity_editor") return { url: "/static/js/features/projects/project_entity_editor.js", type: "module" };
    if (name === "project_workspace_actions") return { url: "/static/js/features/projects/project_workspace_actions.js", type: "module" };
    if (name === "project_workspace_shell") return { url: "/static/js/features/projects/project_workspace_shell.js", type: "module" };
    if (name === "project_workspace_lifecycle") return { url: "/static/js/features/projects/project_workspace_lifecycle.js", type: "module" };
    if (name === "project_workspace_renderer") return { url: "/static/js/features/projects/project_workspace_renderer.js", type: "module" };
    if (name === "project_workspace_bootstrap") return { url: "/static/js/features/projects/project_workspace_bootstrap.js", type: "module" };
    if (name === "project_nested_sheets") return { url: "/static/js/features/projects/project_nested_sheets.js", type: "module" };
    if (name === "project_workspace_events") return { url: "/static/js/features/projects/project_workspace_events.js", type: "module" };
    if (name === "project_targets") return { url: "/static/js/features/projects/project_targets.js", type: "module" };
    if (name === "project_runs") return { url: "/static/js/features/projects/project_runs.js", type: "module" };
    if (name === "project_mobile_compare") return { url: "/static/js/features/projects/project_mobile_compare.js", type: "module" };
    if (name === "project_mobile_shell") return { url: "/static/js/features/projects/project_mobile_shell.js", type: "module" };
    if (name === "project_mobile_detail") return { url: "/static/js/features/projects/project_mobile_detail.js", type: "module" };
    if (name === "project_findings_data") return { url: "/static/js/features/projects/project_findings_data.js", type: "module" };
    if (name === "project_filters") return { url: "/static/js/features/projects/project_filters.js", type: "module" };
    if (name === "project_entities") return { url: "/static/js/features/projects/project_entities.js", type: "module" };
    if (name === "project_findings") return { url: "/static/js/features/projects/project_findings.js", type: "module" };
    if (name === "project_findings_board") return { url: "/static/js/features/projects/project_findings_board.js", type: "module" };
    if (name === "project_packages") return { url: "/static/js/features/projects/project_packages.js", type: "module" };
    if (name === "project_report") return { url: "/static/js/features/projects/project_report.js", type: "module" };
    if (name === "history_compare_core") return { url: "/static/js/features/run-comparison/history_compare_core.js", type: "module" };
    if (name === "history_compare_overlay") return { url: "/static/js/features/run-comparison/history_compare_overlay.js", type: "module" };
    if (name === "history_compare_controls") return { url: "/static/js/features/run-comparison/history_compare_controls.js", type: "module" };
    if (name === "history_compare_navigation") return { url: "/static/js/features/run-comparison/history_compare_navigation.js", type: "module" };
    if (name === "history_compare_renderer") return { url: "/static/js/features/run-comparison/history_compare_renderer.js", type: "module" };
    if (name === "history_compare_launcher") return { url: "/static/js/features/run-comparison/history_compare_launcher.js", type: "module" };
    if (name === "history_run_details") return { url: "/static/js/features/history/history_run_details.js", type: "module" };
    if (name === "options_session_token_controls") return { url: "/static/js/features/preferences/session_token_controls.js", type: "module" };
    if (name === "options_secrets_panel") return { url: "/static/js/features/preferences/secrets_panel.js", type: "module" };
    if (name === "options_teams_panel") return { url: "/static/js/features/preferences/teams_panel.js", type: "module" };
    if (name === "options_notification_channels") return { url: "/static/js/features/preferences/notification_channels.js", type: "module" };
    if (name === "command_registry") return { url: "/static/js/features/command-registry/command_registry.js", type: "module" };
    if (name === "workflows") return { url: "/static/js/features/workflows/workflows.js", type: "module" };
    if (name === "pty_controller") return { url: "/static/js/pty.js", type: "module" };
    if (name === "schedules_modal") return { url: "/static/js/features/schedules/schedules_modal.js", type: "module" };
    if (name === "mobile_running_indicator") {
      return { url: "/static/js/features/mobile/mobile_running_indicator.js", type: "module" };
    }
    if (name === "tour_modal") return { url: "/static/js/tour_modal.js", type: "module" };
    if (name === "watchers_modal") return { url: "/static/js/features/watchers/watchers_modal.js", type: "module" };
    if (name === "status_monitor_core") return { url: "/static/js/features/status-monitor/status_monitor_core.js", type: "module" };
    if (name === "status_monitor_data") return { url: "/static/js/features/status-monitor/status_monitor_data.js", type: "module" };
    if (name === "status_monitor_resources") return { url: "/static/js/features/status-monitor/status_monitor_resources.js", type: "module" };
    if (name === "status_monitor") return { url: "/static/js/status_monitor.js", type: "module" };
    if (name === "jspdf") return { url: "/vendor/jspdf.umd.min.js", type: "classic" };
    if (name === "xterm_css") return { url: "/vendor/xterm.css", type: "classic" };
    if (name === "xterm_js") return { url: "/vendor/xterm.js", type: "classic" };
    if (name === "xterm_fit_js") return { url: "/vendor/xterm-addon-fit.js", type: "classic" };
    return { url: "", type: "classic" };
  }
  function _lazyAssetUrl(name) {
    return _lazyAssetEntry(name).url;
  }
  function _safeLazyAssetLogSrc(src) {
    const raw = String(src || "");
    if (!raw) return "";
    try {
      const parsed = new URL(raw, typeof window !== "undefined" && window.location ? window.location.href : "http://localhost/");
      const version = parsed.searchParams.get("v");
      return version ? `${parsed.pathname}?v=${encodeURIComponent(version)}` : parsed.pathname;
    } catch (_) {
      return raw.split("?", 1)[0].slice(0, 300);
    }
  }
  function _logLazyAssetLoadFailed(name, entry, err, globalCheck) {
    if (typeof logClientError !== "function") return;
    logClientError("lazy asset load failed", err, {
      event: "LAZY_ASSET_LOAD_FAILED",
      level: "error",
      asset_name: String(name || "").slice(0, 120),
      asset_type: entry && entry.type === "module" ? "module" : "classic",
      src: _safeLazyAssetLogSrc(entry && entry.url),
      expected_global: typeof globalCheck === "function"
    });
  }
  function _lazyAssetTimestamp() {
    if (typeof performance !== "undefined" && typeof performance.now === "function") {
      return performance.now();
    }
    return Date.now();
  }
  function _lazyAssetDurationMs(startedAt) {
    const duration = Math.max(0, _lazyAssetTimestamp() - Number(startedAt || 0));
    return Math.round(duration);
  }
  function _lazyAssetDiagnosticsEnabled() {
    const appConfig = typeof getAppConfig === "function" ? getAppConfig() : {};
    return appConfig.frontend_bridge_warnings === true || appConfig.debug === true || appConfig.dev_mode === true || appConfig.environment === "development" || appConfig.env === "development" || appConfig.lazy_asset_debug === true;
  }
  function _logLazyAssetLifecycle(context, name, entry, details = {}) {
    if (!_lazyAssetDiagnosticsEnabled()) return;
    const consoleApi = typeof window !== "undefined" && window.console || typeof globalThis !== "undefined" && globalThis.console;
    const log = consoleApi && (consoleApi.debug || consoleApi.log);
    if (typeof log !== "function") return;
    log.call(consoleApi, `[darklab] ${details.event || context}`, {
      asset_name: String(name || "").slice(0, 120),
      asset_type: entry && entry.type === "module" ? "module" : "classic",
      src: _safeLazyAssetLogSrc(entry && entry.url),
      ...details
    });
  }
  function _logLazyAssetLoadStarted(name, entry, cacheHit = false) {
    _logLazyAssetLifecycle("lazy asset load started", name, entry, {
      event: "LAZY_ASSET_LOAD_STARTED",
      level: "debug",
      cache_hit: cacheHit === true
    });
  }
  function _logLazyAssetLoaded(name, entry, startedAt, cacheHit = false) {
    const firstLoad = !_lazyAssetLoadedLogged.has(name);
    if (!cacheHit) _lazyAssetLoadedLogged.add(name);
    if (!firstLoad && !cacheHit) return;
    _logLazyAssetLifecycle("lazy asset loaded", name, entry, {
      event: "LAZY_ASSET_LOADED",
      level: firstLoad && !cacheHit ? "info" : "debug",
      duration_ms: cacheHit ? 0 : _lazyAssetDurationMs(startedAt),
      cache_hit: cacheHit === true
    });
  }
  function _rememberLazyModuleMeta(moduleApi, name, entry) {
    if (!_lazyModuleAssetMeta || !moduleApi || typeof moduleApi !== "object" && typeof moduleApi !== "function") return;
    try {
      _lazyModuleAssetMeta.set(moduleApi, {
        name: String(name || "").slice(0, 120),
        entry
      });
    } catch (_) {
    }
  }
  function _lazyModuleMeta(moduleApi) {
    if (!_lazyModuleAssetMeta || !moduleApi || typeof moduleApi !== "object" && typeof moduleApi !== "function") return null;
    try {
      return _lazyModuleAssetMeta.get(moduleApi) || null;
    } catch (_) {
      return null;
    }
  }
  function _lazyModuleExportKeys(moduleApi) {
    if (!moduleApi || typeof moduleApi !== "object" && typeof moduleApi !== "function") return [];
    try {
      return Object.keys(moduleApi).sort().slice(0, 80);
    } catch (_) {
      return [];
    }
  }
  function _logLazyModuleExportMissing(moduleApi, err, details = {}) {
    if (typeof logClientError !== "function") return;
    const meta = _lazyModuleMeta(moduleApi);
    logClientError("lazy module export missing", err, {
      event: "LAZY_MODULE_EXPORT_MISSING",
      level: "error",
      asset_name: String(details.assetName || meta?.name || "").slice(0, 120),
      export_name: String(details.exportName || "").slice(0, 160),
      controller_name: String(details.controllerName || "").slice(0, 160),
      src: _safeLazyAssetLogSrc(details.src || meta?.entry?.url || ""),
      module_keys: _lazyModuleExportKeys(moduleApi)
    });
  }
  function lazyAssetUrl(name) {
    return _lazyAssetUrl(name);
  }
  function loadLazyClassicScript(name, globalCheck) {
    if (typeof globalCheck === "function" && globalCheck()) return Promise.resolve();
    const entry = _lazyAssetEntry(name);
    if (_lazyAssetPromises[name]) {
      _logLazyAssetLoadStarted(name, entry, true);
      _lazyAssetPromises[name].then(() => _logLazyAssetLoaded(name, entry, null, true)).catch(() => {
      });
      return _lazyAssetPromises[name];
    }
    const src = entry.url;
    if (!src) {
      const err = new Error(`Unknown lazy asset: ${name}`);
      _logLazyAssetLoadFailed(name, entry, err, globalCheck);
      return Promise.reject(err);
    }
    const startedAt = _lazyAssetTimestamp();
    _logLazyAssetLoadStarted(name, entry, false);
    _lazyAssetPromises[name] = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.async = true;
      script.onload = () => {
        if (typeof globalCheck !== "function" || globalCheck()) resolve();
        else reject(new Error(`Lazy asset did not expose its expected global: ${src}`));
      };
      script.onerror = () => reject(new Error(`Failed to load lazy asset: ${src}`));
      (document.head || document.documentElement).appendChild(script);
    }).then((result) => {
      _logLazyAssetLoaded(name, entry, startedAt, false);
      return result;
    }).catch((err) => {
      delete _lazyAssetPromises[name];
      _logLazyAssetLoadFailed(name, entry, err, globalCheck);
      throw err;
    });
    return _lazyAssetPromises[name];
  }
  function loadLazyModule(name, globalCheck) {
    if (typeof globalCheck === "function" && globalCheck()) return Promise.resolve();
    const entry = _lazyAssetEntry(name);
    if (_lazyAssetPromises[name]) {
      _logLazyAssetLoadStarted(name, entry, true);
      _lazyAssetPromises[name].then(() => _logLazyAssetLoaded(name, entry, null, true)).catch(() => {
      });
      return _lazyAssetPromises[name];
    }
    const src = entry.url;
    if (!src) {
      const err = new Error(`Unknown lazy asset: ${name}`);
      _logLazyAssetLoadFailed(name, entry, err, globalCheck);
      return Promise.reject(err);
    }
    const importer = typeof window !== "undefined" && typeof window.__darklabImportModule === "function" ? window.__darklabImportModule : (url) => import(url);
    const startedAt = _lazyAssetTimestamp();
    _logLazyAssetLoadStarted(name, entry, false);
    _lazyAssetPromises[name] = Promise.resolve().then(() => importer(src)).then((moduleApi) => {
      if (typeof globalCheck !== "function" || globalCheck()) {
        _rememberLazyModuleMeta(moduleApi, name, entry);
        _logLazyAssetLoaded(name, entry, startedAt, false);
        return moduleApi;
      }
      throw new Error(`Lazy module did not expose its expected global: ${src}`);
    }).catch((err) => {
      delete _lazyAssetPromises[name];
      _logLazyAssetLoadFailed(name, entry, err, globalCheck);
      throw err;
    });
    return _lazyAssetPromises[name];
  }
  function loadLazyAsset(name, globalCheck) {
    return _lazyAssetEntry(name).type === "module" ? loadLazyModule(name, globalCheck) : loadLazyClassicScript(name, globalCheck);
  }
  function loadLazyClassicScripts(items) {
    return items.reduce(
      (promise, item) => promise.then(() => loadLazyAsset(item.name, item.globalCheck)),
      Promise.resolve()
    );
  }
  async function loadJsPdf() {
    await loadLazyClassicScript("jspdf", () => !!(window.jspdf && window.jspdf.jsPDF));
    return window.jspdf.jsPDF;
  }
  async function loadExportPdfUtils() {
    const pdfModule = await loadLazyAsset("export_pdf");
    return _requireLazyModuleExport(pdfModule, "ExportPdfUtils", (value) => value && typeof value.buildTerminalExportPdf === "function");
  }
  async function loadFindingsBoard2() {
    const boardModule = await loadLazyAsset("findings_board");
    return {
      openFindingsBoard: _requireLazyModuleExport(boardModule, "openFindingsBoard", (value) => typeof value === "function" && value !== lazyOpenFindingsBoard),
      closeFindingsBoard: boardModule?.closeFindingsBoard || null,
      isFindingsBoardOpen: boardModule?.isFindingsBoardOpen || null
    };
  }
  function _requireLazyModuleExport(moduleApi, exportName, predicate = (value) => !!value) {
    const exported = moduleApi && moduleApi[exportName];
    if (predicate(exported)) return exported;
    const err = new Error(`Lazy module did not expose export: ${exportName}`);
    _logLazyModuleExportMissing(moduleApi, err, { exportName });
    throw err;
  }
  async function loadAtlasOverlay2() {
    const tabsModule = await loadLazyAsset("atlas_tabs");
    const entityRowModule = await loadLazyAsset("atlas_entity_row");
    const detailModule = await loadLazyAsset("atlas_entity_detail");
    const overlayModule = await loadLazyAsset("atlas_overlay");
    const mobileModule = document.getElementById("atlas-mobile-root") ? await loadLazyAsset("atlas_mobile") : null;
    const DarklabAtlasOverlay = _requireLazyModuleExport(overlayModule, "DarklabAtlasOverlay");
    const atlasApi = {
      DarklabAtlasTabs: _requireLazyModuleExport(tabsModule, "DarklabAtlasTabs"),
      DarklabAtlasEntityRow: _requireLazyModuleExport(entityRowModule, "DarklabAtlasEntityRow"),
      DarklabAtlasDetail: _requireLazyModuleExport(detailModule, "DarklabAtlasDetail"),
      DarklabAtlasOverlay,
      DarklabAtlasMobile: mobileModule?.DarklabAtlasMobile || null,
      openAtlas: _requireLazyModuleExport(overlayModule, "openAtlas", (value) => typeof value === "function" && value !== lazyOpenAtlas),
      closeAtlas: overlayModule?.closeAtlas || null,
      isAtlasOverlayOpen: overlayModule?.isAtlasOverlayOpen || null,
      refreshAtlasOverlay: overlayModule?.refreshAtlasOverlay || null,
      cycleAtlasTab: overlayModule?.cycleAtlasTab || null
    };
    if (typeof window !== "undefined") {
      if (typeof atlasApi.openAtlas === "function") window.openAtlas = atlasApi.openAtlas;
      if (typeof atlasApi.closeAtlas === "function") window.closeAtlas = atlasApi.closeAtlas;
      if (typeof atlasApi.isAtlasOverlayOpen === "function") window.isAtlasOverlayOpen = atlasApi.isAtlasOverlayOpen;
      if (typeof atlasApi.refreshAtlasOverlay === "function") window.refreshAtlasOverlay = atlasApi.refreshAtlasOverlay;
      if (typeof atlasApi.cycleAtlasTab === "function") window.cycleAtlasTab = atlasApi.cycleAtlasTab;
    }
    if (typeof setAtlasHandlers === "function") {
      setAtlasHandlers(atlasApi);
    }
    return atlasApi;
  }
  async function loadWatchersModal2() {
    const watchersModule = await loadLazyAsset("watchers_modal");
    return {
      openWatchersModal: _requireLazyModuleExport(watchersModule, "openWatchersModal", (value) => typeof value === "function" && value !== lazyOpenWatchersModal),
      closeWatchersModal: watchersModule?.closeWatchersModal || null,
      isWatchersOverlayOpen: watchersModule?.isWatchersOverlayOpen || null
    };
  }
  async function loadProjectReport() {
    const reportModule = await loadLazyAsset("project_report");
    return _requireLazyModuleExport(reportModule, "DarklabProjectReport", (value) => value && typeof value.createProjectReportController === "function");
  }
  async function loadProjectActivity() {
    const activityModule = await loadLazyAsset("project_activity");
    return _requireLazyModuleExport(activityModule, "DarklabProjectActivity", (value) => value && typeof value.createProjectActivityController === "function");
  }
  async function loadProjectOverview() {
    const overviewModule = await loadLazyAsset("project_overview");
    return _requireLazyModuleExport(overviewModule, "DarklabProjectOverview", (value) => value && typeof value.createProjectOverviewController === "function");
  }
  async function loadProjectMonitoring() {
    const monitoringModule = await loadLazyAsset("project_monitoring");
    return _requireLazyModuleExport(monitoringModule, "DarklabProjectMonitoring", (value) => value && typeof value.createProjectMonitoringController === "function");
  }
  async function loadProjectArtifacts() {
    const artifactsModule = await loadLazyAsset("project_artifacts");
    return _requireLazyModuleExport(artifactsModule, "DarklabProjectArtifacts", (value) => value && typeof value.createProjectArtifactsController === "function");
  }
  async function loadProjectPackages() {
    const packagesModule = await loadLazyAsset("project_packages");
    const DarklabProjectPackages = _requireLazyModuleExport(packagesModule, "DarklabProjectPackages", (value) => value && typeof value.createProjectPackagesController === "function");
    window.DarklabProjectPackages = DarklabProjectPackages;
    return DarklabProjectPackages;
  }
  async function loadProjectWorkspace() {
    const loadProjectNamespace = async (name, globalName, controllerName) => {
      const moduleApi = await loadLazyAsset(name);
      const namespace = moduleApi?.[globalName] || window[globalName];
      if (!namespace || typeof namespace[controllerName] !== "function") {
        const err = new Error(`Lazy module ${name} did not expose ${globalName}.${controllerName}`);
        _logLazyModuleExportMissing(moduleApi, err, {
          assetName: name,
          exportName: globalName,
          controllerName
        });
        throw err;
      }
      window[globalName] = namespace;
      return namespace;
    };
    const DarklabProjectDetails = await loadProjectNamespace(
      "project_details",
      "DarklabProjectDetails",
      "createProjectDetailsController"
    );
    const DarklabProjectList = await loadProjectNamespace(
      "project_list",
      "DarklabProjectList",
      "createProjectListController"
    );
    const DarklabProjectNavigation = await loadProjectNamespace(
      "project_navigation",
      "DarklabProjectNavigation",
      "createProjectNavigationController"
    );
    const DarklabProjectEntityEditor = await loadProjectNamespace(
      "project_entity_editor",
      "DarklabProjectEntityEditor",
      "createProjectEntityEditorController"
    );
    const DarklabProjectWorkspaceActions = await loadProjectNamespace(
      "project_workspace_actions",
      "DarklabProjectWorkspaceActions",
      "createProjectWorkspaceActionsController"
    );
    const DarklabProjectWorkspaceShell = await loadProjectNamespace(
      "project_workspace_shell",
      "DarklabProjectWorkspaceShell",
      "createProjectWorkspaceShellController"
    );
    const DarklabProjectWorkspaceLifecycle = await loadProjectNamespace(
      "project_workspace_lifecycle",
      "DarklabProjectWorkspaceLifecycle",
      "createProjectWorkspaceLifecycleController"
    );
    const DarklabProjectWorkspaceRenderer = await loadProjectNamespace(
      "project_workspace_renderer",
      "DarklabProjectWorkspaceRenderer",
      "createProjectWorkspaceRendererController"
    );
    const DarklabProjectWorkspaceBootstrap = await loadProjectNamespace(
      "project_workspace_bootstrap",
      "DarklabProjectWorkspaceBootstrap",
      "createProjectWorkspaceBootstrapController"
    );
    const DarklabProjectNestedSheets = await loadProjectNamespace(
      "project_nested_sheets",
      "DarklabProjectNestedSheets",
      "createProjectNestedSheetsController"
    );
    const DarklabProjectWorkspaceEvents = await loadProjectNamespace(
      "project_workspace_events",
      "DarklabProjectWorkspaceEvents",
      "createProjectWorkspaceEventsController"
    );
    const DarklabProjectTargets = await loadProjectNamespace(
      "project_targets",
      "DarklabProjectTargets",
      "createProjectTargetsController"
    );
    const DarklabProjectRuns = await loadProjectNamespace(
      "project_runs",
      "DarklabProjectRuns",
      "createProjectRunsController"
    );
    const DarklabProjectMobileCompare = await loadProjectNamespace(
      "project_mobile_compare",
      "DarklabProjectMobileCompare",
      "createProjectMobileCompareController"
    );
    const DarklabProjectMobileShell = await loadProjectNamespace(
      "project_mobile_shell",
      "DarklabProjectMobileShell",
      "createProjectMobileShellController"
    );
    const DarklabProjectMobileDetail = await loadProjectNamespace(
      "project_mobile_detail",
      "DarklabProjectMobileDetail",
      "createProjectMobileDetailController"
    );
    const DarklabProjectFindingsData = await loadProjectNamespace(
      "project_findings_data",
      "DarklabProjectFindingsData",
      "createProjectFindingsDataController"
    );
    const DarklabProjectFilters = await loadProjectNamespace(
      "project_filters",
      "DarklabProjectFilters",
      "createProjectFiltersController"
    );
    const DarklabProjectEntities = await loadProjectNamespace(
      "project_entities",
      "DarklabProjectEntities",
      "createProjectEntitiesController"
    );
    const DarklabProjectFindings = await loadProjectNamespace(
      "project_findings",
      "DarklabProjectFindings",
      "createProjectFindingsController"
    );
    const DarklabProjectFindingsBoard = await loadProjectNamespace(
      "project_findings_board",
      "DarklabProjectFindingsBoard",
      "createProjectFindingsBoardController"
    );
    return {
      DarklabProjectDetails,
      DarklabProjectList,
      DarklabProjectNavigation,
      DarklabProjectEntityEditor,
      DarklabProjectWorkspaceActions,
      DarklabProjectWorkspaceShell,
      DarklabProjectWorkspaceLifecycle,
      DarklabProjectWorkspaceRenderer,
      DarklabProjectWorkspaceBootstrap,
      DarklabProjectNestedSheets,
      DarklabProjectWorkspaceEvents,
      DarklabProjectTargets,
      DarklabProjectRuns,
      DarklabProjectMobileCompare,
      DarklabProjectMobileShell,
      DarklabProjectMobileDetail,
      DarklabProjectFindingsData,
      DarklabProjectFilters,
      DarklabProjectEntities,
      DarklabProjectFindings,
      DarklabProjectFindingsBoard
    };
  }
  async function loadHistoryRunDetails() {
    const detailsModule = await loadLazyAsset("history_run_details");
    return _requireLazyModuleExport(
      detailsModule,
      "openHistoryRunDetails",
      (value) => typeof value === "function" && value !== lazyOpenHistoryRunDetails
    );
  }
  async function loadOptionsPanels() {
    const sessionTokenControls = await loadLazyAsset("options_session_token_controls");
    const secretsPanel = await loadLazyAsset("options_secrets_panel");
    const teamsPanel = await loadLazyAsset("options_teams_panel");
    const notificationChannels = await loadLazyAsset("options_notification_channels");
    return {
      _updateOptionsSessionTokenStatus: _requireLazyModuleExport(
        sessionTokenControls,
        "_updateOptionsSessionTokenStatus",
        (value) => typeof value === "function"
      ),
      refreshOptionsSecrets: _requireLazyModuleExport(secretsPanel, "refreshOptionsSecrets", (value) => typeof value === "function" && value !== lazyRefreshOptionsSecrets),
      invalidateOptionsSecrets: _requireLazyModuleExport(secretsPanel, "invalidateOptionsSecrets", (value) => typeof value === "function" && value !== lazyInvalidateOptionsSecrets),
      openSecretEditor: secretsPanel?.openSecretEditor || null,
      openProviderStatusModal: secretsPanel?.openProviderStatusModal || null,
      refreshOptionsTeams: _requireLazyModuleExport(teamsPanel, "refreshOptionsTeams", (value) => typeof value === "function" && value !== lazyRefreshOptionsTeams),
      refreshNotificationChannels: _requireLazyModuleExport(
        notificationChannels,
        "refreshNotificationChannels",
        (value) => typeof value === "function" && value !== lazyRefreshNotificationChannels
      ),
      openNotificationChannelEditor: notificationChannels?.openNotificationChannelEditor || null
    };
  }
  async function loadCommandRegistry2() {
    const registryModule = await loadLazyAsset("command_registry");
    return {
      showCommandRegistryOverlay: registryModule?.showCommandRegistryOverlay || null,
      hideCommandRegistryOverlay: registryModule?.hideCommandRegistryOverlay || null,
      isCommandRegistryOverlayOpen: registryModule?.isCommandRegistryOverlayOpen || null,
      closeCommandRegistry: registryModule?.closeCommandRegistry || null,
      renderCommandRegistry: registryModule?.renderCommandRegistry || null,
      openCommandRegistry: _requireLazyModuleExport(registryModule, "openCommandRegistry", (value) => typeof value === "function" && value !== lazyOpenCommandRegistry),
      showCommandCatalogOverlay: registryModule?.showCommandCatalogOverlay || null,
      hideCommandCatalogOverlay: registryModule?.hideCommandCatalogOverlay || null,
      closeCommandCatalogModal: registryModule?.closeCommandCatalogModal || null,
      isCommandCatalogOverlayOpen: registryModule?.isCommandCatalogOverlayOpen || null,
      wireCommandCatalogExamples: registryModule?.wireCommandCatalogExamples || null,
      renderCommandCatalogModal: registryModule?.renderCommandCatalogModal || null,
      openCommandCatalogModal: registryModule?.openCommandCatalogModal || null
    };
  }
  async function loadWorkflows2() {
    const workflowsModule = await loadLazyAsset("workflows");
    return {
      renderWorkflowItems: _requireLazyModuleExport(workflowsModule, "renderWorkflowItems", (value) => typeof value === "function" && value !== lazyRenderWorkflowItems),
      reloadWorkflowCatalog: workflowsModule?.reloadWorkflowCatalog || null,
      ensureWorkflowCatalogLoaded: workflowsModule?.ensureWorkflowCatalogLoaded || null,
      handleWorkflowTerminalCommand: _requireLazyModuleExport(
        workflowsModule,
        "handleWorkflowTerminalCommand",
        (value) => typeof value === "function" && value !== lazyHandleWorkflowTerminalCommand
      ),
      _runtimeWorkflowContext: workflowsModule?._runtimeWorkflowContext || null,
      openWorkflowEditor: workflowsModule?.openWorkflowEditor || null,
      closeWorkflowEditor: workflowsModule?.closeWorkflowEditor || null
    };
  }
  async function lazyOpenWorkflowEditor(workflow = null) {
    const workflows = await loadWorkflows2();
    const open = workflows?.openWorkflowEditor;
    if (typeof open !== "function" || open === lazyOpenWorkflowEditor) {
      return false;
    }
    return open(workflow);
  }
  async function loadHistoryCompare() {
    const coreModule = await loadLazyAsset("history_compare_core");
    const overlayModule = await loadLazyAsset("history_compare_overlay");
    const controlsModule = await loadLazyAsset("history_compare_controls");
    const navigationModule = await loadLazyAsset("history_compare_navigation");
    const rendererModule = await loadLazyAsset("history_compare_renderer");
    const launcherModule = await loadLazyAsset("history_compare_launcher");
    _requireLazyModuleExport(coreModule, "DarklabHistoryCompareCore");
    _requireLazyModuleExport(controlsModule, "_closeHistoryCompareActionMenus", (value) => typeof value === "function");
    _requireLazyModuleExport(navigationModule, "_historyCompareScrollToLine", (value) => typeof value === "function");
    return {
      closeHistoryCompareOverlay: _requireLazyModuleExport(
        overlayModule,
        "closeHistoryCompareOverlay",
        (value) => typeof value === "function" && value !== lazyCloseHistoryCompareOverlay
      ),
      isHistoryCompareOverlayOpen: _requireLazyModuleExport(
        overlayModule,
        "isHistoryCompareOverlayOpen",
        (value) => typeof value === "function" && value !== lazyIsHistoryCompareOverlayOpen
      ),
      fetchAndRenderHistoryComparison: _requireLazyModuleExport(
        rendererModule,
        "fetchAndRenderHistoryComparison",
        (value) => typeof value === "function" && value !== lazyFetchAndRenderHistoryComparison
      ),
      openHistoryCompareLauncher: _requireLazyModuleExport(
        launcherModule,
        "openHistoryCompareLauncher",
        (value) => typeof value === "function" && value !== lazyOpenHistoryCompareLauncher
      )
    };
  }
  async function loadPtyController() {
    await loadLazyAsset("pty_controller", () => !!(window.startInteractivePtyCommand && window.startInteractivePtyCommand !== lazyStartInteractivePtyCommand && window.attachInteractivePtyCommand && window.attachInteractivePtyCommand !== lazyAttachInteractivePtyCommand && typeof window.isInteractivePtyCommand === "function"));
    return window.startInteractivePtyCommand;
  }
  async function loadPtyAttachController() {
    await loadPtyController();
    return window.attachInteractivePtyCommand;
  }
  async function loadSchedulesModal2() {
    const schedulesModule = await loadLazyAsset("schedules_modal");
    return {
      openSchedulesModal: _requireLazyModuleExport(schedulesModule, "openSchedulesModal", (value) => typeof value === "function" && value !== lazyOpenSchedulesModal),
      closeSchedulesModal: schedulesModule?.closeSchedulesModal || null,
      isSchedulesOverlayOpen: schedulesModule?.isSchedulesOverlayOpen || null
    };
  }
  async function loadTourModal() {
    const tourModule = await loadLazyAsset("tour_modal");
    return {
      openTourModal: _requireLazyModuleExport(tourModule, "openTourModal", (value) => typeof value === "function" && value !== lazyOpenTourModal),
      closeTourModal: tourModule?.closeTourModal || null,
      _visibleTourModalChapters: tourModule?._visibleTourModalChapters || null,
      _renderTourIllustration: tourModule?._renderTourIllustration || null
    };
  }
  async function loadStatusMonitor() {
    const coreModule = await loadLazyAsset("status_monitor_core");
    const dataModule = await loadLazyAsset("status_monitor_data");
    const resourcesModule = await loadLazyAsset("status_monitor_resources");
    const monitorModule = await loadLazyAsset("status_monitor");
    return {
      DarklabStatusMonitorCore: _requireLazyModuleExport(coreModule, "DarklabStatusMonitorCore"),
      DarklabStatusMonitorData: _requireLazyModuleExport(dataModule, "DarklabStatusMonitorData"),
      DarklabStatusMonitorResources: _requireLazyModuleExport(resourcesModule, "DarklabStatusMonitorResources"),
      openStatusMonitor: _requireLazyModuleExport(monitorModule, "openStatusMonitor", (value) => typeof value === "function" && value !== lazyOpenStatusMonitor),
      closeStatusMonitor: monitorModule?.closeStatusMonitor || null,
      isStatusMonitorOpen: monitorModule?.isStatusMonitorOpen || null,
      refreshStatusMonitor: monitorModule?.refreshStatusMonitor || null
    };
  }
  async function loadMobileRunningIndicator2() {
    const moduleApi = await loadLazyAsset("mobile_running_indicator");
    return moduleApi && typeof moduleApi.createMobileRunningIndicator === "function" ? { create: moduleApi.createMobileRunningIndicator } : null;
  }
  async function lazyOpenFindingsBoard(options = {}) {
    const board = await loadFindingsBoard2();
    const open = board?.openFindingsBoard;
    if (typeof open !== "function" || open === lazyOpenFindingsBoard) return false;
    return open(options);
  }
  async function lazyOpenAtlas(options = {}) {
    const atlas = await loadAtlasOverlay2();
    const open = atlas?.openAtlas;
    if (typeof open !== "function" || open === lazyOpenAtlas) return false;
    return open(options);
  }
  function lazyCloseAtlas(options = {}) {
    if (window.closeAtlas === lazyCloseAtlas) return false;
    if (typeof window.closeAtlas === "function") return window.closeAtlas(options);
    return false;
  }
  function lazyIsAtlasOverlayOpen() {
    if (window.isAtlasOverlayOpen === lazyIsAtlasOverlayOpen) {
      const overlay = document.getElementById("atlas-overlay");
      return !!(overlay && overlay.classList.contains("open"));
    }
    if (typeof window.isAtlasOverlayOpen === "function") return window.isAtlasOverlayOpen();
    return false;
  }
  function lazyCycleAtlasTab(offset) {
    if (window.cycleAtlasTab === lazyCycleAtlasTab) return false;
    if (typeof window.cycleAtlasTab === "function") return window.cycleAtlasTab(offset);
    return false;
  }
  function lazyCloseFindingsBoard(options = {}) {
    if (window.closeFindingsBoard === lazyCloseFindingsBoard) return false;
    if (typeof window.closeFindingsBoard === "function") return window.closeFindingsBoard(options);
    return false;
  }
  function lazyIsFindingsBoardOpen() {
    if (window.isFindingsBoardOpen === lazyIsFindingsBoardOpen) {
      return !!document.getElementById("findings-board-overlay")?.classList.contains("open");
    }
    if (typeof window.isFindingsBoardOpen === "function") return window.isFindingsBoardOpen();
    return false;
  }
  async function lazyOpenWatchersModal(options = {}) {
    const watchers = await loadWatchersModal2();
    const open = watchers?.openWatchersModal;
    if (typeof open !== "function" || open === lazyOpenWatchersModal) return false;
    return open(options);
  }
  async function lazyCloseWatchersModal(options = {}) {
    if (window.closeWatchersModal === lazyCloseWatchersModal) {
      const watchers = await loadWatchersModal2();
      const close = watchers?.closeWatchersModal;
      if (typeof close === "function") return close(options);
      return false;
    }
    if (typeof window.closeWatchersModal === "function") return window.closeWatchersModal(options);
    return false;
  }
  function lazyIsWatchersOverlayOpen() {
    if (window.isWatchersOverlayOpen === lazyIsWatchersOverlayOpen) {
      return !!document.getElementById("watchers-overlay")?.classList.contains("open");
    }
    if (typeof window.isWatchersOverlayOpen === "function") return window.isWatchersOverlayOpen();
    return false;
  }
  async function lazyOpenSchedulesModal(options = {}) {
    const schedules = await loadSchedulesModal2();
    const open = schedules?.openSchedulesModal;
    if (typeof open !== "function" || open === lazyOpenSchedulesModal) return false;
    return open(options);
  }
  async function lazyCloseSchedulesModal(options = {}) {
    if (window.closeSchedulesModal === lazyCloseSchedulesModal) {
      const schedules = await loadSchedulesModal2();
      const close = schedules?.closeSchedulesModal;
      if (typeof close === "function") return close(options);
      return false;
    }
    if (typeof window.closeSchedulesModal === "function") return window.closeSchedulesModal(options);
    return false;
  }
  function lazyIsSchedulesOverlayOpen() {
    if (window.isSchedulesOverlayOpen === lazyIsSchedulesOverlayOpen) {
      return !!document.getElementById("schedules-overlay")?.classList.contains("open");
    }
    if (typeof window.isSchedulesOverlayOpen === "function") return window.isSchedulesOverlayOpen();
    return false;
  }
  async function lazyOpenTourModal(options = {}) {
    const tour = await loadTourModal();
    const open = tour?.openTourModal;
    if (typeof open !== "function" || open === lazyOpenTourModal) return false;
    return open(options);
  }
  function lazyCloseTourModal(options = {}) {
    if (window.closeTourModal === lazyCloseTourModal) {
      const overlay = document.getElementById("tour-overlay");
      if (!overlay) return false;
      overlay.classList.remove("open");
      overlay.classList.add("u-hidden");
      overlay.setAttribute("aria-hidden", "true");
      return true;
    }
    if (typeof window.closeTourModal === "function") return window.closeTourModal(options);
    return false;
  }
  async function lazyOpenStatusMonitor(options = {}) {
    const monitor = await loadStatusMonitor();
    const open = monitor?.openStatusMonitor;
    if (typeof open !== "function" || open === lazyOpenStatusMonitor) return false;
    return open(options);
  }
  async function lazyOpenHistoryRunDetails(run) {
    const open = await loadHistoryRunDetails();
    if (typeof open !== "function" || open === lazyOpenHistoryRunDetails) return false;
    return open(run);
  }
  async function lazyRefreshOptionsSecrets(options = {}) {
    const panels = await loadOptionsPanels();
    const refresh = panels?.refreshOptionsSecrets;
    if (typeof refresh !== "function" || refresh === lazyRefreshOptionsSecrets) {
      return false;
    }
    return refresh(options);
  }
  async function lazyRefreshOptionsTeams(options = {}) {
    const panels = await loadOptionsPanels();
    const refresh = panels?.refreshOptionsTeams;
    if (typeof refresh !== "function" || refresh === lazyRefreshOptionsTeams) {
      return false;
    }
    return refresh(options);
  }
  async function lazyRefreshNotificationChannels(options = {}) {
    const panels = await loadOptionsPanels();
    const refresh = panels?.refreshNotificationChannels;
    if (typeof refresh !== "function" || refresh === lazyRefreshNotificationChannels) {
      return false;
    }
    return refresh(options);
  }
  function lazyInvalidateOptionsSecrets() {
    if (window.invalidateOptionsSecrets === lazyInvalidateOptionsSecrets) return false;
    if (typeof window.invalidateOptionsSecrets === "function") return window.invalidateOptionsSecrets();
    return false;
  }
  async function lazyOpenCommandRegistry() {
    const registry = await loadCommandRegistry2();
    const open = registry?.openCommandRegistry;
    if (typeof open !== "function" || open === lazyOpenCommandRegistry) return false;
    return open();
  }
  function lazyCloseCommandRegistry() {
    return lazyHideCommandRegistryOverlay();
  }
  function lazyHideCommandRegistryOverlay() {
    const overlay = document.getElementById("command-registry-overlay");
    if (!overlay) return false;
    overlay.classList.add("u-hidden");
    overlay.classList.remove("open");
    overlay.setAttribute("aria-hidden", "true");
    return true;
  }
  function lazyIsCommandRegistryOverlayOpen() {
    const overlay = document.getElementById("command-registry-overlay");
    return !!(overlay && overlay.classList.contains("open"));
  }
  function _workflowCachedItems() {
    return Array.isArray(window.__workflowCatalogItems) ? window.__workflowCatalogItems : [];
  }
  function _setWorkflowCachedItems(items) {
    window.__workflowCatalogItems = Array.isArray(items) ? items.slice() : [];
    return window.__workflowCatalogItems;
  }
  function _emitWorkflowCatalog(items) {
    if (typeof emitUiEvent === "function") {
      emitUiEvent("app:workflows-rendered", {
        count: items.length,
        items: items.slice()
      });
    }
  }
  let _workflowCatalogLoadPromise = null;
  function lazyRenderWorkflowItems(items, options = {}) {
    const nextItems = _setWorkflowCachedItems(items);
    if (options.emitCatalogEvent !== false) _emitWorkflowCatalog(nextItems);
    return nextItems;
  }
  async function lazyReloadWorkflowCatalog() {
    if (_workflowCatalogLoadPromise) return _workflowCatalogLoadPromise;
    if (typeof apiFetch !== "function" || !hasRuntimeHandler?.("apiFetch")) return _workflowCachedItems();
    _workflowCatalogLoadPromise = (async () => {
      const resp = await apiFetch("/workflows");
      if (resp && resp.ok === false) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      return lazyRenderWorkflowItems(data.items || []);
    })();
    try {
      return await _workflowCatalogLoadPromise;
    } finally {
      _workflowCatalogLoadPromise = null;
    }
  }
  function lazyEnsureWorkflowCatalogLoaded() {
    const items = _workflowCachedItems();
    if (items.length) return Promise.resolve(items);
    return lazyReloadWorkflowCatalog();
  }
  async function lazyHandleWorkflowTerminalCommand(cmd, tabId) {
    const workflows = await loadWorkflows2();
    const handle = workflows?.handleWorkflowTerminalCommand;
    if (typeof handle !== "function" || handle === lazyHandleWorkflowTerminalCommand) {
      return false;
    }
    return handle(cmd, tabId);
  }
  async function lazyOpenHistoryCompareLauncher(run) {
    const compare = await loadHistoryCompare();
    const open = compare?.openHistoryCompareLauncher;
    if (typeof open !== "function" || open === lazyOpenHistoryCompareLauncher) return false;
    return open(run);
  }
  async function lazyFetchAndRenderHistoryComparison(leftId, rightId, options = {}) {
    const compare = await loadHistoryCompare();
    const fetchAndRender = compare?.fetchAndRenderHistoryComparison;
    if (typeof fetchAndRender !== "function" || fetchAndRender === lazyFetchAndRenderHistoryComparison) return false;
    return fetchAndRender(leftId, rightId, options);
  }
  function lazyCloseHistoryCompareOverlay(options = {}) {
    if (window.closeHistoryCompareOverlay === lazyCloseHistoryCompareOverlay) return false;
    if (typeof window.closeHistoryCompareOverlay === "function") return window.closeHistoryCompareOverlay(options);
    return false;
  }
  function lazyIsHistoryCompareOverlayOpen() {
    if (window.isHistoryCompareOverlayOpen === lazyIsHistoryCompareOverlayOpen) {
      const overlay = document.getElementById("history-compare-overlay");
      return !!(overlay && !overlay.classList.contains("u-hidden"));
    }
    if (typeof window.isHistoryCompareOverlayOpen === "function") return window.isHistoryCompareOverlayOpen();
    return false;
  }
  function lazyCloseStatusMonitor(options = {}) {
    if (window.closeStatusMonitor === lazyCloseStatusMonitor) {
      document.body?.classList?.remove("status-monitor-mobile-open", "status-monitor-desktop-open");
      document.querySelector(".status-monitor-scrim")?.classList?.add("u-hidden");
      document.getElementById("status-monitor")?.classList?.add("u-hidden");
      return true;
    }
    if (typeof window.closeStatusMonitor === "function") return window.closeStatusMonitor(options);
    return false;
  }
  function lazyIsStatusMonitorOpen() {
    if (window.isStatusMonitorOpen === lazyIsStatusMonitorOpen) {
      const monitor = document.getElementById("status-monitor");
      return !!(monitor && !monitor.classList.contains("u-hidden"));
    }
    if (typeof window.isStatusMonitorOpen === "function") return window.isStatusMonitorOpen();
    return false;
  }
  async function lazyRefreshStatusMonitor(options = {}) {
    const monitor = await loadStatusMonitor();
    const refresh = monitor?.refreshStatusMonitor;
    if (typeof refresh !== "function" || refresh === lazyRefreshStatusMonitor) return false;
    return refresh(options);
  }
  function _splitInteractivePtyCommand(cmd) {
    return String(cmd || "").trim().match(/"[^"]*"|'[^']*'|\S+/g) || [];
  }
  function _interactivePtySpecs() {
    const appConfig = typeof getAppConfig === "function" ? getAppConfig() : {};
    const configured = Array.isArray(appConfig.interactive_pty_commands) ? appConfig.interactive_pty_commands : [];
    if (configured.length) return configured;
    return [{ root: "mtr", trigger_flag: "--interactive" }];
  }
  function lazyIsInteractivePtyCommand(cmd) {
    const parts = _splitInteractivePtyCommand(cmd);
    const root = String(parts[0] || "").toLowerCase();
    if (!root) return false;
    return _interactivePtySpecs().some((spec) => {
      const specRoot = String(spec && spec.root || "").toLowerCase();
      const trigger = String(spec && spec.trigger_flag || "");
      return specRoot === root && !!trigger && parts.slice(1).includes(trigger);
    });
  }
  async function lazyStartInteractivePtyCommand(cmd, tabId) {
    const start = await loadPtyController();
    if (typeof start !== "function" || start === lazyStartInteractivePtyCommand) return false;
    return start(cmd, tabId);
  }
  async function lazyAttachInteractivePtyCommand(runOrRunId, tabId = "") {
    const attach = await loadPtyAttachController();
    if (typeof attach !== "function" || attach === lazyAttachInteractivePtyCommand) return false;
    return attach(runOrRunId, tabId);
  }
  window.loadLazyClassicScript = loadLazyClassicScript;
  window.loadLazyModule = loadLazyModule;
  window.loadLazyAsset = loadLazyAsset;
  window.lazyAssetUrl = lazyAssetUrl;
  window.loadJsPdf = loadJsPdf;
  window.loadLazyClassicScripts = loadLazyClassicScripts;
  window.loadExportPdfUtils = loadExportPdfUtils;
  window.loadAtlasOverlay = loadAtlasOverlay2;
  window.loadFindingsBoard = loadFindingsBoard2;
  window.loadProjectActivity = loadProjectActivity;
  window.loadProjectOverview = loadProjectOverview;
  window.loadProjectMonitoring = loadProjectMonitoring;
  window.loadProjectArtifacts = loadProjectArtifacts;
  window.loadProjectWorkspace = loadProjectWorkspace;
  window.loadProjectPackages = loadProjectPackages;
  window.loadProjectReport = loadProjectReport;
  window.loadHistoryCompare = loadHistoryCompare;
  window.loadHistoryRunDetails = loadHistoryRunDetails;
  window.loadOptionsPanels = loadOptionsPanels;
  window.loadCommandRegistry = loadCommandRegistry2;
  window.loadWorkflows = loadWorkflows2;
  window.loadPtyController = loadPtyController;
  window.loadPtyAttachController = loadPtyAttachController;
  window.loadWatchersModal = loadWatchersModal2;
  window.loadSchedulesModal = loadSchedulesModal2;
  window.loadTourModal = loadTourModal;
  window.loadStatusMonitor = loadStatusMonitor;
  window.loadMobileRunningIndicator = loadMobileRunningIndicator2;
  exportedLoadAtlasOverlay = loadAtlasOverlay2;
  exportedLoadCommandRegistry = loadCommandRegistry2;
  exportedLoadFindingsBoard = loadFindingsBoard2;
  exportedLoadMobileRunningIndicator = loadMobileRunningIndicator2;
  exportedLoadSchedulesModal = loadSchedulesModal2;
  exportedLoadWatchersModal = loadWatchersModal2;
  if (typeof window.openAtlas !== "function") window.openAtlas = lazyOpenAtlas;
  if (typeof window.closeAtlas !== "function") window.closeAtlas = lazyCloseAtlas;
  if (typeof window.isAtlasOverlayOpen !== "function") window.isAtlasOverlayOpen = lazyIsAtlasOverlayOpen;
  if (typeof window.cycleAtlasTab !== "function") window.cycleAtlasTab = lazyCycleAtlasTab;
  if (typeof setAtlasHandlers === "function") {
    setAtlasHandlers({
      openAtlas: lazyOpenAtlas,
      closeAtlas: lazyCloseAtlas,
      isAtlasOverlayOpen: lazyIsAtlasOverlayOpen,
      cycleAtlasTab: lazyCycleAtlasTab
    });
  }
  if (typeof window.openFindingsBoard !== "function") window.openFindingsBoard = lazyOpenFindingsBoard;
  if (typeof window.closeFindingsBoard !== "function") window.closeFindingsBoard = lazyCloseFindingsBoard;
  if (typeof window.isFindingsBoardOpen !== "function") window.isFindingsBoardOpen = lazyIsFindingsBoardOpen;
  if (typeof window.openSchedulesModal !== "function") window.openSchedulesModal = lazyOpenSchedulesModal;
  if (typeof window.closeSchedulesModal !== "function") window.closeSchedulesModal = lazyCloseSchedulesModal;
  if (typeof window.isSchedulesOverlayOpen !== "function") window.isSchedulesOverlayOpen = lazyIsSchedulesOverlayOpen;
  if (typeof window.openTourModal !== "function") window.openTourModal = lazyOpenTourModal;
  if (typeof window.closeTourModal !== "function") window.closeTourModal = lazyCloseTourModal;
  if (typeof window.openStatusMonitor !== "function") window.openStatusMonitor = lazyOpenStatusMonitor;
  if (typeof setRuntimeHandlers === "function") {
    setRuntimeHandlers({
      openStatusMonitor: lazyOpenStatusMonitor,
      refreshStatusMonitor: lazyRefreshStatusMonitor
    });
  }
  if (typeof window.closeStatusMonitor !== "function") window.closeStatusMonitor = lazyCloseStatusMonitor;
  if (typeof window.isStatusMonitorOpen !== "function") window.isStatusMonitorOpen = lazyIsStatusMonitorOpen;
  if (typeof window.openWatchersModal !== "function") window.openWatchersModal = lazyOpenWatchersModal;
  if (typeof window.closeWatchersModal !== "function") window.closeWatchersModal = lazyCloseWatchersModal;
  if (typeof window.isWatchersOverlayOpen !== "function") window.isWatchersOverlayOpen = lazyIsWatchersOverlayOpen;
  if (typeof window.openHistoryCompareLauncher !== "function") window.openHistoryCompareLauncher = lazyOpenHistoryCompareLauncher;
  if (typeof window.fetchAndRenderHistoryComparison !== "function") window.fetchAndRenderHistoryComparison = lazyFetchAndRenderHistoryComparison;
  if (typeof setHistoryCompareHandlers === "function") {
    setHistoryCompareHandlers({
      fetchAndRenderHistoryComparison: lazyFetchAndRenderHistoryComparison,
      openHistoryCompareLauncher: lazyOpenHistoryCompareLauncher
    });
  }
  if (typeof window.closeHistoryCompareOverlay !== "function") window.closeHistoryCompareOverlay = lazyCloseHistoryCompareOverlay;
  if (typeof window.isHistoryCompareOverlayOpen !== "function") window.isHistoryCompareOverlayOpen = lazyIsHistoryCompareOverlayOpen;
  if (typeof window.openHistoryRunDetails !== "function") window.openHistoryRunDetails = lazyOpenHistoryRunDetails;
  if (typeof setHistoryRunModalStateHandlers === "function") {
    setHistoryRunModalStateHandlers({
      openHistoryRunDetails: lazyOpenHistoryRunDetails
    });
  }
  if (typeof window.refreshOptionsSecrets !== "function") window.refreshOptionsSecrets = lazyRefreshOptionsSecrets;
  if (typeof window.invalidateOptionsSecrets !== "function") window.invalidateOptionsSecrets = lazyInvalidateOptionsSecrets;
  if (typeof setSecretsHandlers === "function") {
    setSecretsHandlers({
      refreshOptionsSecrets: lazyRefreshOptionsSecrets,
      invalidateOptionsSecrets: lazyInvalidateOptionsSecrets
    });
  }
  if (typeof window.refreshOptionsTeams !== "function") window.refreshOptionsTeams = lazyRefreshOptionsTeams;
  if (typeof window.refreshNotificationChannels !== "function") window.refreshNotificationChannels = lazyRefreshNotificationChannels;
  if (typeof window.openCommandRegistry !== "function") window.openCommandRegistry = lazyOpenCommandRegistry;
  if (typeof setCommandRegistryHandlers === "function") {
    setCommandRegistryHandlers({
      openCommandRegistry: lazyOpenCommandRegistry,
      closeCommandRegistry: lazyCloseCommandRegistry,
      closeCommandCatalogModal: () => {
      },
      hideCommandCatalogOverlay: () => {
      },
      isCommandCatalogOverlayOpen: () => false,
      isCommandRegistryOverlayOpen: lazyIsCommandRegistryOverlayOpen
    });
  }
  if (typeof window.closeCommandRegistry !== "function") window.closeCommandRegistry = lazyCloseCommandRegistry;
  if (typeof window.hideCommandRegistryOverlay !== "function") window.hideCommandRegistryOverlay = lazyHideCommandRegistryOverlay;
  if (typeof window.isCommandRegistryOverlayOpen !== "function") {
    window.isCommandRegistryOverlayOpen = lazyIsCommandRegistryOverlayOpen;
  }
  if (typeof window.renderWorkflowItems !== "function") window.renderWorkflowItems = lazyRenderWorkflowItems;
  if (typeof window.reloadWorkflowCatalog !== "function") window.reloadWorkflowCatalog = lazyReloadWorkflowCatalog;
  if (typeof window.ensureWorkflowCatalogLoaded !== "function") {
    window.ensureWorkflowCatalogLoaded = lazyEnsureWorkflowCatalogLoaded;
  }
  if (typeof window.handleWorkflowTerminalCommand !== "function") {
    window.handleWorkflowTerminalCommand = lazyHandleWorkflowTerminalCommand;
  }
  if (typeof window.openWorkflowEditor !== "function") window.openWorkflowEditor = lazyOpenWorkflowEditor;
  if (typeof setWorkflowHandlers === "function") {
    setWorkflowHandlers({
      renderWorkflowItems: lazyRenderWorkflowItems,
      reloadWorkflowCatalog: lazyReloadWorkflowCatalog,
      ensureWorkflowCatalogLoaded: lazyEnsureWorkflowCatalogLoaded,
      handleWorkflowTerminalCommand: lazyHandleWorkflowTerminalCommand,
      openWorkflowEditor: lazyOpenWorkflowEditor
    });
  }
  if (typeof window.isInteractivePtyCommand !== "function") window.isInteractivePtyCommand = lazyIsInteractivePtyCommand;
  if (typeof window.startInteractivePtyCommand !== "function") window.startInteractivePtyCommand = lazyStartInteractivePtyCommand;
  if (typeof window.attachInteractivePtyCommand !== "function") window.attachInteractivePtyCommand = lazyAttachInteractivePtyCommand;
})();
function loadAtlasOverlay(...args) {
  return typeof exportedLoadAtlasOverlay === "function" ? exportedLoadAtlasOverlay(...args) : Promise.resolve(null);
}
function loadCommandRegistry(...args) {
  return typeof exportedLoadCommandRegistry === "function" ? exportedLoadCommandRegistry(...args) : Promise.resolve(null);
}
function loadFindingsBoard(...args) {
  return typeof exportedLoadFindingsBoard === "function" ? exportedLoadFindingsBoard(...args) : Promise.resolve(null);
}
function loadMobileRunningIndicator(...args) {
  return typeof exportedLoadMobileRunningIndicator === "function" ? exportedLoadMobileRunningIndicator(...args) : Promise.resolve(null);
}
function loadSchedulesModal(...args) {
  return typeof exportedLoadSchedulesModal === "function" ? exportedLoadSchedulesModal(...args) : Promise.resolve(null);
}
function loadWatchersModal(...args) {
  return typeof exportedLoadWatchersModal === "function" ? exportedLoadWatchersModal(...args) : Promise.resolve(null);
}

// app/static/js/features/projects/project_target_validation.js
var ProjectTargetValidation = /* @__PURE__ */ (() => {
  const TARGET_TYPES2 = [
    { value: "domain", label: "domain" },
    { value: "url", label: "url" },
    { value: "host", label: "host" },
    { value: "ip", label: "ip" }
  ];
  const TARGET_NOTES_MAX_LENGTH2 = 2e4;
  const DOMAIN_RE = /^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/i;
  const HOST_RE = /^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*\.?$/i;
  const IPV4_RE = /^(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)$/;
  const TARGET_VALUE_HELP2 = {
    domain: {
      placeholder: "target.example.com",
      help: "Domain name only. Examples: darklab.sh, api.darklab.sh",
      error: "Use a domain name, such as darklab.sh or api.darklab.sh."
    },
    url: {
      placeholder: "https://target.example.com/path",
      help: "Full URL including scheme. Examples: https://darklab.sh, https://api.darklab.sh/login",
      error: "Use a full HTTP or HTTPS URL, such as https://darklab.sh/login."
    },
    host: {
      placeholder: "host.example.com",
      help: "Hostname or IP address. Examples: api.darklab.sh, 192.0.2.10",
      error: "Use a hostname or IP address, such as api.darklab.sh or 192.0.2.10."
    },
    ip: {
      placeholder: "192.0.2.10",
      help: "Single IPv4 or IPv6 address. Examples: 192.0.2.10, 2001:db8::10",
      error: "Use a single IPv4 or IPv6 address, such as 192.0.2.10 or 2001:db8::10."
    }
  };
  function _isValidIpv6Address(value) {
    const candidate = String(value || "").trim();
    if (!candidate || !candidate.includes(":") || /[\s/]/.test(candidate)) return false;
    try {
      return !!new URL(`http://[${candidate}]`).hostname;
    } catch (_) {
      return false;
    }
  }
  function isValidIpAddress(value) {
    const candidate = String(value || "").trim();
    return IPV4_RE.test(candidate) || _isValidIpv6Address(candidate);
  }
  function isValidDomain(value) {
    return DOMAIN_RE.test(String(value || "").trim());
  }
  function isValidHost(value) {
    const candidate = String(value || "").trim();
    if (!candidate || /[:/?#@\s]/.test(candidate)) return isValidIpAddress(candidate);
    return HOST_RE.test(candidate);
  }
  function isValidUrl(value) {
    const candidate = String(value || "").trim();
    if (!candidate || /\s/.test(candidate)) return false;
    try {
      const parsed = new URL(candidate);
      return ["http:", "https:"].includes(parsed.protocol) && !!parsed.hostname;
    } catch (_) {
      return false;
    }
  }
  function helpForType2(type) {
    const normalized = String(type || "domain").trim();
    return TARGET_VALUE_HELP2[normalized] || TARGET_VALUE_HELP2.domain;
  }
  function valueValidationError2(type, value) {
    const normalized = String(type || "domain").trim();
    const candidate = String(value || "").trim();
    if (!candidate) return "Enter a target value before saving.";
    const validators = {
      domain: isValidDomain,
      url: isValidUrl,
      host: isValidHost,
      ip: isValidIpAddress
    };
    const validator = validators[normalized] || validators.domain;
    if (validator(candidate)) return "";
    const copy = helpForType2(normalized);
    return `The target value does not match the selected type. ${copy.error}`;
  }
  function notesValidationError2(notes) {
    const length = String(notes || "").trim().length;
    if (length <= TARGET_NOTES_MAX_LENGTH2) return "";
    return `Target notes must be ${TARGET_NOTES_MAX_LENGTH2.toLocaleString()} characters or fewer.`;
  }
  return {
    TARGET_TYPES: TARGET_TYPES2,
    TARGET_NOTES_MAX_LENGTH: TARGET_NOTES_MAX_LENGTH2,
    TARGET_VALUE_HELP: TARGET_VALUE_HELP2,
    helpForType: helpForType2,
    valueValidationError: valueValidationError2,
    notesValidationError: notesValidationError2
  };
})();
var {
  TARGET_NOTES_MAX_LENGTH,
  TARGET_TYPES,
  TARGET_VALUE_HELP,
  helpForType,
  notesValidationError,
  valueValidationError
} = ProjectTargetValidation;

// app/static/js/features/projects/project_workspace_constants.js
var exportedDarklabProjectWorkspaceConstants = null;
(function projectWorkspaceConstantsModule(global) {
  "use strict";
  const findingReviewStates = [
    { value: "new", label: "New" },
    { value: "reviewed", label: "Reviewed" },
    { value: "important", label: "Important" },
    { value: "false_positive", label: "False positive" },
    { value: "needs_followup", label: "Follow-up" }
  ];
  const findingSeverityRank = {
    critical: 0,
    high: 1,
    medium: 2,
    low: 3,
    info: 4
  };
  const DarklabProjectWorkspaceConstants = {
    findingNoteStateOptions: [
      { value: "all", label: "All notes" },
      { value: "noted", label: "With notes" },
      { value: "unnoted", label: "Without notes" }
    ],
    findingOrphanOptions: [
      { value: "hide", label: "Hide orphans" },
      { value: "all", label: "Show all" },
      { value: "only", label: "Only orphans" }
    ],
    findingReviewRank: findingReviewStates.reduce((acc, state, index) => {
      acc[state.value] = index;
      return acc;
    }, {}),
    findingReviewStates,
    findingScopeOptions: [
      { value: "finding", label: "Finding" },
      { value: "http", label: "HTTP" },
      { value: "port", label: "Port" },
      { value: "warnings", label: "Warnings" },
      { value: "errors", label: "Errors" },
      { value: "summaries", label: "Summaries" }
    ],
    findingSeverityOptions: [
      { value: "critical", label: "Critical" },
      { value: "high", label: "High" },
      { value: "medium", label: "Medium" },
      { value: "low", label: "Low" },
      { value: "info", label: "Info" }
    ],
    findingSeverityRank,
    findingSortOptions: [
      { value: "source", label: "Source order" },
      { value: "run", label: "Run" },
      { value: "severity", label: "Severity" },
      { value: "review", label: "Review state" },
      { value: "target", label: "Target" },
      { value: "newest", label: "Newest run" }
    ],
    mobileNotePreviewLimit: 100,
    projectNotesAutosaveDelayMs: 450,
    workspaceBroadcastKey: "darklab_project_workspace_changed"
  };
  exportedDarklabProjectWorkspaceConstants = DarklabProjectWorkspaceConstants;
})(globalThis);

// app/static/js/features/projects/project_workspace_state.js
var exportedDarklabProjectWorkspaceState = null;
(function projectWorkspaceStateModule(global) {
  "use strict";
  const FINDING_VIEW_MODE_KEY = "darklab_project_finding_view_mode";
  const FINDING_VIEW_MODES = /* @__PURE__ */ new Set(["list", "board"]);
  function normalizedFindingViewMode(value) {
    const normalized = String(value || "list");
    return FINDING_VIEW_MODES.has(normalized) ? normalized : "list";
  }
  function sessionStore() {
    try {
      return global.sessionStorage || global.window?.sessionStorage || null;
    } catch (_) {
      return null;
    }
  }
  function readFindingViewMode() {
    try {
      return normalizedFindingViewMode(sessionStore()?.getItem(FINDING_VIEW_MODE_KEY));
    } catch (_) {
      return "list";
    }
  }
  function writeFindingViewMode(value) {
    try {
      sessionStore()?.setItem(FINDING_VIEW_MODE_KEY, normalizedFindingViewMode(value));
    } catch (_) {
    }
  }
  function createProjectWorkspaceState() {
    let rows = [];
    let summaries = /* @__PURE__ */ new Map();
    let pagination = { limit: 50, offset: 0, total: 0 };
    let loading = false;
    let selectedId = "";
    let tab = "details";
    let editingTargetId = "";
    let lastTargetType = "domain";
    const collapsedFindingGroups = /* @__PURE__ */ new Set();
    const collapsedArtifactGroups = /* @__PURE__ */ new Set();
    let entityTab = "ip";
    let entitySelectMode = false;
    const selectedEntityIds = /* @__PURE__ */ new Set();
    let findingSelectMode = false;
    const selectedFindingIds = /* @__PURE__ */ new Set();
    let findingViewMode = readFindingViewMode();
    let entityPicker = null;
    function setPagination(nextPagination = {}) {
      pagination = {
        limit: Number(nextPagination && nextPagination.limit || 50),
        offset: Number(nextPagination && nextPagination.offset || 0),
        total: Number(nextPagination && nextPagination.total || 0)
      };
    }
    function setPaginationOffset(offset) {
      pagination = {
        ...pagination,
        offset: Math.max(0, Number(offset || 0))
      };
    }
    function setLastTargetType(targetType) {
      lastTargetType = String(targetType || lastTargetType || "domain");
    }
    function toggleArtifactGroup(projectId, runId) {
      const key = `${String(projectId || "")}${String(runId || "")}`;
      if (collapsedArtifactGroups.has(key)) collapsedArtifactGroups.delete(key);
      else collapsedArtifactGroups.add(key);
    }
    function toggleFindingGroup(projectId, runLabel) {
      const key = `${String(projectId || "")}${String(runLabel || "")}`;
      if (collapsedFindingGroups.has(key)) collapsedFindingGroups.delete(key);
      else collapsedFindingGroups.add(key);
    }
    function clearEditingTargetIf(targetId) {
      if (editingTargetId === String(targetId || "")) editingTargetId = "";
    }
    return {
      rows: () => rows,
      setRows: (nextRows) => {
        rows = Array.isArray(nextRows) ? nextRows : [];
      },
      summaries: () => summaries,
      summary: (projectId) => summaries.get(String(projectId || "")) || null,
      setSummary: (projectId, summary) => {
        summaries.set(String(projectId || ""), summary);
      },
      setSummaries: (nextSummaries) => {
        summaries = nextSummaries instanceof Map ? nextSummaries : /* @__PURE__ */ new Map();
      },
      pagination: () => pagination,
      setPagination,
      setPaginationOffset,
      loading: () => loading,
      setLoading: (nextLoading) => {
        loading = !!nextLoading;
      },
      selectedId: () => selectedId,
      setSelectedId: (projectId) => {
        selectedId = String(projectId || "");
      },
      tab: () => tab,
      setTab: (nextTab) => {
        tab = String(nextTab || "details");
      },
      editingTargetId: () => editingTargetId,
      setEditingTargetId: (targetId) => {
        editingTargetId = String(targetId || "");
      },
      clearEditingTargetIf,
      lastTargetType: () => lastTargetType,
      setLastTargetType,
      collapsedFindingGroups: () => collapsedFindingGroups,
      collapsedArtifactGroups: () => collapsedArtifactGroups,
      toggleArtifactGroup,
      toggleFindingGroup,
      entityTab: () => entityTab,
      setEntityTab: (nextTab) => {
        entityTab = String(nextTab || "ip");
      },
      entitySelectMode: () => entitySelectMode,
      setEntitySelectMode: (enabled) => {
        entitySelectMode = !!enabled;
      },
      selectedEntityIds: () => selectedEntityIds,
      findingSelectMode: () => findingSelectMode,
      setFindingSelectMode: (enabled) => {
        findingSelectMode = !!enabled;
      },
      selectedFindingIds: () => selectedFindingIds,
      findingViewMode: () => findingViewMode,
      setFindingViewMode: (mode) => {
        findingViewMode = normalizedFindingViewMode(mode);
        writeFindingViewMode(findingViewMode);
      },
      entityPicker: () => entityPicker,
      setEntityPicker: (picker) => {
        entityPicker = picker;
      }
    };
  }
  const DarklabProjectWorkspaceState = {
    createProjectWorkspaceState
  };
  exportedDarklabProjectWorkspaceState = DarklabProjectWorkspaceState;
})(globalThis);

// app/static/js/features/projects/project_active_context.js
var exportedDarklabProjectActiveContext = null;
(function projectActiveContextModule(global) {
  "use strict";
  function createProjectActiveContextController(context) {
    const ctx = context || {};
    let activeProject = null;
    function project() {
      return activeProject;
    }
    function setProject(nextProject) {
      activeProject = nextProject && typeof nextProject === "object" ? nextProject : null;
      render();
      ctx.syncProjectNotesForm?.();
      ctx.emitUiEvent?.("app:active-project-changed", { project: activeProject });
      return activeProject;
    }
    function render() {
      const name = ctx.projectDisplayName(activeProject);
      const visible = !!name;
      if (ctx.hudProjectCell) {
        ctx.hudProjectCell.classList.remove("u-hidden");
        ctx.hudProjectCell.classList.toggle("hud-project-empty", !visible);
      }
      if (ctx.hudProjectEl) {
        ctx.hudProjectEl.textContent = visible ? name : "No project";
        ctx.hudProjectEl.title = visible ? `Active project: ${name}` : "No active project";
        ctx.setValueColor(ctx.hudProjectEl, visible ? null : "hud-muted");
      }
    }
    async function load() {
      if (typeof ctx.apiFetch !== "function") return null;
      try {
        const resp = await ctx.apiFetch("/projects/active", { cache: "no-store" });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        activeProject = data && data.project && typeof data.project === "object" ? data.project : null;
      } catch (err) {
        activeProject = null;
        ctx.logClientError?.("failed to load /projects/active", err);
      }
      render();
      ctx.syncProjectNotesForm?.();
      ctx.emitUiEvent?.("app:active-project-changed", { project: activeProject });
      return activeProject;
    }
    function targetDiscoveryMessage(count) {
      const total = Number(count || 0);
      if (total === 1) return "1 project target discovered.";
      return `${total.toLocaleString()} project targets discovered.`;
    }
    function pulseNavTargets() {
      const controls = [];
      ctx.railNav?.querySelectorAll('[data-action="projects"]').forEach((control) => controls.push(control));
      const mobileProjectsButton = document.querySelector('#mobile-menu-sheet [data-menu-action="projects"]');
      if (mobileProjectsButton) controls.push(mobileProjectsButton);
      controls.forEach((control) => {
        control.classList.add("has-project-target-discovery");
        window.setTimeout(() => {
          control.classList.remove("has-project-target-discovery");
        }, 5e3);
      });
    }
    function bindTargetDiscoveryEvent() {
      if (typeof document === "undefined" || typeof document.addEventListener !== "function") return;
      document.addEventListener("app:project-target-discovered", (event) => {
        const detail = event && event.detail && typeof event.detail === "object" ? event.detail : {};
        const count = Number(detail.count || detail.target_count || 0);
        if (!Number.isFinite(count) || count <= 0) return;
        pulseNavTargets();
        ctx.showToast?.(targetDiscoveryMessage(count));
        if (ctx.isProjectWorkspaceOpen?.()) {
          ctx.refreshProjectWorkspace?.().catch(() => {
          });
        }
      });
    }
    return {
      bindTargetDiscoveryEvent,
      load,
      project,
      pulseNavTargets,
      render,
      setProject,
      targetDiscoveryMessage
    };
  }
  const DarklabProjectActiveContext = {
    createProjectActiveContextController
  };
  exportedDarklabProjectActiveContext = DarklabProjectActiveContext;
})(globalThis);

// app/static/js/features/projects/project_shared_ui.js
var exportedDarklabProjectSharedUi = null;
(function projectSharedUiModule(global) {
  "use strict";
  function createProjectSharedUiController(context) {
    const ctx = context || {};
    function displayName(project) {
      if (!project || typeof project !== "object") return "";
      return String(project.name || project.slug || project.id || "").trim();
    }
    function counts(summary) {
      return summary && summary.counts && typeof summary.counts === "object" ? summary.counts : {};
    }
    function countEntries(summary) {
      const currentCounts = counts(summary);
      return [
        { id: "runs", label: "runs", value: currentCounts.runs, tab: "runs" },
        { id: "entities", label: "entities", value: currentCounts.entities, tab: "entities" },
        { id: "findings", label: "findings", value: currentCounts.findings, tab: "findings" },
        { id: "artifacts", label: "artifacts", value: currentCounts.artifacts, tab: "artifacts" },
        { id: "targets", label: "targets", value: currentCounts.targets, tab: "details" },
        { id: "packages", label: "packages", value: currentCounts.packages, tab: "packages" },
        { id: "notes", label: "notes", value: currentCounts.notes, tab: "details" }
      ].map((item) => ({ ...item, value: Number(item.value || 0) }));
    }
    function targetItems(summary) {
      return summary && Array.isArray(summary.targets) ? summary.targets : [];
    }
    function targetLabel(summary, targetId) {
      const normalized = String(targetId || "").trim();
      if (!normalized) return "";
      const target = targetItems(summary).find((item) => String(item && item.id || "") === normalized);
      if (!target) return "";
      const type = String(target.type || "target").trim() || "target";
      const value = String(target.value || "").trim();
      return value ? `target ${type}: ${value}` : `target ${type}`;
    }
    function runItems(summary) {
      return summary && Array.isArray(summary.runs) ? summary.runs : [];
    }
    function runById(summary, runId) {
      const normalized = String(runId || "");
      if (!normalized) return null;
      return runItems(summary).find((run) => String(run.id || "") === normalized) || null;
    }
    function comparableRuns(summary) {
      return runItems(summary).filter((run) => run && run.id);
    }
    function shortRunId(runId) {
      return String(runId || "").trim().slice(0, 8);
    }
    function entityLabelValues(entity) {
      const labels = entity && Array.isArray(entity.labels) ? entity.labels : [];
      return labels.map((label) => String(label && typeof label === "object" ? label.label : label || "").trim()).filter(Boolean);
    }
    function entityNoteBody(entity) {
      const note = entity && entity.note && typeof entity.note === "object" ? entity.note : null;
      return note ? String(note.body || "").trim() : "";
    }
    function entityMetadataChips(entity) {
      const chips = entityLabelValues(entity).map((label) => ({ label, kind: "label" }));
      if (entityNoteBody(entity)) chips.push({ label: "note", kind: "note" });
      const triage = entity && entity.triage && typeof entity.triage === "object" ? entity.triage : null;
      if (triage) {
        const status = String(triage.verification_status || entity.verification_status || "not_started");
        if (status && status !== "not_started") {
          const label = typeof verificationStatusLabel === "function" ? verificationStatusLabel(status) : status.replace(/_/g, " ");
          const tone = typeof verificationStatusTone === "function" ? verificationStatusTone(status) : "muted";
          const kind = tone === "green" ? "success" : tone === "amber" ? "warning" : "label";
          chips.push({ label, kind });
        }
        if (triage.has_remediation) chips.push({ label: "remediation", kind: "note" });
        if (triage.has_verification_steps) chips.push({ label: "verification steps", kind: "label" });
      }
      return chips;
    }
    function entityMetadataChipClass(kind = "label") {
      const normalized = String(kind || "");
      const tone = normalized === "note" ? "badge-tone-cyan" : normalized === "success" ? "badge-tone-green" : normalized === "warning" ? "badge-tone-amber" : "badge-tone-muted";
      return `project-explorer-metadata-chip badge ${tone}`;
    }
    function readableToken(value) {
      return String(value || "").trim().replace(/[_-]+/g, " ").replace(/\s+/g, " ");
    }
    function pluralize(label, count) {
      return `${count} ${label}${count === 1 ? "" : "s"}`;
    }
    function selectedEntityCountParts(counts2) {
      const source = counts2 && typeof counts2 === "object" ? counts2 : {};
      const entries = [
        ["run", source.run_ids ?? source.runs],
        ["finding", source.finding_ids ?? source.findings],
        ["artifact", source.artifact_ids ?? source.artifacts],
        ["target", source.target_ids ?? source.targets]
      ];
      return entries.map(([label, value]) => pluralize(label, Math.max(0, Number(value || 0)))).join(", ");
    }
    function selectedCountsFromIds(selectedEntityIds) {
      const source = selectedEntityIds && typeof selectedEntityIds === "object" ? selectedEntityIds : {};
      return Object.fromEntries(
        Object.entries(source).map(([key, value]) => [key, Array.isArray(value) ? value.length : 0])
      );
    }
    function provenanceOrigins(projectLinks) {
      if (!projectLinks || typeof projectLinks !== "object") return "";
      const counts2 = projectLinks.counts_by_origin && typeof projectLinks.counts_by_origin === "object" ? projectLinks.counts_by_origin : {};
      const origins = Array.isArray(projectLinks.origin_sources) ? projectLinks.origin_sources : Object.keys(counts2);
      return { counts: counts2, origins };
    }
    function provenanceOriginSummary(projectLinks) {
      const linkOrigins = provenanceOrigins(projectLinks);
      if (!linkOrigins) return "";
      const { counts: counts2, origins } = linkOrigins;
      const parts = origins.map((origin) => {
        const normalized = String(origin || "").trim();
        if (!normalized) return "";
        const count = Number(counts2[normalized] || 0);
        return count > 0 ? `${readableToken(normalized)} (${count})` : readableToken(normalized);
      }).filter(Boolean);
      if (parts.length) return parts.join(", ");
      return projectLinks.note ? String(projectLinks.note) : "";
    }
    function provenanceOriginChip(projectLinks) {
      const linkOrigins = provenanceOrigins(projectLinks);
      const detail = provenanceOriginSummary(projectLinks);
      if (!linkOrigins) {
        return {
          label: "source: not recorded",
          title: "Project-link origin details were not recorded."
        };
      }
      const { counts: counts2, origins } = linkOrigins;
      const recordedOrigins = origins.map((origin) => String(origin || "").trim()).filter(Boolean);
      if (!recordedOrigins.length) {
        return {
          label: "source: not recorded",
          title: detail || "Project-link origin details were not recorded."
        };
      }
      if (recordedOrigins.length === 1) {
        const origin = recordedOrigins[0];
        const count = Number(counts2[origin] || 0);
        return {
          label: `source: ${readableToken(origin)}`,
          title: detail || (count > 0 ? `${readableToken(origin)} (${count})` : readableToken(origin))
        };
      }
      return {
        label: `source: ${recordedOrigins.length} types`,
        title: detail || recordedOrigins.map(readableToken).join(", ")
      };
    }
    function packageImportWarningSummary(importHints) {
      const warnings = importHints && Array.isArray(importHints.warnings) ? importHints.warnings : [];
      if (!warnings.length) return "none";
      const counts2 = /* @__PURE__ */ new Map();
      warnings.forEach((warning) => {
        const code = readableToken(warning && warning.code || "warning") || "warning";
        counts2.set(code, (counts2.get(code) || 0) + 1);
      });
      return Array.from(counts2.entries()).map(([code, count]) => count > 1 ? `${code} (${count})` : code).join(", ");
    }
    function projectProvenanceSummary(manifest, { fallbackKind = "export" } = {}) {
      const source = manifest && typeof manifest === "object" ? manifest : {};
      const provenance = source.provenance && typeof source.provenance === "object" ? source.provenance : {};
      const build = provenance.build && typeof provenance.build === "object" ? provenance.build : {};
      const privacy = provenance.privacy && typeof provenance.privacy === "object" ? provenance.privacy : {};
      const sources = provenance.sources && typeof provenance.sources === "object" ? provenance.sources : {};
      const importHints = source.import_hints && typeof source.import_hints === "object" ? source.import_hints : null;
      const rows = [];
      const schema = provenance.schema_version ? `v${provenance.schema_version} ${readableToken(provenance.kind || fallbackKind)}` : "not recorded";
      rows.push({ label: "Schema", value: schema });
      const redaction = build.redaction_mode || privacy.redaction_mode || source.redaction_mode;
      const preset = build.preset || source.preset || build.template_id || source.template_id;
      const privateNotes = Object.prototype.hasOwnProperty.call(privacy, "private_notes_included") ? privacy.private_notes_included : source.include_private_notes;
      rows.push({
        label: "Build",
        value: [
          preset ? readableToken(preset) : "",
          redaction ? readableToken(redaction) : "",
          privateNotes === void 0 ? "" : privateNotes ? "private notes included" : "private notes excluded"
        ].filter(Boolean).join(", ") || "not recorded"
      });
      const selectedCounts = build.selected_entity_counts && typeof build.selected_entity_counts === "object" ? build.selected_entity_counts : selectedCountsFromIds(build.selected_entity_ids || source.selected_entity_ids);
      rows.push({ label: "Selected", value: selectedEntityCountParts(selectedCounts) || "not recorded" });
      rows.push({
        label: "Source links",
        value: provenanceOriginSummary(sources.project_links) || "not recorded"
      });
      if (importHints) {
        rows.push({
          label: "Import hints",
          value: `${readableToken(importHints.mode || "preview only")}; warnings: ${packageImportWarningSummary(importHints)}`
        });
      }
      const hasRecordedProvenance = schema !== "not recorded" || rows.some((row) => row.label !== "Schema" && row.value && row.value !== "not recorded");
      const chips = [];
      chips.push({
        label: "provenance",
        kind: hasRecordedProvenance ? "success" : "label",
        title: hasRecordedProvenance ? schema : "Provenance was not recorded in this package format."
      });
      const origin = provenanceOriginChip(sources.project_links);
      if (origin) chips.push({ ...origin, kind: "label" });
      return { rows, chips, hasRecordedProvenance };
    }
    function projectProvenanceSummaryElement(manifest, options = {}) {
      const summary = projectProvenanceSummary(manifest, options);
      const section = document.createElement("section");
      section.className = "project-provenance-summary";
      const heading = document.createElement("h3");
      heading.textContent = options.title || "Provenance summary";
      section.appendChild(heading);
      const rows = document.createElement("div");
      rows.className = "project-provenance-summary-rows";
      summary.rows.forEach((item) => {
        const row = document.createElement("div");
        row.className = "project-provenance-summary-row";
        const label = document.createElement("span");
        label.textContent = item.label;
        const value = document.createElement("strong");
        value.textContent = item.value || "not recorded";
        row.append(label, value);
        rows.appendChild(row);
      });
      section.appendChild(rows);
      return section;
    }
    function entityTitleForEditor(entityType, entity) {
      if (entityType === "project") {
        return String(entity && (entity.name || entity.slug || entity.id) || "Project");
      }
      if (entityType === "finding") {
        return String(entity && (entity.title || entity.raw_line || entity.id) || "Finding");
      }
      if (entityType === "run") {
        return String(entity && (entity.command || entity.id) || "Run");
      }
      if (entityType === "snapshot") {
        return String(entity && (entity.label || entity.id) || "Snapshot");
      }
      if (entityType === "package") {
        return String(entity && (entity.name || entity.id) || "Package");
      }
      if (entityType === "run_file_artifact") {
        return String(entity && (entity.display_name || entity.workspace_path || entity.id) || "Artifact");
      }
      return String(entity && entity.id || "Entity");
    }
    function entityEditorLabelForType(entityType) {
      if (entityType === "finding") return "FINDING";
      if (entityType === "run") return "RUN";
      if (entityType === "snapshot") return "SNAPSHOT";
      if (entityType === "run_file_artifact") return "ARTIFACT";
      if (entityType === "project") return "PROJECT";
      if (entityType === "package") return "PACKAGE";
      if (entityType === "workspace_file") return "WORKSPACE FILE";
      if (entityType === "target") return "TARGET";
      return "METADATA";
    }
    function formatDate(value) {
      if (!value) return "";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return String(value);
      return date.toLocaleString();
    }
    function formatBytes(value) {
      const bytes = Number(value || 0);
      if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
      const units = ["B", "KB", "MB", "GB"];
      let amount = bytes;
      let unitIndex = 0;
      while (amount >= 1024 && unitIndex < units.length - 1) {
        amount /= 1024;
        unitIndex += 1;
      }
      return `${amount >= 10 || unitIndex === 0 ? amount.toFixed(0) : amount.toFixed(1)} ${units[unitIndex]}`;
    }
    function emptyPanel(text) {
      const empty = document.createElement("div");
      empty.className = "project-explorer-empty";
      empty.textContent = text;
      return empty;
    }
    function actionCapability(action) {
      const triageActions = /* @__PURE__ */ new Set([
        "bulk-delete-project-findings",
        "edit-finding-metadata"
      ]);
      const mutateActions = /* @__PURE__ */ new Set([
        "use",
        "clear",
        "archive",
        "unarchive",
        "delete",
        "edit-project-metadata",
        "bulk-unlink-project-entities",
        "unlink-project-entity",
        "open-entity-picker",
        "entity-picker-add",
        "new-target",
        "edit-target",
        "delete-target",
        "confirm-target",
        "dismiss-target",
        "edit-run-metadata",
        "edit-artifact-metadata",
        "link-last-run",
        "unlink-run",
        "package-edit",
        "package-repackage",
        "package-delete",
        "package-wizard-open",
        "package-wizard-next",
        "new-project-auto-promote-rule",
        "edit-project-auto-promote-rule",
        "save-project-auto-promote-rule",
        "apply-project-auto-promote-rule",
        "delete-project-auto-promote-rule"
      ]);
      const normalized = String(action || "");
      if (triageActions.has(normalized)) return "triage_findings";
      if (mutateActions.has(normalized)) return "mutate_projects";
      return "";
    }
    function activeTeamScopeCan2(capability) {
      const can = typeof activeTeamScopeCan === "function" ? activeTeamScopeCan : null;
      return typeof can === "function" ? can(capability) : true;
    }
    function teamScopeDeniedMessage2(capability) {
      const action = capability === "triage_findings" ? "triage team findings" : "change team projects";
      const denied = typeof teamScopeDeniedMessage === "function" ? teamScopeDeniedMessage : null;
      return typeof denied === "function" ? denied(action) : `View-only team members can't ${action}. Switch to Personal or ask for operator access.`;
    }
    function metaRow(label, value) {
      const row = document.createElement("div");
      row.className = "project-explorer-meta-row panel-row";
      const key = document.createElement("span");
      key.textContent = label;
      const val = document.createElement("span");
      val.textContent = String(value || "—");
      row.append(key, val);
      return row;
    }
    function itemRow({ title, meta = "", detail = "", badge = "", chips = [], action = null, accessory = null, forceArticle = false }) {
      const clickableButton = action && !accessory && !forceArticle;
      const row = document.createElement(clickableButton ? "button" : "article");
      row.className = `project-explorer-item panel-row${clickableButton ? " panel-row-clickable" : ""}`;
      let contentHost = row;
      if (action) {
        if (row.tagName === "BUTTON") {
          row.type = "button";
          row.classList.add("control-row");
        } else if (accessory || forceArticle) {
          contentHost = document.createElement("button");
          contentHost.type = "button";
          contentHost.className = "control-row project-explorer-item-click-target";
        }
        contentHost.dataset.projectAction = action.action;
        Object.entries(action.dataset || {}).forEach(([key, value]) => {
          contentHost.dataset[key] = value;
        });
        ctx.bindProjectRuntimePressable?.(contentHost);
      }
      const main = document.createElement("div");
      main.className = "project-explorer-item-main";
      const heading = document.createElement("div");
      heading.className = "project-explorer-item-title";
      heading.textContent = String(title || "");
      main.appendChild(heading);
      if (meta) {
        const metaEl = document.createElement("div");
        metaEl.className = "project-explorer-item-meta";
        metaEl.textContent = meta;
        main.appendChild(metaEl);
      }
      if (detail) {
        const detailEl = document.createElement("div");
        detailEl.className = "project-explorer-item-detail";
        detailEl.textContent = detail;
        main.appendChild(detailEl);
      }
      if (Array.isArray(chips) && chips.length) {
        const chipWrap = document.createElement("div");
        chipWrap.className = "project-explorer-item-chips";
        chips.forEach((chip) => {
          const chipEl = document.createElement("span");
          chipEl.className = entityMetadataChipClass(chip.kind);
          chipEl.textContent = String(chip.label || "");
          if (chip.title) chipEl.title = String(chip.title);
          chipWrap.appendChild(chipEl);
        });
        main.appendChild(chipWrap);
      }
      contentHost.appendChild(main);
      if (contentHost !== row) row.appendChild(contentHost);
      if (accessory) {
        row.appendChild(accessory);
      } else if (badge) {
        const badgeEl = document.createElement("span");
        badgeEl.className = "project-explorer-item-badge";
        badgeEl.textContent = badge;
        row.appendChild(badgeEl);
      }
      return row;
    }
    function makeButton(label, action, projectId, role = "secondary", tone = "") {
      const btn = document.createElement("button");
      btn.type = "button";
      const classes = ["btn", `btn-${role || "secondary"}`, "btn-compact"];
      if (tone) classes.push(`btn-${tone}`);
      btn.className = classes.join(" ");
      btn.textContent = label;
      btn.dataset.projectAction = action;
      if (projectId) btn.dataset.projectId = projectId;
      const capability = actionCapability(action);
      if (capability && !activeTeamScopeCan2(capability)) {
        btn.disabled = true;
        btn.title = teamScopeDeniedMessage2(capability);
      }
      ctx.bindProjectRuntimePressable?.(btn);
      return btn;
    }
    function groupBy(items, keyFn) {
      const grouped = /* @__PURE__ */ new Map();
      (Array.isArray(items) ? items : []).forEach((item) => {
        const key = String(keyFn(item) || "Other");
        if (!grouped.has(key)) grouped.set(key, []);
        grouped.get(key).push(item);
      });
      return grouped;
    }
    function downloadBlobAsAttachment2(blob, filename, successMessage = "") {
      ctx.downloadBlobAsAttachment?.(blob, filename);
      if (successMessage) ctx.setProjectWorkspaceMessage?.(successMessage);
    }
    function downloadUrlAsAttachment2(url, filename = "", successMessage = "") {
      ctx.downloadUrlAsAttachment?.(url, filename ? { filename } : {});
      if (successMessage) ctx.setProjectWorkspaceMessage?.(successMessage);
    }
    return {
      comparableRuns,
      countEntries,
      counts,
      displayName,
      downloadBlobAsAttachment: downloadBlobAsAttachment2,
      downloadUrlAsAttachment: downloadUrlAsAttachment2,
      emptyPanel,
      entityEditorLabelForType,
      entityLabelValues,
      entityMetadataChipClass,
      entityMetadataChips,
      entityNoteBody,
      entityTitleForEditor,
      formatBytes,
      formatDate,
      groupBy,
      itemRow,
      makeButton,
      metaRow,
      projectProvenanceSummary,
      projectProvenanceSummaryElement,
      runById,
      runItems,
      shortRunId,
      targetItems,
      targetLabel
    };
  }
  const DarklabProjectSharedUi = {
    createProjectSharedUiController
  };
  exportedDarklabProjectSharedUi = DarklabProjectSharedUi;
})(globalThis);

// app/static/js/features/shortcuts/global_shortcuts.js
var SHORTCUT_GLOBAL = typeof window !== "undefined" ? window : globalThis;
function shortcutGlobalFunction(name) {
  const windowFn = typeof window !== "undefined" ? window[name] : null;
  if (typeof windowFn === "function") return windowFn;
  const rootFn = SHORTCUT_GLOBAL && SHORTCUT_GLOBAL[name];
  if (typeof rootFn === "function") return rootFn;
  const globalFn = typeof globalThis !== "undefined" ? globalThis[name] : null;
  return typeof globalFn === "function" ? globalFn : null;
}
var SHORTCUT_STABLE_FUNCTION_NAMES = [
  "activateTab",
  "shouldIgnoreGlobalShortcutTarget",
  "createShortcutTab",
  "closeActiveShortcutTab",
  "activateRelativeTab",
  "permalinkActiveShortcutTab",
  "copyActiveShortcutTab",
  "clearActiveShortcutTab",
  "closeThemeSelector",
  "openThemeSelector",
  "closeWorkspace",
  "openWorkspace",
  "isSchedulesOverlayOpen",
  "openSchedulesModal",
  "closeSchedulesModal",
  "isWatchersOverlayOpen",
  "openWatchersModal",
  "closeWatchersModal",
  "isStatusMonitorShortcutOpen",
  "isStatusMonitorOpen",
  "openStatusMonitor",
  "closeStatusMonitor",
  "isAtlasOverlayOpen",
  "cycleAtlasTab",
  "openAtlas",
  "closeAtlas",
  "isCommandRegistryOverlayOpen",
  "openCommandRegistry",
  "closeCommandRegistry",
  "isProjectWorkspaceOpen",
  "cycleProjectWorkspaceTab",
  "openProjectWorkspace",
  "closeProjectWorkspace",
  "toggleHistoryPanelSurface",
  "closeWorkflows",
  "openWorkflows",
  "closeOptions",
  "openOptions",
  "toggleRailCollapsed",
  "closeFaq",
  "openFaq",
  "isHistoryRunOverlayOpen",
  "cycleHistoryRunOverlayTab"
];
var SHORTCUT_IMPORTED_FUNCTIONS = {
  activateRelativeTab,
  clearActiveShortcutTab,
  closeActiveShortcutTab,
  closeAtlas,
  closeOptions,
  closeThemeSelector,
  closeCommandRegistry,
  closeWorkspace: closeWorkspace2,
  copyActiveShortcutTab,
  createShortcutTab,
  isCommandRegistryOverlayOpen,
  isAtlasOverlayOpen,
  isHistoryRunOverlayOpen,
  isProjectWorkspaceOpen,
  isStatusMonitorShortcutOpen,
  openCommandRegistry,
  openAtlas,
  openOptions,
  openProjectWorkspace,
  openThemeSelector,
  openWorkspace,
  openFaq,
  openWorkflows,
  permalinkActiveShortcutTab,
  shouldIgnoreGlobalShortcutTarget,
  closeFaq,
  closeProjectWorkspace,
  closeWorkflows,
  cycleAtlasTab,
  cycleHistoryRunOverlayTab,
  cycleOptionsTab,
  cycleProjectWorkspaceTab,
  toggleHistoryPanelSurface,
  toggleRailCollapsed
};
var shortcutStableFunctions = new Map(
  SHORTCUT_STABLE_FUNCTION_NAMES.map((name) => [
    name,
    typeof SHORTCUT_IMPORTED_FUNCTIONS[name] === "function" ? SHORTCUT_IMPORTED_FUNCTIONS[name] : shortcutGlobalFunction(name)
  ])
);
function shortcutFunction(name) {
  let fn = shortcutGlobalFunction(name);
  if (fn) shortcutStableFunctions.set(name, fn);
  else fn = shortcutStableFunctions.get(name) || null;
  return fn;
}
function shortcutSurfaceFunction(name) {
  const imported = typeof SHORTCUT_IMPORTED_FUNCTIONS[name] === "function" ? SHORTCUT_IMPORTED_FUNCTIONS[name] : null;
  const globalFn = shortcutGlobalFunction(name);
  if (typeof imported === "function" && imported !== globalFn) {
    return (...args) => {
      const importedResult = imported(...args);
      if (importedResult || typeof globalFn !== "function") return importedResult;
      return globalFn(...args);
    };
  }
  return globalFn || shortcutStableFunctions.get(name) || null;
}
function shortcutGetTabs() {
  if (typeof getTabs === "function") return getTabs();
  const read = shortcutFunction("getTabs") || shortcutGlobalFunction("getTabs");
  return read ? read() : [];
}
function getShortcutActivateTab() {
  return shortcutFunction("activateTab") || typeof activateTab !== "undefined" && activateTab;
}
function shortcutCall(name, ...args) {
  const fn = shortcutFunction(name);
  return fn ? fn(...args) : void 0;
}
function shortcutIsOpen(name) {
  const fn = shortcutFunction(name);
  return !!(fn && fn());
}
function markShortcutHandled(e) {
  if (e && typeof e === "object") e.__darklabShortcutHandled = true;
}
function shortcutAlreadyHandled(e) {
  return !!(e && e.__darklabShortcutHandled);
}
function eventMatchesCode(e, code) {
  return !!(e && e.code === code);
}
var MAC_OPTION_KEY_ALIASES = {
  f: ["ƒ"]
};
function eventMatchesLetter(e, letter) {
  if (eventMatchesCode(e, `Key${letter.toUpperCase()}`)) return true;
  const key = e && typeof e.key === "string" ? e.key.toLowerCase() : "";
  const normalizedLetter = String(letter || "").toLowerCase();
  return key === normalizedLetter || (MAC_OPTION_KEY_ALIASES[normalizedLetter] || []).includes(key);
}
function eventMatchesDigit(e, digit) {
  if (eventMatchesCode(e, `Digit${digit}`)) return true;
  return !!(e && e.key === String(digit));
}
function _handleSurfaceTabShortcut(e) {
  if (!e || e.key !== "Tab" || !e.altKey || e.ctrlKey || e.metaKey) return false;
  const offset = e.shiftKey ? -1 : 1;
  const surfaces = [
    {
      isOpen: shortcutSurfaceFunction("isHistoryRunOverlayOpen"),
      cycle: shortcutSurfaceFunction("cycleHistoryRunOverlayTab")
    },
    {
      isOpen: shortcutSurfaceFunction("isAtlasOverlayOpen"),
      cycle: shortcutSurfaceFunction("cycleAtlasTab")
    },
    {
      isOpen: shortcutSurfaceFunction("isProjectWorkspaceOpen"),
      cycle: shortcutSurfaceFunction("cycleProjectWorkspaceTab")
    },
    {
      isOpen: typeof isOptionsOverlayOpen === "function" ? isOptionsOverlayOpen : null,
      cycle: shortcutSurfaceFunction("cycleOptionsTab")
    }
  ];
  const surface = surfaces.find((item) => item.isOpen && item.isOpen() && item.cycle);
  if (!surface || !surface.cycle(offset)) return false;
  markShortcutHandled(e);
  e.preventDefault();
  return true;
}
function handleTabShortcut(e, options = {}) {
  if (shortcutAlreadyHandled(e)) return true;
  if (!e.altKey || e.ctrlKey || e.metaKey) return false;
  if (_handleSurfaceTabShortcut(e)) return true;
  if (options && options.surfaceOnly) return false;
  if (shortcutCall("shouldIgnoreGlobalShortcutTarget", e.target)) return false;
  if (!e.shiftKey && eventMatchesLetter(e, "t")) {
    shortcutCall("createShortcutTab");
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (!e.shiftKey && eventMatchesLetter(e, "w")) {
    shortcutCall("closeActiveShortcutTab");
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (e.shiftKey && e.key === "ArrowRight") {
    shortcutCall("activateRelativeTab", 1);
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (e.shiftKey && e.key === "ArrowLeft") {
    shortcutCall("activateRelativeTab", -1);
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (e.key === "Tab") {
    shortcutCall("activateRelativeTab", e.shiftKey ? -1 : 1);
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  const matchedDigit = [1, 2, 3, 4, 5, 6, 7, 8, 9].find((digit) => eventMatchesDigit(e, digit));
  if (matchedDigit) {
    const tabIndex = matchedDigit - 1;
    const currentTabs = shortcutGetTabs();
    const activate = getShortcutActivateTab();
    if (currentTabs[tabIndex] && typeof activate === "function") {
      activate(currentTabs[tabIndex].id);
    }
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  return false;
}
function handleActionShortcut(e) {
  if (shortcutAlreadyHandled(e)) return true;
  if (shortcutCall("shouldIgnoreGlobalShortcutTarget", e.target)) return false;
  if (e.altKey && !e.ctrlKey && !e.metaKey && e.shiftKey && eventMatchesLetter(e, "p")) {
    shortcutCall("permalinkActiveShortcutTab");
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (e.altKey && !e.ctrlKey && !e.metaKey && e.shiftKey && eventMatchesLetter(e, "c")) {
    shortcutCall("copyActiveShortcutTab");
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (e.ctrlKey && !e.altKey && !e.metaKey && (e.key === "l" || e.key === "L")) {
    shortcutCall("clearActiveShortcutTab");
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (e.ctrlKey && !e.altKey && !e.metaKey && (e.key === "d" || e.key === "D")) {
    shortcutCall("closeActiveShortcutTab");
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  return false;
}
function handleChromeShortcut(e) {
  if (shortcutAlreadyHandled(e)) return true;
  if (!e.altKey || e.ctrlKey || e.metaKey) return false;
  if (_handleSurfaceTabShortcut(e)) return true;
  if (shortcutCall("shouldIgnoreGlobalShortcutTarget", e.target)) return false;
  if (e.shiftKey && eventMatchesLetter(e, "t")) {
    if (typeof isThemeOverlayOpen === "function" && isThemeOverlayOpen()) shortcutCall("closeThemeSelector");
    else shortcutCall("openThemeSelector");
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (e.shiftKey && eventMatchesLetter(e, "f")) {
    if (shortcutIsOpen("isWorkspaceOverlayOpen") || typeof isWorkspaceOverlayOpen === "function" && isWorkspaceOverlayOpen()) {
      if (shortcutFunction("closeWorkspace")) shortcutCall("closeWorkspace");
      else if (typeof hideWorkspaceOverlay === "function") hideWorkspaceOverlay();
    } else {
      shortcutCall("openWorkspace");
    }
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (e.shiftKey && eventMatchesLetter(e, "s")) {
    if (shortcutIsOpen("isSchedulesOverlayOpen")) void shortcutCall("closeSchedulesModal");
    else void shortcutCall("openSchedulesModal");
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (e.shiftKey && eventMatchesLetter(e, "w")) {
    if (shortcutIsOpen("isWatchersOverlayOpen")) void shortcutCall("closeWatchersModal");
    else void shortcutCall("openWatchersModal");
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (e.shiftKey) return false;
  if (eventMatchesLetter(e, "m")) {
    if (shortcutIsOpen("isStatusMonitorOpen") || shortcutCall("isStatusMonitorShortcutOpen")) shortcutCall("closeStatusMonitor");
    else void shortcutCall("openStatusMonitor", { source: "shortcut" });
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, "a")) {
    if (shortcutIsOpen("isAtlasOverlayOpen")) {
      shortcutCall("closeAtlas");
    } else {
      void shortcutCall("openAtlas", { source: "shortcut" });
    }
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, "c")) {
    if (shortcutIsOpen("isCommandRegistryOverlayOpen")) shortcutCall("closeCommandRegistry");
    else shortcutCall("openCommandRegistry");
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, "p")) {
    if (shortcutIsOpen("isProjectWorkspaceOpen")) shortcutCall("closeProjectWorkspace");
    else void shortcutCall("openProjectWorkspace");
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, "h")) {
    if (typeof isHistoryPanelOpen === "function" && isHistoryPanelOpen()) {
      hideHistoryPanel();
    } else {
      shortcutCall("toggleHistoryPanelSurface", true);
    }
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, "g")) {
    if (typeof isWorkflowsOverlayOpen === "function" && isWorkflowsOverlayOpen()) shortcutCall("closeWorkflows");
    else shortcutCall("openWorkflows");
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, "s")) {
    document.getElementById("search-toggle-btn")?.click();
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (eventMatchesCode(e, "Comma") || e.key === ",") {
    if (typeof isOptionsOverlayOpen === "function" && isOptionsOverlayOpen()) shortcutCall("closeOptions");
    else shortcutCall("openOptions");
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (eventMatchesCode(e, "Backslash") || e.key === "\\") {
    shortcutCall("toggleRailCollapsed");
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (eventMatchesCode(e, "Slash") || e.key === "/" || e.key === "÷") {
    if (typeof isFaqOverlayOpen === "function" && isFaqOverlayOpen()) shortcutCall("closeFaq");
    else shortcutCall("openFaq");
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  return false;
}

// app/static/js/features/terminal/mobile_composer_keyboard.js
var MOBILE_KEYBOARD_GLOBAL = typeof window !== "undefined" ? window : globalThis;
function _mobileKeyboardGlobalFunction(name) {
  const fn = MOBILE_KEYBOARD_GLOBAL?.[name];
  return typeof fn === "function" ? fn : null;
}
function _mobileKeyboardRunButton() {
  return typeof mobileRunBtn !== "undefined" && mobileRunBtn || (typeof document !== "undefined" ? document.getElementById("mobile-run-btn") : null);
}
function _mobileKeyboardRefreshFollowingOutputs() {
  const refreshOutputs = typeof _refreshFollowingOutputsAfterLayout !== "undefined" && _refreshFollowingOutputsAfterLayout || _mobileKeyboardGlobalFunction("_refreshFollowingOutputsAfterLayout");
  if (typeof refreshOutputs === "function") refreshOutputs();
}
function _mobileKeyboardSyncShellPrompt() {
  const syncPrompt = typeof hasComposerPromptHandler === "function" && hasComposerPromptHandler("syncShellPrompt") ? syncShellPrompt : _mobileKeyboardGlobalFunction("syncShellPrompt");
  if (typeof syncPrompt === "function") syncPrompt();
}
function _mobileKeyboardSetComposerState(state) {
  const setState = typeof setComposerState !== "undefined" && setComposerState || _mobileKeyboardGlobalFunction("setComposerState");
  if (typeof setState === "function") setState(state);
}
function _mobileKeyboardBlurVisibleComposer() {
  const blurComposer = typeof blurVisibleComposerInputIfMobile !== "undefined" && blurVisibleComposerInputIfMobile || _mobileKeyboardGlobalFunction("blurVisibleComposerInputIfMobile");
  if (typeof blurComposer === "function") blurComposer();
}
function _mobileKeyboardHandleComposerInputChange(input) {
  const handleInput = typeof handleComposerInputChange !== "undefined" && handleComposerInputChange || _mobileKeyboardGlobalFunction("handleComposerInputChange");
  if (typeof handleInput === "function") handleInput(input);
}
function _mobileKeyboardGetActiveTab() {
  if (typeof getActiveTab !== "undefined" && typeof getActiveTab === "function") {
    return getActiveTab();
  }
  const getActiveTab2 = _mobileKeyboardGlobalFunction("getActiveTab");
  return getActiveTab2 ? getActiveTab2() : null;
}
function _mobileKeyboardGetComposerValue(input) {
  const getValue = typeof getComposerValue !== "undefined" && getComposerValue || _mobileKeyboardGlobalFunction("getComposerValue");
  return typeof getValue === "function" ? getValue() : input && input.value || "";
}
function _mobileKeyboardSchedulePersistTabSessionState() {
  const schedulePersist = typeof schedulePersistTabSessionState !== "undefined" && schedulePersistTabSessionState || _mobileKeyboardGlobalFunction("schedulePersistTabSessionState");
  if (typeof schedulePersist === "function") schedulePersist();
}
function _mobileKeyboardSetOpen(open, options = {}) {
  const setOpen = typeof exportedSetMobileKeyboardOpenState !== "undefined" && exportedSetMobileKeyboardOpenState || _mobileKeyboardGlobalFunction("setMobileKeyboardOpenState");
  if (setOpen) setOpen(open, options);
}
function _mobileKeyboardSetViewportClosedHeight(height) {
  const setClosedHeight = typeof exportedSetMobileViewportClosedHeight !== "undefined" && exportedSetMobileViewportClosedHeight || _mobileKeyboardGlobalFunction("setMobileViewportClosedHeight");
  if (setClosedHeight) setClosedHeight(height);
}
function _mobileKeyboardSyncComposerState(offset, options = {}) {
  const syncState = typeof syncMobileComposerKeyboardState !== "undefined" && syncMobileComposerKeyboardState || _mobileKeyboardGlobalFunction("syncMobileComposerKeyboardState");
  return syncState ? syncState(offset, options) : !!options.open;
}
function _mobileKeyboardSubmitVisibleComposerCommand(options = {}) {
  const submit = typeof submitVisibleComposerCommand === "function" && submitVisibleComposerCommand || _mobileKeyboardGlobalFunction("submitVisibleComposerCommand");
  if (submit) submit(options);
}
function syncMobileViewportHeight({ keyboardOpen = null } = {}) {
  if (typeof document === "undefined" || typeof window === "undefined") return;
  const visualHeight = window.visualViewport ? Math.round(window.visualViewport.height) : 0;
  const innerHeight = Math.round(window.innerHeight || 0);
  const useKeyboardOpen = typeof keyboardOpen === "boolean" ? keyboardOpen : !!(typeof document !== "undefined" && document.body && document.body.classList && document.body.classList.contains("mobile-keyboard-open"));
  if (!useKeyboardOpen && innerHeight > 0) {
    _mobileKeyboardSetViewportClosedHeight(innerHeight);
  }
  const h = useKeyboardOpen ? visualHeight || innerHeight : Math.max(innerHeight, visualHeight);
  if (!(h > 0)) return;
  document.documentElement.style.setProperty("--mobile-viewport-height", `${h}px`);
}
function queueMobileOutputTailRefresh({ keyboardOpen = null, delays = [0, 80, 180, 320] } = {}) {
  delays.forEach((delay) => {
    setTimeout(() => {
      if (!useMobileTerminalViewportMode()) return;
      if (!document.body) return;
      if (typeof keyboardOpen === "boolean" && document.body.classList.contains("mobile-keyboard-open") !== keyboardOpen) return;
      _mobileKeyboardRefreshFollowingOutputs();
    }, delay);
  });
}
function syncMobileComposerKeyboard({ open = null } = {}) {
  if (typeof window === "undefined") return;
  const offset = getMobileKeyboardOffset();
  const keyboardOpen = _mobileKeyboardSyncComposerState(offset, { open });
  syncMobileViewportHeight({ keyboardOpen });
  queueMobileOutputTailRefresh({ keyboardOpen, delays: keyboardOpen ? [0] : [0, 80, 180, 320] });
}
var _mobileComposerKeyboardSyncTimer = null;
function queueMobileComposerKeyboardSync(delay = 120) {
  if (typeof window === "undefined") return;
  if (_mobileComposerKeyboardSyncTimer) clearTimeout(_mobileComposerKeyboardSyncTimer);
  _mobileComposerKeyboardSyncTimer = setTimeout(() => {
    _mobileComposerKeyboardSyncTimer = null;
    syncMobileComposerKeyboard();
  }, delay);
}
function bindMobileComposerKeyboardListeners(mobileInput) {
  if (!mobileInput || typeof window === "undefined") return;
  const closeMobileKeyboard = (delay = 120) => {
    _mobileKeyboardSetOpen(false, { delay });
  };
  const resetClosedMobileKeyboardLayout = () => {
    _mobileKeyboardSyncComposerState(0, { open: false });
    syncMobileViewportHeight({ keyboardOpen: false });
  };
  const queueMobileViewportRecovery = (delays = [50, 180]) => {
    delays.forEach((delay) => {
      setTimeout(() => {
        syncMobileComposerKeyboard();
        syncMobileViewportState();
      }, delay);
    });
  };
  if (window.visualViewport && typeof window.visualViewport.addEventListener === "function") {
    window.visualViewport.addEventListener("resize", () => {
      syncMobileComposerKeyboard();
      queueMobileComposerKeyboardSync();
    });
  }
  mobileInput.addEventListener("focus", () => {
    _mobileKeyboardSetComposerState({
      value: mobileInput.value || "",
      selectionStart: typeof mobileInput.selectionStart === "number" ? mobileInput.selectionStart : (mobileInput.value || "").length,
      selectionEnd: typeof mobileInput.selectionEnd === "number" ? mobileInput.selectionEnd : (mobileInput.value || "").length,
      activeInput: "mobile"
    });
    _mobileKeyboardSetOpen(true);
    syncMobileComposerKeyboard();
    queueMobileComposerKeyboardSync();
  });
  mobileInput.addEventListener("blur", () => {
    closeMobileKeyboard();
    syncMobileComposerKeyboard();
    queueMobileComposerKeyboardSync();
  });
  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        closeMobileKeyboard(0);
        _mobileKeyboardBlurVisibleComposer();
        resetClosedMobileKeyboardLayout();
        return;
      }
      queueMobileViewportRecovery();
    });
  }
  window.addEventListener("focus", () => {
    queueMobileViewportRecovery([80, 220]);
  });
  window.addEventListener("pageshow", () => {
    queueMobileViewportRecovery([0, 120]);
  });
}
function bindMobileComposerSubmitAndInputListeners(mobileInput) {
  const runButton = _mobileKeyboardRunButton();
  if (!mobileInput || !runButton) return;
  function _mobileSubmit() {
    _mobileKeyboardSubmitVisibleComposerCommand({ dismissKeyboard: true, focusAfterSubmit: false });
  }
  runButton.addEventListener("click", _mobileSubmit);
  mobileInput.addEventListener("input", () => {
    _mobileKeyboardHandleComposerInputChange(mobileInput);
    const activeTab = _mobileKeyboardGetActiveTab();
    if (activeTab && activeTab.st !== "running") {
      activeTab.draftInput = _mobileKeyboardGetComposerValue(mobileInput);
      _mobileKeyboardSchedulePersistTabSessionState();
    }
  });
  mobileInput.addEventListener("keydown", (e) => {
    if (typeof handleComposerWordArrowShortcut === "function" && handleComposerWordArrowShortcut(e)) return;
    if (e.key === "Enter") {
      e.preventDefault();
      _mobileSubmit();
    }
  });
  mobileInput.addEventListener("click", () => {
    if (!useMobileTerminalViewportMode()) return;
    if (typeof document === "undefined" || document.activeElement !== mobileInput) return;
    const savedStart = mobileInput.selectionStart;
    const savedEnd = mobileInput.selectionEnd;
    const valueLen = (mobileInput.value || "").length;
    if (typeof savedStart !== "number" || savedStart >= valueLen) return;
    setTimeout(() => {
      if (typeof document === "undefined" || document.activeElement !== mobileInput) return;
      if (mobileInput.selectionStart >= (mobileInput.value || "").length) {
        mobileInput.setSelectionRange(savedStart, savedEnd);
      }
      _mobileKeyboardSetComposerState({
        value: mobileInput.value || "",
        selectionStart: typeof mobileInput.selectionStart === "number" ? mobileInput.selectionStart : (mobileInput.value || "").length,
        selectionEnd: typeof mobileInput.selectionEnd === "number" ? mobileInput.selectionEnd : (mobileInput.value || "").length,
        activeInput: "mobile"
      });
      _mobileKeyboardSyncShellPrompt();
    }, 0);
  });
}
if (typeof window !== "undefined") {
}

// app/static/js/features/mobile/mobile_menu_actions.js
var MOBILE_MENU_ACTIONS_GLOBAL = typeof window !== "undefined" ? window : globalThis;
function _mobileMenuGlobalFunction(name) {
  const fn = MOBILE_MENU_ACTIONS_GLOBAL && MOBILE_MENU_ACTIONS_GLOBAL[name];
  return typeof fn === "function" ? fn : null;
}
function _mobileMenuCall(name, ...args) {
  const fn = _mobileMenuGlobalFunction(name);
  if (typeof fn === "function") return fn(...args);
  return void 0;
}
function _mobileMenuImportedCall(importedFn, name, ...args) {
  const fn = typeof importedFn === "function" ? importedFn : _mobileMenuGlobalFunction(name);
  if (typeof fn === "function") return fn(...args);
  return void 0;
}
function _mobileMenuActiveTabId() {
  if (typeof getActiveTabId === "function") return getActiveTabId();
  return MOBILE_MENU_ACTIONS_GLOBAL.activeTabId || null;
}
function _mobileMenuBlurComposer() {
  const blurComposer = (typeof blurVisibleComposerInputIfMobile === "function" ? blurVisibleComposerInputIfMobile : null) || _mobileMenuGlobalFunction("blurVisibleComposerInputIfMobile");
  if (blurComposer) blurComposer();
}
function _mobileMenuRefocusComposer(options = { defer: true }) {
  const refocusComposer = (typeof refocusComposerAfterAction === "function" ? refocusComposerAfterAction : null) || _mobileMenuGlobalFunction("refocusComposerAfterAction");
  if (refocusComposer) refocusComposer(options);
}
function _mobileMenuLineNumberMode() {
  if (typeof getLineNumberMode === "function") return getLineNumberMode();
  return MOBILE_MENU_ACTIONS_GLOBAL.lnMode || "off";
}
function dispatchMobileMenuAction(action, btn = null) {
  if (action === "search") {
    const visible = isSearchBarOpen();
    if (visible) {
      hideSearchBar();
      _mobileMenuCall("clearSearch");
    } else {
      _mobileMenuCall("openSearchFromSignal");
    }
  }
  if (action === "history") {
    _mobileMenuImportedCall(closeMajorOverlays, "_closeMajorOverlays");
    const isOpen = togglePanelOverlay(historyPanel);
    if (isOpen) {
      _mobileMenuImportedCall(resetHistoryMobileFilters, "resetHistoryMobileFilters");
      _mobileMenuBlurComposer();
      _mobileMenuImportedCall(refreshHistoryPanel, "refreshHistoryPanel");
    }
  }
  if (action === "ts-toggle") {
    return;
  }
  if (action === "ts-set") {
    applyTimestampPreference(btn?.dataset.tsMode || "off");
    _mobileMenuRefocusComposer({ defer: true });
  }
  if (action === "ln") {
    applyLineNumberPreference(_mobileMenuLineNumberMode() === "on" ? "off" : "on");
    _mobileMenuRefocusComposer({ defer: true });
  }
  if (action === "clear") {
    const activeId = _mobileMenuActiveTabId();
    if (activeId) {
      _mobileMenuCall("cancelWelcome", activeId);
      if (typeof clearTab2 === "function") clearTab2(activeId, { preserveRunState: true });
    }
    _mobileMenuRefocusComposer({ defer: true });
  }
  if (action === "options") _mobileMenuImportedCall(openOptions, "openOptions");
  if (action === "scope" && typeof openTeamScopeSelector === "function") openTeamScopeSelector();
  if (action === "projects") void _mobileMenuImportedCall(openProjectWorkspace, "openProjectWorkspace");
  if (action === "atlas") void _mobileMenuImportedCall(openAtlas, "openAtlas", { source: "mobile-menu" });
  if (action === "status-monitor") void _mobileMenuImportedCall(openStatusMonitor, "openStatusMonitor", { source: "mobile-menu" });
  if (action === "command-registry") _mobileMenuImportedCall(openCommandRegistry, "openCommandRegistry");
  if (action === "theme") _mobileMenuImportedCall(openThemeSelector, "openThemeSelector");
  if (action === "workflows") _mobileMenuImportedCall(openWorkflows, "openWorkflows");
  if (action === "schedules") void _mobileMenuCall("openSchedulesModal");
  if (action === "watchers") void _mobileMenuCall("openWatchersModal");
  if (action === "findings-board") void _mobileMenuCall("openFindingsBoard", { source: "mobile-menu" });
  if (action === "workspace") _mobileMenuImportedCall(openWorkspace, "openWorkspace");
  if (action === "faq") _mobileMenuImportedCall(openFaq, "openFaq");
  if (action === "diag") MOBILE_MENU_ACTIONS_GLOBAL.location.href = "/diag";
}
if (typeof window !== "undefined") {
}

// app/static/js/controller.js
var closeAtlas2 = (...args) => _controllerFn("closeAtlas", closeAtlas)?.(...args);
var closeCommandCatalogModal2 = (...args) => _controllerFn(
  "closeCommandCatalogModal",
  closeCommandCatalogModal
)?.(...args);
var closeProviderStatusModal2 = (...args) => {
  const fn = typeof hasSecretsHandler === "function" && hasSecretsHandler("closeProviderStatusModal") && typeof closeProviderStatusModal === "function" ? closeProviderStatusModal : _controllerFn("closeProviderStatusModal");
  return typeof fn === "function" ? fn(...args) : void 0;
};
var closeProjectWorkspace2 = (...args) => _controllerFn("closeProjectWorkspace", closeProjectWorkspace)?.(...args);
var closeSchedulesModal = (...args) => _controllerFn("closeSchedulesModal")?.(...args);
var closeWatchersModal = (...args) => _controllerFn("closeWatchersModal")?.(...args);
var closeWorkflowEditor2 = (...args) => _controllerFn("closeWorkflowEditor", closeWorkflowEditor)?.(...args);
var ensureWorkflowCatalogLoaded2 = (...args) => _controllerFn("ensureWorkflowCatalogLoaded", ensureWorkflowCatalogLoaded)?.(...args);
var isAtlasOverlayOpen2 = (...args) => !!_controllerFn("isAtlasOverlayOpen", isAtlasOverlayOpen)?.(...args);
var isCommandCatalogOverlayOpen2 = (...args) => !!_controllerFn(
  "isCommandCatalogOverlayOpen",
  isCommandCatalogOverlayOpen
)?.(...args);
var isHistoryCompareOverlayOpen = (...args) => !!_controllerFn("isHistoryCompareOverlayOpen")?.(...args);
var isHistoryRunOverlayOpen2 = (...args) => !!_controllerFn("isHistoryRunOverlayOpen", isHistoryRunOverlayOpen)?.(...args);
var isProviderStatusModalOpen2 = (...args) => {
  const fn = typeof hasSecretsHandler === "function" && hasSecretsHandler("isProviderStatusModalOpen") && typeof isProviderStatusModalOpen === "function" ? isProviderStatusModalOpen : _controllerFn("isProviderStatusModalOpen");
  return !!fn?.(...args);
};
var isProjectWorkspaceOpen2 = (...args) => !!_controllerFn("isProjectWorkspaceOpen", isProjectWorkspaceOpen)?.(...args);
var isSchedulesOverlayOpen = (...args) => !!_controllerFn("isSchedulesOverlayOpen")?.(...args);
var isWatchersOverlayOpen = (...args) => !!_controllerFn("isWatchersOverlayOpen")?.(...args);
var loadWorkflows = (...args) => _controllerFn("loadWorkflows")?.(...args);
var openWorkflowEditor2 = (...args) => _controllerFn("openWorkflowEditor", openWorkflowEditor)?.(...args);
var renderWorkflowItems2 = (...args) => _controllerFn("renderWorkflowItems", renderWorkflowItems)?.(...args);
var CONTROLLER_GLOBAL = typeof window !== "undefined" ? window : globalThis;
function _controllerFn(name, imported = null) {
  if (typeof imported === "function") return imported;
  const fn = CONTROLLER_GLOBAL && CONTROLLER_GLOBAL[name];
  return typeof fn === "function" ? fn : null;
}
function _controllerActiveTabId() {
  const importedValue = typeof getActiveTabId === "function" ? getActiveTabId() : null;
  if (importedValue) return importedValue;
  const readActive = CONTROLLER_GLOBAL && CONTROLLER_GLOBAL.getActiveTabId;
  if (typeof readActive === "function") {
    const value = readActive();
    if (value) return value;
  }
  return CONTROLLER_GLOBAL?.activeTabId || CONTROLLER_GLOBAL?.APP_STATE?.activeTabId || null;
}
function _controllerTabs() {
  const tabs = _controllerFn("getTabs", getTabs)?.();
  return Array.isArray(tabs) ? tabs : [];
}
function _controllerState() {
  return _controllerFn("getAppState", getAppState)?.() || {};
}
function _controllerWelcomeState() {
  return _controllerFn("getWelcomeState", getWelcomeState)?.() || {};
}
function _controllerSearchCaseSensitive() {
  return !!_controllerState().searchCaseSensitive;
}
function _controllerSetSearchCaseSensitive(value) {
  _controllerState().searchCaseSensitive = !!value;
}
function _controllerSearchRegexMode() {
  return !!_controllerState().searchRegexMode;
}
function _controllerSetSearchRegexMode(value) {
  _controllerState().searchRegexMode = !!value;
}
function _controllerSetWelcomeState(next) {
  return _controllerFn("setWelcomeState", setWelcomeState)?.(next);
}
function _controllerAutocompleteState() {
  return _controllerFn("getAutocompleteState", getAutocompleteState)?.() || {};
}
function _controllerSetAutocompleteState(next) {
  return _controllerFn("setAutocompleteState", setAutocompleteState)?.(next);
}
var _controllerCommandRegistryData = null;
function _controllerSetCommandRegistryData(data) {
  _controllerCommandRegistryData = data || null;
  if (typeof setCommandRegistryData === "function") setCommandRegistryData(data);
  return _controllerCommandRegistryData;
}
renderThemeSelectionOptions();
var initialThemeName = _savedThemeName();
var initialTheme = initialThemeName ? _findThemeEntry(initialThemeName) : null;
var resolvedInitialTheme = initialTheme || _defaultThemeEntry();
if (resolvedInitialTheme) applyThemeSelection(resolvedInitialTheme.name, false);
else syncThemeSelectionControls();
function _welcomeApi(name) {
  return typeof window !== "undefined" && window[name] || typeof globalThis !== "undefined" && globalThis[name] || (name === "runWelcome" && typeof runWelcome !== "undefined" ? runWelcome : null) || (name === "welcomeOwnsTab" && typeof welcomeOwnsTab2 !== "undefined" ? welcomeOwnsTab2 : null) || (name === "requestWelcomeSettle" && typeof requestWelcomeSettle2 !== "undefined" ? requestWelcomeSettle2 : null);
}
function _welcomeActiveNow() {
  return !!_controllerWelcomeState().active;
}
function _welcomeDoneNow() {
  return !!_controllerWelcomeState().done;
}
function _setWelcomeBootPending(value) {
  _controllerSetWelcomeState({ bootPending: !!value });
}
function _setWelcomePromptAfterSettle(value) {
  _controllerSetWelcomeState({ promptAfterSettle: !!value });
}
function _welcomeOwns(tabId) {
  const owns = _welcomeApi("welcomeOwnsTab");
  return typeof owns === "function" && owns(tabId);
}
function _requestWelcomeSettle(tabId) {
  const settle = _welcomeApi("requestWelcomeSettle");
  return typeof settle === "function" ? settle(tabId) : false;
}
function _readControllerAutocompleteState() {
  const apiState = _controllerAutocompleteState();
  return {
    filtered: Array.isArray(apiState.filtered) ? apiState.filtered : [],
    index: apiState.index ?? -1
  };
}
function _writeControllerAutocompleteState(next = {}) {
  _controllerSetAutocompleteState(next);
  return _readControllerAutocompleteState();
}
function _runWelcomeIntro() {
  const run = _welcomeApi("runWelcome");
  if (typeof run === "function") run();
}
tsBtn.addEventListener("click", () => {
  const current = typeof getTimestampMode === "function" ? getTimestampMode() : "off";
  applyTimestampPreference(_tsModes[(_tsModes.indexOf(current) + 1) % _tsModes.length]);
  refocusComposerAfterAction({ defer: true });
});
lnBtn.addEventListener("click", () => {
  const current = typeof getLineNumberMode === "function" ? getLineNumberMode() : "off";
  applyLineNumberPreference(current === "on" ? "off" : "on");
  refocusComposerAfterAction({ defer: true });
});
function openWorkflows2(options = {}) {
  closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === "function") blurVisibleComposerInputIfMobile();
  const scopedItems = Array.isArray(options.items) ? options.items : null;
  if (workflowsOverlay) {
    if (scopedItems) workflowsOverlay.dataset.workflowScoped = "1";
    else delete workflowsOverlay.dataset.workflowScoped;
  }
  showWorkflowsOverlay();
  if (scopedItems) {
    if (typeof renderWorkflowItems2 === "function") {
      renderWorkflowItems2(scopedItems, { emitCatalogEvent: options.emitCatalogEvent !== false });
    }
    if (typeof markInteractionSurfaceReady === "function") {
      markInteractionSurfaceReady("workflows", workflowsOverlay, document.getElementById("workflows-modal"));
    }
    return Promise.resolve(scopedItems);
  }
  const workflowsReady = typeof loadWorkflows === "function" ? loadWorkflows() : Promise.resolve();
  return workflowsReady.then(() => {
    if (typeof ensureWorkflowCatalogLoaded2 !== "function") return null;
    return ensureWorkflowCatalogLoaded2().catch((err) => {
      logClientError2("failed to load /workflows while opening modal", err);
      return null;
    });
  }).catch((err) => {
    logClientError2("failed to load workflows controller", err);
  }).finally(() => {
    if (typeof markInteractionSurfaceReady === "function") {
      markInteractionSurfaceReady("workflows", workflowsOverlay, document.getElementById("workflows-modal"));
    }
  });
}
function closeWorkflows2() {
  if (workflowsOverlay) delete workflowsOverlay.dataset.workflowScoped;
  hideWorkflowsOverlay();
  if (typeof emitUiEvent === "function") emitUiEvent("app:workflows-closed", {});
  refocusComposerAfterAction({ defer: true });
}
function openWorkflowEditorFromButton() {
  if (typeof openWorkflowEditor2 === "function") {
    openWorkflowEditor2();
  } else if (typeof loadWorkflows === "function") {
    loadWorkflows().then(() => {
      if (typeof openWorkflowEditor2 === "function") openWorkflowEditor2();
    }).catch((err) => {
      logClientError2("failed to load workflow editor", err);
    });
  }
}
document.querySelectorAll("#workflow-new-btn, #rail-workflow-new-btn").forEach((btn) => {
  if (btn.dataset.workflowEditorOpenBound === "1") return;
  btn.dataset.workflowEditorOpenBound = "1";
  btn.addEventListener("click", openWorkflowEditorFromButton);
});
function openFaq2() {
  closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === "function") blurVisibleComposerInputIfMobile();
  showFaqOverlay();
  if (typeof applyFaqHashTarget === "function") applyFaqHashTarget();
  if (typeof markInteractionSurfaceReady === "function") {
    markInteractionSurfaceReady("faq", faqOverlay, document.getElementById("faq-modal"));
  }
}
function closeFaq2() {
  if (typeof clearFaqHash === "function") clearFaqHash();
  hideFaqOverlay();
  refocusComposerAfterAction({ defer: true });
}
function closeCommandRegistryPanel() {
  if (typeof closeCommandRegistry === "function") closeCommandRegistry();
}
function openShortcuts() {
  closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === "function") blurVisibleComposerInputIfMobile();
  if (typeof showShortcutsOverlay === "function") showShortcutsOverlay();
  if (typeof markInteractionSurfaceReady === "function") {
    markInteractionSurfaceReady("shortcuts", shortcutsOverlay, document.getElementById("shortcuts-modal"));
  }
}
function closeShortcuts() {
  if (typeof hideShortcutsOverlay === "function") hideShortcutsOverlay();
  refocusComposerAfterAction({ defer: true });
}
function toggleHistoryPanelSurface2(force = null) {
  closeMajorOverlays();
  const isOpen = togglePanelOverlay(historyPanel, force);
  if (isOpen) {
    if (typeof resetHistoryMobileFilters2 === "function") resetHistoryMobileFilters2();
    if (typeof blurVisibleComposerInputIfMobile === "function") blurVisibleComposerInputIfMobile();
    refreshHistoryPanel2();
  } else {
    if (typeof _historyResetSelectionOnClose === "function") _historyResetSelectionOnClose();
    refocusComposerAfterAction({ defer: true });
  }
  return isOpen;
}
function renderShortcuts(data) {
  const listEl = document.getElementById("shortcuts-list");
  if (!listEl) return;
  listEl.textContent = "";
  const sections = Array.isArray(data && data.sections) ? data.sections : [];
  for (const section of sections) {
    const items = Array.isArray(section && section.items) ? section.items : [];
    if (!items.length) continue;
    const sectionEl = document.createElement("div");
    sectionEl.className = "shortcuts-section";
    const headingEl = document.createElement("div");
    headingEl.className = "shortcut-section-title";
    headingEl.textContent = section.title || "";
    sectionEl.appendChild(headingEl);
    const pairsEl = document.createElement("div");
    pairsEl.className = "shortcuts-pairs";
    for (const item of items) {
      const keyEl = document.createElement("div");
      keyEl.className = "shortcut-key";
      keyEl.textContent = item.key || "";
      const descEl = document.createElement("div");
      descEl.className = "shortcut-desc";
      descEl.textContent = item.description || "";
      pairsEl.appendChild(keyEl);
      pairsEl.appendChild(descEl);
    }
    sectionEl.appendChild(pairsEl);
    listEl.appendChild(sectionEl);
  }
}
function setupMobileSheetDragClose() {
  if (typeof bindMobileSheet !== "function") return;
  const faqModal = document.getElementById("faq-modal");
  const optionsModal = document.getElementById("options-modal");
  const workspaceModal = document.getElementById("workspace-modal");
  const workflowsModal = document.getElementById("workflows-modal");
  const workflowEditor = document.getElementById("workflow-editor-form");
  const projectWorkspaceModal = document.getElementById("project-workspace-modal");
  const providerStatusModal = document.getElementById("provider-status-modal");
  const atlasSurface = document.getElementById("atlas-surface");
  const schedulesModal = document.getElementById("schedules-modal");
  const watchersModal = document.getElementById("watchers-modal");
  bindMobileSheet(mobileMenu, { onClose: () => hideMobileMenu() });
  bindMobileSheet(historyPanel, { onClose: () => hideHistoryPanel() });
  bindMobileSheet(workflowsModal, { onClose: () => closeWorkflows2() });
  bindMobileSheet(workspaceModal, { onClose: () => {
    if (typeof closeWorkspace2 === "function") closeWorkspace2();
  } });
  bindMobileSheet(workflowEditor, { onClose: () => {
    if (typeof closeWorkflowEditor2 === "function") closeWorkflowEditor2();
  } });
  bindMobileSheet(faqModal, { onClose: () => closeFaq2() });
  bindMobileSheet(document.getElementById("command-registry-modal"), { onClose: () => closeCommandRegistryPanel() });
  bindMobileSheet(projectWorkspaceModal, { onClose: () => {
    if (typeof closeProjectWorkspace2 === "function") closeProjectWorkspace2();
  } });
  bindMobileSheet(optionsModal, { onClose: () => closeOptions() });
  bindMobileSheet(providerStatusModal, { onClose: () => {
    if (typeof closeProviderStatusModal2 === "function") closeProviderStatusModal2();
  } });
  bindMobileSheet(atlasSurface, { onClose: () => {
    if (typeof closeAtlas2 === "function") closeAtlas2();
  } });
  bindMobileSheet(schedulesModal, { onClose: () => {
    if (typeof closeSchedulesModal === "function") closeSchedulesModal();
  } });
  bindMobileSheet(watchersModal, { onClose: () => {
    if (typeof closeWatchersModal === "function") closeWatchersModal();
  } });
}
function setupDismissibleOverlays() {
  if (typeof bindDismissible !== "function") return;
  const shortcutsOverlayEl = document.getElementById("shortcuts-overlay");
  const shortcutsCloseBtn = shortcutsOverlayEl?.querySelector(".shortcuts-close");
  const workflowEditorOverlay = document.getElementById("workflow-editor-overlay");
  const workflowEditorCloseBtns = workflowEditorOverlay?.querySelectorAll(".workflow-editor-close");
  const projectWorkspaceOverlay = document.getElementById("project-workspace-overlay");
  const projectWorkspaceCloseBtn = projectWorkspaceOverlay?.querySelector(".project-workspace-close");
  const providerStatusOverlay = document.getElementById("provider-status-overlay");
  const providerStatusCloseBtn = providerStatusOverlay?.querySelector(".provider-status-close");
  const schedulesOverlay = document.getElementById("schedules-overlay");
  const schedulesCloseBtns = schedulesOverlay?.querySelectorAll(".schedules-close, .sheet-grab");
  const watchersOverlay = document.getElementById("watchers-overlay");
  const watchersCloseBtns = watchersOverlay?.querySelectorAll(".watchers-close, .sheet-grab");
  bindDismissible(_uiOverlayRefs.workflowsOverlay, {
    level: "panel",
    isOpen: isWorkflowsOverlayOpen,
    onClose: closeWorkflows2,
    closeButtons: workflowsCloseBtn
  });
  bindDismissible(_uiOverlayRefs.workspaceOverlay, {
    level: "panel",
    isOpen: () => !!(_uiOverlayRefs.workspaceOverlay && _uiOverlayRefs.workspaceOverlay.classList.contains("open")),
    onClose: () => {
      if (typeof closeWorkspace2 === "function") closeWorkspace2();
    },
    closeButtons: typeof workspaceCloseBtn !== "undefined" ? workspaceCloseBtn : null
  });
  bindDismissible(_uiOverlayRefs.workspaceViewerOverlay, {
    level: "modal",
    isOpen: () => typeof workspaceViewerOverlay !== "undefined" && workspaceViewerOverlay && !workspaceViewerOverlay.classList.contains("u-hidden"),
    onClose: () => {
      if (typeof hideWorkspaceViewer === "function") hideWorkspaceViewer();
    },
    closeButtons: typeof workspaceCloseViewerBtn !== "undefined" ? workspaceCloseViewerBtn : null
  });
  bindDismissible(_uiOverlayRefs.workspaceEditorOverlay, {
    level: "modal",
    isOpen: () => typeof workspaceEditorOverlay !== "undefined" && workspaceEditorOverlay && !workspaceEditorOverlay.classList.contains("u-hidden"),
    onClose: () => {
      if (typeof hideWorkspaceEditor === "function") hideWorkspaceEditor();
    },
    closeButtons: typeof workspaceCancelEditBtn !== "undefined" ? workspaceCancelEditBtn : null
  });
  bindDismissible(workflowEditorOverlay, {
    level: "modal",
    isOpen: () => !!(workflowEditorOverlay && !workflowEditorOverlay.classList.contains("u-hidden")),
    onClose: () => {
      if (typeof closeWorkflowEditor2 === "function") closeWorkflowEditor2();
    },
    closeButtons: workflowEditorCloseBtns
  });
  bindDismissible(_uiOverlayRefs.faqOverlay, {
    level: "panel",
    isOpen: isFaqOverlayOpen,
    onClose: closeFaq2,
    closeButtons: faqCloseBtn
  });
  bindDismissible(_uiOverlayRefs.commandRegistryOverlay, {
    level: "panel",
    isOpen: () => typeof isCommandRegistryOverlayOpen === "function" && isCommandRegistryOverlayOpen(),
    onClose: closeCommandRegistryPanel,
    closeButtons: typeof commandRegistryCloseBtn !== "undefined" ? commandRegistryCloseBtn : null
  });
  bindDismissible(projectWorkspaceOverlay, {
    level: "modal",
    isOpen: () => typeof isProjectWorkspaceOpen2 === "function" && isProjectWorkspaceOpen2(),
    onClose: () => {
      if (typeof closeProjectWorkspace2 === "function") closeProjectWorkspace2();
    },
    closeButtons: projectWorkspaceCloseBtn
  });
  bindDismissible(commandCatalogOverlay, {
    level: "modal",
    isOpen: () => typeof isCommandCatalogOverlayOpen2 === "function" && isCommandCatalogOverlayOpen2(),
    onClose: () => {
      if (typeof closeCommandCatalogModal2 === "function") closeCommandCatalogModal2();
    },
    closeButtons: commandCatalogCloseBtn
  });
  bindDismissible(providerStatusOverlay, {
    level: "modal",
    isOpen: () => typeof isProviderStatusModalOpen2 === "function" && isProviderStatusModalOpen2(),
    onClose: () => {
      if (typeof closeProviderStatusModal2 === "function") closeProviderStatusModal2();
    },
    closeButtons: providerStatusCloseBtn
  });
  bindDismissible(schedulesOverlay, {
    level: "modal",
    isOpen: () => typeof isSchedulesOverlayOpen === "function" && isSchedulesOverlayOpen(),
    onClose: () => {
      if (typeof closeSchedulesModal === "function") closeSchedulesModal();
    },
    closeButtons: schedulesCloseBtns
  });
  bindDismissible(watchersOverlay, {
    level: "modal",
    isOpen: () => typeof isWatchersOverlayOpen === "function" && isWatchersOverlayOpen(),
    onClose: () => {
      if (typeof closeWatchersModal === "function") closeWatchersModal();
    },
    closeButtons: watchersCloseBtns
  });
  bindDismissible(_uiOverlayRefs.themeOverlay, {
    level: "panel",
    isOpen: isThemeOverlayOpen,
    onClose: closeThemeSelector,
    closeButtons: themeCloseBtn
  });
  bindDismissible(_uiOverlayRefs.optionsOverlay, {
    level: "panel",
    isOpen: isOptionsOverlayOpen,
    onClose: closeOptions,
    closeButtons: optionsCloseBtn
  });
  bindDismissible(shortcutsOverlayEl, {
    level: "panel",
    isOpen: isShortcutsOverlayOpen,
    onClose: closeShortcuts,
    closeButtons: shortcutsCloseBtn
  });
  bindDismissible(historyPanel, {
    level: "panel",
    isOpen: isHistoryPanelOpen,
    onClose: () => {
      if (typeof resetHistoryMobileFilters2 === "function") resetHistoryMobileFilters2();
      hideHistoryPanel();
    },
    closeButtons: historyCloseBtn,
    // historyPanel is an aside, not a modal backdrop — outside click
    // dismissal is handled by the ambient-click listener in the global
    // click handler below, not by backdrop-click here.
    closeOnBackdrop: false
  });
}
function setupModalFocusTraps() {
  if (typeof bindFocusTrap !== "function") return;
  const ids = [
    "options-modal",
    "theme-modal",
    "faq-modal",
    "command-registry-modal",
    "provider-status-modal",
    "findings-board-modal",
    "finding-triage-modal",
    "atlas-import-modal",
    "project-workspace-modal",
    "project-target-editor-modal",
    "project-package-manifest-modal",
    "project-package-wizard-modal",
    "project-entity-editor-modal",
    "workspace-modal",
    "workflows-modal",
    "workflow-editor-form",
    "schedules-modal",
    "watchers-modal",
    "team-scope-modal"
  ];
  ids.forEach((id) => {
    const card = document.getElementById(id);
    if (card) bindFocusTrap(card);
  });
}
function setupMobileComposer() {
  const composerInputs = typeof getComposerInputs === "function" ? getComposerInputs() : {};
  const mobileInput = composerInputs.mobile || null;
  if (!mobileInput || !mobileRunBtn) return;
  bindMobileComposerSubmitAndInputListeners(mobileInput);
  bindMobileComposerKeyboardListeners(mobileInput);
  if (mobileShellTranscript) {
    const closeKeyboardFromTranscript = (e) => {
      const interactiveTarget = e && e.target && e.target.closest && e.target.closest('button, a, input, textarea, select, [contenteditable="true"], .hist-chip');
      if (interactiveTarget) return;
      if (isMobileKeyboardOpen() && typeof blurVisibleComposerInputIfMobile === "function") {
        if (typeof exportedSetMobileKeyboardOpenState === "function") exportedSetMobileKeyboardOpenState(false, { delay: 120 });
        blurVisibleComposerInputIfMobile();
      }
    };
    mobileShellTranscript.addEventListener("click", closeKeyboardFromTranscript);
  }
}
apiFetch2("/config").then((r) => r.json()).then((cfg) => {
  if (typeof window !== "undefined" && window.DarklabConfig && typeof window.DarklabConfig.setAppConfig === "function") {
    window.DarklabConfig.setAppConfig(cfg);
  } else if (typeof window !== "undefined") {
    window.APP_CONFIG = cfg;
  }
  document.title = cfg.app_name;
  if (headerTitle) headerTitle.textContent = cfg.app_name;
  const railWordmarkTitle = document.getElementById("rail-wordmark-title");
  if (railWordmarkTitle) {
    railWordmarkTitle.textContent = cfg.app_name;
    railWordmarkTitle.title = cfg.app_name;
  }
  const wmVersion = cfg.version ? ` v${cfg.version}` : "";
  const projectText = `${cfg.project_name || "darklab_shell"}${wmVersion}`;
  document.querySelectorAll(".menu-footer, .rail-nav-version").forEach((el) => {
    el.textContent = projectText;
    if (cfg.project_readme) el.href = cfg.project_readme;
  });
  syncThemeSelectionControls();
  updateNewTabBtn();
  if (typeof renderFaqLimits === "function") renderFaqLimits(cfg);
  if (cfg.diag_enabled) {
    const railDiagBtn = document.getElementById("rail-diag-btn");
    if (railDiagBtn) railDiagBtn.classList.remove("u-hidden");
    const mobileDiagBtn = _uiOverlayRefs.mobileMenu?.querySelector('button[data-menu-action="diag"]');
    if (mobileDiagBtn) mobileDiagBtn.classList.remove("u-hidden");
  }
}).catch((err) => {
  logClientError2("failed to load /config", err);
});
_uiOverlayRefs.hamburgerBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  if (isMobileMenuOpen()) hideMobileMenu();
  else showMobileMenu();
});
_uiOverlayRefs.mobileMenu?.querySelectorAll("button[data-menu-action]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const action = btn.dataset.menuAction;
    if (action !== "ts-toggle") hideMobileMenu();
    dispatchMobileMenuAction(action, btn);
  });
});
optionsTabs?.addEventListener("click", (e) => {
  const tab = e.target.closest?.("[data-options-tab]");
  if (!tab) return;
  activateOptionsTab(tab.dataset.optionsTab, { persist: true, focus: true });
});
optionsTabs?.addEventListener("keydown", (e) => {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
  const tabs = Array.from(optionsTabs.querySelectorAll("[data-options-tab]"));
  const currentIndex = tabs.indexOf(document.activeElement);
  if (!tabs.length || currentIndex < 0) return;
  e.preventDefault();
  let nextIndex = currentIndex;
  if (e.key === "Home") nextIndex = 0;
  else if (e.key === "End") nextIndex = tabs.length - 1;
  else if (e.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabs.length;
  else nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
  const nextTab = tabs[nextIndex];
  activateOptionsTab(nextTab.dataset.optionsTab, { persist: true, focus: true });
});
optionsTsSelect?.addEventListener("change", (e) => {
  applyTimestampPreference(e.target.value);
});
optionsLnToggle?.addEventListener("change", (e) => {
  applyLineNumberPreference(e.target.checked ? "on" : "off");
});
optionsWelcomeSelect?.addEventListener("change", (e) => {
  applyWelcomeIntroPreference(e.target.value);
});
optionsShareRedactionSelect?.addEventListener("change", (e) => {
  applyShareRedactionDefaultPreference(e.target.value);
});
optionsNotifyToggle?.addEventListener("change", (e) => {
  applyRunNotifyPreference(e.target.checked ? "on" : "off");
});
optionsCommandOutcomeSummariesToggle?.addEventListener("change", (e) => {
  applyCommandOutcomeSummariesPreference(e.target.checked ? "on" : "off");
});
optionsProjectAutoLinkExternalRunsToggle?.addEventListener("change", (e) => {
  applyProjectAutoLinkExternalRunsPreference(e.target.checked ? "on" : "off");
});
optionsProjectAutoLinkRunEntitiesToggle?.addEventListener("change", (e) => {
  applyProjectAutoLinkRunEntitiesPreference(e.target.checked ? "on" : "off");
});
optionsHudClockSelect?.addEventListener("change", (e) => {
  applyHudClockPreference(e.target.value);
});
optionsCompareViewModeSelect?.addEventListener("change", (e) => {
  applyCompareViewModePreference(e.target.value);
});
optionsCompareContextSelect?.addEventListener("change", (e) => {
  applyCompareContextPreference(e.target.value);
});
var promptUsernameAutosaveTimer = null;
var PROMPT_USERNAME_AUTOSAVE_DELAY_MS = 300;
function clearPromptUsernameAutosave() {
  if (!promptUsernameAutosaveTimer) return;
  clearTimeout(promptUsernameAutosaveTimer);
  promptUsernameAutosaveTimer = null;
}
function schedulePromptUsernameAutosave(value) {
  clearPromptUsernameAutosave();
  promptUsernameAutosaveTimer = setTimeout(() => {
    promptUsernameAutosaveTimer = null;
    applyPromptUsernamePreference(value);
  }, PROMPT_USERNAME_AUTOSAVE_DELAY_MS);
}
optionsPromptUsernameInput?.addEventListener("input", () => {
  if (typeof hidePromptUsernameSavedIndicator === "function") hidePromptUsernameSavedIndicator();
  if (syncPromptUsernameValidation()) schedulePromptUsernameAutosave(optionsPromptUsernameInput.value);
  else clearPromptUsernameAutosave();
});
optionsPromptUsernameInput?.addEventListener("change", (e) => {
  if (syncPromptUsernameValidation()) {
    clearPromptUsernameAutosave();
    applyPromptUsernamePreference(e.target.value);
  }
});
apiFetch2("/allowed-commands").then((r) => r.json()).then((data) => {
  if (typeof setAllowedCommandsFaqData === "function") setAllowedCommandsFaqData(data);
  if (typeof renderAllowedCommandsFaq === "function") renderAllowedCommandsFaq(data);
}).catch((err) => {
  logClientError2("failed to load /allowed-commands", err);
});
apiFetch2("/commands/catalog").then((r) => r.json()).then((data) => {
  _controllerSetCommandRegistryData(data);
  if (typeof isCommandRegistryOverlayOpen === "function" && isCommandRegistryOverlayOpen()) {
    if (typeof renderCommandRegistry === "function") renderCommandRegistry();
  }
}).catch((err) => {
  logClientError2("failed to load /commands/catalog", err);
  _controllerSetCommandRegistryData({ restricted: false, commands: [], groups: [] });
});
apiFetch2("/faq").then((r) => r.json()).then((data) => {
  if (typeof renderFaqItems === "function") renderFaqItems(data.items || []);
}).catch((err) => {
  logClientError2("failed to load /faq", err);
});
apiFetch2("/shortcuts").then((r) => r.json()).then((data) => {
  renderShortcuts(data || {});
}).catch((err) => {
  logClientError2("failed to load /shortcuts", err);
});
var workflowsLoad = apiFetch2("/workflows").then((r) => r.json()).then((data) => {
  const items = data.items || [];
  if (typeof renderWorkflowItems2 === "function") renderWorkflowItems2(items);
});
workflowsLoad.catch((err) => {
  logClientError2("failed to load /workflows", err);
});
loadStarredFromServer().catch((err) => {
  logClientError2("failed to load /session/starred", err);
});
if (typeof _seedLocalStorageStarsToServer === "function") {
  _seedLocalStorageStarsToServer().catch((err) => {
    logClientError2("failed to seed localStorage stars", err);
  });
}
setupTabScrollControls();
applyTimestampPreference(getPreference("pref_timestamps") || "off", false);
applyLineNumberPreference(getPreference("pref_line_numbers") || "off", false);
applyWelcomeIntroPreference(getWelcomeIntroPreference(), false);
applyShareRedactionDefaultPreference(getShareRedactionDefaultPreference(), false);
applyHudClockPreference(getHudClockPreference(), false);
applyPromptUsernamePreference(getPromptUsernamePreference(), false);
syncOptionsControls();
var sessionPreferencesLoad = typeof loadSessionPreferences === "function" ? loadSessionPreferences().catch((err) => {
  logClientError2("failed to apply session preferences", err);
}) : Promise.resolve();
var commandHistoryLimit = encodeURIComponent(String(APP_CONFIG.recent_commands_limit || 50));
Promise.all([
  sessionPreferencesLoad,
  apiFetch2(`/history/commands?limit=${commandHistoryLimit}`).then((r) => r.json()).catch((err) => {
    logClientError2("failed to load /history/commands", err);
    return { runs: [] };
  }),
  apiFetch2("/history/active").then((r) => r.json()).catch((err) => {
    logClientError2("failed to load /history/active", err);
    return { runs: [] };
  })
]).then(([, historyData, activeData]) => {
  hydrateCmdHistory(historyData.runs || []);
  const restoredTabs = typeof restoreTabSessionState === "function" && restoreTabSessionState();
  const restoredActiveRuns = typeof restoreActiveRunsAfterReload === "function" && restoreActiveRunsAfterReload(activeData.runs || []);
  if (!restoredTabs && !restoredActiveRuns && !_controllerTabs().length) {
    createTab(typeof createDefaultTabLabel === "function" ? createDefaultTabLabel(1) : "shell 1");
    _runWelcomeIntro();
    return;
  }
  _setWelcomeBootPending(false);
});
setTimeout(() => {
  if (!cmdInput) return;
  if (useMobileTerminalViewportMode()) {
    return;
  }
  refocusComposerAfterAction({ defer: true });
}, 0);
syncMobileViewportState();
setupMobileSheetDragClose();
setupDismissibleOverlays();
setupModalFocusTraps();
newTabBtn.addEventListener("click", () => {
  createShortcutTab();
});
function openSearchFromSignal(scope = null) {
  const normalizedScope = scope || null;
  if (normalizedScope && typeof isSearchBarOpen === "function" && isSearchBarOpen() && _controllerState().searchScope === normalizedScope) {
    navigateSearch(1);
    refocusComposerAfterAction({ defer: true });
    return;
  }
  if (typeof prepareSearchBarForScope === "function" && normalizedScope) {
    prepareSearchBarForScope(normalizedScope);
  } else if (typeof prepareSearchBarForOpen === "function") {
    prepareSearchBarForOpen();
  }
  showSearchBar();
  if (_controllerState().searchScope === "text") focusElement(searchInput);
  else refocusComposerAfterAction({ defer: true });
  runSearch();
}
if (typeof window !== "undefined") {
}
searchToggleBtn.addEventListener("click", () => {
  const visible = isSearchBarOpen();
  if (visible) {
    hideSearchBar();
    clearSearch();
  } else {
    openSearchFromSignal();
  }
});
if (typeof searchSummaryBtn !== "undefined" && searchSummaryBtn) {
  searchSummaryBtn.addEventListener("click", () => {
    if (typeof summarizeCurrentOutputSignals === "function") summarizeCurrentOutputSignals();
    refocusComposerAfterAction({ defer: true });
  });
}
searchInput.addEventListener("input", () => {
  if (typeof scheduleRunSearch === "function") scheduleRunSearch();
  else runSearch();
});
searchPrevBtn.addEventListener("click", () => navigateSearch(-1));
searchNextBtn.addEventListener("click", () => navigateSearch(1));
if (typeof searchScopeButtons !== "undefined" && Array.isArray(searchScopeButtons)) {
  searchScopeButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      setSearchScope(btn.dataset.searchScope || "text");
      if (_controllerState().searchScope === "text") focusElement(searchInput);
      else refocusComposerAfterAction({ defer: true });
    });
  });
}
searchCloseBtn?.addEventListener("click", () => {
  hideSearchBar();
  clearSearch();
});
searchInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    navigateSearch(e.shiftKey ? -1 : 1);
  }
  if (e.key === "Escape") {
    hideSearchBar();
    clearSearch();
    refocusComposerAfterAction({ defer: true });
  }
});
searchCaseBtn.addEventListener("click", () => {
  const next = !_controllerSearchCaseSensitive();
  _controllerSetSearchCaseSensitive(next);
  searchCaseBtn.setAttribute("aria-pressed", next ? "true" : "false");
  runSearch();
});
searchRegexBtn.addEventListener("click", () => {
  const next = !_controllerSearchRegexMode();
  _controllerSetSearchRegexMode(next);
  searchRegexBtn.setAttribute("aria-pressed", next ? "true" : "false");
  runSearch();
});
histClearAllBtn.addEventListener("click", () => {
  confirmHistAction("clear");
});
function hasActiveTerminalConfirm() {
  return typeof hasPendingTerminalConfirm === "function" && hasPendingTerminalConfirm();
}
function isAnyPanelOverlayOpen() {
  return typeof isFaqOverlayOpen === "function" && isFaqOverlayOpen() || typeof isWorkflowsOverlayOpen === "function" && isWorkflowsOverlayOpen() || typeof isWorkspaceOverlayOpen === "function" && isWorkspaceOverlayOpen() || typeof isSchedulesOverlayOpen === "function" && isSchedulesOverlayOpen() || typeof isWatchersOverlayOpen === "function" && isWatchersOverlayOpen() || typeof isHistoryCompareOverlayOpen === "function" && isHistoryCompareOverlayOpen() || typeof isHistoryRunOverlayOpen2 === "function" && isHistoryRunOverlayOpen2() || typeof isOptionsOverlayOpen === "function" && isOptionsOverlayOpen() || typeof isThemeOverlayOpen === "function" && isThemeOverlayOpen();
}
document.addEventListener("keydown", (e) => {
  if (e.defaultPrevented) return;
  if (e.key === "Escape" && typeof closeTopmostDismissible === "function" && closeTopmostDismissible()) {
    e.preventDefault();
    return;
  }
  if (isFaqOverlayOpen() || isOptionsOverlayOpen() || isThemeOverlayOpen() || isWorkflowsOverlayOpen() || typeof isWorkspaceOverlayOpen === "function" && isWorkspaceOverlayOpen() || typeof isSchedulesOverlayOpen === "function" && isSchedulesOverlayOpen() || typeof isWatchersOverlayOpen === "function" && isWatchersOverlayOpen() || isHistoryPanelOpen() || typeof isAtlasOverlayOpen2 === "function" && isAtlasOverlayOpen2() || typeof isHistoryCompareOverlayOpen === "function" && isHistoryCompareOverlayOpen() || typeof isHistoryRunOverlayOpen2 === "function" && isHistoryRunOverlayOpen2()) {
    if (handleTabShortcut(e, { surfaceOnly: true })) return;
    if (handleChromeShortcut(e)) return;
    return;
  }
  if (_welcomeActiveNow() && !_welcomeDoneNow() && _welcomeOwns(_controllerActiveTabId())) {
    const editableWelcomeTarget = isEditableTarget(e.target);
    const composerWelcomeTarget = e.target === cmdInput || typeof mobileCmdInput !== "undefined" && e.target === mobileCmdInput;
    if (editableWelcomeTarget && !composerWelcomeTarget) return;
    const isCtrlC = e.ctrlKey && !e.metaKey && !e.altKey && (e.key === "c" || e.key === "C");
    const isSpace = e.key === " " || e.code === "Space";
    const isPrintable = !e.metaKey && !e.ctrlKey && !e.altKey && !isEditableTarget(e.target) && e.key.length === 1;
    if (isCtrlC) {
      _setWelcomePromptAfterSettle(true);
      _requestWelcomeSettle(_controllerActiveTabId());
      refocusComposerAfterAction({ defer: true });
      e.preventDefault();
      return;
    }
    if (e.key === "Escape" || e.key === "Enter" || isSpace) {
      _requestWelcomeSettle(_controllerActiveTabId());
      refocusComposerAfterAction({ defer: true });
      e.preventDefault();
      return;
    }
    if (isPrintable) {
      _requestWelcomeSettle(_controllerActiveTabId());
      refocusComposerAfterAction({ defer: true });
      setComposerValue((typeof getComposerValue === "function" ? getComposerValue() : "") + e.key);
      e.preventDefault();
      return;
    }
  }
  if (handleTabShortcut(e)) return;
  if (handleActionShortcut(e)) return;
  if (handleChromeShortcut(e)) return;
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === "c" || e.key === "C")) {
    if (e.target === cmdInput) return;
    const editable = isEditableTarget(e.target);
    if (editable) return;
    if (_welcomeActiveNow() && !_welcomeDoneNow() && _welcomeOwns(_controllerActiveTabId())) {
      _setWelcomePromptAfterSettle(true);
      _requestWelcomeSettle(_controllerActiveTabId());
      refocusComposerAfterAction({ defer: true });
      e.preventDefault();
      return;
    }
    const activeTab = getActiveTab();
    if (activeTab && activeTab.st === "running") {
      confirmKill2(_controllerActiveTabId());
    } else if (hasActiveTerminalConfirm()) {
      cancelPendingTerminalConfirm2(_controllerActiveTabId());
    } else {
      interruptPromptLine2(_controllerActiveTabId());
    }
    e.preventDefault();
    return;
  }
  if (typeof isActiveTabRunning === "function" && isActiveTabRunning() && !(typeof isConfirmOpen === "function" && isConfirmOpen()) && !isEditableTarget(e.target) && !e.metaKey && !e.ctrlKey && !e.altKey && (e.key.length === 1 || e.key === "Enter" || e.key === "Tab" || e.key === "Backspace" || e.key === "Delete")) {
    if (typeof acHide === "function") acHide();
    e.preventDefault();
    return;
  }
  if (_welcomeActiveNow() && !_welcomeDoneNow() && _welcomeOwns(_controllerActiveTabId()) && cmdInput && !e.metaKey && !e.ctrlKey && !e.altKey && !isEditableTarget(e.target) && e.key.length === 1) {
    _requestWelcomeSettle(_controllerActiveTabId());
    refocusComposerAfterAction({ defer: true });
    setComposerValue((typeof getComposerValue === "function" ? getComposerValue() : "") + e.key);
    e.preventDefault();
    return;
  }
  if (e.key === "Enter" && _welcomeActiveNow() && !_welcomeDoneNow() && _welcomeOwns(_controllerActiveTabId())) {
    if ((typeof getComposerValue === "function" ? getComposerValue() : "").trim()) return;
    _requestWelcomeSettle(_controllerActiveTabId());
    refocusComposerAfterAction({ defer: true });
    e.preventDefault();
    return;
  }
  if (e.key === "Escape" && _welcomeActiveNow() && !_welcomeDoneNow() && _welcomeOwns(_controllerActiveTabId())) {
    _requestWelcomeSettle(_controllerActiveTabId());
    refocusComposerAfterAction({ defer: true });
    e.preventDefault();
    return;
  }
  if (e.key === "Escape") {
    hideSearchBar();
    clearSearch();
  }
  if (_replayPromptShortcutAfterSelection(e)) return;
  if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey && !e.isComposing && document.activeElement !== cmdInput && !isEditableTarget(e.target) && !(e.target && e.target.closest && e.target.closest("button, a, select")) && cmdInput && !isFaqOverlayOpen() && !isWorkflowsOverlayOpen() && !isOptionsOverlayOpen() && !isThemeOverlayOpen() && !(typeof isWorkspaceOverlayOpen === "function" && isWorkspaceOverlayOpen()) && !(typeof isSchedulesOverlayOpen === "function" && isSchedulesOverlayOpen()) && !(typeof isWatchersOverlayOpen === "function" && isWatchersOverlayOpen()) && !(typeof isHistoryCompareOverlayOpen === "function" && isHistoryCompareOverlayOpen()) && !(typeof isHistoryRunOverlayOpen2 === "function" && isHistoryRunOverlayOpen2()) && !(typeof isConfirmOpen === "function" && isConfirmOpen())) {
    e.preventDefault();
    refocusComposerAfterAction({ preventScroll: true });
    const value = typeof getComposerValue === "function" ? getComposerValue() : cmdInput.value || "";
    const { start, end } = getCmdSelection(value);
    replaceCmdRange(value, start, end, e.key);
  }
});
function acAutocompleteIsHintOnly(item) {
  if (typeof acIsHintOnly === "function") return acIsHintOnly(item);
  return !!(item && typeof item === "object" && item.hintOnly);
}
function acAutocompleteSelectableItems(items) {
  if (typeof acSelectableItems === "function") return acSelectableItems(items);
  return (Array.isArray(items) ? items : []).filter((item) => !acAutocompleteIsHintOnly(item));
}
function acAutocompleteSelectableIndexes(items) {
  if (typeof acSelectableIndexes === "function") return acSelectableIndexes(items);
  return (Array.isArray(items) ? items : []).map((item, index) => acAutocompleteIsHintOnly(item) ? -1 : index).filter((index) => index >= 0);
}
function acAutocompleteNextSelectableIndex(items, currentIndex, direction = 1) {
  if (typeof acNextSelectableIndex === "function") {
    return acNextSelectableIndex(items, currentIndex, direction);
  }
  const indexes = acAutocompleteSelectableIndexes(items);
  if (!indexes.length) return -1;
  const currentPos = indexes.indexOf(currentIndex);
  if (currentPos < 0) return direction < 0 ? indexes[indexes.length - 1] : indexes[0];
  const nextPos = direction < 0 ? currentPos <= 0 ? indexes.length - 1 : currentPos - 1 : (currentPos + 1) % indexes.length;
  return indexes[nextPos];
}
function _replayPromptShortcutAfterSelection(e) {
  if (!cmdInput || document.activeElement === cmdInput) return false;
  if (isEditableTarget(e.target)) return false;
  const isCtrlR = e.ctrlKey && !e.metaKey && !e.altKey && (e.key === "r" || e.key === "R");
  const isSelectionShortcut = e.key === "Enter" || e.key === "ArrowDown" || e.key === "ArrowUp" || isCtrlR;
  if (!isSelectionShortcut) return false;
  const selection = typeof window !== "undefined" && typeof window.getSelection === "function" ? window.getSelection() : null;
  const selectedText = selection && typeof selection.toString === "function" ? selection.toString() : "";
  if (!selectedText) return false;
  e.preventDefault();
  refocusComposerAfterAction({ preventScroll: true });
  if (isCtrlR) {
    if (typeof enterHistSearch === "function") enterHistSearch();
    return true;
  }
  if (e.key === "ArrowDown") {
    if (hasActiveTerminalConfirm()) {
      if (typeof acHide === "function") acHide();
      return true;
    }
    const acState = _readControllerAutocompleteState();
    if (isAcDropdownOpen() && acAutocompleteSelectableItems(acState.filtered).length) {
      const nextIndex = acAutocompleteNextSelectableIndex(acState.filtered, acState.index, 1);
      _writeControllerAutocompleteState({ index: nextIndex });
      if (typeof acShow === "function") acShow(acState.filtered);
    } else if (typeof navigateCmdHistory === "function" && navigateCmdHistory(-1)) {
      if (typeof acHide === "function") acHide();
    }
    return true;
  }
  if (e.key === "ArrowUp") {
    if (hasActiveTerminalConfirm()) {
      if (typeof acHide === "function") acHide();
      return true;
    }
    const acState = _readControllerAutocompleteState();
    if (isAcDropdownOpen() && acAutocompleteSelectableItems(acState.filtered).length) {
      const nextIndex = acAutocompleteNextSelectableIndex(acState.filtered, acState.index, -1);
      _writeControllerAutocompleteState({ index: nextIndex });
      if (typeof acShow === "function") acShow(acState.filtered);
    } else if (typeof navigateCmdHistory === "function" && navigateCmdHistory(1)) {
      if (typeof acHide === "function") acHide();
    }
    return true;
  }
  if (e.key === "Enter") {
    const acState = _readControllerAutocompleteState();
    if (acState.index >= 0 && acState.filtered[acState.index] && !acAutocompleteIsHintOnly(acState.filtered[acState.index])) {
      if (typeof acAccept === "function") acAccept(acState.filtered[acState.index]);
    } else {
      if (typeof acHide === "function") acHide();
      if (typeof submitComposerCommand2 === "function") {
        submitComposerCommand2(typeof getComposerValue === "function" ? getComposerValue() : cmdInput.value || "", { dismissKeyboard: true });
      } else if (typeof runCommand2 === "function") {
        runCommand2();
      }
    }
    return true;
  }
  return true;
}
if (typeof window !== "undefined") {
  Object.assign(window, {});
  if (typeof setControllerActionHandlers === "function") {
    setControllerActionHandlers({
      closeFaq: closeFaq2,
      closeWorkflows: closeWorkflows2,
      openFaq: openFaq2,
      openWorkflows: openWorkflows2,
      toggleHistoryPanelSurface: toggleHistoryPanelSurface2
    });
  }
}

// app/static/js/features/shortcuts/shortcuts_key_handler.js
function _shortcutsGlobal() {
  return typeof window !== "undefined" ? window : {};
}
function _shortcutsCmdInput() {
  return typeof cmdInput !== "undefined" && cmdInput || _shortcutsGlobal().cmdInput;
}
function _shortcutsMobileCmdInput() {
  return typeof mobileCmdInput !== "undefined" && mobileCmdInput || _shortcutsGlobal().mobileCmdInput;
}
function _shortcutsSyncFocusedComposerState(input) {
  const sync = typeof syncFocusedComposerState !== "undefined" && syncFocusedComposerState || null;
  if (typeof sync === "function") sync(input);
}
function _shortcutsWelcomeState() {
  if (typeof getWelcomeState !== "undefined" && typeof getWelcomeState === "function") {
    return getWelcomeState();
  }
  return { active: false };
}
function _shortcutsActiveTabId() {
  if (typeof getActiveTabId !== "undefined" && typeof getActiveTabId === "function") {
    return getActiveTabId();
  }
  return null;
}
document.addEventListener("keydown", (e) => {
  if (e.key !== "?") return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const global = _shortcutsGlobal();
  const ae = document.activeElement;
  if (ae) {
    const tag = (ae.tagName || "").toLowerCase();
    const isEditable = ae.isContentEditable;
    const isTextInput = tag === "textarea" || tag === "input" && !/^(checkbox|radio|button|submit|reset|range|color|file)$/i.test(ae.type || "") || isEditable;
    if (tag === "select") return;
    if (isTextInput) {
      if (ae === _shortcutsCmdInput() || ae === _shortcutsMobileCmdInput()) {
        _shortcutsSyncFocusedComposerState(ae);
      }
      const raw = isEditable ? ae.textContent || "" : ae.value || "";
      if (raw.length > 0) return;
    }
  }
  e.preventDefault();
  e.stopImmediatePropagation();
  const welcomeState = _shortcutsWelcomeState();
  const activeId = _shortcutsActiveTabId();
  if (welcomeState.active && typeof activeId !== "undefined" && typeof welcomeOwnsTab2 === "function" && welcomeOwnsTab2(activeId) && typeof requestWelcomeSettle2 === "function") {
    requestWelcomeSettle2(activeId);
  }
  if (typeof isShortcutsOverlayOpen === "function" && isShortcutsOverlayOpen()) {
    if (typeof closeShortcuts === "function") closeShortcuts();
  } else {
    if (typeof openShortcuts === "function") openShortcuts();
  }
}, true);

// app/static/js/export_html.js
var ExportHtmlUtils = null;
(function() {
  const EXPORT_FONT_FILES = [
    { family: "JetBrains Mono", weight: 300, filename: "JetBrainsMono-300.ttf" },
    { family: "JetBrains Mono", weight: 400, filename: "JetBrainsMono-400.ttf" },
    { family: "JetBrains Mono", weight: 700, filename: "JetBrainsMono-700.ttf" },
    { family: "Syne", weight: 700, filename: "Syne-700.ttf" },
    { family: "Syne", weight: 800, filename: "Syne-800.ttf" }
  ];
  const EXPORT_THEME_VAR_NAMES = [
    "--bg",
    "--surface",
    "--border",
    "--border-bright",
    "--text",
    "--muted",
    "--green",
    "--green-dim",
    "--green-glow",
    "--amber",
    "--red",
    "--blue",
    "--theme-panel-bg",
    "--theme-panel-border",
    "--theme-panel-shadow",
    "--theme-terminal-bar-bg",
    "--terminal-font-size",
    "--terminal-line-height"
  ];
  function runOutputModel() {
    return typeof DarklabRunOutputModel !== "undefined" && DarklabRunOutputModel || null;
  }
  function fallbackLineEvent(line) {
    const cls = String(line && line.cls || "");
    return {
      text: String(line && line.text || ""),
      cls,
      kind: String(line && line.kind || (cls === "notice" ? "notice" : "info")),
      role: String(line && line.role || (["prompt-echo", "denied", "exit-ok", "exit-fail"].includes(cls) ? cls : "body")),
      tsC: String(line && line.tsC || ""),
      tsE: String(line && line.tsE || ""),
      signals: Array.isArray(line && line.signals) ? line.signals.map((signal) => String(signal || "")).filter(Boolean) : [],
      entities: Array.isArray(line && line.entities) ? line.entities : [],
      line_number: Number.isInteger(line && line.line_number) ? line.line_number : void 0
    };
  }
  function lineEventFromWire2(line) {
    const model = runOutputModel();
    if (model && typeof model.fromWireLineEvent === "function") {
      const event = model.fromWireLineEvent(line || {});
      event.cls = lineLegacyClass2(event);
      event.tsC = event.ts_clock || "";
      event.tsE = event.ts_elapsed || "";
      event.signals = Array.isArray(event.signals) ? event.signals : [];
      event.entities = Array.isArray(event.entities) ? event.entities : [];
      if (Number.isInteger(line && line.line_number)) event.line_number = line.line_number;
      return event;
    }
    return fallbackLineEvent(line || {});
  }
  function lineLegacyClass2(event) {
    const model = runOutputModel();
    if (model && typeof model.toLegacyWireLineEvent === "function") {
      return String(model.toLegacyWireLineEvent(event || {}).cls || "");
    }
    return String(event && (event.legacy_cls || event.cls || (event.role !== "body" ? event.role : event.kind !== "info" ? event.kind : "")) || "");
  }
  function isPromptEchoEvent2(event) {
    return String(event && event.role || "") === "prompt-echo";
  }
  function isPlainEvent2(event) {
    const role = String(event && event.role || "body");
    const kind = String(event && event.kind || "info");
    return ["exit-ok", "exit-fail", "denied"].includes(role) || kind === "notice";
  }
  function escapeExportHtml2(text) {
    return String(text ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function escapeExportAttr2(text) {
    return escapeExportHtml2(text).replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function renderExportPromptEcho2(text) {
    const raw = String(text || "");
    const firstSpace = raw.indexOf(" ");
    const prefix = firstSpace === -1 ? raw : raw.slice(0, firstSpace);
    const remainder = firstSpace === -1 ? "" : raw.slice(firstSpace + 1);
    return '<span class="prompt-prefix">' + escapeExportHtml2(prefix) + "</span>" + (remainder ? escapeExportHtml2(" " + remainder) : "");
  }
  function exportEntityRanges(text, entities) {
    const length = String(text || "").length;
    return (Array.isArray(entities) ? entities : []).map((entity) => {
      const start = Number(entity && entity.start);
      const end = Number(entity && entity.end);
      if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start || end > length) {
        return null;
      }
      return { start, end, entity };
    }).filter(Boolean).sort((a, b) => a.start - b.start || a.end - b.end).reduce((ranges, range) => {
      const previous = ranges[ranges.length - 1];
      if (previous && range.start < previous.end) return ranges;
      ranges.push(range);
      return ranges;
    }, []);
  }
  function renderExportEntityContent2(text, entities, ansiToHtml) {
    const raw = String(text || "");
    const ranges = exportEntityRanges(raw, entities);
    if (!ranges.length) return ansiToHtml(raw);
    let cursor = 0;
    let html = "";
    ranges.forEach((range) => {
      if (range.start > cursor) html += ansiToHtml(raw.slice(cursor, range.start));
      const entity = range.entity || {};
      const entityType = String(entity.type || "");
      const entityValue = String(entity.canonical_value || entity.value || raw.slice(range.start, range.end));
      const tokenText = raw.slice(range.start, range.end);
      html += '<span class="export-entity-token" data-entity-type="' + escapeExportAttr2(entityType) + '" data-entity-value="' + escapeExportAttr2(entityValue) + '" title="Entity: ' + escapeExportAttr2(entityValue) + '">' + ansiToHtml(tokenText) + "</span>";
      cursor = range.end;
    });
    if (cursor < raw.length) html += ansiToHtml(raw.slice(cursor));
    return html;
  }
  function exportLineBadgeHtml(line) {
    const kind = String(line && line.kind || "info");
    const signals = Array.isArray(line && line.signals) ? line.signals.map(String) : [];
    if (kind === "error") return '<span class="line-severity-badge line-severity-error">error</span>';
    if (kind === "warn") return '<span class="line-severity-badge line-severity-warn">warn</span>';
    if (signals.includes("findings")) return '<span class="line-severity-badge line-severity-finding">finding</span>';
    return "";
  }
  function buildExportLineSummary2(rawLines) {
    const summary = {
      findings: 0,
      warnings: 0,
      errors: 0,
      entityTypes: {}
    };
    rawLines.forEach((rawLine) => {
      const line = lineEventFromWire2(rawLine);
      const signals = Array.isArray(line.signals) ? line.signals.map(String) : [];
      if (signals.includes("findings")) summary.findings += 1;
      if (line.kind === "warn") summary.warnings += 1;
      if (line.kind === "error") summary.errors += 1;
      (Array.isArray(line.entities) ? line.entities : []).forEach((entity) => {
        const type = String(entity && entity.type || "").trim();
        if (type) summary.entityTypes[type] = (summary.entityTypes[type] || 0) + 1;
      });
    });
    return summary;
  }
  function buildExportSummaryHtml(summary) {
    const chips = [];
    if (summary.findings) chips.push(`findings ${summary.findings}`);
    if (summary.errors) chips.push(`errors ${summary.errors}`);
    if (summary.warnings) chips.push(`warnings ${summary.warnings}`);
    Object.entries(summary.entityTypes || {}).sort((a, b) => a[0].localeCompare(b[0])).slice(0, 8).forEach(([type, count]) => chips.push(`${type} ${count}`));
    if (!chips.length) return "";
    return '<section class="export-findings-summary">' + chips.map((chip) => `<span>${escapeExportHtml2(chip)}</span>`).join("") + "</section>";
  }
  function renderExportLineContent2(line, ansiToHtml) {
    const lineEvent = lineEventFromWire2(line);
    const text = String(lineEvent.text || "");
    let content;
    if (isPromptEchoEvent2(lineEvent)) {
      content = renderExportPromptEcho2(text);
    } else if (isPlainEvent2(lineEvent)) {
      content = escapeExportHtml2(text);
    } else {
      content = renderExportEntityContent2(text, lineEvent.entities, ansiToHtml);
    }
    return exportLineBadgeHtml(lineEvent) + content;
  }
  function exportTimestamp2() {
    return (/* @__PURE__ */ new Date()).toISOString().replace(/[:.]/g, "-").slice(0, 19);
  }
  function buildExportMetaLine2({ label = "", createdText = "" }) {
    const trimmedLabel = String(label || "").trim();
    const trimmedCreated = String(createdText || "").trim();
    if (trimmedLabel && trimmedCreated) return `${trimmedLabel} · ${trimmedCreated}`;
    return trimmedLabel || trimmedCreated;
  }
  function normalizeExportTranscriptLine2(line) {
    if (typeof line === "string") {
      return lineEventFromWire2({ text: line });
    }
    if (line && typeof line.text === "string") {
      return lineEventFromWire2(line);
    }
    return null;
  }
  function normalizeExportTranscriptLines2(lines, { stripTruncationNotices = false } = {}) {
    return (Array.isArray(lines) ? lines : []).map(normalizeExportTranscriptLine2).filter((line) => {
      if (!line) return false;
      if (!stripTruncationNotices) return true;
      return !/^\[(?:preview|tab output) truncated/i.test(String(line.text || ""));
    });
  }
  function isCommandOutcomeSummaryLine2(line) {
    const cls = String(line && line.cls || line && line.legacy_cls || "");
    return cls.split(/\s+/).includes("command-outcome-summary") || Boolean(line && line.command_outcome_summary === true);
  }
  function commandOutcomeItemText(item) {
    if (!item || typeof item !== "object") return "";
    const label = String(item.label || "").trim();
    const value = String(item.value || "").trim();
    if (label && value) return `${label}: ${value}`;
    return value || label;
  }
  function buildExportCommandOutcomeSummary2(command, rawLines) {
    const core = typeof DarklabOutputCore !== "undefined" && DarklabOutputCore || null;
    if (!core || typeof core.buildCommandOutcomeSummary !== "function") return null;
    const normalizer = typeof core.normalizeCommandOutcomeSummary === "function" ? core.normalizeCommandOutcomeSummary : (value) => value;
    return normalizer(core.buildCommandOutcomeSummary(command, rawLines));
  }
  function commandOutcomeSummaryToLines2(summary) {
    if (!summary || !Array.isArray(summary.items) || !summary.items.length) return [];
    const lines = [];
    const title = String(summary.title || "Command outcome").trim() || "Command outcome";
    lines.push({
      text: title,
      cls: "command-outcome-summary command-outcome-summary-title",
      command_outcome_summary: true
    });
    summary.items.forEach((item) => {
      const text = commandOutcomeItemText(item);
      if (!text) return;
      lines.push({
        text,
        cls: "command-outcome-summary command-outcome-summary-row",
        command_outcome_summary: true
      });
    });
    return lines;
  }
  function appendCommandOutcomeSummaryLines2(rawLines, { command = "", enabled = true } = {}) {
    const normalized = normalizeExportTranscriptLines2(rawLines);
    if (!enabled || normalized.some(isCommandOutcomeSummaryLine2)) return normalized;
    const summary = buildExportCommandOutcomeSummary2(command, normalized);
    if (!summary) return normalized;
    return normalized.concat(commandOutcomeSummaryToLines2(summary));
  }
  function normalizeExportRunMeta2(runMeta) {
    if (!runMeta) return null;
    return {
      exitCode: runMeta.exitCode !== void 0 ? runMeta.exitCode : runMeta.exit_code,
      duration: runMeta.duration || null,
      lines: runMeta.lines || null,
      version: runMeta.version || null
    };
  }
  function buildExportDocumentModel2({
    appName = "",
    title = "",
    label = "",
    createdText = "",
    runMeta = null,
    rawLines = [],
    command = "",
    includeCommandOutcomeSummary = false
  }) {
    return {
      appName: String(appName || ""),
      title: String(title || ""),
      metaLine: buildExportMetaLine2({ label, createdText }),
      runMeta: normalizeExportRunMeta2(runMeta),
      rawLines: includeCommandOutcomeSummary ? appendCommandOutcomeSummaryLines2(rawLines, { command, enabled: true }) : normalizeExportTranscriptLines2(rawLines)
    };
  }
  function getThemeExportVars2() {
    const themeRegistry = typeof _getThemeRegistry === "function" ? _getThemeRegistry() : null;
    const registryCurrent = themeRegistry && themeRegistry.current && themeRegistry.current.vars && typeof themeRegistry.current.vars === "object" ? themeRegistry.current.vars : null;
    if (registryCurrent && Object.keys(registryCurrent).length) return registryCurrent;
    const current = window.ThemeCssVars && window.ThemeCssVars.current;
    if (current && typeof current === "object" && Object.keys(current).length) return current;
    const source = window.ThemeCssVars && window.ThemeCssVars.fallback;
    if (source && typeof source === "object") return source;
    const target = document.documentElement;
    const computed = getComputedStyle(target);
    const fallback = {};
    for (const name of EXPORT_THEME_VAR_NAMES) {
      const value = computed.getPropertyValue(name).trim();
      if (value) fallback[name] = value;
    }
    if (Object.keys(fallback).length) return fallback;
    return {};
  }
  function getThemeExportColorScheme2() {
    const themeRegistry = typeof _getThemeRegistry === "function" ? _getThemeRegistry() : null;
    const registryCurrent = themeRegistry && themeRegistry.current;
    if (registryCurrent && typeof registryCurrent.color_scheme === "string" && registryCurrent.color_scheme.trim()) {
      return registryCurrent.color_scheme.trim();
    }
    const colorSchemeMeta = document.querySelector('meta[name="color-scheme"]');
    if (colorSchemeMeta && typeof colorSchemeMeta.content === "string" && colorSchemeMeta.content.trim()) {
      return colorSchemeMeta.content.trim();
    }
    const docScheme = document.documentElement && document.documentElement.style ? document.documentElement.style.colorScheme : "";
    if (typeof docScheme === "string" && docScheme.trim()) return docScheme.trim();
    return "light dark";
  }
  function buildExportLinesHtml2(rawLines, { getPrefix = () => "", ansiToHtml }) {
    const prefixes = rawLines.map((line, i) => getPrefix(line, i));
    const prefixWidth = Math.max(0, ...prefixes.map((p) => p.length));
    const summary = buildExportLineSummary2(rawLines);
    const linesHtml = rawLines.map((rawLine, i) => {
      const line = lineEventFromWire2(rawLine);
      const cls = lineLegacyClass2(line);
      const prefix = prefixes[i];
      const prefixSpan = prefix ? `<span class="perm-prefix">${escapeExportHtml2(prefix)}</span>` : "";
      const content = renderExportLineContent2(line, ansiToHtml);
      return `<span class="line${cls ? " " + cls : ""}">${prefixSpan}<span class="perm-content">${content}</span></span>`;
    }).join("");
    return { linesHtml, prefixWidth, summary, summaryHtml: buildExportSummaryHtml(summary) };
  }
  function buildExportRunMetaItems2(runMeta) {
    if (!runMeta) return [];
    const items = [];
    const { exitCode, duration, lines, version } = runMeta;
    if (exitCode !== null && exitCode !== void 0) {
      items.push({
        kind: "badge",
        tone: exitCode === 0 ? "ok" : "fail",
        text: `exit ${exitCode}`
      });
    }
    if (duration) items.push({ kind: "item", text: String(duration) });
    if (lines) items.push({ kind: "item", text: String(lines) });
    if (version) items.push({ kind: "item", text: `v${version}` });
    return items;
  }
  function buildExportHeaderModel2({ appName, metaLine = "", runMeta = null }) {
    return {
      appName: String(appName || ""),
      metaLine: metaLine ? String(metaLine) : "",
      runMetaItems: buildExportRunMetaItems2(runMeta)
    };
  }
  function buildExportRunMetaHtml2(runMetaOrItems) {
    const items = Array.isArray(runMetaOrItems) ? runMetaOrItems : buildExportRunMetaItems2(runMetaOrItems);
    return items.map((item) => {
      if (item.kind === "badge") {
        const cls = item.tone === "ok" ? "meta-badge-ok" : "meta-badge-fail";
        return `<span class="meta-badge ${cls}">${escapeExportHtml2(item.text)}</span>`;
      }
      return `<span class="meta-item">${escapeExportHtml2(item.text)}</span>`;
    }).join("");
  }
  function buildTerminalExportHeaderHtml2(headerModel, { includeHighlightToggle = false } = {}) {
    const titleHtml = `<h1 class="export-title">${escapeExportHtml2(headerModel.appName)}</h1>`;
    const metaHtml = headerModel.metaLine ? `<div class="export-meta">${escapeExportHtml2(headerModel.metaLine)}</div>` : "";
    const runMetaHtml = headerModel.runMetaItems.length ? `<div class="export-run-meta">${buildExportRunMetaHtml2(headerModel.runMetaItems)}</div>` : "";
    const actionsHtml = includeHighlightToggle ? `<div class="export-header-actions">
    <button type="button" class="export-highlight-toggle" data-export-toggle-highlights aria-pressed="true">highlights: on</button>
  </div>` : "";
    return `<header class="export-header">
  <div class="export-header-copy">
    ${titleHtml}
    ${metaHtml}
    ${runMetaHtml}
  </div>
  ${actionsHtml}
</header>`;
  }
  function buildTerminalExportScript() {
    return `<script>
(function () {
  var btn = document.querySelector('[data-export-toggle-highlights]');
  if (!btn) return;
  function sync() {
    var off = document.body.classList.contains('structured-highlights-off');
    btn.textContent = 'highlights: ' + (off ? 'off' : 'on');
    btn.setAttribute('aria-pressed', off ? 'false' : 'true');
  }
  btn.addEventListener('click', function () {
    document.body.classList.toggle('structured-highlights-off');
    sync();
  });
  sync();
}());
<\/script>`;
  }
  function buildTerminalExportStyles2(fontFacesCss = "", prefixWidth = 0, exportCss = "") {
    const themeVars = getThemeExportVars2();
    const themeDecls = Object.entries(themeVars).map(([name, value]) => `    ${name}: ${value};`).join("\n");
    return `${fontFacesCss}
  :root {
${themeDecls}
    --perm-prefix-width: ${prefixWidth}ch;
  }
  *, *::before, *::after { box-sizing: border-box; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  html, body { height: 100%; margin: 0; }
  body {
    display: flex;
    flex-direction: column;
    background: var(--bg);
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    font-size: var(--terminal-font-size, 14px);
    line-height: var(--terminal-line-height, 1.65);
  }
  ${exportCss}`;
  }
  function buildTerminalExportHtml2({
    appName,
    title,
    metaLine = "",
    runMeta = null,
    linesHtml = "",
    summaryHtml = "",
    prefixWidth = 0,
    fontFacesCss = "",
    exportCss = "",
    includeHighlightToggle = true,
    highlights = "on"
  }) {
    const colorScheme = getThemeExportColorScheme2();
    const headerModel = buildExportHeaderModel2({ appName, metaLine, runMeta });
    const styles = buildTerminalExportStyles2(fontFacesCss, prefixWidth, exportCss);
    const bodyClass = highlights === "off" ? ' class="structured-highlights-off"' : "";
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="color-scheme" content="${escapeExportHtml2(colorScheme)}">
<title>${escapeExportHtml2(title)} — ${escapeExportHtml2(appName)}</title>
<style>
${styles}
</style>
</head>
<body${bodyClass}>
${buildTerminalExportHeaderHtml2(headerModel, { includeHighlightToggle })}
${summaryHtml || ""}
<main class="export-output nice-scroll">
${linesHtml}
</main>
${includeHighlightToggle ? buildTerminalExportScript() : ""}
</body>
</html>`;
  }
  let _cachedTerminalExportCss = null;
  async function fetchTerminalExportCss2() {
    if (_cachedTerminalExportCss !== null) return _cachedTerminalExportCss;
    try {
      const res = await fetch("/static/css/terminal_export.css");
      _cachedTerminalExportCss = res.ok ? await res.text() : "";
    } catch (_) {
      _cachedTerminalExportCss = "";
    }
    return _cachedTerminalExportCss;
  }
  async function fetchVendorFontFacesCss2() {
    const chunks = [];
    for (const font of EXPORT_FONT_FILES) {
      const res = await fetch(`/vendor/fonts/${font.filename}`);
      if (!res.ok) continue;
      const buf = await res.arrayBuffer();
      const bytes = new Uint8Array(buf);
      let binary = "";
      const chunkSize = 32768;
      for (let i = 0; i < bytes.length; i += chunkSize) {
        binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
      }
      const dataUrl = `url(data:font/ttf;base64,${btoa(binary)}) format('truetype')`;
      chunks.push(
        `@font-face { font-family: '${font.family}'; font-style: normal; font-weight: ${font.weight}; font-display: swap; src: ${dataUrl}; }`
      );
    }
    return chunks.join("\n");
  }
  ExportHtmlUtils = {
    exportTimestamp: exportTimestamp2,
    buildExportMetaLine: buildExportMetaLine2,
    normalizeExportTranscriptLine: normalizeExportTranscriptLine2,
    normalizeExportTranscriptLines: normalizeExportTranscriptLines2,
    appendCommandOutcomeSummaryLines: appendCommandOutcomeSummaryLines2,
    buildExportCommandOutcomeSummary: buildExportCommandOutcomeSummary2,
    commandOutcomeSummaryToLines: commandOutcomeSummaryToLines2,
    isCommandOutcomeSummaryLine: isCommandOutcomeSummaryLine2,
    normalizeExportRunMeta: normalizeExportRunMeta2,
    lineEventFromWire: lineEventFromWire2,
    lineLegacyClass: lineLegacyClass2,
    isPromptEchoEvent: isPromptEchoEvent2,
    isPlainEvent: isPlainEvent2,
    buildExportDocumentModel: buildExportDocumentModel2,
    escapeExportHtml: escapeExportHtml2,
    escapeExportAttr: escapeExportAttr2,
    renderExportPromptEcho: renderExportPromptEcho2,
    renderExportEntityContent: renderExportEntityContent2,
    renderExportLineContent: renderExportLineContent2,
    buildExportLinesHtml: buildExportLinesHtml2,
    buildExportLineSummary: buildExportLineSummary2,
    buildExportRunMetaItems: buildExportRunMetaItems2,
    buildExportHeaderModel: buildExportHeaderModel2,
    buildExportRunMetaHtml: buildExportRunMetaHtml2,
    buildTerminalExportHeaderHtml: buildTerminalExportHeaderHtml2,
    buildTerminalExportHtml: buildTerminalExportHtml2,
    buildTerminalExportStyles: buildTerminalExportStyles2,
    getThemeExportVars: getThemeExportVars2,
    getThemeExportColorScheme: getThemeExportColorScheme2,
    fetchVendorFontFacesCss: fetchVendorFontFacesCss2,
    fetchTerminalExportCss: fetchTerminalExportCss2
  };
  if (typeof window !== "undefined") {
    window.ExportHtmlUtils = ExportHtmlUtils;
  }
})();
var {
  appendCommandOutcomeSummaryLines,
  buildExportCommandOutcomeSummary,
  buildExportDocumentModel,
  buildExportHeaderModel,
  buildExportLineSummary,
  buildExportLinesHtml,
  buildExportMetaLine,
  buildExportRunMetaHtml,
  buildExportRunMetaItems,
  buildTerminalExportHeaderHtml,
  buildTerminalExportHtml,
  buildTerminalExportStyles,
  commandOutcomeSummaryToLines,
  escapeExportAttr,
  escapeExportHtml,
  exportTimestamp,
  fetchTerminalExportCss,
  fetchVendorFontFacesCss,
  getThemeExportColorScheme,
  getThemeExportVars,
  isCommandOutcomeSummaryLine,
  isPlainEvent,
  isPromptEchoEvent,
  lineEventFromWire,
  lineLegacyClass,
  normalizeExportRunMeta,
  normalizeExportTranscriptLine,
  normalizeExportTranscriptLines,
  renderExportEntityContent,
  renderExportLineContent,
  renderExportPromptEcho
} = ExportHtmlUtils;

// app/static/js/features/workspace/workspace_drag_drop.js
var _workspaceDragPath = "";
var _workspaceDragKind = "";
function _workspaceDragApi() {
  return typeof window !== "undefined" ? window : globalThis;
}
function _workspaceDragFileListRef() {
  const api = _workspaceDragApi();
  return api.workspaceFileList || typeof workspaceFileList !== "undefined" && workspaceFileList || null;
}
function _workspaceDragShowConfirm() {
  return typeof showConfirm !== "undefined" && showConfirm || (typeof _workspaceDragApi().showConfirm === "function" ? _workspaceDragApi().showConfirm : null);
}
function _workspaceDragSourceFromEvent(event) {
  const list = _workspaceDragFileListRef();
  const row = event.target && event.target.closest ? event.target.closest('.workspace-file-row[draggable="true"]') : null;
  return row && list && list.contains(row) ? row : null;
}
function _workspaceDropTargetFromEvent(event) {
  const list = _workspaceDragFileListRef();
  const row = event.target && event.target.closest ? event.target.closest('[data-workspace-drop-target="folder"]') : null;
  return row && list && list.contains(row) ? row : null;
}
function _workspaceCanDropOnFolder(sourcePath, destinationPath) {
  const api = _workspaceDragApi();
  if (typeof api.isWorkspaceReadOnly === "function" && api.isWorkspaceReadOnly()) return false;
  const source = String(sourcePath || "").trim();
  const destination = String(destinationPath || "").trim();
  if (!source) return false;
  if (!destination) return true;
  return source !== destination && !destination.startsWith(`${source}/`);
}
async function _handleWorkspaceDropMove(event) {
  const api = _workspaceDragApi();
  const state = api.DarklabWorkspaceState || {};
  if (typeof api.workspaceCanWrite === "function" && !api.workspaceCanWrite("move Files", { toast: true })) return;
  const target = _workspaceDropTargetFromEvent(event);
  if (!target || !_workspaceCanDropOnFolder(_workspaceDragPath, target.dataset.path || "")) return;
  event.preventDefault();
  target.classList.remove("workspace-drop-target");
  const destination = target.dataset.path || "";
  const source = _workspaceDragPath;
  const kind = _workspaceDragKind === "folder" ? "folder" : "file";
  if (!source) return;
  const confirmMove = _workspaceDragShowConfirm();
  const confirmed = typeof confirmMove === "function" ? await confirmMove({
    body: {
      text: `Move ${kind} ${source}?`,
      note: destination ? `Destination folder: ${destination}` : "Destination folder: Files"
    },
    actions: [
      { id: "cancel", label: "Cancel", role: "cancel" },
      { id: "move", label: "Move", role: "primary" }
    ]
  }) : "move";
  if (confirmed !== "move") return;
  try {
    const movePath = typeof state.movePath === "function" ? state.movePath : api.moveWorkspacePath;
    if (typeof movePath === "function") await movePath(source, destination);
  } catch (err) {
    const message = typeof state.errorMessage === "function" ? state.errorMessage(err, "Unable to move item") : "Unable to move item";
    if (typeof api._showWorkspaceToast === "function") api._showWorkspaceToast(message, "error");
  }
}
var _workspaceDragFileList = _workspaceDragFileListRef();
_workspaceDragFileList?.addEventListener("dragstart", (event) => {
  const api = _workspaceDragApi();
  if (typeof api.workspaceCanWrite === "function" && !api.workspaceCanWrite("move Files", { toast: true })) {
    event.preventDefault();
    return;
  }
  const row = _workspaceDragSourceFromEvent(event);
  if (!row) return;
  _workspaceDragPath = row.dataset.path || "";
  _workspaceDragKind = row.dataset.kind || "";
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", _workspaceDragPath);
  }
  row.classList.add("workspace-dragging");
});
_workspaceDragFileList?.addEventListener("dragend", (event) => {
  const row = _workspaceDragSourceFromEvent(event);
  if (row) row.classList.remove("workspace-dragging");
  _workspaceDragFileList.querySelectorAll(".workspace-drop-target").forEach((node) => node.classList.remove("workspace-drop-target"));
  _workspaceDragPath = "";
  _workspaceDragKind = "";
});
_workspaceDragFileList?.addEventListener("dragover", (event) => {
  const target = _workspaceDropTargetFromEvent(event);
  if (!target || !_workspaceCanDropOnFolder(_workspaceDragPath, target.dataset.path || "")) return;
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
  target.classList.add("workspace-drop-target");
});
_workspaceDragFileList?.addEventListener("dragleave", (event) => {
  const target = _workspaceDropTargetFromEvent(event);
  if (!target) return;
  const related = event.relatedTarget;
  if (related && target.contains(related)) return;
  target.classList.remove("workspace-drop-target");
});
_workspaceDragFileList?.addEventListener("drop", (event) => {
  void _handleWorkspaceDropMove(event);
});
if (typeof window !== "undefined") {
}

// app/static/js/features/terminal/composer_controller.js
var COMPOSER_GLOBAL = typeof window !== "undefined" ? window : globalThis;
var cmdInput2 = cmdInput || COMPOSER_GLOBAL.cmdInput || null;
var historyPanel2 = historyPanel || COMPOSER_GLOBAL.historyPanel || null;
var runBtn2 = runBtn || COMPOSER_GLOBAL.runBtn || null;
var shellPromptWrap2 = shellPromptWrap || COMPOSER_GLOBAL.shellPromptWrap || null;
function _composerFn(name) {
  const fn = COMPOSER_GLOBAL && COMPOSER_GLOBAL[name];
  return typeof fn === "function" ? fn : null;
}
function _composerImportedFn(importedFn, name) {
  return typeof importedFn === "function" && importedFn || _composerFn(name);
}
function _composerFocusCommandInputFromGesture(...args) {
  return _composerImportedFn(
    focusCommandInputFromGesture,
    "focusCommandInputFromGesture"
  )?.(...args);
}
function _composerHasActiveTerminalConfirm() {
  return !!_composerImportedFn(hasActiveTerminalConfirm, "hasActiveTerminalConfirm")?.();
}
function _composerIsAnyPanelOverlayOpen() {
  return !!_composerImportedFn(isAnyPanelOverlayOpen, "isAnyPanelOverlayOpen")?.();
}
function _composerCloseTopmostDismissible() {
  return !!_composerImportedFn(closeTopmostDismissible, "closeTopmostDismissible")?.();
}
function _composerAutocompleteIsHintOnly(item) {
  return !!_composerImportedFn(acAutocompleteIsHintOnly, "acAutocompleteIsHintOnly")?.(item);
}
function _composerAutocompleteSelectableItems(items) {
  return _composerImportedFn(acAutocompleteSelectableItems, "acAutocompleteSelectableItems")?.(items) || [];
}
function _composerAutocompleteNextSelectableIndex(items, currentIndex, direction = 1) {
  return _composerImportedFn(
    acAutocompleteNextSelectableIndex,
    "acAutocompleteNextSelectableIndex"
  )?.(items, currentIndex, direction) ?? -1;
}
function _composerIsHistSearchMode() {
  return !!_composerImportedFn(isHistSearchMode, "isHistSearchMode")?.();
}
function _composerNavigateCmdHistory(delta) {
  const navigate = typeof navigateCmdHistory === "function" && navigateCmdHistory || _composerFn("navigateCmdHistory");
  return typeof navigate === "function" && navigate(delta);
}
function _composerEnterHistSearch() {
  _composerImportedFn(enterHistSearch, "enterHistSearch")?.();
}
function _composerHandleHistSearchInput(value) {
  _composerImportedFn(handleHistSearchInput, "handleHistSearchInput")?.(value);
}
function _composerHandleHistSearchKey(event) {
  return !!_composerImportedFn(handleHistSearchKey, "handleHistSearchKey")?.(event);
}
function _composerSetupMobileComposer() {
  _composerImportedFn(setupMobileComposer, "setupMobileComposer")?.();
}
function _composerIsEditableTarget(target) {
  return !!_composerImportedFn(isEditableTarget, "isEditableTarget")?.(target);
}
function _composerCloseOptions() {
  _composerImportedFn(closeOptions, "closeOptions")?.();
}
function _composerCloseThemeSelector() {
  _composerImportedFn(closeThemeSelector, "closeThemeSelector")?.();
}
function _composerValue(name) {
  return COMPOSER_GLOBAL ? COMPOSER_GLOBAL[name] : void 0;
}
function _composerActiveTabId() {
  const getId = typeof getActiveTabId === "function" && getActiveTabId || _composerFn("getActiveTabId");
  return typeof getId === "function" ? getId() : _composerValue("activeTabId") || null;
}
function _composerActiveTab() {
  const getActive = typeof getActiveTab === "function" && getActiveTab || _composerFn("getActiveTab");
  return typeof getActive === "function" ? getActive() : null;
}
function _composerSetState(next = {}) {
  const setState = typeof setComposerState === "function" && setComposerState || _composerFn("setComposerState");
  return typeof setState === "function" ? setState(next) : null;
}
function _composerInputs() {
  const readInputs = typeof getComposerInputs === "function" && getComposerInputs || _composerFn("getComposerInputs");
  return typeof readInputs === "function" ? readInputs() : {};
}
function _composerGetValue(fallback = "") {
  const readValue = typeof getComposerValue === "function" && getComposerValue || _composerFn("getComposerValue");
  if (typeof readValue === "function") {
    const value = readValue();
    if (value || !(cmdInput2 && typeof cmdInput2.value === "string" && cmdInput2.value)) return value;
  }
  const composer = typeof getComposerState === "function" ? getComposerState() : null;
  if (composer && typeof composer.value === "string") return composer.value;
  if (cmdInput2 && typeof cmdInput2.value === "string") return cmdInput2.value;
  return fallback;
}
function _composerVisibleInput() {
  const readInput = typeof getVisibleComposerInput === "function" && getVisibleComposerInput || _composerFn("getVisibleComposerInput");
  return typeof readInput === "function" ? readInput() : cmdInput2;
}
function _composerSyncShellPrompt() {
  const syncPrompt = typeof hasComposerPromptHandler === "function" && hasComposerPromptHandler("syncShellPrompt") ? syncShellPrompt : _composerFn("syncShellPrompt");
  if (typeof syncPrompt === "function") syncPrompt();
}
function _composerSyncSelection(start, end, options) {
  const syncSelection = typeof syncComposerSelection === "function" && syncComposerSelection || _composerFn("syncComposerSelection");
  if (typeof syncSelection === "function") return syncSelection(start, end, options);
  return null;
}
function _composerAcHide() {
  const hide = _composerFn("acHide");
  if (typeof hide === "function") hide();
}
function _composerRefocus(options) {
  const refocus = typeof refocusComposerAfterAction === "function" && refocusComposerAfterAction || _composerFn("refocusComposerAfterAction");
  if (typeof refocus === "function") refocus(options);
}
function _composerSubmitCommand(rawCmd, options) {
  const submitCommand = typeof submitComposerCommand === "function" && submitComposerCommand || _composerFn("submitComposerCommand");
  if (typeof submitCommand === "function") return submitCommand(rawCmd, options);
  const run = typeof runCommand === "function" && runCommand || _composerFn("runCommand");
  return typeof run === "function" ? run() : void 0;
}
function _refreshWorkspaceFileCache() {
  const refresh = typeof refreshWorkspaceFileCache !== "undefined" && refreshWorkspaceFileCache || _composerFn("refreshWorkspaceFileCache");
  if (typeof refresh === "function") return refresh();
  return null;
}
function _isMajorSurfaceOpenForPromptPaste() {
  return _composerImportedFn(isFaqOverlayOpen, "isFaqOverlayOpen")?.() || false || (_composerImportedFn(isOptionsOverlayOpen, "isOptionsOverlayOpen")?.() || false) || (_composerImportedFn(isThemeOverlayOpen, "isThemeOverlayOpen")?.() || false) || (_composerImportedFn(isWorkflowsOverlayOpen, "isWorkflowsOverlayOpen")?.() || false) || (_composerImportedFn(isWorkspaceOverlayOpen, "isWorkspaceOverlayOpen")?.() || false) || (_composerFn("isHistoryCompareOverlayOpen")?.() || false) || (_composerImportedFn(isHistoryRunOverlayOpen, "isHistoryRunOverlayOpen")?.() || false) || (_composerFn("isHistoryPanelOpen")?.() || false) || (_composerFn("isConfirmOpen")?.() || false);
}
function _readComposerAutocompleteState() {
  const getState = typeof getAutocompleteState === "function" && getAutocompleteState || _composerFn("getAutocompleteState");
  const apiState = typeof getState === "function" ? getState() : {};
  return {
    filtered: Array.isArray(apiState.filtered) ? apiState.filtered : [],
    index: apiState.index ?? -1
  };
}
function _writeComposerAutocompleteState(next = {}) {
  const setState = typeof setAutocompleteState === "function" && setAutocompleteState || _composerFn("setAutocompleteState");
  if (typeof setState === "function") setState(next);
  return _readComposerAutocompleteState();
}
function _writeComposerAutocompleteCatalog(data = {}) {
  const writeCatalog = typeof setAutocompleteCatalog === "function" && setAutocompleteCatalog || _composerFn("setAutocompleteCatalog");
  if (typeof writeCatalog === "function") return writeCatalog(data);
  return {};
}
function _composerWelcomeActive() {
  const getWelcome = typeof getWelcomeState === "function" && getWelcomeState || _composerFn("getWelcomeState");
  return !!(_composerValue("_welcomeActive") || typeof getWelcome === "function" && getWelcome().active);
}
function _composerWelcomeDone() {
  const getWelcome = typeof getWelcomeState === "function" && getWelcomeState || _composerFn("getWelcomeState");
  return !!(_composerValue("_welcomeDone") || typeof getWelcome === "function" && getWelcome().done);
}
function _setComposerWelcomePromptAfterSettle(value) {
  const setWelcome = typeof setWelcomeState === "function" && setWelcomeState || _composerFn("setWelcomeState");
  if (typeof setWelcome === "function") setWelcome({ promptAfterSettle: !!value });
  if (COMPOSER_GLOBAL) COMPOSER_GLOBAL._welcomePromptAfterSettle = !!value;
}
function _composerWelcomeOwns(tabId) {
  const welcomeOwns = typeof welcomeOwnsTab === "function" && welcomeOwnsTab || _composerFn("welcomeOwnsTab");
  return typeof welcomeOwns === "function" && welcomeOwns(tabId);
}
function _composerRequestWelcomeSettle(tabId) {
  const requestSettle = typeof requestWelcomeSettle === "function" && requestWelcomeSettle || _composerFn("requestWelcomeSettle");
  return typeof requestSettle === "function" ? requestSettle(tabId) : false;
}
document.addEventListener("paste", (e) => {
  if (e.defaultPrevented) return;
  if (!cmdInput2 || _composerIsEditableTarget(e.target) || _isMajorSurfaceOpenForPromptPaste()) return;
  const clipboard = e.clipboardData || (typeof window !== "undefined" ? window.clipboardData : null);
  const text = clipboard && typeof clipboard.getData === "function" ? clipboard.getData("text/plain") || clipboard.getData("text") || "" : "";
  if (!text) return;
  e.preventDefault();
  if (typeof window !== "undefined" && typeof window.getSelection === "function") {
    const selection = window.getSelection();
    if (selection && typeof selection.removeAllRanges === "function") selection.removeAllRanges();
  }
  _composerRefocus({ preventScroll: true });
  const value = _composerGetValue(cmdInput2.value || "");
  const { start, end } = getCmdSelection(value);
  replaceCmdRange(value, start, end, text);
});
var bindOutsideClick = _composerImportedFn(bindOutsideClickClose, "bindOutsideClickClose");
if (historyPanel2 && bindOutsideClick) {
  bindOutsideClick(historyPanel2, {
    triggers: null,
    isOpen: () => _composerImportedFn(isHistoryPanelOpen, "isHistoryPanelOpen")?.() || false,
    onClose: () => _composerImportedFn(hideHistoryPanel, "hideHistoryPanel")?.(),
    exemptSelectors: [".hist-chip-overflow", '[data-action="history"]', ".modal-overlay", "#history-compare-overlay"]
  });
}
if (bindOutsideClick && shellPromptWrap2) {
  bindOutsideClick(shellPromptWrap2, {
    isOpen: () => _composerFn("isAcDropdownOpen")?.() || false,
    onClose: () => {
      _composerAcHide();
    },
    exemptSelectors: [".ac-dropdown", "#mobile-composer"]
  });
}
function _handleRunningComposerShortcut(e) {
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === "c" || e.key === "C")) {
    e.preventDefault();
    e.stopPropagation();
    _composerImportedFn(confirmKill, "confirmKill")?.(_composerActiveTabId());
    return true;
  }
  const isCtrlD = e.ctrlKey && !e.metaKey && !e.altKey && (e.key === "d" || e.key === "D" || (_composerImportedFn(eventMatchesLetter, "eventMatchesLetter")?.(e, "d") || false));
  if (isCtrlD) {
    e.preventDefault();
    e.stopPropagation();
    return true;
  }
  if (_composerImportedFn(handleTabShortcut, "handleTabShortcut")?.(e)) {
    e.stopPropagation();
    return true;
  }
  if (_composerImportedFn(handleActionShortcut, "handleActionShortcut")?.(e)) {
    e.stopPropagation();
    return true;
  }
  if (_composerImportedFn(handleChromeShortcut, "handleChromeShortcut")?.(e)) {
    e.stopPropagation();
    return true;
  }
  return false;
}
function _selectionTouchesElement(el) {
  if (!el || typeof window === "undefined" || typeof window.getSelection !== "function") return false;
  const selection = window.getSelection();
  if (!selection) return false;
  const nodes = [selection.anchorNode, selection.focusNode];
  if (selection.rangeCount > 0) nodes.push(selection.getRangeAt(0).commonAncestorContainer);
  return nodes.some((node) => !!node && el.contains(node.nodeType === Node.ELEMENT_NODE ? node : node.parentNode));
}
var _promptPointerSelectionState = null;
var _suppressPromptFocusUntil = 0;
var _pendingPromptFocusTimer = null;
if (shellPromptWrap2 && cmdInput2) {
  shellPromptWrap2.addEventListener("pointerdown", (e) => {
    if (e.target === runBtn2 || e.target && e.target.closest && e.target.closest("#run-btn")) return;
    if (useMobileTerminalViewportMode()) {
      e.preventDefault();
      _composerFocusCommandInputFromGesture();
      return;
    }
    if (_pendingPromptFocusTimer) {
      clearTimeout(_pendingPromptFocusTimer);
      _pendingPromptFocusTimer = null;
    }
    _promptPointerSelectionState = {
      id: e.pointerId,
      x: e.clientX,
      y: e.clientY,
      moved: false
    };
    if (document.activeElement === cmdInput2 && typeof cmdInput2.blur === "function") {
      cmdInput2.blur();
    }
  });
  shellPromptWrap2.addEventListener("pointermove", (e) => {
    const state = _promptPointerSelectionState;
    if (!state || state.id !== e.pointerId || state.moved) return;
    if (Math.abs(e.clientX - state.x) > 4 || Math.abs(e.clientY - state.y) > 4) {
      state.moved = true;
    }
  });
  shellPromptWrap2.addEventListener("pointerup", (e) => {
    const state = _promptPointerSelectionState;
    if (!state || state.id !== e.pointerId) return;
    if (state.moved) _suppressPromptFocusUntil = Date.now() + 250;
    _promptPointerSelectionState = null;
  });
  shellPromptWrap2.addEventListener("pointercancel", () => {
    _promptPointerSelectionState = null;
  });
  shellPromptWrap2.addEventListener("touchstart", (e) => {
    if (useMobileTerminalViewportMode()) {
      e.preventDefault();
      _composerFocusCommandInputFromGesture();
    }
  }, { passive: false });
  shellPromptWrap2.addEventListener("click", (e) => {
    if (e.target === runBtn2 || e.target && e.target.closest && e.target.closest("#run-btn")) return;
    if (useMobileTerminalViewportMode()) {
      _composerFocusCommandInputFromGesture();
      return;
    }
    if (e.detail > 1 || Date.now() < _suppressPromptFocusUntil) return;
    if (_selectionTouchesElement(shellPromptWrap2)) return;
    if (_pendingPromptFocusTimer) clearTimeout(_pendingPromptFocusTimer);
    _pendingPromptFocusTimer = setTimeout(() => {
      _pendingPromptFocusTimer = null;
      if (_selectionTouchesElement(shellPromptWrap2)) return;
      if (Date.now() < _suppressPromptFocusUntil) return;
      _composerFocusCommandInputFromGesture();
    }, 220);
  });
  shellPromptWrap2.addEventListener("dblclick", () => {
    if (_pendingPromptFocusTimer) {
      clearTimeout(_pendingPromptFocusTimer);
      _pendingPromptFocusTimer = null;
    }
    _suppressPromptFocusUntil = Date.now() + 400;
  });
}
if (typeof _bindMobileComposerInteractions === "function") {
  _bindMobileComposerInteractions(_mobileUiLayoutRefs);
}
if (cmdInput2) {
  cmdInput2.addEventListener("focus", () => {
    _composerSetState({
      value: cmdInput2.value || "",
      selectionStart: typeof cmdInput2.selectionStart === "number" ? cmdInput2.selectionStart : (cmdInput2.value || "").length,
      selectionEnd: typeof cmdInput2.selectionEnd === "number" ? cmdInput2.selectionEnd : (cmdInput2.value || "").length,
      activeInput: "desktop"
    });
    if (shellPromptWrap2) shellPromptWrap2.classList.add("shell-prompt-focused");
    _composerSyncShellPrompt();
    syncMobileViewportState();
  });
  cmdInput2.addEventListener("blur", () => {
    if (shellPromptWrap2) shellPromptWrap2.classList.remove("shell-prompt-focused");
    _composerSyncShellPrompt();
    syncMobileViewportState();
  });
  cmdInput2.addEventListener("select", _composerSyncShellPrompt);
  cmdInput2.addEventListener("keyup", _composerSyncShellPrompt);
}
if (typeof document !== "undefined") {
  document.addEventListener("selectionchange", () => {
    if (!cmdInput2) return;
    if (shellPromptWrap2 && _selectionTouchesElement(shellPromptWrap2)) {
      if (_pendingPromptFocusTimer) {
        clearTimeout(_pendingPromptFocusTimer);
        _pendingPromptFocusTimer = null;
      }
      return;
    }
    const composerInputs = _composerInputs();
    const mobileInput = composerInputs.mobile || null;
    if (document.activeElement === cmdInput2) {
      _composerSetState({
        value: cmdInput2.value || "",
        selectionStart: typeof cmdInput2.selectionStart === "number" ? cmdInput2.selectionStart : (cmdInput2.value || "").length,
        selectionEnd: typeof cmdInput2.selectionEnd === "number" ? cmdInput2.selectionEnd : (cmdInput2.value || "").length,
        activeInput: "desktop"
      });
      _composerSyncShellPrompt();
      return;
    }
    if (mobileInput && document.activeElement === mobileInput) {
      _composerSetState({
        value: mobileInput.value || "",
        selectionStart: typeof mobileInput.selectionStart === "number" ? mobileInput.selectionStart : (mobileInput.value || "").length,
        selectionEnd: typeof mobileInput.selectionEnd === "number" ? mobileInput.selectionEnd : (mobileInput.value || "").length,
        activeInput: "mobile"
      });
      _composerSyncShellPrompt();
    }
  });
}
var _composerApiFetch = typeof apiFetch2 === "function" && apiFetch2 || _composerFn("apiFetch");
if (typeof _composerApiFetch === "function") _composerApiFetch("/autocomplete").then((r) => r.json()).then((data) => {
  _writeComposerAutocompleteCatalog(data);
  _composerImportedFn(loadSessionVariables, "loadSessionVariables")?.()?.catch?.(() => {
  });
  _composerImportedFn(loadRecentValues, "loadRecentValues")?.()?.catch?.(() => {
  });
  _composerImportedFn(loadProjectAutocompleteTargets, "loadProjectAutocompleteTargets")?.()?.catch?.(() => {
  });
  _composerImportedFn(loadScheduleAutocompleteHints, "loadScheduleAutocompleteHints")?.()?.catch?.(() => {
  });
  _composerImportedFn(loadWatcherAutocompleteHints, "loadWatcherAutocompleteHints")?.()?.catch?.(() => {
  });
  _refreshWorkspaceFileCache()?.catch?.(() => {
  });
  const refreshSearchDiscoverability = _composerFn("scheduleSearchDiscoverabilityRefresh") || _composerFn("refreshSearchDiscoverabilityUi");
  refreshSearchDiscoverability?.();
}).catch((err) => {
  const log = typeof logClientError2 === "function" && logClientError2 || _composerFn("logClientError");
  log?.("failed to load /autocomplete", err);
});
cmdInput2.addEventListener("input", () => {
  _composerImportedFn(exportedNormalizeComposerSmartPeriod, "normalizeComposerSmartPeriod")?.(cmdInput2);
  if (_composerImportedFn(isHistoryPanelOpen, "isHistoryPanelOpen")?.()) {
    _composerImportedFn(hideHistoryPanel, "hideHistoryPanel")?.();
  }
  if (_composerIsHistSearchMode()) {
    _composerHandleHistSearchInput(cmdInput2.value);
    const _hsTab = _composerActiveTab();
    if (_hsTab) _hsTab.followOutput = true;
    const _hsOut = document.querySelector(".tab-panel.active .output");
    if (_hsOut) _hsOut.scrollTop = _hsOut.scrollHeight;
    return;
  }
  _composerImportedFn(handleComposerInputChange, "handleComposerInputChange")?.(cmdInput2);
  const _activeTab = _composerActiveTab();
  if (_activeTab && _activeTab.st !== "running") {
    _activeTab.draftInput = _composerGetValue(cmdInput2.value);
    _composerImportedFn(schedulePersistTabSessionState, "schedulePersistTabSessionState")?.();
  }
});
cmdInput2.addEventListener("keydown", (e) => {
  if (_composerIsAnyPanelOverlayOpen()) {
    if (e.key === "Escape") {
      if (!_composerCloseTopmostDismissible()) {
        _composerImportedFn(closeFaq, "closeFaq")?.();
        _composerImportedFn(closeWorkflows, "closeWorkflows")?.();
        _composerImportedFn(closeWorkspace, "closeWorkspace")?.();
        _composerCloseOptions();
        _composerCloseThemeSelector();
      }
      _composerRefocus({ defer: true });
      e.preventDefault();
    }
    return;
  }
  if (_composerIsHistSearchMode()) {
    if (_composerHandleHistSearchKey(e)) return;
  }
  if (_composerImportedFn(isActiveTabRunning, "isActiveTabRunning")?.()) {
    if (_handleRunningComposerShortcut(e)) return;
    _composerAcHide();
    e.preventDefault();
    return;
  }
  const eventMatchesCodeFn = _composerImportedFn(eventMatchesCode, "eventMatchesCode");
  const isWordArrowLeft = e.key === "ArrowLeft" || eventMatchesCodeFn?.(e, "ArrowLeft");
  const isWordArrowRight = e.key === "ArrowRight" || eventMatchesCodeFn?.(e, "ArrowRight");
  if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey && (isWordArrowLeft || isWordArrowRight)) {
    e.preventDefault();
    e.stopPropagation();
    _composerImportedFn(syncFocusedComposerState, "syncFocusedComposerState")?.(cmdInput2);
    const value = _composerGetValue("");
    const { start, end } = getCmdSelection(value);
    const next = isWordArrowLeft ? findWordBoundaryLeft(value, start) : findWordBoundaryRight(value, end);
    const input = _composerVisibleInput();
    _composerSyncSelection(next, next, { input });
    if (input && typeof input.setSelectionRange === "function" && input.selectionStart !== next) {
      input.setSelectionRange(next, next);
    } else if (!input && cmdInput2 && typeof cmdInput2.setSelectionRange === "function") {
      cmdInput2.setSelectionRange(next, next);
    }
    _composerSyncShellPrompt();
    return;
  }
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === "r" || e.key === "R")) {
    e.preventDefault();
    _composerEnterHistSearch();
    return;
  }
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === "c" || e.key === "C")) {
    e.preventDefault();
    const currentTabId = _composerActiveTabId();
    if (_composerWelcomeActive() && !_composerWelcomeDone() && _composerWelcomeOwns(currentTabId)) {
      _setComposerWelcomePromptAfterSettle(true);
      _composerRequestWelcomeSettle(currentTabId);
      _composerRefocus({ defer: true });
      return;
    }
    const activeTab = _composerActiveTab();
    if (activeTab && activeTab.st === "running") {
      _composerImportedFn(confirmKill, "confirmKill")?.(currentTabId);
      return;
    }
    if (_composerHasActiveTerminalConfirm()) {
      _composerImportedFn(cancelPendingTerminalConfirm, "cancelPendingTerminalConfirm")?.(currentTabId);
      return;
    }
    _composerImportedFn(interruptPromptLine, "interruptPromptLine")?.(currentTabId);
    return;
  }
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === "w" || e.key === "W")) {
    e.preventDefault();
    const value = _composerGetValue("");
    const { start, end } = getCmdSelection(value);
    if (start !== end) {
      replaceCmdRange(value, start, end);
      return;
    }
    if (start === 0) return;
    const cut = findWordBoundaryLeft(value, start);
    replaceCmdRange(value, cut, start);
    return;
  }
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === "u" || e.key === "U")) {
    e.preventDefault();
    const value = _composerGetValue("");
    const { start, end } = getCmdSelection(value);
    if (start !== end) {
      replaceCmdRange(value, start, end);
      return;
    }
    if (start === 0) return;
    replaceCmdRange(value, 0, start);
    return;
  }
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === "a" || e.key === "A")) {
    e.preventDefault();
    if (_composerImportedFn(syncComposerSelection, "syncComposerSelection")) _composerSyncSelection(0, 0);
    else if (cmdInput2 && typeof cmdInput2.setSelectionRange === "function") cmdInput2.setSelectionRange(0, 0);
    _composerSyncShellPrompt();
    return;
  }
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === "k" || e.key === "K")) {
    e.preventDefault();
    const value = _composerGetValue("");
    const { start, end } = getCmdSelection(value);
    if (start !== end) {
      replaceCmdRange(value, start, end);
      return;
    }
    if (start >= value.length) return;
    replaceCmdRange(value, start, value.length);
    return;
  }
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === "e" || e.key === "E")) {
    e.preventDefault();
    const value = _composerGetValue("");
    const end = value.length;
    if (_composerImportedFn(syncComposerSelection, "syncComposerSelection")) _composerSyncSelection(end, end);
    else if (cmdInput2 && typeof cmdInput2.setSelectionRange === "function") cmdInput2.setSelectionRange(end, end);
    _composerSyncShellPrompt();
    return;
  }
  const eventMatchesLetterFn = _composerImportedFn(eventMatchesLetter, "eventMatchesLetter");
  if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey && eventMatchesLetterFn?.(e, "b")) {
    e.preventDefault();
    _composerImportedFn(syncFocusedComposerState, "syncFocusedComposerState")?.(cmdInput2);
    const value = _composerGetValue("");
    const { start } = getCmdSelection(value);
    const next = findWordBoundaryLeft(value, start);
    if (_composerImportedFn(syncComposerSelection, "syncComposerSelection")) _composerSyncSelection(next, next);
    else if (cmdInput2 && typeof cmdInput2.setSelectionRange === "function") cmdInput2.setSelectionRange(next, next);
    _composerSyncShellPrompt();
    return;
  }
  if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey && eventMatchesLetterFn?.(e, "f")) {
    e.preventDefault();
    _composerImportedFn(syncFocusedComposerState, "syncFocusedComposerState")?.(cmdInput2);
    const value = _composerGetValue("");
    const { end } = getCmdSelection(value);
    const next = findWordBoundaryRight(value, end);
    if (_composerImportedFn(syncComposerSelection, "syncComposerSelection")) _composerSyncSelection(next, next);
    else if (cmdInput2 && typeof cmdInput2.setSelectionRange === "function") cmdInput2.setSelectionRange(next, next);
    _composerSyncShellPrompt();
    return;
  }
  if (e.key === "Enter") {
    const currentTabId = _composerActiveTabId();
    if (_composerWelcomeActive() && !_composerWelcomeDone() && _composerWelcomeOwns(currentTabId) && !_composerGetValue("").trim()) {
      e.preventDefault();
      _composerRequestWelcomeSettle(currentTabId);
      _composerRefocus({ defer: true });
      return;
    }
    const acState = _readComposerAutocompleteState();
    if (!_composerHasActiveTerminalConfirm() && acState.index >= 0 && acState.filtered[acState.index] && !_composerAutocompleteIsHintOnly(acState.filtered[acState.index])) {
      e.preventDefault();
      _composerFn("acAccept")?.(acState.filtered[acState.index]);
    } else {
      e.preventDefault();
      _composerAcHide();
      _composerSubmitCommand(_composerGetValue(""), { dismissKeyboard: true });
    }
    return;
  }
  if (e.key === "Tab" && !e.altKey && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    if (_composerHasActiveTerminalConfirm()) {
      _composerAcHide();
      return;
    }
    const acState = _readComposerAutocompleteState();
    const selectableItems = _composerAutocompleteSelectableItems(acState.filtered);
    if (selectableItems.length === 1) {
      _composerFn("acAccept")?.(selectableItems[0]);
    } else if (selectableItems.length > 0) {
      if (_composerFn("acExpandSharedPrefix")?.(selectableItems)) return;
      let nextIndex;
      if (acState.index < 0 || !_composerImportedFn(isAcDropdownOpen, "isAcDropdownOpen")?.()) {
        nextIndex = _composerAutocompleteNextSelectableIndex(acState.filtered, -1, 1);
      } else if (e.shiftKey) {
        nextIndex = _composerAutocompleteNextSelectableIndex(acState.filtered, acState.index, -1);
      } else {
        nextIndex = _composerAutocompleteNextSelectableIndex(acState.filtered, acState.index, 1);
      }
      _writeComposerAutocompleteState({ index: nextIndex });
      _composerFn("acShow")?.(acState.filtered);
    }
    return;
  }
  if (e.key === "ArrowDown") {
    e.preventDefault();
    if (_composerHasActiveTerminalConfirm()) {
      _composerAcHide();
      return;
    }
    const acOpen = _composerImportedFn(isAcDropdownOpen, "isAcDropdownOpen")?.();
    const acState = _readComposerAutocompleteState();
    const selectableItems = _composerAutocompleteSelectableItems(acState.filtered);
    if (acOpen && selectableItems.length) {
      const nextIndex = _composerAutocompleteNextSelectableIndex(acState.filtered, acState.index, 1);
      _writeComposerAutocompleteState({ index: nextIndex });
      _composerFn("acShow")?.(acState.filtered);
      return;
    }
    if (_composerNavigateCmdHistory(-1)) _composerAcHide();
    return;
  }
  if (e.key === "ArrowUp") {
    e.preventDefault();
    if (_composerHasActiveTerminalConfirm()) {
      _composerAcHide();
      return;
    }
    const acOpen = _composerImportedFn(isAcDropdownOpen, "isAcDropdownOpen")?.();
    const acState = _readComposerAutocompleteState();
    const selectableItems = _composerAutocompleteSelectableItems(acState.filtered);
    if (acOpen && selectableItems.length) {
      const nextIndex = _composerAutocompleteNextSelectableIndex(acState.filtered, acState.index, -1);
      _writeComposerAutocompleteState({ index: nextIndex });
      _composerFn("acShow")?.(acState.filtered);
      return;
    }
    if (_composerNavigateCmdHistory(1)) _composerAcHide();
    return;
  }
  if (e.key === "Escape") {
    _composerAcHide();
    return;
  }
  if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey && !e.isComposing && !(_composerWelcomeActive() && !_composerWelcomeDone() && _composerWelcomeOwns(_composerActiveTabId()))) {
    e.preventDefault();
    const value = _composerGetValue("");
    const { start, end } = getCmdSelection(value);
    replaceCmdRange(value, start, end, e.key);
    return;
  }
});
if (typeof window !== "undefined") {
  window.addEventListener("resize", syncMobileViewportState);
  if (window.visualViewport && typeof window.visualViewport.addEventListener === "function") {
    window.visualViewport.addEventListener("resize", syncMobileViewportState);
  }
}
if (runBtn2) runBtn2.addEventListener("click", () => {
  _composerSubmitCommand(_composerGetValue(""), { dismissKeyboard: true });
});
_composerSyncShellPrompt();
_composerSyncShellPrompt();
_composerImportedFn(syncRunButtonDisabled, "syncRunButtonDisabled")?.();
_composerSetupMobileComposer();

// app/static/js/e2e_test_hooks.js
var E2E_GLOBAL = typeof window !== "undefined" ? window : globalThis;
function _isE2EBrowser() {
  return !!(E2E_GLOBAL && E2E_GLOBAL.navigator && E2E_GLOBAL.navigator.webdriver === true);
}
function _defineE2EProperty(name, descriptor) {
  if (!E2E_GLOBAL) return;
  Object.defineProperty(E2E_GLOBAL, name, {
    configurable: true,
    enumerable: false,
    ...descriptor
  });
}
function _stateValue(name) {
  const state = typeof getAppState === "function" ? getAppState() : {};
  return state ? state[name] : void 0;
}
function _setStateValue(name, value) {
  const state = typeof getAppState === "function" ? getAppState() : {};
  if (state) state[name] = value;
}
function _defineStateAlias(name) {
  _defineE2EProperty(name, {
    get() {
      return _stateValue(name);
    },
    set(value) {
      _setStateValue(name, value);
    }
  });
}
function _welcomeStateValue(name) {
  const state = typeof getWelcomeState === "function" ? getWelcomeState() : {};
  return state ? state[name] : void 0;
}
function _defineWelcomeStateAlias(globalName, stateName) {
  _defineE2EProperty(globalName, {
    get() {
      return _welcomeStateValue(stateName);
    }
  });
}
function installE2ETestHooks() {
  if (!_isE2EBrowser()) return;
  const showHistoryPanel = () => showPanelOverlay(document.getElementById("history-panel"));
  const hooks = {
    apiFetch: apiFetch2,
    acHide,
    acShow,
    appendLine,
    appendLines,
    clearTab: clearTab2,
    closeOptions,
    getActiveTabId,
    getAutocompleteMatches,
    getOutput,
    getSessionId,
    getTab,
    hideHistoryPanel,
    isHistoryPanelOpen,
    loadRecentValues,
    limitAutocompleteMatchesForDisplay,
    loadScheduleAutocompleteHints,
    loadSessionVariables,
    loadWatcherAutocompleteHints,
    persistTabSessionStateNow,
    refreshSearchDiscoverabilityUi,
    refreshHistoryPanel: refreshHistoryPanel2,
    requestWelcomeSettle: requestWelcomeSettle2,
    runCommand: runCommand2,
    scheduleSearchDiscoverabilityRefresh,
    setTabLabel,
    setTabStatus,
    showHistoryPanel,
    submitComposerCommand: submitComposerCommand2,
    submitVisibleComposerCommand: submitVisibleComposerCommand2,
    openFaq: openFaq2,
    openOptions,
    openProjectWorkspace,
    refreshActiveProjectContext,
    refreshProjectWorkspace,
    openShortcuts,
    openThemeSelector,
    openWorkflows: openWorkflows2,
    openWorkspace,
    _readRecentValues,
    toggleHistoryPanelSurface: toggleHistoryPanelSurface2,
    updateOutputFollowButton,
    welcomeOwnsTab: welcomeOwnsTab2
  };
  E2E_GLOBAL.__darklabE2E = Object.freeze({ ...hooks });
  Object.entries(hooks).forEach(([name, value]) => {
    if (typeof value === "function") {
      _defineE2EProperty(name, { value, writable: true });
    }
  });
  _defineE2EProperty("SESSION_ID", {
    get() {
      return typeof getSessionId === "function" ? getSessionId() : "";
    }
  });
  _defineE2EProperty("activeTabId", {
    get() {
      return typeof getActiveTabId === "function" ? getActiveTabId() : null;
    }
  });
  [
    "acSuggestions",
    "acContextRegistry",
    "acWordlists",
    "acSpecialCommands",
    "acBuiltinCommandRoots",
    "cmdHistory",
    "sessionVariables"
  ].forEach(_defineStateAlias);
  _defineWelcomeStateAlias("_welcomeActive", "active");
  _defineWelcomeStateAlias("_welcomeBootPending", "bootPending");
  _defineWelcomeStateAlias("_welcomeDone", "done");
  _defineWelcomeStateAlias("_welcomeTabId", "tabId");
}
installE2ETestHooks();

// app/static/js/shell_chrome.js
var importedOpenStatusMonitor = openStatusMonitor;
var importedProjectActivity;
var importedProjectArtifacts;
var importedProjectDetails;
var importedProjectEntities;
var importedProjectEntityEditor;
var importedProjectFilters;
var importedProjectFindings;
var importedProjectFindingsBoard;
var importedProjectFindingsData;
var importedProjectList;
var importedProjectMobileCompare;
var importedProjectMobileDetail;
var importedProjectMobileShell;
var importedProjectMonitoring;
var importedProjectNavigation;
var importedProjectNestedSheets;
var importedProjectOverview;
var importedProjectPackages;
var importedProjectReport;
var importedProjectRuns;
var importedProjectTargets;
var importedProjectWorkspaceActions;
var importedProjectWorkspaceBootstrap;
var importedProjectWorkspaceEvents;
var importedProjectWorkspaceLifecycle;
var importedProjectWorkspaceRenderer;
var importedProjectWorkspaceShell;
(function initShellChrome(global) {
  if (typeof document === "undefined") return;
  function _shellFn(name, imported = null) {
    if (typeof imported === "function") return imported;
    const fn = global && global[name];
    return typeof fn === "function" ? fn : null;
  }
  function _shellValue(name, imported = void 0) {
    return imported !== void 0 ? imported : global ? global[name] : void 0;
  }
  function _projectModule(name, imported = void 0) {
    return _shellValue(name, imported) || null;
  }
  const _shellApiFetch = (...args) => _shellFn("apiFetch", apiFetch2)?.(...args);
  const _shellLogClientError = (...args) => _shellFn("logClientError", logClientError2)?.(...args);
  const _shellShowToast = (...args) => _shellFn("showToast", showToast)?.(...args);
  const _shellBindPressable = (...args) => _shellFn("bindPressable", bindPressable)?.(...args);
  const _shellBindOutsideClickClose = (...args) => _shellFn("bindOutsideClickClose", bindOutsideClickClose)?.(...args);
  const _shellBindDisclosure = (...args) => _shellFn("bindDisclosure", bindDisclosure)?.(...args);
  const _shellGetPreference = (name) => _shellFn("getPreference", getPreference)?.(name) || "";
  const _shellSetPreferenceCookie = (name, value) => _shellFn("setPreferenceCookie", setPreferenceCookie)?.(name, value);
  const _shellRefocusComposer = (...args) => _shellFn("refocusComposerAfterAction", refocusComposerAfterAction)?.(...args);
  const _shellSetComposerValue = (...args) => _shellFn("setComposerValue", setComposerValue)?.(...args);
  const _shellDownloadBlobAsAttachment = (...args) => _shellFn("downloadBlobAsAttachment", downloadBlobAsAttachment)?.(...args);
  const _shellDownloadUrlAsAttachment = (...args) => _shellFn("downloadUrlAsAttachment", downloadUrlAsAttachment)?.(...args);
  const _shellMaskSessionToken = (token) => _shellFn("maskSessionToken", maskSessionToken)?.(token) || token;
  const _shellShowConfirm = (...args) => _shellFn("showConfirm", showConfirm)?.(...args);
  const _shellUseMobileTerminalViewportMode = () => !!_shellFn("useMobileTerminalViewportMode", useMobileTerminalViewportMode)?.();
  const _shellResetCmdHistoryNav = (...args) => _shellFn("resetCmdHistoryNav", resetCmdHistoryNav)?.(...args);
  const _shellGetActiveTabId = () => _shellFn("getActiveTabId", getActiveTabId)?.() || null;
  const _shellGetAppState = () => _shellFn("getAppState", getAppState)?.() || {};
  const _shellGetTab = (id) => _shellFn("getTab", getTab)?.(id) || null;
  const _shellTabs = () => {
    const list = _shellFn("getTabs", getTabs)?.();
    return Array.isArray(list) ? list : [];
  };
  const _shellEmitUiEvent = (...args) => _shellFn("emitUiEvent", emitUiEvent)?.(...args);
  const _shellOnUiEvent = (...args) => _shellFn("onUiEvent", onUiEvent)?.(...args);
  async function _shellLoadLazyModal(importedLoader, globalLoaderName) {
    const loader = _shellFn(globalLoaderName, importedLoader);
    return typeof loader === "function" ? loader() : null;
  }
  async function _shellOpenAtlas(...args) {
    const atlas = await _shellLoadLazyModal(loadAtlasOverlay, "loadAtlasOverlay");
    const open = atlas?.openAtlas || _shellFn("openAtlas", openAtlas);
    return typeof open === "function" ? open(...args) : void 0;
  }
  async function _shellOpenCommandRegistry(...args) {
    const registry = await _shellLoadLazyModal(loadCommandRegistry, "loadCommandRegistry");
    const open = registry?.openCommandRegistry || _shellFn("openCommandRegistry", openCommandRegistry);
    return typeof open === "function" ? open(...args) : void 0;
  }
  async function _shellOpenFindingsBoard(...args) {
    const board = await _shellLoadLazyModal(loadFindingsBoard, "loadFindingsBoard");
    const open = board?.openFindingsBoard || _shellFn("openFindingsBoard");
    return typeof open === "function" ? open(...args) : void 0;
  }
  async function _shellOpenSchedulesModal(...args) {
    const schedules = await _shellLoadLazyModal(loadSchedulesModal, "loadSchedulesModal");
    const open = schedules?.openSchedulesModal || _shellFn("openSchedulesModal");
    return typeof open === "function" ? open(...args) : void 0;
  }
  async function _shellOpenWatchersModal(...args) {
    const watchers = await _shellLoadLazyModal(loadWatchersModal, "loadWatchersModal");
    const open = watchers?.openWatchersModal || _shellFn("openWatchersModal");
    return typeof open === "function" ? open(...args) : void 0;
  }
  function _shellActiveTeamScopeCan(capability) {
    const can = typeof activeTeamScopeCan !== "undefined" && activeTeamScopeCan || null;
    return typeof can === "function" ? can(capability) : true;
  }
  function _shellTeamScopeDeniedMessage(action) {
    const denied = typeof teamScopeDeniedMessage !== "undefined" && teamScopeDeniedMessage || null;
    return typeof denied === "function" ? denied(action) : `View-only team members can't ${action}. Switch to Personal or ask for operator access.`;
  }
  function _shellEnhanceAppSelects() {
    return typeof enhanceAppSelects !== "undefined" && enhanceAppSelects || null;
  }
  const rail = document.getElementById("rail");
  if (!rail) return;
  const railCollapseBtn = document.getElementById("rail-collapse-btn");
  const railResizeHandle = document.getElementById("rail-resize-handle");
  const railSplitArea = document.getElementById("rail-split-area");
  const railSplitter = document.getElementById("rail-splitter");
  const railSectionRecent = document.getElementById("rail-section-recent");
  const railRecentBody = document.getElementById("rail-recent-list");
  const railRecentCount = document.getElementById("rail-recent-count");
  const railRecentHeader = document.getElementById("rail-recent-header");
  const railSectionWorkflows = document.getElementById("rail-section-workflows");
  const railWorkflowsBody = document.getElementById("rail-workflows-list");
  const railWorkflowsHeader = document.getElementById("rail-workflows-header");
  const railWorkflowsCount = document.getElementById("rail-workflows-count");
  const railNav = document.getElementById("rail-nav");
  const railMoreBtn = document.getElementById("rail-more-btn");
  const railMoreMenu = document.getElementById("rail-more-menu");
  const hud = document.getElementById("hud");
  const hudLastExitEl = document.getElementById("hud-last-exit");
  const hudTabsEl = document.getElementById("hud-tabs");
  const hudLatencyEl = document.getElementById("hud-latency");
  const hudSessionEl = document.getElementById("hud-session");
  const hudProjectCell = document.getElementById("hud-project-cell");
  const hudProjectEl = document.getElementById("hud-project");
  const hudUptimeEl = document.getElementById("hud-uptime");
  const hudClockEl = document.getElementById("hud-clock");
  const hudDbEl = document.getElementById("hud-db");
  const hudRedisEl = document.getElementById("hud-redis");
  const projectWorkspaceOverlay = document.getElementById("project-workspace-overlay");
  const projectWorkspaceModal = document.getElementById("project-workspace-modal");
  const projectWorkspaceBody = document.getElementById("project-workspace-body");
  const projectWorkspacePagination = document.getElementById("project-workspace-pagination");
  const projectExplorerBody = document.getElementById("project-explorer-body");
  const projectWorkspaceSubtitle = document.getElementById("project-workspace-subtitle");
  const projectWorkspaceCreateForm = document.getElementById("project-workspace-create-form");
  const projectWorkspaceNameInput = document.getElementById("project-workspace-name");
  const projectMobileRoot = document.getElementById("project-mobile-root");
  const projectMobileListView = document.getElementById("project-mobile-list-view");
  const projectMobileBody = document.getElementById("project-mobile-body");
  const projectMobilePagination = document.getElementById("project-mobile-pagination");
  const projectMobileSummary = document.getElementById("project-mobile-summary");
  const projectMobileCreateForm = document.getElementById("project-mobile-create-form");
  const projectMobileNameInput = document.getElementById("project-mobile-name");
  const projectMobileDetailView = document.getElementById("project-mobile-detail-view");
  const projectMobileDetailTopbar = document.getElementById("project-mobile-detail-topbar");
  const projectMobileTabs = document.getElementById("project-mobile-tabs");
  const projectMobileDetailBody = document.getElementById("project-mobile-detail-body");
  let projectWorkspaceOpenToken = 0;
  const projectTargetEditorOverlay = document.getElementById("project-target-editor-overlay");
  const projectTargetEditorTitle = document.getElementById("project-target-editor-title");
  const projectTargetCreateForm = document.getElementById("project-target-create-form");
  const projectTargetTypeSelect = document.getElementById("project-target-type");
  const projectTargetValueInput = document.getElementById("project-target-value");
  const projectTargetValueHelp = document.getElementById("project-target-value-help");
  const projectTargetValueError = document.getElementById("project-target-value-error");
  const projectTargetLabelInput = document.getElementById("project-target-label");
  const projectTargetNotesInput = document.getElementById("project-target-notes");
  const projectTargetSubmitButton = document.getElementById("project-target-submit");
  const projectPackageManifestOverlay = document.getElementById("project-package-manifest-overlay");
  const projectPackageManifestTitle = document.getElementById("project-package-manifest-title");
  const projectPackageManifestSummary = document.getElementById("project-package-manifest-summary");
  const projectPackageManifestJson = document.getElementById("project-package-manifest-json");
  const projectPackageWizardOverlay = document.getElementById("project-package-wizard-overlay");
  const projectPackageWizardBody = document.getElementById("project-package-wizard-body");
  const projectEntityEditorOverlay = document.getElementById("project-entity-editor-overlay");
  const projectEntityEditorTitle = document.getElementById("project-entity-editor-title");
  const projectEntityEditorSubtitle = document.getElementById("project-entity-editor-subtitle");
  const projectEntityEditorForm = document.getElementById("project-entity-editor-form");
  const projectEntityLabelsInput = document.getElementById("project-entity-labels");
  const projectEntityNoteInput = document.getElementById("project-entity-note");
  const projectEntityActivityRoot = document.getElementById("project-entity-activity");
  const projectEntitySubmitButton = document.getElementById("project-entity-submit");
  const projectNotesForm = document.getElementById("project-notes-form");
  const projectNotesInput = document.getElementById("project-notes-input");
  const projectLabelsForm = document.getElementById("project-labels-form");
  const projectLabelsInput = document.getElementById("project-labels-input");
  const projectLabelsSaveButton = document.getElementById("project-labels-save-btn");
  const projectWorkspaceMessage = document.getElementById("project-workspace-message");
  const EntityMetadataClient = typeof DarklabEntityMetadata !== "undefined" && DarklabEntityMetadata || {};
  const PREF_COLLAPSED = "pref_rail_collapsed";
  const PREF_WIDTH = "pref_rail_width";
  const PREF_RECENT = "pref_rail_recent_open";
  const PREF_WORKFLOWS = "pref_rail_workflows_open";
  const MIN_W = 180, MAX_W = 360, DEFAULT_W = 214;
  const NARROW_BRAND_W = 200;
  const MIN_SECTION_H = 80;
  const PROJECT_TARGET_HELPERS = typeof ProjectTargetValidation !== "undefined" && ProjectTargetValidation || null;
  if (!PROJECT_TARGET_HELPERS) throw new Error("ProjectTargetValidation is unavailable");
  const PROJECT_TARGET_TYPES = PROJECT_TARGET_HELPERS.TARGET_TYPES;
  const PROJECT_WORKSPACE_CONSTANTS = typeof exportedDarklabProjectWorkspaceConstants !== "undefined" && exportedDarklabProjectWorkspaceConstants || null;
  if (!PROJECT_WORKSPACE_CONSTANTS) throw new Error("DarklabProjectWorkspaceConstants is unavailable");
  const readBool = (name, dflt) => {
    const v = _shellGetPreference(name);
    if (v === "1" || v === "true") return true;
    if (v === "0" || v === "false") return false;
    return dflt;
  };
  const writePref = (name, value) => {
    _shellSetPreferenceCookie(name, String(value));
  };
  const ui = {
    collapsed: readBool(PREF_COLLAPSED, false),
    railW: (() => {
      const raw = parseInt(_shellGetPreference(PREF_WIDTH), 10);
      return Number.isFinite(raw) ? Math.max(MIN_W, Math.min(MAX_W, raw)) : DEFAULT_W;
    })(),
    recentOpen: readBool(PREF_RECENT, true),
    workflowsOpen: readBool(PREF_WORKFLOWS, true),
    recentHeight: null
    // null → auto-size next time Workflows opens
  };
  let allWorkflows = [];
  const projectWorkspaceStateFactory = exportedDarklabProjectWorkspaceState && exportedDarklabProjectWorkspaceState.createProjectWorkspaceState;
  if (typeof projectWorkspaceStateFactory !== "function") throw new Error("DarklabProjectWorkspaceState is unavailable");
  const projectWorkspaceState = projectWorkspaceStateFactory();
  const PROJECT_WORKSPACE_LAZY_GLOBALS = [
    ["DarklabProjectDetails", "createProjectDetailsController"],
    ["DarklabProjectList", "createProjectListController"],
    ["DarklabProjectNavigation", "createProjectNavigationController"],
    ["DarklabProjectEntityEditor", "createProjectEntityEditorController"],
    ["DarklabProjectWorkspaceActions", "createProjectWorkspaceActionsController"],
    ["DarklabProjectWorkspaceShell", "createProjectWorkspaceShellController"],
    ["DarklabProjectWorkspaceLifecycle", "createProjectWorkspaceLifecycleController"],
    ["DarklabProjectWorkspaceRenderer", "createProjectWorkspaceRendererController"],
    ["DarklabProjectWorkspaceBootstrap", "createProjectWorkspaceBootstrapController"],
    ["DarklabProjectNestedSheets", "createProjectNestedSheetsController"],
    ["DarklabProjectWorkspaceEvents", "createProjectWorkspaceEventsController"],
    ["DarklabProjectTargets", "createProjectTargetsController"],
    ["DarklabProjectRuns", "createProjectRunsController"],
    ["DarklabProjectMobileCompare", "createProjectMobileCompareController"],
    ["DarklabProjectMobileShell", "createProjectMobileShellController"],
    ["DarklabProjectMobileDetail", "createProjectMobileDetailController"],
    ["DarklabProjectFindingsData", "createProjectFindingsDataController"],
    ["DarklabProjectFilters", "createProjectFiltersController"],
    ["DarklabProjectEntities", "createProjectEntitiesController"],
    ["DarklabProjectFindings", "createProjectFindingsController"],
    ["DarklabProjectFindingsBoard", "createProjectFindingsBoardController"]
  ];
  let projectWorkspaceModulesPromise = null;
  let projectWorkspaceBootstrapped = false;
  function _projectWorkspaceModulesReady() {
    return PROJECT_WORKSPACE_LAZY_GLOBALS.every(([name, factory]) => global[name] && typeof global[name][factory] === "function");
  }
  function _projectWorkspaceOverlayOpenFallback() {
    return !!(projectWorkspaceOverlay && projectWorkspaceOverlay.classList.contains("open"));
  }
  function _bindProjectWorkspaceIfNeeded() {
    if (projectWorkspaceBootstrapped) return;
    _projectWorkspaceBootstrapController().bindAll();
    projectWorkspaceBootstrapped = true;
  }
  async function _ensureProjectWorkspaceModules() {
    if (_projectWorkspaceModulesReady()) {
      _bindProjectWorkspaceIfNeeded();
      return;
    }
    if (!projectWorkspaceModulesPromise) {
      const loader = global.loadProjectWorkspace;
      if (typeof loader !== "function") throw new Error("Project workspace loader is unavailable");
      projectWorkspaceModulesPromise = loader().then(() => {
        if (!_projectWorkspaceModulesReady()) throw new Error("Project workspace modules did not finish loading");
        _bindProjectWorkspaceIfNeeded();
      }).finally(() => {
        projectWorkspaceModulesPromise = null;
      });
    }
    await projectWorkspaceModulesPromise;
  }
  function applyCollapsed() {
    rail.classList.toggle("rail-collapsed", ui.collapsed);
    rail.classList.toggle("rail-narrow-brand", !ui.collapsed && ui.railW <= NARROW_BRAND_W);
    rail.style.setProperty("--rail-w", ui.collapsed ? "44px" : `${ui.railW}px`);
    if (railCollapseBtn) {
      railCollapseBtn.textContent = ui.collapsed ? "»" : "«";
      const label = ui.collapsed ? "Expand sidebar (Alt+\\)" : "Collapse sidebar (Alt+\\)";
      railCollapseBtn.title = label;
      railCollapseBtn.setAttribute("aria-label", label);
    }
  }
  function applyWidth() {
    rail.classList.toggle("rail-narrow-brand", !ui.collapsed && ui.railW <= NARROW_BRAND_W);
    if (!ui.collapsed) rail.style.setProperty("--rail-w", `${ui.railW}px`);
  }
  function applySectionsState() {
    if (!railSplitArea) return;
    railSectionRecent?.classList.toggle("closed", !ui.recentOpen);
    railSectionWorkflows?.classList.toggle("closed", !ui.workflowsOpen);
    const bothOpen = ui.recentOpen && ui.workflowsOpen;
    railSplitArea.classList.toggle("both-open", bothOpen);
    railSplitArea.classList.toggle("workflows-closed", !ui.workflowsOpen);
    railSplitArea.classList.toggle("recent-fixed", bothOpen && ui.recentHeight != null);
    if (railSplitter) railSplitter.hidden = !bothOpen;
    if (bothOpen && ui.recentHeight != null) {
      railSplitArea.style.setProperty("--recent-h", `${ui.recentHeight}px`);
    } else {
      railSplitArea.style.removeProperty("--recent-h");
    }
  }
  function setCollapsed(next) {
    ui.collapsed = !!next;
    applyCollapsed();
    writePref(PREF_COLLAPSED, ui.collapsed ? "1" : "0");
  }
  function toggleRailCollapsed2() {
    setCollapsed(!ui.collapsed);
  }
  railCollapseBtn?.addEventListener("click", () => setCollapsed(!ui.collapsed));
  let railDrag = null;
  function beginRailDrag(clientX) {
    railDrag = { startX: clientX, startW: ui.railW };
    rail.classList.add("rail-dragging");
    document.body.style.cursor = "ew-resize";
    document.body.style.userSelect = "none";
  }
  railResizeHandle?.addEventListener("mousedown", (e) => {
    if (ui.collapsed) return;
    e.preventDefault();
    beginRailDrag(e.clientX);
  });
  let splitterDrag = null;
  function beginSplitterDrag(clientY) {
    if (!railSplitArea) return;
    splitterDrag = { rect: railSplitArea.getBoundingClientRect() };
    rail.classList.add("rail-dragging");
    document.body.style.cursor = "ns-resize";
    document.body.style.userSelect = "none";
  }
  railSplitter?.addEventListener("mousedown", (e) => {
    e.preventDefault();
    beginSplitterDrag(e.clientY);
  });
  function clampRecentHeight(pixels) {
    if (!railSplitArea) return pixels;
    const areaH = railSplitArea.getBoundingClientRect().height;
    return Math.max(MIN_SECTION_H, Math.min(areaH - MIN_SECTION_H - 6, pixels));
  }
  window.addEventListener("mousemove", (e) => {
    if (railDrag) {
      const next = Math.max(MIN_W, Math.min(MAX_W, railDrag.startW + (e.clientX - railDrag.startX)));
      ui.railW = next;
      applyWidth();
    } else if (splitterDrag) {
      const offsetY = e.clientY - splitterDrag.rect.top;
      ui.recentHeight = clampRecentHeight(offsetY);
      applySectionsState();
    }
  });
  window.addEventListener("mouseup", () => {
    if (railDrag) {
      railDrag = null;
      writePref(PREF_WIDTH, ui.railW);
    }
    if (splitterDrag) splitterDrag = null;
    rail.classList.remove("rail-dragging");
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  });
  function onRecentToggle(open) {
    ui.recentOpen = open;
    writePref(PREF_RECENT, open ? "1" : "0");
    applySectionsState();
  }
  function onWorkflowsToggle(open) {
    ui.workflowsOpen = open;
    writePref(PREF_WORKFLOWS, open ? "1" : "0");
    applySectionsState();
  }
  if (railRecentHeader) {
    _shellBindDisclosure(railRecentHeader, {
      panel: null,
      openClass: null,
      initialOpen: ui.recentOpen,
      onToggle: onRecentToggle
    });
  }
  if (railWorkflowsHeader) {
    _shellBindDisclosure(railWorkflowsHeader, {
      panel: null,
      openClass: null,
      initialOpen: ui.workflowsOpen,
      onToggle: onWorkflowsToggle
    });
  }
  function renderRailRecent() {
    if (!railRecentBody) return;
    const recentPreviewHistory = _shellGetAppState().recentPreviewHistory;
    const items = Array.isArray(recentPreviewHistory) ? recentPreviewHistory : [];
    railRecentBody.replaceChildren();
    if (railRecentCount) railRecentCount.textContent = String(items.length);
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "rail-section-empty";
      empty.textContent = "no commands yet";
      railRecentBody.appendChild(empty);
      return;
    }
    const starred = typeof _getStarred === "function" ? _getStarred() : /* @__PURE__ */ new Set();
    const ordered = [
      ...items.filter((cmd) => starred.has(cmd)),
      ...items.filter((cmd) => !starred.has(cmd))
    ];
    ordered.forEach((cmd) => {
      const isStarred = starred.has(cmd);
      const row = document.createElement("button");
      row.type = "button";
      row.className = "rail-item" + (isStarred ? " starred" : "");
      row.title = cmd;
      const text = document.createElement("span");
      text.className = "rail-item-text";
      text.textContent = cmd;
      row.appendChild(text);
      row.addEventListener("click", () => {
        _shellSetComposerValue(cmd, cmd.length, cmd.length);
        _shellRefocusComposer({ preventScroll: true });
        _shellResetCmdHistoryNav();
      });
      railRecentBody.appendChild(row);
    });
  }
  function renderRailWorkflows(items) {
    allWorkflows = Array.isArray(items) ? items.slice() : [];
    if (railWorkflowsCount) railWorkflowsCount.textContent = String(allWorkflows.length);
    if (!railWorkflowsBody) return;
    railWorkflowsBody.replaceChildren();
    if (!allWorkflows.length) {
      const empty = document.createElement("div");
      empty.className = "rail-section-empty";
      empty.textContent = "no workflows";
      railWorkflowsBody.appendChild(empty);
      return;
    }
    allWorkflows.forEach((wf, idx) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "rail-item";
      const label = wf.title || wf.name || `workflow ${idx + 1}`;
      row.title = [label, wf.description].filter(Boolean).join("\n");
      const glyph = document.createElement("span");
      glyph.className = "drill-chev";
      glyph.setAttribute("aria-hidden", "true");
      glyph.textContent = "›";
      const text = document.createElement("span");
      text.className = "rail-item-text";
      text.textContent = label;
      row.appendChild(glyph);
      row.appendChild(text);
      row.addEventListener("click", () => openScopedWorkflow(idx));
      railWorkflowsBody.appendChild(row);
    });
  }
  async function openScopedWorkflow(idx) {
    const item = allWorkflows[idx];
    if (!item) return;
    const loadWorkflowsFn = _shellFn("loadWorkflows");
    if (loadWorkflowsFn) {
      try {
        await loadWorkflowsFn();
      } catch (_) {
      }
    }
    const openWorkflowsFn = _shellFn("openWorkflows", openWorkflows2);
    if (openWorkflowsFn) {
      openWorkflowsFn({ items: [item], emitCatalogEvent: false });
    } else {
      _shellFn("showWorkflowsOverlay", showWorkflowsOverlay)?.();
    }
  }
  function positionRailMoreMenu() {
    if (!railMoreBtn || !railMoreMenu || railMoreMenu.classList.contains("u-hidden")) return;
    if (typeof railMoreBtn.getBoundingClientRect !== "function") return;
    const triggerRect = railMoreBtn.getBoundingClientRect();
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1024;
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 768;
    const gutter = 8;
    const menuWidth = Math.max(railMoreMenu.offsetWidth || 220, 180);
    const menuHeight = Math.max(railMoreMenu.offsetHeight || railMoreMenu.getBoundingClientRect?.().height || 1, 1);
    const maxMenuHeight = Math.max(120, viewportHeight - gutter * 2);
    const effectiveMenuHeight = Math.min(menuHeight, maxMenuHeight);
    const desiredArrowFromBottom = 32;
    const triggerCenterY = triggerRect.top + triggerRect.height / 2;
    const preferredTop = triggerCenterY - Math.max(28, effectiveMenuHeight - desiredArrowFromBottom);
    const top = Math.min(
      Math.max(gutter, preferredTop),
      Math.max(gutter, viewportHeight - effectiveMenuHeight - gutter)
    );
    const left = Math.min(
      Math.max(gutter, triggerRect.right + 8),
      Math.max(gutter, viewportWidth - menuWidth - gutter)
    );
    const arrowLimit = Math.max(18, effectiveMenuHeight - 18);
    const arrowY = Math.min(arrowLimit, Math.max(18, triggerCenterY - top - 4));
    railMoreMenu.style.position = "fixed";
    railMoreMenu.style.left = `${left}px`;
    railMoreMenu.style.top = `${top}px`;
    railMoreMenu.style.right = "auto";
    railMoreMenu.style.bottom = "auto";
    railMoreMenu.style.maxHeight = `${maxMenuHeight}px`;
    railMoreMenu.style.overflowY = menuHeight > maxMenuHeight ? "auto" : "";
    railMoreMenu.style.setProperty("--rail-more-arrow-y", `${arrowY}px`);
  }
  function closeRailMoreMenu() {
    if (!railMoreBtn || !railMoreMenu) return;
    railMoreBtn.setAttribute("aria-expanded", "false");
    railMoreMenu.classList.add("u-hidden");
    railMoreMenu.style.position = "";
    railMoreMenu.style.left = "";
    railMoreMenu.style.top = "";
    railMoreMenu.style.right = "";
    railMoreMenu.style.bottom = "";
    railMoreMenu.style.maxHeight = "";
    railMoreMenu.style.overflowY = "";
    railMoreMenu.style.removeProperty("--rail-more-arrow-y");
  }
  function openRailMoreMenu() {
    if (!railMoreBtn || !railMoreMenu) return;
    railMoreBtn.setAttribute("aria-expanded", "true");
    railMoreMenu.classList.remove("u-hidden");
    positionRailMoreMenu();
    railMoreMenu.querySelector("[data-action]:not(.u-hidden)")?.focus?.();
  }
  function toggleRailMoreMenu() {
    if (railMoreBtn?.getAttribute("aria-expanded") === "true") {
      closeRailMoreMenu();
    } else {
      openRailMoreMenu();
    }
  }
  function openStatusMonitorFromHud(source) {
    const openStatusMonitor2 = _shellFn("openStatusMonitor", importedOpenStatusMonitor);
    if (typeof openStatusMonitor2 !== "function") return;
    void openStatusMonitor2({ source });
  }
  function makeHudCellOpenStatusMonitor(cell, source, label) {
    if (!cell || cell.dataset.statusMonitorTrigger === "1") return;
    cell.dataset.statusMonitorTrigger = "1";
    cell.classList.add("hud-cell-clickable", "hud-action-cell");
    cell.setAttribute("role", "button");
    cell.setAttribute("tabindex", "0");
    cell.setAttribute("aria-haspopup", "dialog");
    cell.setAttribute("aria-label", label);
    cell.addEventListener("click", () => openStatusMonitorFromHud(source));
    cell.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      openStatusMonitorFromHud(source);
    });
  }
  function bindHudStatusMonitorTriggers() {
    makeHudCellOpenStatusMonitor(
      document.getElementById("hud-status-cell"),
      "status",
      "Open status monitor from status"
    );
    makeHudCellOpenStatusMonitor(
      document.getElementById("hud-last-exit-cell") || document.getElementById("hud-last-exit")?.closest(".hud-cell"),
      "last-exit",
      "Open status monitor from last exit"
    );
    makeHudCellOpenStatusMonitor(
      document.getElementById("hud-tabs-cell") || document.getElementById("hud-tabs")?.closest(".hud-cell"),
      "tabs",
      "Open status monitor from tabs"
    );
  }
  railNav?.addEventListener("click", (e) => {
    const item = e.target.closest?.("[data-action]");
    if (!item) return;
    const action = item.dataset.action;
    if (action === "diag") {
      closeRailMoreMenu();
      return;
    }
    e.preventDefault();
    if (action === "rail-more") {
      toggleRailMoreMenu();
      return;
    }
    closeRailMoreMenu();
    if (action === "history" && typeof toggleHistoryPanelSurface2 === "function") {
      toggleHistoryPanelSurface2();
      return;
    }
    const openStatusMonitor2 = _shellFn("openStatusMonitor", importedOpenStatusMonitor);
    if (action === "atlas") {
      void _shellOpenAtlas({ source: "rail" });
      return;
    }
    if (action === "findings-board") {
      void _shellOpenFindingsBoard({ source: "rail" });
      return;
    }
    if (action === "status-monitor" && typeof openStatusMonitor2 === "function") {
      void openStatusMonitor2({ source: "rail" });
      return;
    }
    if (action === "command-registry") {
      void _shellOpenCommandRegistry();
      return;
    }
    if (action === "schedules") {
      void _shellOpenSchedulesModal();
      return;
    }
    if (action === "watchers") {
      void _shellOpenWatchersModal();
      return;
    }
    if (action === "projects") {
      void openProjectWorkspace2();
      return;
    }
    if (action === "options" && typeof openOptions === "function") {
      openOptions();
      return;
    }
    if (action === "theme" && typeof openThemeSelector === "function") {
      openThemeSelector();
      return;
    }
    if (action === "workspace" && typeof openWorkspace === "function") {
      openWorkspace();
      return;
    }
    if (action === "faq" && typeof openFaq2 === "function") {
      openFaq2();
    }
  });
  document.addEventListener("click", (event) => {
    if (!railMoreMenu || railMoreMenu.classList.contains("u-hidden")) return;
    const target = event.target;
    if (target instanceof Node && railNav?.contains(target)) return;
    closeRailMoreMenu();
  });
  railNav?.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeRailMoreMenu();
      railMoreBtn?.focus?.();
    }
  });
  window.addEventListener("resize", positionRailMoreMenu);
  let hudProjectMenu = null;
  let hudProjectMenuSearchInput = null;
  let hudProjectMenuProjects = null;
  let hudProjectMenuNote = null;
  let hudProjectMenuSearchTimer = null;
  let hudProjectMenuRequestId = 0;
  function _isHudProjectMenuOpen() {
    return !!(hudProjectMenu && !hudProjectMenu.classList.contains("u-hidden"));
  }
  function _openProjectsFromHudMenu(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    closeHudProjectMenu();
    void openProjectWorkspace2();
  }
  function _canCreateProjectFromHud() {
    return _shellActiveTeamScopeCan("mutate_projects");
  }
  function _projectCreateDeniedTitle() {
    return _shellTeamScopeDeniedMessage("create team projects");
  }
  function _showHudProjectToast(message, tone = "info") {
    _shellShowToast(message, tone);
  }
  async function _hudProjectResponseMessage(resp, fallback) {
    try {
      const data = await resp.json();
      return data?.error || data?.message || fallback;
    } catch (_) {
      return fallback;
    }
  }
  function _createHudProjectMenuButton({ label, action, title = "", disabled = false, selected = false, onActivate }) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "dropdown-item dropdown-item-compact";
    btn.dataset.action = action || "";
    btn.setAttribute("role", selected ? "menuitemradio" : "menuitem");
    if (selected) btn.setAttribute("aria-checked", "true");
    btn.textContent = label;
    if (title) btn.title = title;
    if (disabled) {
      btn.disabled = true;
      btn.setAttribute("aria-disabled", "true");
    }
    const pressable = _shellFn("bindPressable", bindPressable);
    if (pressable) {
      pressable(btn, {
        refocusComposer: false,
        onActivate
      });
    } else if (typeof onActivate === "function") {
      btn.addEventListener("click", onActivate);
    }
    return btn;
  }
  function _positionHudProjectMenu() {
    if (!hudProjectMenu || !hudProjectCell || !_isHudProjectMenuOpen()) return;
    const rect = hudProjectCell.getBoundingClientRect();
    const menuWidth = hudProjectMenu.offsetWidth || 260;
    const viewportWidth = global.innerWidth || document.documentElement.clientWidth || 0;
    const left = Math.max(8, Math.min(rect.left, Math.max(8, viewportWidth - menuWidth - 8)));
    hudProjectMenu.style.left = `${left}px`;
    hudProjectMenu.style.bottom = `${Math.max(8, (global.innerHeight || 0) - rect.top - 1)}px`;
  }
  function closeHudProjectMenu({ restoreFocus = false } = {}) {
    if (!hudProjectMenu) return;
    if (hudProjectMenuSearchTimer) {
      global.clearTimeout?.(hudProjectMenuSearchTimer);
      hudProjectMenuSearchTimer = null;
    }
    hudProjectMenuRequestId += 1;
    hudProjectMenu.classList.add("u-hidden");
    hudProjectCell?.classList.remove("open");
    hudProjectCell?.setAttribute("aria-expanded", "false");
    if (restoreFocus && hudProjectCell && typeof hudProjectCell.focus === "function") {
      hudProjectCell.focus({ preventScroll: true });
    }
  }
  function _focusHudProjectMenuItem(delta) {
    if (!hudProjectMenu) return;
    const items = Array.from(hudProjectMenu.querySelectorAll(".dropdown-item:not([disabled])"));
    if (!items.length) return;
    const currentIdx = items.indexOf(document.activeElement);
    const fallbackIdx = delta > 0 ? -1 : 0;
    const nextIdx = (currentIdx >= 0 ? currentIdx : fallbackIdx) + delta;
    items[(nextIdx + items.length) % items.length]?.focus({ preventScroll: true });
  }
  function _setHudProjectMenuNote(text) {
    if (!hudProjectMenuNote) return;
    hudProjectMenuNote.textContent = text || "";
    hudProjectMenuNote.classList.toggle("u-hidden", !text);
  }
  function _scheduleHudProjectMenuLoad(query) {
    if (hudProjectMenuSearchTimer) {
      global.clearTimeout?.(hudProjectMenuSearchTimer);
      hudProjectMenuSearchTimer = null;
    }
    hudProjectMenuSearchTimer = global.setTimeout?.(() => {
      hudProjectMenuSearchTimer = null;
      void _loadHudProjectMenu(query);
    }, 120) || null;
  }
  async function _selectHudProject(project, event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    if (!project || !project.id) return;
    try {
      const resp = await _shellApiFetch("/projects/active", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: project.id })
      });
      if (!resp.ok) throw new Error(await _hudProjectResponseMessage(resp, "Unable to set active project."));
      const data = await resp.json();
      _setActiveProject(data?.project || project);
      closeHudProjectMenu();
      _showHudProjectToast("Active project updated.");
    } catch (err) {
      const message = err?.message || "Unable to set active project.";
      _setHudProjectMenuNote(message);
      _shellLogClientError("failed to set active project from HUD switcher", err);
      _showHudProjectToast(message, "error");
    }
  }
  async function _clearHudProject(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    try {
      const resp = await _shellApiFetch("/projects/active", { method: "DELETE" });
      if (!resp.ok) throw new Error(await _hudProjectResponseMessage(resp, "Unable to clear active project."));
      _setActiveProject(null);
      closeHudProjectMenu();
      _showHudProjectToast("Active project cleared.");
    } catch (err) {
      const message = err?.message || "Unable to clear active project.";
      _setHudProjectMenuNote(message);
      _shellLogClientError("failed to clear active project from HUD switcher", err);
      _showHudProjectToast(message, "error");
    }
  }
  function _openCreateProjectFromHudMenu(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    if (!_canCreateProjectFromHud()) {
      const message = _projectCreateDeniedTitle();
      _setHudProjectMenuNote(message);
      _showHudProjectToast(message, "error");
      return;
    }
    closeHudProjectMenu();
    void openProjectWorkspace2();
  }
  function _renderHudProjectMenuProjects(projects, query = "") {
    if (!hudProjectMenuProjects) return;
    hudProjectMenuProjects.textContent = "";
    const activeProject = _activeProject();
    const activeProjectId = activeProject?.id ? String(activeProject.id) : "";
    const rows = Array.isArray(projects) ? projects : [];
    if (activeProjectId) {
      hudProjectMenuProjects.appendChild(_createHudProjectMenuButton({
        label: "No project",
        action: "clear-active-project",
        title: "Clear active project",
        onActivate: _clearHudProject
      }));
    }
    rows.forEach((project) => {
      if (!project || !project.id) return;
      const name = _projectDisplayName(project) || String(project.id);
      const selected = String(project.id) === activeProjectId;
      hudProjectMenuProjects.appendChild(_createHudProjectMenuButton({
        label: selected ? `${name} (active)` : name,
        action: "select-project",
        title: selected ? `Active project: ${name}` : `Set active project: ${name}`,
        selected,
        onActivate: (event) => _selectHudProject(project, event)
      }));
    });
    if (!hudProjectMenuProjects.children.length) {
      _setHudProjectMenuNote(query ? "No matching projects." : "No projects yet.");
    } else {
      _setHudProjectMenuNote("");
    }
    _positionHudProjectMenu();
  }
  async function _loadHudProjectMenu(query = "") {
    if (!hudProjectMenuProjects) return;
    const requestId = ++hudProjectMenuRequestId;
    const trimmedQuery = String(query || "").trim();
    const params = new URLSearchParams({ mode: "switcher", limit: "8" });
    if (trimmedQuery) params.set("q", trimmedQuery);
    if (!hudProjectMenuProjects.children.length) {
      _setHudProjectMenuNote("Loading projects...");
    }
    try {
      const resp = await _shellApiFetch(`/projects?${params.toString()}`, { cache: "no-store" });
      if (requestId !== hudProjectMenuRequestId) return;
      if (!resp.ok) throw new Error(await _hudProjectResponseMessage(resp, "Unable to load projects."));
      const data = await resp.json();
      if (requestId !== hudProjectMenuRequestId) return;
      _renderHudProjectMenuProjects(data?.projects || [], trimmedQuery);
    } catch (err) {
      if (requestId !== hudProjectMenuRequestId) return;
      const message = err?.message || "Unable to load projects.";
      hudProjectMenuProjects.textContent = "";
      _setHudProjectMenuNote(message);
      _shellLogClientError("failed to load HUD project switcher", err);
    }
  }
  function _refreshHudProjectCreateAction() {
    const createBtn = hudProjectMenu?.querySelector('[data-action="create-project"]');
    if (!createBtn) return;
    const allowed = _canCreateProjectFromHud();
    createBtn.disabled = !allowed;
    createBtn.setAttribute("aria-disabled", allowed ? "false" : "true");
    createBtn.title = allowed ? "Open Projects to create a project" : _projectCreateDeniedTitle();
  }
  function _ensureHudProjectMenu() {
    if (hudProjectMenu) return hudProjectMenu;
    const menu = document.createElement("div");
    menu.id = "hud-project-menu";
    menu.className = "hud-project-menu dropdown-surface dropdown-up u-hidden";
    menu.setAttribute("role", "menu");
    menu.setAttribute("aria-label", "Active project switcher");
    const search = document.createElement("input");
    search.type = "search";
    search.className = "hud-project-search";
    search.placeholder = "search projects";
    search.setAttribute("aria-label", "Search projects");
    search.autocomplete = "off";
    search.spellcheck = false;
    search.addEventListener("click", (event) => event.stopPropagation());
    search.addEventListener("input", (event) => {
      event.stopPropagation();
      _scheduleHudProjectMenuLoad(search.value);
    });
    search.addEventListener("keydown", (event) => {
      event.stopPropagation();
      if (event.key === "Escape") {
        event.preventDefault();
        closeHudProjectMenu({ restoreFocus: true });
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        _focusHudProjectMenuItem(1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        _focusHudProjectMenuItem(-1);
      } else if (event.key === "Tab") {
        closeHudProjectMenu();
      }
    });
    menu.appendChild(search);
    const projectsSection = document.createElement("div");
    projectsSection.className = "hud-project-menu-section";
    menu.appendChild(projectsSection);
    const note = document.createElement("div");
    note.className = "hud-project-menu-note u-hidden";
    menu.appendChild(note);
    const divider = document.createElement("div");
    divider.className = "hud-project-menu-divider";
    menu.appendChild(divider);
    const createProject = _createHudProjectMenuButton({
      label: "Create project",
      action: "create-project",
      title: "Open Projects to create a project",
      disabled: !_canCreateProjectFromHud(),
      onActivate: _openCreateProjectFromHudMenu
    });
    menu.appendChild(createProject);
    const openProjects = _createHudProjectMenuButton({
      label: "Open Projects",
      action: "open-projects",
      onActivate: _openProjectsFromHudMenu
    });
    menu.appendChild(openProjects);
    menu.addEventListener("click", (event) => event.stopPropagation());
    menu.addEventListener("keydown", (event) => {
      event.stopPropagation();
      if (event.key === "Escape") {
        event.preventDefault();
        closeHudProjectMenu({ restoreFocus: true });
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        _focusHudProjectMenuItem(1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        _focusHudProjectMenuItem(-1);
      } else if (event.key === "Tab") {
        closeHudProjectMenu();
      }
    });
    document.body.appendChild(menu);
    hudProjectMenu = menu;
    hudProjectMenuSearchInput = search;
    hudProjectMenuProjects = projectsSection;
    hudProjectMenuNote = note;
    const bindOutsideClickClose2 = _shellFn("bindOutsideClickClose", bindOutsideClickClose);
    if (bindOutsideClickClose2) {
      bindOutsideClickClose2(menu, {
        capture: true,
        triggers: hudProjectCell,
        isOpen: _isHudProjectMenuOpen,
        onClose: () => closeHudProjectMenu()
      });
    }
    return hudProjectMenu;
  }
  function toggleHudProjectMenu(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    _closeHudSaveMenu();
    _ensureHudProjectMenu();
    if (_isHudProjectMenuOpen()) {
      closeHudProjectMenu({ restoreFocus: true });
      return;
    }
    hudProjectMenu.classList.remove("u-hidden");
    hudProjectCell?.classList.add("open");
    hudProjectCell?.setAttribute("aria-expanded", "true");
    _refreshHudProjectCreateAction();
    if (hudProjectMenuSearchInput) hudProjectMenuSearchInput.value = "";
    _renderHudProjectMenuProjects([], "");
    void _loadHudProjectMenu("");
    _positionHudProjectMenu();
    requestAnimationFrame(_positionHudProjectMenu);
    hudProjectMenuSearchInput?.focus({ preventScroll: true });
  }
  if (hudProjectCell && _shellFn("bindPressable", bindPressable)) {
    _shellBindPressable(hudProjectCell, {
      refocusComposer: false,
      onActivate: toggleHudProjectMenu
    });
  } else {
    hudProjectCell?.addEventListener("click", toggleHudProjectMenu);
    hudProjectCell?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") toggleHudProjectMenu(event);
    });
  }
  global.addEventListener?.("resize", _positionHudProjectMenu);
  global.addEventListener?.("scroll", _positionHudProjectMenu, true);
  document.addEventListener?.("app:active-project-changed", () => {
    if (!_isHudProjectMenuOpen()) return;
    _refreshHudProjectCreateAction();
    void _loadHudProjectMenu(hudProjectMenuSearchInput?.value || "");
  });
  document.addEventListener?.("app:scope-changed", () => {
    closeHudProjectMenu();
    loadActiveProjectContext().catch(() => {
    });
  });
  document.addEventListener?.("app:scope-capabilities-changed", () => {
    _refreshHudProjectCreateAction();
  });
  const hudActions = document.getElementById("hud-actions");
  let hudKillBtn = null;
  let hudShareSnapshotBtn = null;
  function _currentTabId() {
    return _shellGetActiveTabId();
  }
  function _closeHudSaveMenu() {
    document.querySelectorAll(".hud-save-wrap.open").forEach((w) => w.classList.remove("open"));
  }
  function _makeHudBtn(label, action, onClick, cls = "btn btn-secondary btn-compact", title = "") {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = cls;
    btn.textContent = label;
    if (action) btn.dataset.action = action;
    if (title) btn.title = title;
    const isDisclosure = action === "save-menu";
    _shellBindPressable(btn, {
      refocusComposer: !isDisclosure,
      onActivate: (e) => {
        e.preventDefault();
        onClick(e, btn);
      }
    });
    return btn;
  }
  function _bindProjectRuntimePressable(el, options = {}) {
    if (el && _shellFn("bindPressable", bindPressable)) {
      _shellBindPressable(el, { onActivate: () => {
      }, refocusComposer: false, ...options });
    }
    return el;
  }
  function _canCreateHudShareSnapshot() {
    return _shellActiveTeamScopeCan("manage_history");
  }
  function _hudShareSnapshotDeniedTitle() {
    return _shellTeamScopeDeniedMessage("create team history snapshots");
  }
  function _refreshHudShareSnapshotState() {
    if (!hudShareSnapshotBtn) return;
    const allowed = _canCreateHudShareSnapshot();
    hudShareSnapshotBtn.disabled = !allowed;
    hudShareSnapshotBtn.title = allowed ? "Share tab as permalink (Option+P / Alt+P)" : _hudShareSnapshotDeniedTitle();
  }
  function buildHudActions() {
    if (!hudActions) return;
    hudActions.replaceChildren();
    const copyCurrentTab = typeof copyTab === "function" ? copyTab : _shellFn("copyTab");
    const permalinkCurrentTab = typeof permalinkTab === "function" ? permalinkTab : _shellFn("permalinkTab");
    const saveCurrentTab = typeof saveTab === "function" ? saveTab : _shellFn("saveTab");
    const exportCurrentTabHtml = typeof exportTabHtml === "function" ? exportTabHtml : _shellFn("exportTabHtml");
    const exportCurrentTabPdf = typeof exportTabPdf === "function" ? exportTabPdf : _shellFn("exportTabPdf");
    hudKillBtn = _makeHudBtn("■ Kill", "kill", () => {
      const id = _currentTabId();
      const confirmKill3 = typeof confirmKill === "function" && confirmKill || _shellFn("confirmKill");
      if (id) confirmKill3?.(id);
    }, "btn btn-destructive btn-compact u-hidden", "Kill current run");
    hudActions.appendChild(hudKillBtn);
    hudShareSnapshotBtn = _makeHudBtn("share snapshot", "permalink", () => {
      const id = _currentTabId();
      if (id && permalinkCurrentTab) permalinkCurrentTab(id);
    }, "btn btn-secondary btn-compact", "Share tab as permalink (Option+P / Alt+P)");
    hudActions.appendChild(hudShareSnapshotBtn);
    _refreshHudShareSnapshotState();
    hudActions.appendChild(_makeHudBtn("copy", "copy", () => {
      const id = _currentTabId();
      if (id && copyCurrentTab) copyCurrentTab(id);
    }, "btn btn-secondary btn-compact", "Copy tab output (Option+Shift+C)"));
    const saveWrap = document.createElement("div");
    saveWrap.className = "hud-save-wrap";
    const saveBtn = _makeHudBtn("save", "save-menu", () => {
      closeHudProjectMenu();
      saveWrap.classList.toggle("open");
    }, "btn btn-secondary btn-compact", "Save tab output (txt / html / pdf)");
    const saveMenu = document.createElement("div");
    saveMenu.className = "save-menu dropdown-surface dropdown-up";
    [
      ["Plain text (.txt)", "save-txt", () => {
        const id = _currentTabId();
        if (id && saveCurrentTab) saveCurrentTab(id);
      }],
      ["Styled HTML (.html)", "save-html", () => {
        const id = _currentTabId();
        if (id && exportCurrentTabHtml) exportCurrentTabHtml(id);
      }],
      ["PDF document (.pdf)", "save-pdf", () => {
        const id = _currentTabId();
        if (id && exportCurrentTabPdf) exportCurrentTabPdf(id);
      }]
    ].forEach(([label, action, fn]) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "dropdown-item dropdown-item-compact";
      item.textContent = label;
      item.dataset.action = action;
      _shellBindPressable(item, {
        onActivate: (e) => {
          e.preventDefault();
          e.stopPropagation();
          saveWrap.classList.remove("open");
          fn();
        }
      });
      saveMenu.appendChild(item);
    });
    saveWrap.appendChild(saveBtn);
    saveWrap.appendChild(saveMenu);
    hudActions.appendChild(saveWrap);
    hudActions.appendChild(_makeHudBtn("clear", "clear", () => {
      const id = _currentTabId();
      if (!id) return;
      const cancelWelcomeFn = _shellFn("cancelWelcome", cancelWelcome);
      if (typeof cancelWelcomeFn === "function") cancelWelcomeFn(id);
      _shellFn("clearTab", clearTab)?.(id, { preserveRunState: true });
    }, "btn btn-secondary btn-compact", "Clear active tab (Ctrl+L)"));
    _shellBindOutsideClickClose(saveWrap, {
      triggers: saveBtn,
      isOpen: () => saveWrap.classList.contains("open"),
      onClose: () => _closeHudSaveMenu()
    });
  }
  function _setHudKillVisible(show) {
    if (!hudKillBtn) return;
    hudKillBtn.classList.toggle("u-hidden", !show);
  }
  function refreshHudActions(tabId) {
    const id = tabId || _currentTabId();
    const tab = _shellGetTab(id);
    _setHudKillVisible(!!(tab && tab.st === "running"));
    _refreshHudShareSnapshotState();
  }
  buildHudActions();
  document.addEventListener("app:scope-changed", () => {
    _refreshHudShareSnapshotState();
  });
  document.addEventListener("app:scope-capabilities-changed", () => {
    _refreshHudShareSnapshotState();
  });
  const STATUS_POLL_VISIBLE_MS = 3e3;
  const STATUS_POLL_HIDDEN_MS = 15e3;
  const CLOCK_TICK_MS = 1e3;
  const LAT_WARN_MS = 250;
  const LAT_BAD_MS = 500;
  const hudState = {
    lastExit: null,
    // number | 'killed' | null
    latencyMs: null,
    // number | null
    serverUptime: null,
    // seconds as reported by /status
    serverUptimeAt: 0,
    // performance.now() when serverUptime was recorded
    db: null,
    // 'ok' | 'down' | null
    redis: null
    // 'ok' | 'down' | 'none' | null
  };
  let hudStatusPollTimer = null;
  function _setValueColor(el, variant) {
    if (!el) return;
    el.classList.remove("hud-value-green", "hud-value-amber", "hud-value-red", "hud-muted");
    if (variant) el.classList.add(variant);
  }
  function _formatUptime(totalSeconds) {
    if (!Number.isFinite(totalSeconds) || totalSeconds < 0) return "—";
    const s = Math.floor(totalSeconds);
    if (s < 60) return `${s}s`;
    if (s < 3600) {
      const m = Math.floor(s / 60);
      const r = s % 60;
      return r ? `${m}m ${r}s` : `${m}m`;
    }
    if (s < 86400) {
      const h2 = Math.floor(s / 3600);
      const m = Math.floor(s % 3600 / 60);
      return m ? `${h2}h ${m}m` : `${h2}h`;
    }
    const d = Math.floor(s / 86400);
    const h = Math.floor(s % 86400 / 3600);
    return h ? `${d}d ${h}h` : `${d}d`;
  }
  function _formatUtcClock(ms) {
    const d = new Date(Number.isFinite(ms) ? ms : Date.now());
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} UTC`;
  }
  function _formatOffsetLabel(minutesEastOfUtc) {
    const totalMinutes = Number.isFinite(minutesEastOfUtc) ? minutesEastOfUtc : 0;
    if (totalMinutes === 0) return "UTC";
    const sign = totalMinutes >= 0 ? "+" : "-";
    const absMinutes = Math.abs(totalMinutes);
    const hours = String(Math.floor(absMinutes / 60)).padStart(2, "0");
    const minutes = String(absMinutes % 60).padStart(2, "0");
    return `GMT${sign}${hours}:${minutes}`;
  }
  function _getLocalClockLabel(d) {
    try {
      const tzName = new Intl.DateTimeFormat([], { timeZoneName: "short" }).formatToParts(d).find((part) => part.type === "timeZoneName")?.value?.trim();
      if (tzName && !/^GMT(?:[+-]\d{1,2}(?::\d{2})?)?$/i.test(tzName) && !/^UTC(?:[+-]\d{1,2}(?::\d{2})?)?$/i.test(tzName)) {
        return tzName;
      }
    } catch (_) {
    }
    return _formatOffsetLabel(-d.getTimezoneOffset());
  }
  function _formatLocalClock(ms) {
    const d = new Date(Number.isFinite(ms) ? ms : Date.now());
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())} ${_getLocalClockLabel(d)}`;
  }
  function _renderLastExit() {
    if (!hudLastExitEl) return;
    const v = hudState.lastExit;
    const list = _shellTabs();
    const activeTabId = _shellGetActiveTabId();
    const activeRunning = list.some((t) => t && t.id === activeTabId && t.st === "running");
    if (v === null || v === void 0) {
      hudLastExitEl.textContent = "—";
      _setValueColor(hudLastExitEl, "hud-muted");
    } else if (v === "killed") {
      hudLastExitEl.textContent = "KILLED";
      _setValueColor(hudLastExitEl, activeRunning ? "hud-muted" : "hud-value-red");
    } else if (v === 0) {
      hudLastExitEl.textContent = "0";
      _setValueColor(hudLastExitEl, activeRunning ? "hud-muted" : "hud-value-green");
    } else {
      hudLastExitEl.textContent = String(v);
      _setValueColor(hudLastExitEl, activeRunning ? "hud-muted" : "hud-value-red");
    }
  }
  function _renderLatency() {
    if (!hudLatencyEl) return;
    const ms = hudState.latencyMs;
    if (ms === null || ms === void 0) {
      hudLatencyEl.textContent = "— ms";
      _setValueColor(hudLatencyEl, "hud-muted");
      return;
    }
    hudLatencyEl.textContent = `${Math.round(ms)} ms`;
    if (ms >= LAT_BAD_MS) _setValueColor(hudLatencyEl, "hud-value-red");
    else if (ms >= LAT_WARN_MS) _setValueColor(hudLatencyEl, "hud-value-amber");
    else _setValueColor(hudLatencyEl, "hud-value-green");
  }
  function _renderTabs() {
    if (!hudTabsEl) return;
    const list = _shellTabs();
    const running = list.reduce((n, t) => n + (t && t.st === "running" ? 1 : 0), 0);
    const total = list.length;
    if (!total) hudTabsEl.textContent = "0";
    else if (running > 0) hudTabsEl.textContent = `${total} · ${running} active`;
    else hudTabsEl.textContent = String(total);
    _setValueColor(hudTabsEl, running > 0 ? "hud-value-amber" : "hud-muted");
  }
  function _renderSession() {
    if (!hudSessionEl) return;
    let token = "";
    try {
      token = global.localStorage?.getItem("session_token") || "";
    } catch (_) {
    }
    if (token && token.startsWith("tok_")) {
      const masked = _shellMaskSessionToken(token);
      hudSessionEl.textContent = masked;
      hudSessionEl.title = `Active session token (${masked})`;
      _setValueColor(hudSessionEl, "hud-value-green");
    } else {
      hudSessionEl.textContent = "ANON";
      hudSessionEl.title = "Anonymous UUID session — generate a token in Options to carry history across devices";
      _setValueColor(hudSessionEl, "hud-muted");
    }
  }
  let projectSharedUiController = null;
  function _projectSharedUiController() {
    if (projectSharedUiController) return projectSharedUiController;
    const factory = exportedDarklabProjectSharedUi && exportedDarklabProjectSharedUi.createProjectSharedUiController;
    if (typeof factory !== "function") throw new Error("DarklabProjectSharedUi is unavailable");
    projectSharedUiController = factory({
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      downloadBlobAsAttachment: _shellDownloadBlobAsAttachment,
      downloadUrlAsAttachment: _shellDownloadUrlAsAttachment,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage
    });
    return projectSharedUiController;
  }
  function _projectDisplayName(project) {
    return _projectSharedUiController().displayName(project);
  }
  let projectActiveContextController = null;
  function _projectActiveContextController() {
    if (projectActiveContextController) return projectActiveContextController;
    const factory = exportedDarklabProjectActiveContext && exportedDarklabProjectActiveContext.createProjectActiveContextController;
    if (typeof factory !== "function") throw new Error("DarklabProjectActiveContext is unavailable");
    projectActiveContextController = factory({
      apiFetch: _shellApiFetch,
      emitUiEvent: (eventName, detail) => {
        _shellEmitUiEvent(eventName, detail);
      },
      hudProjectCell,
      hudProjectEl,
      isProjectWorkspaceOpen: isProjectWorkspaceOpen3,
      logClientError: (message, err, details) => {
        _shellLogClientError(message, err, details);
      },
      projectDisplayName: _projectDisplayName,
      railNav,
      refreshProjectWorkspace: refreshProjectWorkspace2,
      setValueColor: _setValueColor,
      showToast: _shellFn("showToast", showToast),
      syncProjectNotesForm: _syncProjectNotesForm
    });
    return projectActiveContextController;
  }
  function _activeProject() {
    return _projectActiveContextController().project();
  }
  function _setActiveProject(project) {
    return _projectActiveContextController().setProject(project);
  }
  function _renderActiveProject() {
    _projectActiveContextController().render();
  }
  async function loadActiveProjectContext() {
    return _projectActiveContextController().load();
  }
  let projectWorkspaceShellController = null;
  function _projectWorkspaceShellController() {
    if (projectWorkspaceShellController) return projectWorkspaceShellController;
    const projectWorkspaceShell = _projectModule("DarklabProjectWorkspaceShell", importedProjectWorkspaceShell);
    const factory = projectWorkspaceShell && projectWorkspaceShell.createProjectWorkspaceShellController;
    if (typeof factory !== "function") throw new Error("DarklabProjectWorkspaceShell is unavailable");
    projectWorkspaceShellController = factory({
      EntityMetadataClient,
      blurVisibleComposerInputIfMobile: () => {
        _shellFn("blurVisibleComposerInputIfMobile", blurVisibleComposerInputIfMobile)?.();
      },
      closeMajorOverlays: (options = {}) => {
        if (typeof closeMajorOverlays === "function") closeMajorOverlays(options);
      },
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectMobileActionSheet: _closeProjectMobileActionSheet,
      closeProjectMobileCompareSheet: _closeProjectMobileCompareSheet,
      closeProjectPackageManifest: _closeProjectPackageManifest,
      closeProjectPackageWizard: _closeProjectPackageWizard,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      emitUiEvent: (eventName, detail) => {
        _shellEmitUiEvent(eventName, detail);
      },
      flushProjectNotesAutosave: _flushProjectNotesAutosave,
      markInteractionSurfaceReady: (surfaceName, overlay, modal) => {
        _shellFn("markInteractionSurfaceReady", markInteractionSurfaceReady)?.(surfaceName, overlay, modal);
      },
      projectEntitiesController: _projectEntitiesController,
      projectWorkspaceBody,
      projectWorkspaceBroadcastKey: PROJECT_WORKSPACE_CONSTANTS.workspaceBroadcastKey,
      projectMobileCreateForm,
      projectMobileNameInput,
      projectWorkspaceCreateForm,
      projectWorkspaceMessage,
      projectWorkspaceModal,
      projectWorkspaceNameInput,
      projectWorkspaceOverlay,
      refocusComposerAfterAction: (options) => {
        _shellRefocusComposer(options);
      },
      refreshProjectWorkspace: refreshProjectWorkspace2,
      selectedProjectId: () => projectWorkspaceState.selectedId(),
      setProjectMobileCreateOpen: _setProjectMobileCreateOpen,
      setProjectPaginationOffset: _setProjectPaginationOffset,
      setProjectWorkspaceTab: projectWorkspaceState.setTab,
      setSelectedProjectId: projectWorkspaceState.setSelectedId,
      showToast: _shellFn("showToast", showToast)
    });
    return projectWorkspaceShellController;
  }
  let projectWorkspaceActionsController = null;
  function _projectWorkspaceActionsController() {
    if (projectWorkspaceActionsController) return projectWorkspaceActionsController;
    const projectWorkspaceActions = _projectModule("DarklabProjectWorkspaceActions", importedProjectWorkspaceActions);
    const factory = projectWorkspaceActions && projectWorkspaceActions.createProjectWorkspaceActionsController;
    if (typeof factory !== "function") throw new Error("DarklabProjectWorkspaceActions is unavailable");
    projectWorkspaceActionsController = factory({
      EntityMetadataClient,
      apiFetch: _shellApiFetch,
      projectRunItems: _projectRunItems,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      refreshProjectWorkspace: refreshProjectWorkspace2,
      selectedProjectId: () => projectWorkspaceState.selectedId(),
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      showConfirm: _shellFn("showConfirm", showConfirm)
    });
    return projectWorkspaceActionsController;
  }
  function isProjectWorkspaceOpen3() {
    if (!_projectWorkspaceModulesReady()) return _projectWorkspaceOverlayOpenFallback();
    return _projectWorkspaceShellController().isOpen();
  }
  function _setProjectWorkspaceMessage(text = "", { error = false, toast = true } = {}) {
    if (!_projectWorkspaceModulesReady()) {
      if (toast && text) _shellShowToast(text, error ? "error" : "info");
      return;
    }
    _projectWorkspaceShellController().setMessage(text, { error, toast });
  }
  async function _projectResponseError(resp, fallback) {
    return _projectWorkspaceShellController().responseError(resp, fallback);
  }
  function _selectedProject() {
    return _projectWorkspaceLifecycleController().selectedProject();
  }
  function _projectSummary(projectId = projectWorkspaceState.selectedId()) {
    return _projectWorkspaceLifecycleController().projectSummary(projectId);
  }
  function _ensureSelectedProject() {
    _projectWorkspaceLifecycleController().ensureSelectedProject();
  }
  function _projectCounts(summary) {
    return _projectSharedUiController().counts(summary);
  }
  function _projectCountEntries(summary) {
    return _projectSharedUiController().countEntries(summary);
  }
  function _projectTargetItems(summary) {
    return _projectSharedUiController().targetItems(summary);
  }
  let projectEntitiesController = null;
  function _projectEntitiesController() {
    if (projectEntitiesController) return projectEntitiesController;
    const projectEntities = _projectModule("DarklabProjectEntities", importedProjectEntities);
    const factory = projectEntities && projectEntities.createProjectEntitiesController;
    if (typeof factory !== "function") throw new Error("DarklabProjectEntities is unavailable");
    projectEntitiesController = factory({
      apiFetch: _shellApiFetch,
      getSummary: (projectId) => projectWorkspaceState.summary(projectId),
      getActiveTab: projectWorkspaceState.entityTab,
      setActiveTab: projectWorkspaceState.setEntityTab,
      getSelectMode: projectWorkspaceState.entitySelectMode,
      setSelectMode: projectWorkspaceState.setEntitySelectMode,
      getSelectedIds: projectWorkspaceState.selectedEntityIds,
      getPicker: projectWorkspaceState.entityPicker,
      setPicker: projectWorkspaceState.setEntityPicker,
      getSelectedProjectId: projectWorkspaceState.selectedId,
      projectRows: projectWorkspaceState.rows,
      projectIsArchived: _projectIsArchived,
      formatDate: _formatProjectDate,
      shortProjectRunId: _shortProjectRunId,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      projectMobileEmptyPanel: _projectMobileEmptyPanel,
      projectItemRow: _projectItemRow,
      projectMobileContentRow: _projectMobileContentRow,
      projectMobileActionMenu: _projectMobileActionMenu,
      entityMetadataChips: _entityMetadataChips,
      projectTargetItems: _projectTargetItems,
      projectTargetFilterSet: _projectTargetFilterSet,
      projectRunFilterSet: _projectRunFilterSet,
      projectResponseError: _projectResponseError,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      refreshProjectWorkspace: refreshProjectWorkspace2,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      mobileView: () => _projectMobileShellController().currentView(),
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      showConfirm: _shellFn("showConfirm", showConfirm),
      logClientError: (message, err) => {
        _shellLogClientError(message, err);
      },
      downloadBlobAsAttachment: _downloadBlobAsAttachment,
      downloadUrlAsAttachment: _downloadUrlAsAttachment,
      closeProjectWorkspace: closeProjectWorkspace3,
      openAtlas: _shellOpenAtlas,
      projectDisplayName: _projectDisplayName,
      setWorkspaceTab: projectWorkspaceState.setTab
    });
    return projectEntitiesController;
  }
  let projectPackagesController = null;
  let projectPackagesControllerPromise = null;
  function _projectPackagesController() {
    if (projectPackagesController) return projectPackagesController;
    const projectPackages = _projectModule("DarklabProjectPackages", importedProjectPackages);
    const factory = projectPackages && projectPackages.createProjectPackagesController;
    if (typeof factory !== "function") throw new Error("DarklabProjectPackages is unavailable");
    projectPackagesController = factory({
      apiFetch: _shellApiFetch,
      EntityMetadataClient,
      manifestOverlay: projectPackageManifestOverlay,
      manifestTitle: projectPackageManifestTitle,
      manifestSummary: projectPackageManifestSummary,
      manifestJson: projectPackageManifestJson,
      wizardOverlay: projectPackageWizardOverlay,
      wizardBody: projectPackageWizardBody,
      getSelectedProjectId: projectWorkspaceState.selectedId,
      selectedProject: _selectedProject,
      projectSummary: _projectSummary,
      projectRunItems: _projectRunItems,
      projectArtifactItems: _projectArtifactItems,
      loadAllProjectArtifacts: _loadAllProjectArtifacts,
      projectTargetItems: _projectTargetItems,
      projectFindingItems: _projectFindingItems,
      projectFindingsLoaded: _projectFindingsLoaded,
      loadProjectFindings: _loadProjectFindings,
      projectFilesEnabled: _projectFilesEnabled,
      projectArtifactStatus: _projectArtifactStatus,
      projectArtifactDetail: _projectArtifactDetail,
      projectTargetFilterLabel: _projectTargetFilterLabel,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      entityMetadataChips: _entityMetadataChips,
      projectProvenanceSummary: _projectProvenanceSummary,
      projectProvenanceSummaryElement: _projectProvenanceSummaryElement,
      formatDate: _formatProjectDate,
      formatBytes: _formatProjectBytes,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      projectMobileEmptyPanel: _projectMobileEmptyPanel,
      projectMobileContentRow: _projectMobileContentRow,
      projectMobileActionMenu: _projectMobileActionMenu,
      projectItemRow: _projectItemRow,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      refreshProjectWorkspace: refreshProjectWorkspace2,
      renderProjectExplorer: _renderProjectExplorer,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      downloadBlobAsAttachment: _downloadBlobAsAttachment,
      downloadUrlAsAttachment: _downloadUrlAsAttachment,
      setWorkspaceTab: projectWorkspaceState.setTab,
      syncProjectWorkspaceNestedSuppression: _syncProjectWorkspaceNestedSuppression,
      focusProjectNestedSheet: _focusProjectNestedSheet,
      installProjectMobileKeyboardGuards: _installProjectMobileKeyboardGuards
    });
    return projectPackagesController;
  }
  function _projectPackagesControllerIfReady() {
    return projectPackagesController || null;
  }
  function _loadProjectPackagesController() {
    if (projectPackagesController) return Promise.resolve(projectPackagesController);
    if (projectPackagesControllerPromise) return projectPackagesControllerPromise;
    const loader = global.loadProjectPackages;
    projectPackagesControllerPromise = (typeof loader === "function" ? loader() : Promise.resolve()).then(() => _projectPackagesController()).finally(() => {
      projectPackagesControllerPromise = null;
    });
    return projectPackagesControllerPromise;
  }
  let projectReportController = null;
  let projectReportControllerPromise = null;
  let projectActivityController = null;
  let projectActivityControllerPromise = null;
  let projectOverviewController = null;
  let projectOverviewControllerPromise = null;
  let projectMonitoringController = null;
  let projectMonitoringControllerPromise = null;
  function _projectActivityController() {
    if (projectActivityController) return projectActivityController;
    const projectActivity = _projectModule("DarklabProjectActivity", importedProjectActivity);
    const factory = projectActivity && projectActivity.createProjectActivityController;
    if (typeof factory !== "function") throw new Error("DarklabProjectActivity is unavailable");
    projectActivityController = factory({
      projectWorkspaceRequest: _projectWorkspaceRequest,
      projectResponseError: _projectResponseError,
      formatDate: _formatProjectDate,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      renderProjectExplorer: _renderProjectExplorer,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      openProjectObject: _openProjectObject
    });
    return projectActivityController;
  }
  function _projectActivityControllerIfReady() {
    return projectActivityController || null;
  }
  function _loadProjectActivityController() {
    if (projectActivityController) return Promise.resolve(projectActivityController);
    if (projectActivityControllerPromise) return projectActivityControllerPromise;
    const loader = global.loadProjectActivity;
    projectActivityControllerPromise = (typeof loader === "function" ? loader() : Promise.resolve()).then((namespace) => {
      if (namespace) importedProjectActivity = namespace;
      return _projectActivityController();
    }).finally(() => {
      projectActivityControllerPromise = null;
    });
    return projectActivityControllerPromise;
  }
  function _projectOverviewController() {
    if (projectOverviewController) return projectOverviewController;
    const projectOverview = _projectModule("DarklabProjectOverview", importedProjectOverview);
    const factory = projectOverview && projectOverview.createProjectOverviewController;
    if (typeof factory !== "function") throw new Error("DarklabProjectOverview is unavailable");
    projectOverviewController = factory({
      projectWorkspaceRequest: _projectWorkspaceRequest,
      projectResponseError: _projectResponseError,
      formatDate: _formatProjectDate,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      setProjectWorkspaceTab: projectWorkspaceState.setTab,
      projectTargetFilterSet: _projectTargetFilterSet,
      projectRunFilterSet: _projectRunFilterSet,
      projectFindingSeverityFilterSet: _projectFindingSeverityFilterSet,
      projectFindingStatusFilterSet: _projectFindingStatusFilterSet,
      setProjectFindingOrphanFilter: (projectId, value) => _projectFiltersController().setFindingOrphanFilter(projectId, value),
      invalidateProjectFilteredFindings: _invalidateProjectFilteredFindings,
      logClientError: _shellLogClientError,
      mobileView: () => _projectMobileShellController().currentView()
    });
    return projectOverviewController;
  }
  function _projectOverviewControllerIfReady() {
    return projectOverviewController || null;
  }
  function _loadProjectOverviewController() {
    if (projectOverviewController) return Promise.resolve(projectOverviewController);
    if (projectOverviewControllerPromise) return projectOverviewControllerPromise;
    const loader = global.loadProjectOverview;
    projectOverviewControllerPromise = (typeof loader === "function" ? loader() : Promise.resolve()).then((namespace) => {
      if (namespace) importedProjectOverview = namespace;
      return _projectOverviewController();
    }).finally(() => {
      projectOverviewControllerPromise = null;
    });
    return projectOverviewControllerPromise;
  }
  function _projectMonitoringController() {
    if (projectMonitoringController) return projectMonitoringController;
    const projectMonitoring = _projectModule("DarklabProjectMonitoring", importedProjectMonitoring);
    const factory = projectMonitoring && projectMonitoring.createProjectMonitoringController;
    if (typeof factory !== "function") throw new Error("DarklabProjectMonitoring is unavailable");
    projectMonitoringController = factory({
      projectWorkspaceRequest: _projectWorkspaceRequest,
      projectResponseError: _projectResponseError,
      formatDate: _formatProjectDate,
      makeProjectButton: _makeProjectButton,
      emptyProjectPanel: _emptyProjectPanel,
      showConfirm: _shellFn("showConfirm", showConfirm),
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      logClientError: _shellLogClientError,
      mobileView: () => _projectMobileShellController().currentView()
    });
    return projectMonitoringController;
  }
  function _projectMonitoringControllerIfReady() {
    return projectMonitoringController || null;
  }
  function _loadProjectMonitoringController() {
    if (projectMonitoringController) return Promise.resolve(projectMonitoringController);
    if (projectMonitoringControllerPromise) return projectMonitoringControllerPromise;
    const loader = global.loadProjectMonitoring;
    projectMonitoringControllerPromise = (typeof loader === "function" ? loader() : Promise.resolve()).then((namespace) => {
      if (namespace) importedProjectMonitoring = namespace;
      return _projectMonitoringController();
    }).finally(() => {
      projectMonitoringControllerPromise = null;
    });
    return projectMonitoringControllerPromise;
  }
  function _projectReportController() {
    if (projectReportController) return projectReportController;
    const projectReport = _projectModule("DarklabProjectReport", importedProjectReport);
    const factory = projectReport && projectReport.createProjectReportController;
    if (typeof factory !== "function") throw new Error("DarklabProjectReport is unavailable");
    projectReportController = factory({
      apiFetch: _shellApiFetch,
      getSelectedProjectId: projectWorkspaceState.selectedId,
      selectedProject: _selectedProject,
      projectSummary: _projectSummary,
      projectRunItems: _projectRunItems,
      projectArtifactItems: _projectArtifactItems,
      loadAllProjectArtifacts: _loadAllProjectArtifacts,
      projectTargetItems: _projectTargetItems,
      projectFindingItems: _projectFindingItems,
      loadProjectFindings: _loadProjectFindings,
      projectArtifactDetail: _projectArtifactDetail,
      formatDate: _formatProjectDate,
      projectProvenanceSummaryElement: _projectProvenanceSummaryElement,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      mobileView: () => _projectMobileShellController().currentView(),
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      downloadUrlAsAttachment: _downloadUrlAsAttachment,
      showConfirm: _shellFn("showConfirm", showConfirm),
      logClientError: (message, err) => {
        _shellLogClientError(message, err);
      }
    });
    return projectReportController;
  }
  function _projectReportControllerIfReady() {
    return projectReportController || null;
  }
  function _loadProjectReportController() {
    if (projectReportController) return Promise.resolve(projectReportController);
    if (projectReportControllerPromise) return projectReportControllerPromise;
    const loader = global.loadProjectReport;
    projectReportControllerPromise = (typeof loader === "function" ? loader() : Promise.resolve()).then((namespace) => {
      if (namespace) importedProjectReport = namespace;
      return _projectReportController();
    }).finally(() => {
      projectReportControllerPromise = null;
    });
    return projectReportControllerPromise;
  }
  let projectFiltersController = null;
  function _projectFiltersController() {
    if (projectFiltersController) return projectFiltersController;
    const projectFilters = _projectModule("DarklabProjectFilters", importedProjectFilters);
    const factory = projectFilters && projectFilters.createProjectFiltersController;
    if (typeof factory !== "function") throw new Error("DarklabProjectFilters is unavailable");
    projectFiltersController = factory({
      getSelectedProjectId: projectWorkspaceState.selectedId,
      projectWorkspaceModal: () => projectWorkspaceModal,
      projectExplorerBody: () => projectExplorerBody,
      projectWorkspaceTab: projectWorkspaceState.tab,
      projectSummary: _projectSummary,
      findingReviewStates: PROJECT_WORKSPACE_CONSTANTS.findingReviewStates,
      findingSeverityRank: PROJECT_WORKSPACE_CONSTANTS.findingSeverityRank,
      findingReviewRank: PROJECT_WORKSPACE_CONSTANTS.findingReviewRank,
      projectFindingSortOptions: PROJECT_WORKSPACE_CONSTANTS.findingSortOptions,
      projectFindingNoteStateOptions: PROJECT_WORKSPACE_CONSTANTS.findingNoteStateOptions,
      projectFindingOrphanOptions: PROJECT_WORKSPACE_CONSTANTS.findingOrphanOptions,
      projectFindingScopeOptions: PROJECT_WORKSPACE_CONSTANTS.findingScopeOptions,
      projectFindingSeverityOptions: PROJECT_WORKSPACE_CONSTANTS.findingSeverityOptions,
      projectTargetItems: _projectTargetItems,
      projectTargetLabel: _projectTargetLabel,
      projectRunItems: _projectRunItems,
      projectRunById: _projectRunById,
      shortProjectRunId: _shortProjectRunId,
      projectFindingItems: _projectFindingItems,
      projectFilteredFindingItems: (key) => _projectFindingsDataController().filteredItems(key),
      hasProjectFilteredFindingsKey: (key) => _projectFindingsDataController().hasFilteredKey(key),
      projectArtifactItems: _projectArtifactItems,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      findingReviewStateLabel: _findingReviewStateLabel,
      bindProjectRuntimePressable: _bindProjectRuntimePressable
    });
    return projectFiltersController;
  }
  let projectFindingsDataController = null;
  function _projectFindingsDataController() {
    if (projectFindingsDataController) return projectFindingsDataController;
    const projectFindingsData = _projectModule("DarklabProjectFindingsData", importedProjectFindingsData);
    const factory = projectFindingsData && projectFindingsData.createProjectFindingsDataController;
    if (typeof factory !== "function") throw new Error("DarklabProjectFindingsData is unavailable");
    projectFindingsDataController = factory({
      apiFetch: _shellApiFetch,
      selectedProjectId: projectWorkspaceState.selectedId,
      mobileView: () => _projectMobileShellController().currentView(),
      projectSummary: _projectSummary,
      findingFilteredKey: _projectFindingFilteredKey,
      findingServerFilterParams: _projectFindingServerFilterParams,
      collapsedFindingGroupLabels: _projectCollapsedFindingGroupLabels,
      filteredProjectFindings: _filteredProjectFindings,
      pageLimit: 50,
      projectResponseError: _projectResponseError,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      renderProjectPackageWizardModal: _renderProjectPackageWizardModal,
      projectPackageWizardActive: _projectPackageWizardActive,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      logClientError: (message, err) => {
        _shellLogClientError(message, err);
      }
    });
    return projectFindingsDataController;
  }
  let projectFindingsController = null;
  let projectFindingsBoardController = null;
  function _projectFindingsBoardController() {
    if (projectFindingsBoardController) return projectFindingsBoardController;
    const projectFindingsBoard = _projectModule("DarklabProjectFindingsBoard", importedProjectFindingsBoard);
    const factory = projectFindingsBoard && projectFindingsBoard.createProjectFindingsBoardController;
    if (typeof factory !== "function") throw new Error("DarklabProjectFindingsBoard is unavailable");
    projectFindingsBoardController = factory({
      entityMetadataChipClass: _entityMetadataChipClass,
      entityMetadataChips: _entityMetadataChips,
      projectFindingTargetText: _projectFindingTargetText,
      projectTargetLabel: _projectTargetLabel,
      makeProjectButton: _makeProjectButton,
      reviewControl: (finding, projectId) => _projectFindingsController().reviewControl(finding, projectId),
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      metaSeparator: " · "
    });
    return projectFindingsBoardController;
  }
  function _projectFindingsController() {
    if (projectFindingsController) return projectFindingsController;
    const projectFindings = _projectModule("DarklabProjectFindings", importedProjectFindings);
    const factory = projectFindings && projectFindings.createProjectFindingsController;
    if (typeof factory !== "function") throw new Error("DarklabProjectFindings is unavailable");
    projectFindingsController = factory({
      findingReviewStates: PROJECT_WORKSPACE_CONSTANTS.findingReviewStates,
      collapsedFindingGroups: projectWorkspaceState.collapsedFindingGroups,
      collapsedFindingGroupLabels: _projectCollapsedFindingGroupLabels,
      findingsLoadingId: () => _projectFindingsDataController().loadingId(),
      hasFindings: (projectId) => _projectFindingsDataController().loaded(projectId),
      findingViewMode: projectWorkspaceState.findingViewMode,
      findingSelectMode: projectWorkspaceState.findingSelectMode,
      selectedFindingIds: projectWorkspaceState.selectedFindingIds,
      projectFindingPagination: (projectId, summary) => _projectFindingsDataController().page(projectId, summary),
      projectFindingItems: _projectFindingItems,
      projectFindingBoard: (projectId, summary, options) => _projectFindingsDataController().board(projectId, summary, options),
      filteredProjectFindings: _filteredProjectFindings,
      projectFindingServerFiltersActive: _projectFindingServerFiltersActive,
      findingsBoardAvailable: () => !(document.body && document.body.classList.contains("mobile-terminal-mode")),
      projectFindingTargetText: _projectFindingTargetText,
      projectTargetLabel: _projectTargetLabel,
      entityMetadataChips: _entityMetadataChips,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      renderProjectFindingBoard: (container, projectId, summary, board) => _projectFindingsBoardController().renderBoard(container, projectId, summary, board),
      setFindingSelectMode: projectWorkspaceState.setFindingSelectMode,
      projectItemRow: _projectItemRow,
      groupBy: _groupBy,
      metaSeparator: " · ",
      groupCaret: "▾"
    });
    return projectFindingsController;
  }
  let projectArtifactsController = null;
  let projectArtifactsControllerPromise = null;
  function _projectArtifactsControllerIfReady() {
    return projectArtifactsController;
  }
  function _projectArtifactsFactoryReady() {
    return !!(_projectModule("DarklabProjectArtifacts", importedProjectArtifacts) && typeof _projectModule("DarklabProjectArtifacts", importedProjectArtifacts).createProjectArtifactsController === "function");
  }
  function _projectArtifactsController() {
    if (projectArtifactsController) return projectArtifactsController;
    const projectArtifacts = _projectModule("DarklabProjectArtifacts", importedProjectArtifacts);
    const factory = projectArtifacts && projectArtifacts.createProjectArtifactsController;
    if (typeof factory !== "function") throw new Error("DarklabProjectArtifacts is unavailable");
    projectArtifactsController = factory({
      apiFetch: _shellApiFetch,
      projectResponseError: _projectResponseError,
      collapsedArtifactGroups: projectWorkspaceState.collapsedArtifactGroups,
      filesEnabled: () => !!(_shellValue("APP_CONFIG") && _shellValue("APP_CONFIG").workspace_enabled === true),
      selectedProjectId: projectWorkspaceState.selectedId,
      projectTargetFilterActive: _projectTargetFilterActive,
      projectFindingsLoaded: _projectFindingsLoaded,
      filteredProjectArtifacts: _filteredProjectArtifacts,
      projectRunFilterSet: _projectRunFilterSet,
      projectTargetFilterSet: _projectTargetFilterSet,
      projectTargetItems: _projectTargetItems,
      projectRunById: _projectRunById,
      shortProjectRunId: _shortProjectRunId,
      entityMetadataChips: _entityMetadataChips,
      formatDate: _formatProjectDate,
      formatBytes: _formatProjectBytes,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      projectItemRow: _projectItemRow,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      mobileView: () => _projectMobileShellController().currentView(),
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      logClientError: (message, err) => {
        _shellLogClientError(message, err);
      },
      groupBy: _groupBy,
      downloadBlobAsAttachment: _downloadBlobAsAttachment,
      downloadUrlAsAttachment: _downloadUrlAsAttachment,
      metaSeparator: " · ",
      groupCaret: "▾"
    });
    return projectArtifactsController;
  }
  function _loadProjectArtifactsController() {
    if (projectArtifactsController) return Promise.resolve(projectArtifactsController);
    if (projectArtifactsControllerPromise) return projectArtifactsControllerPromise;
    if (_projectArtifactsFactoryReady()) {
      return Promise.resolve(_projectArtifactsController());
    }
    const loader = global.loadProjectArtifacts;
    if (typeof loader !== "function") {
      return Promise.reject(new Error("Project artifacts loader is unavailable"));
    }
    projectArtifactsControllerPromise = loader().then((namespace) => {
      if (namespace) importedProjectArtifacts = namespace;
      return _projectArtifactsController();
    }).finally(() => {
      projectArtifactsControllerPromise = null;
    });
    return projectArtifactsControllerPromise;
  }
  let projectDetailsController = null;
  function _projectDetailsController() {
    if (projectDetailsController) return projectDetailsController;
    const projectDetails = _projectModule("DarklabProjectDetails", importedProjectDetails);
    const factory = projectDetails && projectDetails.createProjectDetailsController;
    if (typeof factory !== "function") throw new Error("DarklabProjectDetails is unavailable");
    projectDetailsController = factory({
      apiFetch: _shellApiFetch,
      entityMetadataClient: EntityMetadataClient,
      projectNotesForm,
      projectNotesInput,
      projectLabelsForm,
      projectLabelsInput,
      projectLabelsSaveButton,
      projectWorkspaceTab: projectWorkspaceState.tab,
      selectedProject: _selectedProject,
      selectedProjectId: projectWorkspaceState.selectedId,
      projectRows: projectWorkspaceState.rows,
      setProjectRows: projectWorkspaceState.setRows,
      projectSummary: _projectSummary,
      setProjectSummary: projectWorkspaceState.setSummary,
      activeProject: _activeProject,
      setActiveProject: _setActiveProject,
      projectDisplayName: _projectDisplayName,
      projectTargetItems: _projectTargetItems,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      entityMetadataChipClass: _entityMetadataChipClass,
      projectMetaRow: _projectMetaRow,
      formatDate: _formatProjectDate,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      renderProjectTargets: _renderProjectTargets,
      projectResponseError: _projectResponseError,
      syncEntityLabels: _syncEntityLabels,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      renderProjectList: _renderProjectList,
      renderProjectExplorer: _renderProjectExplorer,
      renderActiveProject: _renderActiveProject,
      projectNotesAutosaveDelayMs: PROJECT_WORKSPACE_CONSTANTS.projectNotesAutosaveDelayMs
    });
    return projectDetailsController;
  }
  let projectListController = null;
  function _projectListController() {
    if (projectListController) return projectListController;
    const projectList = _projectModule("DarklabProjectList", importedProjectList);
    const factory = projectList && projectList.createProjectListController;
    if (typeof factory !== "function") throw new Error("DarklabProjectList is unavailable");
    projectListController = factory({
      projectWorkspaceBody,
      projectWorkspaceLoading: projectWorkspaceState.loading,
      projectRows: projectWorkspaceState.rows,
      selectedProjectId: projectWorkspaceState.selectedId,
      activeProject: _activeProject,
      projectSummary: _projectSummary,
      projectCountEntries: _projectCountEntries,
      projectArtifactsVisible: _projectArtifactsVisible,
      projectDisplayName: _projectDisplayName,
      appendProjectLabelChips: _appendProjectLabelChips,
      appendProjectMobileLabelChips: _appendProjectMobileLabelChips,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      mobileMenuText: "☰",
      mobileChevronText: "›",
      projectPagination: projectWorkspaceState.pagination,
      projectWorkspacePagination
    });
    return projectListController;
  }
  let projectNavigationController = null;
  function _projectNavigationController() {
    if (projectNavigationController) return projectNavigationController;
    const projectNavigation = _projectModule("DarklabProjectNavigation", importedProjectNavigation);
    const factory = projectNavigation && projectNavigation.createProjectNavigationController;
    if (typeof factory !== "function") throw new Error("DarklabProjectNavigation is unavailable");
    projectNavigationController = factory({
      projectWorkspaceModal,
      projectMobileDetailTopbar,
      projectMobileTabs,
      activeProject: _activeProject,
      projectWorkspaceTab: projectWorkspaceState.tab,
      setProjectWorkspaceTab: projectWorkspaceState.setTab,
      projectCounts: _projectCounts,
      projectDisplayName: _projectDisplayName,
      projectIsArchived: _projectIsArchived,
      projectArtifactsVisible: _projectArtifactsVisible,
      projectTargetFilterActive: _projectTargetFilterActive,
      projectRunFilterActive: _projectRunFilterActive,
      projectFindingsLoaded: _projectFindingsLoaded,
      projectEntityTabCountText: (projectId, summary, total) => _projectEntitiesController().tabCountText(projectId, summary, total),
      projectFindingPagination: _projectFindingPagination,
      projectFindingServerFiltersActive: _projectFindingServerFiltersActive,
      filteredProjectFindings: _filteredProjectFindings,
      filteredProjectRuns: _filteredProjectRuns,
      filteredProjectArtifacts: _filteredProjectArtifacts,
      appendProjectLabelChips: _appendProjectLabelChips,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      metaSeparator: " · ",
      mobileBackText: "‹ Back"
    });
    return projectNavigationController;
  }
  let projectNestedSheetsController = null;
  function _projectNestedSheetsController() {
    if (projectNestedSheetsController) return projectNestedSheetsController;
    const projectNestedSheets = _projectModule("DarklabProjectNestedSheets", importedProjectNestedSheets);
    const factory = projectNestedSheets && projectNestedSheets.createProjectNestedSheetsController;
    if (typeof factory !== "function") throw new Error("DarklabProjectNestedSheets is unavailable");
    projectNestedSheetsController = factory({
      projectWorkspaceModal,
      projectTargetEditorOverlay,
      projectEntityEditorOverlay,
      projectPackageManifestOverlay,
      projectPackageWizardOverlay,
      isProjectTargetEditorOpen: () => !!(projectTargetEditorOverlay && projectTargetEditorOverlay.classList.contains("open")),
      isProjectEntityEditorOpen: () => !!(projectEntityEditorOverlay && projectEntityEditorOverlay.classList.contains("open")),
      isProjectPackageManifestOpen: () => !!(projectPackageManifestOverlay && projectPackageManifestOverlay.classList.contains("open")),
      isProjectPackageWizardOpen: () => !!(projectPackageWizardOverlay && projectPackageWizardOverlay.classList.contains("open"))
    });
    return projectNestedSheetsController;
  }
  let projectWorkspaceRendererController = null;
  function _projectWorkspaceRendererController() {
    if (projectWorkspaceRendererController) return projectWorkspaceRendererController;
    const projectWorkspaceRenderer = _projectModule("DarklabProjectWorkspaceRenderer", importedProjectWorkspaceRenderer);
    const factory = projectWorkspaceRenderer && projectWorkspaceRenderer.createProjectWorkspaceRendererController;
    if (typeof factory !== "function") throw new Error("DarklabProjectWorkspaceRenderer is unavailable");
    projectWorkspaceRendererController = factory({
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      emptyProjectPanel: _emptyProjectPanel,
      enhanceAppSelects: _shellEnhanceAppSelects(),
      ensureSelectedProject: _ensureSelectedProject,
      flushProjectNotesAutosave: _flushProjectNotesAutosave,
      focusProjectWorkspaceTab: _focusProjectWorkspaceTab,
      isProjectWorkspaceOpen: isProjectWorkspaceOpen3,
      loadProjectFilteredFindings: _loadProjectFilteredFindings,
      loadProjectFindings: _loadProjectFindings,
      mobileView: () => _projectMobileShellController().currentView(),
      projectArtifactsVisible: _projectArtifactsVisible,
      projectExplorerBody,
      projectFindingServerFiltersActive: _projectFindingServerFiltersActive,
      projectFindingsLoaded: _projectFindingsLoaded,
      projectMobileDetailBody,
      projectMobileTabItems: _projectMobileTabItems,
      projectPackageWizardActive: _projectPackageWizardActive,
      projectPagination: projectWorkspaceState.pagination,
      projectRows: projectWorkspaceState.rows,
      projectSummary: _projectSummary,
      projectTargetFilterActive: _projectTargetFilterActive,
      projectWorkspaceLoading: projectWorkspaceState.loading,
      projectWorkspaceSubtitle,
      renderProjectArtifacts: _renderProjectArtifacts,
      renderProjectDetails: _renderProjectDetails,
      renderProjectEntities: _renderProjectEntities,
      renderProjectFilterBar: _renderProjectFilterBar,
      renderProjectFindings: _renderProjectFindings,
      renderProjectHeader: _renderProjectHeader,
      renderProjectList: _renderProjectList,
      renderProjectMobile: _renderProjectMobile,
      renderProjectActivity: _renderProjectActivity,
      renderProjectOverview: _renderProjectOverview,
      renderProjectMonitoring: _renderProjectMonitoring,
      renderProjectPackages: _renderProjectPackages,
      renderProjectPackageWizardModal: _renderProjectPackageWizardModal,
      renderProjectReport: _renderProjectReport,
      renderProjectRuns: _renderProjectRuns,
      scheduleProjectFilterSortDividerSync: _scheduleProjectFilterSortDividerSync,
      selectedProject: _selectedProject,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      setWorkspaceTab: projectWorkspaceState.setTab,
      syncProjectFilterSortDivider: _syncProjectFilterSortDivider,
      syncProjectForms: _syncProjectForms,
      workspaceTab: projectWorkspaceState.tab
    });
    return projectWorkspaceRendererController;
  }
  let projectWorkspaceBootstrapController = null;
  function _projectWorkspaceBootstrapController() {
    if (projectWorkspaceBootstrapController) return projectWorkspaceBootstrapController;
    const projectWorkspaceBootstrap = _projectModule("DarklabProjectWorkspaceBootstrap", importedProjectWorkspaceBootstrap);
    const factory = projectWorkspaceBootstrap && projectWorkspaceBootstrap.createProjectWorkspaceBootstrapController;
    if (typeof factory !== "function") throw new Error("DarklabProjectWorkspaceBootstrap is unavailable");
    const bindDismissibleFn = _shellFn("bindDismissible", bindDismissible);
    const bindMobileSheetFn = _shellFn("bindMobileSheet", bindMobileSheet);
    projectWorkspaceBootstrapController = factory({
      bindDismissible: bindDismissibleFn,
      bindMobileSheet: bindMobileSheetFn,
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectPackageManifest: _closeProjectPackageManifest,
      closeProjectPackageWizard: _closeProjectPackageWizard,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      closeProjectWorkspace: closeProjectWorkspace3,
      isProjectEntityEditorOpen,
      isProjectPackageManifestOpen,
      isProjectPackageWizardOpen,
      isProjectWorkspaceOpen: isProjectWorkspaceOpen3,
      isProjectTargetEditorOpen,
      projectDetailsController: _projectDetailsController,
      projectEntityEditorController: _projectEntityEditorController,
      projectEntityEditorOverlay,
      projectMobileTabs,
      projectPackageManifestOverlay,
      projectPackageWizardOverlay,
      projectActivityController: _projectActivityControllerIfReady,
      projectPackagesController: _projectPackagesControllerIfReady,
      projectTargetEditorOverlay,
      projectTargetsController: _projectTargetsController,
      projectWorkspaceEventsController: _projectWorkspaceEventsController,
      projectWorkspaceModal,
      projectWorkspaceOverlay,
      projectWorkspaceShellController: _projectWorkspaceShellController,
      syncProjectMobileTabEdges: _syncProjectMobileTabEdges
    });
    return projectWorkspaceBootstrapController;
  }
  let projectTargetsController = null;
  function _projectTargetsController() {
    if (projectTargetsController) return projectTargetsController;
    const projectTargets = _projectModule("DarklabProjectTargets", importedProjectTargets);
    const factory = projectTargets && projectTargets.createProjectTargetsController;
    if (typeof factory !== "function") throw new Error("DarklabProjectTargets is unavailable");
    projectTargetsController = factory({
      EntityMetadataClient,
      targetHelpers: PROJECT_TARGET_HELPERS,
      overlay: projectTargetEditorOverlay,
      form: projectTargetCreateForm,
      typeSelect: projectTargetTypeSelect,
      valueInput: projectTargetValueInput,
      valueHelp: projectTargetValueHelp,
      valueError: projectTargetValueError,
      labelInput: projectTargetLabelInput,
      notesInput: projectTargetNotesInput,
      title: projectTargetEditorTitle,
      submitButton: projectTargetSubmitButton,
      getLastTargetType: projectWorkspaceState.lastTargetType,
      setLastTargetType: projectWorkspaceState.setLastTargetType,
      setEditingTargetId: projectWorkspaceState.setEditingTargetId,
      selectedProjectId: projectWorkspaceState.selectedId,
      activeProject: _activeProject,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      entityMetadataChips: _entityMetadataChips,
      entityMetadataChipClass: _entityMetadataChipClass,
      makeProjectButton: _makeProjectButton,
      emptyProjectPanel: _emptyProjectPanel,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      syncEntityLabels: _syncEntityLabels,
      syncEntityNote: _syncEntityNote,
      refreshProjectWorkspace: refreshProjectWorkspace2,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectWorkspace: _renderProjectWorkspace,
      invalidateProjectTargetPage: (projectId) => _projectDetailsController().invalidateTargetPage(projectId),
      invalidateProjectOverview: (projectId = "") => _projectOverviewControllerIfReady()?.invalidate?.(projectId),
      loadProjectTargetPage: (projectId, options) => _projectDetailsController().loadTargetPage(projectId, options),
      renderProjectMobileDetail: _renderProjectMobileDetail,
      loadProjectAutocompleteTargets: () => {
        loadProjectAutocompleteTargets?.().catch(() => {
        });
      },
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      syncProjectWorkspaceNestedSuppression: _syncProjectWorkspaceNestedSuppression,
      installProjectMobileKeyboardGuards: _installProjectMobileKeyboardGuards,
      focusProjectNestedSheet: _focusProjectNestedSheet
    });
    return projectTargetsController;
  }
  let projectRunsController = null;
  function _projectRunsController() {
    if (projectRunsController) return projectRunsController;
    const projectRuns = _projectModule("DarklabProjectRuns", importedProjectRuns);
    const factory = projectRuns && projectRuns.createProjectRunsController;
    if (typeof factory !== "function") throw new Error("DarklabProjectRuns is unavailable");
    projectRunsController = factory({
      apiFetch: _shellApiFetch,
      projectResponseError: _projectResponseError,
      projectExplorerBody: () => projectExplorerBody,
      projectRunItems: _projectRunItems,
      projectComparableRuns: _projectComparableRuns,
      projectFindingItems: _projectFindingItems,
      projectFindingsLoaded: _projectFindingsLoaded,
      projectArtifactItems: _projectArtifactItems,
      projectArtifactsVisible: _projectArtifactsVisible,
      projectTargetFilterActive: _projectTargetFilterActive,
      projectRunFilterActive: _projectRunFilterActive,
      filteredProjectRuns: _filteredProjectRuns,
      entityLabelValues: _entityLabelValues,
      entityMetadataChips: _entityMetadataChips,
      formatDate: _formatProjectDate,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      projectItemRow: _projectItemRow,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      mobileView: () => _projectMobileShellController().currentView(),
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      logClientError: (message, err) => {
        _shellLogClientError(message, err);
      }
    });
    return projectRunsController;
  }
  let projectMobileCompareController = null;
  function _projectMobileCompareController() {
    if (projectMobileCompareController) return projectMobileCompareController;
    const projectMobileCompare = _projectModule("DarklabProjectMobileCompare", importedProjectMobileCompare);
    const factory = projectMobileCompare && projectMobileCompare.createProjectMobileCompareController;
    if (typeof factory !== "function") throw new Error("DarklabProjectMobileCompare is unavailable");
    projectMobileCompareController = factory({
      projectWorkspaceModal,
      projectSummary: projectWorkspaceState.summary,
      projectComparableRuns: _projectComparableRuns,
      projectRunBaselineLabelOptions: _projectRunBaselineLabelOptions,
      projectRunCompareOptionText: _projectRunCompareOptionText,
      entityLabelValues: _entityLabelValues,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      compareProjectRuns: _compareProjectRuns,
      closeProjectWorkspace: closeProjectWorkspace3,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage
    });
    return projectMobileCompareController;
  }
  let projectMobileShellController = null;
  function _projectMobileShellController() {
    if (projectMobileShellController) return projectMobileShellController;
    const projectMobileShell = _projectModule("DarklabProjectMobileShell", importedProjectMobileShell);
    const factory = projectMobileShell && projectMobileShell.createProjectMobileShellController;
    if (typeof factory !== "function") throw new Error("DarklabProjectMobileShell is unavailable");
    projectMobileShellController = factory({
      activeProject: _activeProject,
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      emptyProjectPanel: _emptyProjectPanel,
      mobileSection: _projectMobileSection,
      orderedProjectRows: _orderedProjectRows,
      projectIsArchived: _projectIsArchived,
      projectMobileBody,
      projectMobileCreateForm,
      projectMobileDetailView,
      projectMobileListView,
      projectMobileNameInput,
      projectMobilePagination,
      projectMobileRoot,
      projectMobileSummary,
      projectPagination: projectWorkspaceState.pagination,
      projectRows: projectWorkspaceState.rows,
      projectPagination: projectWorkspaceState.pagination,
      projectWorkspaceLoading: projectWorkspaceState.loading,
      renderMobileListRow: _renderProjectMobileListRow,
      renderProjectPagination: _renderProjectPagination,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      renderProjectWorkspace: _renderProjectWorkspace,
      selectedProjectId: projectWorkspaceState.selectedId,
      ensureProjectSummary: _ensureProjectSummary,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      setSelectedProjectId: projectWorkspaceState.setSelectedId,
      setWorkspaceTab: projectWorkspaceState.setTab
    });
    return projectMobileShellController;
  }
  let projectMobileDetailController = null;
  function _projectMobileDetailController() {
    if (projectMobileDetailController) return projectMobileDetailController;
    const projectMobileDetail = _projectModule("DarklabProjectMobileDetail", importedProjectMobileDetail);
    const factory = projectMobileDetail && projectMobileDetail.createProjectMobileDetailController;
    if (typeof factory !== "function") throw new Error("DarklabProjectMobileDetail is unavailable");
    projectMobileDetailController = factory({
      projectWorkspaceModal,
      projectMobileDetailView,
      projectMobileDetailBody,
      projectMobileTabs,
      notePreviewLimit: PROJECT_WORKSPACE_CONSTANTS.mobileNotePreviewLimit,
      selectedProjectId: projectWorkspaceState.selectedId,
      setSelectedProjectId: projectWorkspaceState.setSelectedId,
      projectWorkspaceTab: projectWorkspaceState.tab,
      projectWorkspaceLoading: projectWorkspaceState.loading,
      activeProject: _activeProject,
      projectRows: projectWorkspaceState.rows,
      projectSummary: _projectSummary,
      projectCounts: _projectCounts,
      projectDisplayName: _projectDisplayName,
      projectTargetItems: _projectTargetItems,
      projectRunItems: _projectRunItems,
      projectRunById: _projectRunById,
      projectComparableRuns: _projectComparableRuns,
      projectArtifactItems: _projectArtifactItems,
      pagedProjectArtifactItems: _pagedProjectArtifactItems,
      projectArtifactPagination: _projectArtifactPagination,
      projectArtifactServerFilterKey: _projectArtifactServerFilterKey,
      loadProjectArtifacts: _loadProjectArtifacts,
      projectFindingItems: _projectFindingItems,
      projectFindingsLoaded: _projectFindingsLoaded,
      projectFindingsLoadingId: () => _projectFindingsDataController().loadingId(),
      hasProjectFindings: (projectId) => _projectFindingsDataController().loaded(projectId),
      projectFindingPagination: (projectId, summary) => _projectFindingsDataController().page(projectId, summary),
      projectFindingServerFiltersActive: _projectFindingServerFiltersActive,
      projectFindingGroupCollapsed: _projectFindingGroupCollapsed,
      collapsedFindingGroupLabels: _projectCollapsedFindingGroupLabels,
      projectArtifactGroupCollapsed: _projectArtifactGroupCollapsed,
      projectTargetFilterActive: _projectTargetFilterActive,
      projectRunFilterActive: _projectRunFilterActive,
      projectRunPagination: _projectRunPagination,
      loadProjectRuns: _loadProjectRuns,
      projectArtifactsVisible: _projectArtifactsVisible,
      projectArtifactStatus: _projectArtifactStatus,
      projectArtifactStatusLabel: _projectArtifactStatusLabel,
      projectArtifactDetailLines: _projectArtifactDetailLines,
      projectFindingTargetText: _projectFindingTargetText,
      projectTargetLabel: _projectTargetLabel,
      projectRunFindingCount: _projectRunFindingCount,
      projectRunArtifactCount: _projectRunArtifactCount,
      filteredProjectRuns: _filteredProjectRuns,
      filteredProjectFindings: _filteredProjectFindings,
      filteredProjectArtifacts: _filteredProjectArtifacts,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      entityMetadataChips: _entityMetadataChips,
      entityMetadataChipClass: _entityMetadataChipClass,
      formatDate: _formatProjectDate,
      shortProjectRunId: _shortProjectRunId,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      findingReviewControl: _findingReviewControl,
      renderProjectMobileDetailTopbar: _renderProjectMobileDetailTopbar,
      renderProjectMobileTabs: _renderProjectMobileTabs,
      renderProjectMobileEntitiesTab: (projectId, summary) => _projectEntitiesController().renderMobileEntitiesTab(projectId, summary),
      renderProjectMobileOverviewTab: _renderProjectMobileOverviewTab,
      renderProjectMobilePackagesTab: _renderProjectMobilePackagesTab,
      renderProjectMobileReportTab: _renderProjectMobileReportTab,
      renderProjectMobileActivityTab: _renderProjectMobileActivityTab,
      renderProjectMobileMonitoringTab: _renderProjectMobileMonitoringTab,
      setProjectMobileView: _setProjectMobileView,
      loadProjectFindings: _loadProjectFindings,
      loadProjectFilteredFindings: _loadProjectFilteredFindings,
      groupBy: _groupBy,
      mobileMenuText: "☰",
      caretText: "▾",
      metaSeparator: " · "
    });
    return projectMobileDetailController;
  }
  let projectEntityEditorController = null;
  function _projectEntityEditorController() {
    if (projectEntityEditorController) return projectEntityEditorController;
    const projectEntityEditor = _projectModule("DarklabProjectEntityEditor", importedProjectEntityEditor);
    const factory = projectEntityEditor && projectEntityEditor.createProjectEntityEditorController;
    if (typeof factory !== "function") throw new Error("DarklabProjectEntityEditor is unavailable");
    projectEntityEditorController = factory({
      overlay: projectEntityEditorOverlay,
      title: projectEntityEditorTitle,
      subtitle: projectEntityEditorSubtitle,
      form: projectEntityEditorForm,
      labelsInput: projectEntityLabelsInput,
      noteInput: projectEntityNoteInput,
      activityRoot: projectEntityActivityRoot,
      submitButton: projectEntitySubmitButton,
      parseLabelInput: EntityMetadataClient.parseLabelInput,
      entityTitleForEditor: _entityTitleForEditor,
      entityEditorLabelForType: _entityEditorLabelForType,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      syncEntityLabels: _syncEntityLabels,
      syncEntityNote: _syncEntityNote,
      projectResponseError: _projectResponseError,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      openProjectActivity: _openProjectActivity,
      refreshProjectWorkspace: refreshProjectWorkspace2,
      invalidateProjectFindings: _invalidateProjectFindings,
      invalidateProjectTargetPage: (projectId) => _projectDetailsController().invalidateTargetPage(projectId),
      loadProjectFindings: _loadProjectFindings,
      renderProjectExplorer: _renderProjectExplorer,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      syncProjectWorkspaceNestedSuppression: _syncProjectWorkspaceNestedSuppression,
      installProjectMobileKeyboardGuards: _installProjectMobileKeyboardGuards,
      focusProjectNestedSheet: _focusProjectNestedSheet
    });
    return projectEntityEditorController;
  }
  let projectWorkspaceLifecycleController = null;
  function _projectWorkspaceLifecycleController() {
    if (projectWorkspaceLifecycleController) return projectWorkspaceLifecycleController;
    const projectWorkspaceLifecycle = _projectModule("DarklabProjectWorkspaceLifecycle", importedProjectWorkspaceLifecycle);
    const factory = projectWorkspaceLifecycle && projectWorkspaceLifecycle.createProjectWorkspaceLifecycleController;
    if (typeof factory !== "function") throw new Error("DarklabProjectWorkspaceLifecycle is unavailable");
    projectWorkspaceLifecycleController = factory({
      apiFetch: _shellApiFetch,
      projectWorkspaceBody,
      selectedProjectId: projectWorkspaceState.selectedId,
      setSelectedProjectId: projectWorkspaceState.setSelectedId,
      projectRows: projectWorkspaceState.rows,
      setProjectRows: projectWorkspaceState.setRows,
      projectPagination: projectWorkspaceState.pagination,
      setProjectPagination: projectWorkspaceState.setPagination,
      projectSummaries: projectWorkspaceState.summaries,
      setProjectSummary: projectWorkspaceState.setSummary,
      setProjectSummaries: projectWorkspaceState.setSummaries,
      projectWorkspaceLoading: projectWorkspaceState.loading,
      setProjectWorkspaceLoading: projectWorkspaceState.setLoading,
      workspaceTab: projectWorkspaceState.tab,
      activeProject: _activeProject,
      loadActiveProjectContext,
      invalidateProjectFindings: _invalidateProjectFindings,
      invalidateProjectRuns: _invalidateProjectRuns,
      invalidateProjectTargetPage: (projectId) => _projectDetailsController().invalidateTargetPage(projectId),
      invalidateProjectEntities: (projectId = "") => _projectEntitiesController().invalidate(projectId),
      invalidateProjectArtifacts: (projectId = "") => _projectArtifactsControllerIfReady()?.invalidate?.(projectId),
      invalidateProjectOverview: (projectId = "") => _projectOverviewControllerIfReady()?.invalidate?.(projectId),
      invalidateProjectMonitoring: (projectId = "") => _projectMonitoringControllerIfReady()?.invalidate?.(projectId),
      renderProjectWorkspace: _renderProjectWorkspace,
      syncProjectNotesForm: _syncProjectNotesForm,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      logClientError: (message, err) => {
        _shellLogClientError(message, err);
      }
    });
    return projectWorkspaceLifecycleController;
  }
  let projectWorkspaceEventsController = null;
  function _projectWorkspaceEventsController() {
    if (projectWorkspaceEventsController) return projectWorkspaceEventsController;
    const projectWorkspaceEvents = _projectModule("DarklabProjectWorkspaceEvents", importedProjectWorkspaceEvents);
    const factory = projectWorkspaceEvents && projectWorkspaceEvents.createProjectWorkspaceEventsController;
    if (typeof factory !== "function") throw new Error("DarklabProjectWorkspaceEvents is unavailable");
    projectWorkspaceEventsController = factory({
      activeProject: _activeProject,
      artifactGroupKey: _projectArtifactGroupKey,
      avoidProjectRunCompareLabelSelfTarget: _avoidProjectRunCompareLabelSelfTarget,
      clearEditingTargetIf: projectWorkspaceState.clearEditingTargetIf,
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectFilterMenus: _closeProjectFilterMenus,
      closeProjectPackageManifest: _closeProjectPackageManifest,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      closeProjectWorkspace: closeProjectWorkspace3,
      compareProjectRuns: _compareProjectRuns,
      confirmProjectDelete: _confirmProjectDelete,
      confirmProjectDestructive: _confirmProjectDestructive,
      confirmProjectPackageDelete: _confirmProjectPackageDelete,
      confirmProjectRunUnlink: _confirmProjectRunUnlink,
      confirmProjectTargetDelete: _confirmProjectTargetDelete,
      downloadProjectArtifact: _downloadProjectArtifact,
      downloadProjectPackage: _downloadProjectPackage,
      entitiesController: _projectEntitiesController,
      entitySelectMode: projectWorkspaceState.entitySelectMode,
      filteredProjectFindings: _filteredProjectFindings,
      filtersController: _projectFiltersController,
      findingGroupKey: _projectFindingGroupKey,
      findingSelectMode: projectWorkspaceState.findingSelectMode,
      flushProjectNotesAutosave: _flushProjectNotesAutosave,
      invalidateProjectFindings: _invalidateProjectFindings,
      invalidateProjectOverview: (projectId = "") => _projectOverviewControllerIfReady()?.invalidate?.(projectId),
      isProjectWorkspaceOpen: isProjectWorkspaceOpen3,
      linkLastRunToProject: _linkLastRunToProject,
      ensureProjectSummary: _ensureProjectSummary,
      loadProjectRuns: _loadProjectRuns,
      loadProjectAutocompleteTargets: () => {
        loadProjectAutocompleteTargets?.().catch(() => {
        });
      },
      loadProjectFilteredFindings: _loadProjectFilteredFindings,
      loadProjectFindings: _loadProjectFindings,
      loadProjectTargetPage: (projectId, options) => _projectDetailsController().loadTargetPage(projectId, options),
      mobileView: () => _projectMobileShellController().currentView(),
      openProjectEntityEditor: _openProjectEntityEditor,
      openProjectEntityInAtlas: _openProjectEntityInAtlas,
      openFindingsBoard: _shellOpenFindingsBoard,
      openProjectEntityPicker: _openProjectEntityPicker,
      openProjectMobileActionSheet: _openProjectMobileActionSheet,
      openProjectMobileCompareSheet: _openProjectMobileCompareSheet,
      openProjectPackageManifest: _openProjectPackageManifest,
      openProjectPackageWizardFromPackage: _openProjectPackageWizardFromPackage,
      openProjectTargetEditor: _openProjectTargetEditor,
      packagesController: _projectPackagesControllerIfReady,
      previewProjectArtifact: _previewProjectArtifact,
      reportController: _projectReportControllerIfReady,
      activityController: _projectActivityControllerIfReady,
      monitoringController: _projectMonitoringControllerIfReady,
      projectArtifactItems: _projectArtifactItems,
      projectArtifactPagination: _projectArtifactPagination,
      projectDisplayName: _projectDisplayName,
      projectExplorerBody,
      projectFindingPagination: _projectFindingPagination,
      projectFindingItems: _projectFindingItems,
      projectFindingCommandFilterSet: _projectFindingCommandFilterSet,
      projectFindingLabelFilterSet: _projectFindingLabelFilterSet,
      projectFindingServerFiltersActive: _projectFindingServerFiltersActive,
      projectFindingSeverityFilterSet: _projectFindingSeverityFilterSet,
      projectFindingScopeFilterSet: _projectFindingScopeFilterSet,
      projectFindingStatusFilterSet: _projectFindingStatusFilterSet,
      projectMobileDetailBody,
      projectMobileListView,
      projectMobileProjectActions: _projectMobileProjectActions,
      projectPackageById: _projectPackageById,
      projectPagination: projectWorkspaceState.pagination,
      projectRows: projectWorkspaceState.rows,
      projectRunPagination: _projectRunPagination,
      projectRunFilterSet: _projectRunFilterSet,
      projectRunItems: _projectRunItems,
      projectSummary: _projectSummary,
      projectTargetFilterSet: _projectTargetFilterSet,
      projectTargetPage: (projectId) => _projectDetailsController().targetPage(projectId),
      projectTargetById: (projectId, targetId) => _projectDetailsController().targetById(projectId, targetId),
      removeCachedProjectTarget: (projectId, targetId) => _projectDetailsController().removeCachedTarget(projectId, targetId),
      updateCachedProjectTarget: (projectId, targetId, updates) => _projectDetailsController().updateCachedTarget(projectId, targetId, updates),
      projectTargetItems: _projectTargetItems,
      projectWorkspaceModal,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      refreshProjectWorkspace: refreshProjectWorkspace2,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobile: _renderProjectMobile,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      renderProjectWorkspace: _renderProjectWorkspace,
      selectedEntityIds: projectWorkspaceState.selectedEntityIds,
      selectedFindingIds: projectWorkspaceState.selectedFindingIds,
      selectedProjectId: projectWorkspaceState.selectedId,
      selectProjectFromMobile: _selectProjectFromMobile,
      setFindingViewMode: projectWorkspaceState.setFindingViewMode,
      setProjectFindingPageOffset: _setProjectFindingPageOffset,
      setProjectArtifactPageOffset: _setProjectArtifactPageOffset,
      setProjectRunPageOffset: _setProjectRunPageOffset,
      setProjectPaginationOffset: _setProjectPaginationOffset,
      setCachedFindingReviewState: _setCachedFindingReviewState,
      updateCachedProjectFinding: _updateCachedProjectFinding,
      setFindingSelectMode: projectWorkspaceState.setFindingSelectMode,
      setProjectMobileCreateOpen: _setProjectMobileCreateOpen,
      setProjectMobileView: _setProjectMobileView,
      setProjectPackageDownloadBusy: _setProjectPackageDownloadBusy,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      setProjectRunCompareMode: _setProjectRunCompareMode,
      setSelectedProjectId: projectWorkspaceState.setSelectedId,
      setWorkspaceTab: projectWorkspaceState.setTab,
      restoreHistoryRunIntoTab: _shellFn("restoreHistoryRunIntoTab", restoreHistoryRunIntoTab),
      syncProjectRunCompareMode: _syncProjectRunCompareMode,
      toggleArtifactGroup: projectWorkspaceState.toggleArtifactGroup,
      toggleFindingGroup: projectWorkspaceState.toggleFindingGroup,
      toggleMobileArchivedOpen: () => {
        _projectMobileShellController().setArchivedOpen(!_projectMobileShellController().isArchivedOpen());
      },
      workspaceTab: projectWorkspaceState.tab
    });
    return projectWorkspaceEventsController;
  }
  function _projectTargetById(summary, targetId) {
    return _projectFiltersController().targetById(summary, targetId);
  }
  function _projectTargetFilterLabel(target) {
    return _projectFiltersController().targetFilterLabel(target);
  }
  function _targetFilterableProjectTab() {
    return _projectFiltersController().targetFilterableProjectTab(projectWorkspaceState.tab());
  }
  function _projectTargetFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().targetFilterSet(projectId);
  }
  function _projectTargetFilterIds(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().targetFilterIds(projectId, summary);
  }
  function _projectTargetFilterActive(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().targetFilterActive(projectId, summary);
  }
  function _projectRunFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().runFilterSet(projectId);
  }
  function _projectRunFilterIds(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().runFilterIds(projectId, summary);
  }
  function _projectRunFilterActive(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().runFilterActive(projectId, summary);
  }
  function _projectRunFilterLabel(run) {
    return _projectFiltersController().runFilterLabel(run);
  }
  function _projectRunFilterChipLabel(run) {
    return _projectFiltersController().runFilterChipLabel(run);
  }
  function _projectFindingStatusFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingStatusFilterSet(projectId);
  }
  function _projectFindingCommandFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingCommandFilterSet(projectId);
  }
  function _projectFindingSeverityFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingSeverityFilterSet(projectId);
  }
  function _projectFindingScopeFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingScopeFilterSet(projectId);
  }
  function _projectFindingStatusFilterValues(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingStatusFilterValues(projectId);
  }
  function _projectFindingStatusFilterActive(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingStatusFilterActive(projectId);
  }
  function _projectFindingLabelFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingLabelFilterSet(projectId);
  }
  function _projectFindingLabelOptions(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingLabelOptions(projectId);
  }
  function _projectFindingLabelFilterValues(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingLabelFilterValues(projectId);
  }
  function _projectFindingLabelFilterActive(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingLabelFilterActive(projectId);
  }
  function _projectFindingNoteStateValue(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingNoteStateValue(projectId);
  }
  function _projectFindingNoteStateFilterActive(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingNoteStateFilterActive(projectId);
  }
  function _projectFindingOrphanFilterValue(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingOrphanFilterValue(projectId);
  }
  function _projectFindingOrphanFilterActive(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingOrphanFilterActive(projectId);
  }
  function _projectFindingSortValue(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingSortValue(projectId);
  }
  function _projectFindingTargetText(summary, finding) {
    return _projectFiltersController().findingTargetText(summary, finding);
  }
  function _sortProjectFindings(findings, projectId, summary) {
    return _projectFiltersController().sortProjectFindings(findings, projectId, summary);
  }
  function _findingReviewStateLabel(value) {
    return _projectFindingsController().reviewStateLabel(value);
  }
  function _projectFindingGroupKey(projectId, runLabel) {
    return _projectFindingsController().groupKey(projectId, runLabel);
  }
  function _projectFindingGroupCollapsed(projectId, runLabel) {
    return _projectFindingsController().groupCollapsed(projectId, runLabel);
  }
  function _projectCollapsedFindingGroupLabels(projectId = projectWorkspaceState.selectedId()) {
    return _projectFindingsController().collapsedGroupLabels(projectId);
  }
  function _projectArtifactGroupKey(projectId, runId) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.groupKey(projectId, runId);
    return `${String(projectId || "")}${String(runId || "")}`;
  }
  function _projectArtifactGroupCollapsed(projectId, runId) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.groupCollapsed(projectId, runId);
    return projectWorkspaceState.collapsedArtifactGroups().has(_projectArtifactGroupKey(projectId, runId));
  }
  function _projectRunItems(summary) {
    return _projectSharedUiController().runItems(summary);
  }
  function _projectRunPagination(projectId = projectWorkspaceState.selectedId()) {
    return _projectRunsController().page(projectId);
  }
  function _setProjectRunPageOffset(projectId = projectWorkspaceState.selectedId(), offset = 0) {
    _projectRunsController().setPageOffset(projectId, offset);
  }
  async function _loadProjectRuns(projectId = projectWorkspaceState.selectedId(), options = {}) {
    await _projectRunsController().load(projectId, options);
  }
  function _invalidateProjectRuns(projectId = "") {
    _projectRunsController().invalidate(projectId);
  }
  function _projectRunById(summary, runId) {
    return _projectSharedUiController().runById(summary, runId);
  }
  function _projectComparableRuns(summary) {
    return _projectSharedUiController().comparableRuns(summary);
  }
  function _shortProjectRunId(runId) {
    return _projectSharedUiController().shortRunId(runId);
  }
  function _projectArtifactItems(summary) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.items(summary);
    return summary && Array.isArray(summary.artifacts) ? summary.artifacts : [];
  }
  function _projectArtifactPagination(projectId = projectWorkspaceState.selectedId()) {
    const controller = _projectArtifactsControllerIfReady() || (_projectArtifactsFactoryReady() ? _projectArtifactsController() : null);
    if (controller) return controller.page(projectId);
    return { artifacts: [], total: 0, runCounts: {}, limit: 50, offset: 0, loading: true, loaded: false, error: "" };
  }
  function _setProjectArtifactPageOffset(projectId = projectWorkspaceState.selectedId(), offset = 0) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) controller.setPageOffset(projectId, offset);
  }
  function _pagedProjectArtifactItems(projectId = projectWorkspaceState.selectedId(), artifacts = []) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.pagedItems(projectId, artifacts);
    const page = _projectArtifactPagination(projectId);
    const offset = Math.max(0, Number(page.offset || 0));
    const limit = Math.max(1, Number(page.limit || 50));
    return (Array.isArray(artifacts) ? artifacts : []).slice(offset, offset + limit);
  }
  async function _loadProjectArtifacts(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId), options = {}) {
    const controller = await _loadProjectArtifactsController();
    return controller.load(projectId, summary, options);
  }
  async function _loadAllProjectArtifacts(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    const controller = await _loadProjectArtifactsController();
    return controller.loadAll(projectId, summary);
  }
  function _projectFilesEnabled() {
    return !!(_shellValue("APP_CONFIG") && _shellValue("APP_CONFIG").workspace_enabled === true);
  }
  function _projectArtifactsVisible() {
    return _projectFilesEnabled();
  }
  function _projectArtifactStatus(artifact) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.status(artifact);
    const artifactStatus = String(artifact && artifact.file_status || "").trim();
    if (["available", "missing", "changed", "disabled"].includes(artifactStatus)) return artifactStatus;
    return artifact && artifact.file_available === false ? "missing" : "available";
  }
  function _projectArtifactStatusLabel(artifact) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.statusLabel(artifact);
    const artifactStatus = _projectArtifactStatus(artifact);
    if (artifactStatus === "disabled") return "disabled";
    if (artifactStatus === "changed") return "changed";
    if (artifactStatus === "missing") return "missing";
    return "available";
  }
  function _projectArtifactAccessory(projectId, artifact) {
    const controller = _projectArtifactsControllerIfReady();
    return controller ? controller.accessory(projectId, artifact) : null;
  }
  function _entityLabelValues(entity) {
    return _projectSharedUiController().entityLabelValues(entity);
  }
  function _entityNoteBody(entity) {
    return _projectSharedUiController().entityNoteBody(entity);
  }
  function _entityMetadataChips(entity) {
    return _projectSharedUiController().entityMetadataChips(entity);
  }
  function _entityMetadataChipClass(kind = "label") {
    return _projectSharedUiController().entityMetadataChipClass(kind);
  }
  function _projectProvenanceSummary(manifest, options) {
    return _projectSharedUiController().projectProvenanceSummary(manifest, options);
  }
  function _projectProvenanceSummaryElement(manifest, options) {
    return _projectSharedUiController().projectProvenanceSummaryElement(manifest, options);
  }
  function _appendProjectLabelChips(parent, project, { className = "project-label-chips" } = {}) {
    _projectDetailsController().appendLabelChips(parent, project, { className });
  }
  function _appendProjectMobileLabelChips(parent, project) {
    _projectDetailsController().appendMobileLabelChips(parent, project);
  }
  function _entityTitleForEditor(entityType, entity) {
    return _projectSharedUiController().entityTitleForEditor(entityType, entity);
  }
  function _entityEditorLabelForType(entityType) {
    return _projectSharedUiController().entityEditorLabelForType(entityType);
  }
  function _projectArtifactDetail(artifact) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.detail(artifact);
    const parts = [
      artifact && artifact.kind || "file",
      artifact && artifact.content_type || "unknown type",
      _formatProjectDate(artifact && artifact.created)
    ];
    const artifactStatus = _projectArtifactStatus(artifact);
    const statusDetail = String(artifact && artifact.file_status_detail || "").trim();
    if (artifactStatus === "changed") {
      parts.push(`current ${_formatProjectBytes(artifact && artifact.current_byte_size)}`);
    } else if (artifactStatus === "missing") {
      parts.push(statusDetail || "workspace file is missing");
    } else if (artifactStatus === "disabled") {
      parts.push(statusDetail || "Files are disabled on this instance");
    }
    return parts.filter(Boolean).join(" · ");
  }
  function _projectArtifactDetailLines(artifact) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.detailLines(artifact);
    const artifactStatus = _projectArtifactStatus(artifact);
    const statusDetail = String(artifact && artifact.file_status_detail || "").trim();
    const lines = [
      [artifact && artifact.kind || "file", artifact && artifact.content_type || "unknown type"].filter(Boolean).join(" · "),
      _formatProjectDate(artifact && artifact.created)
    ].filter(Boolean);
    if (artifactStatus === "changed") {
      lines.push(`current ${_formatProjectBytes(artifact && artifact.current_byte_size)}`);
    } else if (artifactStatus === "missing") {
      lines.push(statusDetail || "workspace file is missing");
    } else if (artifactStatus === "disabled") {
      lines.push(statusDetail || "Files are disabled on this instance");
    }
    return lines;
  }
  function _projectArtifactDownloadName(artifactPath = "", fallback = "artifact") {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.downloadName(artifactPath, fallback);
    const name = String(artifactPath || "").split("/").filter(Boolean).pop();
    return name || fallback;
  }
  function _downloadBlobAsAttachment(blob, filename, successMessage = "") {
    _projectSharedUiController().downloadBlobAsAttachment(blob, filename, successMessage);
  }
  function _downloadUrlAsAttachment(url, filename = "", successMessage = "") {
    _projectSharedUiController().downloadUrlAsAttachment(url, filename, successMessage);
  }
  function _syncProjectWorkspaceNestedSuppression() {
    _projectNestedSheetsController().syncWorkspaceSuppression();
  }
  function _focusProjectNestedSheet(overlay, preferred = null) {
    _projectNestedSheetsController().focusNestedSheet(overlay, preferred);
  }
  function _syncProjectMobileFocusedField() {
    _projectNestedSheetsController().syncMobileFocusedField();
  }
  function _installProjectMobileKeyboardGuards() {
    _projectNestedSheetsController().installKeyboardGuards();
  }
  function _closeProjectPackageManifest() {
    const controller = _projectPackagesControllerIfReady();
    if (controller) {
      controller.closeManifest();
      return;
    }
    if (!projectPackageManifestOverlay) return;
    projectPackageManifestOverlay.classList.add("u-hidden");
    projectPackageManifestOverlay.classList.remove("open");
    projectPackageManifestOverlay.setAttribute("aria-hidden", "true");
  }
  function isProjectPackageManifestOpen() {
    const controller = _projectPackagesControllerIfReady();
    if (controller) return controller.isManifestOpen();
    return !!(projectPackageManifestOverlay && projectPackageManifestOverlay.classList.contains("open"));
  }
  function _openProjectPackageManifest(pkg) {
    _loadProjectPackagesController().then((controller) => controller.openManifest(pkg)).catch((err) => {
      _shellLogClientError("failed to load project package manifest", err);
      _setProjectWorkspaceMessage("Could not load package manifest.", { error: true });
    });
  }
  async function _previewProjectArtifact(projectId, artifactId) {
    const controller = await _loadProjectArtifactsController();
    await controller.preview(projectId, artifactId);
  }
  async function _downloadProjectArtifact(projectId, artifactId, artifactPath = "") {
    const controller = await _loadProjectArtifactsController();
    await controller.download(projectId, artifactId, artifactPath);
  }
  function _projectPackageItems(summary) {
    const controller = _projectPackagesControllerIfReady();
    if (controller) return controller.items(summary);
    return summary && Array.isArray(summary.packages) ? summary.packages : [];
  }
  function _projectPackageWizardActive(projectId = projectWorkspaceState.selectedId()) {
    const controller = _projectPackagesControllerIfReady();
    return controller ? controller.isWizardActive(projectId) : false;
  }
  function isProjectPackageWizardOpen() {
    const controller = _projectPackagesControllerIfReady();
    if (controller) return controller.isWizardOpen();
    return !!(projectPackageWizardOverlay && projectPackageWizardOverlay.classList.contains("open"));
  }
  function isProjectEntityEditorOpen() {
    if (!_projectWorkspaceModulesReady()) {
      return !!(projectEntityEditorOverlay && projectEntityEditorOverlay.classList.contains("open"));
    }
    return _projectEntityEditorController().isOpen();
  }
  function _closeProjectEntityEditor() {
    if (!_projectWorkspaceModulesReady()) {
      if (!projectEntityEditorOverlay) return;
      projectEntityEditorOverlay.classList.add("u-hidden");
      projectEntityEditorOverlay.classList.remove("open");
      projectEntityEditorOverlay.setAttribute("aria-hidden", "true");
      return;
    }
    _projectEntityEditorController().close();
  }
  function _openProjectEntityEditor(projectId, entityType, entity, options = {}) {
    _projectEntityEditorController().open(projectId, entityType, entity, options);
  }
  function openEntityMetadataEditor(entityType, entity, options = {}) {
    const projectId = options && Object.prototype.hasOwnProperty.call(options, "projectId") ? options.projectId : "";
    _ensureProjectWorkspaceModules().then(() => _openProjectEntityEditor(projectId, entityType, entity, options)).catch((err) => {
      _shellLogClientError("failed to load project entity editor", err);
      _shellShowToast("Could not open the metadata editor.", "error");
    });
  }
  function _renderProjectPackageWizardModal(options = {}) {
    const controller = _projectPackagesControllerIfReady();
    if (controller) controller.renderWizardModal(options);
  }
  function _openProjectPackageWizard(projectId, preset = "evidence") {
    _loadProjectPackagesController().then((controller) => controller.openWizard(projectId, preset)).catch((err) => {
      _shellLogClientError("failed to load project package wizard", err);
      _setProjectWorkspaceMessage("Could not load package builder.", { error: true });
    });
  }
  function _openProjectPackageWizardFromPackage(projectId, pkg) {
    _loadProjectPackagesController().then((controller) => controller.openWizardFromPackage(projectId, pkg)).catch((err) => {
      _shellLogClientError("failed to load project package wizard", err);
      _setProjectWorkspaceMessage("Could not load package builder.", { error: true });
    });
  }
  function _closeProjectPackageWizard(options = {}) {
    const controller = _projectPackagesControllerIfReady();
    if (controller) controller.closeWizard(options);
    else if (projectPackageWizardOverlay) {
      projectPackageWizardOverlay.classList.add("u-hidden");
      projectPackageWizardOverlay.classList.remove("open");
      projectPackageWizardOverlay.setAttribute("aria-hidden", "true");
    }
  }
  function _projectPackageById(summary, packageId) {
    const controller = _projectPackagesControllerIfReady();
    if (controller) return controller.byId(summary, packageId);
    const normalized = String(packageId || "").trim();
    if (!normalized || !summary || !Array.isArray(summary.packages)) return null;
    return summary.packages.find((item) => String(item && item.id || "") === normalized) || null;
  }
  function _setProjectPackageDownloadBusy(button, busy) {
    const controller = _projectPackagesControllerIfReady();
    if (controller) {
      controller.setDownloadBusy(button, busy);
      return;
    }
    if (button) button.disabled = !!busy;
  }
  async function _downloadProjectPackage(projectId, pkg) {
    const controller = await _loadProjectPackagesController();
    await controller.downloadPackage(projectId, pkg);
  }
  function _projectFindingItems(projectId = projectWorkspaceState.selectedId()) {
    return _projectFindingsDataController().items(projectId);
  }
  function _projectFindingsLoaded(projectId = projectWorkspaceState.selectedId()) {
    return _projectFindingsDataController().loaded(projectId);
  }
  function _projectFindingPagination(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFindingsDataController().page(projectId, summary);
  }
  function _setProjectFindingPageOffset(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId), offset = 0) {
    _projectFindingsDataController().setPageOffset(projectId, summary, offset);
  }
  function _projectFindingServerFilterParams(projectId, summary = _projectSummary(projectId)) {
    return _projectFiltersController().findingServerFilterParams(projectId, summary);
  }
  function _projectArtifactServerFilterParams(projectId, summary = _projectSummary(projectId)) {
    const controller = _projectArtifactsControllerIfReady();
    return controller ? controller.serverFilterParams(projectId, summary) : new URLSearchParams();
  }
  function _projectArtifactServerFilterKey(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.serverFilterKey(projectId, summary);
    const params = _projectArtifactServerFilterParams(projectId, summary);
    params.sort?.();
    return params.toString();
  }
  function _projectFindingServerFiltersActive(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().findingServerFiltersActive(projectId, summary);
  }
  function _projectFindingFilteredKey(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().findingFilteredKey(projectId, summary);
  }
  function _projectFilteredFindingItems(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().filteredFindingItems(projectId, summary);
  }
  function _invalidateProjectFilteredFindings(projectId = "") {
    _projectFindingsDataController().invalidateFiltered(projectId);
  }
  function _invalidateProjectFindings(projectId = "") {
    _projectFindingsDataController().invalidate(projectId);
  }
  function _projectTargetLabel(summary, targetId) {
    return _projectSharedUiController().targetLabel(summary, targetId);
  }
  function _formatProjectDate(value) {
    return _projectSharedUiController().formatDate(value);
  }
  function _formatProjectBytes(value) {
    return _projectSharedUiController().formatBytes(value);
  }
  function _emptyProjectPanel(text) {
    return _projectSharedUiController().emptyPanel(text);
  }
  function _projectMetaRow(label, value) {
    return _projectSharedUiController().metaRow(label, value);
  }
  function _projectItemRow({ title, meta = "", detail = "", badge = "", chips = [], action = null, accessory = null, forceArticle = false }) {
    return _projectSharedUiController().itemRow({ title, meta, detail, badge, chips, action, accessory, forceArticle });
  }
  function _findingReviewControl(finding, projectId) {
    return _projectFindingsController().reviewControl(finding, projectId);
  }
  function _findingRowAccessory(finding, projectId) {
    return _projectFindingsController().rowAccessory(finding, projectId);
  }
  function _openProjectTargetEditor(projectId, target = null) {
    _projectTargetsController().openEditor(projectId, target);
  }
  function _closeProjectTargetEditor(options = {}) {
    if (!_projectWorkspaceModulesReady()) {
      if (!projectTargetEditorOverlay) return;
      projectTargetEditorOverlay.classList.add("u-hidden");
      projectTargetEditorOverlay.classList.remove("open");
      projectTargetEditorOverlay.setAttribute("aria-hidden", "true");
      return;
    }
    _projectTargetsController().closeEditor(options);
  }
  function isProjectTargetEditorOpen() {
    if (!_projectWorkspaceModulesReady()) {
      return !!(projectTargetEditorOverlay && projectTargetEditorOverlay.classList.contains("open"));
    }
    return _projectTargetsController().isOpen();
  }
  function _projectTargetDisplayRow(projectId, target) {
    return _projectTargetsController().targetDisplayRow(projectId, target);
  }
  function _projectRunRemoveControl(projectId, run) {
    return _projectRunsController().runRemoveControl(projectId, run);
  }
  function _projectRunFindingCount(projectId, runId, run = null) {
    return _projectRunsController().runFindingCount(projectId, runId, run);
  }
  function _projectRunArtifactCount(summary, runId, run = null) {
    return _projectRunsController().runArtifactCount(summary, runId, run);
  }
  function _projectRunControls(projectId, run, summary) {
    return _projectRunsController().runControls(projectId, run, summary);
  }
  function _projectRunBaselineLabelOptions(runs) {
    return _projectRunsController().baselineLabelOptions(runs);
  }
  function _projectRunCompareOptionText(run) {
    return _projectRunsController().compareOptionText(run);
  }
  function _syncProjectRunCompareMode(wrap) {
    _projectRunsController().syncCompareMode(wrap);
  }
  function _setProjectRunCompareMode(modeButton, event = null) {
    _projectRunsController().setCompareMode(modeButton, event);
  }
  function _avoidProjectRunCompareLabelSelfTarget(container, label) {
    _projectRunsController().avoidCompareLabelSelfTarget(container, label);
  }
  function _compareProjectRuns(projectId, leftId, mode, targetValue, controls = null) {
    _projectRunsController().compareRuns(projectId, leftId, mode, targetValue, controls);
  }
  function _renderProjectRunCompareControls(runs) {
    return _projectRunsController().renderCompareControls(runs);
  }
  function _renderProjectTargets(projectId, targets) {
    return _projectTargetsController().renderTargets(projectId, targets);
  }
  function _setProjectFilterMenuOpen(menu, open) {
    _projectFiltersController().setFilterMenuOpen(menu, open);
  }
  function _closeProjectFilterMenus(exceptMenu = null) {
    _projectFiltersController().closeFilterMenus(exceptMenu);
  }
  function _renderProjectFilterBar(projectId, summary) {
    return _projectFiltersController().renderFilterBar(projectId, summary);
  }
  function _syncProjectFilterSortDivider(root) {
    _projectFiltersController().syncFilterSortDivider(root);
  }
  function _scheduleProjectFilterSortDividerSync(root) {
    if (!_projectWorkspaceModulesReady()) return;
    _projectFiltersController().scheduleFilterSortDividerSync(root);
  }
  function _projectRunDirectTargetIds(run) {
    return _projectFiltersController().runDirectTargetIds(run);
  }
  function _projectFindingTargetIds(finding) {
    return _projectFiltersController().findingTargetIds(finding);
  }
  function _projectRunIdsMatchingTargets(projectId, filterIds) {
    return _projectFiltersController().runIdsMatchingTargets(projectId, filterIds);
  }
  function _projectRunMatchesTargetFilters(run, projectId, filterIds, matchingRunIds) {
    return _projectFiltersController().runMatchesTargetFilters(run, projectId, filterIds, matchingRunIds);
  }
  function _filteredProjectRuns(projectId, summary) {
    return _projectFiltersController().filteredRuns(projectId, summary);
  }
  function _filteredProjectFindings(projectId, summary) {
    return _projectFiltersController().filteredFindings(projectId, summary);
  }
  function _filteredProjectArtifacts(projectId, summary) {
    return _projectFiltersController().filteredArtifacts(projectId, summary);
  }
  function _groupBy(items, keyFn) {
    return _projectSharedUiController().groupBy(items, keyFn);
  }
  async function _loadProjectFindings(projectId, options = {}) {
    return _projectFindingsDataController().load(projectId, options);
  }
  async function _loadProjectFilteredFindings(projectId, summary = _projectSummary(projectId), options = {}) {
    await _projectFindingsDataController().loadFiltered(projectId, summary, options);
  }
  function _syncProjectForms(project = _selectedProject()) {
    _projectDetailsController().syncForms(project);
  }
  function _syncProjectNotesForm() {
    if (!_projectWorkspaceModulesReady()) return;
    _projectDetailsController().syncNotesForm();
  }
  function _flushProjectNotesAutosave() {
    if (!_projectWorkspaceModulesReady()) return Promise.resolve();
    return _projectDetailsController().flushNotesAutosave();
  }
  function _makeProjectButton(label, action, projectId, role = "secondary", tone = "") {
    return _projectSharedUiController().makeButton(label, action, projectId, role, tone);
  }
  function _projectIsArchived(project) {
    return _projectListController().isArchived(project);
  }
  function _orderedProjectRows(activeId, rows = projectWorkspaceState.rows()) {
    return _projectListController().orderedRows(activeId, rows);
  }
  function _renderProjectList() {
    _projectListController().renderList();
  }
  function _projectMobileTabItems(projectId, summary) {
    return _projectNavigationController().mobileTabItems(projectId, summary);
  }
  function _syncProjectMobileActiveTabScroll() {
    _projectNavigationController().syncMobileActiveTabScroll();
  }
  function _syncProjectMobileTabEdges() {
    _projectNavigationController().syncMobileTabEdges();
  }
  function _renderProjectMobileListRow(project, activeId) {
    return _projectListController().renderMobileListRow(project, activeId);
  }
  function _renderProjectPagination(host, options = {}) {
    return _projectListController().renderPagination(host, options);
  }
  function _projectMobileSection(label, count, { open = true } = {}) {
    return _projectListController().mobileSection(label, count, { open });
  }
  async function _setProjectMobileCreateOpen(open, { focus = false } = {}) {
    await _ensureProjectWorkspaceModules();
    _projectMobileShellController().setCreateOpen(open, { focus });
  }
  async function _setProjectMobileView(view) {
    await _ensureProjectWorkspaceModules();
    _projectMobileShellController().setView(view);
  }
  async function _selectProjectFromMobile(projectId, tab = "") {
    await _ensureProjectWorkspaceModules();
    _projectMobileShellController().selectProject(projectId, tab);
  }
  function _projectMobileProjectActions(project) {
    return _projectMobileShellController().projectActions(project);
  }
  function _renderProjectMobileDetailTopbar(project, activeId) {
    _projectNavigationController().renderMobileDetailTopbar(project, activeId);
  }
  function _renderProjectMobileTabs(projectId, summary) {
    _projectNavigationController().renderMobileTabs(projectId, summary);
  }
  function _projectMobileActionMenu(projectId, label, actions = []) {
    return _projectMobileDetailController().actionMenu(projectId, label, actions);
  }
  function _closeProjectMobileActionSheet({ restoreFocus = true } = {}) {
    if (!_projectWorkspaceModulesReady()) return;
    _projectMobileDetailController().closeActionSheet({ restoreFocus });
  }
  function _openProjectMobileActionSheet(projectId, label, actions = [], returnFocus = null) {
    _projectMobileDetailController().openActionSheet(projectId, label, actions, returnFocus);
  }
  function _closeProjectMobileCompareSheet({ restoreFocus = true } = {}) {
    if (!_projectWorkspaceModulesReady()) return;
    _projectMobileCompareController().close({ restoreFocus });
  }
  function _openProjectMobileCompareSheet(projectId, returnFocus = null) {
    _projectMobileCompareController().open(projectId, returnFocus);
  }
  function _projectMobileContentRow({
    title,
    meta = "",
    detail = "",
    badge = "",
    chips = [],
    action = null,
    accessory = null,
    className = ""
  }) {
    return _projectMobileDetailController().contentRow({
      title,
      meta,
      detail,
      badge,
      chips,
      action,
      accessory,
      className
    });
  }
  function _projectMobileEmptyPanel(text, actions = []) {
    return _projectMobileDetailController().emptyPanel(text, actions);
  }
  function _renderProjectMobileDetail() {
    _projectMobileDetailController().renderDetail();
  }
  function _renderProjectMobile() {
    _projectMobileShellController().renderMobile();
  }
  function _renderProjectHeader(project, summary, options = {}) {
    return _projectNavigationController().renderProjectHeader(project, summary, options);
  }
  function _focusProjectWorkspaceTab(tabId) {
    _projectNavigationController().focusWorkspaceTab(tabId);
  }
  function cycleProjectWorkspaceTab2(offset = 1) {
    if (!_projectWorkspaceModulesReady()) return false;
    return _projectWorkspaceRendererController().cycleTab(offset);
  }
  function _renderProjectDetails(container, project, summary) {
    _projectDetailsController().renderDetails(container, project, summary);
  }
  function _renderProjectRuns(container, projectId, summary) {
    _projectRunsController().renderRuns(container, projectId, summary);
  }
  function _openProjectEntityInAtlas(projectId, summary, entity) {
    _projectEntitiesController().openInAtlas(projectId, summary, entity);
  }
  function _openProjectEntityPicker(projectId) {
    _projectEntitiesController().openPicker(projectId);
  }
  function _renderProjectEntities(container, projectId, summary) {
    _projectEntitiesController().renderEntities(container, projectId, summary);
  }
  function _renderProjectFindings(container, projectId, summary) {
    _projectFindingsController().renderFindings(container, projectId, summary);
  }
  function _renderProjectArtifacts(container, projectId, summary) {
    if (projectArtifactsController) {
      projectArtifactsController.renderArtifacts(container, projectId, summary);
      return;
    }
    container.replaceChildren(_emptyProjectPanel("Loading project artifacts..."));
    _loadProjectArtifactsController().then((controller) => {
      if (!container.isConnected || projectWorkspaceState.tab() !== "artifacts") return;
      controller.renderArtifacts(container, projectId, summary);
    }).catch((err) => {
      _shellLogClientError("failed to load project artifacts", err);
      if (!container.isConnected) return;
      container.replaceChildren(_emptyProjectPanel("Could not load project artifacts."));
    });
  }
  function _renderProjectPackages(container, projectId, summary) {
    if (projectPackagesController) {
      projectPackagesController.renderPackages(container, projectId, summary);
      return;
    }
    container.replaceChildren(_emptyProjectPanel("Loading evidence packages..."));
    _loadProjectPackagesController().then((controller) => {
      if (!container.isConnected || projectWorkspaceState.tab() !== "packages") return;
      controller.renderPackages(container, projectId, summary);
    }).catch((err) => {
      _shellLogClientError("failed to load project packages", err);
      if (!container.isConnected) return;
      container.replaceChildren(_emptyProjectPanel("Could not load evidence packages."));
    });
  }
  function _renderProjectActivity(container, projectId, summary) {
    if (projectActivityController) {
      projectActivityController.renderActivity(container, projectId, summary);
      return;
    }
    container.replaceChildren(_emptyProjectPanel("Loading project activity..."));
    _loadProjectActivityController().then((controller) => {
      if (!container.isConnected || projectWorkspaceState.tab() !== "activity") return;
      controller.renderActivity(container, projectId, summary);
    }).catch((err) => {
      _shellLogClientError("failed to load project activity", err);
      if (!container.isConnected) return;
      container.replaceChildren(_emptyProjectPanel("Could not load project activity."));
    });
  }
  function _renderProjectOverview(container, projectId, summary) {
    if (projectOverviewController) {
      projectOverviewController.renderOverview(container, projectId, summary);
      return;
    }
    container.replaceChildren(_emptyProjectPanel("Loading project overview..."));
    _loadProjectOverviewController().then((controller) => {
      if (!container.isConnected || projectWorkspaceState.tab() !== "overview") return;
      controller.renderOverview(container, projectId, summary);
    }).catch((err) => {
      _shellLogClientError("failed to load project overview", err);
      if (!container.isConnected) return;
      container.replaceChildren(_emptyProjectPanel("Could not load project overview."));
    });
  }
  function _renderProjectMonitoring(container, projectId, summary) {
    if (projectMonitoringController) {
      projectMonitoringController.renderMonitoring(container, projectId, summary);
      return;
    }
    container.replaceChildren(_emptyProjectPanel("Loading project monitoring..."));
    _loadProjectMonitoringController().then((controller) => {
      if (!container.isConnected || projectWorkspaceState.tab() !== "monitoring") return;
      controller.renderMonitoring(container, projectId, summary);
    }).catch((err) => {
      _shellLogClientError("failed to load project monitoring", err);
      if (!container.isConnected) return;
      container.replaceChildren(_emptyProjectPanel("Could not load project monitoring."));
    });
  }
  function _openProjectObject(projectId, { tab = "", targetType = "", targetId = "" } = {}) {
    const normalizedProjectId = String(projectId || projectWorkspaceState.selectedId() || "").trim();
    const normalizedTab = String(tab || "").trim();
    if (!normalizedProjectId || !normalizedTab) return;
    if (normalizedTab === "activity") {
      _openProjectActivity(normalizedProjectId, { targetType, targetId });
      return;
    }
    projectWorkspaceState.setTab(normalizedTab);
    _renderProjectExplorer();
  }
  function _openProjectActivity(projectId, { targetId = "", targetType = "" } = {}) {
    const normalizedProjectId = String(projectId || projectWorkspaceState.selectedId() || "").trim();
    if (!normalizedProjectId) return;
    _closeProjectEntityEditor();
    projectWorkspaceState.setTab("activity");
    _renderProjectExplorer();
    _loadProjectActivityController().then((controller) => {
      const st = controller.stateFor(normalizedProjectId);
      st.filters.target_id = String(targetId || "").trim();
      st.filters.target_type = String(targetType || "").trim();
      st.offset = 0;
      st.loaded = false;
      if (projectWorkspaceState.tab() === "activity") _renderProjectExplorer();
      return controller.load(normalizedProjectId);
    }).catch((err) => {
      _shellLogClientError("failed to open project activity", err);
    });
  }
  function _renderProjectReport(container, projectId, summary) {
    if (projectReportController) {
      projectReportController.renderReport(container, projectId, summary);
      return;
    }
    container.replaceChildren(_emptyProjectPanel("Loading report builder..."));
    _loadProjectReportController().then((controller) => {
      if (!container.isConnected || projectWorkspaceState.tab() !== "report") return;
      controller.renderReport(container, projectId, summary);
    }).catch((err) => {
      _shellLogClientError("failed to load project report builder", err);
      if (!container.isConnected) return;
      container.replaceChildren(_emptyProjectPanel("Could not load the report builder."));
    });
  }
  function _renderProjectMobileReportTab(projectId, summary) {
    if (projectReportController) return projectReportController.renderMobileReportTab(projectId, summary);
    const panel = _emptyProjectPanel("Loading report builder...");
    _loadProjectReportController().then(() => {
      if (projectWorkspaceState.tab() === "report" && _projectMobileShellController().currentView() === "detail") {
        _renderProjectMobileDetail();
      }
    }).catch((err) => {
      _shellLogClientError("failed to load mobile project report builder", err);
      if (panel.isConnected) panel.replaceChildren("Could not load the report builder.");
    });
    return panel;
  }
  function _renderProjectMobilePackagesTab(projectId, summary) {
    if (projectPackagesController) return projectPackagesController.renderMobilePackagesTab(projectId, summary);
    const panel = _emptyProjectPanel("Loading evidence packages...");
    _loadProjectPackagesController().then(() => {
      if (projectWorkspaceState.tab() === "packages" && _projectMobileShellController().currentView() === "detail") {
        _renderProjectMobileDetail();
      }
    }).catch((err) => {
      _shellLogClientError("failed to load mobile project packages", err);
      if (panel.isConnected) panel.replaceChildren("Could not load evidence packages.");
    });
    return panel;
  }
  function _renderProjectMobileActivityTab(projectId, summary) {
    if (projectActivityController) return projectActivityController.renderMobileActivityTab(projectId, summary);
    const panel = _emptyProjectPanel("Loading project activity...");
    _loadProjectActivityController().then(() => {
      if (projectWorkspaceState.tab() === "activity" && _projectMobileShellController().currentView() === "detail") {
        _renderProjectMobileDetail();
      }
    }).catch((err) => {
      _shellLogClientError("failed to load mobile project activity", err);
      if (panel.isConnected) panel.replaceChildren("Could not load project activity.");
    });
    return panel;
  }
  function _renderProjectMobileOverviewTab(projectId, summary) {
    if (projectOverviewController) return projectOverviewController.renderMobileOverviewTab(projectId, summary);
    const panel = _emptyProjectPanel("Loading project overview...");
    _loadProjectOverviewController().then(() => {
      if (projectWorkspaceState.tab() === "overview" && _projectMobileShellController().currentView() === "detail") {
        _renderProjectMobileDetail();
      }
    }).catch((err) => {
      _shellLogClientError("failed to load mobile project overview", err);
      if (panel.isConnected) panel.replaceChildren("Could not load project overview.");
    });
    return panel;
  }
  function _renderProjectMobileMonitoringTab(projectId, summary) {
    if (projectMonitoringController) return projectMonitoringController.renderMobileMonitoringTab(projectId, summary);
    const panel = _emptyProjectPanel("Loading project monitoring...");
    _loadProjectMonitoringController().then(() => {
      if (projectWorkspaceState.tab() === "monitoring" && _projectMobileShellController().currentView() === "detail") {
        _renderProjectMobileDetail();
      }
    }).catch((err) => {
      _shellLogClientError("failed to load mobile project monitoring", err);
      if (panel.isConnected) panel.replaceChildren("Could not load project monitoring.");
    });
    return panel;
  }
  function _renderProjectExplorer() {
    _projectWorkspaceRendererController().renderExplorer();
  }
  function _renderProjectWorkspace() {
    _projectWorkspaceRendererController().renderWorkspace();
  }
  async function _loadProjectSummaries(projects) {
    await _projectWorkspaceLifecycleController().loadProjectSummaries(projects);
  }
  async function _ensureProjectSummary(projectId = projectWorkspaceState.selectedId()) {
    return _projectWorkspaceLifecycleController().ensureProjectSummary(projectId);
  }
  function _setProjectPaginationOffset(offset) {
    projectWorkspaceState.setPaginationOffset(offset);
  }
  async function refreshProjectWorkspace2() {
    if (!_projectWorkspaceModulesReady()) {
      if (!_projectWorkspaceOverlayOpenFallback()) return;
      await _ensureProjectWorkspaceModules();
    }
    await _projectWorkspaceLifecycleController().refreshProjectWorkspace();
  }
  function _scheduleProjectWorkspaceExternalRefresh() {
    if (!_projectWorkspaceModulesReady()) {
      if (!_projectWorkspaceOverlayOpenFallback()) return;
      _ensureProjectWorkspaceModules().then(() => _scheduleProjectWorkspaceExternalRefresh()).catch((err) => {
        _shellLogClientError("failed to load project workspace for external refresh", err);
      });
      return;
    }
    _projectWorkspaceShellController().scheduleExternalRefresh();
  }
  function _notifyProjectWorkspaceChanged(reason = "updated", projectId = "", { local = true } = {}) {
    if (!_projectWorkspaceModulesReady()) return;
    _projectWorkspaceShellController().notifyChanged(reason, projectId, { local });
  }
  _projectActiveContextController().bindTargetDiscoveryEvent();
  async function openProjectWorkspace2() {
    const openToken = ++projectWorkspaceOpenToken;
    if (!_projectWorkspaceModulesReady() && projectWorkspaceOverlay) {
      projectWorkspaceOverlay.classList.remove("u-hidden");
      projectWorkspaceOverlay.classList.add("open");
      projectWorkspaceOverlay.setAttribute("aria-hidden", "false");
      if (projectWorkspaceBody && !String(projectWorkspaceBody.textContent || "").trim()) {
        projectWorkspaceBody.textContent = "Loading projects...";
      }
      if (projectMobileBody && !String(projectMobileBody.textContent || "").trim()) {
        projectMobileBody.textContent = "Loading projects...";
      }
      _shellFn("markInteractionSurfaceReady", markInteractionSurfaceReady)?.("projects", projectWorkspaceOverlay, projectWorkspaceModal);
    }
    await _ensureProjectWorkspaceModules();
    if (openToken !== projectWorkspaceOpenToken) return false;
    await _projectWorkspaceShellController().open();
    if (openToken !== projectWorkspaceOpenToken) {
      _projectWorkspaceShellController().close({ refocus: false });
      return false;
    }
    return true;
  }
  function _autoPromoteProjectPickerContent(projects, preferredProjectId = "") {
    const wrap = document.createElement("div");
    wrap.className = "history-project-picker";
    const select = document.createElement("select");
    select.className = "form-select form-control-compact";
    select.setAttribute("aria-label", "Project");
    projects.forEach((project) => {
      const option = document.createElement("option");
      option.value = String(project.id || "");
      option.textContent = _projectDisplayName(project) || String(project.id || "");
      select.appendChild(option);
    });
    if (preferredProjectId && projects.some((project) => String(project.id || "") === preferredProjectId)) {
      select.value = preferredProjectId;
    }
    const help = document.createElement("div");
    help.className = "history-project-picker-help";
    help.textContent = "Choose a project for the new auto-promote rule.";
    wrap.append(select, help);
    return { wrap, select };
  }
  async function _promptAutoPromoteRuleProject(preferredProjectId = "") {
    if (!_shellFn("showConfirm", showConfirm)) return "";
    const resp = await _shellApiFetch("/projects?include_archived=1&include_counts=0&limit=100&offset=0", { cache: "no-store" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const projects = (Array.isArray(data.projects) ? data.projects : []).filter((project) => String(project && project.status || "active") !== "archived");
    if (!projects.length) {
      _shellShowToast("Create an active project before creating an auto-promote rule.", "error");
      return "";
    }
    const activeProject = _activeProject();
    const preferredId = preferredProjectId || (activeProject && activeProject.id ? String(activeProject.id) : "");
    const ordered = _orderedProjectRows(preferredId, projects);
    const { wrap, select } = _autoPromoteProjectPickerContent(ordered, preferredId);
    const choicePromise = _shellShowConfirm({
      body: "Create auto-promote rule from Atlas view",
      content: wrap,
      defaultFocus: select,
      actions: [
        { id: "cancel", label: "Cancel", role: "cancel" },
        { id: "create", label: "Create rule", role: "primary" }
      ],
      refocusOnResolve: false
    });
    const enhanceAppSelects2 = _shellEnhanceAppSelects();
    if (typeof enhanceAppSelects2 === "function") {
      enhanceAppSelects2(wrap);
      if (_shellUseMobileTerminalViewportMode()) {
        wrap.querySelector(".app-select-menu")?.classList.add("dropdown-up");
      }
    }
    const choice = await choicePromise;
    return choice === "create" ? String(select.value || "") : "";
  }
  async function openProjectAutoPromoteRuleFromAtlas(draft = {}) {
    const activeProject = _activeProject();
    let projectId = String(draft.project_id || "").trim();
    if (!projectId && activeProject && activeProject.id) projectId = String(activeProject.id);
    if (!projectId) projectId = await _promptAutoPromoteRuleProject();
    if (!projectId) return false;
    await openProjectWorkspace2();
    projectWorkspaceState.setSelectedId(projectId);
    projectWorkspaceState.setTab("entities");
    await _ensureProjectSummary(projectId);
    _projectEntitiesController().openAutoPromoteRuleFromAtlas(projectId, draft);
    _renderProjectWorkspace();
    _renderProjectExplorer();
    return true;
  }
  function closeProjectWorkspace3({ refocus = true } = {}) {
    projectWorkspaceOpenToken += 1;
    if (!_projectWorkspaceModulesReady()) {
      if (!projectWorkspaceOverlay) return;
      projectWorkspaceOverlay.classList.add("u-hidden");
      projectWorkspaceOverlay.classList.remove("open");
      projectWorkspaceOverlay.setAttribute("aria-hidden", "true");
      return;
    }
    _projectWorkspaceShellController().close({ refocus });
  }
  async function _projectWorkspaceRequest(url, options = {}) {
    return _projectWorkspaceShellController().request(url, options);
  }
  async function _syncEntityLabels(entityType, entityId, nextLabels) {
    await _projectWorkspaceActionsController().syncEntityLabels(entityType, entityId, nextLabels);
  }
  async function _syncEntityNote(entityType, entityId, body) {
    await _projectWorkspaceActionsController().syncEntityNote(entityType, entityId, body);
  }
  async function _linkLastRunToProject(projectId, summary) {
    await _projectWorkspaceActionsController().linkLastRunToProject(projectId, summary);
  }
  async function _confirmProjectDestructive({ body, actionLabel, actionId, note }) {
    return _projectWorkspaceActionsController().confirmDestructive({ body, actionLabel, actionId, note });
  }
  function _confirmProjectTargetDelete(targetValue) {
    return _projectWorkspaceActionsController().confirmTargetDelete(targetValue);
  }
  function _confirmProjectRunUnlink(runCommand3) {
    return _projectWorkspaceActionsController().confirmRunUnlink(runCommand3);
  }
  function _confirmProjectPackageDelete(packageName) {
    return _projectWorkspaceActionsController().confirmPackageDelete(packageName);
  }
  function _confirmProjectDelete(projectName) {
    return _projectWorkspaceActionsController().confirmProjectDelete(projectName);
  }
  function _setCachedFindingReviewState(projectId, findingId, reviewState) {
    _projectFindingsDataController().setCachedReviewState(projectId, findingId, reviewState);
  }
  function _updateCachedProjectFinding(projectId, findingId, updates) {
    _projectFindingsDataController().updateCachedFinding(projectId, findingId, updates);
  }
  function _renderUptime() {
    if (!hudUptimeEl) return;
    if (hudState.serverUptime === null) {
      hudUptimeEl.textContent = "—";
      _setValueColor(hudUptimeEl, "hud-muted");
      return;
    }
    const deltaS = (performance.now() - hudState.serverUptimeAt) / 1e3;
    hudUptimeEl.textContent = _formatUptime(hudState.serverUptime + deltaS);
    _setValueColor(hudUptimeEl, null);
  }
  function _renderClock() {
    if (!hudClockEl) return;
    const mode = typeof getHudClockPreference === "function" ? getHudClockPreference() : "utc";
    const now = Date.now();
    hudClockEl.textContent = mode === "local" ? _formatLocalClock(now) : _formatUtcClock(now);
    if (mode === "local") {
      try {
        const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || "browser local time";
        hudClockEl.title = `Clock: local time (${zone}, ${_getLocalClockLabel(new Date(now))})`;
      } catch (_) {
        hudClockEl.title = "Clock: local time";
      }
    } else {
      hudClockEl.title = "Clock: UTC";
    }
    _setValueColor(hudClockEl, null);
  }
  function _renderDb() {
    if (!hudDbEl) return;
    if (hudState.db === "ok") {
      hudDbEl.textContent = "ONLINE";
      _setValueColor(hudDbEl, "hud-value-green");
    } else if (hudState.db === "down") {
      hudDbEl.textContent = "OFFLINE";
      _setValueColor(hudDbEl, "hud-value-red");
    } else {
      hudDbEl.textContent = "—";
      _setValueColor(hudDbEl, "hud-muted");
    }
  }
  function _renderRedis() {
    if (!hudRedisEl) return;
    if (hudState.redis === "ok") {
      hudRedisEl.textContent = "ONLINE";
      _setValueColor(hudRedisEl, "hud-value-green");
      hudRedisEl.title = "Redis backend is reachable";
    } else if (hudState.redis === "down") {
      hudRedisEl.textContent = "OFFLINE";
      _setValueColor(hudRedisEl, "hud-value-red");
      hudRedisEl.title = "Redis configured but unreachable";
    } else if (hudState.redis === "none") {
      hudRedisEl.textContent = "N/A";
      _setValueColor(hudRedisEl, "hud-muted");
      hudRedisEl.title = "Redis not configured — rate limiting and process tracking run in-process";
    } else {
      hudRedisEl.textContent = "—";
      _setValueColor(hudRedisEl, "hud-muted");
    }
  }
  async function pollHudStatus() {
    const t0 = performance.now();
    try {
      const resp = await fetch("/status", { cache: "no-store", credentials: "same-origin" });
      const t1 = performance.now();
      hudState.latencyMs = t1 - t0;
      if (resp.ok) {
        const data = await resp.json();
        if (typeof data.uptime === "number") {
          hudState.serverUptime = data.uptime;
          hudState.serverUptimeAt = performance.now();
        }
        if (typeof data.db === "string") hudState.db = data.db;
        if (typeof data.redis === "string") hudState.redis = data.redis;
      }
    } catch (_) {
      hudState.latencyMs = null;
      hudState.db = "down";
      if (hudState.redis !== "none") hudState.redis = "down";
    }
    _renderLatency();
    _renderUptime();
    _renderDb();
    _renderRedis();
  }
  function _currentHudStatusPollMs() {
    return document.visibilityState === "visible" ? STATUS_POLL_VISIBLE_MS : STATUS_POLL_HIDDEN_MS;
  }
  function _startHudStatusPoll({ pollNow = false } = {}) {
    if (hudStatusPollTimer) clearInterval(hudStatusPollTimer);
    hudStatusPollTimer = setInterval(pollHudStatus, _currentHudStatusPollMs());
    if (pollNow) pollHudStatus();
  }
  window.addEventListener("storage", (e) => {
    if (e.key === "session_token") {
      _renderSession();
      loadActiveProjectContext().catch(() => {
      });
      return;
    }
    if (e.key === PROJECT_WORKSPACE_CONSTANTS.workspaceBroadcastKey && e.newValue) {
      _scheduleProjectWorkspaceExternalRefresh();
    }
  });
  document.addEventListener("visibilitychange", () => {
    _startHudStatusPoll({ pollNow: document.visibilityState === "visible" });
  });
  window.addEventListener("resize", () => {
    _scheduleProjectFilterSortDividerSync(projectExplorerBody);
  });
  if (_shellFn("onUiEvent", onUiEvent)) {
    _shellOnUiEvent("app:history-rendered", () => {
      try {
        renderRailRecent();
      } catch (_) {
      }
    });
    _shellOnUiEvent("app:workflows-rendered", (e) => {
      try {
        renderRailWorkflows(e.detail && e.detail.items);
      } catch (_) {
      }
    });
    _shellOnUiEvent("app:workflows-closed", () => {
      try {
        const renderWorkflowItemsFn = typeof hasWorkflowHandler === "function" && hasWorkflowHandler("renderWorkflowItems") ? renderWorkflowItems : _shellFn("renderWorkflowItems");
        renderWorkflowItemsFn?.(allWorkflows);
      } catch (_) {
      }
    });
    _shellOnUiEvent("app:tab-status-changed", () => {
      try {
        _renderTabs();
      } catch (_) {
      }
      try {
        _renderLastExit();
      } catch (_) {
      }
      try {
        refreshHudActions();
      } catch (_) {
      }
    });
    _shellOnUiEvent("app:tab-activated", () => {
      try {
        _renderLastExit();
      } catch (_) {
      }
      try {
        refreshHudActions();
      } catch (_) {
      }
    });
    _shellOnUiEvent("app:tab-created", () => {
      try {
        _renderTabs();
      } catch (_) {
      }
      try {
        refreshHudActions();
      } catch (_) {
      }
    });
    _shellOnUiEvent("app:tab-closed", () => {
      try {
        _renderTabs();
      } catch (_) {
      }
      try {
        refreshHudActions();
      } catch (_) {
      }
    });
    _shellOnUiEvent("app:last-exit-changed", (e) => {
      hudState.lastExit = e.detail ? e.detail.value : null;
      try {
        _renderLastExit();
      } catch (_) {
      }
    });
    _shellOnUiEvent("app:tab-kill-visibility-changed", (e) => {
      const tabId = e.detail && e.detail.tabId;
      const activeId = _shellGetActiveTabId();
      if (tabId !== activeId) return;
      try {
        _setHudKillVisible(!!(e.detail && e.detail.visible));
      } catch (_) {
      }
    });
  }
  _renderLastExit();
  _renderTabs();
  _renderSession();
  _renderClock();
  _renderLatency();
  _renderUptime();
  _renderDb();
  _renderRedis();
  _renderActiveProject();
  _startHudStatusPoll({ pollNow: true });
  setInterval(() => {
    _renderClock();
    _renderUptime();
    _renderSession();
  }, CLOCK_TICK_MS);
  applyCollapsed();
  applyWidth();
  applySectionsState();
  renderRailRecent();
  bindHudStatusMonitorTriggers();
  const ensureWorkflowCatalogLoadedFn = typeof hasWorkflowHandler === "function" && hasWorkflowHandler("ensureWorkflowCatalogLoaded") ? ensureWorkflowCatalogLoaded : _shellFn("ensureWorkflowCatalogLoaded");
  if (ensureWorkflowCatalogLoadedFn) {
    ensureWorkflowCatalogLoadedFn().then((items) => renderRailWorkflows(items)).catch(() => {
    });
  }
  refreshHudActions();
  loadActiveProjectContext().catch(() => {
  });
  document.addEventListener("click", (event) => {
    if (event.target?.closest?.("#project-mobile-new-btn")) {
      event.preventDefault();
      event.stopPropagation();
      _setProjectWorkspaceMessage("");
      _setProjectMobileCreateOpen(true, { focus: true }).catch((err) => {
        _shellLogClientError("failed to open mobile project create form", err);
      });
      return;
    }
    if (event.target?.closest?.('#project-mobile-create-form [data-project-mobile-action="cancel-create"]')) {
      event.preventDefault();
      event.stopPropagation();
      _setProjectWorkspaceMessage("");
      _setProjectMobileCreateOpen(false).catch((err) => {
        _shellLogClientError("failed to close mobile project create form", err);
      });
    }
  }, true);
  if (typeof setProjectHudHandlers === "function") {
    setProjectHudHandlers({ renderHudClock: _renderClock });
  }
  if (typeof setProjectContextHandlers === "function") {
    setProjectContextHandlers({
      closeProjectWorkspace: closeProjectWorkspace3,
      cycleProjectWorkspaceTab: cycleProjectWorkspaceTab2,
      getActiveProjectContext: _activeProject,
      isProjectWorkspaceOpen: isProjectWorkspaceOpen3,
      notifyProjectWorkspaceChanged: _notifyProjectWorkspaceChanged,
      openEntityMetadataEditor,
      openProjectAutoPromoteRuleFromAtlas,
      openProjectWorkspace: openProjectWorkspace2,
      refreshActiveProjectContext: loadActiveProjectContext,
      refreshProjectWorkspace: refreshProjectWorkspace2
    });
  }
  if (typeof setControllerActionHandlers === "function") {
    setControllerActionHandlers({ toggleRailCollapsed: toggleRailCollapsed2 });
  }
})(globalThis);

// app/static/js/mobile_chrome.js
(function initMobileChrome(global) {
  if (typeof document === "undefined") return;
  const mobileShell = document.getElementById("mobile-shell");
  if (!mobileShell) return;
  const activeTeamScopeCan2 = typeof activeTeamScopeCan !== "undefined" && activeTeamScopeCan || null;
  const apiFetch3 = typeof apiFetch2 !== "undefined" && apiFetch2 || null;
  const bindDisclosure2 = typeof bindDisclosure !== "undefined" && bindDisclosure || null;
  const bindDismissible2 = typeof bindDismissible !== "undefined" && bindDismissible || null;
  const bindMobileSheet2 = typeof bindMobileSheet !== "undefined" && bindMobileSheet || null;
  const bindOutsideClickClose2 = typeof bindOutsideClickClose !== "undefined" && bindOutsideClickClose || null;
  const bindPressable2 = typeof bindPressable !== "undefined" && bindPressable || null;
  const blurVisibleComposerInputIfMobile2 = typeof blurVisibleComposerInputIfMobile !== "undefined" && blurVisibleComposerInputIfMobile || null;
  const confirmHistAction2 = typeof confirmHistAction !== "undefined" && confirmHistAction || null;
  const confirmKill3 = typeof confirmKill2 !== "undefined" && confirmKill2 || null;
  const copyTextToClipboard2 = typeof copyTextToClipboard !== "undefined" && copyTextToClipboard || null;
  const dispatchMobileMenuAction2 = typeof dispatchMobileMenuAction !== "undefined" && dispatchMobileMenuAction || null;
  const getActiveTab2 = typeof getActiveTab !== "undefined" && getActiveTab || null;
  const getActiveTabId2 = typeof getActiveTabId !== "undefined" && getActiveTabId || null;
  const getAppState2 = typeof getAppState !== "undefined" && getAppState || null;
  const getStarred = typeof _getStarred !== "undefined" && _getStarred || null;
  const historyAddRunToActiveProject = typeof _historyAddRunToActiveProject !== "undefined" && _historyAddRunToActiveProject || null;
  const historyAddRunToProject = typeof _historyAddRunToProject !== "undefined" && _historyAddRunToProject || null;
  const historyEditEntityMetadata = typeof _historyEditEntityMetadata !== "undefined" && _historyEditEntityMetadata || null;
  const historyRelativeTime = typeof _historyRelativeTime !== "undefined" && _historyRelativeTime || null;
  const onUiEvent2 = typeof onUiEvent !== "undefined" && onUiEvent || null;
  const openHistoryCompareLauncher2 = typeof openHistoryCompareLauncher !== "undefined" && openHistoryCompareLauncher || null;
  const openHistoryRunDetails2 = typeof openHistoryRunDetails !== "undefined" && openHistoryRunDetails || null;
  const openHistoryWithFilters2 = typeof openHistoryWithFilters !== "undefined" && openHistoryWithFilters || null;
  const performMobileEditAction2 = typeof performMobileEditAction !== "undefined" && performMobileEditAction || null;
  const resetHistoryMobileFilters3 = typeof resetHistoryMobileFilters2 !== "undefined" && resetHistoryMobileFilters2 || null;
  const restoreHistoryRunIntoTab3 = typeof restoreHistoryRunIntoTab2 !== "undefined" && restoreHistoryRunIntoTab2 || null;
  const setComposerValue2 = typeof setComposerValue !== "undefined" && setComposerValue || null;
  const shareUrl2 = typeof shareUrl !== "undefined" && shareUrl || null;
  const showToast2 = typeof showToast !== "undefined" && showToast || null;
  const toggleStar = typeof _toggleStar !== "undefined" && _toggleStar || null;
  function logMobileChromeError(context, err) {
    if (typeof logClientError2 === "function") logClientError2(context, err);
  }
  function _recentsOpenHistoryCompare(run) {
    const hasImportedHandler = typeof openHistoryCompareLauncher2?.hasHandler === "function" && openHistoryCompareLauncher2.hasHandler();
    const openCompare = hasImportedHandler || typeof openHistoryCompareLauncher2?.hasHandler !== "function" ? openHistoryCompareLauncher2 : null;
    if (typeof openCompare !== "function") return false;
    try {
      const result = openCompare(run);
      return result !== false;
    } catch (err) {
      logMobileChromeError("mobile recents compare unavailable", err);
      return false;
    }
  }
  function _recentsOpenRunDetails(run) {
    const hasImportedHandler = typeof openHistoryRunDetails2?.hasHandler === "function" && openHistoryRunDetails2.hasHandler();
    const openDetails = hasImportedHandler || typeof openHistoryRunDetails2?.hasHandler !== "function" ? openHistoryRunDetails2 : null;
    if (typeof openDetails !== "function") return false;
    try {
      const result = openDetails(run);
      return result !== false;
    } catch (err) {
      logMobileChromeError("mobile recents run details unavailable", err);
      return false;
    }
  }
  const mobileShellChrome = document.getElementById("mobile-shell-chrome");
  const mobileComposer = document.getElementById("mobile-composer");
  const mobileKillBtn = document.getElementById("mobile-kill-btn");
  const statusPillEl = document.getElementById("status");
  const recentPeek = document.getElementById("mobile-recent-peek");
  const recentPeekCount = document.getElementById("mobile-recent-peek-count");
  const recentPeekPreview = document.getElementById("mobile-recent-peek-preview");
  const recentsSheet = document.getElementById("mobile-recents-sheet");
  const recentsSheetScrim = document.getElementById("mobile-recents-sheet-scrim");
  const recentsSheetClearBtn = document.getElementById("mobile-recents-clear");
  const recentsSheetSearch = document.getElementById("mobile-recents-search");
  const recentsPagination = document.getElementById("mobile-recents-pagination");
  const recentsPaginationSummary = document.getElementById("mobile-recents-pagination-summary");
  const recentsPaginationControls = document.getElementById("mobile-recents-pagination-controls");
  const recentsSheetList = document.getElementById("mobile-recents-list");
  const menuSheet = document.getElementById("mobile-menu-sheet");
  const menuSheetScrim = document.getElementById("mobile-menu-sheet-scrim");
  const menuLnState = document.getElementById("mobile-menu-ln-state");
  const menuTsState = document.getElementById("mobile-menu-ts-state");
  const menuWorkflowsCount = document.getElementById("mobile-menu-workflows-count");
  const menuSchedulesCount = document.getElementById("mobile-menu-schedules-count");
  const menuWatchersCount = document.getElementById("mobile-menu-watchers-count");
  const menuHistoryCount = document.getElementById("mobile-menu-history-count");
  const menuAtlasHint = document.getElementById("mobile-menu-atlas-hint");
  const menuFilesHint = document.getElementById("mobile-menu-files-hint");
  const menuProjectHint = document.getElementById("mobile-menu-project-hint");
  const menuThemeHint = document.getElementById("mobile-menu-theme-hint");
  const kbHelper = document.getElementById("mobile-kb-helper");
  let progressBar = null;
  function ensureChromeMounts() {
    if (!mobileShellChrome) return;
    if (!progressBar) {
      progressBar = document.createElement("div");
      progressBar.id = "mobile-progress-bar";
      progressBar.className = "shell-progress-bar u-hidden";
      mobileShellChrome.appendChild(progressBar);
    }
  }
  ensureChromeMounts();
  const show = (el) => el && el.classList && el.classList.remove("u-hidden");
  const hide = (el) => el && el.classList && el.classList.add("u-hidden");
  const isRunning = () => !!(statusPillEl && statusPillEl.classList && statusPillEl.classList.contains("running"));
  const STATUS_MONITOR_PEEK_PULSE_KEY = "status_monitor_mobile_peek_seen";
  let _statusMonitorPeekHoldUntil = 0;
  let _statusMonitorPeekTimer = 0;
  function syncRunState() {
    const running = isRunning();
    if (running) {
      show(progressBar);
      if (mobileComposer && mobileComposer.classList) mobileComposer.classList.add("is-running");
    } else {
      hide(progressBar);
      if (mobileComposer && mobileComposer.classList) mobileComposer.classList.remove("is-running");
    }
    if (statusPillEl && statusPillEl.classList && document.body.classList.contains("mobile-terminal-mode")) {
      if (statusPillEl.classList.contains("killed")) statusPillEl.textContent = "KILLED";
      else if (statusPillEl.classList.contains("fail")) statusPillEl.textContent = "FAILED";
    }
  }
  if (mobileKillBtn) {
    mobileKillBtn.addEventListener("click", () => {
      const tabId = typeof getActiveTabId2 === "function" ? getActiveTabId2() : null;
      if (tabId && typeof confirmKill3 === "function") confirmKill3(tabId);
    });
  }
  if (typeof onUiEvent2 === "function") {
    onUiEvent2("app:status-changed", () => syncRunState());
  }
  syncRunState();
  const runningIndicatorDisabled = (() => {
    try {
      const q = typeof location !== "undefined" && location.search ? location.search : "";
      return /[?&]ri=(?:off|0)\b/.test(q);
    } catch (_) {
      return false;
    }
  })();
  const tabsBarEl = runningIndicatorDisabled ? null : document.getElementById("tabs-bar");
  let mobileRunningIndicatorPromise = null;
  function mobileRunningIndicatorActive() {
    return !!(document.body && document.body.classList.contains("mobile-terminal-mode"));
  }
  function ensureMobileRunningIndicator() {
    if (!tabsBarEl || typeof tabsBarEl.isConnected === "boolean" && !tabsBarEl.isConnected || !mobileRunningIndicatorActive() || typeof loadMobileRunningIndicator !== "function") return null;
    if (mobileRunningIndicatorPromise) return mobileRunningIndicatorPromise;
    mobileRunningIndicatorPromise = loadMobileRunningIndicator().then((indicator) => {
      indicator?.create?.({
        tabsBarEl,
        terminalBarEl: tabsBarEl.closest(".terminal-bar")
      });
    }).catch((err) => {
      mobileRunningIndicatorPromise = null;
      logMobileChromeError("failed to load mobile running indicator", err);
    });
    return mobileRunningIndicatorPromise;
  }
  ensureMobileRunningIndicator();
  if (tabsBarEl && typeof document.addEventListener === "function") {
    document.addEventListener("app:mobile-terminal-mode-changed", (event) => {
      if (event?.detail?.active) ensureMobileRunningIndicator();
    });
  }
  function setActionHint(el, text) {
    if (el) el.textContent = text || "";
  }
  function setTogglePressed(labelEl, value) {
    if (!labelEl) return;
    const btn = labelEl.closest("button[data-menu-action]");
    if (!btn) return;
    const normalized = typeof value === "string" ? value.trim().toLowerCase() : "";
    const on = normalized && normalized !== "off";
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  }
  function refreshMenuStateHints() {
    const cls = document.body && document.body.classList || null;
    const lnValue = cls && cls.contains("ln-on") ? "on" : "off";
    let tsValue = "off";
    if (cls && cls.contains("ts-elapsed")) tsValue = "elapsed";
    else if (cls && cls.contains("ts-clock")) tsValue = "clock";
    setActionHint(menuLnState, lnValue);
    setTogglePressed(menuLnState, lnValue);
    setActionHint(menuTsState, tsValue);
    setTogglePressed(menuTsState, tsValue);
    menuSheet?.querySelectorAll('[data-menu-action="ts-set"]').forEach((btn) => {
      const isActive = btn.dataset.tsMode === tsValue;
      btn.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  }
  function refreshWorkflowsCount(items) {
    if (!menuWorkflowsCount) return;
    const list = Array.isArray(items) ? items : [];
    menuWorkflowsCount.textContent = list.length ? `${list.length} saved` : "";
  }
  function setSavedCount(el, count) {
    if (!el) return;
    const total = Math.max(0, Number(count || 0));
    el.textContent = total > 0 ? `${total} saved` : "";
  }
  function pluralCount(count, singular, plural = `${singular}s`) {
    const total = Math.max(0, Number(count || 0));
    if (!total) return "";
    return `${total} ${total === 1 ? singular : plural}`;
  }
  let schedulesCountRequestSeq = 0;
  function refreshSchedulesCount(items = null) {
    if (!menuSchedulesCount) return;
    if (Array.isArray(items)) {
      setSavedCount(menuSchedulesCount, items.length);
      return;
    }
    if (typeof apiFetch3 !== "function") return;
    const requestSeq = ++schedulesCountRequestSeq;
    apiFetch3("/schedules", { cache: "no-store" }).then((resp) => resp && resp.ok === false ? Promise.reject(new Error(`HTTP ${resp.status}`)) : resp.json()).then((data) => {
      if (requestSeq !== schedulesCountRequestSeq) return;
      setSavedCount(menuSchedulesCount, Array.isArray(data?.schedules) ? data.schedules.length : 0);
    }).catch((err) => {
      logMobileChromeError("failed to load schedules count for mobile menu", err);
    });
  }
  let watchersCountRequestSeq = 0;
  function refreshWatchersCount(items = null) {
    if (!menuWatchersCount) return;
    if (Array.isArray(items)) {
      setSavedCount(menuWatchersCount, items.length);
      return;
    }
    if (typeof apiFetch3 !== "function") return;
    const requestSeq = ++watchersCountRequestSeq;
    apiFetch3("/watchers", { cache: "no-store" }).then((resp) => resp && resp.ok === false ? Promise.reject(new Error(`HTTP ${resp.status}`)) : resp.json()).then((data) => {
      if (requestSeq !== watchersCountRequestSeq) return;
      setSavedCount(menuWatchersCount, Array.isArray(data?.watchers) ? data.watchers.length : 0);
    }).catch((err) => {
      logMobileChromeError("failed to load watchers count for mobile menu", err);
    });
  }
  let historyCountRequestSeq = 0;
  function setMenuHistoryCount(count) {
    const total = Number(count || 0);
    menuHistoryCount.textContent = total > 0 ? `${total} saved` : "";
  }
  function _recentsTotalCountFromCache() {
    if (!_recentsLoaded) return null;
    const total = Number(_recentsPaging.totalCount || 0);
    return Number.isFinite(total) ? Math.max(0, total) : 0;
  }
  function refreshHistoryCount() {
    if (!menuHistoryCount) return;
    const runs = readCmdHistory();
    setMenuHistoryCount(runs.length);
    const requestSeq = ++historyCountRequestSeq;
    if (typeof apiFetch3 !== "function") return;
    apiFetch3("/history", { cache: "no-store" }).then((resp) => resp && resp.ok === false ? Promise.reject(new Error(`HTTP ${resp.status}`)) : resp.json()).then((data) => {
      if (requestSeq !== historyCountRequestSeq) return;
      const total = Number(data?.total_count ?? data?.items?.length ?? data?.runs?.length ?? 0);
      setMenuHistoryCount(Number.isFinite(total) ? total : 0);
    }).catch((err) => {
      logMobileChromeError("failed to load history count for mobile menu", err);
    });
  }
  let atlasHintRequestSeq = 0;
  function refreshAtlasHint() {
    if (!menuAtlasHint || typeof apiFetch3 !== "function") return;
    const requestSeq = ++atlasHintRequestSeq;
    apiFetch3("/atlas?orphan_filter=hide&suppression_filter=hide", { cache: "no-store" }).then((resp) => resp && resp.ok === false ? Promise.reject(new Error(`HTTP ${resp.status}`)) : resp.json()).then((data) => {
      if (requestSeq !== atlasHintRequestSeq) return;
      const total = Math.max(0, Number(data?.total || 0));
      const findings = Math.max(0, Number(data?.findings || 0));
      menuAtlasHint.textContent = total ? pluralCount(total, "entity", "entities") : pluralCount(findings, "finding");
    }).catch((err) => {
      logMobileChromeError("failed to load Atlas count for mobile menu", err);
    });
  }
  let filesHintRequestSeq = 0;
  function refreshFilesHint() {
    if (!menuFilesHint || typeof apiFetch3 !== "function") return;
    const requestSeq = ++filesHintRequestSeq;
    apiFetch3("/workspace/files", { cache: "no-store" }).then((resp) => resp && resp.ok === false ? Promise.reject(new Error(`HTTP ${resp.status}`)) : resp.json()).then((data) => {
      if (requestSeq !== filesHintRequestSeq) return;
      const usageCount = Number(data?.usage?.file_count);
      const files = Number.isFinite(usageCount) ? usageCount : Array.isArray(data?.files) ? data.files.length : 0;
      menuFilesHint.textContent = pluralCount(files, "file");
    }).catch((err) => {
      logMobileChromeError("failed to load Files count for mobile menu", err);
    });
  }
  function _projectHintName(project) {
    if (!project || typeof project !== "object") return "";
    return String(project.name || project.slug || project.id || "").trim();
  }
  function refreshProjectHint(project) {
    if (!menuProjectHint) return;
    const current = project || (typeof getActiveProjectContext === "function" ? getActiveProjectContext() : null);
    const name = _projectHintName(current);
    menuProjectHint.textContent = name;
    menuProjectHint.title = name ? `Active project: ${name}` : "";
  }
  function refreshProjectHintFromServer() {
    refreshProjectHint();
    if (typeof refreshActiveProjectContext !== "function") return;
    refreshActiveProjectContext().then((project) => refreshProjectHint(project)).catch((err) => {
      logMobileChromeError("failed to load active project for mobile menu", err);
    });
  }
  function refreshThemeHint() {
    if (!menuThemeHint) return;
    const name = document.body && document.body.dataset && document.body.dataset.theme || "";
    menuThemeHint.textContent = name;
  }
  const tsToggleBtn = menuSheet?.querySelector('[data-menu-action="ts-toggle"]');
  const tsSubmenuEl = document.getElementById("mobile-menu-ts-submenu");
  const tsDisclosure = tsToggleBtn ? bindDisclosure2(tsToggleBtn, {
    panel: tsSubmenuEl,
    openClass: null,
    hiddenClass: "u-hidden"
  }) : null;
  function openMenuSheet() {
    refreshMenuStateHints();
    refreshThemeHint();
    refreshHistoryCount();
    refreshAtlasHint();
    refreshFilesHint();
    refreshSchedulesCount();
    refreshWatchersCount();
    refreshProjectHintFromServer();
    tsDisclosure?.close();
    show(menuSheetScrim);
    show(menuSheet);
  }
  function closeMenuSheet() {
    hide(menuSheet);
    hide(menuSheetScrim);
  }
  function isMenuSheetOpen() {
    return !!(menuSheet && menuSheet.classList && !menuSheet.classList.contains("u-hidden"));
  }
  if (typeof onUiEvent2 === "function") {
    onUiEvent2("app:mobile-menu-show", openMenuSheet);
    onUiEvent2("app:mobile-menu-hide", closeMenuSheet);
  }
  function openMobileHistorySurface() {
    if (typeof resetHistoryMobileFilters3 === "function") {
      resetHistoryMobileFilters3();
    }
    if (typeof openHistoryWithFilters2 === "function") {
      openHistoryWithFilters2();
    } else if (typeof dispatchMobileMenuAction2 === "function") {
      dispatchMobileMenuAction2("history", null);
    } else {
      showRecentsSheet();
    }
  }
  menuSheet?.querySelectorAll("button[data-menu-action]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const action = btn.dataset.menuAction;
      if (action === "history") {
        e.stopImmediatePropagation();
        closeMenuSheet();
        openMobileHistorySurface();
      }
    }, true);
  });
  if (typeof bindDismissible2 === "function") {
    bindDismissible2(menuSheet, {
      level: "sheet",
      isOpen: isMenuSheetOpen,
      onClose: closeMenuSheet,
      backdropEl: menuSheetScrim
    });
  }
  function readCmdHistory() {
    const h = typeof getAppState2 === "function" ? getAppState2().recentPreviewHistory : null;
    return Array.isArray(h) ? h : [];
  }
  function _prefersReducedMotion() {
    try {
      return !!(global.matchMedia && global.matchMedia("(prefers-reduced-motion: reduce)").matches);
    } catch (_) {
      return false;
    }
  }
  function _formatPeekElapsed(runStart) {
    const start = Number(runStart);
    if (!Number.isFinite(start) || start <= 0) return "";
    const seconds = Math.max(0, Math.floor((Date.now() - start) / 1e3));
    const minutes = Math.floor(seconds / 60);
    const remainder = String(seconds % 60).padStart(2, "0");
    return `${minutes}:${remainder}`;
  }
  function _syncStatusMonitorPeekTimer(activeRunning) {
    if (activeRunning) {
      if (!_statusMonitorPeekTimer) {
        _statusMonitorPeekTimer = window.setInterval(() => {
          try {
            renderRecentPeek();
          } catch (_) {
          }
        }, 1e3);
      }
      return;
    }
    if (_statusMonitorPeekTimer) {
      window.clearInterval(_statusMonitorPeekTimer);
      _statusMonitorPeekTimer = 0;
    }
  }
  function renderRecentPeek() {
    if (!recentPeek) return;
    const activeTab = typeof getActiveTab2 === "function" ? getActiveTab2() : null;
    const activeRunning = !!(activeTab && activeTab.st === "running");
    _syncStatusMonitorPeekTimer(activeRunning);
    const holdStatusMonitor = !activeRunning && _statusMonitorPeekHoldUntil && Date.now() < _statusMonitorPeekHoldUntil;
    if (activeRunning || holdStatusMonitor) {
      recentPeek.dataset.peekMode = "status-monitor";
      recentPeek.setAttribute("aria-label", "Open Status Monitor");
      const elapsed = activeRunning ? _formatPeekElapsed(activeTab.runStart) : "";
      if (recentPeekCount) recentPeekCount.textContent = activeRunning ? elapsed || "live" : "done";
      if (recentPeekPreview) {
        recentPeekPreview.textContent = activeRunning ? String(activeTab.command || "active command") : "final state available";
      }
      const label2 = recentPeek.querySelector(".recent-peek-label");
      if (label2) label2.textContent = "Status Monitor";
      show(recentPeek);
      if (activeRunning && !_prefersReducedMotion()) {
        try {
          if (sessionStorage.getItem(STATUS_MONITOR_PEEK_PULSE_KEY) !== "1") {
            sessionStorage.setItem(STATUS_MONITOR_PEEK_PULSE_KEY, "1");
            recentPeek.classList.add("recent-peek-status-monitor-wiggle");
            window.setTimeout(() => recentPeek.classList.remove("recent-peek-status-monitor-wiggle"), 1900);
          }
        } catch (_) {
          if (recentPeek.dataset.statusMonitorWiggled !== "1") {
            recentPeek.dataset.statusMonitorWiggled = "1";
            recentPeek.classList.add("recent-peek-status-monitor-wiggle");
            window.setTimeout(() => recentPeek.classList.remove("recent-peek-status-monitor-wiggle"), 1900);
          }
        }
      }
      return;
    }
    recentPeek.dataset.peekMode = "recents";
    recentPeek.setAttribute("aria-label", "Show recent commands");
    const label = recentPeek.querySelector(".recent-peek-label");
    if (label) label.textContent = "Recent";
    const items = readCmdHistory();
    if (!items.length) {
      hide(recentPeek);
      return;
    }
    if (recentPeekCount) recentPeekCount.textContent = String(items.length);
    if (recentPeekPreview) recentPeekPreview.textContent = items.slice(0, 3).join(" · ");
    show(recentPeek);
  }
  let _recentsItems = [];
  let _recentsSearchQuery = "";
  let _recentsLoaded = false;
  let _recentsFetchInFlight = null;
  let _recentsRequestSeq = 0;
  const _recentsFilterState = { type: "all", root: "", exit: "all", date: "all", starred: false };
  const _recentsPaging = {
    page: 1,
    pageSize: getAppConfig?.() && getAppConfig().history_panel_limit ? Math.max(1, Number(getAppConfig().history_panel_limit) || 50) : 50,
    totalCount: 0,
    pageCount: 0,
    hasPrev: false,
    hasNext: false
  };
  function _recentsParseDate(iso) {
    if (!iso) return null;
    try {
      const d = new Date(iso);
      return Number.isNaN(d.getTime()) ? null : d;
    } catch (_) {
      return null;
    }
  }
  function _recentsFiltersActiveCount() {
    let n = 0;
    if (_recentsFilterState.type !== "all") n++;
    if (_recentsFilterState.root.trim()) n++;
    if (_recentsFilterState.exit !== "all") n++;
    if (_recentsFilterState.date !== "all") n++;
    if (_recentsFilterState.starred) n++;
    return n;
  }
  function _recentsStarred() {
    try {
      if (typeof getStarred === "function") return getStarred();
    } catch (_) {
    }
    return /* @__PURE__ */ new Set();
  }
  function _recentsHasActiveFilters() {
    return Boolean(
      _recentsSearchQuery.trim() || _recentsFilterState.type !== "all" || _recentsFilterState.root.trim() || _recentsFilterState.exit !== "all" || _recentsFilterState.date !== "all" || _recentsFilterState.starred
    );
  }
  function _recentsBuildHistoryRequestUrl() {
    const params = new URLSearchParams();
    params.set("page", String(_recentsPaging.page || 1));
    params.set("page_size", String(_recentsPaging.pageSize || 1));
    params.set("include_total", "1");
    if (_recentsFilterState.type !== "all") params.set("type", _recentsFilterState.type);
    if (_recentsSearchQuery.trim()) params.set("q", _recentsSearchQuery.trim());
    if (_recentsFilterState.root.trim()) params.set("command_root", _recentsFilterState.root.trim());
    if (_recentsFilterState.exit === "success") params.set("exit_code", "0");
    else if (_recentsFilterState.exit === "failed") params.set("exit_code", "nonzero");
    if (_recentsFilterState.date === "today") params.set("date_range", "24h");
    else if (_recentsFilterState.date === "week") params.set("date_range", "7d");
    if (_recentsFilterState.starred) params.set("starred_only", "1");
    const query = params.toString();
    return query ? `/history?${query}` : "/history";
  }
  function _recentsSetPage(nextPage, { refresh = true } = {}) {
    _recentsPaging.page = Math.max(1, Number(nextPage) || 1);
    if (refresh) _recentsRefresh();
  }
  function _recentsRenderPagination(visibleCount = 0) {
    if (!recentsPagination || !recentsPaginationSummary || !recentsPaginationControls) return;
    const { page, pageSize, totalCount, pageCount } = _recentsPaging;
    const totalLabel = _recentsFilterState.type === "runs" ? totalCount === 1 ? "stored run" : "stored runs" : _recentsFilterState.type === "snapshots" ? totalCount === 1 ? "stored snapshot" : "stored snapshots" : totalCount === 1 ? "stored item" : "stored items";
    if (totalCount > 0) {
      const start = (page - 1) * pageSize + 1;
      const count = Math.max(0, Number(visibleCount) || 0);
      const end = count > 0 ? Math.min(totalCount, start + count - 1) : start;
      recentsPaginationSummary.textContent = `Showing ${start}-${end} of ${totalCount} ${totalLabel}`;
    } else {
      recentsPaginationSummary.textContent = `Showing 0 of 0 ${totalLabel}`;
    }
    recentsPaginationControls.replaceChildren();
    const prevPage = page > 1 ? page - 1 : 1;
    const prevBtn = document.createElement("button");
    prevBtn.type = "button";
    prevBtn.className = "btn btn-secondary btn-compact history-pagination-chevron";
    prevBtn.textContent = "‹ Prev";
    prevBtn.disabled = page <= 1;
    prevBtn.setAttribute("aria-label", "Previous page");
    prevBtn.addEventListener("click", () => _recentsSetPage(prevPage));
    recentsPaginationControls.appendChild(prevBtn);
    const pageLabel = document.createElement("span");
    pageLabel.className = "history-pagination-status";
    pageLabel.textContent = `Page ${pageCount > 0 ? page : 0} of ${pageCount}`;
    pageLabel.setAttribute("aria-live", "polite");
    recentsPaginationControls.appendChild(pageLabel);
    const nextPage = pageCount > page ? page + 1 : page;
    const nextBtn = document.createElement("button");
    nextBtn.type = "button";
    nextBtn.className = "btn btn-secondary btn-compact history-pagination-chevron";
    nextBtn.textContent = "Next ›";
    nextBtn.disabled = page >= pageCount;
    nextBtn.setAttribute("aria-label", "Next page");
    nextBtn.addEventListener("click", () => _recentsSetPage(nextPage));
    recentsPaginationControls.appendChild(nextBtn);
    recentsPagination.classList.remove("u-hidden");
  }
  function _recentsMakeAction(label, handler, role = "secondary") {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `sheet-item-action btn btn-${role} btn-compact`;
    btn.textContent = label;
    bindPressable2(btn, {
      clearPressStyle: true,
      onActivate: (e) => {
        e.stopPropagation();
        try {
          handler();
        } catch (_) {
        }
      }
    });
    return btn;
  }
  function _recentsCloseActionMenus(except = null) {
    recentsSheetList?.querySelectorAll(".sheet-item-action-menu-wrap.open").forEach((wrap) => {
      if (except && wrap === except) return;
      wrap.classList.remove("open");
      wrap.querySelector(".sheet-item-action-menu-trigger")?.setAttribute("aria-expanded", "false");
      _recentsResetActionMenuPosition(wrap);
    });
  }
  function _recentsResetActionMenuPosition(wrap) {
    const menu = wrap?.querySelector?.(".sheet-item-action-menu");
    if (!menu) return;
    menu.style.position = "";
    menu.style.left = "";
    menu.style.top = "";
    menu.style.right = "";
    menu.style.bottom = "";
    menu.style.width = "";
    menu.style.maxHeight = "";
    menu.style.overflowY = "";
    wrap.classList.add("save-menu-down");
  }
  function _recentsPositionActionMenu(wrap) {
    const trigger = wrap?.querySelector?.(".sheet-item-action-menu-trigger");
    const menu = wrap?.querySelector?.(".sheet-item-action-menu");
    if (!trigger || !menu || typeof trigger.getBoundingClientRect !== "function") return;
    const triggerRect = trigger.getBoundingClientRect();
    const sheetRect = recentsSheet?.getBoundingClientRect?.();
    const viewportHeight = typeof window !== "undefined" ? window.innerHeight : document.documentElement.clientHeight;
    const gutter = 8;
    const lowerBound = Math.min(viewportHeight || 0, sheetRect?.bottom || viewportHeight || 0) - gutter;
    const upperBound = Math.max(0, sheetRect?.top || 0) + gutter;
    const spaceBelow = Math.max(0, lowerBound - triggerRect.bottom);
    const spaceAbove = Math.max(0, triggerRect.top - upperBound);
    const viewportWidth = typeof window !== "undefined" ? window.innerWidth : document.documentElement.clientWidth;
    const menuWidth = Math.max(190, menu.offsetWidth || 190);
    const menuHeight = Math.max(1, menu.scrollHeight || menu.offsetHeight || 1);
    const openDown = spaceBelow >= menuHeight || spaceBelow >= spaceAbove;
    wrap.classList.toggle("save-menu-down", openDown);
    const availableSpace = openDown ? spaceBelow : spaceAbove;
    const left = Math.min(
      Math.max(gutter, triggerRect.right - menuWidth),
      Math.max(gutter, (viewportWidth || menuWidth) - menuWidth - gutter)
    );
    const top = openDown ? triggerRect.bottom + 4 : Math.max(gutter, triggerRect.top - Math.min(menuHeight, Math.max(44, availableSpace)) - 4);
    menu.style.position = "fixed";
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
    menu.style.right = "auto";
    menu.style.bottom = "auto";
    menu.style.width = `${menuWidth}px`;
    if (menuHeight > availableSpace && availableSpace > 0) {
      menu.style.maxHeight = `${Math.max(44, availableSpace)}px`;
      menu.style.overflowY = "auto";
    } else {
      menu.style.maxHeight = "";
      menu.style.overflowY = "";
    }
  }
  function _recentsCopyCommand(run) {
    const command = run?.command || "";
    if (typeof copyTextToClipboard2 !== "function") return;
    copyTextToClipboard2(command).then(() => showToast2 && showToast2("Command copied")).catch(() => showToast2 && showToast2("Failed to copy command", "error"));
  }
  function _recentsCanManageHistory() {
    return typeof activeTeamScopeCan2 === "function" ? activeTeamScopeCan2("manage_history") : true;
  }
  function _recentsCanMutateProjects() {
    return typeof activeTeamScopeCan2 === "function" ? activeTeamScopeCan2("mutate_projects") : true;
  }
  function _recentsRunActionMenu(run) {
    const wrap = document.createElement("div");
    wrap.className = "sheet-item-action-menu-wrap save-menu-wrap save-menu-down";
    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "sheet-item-action sheet-item-action-menu-trigger btn btn-secondary btn-compact";
    trigger.textContent = "more";
    trigger.setAttribute("aria-label", "More run actions");
    trigger.setAttribute("aria-haspopup", "menu");
    trigger.setAttribute("aria-expanded", "false");
    const menu = document.createElement("div");
    menu.className = "sheet-item-action-menu save-menu dropdown-surface";
    menu.setAttribute("role", "menu");
    const addItem = (label, handler) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "dropdown-item dropdown-item-compact";
      item.setAttribute("role", "menuitem");
      item.textContent = label;
      item.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        _recentsCloseActionMenus();
        handler();
      });
      menu.appendChild(item);
    };
    addItem("permalink", () => {
      if (!run.id) return;
      const url = `${location.origin}/history/${run.id}`;
      if (typeof shareUrl2 === "function") {
        shareUrl2(url).catch(() => showToast2 && showToast2("Share failed", "error"));
      }
    });
    addItem("compare", () => {
      if (_recentsOpenHistoryCompare(run)) {
        closeRecentsSheet();
      } else if (showToast2) {
        showToast2("Run comparison is not available.", "error");
      }
    });
    if (_recentsCanManageHistory()) {
      addItem("edit", () => {
        if (typeof historyEditEntityMetadata === "function") historyEditEntityMetadata("run", run);
      });
    }
    if (_recentsCanMutateProjects()) {
      addItem("add to active project", () => {
        if (typeof historyAddRunToActiveProject === "function") {
          historyAddRunToActiveProject(run).catch(() => showToast2 && showToast2("Failed to add run to active project", "error"));
        }
      });
      addItem("add to project", () => {
        if (typeof historyAddRunToProject === "function") {
          historyAddRunToProject(run).catch(() => showToast2 && showToast2("Failed to add run to project", "error"));
        }
      });
    }
    addItem("copy run id", () => {
      if (typeof copyTextToClipboard2 === "function") {
        copyTextToClipboard2(run.id).then(() => showToast2 && showToast2("Run ID copied")).catch(() => showToast2 && showToast2("Failed to copy run ID", "error"));
      }
    });
    if (_recentsCanManageHistory()) {
      addItem("delete", () => {
        if (run.id && typeof confirmHistAction2 === "function") {
          confirmHistAction2("delete", run.id, run.command, "run");
        }
      });
    }
    bindPressable2(trigger, {
      refocusComposer: false,
      clearPressStyle: true,
      onActivate: (event) => {
        event.preventDefault();
        event.stopPropagation();
        const open = !wrap.classList.contains("open");
        _recentsCloseActionMenus(open ? wrap : null);
        wrap.classList.toggle("open", open);
        trigger.setAttribute("aria-expanded", open ? "true" : "false");
        if (open) {
          _recentsPositionActionMenu(wrap);
        } else {
          _recentsResetActionMenuPosition(wrap);
        }
      }
    });
    wrap.append(trigger, menu);
    return wrap;
  }
  function _recentsMakeKindBadge(kind, label = kind.toUpperCase()) {
    const badge = document.createElement("span");
    const tone = kind === "run" ? "badge-tone-green" : "badge-tone-muted";
    badge.className = `sheet-item-kind sheet-item-kind-${kind} badge ${tone}`;
    badge.textContent = label;
    return badge;
  }
  const RECENTS_GRACEFUL_TERMINATION_EXIT_CODES = /* @__PURE__ */ new Set([-15]);
  function _recentsExitCodeNumber(exitCode) {
    if (exitCode === null || exitCode === void 0 || exitCode === "") return null;
    const number = Number(exitCode);
    return Number.isFinite(number) ? number : null;
  }
  function _recentsIsGracefulTerminationExitCode(exitCode) {
    const code = _recentsExitCodeNumber(exitCode);
    return code !== null && RECENTS_GRACEFUL_TERMINATION_EXIT_CODES.has(code);
  }
  function _recentsIsFailedExitCode(exitCode) {
    const code = _recentsExitCodeNumber(exitCode);
    return code !== null && code !== 0 && !RECENTS_GRACEFUL_TERMINATION_EXIT_CODES.has(code);
  }
  function _recentsExitLabel(exitCode) {
    const code = _recentsExitCodeNumber(exitCode);
    if (code === null) return "—";
    return _recentsIsGracefulTerminationExitCode(code) ? "terminated" : `exit ${code}`;
  }
  function _recentsSnapshotUrl(item) {
    return `${location.origin}/share/${item.id}`;
  }
  function _recentsOpenSnapshot(item) {
    if (!item || !item.id || typeof window === "undefined" || !window || typeof window.open !== "function") return;
    window.open(_recentsSnapshotUrl(item), "_blank", "noopener,noreferrer");
  }
  function _recentsRenderList() {
    if (!recentsSheetList) return;
    recentsSheetList.replaceChildren();
    const starred = _recentsStarred();
    if (!_recentsItems.length) {
      const empty = document.createElement("div");
      empty.className = "sheet-item chrome-row";
      empty.style.color = "var(--muted)";
      empty.style.opacity = "0.7";
      empty.style.justifyContent = "center";
      empty.style.alignItems = "center";
      empty.textContent = _recentsHasActiveFilters() ? "no matches" : _recentsFilterState.type === "snapshots" ? "no snapshots yet" : _recentsFilterState.type === "runs" ? "no recent commands" : "no history yet";
      recentsSheetList.appendChild(empty);
      _recentsRenderPagination(0);
      return;
    }
    _recentsItems.forEach((entryData) => {
      const isRun = entryData.type !== "snapshot";
      const run = isRun ? entryData : null;
      const snapshot = isRun ? null : entryData;
      const cmd = run?.command || "";
      const isStarred = isRun && starred.has(cmd);
      const item = document.createElement("div");
      item.className = "sheet-item chrome-row";
      if (cmd) item.dataset.cmd = cmd;
      const head = document.createElement("div");
      head.className = "sheet-item-head";
      const star = document.createElement("span");
      star.className = "sheet-item-star" + (isStarred ? " starred" : "");
      if (isRun) {
        star.textContent = isStarred ? "★" : "☆";
        star.setAttribute("role", "button");
        star.setAttribute("tabindex", "0");
        const starLabel = isStarred ? "Unstar — stop pinning this command to the top" : "Star — keep this command pinned at the top";
        star.setAttribute("aria-label", starLabel);
        star.title = starLabel;
        bindPressable2(star, {
          refocusComposer: false,
          clearPressStyle: true,
          onActivate: (e) => {
            e.stopPropagation();
            if (typeof toggleStar === "function") {
              try {
                toggleStar(cmd);
              } catch (_) {
              }
            }
            _recentsRenderList();
            if (_recentsFilterState.starred) _recentsRefresh();
          }
        });
      } else {
        star.textContent = "⬚";
        star.setAttribute("aria-hidden", "true");
      }
      const cmdEl = document.createElement("span");
      cmdEl.className = "sheet-item-cmd";
      cmdEl.textContent = isRun ? cmd : snapshot.label || "snapshot";
      head.appendChild(star);
      head.appendChild(cmdEl);
      const meta = document.createElement("div");
      meta.className = "sheet-item-meta";
      meta.appendChild(_recentsMakeKindBadge(isRun ? "run" : "snapshot"));
      const timeEl = document.createElement("span");
      timeEl.className = "sheet-item-time";
      const parsed = _recentsParseDate(isRun ? run.started : snapshot.created);
      const relFn = typeof historyRelativeTime === "function" ? historyRelativeTime : null;
      timeEl.textContent = parsed && relFn ? relFn(parsed) : "";
      if (parsed) timeEl.title = parsed.toLocaleString();
      meta.appendChild(timeEl);
      if (isRun) {
        const exitEl = document.createElement("span");
        const exitCode = run.exit_code ?? null;
        exitEl.className = "sheet-item-exit" + (_recentsIsFailedExitCode(exitCode) ? " nonzero" : "");
        exitEl.textContent = _recentsExitLabel(exitCode);
        meta.appendChild(exitEl);
      }
      const actions = document.createElement("div");
      actions.className = "sheet-item-actions";
      if (isRun) {
        actions.appendChild(_recentsMakeAction("copy command", () => _recentsCopyCommand(run)));
        actions.appendChild(_recentsMakeAction("restore", () => {
          if (typeof restoreHistoryRunIntoTab3 !== "function") return;
          const cmdEl2 = item.querySelector(".sheet-item-cmd");
          if (cmdEl2) cmdEl2.textContent = "loading…";
          restoreHistoryRunIntoTab3(run, { hidePanelOnSuccess: false }).then(() => closeRecentsSheet()).catch(() => {
            if (cmdEl2) cmdEl2.textContent = cmd;
            if (typeof showToast2 === "function") showToast2("Failed to load run");
          });
        }));
        actions.appendChild(_recentsRunActionMenu(run));
      } else {
        actions.appendChild(_recentsMakeAction("open", () => {
          _recentsOpenSnapshot(snapshot);
          closeRecentsSheet();
        }));
        actions.appendChild(_recentsMakeAction("copy link", () => {
          if (typeof shareUrl2 === "function") {
            shareUrl2(_recentsSnapshotUrl(snapshot)).catch(() => showToast2 && showToast2("Share failed", "error"));
          }
        }));
      }
      if (!isRun) {
        if (_recentsCanManageHistory()) {
          actions.appendChild(_recentsMakeAction("delete", () => {
            if (!entryData.id) return;
            if (typeof confirmHistAction2 === "function") {
              confirmHistAction2("delete", entryData.id, snapshot.label, "snapshot");
            }
          }));
        }
      }
      item.appendChild(head);
      item.appendChild(meta);
      item.appendChild(actions);
      item.addEventListener("click", (e) => {
        if (e.target.closest(".sheet-item-action, .sheet-item-star, .sheet-item-action-menu-wrap")) return;
        _recentsCloseActionMenus();
        if (!isRun) {
          _recentsOpenSnapshot(snapshot);
          closeRecentsSheet();
          return;
        }
        if (_recentsOpenRunDetails(run)) {
          closeRecentsSheet();
          return;
        }
        if (typeof setComposerValue2 === "function") setComposerValue2(cmd, cmd.length, cmd.length);
        closeRecentsSheet();
      });
      recentsSheetList.appendChild(item);
    });
    _recentsRenderPagination(_recentsItems.length);
  }
  function _recentsRenderLoading() {
    if (!recentsSheetList) return;
    recentsSheetList.replaceChildren();
    const loading = document.createElement("div");
    loading.className = "sheet-item chrome-row";
    loading.style.color = "var(--muted)";
    loading.style.opacity = "0.7";
    loading.style.justifyContent = "center";
    loading.style.alignItems = "center";
    loading.textContent = "loading history...";
    recentsSheetList.appendChild(loading);
    _recentsRenderPagination(0);
  }
  function _recentsRefresh({ render = true } = {}) {
    if (typeof apiFetch3 !== "function") return Promise.resolve([]);
    const requestUrl = _recentsBuildHistoryRequestUrl();
    const requestSeq = ++_recentsRequestSeq;
    const request = apiFetch3(requestUrl).then((r) => r.json()).then((data) => {
      if (requestSeq !== _recentsRequestSeq) return _recentsItems;
      _recentsPaging.page = Math.max(1, Number(data.page) || _recentsPaging.page || 1);
      _recentsPaging.pageSize = Math.max(1, Number(data.page_size) || _recentsPaging.pageSize || 1);
      _recentsPaging.totalCount = Math.max(0, Number(data.total_count ?? data.items?.length ?? data.runs?.length ?? 0) || 0);
      _recentsPaging.pageCount = Math.max(0, Number(data.page_count) || 0);
      _recentsPaging.hasPrev = !!data.has_prev;
      _recentsPaging.hasNext = !!data.has_next;
      _recentsItems = Array.isArray(data.items) ? data.items : Array.isArray(data.runs) ? data.runs : [];
      _recentsLoaded = true;
      if (render || isRecentsSheetOpen()) _recentsRenderList();
      return _recentsItems;
    }).catch(() => {
      if (requestSeq !== _recentsRequestSeq) return _recentsItems;
      _recentsItems = [];
      _recentsLoaded = false;
      _recentsPaging.totalCount = 0;
      _recentsPaging.pageCount = 0;
      _recentsPaging.hasPrev = false;
      _recentsPaging.hasNext = false;
      if (render || isRecentsSheetOpen()) _recentsRenderList();
      return [];
    });
    _recentsFetchInFlight = request.finally(() => {
      if (_recentsFetchInFlight === request && requestSeq === _recentsRequestSeq) _recentsFetchInFlight = null;
    });
    return _recentsFetchInFlight;
  }
  function _recentsPrefetch() {
    if (_recentsLoaded || _recentsFetchInFlight) return _recentsFetchInFlight || Promise.resolve(_recentsItems);
    return _recentsRefresh({ render: false });
  }
  function showRecentsSheet() {
    if (!recentsSheet) return;
    _recentsSearchQuery = "";
    if (recentsSheetSearch) recentsSheetSearch.value = "";
    if (typeof blurVisibleComposerInputIfMobile2 === "function") {
      try {
        blurVisibleComposerInputIfMobile2();
      } catch (_) {
      }
    }
    _recentsFilterState.type = "all";
    _recentsFilterState.root = "";
    _recentsFilterState.exit = "all";
    _recentsFilterState.date = "all";
    _recentsFilterState.starred = false;
    _recentsPaging.page = 1;
    if (recentsFiltersToggle) recentsFiltersToggle.setAttribute("aria-expanded", "false");
    if (recentsFiltersExpanded) recentsFiltersExpanded.classList.add("u-hidden");
    _recentsSyncFilterUI();
    _recentsRenderLoading();
    show(recentsSheetScrim);
    show(recentsSheet);
    _recentsRefresh();
  }
  function closeRecentsSheet() {
    _closeRecentsDropdowns();
    _recentsCloseActionMenus();
    hide(recentsSheet);
    hide(recentsSheetScrim);
  }
  function isRecentsSheetOpen() {
    return !!(recentsSheet && recentsSheet.classList && !recentsSheet.classList.contains("u-hidden"));
  }
  if (typeof bindDismissible2 === "function") {
    bindDismissible2(recentsSheet, {
      level: "sheet",
      isOpen: isRecentsSheetOpen,
      onClose: closeRecentsSheet,
      backdropEl: recentsSheetScrim
    });
  }
  if (recentsSheetClearBtn) {
    bindPressable2(recentsSheetClearBtn, {
      refocusComposer: false,
      clearPressStyle: true,
      onActivate: () => {
        if (!_recentsCanManageHistory()) return;
        if (typeof confirmHistAction2 === "function") {
          confirmHistAction2("clear");
        }
      }
    });
  }
  if (typeof onUiEvent2 === "function") {
    onUiEvent2("app:history-panel-refreshed", () => {
      if (isRecentsSheetOpen()) _recentsRefresh();
    });
  }
  _recentsPrefetch();
  let _recentsSearchTimer = null;
  recentsSheetSearch?.addEventListener("input", (e) => {
    _recentsSearchQuery = e.target.value || "";
    if (_recentsSearchTimer) clearTimeout(_recentsSearchTimer);
    _recentsSearchTimer = setTimeout(() => {
      _recentsPaging.page = 1;
      _recentsRefresh();
    }, 100);
  });
  recentsSheetList?.addEventListener("touchmove", () => {
    if (recentsSheetSearch && document.activeElement === recentsSheetSearch) {
      recentsSheetSearch.blur();
    }
  }, { passive: true });
  if (typeof bindMobileSheet2 === "function") {
    bindMobileSheet2(recentsSheet, { onClose: closeRecentsSheet });
  }
  const recentsFiltersToggle = document.getElementById("mobile-recents-filters-toggle");
  const recentsFiltersExpanded = document.getElementById("mobile-recents-filters-expanded");
  const recentsFiltersClear = document.getElementById("mobile-recents-filters-clear");
  const recentsFilterRoot = document.getElementById("mobile-recents-filter-root");
  const recentsFilterStarred = recentsSheet?.querySelector('[data-recents-filter="starred"]') || null;
  const recentsDropdowns = Array.from(recentsSheet?.querySelectorAll("[data-recents-dropdown]") || []);
  const recentsChipsEl = document.getElementById("mobile-recents-chips");
  const _dropdownLabels = {
    type: { all: "all", runs: "runs", snapshots: "snapshots" },
    exit: { all: "all", success: "success (0)", failed: "failed" },
    date: { all: "all", today: "today", week: "this week" }
  };
  const _chipLabels = {
    type: { runs: "runs", snapshots: "snapshots" },
    exit: { success: "exit 0", failed: "failed" },
    date: { today: "today", week: "past week" }
  };
  function _recentsResetRunOnlyFilters() {
    _recentsFilterState.root = "";
    _recentsFilterState.exit = "all";
    _recentsFilterState.starred = false;
  }
  function _clearOneFilter(key) {
    if (key === "type") _recentsFilterState.type = "all";
    if (key === "root") _recentsFilterState.root = "";
    if (key === "exit") _recentsFilterState.exit = "all";
    if (key === "date") _recentsFilterState.date = "all";
    if (key === "starred") _recentsFilterState.starred = false;
    _recentsSyncFilterUI();
    _recentsPaging.page = 1;
    _recentsRefresh();
  }
  function _renderRecentsChips() {
    if (!recentsChipsEl) return;
    recentsChipsEl.replaceChildren();
    const push = (key, text) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "filter-chip chip chip-removable";
      chip.dataset.chipKey = key;
      chip.setAttribute("aria-label", `Clear filter ${text}`);
      const label = document.createElement("span");
      label.textContent = text;
      const x = document.createElement("span");
      x.className = "filter-chip-x";
      x.textContent = "×";
      chip.append(label, x);
      bindPressable2(chip, {
        refocusComposer: false,
        clearPressStyle: true,
        onActivate: () => _clearOneFilter(key)
      });
      recentsChipsEl.appendChild(chip);
    };
    const s = _recentsFilterState;
    if (s.type !== "all") push("type", _chipLabels.type[s.type] || s.type);
    if (s.root.trim()) push("root", `command: ${s.root.trim()}`);
    if (s.exit !== "all") push("exit", _chipLabels.exit[s.exit] || s.exit);
    if (s.date !== "all") push("date", _chipLabels.date[s.date] || s.date);
    if (s.starred) push("starred", "starred");
  }
  function _closeRecentsDropdowns(except) {
    recentsDropdowns.forEach((wrap) => {
      if (wrap === except) return;
      wrap.classList.remove("open");
      wrap.querySelector(".sheet-filter-dropdown")?.setAttribute("aria-expanded", "false");
    });
  }
  function _recentsSyncFilterUI() {
    const runOnlyEnabled = _recentsFilterState.type !== "snapshots";
    if (recentsSheetClearBtn) {
      const showClear = runOnlyEnabled && _recentsCanManageHistory();
      recentsSheetClearBtn.classList.toggle("u-hidden", !showClear);
      recentsSheetClearBtn.disabled = !showClear;
    }
    if (recentsFilterRoot) {
      recentsFilterRoot.value = _recentsFilterState.root;
      recentsFilterRoot.closest(".sheet-filter-row")?.classList.toggle("active", !!_recentsFilterState.root.trim());
      recentsFilterRoot.disabled = !runOnlyEnabled;
    }
    recentsDropdowns.forEach((wrap) => {
      const key = wrap.dataset.recentsDropdown;
      const val = _recentsFilterState[key] || "all";
      const labelMap = _dropdownLabels[key] || {};
      const labelEl = wrap.querySelector("[data-dropdown-label]");
      const trigger = wrap.querySelector(".sheet-filter-dropdown");
      if (labelEl) labelEl.textContent = labelMap[val] || val;
      wrap.classList.toggle("active", val !== "all");
      if (trigger) trigger.disabled = !runOnlyEnabled && key === "exit";
      wrap.querySelectorAll("[data-dropdown-value]").forEach((opt) => {
        const active = opt.dataset.dropdownValue === val;
        opt.setAttribute("aria-selected", active ? "true" : "false");
        opt.classList.toggle("dropdown-item-active", active);
      });
    });
    if (recentsFilterStarred) {
      recentsFilterStarred.setAttribute("aria-pressed", _recentsFilterState.starred ? "true" : "false");
      recentsFilterStarred.disabled = !runOnlyEnabled;
    }
    if (recentsFiltersToggle) {
      const count = _recentsFiltersActiveCount();
      const open = recentsFiltersToggle.getAttribute("aria-expanded") === "true";
      const labelEl = recentsFiltersToggle.querySelector(".sheet-filter-toggle-label");
      const text = (open ? "hide filters" : "filters") + (count ? ` (${count})` : "");
      if (labelEl) labelEl.textContent = text;
      else recentsFiltersToggle.textContent = text;
    }
    _renderRecentsChips();
  }
  if (recentsFiltersToggle) {
    bindDisclosure2(recentsFiltersToggle, {
      panel: recentsFiltersExpanded,
      openClass: null,
      hiddenClass: "u-hidden",
      clearPressStyle: true,
      onToggle: (open) => {
        if (!open) _closeRecentsDropdowns();
        _recentsSyncFilterUI();
      }
    });
  }
  let _recentsRootTimer = null;
  recentsFilterRoot?.addEventListener("input", (e) => {
    _recentsFilterState.root = e.target.value || "";
    if (_recentsRootTimer) clearTimeout(_recentsRootTimer);
    _recentsRootTimer = setTimeout(() => {
      _recentsSyncFilterUI();
      _recentsPaging.page = 1;
      _recentsRefresh();
    }, 100);
  });
  recentsDropdowns.forEach((wrap) => {
    const key = wrap.dataset.recentsDropdown;
    const trigger = wrap.querySelector(".sheet-filter-dropdown");
    if (trigger) {
      bindPressable2(trigger, {
        refocusComposer: false,
        clearPressStyle: true,
        onActivate: () => {
          const open = wrap.classList.contains("open");
          _closeRecentsDropdowns(open ? null : wrap);
          wrap.classList.toggle("open", !open);
          trigger.setAttribute("aria-expanded", !open ? "true" : "false");
        }
      });
    }
    wrap.querySelectorAll("[data-dropdown-value]").forEach((opt) => {
      bindPressable2(opt, {
        refocusComposer: false,
        clearPressStyle: true,
        onActivate: () => {
          _recentsFilterState[key] = opt.dataset.dropdownValue;
          if (key === "type" && _recentsFilterState.type === "snapshots") _recentsResetRunOnlyFilters();
          wrap.classList.remove("open");
          trigger?.setAttribute("aria-expanded", "false");
          _recentsSyncFilterUI();
          _recentsPaging.page = 1;
          _recentsRefresh();
        }
      });
    });
  });
  if (recentsSheet && typeof bindOutsideClickClose2 === "function") {
    bindOutsideClickClose2(null, {
      scope: recentsSheet,
      isOpen: () => recentsDropdowns.some((w) => w.classList.contains("open")),
      onClose: () => _closeRecentsDropdowns(),
      exemptSelectors: ["[data-recents-dropdown]"]
    });
  }
  if (recentsFilterStarred) {
    bindPressable2(recentsFilterStarred, {
      refocusComposer: false,
      clearPressStyle: true,
      onActivate: () => {
        _recentsFilterState.starred = !_recentsFilterState.starred;
        _recentsSyncFilterUI();
        _recentsPaging.page = 1;
        _recentsRefresh();
      }
    });
  }
  if (recentsFiltersClear) {
    bindPressable2(recentsFiltersClear, {
      refocusComposer: false,
      clearPressStyle: true,
      onActivate: () => {
        _recentsFilterState.type = "all";
        _recentsFilterState.root = "";
        _recentsFilterState.exit = "all";
        _recentsFilterState.date = "all";
        _recentsFilterState.starred = false;
        _recentsPaging.page = 1;
        _closeRecentsDropdowns();
        _recentsSyncFilterUI();
        _recentsRefresh();
      }
    });
  }
  function openPeekSurface(event) {
    if (event && typeof event.stopPropagation === "function") event.stopPropagation();
    if (recentPeek && recentPeek.dataset.peekMode === "status-monitor") {
      if (typeof openStatusMonitor === "function") void openStatusMonitor({ source: "mobile-peek" });
      return;
    }
    openMobileHistorySurface();
  }
  if (recentPeek) {
    bindPressable2(recentPeek, {
      refocusComposer: false,
      clearPressStyle: true,
      onActivate: openPeekSurface
    });
  }
  if (recentPeek) {
    let peekStartY = null;
    recentPeek.addEventListener("pointerdown", (e) => {
      peekStartY = e.clientY;
    });
    recentPeek.addEventListener("pointermove", (e) => {
      if (peekStartY === null) return;
      const dy = peekStartY - e.clientY;
      if (dy > 8) {
        peekStartY = null;
        openPeekSurface();
      }
    });
    const endPeekDrag = () => {
      peekStartY = null;
    };
    recentPeek.addEventListener("pointerup", endPeekDrag);
    recentPeek.addEventListener("pointercancel", endPeekDrag);
  }
  if (typeof onUiEvent2 === "function") {
    onUiEvent2("app:history-rendered", () => {
      try {
        renderRecentPeek();
      } catch (_) {
      }
      if (isMenuSheetOpen()) {
        try {
          refreshHistoryCount();
        } catch (_) {
        }
      }
    });
    onUiEvent2("app:tab-status-changed", (e) => {
      const activeId = typeof getActiveTabId2 === "function" ? getActiveTabId2() : null;
      const activeTab = typeof getActiveTab2 === "function" ? getActiveTab2() : null;
      const detail = e && e.detail ? e.detail : {};
      const suppressStatusMonitorHold = !!(activeTab && activeTab.suppressStatusMonitorPeekHold);
      if (detail.id === activeId && detail.status && detail.status !== "running" && suppressStatusMonitorHold) {
        _statusMonitorPeekHoldUntil = 0;
      } else if (detail.id === activeId && detail.status && detail.status !== "running") {
        _statusMonitorPeekHoldUntil = Date.now() + 2500;
        window.setTimeout(() => {
          try {
            renderRecentPeek();
          } catch (_) {
          }
        }, 2550);
      }
      try {
        renderRecentPeek();
      } catch (_) {
      }
      if (isMenuSheetOpen()) {
        try {
          refreshHistoryCount();
        } catch (_) {
        }
      }
    });
    onUiEvent2("app:tab-activated", () => {
      _statusMonitorPeekHoldUntil = 0;
      try {
        renderRecentPeek();
      } catch (_) {
      }
    });
  }
  renderRecentPeek();
  if (typeof onUiEvent2 === "function") {
    onUiEvent2("app:workflows-rendered", (e) => {
      try {
        refreshWorkflowsCount(e.detail && e.detail.items);
      } catch (_) {
      }
    });
    onUiEvent2("app:schedules-rendered", (e) => {
      try {
        refreshSchedulesCount(e.detail && e.detail.items);
      } catch (_) {
      }
    });
    onUiEvent2("app:watchers-rendered", (e) => {
      try {
        refreshWatchersCount(e.detail && e.detail.items);
      } catch (_) {
      }
    });
    onUiEvent2("app:active-project-changed", (e) => {
      try {
        refreshProjectHint(e.detail && e.detail.project);
      } catch (_) {
      }
    });
  }
  function syncKbHelper() {
    const open = !!(document.body && document.body.classList && document.body.classList.contains("mobile-keyboard-open"));
    if (open) {
      show(kbHelper);
    } else {
      hide(kbHelper);
    }
  }
  if (typeof onUiEvent2 === "function") {
    onUiEvent2("app:mobile-keyboard-state", () => syncKbHelper());
  }
  syncKbHelper();
  kbHelper?.querySelectorAll("button[data-kb-action]").forEach((btn) => {
    const action = btn.dataset.kbAction;
    const fire = () => {
      if (typeof performMobileEditAction2 === "function") {
        try {
          performMobileEditAction2(action);
        } catch (_) {
        }
      }
    };
    btn.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      fire();
    });
    btn.addEventListener("mousedown", (e) => {
      e.preventDefault();
    });
    btn.addEventListener("click", (e) => {
      e.preventDefault();
    });
  });
  let _touchStartX = null;
  let _touchStartY = null;
  document.addEventListener("touchstart", (e) => {
    if (e.touches.length === 1) {
      _touchStartX = e.touches[0].clientX;
      _touchStartY = e.touches[0].clientY;
    } else {
      _touchStartX = null;
      _touchStartY = null;
    }
  }, { passive: true });
  document.addEventListener("touchmove", (e) => {
    if (!document.body.classList.contains("mobile-terminal-mode")) return;
    if (_touchStartY == null || e.touches.length !== 1) return;
    const dy = e.touches[0].clientY - _touchStartY;
    const dx = e.touches[0].clientX - _touchStartX;
    if (dy === 0) return;
    if (Math.abs(dx) >= Math.abs(dy)) return;
    let el = e.target;
    while (el && el !== document.body && el !== document.documentElement) {
      if (el.scrollHeight > el.clientHeight) {
        const oy = getComputedStyle(el).overflowY;
        if (oy === "auto" || oy === "scroll") {
          if (dy > 0 && el.scrollTop > 0) return;
          if (dy < 0 && el.scrollTop + el.clientHeight < el.scrollHeight) return;
          break;
        }
      }
      el = el.parentElement;
    }
    if (e.cancelable) e.preventDefault();
  }, { passive: false });
})(typeof window !== "undefined" ? window : void 0);
