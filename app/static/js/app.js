// ── Desktop UI module ──
// Shared helpers for keyboard shortcuts, overlays, and mobile-layout glue.

function syncShellPrompt() {
  // The visible prompt is rendered from shared composer state instead of from
  // the hidden input directly, so selection/caret state stays correct across
  // desktop/mobile and while welcome owns the tab.
  if (typeof shellPromptText === 'undefined' || !shellPromptText) return;
  const composer = typeof getComposerState === 'function' ? getComposerState() : null;
  const fallbackInput = typeof cmdInput !== 'undefined' && cmdInput ? cmdInput : null;
  const value = composer && typeof composer.value === 'string'
    ? composer.value
    : (fallbackInput ? fallbackInput.value || '' : '');
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
  if (typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode()) {
    const mobileInput = typeof getComposerInputs === 'function' ? getComposerInputs().mobile : null;
    if (mobileInput && typeof focusComposerInput === 'function') {
      if (typeof setMobileKeyboardOpenState === 'function') setMobileKeyboardOpenState(true);
      focusComposerInput(mobileInput, { preventScroll });
    }
    return;
  }
  if (typeof focusAnyComposerInput === 'function' && focusAnyComposerInput({ preventScroll: true })) return;
}

function useMobileTerminalViewportMode() {
  // Mobile mode depends on both width and input modality. A narrow desktop
  // browser window should not automatically switch into the mobile shell.
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
const _confirmHostEl = document.getElementById('confirm-host');
const _confirmHostHomeParent = _confirmHostEl ? _confirmHostEl.parentElement : null;
const _workflowsOverlayHomeParent = typeof workflowsOverlay !== 'undefined' && workflowsOverlay ? workflowsOverlay.parentElement : null;
const _faqOverlayHomeParent = typeof faqOverlay !== 'undefined' && faqOverlay ? faqOverlay.parentElement : null;
const _themeOverlayHomeParent = typeof themeOverlay !== 'undefined' && themeOverlay ? themeOverlay.parentElement : null;
const _optionsOverlayHomeParent = typeof optionsOverlay !== 'undefined' && optionsOverlay ? optionsOverlay.parentElement : null;
const _statusHomeParent = typeof status !== 'undefined' && status ? status.parentElement : null;
const _runTimerHomeParent = typeof runTimer !== 'undefined' && runTimer ? runTimer.parentElement : null;
const _headerHomeParent = typeof headerTitle !== 'undefined' && headerTitle ? headerTitle.closest('header') : (typeof document !== 'undefined' ? document.querySelector('header') : null);
const _mobileHeaderActionsHomeParent = typeof mobileHeaderActions !== 'undefined' && mobileHeaderActions ? mobileHeaderActions : _headerHomeParent;
const TAB_SESSION_STATE_KEY = `tab_session_state:${typeof SESSION_ID !== 'undefined' ? SESSION_ID : 'session'}`;
let _tabSessionPersistTimer = null;
let _tabSessionRestoreInProgress = false;
const _welcomeIntroModes = ['animated', 'disable_animation', 'remove'];
const _shareRedactionDefaultModes = ['unset', 'redacted', 'raw'];
const _hudClockModes = ['utc', 'local'];

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

// These refs let the same DOM nodes move between the desktop document flow and
// the simplified mobile shell without duplicating markup or event handlers.
const _mobileUiLayoutRefs = _getMobileUiLayoutRefs();
const _uiOverlayRefs = {
  mobileMenu: mobileMenu || null,
  hamburgerBtn: hamburgerBtn || null,
  workflowsOverlay: typeof workflowsOverlay !== 'undefined' && workflowsOverlay ? workflowsOverlay : null,
  faqOverlay: typeof faqOverlay !== 'undefined' && faqOverlay ? faqOverlay : null,
  themeOverlay: typeof themeOverlay !== 'undefined' && themeOverlay ? themeOverlay : null,
  optionsOverlay: typeof optionsOverlay !== 'undefined' && optionsOverlay ? optionsOverlay : null,
  historyPanel: typeof historyPanel !== 'undefined' && historyPanel ? historyPanel : null,
};

function _bindMobileComposerInteractions(uiRefs) {
  const composerRefs = uiRefs && uiRefs.composer;
  if (!composerRefs || !composerRefs.host || !cmdInput) return;
}

function _bindMobileEditBarInteractions(editBar) {
  if (!editBar || !cmdInput) return;
  editBar.querySelectorAll('button[data-mobile-edit], button[data-edit-action]').forEach(btn => {
    if (btn.dataset.mobileEditBound === '1') return;
    btn.dataset.mobileEditBound = '1';
    const action = btn.dataset.mobileEdit || btn.dataset.editAction;
    const repeating = action === 'left' || action === 'right';
    let handledPointerDown = false;
    let _repeatDelay = null;
    let _repeatInterval = null;
    const _clearRepeat = () => {
      if (_repeatDelay)    { clearTimeout(_repeatDelay);   _repeatDelay = null; }
      if (_repeatInterval) { clearInterval(_repeatInterval); _repeatInterval = null; }
    };
    const handler = (e) => {
      e.preventDefault();
      e.stopPropagation();
      performMobileEditAction(action);
      if (repeating) {
        _clearRepeat();
        _repeatDelay = setTimeout(() => {
          _repeatInterval = setInterval(() => performMobileEditAction(action), 60);
        }, 400);
      }
    };
    const stopRepeat = () => _clearRepeat();
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
      if (repeating) {
        btn.addEventListener('pointerup',     stopRepeat);
        btn.addEventListener('pointercancel', stopRepeat);
        btn.addEventListener('pointerleave',  stopRepeat);
      }
    } else {
      btn.addEventListener('mousedown',  handler);
      btn.addEventListener('touchstart', handler, { passive: false });
      if (repeating) {
        btn.addEventListener('mouseup',     stopRepeat);
        btn.addEventListener('touchend',    stopRepeat);
        btn.addEventListener('touchcancel', stopRepeat);
      }
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
  { node: permalinkToast, homeParent: _permalinkToastHomeParent, desktopAnchor: _confirmHostEl || faqOverlay || null },
  { node: _confirmHostEl, homeParent: _confirmHostHomeParent, desktopAnchor: faqOverlay || null },
  { node: faqOverlay, homeParent: _faqOverlayHomeParent, desktopAnchor: themeOverlay || null },
  { node: themeOverlay, homeParent: _themeOverlayHomeParent, desktopAnchor: optionsOverlay || null },
  { node: optionsOverlay, homeParent: _optionsOverlayHomeParent, desktopAnchor: workflowsOverlay || null },
  { node: workflowsOverlay, homeParent: _workflowsOverlayHomeParent, desktopAnchor: null },
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
  // The mobile shell is mostly a re-parenting operation: move the same chrome,
  // transcript, and overlays into mobile mounts instead of rendering variants.
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
    if (useMobile) _moveComposerNode(status, _mobileHeaderActionsHomeParent, hamburgerBtn || null);
    else _moveComposerNode(status, _statusHomeParent);
  }
  if (runTimer && _headerHomeParent) {
    if (useMobile) _moveComposerNode(runTimer, _mobileHeaderActionsHomeParent, hamburgerBtn || null);
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
  const liveInnerHeight = Math.round(window.innerHeight || 0);
  const visualHeight = Math.round(window.visualViewport.height || 0);
  const offsetTop = Math.round(window.visualViewport.offsetTop || 0);
  const closedHeight = typeof getMobileViewportClosedHeight === 'function'
    ? getMobileViewportClosedHeight()
    : null;
  const baselineHeight = typeof closedHeight === 'number' && closedHeight > 0
    ? Math.max(closedHeight, liveInnerHeight)
    : liveInnerHeight;
  return Math.max(0, baselineHeight - visualHeight - offsetTop);
}

function isMobileKeyboardOpen(offset = null) {
  if (!useMobileTerminalViewportMode()) return false;
  const mobileInputEl = (typeof getVisibleComposerInput === 'function' && getVisibleComposerInput()) || null;
  const mobileInputFocused = !!(mobileInputEl && typeof document !== 'undefined' && document.activeElement === mobileInputEl);
  if (!mobileInputFocused) return false;
  const keyboardMarkedOpen = !!(
    typeof document !== 'undefined'
    && document.body
    && document.body.classList
    && document.body.classList.contains('mobile-keyboard-open')
  );
  if (keyboardMarkedOpen) return true;
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
  if (typeof syncMobileComposerKeyboardState === 'function') {
    syncMobileComposerKeyboardState(keyboardOffset, {
      active: activeMobileMode,
      open: activeMobileMode && keyboardOpen,
    });
  }
  else document.body.classList.toggle('mobile-keyboard-open', activeMobileMode && keyboardOpen);
  syncMobileShellLayout(activeMobileMode);
  syncMobileComposerLayout(activeMobileMode);
  if (activeMobileMode) syncMobileViewportHeight({ keyboardOpen });
  if (activeMobileMode && keyboardOpen && typeof _refreshFollowingOutputsAfterLayout === 'function') {
    setTimeout(() => {
      if (!useMobileTerminalViewportMode()) return;
      if (!document.body || !document.body.classList.contains('mobile-keyboard-open')) return;
      _refreshFollowingOutputsAfterLayout();
    }, 0);
  }
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

function getWelcomeIntroPreference() {
  const value = getPreference('pref_welcome_intro');
  return _welcomeIntroModes.includes(value) ? value : 'animated';
}

function getShareRedactionDefaultPreference() {
  const value = getPreference('pref_share_redaction_default');
  return _shareRedactionDefaultModes.includes(value) ? value : 'unset';
}

function getRunNotifyPreference() {
  return getPreference('pref_run_notify') === 'on' ? 'on' : 'off';
}

function getHudClockPreference() {
  const value = getPreference('pref_hud_clock');
  return _hudClockModes.includes(value) ? value : 'utc';
}

async function applyRunNotifyPreference(mode, persist = true) {
  let nextMode = mode === 'on' ? 'on' : 'off';
  if (nextMode === 'on') {
    if (typeof Notification === 'undefined') {
      nextMode = 'off';
    } else if (Notification.permission === 'denied') {
      nextMode = 'off';
      showToast('Notifications are blocked in your browser settings.');
    } else if (Notification.permission !== 'granted') {
      const result = await Notification.requestPermission();
      if (result !== 'granted') nextMode = 'off';
    }
  }
  if (persist) setPreferenceCookie('pref_run_notify', nextMode);
  syncOptionsControls();
}

function applyHudClockPreference(mode, persist = true) {
  const nextMode = _hudClockModes.includes(mode) ? mode : 'utc';
  if (persist) setPreferenceCookie('pref_hud_clock', nextMode);
  syncOptionsControls();
  if (typeof globalThis.renderHudClock === 'function') globalThis.renderHudClock();
}

function syncOptionsControls() {
  const tsSelect = optionsTsSelect;
  if (tsSelect) tsSelect.value = typeof tsMode === 'string' ? tsMode : 'off';
  const lnToggle = optionsLnToggle;
  if (lnToggle) lnToggle.checked = typeof lnMode === 'string' && lnMode === 'on';
  if (optionsWelcomeSelect) optionsWelcomeSelect.value = getWelcomeIntroPreference();
  if (optionsShareRedactionSelect) optionsShareRedactionSelect.value = getShareRedactionDefaultPreference();
  if (optionsNotifyToggle) optionsNotifyToggle.checked = getRunNotifyPreference() === 'on';
  if (optionsHudClockSelect) optionsHudClockSelect.value = getHudClockPreference();
}

function applyThemePreference(theme, persist = true) {
  applyThemeSelection(theme, persist);
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

function applyWelcomeIntroPreference(mode, persist = true) {
  const nextMode = _welcomeIntroModes.includes(mode) ? mode : 'animated';
  if (persist) setPreferenceCookie('pref_welcome_intro', nextMode);
  syncOptionsControls();
}

function applyShareRedactionDefaultPreference(mode, persist = true) {
  const nextMode = _shareRedactionDefaultModes.includes(mode) ? mode : 'unset';
  if (persist) setPreferenceCookie('pref_share_redaction_default', nextMode);
  syncOptionsControls();
}

function _closeMajorOverlays() {
  if (isHistoryPanelOpen()) hideHistoryPanel();
  if (isWorkflowsOverlayOpen()) hideWorkflowsOverlay();
  if (isFaqOverlayOpen()) hideFaqOverlay();
  if (isThemeOverlayOpen()) hideThemeOverlay();
  if (isOptionsOverlayOpen()) hideOptionsOverlay();
  if (typeof isShortcutsOverlayOpen === 'function' && isShortcutsOverlayOpen()) {
    if (typeof hideShortcutsOverlay === 'function') hideShortcutsOverlay();
  }
}

function openOptions() {
  // Opening one major overlay should implicitly close the others so mobile and
  // desktop never stack multiple drawers/modals on top of each other.
  _closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  syncOptionsControls();
  if (typeof _updateOptionsSessionTokenStatus === 'function') _updateOptionsSessionTokenStatus();
  showOptionsOverlay();
}

function closeOptions() {
  hideOptionsOverlay();
  refocusComposerAfterAction({ defer: true });
}

function openThemeSelector() {
  _closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  renderThemeSelectionOptions();
  syncThemeSelectionControls();
  showThemeOverlay();
  setTimeout(() => {
    const selectedCard = themeSelect && themeSelect.querySelector('.theme-card-active');
    const target = selectedCard || themeSelect?.querySelector('[data-theme-name]');
    if (focusElement(target, { preventScroll: true })) return;
    focusElement(themeSelect, { preventScroll: true });
  }, 0);
}

function closeThemeSelector() {
  hideThemeOverlay();
  refocusComposerAfterAction({ defer: true });
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
  if (APP_CONFIG && APP_CONFIG.share_redaction_enabled === false) return 'raw';
  const preferred = getShareRedactionDefaultPreference();
  if (preferred === 'raw' || preferred === 'redacted') return preferred;

  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();

  const { field, checkbox } = _buildShareRedactionRememberField();
  let choice = null;
  try {
    choice = await showConfirm({
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
    applyShareRedactionDefaultPreference(choice);
  }
  if (choice === 'raw' || choice === 'redacted') return choice;
  return null;
}

function _snapshotTabRawLines(rawLines) {
  if (!Array.isArray(rawLines)) return [];
  return rawLines.map(line => ({
    text: String(line && line.text || ''),
    cls: String(line && line.cls || ''),
    tsC: String(line && line.tsC || ''),
    tsE: String(line && line.tsE || ''),
  }));
}

function _flushActiveTabDraftForSessionState() {
  const activeTab = typeof getActiveTab === 'function' ? getActiveTab() : null;
  if (!activeTab || activeTab.st === 'running') return;
  activeTab.draftInput = typeof getComposerValue === 'function'
    ? getComposerValue()
    : (typeof cmdInput !== 'undefined' && cmdInput ? cmdInput.value || '' : '');
}

function _tabSessionSnapshot() {
  _flushActiveTabDraftForSessionState();
  const allTabs = Array.isArray(tabs) ? tabs : [];
  const persisted = allTabs
    .filter(tab => tab && tab.st !== 'running' && !tab.closing)
    .map(tab => ({
      label: String(tab.label || ''),
      command: String(tab.command || ''),
      renamed: !!tab.renamed,
      draftInput: String(tab.draftInput || ''),
      st: String(tab.st || 'idle'),
      exitCode: tab.exitCode == null ? null : Number(tab.exitCode),
      historyRunId: String(tab.historyRunId || ''),
      previewTruncated: !!tab.previewTruncated,
      fullOutputAvailable: !!tab.fullOutputAvailable,
      fullOutputLoaded: !!tab.fullOutputLoaded,
      rawLines: _snapshotTabRawLines(tab.rawLines),
    }));
  if (!persisted.length) return null;
  const activeIndex = persisted.findIndex((_, idx) => {
    const sourceTabs = allTabs.filter(tab => tab && tab.st !== 'running' && !tab.closing);
    return sourceTabs[idx] && sourceTabs[idx].id === activeTabId;
  });
  return {
    version: 1,
    activeIndex: activeIndex >= 0 ? activeIndex : 0,
    tabs: persisted,
  };
}

function persistTabSessionStateNow() {
  if (_tabSessionRestoreInProgress) return;
  try {
    const snapshot = _tabSessionSnapshot();
    if (!snapshot) {
      sessionStorage.removeItem(TAB_SESSION_STATE_KEY);
      return;
    }
    sessionStorage.setItem(TAB_SESSION_STATE_KEY, JSON.stringify(snapshot));
  } catch (_) {}
}

function schedulePersistTabSessionState() {
  if (_tabSessionRestoreInProgress) return;
  clearTimeout(_tabSessionPersistTimer);
  _tabSessionPersistTimer = setTimeout(() => {
    _tabSessionPersistTimer = null;
    persistTabSessionStateNow();
  }, 120);
}

if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', () => {
    persistTabSessionStateNow();
  });
  window.addEventListener('beforeunload', () => {
    persistTabSessionStateNow();
  });
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      persistTabSessionStateNow();
    }
  });
}

function restoreTabSessionState() {
  let parsed;
  try {
    parsed = JSON.parse(sessionStorage.getItem(TAB_SESSION_STATE_KEY) || 'null');
  } catch (_) {
    return false;
  }
  if (!parsed || parsed.version !== 1 || !Array.isArray(parsed.tabs) || !parsed.tabs.length) return false;

  _tabSessionRestoreInProgress = true;
  try {
    _welcomeBootPending = false;
    if (typeof unmountShellPrompt === 'function') unmountShellPrompt();
    if (typeof tabsBar !== 'undefined' && tabsBar) {
      tabsBar.querySelectorAll('.tab').forEach(node => node.remove());
    }
    if (typeof tabPanels !== 'undefined' && tabPanels) tabPanels.innerHTML = '';
    if (typeof setTabs === 'function') setTabs([]);
    if (typeof setActiveTabId === 'function') setActiveTabId(null);

    const restoredIds = [];
    const restoredRecords = [];
    parsed.tabs.forEach((item, index) => {
      const label = String(item && item.label || `tab ${index + 1}`);
      const tabId = typeof createTab === 'function' ? createTab(label) : null;
      if (!tabId) return;
      const tab = typeof getTab === 'function' ? getTab(tabId) : null;
      if (!tab) return;
      tab.command = String(item && item.command || '');
      tab.renamed = !!(item && item.renamed);
      tab.draftInput = String(item && item.draftInput || '');
      tab.exitCode = item && item.exitCode == null ? null : Number(item.exitCode);
      tab.historyRunId = String(item && item.historyRunId || '');
      tab.previewTruncated = !!(item && item.previewTruncated);
      tab.fullOutputAvailable = !!(item && item.fullOutputAvailable);
      tab.fullOutputLoaded = !!(item && item.fullOutputLoaded);
      if (typeof renderRestoredTabOutput === 'function') {
        renderRestoredTabOutput(tabId, item && item.rawLines);
      }
      if (typeof setTabStatus === 'function') {
        const status = typeof item?.st === 'string' && item.st !== 'running' ? item.st : 'idle';
        setTabStatus(tabId, status);
      }
      if (typeof hideTabKillBtn === 'function') hideTabKillBtn(tabId);
      restoredIds.push(tabId);
      restoredRecords.push({ tabId, item });
    });

    restoredRecords.forEach(({ tabId, item }) => {
      const tab = typeof getTab === 'function' ? getTab(tabId) : null;
      if (!tab) return;
      tab.command = String(item && item.command || '');
      tab.renamed = !!(item && item.renamed);
      tab.draftInput = String(item && item.draftInput || '');
      tab.exitCode = item && item.exitCode == null ? null : Number(item.exitCode);
      tab.historyRunId = String(item && item.historyRunId || '');
      tab.previewTruncated = !!(item && item.previewTruncated);
      tab.fullOutputAvailable = !!(item && item.fullOutputAvailable);
      tab.fullOutputLoaded = !!(item && item.fullOutputLoaded);
    });

    if (!restoredIds.length) return false;
    const activeIndex = Math.max(0, Math.min(Number(parsed.activeIndex) || 0, restoredIds.length - 1));
    if (typeof activateTab === 'function') activateTab(restoredIds[activeIndex], { focusComposer: false });
    if (typeof mountShellPrompt === 'function') mountShellPrompt(restoredIds[activeIndex], true);
    return true;
  } finally {
    _tabSessionRestoreInProgress = false;
  }
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
  // Letter chords (T, W) require no Shift — Alt+Shift+T is the theme-selector
  // chrome shortcut and must fall through to handleChromeShortcut.
  if (!e.shiftKey && eventMatchesLetter(e, 't')) {
    createShortcutTab();
    e.preventDefault();
    return true;
  }
  if (!e.shiftKey && eventMatchesLetter(e, 'w')) {
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
  if (e.key === 'Tab') {
    activateRelativeTab(e.shiftKey ? -1 : 1);
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

// Desktop chrome shortcuts (rail, search, history, options, theme, workflows).
// The composer is allowed to pass through so prompt-focused users can still
// trigger chrome toggles — each branch calls preventDefault so Option-glyphs
// (`«`, `˙`, `©`, `≤`, `ˇ`, `ß`) never leak into the prompt on macOS. Other
// editable targets (modal inputs, search field, options textarea) remain
// gated so typing isn't hijacked.
//
// Search is bound to Alt+S (not Alt+F) because the composer owns Alt+F as
// readline word-forward; binding search to Alt+F would either hijack that
// or require a context-dependent chord that's a net UX loss. Alt+S has no
// readline conflict and works identically from everywhere.
//
// Each chord toggles its surface directly rather than delegating to the
// corresponding header button's click handler. The header buttons share a
// pre-existing quirk where they call _closeMajorOverlays() before toggling,
// which cancels out the close half of the toggle.
function handleChromeShortcut(e) {
  if (!e.altKey || e.ctrlKey || e.metaKey) return false;
  if (shouldIgnoreGlobalShortcutTarget(e.target)) return false;
  // Alt+Shift+T → theme; guard first so it doesn't match Alt+Shift letter = T as tab-new.
  if (e.shiftKey && eventMatchesLetter(e, 't')) {
    if (typeof isThemeOverlayOpen === 'function' && isThemeOverlayOpen()) closeThemeSelector();
    else openThemeSelector();
    e.preventDefault();
    return true;
  }
  // All remaining chrome chords are shift-free.
  if (e.shiftKey) return false;
  if (eventMatchesLetter(e, 'h')) {
    if (typeof isHistoryPanelOpen === 'function' && isHistoryPanelOpen()) {
      hideHistoryPanel();
    } else {
      document.getElementById('hist-btn')?.click();
    }
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, 'g')) {
    if (typeof isWorkflowsOverlayOpen === 'function' && isWorkflowsOverlayOpen()) closeWorkflows();
    else openWorkflows();
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, 's')) {
    document.getElementById('search-toggle-btn')?.click();
    e.preventDefault();
    return true;
  }
  if (eventMatchesCode(e, 'Comma') || e.key === ',') {
    if (typeof isOptionsOverlayOpen === 'function' && isOptionsOverlayOpen()) closeOptions();
    else openOptions();
    e.preventDefault();
    return true;
  }
  if (eventMatchesCode(e, 'Backslash') || e.key === '\\') {
    if (typeof toggleRailCollapsed === 'function') toggleRailCollapsed();
    e.preventDefault();
    return true;
  }
  if (eventMatchesCode(e, 'Slash') || e.key === '/' || e.key === '÷') {
    if (typeof isFaqOverlayOpen === 'function' && isFaqOverlayOpen()) closeFaq();
    else openFaq();
    e.preventDefault();
    return true;
  }
  return false;
}

function getComposerStateSnapshot() {
  if (typeof getComposerState === 'function') {
    const composer = getComposerState();
    if (composer) return composer;
  }
  return null;
}

function getCmdSelection(value = null) {
  const composer = getComposerStateSnapshot();
  const sourceValue = typeof value === 'string'
    ? value
    : (composer && typeof composer.value === 'string'
      ? composer.value
      : (cmdInput.value || ''));
  let start = composer && typeof composer.selectionStart === 'number'
    ? composer.selectionStart
    : (typeof cmdInput.selectionStart === 'number' ? cmdInput.selectionStart : sourceValue.length);
  let end = composer && typeof composer.selectionEnd === 'number'
    ? composer.selectionEnd
    : (typeof cmdInput.selectionEnd === 'number' ? cmdInput.selectionEnd : sourceValue.length);
  if (start > end) [start, end] = [end, start];
  return { start, end };
}

function getInputSelection(input, value = input && input.value ? input.value : '') {
  let start = typeof input.selectionStart === 'number' ? input.selectionStart : value.length;
  let end = typeof input.selectionEnd === 'number' ? input.selectionEnd : value.length;
  if (start > end) [start, end] = [end, start];
  return { start, end };
}

function replaceCmdRange(value, start, end, replacement = '') {
  const nextPos = start + replacement.length;
  setComposerValue(value.slice(0, start) + replacement + value.slice(end), nextPos, nextPos);
}

function moveCmdCaret(delta) {
  const value = typeof getComposerValue === 'function' ? getComposerValue() : (cmdInput.value || '');
  const { start, end } = getCmdSelection(value);
  const next = Math.max(0, Math.min(value.length, (delta < 0 ? start : end) + delta));
  if (typeof syncComposerSelection === 'function') syncComposerSelection(next, next, { input: getVisibleComposerInput() });
  else if (cmdInput && typeof cmdInput.setSelectionRange === 'function') cmdInput.setSelectionRange(next, next);
  syncShellPrompt();
}

function setCmdCaret(position) {
  const value = typeof getComposerValue === 'function' ? getComposerValue() : (cmdInput.value || '');
  const next = Math.max(0, Math.min(value.length, position));
  if (typeof syncComposerSelection === 'function') syncComposerSelection(next, next, { input: getVisibleComposerInput() });
  else if (cmdInput && typeof cmdInput.setSelectionRange === 'function') cmdInput.setSelectionRange(next, next);
  syncShellPrompt();
}

function deleteCmdWordLeft() {
  const value = typeof getComposerValue === 'function' ? getComposerValue() : (cmdInput.value || '');
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

  const composer = getComposerStateSnapshot();
  const value = composer && typeof composer.value === 'string'
    ? composer.value
    : (input.value || '');
  const { start, end } = composer
    ? getCmdSelection(value)
    : getInputSelection(input, value);
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
    if (typeof syncComposerSelection === 'function') syncComposerSelection(nextStart, nextEnd, { input });
    else if (input && typeof input.setSelectionRange === 'function') input.setSelectionRange(nextStart, nextEnd);
  } else {
    setComposerValue(nextValue, nextStart, nextEnd);
  }

  if (typeof focusAnyComposerInput === 'function') setTimeout(() => focusAnyComposerInput({ preventScroll: true }), 0);
}

function syncMobileViewportHeight({ keyboardOpen = null } = {}) {
  if (typeof document === 'undefined' || typeof window === 'undefined') return;
  const visualHeight = window.visualViewport ? Math.round(window.visualViewport.height) : 0;
  const innerHeight = Math.round(window.innerHeight || 0);
  const useKeyboardOpen = typeof keyboardOpen === 'boolean'
    ? keyboardOpen
    : !!(typeof document !== 'undefined'
      && document.body
      && document.body.classList
      && document.body.classList.contains('mobile-keyboard-open'));
  if (!useKeyboardOpen && innerHeight > 0 && typeof setMobileViewportClosedHeight === 'function') {
    setMobileViewportClosedHeight(innerHeight);
  }
  const h = useKeyboardOpen
    ? (visualHeight || innerHeight)
    : Math.max(innerHeight, visualHeight);
  if (!(h > 0)) return;
  document.documentElement.style.setProperty('--mobile-viewport-height', `${h}px`);
}

function syncMobileComposerKeyboard({ open = null } = {}) {
  if (typeof window === 'undefined') return;
  const offset = getMobileKeyboardOffset();
  const keyboardOpen = typeof syncMobileComposerKeyboardState === 'function'
    ? syncMobileComposerKeyboardState(offset, { open })
    : !!open;
  syncMobileViewportHeight({ keyboardOpen });
  if (keyboardOpen && typeof _refreshFollowingOutputsAfterLayout === 'function') {
    setTimeout(() => {
      if (!document.body || !document.body.classList.contains('mobile-keyboard-open')) return;
      _refreshFollowingOutputsAfterLayout();
    }, 0);
  }
}

let _mobileComposerKeyboardSyncTimer = null;
function queueMobileComposerKeyboardSync(delay = 120) {
  if (typeof window === 'undefined') return;
  if (_mobileComposerKeyboardSyncTimer) clearTimeout(_mobileComposerKeyboardSyncTimer);
  _mobileComposerKeyboardSyncTimer = setTimeout(() => {
    _mobileComposerKeyboardSyncTimer = null;
    syncMobileComposerKeyboard();
  }, delay);
}

function bindMobileComposerKeyboardListeners(mobileInput) {
  if (!mobileInput || typeof window === 'undefined') return;
  const closeMobileKeyboard = (delay = 120) => {
    if (typeof setMobileKeyboardOpenState === 'function') setMobileKeyboardOpenState(false, { delay });
  };
  const resetClosedMobileKeyboardLayout = () => {
    if (typeof syncMobileComposerKeyboardState === 'function') {
      syncMobileComposerKeyboardState(0, { open: false });
    }
    syncMobileViewportHeight({ keyboardOpen: false });
  };
  const queueMobileViewportRecovery = (delays = [50, 180]) => {
    delays.forEach(delay => {
      setTimeout(() => {
        syncMobileComposerKeyboard();
        syncMobileViewportState();
      }, delay);
    });
  };
  if (window.visualViewport && typeof window.visualViewport.addEventListener === 'function') {
    window.visualViewport.addEventListener('resize', () => {
      syncMobileComposerKeyboard();
      queueMobileComposerKeyboardSync();
    });
  }
  mobileInput.addEventListener('focus', () => {
    if (typeof setComposerState === 'function') {
      setComposerState({
        value: mobileInput.value || '',
        selectionStart: typeof mobileInput.selectionStart === 'number' ? mobileInput.selectionStart : (mobileInput.value || '').length,
        selectionEnd: typeof mobileInput.selectionEnd === 'number' ? mobileInput.selectionEnd : (mobileInput.value || '').length,
        activeInput: 'mobile',
      });
    }
    if (typeof setMobileKeyboardOpenState === 'function') setMobileKeyboardOpenState(true);
    syncMobileComposerKeyboard();
    queueMobileComposerKeyboardSync();
  });
  mobileInput.addEventListener('blur', () => {
    closeMobileKeyboard();
    syncMobileComposerKeyboard();
    queueMobileComposerKeyboardSync();
  });

  // When the user returns to the browser from another app, the OS may have
  // closed the keyboard without firing a visualViewport resize event, leaving
  // the stale mobile-keyboard-open class and --mobile-keyboard-offset on the
  // page.  Re-run a full viewport state sync after a short settle delay.
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        closeMobileKeyboard(0);
        if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
        resetClosedMobileKeyboardLayout();
        return;
      }
      queueMobileViewportRecovery();
    });
  }
  window.addEventListener('focus', () => {
    queueMobileViewportRecovery([80, 220]);
  });
  window.addEventListener('pageshow', () => {
    queueMobileViewportRecovery([0, 120]);
  });
}

