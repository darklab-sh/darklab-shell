// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// ── Desktop UI module ──
// Shared helpers for keyboard shortcuts, overlays, and mobile-layout glue.

import {
  findWordBoundaryLeft,
  findWordBoundaryRight,
  getCmdSelection,
  getComposerStateSnapshot,
  getInputSelection,
} from './features/terminal/composer_editing.js';
import {
  cmdInput as importedCmdInput,
  mobileCmdInput as importedMobileCmdInput,
  mobileComposerRow as importedMobileComposerRow,
  optionsOverlay as importedOptionsOverlay,
  shellPromptText as importedShellPromptText,
  shellPromptWrap as importedShellPromptWrap,
  themeOverlay as importedThemeOverlay,
  themeSelect as importedThemeSelect,
  tsBtn as importedTsBtn,
} from './core/dom.js';
import { getAppConfig as importedGetAppConfig } from './core/config.js';
import { maskSessionToken as importedMaskSessionToken } from './core/session_core.js';
import { showToast as importedShowToast } from './core/utils.js';
import {
  getActiveTab as importedGetActiveTab,
  getActiveTabId as importedGetActiveTabId,
  getAppState as importedGetAppState,
  getAutocompleteState as importedGetAutocompleteState,
  getComposerState as importedGetComposerState,
  getTabs as importedGetTabs,
  setAutocompleteState as importedSetAutocompleteState,
  setComposerState as importedSetComposerState,
} from './core/state.js';
import {
  blurVisibleComposerInputIfMobile as importedBlurVisibleComposerInputIfMobile,
  focusAnyComposerInput as importedFocusAnyComposerInput,
  focusComposerInput as importedFocusComposerInput,
  focusElement as importedFocusElement,
  getComposerInputs as importedGetComposerInputs,
  getVisibleComposerInput as importedGetVisibleComposerInput,
  hideFaqOverlay as importedHideFaqOverlay,
  hideHistoryPanel as importedHideHistoryPanel,
  hideOptionsOverlay as importedHideOptionsOverlay,
  hideShortcutsOverlay as importedHideShortcutsOverlay,
  hideThemeOverlay as importedHideThemeOverlay,
  hideWorkflowsOverlay as importedHideWorkflowsOverlay,
  hideWorkspaceOverlay as importedHideWorkspaceOverlay,
  isFaqOverlayOpen as importedIsFaqOverlayOpen,
  isHistoryPanelOpen as importedIsHistoryPanelOpen,
  isOptionsOverlayOpen as importedIsOptionsOverlayOpen,
  isShortcutsOverlayOpen as importedIsShortcutsOverlayOpen,
  isThemeOverlayOpen as importedIsThemeOverlayOpen,
  isWorkflowsOverlayOpen as importedIsWorkflowsOverlayOpen,
  isWorkspaceOverlayOpen as importedIsWorkspaceOverlayOpen,
  markInteractionSurfaceReady as importedMarkInteractionSurfaceReady,
  refocusComposerAfterAction as importedRefocusComposerAfterAction,
  setComposerValue as importedSetComposerValue,
  setMobileKeyboardOpenState as importedSetMobileKeyboardOpenState,
  showOptionsOverlay as importedShowOptionsOverlay,
  showThemeOverlay as importedShowThemeOverlay,
  syncComposerSelection as importedSyncComposerSelection,
  syncFocusedComposerState as importedSyncFocusedComposerState,
} from './ui/ui_helpers.js';
import {
  _refreshFollowingOutputsAfterLayout as importedRefreshFollowingOutputsAfterLayout,
  buildPromptLabel as importedBuildPromptLabel,
  currentPromptWorkspacePath as importedCurrentPromptWorkspacePath,
  syncOutputPrefixes as importedSyncOutputPrefixes,
} from './output.js';
import { clearFaqHash as importedClearFaqHash } from './features/command-registry/faq_helpers.js';
import {
  hideCommandCatalogOverlay as importedHideCommandCatalogOverlay,
  isCommandCatalogOverlayOpen as importedIsCommandCatalogOverlayOpen,
} from './features/command-registry/command_registry_bridge.js';
import { closeWorkflows as importedCloseWorkflows } from './controller_action_bridge.js';
import {
  activateTab as importedActivateTab,
  clearTab as importedClearTab,
  createDefaultTabLabel as importedCreateDefaultTabLabel,
  createTab as importedCreateTab,
} from './tabs.js';
import { closeTab as importedCloseTab } from './features/tabs/tab_close_lifecycle.js';
import {
  copyTab as importedCopyTab,
  permalinkTab as importedPermalinkTab,
} from './features/tabs/tab_exports.js';
import {
  renderThemeSelectionOptions as importedRenderThemeSelectionOptions,
  syncThemeSelectionControls as importedSyncThemeSelectionControls,
} from './features/theme/theme.js';
import {
  applyShareRedactionDefaultPreference as importedApplyShareRedactionDefaultPreference,
  getShareRedactionDefaultPreference as importedGetShareRedactionDefaultPreference,
  syncOptionsControls as importedSyncOptionsControls,
} from './features/preferences/preferences.js';
import { updateOptionsSessionTokenStatus as importedUpdateOptionsSessionTokenStatus } from './features/preferences/session_token_bridge.js';
import {
  closeWorkspace as importedCloseWorkspace,
} from './workspace_bridge.js';
import {
  closeAtlas as importedCloseAtlas,
  isAtlasOverlayOpen as importedIsAtlasOverlayOpen,
} from './features/atlas/atlas_bridge.js';
import {
  closeHistoryRunOverlay as importedCloseHistoryRunOverlay,
  isHistoryRunOverlayOpen as importedIsHistoryRunOverlayOpen,
} from './features/history/history_run_modal_state_bridge.js';
import {
  closeTeamScopeSelector as importedCloseTeamScopeSelector,
  isTeamScopeSelectorOpen as importedIsTeamScopeSelectorOpen,
} from './features/team_scope.js';
import {
  closeProjectWorkspace as importedCloseProjectWorkspace,
  isProjectWorkspaceOpen as importedIsProjectWorkspaceOpen,
} from './features/projects/project_context_bridge.js';
import {
  hasMobileShellLayoutHandler as importedHasMobileShellLayoutHandler,
  useMobileTerminalViewportMode as importedUseMobileTerminalViewportMode,
} from './features/mobile/mobile_shell_layout_bridge.js';
import { setComposerPromptHandlers as importedSetComposerPromptHandlers } from './features/terminal/composer_prompt_bridge.js';
import { setShareRedactionHandlers as importedSetShareRedactionHandlers } from './features/tabs/share_redaction_bridge.js';
import {
  hasSecretsHandler as importedHasSecretsHandler,
  refreshOptionsSecrets as importedRefreshOptionsSecrets,
} from './features/preferences/secrets_bridge.js';
import { setTimestampMode as importedSetOutputTimestampMode } from './output_mode_bridge.js';
import { cancelWelcome as importedCancelWelcome } from './welcome_bridge.js';
import { showConfirm as importedShowConfirm } from './ui/ui_confirm.js';
import { setOverlayActionHandlers as importedSetOverlayActionHandlers } from './ui/overlay_actions_bridge.js';
import {
  hasRuntimeHandler as importedHasRuntimeHandler,
  logClientError as importedLogClientError,
} from './runtime_bridge.js';

