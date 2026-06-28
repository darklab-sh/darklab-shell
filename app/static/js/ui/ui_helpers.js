// ── Shared UI helpers ──
import {
  emitUiEvent as importedEmitUiEvent,
  getActiveTab as importedGetActiveTab,
  getActiveTabId as importedGetActiveTabId,
  getAppState as importedGetAppState,
  getAutocompleteState as importedGetAutocompleteState,
  getComposerState as importedGetComposerState,
  setAutocompleteState as importedSetAutocompleteState,
  setComposerState as importedSetComposerState,
} from '../core/state.js';
import {
  acDropdown as importedAcDropdown,
  cmdInput as importedCmdInput,
  faqOverlay as importedFaqOverlay,
  histRow as importedHistRow,
  historyLoadOverlay as importedHistoryLoadOverlay,
  historyPanel as importedHistoryPanel,
  mobileCmdInput as importedMobileCmdInput,
  mobileMenu as importedMobileMenu,
  mobileRunBtn as importedMobileRunBtn,
  optionsOverlay as importedOptionsOverlay,
  runBtn as importedRunBtn,
  runTimer as importedRunTimer,
  searchBar as importedSearchBar,
  shortcutsOverlay as importedShortcutsOverlay,
  tabPanels as importedTabPanels,
  themeOverlay as importedThemeOverlay,
  workflowsOverlay as importedWorkflowsOverlay,
  workspaceOverlay as importedWorkspaceOverlay,
} from '../core/dom.js';
import {
  hasComposerPromptHandler as importedHasComposerPromptHandler,
  syncShellPrompt as importedSyncShellPrompt,
} from '../features/terminal/composer_prompt_bridge.js';
import {
  getMobileKeyboardOffset as importedGetMobileKeyboardOffset,
  hasMobileShellLayoutHandler as importedHasMobileShellLayoutHandler,
  isMobileKeyboardOpen as importedIsMobileKeyboardOpen,
  syncMobileViewportState as importedSyncMobileViewportState,
  useMobileTerminalViewportMode as importedUseMobileTerminalViewportMode,
} from '../features/mobile/mobile_shell_layout_bridge.js';
import {
  hasHistoryPanelHandler as importedHasHistoryPanelHandler,
  resetHistorySelectionOnClose as importedResetHistorySelectionOnClose,
} from '../features/history/history_panel_bridge.js';
import { resetCmdHistoryNav as importedResetCmdHistoryNav } from '../features/history/history_recall_bridge.js';
import {
  hasPendingTerminalConfirm as importedHasPendingTerminalConfirm,
  hasRunnerHandler as importedHasRunnerHandler,
} from '../runner_bridge.js';
import { requestWelcomeSettle as importedRequestWelcomeSettle } from '../welcome_bridge.js';

