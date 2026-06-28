// ── Desktop UI controller ──
// Bootstraps the page, wires listeners, and coordinates the feature helpers.

import {
  getCmdSelection,
  replaceCmdRange,
} from './features/terminal/composer_editing.js';
import { setControllerActionHandlers as importedSetControllerActionHandlers } from './controller_action_bridge.js';
import {
  emitUiEvent,
  getActiveTabId as importedGetActiveTabId,
  getActiveTab,
  getAppState as importedGetAppState,
  getAutocompleteState as importedGetAutocompleteState,
  getTabs as importedGetTabs,
  getWelcomeState as importedGetWelcomeState,
  setAutocompleteState as importedSetAutocompleteState,
  setWelcomeState as importedSetWelcomeState,
} from './core/state.js';
import {
  cmdInput,
  commandCatalogCloseBtn,
  commandCatalogOverlay,
  commandRegistryCloseBtn,
  faqCloseBtn,
  faqOverlay,
  headerTitle,
  histClearAllBtn,
  historyCloseBtn,
  historyPanel,
  lnBtn,
  mobileCmdInput,
  mobileMenu,
  mobileRunBtn,
  mobileShellTranscript,
  newTabBtn,
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
  searchCaseBtn,
  searchCloseBtn,
  searchInput,
  searchNextBtn,
  searchPrevBtn,
  searchRegexBtn,
  searchScopeButtons,
  searchSummaryBtn,
  searchToggleBtn,
  shortcutsOverlay,
  themeCloseBtn,
  tsBtn,
  workflowsCloseBtn,
  workflowsOverlay,
  workspaceCancelEditBtn,
  workspaceCloseBtn,
  workspaceCloseViewerBtn,
  workspaceEditorOverlay,
  workspaceViewerOverlay,
} from './core/dom.js';
import {
  blurVisibleComposerInputIfMobile,
  focusElement,
  getComposerInputs,
  getComposerValue,
  hideFaqOverlay,
  hideHistoryPanel,
  hideMobileMenu,
  hideSearchBar,
  hideShortcutsOverlay,
  hideWorkflowsOverlay,
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
  markInteractionSurfaceReady,
  refocusComposerAfterAction,
  setComposerValue,
  setMobileKeyboardOpenState,
  showFaqOverlay,
  showMobileMenu,
  showSearchBar,
  showShortcutsOverlay,
  showWorkflowsOverlay,
  togglePanelOverlay,
} from './ui/ui_helpers.js';
import {
  bindDismissible,
  closeTopmostDismissible,
} from './ui/ui_dismissible.js';
import { bindFocusTrap } from './ui/ui_focus_trap.js';
import { bindMobileSheet } from './ui/mobile_sheet.js';
import { closeMajorOverlays as _closeMajorOverlays } from './ui/overlay_actions_bridge.js';
import {
  _tsModes,
  closeOptions,
  closeThemeSelector,
  createShortcutTab,
  hidePromptUsernameSavedIndicator,
  isEditableTarget,
} from './app.js';
import {
  _defaultThemeEntry,
  _findThemeEntry,
  _savedThemeName,
  applyThemeSelection,
  renderThemeSelectionOptions,
  syncThemeSelectionControls,
} from './features/theme/theme.js';
import {
  activateOptionsTab,
  applyCommandOutcomeSummariesPreference,
  applyCompareContextPreference,
  applyCompareViewModePreference,
  applyHudClockPreference,
  applyLineNumberPreference,
  applyProjectAutoLinkExternalRunsPreference,
  applyProjectAutoLinkRunEntitiesPreference,
  applyPromptUsernamePreference,
  applyRunNotifyPreference,
  applyShareRedactionDefaultPreference,
  applyTimestampPreference,
  applyWelcomeIntroPreference,
  getHudClockPreference,
  getPreference,
  getPromptUsernamePreference,
  getShareRedactionDefaultPreference,
  getWelcomeIntroPreference,
  loadSessionPreferences,
  syncOptionsControls,
  syncPromptUsernameValidation,
} from './features/preferences/preferences.js';
import {
  _seedLocalStorageStarsToServer,
  cancelPendingTerminalConfirm,
  confirmKill,
  hasPendingTerminalConfirm,
  interruptPromptLine,
  restoreActiveRunsAfterReload,
  runCommand,
  submitComposerCommand,
} from './runner.js';
import {
  applyFaqHashTarget,
  clearFaqHash,
  renderAllowedCommandsFaq,
  renderFaqItems,
  renderFaqLimits,
  setAllowedCommandsFaqData,
} from './features/command-registry/faq_helpers.js';
import {
  closeCommandCatalogModal as importedCloseCommandCatalogModal,
  closeCommandRegistry,
  isCommandCatalogOverlayOpen as importedIsCommandCatalogOverlayOpen,
  isCommandRegistryOverlayOpen,
  renderCommandRegistry,
  setCommandRegistryData as importedSetCommandRegistryData,
} from './features/command-registry/command_registry_bridge.js';
import {
  apiFetch,
  logClientError,
} from './session.js';
import {
  getLineNumberMode,
  getTimestampMode,
} from './output.js';
import {
  acAccept,
  acHide,
  acIsHintOnly,
  acNextSelectableIndex,
  acSelectableIndexes,
  acSelectableItems,
  acShow,
} from './autocomplete.js';
import {
  bindMobileComposerKeyboardListeners,
  bindMobileComposerSubmitAndInputListeners,
} from './features/terminal/mobile_composer_keyboard.js';
import {
  clearSearch,
  navigateSearch,
  prepareSearchBarForOpen,
  prepareSearchBarForScope,
  runSearch,
  scheduleRunSearch,
  setSearchScope,
  summarizeCurrentOutputSignals,
} from './search.js';
import {
  createDefaultTabLabel,
  createTab,
  setupTabScrollControls,
  updateNewTabBtn,
} from './tabs.js';
import {
  handleActionShortcut,
  handleChromeShortcut,
  handleTabShortcut,
} from './features/shortcuts/global_shortcuts.js';
import {
  hydrateCmdHistory,
  navigateCmdHistory,
} from './features/history/history_recall.js';
import {
  refreshHistoryPanel,
  resetHistoryMobileFilters,
  resetHistorySelectionOnClose,
} from './history.js';
import { loadStarredFromServer } from './features/history/history_actions.js';
import { confirmHistAction } from './features/history/history_mutations.js';
import { enterHistSearch } from './features/history/history_search.js';
import {
  closeAtlas as importedCloseAtlas,
  isAtlasOverlayOpen as importedIsAtlasOverlayOpen,
} from './features/atlas/atlas_bridge.js';
import { isHistoryRunOverlayOpen as importedIsHistoryRunOverlayOpen } from './features/history/history_run_modal_state_bridge.js';
import {
  requestWelcomeSettle,
  runWelcome,
  welcomeOwnsTab,
} from './welcome.js';
import { restoreTabSessionState } from './features/tabs/tab_session_state.js';
import { isConfirmOpen } from './ui/ui_confirm.js';
import {
  _uiOverlayRefs,
  isMobileKeyboardOpen,
  syncMobileViewportState,
  useMobileTerminalViewportMode,
} from './features/mobile/mobile_shell_layout.js';
import { dispatchMobileMenuAction } from './features/mobile/mobile_menu_actions.js';
import {
  closeWorkspace,
  hideWorkspaceEditor,
  hideWorkspaceViewer,
} from './workspace.js';
import {
  closeWorkflowEditor as importedCloseWorkflowEditor,
  ensureWorkflowCatalogLoaded as importedEnsureWorkflowCatalogLoaded,
  openWorkflowEditor as importedOpenWorkflowEditor,
  renderWorkflowItems as importedRenderWorkflowItems,
} from './features/workflows/workflows_bridge.js';
import {
  closeProviderStatusModal as importedCloseProviderStatusModal,
  hasSecretsHandler as importedHasSecretsHandler,
  isProviderStatusModalOpen as importedIsProviderStatusModalOpen,
} from './features/preferences/secrets_bridge.js';
import {
  closeProjectWorkspace as importedCloseProjectWorkspace,
  isProjectWorkspaceOpen as importedIsProjectWorkspaceOpen,
} from './features/projects/project_context_bridge.js';

