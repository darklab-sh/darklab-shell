// ── Desktop UI module ──
// Keyboard shortcuts, overlays, mobile-layout glue, and app bootstrap wiring.

function syncShellPrompt() {
  if (typeof shellPromptText === 'undefined' || !shellPromptText || !cmdInput) return;
  const value = cmdInput.value || '';
  const len = value.length;
  let start = typeof cmdInput.selectionStart === 'number' ? cmdInput.selectionStart : len;
  let end = typeof cmdInput.selectionEnd === 'number' ? cmdInput.selectionEnd : len;
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

function refocusTerminalInput() {
  setTimeout(() => {
    if (typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode()) return;
    if (typeof focusAnyComposerInput === 'function' && focusAnyComposerInput()) return;
  }, 0);
}

function focusCommandInputFromGesture() {
  if (typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode()) return;
  if (typeof focusAnyComposerInput === 'function' && focusAnyComposerInput({ preventScroll: true })) return;
}

function useMobileTerminalViewportMode() {
  if (typeof window === 'undefined') return false;
  const touchPoints = typeof navigator !== 'undefined' ? (navigator.maxTouchPoints || 0) : 0;
  const hasTouch = touchPoints > 0
    || (typeof window.matchMedia === 'function' && window.matchMedia('(pointer: coarse)').matches);
  if (!hasTouch) return false;
  if (typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 900px)').matches) return true;
  return window.innerWidth <= 900;
}

const _shellInputRowHomeParent = typeof shellInputRow !== 'undefined' && shellInputRow ? shellInputRow.parentElement : null;
const _acDropdownHomeParent = typeof acDropdown !== 'undefined' && acDropdown ? acDropdown.parentElement : null;
const _histRowHomeParent = typeof histRow !== 'undefined' && histRow ? histRow.parentElement : null;
const _terminalBarHomeParent = typeof terminalBar !== 'undefined' && terminalBar ? terminalBar.parentElement : null;
const _searchBarHomeParent = typeof searchBar !== 'undefined' && searchBar ? searchBar.parentElement : null;
const _tabPanelsHomeParent = typeof tabPanels !== 'undefined' && tabPanels ? tabPanels.parentElement : null;
const _historyPanelHomeParent = typeof historyPanel !== 'undefined' && historyPanel ? historyPanel.parentElement : null;
const _permalinkToastHomeParent = typeof permalinkToast !== 'undefined' && permalinkToast ? permalinkToast.parentElement : null;
const _killOverlayHomeParent = typeof killOverlay !== 'undefined' && killOverlay ? killOverlay.parentElement : null;
const _histDelOverlayHomeParent = typeof histDelOverlay !== 'undefined' && histDelOverlay ? histDelOverlay.parentElement : null;
const _faqOverlayHomeParent = typeof faqOverlay !== 'undefined' && faqOverlay ? faqOverlay.parentElement : null;
const _optionsOverlayHomeParent = typeof optionsOverlay !== 'undefined' && optionsOverlay ? optionsOverlay.parentElement : null;
const _statusHomeParent = typeof status !== 'undefined' && status ? status.parentElement : null;
const _runTimerHomeParent = typeof runTimer !== 'undefined' && runTimer ? runTimer.parentElement : null;
const _headerHomeParent = typeof headerTitle !== 'undefined' && headerTitle ? headerTitle.closest('header') : (typeof document !== 'undefined' ? document.querySelector('header') : null);

function _moveComposerNode(node, target, anchor = null) {
  if (!node || !target || node.parentElement === target) return;
  if (anchor && anchor.parentElement === target) {
    target.insertBefore(node, anchor);
  } else {
    target.appendChild(node);
  }
}

function _syncShellNodeGroup(useMobile, target, specs) {
  if (!Array.isArray(specs) || !target) return;
  for (const spec of specs) {
    if (!spec || !spec.node) continue;
    if (useMobile) {
      _moveComposerNode(spec.node, target);
    } else if (spec.homeParent) {
      _moveComposerNode(spec.node, spec.homeParent, spec.desktopAnchor || null);
    }
  }
}

function _syncVisibilityGroup(useMobile, specs) {
  if (!Array.isArray(specs)) return;
  for (const spec of specs) {
    if (!spec || !spec.node) continue;
    const visible = useMobile ? spec.visibleOnMobile : spec.visibleOnDesktop;
    const ariaHidden = useMobile ? spec.ariaHiddenOnMobile : spec.ariaHiddenOnDesktop;
    if (typeof visible === 'boolean') {
      setVisibilityState(spec.node, !visible, ariaHidden);
    }
  }
}

function _getMobileUiLayoutRefs() {
  const shellRoot = typeof mobileShell !== 'undefined' && mobileShell ? mobileShell : null;
  const composerHost = typeof mobileComposerHost !== 'undefined' && mobileComposerHost ? mobileComposerHost : null;
  const composerRow = typeof mobileComposerRow !== 'undefined' && mobileComposerRow ? mobileComposerRow : null;
  const editBar = typeof mobileEditBar !== 'undefined' && mobileEditBar ? mobileEditBar : null;
  if (!shellRoot && !composerHost && !composerRow && !editBar) return null;
  return {
    shell: shellRoot ? {
      root: shellRoot,
      chromeMount: typeof mobileShellChrome !== 'undefined' && mobileShellChrome ? mobileShellChrome : shellRoot,
      transcriptMount: typeof mobileShellTranscript !== 'undefined' && mobileShellTranscript ? mobileShellTranscript : shellRoot,
      overlaysMount: typeof mobileShellOverlays !== 'undefined' && mobileShellOverlays ? mobileShellOverlays : shellRoot,
    } : null,
    composer: {
      host: composerHost,
      row: composerRow,
      editBar,
    },
  };
}

const _mobileUiLayoutRefs = _getMobileUiLayoutRefs();
const _uiOverlayRefs = {
  mobileMenu: mobileMenu || null,
  hamburgerBtn: hamburgerBtn || null,
  faqOverlay: typeof faqOverlay !== 'undefined' && faqOverlay ? faqOverlay : null,
  optionsOverlay: typeof optionsOverlay !== 'undefined' && optionsOverlay ? optionsOverlay : null,
  historyPanel: typeof historyPanel !== 'undefined' && historyPanel ? historyPanel : null,
  killOverlay: typeof killOverlay !== 'undefined' && killOverlay ? killOverlay : null,
  histDelOverlay: typeof histDelOverlay !== 'undefined' && histDelOverlay ? histDelOverlay : null,
};

function _bindMobileComposerInteractions(uiRefs) {
  const composerRefs = uiRefs && uiRefs.composer;
  if (!composerRefs || !composerRefs.host || !cmdInput) return;
  composerRefs.host.addEventListener('click', e => {
    if (useMobileTerminalViewportMode() && e.target === composerRefs.host) {
      focusCommandInputFromGesture();
    }
  });
  if (composerRefs.row) {
    composerRefs.row.addEventListener('pointerdown', e => {
      if (useMobileTerminalViewportMode() && e.target !== runBtn) {
        focusCommandInputFromGesture();
      }
    });
    composerRefs.row.addEventListener('touchstart', e => {
      if (useMobileTerminalViewportMode() && e.target !== runBtn) {
        focusCommandInputFromGesture();
      }
    }, { passive: false });
  }
}

function _bindMobileEditBarInteractions(editBar) {
  if (!editBar || !cmdInput) return;
  editBar.querySelectorAll('button[data-edit-action]').forEach(btn => {
    let handledPointerDown = false;
    const handler = (e) => {
      e.preventDefault();
      e.stopPropagation();
      performMobileEditAction(btn.dataset.editAction);
    };
    if (typeof window !== 'undefined' && typeof window.PointerEvent === 'function') {
      btn.addEventListener('pointerdown', e => {
        handledPointerDown = true;
        handler(e);
      });
      btn.addEventListener('mousedown', e => {
        if (handledPointerDown) {
          handledPointerDown = false;
          e.preventDefault();
          return;
        }
        handler(e);
      });
    } else {
      btn.addEventListener('mousedown', handler);
      btn.addEventListener('touchstart', handler, { passive: false });
    }
  });
}

const _mobileShellChromeNodes = [
  { node: histRow, homeParent: _histRowHomeParent, desktopAnchor: terminalBar || null },
  { node: terminalBar, homeParent: _terminalBarHomeParent, desktopAnchor: searchBar || null },
  { node: searchBar, homeParent: _searchBarHomeParent, desktopAnchor: tabPanels || null },
];
const _mobileShellTranscriptNodes = [
  { node: tabPanels, homeParent: _tabPanelsHomeParent, desktopAnchor: mobileComposerHost || null },
];
const _mobileShellOverlayNodes = [
  { node: historyPanel, homeParent: _historyPanelHomeParent, desktopAnchor: permalinkToast || null },
  { node: permalinkToast, homeParent: _permalinkToastHomeParent, desktopAnchor: killOverlay || null },
  { node: killOverlay, homeParent: _killOverlayHomeParent, desktopAnchor: histDelOverlay || null },
  { node: histDelOverlay, homeParent: _histDelOverlayHomeParent, desktopAnchor: faqOverlay || null },
  { node: faqOverlay, homeParent: _faqOverlayHomeParent, desktopAnchor: optionsOverlay || null },
  { node: optionsOverlay, homeParent: _optionsOverlayHomeParent, desktopAnchor: null },
];

function syncMobileShellChromeLayout(useMobile, mobileShellChromeMount) {
  _syncShellNodeGroup(useMobile, mobileShellChromeMount, _mobileShellChromeNodes);
}

function syncMobileShellTranscriptLayout(useMobile, mobileShellTranscriptMount, mobileShellChromeMount) {
  _syncShellNodeGroup(useMobile, mobileShellTranscriptMount || mobileShellChromeMount, _mobileShellTranscriptNodes);
}

function syncMobileShellOverlayLayout(useMobile, mobileShellOverlaysMount) {
  _syncShellNodeGroup(useMobile, mobileShellOverlaysMount, _mobileShellOverlayNodes);
}

function syncMobileShellLayout(mobileMode) {
  if (typeof document === 'undefined') return;
  const useMobile = !!mobileMode;
  const mobileShellRefs = _mobileUiLayoutRefs && _mobileUiLayoutRefs.shell;
  const mobileShellRoot = mobileShellRefs && mobileShellRefs.root;
  const desktopShell = typeof terminalWrap !== 'undefined' && terminalWrap ? terminalWrap : null;
  if (mobileShellRoot) {
    setVisibilityState(mobileShellRoot, !useMobile, useMobile ? 'false' : 'true');
  }
  if (desktopShell) {
    setVisibilityState(desktopShell, useMobile, useMobile ? 'true' : 'false');
  }
  if (!mobileShellRefs) return;
  const mobileShellChromeMount = mobileShellRefs.chromeMount;
  const mobileShellOverlaysMount = mobileShellRefs.overlaysMount;
  const mobileShellTranscriptMount = mobileShellRefs.transcriptMount || mobileShellChromeMount;
  syncMobileShellChromeLayout(useMobile, mobileShellChromeMount);
  syncMobileShellTranscriptLayout(useMobile, mobileShellTranscriptMount, mobileShellChromeMount);
  syncMobileShellOverlayLayout(useMobile, mobileShellOverlaysMount);
  if (status && _headerHomeParent) {
    if (useMobile) _moveComposerNode(status, _headerHomeParent, hamburgerBtn || null);
    else _moveComposerNode(status, _statusHomeParent);
  }
  if (runTimer && _headerHomeParent) {
    if (useMobile) _moveComposerNode(runTimer, _headerHomeParent, hamburgerBtn || null);
    else _moveComposerNode(runTimer, _runTimerHomeParent);
  }
  if (!useMobile && _shellInputRowHomeParent) _moveComposerNode(shellInputRow, _shellInputRowHomeParent);
}

function syncMobileComposerLayout(mobileMode) {
  if (typeof document === 'undefined') return;
  const useMobile = !!mobileMode;
  const mobileComposerRefs = _mobileUiLayoutRefs && _mobileUiLayoutRefs.composer;
  _syncVisibilityGroup(useMobile, [
    { node: mobileComposerRefs.host, visibleOnMobile: true, visibleOnDesktop: false, ariaHiddenOnMobile: 'false', ariaHiddenOnDesktop: 'true' },
    { node: shellPromptWrap, visibleOnMobile: false, visibleOnDesktop: true, ariaHiddenOnMobile: 'true', ariaHiddenOnDesktop: 'false' },
    { node: mobileComposerRefs.row, visibleOnMobile: true, visibleOnDesktop: false, ariaHiddenOnMobile: 'false', ariaHiddenOnDesktop: 'true' },
    { node: runBtn, visibleOnMobile: false, visibleOnDesktop: false, ariaHiddenOnMobile: 'true', ariaHiddenOnDesktop: 'true' },
    { node: shellInputRow, visibleOnMobile: false, visibleOnDesktop: true, ariaHiddenOnMobile: 'true', ariaHiddenOnDesktop: 'true' },
  ]);
  if (useMobile) {
    _moveComposerNode(acDropdown, mobileComposerRefs.row);
  } else {
    if (typeof shellInputRow !== 'undefined' && shellInputRow && _shellInputRowHomeParent) {
      _moveComposerNode(shellInputRow, _shellInputRowHomeParent);
    }
    if (typeof acDropdown !== 'undefined' && acDropdown && _acDropdownHomeParent) {
      _moveComposerNode(acDropdown, _acDropdownHomeParent, shellInputRow || null);
    }
  }
}

function isChromeIOS() {
  if (typeof navigator === 'undefined') return false;
  return /CriOS/i.test(navigator.userAgent || '');
}

function getMobileKeyboardOffset() {
  if (!useMobileTerminalViewportMode() || !window.visualViewport) return 0;
  return Math.max(0, Math.round(window.innerHeight - window.visualViewport.height - window.visualViewport.offsetTop));
}

function isMobileKeyboardOpen(offset = null) {
  if (!useMobileTerminalViewportMode()) return false;
  const mobileInputEl = (typeof getVisibleComposerInput === 'function' && getVisibleComposerInput()) || null;
  const mobileInputFocused = !!(mobileInputEl && typeof document !== 'undefined' && document.activeElement === mobileInputEl);
  if (!mobileInputFocused) return false;
  const keyboardBaseline = typeof getMobileKeyboardOffsetBaseline === 'function'
    ? getMobileKeyboardOffsetBaseline()
    : null;
  const baseline = typeof keyboardBaseline === 'number' ? keyboardBaseline : 0;
  if (typeof offset === 'number') return offset > baseline + 40;
  return true;
}

function syncMobileViewportState() {
  if (typeof document === 'undefined') return;
  const mobileMode = useMobileTerminalViewportMode();
  const hasMobileShell = !!(_mobileUiLayoutRefs && _mobileUiLayoutRefs.shell);
  const activeMobileMode = mobileMode && hasMobileShell;
  const keyboardOffset = getMobileKeyboardOffset();
  const keyboardOpen = isMobileKeyboardOpen(keyboardOffset);
  const wasMobileKeyboardOpen = document.body.classList.contains('mobile-keyboard-open');
  if (!hasMobileShell) return;
  document.body.classList.toggle('mobile-terminal-mode', activeMobileMode);
  document.body.classList.toggle('mobile-chrome-ios', activeMobileMode && isChromeIOS());
  if (typeof syncMobileComposerKeyboardState === 'function') syncMobileComposerKeyboardState(keyboardOffset, { active: activeMobileMode });
  else document.body.classList.toggle('mobile-keyboard-open', activeMobileMode && keyboardOpen);
  syncMobileShellLayout(activeMobileMode);
  syncMobileComposerLayout(activeMobileMode);
  if (activeMobileMode) syncMobileViewportHeight();
  if (activeMobileMode && keyboardOpen) {
    hideMobileMenu();
    if (isHistoryPanelOpen()) hideHistoryPanel();
    // Hide autocomplete only when the mobile keyboard becomes active.
    if (!wasMobileKeyboardOpen && typeof acHide === 'function') acHide();
  }
}

function dismissMobileKeyboardAfterSubmit() {
  if (!useMobileTerminalViewportMode()) return;
  if (typeof blurVisibleComposerInputIfMobile === 'function') {
    setTimeout(() => blurVisibleComposerInputIfMobile(), 0);
    return;
  }
}

const PREF_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

function getPreferenceCookie(name) {
  const prefix = `${name}=`;
  return document.cookie.split(';').map(part => part.trim()).find(part => part.startsWith(prefix))
    ?.slice(prefix.length) || '';
}

function setPreferenceCookie(name, value) {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${PREF_COOKIE_MAX_AGE}; SameSite=Lax`;
}

function getPreference(name) {
  const value = getPreferenceCookie(name);
  return value ? decodeURIComponent(value) : '';
}

function syncOptionsControls() {
  const themeValue = document.body.classList.contains('light') ? 'light' : 'dark';
  themePrefInputs.forEach(input => {
    input.checked = input.value === themeValue;
  });
  const tsSelect = optionsTsSelect;
  if (tsSelect) tsSelect.value = typeof tsMode === 'string' ? tsMode : 'off';
  const lnToggle = optionsLnToggle;
  if (lnToggle) lnToggle.checked = typeof lnMode === 'string' && lnMode === 'on';
}

function applyThemePreference(theme, persist = true) {
  const nextTheme = theme === 'light' ? 'light' : 'dark';
  document.body.classList.toggle('light', nextTheme === 'light');
  if (persist) {
    setPreferenceCookie('pref_theme', nextTheme);
    localStorage.setItem('theme', nextTheme);
  }
  syncOptionsControls();
}

function applyTimestampPreference(mode, persist = true) {
  const nextMode = _tsModes.includes(mode) ? mode : 'off';
  _setTsMode(nextMode);
  if (persist) setPreferenceCookie('pref_timestamps', nextMode);
  syncOptionsControls();
}

function applyLineNumberPreference(mode, persist = true) {
  const nextMode = mode === 'on' ? 'on' : 'off';
  _setLnMode(nextMode);
  if (persist) setPreferenceCookie('pref_line_numbers', nextMode);
  syncOptionsControls();
}

function _closeMajorOverlays() {
  if (isHistoryPanelOpen()) hideHistoryPanel();
  if (isFaqOverlayOpen()) hideFaqOverlay();
  if (isOptionsOverlayOpen()) hideOptionsOverlay();
}

function openOptions() {
  _closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  syncOptionsControls();
  showOptionsOverlay();
}

function closeOptions() {
  hideOptionsOverlay();
  refocusTerminalInput();
}

function isEditableTarget(target) {
  return !!(target && target.closest && target.closest('input, textarea, [contenteditable="true"]'));
}

function shouldIgnoreGlobalShortcutTarget(target) {
  return isEditableTarget(target) && target !== cmdInput;
}

function createNextTabLabel() {
  return 'tab ' + (tabs.length + 1);
}

function createShortcutTab() {
  createTab(createNextTabLabel());
}

function activateRelativeTab(offset) {
  if (!Array.isArray(tabs) || !tabs.length) return;
  const currentIndex = tabs.findIndex(tab => tab.id === activeTabId);
  const baseIndex = currentIndex >= 0 ? currentIndex : 0;
  const nextIndex = (baseIndex + offset + tabs.length) % tabs.length;
  activateTab(tabs[nextIndex].id);
}

function closeActiveShortcutTab() {
  if (!activeTabId || typeof closeTab !== 'function') return;
  closeTab(activeTabId);
}

function permalinkActiveShortcutTab() {
  if (!activeTabId || typeof permalinkTab !== 'function') return;
  permalinkTab(activeTabId);
}

function copyActiveShortcutTab() {
  if (!activeTabId || typeof copyTab !== 'function') return;
  copyTab(activeTabId);
}

function clearActiveShortcutTab() {
  if (!activeTabId) return;
  cancelWelcome(activeTabId);
  const activeTab = typeof getActiveTab === 'function' ? getActiveTab() : null;
  clearTab(activeTabId, { preserveRunState: !!(activeTab && activeTab.st === 'running') });
}

function closeKillOverlay() {
  hideKillOverlay();
  pendingKillTabId = null;
  refocusTerminalInput();
}

function confirmPendingKill() {
  hideKillOverlay();
  if (pendingKillTabId) {
    doKill(pendingKillTabId);
    pendingKillTabId = null;
  }
  refocusTerminalInput();
}

function eventMatchesCode(e, code) {
  return !!(e && e.code === code);
}

function eventMatchesLetter(e, letter) {
  if (eventMatchesCode(e, `Key${letter.toUpperCase()}`)) return true;
  const key = e && typeof e.key === 'string' ? e.key.toLowerCase() : '';
  return key === letter.toLowerCase();
}

function eventMatchesDigit(e, digit) {
  if (eventMatchesCode(e, `Digit${digit}`)) return true;
  return !!(e && e.key === String(digit));
}

function handleTabShortcut(e) {
  if (!e.altKey || e.ctrlKey || e.metaKey) return false;
  if (shouldIgnoreGlobalShortcutTarget(e.target)) return false;
  if (eventMatchesLetter(e, 't')) {
    createShortcutTab();
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, 'w')) {
    closeActiveShortcutTab();
    e.preventDefault();
    return true;
  }
  if (e.key === 'ArrowRight') {
    activateRelativeTab(1);
    e.preventDefault();
    return true;
  }
  if (e.key === 'ArrowLeft') {
    activateRelativeTab(-1);
    e.preventDefault();
    return true;
  }
  const matchedDigit = [1, 2, 3, 4, 5, 6, 7, 8, 9].find(digit => eventMatchesDigit(e, digit));
  if (matchedDigit) {
    const tabIndex = matchedDigit - 1;
    if (tabs[tabIndex]) activateTab(tabs[tabIndex].id);
    e.preventDefault();
    return true;
  }
  return false;
}

function handleActionShortcut(e) {
  if (shouldIgnoreGlobalShortcutTarget(e.target)) return false;
  if (e.altKey && !e.ctrlKey && !e.metaKey && eventMatchesLetter(e, 'p')) {
    permalinkActiveShortcutTab();
    e.preventDefault();
    return true;
  }
  if (e.altKey && !e.ctrlKey && !e.metaKey && e.shiftKey && eventMatchesLetter(e, 'c')) {
    copyActiveShortcutTab();
    e.preventDefault();
    return true;
  }
  if (e.ctrlKey && !e.altKey && !e.metaKey && (e.key === 'l' || e.key === 'L')) {
    clearActiveShortcutTab();
    e.preventDefault();
    return true;
  }
  return false;
}

function getCmdSelection(value = cmdInput.value || '') {
  let start = typeof cmdInput.selectionStart === 'number' ? cmdInput.selectionStart : value.length;
  let end = typeof cmdInput.selectionEnd === 'number' ? cmdInput.selectionEnd : value.length;
  if (start > end) [start, end] = [end, start];
  return { start, end };
}

function getInputSelection(input, value = input && input.value ? input.value : '') {
  let start = typeof input.selectionStart === 'number' ? input.selectionStart : value.length;
  let end = typeof input.selectionEnd === 'number' ? input.selectionEnd : value.length;
  if (start > end) [start, end] = [end, start];
  return { start, end };
}

function syncHiddenCommandInputFromVisible(value, start = null, end = null) {
  setComposerValue(value, start, end);
}

function replaceCmdRange(value, start, end, replacement = '') {
  const nextPos = start + replacement.length;
  setComposerValue(value.slice(0, start) + replacement + value.slice(end), nextPos, nextPos);
}

function moveCmdCaret(delta) {
  const value = cmdInput.value || '';
  const { start, end } = getCmdSelection(value);
  const next = Math.max(0, Math.min(value.length, (delta < 0 ? start : end) + delta));
  cmdInput.setSelectionRange(next, next);
  syncShellPrompt();
}

function setCmdCaret(position) {
  const value = cmdInput.value || '';
  const next = Math.max(0, Math.min(value.length, position));
  cmdInput.setSelectionRange(next, next);
  syncShellPrompt();
}

function deleteCmdWordLeft() {
  const value = cmdInput.value || '';
  const { start, end } = getCmdSelection(value);
  if (start !== end) {
    replaceCmdRange(value, start, end);
    return;
  }
  if (start === 0) return;
  const cut = findWordBoundaryLeft(value, start);
  replaceCmdRange(value, cut, start);
}

function performMobileEditAction(action) {
  const input = (typeof getVisibleComposerInput === 'function' && getVisibleComposerInput()) || null;
  if (!input) return;
  if (document.activeElement !== input && typeof focusAnyComposerInput === 'function') focusAnyComposerInput({ preventScroll: true });

  // Mobile edit helpers are meant to adjust the existing command in place.
  // Suppress autocomplete for this synthetic input update so the dropdown
  // does not pop back up and cover the helper row itself.
  if (typeof acSuppressInputOnce !== 'undefined') acSuppressInputOnce = true;
  if (typeof acHide === 'function') acHide();

  const value = input.value || '';
  const { start, end } = getInputSelection(input, value);
  let nextValue = value;
  let nextStart = start;
  let nextEnd = end;

  if (action === 'left') {
    const pos = Math.max(0, start - 1);
    nextStart = pos;
    nextEnd = pos;
  } else if (action === 'right') {
    const pos = Math.min(value.length, end + 1);
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
  }

  setComposerValue(nextValue, nextStart, nextEnd);

  if (typeof focusAnyComposerInput === 'function') setTimeout(() => focusAnyComposerInput({ preventScroll: true }), 0);
}

function syncMobileViewportHeight() {
  if (typeof document === 'undefined' || typeof window === 'undefined') return;
  const h = window.visualViewport ? Math.round(window.visualViewport.height) : window.innerHeight;
  document.documentElement.style.setProperty('--mobile-viewport-height', `${h}px`);
}

function syncMobileComposerKeyboard() {
  if (typeof window === 'undefined') return;
  const offset = getMobileKeyboardOffset();
  if (typeof syncMobileComposerKeyboardState === 'function') syncMobileComposerKeyboardState(offset);
  syncMobileViewportHeight();
}

function bindMobileComposerKeyboardListeners(mobileInput) {
  if (!mobileInput || typeof window === 'undefined') return;
  if (window.visualViewport && typeof window.visualViewport.addEventListener === 'function') {
    window.visualViewport.addEventListener('resize', syncMobileComposerKeyboard);
    window.visualViewport.addEventListener('scroll', syncMobileComposerKeyboard);
  }
  mobileInput.addEventListener('focus', syncMobileComposerKeyboard);
  mobileInput.addEventListener('blur', syncMobileComposerKeyboard);
}

function bindMobileComposerSubmitAndInputListeners(mobileInput) {
  if (!mobileInput || !mobileRunBtn) return;
  mobileInput.addEventListener('pointerdown', e => {
    if (!useMobileTerminalViewportMode()) return;
    e.preventDefault();
    e.stopPropagation();
    if (typeof focusComposerInput === 'function') {
      focusComposerInput(mobileInput, { preventScroll: true });
    } else if (typeof mobileInput.focus === 'function') {
      try {
        mobileInput.focus({ preventScroll: true });
      } catch (_) {
        mobileInput.focus();
      }
    }
  });
  mobileInput.addEventListener('touchstart', e => {
    if (!useMobileTerminalViewportMode()) return;
    e.preventDefault();
    e.stopPropagation();
    if (typeof focusComposerInput === 'function') {
      focusComposerInput(mobileInput, { preventScroll: true });
    } else if (typeof mobileInput.focus === 'function') {
      try {
        mobileInput.focus({ preventScroll: true });
      } catch (_) {
        mobileInput.focus();
      }
    }
  }, { passive: false });
  // Submit handler — read the visible composer input and submit through the
  // shared command engine.
  function _mobileSubmit() {
    submitVisibleComposerCommand({ dismissKeyboard: true, focusAfterSubmit: false });
  }

  mobileRunBtn.addEventListener('click', _mobileSubmit);

  // Sync mobile input through the shared composer handler so autocomplete and
  // hidden-desktop mirroring stay on the same path.
  mobileInput.addEventListener('input', () => {
    handleComposerInputChange(mobileInput);
  });

  mobileInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      e.preventDefault();
      _mobileSubmit();
    }
  });
}

function bindMobileEditBarListeners(editBar) {
  if (!editBar) return;
  editBar.querySelectorAll('button[data-mobile-edit]').forEach(btn => {
    let handledPointerDown = false;
    const handler = e => {
      e.preventDefault();
      e.stopPropagation();
      performMobileEditAction(btn.dataset.mobileEdit);
    };
    if (typeof window !== 'undefined' && typeof window.PointerEvent === 'function') {
      btn.addEventListener('pointerdown', e => {
        handledPointerDown = true;
        handler(e);
      });
      btn.addEventListener('mousedown', e => {
        if (handledPointerDown) {
          handledPointerDown = false;
          e.preventDefault();
          return;
        }
        handler(e);
      });
    } else {
      btn.addEventListener('mousedown', handler);
      btn.addEventListener('touchstart', handler, { passive: false });
    }
  });
}

function findWordBoundaryLeft(value, index) {
  let next = Math.max(0, index);
  while (next > 0 && /\s/.test(value[next - 1])) next--;
  while (next > 0 && !/\s/.test(value[next - 1])) next--;
  return next;
}

function findWordBoundaryRight(value, index) {
  let next = Math.min(value.length, index);
  while (next < value.length && /\s/.test(value[next])) next++;
  while (next < value.length && !/\s/.test(value[next])) next++;
  return next;
}

// ── Theme ──
const savedTheme = getPreference('pref_theme') || localStorage.getItem('theme');
if (!getPreference('pref_theme') && savedTheme) setPreferenceCookie('pref_theme', savedTheme);
if (savedTheme === 'light') document.body.classList.add('light');

// ── Timestamps ──
const _tsModes  = ['off', 'elapsed', 'clock'];
const _tsLabels = { off: 'timestamps: off', elapsed: 'timestamps: elapsed', clock: 'timestamps: clock' };

function _setTsMode(mode) {
  tsMode = mode;
  document.body.classList.remove('ts-elapsed', 'ts-clock');
  if (mode === 'elapsed') document.body.classList.add('ts-elapsed');
  if (mode === 'clock')   document.body.classList.add('ts-clock');
  const label = _tsLabels[mode];
  if (tsBtn) { tsBtn.textContent = label; tsBtn.classList.toggle('active', mode !== 'off'); }
  const mobileTs = mobileMenu ? mobileMenu.querySelector('[data-action="ts"]') : null;
  if (mobileTs) mobileTs.textContent = label;
  if (typeof syncOutputPrefixes === 'function') syncOutputPrefixes();
  try { _refreshFollowingOutputsAfterLayout(); } catch (_) {}
}

tsBtn.addEventListener('click', () => {
  applyTimestampPreference(_tsModes[(_tsModes.indexOf(tsMode) + 1) % _tsModes.length]);
  refocusTerminalInput();
});

lnBtn.addEventListener('click', () => {
  applyLineNumberPreference(typeof lnMode !== 'undefined' ? (lnMode === 'on' ? 'off' : 'on') : 'on');
  refocusTerminalInput();
});

themeBtn.addEventListener('click', () => {
  applyThemePreference(document.body.classList.contains('light') ? 'dark' : 'light');
  refocusTerminalInput();
});

let allowedCommandsFaqData = null;

function formatFaqLimits(cfg) {
  if (!cfg) return '';
  function _fmtDuration(s) {
    if (s >= 3600 && s % 3600 === 0) return (s / 3600) + (s / 3600 === 1 ? ' hour' : ' hours');
    if (s >= 60 && s % 60 === 0) return (s / 60) + (s / 60 === 1 ? ' minute' : ' minutes');
    return s + (s === 1 ? ' second' : ' seconds');
  }
  const timeout = cfg.command_timeout_seconds || 0;
  const maxLines = cfg.max_output_lines || 0;
  const retention = cfg.permalink_retention_days || 0;

  const rows = [
    {
      label: 'Command timeout',
      value: timeout > 0
        ? `<strong>${_fmtDuration(timeout)}</strong> — commands are automatically killed after this time; a notice appears inline in the output`
        : '<strong>None</strong> — commands run until they finish or you click ■ Kill',
    },
    {
      label: 'Output line limit',
      value: maxLines > 0
        ? `<strong>${maxLines.toLocaleString()} lines</strong> per tab — older lines are dropped from the top when this is reached`
        : '<strong>Unlimited</strong>',
    },
    {
      label: 'Permalink &amp; history retention',
      value: retention > 0
        ? `<strong>${retention} day${retention === 1 ? '' : 's'}</strong> — run history and share links are deleted after this period`
        : '<strong>Unlimited</strong> — run history and share links are kept indefinitely',
    },
  ];

  const tableRows = rows.map(r =>
    `<tr><td style="padding:2px 12px 2px 0;white-space:nowrap;color:var(--muted)">${r.label}</td>` +
    `<td style="padding:2px 0">${r.value}</td></tr>`
  ).join('');

  return `<table style="border-collapse:collapse;margin-bottom:6px">${tableRows}</table>` +
    '<span style="color:var(--muted);font-size:11px">These limits are configured by the operator of this instance.</span>';
}

function renderFaqLimits(cfg) {
  const limitsEl = faqLimitsText;
  if (!limitsEl || !cfg) return;
  limitsEl.innerHTML = formatFaqLimits(cfg);
}

function makeAllowedCommandChip(cmd) {
  const chip = document.createElement('span');
  chip.className = 'allowed-chip';
  chip.textContent = cmd;
  chip.title = 'Click to load into prompt';
  chip.addEventListener('click', () => {
    setComposerValue(cmd + ' ');
    closeFaq();
  });
  return chip;
}

function renderAllowedCommandsFaq(data) {
  const el = faqAllowedText;
  if (!el || !data) return;
  if (!data.restricted) {
    el.textContent = 'No restrictions are configured — all commands are permitted.';
    return;
  }

  el.innerHTML = 'Click any command to load it into the prompt:';
  if (data.groups && data.groups.length > 0) {
    data.groups.forEach(group => {
      const groupEl = document.createElement('div');
      groupEl.className = 'allowed-group';
      if (group.name) {
        const header = document.createElement('div');
        header.className = 'allowed-group-header';
        header.textContent = group.name;
        groupEl.appendChild(header);
      }
      const list = document.createElement('div');
      list.className = 'allowed-list';
      group.commands.forEach(cmd => list.appendChild(makeAllowedCommandChip(cmd)));
      groupEl.appendChild(list);
      el.appendChild(groupEl);
    });
    return;
  }

  const list = document.createElement('div');
  list.className = 'allowed-list';
  data.commands.forEach(cmd => list.appendChild(makeAllowedCommandChip(cmd)));
  el.appendChild(list);
}

function renderFaqItems(items) {
  if (!faqBody) return;
  faqBody.innerHTML = '';
  (items || []).forEach(item => {
    const div = document.createElement('div');
    div.className = 'faq-item';

    const q = document.createElement('div');
    q.className = 'faq-q';
    q.textContent = item.question || '';

    const a = document.createElement('div');
    a.className = 'faq-a';
    if (item.ui_kind === 'allowed_commands') {
      a.id = 'faq-allowed-text';
      a.textContent = 'Loading…';
    } else if (item.ui_kind === 'limits') {
      a.id = 'faq-limits-text';
      a.textContent = 'Loading…';
    } else if (item.answer_html) {
      a.innerHTML = item.answer_html;
    } else {
      a.textContent = item.answer || '';
    }

    div.appendChild(q);
    div.appendChild(a);
    faqBody.appendChild(div);
  });

  renderAllowedCommandsFaq(allowedCommandsFaqData);
  renderFaqLimits(APP_CONFIG);
}

// ── Load config from server ──
apiFetch('/config').then(r => r.json()).then(cfg => {
  APP_CONFIG = cfg;
  document.title = cfg.app_name;
  if (headerTitle) headerTitle.textContent = cfg.app_name;
  const verEl = versionLabel;
  if (verEl) verEl.textContent = cfg.version ? `v${cfg.version} · real-time` : 'real-time';
  // Only apply server default theme if the user hasn't saved a local preference
  if (!getPreference('pref_theme') && !localStorage.getItem('theme') && cfg.default_theme === 'light') {
    applyThemePreference('light', false);
  }
  if (cfg.motd) {
    if (motd && motdWrap) { motd.innerHTML = renderMotd(cfg.motd); showMotdWrap(); }
  }
  updateNewTabBtn();
  renderFaqLimits(cfg);
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
    if (action === 'theme') {
      applyThemePreference(document.body.classList.contains('light') ? 'dark' : 'light');
      refocusTerminalInput();
    }
    if (action === 'faq') openFaq();
  });
});

// ── FAQ ──
function openFaq() {
  _closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  showFaqOverlay();
}
function closeFaq() {
  hideFaqOverlay();
  refocusTerminalInput();
}

faqBtn.addEventListener('click', openFaq);
_uiOverlayRefs.faqOverlay.addEventListener('click', e => {
  if (e.target === _uiOverlayRefs.faqOverlay) closeFaq();
});
faqCloseBtn.addEventListener('click', closeFaq);
optionsBtn?.addEventListener('click', openOptions);
_uiOverlayRefs.optionsOverlay?.addEventListener('click', e => {
  if (e.target === _uiOverlayRefs.optionsOverlay) closeOptions();
});
optionsCloseBtn?.addEventListener('click', closeOptions);
themePrefInputs.forEach(input => {
  input.addEventListener('change', () => applyThemePreference(input.value));
});
optionsTsSelect?.addEventListener('change', e => {
  applyTimestampPreference(e.target.value);
});
optionsLnToggle?.addEventListener('change', e => {
  applyLineNumberPreference(e.target.checked ? 'on' : 'off');
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

apiFetch('/history').then(r => r.json()).then(data => {
  hydrateCmdHistory(data.runs || []);
}).catch(err => {
  logClientError('failed to load /history', err);
});

// ── Tabs ──
setupTabScrollControls();
applyTimestampPreference(getPreference('pref_timestamps') || 'off', false);
applyLineNumberPreference(getPreference('pref_line_numbers') || 'off', false);
createTab('tab 1');
runWelcome();
setTimeout(() => {
  if (!cmdInput) return;
  if (useMobileTerminalViewportMode()) {
    if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
    if (typeof window !== 'undefined' && typeof window.scrollTo === 'function') {
      try {
        window.scrollTo({ top: 0, behavior: 'auto' });
      } catch (_) {
        // jsdom does not implement scrollTo; browsers do.
      }
    }
    return;
  }
  refocusTerminalInput();
}, 0);
syncMobileViewportState();

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
    if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
    refreshHistoryPanel();
  } else {
    refocusTerminalInput();
  }
});
historyCloseBtn.addEventListener('click', () => {
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
// - Alt+ArrowLeft / Alt+ArrowRight for tab cycling
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
      setComposerValue((cmdInput.value || '') + e.key);
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
    setComposerValue((cmdInput.value || '') + e.key);
    e.preventDefault();
    return;
  }
  if (e.key === 'Enter' && _welcomeActive && welcomeOwnsTab(activeTabId)) {
    if (cmdInput && cmdInput.value.trim()) return;
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
    closeFaq();
    closeOptions();
    hideSearchBar();
    clearSearch();
    if (isHistoryPanelOpen()) hideHistoryPanel();
  }
});

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
    if (!cmdInput || document.activeElement !== cmdInput) return;
    syncShellPrompt();
  });
}

// ── Autocomplete ──
apiFetch('/autocomplete').then(r => r.json()).then(data => {
  acSuggestions = data.suggestions || [];
}).catch(err => {
  logClientError('failed to load /autocomplete', err);
});

cmdInput.addEventListener('input', () => {
  handleComposerInputChange(cmdInput);
});

cmdInput.addEventListener('keydown', e => {
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
    const value = cmdInput.value;
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
    const value = cmdInput.value;
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
    cmdInput.setSelectionRange(0, 0);
    syncShellPrompt();
    return;
  }

  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault();
    const value = cmdInput.value;
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
    const value = cmdInput.value;
    const end = value.length;
    cmdInput.setSelectionRange(end, end);
    syncShellPrompt();
    return;
  }

  if (e.altKey && !e.ctrlKey && !e.metaKey && eventMatchesLetter(e, 'b')) {
    e.preventDefault();
    const value = cmdInput.value;
    const { start } = getCmdSelection(value);
    const next = findWordBoundaryLeft(value, start);
    cmdInput.setSelectionRange(next, next);
    syncShellPrompt();
    return;
  }

  if (e.altKey && !e.ctrlKey && !e.metaKey && eventMatchesLetter(e, 'f')) {
    e.preventDefault();
    const value = cmdInput.value;
    const { end } = getCmdSelection(value);
    const next = findWordBoundaryRight(value, end);
    cmdInput.setSelectionRange(next, next);
    syncShellPrompt();
    return;
  }

  if (e.key === 'Enter') {
    if (_welcomeActive && welcomeOwnsTab(activeTabId) && !cmdInput.value.trim()) {
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
        submitComposerCommand(cmdInput.value, { dismissKeyboard: true });
      } else {
        runCommand();
      }
    }
    return;
  }
  if (e.key === 'Tab') {
    e.preventDefault();
    if (acFiltered.length === 1) { acAccept(acFiltered[0]); }
    else if (acIndex >= 0 && acFiltered[acIndex]) { acAccept(acFiltered[acIndex]); }
    else if (acFiltered.length > 0) { acIndex = 0; acShow(acFiltered); }
    return;
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    const acOpen = isAcDropdownOpen();
    if (acOpen && acFiltered.length) {
      const acAbove = acDropdown.classList.contains('ac-up');
      acIndex = acAbove
        ? Math.max(acIndex - 1, 0)
        : Math.min(acIndex + 1, acFiltered.length - 1);
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
      const acAbove = acDropdown.classList.contains('ac-up');
      acIndex = acAbove
        ? Math.min(acIndex + 1, acFiltered.length - 1)
        : Math.max(acIndex - 1, -1);
      acShow(acFiltered);
      return;
    }
    if (navigateCmdHistory(1)) acHide();
    return;
  }
  if (e.key === 'Escape')    { acHide(); return; }
});

if (typeof window !== 'undefined') {
  window.addEventListener('resize', syncMobileViewportState);
  if (window.visualViewport && typeof window.visualViewport.addEventListener === 'function') {
    // Mobile keyboards resize the visual viewport after focus; keep the prompt pinned above it.
    window.visualViewport.addEventListener('resize', syncMobileViewportState);
    window.visualViewport.addEventListener('scroll', syncMobileViewportState);
  }
}

// ── Run button ──
runBtn.addEventListener('click', runCommand);

syncShellPrompt();

// ── Mobile composer ──
// A dedicated native input for narrow screens, separate from the desktop shell prompt.
// Uses CSS @media (max-width: 600px) to show/hide — no JS class needed for display.
// Only keyboard detection requires JS (to float composer above keyboard when open).

function setupMobileComposer() {
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
        blurVisibleComposerInputIfMobile();
      }
    };
    mobileShellTranscript.addEventListener('click', closeKeyboardFromTranscript);
  }
}

setupMobileComposer();
