// ── Desktop UI controller ──
// Bootstraps the page, wires listeners, and coordinates the feature helpers.

renderThemeSelectionOptions();
const initialThemeName = _savedThemeName();
const initialTheme = initialThemeName ? _findThemeEntry(initialThemeName) : null;
const resolvedInitialTheme = initialTheme || _defaultThemeEntry();
if (resolvedInitialTheme) applyThemeSelection(resolvedInitialTheme.name, false);
else syncThemeSelectionControls();

tsBtn.addEventListener('click', () => {
  applyTimestampPreference(_tsModes[(_tsModes.indexOf(tsMode) + 1) % _tsModes.length]);
  refocusTerminalInput();
});

lnBtn.addEventListener('click', () => {
  applyLineNumberPreference(typeof lnMode !== 'undefined' ? (lnMode === 'on' ? 'off' : 'on') : 'on');
  refocusTerminalInput();
});

themeBtn.addEventListener('click', () => {
  openThemeSelector();
});

function openWorkflows() {
  _closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  showWorkflowsOverlay();
}

function closeWorkflows() {
  hideWorkflowsOverlay();
  refocusTerminalInput();
}

function openFaq() {
  _closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  showFaqOverlay();
}

function closeFaq() {
  hideFaqOverlay();
  refocusTerminalInput();
}

function ensureMobileSheetHandle(sheet) {
  if (!sheet) return null;
  let handle = sheet.querySelector(':scope > .mobile-sheet-handle');
  if (handle) return handle;
  handle = document.createElement('div');
  handle.className = 'mobile-sheet-handle';
  handle.setAttribute('aria-hidden', 'true');
  sheet.insertBefore(handle, sheet.firstChild || null);
  return handle;
}

function bindMobileSheetDragClose(sheet, onClose, { threshold = 72 } = {}) {
  // Bottom sheets should only drag from the visible handle area; otherwise
  // normal scrolling and button interaction inside the sheet would feel broken.
  if (!sheet || typeof onClose !== 'function' || sheet.dataset.mobileSheetDragBound === '1') return;
  sheet.dataset.mobileSheetDragBound = '1';
  const handle = ensureMobileSheetHandle(sheet);
  if (!handle) return;

  let drag = null;

  const clearSheetDragStyles = () => {
    sheet.style.removeProperty('transform');
    sheet.style.removeProperty('transition');
    sheet.style.removeProperty('will-change');
    sheet.style.removeProperty('opacity');
  };

  const finishDrag = (pointerId, shouldClose) => {
    if (!drag || drag.pointerId !== pointerId) return;
    const dy = drag.dy;
    drag = null;
    try {
      sheet.releasePointerCapture(pointerId);
    } catch (_) {}

    if (!shouldClose) {
      sheet.style.transition = 'transform 160ms ease';
      sheet.style.transform = 'translateY(0)';
      setTimeout(clearSheetDragStyles, 180);
      return;
    }

    sheet.style.transition = 'transform 180ms ease, opacity 180ms ease';
    sheet.style.transform = `translateY(${Math.max(sheet.getBoundingClientRect().height, dy)}px)`;
    sheet.style.opacity = '0.98';
    setTimeout(() => {
      clearSheetDragStyles();
      onClose();
    }, 180);
  };

  handle.addEventListener('pointerdown', e => {
    if (typeof useMobileTerminalViewportMode === 'function' && !useMobileTerminalViewportMode()) return;
    if (typeof e.button === 'number' && e.button !== 0) return;
    drag = { pointerId: e.pointerId, startY: e.clientY, dy: 0 };
    sheet.style.willChange = 'transform';
    sheet.style.transition = 'none';
    try {
      sheet.setPointerCapture(e.pointerId);
    } catch (_) {}
  });

  sheet.addEventListener('pointermove', e => {
    if (!drag || drag.pointerId !== e.pointerId) return;
    const dy = Math.max(0, e.clientY - drag.startY);
    drag.dy = dy;
    if (dy <= 0) return;
    e.preventDefault();
    sheet.style.transform = `translateY(${dy}px)`;
  });

  sheet.addEventListener('pointerup', e => {
    if (!drag || drag.pointerId !== e.pointerId) return;
    finishDrag(e.pointerId, drag.dy >= threshold);
  });

  sheet.addEventListener('pointercancel', e => {
    if (!drag || drag.pointerId !== e.pointerId) return;
    finishDrag(e.pointerId, false);
  });
}