const closeAtlas = (...args) => _controllerFn('closeAtlas', importedCloseAtlas)?.(...args);
const closeCommandCatalogModal = (...args) => _controllerFn(
  'closeCommandCatalogModal',
  importedCloseCommandCatalogModal
)?.(...args);
const closeProviderStatusModal = (...args) => {
  const fn = (
    typeof importedHasSecretsHandler === 'function'
    && importedHasSecretsHandler('closeProviderStatusModal')
    && typeof importedCloseProviderStatusModal === 'function'
  ) ? importedCloseProviderStatusModal : _controllerFn('closeProviderStatusModal');
  return typeof fn === 'function' ? fn(...args) : undefined;
};
const closeProjectWorkspace = (...args) => _controllerFn('closeProjectWorkspace', importedCloseProjectWorkspace)?.(...args);
const closeSchedulesModal = (...args) => _controllerFn('closeSchedulesModal')?.(...args);
const closeWatchersModal = (...args) => _controllerFn('closeWatchersModal')?.(...args);
const closeWorkflowEditor = (...args) => _controllerFn('closeWorkflowEditor', importedCloseWorkflowEditor)?.(...args);
const ensureWorkflowCatalogLoaded = (...args) => _controllerFn('ensureWorkflowCatalogLoaded', importedEnsureWorkflowCatalogLoaded)?.(...args);
const isAtlasOverlayOpen = (...args) => !!_controllerFn('isAtlasOverlayOpen', importedIsAtlasOverlayOpen)?.(...args);
const isCommandCatalogOverlayOpen = (...args) => !!_controllerFn(
  'isCommandCatalogOverlayOpen',
  importedIsCommandCatalogOverlayOpen
)?.(...args);
const isHistoryCompareOverlayOpen = (...args) => !!_controllerFn('isHistoryCompareOverlayOpen')?.(...args);
const isHistoryRunOverlayOpen = (...args) => !!_controllerFn('isHistoryRunOverlayOpen', importedIsHistoryRunOverlayOpen)?.(...args);
const isProviderStatusModalOpen = (...args) => {
  const fn = (
    typeof importedHasSecretsHandler === 'function'
    && importedHasSecretsHandler('isProviderStatusModalOpen')
    && typeof importedIsProviderStatusModalOpen === 'function'
  ) ? importedIsProviderStatusModalOpen : _controllerFn('isProviderStatusModalOpen');
  return !!fn?.(...args);
};
const isProjectWorkspaceOpen = (...args) => !!_controllerFn('isProjectWorkspaceOpen', importedIsProjectWorkspaceOpen)?.(...args);
const isSchedulesOverlayOpen = (...args) => !!_controllerFn('isSchedulesOverlayOpen')?.(...args);
const isWatchersOverlayOpen = (...args) => !!_controllerFn('isWatchersOverlayOpen')?.(...args);
const loadWorkflows = (...args) => _controllerFn('loadWorkflows')?.(...args);
const openWorkflowEditor = (...args) => _controllerFn('openWorkflowEditor', importedOpenWorkflowEditor)?.(...args);
const renderWorkflowItems = (...args) => _controllerFn('renderWorkflowItems', importedRenderWorkflowItems)?.(...args);

const CONTROLLER_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _controllerFn(name, imported = null) {
  if (typeof imported === 'function') return imported;
  const fn = CONTROLLER_GLOBAL && CONTROLLER_GLOBAL[name];
  return typeof fn === 'function' ? fn : null;
}

function _controllerActiveTabId() {
  const importedValue = typeof importedGetActiveTabId === 'function' ? importedGetActiveTabId() : null;
  if (importedValue) return importedValue;
  const readActive = CONTROLLER_GLOBAL && CONTROLLER_GLOBAL.getActiveTabId;
  if (typeof readActive === 'function') {
    const value = readActive();
    if (value) return value;
  }
  return CONTROLLER_GLOBAL?.activeTabId || CONTROLLER_GLOBAL?.APP_STATE?.activeTabId || null;
}

function _controllerTabs() {
  const tabs = _controllerFn('getTabs', importedGetTabs)?.();
  return Array.isArray(tabs) ? tabs : [];
}

function _controllerState() {
  return _controllerFn('getAppState', importedGetAppState)?.() || {};
}

function _controllerWelcomeState() {
  return _controllerFn('getWelcomeState', importedGetWelcomeState)?.() || {};
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
  return _controllerFn('setWelcomeState', importedSetWelcomeState)?.(next);
}

function _controllerAutocompleteState() {
  return _controllerFn('getAutocompleteState', importedGetAutocompleteState)?.() || {};
}

function _controllerSetAutocompleteState(next) {
  return _controllerFn('setAutocompleteState', importedSetAutocompleteState)?.(next);
}

let _controllerCommandRegistryData = null;

function _controllerSetCommandRegistryData(data) {
  _controllerCommandRegistryData = data || null;
  if (typeof importedSetCommandRegistryData === 'function') importedSetCommandRegistryData(data);
  return _controllerCommandRegistryData;
}

renderThemeSelectionOptions();
const initialThemeName = _savedThemeName();
const initialTheme = initialThemeName ? _findThemeEntry(initialThemeName) : null;
const resolvedInitialTheme = initialTheme || _defaultThemeEntry();
if (resolvedInitialTheme) applyThemeSelection(resolvedInitialTheme.name, false);
else syncThemeSelectionControls();

function _welcomeApi(name) {
  return (typeof window !== 'undefined' && window[name])
    || (typeof globalThis !== 'undefined' && globalThis[name])
    || (name === 'runWelcome' && typeof runWelcome !== 'undefined' ? runWelcome : null)
    || (name === 'welcomeOwnsTab' && typeof welcomeOwnsTab !== 'undefined' ? welcomeOwnsTab : null)
    || (name === 'requestWelcomeSettle' && typeof requestWelcomeSettle !== 'undefined' ? requestWelcomeSettle : null);
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
  const owns = _welcomeApi('welcomeOwnsTab');
  return typeof owns === 'function' && owns(tabId);
}

function _requestWelcomeSettle(tabId) {
  const settle = _welcomeApi('requestWelcomeSettle');
  return typeof settle === 'function' ? settle(tabId) : false;
}

function _readControllerAutocompleteState() {
  const apiState = _controllerAutocompleteState();
  return {
    filtered: Array.isArray(apiState.filtered) ? apiState.filtered : [],
    index: apiState.index ?? -1,
  };
}

function _writeControllerAutocompleteState(next = {}) {
  _controllerSetAutocompleteState(next);
  return _readControllerAutocompleteState();
}

function _runWelcomeIntro() {
  const run = _welcomeApi('runWelcome');
  if (typeof run === 'function') run();
}

