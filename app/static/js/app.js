// ── Desktop UI module ──
// Shared helpers for keyboard shortcuts, overlays, and mobile-layout glue.

const _defaultDesktopPromptLabel = (() => {
  if (typeof shellPromptWrap === 'undefined' || !shellPromptWrap) return '';
  return String(shellPromptWrap.querySelector('.prompt-prefix')?.textContent || '');
})();
const _defaultMobilePromptLabel = (() => {
  if (typeof mobileComposerRow === 'undefined' || !mobileComposerRow) return '$';
  return String(mobileComposerRow.querySelector('.mobile-prompt-label')?.textContent || '$');
})();
let _composerPromptMode = null;

function _applyComposerPromptMode() {
  const isConfirm = _composerPromptMode === 'confirm';
  const desktopLabel = isConfirm ? '[yes/no]:' : _defaultDesktopPromptLabel;
  const mobileLabel = isConfirm ? '[yes/no]:' : _defaultMobilePromptLabel;
  const promptPrefix = typeof shellPromptWrap !== 'undefined' && shellPromptWrap
    ? shellPromptWrap.querySelector('.prompt-prefix')
    : null;
  if (promptPrefix) promptPrefix.textContent = desktopLabel;
  if (typeof shellPromptWrap !== 'undefined' && shellPromptWrap) {
    shellPromptWrap.classList.toggle('shell-prompt-confirm', isConfirm);
  }
  const mobilePromptLabel = typeof mobileComposerRow !== 'undefined' && mobileComposerRow
    ? mobileComposerRow.querySelector('.mobile-prompt-label')
    : null;
  if (mobilePromptLabel) mobilePromptLabel.textContent = mobileLabel;
}

function setComposerPromptMode(mode = null) {
  _composerPromptMode = mode === 'confirm' ? 'confirm' : null;
  _applyComposerPromptMode();
}

function syncShellPrompt() {
  // The visible prompt is rendered from shared composer state instead of from
  // the hidden input directly, so selection/caret state stays correct across
  // desktop/mobile and while welcome owns the tab.
  if (typeof shellPromptText === 'undefined' || !shellPromptText) return;
  if (
    typeof document !== 'undefined'
    && typeof syncFocusedComposerState === 'function'
    && typeof getComposerInputs === 'function'
  ) {
    const { desktop, mobile } = getComposerInputs();
    const active = document.activeElement;
    if (active && (active === desktop || active === mobile)) syncFocusedComposerState(active);
  }
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
const _workspaceOverlayHomeParent = typeof workspaceOverlay !== 'undefined' && workspaceOverlay ? workspaceOverlay.parentElement : null;
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
  if (!shellRoot && !composerHost && !composerRow) return null;
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
    },
  };
}

// These refs let the same DOM nodes move between the desktop document flow and
// the simplified mobile shell without duplicating markup or event handlers.
const _mobileUiLayoutRefs = _getMobileUiLayoutRefs();
const _workspaceOverlayEl = typeof workspaceOverlay !== 'undefined' && workspaceOverlay ? workspaceOverlay : null;
const _uiOverlayRefs = {
  mobileMenu: mobileMenu || null,
  hamburgerBtn: hamburgerBtn || null,
  workflowsOverlay: typeof workflowsOverlay !== 'undefined' && workflowsOverlay ? workflowsOverlay : null,
  workspaceOverlay: _workspaceOverlayEl,
  faqOverlay: typeof faqOverlay !== 'undefined' && faqOverlay ? faqOverlay : null,
  themeOverlay: typeof themeOverlay !== 'undefined' && themeOverlay ? themeOverlay : null,
  optionsOverlay: typeof optionsOverlay !== 'undefined' && optionsOverlay ? optionsOverlay : null,
  historyPanel: typeof historyPanel !== 'undefined' && historyPanel ? historyPanel : null,
};

