// ── Terminal composer controller ──
// Owns prompt focus/paste behavior, autocomplete loading, and keyboard handling.

import {
  findWordBoundaryLeft,
  findWordBoundaryRight,
  getCmdSelection,
  replaceCmdRange,
} from './composer_editing.js';
import {
  _bindMobileComposerInteractions,
  _mobileUiLayoutRefs,
  syncMobileViewportState,
  useMobileTerminalViewportMode,
} from '../mobile/mobile_shell_layout.js';
import { refreshWorkspaceFileCache as importedRefreshWorkspaceFileCache } from '../workspace/workspace_autocomplete_cache.js';
import { loadSessionVariables as importedLoadSessionVariables } from '../autocomplete/runtime_context.js';
import {
  loadProjectAutocompleteTargets as importedLoadProjectAutocompleteTargets,
  loadRecentValues as importedLoadRecentValues,
  loadScheduleAutocompleteHints as importedLoadScheduleAutocompleteHints,
  loadWatcherAutocompleteHints as importedLoadWatcherAutocompleteHints,
  setAutocompleteCatalog as importedSetAutocompleteCatalog,
} from '../autocomplete/suggestions.js';
import {
  apiFetch as importedApiFetch,
  logClientError as importedLogClientError,
} from '../../session.js';
import { schedulePersistTabSessionState as importedSchedulePersistTabSessionState } from '../tabs/tab_session_state.js';
import { isHistoryRunOverlayOpen as importedIsHistoryRunOverlayOpen } from '../history/history_run_modal_state_bridge.js';
import {
  enterHistSearch as importedEnterHistSearch,
  handleHistSearchInput as importedHandleHistSearchInput,
  handleHistSearchKey as importedHandleHistSearchKey,
  isHistSearchMode as importedIsHistSearchMode,
} from '../history/history_search.js';
import { navigateCmdHistory as importedNavigateCmdHistory } from '../history/history_recall.js';
import {
  hasComposerPromptHandler as importedHasComposerPromptHandler,
  syncShellPrompt as importedSyncShellPrompt,
} from './composer_prompt_bridge.js';
import {
  eventMatchesCode as importedEventMatchesCode,
  eventMatchesLetter as importedEventMatchesLetter,
  handleActionShortcut as importedHandleActionShortcut,
  handleChromeShortcut as importedHandleChromeShortcut,
  handleTabShortcut as importedHandleTabShortcut,
} from '../shortcuts/global_shortcuts.js';
import {
  acAutocompleteIsHintOnly as importedAcAutocompleteIsHintOnly,
  acAutocompleteNextSelectableIndex as importedAcAutocompleteNextSelectableIndex,
  acAutocompleteSelectableItems as importedAcAutocompleteSelectableItems,
  hasActiveTerminalConfirm as importedHasActiveTerminalConfirm,
  isAnyPanelOverlayOpen as importedIsAnyPanelOverlayOpen,
  setupMobileComposer as importedSetupMobileComposer,
} from '../../controller.js';
import {
  closeOptions as importedCloseOptions,
  closeThemeSelector as importedCloseThemeSelector,
  focusCommandInputFromGesture as importedFocusCommandInputFromGesture,
  isEditableTarget as importedIsEditableTarget,
} from '../../app.js';
import {
  closeWorkspace as importedCloseWorkspace,
} from '../../workspace_bridge.js';
import {
  closeFaq as importedCloseFaq,
  closeWorkflows as importedCloseWorkflows,
} from '../../controller_action_bridge.js';
import { bindOutsideClickClose as importedBindOutsideClickClose } from '../../ui/ui_outside_click.js';
import {
  getComposerInputs as importedGetComposerInputs,
  getComposerValue as importedGetComposerValue,
  getVisibleComposerInput as importedGetVisibleComposerInput,
  handleComposerInputChange as importedHandleComposerInputChange,
  hideHistoryPanel as importedHideHistoryPanel,
  isAcDropdownOpen as importedIsAcDropdownOpen,
  isActiveTabRunning as importedIsActiveTabRunning,
  isFaqOverlayOpen as importedIsFaqOverlayOpen,
  isHistoryPanelOpen as importedIsHistoryPanelOpen,
  isOptionsOverlayOpen as importedIsOptionsOverlayOpen,
  isThemeOverlayOpen as importedIsThemeOverlayOpen,
  isWorkflowsOverlayOpen as importedIsWorkflowsOverlayOpen,
  isWorkspaceOverlayOpen as importedIsWorkspaceOverlayOpen,
  normalizeComposerSmartPeriod as importedNormalizeComposerSmartPeriod,
  refocusComposerAfterAction as importedRefocusComposerAfterAction,
  syncComposerSelection as importedSyncComposerSelection,
  syncFocusedComposerState as importedSyncFocusedComposerState,
  syncRunButtonDisabled as importedSyncRunButtonDisabled,
} from '../../ui/ui_helpers.js';
import { closeTopmostDismissible as importedCloseTopmostDismissible } from '../../ui/ui_dismissible.js';
import {
  cancelPendingTerminalConfirm as importedCancelPendingTerminalConfirm,
  confirmKill as importedConfirmKill,
  interruptPromptLine as importedInterruptPromptLine,
  runCommand as importedRunCommand,
  submitComposerCommand as importedSubmitComposerCommand,
} from '../../runner_bridge.js';
import {
  cmdInput as importedCmdInput,
  historyPanel as importedHistoryPanel,
  runBtn as importedRunBtn,
  shellPromptWrap as importedShellPromptWrap,
} from '../../core/dom.js';
import {
  APP_STATE_API as importedAppStateApi,
  getActiveTab as importedGetActiveTab,
  getActiveTabId as importedGetActiveTabId,
  getAutocompleteState as importedGetAutocompleteState,
  getComposerState as importedGetComposerState,
  getWelcomeState as importedGetWelcomeState,
  setAutocompleteState as importedSetAutocompleteState,
  setComposerState as importedSetComposerState,
  setWelcomeState as importedSetWelcomeState,
} from '../../core/state.js';
import {
  requestWelcomeSettle as importedRequestWelcomeSettle,
  welcomeOwnsTab as importedWelcomeOwnsTab,
} from '../../welcome_bridge.js';