tsBtn.addEventListener('click', () => {
  const current = typeof getTimestampMode === 'function' ? getTimestampMode() : 'off';
  applyTimestampPreference(_tsModes[(_tsModes.indexOf(current) + 1) % _tsModes.length]);
  refocusComposerAfterAction({ defer: true });
});

lnBtn.addEventListener('click', () => {
  const current = typeof getLineNumberMode === 'function' ? getLineNumberMode() : 'off';
  applyLineNumberPreference(current === 'on' ? 'off' : 'on');
  refocusComposerAfterAction({ defer: true });
});

function openWorkflows(options = {}) {
  _closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  const scopedItems = Array.isArray(options.items) ? options.items : null;
  if (workflowsOverlay) {
    if (scopedItems) workflowsOverlay.dataset.workflowScoped = '1';
    else delete workflowsOverlay.dataset.workflowScoped;
  }
  showWorkflowsOverlay();
  if (scopedItems) {
    if (typeof renderWorkflowItems === 'function') {
      renderWorkflowItems(scopedItems, { emitCatalogEvent: options.emitCatalogEvent !== false });
    }
    if (typeof markInteractionSurfaceReady === 'function') {
      markInteractionSurfaceReady('workflows', workflowsOverlay, document.getElementById('workflows-modal'));
    }
    return Promise.resolve(scopedItems);
  }
  const workflowsReady = typeof loadWorkflows === 'function'
    ? loadWorkflows()
    : Promise.resolve();
  return workflowsReady.then(() => {
    if (typeof ensureWorkflowCatalogLoaded !== 'function') return null;
    return ensureWorkflowCatalogLoaded().catch(err => {
      logClientError('failed to load /workflows while opening modal', err);
      return null;
    });
  }).catch(err => {
    logClientError('failed to load workflows controller', err);
  }).finally(() => {
    if (typeof markInteractionSurfaceReady === 'function') {
      markInteractionSurfaceReady('workflows', workflowsOverlay, document.getElementById('workflows-modal'));
    }
  });
}

function closeWorkflows() {
  if (workflowsOverlay) delete workflowsOverlay.dataset.workflowScoped;
  hideWorkflowsOverlay();
  if (typeof emitUiEvent === 'function') emitUiEvent('app:workflows-closed', {});
  refocusComposerAfterAction({ defer: true });
}

function openWorkflowEditorFromButton() {
  if (typeof openWorkflowEditor === 'function') {
    openWorkflowEditor();
  } else if (typeof loadWorkflows === 'function') {
    loadWorkflows()
      .then(() => {
        if (typeof openWorkflowEditor === 'function') openWorkflowEditor();
      })
      .catch(err => {
        logClientError('failed to load workflow editor', err);
      });
  }
}

document.querySelectorAll('#workflow-new-btn, #rail-workflow-new-btn').forEach(btn => {
  if (btn.dataset.workflowEditorOpenBound === '1') return;
  btn.dataset.workflowEditorOpenBound = '1';
  btn.addEventListener('click', openWorkflowEditorFromButton);
});

function openFaq() {
  _closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  showFaqOverlay();
  if (typeof applyFaqHashTarget === 'function') applyFaqHashTarget();
  if (typeof markInteractionSurfaceReady === 'function') {
    markInteractionSurfaceReady('faq', faqOverlay, document.getElementById('faq-modal'));
  }
}

function closeFaq() {
  if (typeof clearFaqHash === 'function') clearFaqHash();
  hideFaqOverlay();
  refocusComposerAfterAction({ defer: true });
}

function closeCommandRegistryPanel() {
  if (typeof closeCommandRegistry === 'function') closeCommandRegistry();
}

function openShortcuts() {
  _closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  if (typeof showShortcutsOverlay === 'function') showShortcutsOverlay();
  if (typeof markInteractionSurfaceReady === 'function') {
    markInteractionSurfaceReady('shortcuts', shortcutsOverlay, document.getElementById('shortcuts-modal'));
  }
}

function closeShortcuts() {
  if (typeof hideShortcutsOverlay === 'function') hideShortcutsOverlay();
  refocusComposerAfterAction({ defer: true });
}

function toggleHistoryPanelSurface(force = null) {
  _closeMajorOverlays();
  const isOpen = togglePanelOverlay(historyPanel, force);
  if (isOpen) {
    if (typeof resetHistoryMobileFilters === 'function') resetHistoryMobileFilters();
    if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
    refreshHistoryPanel();
  } else {
    if (typeof resetHistorySelectionOnClose === 'function') resetHistorySelectionOnClose();
    refocusComposerAfterAction({ defer: true });
  }
  return isOpen;
}


function renderShortcuts(data) {
  const listEl = document.getElementById('shortcuts-list');
  if (!listEl) return;
  listEl.textContent = '';
  const sections = Array.isArray(data && data.sections) ? data.sections : [];
  for (const section of sections) {
    const items = Array.isArray(section && section.items) ? section.items : [];
    if (!items.length) continue;
    const sectionEl = document.createElement('div');
    sectionEl.className = 'shortcuts-section';
    const headingEl = document.createElement('div');
    headingEl.className = 'shortcut-section-title';
    headingEl.textContent = section.title || '';
    sectionEl.appendChild(headingEl);
    const pairsEl = document.createElement('div');
    pairsEl.className = 'shortcuts-pairs';
    for (const item of items) {
      const keyEl = document.createElement('div');
      keyEl.className = 'shortcut-key';
      keyEl.textContent = item.key || '';
      const descEl = document.createElement('div');
      descEl.className = 'shortcut-desc';
      descEl.textContent = item.description || '';
      pairsEl.appendChild(keyEl);
      pairsEl.appendChild(descEl);
    }
    sectionEl.appendChild(pairsEl);
    listEl.appendChild(sectionEl);
  }
}

function setupMobileSheetDragClose() {
  // All sheet drag/tap/keyboard close behavior lives in mobile_sheet.js so the
  // wiring per sheet stays a one-liner and behavior cannot drift between them.
  if (typeof bindMobileSheet !== 'function') return;
  const faqModal = document.getElementById('faq-modal');
  const optionsModal = document.getElementById('options-modal');
  const workspaceModal = document.getElementById('workspace-modal');
  const workflowsModal = document.getElementById('workflows-modal');
  const workflowEditor = document.getElementById('workflow-editor-form');
  const projectWorkspaceModal = document.getElementById('project-workspace-modal');
  const providerStatusModal = document.getElementById('provider-status-modal');
  const atlasSurface = document.getElementById('atlas-surface');
  const schedulesModal = document.getElementById('schedules-modal');
  const watchersModal = document.getElementById('watchers-modal');

  bindMobileSheet(mobileMenu,         { onClose: () => hideMobileMenu() });
  bindMobileSheet(historyPanel,       { onClose: () => hideHistoryPanel() });
  bindMobileSheet(workflowsModal,     { onClose: () => closeWorkflows() });
  bindMobileSheet(workspaceModal,     { onClose: () => { if (typeof closeWorkspace === 'function') closeWorkspace(); } });
  bindMobileSheet(workflowEditor,     { onClose: () => { if (typeof closeWorkflowEditor === 'function') closeWorkflowEditor(); } });
  bindMobileSheet(faqModal,           { onClose: () => closeFaq() });
  bindMobileSheet(document.getElementById('command-registry-modal'), { onClose: () => closeCommandRegistryPanel() });
  bindMobileSheet(projectWorkspaceModal, { onClose: () => { if (typeof closeProjectWorkspace === 'function') closeProjectWorkspace(); } });
  bindMobileSheet(optionsModal,       { onClose: () => closeOptions() });
  bindMobileSheet(providerStatusModal, { onClose: () => { if (typeof closeProviderStatusModal === 'function') closeProviderStatusModal(); } });
  bindMobileSheet(atlasSurface,       { onClose: () => { if (typeof closeAtlas === 'function') closeAtlas(); } });
  bindMobileSheet(schedulesModal,     { onClose: () => { if (typeof closeSchedulesModal === 'function') closeSchedulesModal(); } });
  bindMobileSheet(watchersModal,      { onClose: () => { if (typeof closeWatchersModal === 'function') closeWatchersModal(); } });
}