function bindMobileComposerSubmitAndInputListeners(mobileInput) {
  if (!mobileInput || !mobileRunBtn) return;
  // Submit handler — read the visible composer input and submit through the
  // shared command engine.
  function _mobileSubmit() {
    submitVisibleComposerCommand({ dismissKeyboard: true, focusAfterSubmit: false });
  }

  mobileRunBtn.addEventListener('click', _mobileSubmit);

  // Sync mobile input through the shared composer handler so autocomplete and
  // shared composer state stay on the same path.
  mobileInput.addEventListener('input', () => {
    handleComposerInputChange(mobileInput);
    const activeTab = typeof getActiveTab === 'function' ? getActiveTab() : null;
    if (activeTab && activeTab.st !== 'running') {
      activeTab.draftInput = typeof getComposerValue === 'function' ? getComposerValue() : (mobileInput.value || '');
      if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
    }
  });

  mobileInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      e.preventDefault();
      _mobileSubmit();
    }
  });

  // Guard against something resetting the cursor to end synchronously after a
  // tap repositions it. Capture the cursor position at click time (iOS has
  // already placed it by then) and restore it on the next tick if it moved
  // specifically to end — the symptom of a spurious focus() or setSelectionRange
  // call clobbering the tap-to-reposition result.
  mobileInput.addEventListener('click', () => {
    if (!useMobileTerminalViewportMode()) return;
    if (typeof document === 'undefined' || document.activeElement !== mobileInput) return;
    const savedStart = mobileInput.selectionStart;
    const savedEnd   = mobileInput.selectionEnd;
    const valueLen   = (mobileInput.value || '').length;
    if (typeof savedStart !== 'number' || savedStart >= valueLen) return;
    setTimeout(() => {
      if (typeof document === 'undefined' || document.activeElement !== mobileInput) return;
      if (mobileInput.selectionStart >= (mobileInput.value || '').length) {
        mobileInput.setSelectionRange(savedStart, savedEnd);
      }
      if (typeof setComposerState === 'function') {
        setComposerState({
          value: mobileInput.value || '',
          selectionStart: typeof mobileInput.selectionStart === 'number' ? mobileInput.selectionStart : (mobileInput.value || '').length,
          selectionEnd: typeof mobileInput.selectionEnd === 'number' ? mobileInput.selectionEnd : (mobileInput.value || '').length,
          activeInput: 'mobile',
        });
      }
      syncShellPrompt();
    }, 0);
  });
}