const COMPOSER_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

var cmdInput = importedCmdInput || COMPOSER_GLOBAL.cmdInput || null;
var historyPanel = importedHistoryPanel || COMPOSER_GLOBAL.historyPanel || null;
var runBtn = importedRunBtn || COMPOSER_GLOBAL.runBtn || null;
var shellPromptWrap = importedShellPromptWrap || COMPOSER_GLOBAL.shellPromptWrap || null;

function _composerFn(name) {
  const fn = COMPOSER_GLOBAL && COMPOSER_GLOBAL[name];
  return typeof fn === 'function' ? fn : null;
}

function _composerImportedFn(importedFn, name) {
  return (typeof importedFn === 'function' && importedFn) || _composerFn(name);
}

function _composerFocusCommandInputFromGesture(...args) {
  return _composerImportedFn(
    importedFocusCommandInputFromGesture,
    'focusCommandInputFromGesture',
  )?.(...args);
}

function _composerHasActiveTerminalConfirm() {
  return !!_composerImportedFn(importedHasActiveTerminalConfirm, 'hasActiveTerminalConfirm')?.();
}

function _composerIsAnyPanelOverlayOpen() {
  return !!_composerImportedFn(importedIsAnyPanelOverlayOpen, 'isAnyPanelOverlayOpen')?.();
}

function _composerCloseTopmostDismissible() {
  return !!_composerImportedFn(importedCloseTopmostDismissible, 'closeTopmostDismissible')?.();
}

function _composerAutocompleteIsHintOnly(item) {
  return !!_composerImportedFn(importedAcAutocompleteIsHintOnly, 'acAutocompleteIsHintOnly')?.(item);
}

function _composerAutocompleteSelectableItems(items) {
  return _composerImportedFn(importedAcAutocompleteSelectableItems, 'acAutocompleteSelectableItems')?.(items) || [];
}

function _composerAutocompleteNextSelectableIndex(items, currentIndex, direction = 1) {
  return _composerImportedFn(
    importedAcAutocompleteNextSelectableIndex,
    'acAutocompleteNextSelectableIndex',
  )?.(items, currentIndex, direction) ?? -1;
}

function _composerIsHistSearchMode() {
  return !!_composerImportedFn(importedIsHistSearchMode, 'isHistSearchMode')?.();
}

function _composerNavigateCmdHistory(delta) {
  const navigate = (typeof importedNavigateCmdHistory === 'function' && importedNavigateCmdHistory)
    || _composerFn('navigateCmdHistory');
  return typeof navigate === 'function' && navigate(delta);
}

function _composerEnterHistSearch() {
  _composerImportedFn(importedEnterHistSearch, 'enterHistSearch')?.();
}

function _composerHandleHistSearchInput(value) {
  _composerImportedFn(importedHandleHistSearchInput, 'handleHistSearchInput')?.(value);
}

function _composerHandleHistSearchKey(event) {
  return !!_composerImportedFn(importedHandleHistSearchKey, 'handleHistSearchKey')?.(event);
}

function _composerSetupMobileComposer() {
  _composerImportedFn(importedSetupMobileComposer, 'setupMobileComposer')?.();
}

function _composerIsEditableTarget(target) {
  return !!_composerImportedFn(importedIsEditableTarget, 'isEditableTarget')?.(target);
}

function _composerCloseOptions() {
  _composerImportedFn(importedCloseOptions, 'closeOptions')?.();
}

function _composerCloseThemeSelector() {
  _composerImportedFn(importedCloseThemeSelector, 'closeThemeSelector')?.();
}

function _composerValue(name) {
  return COMPOSER_GLOBAL ? COMPOSER_GLOBAL[name] : undefined;
}

function _composerAppStateApi() {
  return importedAppStateApi || _composerValue('APP_STATE_API') || null;
}

function _composerActiveTabId() {
  const getId = (typeof importedGetActiveTabId === 'function' && importedGetActiveTabId)
    || _composerFn('getActiveTabId');
  return typeof getId === 'function' ? getId() : (_composerValue('activeTabId') || null);
}