let importedHideCommandRegistryOverlay;
let importedIsCommandRegistryOverlayOpen;

const APP_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _appFn(name, imported = null) {
  if (typeof imported === 'function') return imported;
  const fn = APP_GLOBAL && APP_GLOBAL[name];
  if (typeof fn === 'function') return fn;
  return null;
}

function _appValue(name, imported = undefined) {
  return imported !== undefined ? imported : (APP_GLOBAL ? APP_GLOBAL[name] : undefined);
}

function _appEl(name, imported = undefined) {
  return _appValue(name, imported) || null;
}

function _appConfig() {
  const globalConfig = _appValue('APP_CONFIG');
  if (globalConfig && typeof globalConfig === 'object' && !Array.isArray(globalConfig)) {
    return globalConfig;
  }
  const config = _appFn('getAppConfig', importedGetAppConfig)?.();
  return config || {};
}

function _appState() {
  const state = _appFn('getAppState', importedGetAppState)?.();
  return state || _appValue('APP_STATE') || {};
}

function _appTabs() {
  const tabs = _appFn('getTabs', importedGetTabs)?.();
  if (Array.isArray(tabs)) return tabs;
  const state = _appState();
  return Array.isArray(state.tabs) ? state.tabs : [];
}

function _appActiveTabId() {
  const id = _appFn('getActiveTabId', importedGetActiveTabId)?.();
  return id || _appState().activeTabId || null;
}

function _appAutocompleteState() {
  const state = _appFn('getAutocompleteState', importedGetAutocompleteState)?.();
  return state || _appState();
}