function bindMobileEditBarListeners(editBar) {
  if (!editBar) return;
  editBar.querySelectorAll('button[data-mobile-edit], button[data-edit-action]').forEach(btn => {
    if (btn.dataset.mobileEditBound === '1') return;
    btn.dataset.mobileEditBound = '1';
    const action = btn.dataset.mobileEdit || btn.dataset.editAction;
    const repeating = action === 'left' || action === 'right';
    let handledPointerDown = false;
    let _repeatDelay = null;
    let _repeatInterval = null;
    const _clearRepeat = () => {
      if (_repeatDelay)    { clearTimeout(_repeatDelay);   _repeatDelay = null; }
      if (_repeatInterval) { clearInterval(_repeatInterval); _repeatInterval = null; }
      if (typeof document !== 'undefined') {
        document.removeEventListener('pointerup',     stopRepeat);
        document.removeEventListener('pointercancel', stopRepeat);
        document.removeEventListener('touchend',      stopRepeat);
        document.removeEventListener('touchcancel',   stopRepeat);
      }
    };
    const stopRepeat = () => _clearRepeat();
    const handler = e => {
      e.preventDefault();
      e.stopPropagation();
      performMobileEditAction(action);
      if (repeating) {
        _clearRepeat();
        _repeatDelay = setTimeout(() => {
          _repeatInterval = setInterval(() => performMobileEditAction(action), 60);
        }, 400);
        if (typeof document !== 'undefined') {
          document.addEventListener('pointerup',     stopRepeat);
          document.addEventListener('pointercancel', stopRepeat);
          document.addEventListener('touchend',      stopRepeat);
          document.addEventListener('touchcancel',   stopRepeat);
        }
      }
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
      if (repeating) {
        btn.addEventListener('pointerup',     stopRepeat);
        btn.addEventListener('pointercancel', stopRepeat);
        btn.addEventListener('pointerleave',  stopRepeat);
      }
    } else {
      btn.addEventListener('mousedown',  handler);
      btn.addEventListener('touchstart', handler, { passive: false });
      if (repeating) {
        btn.addEventListener('mouseup',     stopRepeat);
        btn.addEventListener('touchend',    stopRepeat);
        btn.addEventListener('touchcancel', stopRepeat);
      }
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
function _getThemeRegistry() {
  // Prefer the runtime /themes payload when present, then fall back to the
  // bootstrapped globals so the selector still works during partial failures.
  if (typeof window !== 'undefined' && window.ThemeRegistry && typeof window.ThemeRegistry === 'object') {
    return window.ThemeRegistry;
  }
  const currentThemeName = (document.body && document.body.dataset && document.body.dataset.theme) || _savedThemeName() || '';
  const currentThemeVars = typeof window !== 'undefined' && window.ThemeCssVars && window.ThemeCssVars.current
    && typeof window.ThemeCssVars.current === 'object'
    ? window.ThemeCssVars.current
    : {};
  return {
    current: currentThemeName
      ? { name: currentThemeName, label: currentThemeName, source: 'fallback', vars: currentThemeVars }
      : null,
    themes: [],
  };
}

function _getThemeThemes() {
  const registry = _getThemeRegistry();
  return Array.isArray(registry.themes) ? registry.themes : [];
}

function _normalizeThemeName(name) {
  const value = typeof name === 'string' ? name.trim() : '';
  return value.endsWith('.yaml') ? value.slice(0, -5) : value;
}

function _themeEntryMatches(entry, name) {
  const needle = _normalizeThemeName(name);
  if (!needle) return false;
  return _normalizeThemeName(entry?.name) === needle || _normalizeThemeName(entry?.filename) === needle;
}

function _themeEntryGroup(entry) {
  const group = typeof entry?.group === 'string' ? entry.group.trim() : '';
  return group || 'Other';
}

function _themeEntrySortValue(entry) {
  const value = Number(entry?.sort);
  return Number.isFinite(value) ? value : Number.POSITIVE_INFINITY;
}

function _compareThemeEntries(a, b) {
  const sortA = _themeEntrySortValue(a);
  const sortB = _themeEntrySortValue(b);
  if (sortA !== sortB) return sortA - sortB;
  const groupA = _themeEntryGroup(a).toLowerCase();
  const groupB = _themeEntryGroup(b).toLowerCase();
  if (groupA !== groupB) return groupA.localeCompare(groupB);
  const labelA = String(a?.label || a?.name || '').toLowerCase();
  const labelB = String(b?.label || b?.name || '').toLowerCase();
  if (labelA !== labelB) return labelA.localeCompare(labelB);
  return String(a?.name || '').localeCompare(String(b?.name || ''));
}

function _findThemeEntry(name) {
  const needle = _normalizeThemeName(name);
  if (!needle) return null;
  const registry = _getThemeRegistry();
  if (registry.current && _themeEntryMatches(registry.current, needle)) return registry.current;
  return _getThemeThemes().find(theme => theme && _themeEntryMatches(theme, needle)) || null;
}

function _defaultThemeEntry() {
  const registry = _getThemeRegistry();
  return registry.current || _findThemeEntry(APP_CONFIG?.default_theme || '') || {
    name: 'dark',
    label: 'Dark',
    source: 'built-in',
    vars: (window.ThemeCssVars && window.ThemeCssVars.fallback) || {},
    theme_vars: (window.ThemeCssVars && window.ThemeCssVars.fallback) || {},
  };
}

function _applyThemeVars(entry) {
  if (!entry || !entry.vars || !document.documentElement) return;
  Object.entries(entry.vars).forEach(([name, value]) => {
    document.documentElement.style.setProperty(name, value);
  });
  document.documentElement.style.colorScheme = entry.color_scheme || 'light dark';
  const colorSchemeMeta = document.querySelector('meta[name="color-scheme"]');
  if (colorSchemeMeta) colorSchemeMeta.setAttribute('content', entry.color_scheme || 'light dark');
}

function _applyThemePreviewVars(target, vars) {
  if (!target || !vars || !target.style) return;
  Object.entries(vars).forEach(([name, value]) => {
    target.style.setProperty(name, value);
  });
}

function _persistThemeEntry(entry) {
  if (!entry) return;
  setPreferenceCookie('pref_theme_name', entry.name);
  localStorage.setItem('theme', entry.name);
}

function _savedThemeName() {
  return getPreference('pref_theme_name')
    || localStorage.getItem('theme')
    || getPreference('pref_theme')
    || '';
}

function _resolveThemeEntry(name) {
  return _findThemeEntry(name) || _defaultThemeEntry();
}

function _buildThemePreviewCard(theme) {
  const card = document.createElement('button');
  const themeName = theme?.name || '';
  const themeLabel = theme?.label || themeName;
  card.type = 'button';
  card.className = 'theme-card';
  card.dataset.themeName = themeName;
  card.dataset.themeLabel = themeLabel;
  card.setAttribute('aria-label', `${themeLabel} theme`);
  card.setAttribute('aria-pressed', 'false');
  _applyThemePreviewVars(card, theme?.vars || {});
  const preview = document.createElement('span');
  preview.className = 'theme-card-preview';
  preview.setAttribute('aria-hidden', 'true');

  const bar = document.createElement('span');
  bar.className = 'theme-card-preview-bar';
  ['dot-r', 'dot-y', 'dot-g'].forEach(dotClass => {
    const dot = document.createElement('span');
    dot.className = `dot ${dotClass}`;
    bar.appendChild(dot);
  });
  const pill = document.createElement('span');
  pill.className = 'theme-card-preview-pill';
  bar.appendChild(pill);

  const panel = document.createElement('span');
  panel.className = 'theme-card-preview-panel';
  const prompt = document.createElement('span');
  prompt.className = 'theme-card-preview-prompt';
  const prefix = document.createElement('span');
  prefix.className = 'theme-card-preview-prefix';
  prefix.textContent = (typeof APP_CONFIG !== 'undefined' && APP_CONFIG.prompt_prefix) || 'anon@darklab:~$';
  prompt.appendChild(prefix);

  const line1 = document.createElement('span');
  line1.className = 'theme-card-preview-line';
  const line2 = document.createElement('span');
  line2.className = 'theme-card-preview-line theme-card-preview-line-short';
  const chipRow = document.createElement('span');
  chipRow.className = 'theme-card-preview-chip-row';
  for (let i = 0; i < 2; i += 1) {
    const chip = document.createElement('span');
    chip.className = 'theme-card-preview-chip';
    chipRow.appendChild(chip);
  }

  panel.appendChild(prompt);
  panel.appendChild(line1);
  panel.appendChild(line2);
  panel.appendChild(chipRow);
  preview.appendChild(bar);
  preview.appendChild(panel);

  const label = document.createElement('span');
  label.className = 'theme-card-label';
  label.textContent = themeLabel;
  card.appendChild(preview);
  card.appendChild(label);
  card.addEventListener('click', () => {
    applyThemeSelection(themeName);
  });
  return card;
}

function renderThemeSelectionOptions() {
  if (!themeSelect || themeSelect.dataset.wired === '1') return;
  const themes = [..._getThemeThemes()].sort(_compareThemeEntries);
  themeSelect.innerHTML = '';
  if (!themes.length) {
    const empty = document.createElement('div');
    empty.className = 'theme-picker-empty';
    empty.textContent = 'No themes available';
    themeSelect.appendChild(empty);
    themeSelect.dataset.wired = '1';
    return;
  }
  const groupCounts = themes.reduce((counts, theme) => {
    const themeGroup = _themeEntryGroup(theme);
    counts[themeGroup] = (counts[themeGroup] || 0) + 1;
    return counts;
  }, {});
  const maxColumns = Math.max(1, ...Object.values(groupCounts));
  const desktopColumns = Math.max(1, Math.min(maxColumns, 2));
  themeSelect.style.setProperty('--theme-picker-columns', String(desktopColumns));
  const mobileColumns = Math.max(1, Math.min(maxColumns, 2));
  themeSelect.style.setProperty('--theme-picker-columns-mobile', String(mobileColumns));
  let currentGroup = null;
  let groupSection = null;
  let groupGrid = null;
  themes.forEach(theme => {
    const themeGroup = _themeEntryGroup(theme);
    if (themeGroup !== currentGroup) {
      currentGroup = themeGroup;
      groupSection = document.createElement('section');
      groupSection.className = 'theme-picker-group';
      groupSection.dataset.themeGroup = themeGroup;
      const groupTitle = document.createElement('div');
      groupTitle.className = 'theme-picker-group-title';
      groupTitle.textContent = themeGroup;
      groupGrid = document.createElement('div');
      groupGrid.className = 'theme-picker-group-grid';
      groupSection.appendChild(groupTitle);
      groupSection.appendChild(groupGrid);
      themeSelect.appendChild(groupSection);
    }
    if (groupGrid) groupGrid.appendChild(_buildThemePreviewCard(theme));
  });
  themeSelect.dataset.wired = '1';
}

function syncThemeSelectionControls() {
  const current = _resolveThemeEntry(document.body?.dataset?.theme || _savedThemeName());
  const themeName = current?.name || '';
  if (!themeSelect) return;
  themeSelect.dataset.theme = themeName;
  themeSelect.querySelectorAll('[data-theme-name]').forEach(card => {
    const active = card.dataset.themeName === themeName;
    card.classList.toggle('theme-card-active', active);
    card.classList.toggle('is-selected-card', active);
    card.setAttribute('aria-pressed', active ? 'true' : 'false');
  });
}

function applyThemeSelection(themeName, persist = true) {
  // Theme preview uses the same resolved-entry path as persisted selection, so
  // the drawer/modal never shows a palette the runtime cannot actually apply.
  const entry = _resolveThemeEntry(themeName);
  if (!entry) return;
  if (document.body) document.body.dataset.theme = entry.name;
  _applyThemeVars(entry);
  if (typeof window !== 'undefined') {
    const registry = _getThemeRegistry();
    registry.current = entry;
    window.ThemeRegistry = registry;
    if (window.ThemeCssVars && typeof window.ThemeCssVars === 'object') {
      window.ThemeCssVars.current = entry.vars || {};
    }
  }
  if (persist) _persistThemeEntry(entry);
  syncThemeSelectionControls();
}

// ── Timestamps ──
const _tsModes  = ['off', 'elapsed', 'clock'];
const _tsLabels = { off: 'timestamps: off', elapsed: 'timestamps: elapsed', clock: 'timestamps: clock' };

function _setTsMode(mode) {
  // Timestamp mode is expressed via body classes so both active transcript
  // rendering and exported/permalink views can share the same styling model.
  tsMode = mode;
  document.body.classList.remove('ts-elapsed', 'ts-clock');
  if (mode === 'elapsed') document.body.classList.add('ts-elapsed');
  if (mode === 'clock')   document.body.classList.add('ts-clock');
  const label = _tsLabels[mode];
  if (tsBtn) { tsBtn.textContent = label; tsBtn.classList.toggle('active', mode !== 'off'); }
  if (typeof syncOutputPrefixes === 'function') syncOutputPrefixes();
  try { _refreshFollowingOutputsAfterLayout(); } catch (_) {}
}

let allowedCommandsFaqData = null;

function _buildFaqLimitsContent(cfg) {
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
      label: 'Permalink & history retention',
      value: retention > 0
        ? `<strong>${retention} day${retention === 1 ? '' : 's'}</strong> — run history and share links are deleted after this period`
        : '<strong>Unlimited</strong> — run history and share links are kept indefinitely',
    },
  ];

  const frag = document.createDocumentFragment();
  const list = document.createElement('div');
  list.className = 'faq-limits-list';
  rows.forEach(r => {
    const row = document.createElement('div');
    row.className = 'faq-limits-row';

    const labelEl = document.createElement('div');
    labelEl.className = 'faq-limits-label';
    labelEl.textContent = r.label;

    const valueEl = document.createElement('div');
    valueEl.className = 'faq-limits-value';
    valueEl.innerHTML = r.value;

    row.appendChild(labelEl);
    row.appendChild(valueEl);
    list.appendChild(row);
  });
  frag.appendChild(list);
  return frag;
}

function renderFaqLimits(cfg) {
  const limitsEl = document.getElementById('faq-limits-text');
  if (!limitsEl || !cfg) return;
  limitsEl.replaceChildren(_buildFaqLimitsContent(cfg));
}

function activateFaqCommandChip(cmd) {
  if (!cmd) return;
  setComposerValue(cmd + ' ');
  _closeMajorOverlays();
  refocusComposerAfterAction({ defer: true });
}

function wireFaqCommandChips(root = faqBody) {
  if (!root) return;
  root.querySelectorAll('.faq-chip[data-faq-command]').forEach(chip => {
    if (chip.dataset.faqWired === '1') return;
    chip.dataset.faqWired = '1';
    chip.addEventListener('click', () => {
      activateFaqCommandChip(chip.dataset.faqCommand || '');
    });
    chip.addEventListener('keydown', e => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      e.preventDefault();
      activateFaqCommandChip(chip.dataset.faqCommand || '');
    });
  });
}

function makeAllowedCommandChip(cmd) {
  const chip = document.createElement('span');
  chip.className = 'allowed-chip faq-chip';
  chip.textContent = cmd;
  chip.title = 'Click to load into prompt';
  chip.dataset.faqCommand = cmd;
  return chip;
}

function renderAllowedCommandsFaq(data) {
  const el = document.getElementById('faq-allowed-text');
  if (!el || !data) return;
  if (!data.restricted) {
    el.textContent = 'No restrictions are configured — all commands are permitted.';
    return;
  }

  el.replaceChildren();
  const intro = document.createElement('div');
  intro.className = 'allowed-intro';
  intro.textContent = 'Click any command to load it into the prompt:';
  el.appendChild(intro);
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
    wireFaqCommandChips(el);
    return;
  }

  const list = document.createElement('div');
  list.className = 'allowed-list';
  data.commands.forEach(cmd => list.appendChild(makeAllowedCommandChip(cmd)));
  el.appendChild(list);
  wireFaqCommandChips(el);
}