function _composerActiveTab() {
  const getActive = (typeof importedGetActiveTab === 'function' && importedGetActiveTab)
    || _composerFn('getActiveTab');
  return typeof getActive === 'function' ? getActive() : null;
}

function _composerSetState(next = {}) {
  const setState = (typeof importedSetComposerState === 'function' && importedSetComposerState)
    || _composerFn('setComposerState');
  return typeof setState === 'function' ? setState(next) : null;
}

function _composerInputs() {
  const readInputs = (typeof importedGetComposerInputs === 'function' && importedGetComposerInputs)
    || _composerFn('getComposerInputs');
  return typeof readInputs === 'function' ? readInputs() : {};
}

function _composerGetValue(fallback = '') {
  const readValue = (typeof importedGetComposerValue === 'function' && importedGetComposerValue)
    || _composerFn('getComposerValue');
  if (typeof readValue === 'function') {
    const value = readValue();
    if (value || !(cmdInput && typeof cmdInput.value === 'string' && cmdInput.value)) return value;
  }
  const composer = typeof importedGetComposerState === 'function' ? importedGetComposerState() : null;
  if (composer && typeof composer.value === 'string') return composer.value;
  if (cmdInput && typeof cmdInput.value === 'string') return cmdInput.value;
  return fallback;
}

function _composerVisibleInput() {
  const readInput = (typeof importedGetVisibleComposerInput === 'function' && importedGetVisibleComposerInput)
    || _composerFn('getVisibleComposerInput');
  return typeof readInput === 'function' ? readInput() : cmdInput;
}

function _composerSyncShellPrompt() {
  const syncPrompt = (
    typeof importedHasComposerPromptHandler === 'function'
    && importedHasComposerPromptHandler('syncShellPrompt')
  ) ? importedSyncShellPrompt : _composerFn('syncShellPrompt');
  if (typeof syncPrompt === 'function') syncPrompt();
}

function _composerSyncSelection(start, end, options) {
  const syncSelection = (typeof importedSyncComposerSelection === 'function' && importedSyncComposerSelection)
    || _composerFn('syncComposerSelection');
  if (typeof syncSelection === 'function') return syncSelection(start, end, options);
  return null;
}

function _composerAcHide() {
  const hide = _composerFn('acHide');
  if (typeof hide === 'function') hide();
}

function _composerRefocus(options) {
  const refocus = (typeof importedRefocusComposerAfterAction === 'function' && importedRefocusComposerAfterAction)
    || _composerFn('refocusComposerAfterAction');
  if (typeof refocus === 'function') refocus(options);
}

function _composerSubmitCommand(rawCmd, options) {
  const submitCommand = (typeof importedSubmitComposerCommand === 'function' && importedSubmitComposerCommand)
    || _composerFn('submitComposerCommand');
  if (typeof submitCommand === 'function') return submitCommand(rawCmd, options);
  const run = (typeof importedRunCommand === 'function' && importedRunCommand)
    || _composerFn('runCommand');
  return typeof run === 'function' ? run() : undefined;
}

function _refreshWorkspaceFileCache() {
  const refresh = (typeof importedRefreshWorkspaceFileCache !== 'undefined' && importedRefreshWorkspaceFileCache)
    || _composerFn('refreshWorkspaceFileCache');
  if (typeof refresh === 'function') return refresh();
  return null;
}

function _isMajorSurfaceOpenForPromptPaste() {
  return (
    (_composerImportedFn(importedIsFaqOverlayOpen, 'isFaqOverlayOpen')?.() || false)
    || (_composerImportedFn(importedIsOptionsOverlayOpen, 'isOptionsOverlayOpen')?.() || false)
    || (_composerImportedFn(importedIsThemeOverlayOpen, 'isThemeOverlayOpen')?.() || false)
    || (_composerImportedFn(importedIsWorkflowsOverlayOpen, 'isWorkflowsOverlayOpen')?.() || false)
    || (_composerImportedFn(importedIsWorkspaceOverlayOpen, 'isWorkspaceOverlayOpen')?.() || false)
    || (_composerFn('isHistoryCompareOverlayOpen')?.() || false)
    || (_composerImportedFn(importedIsHistoryRunOverlayOpen, 'isHistoryRunOverlayOpen')?.() || false)
    || (_composerFn('isHistoryPanelOpen')?.() || false)
    || (_composerFn('isConfirmOpen')?.() || false)
  );
}

function _readComposerAutocompleteState() {
  const getState = (typeof importedGetAutocompleteState === 'function' && importedGetAutocompleteState)
    || _composerFn('getAutocompleteState');
  const apiState = typeof getState === 'function' ? getState() : {};
  return {
    filtered: Array.isArray(apiState.filtered) ? apiState.filtered : [],
    index: apiState.index ?? -1,
  };
}

function _writeComposerAutocompleteState(next = {}) {
  const setState = (typeof importedSetAutocompleteState === 'function' && importedSetAutocompleteState)
    || _composerFn('setAutocompleteState');
  if (typeof setState === 'function') setState(next);
  return _readComposerAutocompleteState();
}