function setupDismissibleOverlays() {
  // Each overlay/modal surface is registered with bindDismissible so
  // backdrop click + explicit close button + Escape are owned by one
  // helper (app/static/js/ui/ui_dismissible.js). The Escape cascade
  // dispatcher (closeTopmostDismissible) enforces modal > sheet > panel
  // priority declaratively instead of the hand-rolled if-chain this
  // setup replaces.
  if (typeof bindDismissible !== 'function') return;
  const shortcutsOverlayEl = document.getElementById('shortcuts-overlay');
  const shortcutsCloseBtn = shortcutsOverlayEl?.querySelector('.shortcuts-close');
  const workflowEditorOverlay = document.getElementById('workflow-editor-overlay');
  const workflowEditorCloseBtns = workflowEditorOverlay?.querySelectorAll('.workflow-editor-close');
  const projectWorkspaceOverlay = document.getElementById('project-workspace-overlay');
  const projectWorkspaceCloseBtn = projectWorkspaceOverlay?.querySelector('.project-workspace-close');
  const providerStatusOverlay = document.getElementById('provider-status-overlay');
  const providerStatusCloseBtn = providerStatusOverlay?.querySelector('.provider-status-close');
  const schedulesOverlay = document.getElementById('schedules-overlay');
  const schedulesCloseBtns = schedulesOverlay?.querySelectorAll('.schedules-close, .sheet-grab');
  const watchersOverlay = document.getElementById('watchers-overlay');
  const watchersCloseBtns = watchersOverlay?.querySelectorAll('.watchers-close, .sheet-grab');

  bindDismissible(_uiOverlayRefs.workflowsOverlay, {
    level: 'panel',
    isOpen: isWorkflowsOverlayOpen,
    onClose: closeWorkflows,
    closeButtons: workflowsCloseBtn,
  });
  bindDismissible(_uiOverlayRefs.workspaceOverlay, {
    level: 'panel',
    isOpen: () => !!(
      _uiOverlayRefs.workspaceOverlay
      && _uiOverlayRefs.workspaceOverlay.classList.contains('open')
    ),
    onClose: () => { if (typeof closeWorkspace === 'function') closeWorkspace(); },
    closeButtons: typeof workspaceCloseBtn !== 'undefined' ? workspaceCloseBtn : null,
  });
  bindDismissible(_uiOverlayRefs.workspaceViewerOverlay, {
    level: 'modal',
    isOpen: () => (
      typeof workspaceViewerOverlay !== 'undefined'
      && workspaceViewerOverlay
      && !workspaceViewerOverlay.classList.contains('u-hidden')
    ),
    onClose: () => { if (typeof hideWorkspaceViewer === 'function') hideWorkspaceViewer(); },
    closeButtons: typeof workspaceCloseViewerBtn !== 'undefined' ? workspaceCloseViewerBtn : null,
  });
  bindDismissible(_uiOverlayRefs.workspaceEditorOverlay, {
    level: 'modal',
    isOpen: () => (
      typeof workspaceEditorOverlay !== 'undefined'
      && workspaceEditorOverlay
      && !workspaceEditorOverlay.classList.contains('u-hidden')
    ),
    onClose: () => { if (typeof hideWorkspaceEditor === 'function') hideWorkspaceEditor(); },
    closeButtons: typeof workspaceCancelEditBtn !== 'undefined' ? workspaceCancelEditBtn : null,
  });
  bindDismissible(workflowEditorOverlay, {
    level: 'modal',
    isOpen: () => !!(workflowEditorOverlay && !workflowEditorOverlay.classList.contains('u-hidden')),
    onClose: () => { if (typeof closeWorkflowEditor === 'function') closeWorkflowEditor(); },
    closeButtons: workflowEditorCloseBtns,
  });
  bindDismissible(_uiOverlayRefs.faqOverlay, {
    level: 'panel',
    isOpen: isFaqOverlayOpen,
    onClose: closeFaq,
    closeButtons: faqCloseBtn,
  });
  bindDismissible(_uiOverlayRefs.commandRegistryOverlay, {
    level: 'panel',
    isOpen: () => typeof isCommandRegistryOverlayOpen === 'function' && isCommandRegistryOverlayOpen(),
    onClose: closeCommandRegistryPanel,
    closeButtons: typeof commandRegistryCloseBtn !== 'undefined' ? commandRegistryCloseBtn : null,
  });
  bindDismissible(projectWorkspaceOverlay, {
    level: 'modal',
    isOpen: () => typeof isProjectWorkspaceOpen === 'function' && isProjectWorkspaceOpen(),
    onClose: () => { if (typeof closeProjectWorkspace === 'function') closeProjectWorkspace(); },
    closeButtons: projectWorkspaceCloseBtn,
  });
  bindDismissible(commandCatalogOverlay, {
    level: 'modal',
    isOpen: () => typeof isCommandCatalogOverlayOpen === 'function' && isCommandCatalogOverlayOpen(),
    onClose: () => { if (typeof closeCommandCatalogModal === 'function') closeCommandCatalogModal(); },
    closeButtons: commandCatalogCloseBtn,
  });
  bindDismissible(providerStatusOverlay, {
    level: 'modal',
    isOpen: () => typeof isProviderStatusModalOpen === 'function' && isProviderStatusModalOpen(),
    onClose: () => { if (typeof closeProviderStatusModal === 'function') closeProviderStatusModal(); },
    closeButtons: providerStatusCloseBtn,
  });
  bindDismissible(schedulesOverlay, {
    level: 'modal',
    isOpen: () => typeof isSchedulesOverlayOpen === 'function' && isSchedulesOverlayOpen(),
    onClose: () => { if (typeof closeSchedulesModal === 'function') closeSchedulesModal(); },
    closeButtons: schedulesCloseBtns,
  });
  bindDismissible(watchersOverlay, {
    level: 'modal',
    isOpen: () => typeof isWatchersOverlayOpen === 'function' && isWatchersOverlayOpen(),
    onClose: () => { if (typeof closeWatchersModal === 'function') closeWatchersModal(); },
    closeButtons: watchersCloseBtns,
  });
  bindDismissible(_uiOverlayRefs.themeOverlay, {
    level: 'panel',
    isOpen: isThemeOverlayOpen,
    onClose: closeThemeSelector,
    closeButtons: themeCloseBtn,
  });
  bindDismissible(_uiOverlayRefs.optionsOverlay, {
    level: 'panel',
    isOpen: isOptionsOverlayOpen,
    onClose: closeOptions,
    closeButtons: optionsCloseBtn,
  });
  bindDismissible(shortcutsOverlayEl, {
    level: 'panel',
    isOpen: isShortcutsOverlayOpen,
    onClose: closeShortcuts,
    closeButtons: shortcutsCloseBtn,
  });
  bindDismissible(historyPanel, {
    level: 'panel',
    isOpen: isHistoryPanelOpen,
    onClose: () => {
      if (typeof resetHistoryMobileFilters === 'function') resetHistoryMobileFilters();
      hideHistoryPanel();
    },
    closeButtons: historyCloseBtn,
    // historyPanel is an aside, not a modal backdrop — outside click
    // dismissal is handled by the ambient-click listener in the global
    // click handler below, not by backdrop-click here.
    closeOnBackdrop: false,
  });
}