(function initSharedUiHelpers(global) {
  const uiFn = (name) => {
    const fn = global && global[name];
    return typeof fn === 'function' ? fn : null;
  };
  const syncShellPromptFromBridge = () => {
    const syncPrompt = (
      typeof importedHasComposerPromptHandler === 'function'
      && importedHasComposerPromptHandler('syncShellPrompt')
    ) ? importedSyncShellPrompt : uiFn('syncShellPrompt');
    if (typeof syncPrompt === 'function') syncPrompt();
  };
  const useMobileTerminalViewportModeFromBridge = () => {
    if (
      typeof importedHasMobileShellLayoutHandler === 'function'
      && importedHasMobileShellLayoutHandler('useMobileTerminalViewportMode')
    ) {
      return importedUseMobileTerminalViewportMode();
    }
    const useMobile = uiFn('useMobileTerminalViewportMode');
    return !!(useMobile && useMobile());
  };
  const getMobileKeyboardOffsetFromBridge = () => {
    if (
      typeof importedHasMobileShellLayoutHandler === 'function'
      && importedHasMobileShellLayoutHandler('getMobileKeyboardOffset')
    ) {
      return importedGetMobileKeyboardOffset();
    }
    const getOffset = uiFn('getMobileKeyboardOffset');
    return typeof getOffset === 'function' ? getOffset() : 0;
  };
  const isMobileKeyboardOpenFromBridge = (offset = null) => {
    if (
      typeof importedHasMobileShellLayoutHandler === 'function'
      && importedHasMobileShellLayoutHandler('isMobileKeyboardOpen')
    ) {
      return importedIsMobileKeyboardOpen(offset);
    }
    const isKeyboardOpen = uiFn('isMobileKeyboardOpen');
    return typeof isKeyboardOpen === 'function' ? !!isKeyboardOpen(offset) : false;
  };
  const syncMobileViewportStateFromBridge = () => {
    if (
      typeof importedHasMobileShellLayoutHandler === 'function'
      && importedHasMobileShellLayoutHandler('syncMobileViewportState')
    ) {
      importedSyncMobileViewportState();
      return;
    }
    uiFn('syncMobileViewportState')?.();
  };
  const resetCmdHistoryNavFromBridge = () => {
    if (typeof importedResetCmdHistoryNav === 'function') importedResetCmdHistoryNav();
  };
  const requestWelcomeSettleFromBridge = (...args) => {
    const settle = (typeof importedRequestWelcomeSettle === 'function' && importedRequestWelcomeSettle)
      || uiFn('requestWelcomeSettle');
    return typeof settle === 'function' ? settle(...args) : undefined;
  };
  const hasPendingTerminalConfirmFromBridge = () => {
    if (
      typeof importedHasRunnerHandler === 'function'
      && importedHasRunnerHandler('hasPendingTerminalConfirm')
      && typeof importedHasPendingTerminalConfirm === 'function'
    ) {
      return !!importedHasPendingTerminalConfirm();
    }
    return !!uiFn('hasPendingTerminalConfirm')?.();
  };
  const uiValue = (name) => (global ? global[name] : undefined);
  const uiEl = (imported, name) => imported || uiValue(name) || null;
  const emitUi = (name, detail) => {
    const emit = (typeof importedEmitUiEvent === 'function' && importedEmitUiEvent)
      || uiFn('emitUiEvent');
    if (emit) emit(name, detail);
  };
  const activeTab = () => {
    if (typeof importedGetActiveTab === 'function') return importedGetActiveTab();
    const getActive = uiFn('getActiveTab');
    return getActive ? getActive() : null;
  };
  const activeTabId = () => {
    if (typeof importedGetActiveTabId === 'function') return importedGetActiveTabId();
    const getActiveId = uiFn('getActiveTabId');
    return getActiveId ? getActiveId() : (uiValue('activeTabId') || null);
  };
  const setComposerStateValue = (next) => {
    const setComposer = (typeof importedSetComposerState === 'function' && importedSetComposerState)
      || uiFn('setComposerState');
    return setComposer ? setComposer(next) : null;
  };
  // These helpers wrap the split desktop/mobile composer model so the rest of
  // the code can ask for "the visible input" instead of branching everywhere.
  const readAppState = (typeof importedGetAppState !== 'undefined' && importedGetAppState)
    || uiFn('getAppState');
  const readComposerState = (typeof importedGetComposerState !== 'undefined' && importedGetComposerState)
    || uiFn('getComposerState');
  const state = typeof readAppState === 'function' ? readAppState() : {};
  let _mobileKeyboardVisibilityTimer = null;
  const readAutocompleteState = () => {
    const getAutocomplete = (typeof importedGetAutocompleteState !== 'undefined' && importedGetAutocompleteState)
      || uiFn('getAutocompleteState');
    const apiState = typeof getAutocomplete === 'function' ? getAutocomplete() : {};
    return {
      filtered: Array.isArray(apiState.filtered) ? apiState.filtered : [],
      index: apiState.index ?? -1,
      suppressInputOnce: !!apiState.suppressInputOnce,
    };
  };
  const writeAutocompleteState = (next = {}) => {
    const setAutocomplete = (typeof importedSetAutocompleteState !== 'undefined' && importedSetAutocompleteState)
      || uiFn('setAutocompleteState');
    if (typeof setAutocomplete === 'function') setAutocomplete(next);
    return readAutocompleteState();
  };
  const getMobileMenuEl = () => uiEl(importedMobileMenu, 'mobileMenu');
  const isMobileTerminalViewportActive = () => !!(
    useMobileTerminalViewportModeFromBridge()
    && document.body
    && document.body.classList
    && document.body.classList.contains("mobile-terminal-mode")
  );

  let _setComposerValueInProgress = false;
  const _baseSetComposerState = typeof global.setComposerState === 'function'
    ? global.setComposerState
    : null;
  function _syncComposerInputsFromState() {
    if (_setComposerValueInProgress || typeof readComposerState !== 'function') return;
    const composer = readComposerState();
    if (!composer) return;
    const value = typeof composer.value === 'string' ? composer.value : '';
    const start = typeof composer.selectionStart === 'number' ? Math.max(0, Math.min(composer.selectionStart, value.length)) : value.length;
    const end = typeof composer.selectionEnd === 'number' ? Math.max(0, Math.min(composer.selectionEnd, value.length)) : start;
    const inputs = global.getComposerInputs();
    const target = composer.activeInput === 'mobile' ? inputs.mobile : inputs.desktop;
    if (target) {
      if (target.value !== value) target.value = value;
      if (
        typeof target.setSelectionRange === 'function'
        && (document.activeElement === target || target === global.getVisibleComposerInput())
      ) {
        target.setSelectionRange(start, end);
        _syncComposerCaretVisibility(target, start, end);
      }
    }
    if (typeof global.syncRunButtonDisabled === 'function') global.syncRunButtonDisabled();
  }
  if (_baseSetComposerState) {
    const appStateApi = uiValue('APP_STATE_API');
    if (appStateApi) {
      appStateApi.setComposerState = (next) => global.setComposerState(next);
    }
  }
  function _estimateComposerTextWidth(input, text) {
    if (!input || typeof window === 'undefined' || typeof window.getComputedStyle !== 'function') return 0;
    const style = window.getComputedStyle(input);
    const fontSize = parseFloat(style.fontSize || '16') || 16;
    const rawLetterSpacing = parseFloat(style.letterSpacing || '0');
    const letterSpacing = Number.isFinite(rawLetterSpacing) ? rawLetterSpacing : 0;
    const len = String(text || '').length;
    if (!len) return 0;
    return (len * (fontSize * 0.62)) + (Math.max(0, len - 1) * letterSpacing);
  }
  function _syncComposerCaretVisibility(input, start, end) {
    if (!input || typeof input.scrollLeft !== 'number') return;
    if (typeof input.clientWidth !== 'number' || input.clientWidth <= 0) return;
    const value = typeof input.value === 'string' ? input.value : '';
    const caret = Math.max(0, Math.min(typeof end === 'number' ? end : start, value.length));
    const anchor = Math.max(0, Math.min(typeof start === 'number' ? start : caret, value.length));
    if (caret === 0 && anchor === 0) {
      input.scrollLeft = 0;
      return;
    }
    const style = typeof window !== 'undefined' && typeof window.getComputedStyle === 'function'
      ? window.getComputedStyle(input)
      : null;
    const paddingLeft = style ? (parseFloat(style.paddingLeft || '0') || 0) : 0;
    const paddingRight = style ? (parseFloat(style.paddingRight || '0') || 0) : 0;
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

  const getComposerInputs = () => ({
    desktop: uiEl(importedCmdInput, 'cmdInput'),
    mobile: uiEl(importedMobileCmdInput, 'mobileCmdInput'),
  });
  const getVisibleComposerInput = () => {
    const { desktop, mobile } = getComposerInputs();
    const mobileShellActive = !!(typeof document !== 'undefined'
      && document.body
      && document.body.classList
      && document.body.classList.contains('mobile-terminal-mode'));
    if (mobileShellActive && mobile) return mobile;
    return desktop;
  };
  const getActiveComposerInput = () => {
    const { desktop, mobile } = getComposerInputs();
    const visible = getVisibleComposerInput();
    if (visible) return visible;
    const composer = typeof readComposerState === 'function' ? readComposerState() : null;
    if (composer?.activeInput === 'mobile' && mobile) return mobile;
    if (composer?.activeInput === 'desktop' && desktop) return desktop;
    return desktop || mobile || null;
  };
  const getComposerValue = () => {
    if (typeof readComposerState === 'function') {
      const composer = readComposerState();
      if (composer && typeof composer.value === 'string') return composer.value;
    }
    const input = getVisibleComposerInput();
    return input ? input.value : '';
  };
  const applyMobileTextInputDefaults = (input) => {
    if (!input || typeof input.setAttribute !== 'function') return;
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('autocapitalize', 'none');
    input.setAttribute('autocorrect', 'off');
    input.setAttribute('spellcheck', 'false');
    input.setAttribute('inputmode', 'text');
  };
  const normalizeComposerSmartPeriod = (sourceInput) => {
    if (!sourceInput || typeof sourceInput.value !== 'string') return false;
    const composer = typeof readComposerState === 'function' ? readComposerState() : null;
    if (!composer || typeof composer.value !== 'string') return false;
    const prevValue = composer.value;
    const prevStart = typeof composer.selectionStart === 'number' ? composer.selectionStart : prevValue.length;
    const prevEnd = typeof composer.selectionEnd === 'number' ? composer.selectionEnd : prevStart;
    if (prevStart !== prevEnd || prevStart < 1 || prevValue[prevStart - 1] !== ' ') return false;

    const smartPeriodValue = `${prevValue.slice(0, prevStart - 1)}. ${prevValue.slice(prevStart)}`;
    if (sourceInput.value !== smartPeriodValue) return false;

    const normalizedValue = `${prevValue.slice(0, prevStart)} ${prevValue.slice(prevStart)}`;
    const nextCaret = prevStart + 1;
    sourceInput.value = normalizedValue;
    if (typeof sourceInput.setSelectionRange === 'function') {
      sourceInput.setSelectionRange(nextCaret, nextCaret);
    }
    return true;
  };
  const focusElement = (el, { preventScroll = false } = {}) => {
    if (!el || typeof el.focus !== 'function') return false;
    try {
      if (preventScroll) el.focus({ preventScroll: true });
      else el.focus();
    } catch (_) {
      el.focus();
    }
    return true;
  };
  const blurActiveElement = () => {
    if (typeof document === 'undefined') return false;
    const active = document.activeElement;
    if (!active || typeof active.blur !== 'function') return false;
    active.blur();
    return true;
  };
  const focusComposerInput = (input = null, { preventScroll = false } = {}) => {
    const target = input || getVisibleComposerInput();
    return focusElement(target, { preventScroll });
  };
  const focusVisibleComposerInput = ({ preventScroll = false } = {}) => {
    if (isMobileTerminalViewportActive()) return false;
    return focusComposerInput(getVisibleComposerInput(), { preventScroll });
  };
  const getMobileKeyboardOffsetBaseline = () => state._mobileKeyboardOffsetBaseline;
  const getMobileViewportClosedHeight = () => state._mobileViewportClosedHeight;
  const setMobileViewportClosedHeight = (value) => {
    state._mobileViewportClosedHeight = typeof value === 'number' ? value : null;
    return state._mobileViewportClosedHeight;
  };
  const blurVisibleComposerInput = () => {
    const target = getVisibleComposerInput();
    if (!target || typeof target.blur !== 'function') return false;
    target.blur();
    return true;
  };
  const blurVisibleComposerInputIfMobile = () => {
    if (!useMobileTerminalViewportModeFromBridge()) return false;
    return blurVisibleComposerInput();
  };
  const focusAnyComposerInput = ({ preventScroll = false } = {}) => focusVisibleComposerInput({ preventScroll });
  const syncMobileComposerKeyboardState = (offset = null, { active = true, open = null } = {}) => {
    if (typeof document === 'undefined' || !document.body || !document.body.classList) return false;
    const requestedOffset = typeof offset === 'number' ? offset : 0;
    const requestedOpen = typeof open === 'boolean'
      ? open
      : document.body.classList.contains('mobile-keyboard-open');
    const lastOpenOffset = state._mobileKeyboardLastOpenOffset || 0;
    const nextOffset = requestedOpen && requestedOffset <= 0 && lastOpenOffset > 0
      ? lastOpenOffset
      : requestedOffset;
    document.documentElement?.style?.setProperty('--mobile-keyboard-offset', `${nextOffset}px`);
    if (!active) {
      state._mobileKeyboardOffsetBaseline = nextOffset;
      if (_mobileKeyboardVisibilityTimer) {
        clearTimeout(_mobileKeyboardVisibilityTimer);
        _mobileKeyboardVisibilityTimer = null;
      }
      document.body.classList.remove('mobile-keyboard-open');
      emitUi('app:mobile-keyboard-state', { open: false });
      return false;
    }
    if (typeof state._mobileKeyboardOffsetBaseline !== 'number') {
      state._mobileKeyboardOffsetBaseline = nextOffset;
    }
    const nextOpen = requestedOpen;
    if (nextOpen && nextOffset > 0) state._mobileKeyboardLastOpenOffset = nextOffset;
    if (!nextOpen) state._mobileKeyboardOffsetBaseline = nextOffset;
    document.body.classList.toggle('mobile-keyboard-open', nextOpen);
    emitUi('app:mobile-keyboard-state', { open: !!nextOpen });
    return nextOpen;
  };
  const setMobileKeyboardOpenState = (open, { delay = 0 } = {}) => {
    if (typeof document === 'undefined' || !document.body || !document.body.classList) return false;
    if (_mobileKeyboardVisibilityTimer) {
      clearTimeout(_mobileKeyboardVisibilityTimer);
      _mobileKeyboardVisibilityTimer = null;
    }

    const applyOpen = () => {
      const wasKeyboardOpen = document.body.classList.contains('mobile-keyboard-open');
      document.body.classList.toggle('mobile-keyboard-open', !!open);
      if (open && !wasKeyboardOpen) {
        const hideMobile = uiFn('hideMobileMenu') || hideMobileMenu;
        const isHistoryOpen = uiFn('isHistoryPanelOpen') || isHistoryPanelOpen;
        const hideHistory = uiFn('hideHistoryPanel') || hideHistoryPanel;
        const hideAutocomplete = uiFn('acHide');
        if (hideMobile) hideMobile();
        if (isHistoryOpen && isHistoryOpen() && hideHistory) hideHistory();
        if (hideAutocomplete) hideAutocomplete();
      }
      emitUi('app:mobile-keyboard-state', { open: !!open });
      return !!open;
    };

    if (open) return applyOpen();

    const closeDelay = Math.max(0, Number(delay) || 0);
    if (closeDelay === 0) return applyOpen();

    _mobileKeyboardVisibilityTimer = setTimeout(() => {
      _mobileKeyboardVisibilityTimer = null;
      const mobileInput = getVisibleComposerInput();
      const keyboardStillOpen = !!(
        mobileInput
        && document.activeElement === mobileInput
        && isMobileKeyboardOpenFromBridge(getMobileKeyboardOffsetFromBridge())
      );
      if (keyboardStillOpen) return;
      document.body.classList.remove('mobile-keyboard-open');
      emitUi('app:mobile-keyboard-state', { open: false });
      if (typeof window !== 'undefined' && document.documentElement) {
        const h = window.innerHeight || 0;
        if (h > 0) document.documentElement.style.setProperty('--mobile-viewport-height', `${h}px`);
        syncMobileComposerKeyboardState(0, { open: false });
      }
    }, closeDelay);
    return false;
  };
  const isActiveTabRunning = () => {
    const active = activeTab();
    return !!(active && active.st === 'running');
  };
  const setComposerValue = (value, start = null, end = null, { dispatch = true, exclude = null, allowDuringRun = false } = {}) => {
    const nextValue = String(value ?? '');
    if (!allowDuringRun && nextValue.trim() && isActiveTabRunning()) {
      const hideAutocomplete = uiFn('acHide');
      if (hideAutocomplete) hideAutocomplete();
      if (typeof global.syncRunButtonDisabled === 'function') global.syncRunButtonDisabled();
      return getComposerValue();
    }
    const nextStart = typeof start === 'number' ? start : nextValue.length;
    const nextEnd = typeof end === 'number' ? end : nextStart;
    const target = getActiveComposerInput();
    if (typeof setComposerStateValue === 'function') {
      _setComposerValueInProgress = true;
      try {
        setComposerStateValue({
          value: nextValue,
          selectionStart: nextStart,
          selectionEnd: nextEnd,
          activeInput: (typeof document !== 'undefined'
            && document.body
            && document.body.classList
            && document.body.classList.contains('mobile-terminal-mode'))
            ? 'mobile'
            : 'desktop',
        });
      } finally {
        _setComposerValueInProgress = false;
      }
    }
    if (target && target !== exclude) {
      target.value = nextValue;
      if (typeof target.setSelectionRange === 'function') {
        target.setSelectionRange(nextStart, nextEnd);
      }
      _syncComposerCaretVisibility(target, nextStart, nextEnd);
    }
    if (dispatch && target && target !== exclude) {
      target.dispatchEvent(new Event('input'));
    }
    if (typeof global.syncRunButtonDisabled === 'function') global.syncRunButtonDisabled();
    return nextValue;
  };
  const syncComposerSelection = (start = null, end = null, { input = null } = {}) => {
    const target = input || getActiveComposerInput();
    const composer = typeof readComposerState === 'function' ? readComposerState() : null;
    const value = composer && typeof composer.value === 'string'
      ? composer.value
      : (target && typeof target.value === 'string' ? target.value : '');
    const len = value.length;
    const nextStart = typeof start === 'number' ? Math.max(0, Math.min(start, len)) : len;
    const nextEnd = typeof end === 'number' ? Math.max(0, Math.min(end, len)) : nextStart;
    const orderedStart = Math.min(nextStart, nextEnd);
    const orderedEnd = Math.max(nextStart, nextEnd);
    setComposerStateValue({
      selectionStart: orderedStart,
      selectionEnd: orderedEnd,
      activeInput: (typeof document !== 'undefined'
        && document.body
        && document.body.classList
        && document.body.classList.contains('mobile-terminal-mode'))
        ? 'mobile'
        : 'desktop',
    });
    if (target && typeof target.setSelectionRange === 'function') {
      target.setSelectionRange(orderedStart, orderedEnd);
    }
    _syncComposerCaretVisibility(target, orderedStart, orderedEnd);
    return { start: orderedStart, end: orderedEnd };
  };
  const syncFocusedComposerState = (input = null) => {
    const target = input || getActiveComposerInput();
    if (!target || typeof target.value !== 'string') return null;
    const value = target.value;
    const start = typeof target.selectionStart === 'number' ? target.selectionStart : value.length;
    const end = typeof target.selectionEnd === 'number' ? target.selectionEnd : start;
    setComposerStateValue({
      value,
      selectionStart: start,
      selectionEnd: end,
      activeInput: target === getComposerInputs().mobile ? 'mobile' : 'desktop',
    });
    return { value, start, end, input: target };
  };
  const handleComposerInputChange = (sourceInput) => {
    if (!sourceInput) return;
    const _activeTab = activeTab();
    if (_activeTab && _activeTab.st === 'running') {
      sourceInput.value = '';
      setComposerValue('', 0, 0, { dispatch: false, exclude: sourceInput, allowDuringRun: true });
      uiFn('acHide')?.();
      syncShellPromptFromBridge();
      return;
    }
    normalizeComposerSmartPeriod(sourceInput);
    if (_activeTab) _activeTab.followOutput = true;
    const _out = typeof document !== 'undefined'
      ? document.querySelector('.tab-panel.active .output') : null;
    if (_out) _out.scrollTop = _out.scrollHeight;
    syncShellPromptFromBridge();
    syncMobileViewportStateFromBridge();
    const value = sourceInput.value;
    const start = typeof sourceInput.selectionStart === 'number' ? sourceInput.selectionStart : value.length;
    const end = typeof sourceInput.selectionEnd === 'number' ? sourceInput.selectionEnd : value.length;
    setComposerValue(value, start, end, { dispatch: false, exclude: sourceInput });
    if (state && state._suspendCmdHistoryNavReset) state._suspendCmdHistoryNavReset = false;
    else resetCmdHistoryNavFromBridge();
    if (value.length > 0) requestWelcomeSettleFromBridge(activeTabId());

    const autocomplete = readAutocompleteState();
    if (autocomplete.suppressInputOnce) {
      writeAutocompleteState({ suppressInputOnce: false });
      uiFn('acHide')?.();
      return;
    }
    if (hasPendingTerminalConfirmFromBridge()) {
      writeAutocompleteState({ index: -1, filtered: [] });
      uiFn('acHide')?.();
      return;
    }
    writeAutocompleteState({ index: -1 });
    if (!value.trim()) {
      uiFn('acHide')?.();
      return;
    }
    const getMatches = uiFn('getAutocompleteMatches');
    const usedContextMatcher = !!getMatches;
    const contextMatches = usedContextMatcher ? getMatches(value, start) : [];
    const limitMatches = uiFn('limitAutocompleteMatchesForDisplay');
    const suggestions = Array.isArray(uiValue('acSuggestions')) ? uiValue('acSuggestions') : [];
    const filtered = usedContextMatcher
      ? (limitMatches ? limitMatches(contextMatches, 12) : contextMatches.slice(0, 12))
      : suggestions
        .filter(s => s.toLowerCase().startsWith(value.toLowerCase()))
        .slice(0, 12);
    writeAutocompleteState({ filtered });
    if (!filtered.length) {
      uiFn('acHide')?.();
      return;
    }
    if (!usedContextMatcher) {
      const q = value.trim().toLowerCase();
      if (filtered.some(s => String(s || '').toLowerCase() === q)) {
        uiFn('acHide')?.();
        return;
      }
    }
    uiFn('acShow')?.(filtered);
  };

  function _isVisibleModalOverlay(el) {
    if (!el || !el.classList) return false;
    if (el.id === 'history-panel' || el.id === 'history-load-overlay') return false;
    const isOverlay = el.classList.contains('modal-overlay')
      || el.classList.contains('mobile-sheet-overlay')
      || el.id === 'shortcuts-overlay'
      || el.id === 'theme-overlay'
      || el.classList.contains('status-monitor-scrim');
    if (!isOverlay) return false;
    if (el.classList.contains('u-hidden')) return false;
    return el.classList.contains('open')
      || (el.style && el.style.display && el.style.display !== 'none');
  }

  function _syncModalOverlayState() {
    if (!global.document || !global.document.body) return false;
    const overlays = global.document.querySelectorAll(
      '.modal-overlay, .mobile-sheet-overlay, #shortcuts-overlay, #theme-overlay, .status-monitor-scrim',
    );
    const active = Array.prototype.some.call(overlays, _isVisibleModalOverlay);
    global.document.body.classList.toggle('modal-overlay-active', active);
    return active;
  }

  // Canonical post-action refocus path for chrome interactions. Every
  // "return focus to the terminal after a button/overlay/sheet action" call
  // site routes through here so mobile-skip, preventScroll, and timing
  // semantics stay consistent across modules.
  //
  // Options:
  //   preventScroll: avoid scrolling the focused input into view (default true;
  //     right for all chrome refocus paths — the composer is already visible).
  //   defer: wrap the refocus in setTimeout(..., 0) so any pending blur events
  //     from the triggering click finish first before focus returns. Use for
  //     handlers that close overlays, dispatch into other modules, or run
  //     inside a pointerdown/click where the current event is still propagating.
  function _doRefocusComposer(preventScroll) {
    const isMobileMode = useMobileTerminalViewportModeFromBridge();
    // Intentional no-op on the mobile terminal viewport: programmatically
    // refocusing would re-pop the software keyboard, which users don't want
    // after every chrome action.
    if (isMobileMode) return false;
    const isConfirmOpen = uiFn('isConfirmOpen');
    if (isConfirmOpen && isConfirmOpen()) return false;
    const focusPty = uiFn('focusActiveInteractivePty');
    if (
      focusPty
      && focusPty({ preventScroll })
    ) {
      return true;
    }
    const getVisible = uiFn('getVisibleComposerInput') || global.getVisibleComposerInput;
    const focusComposer = uiFn('focusComposerInput') || global.focusComposerInput;
    const target = getVisible ? getVisible() : null;
    if (target && focusComposer && focusComposer(target, { preventScroll })) {
      return true;
    }
    const focusAny = uiFn('focusAnyComposerInput') || global.focusAnyComposerInput;
    if (focusAny && focusAny({ preventScroll })) return true;
    return false;
  }
  const historyPanelEl = () => uiEl(importedHistoryPanel, 'historyPanel');
  const workflowsOverlayEl = () => uiEl(importedWorkflowsOverlay, 'workflowsOverlay');
  const faqOverlayEl = () => uiEl(importedFaqOverlay, 'faqOverlay');
  const shortcutsOverlayEl = () => uiEl(importedShortcutsOverlay, 'shortcutsOverlay');
  const themeOverlayEl = () => uiEl(importedThemeOverlay, 'themeOverlay');
  const optionsOverlayEl = () => uiEl(importedOptionsOverlay, 'optionsOverlay');
  const historyLoadOverlayEl = () => uiEl(importedHistoryLoadOverlay, 'historyLoadOverlay');
  const searchBarEl = () => uiEl(importedSearchBar, 'searchBar');
  const histRowEl = () => uiEl(importedHistRow, 'histRow');
  const runTimerEl = () => uiEl(importedRunTimer, 'runTimer');
  const runBtnEl = () => uiEl(importedRunBtn, 'runBtn');
  const mobileRunBtnEl = () => uiEl(importedMobileRunBtn, 'mobileRunBtn');
  const tabPanelsEl = () => uiEl(importedTabPanels, 'tabPanels');
  const getWorkspaceOverlay = () => (
    uiEl(importedWorkspaceOverlay, 'workspaceOverlay')
  );
  const refocusComposerAfterAction = ({ preventScroll = true, defer = false } = {}) => {
    if (defer) {
      setTimeout(() => { _doRefocusComposer(preventScroll); }, 0);
      return undefined;
    }
    return _doRefocusComposer(preventScroll);
  };
  const togglePanelOverlay = (el, force = null) => {
    if (!el || !el.classList) return false;
    const next = force === null ? !el.classList.contains('open') : !!force;
    el.classList.toggle('open', next);
    return next;
  };
  const isPanelOverlayOpen = (el) => !!(el && el.classList && el.classList.contains('open'));
  const showPanelOverlay = (el) => {
    if (el && el.classList) el.classList.add('open');
    if (el && el.dataset) el.dataset.interactionReady = '0';
    _syncModalOverlayState();
  };
  const hidePanelOverlay = (el) => {
    if (el && el.classList) el.classList.remove('open');
    if (el && el.dataset) delete el.dataset.interactionReady;
    _syncModalOverlayState();
  };
  const showModalOverlay = (el, display = 'flex') => {
    if (el && el.style) el.style.display = display;
    _syncModalOverlayState();
  };
  const hideModalOverlay = (el) => {
    if (el && el.style) el.style.display = 'none';
    _syncModalOverlayState();
  };
  const markInteractionSurfaceReady = (surface, overlay, card = null) => {
    if (overlay && overlay.dataset) overlay.dataset.interactionReady = '1';
    if (card && card.dataset) card.dataset.interactionReady = '1';
    emitUi('app:interaction-surface-ready', {
      surface: surface || '',
      overlayId: overlay && overlay.id ? overlay.id : '',
      cardId: card && card.id ? card.id : '',
      activeElementId: document.activeElement && document.activeElement.id ? document.activeElement.id : '',
      focusTrapBound: !!(card && card.dataset && card.dataset.focusTrapBound === '1'),
    });
  };
  const showHistoryPanel = () => showPanelOverlay(historyPanelEl());
  const hideHistoryPanel = () => {
    if (
      typeof importedHasHistoryPanelHandler === 'function'
      && importedHasHistoryPanelHandler('resetHistorySelectionOnClose')
      && typeof importedResetHistorySelectionOnClose === 'function'
    ) {
      importedResetHistorySelectionOnClose();
    } else {
      uiFn('resetHistorySelectionOnClose')?.();
    }
    hidePanelOverlay(historyPanelEl());
    refocusComposerAfterAction({ preventScroll: true });
  };
  const isHistoryPanelOpen = () => isPanelOverlayOpen(historyPanelEl());
  const showWorkflowsOverlay = () => showPanelOverlay(workflowsOverlayEl());
  const hideWorkflowsOverlay = () => hidePanelOverlay(workflowsOverlayEl());
  const isWorkflowsOverlayOpen = () => isPanelOverlayOpen(workflowsOverlayEl());
  const showFaqOverlay = () => showPanelOverlay(faqOverlayEl());
  const hideFaqOverlay = () => hidePanelOverlay(faqOverlayEl());
  const isFaqOverlayOpen = () => isPanelOverlayOpen(faqOverlayEl());
  const showShortcutsOverlay = () => {
    const el = shortcutsOverlayEl();
    if (el) el.setAttribute('aria-hidden', 'false');
    showPanelOverlay(el);
  };
  const hideShortcutsOverlay = () => {
    const el = shortcutsOverlayEl();
    if (el) el.setAttribute('aria-hidden', 'true');
    hidePanelOverlay(el);
  };
  const isShortcutsOverlayOpen = () => isPanelOverlayOpen(shortcutsOverlayEl());
  const showThemeOverlay = () => showPanelOverlay(themeOverlayEl());
  const hideThemeOverlay = () => hidePanelOverlay(themeOverlayEl());
  const isThemeOverlayOpen = () => isPanelOverlayOpen(themeOverlayEl());
  const showOptionsOverlay = () => showPanelOverlay(optionsOverlayEl());
  const hideOptionsOverlay = () => hidePanelOverlay(optionsOverlayEl());
  const isOptionsOverlayOpen = () => isPanelOverlayOpen(optionsOverlayEl());
  const showWorkspaceOverlay = () => showPanelOverlay(getWorkspaceOverlay());
  const hideWorkspaceOverlay = () => hidePanelOverlay(getWorkspaceOverlay());
  const isWorkspaceOverlayOpen = () => isPanelOverlayOpen(getWorkspaceOverlay());
  const showHistoryLoadOverlay = () => {
    const el = historyLoadOverlayEl();
    if (el && el.classList) el.classList.add('open');
    if (el) el.setAttribute('aria-hidden', 'false');
  };
  const hideHistoryLoadOverlay = () => {
    const el = historyLoadOverlayEl();
    if (el && el.classList) el.classList.remove('open');
    if (el) el.setAttribute('aria-hidden', 'true');
  };
  // Initialise inline display so the inline style takes precedence over the
  // conflicting .search-bar { display: flex } class rule (same specificity,
  // later in the sheet) when .u-hidden is also present on the element.
  if (searchBarEl() && searchBarEl().style) searchBarEl().style.display = 'none';
  const showSearchBar = () => {
    const el = searchBarEl();
    if (el && el.style) el.style.display = 'flex';
  };
  const hideSearchBar = () => {
    const el = searchBarEl();
    if (el && el.style) el.style.display = 'none';
    refocusComposerAfterAction({ preventScroll: true });
  };
  const isSearchBarOpen = () => {
    const el = searchBarEl();
    return !!(el && el.style && el.style.display === 'flex');
  };
  const showHistoryRow = () => {
    const el = histRowEl();
    if (el && el.style) el.style.display = 'flex';
  };
  const hideHistoryRow = () => {
    const el = histRowEl();
    if (el && el.style) el.style.display = 'none';
  };
  const showRunTimer = () => {
    const el = runTimerEl();
    if (el && el.style) el.style.display = 'inline';
  };
  const hideRunTimer = () => {
    const el = runTimerEl();
    if (el && el.style) el.style.display = 'none';
    if (el) el.textContent = '';
  };
  const setRunButtonDisabled = (disabled) => {
    const next = !!disabled;
    const desktop = runBtnEl();
    const mobile = mobileRunBtnEl();
    if (desktop) desktop.disabled = next;
    if (mobile) mobile.disabled = next;
  };
  const syncRunButtonDisabled = () => {
    const active = activeTab();
    const composerValue = String(getComposerValue() || '');
    const disabled = !!(active && active.st === 'running') || !composerValue.trim();
    const desktop = runBtnEl();
    const mobile = mobileRunBtnEl();
    if (desktop) desktop.disabled = disabled;
    if (mobile) mobile.disabled = disabled;
    return disabled;
  };
  const isRunButtonDisabled = () => {
    const desktop = runBtnEl();
    const mobile = mobileRunBtnEl();
    return !!((desktop && desktop.disabled) || (mobile && mobile.disabled));
  };
  const syncTerminalActionLayout = (tabId) => {
    const tabPanels = tabPanelsEl();
    const btn = tabPanels
      ? tabPanels.querySelector(`.tab-kill-btn[data-tab="${tabId}"]`)
      : null;
    const actions = btn && btn.parentElement && btn.parentElement.classList && btn.parentElement.classList.contains('terminal-actions')
      ? btn.parentElement
      : null;
    if (!actions) return;
    const hasVisibleKill = !!(btn.style ? btn.style.display !== 'none' : !btn.hidden);
    actions.classList.toggle('terminal-actions-has-visible-kill', hasVisibleKill);
  };
  const showTabKillBtn = (tabId) => {
    const tabPanels = tabPanelsEl();
    const btn = tabPanels ? tabPanels.querySelector(`.tab-kill-btn[data-tab="${tabId}"]`) : null;
    if (btn) {
      btn.hidden = false;
      if (btn.style) btn.style.display = 'inline-block';
    }
    syncTerminalActionLayout(tabId);
    emitUi('app:tab-kill-visibility-changed', { tabId, visible: true });
  };
  const hideTabKillBtn = (tabId) => {
    const tabPanels = tabPanelsEl();
    const btn = tabPanels ? tabPanels.querySelector(`.tab-kill-btn[data-tab="${tabId}"]`) : null;
    if (btn) {
      btn.hidden = true;
      if (btn.style) btn.style.display = 'none';
    }
    syncTerminalActionLayout(tabId);
    emitUi('app:tab-kill-visibility-changed', { tabId, visible: false });
  };
  // Fallbacks. mobile_chrome.js overrides these with sheet-aware versions when
  // the mobile shell initializes; these stubs only run if that init didn't.
  const showMobileMenu = () => {
    const mobileMenu = getMobileMenuEl();
    if (mobileMenu && mobileMenu.classList) mobileMenu.classList.remove('u-hidden');
    emitUi('app:mobile-menu-show');
  };
  const hideMobileMenu = () => {
    const mobileMenu = getMobileMenuEl();
    if (mobileMenu && mobileMenu.classList) mobileMenu.classList.add('u-hidden');
    emitUi('app:mobile-menu-hide');
  };
  const isMobileMenuOpen = () => {
    const mobileMenu = getMobileMenuEl();
    return !!(mobileMenu && mobileMenu.classList && !mobileMenu.classList.contains('u-hidden'));
  };
  const showAcDropdown = () => {
    const el = uiEl(importedAcDropdown, 'acDropdown');
    if (!el) return;
    if (el.classList) el.classList.remove('u-hidden');
    if (el.style) el.style.display = 'block';
  };
  const hideAcDropdown = () => {
    const el = uiEl(importedAcDropdown, 'acDropdown');
    if (!el) return;
    if (el.classList) el.classList.add('u-hidden');
    if (el.style) el.style.display = 'none';
  };
  const isAcDropdownOpen = () => {
    const el = uiEl(importedAcDropdown, 'acDropdown');
    return !!(el && el.style && el.style.display !== 'none');
  };
  const setVisibilityState = (el, hidden, ariaHidden = null) => {
    if (!el) return;
    el.hidden = !!hidden;
    if (typeof el.setAttribute === 'function') {
      if (ariaHidden === null || typeof ariaHidden === 'undefined') {
        if (typeof el.removeAttribute === 'function') el.removeAttribute('aria-hidden');
      } else {
        el.setAttribute('aria-hidden', String(ariaHidden));
      }
    }
  };
  const _appSelects = new Map();
  // Portals an open dropdown menu to document.body so it escapes ancestor
  // stacking contexts and clipped modal bodies. Callers can opt in with
  // select.dataset.portalMenu = 'true', and modal/sheet selects opt in
  // automatically because those surfaces commonly scroll or clip overflow.
  function _viewportBounds() {
    const vv = global.visualViewport;
    if (vv && Number.isFinite(vv.width) && Number.isFinite(vv.height)) {
      return {
        top: Number(vv.offsetTop) || 0,
        left: Number(vv.offsetLeft) || 0,
        width: Number(vv.width) || 0,
        height: Number(vv.height) || 0,
      };
    }
    const docEl = document.documentElement || {};
    return {
      top: 0,
      left: 0,
      width: global.innerWidth || docEl.clientWidth || 0,
      height: global.innerHeight || docEl.clientHeight || 0,
    };
  }

  function _clampNumber(value, min, max) {
    if (max < min) return min;
    return Math.min(Math.max(value, min), max);
  }

  function _portalAppSelectMenu(wrap, trigger, menu) {
    if (wrap.dataset.portalMenu !== 'true') return;
    const rect = trigger.getBoundingClientRect();
    const viewport = _viewportBounds();
    const margin = 8;
    // Portaled menus sit on document.body without the surrounding context
    // (border, shadow, parent panel) that the non-portaled CSS rules in
    // shell.css use to bridge their 4px gap. Setting gap = 0 here makes
    // the menu visually attach to the trigger so the dropdown reads as
    // one connected control rather than two disconnected surfaces.
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
    if (menu.dataset.appSelectPortaled !== 'true') {
      menu._portalReturnTo = wrap;
      menu.dataset.appSelectPortaled = 'true';
      document.body.appendChild(menu);
    }
    // The wrap.open menu { display: flex } selectors don't match once the
    // menu is reparented to body, so apply visibility inline here.
    menu.style.display = 'flex';
    menu.style.flexDirection = 'column';
    menu.style.position = 'fixed';
    // Clear bottom/right that some menu base classes (e.g. .save-menu) set,
    // otherwise both top and bottom apply and the element ends up zero-height.
    menu.style.bottom = 'auto';
    menu.style.right = 'auto';
    menu.style.left = left + 'px';
    menu.style.width = width + 'px';
    menu.style.zIndex = '10000';
    menu.style.maxHeight = maxHeight + 'px';
    menu.style.overflowY = 'auto';
    const renderedHeight = menu.getBoundingClientRect?.().height || menu.offsetHeight || 0;
    const contentHeight = menu.scrollHeight || renderedHeight || maxHeight;
    const menuHeight = Math.min(maxHeight, Math.max(48, contentHeight));
    const top = openAbove
      ? Math.max(rect.top - gap - menuHeight, viewportTop + margin)
      : _clampNumber(rect.bottom + gap, viewportTop + margin, viewportBottom - menuHeight - margin);
    menu.style.top = top + 'px';
    // dropdown-up is used only as a visual/state hint for portaled menus;
    // inline positioning above handles the actual placement.
    menu.classList.toggle('dropdown-up', openAbove);
  }
  function _shouldPortalAppSelect(select) {
    if (!select || typeof select.closest !== 'function') return false;
    if (select.dataset.portalMenu === 'true') return true;
    return !!select.closest(
      '.mobile-sheet-surface, .bottom-sheet, .modal, [role="dialog"], [aria-modal="true"]'
    );
  }
  function _unportalAppSelectMenu(menu) {
    if (!menu || menu.dataset.appSelectPortaled !== 'true') return;
    const returnTo = menu._portalReturnTo;
    delete menu.dataset.appSelectPortaled;
    delete menu._portalReturnTo;
    menu.style.display = '';
    menu.style.flexDirection = '';
    menu.style.position = '';
    menu.style.bottom = '';
    menu.style.right = '';
    menu.style.left = '';
    menu.style.top = '';
    menu.style.width = '';
    menu.style.zIndex = '';
    menu.style.maxHeight = '';
    menu.style.overflowY = '';
    // dropdown-up is added by _portalAppSelectMenu when flipping above the
    // trigger; clear it on close so a future open recomputes placement.
    menu.classList.remove('dropdown-up');
    if (returnTo) returnTo.appendChild(menu);
  }
  function _closeAppSelects(exceptWrap = null) {
    _appSelects.forEach(({ wrap, trigger, menu }) => {
      if (wrap === exceptWrap) return;
      if (wrap.classList.contains('open')) _unportalAppSelectMenu(menu);
      wrap.classList.remove('open');
      trigger.setAttribute('aria-expanded', 'false');
    });
  }
  function _syncAppSelect(select) {
    const state = _appSelects.get(select);
    if (!state) return;
    const currentOptions = Array.from(select.options);
    const menuOptionsChanged = currentOptions.length !== state.options.length
      || currentOptions.some((option, index) => {
        const btn = state.options[index];
        return !btn
          || btn.dataset.value !== option.value
          || btn.textContent !== option.textContent
          || btn.disabled !== option.disabled;
      });
    if (menuOptionsChanged) {
      state.menu.replaceChildren();
      state.options = currentOptions.map(option => _buildAppSelectOption(select, option, state.menu));
    }
    const selected = select.options[select.selectedIndex] || select.options[0] || null;
    state.valueEl.textContent = selected ? selected.textContent : '';
    state.trigger.disabled = !!select.disabled;
    state.wrap.classList.toggle('disabled', !!select.disabled);
    state.options.forEach((btn) => {
      const active = btn.dataset.value === select.value;
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
      btn.classList.toggle('active', active);
      btn.classList.toggle('dropdown-item-active', active);
    });
  }
  function _buildAppSelectOption(select, option, menu) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'dropdown-item dropdown-item-touch';
    btn.setAttribute('role', 'option');
    btn.dataset.value = option.value;
    btn.textContent = option.textContent;
    btn.disabled = option.disabled;
    btn.addEventListener('click', () => {
      if (select.value !== option.value) {
        select.value = option.value;
        select.dispatchEvent(new Event('change', { bubbles: true }));
      }
      _closeAppSelects();
      _syncAppSelect(select);
    });
    menu.appendChild(btn);
    return btn;
  }
  function _enhanceAppSelect(select) {
    if (!select || _appSelects.has(select)) return;
    if (select.dataset.appSelectEnhanced === 'true') {
      const staleWrap = select.nextElementSibling;
      if (staleWrap && staleWrap.classList?.contains('app-select')) {
        const trigger = staleWrap.querySelector('.app-select-trigger');
        const valueEl = staleWrap.querySelector('.app-select-value');
        const menu = staleWrap.querySelector('.app-select-menu');
        if (trigger && valueEl && menu) {
          if (_shouldPortalAppSelect(select)) staleWrap.dataset.portalMenu = 'true';
          _appSelects.set(select, {
            wrap: staleWrap,
            trigger,
            valueEl,
            menu,
            options: Array.from(menu.querySelectorAll('[role="option"]')),
          });
          _syncAppSelect(select);
          return;
        }
        staleWrap.remove();
      }
      select.classList.remove('app-select-native');
      delete select.dataset.appSelectEnhanced;
    }
    const wrap = document.createElement('div');
    wrap.className = 'app-select';
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'app-select-trigger control-row form-control-compact';
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    const label = select.getAttribute('aria-label');
    if (label) trigger.setAttribute('aria-label', label);
    const valueEl = document.createElement('span');
    valueEl.className = 'app-select-value';
    const caret = document.createElement('span');
    caret.className = 'app-select-caret';
    caret.setAttribute('aria-hidden', 'true');
    caret.textContent = '▾';
    trigger.append(valueEl, caret);
    const menu = document.createElement('div');
    menu.className = 'app-select-menu dropdown-surface';
    menu.setAttribute('role', 'listbox');
    if (label) menu.setAttribute('aria-label', label);
    const options = Array.from(select.options).map(option => _buildAppSelectOption(select, option, menu));
    wrap.append(trigger, menu);
    select.insertAdjacentElement('afterend', wrap);
    select.classList.add('app-select-native');
    select.dataset.appSelectEnhanced = 'true';
    if (_shouldPortalAppSelect(select)) wrap.dataset.portalMenu = 'true';
    _appSelects.set(select, { wrap, trigger, valueEl, menu, options });
    trigger.addEventListener('click', () => {
      if (select.disabled) return;
      const open = wrap.classList.contains('open');
      _closeAppSelects(open ? null : wrap);
      wrap.classList.toggle('open', !open);
      trigger.setAttribute('aria-expanded', !open ? 'true' : 'false');
      if (!open) _portalAppSelectMenu(wrap, trigger, menu);
      else _unportalAppSelectMenu(menu);
    });
    trigger.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        _closeAppSelects();
        return;
      }
      if (!['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) return;
      event.preventDefault();
      const enabledOptions = options.filter((btn) => !btn.disabled);
      if (!enabledOptions.length) return;
      const currentIndex = Math.max(0, enabledOptions.findIndex((btn) => btn.dataset.value === select.value));
      const delta = event.key === 'ArrowUp' ? -1 : 1;
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        const next = enabledOptions[(currentIndex + delta + enabledOptions.length) % enabledOptions.length];
        select.value = next.dataset.value;
        select.dispatchEvent(new Event('change', { bubbles: true }));
        _syncAppSelect(select);
        return;
      }
      wrap.classList.add('open');
      trigger.setAttribute('aria-expanded', 'true');
      _portalAppSelectMenu(wrap, trigger, menu);
    });
    select.addEventListener('change', () => _syncAppSelect(select));
    _syncAppSelect(select);
  }
  const APP_SELECT_SELECTOR = 'select.form-select, .history-panel-filters select';
  function _enhanceAppSelectTree(root) {
    if (!root || typeof root.querySelectorAll !== 'function') return;
    if (typeof root.matches === 'function' && root.matches(APP_SELECT_SELECTOR)) {
      _enhanceAppSelect(root);
    }
    root.querySelectorAll(APP_SELECT_SELECTOR).forEach(_enhanceAppSelect);
  }
  function enhanceAppSelects(root = document) {
    if (!root || typeof root.querySelectorAll !== 'function') return;
    _enhanceAppSelectTree(root);
  }
  const syncAppSelect = (select) => _syncAppSelect(select);
  const closeAppSelects = (exceptWrap = null) => _closeAppSelects(exceptWrap);
  const portalDropdownMenu = (wrap, trigger, menu) => _portalAppSelectMenu(wrap, trigger, menu);
  const unportalDropdownMenu = (menu) => _unportalAppSelectMenu(menu);
  function observeAppSelects() {
    if (
      typeof MutationObserver === 'undefined'
      || !document.body
      || document.body.nodeType !== 1
    ) return;
    if (global.__darklabAppSelectObserver && typeof global.__darklabAppSelectObserver.disconnect === 'function') {
      global.__darklabAppSelectObserver.disconnect();
    }
    const observer = new MutationObserver((records) => {
      records.forEach((record) => {
        if (record.type === 'attributes') {
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
      attributeFilter: ['class'],
    });
  }
  // Exposed for non-app-select dropdowns (e.g. history compare actions menu)
  // that need the same body-portal escape from ancestor stacking contexts.
  observeAppSelects();
  enhanceAppSelects();
  if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
    document.addEventListener('click', (event) => {
      const target = event.target;
      if (target && typeof target.closest === 'function' && target.closest('.app-select')) return;
      _closeAppSelects();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') _closeAppSelects();
    });
  }
  const publicApi = {
    applyMobileTextInputDefaults,
    blurActiveElement,
    blurVisibleComposerInput,
    blurVisibleComposerInputIfMobile,
    closeAppSelects,
    enhanceAppSelects,
    focusAnyComposerInput,
    focusComposerInput,
    focusElement,
    focusVisibleComposerInput,
    getActiveComposerInput,
    getComposerInputs,
    getComposerValue,
    getMobileKeyboardOffsetBaseline,
    getMobileViewportClosedHeight,
    getVisibleComposerInput,
    handleComposerInputChange,
    hideAcDropdown,
    hideFaqOverlay,
    hideHistoryPanel,
    hideModalOverlay,
    hideMobileMenu,
    hideOptionsOverlay,
    hidePanelOverlay,
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
    isMobileMenuOpen,
    isOptionsOverlayOpen,
    isPanelOverlayOpen,
    isSearchBarOpen,
    isShortcutsOverlayOpen,
    isThemeOverlayOpen,
    isWorkflowsOverlayOpen,
    isWorkspaceOverlayOpen,
    markInteractionSurfaceReady,
    normalizeComposerSmartPeriod,
    portalDropdownMenu,
    refocusComposerAfterAction,
    setComposerValue,
    setRunButtonDisabled,
    setMobileKeyboardOpenState,
    setMobileViewportClosedHeight,
    setVisibilityState,
    showAcDropdown,
    showFaqOverlay,
    showHistoryLoadOverlay,
    hideHistoryLoadOverlay,
    showHistoryPanel,
    showHistoryRow,
    showModalOverlay,
    showMobileMenu,
    showPanelOverlay,
    showRunTimer,
    showSearchBar,
    showShortcutsOverlay,
    showTabKillBtn,
    showThemeOverlay,
    showOptionsOverlay,
    showWorkflowsOverlay,
    showWorkspaceOverlay,
    syncAppSelect,
    syncComposerSelection,
    syncFocusedComposerState,
    syncMobileComposerKeyboardState,
    syncModalOverlayState: _syncModalOverlayState,
    syncRunButtonDisabled,
    hideHistoryRow,
    hideRunTimer,
    isRunButtonDisabled,
    togglePanelOverlay,
    unportalDropdownMenu,
  };
  Object.assign(global, publicApi);
  if (typeof window !== 'undefined' && window !== global) {
    Object.assign(window, publicApi);
  }
})(globalThis);