function _writeComposerAutocompleteCatalog(data = {}) {
  const writeCatalog = (typeof importedSetAutocompleteCatalog === 'function' && importedSetAutocompleteCatalog)
    || _composerFn('setAutocompleteCatalog');
  if (typeof writeCatalog === 'function') return writeCatalog(data);
  return {};
}

function _composerWelcomeActive() {
  const getWelcome = (typeof importedGetWelcomeState === 'function' && importedGetWelcomeState)
    || _composerFn('getWelcomeState');
  return !!(_composerValue('_welcomeActive')
    || (typeof getWelcome === 'function' && getWelcome().active));
}

function _composerWelcomeDone() {
  const getWelcome = (typeof importedGetWelcomeState === 'function' && importedGetWelcomeState)
    || _composerFn('getWelcomeState');
  return !!(_composerValue('_welcomeDone')
    || (typeof getWelcome === 'function' && getWelcome().done));
}

function _setComposerWelcomePromptAfterSettle(value) {
  const setWelcome = (typeof importedSetWelcomeState === 'function' && importedSetWelcomeState)
    || _composerFn('setWelcomeState');
  if (typeof setWelcome === 'function') setWelcome({ promptAfterSettle: !!value });
  if (COMPOSER_GLOBAL) COMPOSER_GLOBAL._welcomePromptAfterSettle = !!value;
}

function _composerWelcomeOwns(tabId) {
  const welcomeOwns = (typeof importedWelcomeOwnsTab === 'function' && importedWelcomeOwnsTab)
    || _composerFn('welcomeOwnsTab');
  return typeof welcomeOwns === 'function' && welcomeOwns(tabId);
}

function _composerRequestWelcomeSettle(tabId) {
  const requestSettle = (typeof importedRequestWelcomeSettle === 'function' && importedRequestWelcomeSettle)
    || _composerFn('requestWelcomeSettle');
  return typeof requestSettle === 'function' ? requestSettle(tabId) : false;
}

document.addEventListener('paste', e => {
  if (e.defaultPrevented) return;
  if (!cmdInput || _composerIsEditableTarget(e.target) || _isMajorSurfaceOpenForPromptPaste()) return;
  const clipboard = e.clipboardData || (typeof window !== 'undefined' ? window.clipboardData : null);
  const text = clipboard && typeof clipboard.getData === 'function'
    ? (clipboard.getData('text/plain') || clipboard.getData('text') || '')
    : '';
  if (!text) return;

  e.preventDefault();
  if (typeof window !== 'undefined' && typeof window.getSelection === 'function') {
    const selection = window.getSelection();
    if (selection && typeof selection.removeAllRanges === 'function') selection.removeAllRanges();
  }
  _composerRefocus({ preventScroll: true });
  const value = _composerGetValue(cmdInput.value || '');
  const { start, end } = getCmdSelection(value);
  replaceCmdRange(value, start, end, text);
});

// bindOutsideClickClose owns ambient click dismissal for the two surfaces
// that have no scrim of their own (the history side panel and the
// autocomplete dropdown). The mobile menu sheet's dismissal is owned by
// its bindDismissible registration in mobile_chrome.js — the scrim covers
// the viewport so every outside click hits it.
const bindOutsideClick = _composerImportedFn(importedBindOutsideClickClose, 'bindOutsideClickClose');
if (historyPanel && bindOutsideClick) {
  bindOutsideClick(historyPanel, {
    triggers: null,
    isOpen: () => _composerImportedFn(importedIsHistoryPanelOpen, 'isHistoryPanelOpen')?.() || false,
    onClose: () => _composerImportedFn(importedHideHistoryPanel, 'hideHistoryPanel')?.(),
    exemptSelectors: ['.hist-chip-overflow', '[data-action="history"]', '.modal-overlay', '#history-compare-overlay'],
  });
}
if (bindOutsideClick && shellPromptWrap) {
  // Autocomplete dismissal: the dropdown itself is a transient element, so we
  // anchor the helper on the prompt wrap (always present) and exempt the
  // dropdown + mobile composer via selectors. Any click outside all three
  // zones hides the dropdown, matching the prior global-click behavior.
  bindOutsideClick(shellPromptWrap, {
    isOpen: () => _composerFn('isAcDropdownOpen')?.() || false,
    onClose: () => { _composerAcHide(); },
    exemptSelectors: ['.ac-dropdown', '#mobile-composer'],
  });
}

function _handleRunningComposerShortcut(e) {
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'c' || e.key === 'C')) {
    e.preventDefault();
    e.stopPropagation();
    _composerImportedFn(importedConfirmKill, 'confirmKill')?.(_composerActiveTabId());
    return true;
  }

  const isCtrlD = e.ctrlKey && !e.metaKey && !e.altKey && (
    e.key === 'd'
    || e.key === 'D'
    || (_composerImportedFn(importedEventMatchesLetter, 'eventMatchesLetter')?.(e, 'd') || false)
  );
  if (isCtrlD) {
    e.preventDefault();
    e.stopPropagation();
    return true;
  }

  if (_composerImportedFn(importedHandleTabShortcut, 'handleTabShortcut')?.(e)) {
    e.stopPropagation();
    return true;
  }

  if (_composerImportedFn(importedHandleActionShortcut, 'handleActionShortcut')?.(e)) {
    e.stopPropagation();
    return true;
  }

  if (_composerImportedFn(importedHandleChromeShortcut, 'handleChromeShortcut')?.(e)) {
    e.stopPropagation();
    return true;
  }
  return false;
}