var cmdInput = _appEl('cmdInput', importedCmdInput);
var mobileCmdInput = _appEl('mobileCmdInput', importedMobileCmdInput);
var mobileComposerRow = _appEl('mobileComposerRow', importedMobileComposerRow);
var optionsOverlay = _appEl('optionsOverlay', importedOptionsOverlay);
var shellPromptText = _appEl('shellPromptText', importedShellPromptText);
var shellPromptWrap = _appEl('shellPromptWrap', importedShellPromptWrap);
var themeOverlay = _appEl('themeOverlay', importedThemeOverlay);
var themeSelect = _appEl('themeSelect', importedThemeSelect);
var tsBtn = _appEl('tsBtn', importedTsBtn);
var _appSetAutocompleteStateAdapter = (...args) => _appFn('setAutocompleteState', importedSetAutocompleteState)?.(...args);
var _appShowToastAdapter = (...args) => _appFn('showToast', importedShowToast)?.(...args);
var _appBuildPromptLabelAdapter = (...args) => _appFn('buildPromptLabel', importedBuildPromptLabel)?.(...args);
var _appCurrentPromptWorkspacePathAdapter = (...args) => _appFn('currentPromptWorkspacePath', importedCurrentPromptWorkspacePath)?.(...args);
var _appGetComposerInputsAdapter = (...args) => _appFn('getComposerInputs', importedGetComposerInputs)?.(...args);
var _appSyncFocusedComposerStateAdapter = (...args) => _appFn('syncFocusedComposerState', importedSyncFocusedComposerState)?.(...args);
var _appGetComposerStateAdapter = (...args) => _appFn('getComposerState', importedGetComposerState)?.(...args);
var _appUseMobileViewportAdapter = (...args) => {
  const fn = (
    typeof importedHasMobileShellLayoutHandler === 'function'
    && importedHasMobileShellLayoutHandler('useMobileTerminalViewportMode')
  ) ? importedUseMobileTerminalViewportMode : _appFn('useMobileTerminalViewportMode');
  return typeof fn === 'function' ? fn(...args) : false;
};
var _appSetMobileKeyboardOpenStateAdapter = (...args) => _appFn('setMobileKeyboardOpenState', importedSetMobileKeyboardOpenState)?.(...args);
var _appFocusComposerInputAdapter = (...args) => _appFn('focusComposerInput', importedFocusComposerInput)?.(...args);
var _appFocusAnyComposerInputAdapter = (...args) => _appFn('focusAnyComposerInput', importedFocusAnyComposerInput)?.(...args);
var _appIsAtlasOverlayOpenAdapter = (...args) => _appFn('isAtlasOverlayOpen', importedIsAtlasOverlayOpen)?.(...args);
var _appCloseAtlasAdapter = (...args) => _appFn('closeAtlas', importedCloseAtlas)?.(...args);
var _appIsFindingsBoardOpenAdapter = (...args) => _appFn('isFindingsBoardOpen')?.(...args);
var _appCloseFindingsBoardAdapter = (...args) => _appFn('closeFindingsBoard')?.(...args);
var _appIsTeamScopeSelectorOpenAdapter = (...args) => _appFn('isTeamScopeSelectorOpen', importedIsTeamScopeSelectorOpen)?.(...args);
var _appCloseTeamScopeSelectorAdapter = (...args) => _appFn('closeTeamScopeSelector', importedCloseTeamScopeSelector)?.(...args);
var _appIsHistoryRunOverlayOpenAdapter = (...args) => _appFn('isHistoryRunOverlayOpen', importedIsHistoryRunOverlayOpen)?.(...args);
var _appCloseHistoryRunOverlayAdapter = (...args) => _appFn('closeHistoryRunOverlay', importedCloseHistoryRunOverlay)?.(...args);
var _appIsHistoryPanelOpenAdapter = (...args) => _appFn('isHistoryPanelOpen', importedIsHistoryPanelOpen)?.(...args);
var _appHideHistoryPanelAdapter = (...args) => _appFn('hideHistoryPanel', importedHideHistoryPanel)?.(...args);
var _appIsWorkflowsOverlayOpenAdapter = (...args) => _appFn('isWorkflowsOverlayOpen', importedIsWorkflowsOverlayOpen)?.(...args);
var _appCloseWorkflowsAdapter = (...args) => _appFn('closeWorkflows', importedCloseWorkflows)?.(...args);
var _appHideWorkflowsOverlayAdapter = (...args) => _appFn('hideWorkflowsOverlay', importedHideWorkflowsOverlay)?.(...args);
var _appIsSchedulesOverlayOpenAdapter = (...args) => _appFn('isSchedulesOverlayOpen')?.(...args);
var _appCloseSchedulesModalAdapter = (...args) => _appFn('closeSchedulesModal')?.(...args);
var _appIsWatchersOverlayOpenAdapter = (...args) => _appFn('isWatchersOverlayOpen')?.(...args);
var _appCloseWatchersModalAdapter = (...args) => _appFn('closeWatchersModal')?.(...args);
var _appIsWorkspaceOverlayOpenAdapter = (...args) => _appFn('isWorkspaceOverlayOpen', importedIsWorkspaceOverlayOpen)?.(...args);
var _appCloseWorkspaceAdapter = (...args) => _appFn('closeWorkspace', importedCloseWorkspace)?.(...args);
var _appHideWorkspaceOverlayAdapter = (...args) => _appFn('hideWorkspaceOverlay', importedHideWorkspaceOverlay)?.(...args);
var _appIsFaqOverlayOpenAdapter = (...args) => _appFn('isFaqOverlayOpen', importedIsFaqOverlayOpen)?.(...args);
var _appHideFaqOverlayAdapter = (...args) => _appFn('hideFaqOverlay', importedHideFaqOverlay)?.(...args);
var _appIsThemeOverlayOpenAdapter = (...args) => _appFn('isThemeOverlayOpen', importedIsThemeOverlayOpen)?.(...args);
var _appHideThemeOverlayAdapter = (...args) => _appFn('hideThemeOverlay', importedHideThemeOverlay)?.(...args);
var _appIsOptionsOverlayOpenAdapter = (...args) => _appFn('isOptionsOverlayOpen', importedIsOptionsOverlayOpen)?.(...args);
var _appHideOptionsOverlayAdapter = (...args) => _appFn('hideOptionsOverlay', importedHideOptionsOverlay)?.(...args);
var _appIsShortcutsOverlayOpenAdapter = (...args) => _appFn('isShortcutsOverlayOpen', importedIsShortcutsOverlayOpen)?.(...args);
var _appHideShortcutsOverlayAdapter = (...args) => _appFn('hideShortcutsOverlay', importedHideShortcutsOverlay)?.(...args);
var _appMaskSessionTokenAdapter = (...args) => (
  typeof importedMaskSessionToken === 'function' ? importedMaskSessionToken(...args) : undefined
);
var _appSyncOptionsControlsAdapter = (...args) => _appFn('syncOptionsControls', importedSyncOptionsControls)?.(...args);
var _appUpdateOptionsSessionTokenStatusAdapter = (...args) => _appFn('_updateOptionsSessionTokenStatus', importedUpdateOptionsSessionTokenStatus)?.(...args);
var _appShowOptionsOverlayAdapter = (...args) => _appFn('showOptionsOverlay', importedShowOptionsOverlay)?.(...args);
var _appMarkInteractionSurfaceReadyAdapter = (...args) => _appFn('markInteractionSurfaceReady', importedMarkInteractionSurfaceReady)?.(...args);
var _appLoadOptionsPanelsAdapter = (...args) => _appFn('loadOptionsPanels')?.(...args);
var _appRefreshOptionsSecretsAdapter = (...args) => {
  const fn = (
    typeof importedHasSecretsHandler === 'function'
    && importedHasSecretsHandler('refreshOptionsSecrets')
    && typeof importedRefreshOptionsSecrets === 'function'
  ) ? importedRefreshOptionsSecrets : _appFn('refreshOptionsSecrets');
  return typeof fn === 'function' ? fn(...args) : undefined;
};
var _appRefreshOptionsTeamsAdapter = (...args) => _appFn('refreshOptionsTeams')?.(...args);
var _appRefreshNotificationChannelsAdapter = (...args) => _appFn('refreshNotificationChannels')?.(...args);
var _appLogClientErrorAdapter = (...args) => {
  const bridge = (
    typeof importedHasRuntimeHandler === 'function'
    && importedHasRuntimeHandler('logClientError')
    && typeof importedLogClientError === 'function'
      ? importedLogClientError
      : null
  );
  return _appFn('logClientError', bridge)?.(...args);
};
var _appBlurVisibleComposerMobileAdapter = (...args) => _appFn('blurVisibleComposerInputIfMobile', importedBlurVisibleComposerInputIfMobile)?.(...args);
var _appRefocusComposerAdapter = (...args) => _appFn('refocusComposerAfterAction', importedRefocusComposerAfterAction)?.(...args);
var _appRenderThemeSelectionOptionsAdapter = (...args) => _appFn('renderThemeSelectionOptions', importedRenderThemeSelectionOptions)?.(...args);
var _appSyncThemeSelectionControlsAdapter = (...args) => _appFn('syncThemeSelectionControls', importedSyncThemeSelectionControls)?.(...args);
var _appShowThemeOverlayAdapter = (...args) => _appFn('showThemeOverlay', importedShowThemeOverlay)?.(...args);
var _appFocusElementAdapter = (...args) => _appFn('focusElement', importedFocusElement)?.(...args);
var _appCloseTabAdapter = (...args) => _appFn('closeTab', importedCloseTab)?.(...args);
var _appPermalinkTabAdapter = (...args) => _appFn('permalinkTab', importedPermalinkTab)?.(...args);
var _appCopyTabAdapter = (...args) => _appFn('copyTab', importedCopyTab)?.(...args);
var _appCancelWelcomeAdapter = (...args) => _appFn('cancelWelcome')?.(...args);
var _appGetActiveTabAdapter = (...args) => _appFn('getActiveTab', importedGetActiveTab)?.(...args);
var _appClearTabAdapter = (...args) => _appFn('clearTab', importedClearTab)?.(...args);
var _appIsStatusMonitorOpenAdapter = (...args) => _appFn('isStatusMonitorOpen')?.(...args);
var _appGetShareRedactionDefaultPreferenceAdapter = (...args) => _appFn('getShareRedactionDefaultPreference', importedGetShareRedactionDefaultPreference)?.(...args);
var _appShowConfirmAdapter = (...args) => _appFn('showConfirm', importedShowConfirm)?.(...args);
var _appApplyShareRedactionDefaultPreferenceAdapter = (...args) => _appFn('applyShareRedactionDefaultPreference', importedApplyShareRedactionDefaultPreference)?.(...args);
var _appGetVisibleComposerInputAdapter = (...args) => _appFn('getVisibleComposerInput', importedGetVisibleComposerInput)?.(...args);
var _appHideAutocompleteAdapter = (...args) => _appFn('acHide')?.(...args);
var _appSyncComposerSelectionAdapter = (...args) => _appFn('syncComposerSelection', importedSyncComposerSelection)?.(...args);
var _appSetComposerStateAdapter = (...args) => _appFn('setComposerState', importedSetComposerState)?.(...args);
var _appSetComposerValueAdapter = (...args) => _appFn('setComposerValue', importedSetComposerValue)?.(...args);
var _appSyncOutputPrefixesAdapter = (...args) => _appFn('syncOutputPrefixes', importedSyncOutputPrefixes)?.(...args);
var _appRefreshFollowingOutputsAfterLayoutAdapter = (...args) => _appFn('_refreshFollowingOutputsAfterLayout', importedRefreshFollowingOutputsAfterLayout)?.(...args);
var _appCreateDefaultTabLabelAdapter = (...args) => _appFn('createDefaultTabLabel', importedCreateDefaultTabLabel)?.(...args);
var _appCreateTabAdapter = (...args) => _appFn('createTab', importedCreateTab)?.(...args);
var _appActivateTabAdapter = (...args) => _appFn('activateTab', importedActivateTab)?.(...args);
var _appClearFaqHashAdapter = (...args) => _appFn('clearFaqHash', importedClearFaqHash)?.(...args);
var _appHideCommandCatalogOverlayAdapter = (...args) => _appFn('hideCommandCatalogOverlay', importedHideCommandCatalogOverlay)?.(...args);
var _appHideCommandRegistryOverlayAdapter = (...args) => _appFn('hideCommandRegistryOverlay', importedHideCommandRegistryOverlay)?.(...args);
var _appIsCommandCatalogOverlayOpenAdapter = (...args) => _appFn('isCommandCatalogOverlayOpen', importedIsCommandCatalogOverlayOpen)?.(...args);
var _appIsCommandRegistryOverlayOpenAdapter = (...args) => _appFn('isCommandRegistryOverlayOpen', importedIsCommandRegistryOverlayOpen)?.(...args);