function setupModalFocusTraps() {
  // Keep Tab / Shift+Tab cycling inside each modal card while its overlay is
  // open — otherwise focus falls through to the rail / tabs / HUD behind the
  // backdrop. #confirm-host wires its own focus trap per-open through
  // showConfirm() because the card's focusables change between shows; the
  // app-level modals have persistent DOM, so a one-shot idempotent bind
  // at startup is equivalent. bindFocusTrap is a no-op when the card is
  // hidden (display: none on the overlay wrapper), so the listener is only
  // reachable while the modal is open.
  if (typeof bindFocusTrap !== 'function') return;
  const ids = [
    'options-modal',
    'theme-modal',
    'faq-modal',
    'command-registry-modal',
    'provider-status-modal',
    'findings-board-modal',
    'finding-triage-modal',
    'atlas-import-modal',
    'project-workspace-modal',
    'project-target-editor-modal',
    'project-package-manifest-modal',
    'project-package-wizard-modal',
    'project-entity-editor-modal',
    'workspace-modal',
    'workflows-modal',
    'workflow-editor-form',
    'schedules-modal',
    'watchers-modal',
    'team-scope-modal',
  ];
  ids.forEach((id) => {
    const card = document.getElementById(id);
    if (card) bindFocusTrap(card);
  });
}

function setupMobileComposer() {
  // The mobile composer reuses the same shared input state as desktop, but its
  // focus/keyboard handling has to be managed separately for mobile browsers.
  const composerInputs = typeof getComposerInputs === 'function' ? getComposerInputs() : {};
  const mobileInput = composerInputs.mobile || null;
  if (!mobileInput || !mobileRunBtn) return;
  bindMobileComposerSubmitAndInputListeners(mobileInput);
  bindMobileComposerKeyboardListeners(mobileInput);
  if (mobileShellTranscript) {
    const closeKeyboardFromTranscript = e => {
      const interactiveTarget = e && e.target && e.target.closest
        && e.target.closest('button, a, input, textarea, select, [contenteditable="true"], .hist-chip');
      if (interactiveTarget) return;
      if (isMobileKeyboardOpen() && typeof blurVisibleComposerInputIfMobile === 'function') {
        if (typeof setMobileKeyboardOpenState === 'function') setMobileKeyboardOpenState(false, { delay: 120 });
        blurVisibleComposerInputIfMobile();
      }
    };
    mobileShellTranscript.addEventListener('click', closeKeyboardFromTranscript);
  }
}

// ── Load config from server ──
apiFetch('/config').then(r => r.json()).then(cfg => {
  if (
    typeof window !== 'undefined'
    && window.DarklabConfig
    && typeof window.DarklabConfig.setAppConfig === 'function'
  ) {
    window.DarklabConfig.setAppConfig(cfg);
  } else if (typeof window !== 'undefined') {
    window.APP_CONFIG = cfg;
  }
  document.title = cfg.app_name;
  if (headerTitle) headerTitle.textContent = cfg.app_name;
  const railWordmarkTitle = document.getElementById('rail-wordmark-title');
  if (railWordmarkTitle) {
    railWordmarkTitle.textContent = cfg.app_name;
    railWordmarkTitle.title = cfg.app_name;
  }
  const wmVersion = cfg.version ? ` v${cfg.version}` : '';
  const projectText = `${cfg.project_name || 'darklab_shell'}${wmVersion}`;
  document.querySelectorAll('.menu-footer, .rail-nav-version').forEach(el => {
    el.textContent = projectText;
    if (cfg.project_readme) el.href = cfg.project_readme;
  });
  syncThemeSelectionControls();
  updateNewTabBtn();
  if (typeof renderFaqLimits === 'function') renderFaqLimits(cfg);
  if (cfg.diag_enabled) {
    const railDiagBtn = document.getElementById('rail-diag-btn');
    if (railDiagBtn) railDiagBtn.classList.remove('u-hidden');
    const mobileDiagBtn = _uiOverlayRefs.mobileMenu?.querySelector('button[data-menu-action="diag"]');
    if (mobileDiagBtn) mobileDiagBtn.classList.remove('u-hidden');
  }
}).catch(err => {
  logClientError('failed to load /config', err);
});

// ── Hamburger menu (mobile) ──
_uiOverlayRefs.hamburgerBtn.addEventListener('click', e => {
  e.stopPropagation();
  if (isMobileMenuOpen()) hideMobileMenu();
  else showMobileMenu();
});

_uiOverlayRefs.mobileMenu?.querySelectorAll('button[data-menu-action]').forEach(btn => {
  btn.addEventListener('click', () => {
    const action = btn.dataset.menuAction;
    // ts-toggle keeps the sheet open; its whole purpose is to expand an inline
    // sub-menu beneath the timestamps row. Every other action closes the sheet
    // as it transitions to another surface.
    if (action !== 'ts-toggle') hideMobileMenu();
    dispatchMobileMenuAction(action, btn);
  });
});

// Theme + Options: backdrop + close button dismissal is registered via
// bindDismissible in setupDismissibleOverlays(); only the open triggers
// live here.
optionsTabs?.addEventListener('click', e => {
  const tab = e.target.closest?.('[data-options-tab]');
  if (!tab) return;
  activateOptionsTab(tab.dataset.optionsTab, { persist: true, focus: true });
});
optionsTabs?.addEventListener('keydown', e => {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
  const tabs = Array.from(optionsTabs.querySelectorAll('[data-options-tab]'));
  const currentIndex = tabs.indexOf(document.activeElement);
  if (!tabs.length || currentIndex < 0) return;
  e.preventDefault();
  let nextIndex = currentIndex;
  if (e.key === 'Home') nextIndex = 0;
  else if (e.key === 'End') nextIndex = tabs.length - 1;
  else if (e.key === 'ArrowRight') nextIndex = (currentIndex + 1) % tabs.length;
  else nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
  const nextTab = tabs[nextIndex];
  activateOptionsTab(nextTab.dataset.optionsTab, { persist: true, focus: true });
});
optionsTsSelect?.addEventListener('change', e => {
  applyTimestampPreference(e.target.value);
});
optionsLnToggle?.addEventListener('change', e => {
  applyLineNumberPreference(e.target.checked ? 'on' : 'off');
});
optionsWelcomeSelect?.addEventListener('change', e => {
  applyWelcomeIntroPreference(e.target.value);
});
optionsShareRedactionSelect?.addEventListener('change', e => {
  applyShareRedactionDefaultPreference(e.target.value);
});
optionsNotifyToggle?.addEventListener('change', e => {
  applyRunNotifyPreference(e.target.checked ? 'on' : 'off');
});
optionsCommandOutcomeSummariesToggle?.addEventListener('change', e => {
  applyCommandOutcomeSummariesPreference(e.target.checked ? 'on' : 'off');
});
optionsProjectAutoLinkExternalRunsToggle?.addEventListener('change', e => {
  applyProjectAutoLinkExternalRunsPreference(e.target.checked ? 'on' : 'off');
});
optionsProjectAutoLinkRunEntitiesToggle?.addEventListener('change', e => {
  applyProjectAutoLinkRunEntitiesPreference(e.target.checked ? 'on' : 'off');
});
optionsHudClockSelect?.addEventListener('change', e => {
  applyHudClockPreference(e.target.value);
});
optionsCompareViewModeSelect?.addEventListener('change', e => {
  applyCompareViewModePreference(e.target.value);
});
optionsCompareContextSelect?.addEventListener('change', e => {
  applyCompareContextPreference(e.target.value);
});
let promptUsernameAutosaveTimer = null;
const PROMPT_USERNAME_AUTOSAVE_DELAY_MS = 300;
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
optionsPromptUsernameInput?.addEventListener('input', () => {
  if (typeof hidePromptUsernameSavedIndicator === 'function') hidePromptUsernameSavedIndicator();
  if (syncPromptUsernameValidation()) schedulePromptUsernameAutosave(optionsPromptUsernameInput.value);
  else clearPromptUsernameAutosave();
});
optionsPromptUsernameInput?.addEventListener('change', e => {
  if (syncPromptUsernameValidation()) {
    clearPromptUsernameAutosave();
    applyPromptUsernamePreference(e.target.value);
  }
});