function _selectionTouchesElement(el) {
  if (!el || typeof window === 'undefined' || typeof window.getSelection !== 'function') return false;
  const selection = window.getSelection();
  if (!selection) return false;
  const nodes = [selection.anchorNode, selection.focusNode];
  if (selection.rangeCount > 0) nodes.push(selection.getRangeAt(0).commonAncestorContainer);
  return nodes.some(node => (
    !!node && el.contains(node.nodeType === Node.ELEMENT_NODE ? node : node.parentNode)
  ));
}

let _promptPointerSelectionState = null;
let _suppressPromptFocusUntil = 0;
let _pendingPromptFocusTimer = null;

if (shellPromptWrap && cmdInput) {
  shellPromptWrap.addEventListener('pointerdown', e => {
    if (e.target === runBtn || (e.target && e.target.closest && e.target.closest('#run-btn'))) return;
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
      moved: false,
    };
    if (document.activeElement === cmdInput && typeof cmdInput.blur === 'function') {
      cmdInput.blur();
    }
  });
  shellPromptWrap.addEventListener('pointermove', e => {
    const state = _promptPointerSelectionState;
    if (!state || state.id !== e.pointerId || state.moved) return;
    if (Math.abs(e.clientX - state.x) > 4 || Math.abs(e.clientY - state.y) > 4) {
      state.moved = true;
    }
  });
  shellPromptWrap.addEventListener('pointerup', e => {
    const state = _promptPointerSelectionState;
    if (!state || state.id !== e.pointerId) return;
    if (state.moved) _suppressPromptFocusUntil = Date.now() + 250;
    _promptPointerSelectionState = null;
  });
  shellPromptWrap.addEventListener('pointercancel', () => {
    _promptPointerSelectionState = null;
  });
  shellPromptWrap.addEventListener('touchstart', e => {
    if (useMobileTerminalViewportMode()) {
      e.preventDefault();
      _composerFocusCommandInputFromGesture();
    }
  }, { passive: false });
  shellPromptWrap.addEventListener('click', e => {
    if (e.target === runBtn || (e.target && e.target.closest && e.target.closest('#run-btn'))) return;
    if (useMobileTerminalViewportMode()) {
      _composerFocusCommandInputFromGesture();
      return;
    }
    if (e.detail > 1 || Date.now() < _suppressPromptFocusUntil) return;
    if (_selectionTouchesElement(shellPromptWrap)) return;
    if (_pendingPromptFocusTimer) clearTimeout(_pendingPromptFocusTimer);
    _pendingPromptFocusTimer = setTimeout(() => {
      _pendingPromptFocusTimer = null;
      if (_selectionTouchesElement(shellPromptWrap)) return;
      if (Date.now() < _suppressPromptFocusUntil) return;
      _composerFocusCommandInputFromGesture();
    }, 220);
  });
  shellPromptWrap.addEventListener('dblclick', () => {
    if (_pendingPromptFocusTimer) {
      clearTimeout(_pendingPromptFocusTimer);
      _pendingPromptFocusTimer = null;
    }
    _suppressPromptFocusUntil = Date.now() + 400;
  });
}

if (typeof _bindMobileComposerInteractions === 'function') {
  _bindMobileComposerInteractions(_mobileUiLayoutRefs);
}

if (cmdInput) {
  cmdInput.addEventListener('focus', () => {
    _composerSetState({
        value: cmdInput.value || '',
        selectionStart: typeof cmdInput.selectionStart === 'number' ? cmdInput.selectionStart : (cmdInput.value || '').length,
        selectionEnd: typeof cmdInput.selectionEnd === 'number' ? cmdInput.selectionEnd : (cmdInput.value || '').length,
        activeInput: 'desktop',
      });
    if (shellPromptWrap) shellPromptWrap.classList.add('shell-prompt-focused');
    _composerSyncShellPrompt();
    syncMobileViewportState();
  });
  cmdInput.addEventListener('blur', () => {
    if (shellPromptWrap) shellPromptWrap.classList.remove('shell-prompt-focused');
    _composerSyncShellPrompt();
    syncMobileViewportState();
  });
  cmdInput.addEventListener('select', _composerSyncShellPrompt);
  cmdInput.addEventListener('keyup', _composerSyncShellPrompt);
}