const applyMobileTextInputDefaults = globalThis.applyMobileTextInputDefaults;
const blurActiveElement = globalThis.blurActiveElement;
const blurVisibleComposerInput = globalThis.blurVisibleComposerInput;
const blurVisibleComposerInputIfMobile = globalThis.blurVisibleComposerInputIfMobile;
const closeAppSelects = globalThis.closeAppSelects;
const enhanceAppSelects = globalThis.enhanceAppSelects;
const focusAnyComposerInput = globalThis.focusAnyComposerInput;
const focusComposerInput = globalThis.focusComposerInput;
const focusElement = globalThis.focusElement;
const focusVisibleComposerInput = globalThis.focusVisibleComposerInput;
const getActiveComposerInput = globalThis.getActiveComposerInput;
const getComposerInputs = globalThis.getComposerInputs;
const getComposerValue = globalThis.getComposerValue;
const getMobileKeyboardOffsetBaseline = globalThis.getMobileKeyboardOffsetBaseline;
const getMobileViewportClosedHeight = globalThis.getMobileViewportClosedHeight;
const getVisibleComposerInput = globalThis.getVisibleComposerInput;
const handleComposerInputChange = globalThis.handleComposerInputChange;
const hideAcDropdown = globalThis.hideAcDropdown;
const hideFaqOverlay = globalThis.hideFaqOverlay;
const hideModalOverlay = globalThis.hideModalOverlay;
const hideHistoryPanel = globalThis.hideHistoryPanel;
var exportedHideHistoryRow = globalThis.hideHistoryRow;
const hideOptionsOverlay = globalThis.hideOptionsOverlay;
const hidePanelOverlay = globalThis.hidePanelOverlay;
const hideSearchBar = globalThis.hideSearchBar;
const hideShortcutsOverlay = globalThis.hideShortcutsOverlay;
const hideTabKillBtn = globalThis.hideTabKillBtn;
const hideThemeOverlay = globalThis.hideThemeOverlay;
const hideWorkflowsOverlay = globalThis.hideWorkflowsOverlay;
const hideWorkspaceOverlay = globalThis.hideWorkspaceOverlay;
var exportedHideRunTimer = globalThis.hideRunTimer;
const isAcDropdownOpen = globalThis.isAcDropdownOpen;
const isActiveTabRunning = globalThis.isActiveTabRunning;
const isFaqOverlayOpen = globalThis.isFaqOverlayOpen;
const isHistoryPanelOpen = globalThis.isHistoryPanelOpen;
const isOptionsOverlayOpen = globalThis.isOptionsOverlayOpen;
const isPanelOverlayOpen = globalThis.isPanelOverlayOpen;
const isSearchBarOpen = globalThis.isSearchBarOpen;
const isShortcutsOverlayOpen = globalThis.isShortcutsOverlayOpen;
const isThemeOverlayOpen = globalThis.isThemeOverlayOpen;
const isWorkflowsOverlayOpen = globalThis.isWorkflowsOverlayOpen;
const isWorkspaceOverlayOpen = globalThis.isWorkspaceOverlayOpen;
var exportedIsRunButtonDisabled = globalThis.isRunButtonDisabled;
const showMobileMenu = globalThis.showMobileMenu;
const hideMobileMenu = globalThis.hideMobileMenu;
const isMobileMenuOpen = globalThis.isMobileMenuOpen;
const markInteractionSurfaceReady = globalThis.markInteractionSurfaceReady;
var exportedNormalizeComposerSmartPeriod = globalThis.normalizeComposerSmartPeriod;
const portalDropdownMenu = globalThis.portalDropdownMenu;
const refocusComposerAfterAction = globalThis.refocusComposerAfterAction;
const setComposerValue = globalThis.setComposerValue;
var exportedSetMobileKeyboardOpenState = globalThis.setMobileKeyboardOpenState;
var exportedSetMobileViewportClosedHeight = globalThis.setMobileViewportClosedHeight;
var exportedSetRunButtonDisabled = globalThis.setRunButtonDisabled;
const setVisibilityState = globalThis.setVisibilityState;
const showAcDropdown = globalThis.showAcDropdown;
const showFaqOverlay = globalThis.showFaqOverlay;
var exportedShowHistoryPanel = globalThis.showHistoryPanel;
var exportedShowHistoryRow = globalThis.showHistoryRow;
const showModalOverlay = globalThis.showModalOverlay;
const showPanelOverlay = globalThis.showPanelOverlay;
const showSearchBar = globalThis.showSearchBar;
const showShortcutsOverlay = globalThis.showShortcutsOverlay;
const showTabKillBtn = globalThis.showTabKillBtn;
var exportedShowThemeOverlay = globalThis.showThemeOverlay;
var exportedShowOptionsOverlay = globalThis.showOptionsOverlay;
var exportedShowRunTimer = globalThis.showRunTimer;
const showWorkflowsOverlay = globalThis.showWorkflowsOverlay;
const showWorkspaceOverlay = globalThis.showWorkspaceOverlay;
const syncAppSelect = globalThis.syncAppSelect;
const syncComposerSelection = globalThis.syncComposerSelection;
const syncFocusedComposerState = globalThis.syncFocusedComposerState;
const syncMobileComposerKeyboardState = globalThis.syncMobileComposerKeyboardState;
const syncModalOverlayState = globalThis.syncModalOverlayState;
const syncRunButtonDisabled = globalThis.syncRunButtonDisabled;
const togglePanelOverlay = globalThis.togglePanelOverlay;
const unportalDropdownMenu = globalThis.unportalDropdownMenu;