const _defaultDesktopPromptLabel = (() => {
  if (typeof shellPromptWrap === 'undefined' || !shellPromptWrap) return '';
  return String(shellPromptWrap.querySelector('.prompt-prefix')?.textContent || '');
})();
const _defaultMobilePromptLabel = (() => {
  if (typeof mobileComposerRow === 'undefined' || !mobileComposerRow) return '$';
  return String(mobileComposerRow.querySelector('.mobile-prompt-label')?.textContent || '$');
})();
let _composerPromptMode = null;

function _setAutocompleteSuppressInputOnce(value) {
  if (typeof _appSetAutocompleteStateAdapter === 'function') _appSetAutocompleteStateAdapter({ suppressInputOnce: !!value });
  if (_appAutocompleteState()) _appAutocompleteState().suppressInputOnce = !!value;
}

function hidePromptUsernameSavedIndicator() {
  return undefined;
}

function showPromptUsernameSavedIndicator() {
  if (typeof _appShowToastAdapter === 'function') _appShowToastAdapter('Prompt name saved', 'success');
}

function _compactMobileComposerPath(path = '/') {
  const displayPath = String(path || '/').trim() || '/';
  if (displayPath === '/') return '/';
  if (displayPath.length <= 18) return displayPath;
  const parts = displayPath.split('/').filter(Boolean);
  const folder = parts[parts.length - 1] || displayPath.replace(/^\/+/, '') || '/';
  return `.../${folder}`;
}

function _mobileComposerPlaceholder() {
  if (
    _appConfig().workspace_enabled === true
    && typeof _appCurrentPromptWorkspacePathAdapter === 'function'
  ) {
    return `${_compactMobileComposerPath(_appCurrentPromptWorkspacePathAdapter())} · type command`;
  }
  return 'Type a command';
}

function _applyComposerPromptMode() {
  const isConfirm = _composerPromptMode === 'confirm';
  const isSecret = _composerPromptMode === 'secret';
  const isPrompt = isConfirm || isSecret;
  const defaultPromptLabel = typeof _appBuildPromptLabelAdapter === 'function'
    ? _appBuildPromptLabelAdapter()
    : (_defaultDesktopPromptLabel || 'anon@darklab.sh:~ $');
  const desktopLabel = isConfirm ? '[yes/no]:' : (isSecret ? '[hidden]:' : defaultPromptLabel);
  const mobileLabel = isConfirm ? '[yes/no]:' : (isSecret ? '[hidden]:' : '');
  const promptPrefix = typeof shellPromptWrap !== 'undefined' && shellPromptWrap
    ? shellPromptWrap.querySelector('.prompt-prefix')
    : null;
  if (promptPrefix) promptPrefix.textContent = desktopLabel;
  if (typeof shellPromptWrap !== 'undefined' && shellPromptWrap) {
    shellPromptWrap.classList.toggle('shell-prompt-confirm', isPrompt);
  }
  const mobilePromptLabel = typeof mobileComposerRow !== 'undefined' && mobileComposerRow
    ? mobileComposerRow.querySelector('.mobile-prompt-label')
    : null;
  if (mobilePromptLabel) {
    mobilePromptLabel.textContent = mobileLabel;
    mobilePromptLabel.hidden = !isPrompt;
  }
  if (typeof mobileCmdInput !== 'undefined' && mobileCmdInput) {
    mobileCmdInput.placeholder = isPrompt ? '' : _mobileComposerPlaceholder();
  }
  if (typeof _appGetComposerInputsAdapter === 'function') {
    const { desktop, mobile } = _appGetComposerInputsAdapter();
    if (desktop) desktop.type = isSecret ? 'password' : 'text';
    if (mobile) mobile.type = isSecret ? 'password' : 'text';
  }
}

