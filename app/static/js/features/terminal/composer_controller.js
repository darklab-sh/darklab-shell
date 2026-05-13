// ── Terminal composer controller ──
// Owns prompt focus/paste behavior, autocomplete loading, and keyboard handling.

function _isMajorSurfaceOpenForPromptPaste() {
  return (
    isFaqOverlayOpen()
    || isOptionsOverlayOpen()
    || isThemeOverlayOpen()
    || isWorkflowsOverlayOpen()
    || (typeof isWorkspaceOverlayOpen === 'function' && isWorkspaceOverlayOpen())
    || (typeof isHistoryCompareOverlayOpen === 'function' && isHistoryCompareOverlayOpen())
    || (typeof isHistoryRunOverlayOpen === 'function' && isHistoryRunOverlayOpen())
    || isHistoryPanelOpen()
    || (typeof isConfirmOpen === 'function' && isConfirmOpen())
  );
}

document.addEventListener('paste', e => {
  if (e.defaultPrevented) return;
  if (!cmdInput || isEditableTarget(e.target) || _isMajorSurfaceOpenForPromptPaste()) return;
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
  refocusComposerAfterAction({ preventScroll: true });
  const value = typeof getComposerValue === 'function' ? getComposerValue() : (cmdInput.value || '');
  const { start, end } = getCmdSelection(value);
  replaceCmdRange(value, start, end, text);
});

// bindOutsideClickClose owns ambient click dismissal for the two surfaces
// that have no scrim of their own (the history side panel and the
// autocomplete dropdown). The mobile menu sheet's dismissal is owned by
// its bindDismissible registration in mobile_chrome.js — the scrim covers
// the viewport so every outside click hits it.
if (historyPanel && typeof bindOutsideClickClose === 'function') {
  bindOutsideClickClose(historyPanel, {
    triggers: null,
    isOpen: isHistoryPanelOpen,
    onClose: hideHistoryPanel,
    exemptSelectors: ['.hist-chip-overflow', '[data-action="history"]', '.modal-overlay', '#history-compare-overlay'],
  });
}
if (typeof bindOutsideClickClose === 'function' && typeof shellPromptWrap !== 'undefined' && shellPromptWrap) {
  // Autocomplete dismissal: the dropdown itself is a transient element, so we
  // anchor the helper on the prompt wrap (always present) and exempt the
  // dropdown + mobile composer via selectors. Any click outside all three
  // zones hides the dropdown, matching the prior global-click behavior.
  bindOutsideClickClose(shellPromptWrap, {
    isOpen: () => typeof isAcDropdownOpen === 'function' && isAcDropdownOpen(),
    onClose: () => { if (typeof acHide === 'function') acHide(); },
    exemptSelectors: ['.ac-dropdown', '#mobile-composer'],
  });
}