apiFetch('/allowed-commands').then(r => r.json()).then(data => {
  if (typeof setAllowedCommandsFaqData === 'function') setAllowedCommandsFaqData(data);
  if (typeof renderAllowedCommandsFaq === 'function') renderAllowedCommandsFaq(data);
}).catch(err => {
  logClientError('failed to load /allowed-commands', err);
});

apiFetch('/commands/catalog').then(r => r.json()).then(data => {
  _controllerSetCommandRegistryData(data);
  if (typeof isCommandRegistryOverlayOpen === 'function' && isCommandRegistryOverlayOpen()) {
    if (typeof renderCommandRegistry === 'function') renderCommandRegistry();
  }
}).catch(err => {
  logClientError('failed to load /commands/catalog', err);
  _controllerSetCommandRegistryData({ restricted: false, commands: [], groups: [] });
});

apiFetch('/faq').then(r => r.json()).then(data => {
  if (typeof renderFaqItems === 'function') renderFaqItems(data.items || []);
}).catch(err => {
  logClientError('failed to load /faq', err);
});

apiFetch('/shortcuts').then(r => r.json()).then(data => {
  renderShortcuts(data || {});
}).catch(err => {
  logClientError('failed to load /shortcuts', err);
});

const workflowsLoad = apiFetch('/workflows').then(r => r.json()).then(data => {
  const items = data.items || [];
  if (typeof renderWorkflowItems === 'function') renderWorkflowItems(items);
});
workflowsLoad.catch(err => {
  logClientError('failed to load /workflows', err);
});

loadStarredFromServer().catch(err => {
  logClientError('failed to load /session/starred', err);
});

// Migrate any legacy stars from localStorage to the server, and clean up the
// stale key for users who never trigger a session change.
if (typeof _seedLocalStorageStarsToServer === 'function') {
  _seedLocalStorageStarsToServer().catch(err => {
    logClientError('failed to seed localStorage stars', err);
  });
}

// ── Tabs ──
setupTabScrollControls();
applyTimestampPreference(getPreference('pref_timestamps') || 'off', false);
applyLineNumberPreference(getPreference('pref_line_numbers') || 'off', false);
applyWelcomeIntroPreference(getWelcomeIntroPreference(), false);
applyShareRedactionDefaultPreference(getShareRedactionDefaultPreference(), false);
applyHudClockPreference(getHudClockPreference(), false);
applyPromptUsernamePreference(getPromptUsernamePreference(), false);
syncOptionsControls();
const sessionPreferencesLoad = typeof loadSessionPreferences === 'function'
  ? loadSessionPreferences().catch(err => {
    logClientError('failed to apply session preferences', err);
  })
  : Promise.resolve();

const commandHistoryLimit = encodeURIComponent(String(APP_CONFIG.recent_commands_limit || 50));
Promise.all([
  sessionPreferencesLoad,
  apiFetch(`/history/commands?limit=${commandHistoryLimit}`).then(r => r.json()).catch(err => {
    logClientError('failed to load /history/commands', err);
    return { runs: [] };
  }),
  apiFetch('/history/active').then(r => r.json()).catch(err => {
    logClientError('failed to load /history/active', err);
    return { runs: [] };
  }),
]).then(([, historyData, activeData]) => {
  hydrateCmdHistory(historyData.runs || []);
  const restoredTabs = typeof restoreTabSessionState === 'function'
    && restoreTabSessionState();
  const restoredActiveRuns = typeof restoreActiveRunsAfterReload === 'function'
    && restoreActiveRunsAfterReload(activeData.runs || []);
  if (!restoredTabs && !restoredActiveRuns && (!_controllerTabs().length)) {
    createTab(typeof createDefaultTabLabel === 'function' ? createDefaultTabLabel(1) : 'shell 1');
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

newTabBtn.addEventListener('click', () => {
  createShortcutTab();
});

function openSearchFromSignal(scope = null) {
  const normalizedScope = scope || null;
  if (
    normalizedScope
    && typeof isSearchBarOpen === 'function'
    && isSearchBarOpen()
    && _controllerState().searchScope === normalizedScope
  ) {
    navigateSearch(1);
    refocusComposerAfterAction({ defer: true });
    return;
  }
  if (typeof prepareSearchBarForScope === 'function' && normalizedScope) {
    prepareSearchBarForScope(normalizedScope);
  } else if (typeof prepareSearchBarForOpen === 'function') {
    prepareSearchBarForOpen();
  }
  showSearchBar();
  if (_controllerState().searchScope === 'text') focusElement(searchInput);
  else refocusComposerAfterAction({ defer: true });
  runSearch();
}

if (typeof window !== 'undefined') {
}

// ── Search ──
searchToggleBtn.addEventListener('click', () => {
  const visible = isSearchBarOpen();
  if (visible) {
    hideSearchBar();
    clearSearch();
  } else {
    openSearchFromSignal();
  }
});

if (typeof searchSummaryBtn !== 'undefined' && searchSummaryBtn) {
  searchSummaryBtn.addEventListener('click', () => {
    if (typeof summarizeCurrentOutputSignals === 'function') summarizeCurrentOutputSignals();
    refocusComposerAfterAction({ defer: true });
  });
}

searchInput.addEventListener('input', () => {
  if (typeof scheduleRunSearch === 'function') scheduleRunSearch();
  else runSearch();
});
searchPrevBtn.addEventListener('click', () => navigateSearch(-1));
searchNextBtn.addEventListener('click', () => navigateSearch(1));
if (typeof searchScopeButtons !== 'undefined' && Array.isArray(searchScopeButtons)) {
  searchScopeButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      setSearchScope(btn.dataset.searchScope || 'text');
      if (_controllerState().searchScope === 'text') focusElement(searchInput);
      else refocusComposerAfterAction({ defer: true });
    });
  });
}
searchCloseBtn?.addEventListener('click', () => {
  hideSearchBar();
  clearSearch();
});
searchInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    e.preventDefault();
    navigateSearch(e.shiftKey ? -1 : 1);
  }
  if (e.key === 'Escape') {
    hideSearchBar();
    clearSearch();
    refocusComposerAfterAction({ defer: true });
  }
});

searchCaseBtn.addEventListener('click', () => {
  const next = !_controllerSearchCaseSensitive();
  _controllerSetSearchCaseSensitive(next);
  searchCaseBtn.setAttribute('aria-pressed', next ? 'true' : 'false');
  runSearch();
});