if (typeof document !== 'undefined') {
  document.addEventListener('selectionchange', () => {
    if (!cmdInput) return;
    if (shellPromptWrap && _selectionTouchesElement(shellPromptWrap)) {
      if (_pendingPromptFocusTimer) {
        clearTimeout(_pendingPromptFocusTimer);
        _pendingPromptFocusTimer = null;
      }
      return;
    }
    const composerInputs = _composerInputs();
    const mobileInput = composerInputs.mobile || null;
    if (document.activeElement === cmdInput) {
      _composerSetState({
          value: cmdInput.value || '',
          selectionStart: typeof cmdInput.selectionStart === 'number' ? cmdInput.selectionStart : (cmdInput.value || '').length,
          selectionEnd: typeof cmdInput.selectionEnd === 'number' ? cmdInput.selectionEnd : (cmdInput.value || '').length,
          activeInput: 'desktop',
        });
      _composerSyncShellPrompt();
      return;
    }
    if (mobileInput && document.activeElement === mobileInput) {
      _composerSetState({
          value: mobileInput.value || '',
          selectionStart: typeof mobileInput.selectionStart === 'number' ? mobileInput.selectionStart : (mobileInput.value || '').length,
          selectionEnd: typeof mobileInput.selectionEnd === 'number' ? mobileInput.selectionEnd : (mobileInput.value || '').length,
          activeInput: 'mobile',
        });
      _composerSyncShellPrompt();
    }
  });
}

const _composerApiFetch = (typeof importedApiFetch === 'function' && importedApiFetch)
  || _composerFn('apiFetch');
if (typeof _composerApiFetch === 'function') _composerApiFetch('/autocomplete').then(r => r.json()).then(data => {
  _writeComposerAutocompleteCatalog(data);
  _composerImportedFn(importedLoadSessionVariables, 'loadSessionVariables')?.()?.catch?.(() => {});
  _composerImportedFn(importedLoadRecentValues, 'loadRecentValues')?.()?.catch?.(() => {});
  _composerImportedFn(importedLoadProjectAutocompleteTargets, 'loadProjectAutocompleteTargets')?.()?.catch?.(() => {});
  _composerImportedFn(importedLoadScheduleAutocompleteHints, 'loadScheduleAutocompleteHints')?.()?.catch?.(() => {});
  _composerImportedFn(importedLoadWatcherAutocompleteHints, 'loadWatcherAutocompleteHints')?.()?.catch?.(() => {});
  _refreshWorkspaceFileCache()?.catch?.(() => {});
  const refreshSearchDiscoverability = _composerFn('scheduleSearchDiscoverabilityRefresh')
    || _composerFn('refreshSearchDiscoverabilityUi');
  refreshSearchDiscoverability?.();
}).catch(err => {
  const log = (typeof importedLogClientError === 'function' && importedLogClientError)
    || _composerFn('logClientError');
  log?.('failed to load /autocomplete', err);
});

cmdInput.addEventListener('input', () => {
  _composerImportedFn(importedNormalizeComposerSmartPeriod, 'normalizeComposerSmartPeriod')?.(cmdInput);
  if (_composerImportedFn(importedIsHistoryPanelOpen, 'isHistoryPanelOpen')?.()) {
    _composerImportedFn(importedHideHistoryPanel, 'hideHistoryPanel')?.();
  }
  if (_composerIsHistSearchMode()) {
    // Read the DOM value directly — the hist-search path intentionally
    // short-circuits handleComposerInputChange, so the shared composer
    // state is one keystroke stale (reads showed the pre-backspace query).
    _composerHandleHistSearchInput(cmdInput.value);
    const _hsTab = _composerActiveTab();
    if (_hsTab) _hsTab.followOutput = true;
    const _hsOut = document.querySelector('.tab-panel.active .output');
    if (_hsOut) _hsOut.scrollTop = _hsOut.scrollHeight;
    return;
  }
  _composerImportedFn(importedHandleComposerInputChange, 'handleComposerInputChange')?.(cmdInput);
  // Keep the active tab's draft current so activateTab can read it directly.
  const _activeTab = _composerActiveTab();
  if (_activeTab && _activeTab.st !== 'running') {
    _activeTab.draftInput = _composerGetValue(cmdInput.value);
    _composerImportedFn(importedSchedulePersistTabSessionState, 'schedulePersistTabSessionState')?.();
  }
});