function _syncDesktopPromptPrefix() {
  const promptPrefix = typeof shellPromptWrap !== 'undefined' && shellPromptWrap
    ? shellPromptWrap.querySelector('.prompt-prefix')
    : null;
  if (!promptPrefix) return;
  const defaultPromptLabel = typeof _appBuildPromptLabelAdapter === 'function'
    ? _appBuildPromptLabelAdapter()
    : (_defaultDesktopPromptLabel || 'anon@darklab.sh:~ $');
  promptPrefix.textContent = _composerPromptMode === 'confirm'
    ? '[yes/no]:'
    : (_composerPromptMode === 'secret' ? '[hidden]:' : defaultPromptLabel);
  if (
    _composerPromptMode === null
    && _appConfig().workspace_enabled === true
    && typeof mobileCmdInput !== 'undefined'
    && mobileCmdInput
  ) {
    mobileCmdInput.placeholder = _mobileComposerPlaceholder();
  }
}

function setComposerPromptMode(mode = null) {
  _composerPromptMode = ['confirm', 'secret'].includes(mode) ? mode : null;
  if (typeof window !== 'undefined')  _applyComposerPromptMode();
}

function syncShellPrompt() {
  // The visible prompt is rendered from shared composer state instead of from
  // the hidden input directly, so selection/caret state stays correct across
  // desktop/mobile and while welcome owns the tab.
  if (typeof shellPromptText === 'undefined' || !shellPromptText) return;
  _syncDesktopPromptPrefix();
  if (
    typeof document !== 'undefined'
    && typeof _appSyncFocusedComposerStateAdapter === 'function'
    && typeof _appGetComposerInputsAdapter === 'function'
  ) {
    const { desktop, mobile } = _appGetComposerInputsAdapter();
    const active = document.activeElement;
    if (active && (active === desktop || active === mobile)) _appSyncFocusedComposerStateAdapter(active);
  }
  const composer = typeof _appGetComposerStateAdapter === 'function' ? _appGetComposerStateAdapter() : null;
  const fallbackInput = typeof cmdInput !== 'undefined' && cmdInput ? cmdInput : null;
  const rawValue = composer && typeof composer.value === 'string'
    ? composer.value
    : (fallbackInput ? fallbackInput.value || '' : '');
  const value = _composerPromptMode === 'secret' ? '*'.repeat(rawValue.length) : rawValue;
  const len = value.length;
  let start = composer && typeof composer.selectionStart === 'number'
    ? composer.selectionStart
    : (fallbackInput && typeof fallbackInput.selectionStart === 'number' ? fallbackInput.selectionStart : len);
  let end = composer && typeof composer.selectionEnd === 'number'
    ? composer.selectionEnd
    : (fallbackInput && typeof fallbackInput.selectionEnd === 'number' ? fallbackInput.selectionEnd : len);
  start = Math.max(0, Math.min(start, len));
  end = Math.max(0, Math.min(end, len));
  if (start > end) [start, end] = [end, start];

  if (typeof shellPromptWrap !== 'undefined' && shellPromptWrap) {
    shellPromptWrap.classList.toggle('shell-prompt-empty', len === 0);
    shellPromptWrap.classList.toggle('shell-prompt-has-value', len > 0);
    shellPromptWrap.classList.toggle('shell-prompt-has-selection', end > start);
  }

  shellPromptText.replaceChildren();
  if (!len) return;

  if (start > 0) shellPromptText.appendChild(document.createTextNode(value.slice(0, start)));

  if (end > start) {
    const sel = document.createElement('span');
    sel.className = 'shell-prompt-selection';
    sel.textContent = value.slice(start, end);
    shellPromptText.appendChild(sel);
  } else {
    if (start < len) {
      const caretChar = document.createElement('span');
      caretChar.className = 'shell-caret-char';
      caretChar.setAttribute('aria-hidden', 'true');
      caretChar.textContent = value.slice(start, start + 1);
      shellPromptText.appendChild(caretChar);
      if (start + 1 < len) shellPromptText.appendChild(document.createTextNode(value.slice(start + 1)));
      return;
    }
    const caret = document.createElement('span');
    caret.className = 'shell-inline-caret';
    caret.setAttribute('aria-hidden', 'true');
    caret.textContent = '';
    shellPromptText.appendChild(caret);
  }

  if (end < len) shellPromptText.appendChild(document.createTextNode(value.slice(end)));
}

function focusCommandInputFromGesture({ preventScroll = true } = {}) {
  if (typeof _appUseMobileViewportAdapter === 'function' && _appUseMobileViewportAdapter()) {
    const mobileInput = typeof _appGetComposerInputsAdapter === 'function' ? _appGetComposerInputsAdapter().mobile : null;
    if (mobileInput && typeof _appFocusComposerInputAdapter === 'function') {
      if (typeof _appSetMobileKeyboardOpenStateAdapter === 'function') _appSetMobileKeyboardOpenStateAdapter(true);
      _appFocusComposerInputAdapter(mobileInput, { preventScroll });
    }
    return;
  }
  if (typeof _appFocusAnyComposerInputAdapter === 'function' && _appFocusAnyComposerInputAdapter({ preventScroll: true })) return;
}