function setupMobileSheetDragClose() {
  const faqModal = document.getElementById('faq-modal');
  const optionsModal = document.getElementById('options-modal');
  const killModal = document.getElementById('kill-modal');
  const histDelModal = document.getElementById('hist-del-modal');
  const shareRedactionModal = document.getElementById('share-redaction-modal');

  bindMobileSheetDragClose(mobileMenu, () => hideMobileMenu());
  bindMobileSheetDragClose(historyPanel, () => hideHistoryPanel());
  const workflowsModal = document.getElementById('workflows-modal');
  bindMobileSheetDragClose(workflowsModal, () => closeWorkflows());
  bindMobileSheetDragClose(faqModal, () => closeFaq());
  bindMobileSheetDragClose(optionsModal, () => closeOptions());
  bindMobileSheetDragClose(killModal, () => closeKillOverlay());
  bindMobileSheetDragClose(histDelModal, () => {
    hideHistoryDeleteOverlay();
    pendingHistAction = null;
  });
  bindMobileSheetDragClose(shareRedactionModal, () => cancelShareRedactionChoice());
}

function setupMobileComposer() {
  // The mobile composer reuses the same shared input state as desktop, but its
  // focus/keyboard handling has to be managed separately for mobile browsers.
  const composerInputs = typeof getComposerInputs === 'function' ? getComposerInputs() : {};
  const mobileInput = composerInputs.mobile || null;
  if (!mobileInput || !mobileRunBtn) return;
  bindMobileComposerSubmitAndInputListeners(mobileInput);
  bindMobileEditBarListeners(_mobileUiLayoutRefs && _mobileUiLayoutRefs.composer ? _mobileUiLayoutRefs.composer.editBar : null);
  bindMobileComposerKeyboardListeners(mobileInput);
  if (mobileShellTranscript) {
    const closeKeyboardFromTranscript = e => {
      const interactiveTarget = e && e.target && e.target.closest
        && e.target.closest('button, a, input, textarea, select, [contenteditable="true"], .term-action-btn, .hist-chip');
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
  APP_CONFIG = cfg;
  document.title = cfg.app_name;
  if (headerTitle) headerTitle.textContent = cfg.app_name;
  const wmVersion = cfg.version ? ` v${cfg.version}` : '';
  const wmText = `${cfg.app_name || 'darklab shell'}${wmVersion}`;
  document.querySelectorAll('.terminal-wordmark').forEach(el => {
    el.textContent = wmText;
    if (cfg.project_readme) el.href = cfg.project_readme;
  });
  document.querySelectorAll('.mobile-menu-wordmark').forEach(el => {
    el.textContent = `GitLab: ${wmText}`;
    if (cfg.project_readme) el.href = cfg.project_readme;
  });
  syncThemeSelectionControls();
  updateNewTabBtn();
  renderFaqLimits(cfg);
  if (cfg.diag_enabled) {
    if (diagBtn) diagBtn.classList.remove('u-hidden');
    const mobileDiagBtn = _uiOverlayRefs.mobileMenu?.querySelector('button[data-action="diag"]');
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

_uiOverlayRefs.mobileMenu?.querySelectorAll('button[data-action]').forEach(btn => {
  btn.addEventListener('click', () => {
    hideMobileMenu();
    const action = btn.dataset.action;
    if (action === 'search') {
      const visible = isSearchBarOpen();
      if (visible) {
        hideSearchBar();
        clearSearch();
      } else {
        showSearchBar();
        searchInput.focus();
        runSearch();
      }
    }
    if (action === 'history') {
      _closeMajorOverlays();
      const isOpen = togglePanelOverlay(historyPanel);
      if (isOpen) {
        if (typeof resetHistoryMobileFilters === 'function') resetHistoryMobileFilters();
        if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
        refreshHistoryPanel();
      }
    }
    if (action === 'ts') {
      applyTimestampPreference(_tsModes[(_tsModes.indexOf(tsMode) + 1) % _tsModes.length]);
      refocusTerminalInput();
    }
    if (action === 'ln') {
      applyLineNumberPreference(typeof lnMode !== 'undefined' ? (lnMode === 'on' ? 'off' : 'on') : 'on');
      refocusTerminalInput();
    }
    if (action === 'options') openOptions();
    if (action === 'theme') openThemeSelector();
    if (action === 'workflows') openWorkflows();
    if (action === 'faq') openFaq();
    if (action === 'diag') window.location.href = '/diag';
  });
});

// ── Workflows ──
workflowsBtn?.addEventListener('click', openWorkflows);
_uiOverlayRefs.workflowsOverlay?.addEventListener('click', e => {
  if (e.target === _uiOverlayRefs.workflowsOverlay) closeWorkflows();
});
workflowsCloseBtn?.addEventListener('click', closeWorkflows);

// ── FAQ ──
faqBtn.addEventListener('click', openFaq);
_uiOverlayRefs.faqOverlay.addEventListener('click', e => {
  if (e.target === _uiOverlayRefs.faqOverlay) closeFaq();
});
faqCloseBtn.addEventListener('click', closeFaq);
_uiOverlayRefs.themeOverlay?.addEventListener('click', e => {
  if (e.target === _uiOverlayRefs.themeOverlay) closeThemeSelector();
});
themeCloseBtn?.addEventListener('click', closeThemeSelector);
optionsBtn?.addEventListener('click', openOptions);
_uiOverlayRefs.optionsOverlay?.addEventListener('click', e => {
  if (e.target === _uiOverlayRefs.optionsOverlay) closeOptions();
});
optionsCloseBtn?.addEventListener('click', closeOptions);
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

apiFetch('/allowed-commands').then(r => r.json()).then(data => {
  allowedCommandsFaqData = data;
  renderAllowedCommandsFaq(data);
}).catch(err => {
  logClientError('failed to load /allowed-commands', err);
});

apiFetch('/faq').then(r => r.json()).then(data => {
  renderFaqItems(data.items || []);
}).catch(err => {
  logClientError('failed to load /faq', err);
});

apiFetch('/workflows').then(r => r.json()).then(data => {
  renderWorkflowItems(data.items || []);
}).catch(err => {
  logClientError('failed to load /workflows', err);
});

// ── Tabs ──
setupTabScrollControls();
applyTimestampPreference(getPreference('pref_timestamps') || 'off', false);
applyLineNumberPreference(getPreference('pref_line_numbers') || 'off', false);
applyWelcomeIntroPreference(getWelcomeIntroPreference(), false);
applyShareRedactionDefaultPreference(getShareRedactionDefaultPreference(), false);

Promise.all([
  apiFetch('/history').then(r => r.json()).catch(err => {
    logClientError('failed to load /history', err);
    return { runs: [] };
  }),
  apiFetch('/history/active').then(r => r.json()).catch(err => {
    logClientError('failed to load /history/active', err);
    return { runs: [] };
  }),
]).then(([historyData, activeData]) => {
  hydrateCmdHistory(historyData.runs || []);
  const restoredTabs = typeof restoreTabSessionState === 'function'
    && restoreTabSessionState();
  const restoredActiveRuns = typeof restoreActiveRunsAfterReload === 'function'
    && restoreActiveRunsAfterReload(activeData.runs || []);
  if (!restoredTabs && !restoredActiveRuns) {
    createTab('tab 1');
    runWelcome();
    return;
  }
  _welcomeBootPending = false;
});

setTimeout(() => {
  if (!cmdInput) return;
  if (useMobileTerminalViewportMode()) {
    return;
  }
  refocusTerminalInput();
}, 0);
syncMobileViewportState();
setupMobileSheetDragClose();

newTabBtn.addEventListener('click', () => {
  createShortcutTab();
});

// ── Search ──
searchToggleBtn.addEventListener('click', () => {
  const visible = isSearchBarOpen();
  if (visible) {
    hideSearchBar();
    clearSearch();
  } else {
    showSearchBar();
    searchInput.focus();
    runSearch();
  }
});

searchInput.addEventListener('input', runSearch);
searchPrevBtn.addEventListener('click', () => navigateSearch(-1));
searchNextBtn.addEventListener('click', () => navigateSearch(1));
searchCloseBtn?.addEventListener('click', () => {
  hideSearchBar();
  clearSearch();
});
searchInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') navigateSearch(e.shiftKey ? -1 : 1);
  if (e.key === 'Escape') {
    hideSearchBar();
    clearSearch();
    refocusTerminalInput();
  }
});

searchCaseBtn.addEventListener('click', () => {
  searchCaseSensitive = !searchCaseSensitive;
  searchCaseBtn.classList.toggle('active', searchCaseSensitive);
  runSearch();
});

searchRegexBtn.addEventListener('click', () => {
  searchRegexMode = !searchRegexMode;
  searchRegexBtn.classList.toggle('active', searchRegexMode);
  runSearch();
});

// ── Run history panel ──
histBtn.addEventListener('click', () => {
  _closeMajorOverlays();
  const isOpen = togglePanelOverlay(historyPanel);
  if (isOpen) {
    if (typeof resetHistoryMobileFilters === 'function') resetHistoryMobileFilters();
    if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
    refreshHistoryPanel();
  } else {
    refocusTerminalInput();
  }
});
historyCloseBtn.addEventListener('click', () => {
  if (typeof resetHistoryMobileFilters === 'function') resetHistoryMobileFilters();
  hideHistoryPanel();
});

// ── History delete modal ──
histClearAllBtn.addEventListener('click', () => {
  confirmHistAction('clear');
});
histDelCancelBtn.addEventListener('click', () => {
  hideHistoryDeleteOverlay();
  pendingHistAction = null;
});
histDelNonfavBtn.addEventListener('click', () => {
  hideHistoryDeleteOverlay();
  executeHistAction('clear-nonfav');
});
histDelConfirmBtn.addEventListener('click', () => {
  hideHistoryDeleteOverlay();
  executeHistAction();
});
histDelOverlay.addEventListener('click', e => {
  if (e.target === _uiOverlayRefs.histDelOverlay) { hideHistoryDeleteOverlay(); pendingHistAction = null; }
});

// ── Share redaction modal ──
shareRedactionCancelBtn?.addEventListener('click', () => {
  cancelShareRedactionChoice();
});
shareRedactionRawBtn?.addEventListener('click', () => {
  resolveShareRedactionChoice('raw');
});
shareRedactionConfirmBtn?.addEventListener('click', () => {
  resolveShareRedactionChoice('redacted');
});
_uiOverlayRefs.shareRedactionOverlay?.addEventListener('click', e => {
  if (e.target === _uiOverlayRefs.shareRedactionOverlay) cancelShareRedactionChoice();
});

// ── Kill modal ──
killCancelBtn.addEventListener('click', () => {
  closeKillOverlay();
});
killConfirmBtn.addEventListener('click', () => {
  confirmPendingKill();
});
_uiOverlayRefs.killOverlay.addEventListener('click', e => {
  if (e.target === _uiOverlayRefs.killOverlay) closeKillOverlay();
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
// - Alt+ArrowLeft / Alt+ArrowRight for tab cycling (same as Tab)
// - Alt+P for permalink, Alt+Shift+C for copy
// - Enter / Escape for kill-confirm accept / cancel
// Browser-native combos like Ctrl/Cmd+T or Ctrl/Cmd+W remain environment-dependent.
document.addEventListener('keydown', e => {
  if (isKillOverlayOpen()) {
    if (e.key === 'Enter') {
      confirmPendingKill();
      e.preventDefault();
      return;
    }
    if (e.key === 'Escape') {
      closeKillOverlay();
      e.preventDefault();
      return;
    }
  }
  if (isHistoryDeleteOverlayOpen()) {
    if (e.key === 'Escape') {
      hideHistoryDeleteOverlay();
      pendingHistAction = null;
      e.preventDefault();
      return;
    }
  }
  if (isShareRedactionOverlayOpen()) {
    if (e.key === 'Escape') {
      cancelShareRedactionChoice();
      e.preventDefault();
      return;
    }
  }
  if (isFaqOverlayOpen() || isOptionsOverlayOpen() || isThemeOverlayOpen()) {
    if (e.key !== 'Escape') return;
  }
  if (_welcomeActive && welcomeOwnsTab(activeTabId)) {
    const isCtrlC = e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'c' || e.key === 'C');
    const isSpace = e.key === ' ' || e.code === 'Space';
    const isPrintable = !e.metaKey && !e.ctrlKey && !e.altKey && !isEditableTarget(e.target) && e.key.length === 1;
    if (isCtrlC) {
      _welcomePromptAfterSettle = true;
      requestWelcomeSettle(activeTabId);
      refocusTerminalInput();
      e.preventDefault();
      return;
    }
    if (e.key === 'Escape' || e.key === 'Enter' || isSpace) {
      requestWelcomeSettle(activeTabId);
      refocusTerminalInput();
      e.preventDefault();
      return;
    }
    if (isPrintable) {
      requestWelcomeSettle(activeTabId);
      refocusTerminalInput();
      setComposerValue((typeof getComposerValue === 'function' ? getComposerValue() : '') + e.key);
      e.preventDefault();
      return;
    }
  }
  if (handleTabShortcut(e)) return;
  if (handleActionShortcut(e)) return;
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'c' || e.key === 'C')) {
    if (e.target === cmdInput) return;
    const editable = isEditableTarget(e.target);
    if (editable) return;
    if (_welcomeActive && welcomeOwnsTab(activeTabId)) {
      _welcomePromptAfterSettle = true;
      requestWelcomeSettle(activeTabId);
      refocusTerminalInput();
      e.preventDefault();
      return;
    }
    const activeTab = getActiveTab();
    if (activeTab && activeTab.st === 'running') {
      confirmKill(activeTabId);
    } else {
      interruptPromptLine(activeTabId);
    }
    e.preventDefault();
    return;
  }
  if (
    _welcomeActive && welcomeOwnsTab(activeTabId)
    && cmdInput
    && !e.metaKey && !e.ctrlKey && !e.altKey
    && !isEditableTarget(e.target)
    && e.key.length === 1
  ) {
    requestWelcomeSettle(activeTabId);
    refocusTerminalInput();
    setComposerValue((typeof getComposerValue === 'function' ? getComposerValue() : '') + e.key);
    e.preventDefault();
    return;
  }
  if (e.key === 'Enter' && _welcomeActive && welcomeOwnsTab(activeTabId)) {
    if ((typeof getComposerValue === 'function' ? getComposerValue() : '').trim()) return;
    requestWelcomeSettle(activeTabId);
    refocusTerminalInput();
    e.preventDefault();
    return;
  }
  if (e.key === 'Escape' && _welcomeActive && welcomeOwnsTab(activeTabId)) {
    requestWelcomeSettle(activeTabId);
    refocusTerminalInput();
    e.preventDefault();
    return;
  }
  if (e.key === 'Escape') {
    closeWorkflows();
    closeFaq();
    closeOptions();
    closeThemeSelector();
    cancelShareRedactionChoice();
    hideSearchBar();
    clearSearch();
    if (isHistoryPanelOpen()) hideHistoryPanel();
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
    && !isKillOverlayOpen()
    && !isShareRedactionOverlayOpen()
  ) {
    e.preventDefault();
    if (typeof focusAnyComposerInput === 'function') focusAnyComposerInput({ preventScroll: true });
    const value = typeof getComposerValue === 'function' ? getComposerValue() : (cmdInput.value || '');
    const { start, end } = getCmdSelection(value);
    replaceCmdRange(value, start, end, e.key);
  }
});

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
  if (typeof focusAnyComposerInput === 'function') focusAnyComposerInput({ preventScroll: true });
  if (isCtrlR) {
    if (typeof enterHistSearch === 'function') enterHistSearch();
    return true;
  }
  if (e.key === 'ArrowDown') {
    if (isAcDropdownOpen() && acFiltered.length) {
      acIndex = (acIndex + 1) % acFiltered.length;
      if (typeof acShow === 'function') acShow(acFiltered);
    } else if (typeof navigateCmdHistory === 'function' && navigateCmdHistory(-1)) {
      if (typeof acHide === 'function') acHide();
    }
    return true;
  }
  if (e.key === 'ArrowUp') {
    if (isAcDropdownOpen() && acFiltered.length) {
      acIndex = acIndex <= 0 ? acFiltered.length - 1 : acIndex - 1;
      if (typeof acShow === 'function') acShow(acFiltered);
    } else if (typeof navigateCmdHistory === 'function' && navigateCmdHistory(1)) {
      if (typeof acHide === 'function') acHide();
    }
    return true;
  }
  if (e.key === 'Enter') {
    if (acIndex >= 0 && acFiltered[acIndex]) {
      if (typeof acAccept === 'function') acAccept(acFiltered[acIndex]);
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

// ── Global click: dismiss mobile menu and autocomplete ──
document.addEventListener('click', e => {
  if (_uiOverlayRefs.mobileMenu && !_uiOverlayRefs.mobileMenu.contains(e.target) && e.target !== _uiOverlayRefs.hamburgerBtn) {
    hideMobileMenu();
  }
  if (historyPanel && isHistoryPanelOpen() && e.target !== histBtn && !historyPanel.contains(e.target)) {
    if (e.target.closest?.('.hist-chip-overflow') || e.target.closest?.('[data-action="history"]')) {
      return;
    }
    hideHistoryPanel();
  }
  if (!(e.target && e.target.closest &&
        (e.target.closest('.prompt-wrap') || e.target.closest('.ac-dropdown') || e.target.closest('#mobile-composer')))) acHide();
});

if (typeof shellPromptWrap !== 'undefined' && shellPromptWrap && cmdInput) {
  shellPromptWrap.addEventListener('pointerdown', e => {
    if (useMobileTerminalViewportMode()) {
      e.preventDefault();
      focusCommandInputFromGesture();
    }
  });
  shellPromptWrap.addEventListener('touchstart', e => {
    if (useMobileTerminalViewportMode()) {
      e.preventDefault();
      focusCommandInputFromGesture();
    }
  }, { passive: false });
  shellPromptWrap.addEventListener('click', e => {
    if (e.target === runBtn || (e.target && e.target.closest && e.target.closest('#run-btn'))) return;
    focusCommandInputFromGesture();
  });
}

_bindMobileComposerInteractions(_mobileUiLayoutRefs);
_bindMobileEditBarInteractions(_mobileUiLayoutRefs && _mobileUiLayoutRefs.composer && _mobileUiLayoutRefs.composer.editBar);

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

// ── Autocomplete ──
apiFetch('/autocomplete').then(r => r.json()).then(data => {
  acSuggestions = data.suggestions || [];
  acContextRegistry = data.context || {};
  acSpecialCommands = data.special_commands || [];
}).catch(err => {
  logClientError('failed to load /autocomplete', err);
});

cmdInput.addEventListener('input', () => {
  if (isHistoryPanelOpen()) hideHistoryPanel();
  if (typeof isHistSearchMode === 'function' && isHistSearchMode()) {
    if (typeof handleHistSearchInput === 'function') {
      const value = (typeof getComposerValue === 'function') ? getComposerValue() : cmdInput.value;
      handleHistSearchInput(value);
    }
    const _hsTab = typeof getActiveTab === 'function' ? getActiveTab() : null;
    if (_hsTab) _hsTab.followOutput = true;
    const _hsOut = document.querySelector('.tab-panel.active .output');
    if (_hsOut) _hsOut.scrollTop = _hsOut.scrollHeight;
    return;
  }
  handleComposerInputChange(cmdInput);
  // Keep the active tab's draft current so activateTab can read it directly
  const _activeTab = typeof getActiveTab === 'function' ? getActiveTab() : null;
  if (_activeTab && _activeTab.st !== 'running') {
    _activeTab.draftInput = (typeof getComposerValue === 'function') ? getComposerValue() : cmdInput.value;
    if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
  }
});

cmdInput.addEventListener('keydown', e => {
  if (isFaqOverlayOpen() || isWorkflowsOverlayOpen() || isOptionsOverlayOpen() || isThemeOverlayOpen() || isShareRedactionOverlayOpen()) {
    if (e.key === 'Escape') {
      closeFaq(); closeWorkflows(); closeOptions(); closeThemeSelector(); cancelShareRedactionChoice();
      refocusTerminalInput();
      e.preventDefault();
    }
    return;
  }
  if (typeof isHistSearchMode === 'function' && isHistSearchMode()) {
    if (typeof handleHistSearchKey === 'function' && handleHistSearchKey(e)) return;
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
      refocusTerminalInput();
      return;
    }
    const activeTab = getActiveTab();
    if (activeTab && activeTab.st === 'running') {
      confirmKill(activeTabId);
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

  if (e.altKey && !e.ctrlKey && !e.metaKey && eventMatchesLetter(e, 'b')) {
    e.preventDefault();
    const value = typeof getComposerValue === 'function' ? getComposerValue() : '';
    const { start } = getCmdSelection(value);
    const next = findWordBoundaryLeft(value, start);
    if (typeof syncComposerSelection === 'function') syncComposerSelection(next, next);
    else if (cmdInput && typeof cmdInput.setSelectionRange === 'function') cmdInput.setSelectionRange(next, next);
    syncShellPrompt();
    return;
  }

  if (e.altKey && !e.ctrlKey && !e.metaKey && eventMatchesLetter(e, 'f')) {
    e.preventDefault();
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
      refocusTerminalInput();
      return;
    }
    if (acIndex >= 0 && acFiltered[acIndex]) {
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
    if (acFiltered.length === 1) { acAccept(acFiltered[0]); }
    else if (acFiltered.length > 0) {
      if (typeof acExpandSharedPrefix === 'function' && acExpandSharedPrefix(acFiltered)) return;
      if (acIndex < 0 || !isAcDropdownOpen()) {
        acIndex = 0;
      } else if (e.shiftKey) {
        acIndex = acIndex <= 0 ? acFiltered.length - 1 : acIndex - 1;
      } else {
        acIndex = (acIndex + 1) % acFiltered.length;
      }
      acShow(acFiltered);
    }
    return;
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    const acOpen = isAcDropdownOpen();
    if (acOpen && acFiltered.length) {
      acIndex = (acIndex + 1) % acFiltered.length;
      acShow(acFiltered);
      return;
    }
    if (navigateCmdHistory(-1)) acHide();
    return;
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    const acOpen = isAcDropdownOpen();
    if (acOpen && acFiltered.length) {
      acIndex = acIndex <= 0 ? acFiltered.length - 1 : acIndex - 1;
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

// ── Run button ──
runBtn.addEventListener('click', runCommand);

syncShellPrompt();
if (typeof syncRunButtonDisabled === 'function') syncRunButtonDisabled();

setupMobileComposer();