cmdInput.addEventListener('keydown', e => {
  if (_composerIsAnyPanelOverlayOpen()) {
    if (e.key === 'Escape') {
      if (!_composerCloseTopmostDismissible()) {
        _composerImportedFn(importedCloseFaq, 'closeFaq')?.();
        _composerImportedFn(importedCloseWorkflows, 'closeWorkflows')?.();
        _composerImportedFn(importedCloseWorkspace, 'closeWorkspace')?.();
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

  if (_composerImportedFn(importedIsActiveTabRunning, 'isActiveTabRunning')?.()) {
    if (_handleRunningComposerShortcut(e)) return;
    _composerAcHide();
    e.preventDefault();
    return;
  }

  const eventMatchesCodeFn = _composerImportedFn(importedEventMatchesCode, 'eventMatchesCode');
  const isWordArrowLeft = e.key === 'ArrowLeft' || eventMatchesCodeFn?.(e, 'ArrowLeft');
  const isWordArrowRight = e.key === 'ArrowRight' || eventMatchesCodeFn?.(e, 'ArrowRight');
  if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey && (isWordArrowLeft || isWordArrowRight)) {
    e.preventDefault();
    e.stopPropagation();
    _composerImportedFn(importedSyncFocusedComposerState, 'syncFocusedComposerState')?.(cmdInput);
    const value = _composerGetValue('');
    const { start, end } = getCmdSelection(value);
    const next = isWordArrowLeft
      ? findWordBoundaryLeft(value, start)
      : findWordBoundaryRight(value, end);
    const input = _composerVisibleInput();
    _composerSyncSelection(next, next, { input });
    if (input && typeof input.setSelectionRange === 'function' && input.selectionStart !== next) {
      input.setSelectionRange(next, next);
    } else if (!input && cmdInput && typeof cmdInput.setSelectionRange === 'function') {
      cmdInput.setSelectionRange(next, next);
    }
    _composerSyncShellPrompt();
    return;
  }

  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'r' || e.key === 'R')) {
    e.preventDefault();
    _composerEnterHistSearch();
    return;
  }

  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'c' || e.key === 'C')) {
    e.preventDefault();
    const currentTabId = _composerActiveTabId();
    if (_composerWelcomeActive() && !_composerWelcomeDone() && _composerWelcomeOwns(currentTabId)) {
      _setComposerWelcomePromptAfterSettle(true);
      _composerRequestWelcomeSettle(currentTabId);
      _composerRefocus({ defer: true });
      return;
    }
    const activeTab = _composerActiveTab();
    if (activeTab && activeTab.st === 'running') {
      _composerImportedFn(importedConfirmKill, 'confirmKill')?.(currentTabId);
      return;
    }
    if (_composerHasActiveTerminalConfirm()) {
      _composerImportedFn(importedCancelPendingTerminalConfirm, 'cancelPendingTerminalConfirm')?.(currentTabId);
      return;
    }
    _composerImportedFn(importedInterruptPromptLine, 'interruptPromptLine')?.(currentTabId);
    return;
  }

  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'w' || e.key === 'W')) {
    e.preventDefault();
    const value = _composerGetValue('');
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

  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'u' || e.key === 'U')) {
    e.preventDefault();
    const value = _composerGetValue('');
    const { start, end } = getCmdSelection(value);
    if (start !== end) {
      replaceCmdRange(value, start, end);
      return;
    }
    if (start === 0) return;
    replaceCmdRange(value, 0, start);
    return;
  }

  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'a' || e.key === 'A')) {
    e.preventDefault();
    if (_composerImportedFn(importedSyncComposerSelection, 'syncComposerSelection')) _composerSyncSelection(0, 0);
    else if (cmdInput && typeof cmdInput.setSelectionRange === 'function') cmdInput.setSelectionRange(0, 0);
    _composerSyncShellPrompt();
    return;
  }

  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault();
    const value = _composerGetValue('');
    const { start, end } = getCmdSelection(value);
    if (start !== end) {
      replaceCmdRange(value, start, end);
      return;
    }
    if (start >= value.length) return;
    replaceCmdRange(value, start, value.length);
    return;
  }

  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'e' || e.key === 'E')) {
    e.preventDefault();
    const value = _composerGetValue('');
    const end = value.length;
    if (_composerImportedFn(importedSyncComposerSelection, 'syncComposerSelection')) _composerSyncSelection(end, end);
    else if (cmdInput && typeof cmdInput.setSelectionRange === 'function') cmdInput.setSelectionRange(end, end);
    _composerSyncShellPrompt();
    return;
  }

  const eventMatchesLetterFn = _composerImportedFn(importedEventMatchesLetter, 'eventMatchesLetter');
  if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey && eventMatchesLetterFn?.(e, 'b')) {
    e.preventDefault();
    _composerImportedFn(importedSyncFocusedComposerState, 'syncFocusedComposerState')?.(cmdInput);
    const value = _composerGetValue('');
    const { start } = getCmdSelection(value);
    const next = findWordBoundaryLeft(value, start);
    if (_composerImportedFn(importedSyncComposerSelection, 'syncComposerSelection')) _composerSyncSelection(next, next);
    else if (cmdInput && typeof cmdInput.setSelectionRange === 'function') cmdInput.setSelectionRange(next, next);
    _composerSyncShellPrompt();
    return;
  }

  if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey && eventMatchesLetterFn?.(e, 'f')) {
    e.preventDefault();
    _composerImportedFn(importedSyncFocusedComposerState, 'syncFocusedComposerState')?.(cmdInput);
    const value = _composerGetValue('');
    const { end } = getCmdSelection(value);
    const next = findWordBoundaryRight(value, end);
    if (_composerImportedFn(importedSyncComposerSelection, 'syncComposerSelection')) _composerSyncSelection(next, next);
    else if (cmdInput && typeof cmdInput.setSelectionRange === 'function') cmdInput.setSelectionRange(next, next);
    _composerSyncShellPrompt();
    return;
  }

  if (e.key === 'Enter') {
    const currentTabId = _composerActiveTabId();
    if (_composerWelcomeActive() && !_composerWelcomeDone() && _composerWelcomeOwns(currentTabId) && !_composerGetValue('').trim()) {
      e.preventDefault();
      _composerRequestWelcomeSettle(currentTabId);
      _composerRefocus({ defer: true });
      return;
    }
    const acState = _readComposerAutocompleteState();
    if (
      !_composerHasActiveTerminalConfirm()
      && acState.index >= 0
      && acState.filtered[acState.index]
      && !_composerAutocompleteIsHintOnly(acState.filtered[acState.index])
    ) {
      e.preventDefault();
      _composerFn('acAccept')?.(acState.filtered[acState.index]);
    } else {
      e.preventDefault();
      _composerAcHide();
      _composerSubmitCommand(_composerGetValue(''), { dismissKeyboard: true });
    }
    return;
  }
  if (e.key === 'Tab' && !e.altKey && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    if (_composerHasActiveTerminalConfirm()) {
      _composerAcHide();
      return;
    }
    const acState = _readComposerAutocompleteState();
    const selectableItems = _composerAutocompleteSelectableItems(acState.filtered);
    if (selectableItems.length === 1) { _composerFn('acAccept')?.(selectableItems[0]); }
    else if (selectableItems.length > 0) {
      if (_composerFn('acExpandSharedPrefix')?.(selectableItems)) return;
      let nextIndex;
      if (acState.index < 0 || !_composerImportedFn(importedIsAcDropdownOpen, 'isAcDropdownOpen')?.()) {
        nextIndex = _composerAutocompleteNextSelectableIndex(acState.filtered, -1, 1);
      } else if (e.shiftKey) {
        nextIndex = _composerAutocompleteNextSelectableIndex(acState.filtered, acState.index, -1);
      } else {
        nextIndex = _composerAutocompleteNextSelectableIndex(acState.filtered, acState.index, 1);
      }
      _writeComposerAutocompleteState({ index: nextIndex });
      _composerFn('acShow')?.(acState.filtered);
    }
    return;
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    if (_composerHasActiveTerminalConfirm()) {
      _composerAcHide();
      return;
    }
    const acOpen = _composerImportedFn(importedIsAcDropdownOpen, 'isAcDropdownOpen')?.();
    const acState = _readComposerAutocompleteState();
    const selectableItems = _composerAutocompleteSelectableItems(acState.filtered);
    if (acOpen && selectableItems.length) {
      const nextIndex = _composerAutocompleteNextSelectableIndex(acState.filtered, acState.index, 1);
      _writeComposerAutocompleteState({ index: nextIndex });
      _composerFn('acShow')?.(acState.filtered);
      return;
    }
    if (_composerNavigateCmdHistory(-1)) _composerAcHide();
    return;
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (_composerHasActiveTerminalConfirm()) {
      _composerAcHide();
      return;
    }
    const acOpen = _composerImportedFn(importedIsAcDropdownOpen, 'isAcDropdownOpen')?.();
    const acState = _readComposerAutocompleteState();
    const selectableItems = _composerAutocompleteSelectableItems(acState.filtered);
    if (acOpen && selectableItems.length) {
      const nextIndex = _composerAutocompleteNextSelectableIndex(acState.filtered, acState.index, -1);
      _writeComposerAutocompleteState({ index: nextIndex });
      _composerFn('acShow')?.(acState.filtered);
      return;
    }
    if (_composerNavigateCmdHistory(1)) _composerAcHide();
    return;
  }
  if (e.key === 'Escape')    { _composerAcHide(); return; }

  // Suppress the macOS 'Press and Hold' accent picker. On macOS, holding a key
  // on a native <input> shows an accent chooser instead of repeating the character.
  // Calling preventDefault() signals that we handle the key ourselves, so the OS
  // never intercepts the repeat. We then insert the character manually so the
  // input value stays correct. Guard: skip modifier combos (handled above),
  // non-printable keys (length !== 1), IME composition sequences, and the welcome
  // settle phase (the document keydown handler owns key routing while welcome is
  // active, including Space/Enter/Escape settle triggers and printable insertion).
  if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey && !e.isComposing
      && !(_composerWelcomeActive() && !_composerWelcomeDone() && _composerWelcomeOwns(_composerActiveTabId()))) {
    e.preventDefault();
    const value = _composerGetValue('');
    const { start, end } = getCmdSelection(value);
    replaceCmdRange(value, start, end, e.key);
    return;
  }
});

if (typeof window !== 'undefined') {
  window.addEventListener('resize', syncMobileViewportState);
  if (window.visualViewport && typeof window.visualViewport.addEventListener === 'function') {
    // Mobile keyboards resize the visual viewport after focus; keep the prompt pinned above it.
    window.visualViewport.addEventListener('resize', syncMobileViewportState);
  }
}

if (runBtn) runBtn.addEventListener('click', () => { _composerSubmitCommand(_composerGetValue(''), { dismissKeyboard: true }); });

_composerSyncShellPrompt();
_composerSyncShellPrompt();
_composerImportedFn(importedSyncRunButtonDisabled, 'syncRunButtonDisabled')?.();

_composerSetupMobileComposer();