function _closeMajorOverlays(options = {}) {
  const skipProjectWorkspace = !!(options && options.skipProjectWorkspace);
  const skipAtlas = !!(options && options.skipAtlas);
  if (typeof _appIsCommandCatalogOverlayOpenAdapter === 'function' && _appIsCommandCatalogOverlayOpenAdapter()) {
    if (typeof _appHideCommandCatalogOverlayAdapter === 'function') _appHideCommandCatalogOverlayAdapter();
  }
  if (typeof _appIsCommandRegistryOverlayOpenAdapter === 'function' && _appIsCommandRegistryOverlayOpenAdapter()) {
    if (typeof _appHideCommandRegistryOverlayAdapter === 'function') _appHideCommandRegistryOverlayAdapter();
  }
  if (!skipProjectWorkspace && typeof importedIsProjectWorkspaceOpen === 'function' && importedIsProjectWorkspaceOpen()) {
    importedCloseProjectWorkspace({ refocus: false });
  }
  if (!skipAtlas && typeof _appIsAtlasOverlayOpenAdapter === 'function' && _appIsAtlasOverlayOpenAdapter()) {
    if (typeof _appCloseAtlasAdapter === 'function') _appCloseAtlasAdapter({ refocus: false });
  }
  if (typeof _appIsFindingsBoardOpenAdapter === 'function' && _appIsFindingsBoardOpenAdapter()) {
    if (typeof _appCloseFindingsBoardAdapter === 'function') _appCloseFindingsBoardAdapter({ refocus: false });
  }
  if (typeof _appIsTeamScopeSelectorOpenAdapter === 'function' && _appIsTeamScopeSelectorOpenAdapter()) {
    if (typeof _appCloseTeamScopeSelectorAdapter === 'function') _appCloseTeamScopeSelectorAdapter({ refocus: false });
  }
  if (typeof _appIsHistoryRunOverlayOpenAdapter === 'function' && _appIsHistoryRunOverlayOpenAdapter()) {
    if (typeof _appCloseHistoryRunOverlayAdapter === 'function') _appCloseHistoryRunOverlayAdapter();
  }
  if (_appIsHistoryPanelOpenAdapter()) _appHideHistoryPanelAdapter();
  if (_appIsWorkflowsOverlayOpenAdapter()) {
    if (typeof _appCloseWorkflowsAdapter === 'function') _appCloseWorkflowsAdapter();
    else _appHideWorkflowsOverlayAdapter();
  }
  if (typeof _appIsSchedulesOverlayOpenAdapter === 'function' && _appIsSchedulesOverlayOpenAdapter()) {
    if (typeof _appCloseSchedulesModalAdapter === 'function') _appCloseSchedulesModalAdapter({ refocus: false });
  }
  if (typeof _appIsWatchersOverlayOpenAdapter === 'function' && _appIsWatchersOverlayOpenAdapter()) {
    if (typeof _appCloseWatchersModalAdapter === 'function') _appCloseWatchersModalAdapter({ refocus: false });
  }
  if (typeof _appIsWorkspaceOverlayOpenAdapter === 'function' && _appIsWorkspaceOverlayOpenAdapter()) {
    if (typeof _appCloseWorkspaceAdapter === 'function') _appCloseWorkspaceAdapter();
    else _appHideWorkspaceOverlayAdapter();
  }
  if (_appIsFaqOverlayOpenAdapter()) {
    if (typeof _appClearFaqHashAdapter === 'function') _appClearFaqHashAdapter();
    _appHideFaqOverlayAdapter();
  }
  if (_appIsThemeOverlayOpenAdapter()) _appHideThemeOverlayAdapter();
  if (_appIsOptionsOverlayOpenAdapter()) _appHideOptionsOverlayAdapter();
  if (typeof _appIsShortcutsOverlayOpenAdapter === 'function' && _appIsShortcutsOverlayOpenAdapter()) {
    if (typeof _appHideShortcutsOverlayAdapter === 'function') _appHideShortcutsOverlayAdapter();
  }
}


function _syncOptionsSessionTokenStatusFallback() {
  const el = document.getElementById('options-session-token-status');
  const token = localStorage.getItem('session_token');
  const hasToken = Boolean(token);
  if (el) {
    el.textContent = hasToken && typeof _appMaskSessionTokenAdapter === 'function'
      ? _appMaskSessionTokenAdapter(token)
      : (hasToken ? token : 'No session token — anonymous session');
    el.classList.toggle('is-active', hasToken);
  }
  const generateBtn = document.getElementById('options-session-token-generate-btn');
  const rotateBtn = document.getElementById('options-session-token-rotate-btn');
  const clearBtn = document.getElementById('options-session-token-clear-btn');
  const copyBtn = document.getElementById('options-session-token-copy-btn');
  if (generateBtn) generateBtn.style.display = hasToken ? 'none' : '';
  if (rotateBtn) rotateBtn.style.display = hasToken ? '' : 'none';
  if (clearBtn) clearBtn.style.display = hasToken ? '' : 'none';
  if (copyBtn) copyBtn.style.display = hasToken ? '' : 'none';
}

function openOptions() {
  // Opening one major overlay should implicitly close the others so mobile and
  // desktop never stack multiple drawers/modals on top of each other.
  _closeMajorOverlays();
  if (typeof _appBlurVisibleComposerMobileAdapter === 'function') _appBlurVisibleComposerMobileAdapter();
  _appSyncOptionsControlsAdapter();
  if (typeof _appUpdateOptionsSessionTokenStatusAdapter === 'function') _appUpdateOptionsSessionTokenStatusAdapter();
  else _syncOptionsSessionTokenStatusFallback();
  _appShowOptionsOverlayAdapter();
  if (typeof _appMarkInteractionSurfaceReadyAdapter === 'function') {
    _appMarkInteractionSurfaceReadyAdapter('options', optionsOverlay, document.getElementById('options-modal'));
  }
  const panelsReady = typeof _appLoadOptionsPanelsAdapter === 'function'
    ? Promise.resolve(_appLoadOptionsPanelsAdapter())
    : Promise.resolve();
  panelsReady.then((panels) => {
    const updateSessionTokenStatus = panels?._updateOptionsSessionTokenStatus
      || (typeof _appUpdateOptionsSessionTokenStatusAdapter === 'function' ? _appUpdateOptionsSessionTokenStatusAdapter : null);
    const refreshSecrets = panels?.refreshOptionsSecrets
      || (typeof _appRefreshOptionsSecretsAdapter === 'function' ? _appRefreshOptionsSecretsAdapter : null);
    const refreshTeams = panels?.refreshOptionsTeams
      || (typeof _appRefreshOptionsTeamsAdapter === 'function' ? _appRefreshOptionsTeamsAdapter : null);
    const refreshNotifications = panels?.refreshNotificationChannels
      || (typeof _appRefreshNotificationChannelsAdapter === 'function' ? _appRefreshNotificationChannelsAdapter : null);
    if (typeof updateSessionTokenStatus === 'function') updateSessionTokenStatus();
    if (typeof refreshSecrets === 'function') {
      refreshSecrets().catch((err) => _appLogClientErrorAdapter('failed to load options secrets', err));
    }
    const activeTab = document.querySelector('[data-options-tab][aria-selected="true"]')?.dataset?.optionsTab;
    if (activeTab === 'teams' && typeof refreshTeams === 'function') {
      refreshTeams().catch((err) => _appLogClientErrorAdapter('failed to load options teams', err));
    }
    if (activeTab === 'notifications' && typeof refreshNotifications === 'function') {
      refreshNotifications().catch((err) => _appLogClientErrorAdapter('failed to load notification channels', err));
    }
  }).catch((err) => _appLogClientErrorAdapter('failed to load options panels', err));
}