searchRegexBtn.addEventListener('click', () => {
  const next = !_controllerSearchRegexMode();
  _controllerSetSearchRegexMode(next);
  searchRegexBtn.setAttribute('aria-pressed', next ? 'true' : 'false');
  runSearch();
});

// ── Run history panel ──
// history panel close button + outside-area dismissal are registered via
// bindDismissible in setupDismissibleOverlays().

// ── History delete modal ──
// The modal itself lives in ui_confirm.js — confirmHistAction() builds
// the action list and resolves the choice. Only the entry-point button
// for the bulk clear path lives here.
histClearAllBtn.addEventListener('click', () => {
  confirmHistAction('clear');
});


// ── Global keyboard shortcuts ──
// Current bindings intentionally stay narrow:
// - Ctrl+C: running => kill confirm, idle => fresh prompt line
// - welcome settle: printable typing, Enter, Escape
// - Escape: close FAQ/options and search UI
//
// App-safe key bindings stay narrow:
// - Alt+T / Alt+W for new/close tab
// - Alt+Tab / Alt+Shift+Tab for tab cycling (forward/backward)
// - Alt+Shift+ArrowLeft / Alt+Shift+ArrowRight for tab cycling
// - Alt+P for permalink, Alt+Shift+C for copy
// Confirmation dialogs (kill, history-delete, share-redaction, ...) use
// default-focus-on-cancel so Enter resolves to the safe action via the
// browser's native button activation. Escape is routed through the
// dismissible dispatcher below.
// Browser-native combos like Ctrl/Cmd+T or Ctrl/Cmd+W remain environment-dependent.
function hasActiveTerminalConfirm() {
  return typeof hasPendingTerminalConfirm === 'function' && hasPendingTerminalConfirm();
}

function isAnyPanelOverlayOpen() {
  return (typeof isFaqOverlayOpen === 'function' && isFaqOverlayOpen())
    || (typeof isWorkflowsOverlayOpen === 'function' && isWorkflowsOverlayOpen())
    || (typeof isWorkspaceOverlayOpen === 'function' && isWorkspaceOverlayOpen())
    || (typeof isSchedulesOverlayOpen === 'function' && isSchedulesOverlayOpen())
    || (typeof isWatchersOverlayOpen === 'function' && isWatchersOverlayOpen())
    || (typeof isHistoryCompareOverlayOpen === 'function' && isHistoryCompareOverlayOpen())
    || (typeof isHistoryRunOverlayOpen === 'function' && isHistoryRunOverlayOpen())
    || (typeof isOptionsOverlayOpen === 'function' && isOptionsOverlayOpen())
    || (typeof isThemeOverlayOpen === 'function' && isThemeOverlayOpen());
}

document.addEventListener('keydown', e => {
  if (e.defaultPrevented) return;
  // Unified Escape dispatch: closes the topmost open dismissible
  // (modal > sheet > panel) via the registry populated by
  // setupDismissibleOverlays(). Replaces the per-overlay if-chain that
  // used to live here.
  if (e.key === 'Escape' && typeof closeTopmostDismissible === 'function' && closeTopmostDismissible()) {
    e.preventDefault();
    return;
  }
  // When a major panel is open, swallow non-chrome keys so shortcuts
  // don't dispatch behind the overlay. Chrome shortcuts (Alt+H, Alt+G,
  // Alt+, etc.) still fire so the opening chord can also close the
  // surface.
  if (
    isFaqOverlayOpen()
    || isOptionsOverlayOpen()
    || isThemeOverlayOpen()
    || isWorkflowsOverlayOpen()
    || (typeof isWorkspaceOverlayOpen === 'function' && isWorkspaceOverlayOpen())
    || (typeof isSchedulesOverlayOpen === 'function' && isSchedulesOverlayOpen())
    || (typeof isWatchersOverlayOpen === 'function' && isWatchersOverlayOpen())
    || isHistoryPanelOpen()
    || (typeof isAtlasOverlayOpen === 'function' && isAtlasOverlayOpen())
    || (typeof isHistoryCompareOverlayOpen === 'function' && isHistoryCompareOverlayOpen())
    || (typeof isHistoryRunOverlayOpen === 'function' && isHistoryRunOverlayOpen())
  ) {
    if (handleTabShortcut(e, { surfaceOnly: true })) return;
    if (handleChromeShortcut(e)) return;
    return;
  }
  if (_welcomeActiveNow() && !_welcomeDoneNow() && _welcomeOwns(_controllerActiveTabId())) {
    const editableWelcomeTarget = isEditableTarget(e.target);
    const composerWelcomeTarget = e.target === cmdInput || (typeof mobileCmdInput !== 'undefined' && e.target === mobileCmdInput);
    if (editableWelcomeTarget && !composerWelcomeTarget) return;
    const isCtrlC = e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'c' || e.key === 'C');
    const isSpace = e.key === ' ' || e.code === 'Space';
    const isPrintable = !e.metaKey && !e.ctrlKey && !e.altKey && !isEditableTarget(e.target) && e.key.length === 1;
    if (isCtrlC) {
      _setWelcomePromptAfterSettle(true);
      _requestWelcomeSettle(_controllerActiveTabId());
      refocusComposerAfterAction({ defer: true });
      e.preventDefault();
      return;
    }
    if (e.key === 'Escape' || e.key === 'Enter' || isSpace) {
      _requestWelcomeSettle(_controllerActiveTabId());
      refocusComposerAfterAction({ defer: true });
      e.preventDefault();
      return;
    }
    if (isPrintable) {
      _requestWelcomeSettle(_controllerActiveTabId());
      refocusComposerAfterAction({ defer: true });
      setComposerValue((typeof getComposerValue === 'function' ? getComposerValue() : '') + e.key);
      e.preventDefault();
      return;
    }
  }
  if (handleTabShortcut(e)) return;
  if (handleActionShortcut(e)) return;
  if (handleChromeShortcut(e)) return;
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'c' || e.key === 'C')) {
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
    if (activeTab && activeTab.st === 'running') {
      confirmKill(_controllerActiveTabId());
    } else if (hasActiveTerminalConfirm()) {
      cancelPendingTerminalConfirm(_controllerActiveTabId());
    } else {
      interruptPromptLine(_controllerActiveTabId());
    }
    e.preventDefault();
    return;
  }
  if (
    typeof isActiveTabRunning === 'function'
    && isActiveTabRunning()
    && !(typeof isConfirmOpen === 'function' && isConfirmOpen())
    && !isEditableTarget(e.target)
    && !e.metaKey
    && !e.ctrlKey
    && !e.altKey
    && (e.key.length === 1 || e.key === 'Enter' || e.key === 'Tab' || e.key === 'Backspace' || e.key === 'Delete')
  ) {
    if (typeof acHide === 'function') acHide();
    e.preventDefault();
    return;
  }
  if (
    _welcomeActiveNow() && !_welcomeDoneNow() && _welcomeOwns(_controllerActiveTabId())
    && cmdInput
    && !e.metaKey && !e.ctrlKey && !e.altKey
    && !isEditableTarget(e.target)
    && e.key.length === 1
  ) {
    _requestWelcomeSettle(_controllerActiveTabId());
    refocusComposerAfterAction({ defer: true });
    setComposerValue((typeof getComposerValue === 'function' ? getComposerValue() : '') + e.key);
    e.preventDefault();
    return;
  }
  if (e.key === 'Enter' && _welcomeActiveNow() && !_welcomeDoneNow() && _welcomeOwns(_controllerActiveTabId())) {
    if ((typeof getComposerValue === 'function' ? getComposerValue() : '').trim()) return;
    _requestWelcomeSettle(_controllerActiveTabId());
    refocusComposerAfterAction({ defer: true });
    e.preventDefault();
    return;
  }
  if (e.key === 'Escape' && _welcomeActiveNow() && !_welcomeDoneNow() && _welcomeOwns(_controllerActiveTabId())) {
    _requestWelcomeSettle(_controllerActiveTabId());
    refocusComposerAfterAction({ defer: true });
    e.preventDefault();
    return;
  }
  if (e.key === 'Escape') {
    // Dismissibles are closed by the unified Escape dispatch at the top
    // of this handler; only the search-bar and search-term clears
    // remain, since those are not registered surfaces.
    hideSearchBar();
    clearSearch();
  }

  if (_replayPromptShortcutAfterSelection(e)) return;

  // If a printable key lands outside the command input (e.g. user had text selected
  // in the output), forward it to the prompt so no keystroke is lost.
  if (
    e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey && !e.isComposing
    && document.activeElement !== cmdInput
    && !isEditableTarget(e.target)
    && !(e.target && e.target.closest && e.target.closest('button, a, select'))
    && cmdInput
    && !isFaqOverlayOpen() && !isWorkflowsOverlayOpen() && !isOptionsOverlayOpen() && !isThemeOverlayOpen()
    && !(typeof isWorkspaceOverlayOpen === 'function' && isWorkspaceOverlayOpen())
    && !(typeof isSchedulesOverlayOpen === 'function' && isSchedulesOverlayOpen())
    && !(typeof isWatchersOverlayOpen === 'function' && isWatchersOverlayOpen())
    && !(typeof isHistoryCompareOverlayOpen === 'function' && isHistoryCompareOverlayOpen())
    && !(typeof isHistoryRunOverlayOpen === 'function' && isHistoryRunOverlayOpen())
    && !(typeof isConfirmOpen === 'function' && isConfirmOpen())
  ) {
    e.preventDefault();
    refocusComposerAfterAction({ preventScroll: true });
    const value = typeof getComposerValue === 'function' ? getComposerValue() : (cmdInput.value || '');
    const { start, end } = getCmdSelection(value);
    replaceCmdRange(value, start, end, e.key);
  }
});

