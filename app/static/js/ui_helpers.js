// ── Shared UI helpers ──
(function initSharedUiHelpers(global) {
  // These helpers wrap the split desktop/mobile composer model so the rest of
  // the code can ask for "the visible input" instead of branching everywhere.
  const state = getAppState();
  let _mobileKeyboardVisibilityTimer = null;
  const getMobileMenuEl = () => mobileMenu || null;
  const isMobileTerminalViewportActive = () => !!(
    typeof useMobileTerminalViewportMode === "function"
    && useMobileTerminalViewportMode()
    && document.body
    && document.body.classList
    && document.body.classList.contains("mobile-terminal-mode")
  );

  global.getComposerInputs = () => ({
    desktop: (typeof cmdInput !== 'undefined' && cmdInput) || null,
    mobile: (typeof mobileCmdInput !== 'undefined' && mobileCmdInput) || null,
  });
  global.getVisibleComposerInput = () => {
    const { desktop, mobile } = global.getComposerInputs();
    const mobileShellActive = !!(typeof document !== 'undefined'
      && document.body
      && document.body.classList
      && document.body.classList.contains('mobile-terminal-mode'));
    if (mobileShellActive && mobile) return mobile;
    return desktop;
  };
  global.getActiveComposerInput = () => {
    const { desktop, mobile } = global.getComposerInputs();
    const visible = global.getVisibleComposerInput();
    if (visible) return visible;
    const composer = typeof getComposerState === 'function' ? getComposerState() : null;
    if (composer?.activeInput === 'mobile' && mobile) return mobile;
    if (composer?.activeInput === 'desktop' && desktop) return desktop;
    return desktop || mobile || null;
  };
  global.getComposerValue = () => {
    if (typeof getComposerState === 'function') {
      const composer = getComposerState();
      if (composer && typeof composer.value === 'string') return composer.value;
    }
    const input = global.getVisibleComposerInput();
    return input ? input.value : '';
  };
  global.getComposerSelection = () => {
    if (typeof getComposerState === 'function') {
      const composer = getComposerState();
      if (composer) {
        const value = typeof composer.value === 'string' ? composer.value : '';
        const len = value.length;
        const start = typeof composer.selectionStart === 'number' ? Math.max(0, Math.min(composer.selectionStart, len)) : len;
        const end = typeof composer.selectionEnd === 'number' ? Math.max(0, Math.min(composer.selectionEnd, len)) : len;
        return start <= end ? { start, end } : { start: end, end: start };
      }
    }
    const input = global.getVisibleComposerInput();
    if (!input) return { start: 0, end: 0 };
    const value = input.value || '';
    let start = typeof input.selectionStart === 'number' ? input.selectionStart : value.length;
    let end = typeof input.selectionEnd === 'number' ? input.selectionEnd : value.length;
    if (start > end) [start, end] = [end, start];
    return { start, end };
  };
  let _setComposerValueInProgress = false;
  const _baseSetComposerState = typeof global.setComposerState === 'function'
    ? global.setComposerState
    : null;
  function _syncComposerInputsFromState() {
    if (_setComposerValueInProgress || typeof getComposerState !== 'function') return;
    const composer = getComposerState();
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
    global.setComposerState = (next = {}) => {
      const stateSnapshot = _baseSetComposerState(next);
      _syncComposerInputsFromState();
      return stateSnapshot;
    };
    if (global.APP_STATE_API) {
      global.APP_STATE_API.setComposerState = (next) => global.setComposerState(next);
    }
  }
  global.applyMobileTextInputDefaults = (input) => {
    if (!input || typeof input.setAttribute !== 'function') return;
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('autocapitalize', 'none');
    input.setAttribute('autocorrect', 'off');
    input.setAttribute('spellcheck', 'false');
    input.setAttribute('inputmode', 'text');
  };
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
  global.focusElement = (el, { preventScroll = false } = {}) => {
    if (!el || typeof el.focus !== 'function') return false;
    try {
      if (preventScroll) el.focus({ preventScroll: true });
      else el.focus();
    } catch (_) {
      el.focus();
    }
    return true;
  };
  global.blurActiveElement = () => {
    if (typeof document === 'undefined') return false;
    const active = document.activeElement;
    if (!active || typeof active.blur !== 'function') return false;
    active.blur();
    return true;
  };
  global.focusComposerInput = (input = null, { preventScroll = false } = {}) => {
    const target = input || global.getVisibleComposerInput();
    return global.focusElement(target, { preventScroll });
  };
  global.focusVisibleComposerInput = ({ preventScroll = false } = {}) => {
    if (isMobileTerminalViewportActive()) return false;
    const target = (typeof getVisibleComposerInput === 'function')
      ? getVisibleComposerInput()
      : global.getVisibleComposerInput();
    return global.focusComposerInput(target, { preventScroll });
  };
  global.getMobileKeyboardOffsetBaseline = () => state._mobileKeyboardOffsetBaseline;
  global.setMobileKeyboardOffsetBaseline = (value) => {
    state._mobileKeyboardOffsetBaseline = typeof value === 'number' ? value : null;
    return state._mobileKeyboardOffsetBaseline;
  };
  global.getMobileViewportClosedHeight = () => state._mobileViewportClosedHeight;
  global.setMobileViewportClosedHeight = (value) => {
    state._mobileViewportClosedHeight = typeof value === 'number' ? value : null;
    return state._mobileViewportClosedHeight;
  };
  global.getMobileKeyboardLastOpenOffset = () => state._mobileKeyboardLastOpenOffset || 0;
  global.setMobileKeyboardLastOpenOffset = (value) => {
    state._mobileKeyboardLastOpenOffset = Math.max(0, Number(value) || 0);
    return state._mobileKeyboardLastOpenOffset;
  };
  global.blurVisibleComposerInput = () => {
    const target = (typeof getVisibleComposerInput === 'function')
      ? getVisibleComposerInput()
      : global.getVisibleComposerInput();
    if (!target || typeof target.blur !== 'function') return false;
    target.blur();
    return true;
  };
  global.blurVisibleComposerInputIfMobile = () => {
    if (typeof useMobileTerminalViewportMode !== 'function' || !useMobileTerminalViewportMode()) return false;
    return global.blurVisibleComposerInput();
  };
  global.focusAnyComposerInput = ({ preventScroll = false } = {}) => {
    return global.focusVisibleComposerInput({ preventScroll });
  };
  global.syncMobileComposerKeyboardState = (offset = null, { active = true, open = null } = {}) => {
    if (typeof document === 'undefined' || !document.body || !document.body.classList) return false;
    const requestedOffset = typeof offset === 'number' ? offset : 0;
    const requestedOpen = typeof open === 'boolean'
      ? open
      : document.body.classList.contains('mobile-keyboard-open');
    const lastOpenOffset = global.getMobileKeyboardLastOpenOffset();
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
      if (typeof emitUiEvent === 'function') emitUiEvent('app:mobile-keyboard-state', { open: false });
      return false;
    }
    if (typeof state._mobileKeyboardOffsetBaseline !== 'number') {
      state._mobileKeyboardOffsetBaseline = nextOffset;
    }
    const nextOpen = requestedOpen;
    if (nextOpen && nextOffset > 0) state._mobileKeyboardLastOpenOffset = nextOffset;
    if (!nextOpen) state._mobileKeyboardOffsetBaseline = nextOffset;
    document.body.classList.toggle('mobile-keyboard-open', nextOpen);
    if (typeof emitUiEvent === 'function') emitUiEvent('app:mobile-keyboard-state', { open: !!nextOpen });
    return nextOpen;
  };
  global.setMobileKeyboardOpenState = (open, { delay = 0 } = {}) => {
    if (typeof document === 'undefined' || !document.body || !document.body.classList) return false;
    if (_mobileKeyboardVisibilityTimer) {
      clearTimeout(_mobileKeyboardVisibilityTimer);
      _mobileKeyboardVisibilityTimer = null;
    }

    const applyOpen = () => {
      const wasKeyboardOpen = document.body.classList.contains('mobile-keyboard-open');
      document.body.classList.toggle('mobile-keyboard-open', !!open);
      if (open && !wasKeyboardOpen) {
        if (typeof hideMobileMenu === 'function') hideMobileMenu();
        if (typeof isHistoryPanelOpen === 'function' && isHistoryPanelOpen() && typeof hideHistoryPanel === 'function') {
          hideHistoryPanel();
        }
        if (typeof acHide === 'function') acHide();
      }
      if (typeof emitUiEvent === 'function') emitUiEvent('app:mobile-keyboard-state', { open: !!open });
      return !!open;
    };

    if (open) {
      return applyOpen();
    }

    const closeDelay = Math.max(0, Number(delay) || 0);
    if (closeDelay === 0) {
      return applyOpen();
    }

    _mobileKeyboardVisibilityTimer = setTimeout(() => {
      _mobileKeyboardVisibilityTimer = null;
      const mobileInput = typeof getVisibleComposerInput === 'function' ? getVisibleComposerInput() : null;
      const keyboardStillOpen = !!(
        mobileInput
        && document.activeElement === mobileInput
        && typeof getMobileKeyboardOffset === 'function'
        && typeof isMobileKeyboardOpen === 'function'
        && isMobileKeyboardOpen(getMobileKeyboardOffset())
      );
      if (keyboardStillOpen) return;
      document.body.classList.remove('mobile-keyboard-open');
      if (typeof emitUiEvent === 'function') emitUiEvent('app:mobile-keyboard-state', { open: false });
      // Reset keyboard CSS vars to their closed-keyboard values. Use window.innerHeight
      // rather than visualViewport.height — the keyboard animation may still be in
      // progress at this point, leaving visualViewport.height at a mid-animation
      // (shrunk) value that would break the layout.  window.innerHeight is stable
      // on iOS and unaffected by the software keyboard.
      if (typeof window !== 'undefined' && document.documentElement) {
        const h = window.innerHeight || 0;
        if (h > 0) document.documentElement.style.setProperty('--mobile-viewport-height', `${h}px`);
        global.syncMobileComposerKeyboardState(0, { open: false });
      }
    }, closeDelay);
    return false;
  };
  global.setComposerValue = (value, start = null, end = null, { dispatch = true, exclude = null } = {}) => {
    const nextValue = String(value ?? '');
    const nextStart = typeof start === 'number' ? start : nextValue.length;
    const nextEnd = typeof end === 'number' ? end : nextStart;
    const target = typeof getActiveComposerInput === 'function'
      ? getActiveComposerInput()
      : global.getVisibleComposerInput();
    if (typeof setComposerState === 'function') {
      _setComposerValueInProgress = true;
      try {
        setComposerState({
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
      // Skip programmatic value assignment on the excluded input (typically the
      // source that just triggered an input event). Assigning .value on a focused
      // input resets the browser's OS key-repeat state, breaking hold-to-repeat.
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
  global.syncComposerSelection = (start = null, end = null, { input = null } = {}) => {
    const target = input || global.getActiveComposerInput();
    const composer = typeof getComposerState === 'function' ? getComposerState() : null;
    const value = composer && typeof composer.value === 'string'
      ? composer.value
      : (target && typeof target.value === 'string' ? target.value : '');
    const len = value.length;
    const nextStart = typeof start === 'number' ? Math.max(0, Math.min(start, len)) : len;
    const nextEnd = typeof end === 'number' ? Math.max(0, Math.min(end, len)) : nextStart;
    const orderedStart = Math.min(nextStart, nextEnd);
    const orderedEnd = Math.max(nextStart, nextEnd);
    if (typeof setComposerState === 'function') {
      setComposerState({
        selectionStart: orderedStart,
        selectionEnd: orderedEnd,
        activeInput: (typeof document !== 'undefined'
          && document.body
          && document.body.classList
          && document.body.classList.contains('mobile-terminal-mode'))
          ? 'mobile'
          : 'desktop',
      });
    }
    if (target && typeof target.setSelectionRange === 'function') {
      target.setSelectionRange(orderedStart, orderedEnd);
    }
    _syncComposerCaretVisibility(target, orderedStart, orderedEnd);
    return { start: orderedStart, end: orderedEnd };
  };
  global.syncFocusedComposerState = (input = null) => {
    const target = input || global.getActiveComposerInput();
    if (!target || typeof target.value !== 'string') return null;
    const value = target.value;
    const start = typeof target.selectionStart === 'number' ? target.selectionStart : value.length;
    const end = typeof target.selectionEnd === 'number' ? target.selectionEnd : start;
    if (typeof setComposerState === 'function') {
      setComposerState({
        value,
        selectionStart: start,
        selectionEnd: end,
        activeInput: target === global.getComposerInputs().mobile ? 'mobile' : 'desktop',
      });
    }
    return { value, start, end, input: target };
  };
  global.handleComposerInputChange = (sourceInput) => {
    if (!sourceInput) return;
    // Typing always snaps the output back to bottom so the prompt stays visible.
    const _activeTab = typeof getActiveTab === 'function' ? getActiveTab() : null;
    if (_activeTab) _activeTab.followOutput = true;
    const _out = typeof document !== 'undefined'
      ? document.querySelector('.tab-panel.active .output') : null;
    if (_out) _out.scrollTop = _out.scrollHeight;
    if (typeof syncShellPrompt === 'function') syncShellPrompt();
    if (typeof syncMobileViewportState === 'function') syncMobileViewportState();
    const value = sourceInput.value;
    const start = typeof sourceInput.selectionStart === 'number' ? sourceInput.selectionStart : value.length;
    const end = typeof sourceInput.selectionEnd === 'number' ? sourceInput.selectionEnd : value.length;
    global.setComposerValue(value, start, end, { dispatch: false, exclude: sourceInput });
    const keepHistoryNav = typeof _suspendCmdHistoryNavReset !== 'undefined' && _suspendCmdHistoryNavReset;
    if (keepHistoryNav) _suspendCmdHistoryNavReset = false;
    else if (typeof resetCmdHistoryNav === 'function') resetCmdHistoryNav();
    if (value.length > 0 && typeof requestWelcomeSettle === 'function') {
      requestWelcomeSettle(activeTabId);
    }
    if (typeof acSuppressInputOnce !== 'undefined' && acSuppressInputOnce) {
      acSuppressInputOnce = false;
      if (typeof acHide === 'function') acHide();
      return;
    }
    acIndex = -1;
    if (!value.trim()) {
      if (typeof acHide === 'function') acHide();
      return;
    }
    const usedContextMatcher = typeof getAutocompleteMatches === 'function';
    const contextMatches = usedContextMatcher ? getAutocompleteMatches(value, start) : [];
    acFiltered = usedContextMatcher
      ? (typeof limitAutocompleteMatchesForDisplay === 'function'
        ? limitAutocompleteMatchesForDisplay(contextMatches, 12)
        : contextMatches.slice(0, 12))
      : ((typeof acSuggestions !== 'undefined' && acSuggestions ? acSuggestions : [])
        .filter(s => s.toLowerCase().startsWith(value.toLowerCase()))
        .slice(0, 12));
    if (!acFiltered.length) {
      if (typeof acHide === 'function') acHide();
      return;
    }
    if (!usedContextMatcher) {
      const q = value.trim().toLowerCase();
      if (acFiltered.some(s => String(s || '').toLowerCase() === q)) {
        if (typeof acHide === 'function') acHide();
        return;
      }
    }
    if (typeof acShow === 'function') acShow(acFiltered);
  };
  global.showPanelOverlay = (el) => {
    if (el && el.classList) el.classList.add('open');
  };
  global.hidePanelOverlay = (el) => {
    if (el && el.classList) el.classList.remove('open');
  };
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
    const isMobileMode = typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode();
    // Intentional no-op on the mobile terminal viewport: programmatically
    // refocusing would re-pop the software keyboard, which users don't want
    // after every chrome action.
    if (isMobileMode) return false;
    if (typeof global.isConfirmOpen === 'function' && global.isConfirmOpen()) return false;
    const target = typeof getVisibleComposerInput === 'function' ? getVisibleComposerInput() : null;
    if (target && typeof focusComposerInput === 'function' && focusComposerInput(target, { preventScroll })) {
      return true;
    }
    if (typeof focusAnyComposerInput === 'function' && focusAnyComposerInput({ preventScroll })) return true;
    return false;
  }
  global.refocusComposerAfterAction = ({ preventScroll = true, defer = false } = {}) => {
    if (defer) {
      setTimeout(() => { _doRefocusComposer(preventScroll); }, 0);
      return undefined;
    }
    return _doRefocusComposer(preventScroll);
  };
  global.togglePanelOverlay = (el, force = null) => {
    if (!el || !el.classList) return false;
    const next = force === null ? !el.classList.contains('open') : !!force;
    el.classList.toggle('open', next);
    return next;
  };
  global.isPanelOverlayOpen = (el) => !!(el && el.classList && el.classList.contains('open'));
  global.showModalOverlay = (el, display = 'flex') => {
    if (el && el.style) el.style.display = display;
  };
  global.hideModalOverlay = (el) => {
    if (el && el.style) el.style.display = 'none';
  };
  global.toggleModalOverlay = (el, force = null, display = 'flex') => {
    if (!el || !el.style) return false;
    const next = force === null ? el.style.display !== display : !!force;
    el.style.display = next ? display : 'none';
    return next;
  };
  global.isModalOverlayOpen = (el, display = 'flex') => !!(el && el.style && el.style.display === display);
  global.showHistoryPanel = () => showPanelOverlay(historyPanel);
  global.hideHistoryPanel = () => {
    hidePanelOverlay(historyPanel);
    if (typeof refocusComposerAfterAction === 'function') refocusComposerAfterAction({ preventScroll: true });
  };
  global.isHistoryPanelOpen = () => isPanelOverlayOpen(historyPanel);
  global.showWorkflowsOverlay = () => showPanelOverlay(workflowsOverlay || null);
  global.hideWorkflowsOverlay = () => hidePanelOverlay(workflowsOverlay || null);
  global.isWorkflowsOverlayOpen = () => isPanelOverlayOpen(workflowsOverlay || null);
  global.showFaqOverlay = () => showPanelOverlay(faqOverlay || null);
  global.hideFaqOverlay = () => hidePanelOverlay(faqOverlay || null);
  global.isFaqOverlayOpen = () => isPanelOverlayOpen(faqOverlay || null);
  global.showShortcutsOverlay = () => {
    const el = typeof shortcutsOverlay !== 'undefined' ? shortcutsOverlay : null;
    if (el) el.setAttribute('aria-hidden', 'false');
    showPanelOverlay(el);
  };
  global.hideShortcutsOverlay = () => {
    const el = typeof shortcutsOverlay !== 'undefined' ? shortcutsOverlay : null;
    if (el) el.setAttribute('aria-hidden', 'true');
    hidePanelOverlay(el);
  };
  global.isShortcutsOverlayOpen = () => {
    const el = typeof shortcutsOverlay !== 'undefined' ? shortcutsOverlay : null;
    return isPanelOverlayOpen(el);
  };
  global.showThemeOverlay = () => showPanelOverlay(themeOverlay || null);
  global.hideThemeOverlay = () => hidePanelOverlay(themeOverlay || null);
  global.isThemeOverlayOpen = () => isPanelOverlayOpen(themeOverlay || null);
  global.showOptionsOverlay = () => showPanelOverlay(optionsOverlay || null);
  global.hideOptionsOverlay = () => hidePanelOverlay(optionsOverlay || null);
  global.isOptionsOverlayOpen = () => isPanelOverlayOpen(optionsOverlay || null);
  const getWorkspaceOverlay = () => (
    typeof workspaceOverlay !== 'undefined' && workspaceOverlay ? workspaceOverlay : null
  );
  global.showWorkspaceOverlay = () => showPanelOverlay(getWorkspaceOverlay());
  global.hideWorkspaceOverlay = () => hidePanelOverlay(getWorkspaceOverlay());
  global.isWorkspaceOverlayOpen = () => isPanelOverlayOpen(getWorkspaceOverlay());
  global.showHistoryLoadOverlay = () => {
    if (historyLoadOverlay && historyLoadOverlay.classList) historyLoadOverlay.classList.add('open');
    if (historyLoadOverlay) historyLoadOverlay.setAttribute('aria-hidden', 'false');
  };
  global.hideHistoryLoadOverlay = () => {
    if (historyLoadOverlay && historyLoadOverlay.classList) historyLoadOverlay.classList.remove('open');
    if (historyLoadOverlay) historyLoadOverlay.setAttribute('aria-hidden', 'true');
  };
  global.isHistoryLoadOverlayOpen = () => !!(historyLoadOverlay && historyLoadOverlay.classList && historyLoadOverlay.classList.contains('open'));
  // Initialise inline display so the inline style takes precedence over the
  // conflicting .search-bar { display: flex } class rule (same specificity,
  // later in the sheet) when .u-hidden is also present on the element.
  if (typeof searchBar !== 'undefined' && searchBar && searchBar.style) searchBar.style.display = 'none';
  global.showSearchBar = () => {
    if (searchBar && searchBar.style) searchBar.style.display = 'flex';
  };
  global.hideSearchBar = () => {
    if (searchBar && searchBar.style) searchBar.style.display = 'none';
    refocusComposerAfterAction({ preventScroll: true });
  };
  global.isSearchBarOpen = () => !!(searchBar && searchBar.style && searchBar.style.display === 'flex');
  global.showHistoryRow = () => {
    if (histRow && histRow.style) histRow.style.display = 'flex';
  };
  global.hideHistoryRow = () => {
    if (histRow && histRow.style) histRow.style.display = 'none';
  };
  global.isHistoryRowVisible = () => !!(histRow && histRow.style && histRow.style.display !== 'none');
  global.showRunTimer = () => {
    if (runTimer && runTimer.style) runTimer.style.display = 'inline';
  };
  global.hideRunTimer = () => {
    if (runTimer && runTimer.style) runTimer.style.display = 'none';
    if (runTimer) runTimer.textContent = '';
  };
  global.isRunTimerVisible = () => !!(runTimer && runTimer.style && runTimer.style.display !== 'none');
  global.setRunButtonDisabled = (disabled) => {
    const next = !!disabled;
    if (typeof runBtn !== 'undefined' && runBtn) runBtn.disabled = next;
    if (typeof mobileRunBtn !== 'undefined' && mobileRunBtn) mobileRunBtn.disabled = next;
  };
  global.syncRunButtonDisabled = () => {
    const active = typeof getActiveTab === 'function' ? getActiveTab() : null;
    const composerValue = typeof global.getComposerValue === 'function' ? String(global.getComposerValue() || '') : '';
    const disabled = !!(active && active.st === 'running') || !composerValue.trim();
    if (typeof runBtn !== 'undefined' && runBtn) runBtn.disabled = disabled;
    if (typeof mobileRunBtn !== 'undefined' && mobileRunBtn) mobileRunBtn.disabled = disabled;
    return disabled;
  };
  global.isRunButtonDisabled = () => !!((runBtn && runBtn.disabled) || (typeof mobileRunBtn !== 'undefined' && mobileRunBtn && mobileRunBtn.disabled));
  const syncTerminalActionLayout = (tabId) => {
    const btn = (typeof tabPanels !== 'undefined' && tabPanels)
      ? tabPanels.querySelector(`.tab-kill-btn[data-tab="${tabId}"]`)
      : null;
    const actions = btn && btn.parentElement && btn.parentElement.classList && btn.parentElement.classList.contains('terminal-actions')
      ? btn.parentElement
      : null;
    if (!actions) return;
    const hasVisibleKill = !!(btn.style ? btn.style.display !== 'none' : !btn.hidden);
    actions.classList.toggle('terminal-actions-has-visible-kill', hasVisibleKill);
  };
  global.showTabKillBtn = (tabId) => {
    const btn = (typeof tabPanels !== 'undefined' && tabPanels) ? tabPanels.querySelector(`.tab-kill-btn[data-tab="${tabId}"]`) : null;
    if (btn) {
      btn.hidden = false;
      if (btn.style) btn.style.display = 'inline-block';
    }
    syncTerminalActionLayout(tabId);
    if (typeof emitUiEvent === 'function') emitUiEvent('app:tab-kill-visibility-changed', { tabId, visible: true });
  };
  global.hideTabKillBtn = (tabId) => {
    const btn = (typeof tabPanels !== 'undefined' && tabPanels) ? tabPanels.querySelector(`.tab-kill-btn[data-tab="${tabId}"]`) : null;
    if (btn) {
      btn.hidden = true;
      if (btn.style) btn.style.display = 'none';
    }
    syncTerminalActionLayout(tabId);
    if (typeof emitUiEvent === 'function') emitUiEvent('app:tab-kill-visibility-changed', { tabId, visible: false });
  };
  // Fallbacks. mobile_chrome.js overrides these with sheet-aware versions when
  // the mobile shell initializes; these stubs only run if that init didn't.
  global.showMobileMenu = () => {
    const mobileMenu = getMobileMenuEl();
    if (mobileMenu && mobileMenu.classList) mobileMenu.classList.remove('u-hidden');
  };
  global.hideMobileMenu = () => {
    const mobileMenu = getMobileMenuEl();
    if (mobileMenu && mobileMenu.classList) mobileMenu.classList.add('u-hidden');
  };
  global.isMobileMenuOpen = () => {
    const mobileMenu = getMobileMenuEl();
    return !!(mobileMenu && mobileMenu.classList && !mobileMenu.classList.contains('u-hidden'));
  };
  global.showAcDropdown = () => {
    if (!acDropdown) return;
    if (acDropdown.classList) acDropdown.classList.remove('u-hidden');
    if (acDropdown.style) acDropdown.style.display = 'block';
  };
  global.hideAcDropdown = () => {
    if (!acDropdown) return;
    if (acDropdown.classList) acDropdown.classList.add('u-hidden');
    if (acDropdown.style) acDropdown.style.display = 'none';
  };
  global.isAcDropdownOpen = () => !!(acDropdown && acDropdown.style && acDropdown.style.display !== 'none');
  global.setVisibilityState = (el, hidden, ariaHidden = null) => {
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
  global.setDisplayState = (el, visible, display = 'block') => {
    if (!el || !el.style) return;
    el.style.display = visible ? display : 'none';
  };
})(globalThis);