function closeOptions() {
  _appHideOptionsOverlayAdapter();
  _appRefocusComposerAdapter({ defer: true });
}

function openThemeSelector() {
  _closeMajorOverlays();
  if (typeof _appBlurVisibleComposerMobileAdapter === 'function') _appBlurVisibleComposerMobileAdapter();
  _appRenderThemeSelectionOptionsAdapter();
  _appSyncThemeSelectionControlsAdapter();
  _appShowThemeOverlayAdapter();
  setTimeout(() => {
    const selectedCard = themeSelect && themeSelect.querySelector('.theme-card-active');
    const target = selectedCard || themeSelect?.querySelector('[data-theme-name]');
    if (!_appFocusElementAdapter(target, { preventScroll: true })) {
      _appFocusElementAdapter(themeSelect, { preventScroll: true });
    }
    if (typeof _appMarkInteractionSurfaceReadyAdapter === 'function') {
      _appMarkInteractionSurfaceReadyAdapter('theme', themeOverlay, document.getElementById('theme-modal'));
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
  return isEditableTarget(target) && target !== cmdInput;
}

function createNextTabLabel() {
  if (typeof _appCreateDefaultTabLabelAdapter === 'function') {
    const label = _appCreateDefaultTabLabelAdapter();
    if (typeof label === 'string' && label) return label;
  }
  return 'shell ' + (_appTabs().length + 1);
}

function createShortcutTab() {
  _appCreateTabAdapter(createNextTabLabel());
}

function activateRelativeTab(offset) {
  const tabs = _appTabs();
  const activeTabId = _appActiveTabId();
  if (!Array.isArray(tabs) || !tabs.length) return;
  const currentIndex = tabs.findIndex(tab => tab.id === activeTabId);
  const baseIndex = currentIndex >= 0 ? currentIndex : 0;
  const nextIndex = (baseIndex + offset + tabs.length) % tabs.length;
  _appActivateTabAdapter(tabs[nextIndex].id);
}

function closeActiveShortcutTab() {
  const closeActiveTab = typeof importedCloseTab === 'function'
    ? (typeof _appCloseTabAdapter === 'function' ? _appCloseTabAdapter : importedCloseTab)
    : (typeof _appCloseTabAdapter === 'function' ? _appCloseTabAdapter : null);
  const activeTabId = _appActiveTabId();
  if (!activeTabId || !closeActiveTab) return;
  closeActiveTab(activeTabId);
}

function permalinkActiveShortcutTab() {
  const permalinkActiveTab = typeof importedPermalinkTab === 'function'
    ? (typeof _appPermalinkTabAdapter === 'function' ? _appPermalinkTabAdapter : importedPermalinkTab)
    : (typeof _appPermalinkTabAdapter === 'function' ? _appPermalinkTabAdapter : null);
  const activeTabId = _appActiveTabId();
  if (!activeTabId || !permalinkActiveTab) return;
  permalinkActiveTab(activeTabId);
}

function copyActiveShortcutTab() {
  const copyActiveTab = typeof importedCopyTab === 'function'
    ? (typeof _appCopyTabAdapter === 'function' ? _appCopyTabAdapter : importedCopyTab)
    : (typeof _appCopyTabAdapter === 'function' ? _appCopyTabAdapter : null);
  const activeTabId = _appActiveTabId();
  if (!activeTabId || !copyActiveTab) return;
  copyActiveTab(activeTabId);
}

function clearActiveShortcutTab() {
  const activeTabId = _appActiveTabId();
  if (!activeTabId) return;
  const cancel = typeof importedCancelWelcome === 'function'
    ? (typeof _appCancelWelcomeAdapter === 'function' ? _appCancelWelcomeAdapter : importedCancelWelcome)
    : (typeof _appCancelWelcomeAdapter === 'function' ? _appCancelWelcomeAdapter : null);
  if (typeof cancel === 'function') cancel(activeTabId);
  const activeTab = typeof _appGetActiveTabAdapter === 'function' ? _appGetActiveTabAdapter() : null;
  _appClearTabAdapter(activeTabId, { preserveRunState: !!(activeTab && activeTab.st === 'running') });
}

function isStatusMonitorShortcutOpen() {
  if (typeof _appIsStatusMonitorOpenAdapter === 'function') return _appIsStatusMonitorOpenAdapter();
  const monitor = document.getElementById('status-monitor');
  return !!(monitor && !monitor.classList.contains('u-hidden'));
}

function _buildShareRedactionRememberField() {
  const field = document.createElement('div');
  field.className = 'faq-item modal-inline-field';
  const fieldset = document.createElement('div');
  fieldset.className = 'faq-a form-fieldset';
  const choice = document.createElement('label');
  choice.className = 'form-check';
  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.id = 'share-redaction-remember-toggle';
  const text = document.createElement('span');
  text.textContent = 'Set this as my default share-snapshot choice';
  choice.appendChild(checkbox);
  choice.appendChild(text);
  fieldset.appendChild(choice);
  field.appendChild(fieldset);
  return { field, checkbox };
}

async function confirmPermalinkRedactionChoice() {
  if (_appConfig().share_redaction_enabled === false) return 'raw';
  const preferred = _appGetShareRedactionDefaultPreferenceAdapter();
  if (preferred === 'raw' || preferred === 'redacted') return preferred;

  if (typeof _appBlurVisibleComposerMobileAdapter === 'function') _appBlurVisibleComposerMobileAdapter();

  const { field, checkbox } = _buildShareRedactionRememberField();
  let choice = null;
  try {
    choice = await _appShowConfirmAdapter({
      body: {
        text: 'Create permalink with redaction enabled?',
        note: 'Redaction can mask common sensitive values such as IP addresses, host names, email addresses, bearer tokens, and any operator-defined share redaction rules before the snapshot is saved.',
      },
      content: field,
      actions: [
        { id: 'cancel',   label: 'Cancel',         role: 'cancel' },
        { id: 'raw',      label: 'Share Raw',      role: 'secondary' },
        { id: 'redacted', label: 'Share Redacted', role: 'primary' },
      ],
    });
  } catch (_) { choice = null; }

  if ((choice === 'raw' || choice === 'redacted') && checkbox.checked) {
    _appApplyShareRedactionDefaultPreferenceAdapter(choice);
  }
  if (choice === 'raw' || choice === 'redacted') return choice;
  return null;
}

function performMobileEditAction(action) {
  const input = (typeof _appGetVisibleComposerInputAdapter === 'function' && _appGetVisibleComposerInputAdapter()) || null;
  if (!input) return;
  if (document.activeElement !== input && typeof _appFocusAnyComposerInputAdapter === 'function') _appFocusAnyComposerInputAdapter({ preventScroll: true });

  // Mobile edit helpers are meant to adjust the existing command in place.
  // Suppress autocomplete for this synthetic input update so the dropdown
  // does not pop back up and cover the helper row itself.
  _setAutocompleteSuppressInputOnce(true);
  if (typeof _appHideAutocompleteAdapter === 'function') _appHideAutocompleteAdapter();

  const composer = getComposerStateSnapshot();
  const inputValue = input.value || '';
  const composerValue = composer && typeof composer.value === 'string' ? composer.value : null;
  const preferLiveInput = document.activeElement === input && composerValue !== inputValue;
  const value = preferLiveInput
    ? inputValue
    : (composerValue !== null ? composerValue : inputValue);
  const { start, end } = preferLiveInput || !composer
    ? getInputSelection(input, value)
    : getCmdSelection(value);
  let nextValue = value;
  let nextStart = start;
  let nextEnd = end;

  if (action === 'left') {
    const pos = Math.max(0, start - 1);
    nextStart = pos;
    nextEnd = pos;
  } else if (action === 'word-left') {
    const pos = findWordBoundaryLeft(value, start);
    nextStart = pos;
    nextEnd = pos;
  } else if (action === 'right') {
    const pos = Math.min(value.length, end + 1);
    nextStart = pos;
    nextEnd = pos;
  } else if (action === 'word-right') {
    const pos = findWordBoundaryRight(value, end);
    nextStart = pos;
    nextEnd = pos;
  } else if (action === 'home') {
    nextStart = 0;
    nextEnd = 0;
  } else if (action === 'end') {
    nextStart = value.length;
    nextEnd = value.length;
  } else if (action === 'delete-word') {
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
  } else if (action === 'delete-line') {
    nextValue = '';
    nextStart = 0;
    nextEnd = 0;
  }

  if (
    action === 'left'
    || action === 'right'
    || action === 'word-left'
    || action === 'word-right'
    || action === 'home'
    || action === 'end'
  ) {
    if (typeof _appSyncComposerSelectionAdapter === 'function') _appSyncComposerSelectionAdapter(nextStart, nextEnd, { input });
    else if (input && typeof input.setSelectionRange === 'function') input.setSelectionRange(nextStart, nextEnd);
    setTimeout(() => {
      if (!input || typeof input.setSelectionRange !== 'function') return;
      if (typeof document !== 'undefined' && document.activeElement !== input) return;
      if ((input.value || '') !== value) return;
      if (input.selectionStart === nextStart && input.selectionEnd === nextEnd) return;
      input.setSelectionRange(nextStart, nextEnd);
      if (typeof _appSetComposerStateAdapter === 'function') {
        _appSetComposerStateAdapter({
          value,
          selectionStart: nextStart,
          selectionEnd: nextEnd,
          activeInput: 'mobile',
        });
      }
      syncShellPrompt();
    }, 0);
  } else {
    _appSetComposerValueAdapter(nextValue, nextStart, nextEnd);
  }

  if (typeof _appFocusAnyComposerInputAdapter === 'function') setTimeout(() => _appFocusAnyComposerInputAdapter({ preventScroll: true }), 0);
}

// ── Timestamps ──
const _tsModes  = ['off', 'elapsed', 'clock'];
// Off drops the suffix (the active-dot indicator shows on/off); the active
// modes keep their name so elapsed and clock stay distinguishable at a glance.
const _tsLabels = { off: 'timestamps', elapsed: 'timestamps: elapsed', clock: 'timestamps: clock' };

function _setTsMode(mode) {
  // Timestamp mode is expressed via body classes so both active transcript
  // rendering and exported/permalink views can share the same styling model.
  const handledByOutput = typeof importedSetOutputTimestampMode === 'function' && importedSetOutputTimestampMode(mode);
  if (!handledByOutput) {
    document.body.classList.remove('ts-elapsed', 'ts-clock');
    if (mode === 'elapsed') document.body.classList.add('ts-elapsed');
    if (mode === 'clock')   document.body.classList.add('ts-clock');
    if (typeof _appSyncOutputPrefixesAdapter === 'function') _appSyncOutputPrefixesAdapter();
    try { _appRefreshFollowingOutputsAfterLayoutAdapter(); } catch (_) {}
  }
  const label = _tsLabels[mode];
  if (tsBtn) {
    tsBtn.textContent = label;
    tsBtn.classList.toggle('active', mode !== 'off');
    tsBtn.setAttribute('aria-pressed', mode !== 'off' ? 'true' : 'false');
  }
}

if (typeof window !== 'undefined') {
  if (typeof importedSetComposerPromptHandlers === 'function') {
    importedSetComposerPromptHandlers({
      getComposerPromptMode: () => _composerPromptMode,
      hidePromptUsernameSavedIndicator,
      setComposerPromptMode,
      showPromptUsernameSavedIndicator,
      syncShellPrompt,
    });
  }
  if (typeof importedSetShareRedactionHandlers === 'function') {
    importedSetShareRedactionHandlers({ confirmPermalinkRedactionChoice });
  }
  if (typeof importedSetOverlayActionHandlers === 'function') {
    importedSetOverlayActionHandlers({ closeMajorOverlays: _closeMajorOverlays });
  }
}

export {
  _tsModes,
  activateRelativeTab,
  clearActiveShortcutTab,
  closeOptions,
  closeActiveShortcutTab,
  closeThemeSelector,
  copyActiveShortcutTab,
  createShortcutTab,
  focusCommandInputFromGesture,
  hidePromptUsernameSavedIndicator,
  isEditableTarget,
  isStatusMonitorShortcutOpen,
  openOptions,
  openThemeSelector,
  permalinkActiveShortcutTab,
  performMobileEditAction,
  shouldIgnoreGlobalShortcutTarget,
};
