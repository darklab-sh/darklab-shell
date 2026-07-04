import {
  closeWorkflows
} from "./static-chunk-z6julpv5.351f6d6acdf5.js";
import {
  closeHistoryRunOverlay,
  isHistoryRunOverlayOpen
} from "./static-chunk-su3zfblw.dfaa45e2b263.js";
import {
  activateTab,
  applyShareRedactionDefaultPreference,
  buildPromptLabel,
  clearFaqHash,
  clearTab2 as clearTab,
  closeAtlas,
  closeProjectWorkspace,
  closeTab,
  closeTeamScopeSelector,
  closeWorkspace,
  copyTab,
  createDefaultTabLabel,
  createTab,
  currentPromptWorkspacePath,
  getShareRedactionDefaultPreference,
  hasSecretsHandler,
  hideCommandCatalogOverlay,
  isAtlasOverlayOpen,
  isCommandCatalogOverlayOpen,
  isProjectWorkspaceOpen,
  isTeamScopeSelectorOpen,
  maskSessionToken,
  permalinkTab,
  refreshOptionsSecrets,
  renderThemeSelectionOptions,
  setOverlayActionHandlers,
  setShareRedactionHandlers,
  syncOptionsControls,
  syncThemeSelectionControls,
  updateOptionsSessionTokenStatus
} from "./static-chunk-zq3stbfi.dfa2064403d5.js";
import {
  showToast
} from "./static-chunk-poi5czx6.3f5c94749765.js";
import {
  showConfirm
} from "./static-chunk-4m44pm74.0a8001fa1d52.js";
import {
  blurVisibleComposerInputIfMobile,
  cancelWelcome,
  cmdInput,
  exportedSetMobileKeyboardOpenState,
  exportedShowOptionsOverlay,
  exportedShowThemeOverlay,
  focusAnyComposerInput,
  focusComposerInput,
  focusElement,
  getActiveTab,
  getActiveTabId,
  getAppState,
  getAutocompleteState,
  getComposerInputs,
  getComposerState,
  getComposerValue,
  getTabs,
  getVisibleComposerInput,
  hasComposerPromptHandler,
  hasMobileShellLayoutHandler,
  hideFaqOverlay,
  hideHistoryPanel,
  hideOptionsOverlay,
  hideShortcutsOverlay,
  hideThemeOverlay,
  hideWorkflowsOverlay,
  hideWorkspaceOverlay,
  isFaqOverlayOpen,
  isHistoryPanelOpen,
  isOptionsOverlayOpen,
  isShortcutsOverlayOpen,
  isThemeOverlayOpen,
  isWorkflowsOverlayOpen,
  isWorkspaceOverlayOpen,
  markInteractionSurfaceReady,
  mobileCmdInput,
  mobileComposerRow,
  optionsOverlay,
  refocusComposerAfterAction,
  setAutocompleteState,
  setComposerPromptHandlers,
  setComposerState,
  setComposerValue,
  shellPromptText,
  shellPromptWrap,
  syncComposerSelection,
  syncFocusedComposerState,
  syncShellPrompt,
  themeOverlay,
  themeSelect,
  tsBtn,
  useMobileTerminalViewportMode
} from "./static-chunk-yo5cjr7d.b86e0c93eff0.js";
import {
  getAppConfig
} from "./static-chunk-gwztcp24.e58b5ff85d88.js";
import {
  hasRuntimeHandler,
  logClientError
} from "./static-chunk-2kxtimik.c9801087c7a7.js";