function renderFaqItems(items) {
  // FAQ content is backend-driven so operators can extend it, but chips and
  // special UI sections are still wired client-side after the HTML is inserted.
  if (!faqBody) return;
  faqBody.innerHTML = '';
  const faqHandles = [];
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

    q.setAttribute('role', 'button');
    q.setAttribute('tabindex', '0');
    // FAQ question is a disclosure trigger. role="button" divs never receive
    // DOM focus from click, so the pressable's blur is a no-op — the
    // disclosure helper inherits clearPressStyle to punch through sticky
    // :hover highlights.
    faqHandles.push(bindDisclosure(q, {
      panel: div,
      openClass: 'faq-open',
      clearPressStyle: true,
    }));

    div.appendChild(q);
    div.appendChild(a);
    faqBody.appendChild(div);
  });

  if (faqHandles[0]) faqHandles[0].open();

  renderAllowedCommandsFaq(allowedCommandsFaqData);
  renderFaqLimits(APP_CONFIG);
  wireFaqCommandChips(faqBody);
}

function renderWorkflowItems(items) {
  const body = document.querySelector('.workflows-body');
  if (!body) return;
  body.innerHTML = '';
  (items || []).forEach(item => {
    const card = document.createElement('div');
    card.className = 'workflow-card';

    const titleEl = document.createElement('div');
    titleEl.className = 'workflow-title';
    titleEl.textContent = item.title || '';
    card.appendChild(titleEl);

    if (item.description) {
      const desc = document.createElement('div');
      desc.className = 'workflow-desc';
      desc.textContent = item.description;
      card.appendChild(desc);
    }

    const steps = item.steps || [];
    if (steps.length) {
      const stepsEl = document.createElement('ol');
      stepsEl.className = 'workflow-steps';
      steps.forEach(step => {
        const li = document.createElement('li');
        li.className = 'workflow-step';

        const main = document.createElement('div');
        main.className = 'workflow-step-main';

        const chip = document.createElement('span');
        chip.className = 'allowed-chip faq-chip workflow-step-cmd';
        chip.textContent = step.cmd || '';
        chip.title = 'Click to load into prompt';
        chip.dataset.faqCommand = step.cmd || '';
        main.appendChild(chip);

        const runBtn = document.createElement('button');
        runBtn.type = 'button';
        runBtn.className = 'btn btn-ghost btn-compact btn-icon-only workflow-step-run';
        runBtn.textContent = '▶';
        runBtn.title = 'Run this step';
        runBtn.setAttribute('aria-label', `Run: ${step.cmd || ''}`);
        runBtn.dataset.workflowStepCmd = step.cmd || '';
        main.appendChild(runBtn);

        li.appendChild(main);

        if (step.note) {
          const note = document.createElement('span');
          note.className = 'workflow-step-note';
          note.textContent = step.note;
          li.appendChild(note);
        }

        stepsEl.appendChild(li);
      });
      card.appendChild(stepsEl);
    }

    body.appendChild(card);
  });

  wireFaqCommandChips(body);
  wireWorkflowStepRunButtons(body);
}

function activateWorkflowStepRun(cmd) {
  if (!cmd) return;
  _closeMajorOverlays();
  if (typeof submitComposerCommand === 'function') {
    submitComposerCommand(cmd, { dismissKeyboard: true });
  }
}

function wireWorkflowStepRunButtons(root) {
  if (!root || typeof bindPressable !== 'function') return;
  root.querySelectorAll('.workflow-step-run[data-workflow-step-cmd]').forEach(btn => {
    bindPressable(btn, {
      onActivate: () => activateWorkflowStepRun(btn.dataset.workflowStepCmd || ''),
    });
  });
}