function _handleRunningComposerShortcut(e) {
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'c' || e.key === 'C')) {
    e.preventDefault();
    e.stopPropagation();
    confirmKill(activeTabId);
    return true;
  }

  const isCtrlD = e.ctrlKey && !e.metaKey && !e.altKey && (
    e.key === 'd'
    || e.key === 'D'
    || (typeof eventMatchesLetter === 'function' && eventMatchesLetter(e, 'd'))
  );
  if (isCtrlD) {
    e.preventDefault();
    e.stopPropagation();
    return true;
  }

  if (typeof handleTabShortcut === 'function' && handleTabShortcut(e)) {
    e.stopPropagation();
    return true;
  }

  if (typeof handleActionShortcut === 'function' && handleActionShortcut(e)) {
    e.stopPropagation();
    return true;
  }

  if (typeof handleChromeShortcut === 'function' && handleChromeShortcut(e)) {
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

if (typeof shellPromptWrap !== 'undefined' && shellPromptWrap && cmdInput) {
  shellPromptWrap.addEventListener('pointerdown', e => {
    if (e.target === runBtn || (e.target && e.target.closest && e.target.closest('#run-btn'))) return;
    if (useMobileTerminalViewportMode()) {
      e.preventDefault();
      focusCommandInputFromGesture();
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
      focusCommandInputFromGesture();
    }
  }, { passive: false });
  shellPromptWrap.addEventListener('click', e => {
    if (e.target === runBtn || (e.target && e.target.closest && e.target.closest('#run-btn'))) return;
    if (useMobileTerminalViewportMode()) {
      focusCommandInputFromGesture();
      return;
    }
    if (e.detail > 1 || Date.now() < _suppressPromptFocusUntil) return;
    if (_selectionTouchesElement(shellPromptWrap)) return;
    if (_pendingPromptFocusTimer) clearTimeout(_pendingPromptFocusTimer);
    _pendingPromptFocusTimer = setTimeout(() => {
      _pendingPromptFocusTimer = null;
      if (_selectionTouchesElement(shellPromptWrap)) return;
      if (Date.now() < _suppressPromptFocusUntil) return;
      focusCommandInputFromGesture();
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

_bindMobileComposerInteractions(_mobileUiLayoutRefs);

if (cmdInput) {
  cmdInput.addEventListener('focus', () => {
    if (typeof setComposerState === 'function') {
      setComposerState({
        value: cmdInput.value || '',
        selectionStart: typeof cmdInput.selectionStart === 'number' ? cmdInput.selectionStart : (cmdInput.value || '').length,
        selectionEnd: typeof cmdInput.selectionEnd === 'number' ? cmdInput.selectionEnd : (cmdInput.value || '').length,
        activeInput: 'desktop',
      });
    }
    if (typeof shellPromptWrap !== 'undefined' && shellPromptWrap) shellPromptWrap.classList.add('shell-prompt-focused');
    syncShellPrompt();
    syncMobileViewportState();
  });
  cmdInput.addEventListener('blur', () => {
    if (typeof shellPromptWrap !== 'undefined' && shellPromptWrap) shellPromptWrap.classList.remove('shell-prompt-focused');
    syncShellPrompt();
    syncMobileViewportState();
  });
  cmdInput.addEventListener('select', syncShellPrompt);
  cmdInput.addEventListener('keyup', syncShellPrompt);
}

if (typeof document !== 'undefined') {
  document.addEventListener('selectionchange', () => {
    if (!cmdInput) return;
    if (typeof shellPromptWrap !== 'undefined' && shellPromptWrap && _selectionTouchesElement(shellPromptWrap)) {
      if (_pendingPromptFocusTimer) {
        clearTimeout(_pendingPromptFocusTimer);
        _pendingPromptFocusTimer = null;
      }
      return;
    }
    const composerInputs = typeof getComposerInputs === 'function' ? getComposerInputs() : {};
    const mobileInput = composerInputs.mobile || null;
    if (document.activeElement === cmdInput) {
      if (typeof setComposerState === 'function') {
        setComposerState({
          value: cmdInput.value || '',
          selectionStart: typeof cmdInput.selectionStart === 'number' ? cmdInput.selectionStart : (cmdInput.value || '').length,
          selectionEnd: typeof cmdInput.selectionEnd === 'number' ? cmdInput.selectionEnd : (cmdInput.value || '').length,
          activeInput: 'desktop',
        });
      }
      syncShellPrompt();
      return;
    }
    if (mobileInput && document.activeElement === mobileInput) {
      if (typeof setComposerState === 'function') {
        setComposerState({
          value: mobileInput.value || '',
          selectionStart: typeof mobileInput.selectionStart === 'number' ? mobileInput.selectionStart : (mobileInput.value || '').length,
          selectionEnd: typeof mobileInput.selectionEnd === 'number' ? mobileInput.selectionEnd : (mobileInput.value || '').length,
          activeInput: 'mobile',
        });
      }
      syncShellPrompt();
    }
  });
}

apiFetch('/autocomplete').then(r => r.json()).then(data => {
  acSuggestions = data.suggestions || [];
  acContextRegistry = data.context || {};
  acWordlists = Array.isArray(data.wordlists) ? data.wordlists : [];
  acSpecialCommands = data.special_commands || [];
  acBuiltinCommandRoots = data.builtin_command_roots || [];
  if (typeof loadSessionVariables === 'function') loadSessionVariables().catch(() => {});
  if (typeof loadRecentDomains === 'function') loadRecentDomains().catch(() => {});
  if (typeof loadProjectAutocompleteTargets === 'function') loadProjectAutocompleteTargets().catch(() => {});
  if (typeof scheduleSearchDiscoverabilityRefresh === 'function') scheduleSearchDiscoverabilityRefresh();
  else if (typeof refreshSearchDiscoverabilityUi === 'function') refreshSearchDiscoverabilityUi();
}).catch(err => {
  logClientError('failed to load /autocomplete', err);
});

cmdInput.addEventListener('input', () => {
  if (typeof normalizeComposerSmartPeriod === 'function') normalizeComposerSmartPeriod(cmdInput);
  if (isHistoryPanelOpen()) hideHistoryPanel();
  if (typeof isHistSearchMode === 'function' && isHistSearchMode()) {
    if (typeof handleHistSearchInput === 'function') {
      // Read the DOM value directly — the hist-search path intentionally
      // short-circuits handleComposerInputChange, so the shared composer
      // state is one keystroke stale (reads showed the pre-backspace query).
      handleHistSearchInput(cmdInput.value);
    }
    const _hsTab = typeof getActiveTab === 'function' ? getActiveTab() : null;
    if (_hsTab) _hsTab.followOutput = true;
    const _hsOut = document.querySelector('.tab-panel.active .output');
    if (_hsOut) _hsOut.scrollTop = _hsOut.scrollHeight;
    return;
  }
  handleComposerInputChange(cmdInput);
  // Keep the active tab's draft current so activateTab can read it directly.
  const _activeTab = typeof getActiveTab === 'function' ? getActiveTab() : null;
  if (_activeTab && _activeTab.st !== 'running') {
    _activeTab.draftInput = (typeof getComposerValue === 'function') ? getComposerValue() : cmdInput.value;
    if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
  }
});

cmdInput.addEventListener('keydown', e => {
  if (isAnyPanelOverlayOpen()) {
    if (e.key === 'Escape') {
      closeFaq(); closeWorkflows(); if (typeof closeWorkspace === 'function') closeWorkspace(); closeOptions(); closeThemeSelector();
      refocusComposerAfterAction({ defer: true });
      e.preventDefault();
    }
    return;
  }
  if (typeof isHistSearchMode === 'function' && isHistSearchMode()) {
    if (typeof handleHistSearchKey === 'function' && handleHistSearchKey(e)) return;
  }

  if (typeof isActiveTabRunning === 'function' && isActiveTabRunning()) {
    if (_handleRunningComposerShortcut(e)) return;
    if (typeof acHide === 'function') acHide();
    e.preventDefault();
    return;
  }

  const isWordArrowLeft = e.key === 'ArrowLeft' || eventMatchesCode(e, 'ArrowLeft');
  const isWordArrowRight = e.key === 'ArrowRight' || eventMatchesCode(e, 'ArrowRight');
  if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey && (isWordArrowLeft || isWordArrowRight)) {
    e.preventDefault();
    e.stopPropagation();
    if (typeof syncFocusedComposerState === 'function') syncFocusedComposerState(cmdInput);
    const value = typeof getComposerValue === 'function' ? getComposerValue() : '';
    const { start, end } = getCmdSelection(value);
    const next = isWordArrowLeft
      ? findWordBoundaryLeft(value, start)
      : findWordBoundaryRight(value, end);
    const input = typeof getVisibleComposerInput === 'function' ? getVisibleComposerInput() : cmdInput;
    if (typeof syncComposerSelection === 'function') syncComposerSelection(next, next, { input });
    if (input && typeof input.setSelectionRange === 'function' && input.selectionStart !== next) {
      input.setSelectionRange(next, next);
    } else if (!input && cmdInput && typeof cmdInput.setSelectionRange === 'function') {
      cmdInput.setSelectionRange(next, next);
    }
    syncShellPrompt();
    return;
  }

  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'r' || e.key === 'R')) {
    e.preventDefault();
    if (typeof enterHistSearch === 'function') enterHistSearch();
    return;
  }

  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'c' || e.key === 'C')) {
    e.preventDefault();
    if (_welcomeActive && welcomeOwnsTab(activeTabId)) {
      _welcomePromptAfterSettle = true;
      requestWelcomeSettle(activeTabId);
      refocusComposerAfterAction({ defer: true });
      return;
    }
    const activeTab = getActiveTab();
    if (activeTab && activeTab.st === 'running') {
      confirmKill(activeTabId);
      return;
    }
    if (hasActiveTerminalConfirm()) {
      cancelPendingTerminalConfirm(activeTabId);
      return;
    }
    interruptPromptLine(activeTabId);
    return;
  }

  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'w' || e.key === 'W')) {
    e.preventDefault();
    const value = typeof getComposerValue === 'function' ? getComposerValue() : '';
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
    const value = typeof getComposerValue === 'function' ? getComposerValue() : '';
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
    if (typeof syncComposerSelection === 'function') syncComposerSelection(0, 0);
    else if (cmdInput && typeof cmdInput.setSelectionRange === 'function') cmdInput.setSelectionRange(0, 0);
    syncShellPrompt();
    return;
  }

  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault();
    const value = typeof getComposerValue === 'function' ? getComposerValue() : '';
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
    const value = typeof getComposerValue === 'function' ? getComposerValue() : '';
    const end = value.length;
    if (typeof syncComposerSelection === 'function') syncComposerSelection(end, end);
    else if (cmdInput && typeof cmdInput.setSelectionRange === 'function') cmdInput.setSelectionRange(end, end);
    syncShellPrompt();
    return;
  }

  if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey && eventMatchesLetter(e, 'b')) {
    e.preventDefault();
    if (typeof syncFocusedComposerState === 'function') syncFocusedComposerState(cmdInput);
    const value = typeof getComposerValue === 'function' ? getComposerValue() : '';
    const { start } = getCmdSelection(value);
    const next = findWordBoundaryLeft(value, start);
    if (typeof syncComposerSelection === 'function') syncComposerSelection(next, next);
    else if (cmdInput && typeof cmdInput.setSelectionRange === 'function') cmdInput.setSelectionRange(next, next);
    syncShellPrompt();
    return;
  }

  if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey && eventMatchesLetter(e, 'f')) {
    e.preventDefault();
    if (typeof syncFocusedComposerState === 'function') syncFocusedComposerState(cmdInput);
    const value = typeof getComposerValue === 'function' ? getComposerValue() : '';
    const { end } = getCmdSelection(value);
    const next = findWordBoundaryRight(value, end);
    if (typeof syncComposerSelection === 'function') syncComposerSelection(next, next);
    else if (cmdInput && typeof cmdInput.setSelectionRange === 'function') cmdInput.setSelectionRange(next, next);
    syncShellPrompt();
    return;
  }

  if (e.key === 'Enter') {
    if (_welcomeActive && welcomeOwnsTab(activeTabId) && !(typeof getComposerValue === 'function' ? getComposerValue() : '').trim()) {
      e.preventDefault();
      requestWelcomeSettle(activeTabId);
      refocusComposerAfterAction({ defer: true });
      return;
    }
    if (
      !hasActiveTerminalConfirm()
      && acIndex >= 0
      && acFiltered[acIndex]
      && !acAutocompleteIsHintOnly(acFiltered[acIndex])
    ) {
      e.preventDefault();
      acAccept(acFiltered[acIndex]);
    } else {
      e.preventDefault();
      acHide();
      if (typeof submitComposerCommand === 'function') {
        submitComposerCommand(typeof getComposerValue === 'function' ? getComposerValue() : '', { dismissKeyboard: true });
      } else {
        runCommand();
      }
    }
    return;
  }
  if (e.key === 'Tab' && !e.altKey && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    if (hasActiveTerminalConfirm()) {
      acHide();
      return;
    }
    const selectableItems = acAutocompleteSelectableItems(acFiltered);
    if (selectableItems.length === 1) { acAccept(selectableItems[0]); }
    else if (selectableItems.length > 0) {
      if (typeof acExpandSharedPrefix === 'function' && acExpandSharedPrefix(selectableItems)) return;
      if (acIndex < 0 || !isAcDropdownOpen()) {
        acIndex = acAutocompleteNextSelectableIndex(acFiltered, -1, 1);
      } else if (e.shiftKey) {
        acIndex = acAutocompleteNextSelectableIndex(acFiltered, acIndex, -1);
      } else {
        acIndex = acAutocompleteNextSelectableIndex(acFiltered, acIndex, 1);
      }
      acShow(acFiltered);
    }
    return;
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    if (hasActiveTerminalConfirm()) {
      acHide();
      return;
    }
    const acOpen = isAcDropdownOpen();
    if (acOpen && acAutocompleteSelectableItems(acFiltered).length) {
      acIndex = acAutocompleteNextSelectableIndex(acFiltered, acIndex, 1);
      acShow(acFiltered);
      return;
    }
    if (navigateCmdHistory(-1)) acHide();
    return;
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (hasActiveTerminalConfirm()) {
      acHide();
      return;
    }
    const acOpen = isAcDropdownOpen();
    if (acOpen && acAutocompleteSelectableItems(acFiltered).length) {
      acIndex = acAutocompleteNextSelectableIndex(acFiltered, acIndex, -1);
      acShow(acFiltered);
      return;
    }
    if (navigateCmdHistory(1)) acHide();
    return;
  }
  if (e.key === 'Escape')    { acHide(); return; }

  // Suppress the macOS 'Press and Hold' accent picker. On macOS, holding a key
  // on a native <input> shows an accent chooser instead of repeating the character.
  // Calling preventDefault() signals that we handle the key ourselves, so the OS
  // never intercepts the repeat. We then insert the character manually so the
  // input value stays correct. Guard: skip modifier combos (handled above),
  // non-printable keys (length !== 1), IME composition sequences, and the welcome
  // settle phase (the document keydown handler owns key routing while welcome is
  // active, including Space/Enter/Escape settle triggers and printable insertion).
  if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey && !e.isComposing
      && !(_welcomeActive && welcomeOwnsTab(activeTabId))) {
    e.preventDefault();
    const value = typeof getComposerValue === 'function' ? getComposerValue() : '';
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

runBtn.addEventListener('click', runCommand);

if (typeof _applyComposerPromptMode === 'function') _applyComposerPromptMode();
syncShellPrompt();
if (typeof syncRunButtonDisabled === 'function') syncRunButtonDisabled();

setupMobileComposer();