function acAutocompleteIsHintOnly(item) {
  if (typeof acIsHintOnly === 'function') return acIsHintOnly(item);
  return !!(item && typeof item === 'object' && item.hintOnly);
}

function acAutocompleteSelectableItems(items) {
  if (typeof acSelectableItems === 'function') return acSelectableItems(items);
  return (Array.isArray(items) ? items : []).filter(item => !acAutocompleteIsHintOnly(item));
}

function acAutocompleteSelectableIndexes(items) {
  if (typeof acSelectableIndexes === 'function') return acSelectableIndexes(items);
  return (Array.isArray(items) ? items : [])
    .map((item, index) => (acAutocompleteIsHintOnly(item) ? -1 : index))
    .filter(index => index >= 0);
}

function acAutocompleteNextSelectableIndex(items, currentIndex, direction = 1) {
  if (typeof acNextSelectableIndex === 'function') {
    return acNextSelectableIndex(items, currentIndex, direction);
  }
  const indexes = acAutocompleteSelectableIndexes(items);
  if (!indexes.length) return -1;
  const currentPos = indexes.indexOf(currentIndex);
  if (currentPos < 0) return direction < 0 ? indexes[indexes.length - 1] : indexes[0];
  const nextPos = direction < 0
    ? (currentPos <= 0 ? indexes.length - 1 : currentPos - 1)
    : ((currentPos + 1) % indexes.length);
  return indexes[nextPos];
}

function _replayPromptShortcutAfterSelection(e) {
  // If the user has selected terminal output text, re-dispatch prompt-oriented
  // shortcuts so shell navigation still works after copy/select interactions.
  if (!cmdInput || document.activeElement === cmdInput) return false;
  if (isEditableTarget(e.target)) return false;
  const isCtrlR = e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'r' || e.key === 'R');
  const isSelectionShortcut = e.key === 'Enter' || e.key === 'ArrowDown' || e.key === 'ArrowUp' || isCtrlR;
  if (!isSelectionShortcut) return false;
  const selection = typeof window !== 'undefined' && typeof window.getSelection === 'function'
    ? window.getSelection()
    : null;
  const selectedText = selection && typeof selection.toString === 'function' ? selection.toString() : '';
  if (!selectedText) return false;

  e.preventDefault();
  refocusComposerAfterAction({ preventScroll: true });
  if (isCtrlR) {
    if (typeof enterHistSearch === 'function') enterHistSearch();
    return true;
  }
  if (e.key === 'ArrowDown') {
    if (hasActiveTerminalConfirm()) {
      if (typeof acHide === 'function') acHide();
      return true;
    }
    const acState = _readControllerAutocompleteState();
    if (isAcDropdownOpen() && acAutocompleteSelectableItems(acState.filtered).length) {
      const nextIndex = acAutocompleteNextSelectableIndex(acState.filtered, acState.index, 1);
      _writeControllerAutocompleteState({ index: nextIndex });
      if (typeof acShow === 'function') acShow(acState.filtered);
    } else if (typeof navigateCmdHistory === 'function' && navigateCmdHistory(-1)) {
      if (typeof acHide === 'function') acHide();
    }
    return true;
  }
  if (e.key === 'ArrowUp') {
    if (hasActiveTerminalConfirm()) {
      if (typeof acHide === 'function') acHide();
      return true;
    }
    const acState = _readControllerAutocompleteState();
    if (isAcDropdownOpen() && acAutocompleteSelectableItems(acState.filtered).length) {
      const nextIndex = acAutocompleteNextSelectableIndex(acState.filtered, acState.index, -1);
      _writeControllerAutocompleteState({ index: nextIndex });
      if (typeof acShow === 'function') acShow(acState.filtered);
    } else if (typeof navigateCmdHistory === 'function' && navigateCmdHistory(1)) {
      if (typeof acHide === 'function') acHide();
    }
    return true;
  }
  if (e.key === 'Enter') {
    const acState = _readControllerAutocompleteState();
    if (acState.index >= 0 && acState.filtered[acState.index] && !acAutocompleteIsHintOnly(acState.filtered[acState.index])) {
      if (typeof acAccept === 'function') acAccept(acState.filtered[acState.index]);
    } else {
      if (typeof acHide === 'function') acHide();
      if (typeof submitComposerCommand === 'function') {
        submitComposerCommand(typeof getComposerValue === 'function' ? getComposerValue() : (cmdInput.value || ''), { dismissKeyboard: true });
      } else if (typeof runCommand === 'function') {
        runCommand();
      }
    }
    return true;
  }
  return true;
}

if (typeof window !== 'undefined') {
  Object.assign(window, {
  });
  if (typeof importedSetControllerActionHandlers === 'function') {
    importedSetControllerActionHandlers({
      closeFaq,
      closeWorkflows,
      openFaq,
      openWorkflows,
      toggleHistoryPanelSurface,
    });
  }
}

export {
  acAutocompleteIsHintOnly,
  acAutocompleteNextSelectableIndex,
  acAutocompleteSelectableItems,
  closeShortcuts,
  hasActiveTerminalConfirm,
  isAnyPanelOverlayOpen,
  openFaq,
  openShortcuts,
  openWorkflows,
  setupMobileComposer,
  toggleHistoryPanelSurface,
};