function _bindMobileComposerInteractions(uiRefs) {
  const composerRefs = uiRefs && uiRefs.composer;
  if (!composerRefs || !composerRefs.host || !cmdInput) return;
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
  { node: optionsOverlay, homeParent: _optionsOverlayHomeParent, desktopAnchor: _workspaceOverlayEl || workflowsOverlay || null },
  { node: _workspaceOverlayEl, homeParent: _workspaceOverlayHomeParent, desktopAnchor: workflowsOverlay || null },
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
const _sessionPreferenceKeys = [
  'pref_theme_name',
  'pref_timestamps',
  'pref_line_numbers',
  'pref_welcome_intro',
  'pref_share_redaction_default',
  'pref_run_notify',
  'pref_hud_clock',
];
let _sessionPreferenceOverrides = null;
if (typeof window !== 'undefined') {
  window.__sessionPreferencesLoadState = 'idle';
}

function getPreferenceCookie(name) {
  const prefix = `${name}=`;
  return document.cookie.split(';').map(part => part.trim()).find(part => part.startsWith(prefix))
    ?.slice(prefix.length) || '';
}

function setPreferenceCookie(name, value) {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${PREF_COOKIE_MAX_AGE}; SameSite=Lax`;
}

function _primePreferenceValue(name, value) {
  setPreferenceCookie(name, value);
  if (_sessionPreferenceOverrides && Object.prototype.hasOwnProperty.call(_sessionPreferenceOverrides, name)) {
    _sessionPreferenceOverrides[name] = value;
  }
}

function getPreference(name) {
  if (_sessionPreferenceOverrides && Object.prototype.hasOwnProperty.call(_sessionPreferenceOverrides, name)) {
    return _sessionPreferenceOverrides[name];
  }
  const value = getPreferenceCookie(name);
  return value ? decodeURIComponent(value) : '';
}

function _defaultSessionPreferences() {
  const defaultTheme = _defaultThemeEntry?.()?.name || APP_CONFIG.default_theme || 'darklab_obsidian.yaml';
  return {
    pref_theme_name: defaultTheme,
    pref_timestamps: 'off',
    pref_line_numbers: 'off',
    pref_welcome_intro: 'animated',
    pref_share_redaction_default: 'unset',
    pref_run_notify: 'off',
    pref_hud_clock: 'utc',
  };
}

function _normalizeSessionPreferences(raw) {
  const defaults = _defaultSessionPreferences();
  const prefs = { ...defaults };
  const source = (raw && typeof raw === 'object') ? raw : {};
  if (typeof source.pref_theme_name === 'string' && source.pref_theme_name.trim()) {
    prefs.pref_theme_name = source.pref_theme_name.trim();
  }
  if (_tsModes.includes(source.pref_timestamps)) prefs.pref_timestamps = source.pref_timestamps;
  if (source.pref_line_numbers === 'on' || source.pref_line_numbers === 'off') {
    prefs.pref_line_numbers = source.pref_line_numbers;
  }
  if (_welcomeIntroModes.includes(source.pref_welcome_intro)) {
    prefs.pref_welcome_intro = source.pref_welcome_intro;
  }
  if (_shareRedactionDefaultModes.includes(source.pref_share_redaction_default)) {
    prefs.pref_share_redaction_default = source.pref_share_redaction_default;
  }
  if (source.pref_run_notify === 'on' || source.pref_run_notify === 'off') {
    prefs.pref_run_notify = source.pref_run_notify;
  }
  if (_hudClockModes.includes(source.pref_hud_clock)) {
    prefs.pref_hud_clock = source.pref_hud_clock;
  }
  return prefs;
}

function _sessionPreferenceCacheKey(sessionId = SESSION_ID) {
  return `session_pref_cache:${sessionId || ''}`;
}

function _readCachedSessionPreferences(sessionId = SESSION_ID) {
  try {
    const raw = localStorage.getItem(_sessionPreferenceCacheKey(sessionId));
    if (!raw) return null;
    return _normalizeSessionPreferences(JSON.parse(raw));
  } catch (_) {
    return null;
  }
}

function _cacheSessionPreferences(prefs, sessionId = SESSION_ID) {
  try {
    localStorage.setItem(_sessionPreferenceCacheKey(sessionId), JSON.stringify(prefs));
  } catch (_) {}
}

function _writePreferenceSnapshotToStorage(prefs, { writeThemeToLocalStorage = true } = {}) {
  _sessionPreferenceKeys.forEach((key) => {
    if (Object.prototype.hasOwnProperty.call(prefs, key)) {
      setPreferenceCookie(key, prefs[key]);
    }
  });
  if (writeThemeToLocalStorage && prefs.pref_theme_name) {
    localStorage.setItem('theme', prefs.pref_theme_name);
  }
}

function _buildCurrentSessionPreferenceSnapshot() {
  const defaultTheme = _defaultThemeEntry?.()?.name || APP_CONFIG.default_theme || 'darklab_obsidian.yaml';
  const currentThemeName = (document.body && document.body.dataset && document.body.dataset.theme)
    || _savedThemeName()
    || defaultTheme;
  return _normalizeSessionPreferences({
    pref_theme_name: currentThemeName,
    pref_timestamps: typeof tsMode === 'string' ? tsMode : 'off',
    pref_line_numbers: typeof lnMode === 'string' ? lnMode : 'off',
    pref_welcome_intro: getWelcomeIntroPreference(),
    pref_share_redaction_default: getShareRedactionDefaultPreference(),
    pref_run_notify: getRunNotifyPreference(),
    pref_hud_clock: getHudClockPreference(),
  });
}

async function _persistCurrentSessionPreferences() {
  const prefs = _buildCurrentSessionPreferenceSnapshot();
  _sessionPreferenceOverrides = prefs;
  _writePreferenceSnapshotToStorage(prefs, { writeThemeToLocalStorage: false });
  _cacheSessionPreferences(prefs);
  const resp = await apiFetch('/session/preferences', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ preferences: prefs }),
  });
  if (resp && resp.ok === false) {
    let detail = '';
    try {
      const data = await resp.json();
      detail = data && data.error ? `: ${data.error}` : '';
    } catch (_) {}
    throw new Error(`failed to save session preferences${detail}`);
  }
  return prefs;
}

async function loadSessionPreferences() {
  if (typeof window !== 'undefined') {
    window.__sessionPreferencesLoadState = 'pending';
  }
  try {
    const sessionId = (typeof SESSION_ID === 'string' && SESSION_ID.trim()) ? SESSION_ID.trim() : '';
    const defaults = _defaultSessionPreferences();
    const localFallback = sessionId && !sessionId.startsWith('tok_')
      ? _normalizeSessionPreferences(_buildCurrentSessionPreferenceSnapshot())
      : null;
    let prefs = null;
    try {
      const resp = await apiFetch('/session/preferences');
      if (resp && resp.ok === false) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const remote = _normalizeSessionPreferences(data && data.preferences);
      if (data && data.preferences && Object.keys(data.preferences).length) {
        prefs = remote;
      }
    } catch (err) {
      logClientError('failed to load /session/preferences', err);
    }
    if (!prefs) prefs = _readCachedSessionPreferences(sessionId);
    if (!prefs) prefs = localFallback;
    if (!prefs) prefs = defaults;
    _sessionPreferenceOverrides = prefs;
    _writePreferenceSnapshotToStorage(prefs);
    _cacheSessionPreferences(prefs, sessionId);
    applyThemePreference(prefs.pref_theme_name, false);
    applyTimestampPreference(prefs.pref_timestamps, false);
    applyLineNumberPreference(prefs.pref_line_numbers, false);
    applyWelcomeIntroPreference(prefs.pref_welcome_intro, false);
    applyShareRedactionDefaultPreference(prefs.pref_share_redaction_default, false);
    applyHudClockPreference(prefs.pref_hud_clock, false);
    if (typeof applyRunNotifyPreference === 'function') {
      await applyRunNotifyPreference(prefs.pref_run_notify, false);
    }
    syncOptionsControls();
    return prefs;
  } finally {
    if (typeof window !== 'undefined') {
      window.__sessionPreferencesLoadState = 'settled';
    }
  }
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
  if (persist && nextMode === 'on') {
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
  if (persist) {
    _primePreferenceValue('pref_run_notify', nextMode);
    try { await _persistCurrentSessionPreferences(); } catch (err) { logClientError('failed to persist run notify preference', err); }
  } else {
    _primePreferenceValue('pref_run_notify', nextMode);
  }
  syncOptionsControls();
}

function applyHudClockPreference(mode, persist = true) {
  const nextMode = _hudClockModes.includes(mode) ? mode : 'utc';
  if (persist) {
    _primePreferenceValue('pref_hud_clock', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { logClientError('failed to persist HUD clock preference', err); }
  }
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
  if (typeof syncAppSelect === 'function') {
    syncAppSelect(optionsTsSelect);
    syncAppSelect(optionsWelcomeSelect);
    syncAppSelect(optionsShareRedactionSelect);
    syncAppSelect(optionsHudClockSelect);
  }
}

function applyThemePreference(theme, persist = true) {
  applyThemeSelection(theme, persist);
}

function applyTimestampPreference(mode, persist = true) {
  const nextMode = _tsModes.includes(mode) ? mode : 'off';
  _setTsMode(nextMode);
  if (persist) {
    _primePreferenceValue('pref_timestamps', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { logClientError('failed to persist timestamp preference', err); }
  }
  syncOptionsControls();
}

function applyLineNumberPreference(mode, persist = true) {
  const nextMode = mode === 'on' ? 'on' : 'off';
  _setLnMode(nextMode);
  if (persist) {
    _primePreferenceValue('pref_line_numbers', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { logClientError('failed to persist line-number preference', err); }
  }
  syncOptionsControls();
}

function applyWelcomeIntroPreference(mode, persist = true) {
  const nextMode = _welcomeIntroModes.includes(mode) ? mode : 'animated';
  if (persist) {
    _primePreferenceValue('pref_welcome_intro', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { logClientError('failed to persist welcome-intro preference', err); }
  }
  syncOptionsControls();
}

function applyShareRedactionDefaultPreference(mode, persist = true) {
  const nextMode = _shareRedactionDefaultModes.includes(mode) ? mode : 'unset';
  if (persist) {
    _primePreferenceValue('pref_share_redaction_default', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { logClientError('failed to persist share-redaction preference', err); }
  }
  syncOptionsControls();
}

function _closeMajorOverlays() {
  if (isHistoryPanelOpen()) hideHistoryPanel();
  if (isWorkflowsOverlayOpen()) {
    if (typeof closeWorkflows === 'function') closeWorkflows();
    else hideWorkflowsOverlay();
  }
  if (typeof isWorkspaceOverlayOpen === 'function' && isWorkspaceOverlayOpen()) {
    if (typeof closeWorkspace === 'function') closeWorkspace();
    else hideWorkspaceOverlay();
  }
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
  if (typeof createDefaultTabLabel === 'function') return createDefaultTabLabel();
  return 'shell ' + (tabs.length + 1);
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
    signals: Array.isArray(line && line.signals)
      ? line.signals.map(signal => String(signal || '')).filter(Boolean)
      : [],
    line_index: Number.isInteger(line && line.line_index) ? line.line_index : undefined,
    command_root: String(line && line.command_root || ''),
    target: String(line && line.target || ''),
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
      commandHistory: Array.isArray(tab.commandHistory)
        ? tab.commandHistory.map(cmd => String(cmd || '')).filter(Boolean)
        : [],
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
      const label = String(item && item.label || (
        typeof createDefaultTabLabel === 'function' ? createDefaultTabLabel(index + 1) : `shell ${index + 1}`
      ));
      const tabId = typeof createTab === 'function' ? createTab(label) : null;
      if (!tabId) return;
      const tab = typeof getTab === 'function' ? getTab(tabId) : null;
      if (!tab) return;
      tab.command = String(item && item.command || '');
      tab.renamed = !!(item && item.renamed);
      tab.draftInput = String(item && item.draftInput || '');
      tab.commandHistory = Array.isArray(item && item.commandHistory)
        ? item.commandHistory.map(cmd => String(cmd || '')).filter(Boolean)
        : [];
      tab.historyNavIndex = -1;
      tab.historyNavDraft = '';
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
      tab.commandHistory = Array.isArray(item && item.commandHistory)
        ? item.commandHistory.map(cmd => String(cmd || '')).filter(Boolean)
        : [];
      tab.historyNavIndex = -1;
      tab.historyNavDraft = '';
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
    if (typeof _restoreOutputTailAfterLayout === 'function'
      && typeof getOutput === 'function'
      && typeof getTab === 'function') {
      const activeTab = getTab(restoredIds[activeIndex]);
      const activeOutput = getOutput(restoredIds[activeIndex]);
      _restoreOutputTailAfterLayout(activeOutput, activeTab);
    }
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
  if (e.shiftKey && e.key === 'ArrowRight') {
    activateRelativeTab(1);
    e.preventDefault();
    return true;
  }
  if (e.shiftKey && e.key === 'ArrowLeft') {
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

// Desktop chrome shortcuts (rail, search, history, options, theme, workflows,
// Files, and Run Monitor).
// The composer is allowed to pass through so prompt-focused users can still
// trigger chrome toggles — each branch calls preventDefault so Option-glyphs
// (`«`, `˙`, `®`, `©`, `≤`, `ˇ`, `ß`) never leak into the prompt on macOS.
// Other editable targets (modal inputs, search field, options textarea)
// remain gated so typing isn't hijacked.
//
// Search is bound to Alt+S (not Alt+F) because the composer owns Alt+F as
// readline word-forward; binding search to Alt+F would either hijack that
// or require a context-dependent chord that's a net UX loss. Alt+S has no
// readline conflict and works identically from everywhere.
//
// Each chord toggles its surface directly so the shortcut behavior stays in
// sync with the current rail/menu surfaces.
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
  if (e.shiftKey && eventMatchesLetter(e, 'f')) {
    if (typeof openWorkspace === 'function') openWorkspace();
    e.preventDefault();
    return true;
  }
  // All remaining chrome chords are shift-free.
  if (e.shiftKey) return false;
  if (eventMatchesLetter(e, 'r')) {
    if (typeof openRunMonitor === 'function') void openRunMonitor({ source: 'shortcut' });
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, 'h')) {
    if (typeof isHistoryPanelOpen === 'function' && isHistoryPanelOpen()) {
      hideHistoryPanel();
    } else {
      if (typeof toggleHistoryPanelSurface === 'function') toggleHistoryPanelSurface(true);
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

function moveCmdCaretByWord(direction) {
  const input = typeof getVisibleComposerInput === 'function' ? getVisibleComposerInput() : cmdInput;
  if (typeof syncFocusedComposerState === 'function') syncFocusedComposerState(input);
  const value = typeof getComposerValue === 'function' ? getComposerValue() : (cmdInput.value || '');
  const { start, end } = getCmdSelection(value);
  const next = direction < 0
    ? findWordBoundaryLeft(value, start)
    : findWordBoundaryRight(value, end);
  if (typeof syncComposerSelection === 'function') syncComposerSelection(next, next, { input });
  if (input && typeof input.setSelectionRange === 'function' && input.selectionStart !== next) {
    input.setSelectionRange(next, next);
  } else if (!input && cmdInput && typeof cmdInput.setSelectionRange === 'function') {
    cmdInput.setSelectionRange(next, next);
  }
  syncShellPrompt();
}

function handleComposerWordArrowShortcut(e) {
  if (!e || !e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return false;
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return false;
  e.preventDefault();
  e.stopPropagation();
  moveCmdCaretByWord(e.key === 'ArrowLeft' ? -1 : 1);
  return true;
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
    if (typeof syncComposerSelection === 'function') syncComposerSelection(nextStart, nextEnd, { input });
    else if (input && typeof input.setSelectionRange === 'function') input.setSelectionRange(nextStart, nextEnd);
    setTimeout(() => {
      if (!input || typeof input.setSelectionRange !== 'function') return;
      if (typeof document !== 'undefined' && document.activeElement !== input) return;
      if ((input.value || '') !== value) return;
      if (input.selectionStart === nextStart && input.selectionEnd === nextEnd) return;
      input.setSelectionRange(nextStart, nextEnd);
      if (typeof setComposerState === 'function') {
        setComposerState({
          value,
          selectionStart: nextStart,
          selectionEnd: nextEnd,
          activeInput: 'mobile',
        });
      }
      syncShellPrompt();
    }, 0);
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
    if (typeof handleComposerWordArrowShortcut === 'function' && handleComposerWordArrowShortcut(e)) return;
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
  try { void _persistCurrentSessionPreferences(); } catch (err) { logClientError('failed to persist theme preference', err); }
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

  const rail = document.createElement('span');
  rail.className = 'theme-card-preview-rail';
  for (let i = 0; i < 3; i += 1) {
    const railSection = document.createElement('span');
    railSection.className = 'theme-card-preview-rail-section';
    const railHeader = document.createElement('span');
    railHeader.className = 'theme-card-preview-rail-header';
    railSection.appendChild(railHeader);
    for (let j = 0; j < 2; j += 1) {
      const railLine = document.createElement('span');
      railLine.className = 'theme-card-preview-rail-line';
      railSection.appendChild(railLine);
    }
    rail.appendChild(railSection);
  }

  const shell = document.createElement('span');
  shell.className = 'theme-card-preview-shell';

  const tabbar = document.createElement('span');
  tabbar.className = 'theme-card-preview-tabbar';
  const activeTab = document.createElement('span');
  activeTab.className = 'theme-card-preview-tab theme-card-preview-tab-active';
  const idleTab = document.createElement('span');
  idleTab.className = 'theme-card-preview-tab';
  tabbar.appendChild(activeTab);
  tabbar.appendChild(idleTab);

  const content = document.createElement('span');
  content.className = 'theme-card-preview-content';
  const prompt = document.createElement('span');
  prompt.className = 'theme-card-preview-prompt';
  prompt.textContent = (typeof APP_CONFIG !== 'undefined' && APP_CONFIG.prompt_prefix) || 'anon@darklab:~$';
  content.appendChild(prompt);
  for (let index = 0; index < 4; index += 1) {
    const line = document.createElement('span');
    line.className = 'theme-card-preview-line';
    line.style.setProperty('--theme-preview-line-width', `${86 - (index * 13)}%`);
    content.appendChild(line);
  }

  const modal = document.createElement('span');
  modal.className = 'theme-card-preview-modal';
  const modalHeader = document.createElement('span');
  modalHeader.className = 'theme-card-preview-modal-header';
  const modalBody = document.createElement('span');
  modalBody.className = 'theme-card-preview-modal-body';
  const modalActions = document.createElement('span');
  modalActions.className = 'theme-card-preview-modal-actions';
  for (let i = 0; i < 2; i += 1) {
    const modalButton = document.createElement('span');
    modalButton.className = 'theme-card-preview-modal-button';
    modalActions.appendChild(modalButton);
  }
  modal.appendChild(modalHeader);
  modal.appendChild(modalBody);
  modal.appendChild(modalActions);

  const hud = document.createElement('span');
  hud.className = 'theme-card-preview-hud';
  for (let i = 0; i < 5; i += 1) {
    const cell = document.createElement('span');
    cell.className = 'theme-card-preview-hud-cell';
    hud.appendChild(cell);
  }

  shell.appendChild(tabbar);
  shell.appendChild(content);
  shell.appendChild(modal);
  shell.appendChild(hud);
  preview.appendChild(rail);
  preview.appendChild(shell);

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

// ── Terminal-native theme/config commands ──
function _cliAppendLine(text, cls = '', tabId = null) {
  if (typeof appendLine === 'function') appendLine(text, cls, tabId);
}

function _cliShouldPreserveOutputTail(tabId = null) {
  const id = tabId || (typeof activeTabId !== 'undefined' ? activeTabId : null);
  const tab = typeof getTab === 'function' ? getTab(id) : null;
  return !!tab && tab.followOutput !== false;
}

function _cliPreserveOutputTail(tabId = null, shouldPreserve = true) {
  if (!shouldPreserve) return;
  const id = tabId || (typeof activeTabId !== 'undefined' ? activeTabId : null);
  const tab = typeof getTab === 'function' ? getTab(id) : null;
  const out = typeof getOutput === 'function' ? getOutput(id) : null;
  if (tab) tab.followOutput = true;
  if (out && typeof _stickOutputToBottom === 'function') {
    _stickOutputToBottom(out, tab);
  } else if (out) {
    out.scrollTop = out.scrollHeight;
  }
  if (typeof updateOutputFollowButton === 'function') updateOutputFollowButton(id);
}

function _cliSetStatus(statusValue) {
  if (typeof setStatus === 'function') setStatus(statusValue);
}

function _cliRecordSuccess(command) {
  if (typeof _recordSuccessfulLocalCommand === 'function') _recordSuccessfulLocalCommand(command);
}

function _cliThemeSlug(entry) {
  return _normalizeThemeName(entry?.name || entry?.filename || '');
}

function _cliThemeEntries() {
  return [..._getThemeThemes()].sort(_compareThemeEntries).filter(entry => _cliThemeSlug(entry));
}

function _cliThemeColorScheme(entry) {
  const scheme = String(entry?.color_scheme || '').trim().toLowerCase();
  if (scheme === 'light' || scheme === 'only light') return 'light';
  if (scheme === 'dark' || scheme === 'only dark') return 'dark';
  return 'other';
}

function _cliThemeColorSchemeLabel(scheme) {
  if (scheme === 'light') return 'Light themes:';
  if (scheme === 'dark') return 'Dark themes:';
  return 'Other themes:';
}

function _cliThemeEntriesByColorScheme() {
  const grouped = { dark: [], light: [], other: [] };
  _cliThemeEntries().forEach((entry) => {
    grouped[_cliThemeColorScheme(entry)].push(entry);
  });
  return grouped;
}

function _cliCurrentThemeEntry() {
  return _resolveThemeEntry(document.body?.dataset?.theme || _savedThemeName());
}

function _cliCurrentThemeSlug() {
  return _cliThemeSlug(_cliCurrentThemeEntry());
}

function _formatCliRecord(key, value, width = 18) {
  return `${key.padEnd(width)}  ${value}`;
}

function _cliThemeDescription(entry) {
  const label = String(entry?.label || entry?.name || '').trim();
  const slug = _cliThemeSlug(entry);
  const current = slug && slug === _cliCurrentThemeSlug();
  return `${label || slug}${current ? ' (current)' : ''}`;
}

async function handleThemeCommand(cmd, tabId = null) {
  const parts = String(cmd || '').trim().split(/\s+/).filter(Boolean);
  const sub = (parts[1] || '').toLowerCase();
  if (typeof appendCommandEcho === 'function') appendCommandEcho(cmd, tabId);

  if (parts.length === 1 || sub === 'list') {
    const current = _cliCurrentThemeEntry();
    _cliAppendLine(_formatCliRecord('current theme', _cliThemeDescription(current)), 'fake-kv', tabId);
    _cliAppendLine('', 'fake-spacer', tabId);
    _cliAppendLine('Available themes:', 'fake-section', tabId);
    const grouped = _cliThemeEntriesByColorScheme();
    ['dark', 'light', 'other'].forEach((scheme) => {
      const entries = grouped[scheme] || [];
      if (!entries.length) return;
      _cliAppendLine(_cliThemeColorSchemeLabel(scheme), 'fake-section', tabId);
      entries.forEach((entry) => {
        const slug = _cliThemeSlug(entry);
        const marker = slug === _cliCurrentThemeSlug() ? '*' : ' ';
        _cliAppendLine(`  ${marker} ${slug.padEnd(24)}  ${String(entry.label || slug)}`, 'fake-help-row', tabId);
      });
    });
    _cliRecordSuccess(cmd);
    _cliSetStatus('ok');
    return true;
  }

  if (sub === 'current') {
    _cliAppendLine(_formatCliRecord('current theme', _cliThemeDescription(_cliCurrentThemeEntry())), 'fake-kv', tabId);
    _cliRecordSuccess(cmd);
    _cliSetStatus('ok');
    return true;
  }

  const requested = sub === 'set' ? parts.slice(2).join(' ').trim() : '';
  if (!requested) {
    _cliAppendLine('usage: theme [list | current | set <theme>]', '', tabId);
    _cliSetStatus('fail');
    return true;
  }

  const entry = _findThemeEntry(requested);
  if (!entry) {
    _cliAppendLine(`theme: unknown theme '${requested}'`, 'exit-fail', tabId);
    _cliAppendLine("run 'theme list' to see available themes", '', tabId);
    _cliSetStatus('fail');
    return true;
  }

  applyThemeSelection(entry.name);
  _cliAppendLine(`theme set: ${_cliThemeDescription(entry)}`, '', tabId);
  _cliRecordSuccess(cmd);
  _cliSetStatus('ok');
  return true;
}

const _cliConfigValueLabels = {
  animated: 'animated',
  static: 'static',
  off: 'off',
  ask: 'ask',
};

function _cliNormalizeValue(value) {
  return String(value || '').trim().toLowerCase().replace(/_/g, '-');
}

function _cliConfigEntries() {
  return [
    {
      key: 'line-numbers',
      description: 'Show line numbers beside output and the live prompt',
      values: ['on', 'off'],
      get: () => (typeof lnMode === 'string' && lnMode === 'on' ? 'on' : 'off'),
      set: (value) => applyLineNumberPreference(value),
    },
    {
      key: 'timestamps',
      description: 'Timestamp display mode',
      values: _tsModes.slice(),
      get: () => (_tsModes.includes(tsMode) ? tsMode : 'off'),
      set: (value) => applyTimestampPreference(value),
    },
    {
      key: 'welcome',
      description: 'Welcome intro behavior',
      values: ['animated', 'static', 'off'],
      aliases: { disable_animation: 'static', disable: 'static', remove: 'off', removed: 'off' },
      toStored: { animated: 'animated', static: 'disable_animation', off: 'remove' },
      fromStored: { animated: 'animated', disable_animation: 'static', remove: 'off' },
      get: function getWelcomeCliValue() {
        return this.fromStored[getWelcomeIntroPreference()] || 'animated';
      },
      set: function setWelcomeCliValue(value) {
        applyWelcomeIntroPreference(this.toStored[value] || value);
      },
    },
    {
      key: 'share-redaction',
      description: 'Default redaction behavior for shared snapshots',
      values: ['ask', 'redacted', 'raw'],
      aliases: { unset: 'ask', prompt: 'ask', redacted: 'redacted', raw: 'raw' },
      toStored: { ask: 'unset', redacted: 'redacted', raw: 'raw' },
      fromStored: { unset: 'ask', redacted: 'redacted', raw: 'raw' },
      get: function getShareRedactionCliValue() {
        return this.fromStored[getShareRedactionDefaultPreference()] || 'ask';
      },
      set: function setShareRedactionCliValue(value) {
        applyShareRedactionDefaultPreference(this.toStored[value] || value);
      },
    },
    {
      key: 'run-notifications',
      description: 'Desktop notification when a run completes or is killed',
      values: ['on', 'off'],
      get: () => getRunNotifyPreference(),
      set: (value) => applyRunNotifyPreference(value),
    },
    {
      key: 'hud-clock',
      description: 'HUD clock timezone',
      values: _hudClockModes.slice(),
      get: () => getHudClockPreference(),
      set: (value) => applyHudClockPreference(value),
    },
  ];
}

function _findCliConfigEntry(key) {
  const normalized = _cliNormalizeValue(key);
  return _cliConfigEntries().find(entry => entry.key === normalized) || null;
}

function _normalizeCliConfigEntryValue(entry, value) {
  const normalized = _cliNormalizeValue(value);
  const aliased = entry.aliases && Object.prototype.hasOwnProperty.call(entry.aliases, normalized)
    ? entry.aliases[normalized]
    : normalized;
  return entry.values.includes(aliased) ? aliased : null;
}

function _cliConfigDisplayValue(value) {
  return _cliConfigValueLabels[value] || value;
}

function _printCliConfigEntry(entry, tabId) {
  _cliAppendLine(
    _formatCliRecord(entry.key, _cliConfigDisplayValue(entry.get()), 19),
    'fake-kv',
    tabId,
  );
}

function _printCliConfigList(tabId) {
  _cliAppendLine('Current user config:', 'fake-section', tabId);
  _cliConfigEntries().forEach(entry => _printCliConfigEntry(entry, tabId));
}

async function handleConfigCommand(cmd, tabId = null) {
  const parts = String(cmd || '').trim().split(/\s+/).filter(Boolean);
  const sub = (parts[1] || '').toLowerCase();
  const preserveTail = _cliShouldPreserveOutputTail(tabId);
  if (typeof appendCommandEcho === 'function') appendCommandEcho(cmd, tabId);

  if (parts.length === 1 || sub === 'list') {
    _printCliConfigList(tabId);
    _cliRecordSuccess(cmd);
    _cliSetStatus('ok');
    return true;
  }

  if (sub === 'get') {
    const key = parts[2] || '';
    const entry = _findCliConfigEntry(key);
    if (!entry) {
      _cliAppendLine(`config: unknown option '${key}'`, 'exit-fail', tabId);
      _cliAppendLine("run 'config list' to see available options", '', tabId);
      _cliSetStatus('fail');
      return true;
    }
    _printCliConfigEntry(entry, tabId);
    _cliRecordSuccess(cmd);
    _cliSetStatus('ok');
    return true;
  }

  const isSet = sub === 'set';
  const key = isSet ? parts[2] : '';
  const value = isSet ? parts[3] : '';
  const entry = _findCliConfigEntry(key);

  if (!entry || !value) {
    _cliAppendLine('usage: config [list | get <option> | set <option> <value>]', '', tabId);
    _cliSetStatus('fail');
    return true;
  }

  const normalizedValue = _normalizeCliConfigEntryValue(entry, value);
  if (!normalizedValue) {
    _cliAppendLine(`config: invalid value '${value}' for ${entry.key}`, 'exit-fail', tabId);
    _cliAppendLine(`allowed values: ${entry.values.join(', ')}`, '', tabId);
    _cliSetStatus('fail');
    return true;
  }

  await entry.set(normalizedValue);
  _cliAppendLine(`config set: ${entry.key}=${_cliConfigDisplayValue(entry.get())}`, '', tabId);
  _cliPreserveOutputTail(tabId, preserveTail);
  _cliRecordSuccess(cmd);
  _cliSetStatus('ok');
  return true;
}

function _runtimeHint(value, description = '', insertValue = null, label = null) {
  const item = { value, description };
  if (insertValue != null) item.insertValue = insertValue;
  if (label != null) item.label = label;
  return item;
}

function _runtimeContextSpec({
  flags = [],
  expectsValue = [],
  argHints = {},
  sequenceArgHints = {},
  argumentLimit = null,
  pipeCommand = false,
  pipeInsertValue = '',
  pipeLabel = '',
  pipeDescription = '',
  examples = [],
  closeAfter = {},
} = {}) {
  return {
    flags,
    expects_value: expectsValue,
    arg_hints: argHints,
    sequence_arg_hints: sequenceArgHints,
    argument_limit: argumentLimit,
    pipe_command: pipeCommand,
    pipe_insert_value: pipeInsertValue,
    pipe_label: pipeLabel,
    pipe_description: pipeDescription,
    examples,
    close_after: closeAfter,
  };
}

function isWorkspaceFeatureEnabled() {
  return !!(typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.workspace_enabled === true);
}

function _runtimeSpecEnabledForFeatures(root, spec) {
  const featureRequired = spec && spec.feature_required;
  const features = Array.isArray(featureRequired) ? featureRequired : [featureRequired];
  if (features.some(feature => String(feature || '').toLowerCase() === 'workspace')) {
    return isWorkspaceFeatureEnabled();
  }
  return !['file', 'cat', 'ls', 'rm'].includes(String(root || '').toLowerCase()) || isWorkspaceFeatureEnabled();
}

function _cloneRuntimeSpec(spec) {
  if (!spec || typeof spec !== 'object') return _runtimeContextSpec();
  try {
    return JSON.parse(JSON.stringify(spec));
  } catch (err) {
    return _runtimeContextSpec();
  }
}

function _runtimeMergeHints(baseHints = {}, overlayHints = {}) {
  const merged = Object.assign({}, baseHints || {});
  Object.entries(overlayHints || {}).forEach(([trigger, hints]) => {
    const bucket = Array.isArray(merged[trigger]) ? merged[trigger].slice() : [];
    const seen = new Set(bucket.map(item => String(item && item.value || '').toLowerCase()));
    (hints || []).forEach((hint) => {
      const value = String(hint && hint.value || '');
      const key = value.toLowerCase();
      if (!value || seen.has(key)) return;
      seen.add(key);
      bucket.push(hint);
    });
    merged[trigger] = bucket;
  });
  return merged;
}

function _runtimeMergeContextSpec(baseSpec = {}, overlaySpec = {}) {
  const merged = _cloneRuntimeSpec(baseSpec);
  const appendItems = (key) => {
    const bucket = Array.isArray(merged[key]) ? merged[key] : [];
    const seen = new Set(bucket.map(item => String(item && item.value != null ? item.value : item).toLowerCase()));
    (overlaySpec[key] || []).forEach((item) => {
      const raw = item && item.value != null ? item.value : item;
      const value = String(raw || '');
      const lookup = value.toLowerCase();
      if (!value || seen.has(lookup)) return;
      seen.add(lookup);
      bucket.push(item);
    });
    merged[key] = bucket;
  };
  appendItems('flags');
  appendItems('expects_value');
  appendItems('examples');
  merged.arg_hints = _runtimeMergeHints(merged.arg_hints, overlaySpec.arg_hints);
  merged.sequence_arg_hints = _runtimeMergeHints(merged.sequence_arg_hints, overlaySpec.sequence_arg_hints);
  merged.close_after = Object.assign({}, merged.close_after || {}, overlaySpec.close_after || {});
  if (Number.isInteger(overlaySpec.argument_limit) && overlaySpec.argument_limit > 0) {
    merged.argument_limit = overlaySpec.argument_limit;
  }
  return merged;
}

function _runtimeActiveBuiltinRoots(baseRegistry = {}) {
  const roots = new Set(
    Array.isArray(acBuiltinCommandRoots) ? acBuiltinCommandRoots.map(root => String(root || '')) : [],
  );
  Object.entries(baseRegistry || {}).forEach(([root, spec]) => {
    if (spec && typeof spec === 'object' && String(spec.description || '').startsWith('built-in:')) {
      roots.add(root);
    }
  });
  return [...roots].filter(Boolean).sort();
}

function _runtimeBuiltinDescription(root, baseRegistry = {}) {
  return String(baseRegistry[root]?.description || 'built-in command');
}

function _runtimeAllowedCommandRoots() {
  const roots = new Set();
  const source = allowedCommandsFaqData && Array.isArray(allowedCommandsFaqData.commands)
    ? allowedCommandsFaqData.commands
    : [];
  source.forEach((command) => {
    const root = String(command || '').trim().split(/\s+/, 1)[0].toLowerCase();
    if (root) roots.add(root);
  });
  return roots;
}

function _runtimeCommandLookupHints(baseRegistry = {}, descriptionForExternal = 'manual page') {
  const builtinNames = new Set(
    _runtimeActiveBuiltinRoots(baseRegistry)
      .filter(root => _runtimeSpecEnabledForFeatures(root, baseRegistry[root])),
  );
  const externalRoots = new Set(
    Object.keys(baseRegistry || {})
      .filter(root => _runtimeSpecEnabledForFeatures(root, baseRegistry[root])),
  );
  _runtimeAllowedCommandRoots().forEach(root => externalRoots.add(root));
  builtinNames.forEach(root => externalRoots.delete(root));

  const items = [];
  [...externalRoots].sort().forEach(root => {
    items.push(_runtimeHint(root, `${root} ${descriptionForExternal}`));
  });
  [...builtinNames].sort().forEach(root => {
    items.push(_runtimeHint(root, _runtimeBuiltinDescription(root, baseRegistry)));
  });
  items.push(_runtimeHint('<command>', 'Any built-in or allowed command'));
  return items;
}

function _runtimeWorkspaceFileHints() {
  if (typeof getWorkspaceAutocompleteFileHints !== 'function') return [];
  return getWorkspaceAutocompleteFileHints();
}

function _runtimeWorkspaceContext() {
  const fileHints = _runtimeWorkspaceFileHints();
  return _runtimeContextSpec({
    expectsValue: ['show', 'add', 'edit', 'download', 'rm', 'delete'],
    argHints: {
      list: [],
      help: [],
      show: fileHints,
      add: [_runtimeHint('<file>', 'New session file name')],
      edit: fileHints,
      download: fileHints,
      rm: fileHints,
      delete: fileHints,
      __positional__: [
        _runtimeHint('list', 'List current session files'),
        _runtimeHint('show <file>', 'Print a session file in the terminal', 'show '),
        _runtimeHint('add <file>', 'Open the Files editor for a new session file', 'add '),
        _runtimeHint('edit <file>', 'Open the Files editor for an existing session file', 'edit '),
        _runtimeHint('download <file>', 'Download a session file through the browser', 'download '),
        _runtimeHint('delete <file>', 'Remove a session file from this session', 'delete '),
        _runtimeHint('help', 'Show file command usage'),
      ],
    },
  });
}

function _runtimeThemeContext() {
  const themeHints = _cliThemeEntries().map(entry => _runtimeHint(_cliThemeSlug(entry), _cliThemeDescription(entry)));
  const argHints = {
    list: [],
    current: [],
    set: themeHints,
    __positional__: [
      _runtimeHint('list', 'Show available themes'),
      _runtimeHint('current', 'Show the active theme'),
      _runtimeHint('set', 'Apply a theme', 'set '),
    ],
  };
  themeHints.forEach(item => { argHints[item.value] = []; });
  return _runtimeContextSpec({ expectsValue: ['set'], argHints });
}

function _runtimeConfigContext() {
  const entries = _cliConfigEntries();
  const optionHints = entries.map(entry => _runtimeHint(entry.key, entry.description));
  const argHints = {
    list: [],
    get: optionHints,
    set: optionHints,
    __positional__: [
      _runtimeHint('list', 'Show all current user config'),
      _runtimeHint('get', 'Show one user config value', 'get '),
      _runtimeHint('set', 'Set one user config value', 'set '),
    ],
  };
  const sequenceArgHints = {};
  entries.forEach((entry) => {
    sequenceArgHints[`set ${entry.key}`] = entry.values.map(value => _runtimeHint(value, entry.description));
    sequenceArgHints[`get ${entry.key}`] = [];
    entry.values.forEach(value => { argHints[value] = []; });
  });
  return _runtimeContextSpec({ expectsValue: ['get', 'set'], argHints, sequenceArgHints });
}

function _runtimeVariableHints(description = 'Session variable') {
  const variables = Array.isArray(sessionVariables) ? sessionVariables : [];
  return variables.map(variable => {
    const name = String(variable && variable.name || '').trim();
    const value = String(variable && variable.value || '').trim();
    return _runtimeHint(name, value ? `${description}: ${value}` : description);
  }).filter(item => item.value);
}

function _runtimeVarContext() {
  const variableHints = _runtimeVariableHints('Current value');
  const starterNames = ['HOST', 'PORT', 'IP_ADDR'];
  const currentNames = new Set(variableHints.map(item => String(item.value || '').toUpperCase()));
  const starterHints = starterNames
    .filter(name => !currentNames.has(name))
    .map(name => _runtimeHint(name, `Common ${name.toLowerCase()} value`));
  const sequenceArgHints = {};
  variableHints.concat(starterNames.map(name => _runtimeHint(name))).forEach(item => {
    const name = String(item && item.value || '').trim();
    if (name) {
      sequenceArgHints[`set ${name.toLowerCase()}`] = [_runtimeHint('<value>', `Value for ${name}`)];
      sequenceArgHints[`unset ${name.toLowerCase()}`] = [];
    }
  });
  const argHints = {
    list: [],
    set: variableHints.concat(starterHints),
    unset: variableHints,
    __positional__: [
      _runtimeHint('list', 'Show session variables'),
      _runtimeHint('set', 'Set a session variable', 'set '),
      _runtimeHint('unset', 'Remove a session variable', 'unset '),
    ],
  };
  return _runtimeContextSpec({
    expectsValue: ['set', 'unset'],
    argHints,
    sequenceArgHints,
    closeAfter: {
      list: 0,
      set: 2,
      unset: 1,
    },
  });
}

function getRuntimeAutocompleteContext(baseRegistry = {}) {
  const context = {};
  _runtimeActiveBuiltinRoots(baseRegistry).forEach((root) => {
    if (baseRegistry[root] && _runtimeSpecEnabledForFeatures(root, baseRegistry[root])) {
      context[root] = _cloneRuntimeSpec(baseRegistry[root]);
    }
  });
  const lookupHints = _runtimeCommandLookupHints(baseRegistry);
  context.theme = _runtimeMergeContextSpec(baseRegistry.theme, _runtimeThemeContext());
  context.config = _runtimeMergeContextSpec(baseRegistry.config, _runtimeConfigContext());
  context.var = _runtimeMergeContextSpec(baseRegistry.var, _runtimeVarContext());
  if (isWorkspaceFeatureEnabled() && baseRegistry.file) {
    context.file = _runtimeMergeContextSpec(baseRegistry.file, _runtimeWorkspaceContext());
  }
  if (isWorkspaceFeatureEnabled() && baseRegistry.cat) {
    context.cat = _runtimeMergeContextSpec(baseRegistry.cat, _runtimeContextSpec({
      argHints: { __positional__: _runtimeWorkspaceFileHints() },
    }));
  }
  if (isWorkspaceFeatureEnabled() && baseRegistry.rm) {
    context.rm = _runtimeMergeContextSpec(baseRegistry.rm, _runtimeContextSpec({
      argHints: { __positional__: _runtimeWorkspaceFileHints() },
    }));
  }
  context.man = _runtimeMergeContextSpec(baseRegistry.man, _runtimeContextSpec({
    argHints: { __positional__: lookupHints },
  }));
  context.which = _runtimeMergeContextSpec(baseRegistry.which, _runtimeContextSpec({
    argHints: { __positional__: _runtimeCommandLookupHints(baseRegistry, 'command path') },
  }));
  context.type = _runtimeMergeContextSpec(baseRegistry.type, _runtimeContextSpec({
    argHints: { __positional__: _runtimeCommandLookupHints(baseRegistry, 'command type') },
  }));
  return context;
}

function getRuntimeAutocompleteItems(ctx, buildItem, filterItems) {
  const token = String(ctx && ctx.currentToken || '');
  const dollarIndex = token.lastIndexOf('$');
  if (dollarIndex < 0 || !buildItem || !filterItems) return [];
  const afterDollar = token.slice(dollarIndex + 1);
  const braced = afterDollar.startsWith('{');
  const query = braced ? afterDollar.slice(1) : afterDollar;
  if (!/^\{?[A-Za-z_][A-Za-z0-9_]*$/.test(afterDollar) && afterDollar !== '{') return [];
  const variables = Array.isArray(sessionVariables) ? sessionVariables : [];
  const items = variables.map(variable => {
    const name = String(variable && variable.name || '').trim();
    if (!name) return null;
    const label = braced ? '${' + name + '}' : '$' + name;
    return buildItem({
      value: label,
      label,
      description: String(variable && variable.value || ''),
      replaceStart: ctx.tokenStart + dollarIndex,
      replaceEnd: ctx.tokenEnd,
      insertValue: label,
    });
  }).filter(Boolean);
  return filterItems(items, braced ? '${' + query : '$' + query);
}

async function loadSessionVariables() {
  try {
    const resp = await apiFetch('/session/variables');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    sessionVariables = Array.isArray(data.variables) ? data.variables : [];
  } catch (err) {
    logClientError('failed to load /session/variables', err);
    sessionVariables = [];
  }
  return sessionVariables;
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
  chip.className = 'allowed-chip faq-chip chip chip-action';
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

const WORKFLOW_TOKEN_RE = /{{\s*([a-z][a-z0-9_]*)\s*}}/g;
const WORKFLOW_INPUT_STATE_KEY = 'workflow_input_state_v1';
const _workflowRunQueueByTab = new Map();

function getWorkflowStorageKey(workflow) {
  const title = String(workflow?.title || '').trim();
  const description = String(workflow?.description || '').trim();
  return `${title}::${description}`;
}

function readWorkflowInputState() {
  if (typeof localStorage === 'undefined') return {};
  try {
    const raw = localStorage.getItem(WORKFLOW_INPUT_STATE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch (_err) {
    return {};
  }
}

function writeWorkflowInputState(nextState) {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(WORKFLOW_INPUT_STATE_KEY, JSON.stringify(nextState || {}));
  } catch (_err) {
    // Non-critical persistence failure; the workflow form still works in-memory.
  }
}

function loadWorkflowInputValues(workflow) {
  const base = getWorkflowInputValues(workflow);
  const state = readWorkflowInputState();
  const saved = state[getWorkflowStorageKey(workflow)];
  if (!saved || typeof saved !== 'object') return base;
  const next = { ...base };
  Object.entries(saved).forEach(([key, value]) => {
    const input = (workflow?.inputs || []).find((item) => item.id === key);
    if (!input) return;
    next[key] = sanitizeWorkflowInputValue(input, value);
  });
  return next;
}

function persistWorkflowInputValues(workflow, values) {
  const state = readWorkflowInputState();
  const nextState = { ...state };
  nextState[getWorkflowStorageKey(workflow)] = { ...(values || {}) };
  writeWorkflowInputState(nextState);
}

function sanitizeWorkflowInputValue(input, value) {
  const raw = String(value == null ? '' : value).trim();
  if (!input || !raw) return raw;
  if (input.type === 'port') return raw.replace(/[^\d]/g, '');
  return raw;
}

function getWorkflowInputValues(workflow) {
  const values = {};
  const inputs = Array.isArray(workflow?.inputs) ? workflow.inputs : [];
  inputs.forEach((input) => {
    values[input.id] = sanitizeWorkflowInputValue(input, input.default || '');
  });
  return values;
}

function renderWorkflowCommandTemplate(template, values) {
  return String(template || '').replace(WORKFLOW_TOKEN_RE, (_match, token) => values[token] || '');
}

function workflowInputsReady(workflow, values) {
  const inputs = Array.isArray(workflow?.inputs) ? workflow.inputs : [];
  return inputs.every((input) => !input.required || String(values[input.id] || '').trim().length > 0);
}

function buildRenderedWorkflow(workflow, values) {
  const renderedValues = { ...(values || {}) };
  const ready = workflowInputsReady(workflow, renderedValues);
  const steps = Array.isArray(workflow?.steps) ? workflow.steps : [];
  return {
    ready,
    steps: steps.map((step) => ({
      ...step,
      renderedCmd: renderWorkflowCommandTemplate(step.cmd || '', renderedValues).trim(),
    })),
  };
}

function runWorkflowCommands(commands) {
  const runnable = (commands || []).map((cmd) => String(cmd || '').trim()).filter(Boolean);
  if (!runnable.length) return;
  const targetTabId = typeof getActiveTabId === 'function' ? getActiveTabId() : activeTabId;
  if (!targetTabId) return;
  if (typeof welcomeOwnsTab === 'function' && welcomeOwnsTab(targetTabId)) {
    if (typeof cancelWelcome === 'function') cancelWelcome(targetTabId);
    if (typeof clearTab === 'function') clearTab(targetTabId);
    if (typeof setTabStatus === 'function') setTabStatus(targetTabId, 'idle');
  }
  _closeMajorOverlays();
  _workflowRunQueueByTab.set(targetTabId, {
    commands: runnable.slice(),
    nextIndex: 1,
    total: runnable.length,
  });
  if (typeof activateTab === 'function') activateTab(targetTabId);
  if (typeof appendLine === 'function' && runnable.length > 1) {
    appendLine(`[workflow] Running ${runnable.length} steps sequentially in this tab.`, 'notice', targetTabId);
  }
  if (typeof submitComposerCommand === 'function') {
    submitComposerCommand(runnable[0], {
      dismissKeyboard: true,
      focusAfterSubmit: true,
    });
  }
}

function _runNextWorkflowQueueStep(tabId) {
  const queue = _workflowRunQueueByTab.get(tabId);
  if (!queue) return;
  const nextCommand = queue.commands[queue.nextIndex];
  if (!nextCommand) {
    _workflowRunQueueByTab.delete(tabId);
    if (typeof appendLine === 'function') {
      appendLine('[workflow] Completed all queued steps.', 'exit-ok', tabId);
    }
    return;
  }
  queue.nextIndex += 1;
  if (typeof appendLine === 'function') {
    appendLine(`[workflow] Continuing with step ${queue.nextIndex}/${queue.total}.`, 'notice', tabId);
  }
  if (typeof activateTab === 'function') activateTab(tabId, { focusComposer: false });
  if (typeof submitComposerCommand === 'function') {
    submitComposerCommand(nextCommand, {
      dismissKeyboard: false,
      focusAfterSubmit: false,
    });
  }
}

function _scheduleNextWorkflowQueueStep(tabId) {
  const waitForFlush = () => {
    if (!_workflowRunQueueByTab.has(tabId)) return;
    if (typeof hasPendingOutputBatch === 'function' && hasPendingOutputBatch(tabId)) {
      setTimeout(waitForFlush, 20);
      return;
    }
    _runNextWorkflowQueueStep(tabId);
  };
  setTimeout(waitForFlush, 0);
}

if (typeof onUiEvent === 'function') {
  onUiEvent('app:tab-status-changed', (e) => {
    const tabId = e?.detail?.id;
    const status = e?.detail?.status;
    if (!tabId || !_workflowRunQueueByTab.has(tabId) || status === 'running') return;
    if (status === 'killed') {
      _workflowRunQueueByTab.delete(tabId);
      if (typeof appendLine === 'function') {
        appendLine('[workflow] Queue stopped because the current step was killed.', 'denied', tabId);
      }
      return;
    }
    _scheduleNextWorkflowQueueStep(tabId);
  });
}

function renderWorkflowInputCard(card, workflow) {
  const inputs = Array.isArray(workflow?.inputs) ? workflow.inputs : [];
  if (!inputs.length) return null;

  const panel = document.createElement('div');
  panel.className = 'workflow-input-panel';

  const intro = document.createElement('div');
  intro.className = 'workflow-input-intro';
  intro.textContent = 'Fill in your target to preview the exact commands before loading or running a step.';
  panel.appendChild(intro);

  const grid = document.createElement('div');
  grid.className = 'workflow-input-grid';
  panel.appendChild(grid);

  const values = loadWorkflowInputValues(workflow);
  const hint = document.createElement('div');
  hint.className = 'workflow-input-hint';
  const actions = document.createElement('div');
  actions.className = 'workflow-input-actions';

  const runAllBtn = document.createElement('button');
  runAllBtn.type = 'button';
  runAllBtn.className = 'btn btn-secondary btn-compact workflow-run-all';
  runAllBtn.textContent = 'Run all';
  runAllBtn.title = 'Run each rendered workflow step sequentially in this tab';
  actions.appendChild(runAllBtn);

  panel.appendChild(actions);

  inputs.forEach((input) => {
    const field = document.createElement('label');
    field.className = 'workflow-input-field';

    const label = document.createElement('span');
    label.className = 'workflow-input-label';
    label.textContent = input.label || input.id || '';
    field.appendChild(label);

    const control = document.createElement('input');
    control.className = 'options-token-input workflow-input-control';
    control.type = input.type === 'port' ? 'text' : 'text';
    control.autocomplete = 'off';
    control.autocapitalize = 'none';
    control.autocorrect = 'off';
    control.spellcheck = false;
    control.inputMode = input.type === 'port' ? 'numeric' : 'text';
    control.placeholder = input.placeholder || '';
    control.value = values[input.id] || '';
    control.dataset.workflowInputId = input.id;
    if (input.required) {
      control.required = true;
      control.setAttribute('aria-required', 'true');
    }
    field.appendChild(control);

    if (input.help) {
      const help = document.createElement('span');
      help.className = 'workflow-input-help';
      help.textContent = input.help;
      field.appendChild(help);
    }

    grid.appendChild(field);
  });

  panel.appendChild(hint);

  const applyRenderedState = () => {
    const rendered = buildRenderedWorkflow(workflow, values);
    const stepsEl = card.querySelector('.workflow-steps');
    if (!stepsEl) return;
    stepsEl.querySelectorAll('.workflow-step').forEach((stepEl, idx) => {
      const chip = stepEl.querySelector('.workflow-step-cmd');
      const runBtn = stepEl.querySelector('.workflow-step-run');
      const renderedStep = rendered.steps[idx];
      const renderedCmd = renderedStep?.renderedCmd || '';
      if (chip) {
        chip.textContent = rendered.ready ? (renderedCmd || renderedStep?.cmd || '') : (renderedStep?.cmd || '');
        if (rendered.ready && renderedCmd) {
          chip.title = 'Click to load into prompt';
          chip.dataset.faqCommand = renderedCmd;
          chip.classList.remove('is-disabled');
        } else {
          chip.title = 'Fill required workflow inputs to load this step';
          delete chip.dataset.faqCommand;
          chip.classList.add('is-disabled');
        }
      }
      if (runBtn) {
        runBtn.dataset.workflowStepCmd = rendered.ready ? renderedCmd : '';
        runBtn.disabled = !(rendered.ready && renderedCmd);
        runBtn.setAttribute('aria-disabled', runBtn.disabled ? 'true' : 'false');
        runBtn.title = runBtn.disabled ? 'Fill required workflow inputs to run this step' : 'Run this step';
        runBtn.setAttribute('aria-label', rendered.ready && renderedCmd ? `Run: ${renderedCmd}` : 'Run this step');
      }
    });
    runAllBtn.disabled = !(rendered.ready && rendered.steps.some((step) => step.renderedCmd));
    runAllBtn.setAttribute('aria-disabled', runAllBtn.disabled ? 'true' : 'false');
    hint.textContent = rendered.ready
      ? 'Rendered commands are live. Click a chip to load it, use ▶ to run one step, or Run all to execute the full workflow here in sequence.'
      : 'Fill the required fields to render runnable commands.';
    wireFaqCommandChips(card);
    wireWorkflowStepRunButtons(card);
  };

  bindPressable(runAllBtn, {
    onActivate: () => {
      const rendered = buildRenderedWorkflow(workflow, values);
      if (!rendered.ready) return;
      runWorkflowCommands(rendered.steps.map((step) => step.renderedCmd));
    },
  });

  grid.querySelectorAll('.workflow-input-control').forEach((control) => {
    control.addEventListener('input', () => {
      const input = inputs.find((item) => item.id === control.dataset.workflowInputId);
      values[control.dataset.workflowInputId || ''] = sanitizeWorkflowInputValue(input, control.value);
      if (input?.type === 'port' && control.value !== values[control.dataset.workflowInputId || '']) {
        control.value = values[control.dataset.workflowInputId || ''];
      }
      persistWorkflowInputValues(workflow, values);
      applyRenderedState();
    });
  });

  panel._workflowApplyRenderedState = applyRenderedState;
  return panel;
}

function renderWorkflowItems(items, { emitCatalogEvent = true } = {}) {
  const body = document.querySelector('.workflows-body');
  if (!body) return;
  body.innerHTML = '';
  const list = Array.isArray(items) ? items : [];
  list.forEach(item => {
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

    const inputPanel = renderWorkflowInputCard(card, item);
    if (inputPanel) card.appendChild(inputPanel);

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
        chip.className = 'allowed-chip faq-chip workflow-step-cmd chip chip-action';
        chip.textContent = step.cmd || '';
        if (inputPanel) {
          chip.title = 'Fill required workflow inputs to load this step';
          chip.classList.add('is-disabled');
        } else {
          chip.title = 'Click to load into prompt';
          chip.dataset.faqCommand = step.cmd || '';
        }
        main.appendChild(chip);

        const runBtn = document.createElement('button');
        runBtn.type = 'button';
        runBtn.className = 'btn btn-ghost btn-compact btn-icon-only workflow-step-run';
        runBtn.textContent = '▶';
        if (inputPanel) {
          runBtn.title = 'Fill required workflow inputs to run this step';
          runBtn.setAttribute('aria-label', 'Run this step');
          runBtn.dataset.workflowStepCmd = '';
          runBtn.disabled = true;
          runBtn.setAttribute('aria-disabled', 'true');
        } else {
          runBtn.title = 'Run this step';
          runBtn.setAttribute('aria-label', `Run: ${step.cmd || ''}`);
          runBtn.dataset.workflowStepCmd = step.cmd || '';
        }
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

    if (inputPanel && typeof inputPanel._workflowApplyRenderedState === 'function') {
      inputPanel._workflowApplyRenderedState();
    }

    body.appendChild(card);
  });

  wireFaqCommandChips(body);
  wireWorkflowStepRunButtons(body);

  if (emitCatalogEvent && typeof emitUiEvent === 'function') {
    emitUiEvent('app:workflows-rendered', {
      items: list.slice(),
    });
  }
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