// app/static/js/features/terminal/composer_editing.js
var COMPOSER_EDITING_GLOBAL = typeof window !== "undefined" ? window : globalThis;
function _composerEditingGlobalFunction(name) {
  const fn = COMPOSER_EDITING_GLOBAL?.[name];
  return typeof fn === "function" ? fn : null;
}
function _composerEditingCmdInput() {
  return typeof cmdInput !== "undefined" && cmdInput || (typeof document !== "undefined" ? document.getElementById("cmd") : null);
}
function _composerEditingGetComposerState() {
  if (typeof getComposerState !== "undefined" && typeof getComposerState === "function") {
    return getComposerState();
  }
  const getComposerState2 = _composerEditingGlobalFunction("getComposerState");
  return getComposerState2 ? getComposerState2() : null;
}
function _composerEditingGetComposerValue() {
  if (typeof getComposerValue !== "undefined" && typeof getComposerValue === "function") {
    return getComposerValue();
  }
  const input = _composerEditingCmdInput();
  const getComposerValue2 = _composerEditingGlobalFunction("getComposerValue");
  return getComposerValue2 ? getComposerValue2() : input && input.value || "";
}
function _composerEditingVisibleInput() {
  if (typeof getVisibleComposerInput !== "undefined" && typeof getVisibleComposerInput === "function") {
    return getVisibleComposerInput();
  }
  const getVisibleComposerInput2 = _composerEditingGlobalFunction("getVisibleComposerInput");
  return getVisibleComposerInput2 ? getVisibleComposerInput2() : _composerEditingCmdInput();
}
function _composerEditingSetValue(value, start, end) {
  const setValue = typeof setComposerValue !== "undefined" && setComposerValue || _composerEditingGlobalFunction("setComposerValue");
  if (typeof setValue === "function") setValue(value, start, end);
}
function _composerEditingSyncSelection(start, end, options = {}) {
  const syncSelection = typeof syncComposerSelection !== "undefined" && syncComposerSelection || _composerEditingGlobalFunction("syncComposerSelection");
  if (typeof syncSelection === "function") {
    syncSelection(start, end, options);
    return true;
  }
  return false;
}
function _composerEditingSyncFocusedState(input) {
  const syncFocused = typeof syncFocusedComposerState !== "undefined" && syncFocusedComposerState || _composerEditingGlobalFunction("syncFocusedComposerState");
  if (typeof syncFocused === "function") syncFocused(input);
}
function _composerEditingSyncShellPrompt() {
  const syncPrompt = typeof hasComposerPromptHandler === "function" && hasComposerPromptHandler("syncShellPrompt") ? syncShellPrompt : _composerEditingGlobalFunction("syncShellPrompt");
  if (typeof syncPrompt === "function") syncPrompt();
}
function getComposerStateSnapshot() {
  return _composerEditingGetComposerState();
}
function getCmdSelection(value = null) {
  const composer = getComposerStateSnapshot();
  const input = _composerEditingCmdInput();
  const sourceValue = typeof value === "string" ? value : composer && typeof composer.value === "string" ? composer.value : input && input.value || "";
  let start = composer && typeof composer.selectionStart === "number" ? composer.selectionStart : input && typeof input.selectionStart === "number" ? input.selectionStart : sourceValue.length;
  let end = composer && typeof composer.selectionEnd === "number" ? composer.selectionEnd : input && typeof input.selectionEnd === "number" ? input.selectionEnd : sourceValue.length;
  if (start > end) [start, end] = [end, start];
  return { start, end };
}
function getInputSelection(input, value = input && input.value ? input.value : "") {
  let start = typeof input.selectionStart === "number" ? input.selectionStart : value.length;
  let end = typeof input.selectionEnd === "number" ? input.selectionEnd : value.length;
  if (start > end) [start, end] = [end, start];
  return { start, end };
}
function replaceCmdRange(value, start, end, replacement = "") {
  const nextPos = start + replacement.length;
  _composerEditingSetValue(value.slice(0, start) + replacement + value.slice(end), nextPos, nextPos);
}
function moveCmdCaretByWord(direction) {
  const input = _composerEditingVisibleInput();
  const fallbackInput = _composerEditingCmdInput();
  _composerEditingSyncFocusedState(input);
  const value = _composerEditingGetComposerValue();
  const { start, end } = getCmdSelection(value);
  const next = direction < 0 ? findWordBoundaryLeft(value, start) : findWordBoundaryRight(value, end);
  _composerEditingSyncSelection(next, next, { input });
  if (input && typeof input.setSelectionRange === "function" && input.selectionStart !== next) {
    input.setSelectionRange(next, next);
  } else if (!input && fallbackInput && typeof fallbackInput.setSelectionRange === "function") {
    fallbackInput.setSelectionRange(next, next);
  }
  _composerEditingSyncShellPrompt();
}
function handleComposerWordArrowShortcut(e) {
  if (!e || !e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return false;
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return false;
  e.preventDefault();
  e.stopPropagation();
  moveCmdCaretByWord(e.key === "ArrowLeft" ? -1 : 1);
  return true;
}
function isTerminalWordChar(char) {
  return /[A-Za-z0-9]/.test(char || "");
}
function findWordBoundaryLeft(value, index) {
  let next = Math.max(0, index);
  while (next > 0 && !isTerminalWordChar(value[next - 1])) next--;
  while (next > 0 && isTerminalWordChar(value[next - 1])) next--;
  return next;
}
function findWordBoundaryRight(value, index) {
  let next = Math.min(value.length, index);
  while (next < value.length && !isTerminalWordChar(value[next])) next++;
  while (next < value.length && isTerminalWordChar(value[next])) next++;
  return next;
}
if (typeof window !== "undefined") {
}

// app/static/js/app.js
var importedHideCommandRegistryOverlay;
var importedIsCommandRegistryOverlayOpen;
var APP_GLOBAL = typeof window !== "undefined" ? window : globalThis;
function _appFn(name, imported = null) {
  if (typeof imported === "function") return imported;
  const fn = APP_GLOBAL && APP_GLOBAL[name];
  if (typeof fn === "function") return fn;
  return null;
}
function _appValue(name, imported = void 0) {
  return imported !== void 0 ? imported : APP_GLOBAL ? APP_GLOBAL[name] : void 0;
}
function _appEl(name, imported = void 0) {
  return _appValue(name, imported) || null;
}
function _appConfig() {
  const globalConfig = _appValue("APP_CONFIG");
  if (globalConfig && typeof globalConfig === "object" && !Array.isArray(globalConfig)) {
    return globalConfig;
  }
  const config = _appFn("getAppConfig", getAppConfig)?.();
  return config || {};
}
function _appState() {
  const state = _appFn("getAppState", getAppState)?.();
  return state || _appValue("APP_STATE") || {};
}
function _appTabs() {
  const tabs = _appFn("getTabs", getTabs)?.();
  if (Array.isArray(tabs)) return tabs;
  const state = _appState();
  return Array.isArray(state.tabs) ? state.tabs : [];
}
function _appActiveTabId() {
  const id = _appFn("getActiveTabId", getActiveTabId)?.();
  return id || _appState().activeTabId || null;
}
function _appAutocompleteState() {
  const state = _appFn("getAutocompleteState", getAutocompleteState)?.();
  return state || _appState();
}
var cmdInput2 = _appEl("cmdInput", cmdInput);
var mobileCmdInput2 = _appEl("mobileCmdInput", mobileCmdInput);
var mobileComposerRow2 = _appEl("mobileComposerRow", mobileComposerRow);
var optionsOverlay2 = _appEl("optionsOverlay", optionsOverlay);
var shellPromptText2 = _appEl("shellPromptText", shellPromptText);
var shellPromptWrap2 = _appEl("shellPromptWrap", shellPromptWrap);
var themeOverlay2 = _appEl("themeOverlay", themeOverlay);
var themeSelect2 = _appEl("themeSelect", themeSelect);
var tsBtn2 = _appEl("tsBtn", tsBtn);
var _appSetAutocompleteStateAdapter = (...args) => _appFn("setAutocompleteState", setAutocompleteState)?.(...args);
var _appShowToastAdapter = (...args) => _appFn("showToast", showToast)?.(...args);
var _appBuildPromptLabelAdapter = (...args) => _appFn("buildPromptLabel", buildPromptLabel)?.(...args);
var _appCurrentPromptWorkspacePathAdapter = (...args) => _appFn("currentPromptWorkspacePath", currentPromptWorkspacePath)?.(...args);
var _appGetComposerInputsAdapter = (...args) => _appFn("getComposerInputs", getComposerInputs)?.(...args);
var _appSyncFocusedComposerStateAdapter = (...args) => _appFn("syncFocusedComposerState", syncFocusedComposerState)?.(...args);
var _appGetComposerStateAdapter = (...args) => _appFn("getComposerState", getComposerState)?.(...args);
var _appUseMobileViewportAdapter = (...args) => {
  const fn = typeof hasMobileShellLayoutHandler === "function" && hasMobileShellLayoutHandler("useMobileTerminalViewportMode") ? useMobileTerminalViewportMode : _appFn("useMobileTerminalViewportMode");
  return typeof fn === "function" ? fn(...args) : false;
};
var _appSetMobileKeyboardOpenStateAdapter = (...args) => _appFn("setMobileKeyboardOpenState", exportedSetMobileKeyboardOpenState)?.(...args);
var _appFocusComposerInputAdapter = (...args) => _appFn("focusComposerInput", focusComposerInput)?.(...args);
var _appFocusAnyComposerInputAdapter = (...args) => _appFn("focusAnyComposerInput", focusAnyComposerInput)?.(...args);
var _appIsAtlasOverlayOpenAdapter = (...args) => _appFn("isAtlasOverlayOpen", isAtlasOverlayOpen)?.(...args);
var _appCloseAtlasAdapter = (...args) => _appFn("closeAtlas", closeAtlas)?.(...args);
var _appIsFindingsBoardOpenAdapter = (...args) => _appFn("isFindingsBoardOpen")?.(...args);
var _appCloseFindingsBoardAdapter = (...args) => _appFn("closeFindingsBoard")?.(...args);
var _appIsTeamScopeSelectorOpenAdapter = (...args) => _appFn("isTeamScopeSelectorOpen", isTeamScopeSelectorOpen)?.(...args);
var _appCloseTeamScopeSelectorAdapter = (...args) => _appFn("closeTeamScopeSelector", closeTeamScopeSelector)?.(...args);
var _appIsHistoryRunOverlayOpenAdapter = (...args) => _appFn("isHistoryRunOverlayOpen", isHistoryRunOverlayOpen)?.(...args);
var _appCloseHistoryRunOverlayAdapter = (...args) => _appFn("closeHistoryRunOverlay", closeHistoryRunOverlay)?.(...args);
var _appIsHistoryPanelOpenAdapter = (...args) => _appFn("isHistoryPanelOpen", isHistoryPanelOpen)?.(...args);
var _appHideHistoryPanelAdapter = (...args) => _appFn("hideHistoryPanel", hideHistoryPanel)?.(...args);
var _appIsWorkflowsOverlayOpenAdapter = (...args) => _appFn("isWorkflowsOverlayOpen", isWorkflowsOverlayOpen)?.(...args);
var _appCloseWorkflowsAdapter = (...args) => _appFn("closeWorkflows", closeWorkflows)?.(...args);
var _appHideWorkflowsOverlayAdapter = (...args) => _appFn("hideWorkflowsOverlay", hideWorkflowsOverlay)?.(...args);
var _appIsSchedulesOverlayOpenAdapter = (...args) => _appFn("isSchedulesOverlayOpen")?.(...args);
var _appCloseSchedulesModalAdapter = (...args) => _appFn("closeSchedulesModal")?.(...args);
var _appIsWatchersOverlayOpenAdapter = (...args) => _appFn("isWatchersOverlayOpen")?.(...args);
var _appCloseWatchersModalAdapter = (...args) => _appFn("closeWatchersModal")?.(...args);
var _appIsWorkspaceOverlayOpenAdapter = (...args) => _appFn("isWorkspaceOverlayOpen", isWorkspaceOverlayOpen)?.(...args);
var _appCloseWorkspaceAdapter = (...args) => _appFn("closeWorkspace", closeWorkspace)?.(...args);
var _appHideWorkspaceOverlayAdapter = (...args) => _appFn("hideWorkspaceOverlay", hideWorkspaceOverlay)?.(...args);
var _appIsFaqOverlayOpenAdapter = (...args) => _appFn("isFaqOverlayOpen", isFaqOverlayOpen)?.(...args);
var _appHideFaqOverlayAdapter = (...args) => _appFn("hideFaqOverlay", hideFaqOverlay)?.(...args);
var _appIsThemeOverlayOpenAdapter = (...args) => _appFn("isThemeOverlayOpen", isThemeOverlayOpen)?.(...args);
var _appHideThemeOverlayAdapter = (...args) => _appFn("hideThemeOverlay", hideThemeOverlay)?.(...args);
var _appIsOptionsOverlayOpenAdapter = (...args) => _appFn("isOptionsOverlayOpen", isOptionsOverlayOpen)?.(...args);
var _appHideOptionsOverlayAdapter = (...args) => _appFn("hideOptionsOverlay", hideOptionsOverlay)?.(...args);
var _appIsShortcutsOverlayOpenAdapter = (...args) => _appFn("isShortcutsOverlayOpen", isShortcutsOverlayOpen)?.(...args);
var _appHideShortcutsOverlayAdapter = (...args) => _appFn("hideShortcutsOverlay", hideShortcutsOverlay)?.(...args);
var _appMaskSessionTokenAdapter = (...args) => typeof maskSessionToken === "function" ? maskSessionToken(...args) : void 0;
var _appSyncOptionsControlsAdapter = (...args) => _appFn("syncOptionsControls", syncOptionsControls)?.(...args);
var _appUpdateOptionsSessionTokenStatusAdapter = (...args) => _appFn("_updateOptionsSessionTokenStatus", updateOptionsSessionTokenStatus)?.(...args);
var _appShowOptionsOverlayAdapter = (...args) => _appFn("showOptionsOverlay", exportedShowOptionsOverlay)?.(...args);
var _appMarkInteractionSurfaceReadyAdapter = (...args) => _appFn("markInteractionSurfaceReady", markInteractionSurfaceReady)?.(...args);
var _appLoadOptionsPanelsAdapter = (...args) => _appFn("loadOptionsPanels")?.(...args);
var _appRefreshOptionsSecretsAdapter = (...args) => {
  const fn = typeof hasSecretsHandler === "function" && hasSecretsHandler("refreshOptionsSecrets") && typeof refreshOptionsSecrets === "function" ? refreshOptionsSecrets : _appFn("refreshOptionsSecrets");
  return typeof fn === "function" ? fn(...args) : void 0;
};
var _appRefreshOptionsTeamsAdapter = (...args) => _appFn("refreshOptionsTeams")?.(...args);
var _appRefreshNotificationChannelsAdapter = (...args) => _appFn("refreshNotificationChannels")?.(...args);
var _appLogClientErrorAdapter = (...args) => {
  const bridge = typeof hasRuntimeHandler === "function" && hasRuntimeHandler("logClientError") && typeof logClientError === "function" ? logClientError : null;
  return _appFn("logClientError", bridge)?.(...args);
};
var _appBlurVisibleComposerMobileAdapter = (...args) => _appFn("blurVisibleComposerInputIfMobile", blurVisibleComposerInputIfMobile)?.(...args);
var _appRefocusComposerAdapter = (...args) => _appFn("refocusComposerAfterAction", refocusComposerAfterAction)?.(...args);
var _appRenderThemeSelectionOptionsAdapter = (...args) => _appFn("renderThemeSelectionOptions", renderThemeSelectionOptions)?.(...args);
var _appSyncThemeSelectionControlsAdapter = (...args) => _appFn("syncThemeSelectionControls", syncThemeSelectionControls)?.(...args);
var _appShowThemeOverlayAdapter = (...args) => _appFn("showThemeOverlay", exportedShowThemeOverlay)?.(...args);
var _appFocusElementAdapter = (...args) => _appFn("focusElement", focusElement)?.(...args);
var _appCloseTabAdapter = (...args) => _appFn("closeTab", closeTab)?.(...args);
var _appPermalinkTabAdapter = (...args) => _appFn("permalinkTab", permalinkTab)?.(...args);
var _appCopyTabAdapter = (...args) => _appFn("copyTab", copyTab)?.(...args);
var _appCancelWelcomeAdapter = (...args) => _appFn("cancelWelcome")?.(...args);
var _appGetActiveTabAdapter = (...args) => _appFn("getActiveTab", getActiveTab)?.(...args);
var _appClearTabAdapter = (...args) => _appFn("clearTab", clearTab)?.(...args);
var _appIsStatusMonitorOpenAdapter = (...args) => _appFn("isStatusMonitorOpen")?.(...args);
var _appGetShareRedactionDefaultPreferenceAdapter = (...args) => _appFn("getShareRedactionDefaultPreference", getShareRedactionDefaultPreference)?.(...args);
var _appShowConfirmAdapter = (...args) => _appFn("showConfirm", showConfirm)?.(...args);
var _appApplyShareRedactionDefaultPreferenceAdapter = (...args) => _appFn("applyShareRedactionDefaultPreference", applyShareRedactionDefaultPreference)?.(...args);
var _appGetVisibleComposerInputAdapter = (...args) => _appFn("getVisibleComposerInput", getVisibleComposerInput)?.(...args);
var _appHideAutocompleteAdapter = (...args) => _appFn("acHide")?.(...args);
var _appSyncComposerSelectionAdapter = (...args) => _appFn("syncComposerSelection", syncComposerSelection)?.(...args);
var _appSetComposerStateAdapter = (...args) => _appFn("setComposerState", setComposerState)?.(...args);
var _appSetComposerValueAdapter = (...args) => _appFn("setComposerValue", setComposerValue)?.(...args);
var _appCreateDefaultTabLabelAdapter = (...args) => _appFn("createDefaultTabLabel", createDefaultTabLabel)?.(...args);
var _appCreateTabAdapter = (...args) => _appFn("createTab", createTab)?.(...args);
var _appActivateTabAdapter = (...args) => _appFn("activateTab", activateTab)?.(...args);
var _appClearFaqHashAdapter = (...args) => _appFn("clearFaqHash", clearFaqHash)?.(...args);
var _appHideCommandCatalogOverlayAdapter = (...args) => _appFn("hideCommandCatalogOverlay", hideCommandCatalogOverlay)?.(...args);
var _appHideCommandRegistryOverlayAdapter = (...args) => _appFn("hideCommandRegistryOverlay", importedHideCommandRegistryOverlay)?.(...args);
var _appIsCommandCatalogOverlayOpenAdapter = (...args) => _appFn("isCommandCatalogOverlayOpen", isCommandCatalogOverlayOpen)?.(...args);
var _appIsCommandRegistryOverlayOpenAdapter = (...args) => _appFn("isCommandRegistryOverlayOpen", importedIsCommandRegistryOverlayOpen)?.(...args);
var _defaultDesktopPromptLabel = (() => {
  if (typeof shellPromptWrap2 === "undefined" || !shellPromptWrap2) return "";
  return String(shellPromptWrap2.querySelector(".prompt-prefix")?.textContent || "");
})();
var _defaultMobilePromptLabel = (() => {
  if (typeof mobileComposerRow2 === "undefined" || !mobileComposerRow2) return "$";
  return String(mobileComposerRow2.querySelector(".mobile-prompt-label")?.textContent || "$");
})();
var _composerPromptMode = null;
function _setAutocompleteSuppressInputOnce(value) {
  if (typeof _appSetAutocompleteStateAdapter === "function") _appSetAutocompleteStateAdapter({ suppressInputOnce: !!value });
  if (_appAutocompleteState()) _appAutocompleteState().suppressInputOnce = !!value;
}
function hidePromptUsernameSavedIndicator() {
  return void 0;
}
function showPromptUsernameSavedIndicator() {
  if (typeof _appShowToastAdapter === "function") _appShowToastAdapter("Prompt name saved", "success");
}
function _compactMobileComposerPath(path = "/") {
  const displayPath = String(path || "/").trim() || "/";
  if (displayPath === "/") return "/";
  if (displayPath.length <= 18) return displayPath;
  const parts = displayPath.split("/").filter(Boolean);
  const folder = parts[parts.length - 1] || displayPath.replace(/^\/+/, "") || "/";
  return `.../${folder}`;
}
function _mobileComposerPlaceholder() {
  if (_appConfig().workspace_enabled === true && typeof _appCurrentPromptWorkspacePathAdapter === "function") {
    return `${_compactMobileComposerPath(_appCurrentPromptWorkspacePathAdapter())} · type command`;
  }
  return "Type a command";
}
function _applyComposerPromptMode() {
  const isConfirm = _composerPromptMode === "confirm";
  const defaultPromptLabel = typeof _appBuildPromptLabelAdapter === "function" ? _appBuildPromptLabelAdapter() : _defaultDesktopPromptLabel || "anon@darklab.sh:~ $";
  const desktopLabel = isConfirm ? "[yes/no]:" : defaultPromptLabel;
  const mobileLabel = isConfirm ? "[yes/no]:" : "";
  const promptPrefix = typeof shellPromptWrap2 !== "undefined" && shellPromptWrap2 ? shellPromptWrap2.querySelector(".prompt-prefix") : null;
  if (promptPrefix) promptPrefix.textContent = desktopLabel;
  if (typeof shellPromptWrap2 !== "undefined" && shellPromptWrap2) {
    shellPromptWrap2.classList.toggle("shell-prompt-confirm", isConfirm);
  }
  const mobilePromptLabel = typeof mobileComposerRow2 !== "undefined" && mobileComposerRow2 ? mobileComposerRow2.querySelector(".mobile-prompt-label") : null;
  if (mobilePromptLabel) {
    mobilePromptLabel.textContent = mobileLabel;
    mobilePromptLabel.hidden = !isConfirm;
  }
  if (typeof mobileCmdInput2 !== "undefined" && mobileCmdInput2) {
    mobileCmdInput2.placeholder = isConfirm ? "" : _mobileComposerPlaceholder();
  }
}
function _syncDesktopPromptPrefix() {
  const promptPrefix = typeof shellPromptWrap2 !== "undefined" && shellPromptWrap2 ? shellPromptWrap2.querySelector(".prompt-prefix") : null;
  if (!promptPrefix) return;
  const defaultPromptLabel = typeof _appBuildPromptLabelAdapter === "function" ? _appBuildPromptLabelAdapter() : _defaultDesktopPromptLabel || "anon@darklab.sh:~ $";
  promptPrefix.textContent = _composerPromptMode === "confirm" ? "[yes/no]:" : defaultPromptLabel;
  if (_composerPromptMode !== "confirm" && _appConfig().workspace_enabled === true && typeof mobileCmdInput2 !== "undefined" && mobileCmdInput2) {
    mobileCmdInput2.placeholder = _mobileComposerPlaceholder();
  }
}
function setComposerPromptMode(mode = null) {
  _composerPromptMode = mode === "confirm" ? "confirm" : null;
  if (typeof window !== "undefined") _applyComposerPromptMode();
}
function syncShellPrompt2() {
  if (typeof shellPromptText2 === "undefined" || !shellPromptText2) return;
  _syncDesktopPromptPrefix();
  if (typeof document !== "undefined" && typeof _appSyncFocusedComposerStateAdapter === "function" && typeof _appGetComposerInputsAdapter === "function") {
    const { desktop, mobile } = _appGetComposerInputsAdapter();
    const active = document.activeElement;
    if (active && (active === desktop || active === mobile)) _appSyncFocusedComposerStateAdapter(active);
  }
  const composer = typeof _appGetComposerStateAdapter === "function" ? _appGetComposerStateAdapter() : null;
  const fallbackInput = typeof cmdInput2 !== "undefined" && cmdInput2 ? cmdInput2 : null;
  const value = composer && typeof composer.value === "string" ? composer.value : fallbackInput ? fallbackInput.value || "" : "";
  const len = value.length;
  let start = composer && typeof composer.selectionStart === "number" ? composer.selectionStart : fallbackInput && typeof fallbackInput.selectionStart === "number" ? fallbackInput.selectionStart : len;
  let end = composer && typeof composer.selectionEnd === "number" ? composer.selectionEnd : fallbackInput && typeof fallbackInput.selectionEnd === "number" ? fallbackInput.selectionEnd : len;
  start = Math.max(0, Math.min(start, len));
  end = Math.max(0, Math.min(end, len));
  if (start > end) [start, end] = [end, start];
  if (typeof shellPromptWrap2 !== "undefined" && shellPromptWrap2) {
    shellPromptWrap2.classList.toggle("shell-prompt-empty", len === 0);
    shellPromptWrap2.classList.toggle("shell-prompt-has-value", len > 0);
    shellPromptWrap2.classList.toggle("shell-prompt-has-selection", end > start);
  }
  shellPromptText2.replaceChildren();
  if (!len) return;
  if (start > 0) shellPromptText2.appendChild(document.createTextNode(value.slice(0, start)));
  if (end > start) {
    const sel = document.createElement("span");
    sel.className = "shell-prompt-selection";
    sel.textContent = value.slice(start, end);
    shellPromptText2.appendChild(sel);
  } else {
    if (start < len) {
      const caretChar = document.createElement("span");
      caretChar.className = "shell-caret-char";
      caretChar.setAttribute("aria-hidden", "true");
      caretChar.textContent = value.slice(start, start + 1);
      shellPromptText2.appendChild(caretChar);
      if (start + 1 < len) shellPromptText2.appendChild(document.createTextNode(value.slice(start + 1)));
      return;
    }
    const caret = document.createElement("span");
    caret.className = "shell-inline-caret";
    caret.setAttribute("aria-hidden", "true");
    caret.textContent = "";
    shellPromptText2.appendChild(caret);
  }
  if (end < len) shellPromptText2.appendChild(document.createTextNode(value.slice(end)));
}
function focusCommandInputFromGesture({ preventScroll = true } = {}) {
  if (typeof _appUseMobileViewportAdapter === "function" && _appUseMobileViewportAdapter()) {
    const mobileInput = typeof _appGetComposerInputsAdapter === "function" ? _appGetComposerInputsAdapter().mobile : null;
    if (mobileInput && typeof _appFocusComposerInputAdapter === "function") {
      if (typeof _appSetMobileKeyboardOpenStateAdapter === "function") _appSetMobileKeyboardOpenStateAdapter(true);
      _appFocusComposerInputAdapter(mobileInput, { preventScroll });
    }
    return;
  }
  if (typeof _appFocusAnyComposerInputAdapter === "function" && _appFocusAnyComposerInputAdapter({ preventScroll: true })) return;
}
function _closeMajorOverlays(options = {}) {
  const skipProjectWorkspace = !!(options && options.skipProjectWorkspace);
  if (typeof _appIsCommandCatalogOverlayOpenAdapter === "function" && _appIsCommandCatalogOverlayOpenAdapter()) {
    if (typeof _appHideCommandCatalogOverlayAdapter === "function") _appHideCommandCatalogOverlayAdapter();
  }
  if (typeof _appIsCommandRegistryOverlayOpenAdapter === "function" && _appIsCommandRegistryOverlayOpenAdapter()) {
    if (typeof _appHideCommandRegistryOverlayAdapter === "function") _appHideCommandRegistryOverlayAdapter();
  }
  if (!skipProjectWorkspace && typeof isProjectWorkspaceOpen === "function" && isProjectWorkspaceOpen()) {
    closeProjectWorkspace({ refocus: false });
  }
  if (typeof _appIsAtlasOverlayOpenAdapter === "function" && _appIsAtlasOverlayOpenAdapter()) {
    if (typeof _appCloseAtlasAdapter === "function") _appCloseAtlasAdapter({ refocus: false });
  }
  if (typeof _appIsFindingsBoardOpenAdapter === "function" && _appIsFindingsBoardOpenAdapter()) {
    if (typeof _appCloseFindingsBoardAdapter === "function") _appCloseFindingsBoardAdapter({ refocus: false });
  }
  if (typeof _appIsTeamScopeSelectorOpenAdapter === "function" && _appIsTeamScopeSelectorOpenAdapter()) {
    if (typeof _appCloseTeamScopeSelectorAdapter === "function") _appCloseTeamScopeSelectorAdapter({ refocus: false });
  }
  if (typeof _appIsHistoryRunOverlayOpenAdapter === "function" && _appIsHistoryRunOverlayOpenAdapter()) {
    if (typeof _appCloseHistoryRunOverlayAdapter === "function") _appCloseHistoryRunOverlayAdapter();
  }
  if (_appIsHistoryPanelOpenAdapter()) _appHideHistoryPanelAdapter();
  if (_appIsWorkflowsOverlayOpenAdapter()) {
    if (typeof _appCloseWorkflowsAdapter === "function") _appCloseWorkflowsAdapter();
    else _appHideWorkflowsOverlayAdapter();
  }
  if (typeof _appIsSchedulesOverlayOpenAdapter === "function" && _appIsSchedulesOverlayOpenAdapter()) {
    if (typeof _appCloseSchedulesModalAdapter === "function") _appCloseSchedulesModalAdapter({ refocus: false });
  }
  if (typeof _appIsWatchersOverlayOpenAdapter === "function" && _appIsWatchersOverlayOpenAdapter()) {
    if (typeof _appCloseWatchersModalAdapter === "function") _appCloseWatchersModalAdapter({ refocus: false });
  }
  if (typeof _appIsWorkspaceOverlayOpenAdapter === "function" && _appIsWorkspaceOverlayOpenAdapter()) {
    if (typeof _appCloseWorkspaceAdapter === "function") _appCloseWorkspaceAdapter();
    else _appHideWorkspaceOverlayAdapter();
  }
  if (_appIsFaqOverlayOpenAdapter()) {
    if (typeof _appClearFaqHashAdapter === "function") _appClearFaqHashAdapter();
    _appHideFaqOverlayAdapter();
  }
  if (_appIsThemeOverlayOpenAdapter()) _appHideThemeOverlayAdapter();
  if (_appIsOptionsOverlayOpenAdapter()) _appHideOptionsOverlayAdapter();
  if (typeof _appIsShortcutsOverlayOpenAdapter === "function" && _appIsShortcutsOverlayOpenAdapter()) {
    if (typeof _appHideShortcutsOverlayAdapter === "function") _appHideShortcutsOverlayAdapter();
  }
}
function _syncOptionsSessionTokenStatusFallback() {
  const el = document.getElementById("options-session-token-status");
  const token = localStorage.getItem("session_token");
  const hasToken = Boolean(token);
  if (el) {
    el.textContent = hasToken && typeof _appMaskSessionTokenAdapter === "function" ? _appMaskSessionTokenAdapter(token) : hasToken ? token : "No session token — anonymous session";
    el.classList.toggle("is-active", hasToken);
  }
  const generateBtn = document.getElementById("options-session-token-generate-btn");
  const rotateBtn = document.getElementById("options-session-token-rotate-btn");
  const clearBtn = document.getElementById("options-session-token-clear-btn");
  const copyBtn = document.getElementById("options-session-token-copy-btn");
  if (generateBtn) generateBtn.style.display = hasToken ? "none" : "";
  if (rotateBtn) rotateBtn.style.display = hasToken ? "" : "none";
  if (clearBtn) clearBtn.style.display = hasToken ? "" : "none";
  if (copyBtn) copyBtn.style.display = hasToken ? "" : "none";
}
function openOptions() {
  _closeMajorOverlays();
  if (typeof _appBlurVisibleComposerMobileAdapter === "function") _appBlurVisibleComposerMobileAdapter();
  _appSyncOptionsControlsAdapter();
  if (typeof _appUpdateOptionsSessionTokenStatusAdapter === "function") _appUpdateOptionsSessionTokenStatusAdapter();
  else _syncOptionsSessionTokenStatusFallback();
  _appShowOptionsOverlayAdapter();
  if (typeof _appMarkInteractionSurfaceReadyAdapter === "function") {
    _appMarkInteractionSurfaceReadyAdapter("options", optionsOverlay2, document.getElementById("options-modal"));
  }
  const panelsReady = typeof _appLoadOptionsPanelsAdapter === "function" ? Promise.resolve(_appLoadOptionsPanelsAdapter()) : Promise.resolve();
  panelsReady.then((panels) => {
    const updateSessionTokenStatus = panels?._updateOptionsSessionTokenStatus || (typeof _appUpdateOptionsSessionTokenStatusAdapter === "function" ? _appUpdateOptionsSessionTokenStatusAdapter : null);
    const refreshSecrets = panels?.refreshOptionsSecrets || (typeof _appRefreshOptionsSecretsAdapter === "function" ? _appRefreshOptionsSecretsAdapter : null);
    const refreshTeams = panels?.refreshOptionsTeams || (typeof _appRefreshOptionsTeamsAdapter === "function" ? _appRefreshOptionsTeamsAdapter : null);
    const refreshNotifications = panels?.refreshNotificationChannels || (typeof _appRefreshNotificationChannelsAdapter === "function" ? _appRefreshNotificationChannelsAdapter : null);
    if (typeof updateSessionTokenStatus === "function") updateSessionTokenStatus();
    if (typeof refreshSecrets === "function") {
      refreshSecrets().catch((err) => _appLogClientErrorAdapter("failed to load options secrets", err));
    }
    const activeTab = document.querySelector('[data-options-tab][aria-selected="true"]')?.dataset?.optionsTab;
    if (activeTab === "teams" && typeof refreshTeams === "function") {
      refreshTeams().catch((err) => _appLogClientErrorAdapter("failed to load options teams", err));
    }
    if (activeTab === "notifications" && typeof refreshNotifications === "function") {
      refreshNotifications().catch((err) => _appLogClientErrorAdapter("failed to load notification channels", err));
    }
  }).catch((err) => _appLogClientErrorAdapter("failed to load options panels", err));
}
function closeOptions() {
  _appHideOptionsOverlayAdapter();
  _appRefocusComposerAdapter({ defer: true });
}
function openThemeSelector() {
  _closeMajorOverlays();
  if (typeof _appBlurVisibleComposerMobileAdapter === "function") _appBlurVisibleComposerMobileAdapter();
  _appRenderThemeSelectionOptionsAdapter();
  _appSyncThemeSelectionControlsAdapter();
  _appShowThemeOverlayAdapter();
  setTimeout(() => {
    const selectedCard = themeSelect2 && themeSelect2.querySelector(".theme-card-active");
    const target = selectedCard || themeSelect2?.querySelector("[data-theme-name]");
    if (!_appFocusElementAdapter(target, { preventScroll: true })) {
      _appFocusElementAdapter(themeSelect2, { preventScroll: true });
    }
    if (typeof _appMarkInteractionSurfaceReadyAdapter === "function") {
      _appMarkInteractionSurfaceReadyAdapter("theme", themeOverlay2, document.getElementById("theme-modal"));
    }
  }, 0);
}
function closeThemeSelector() {
  _appHideThemeOverlayAdapter();
  _appRefocusComposerAdapter({ defer: true });
}
function isEditableTarget(target) {
  return !!(target && target.closest && target.closest('input, textarea, [contenteditable="true"]'));
}
function shouldIgnoreGlobalShortcutTarget(target) {
  return isEditableTarget(target) && target !== cmdInput2;
}
function createNextTabLabel() {
  if (typeof _appCreateDefaultTabLabelAdapter === "function") {
    const label = _appCreateDefaultTabLabelAdapter();
    if (typeof label === "string" && label) return label;
  }
  return "shell " + (_appTabs().length + 1);
}
function createShortcutTab() {
  _appCreateTabAdapter(createNextTabLabel());
}
function activateRelativeTab(offset) {
  const tabs = _appTabs();
  const activeTabId = _appActiveTabId();
  if (!Array.isArray(tabs) || !tabs.length) return;
  const currentIndex = tabs.findIndex((tab) => tab.id === activeTabId);
  const baseIndex = currentIndex >= 0 ? currentIndex : 0;
  const nextIndex = (baseIndex + offset + tabs.length) % tabs.length;
  _appActivateTabAdapter(tabs[nextIndex].id);
}
function closeActiveShortcutTab() {
  const closeActiveTab = typeof closeTab === "function" ? typeof _appCloseTabAdapter === "function" ? _appCloseTabAdapter : closeTab : typeof _appCloseTabAdapter === "function" ? _appCloseTabAdapter : null;
  const activeTabId = _appActiveTabId();
  if (!activeTabId || !closeActiveTab) return;
  closeActiveTab(activeTabId);
}
function permalinkActiveShortcutTab() {
  const permalinkActiveTab = typeof permalinkTab === "function" ? typeof _appPermalinkTabAdapter === "function" ? _appPermalinkTabAdapter : permalinkTab : typeof _appPermalinkTabAdapter === "function" ? _appPermalinkTabAdapter : null;
  const activeTabId = _appActiveTabId();
  if (!activeTabId || !permalinkActiveTab) return;
  permalinkActiveTab(activeTabId);
}
function copyActiveShortcutTab() {
  const copyActiveTab = typeof copyTab === "function" ? typeof _appCopyTabAdapter === "function" ? _appCopyTabAdapter : copyTab : typeof _appCopyTabAdapter === "function" ? _appCopyTabAdapter : null;
  const activeTabId = _appActiveTabId();
  if (!activeTabId || !copyActiveTab) return;
  copyActiveTab(activeTabId);
}
function clearActiveShortcutTab() {
  const activeTabId = _appActiveTabId();
  if (!activeTabId) return;
  const cancel = typeof cancelWelcome === "function" ? typeof _appCancelWelcomeAdapter === "function" ? _appCancelWelcomeAdapter : cancelWelcome : typeof _appCancelWelcomeAdapter === "function" ? _appCancelWelcomeAdapter : null;
  if (typeof cancel === "function") cancel(activeTabId);
  const activeTab = typeof _appGetActiveTabAdapter === "function" ? _appGetActiveTabAdapter() : null;
  _appClearTabAdapter(activeTabId, { preserveRunState: !!(activeTab && activeTab.st === "running") });
}
function isStatusMonitorShortcutOpen() {
  if (typeof _appIsStatusMonitorOpenAdapter === "function") return _appIsStatusMonitorOpenAdapter();
  const monitor = document.getElementById("status-monitor");
  return !!(monitor && !monitor.classList.contains("u-hidden"));
}
function _buildShareRedactionRememberField() {
  const field = document.createElement("div");
  field.className = "faq-item modal-inline-field";
  const fieldset = document.createElement("div");
  fieldset.className = "faq-a form-fieldset";
  const choice = document.createElement("label");
  choice.className = "form-check";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.id = "share-redaction-remember-toggle";
  const text = document.createElement("span");
  text.textContent = "Set this as my default share-snapshot choice";
  choice.appendChild(checkbox);
  choice.appendChild(text);
  fieldset.appendChild(choice);
  field.appendChild(fieldset);
  return { field, checkbox };
}
async function confirmPermalinkRedactionChoice() {
  if (_appConfig().share_redaction_enabled === false) return "raw";
  const preferred = _appGetShareRedactionDefaultPreferenceAdapter();
  if (preferred === "raw" || preferred === "redacted") return preferred;
  if (typeof _appBlurVisibleComposerMobileAdapter === "function") _appBlurVisibleComposerMobileAdapter();
  const { field, checkbox } = _buildShareRedactionRememberField();
  let choice = null;
  try {
    choice = await _appShowConfirmAdapter({
      body: {
        text: "Create permalink with redaction enabled?",
        note: "Redaction can mask common sensitive values such as IP addresses, host names, email addresses, bearer tokens, and any operator-defined share redaction rules before the snapshot is saved."
      },
      content: field,
      actions: [
        { id: "cancel", label: "Cancel", role: "cancel" },
        { id: "raw", label: "Share Raw", role: "secondary" },
        { id: "redacted", label: "Share Redacted", role: "primary" }
      ]
    });
  } catch (_) {
    choice = null;
  }
  if ((choice === "raw" || choice === "redacted") && checkbox.checked) {
    _appApplyShareRedactionDefaultPreferenceAdapter(choice);
  }
  if (choice === "raw" || choice === "redacted") return choice;
  return null;
}
function performMobileEditAction(action) {
  const input = typeof _appGetVisibleComposerInputAdapter === "function" && _appGetVisibleComposerInputAdapter() || null;
  if (!input) return;
  if (document.activeElement !== input && typeof _appFocusAnyComposerInputAdapter === "function") _appFocusAnyComposerInputAdapter({ preventScroll: true });
  _setAutocompleteSuppressInputOnce(true);
  if (typeof _appHideAutocompleteAdapter === "function") _appHideAutocompleteAdapter();
  const composer = getComposerStateSnapshot();
  const inputValue = input.value || "";
  const composerValue = composer && typeof composer.value === "string" ? composer.value : null;
  const preferLiveInput = document.activeElement === input && composerValue !== inputValue;
  const value = preferLiveInput ? inputValue : composerValue !== null ? composerValue : inputValue;
  const { start, end } = preferLiveInput || !composer ? getInputSelection(input, value) : getCmdSelection(value);
  let nextValue = value;
  let nextStart = start;
  let nextEnd = end;
  if (action === "left") {
    const pos = Math.max(0, start - 1);
    nextStart = pos;
    nextEnd = pos;
  } else if (action === "word-left") {
    const pos = findWordBoundaryLeft(value, start);
    nextStart = pos;
    nextEnd = pos;
  } else if (action === "right") {
    const pos = Math.min(value.length, end + 1);
    nextStart = pos;
    nextEnd = pos;
  } else if (action === "word-right") {
    const pos = findWordBoundaryRight(value, end);
    nextStart = pos;
    nextEnd = pos;
  } else if (action === "home") {
    nextStart = 0;
    nextEnd = 0;
  } else if (action === "end") {
    nextStart = value.length;
    nextEnd = value.length;
  } else if (action === "delete-word") {
    if (start !== end) {
      nextValue = value.slice(0, start) + value.slice(end);
      nextStart = start;
      nextEnd = start;
    } else if (start > 0) {
      const cut = findWordBoundaryLeft(value, start);
      nextValue = value.slice(0, cut) + value.slice(start);
      nextStart = cut;
      nextEnd = cut;
    }
  } else if (action === "delete-line") {
    nextValue = "";
    nextStart = 0;
    nextEnd = 0;
  }
  if (action === "left" || action === "right" || action === "word-left" || action === "word-right" || action === "home" || action === "end") {
    if (typeof _appSyncComposerSelectionAdapter === "function") _appSyncComposerSelectionAdapter(nextStart, nextEnd, { input });
    else if (input && typeof input.setSelectionRange === "function") input.setSelectionRange(nextStart, nextEnd);
    setTimeout(() => {
      if (!input || typeof input.setSelectionRange !== "function") return;
      if (typeof document !== "undefined" && document.activeElement !== input) return;
      if ((input.value || "") !== value) return;
      if (input.selectionStart === nextStart && input.selectionEnd === nextEnd) return;
      input.setSelectionRange(nextStart, nextEnd);
      if (typeof _appSetComposerStateAdapter === "function") {
        _appSetComposerStateAdapter({
          value,
          selectionStart: nextStart,
          selectionEnd: nextEnd,
          activeInput: "mobile"
        });
      }
      syncShellPrompt2();
    }, 0);
  } else {
    _appSetComposerValueAdapter(nextValue, nextStart, nextEnd);
  }
  if (typeof _appFocusAnyComposerInputAdapter === "function") setTimeout(() => _appFocusAnyComposerInputAdapter({ preventScroll: true }), 0);
}
var _tsModes = ["off", "elapsed", "clock"];
if (typeof window !== "undefined") {
  if (typeof setComposerPromptHandlers === "function") {
    setComposerPromptHandlers({
      getComposerPromptMode: () => _composerPromptMode,
      hidePromptUsernameSavedIndicator,
      setComposerPromptMode,
      showPromptUsernameSavedIndicator,
      syncShellPrompt: syncShellPrompt2
    });
  }
  if (typeof setShareRedactionHandlers === "function") {
    setShareRedactionHandlers({ confirmPermalinkRedactionChoice });
  }
  if (typeof setOverlayActionHandlers === "function") {
    setOverlayActionHandlers({ closeMajorOverlays: _closeMajorOverlays });
  }
}

export {
  getCmdSelection,
  replaceCmdRange,
  handleComposerWordArrowShortcut,
  findWordBoundaryLeft,
  findWordBoundaryRight,
  hidePromptUsernameSavedIndicator,
  focusCommandInputFromGesture,
  openOptions,
  closeOptions,
  openThemeSelector,
  closeThemeSelector,
  isEditableTarget,
  shouldIgnoreGlobalShortcutTarget,
  createShortcutTab,
  activateRelativeTab,
  closeActiveShortcutTab,
  permalinkActiveShortcutTab,
  copyActiveShortcutTab,
  clearActiveShortcutTab,
  isStatusMonitorShortcutOpen,
  performMobileEditAction,
  _tsModes
};