export {
  applyMobileTextInputDefaults,
  blurActiveElement,
  blurVisibleComposerInput,
  blurVisibleComposerInputIfMobile,
  closeAppSelects,
  enhanceAppSelects,
  focusAnyComposerInput,
  focusComposerInput,
  focusElement,
  focusVisibleComposerInput,
  getActiveComposerInput,
  getComposerInputs,
  getComposerValue,
  getMobileKeyboardOffsetBaseline,
  getMobileViewportClosedHeight,
  getVisibleComposerInput,
  handleComposerInputChange,
  hideAcDropdown,
  hideFaqOverlay,
  hideHistoryPanel,
  exportedHideHistoryRow as hideHistoryRow,
  hideModalOverlay,
  hideMobileMenu,
  hideOptionsOverlay,
  hidePanelOverlay,
  hideSearchBar,
  hideShortcutsOverlay,
  hideTabKillBtn,
  hideThemeOverlay,
  hideWorkflowsOverlay,
  hideWorkspaceOverlay,
  exportedHideRunTimer as hideRunTimer,
  isAcDropdownOpen,
  isActiveTabRunning,
  isFaqOverlayOpen,
  isHistoryPanelOpen,
  isMobileMenuOpen,
  isOptionsOverlayOpen,
  isPanelOverlayOpen,
  isSearchBarOpen,
  isShortcutsOverlayOpen,
  isThemeOverlayOpen,
  isWorkflowsOverlayOpen,
  isWorkspaceOverlayOpen,
  exportedIsRunButtonDisabled as isRunButtonDisabled,
  markInteractionSurfaceReady,
  exportedNormalizeComposerSmartPeriod as normalizeComposerSmartPeriod,
  portalDropdownMenu,
  refocusComposerAfterAction,
  setComposerValue,
  exportedSetMobileKeyboardOpenState as setMobileKeyboardOpenState,
  exportedSetMobileViewportClosedHeight as setMobileViewportClosedHeight,
  exportedSetRunButtonDisabled as setRunButtonDisabled,
  setVisibilityState,
  showAcDropdown,
  showFaqOverlay,
  exportedShowHistoryPanel as showHistoryPanel,
  exportedShowHistoryRow as showHistoryRow,
  showModalOverlay,
  showMobileMenu,
  showPanelOverlay,
  showSearchBar,
  showShortcutsOverlay,
  showTabKillBtn,
  exportedShowThemeOverlay as showThemeOverlay,
  exportedShowOptionsOverlay as showOptionsOverlay,
  exportedShowRunTimer as showRunTimer,
  showWorkflowsOverlay,
  showWorkspaceOverlay,
  syncAppSelect,
  syncComposerSelection,
  syncFocusedComposerState,
  syncMobileComposerKeyboardState,
  syncModalOverlayState,
  syncRunButtonDisabled,
  togglePanelOverlay,
  unportalDropdownMenu,
};
