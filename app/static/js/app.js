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
let promptUsernameSavedDelayTimer = null;
let promptUsernameSavedHideTimer = null;
let _tourOpenedRecordedThisSession = false;
const FIELD_SAVED_INDICATOR_DELAY_MS = 200;
const FIELD_SAVED_INDICATOR_VISIBLE_MS = 1600;

function _setFieldSavedIndicator(el, visible) {
  if (!el) return;
  el.classList.toggle('u-hidden', !visible);
}

function _clearPromptUsernameSavedTimers() {
  if (promptUsernameSavedDelayTimer) {
    clearTimeout(promptUsernameSavedDelayTimer);
    promptUsernameSavedDelayTimer = null;
  }
  if (promptUsernameSavedHideTimer) {
    clearTimeout(promptUsernameSavedHideTimer);
    promptUsernameSavedHideTimer = null;
  }
}

function hidePromptUsernameSavedIndicator() {
  _clearPromptUsernameSavedTimers();
  _setFieldSavedIndicator(optionsPromptUsernameSaved, false);
}

function showPromptUsernameSavedIndicator() {
  _clearPromptUsernameSavedTimers();
  _setFieldSavedIndicator(optionsPromptUsernameSaved, false);
  promptUsernameSavedDelayTimer = setTimeout(() => {
    promptUsernameSavedDelayTimer = null;
    _setFieldSavedIndicator(optionsPromptUsernameSaved, true);
    promptUsernameSavedHideTimer = setTimeout(() => {
      promptUsernameSavedHideTimer = null;
      _setFieldSavedIndicator(optionsPromptUsernameSaved, false);
    }, FIELD_SAVED_INDICATOR_VISIBLE_MS);
  }, FIELD_SAVED_INDICATOR_DELAY_MS);
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
    typeof APP_CONFIG !== 'undefined'
    && APP_CONFIG
    && APP_CONFIG.workspace_enabled === true
    && typeof currentPromptWorkspacePath === 'function'
  ) {
    return `${_compactMobileComposerPath(currentPromptWorkspacePath())} · type command`;
  }
  return 'Type a command';
}

function _applyComposerPromptMode() {
  const isConfirm = _composerPromptMode === 'confirm';
  const defaultPromptLabel = typeof buildPromptLabel === 'function'
    ? buildPromptLabel()
    : (_defaultDesktopPromptLabel || 'anon@darklab.sh:~ $');
  const desktopLabel = isConfirm ? '[yes/no]:' : defaultPromptLabel;
  const mobileLabel = isConfirm ? '[yes/no]:' : '';
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
  if (mobilePromptLabel) {
    mobilePromptLabel.textContent = mobileLabel;
    mobilePromptLabel.hidden = !isConfirm;
  }
  if (typeof mobileCmdInput !== 'undefined' && mobileCmdInput) {
    mobileCmdInput.placeholder = isConfirm ? '' : _mobileComposerPlaceholder();
  }
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
const _commandRegistryOverlayHomeParent = typeof commandRegistryOverlay !== 'undefined' && commandRegistryOverlay ? commandRegistryOverlay.parentElement : null;
const _themeOverlayHomeParent = typeof themeOverlay !== 'undefined' && themeOverlay ? themeOverlay.parentElement : null;
const _optionsOverlayHomeParent = typeof optionsOverlay !== 'undefined' && optionsOverlay ? optionsOverlay.parentElement : null;
const _statusHomeParent = typeof status !== 'undefined' && status ? status.parentElement : null;
const _runTimerHomeParent = typeof runTimer !== 'undefined' && runTimer ? runTimer.parentElement : null;
const _headerHomeParent = typeof headerTitle !== 'undefined' && headerTitle ? headerTitle.closest('header') : (typeof document !== 'undefined' ? document.querySelector('header') : null);
const _mobileHeaderActionsHomeParent = typeof mobileHeaderActions !== 'undefined' && mobileHeaderActions ? mobileHeaderActions : _headerHomeParent;
const TAB_SESSION_STATE_KEY = `tab_session_state:${typeof SESSION_ID !== 'undefined' ? SESSION_ID : 'session'}`;
let _tabSessionPersistTimer = null;
let _tabSessionRestoreInProgress = false;
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
  workspaceViewerOverlay: typeof workspaceViewerOverlay !== 'undefined' && workspaceViewerOverlay ? workspaceViewerOverlay : null,
  workspaceEditorOverlay: typeof workspaceEditorOverlay !== 'undefined' && workspaceEditorOverlay ? workspaceEditorOverlay : null,
  faqOverlay: typeof faqOverlay !== 'undefined' && faqOverlay ? faqOverlay : null,
  commandRegistryOverlay: typeof commandRegistryOverlay !== 'undefined' && commandRegistryOverlay ? commandRegistryOverlay : null,
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
  { node: faqOverlay, homeParent: _faqOverlayHomeParent, desktopAnchor: commandRegistryOverlay || themeOverlay || null },
  { node: commandRegistryOverlay, homeParent: _commandRegistryOverlayHomeParent, desktopAnchor: themeOverlay || null },
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
    _moveComposerNode(acDropdown, mobileComposerRefs.host, mobileComposerRefs.host.firstElementChild || null);
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
  if (activeMobileMode && keyboardOpen) {
    queueMobileOutputTailRefresh({ keyboardOpen: true, delays: [0] });
  } else if (activeMobileMode && wasMobileKeyboardOpen) {
    queueMobileOutputTailRefresh({ keyboardOpen: false });
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

function _closeMajorOverlays() {
  if (typeof isCommandCatalogOverlayOpen === 'function' && isCommandCatalogOverlayOpen()) {
    hideCommandCatalogOverlay();
  }
  if (typeof isCommandRegistryOverlayOpen === 'function' && isCommandRegistryOverlayOpen()) {
    hideCommandRegistryOverlay();
  }
  if (globalThis.isProjectWorkspaceOpen && globalThis.isProjectWorkspaceOpen()) {
    globalThis.closeProjectWorkspace({ refocus: false });
  }
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

globalThis._closeMajorOverlays = _closeMajorOverlays;

function openOptions() {
  // Opening one major overlay should implicitly close the others so mobile and
  // desktop never stack multiple drawers/modals on top of each other.
  _closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  syncOptionsControls();
  if (typeof _updateOptionsSessionTokenStatus === 'function') _updateOptionsSessionTokenStatus();
  showOptionsOverlay();
  if (typeof markInteractionSurfaceReady === 'function') {
    markInteractionSurfaceReady('options', optionsOverlay, document.getElementById('options-modal'));
  }
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
    if (!focusElement(target, { preventScroll: true })) {
      focusElement(themeSelect, { preventScroll: true });
    }
    if (typeof markInteractionSurfaceReady === 'function') {
      markInteractionSurfaceReady('theme', themeOverlay, document.getElementById('theme-modal'));
    }
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

function isStatusMonitorShortcutOpen() {
  if (typeof isStatusMonitorOpen === 'function') return isStatusMonitorOpen();
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
    line_number: Number.isInteger(line && line.line_number) ? line.line_number : undefined,
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
      workspaceCwd: String(tab.workspaceCwd || ''),
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

function _normalizeRestoredWorkspaceCwd(path = '') {
  const parts = String(path || '').split('/').map(part => String(part || '').trim()).filter(Boolean);
  return parts.join('/');
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
      tab.workspaceCwd = _normalizeRestoredWorkspaceCwd(item && item.workspaceCwd || '');
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
      tab.workspaceCwd = _normalizeRestoredWorkspaceCwd(item && item.workspaceCwd || '');
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

const MAC_OPTION_KEY_ALIASES = {
  f: ['ƒ'],
};

function eventMatchesLetter(e, letter) {
  if (eventMatchesCode(e, `Key${letter.toUpperCase()}`)) return true;
  const key = e && typeof e.key === 'string' ? e.key.toLowerCase() : '';
  const normalizedLetter = String(letter || '').toLowerCase();
  return key === normalizedLetter || (MAC_OPTION_KEY_ALIASES[normalizedLetter] || []).includes(key);
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
  if (e.altKey && !e.ctrlKey && !e.metaKey && e.shiftKey && eventMatchesLetter(e, 'p')) {
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
  if (e.ctrlKey && !e.altKey && !e.metaKey && (e.key === 'd' || e.key === 'D')) {
    closeActiveShortcutTab();
    e.preventDefault();
    return true;
  }
  return false;
}

// Desktop chrome shortcuts (rail, search, history, options, theme, workflows,
// Files, projects, command registry, and Status Monitor).
// The composer is allowed to pass through so prompt-focused users can still
// trigger chrome toggles — each branch calls preventDefault so Option-glyphs
// (`«`, `˙`, `µ`, `©`, `≤`, `ˇ`, `ß`) never leak into the prompt on macOS.
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
    if (typeof isWorkspaceOverlayOpen === 'function' && isWorkspaceOverlayOpen()) {
      if (typeof closeWorkspace === 'function') closeWorkspace();
      else if (typeof hideWorkspaceOverlay === 'function') hideWorkspaceOverlay();
    } else if (typeof openWorkspace === 'function') {
      openWorkspace();
    }
    e.preventDefault();
    return true;
  }
  // All remaining chrome chords are shift-free.
  if (e.shiftKey) return false;
  if (eventMatchesLetter(e, 'm')) {
    if (isStatusMonitorShortcutOpen() && typeof closeStatusMonitor === 'function') closeStatusMonitor();
    else if (typeof openStatusMonitor === 'function') void openStatusMonitor({ source: 'shortcut' });
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, 'c')) {
    if (
      typeof isCommandRegistryOverlayOpen === 'function'
      && isCommandRegistryOverlayOpen()
      && typeof closeCommandRegistry === 'function'
    ) closeCommandRegistry();
    else if (typeof openCommandRegistry === 'function') openCommandRegistry();
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, 'p')) {
    if (
      typeof isProjectWorkspaceOpen === 'function'
      && isProjectWorkspaceOpen()
      && typeof closeProjectWorkspace === 'function'
    ) closeProjectWorkspace();
    else if (typeof openProjectWorkspace === 'function') void openProjectWorkspace();
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

function queueMobileOutputTailRefresh({ keyboardOpen = null, delays = [0, 80, 180, 320] } = {}) {
  if (typeof _refreshFollowingOutputsAfterLayout !== 'function') return;
  delays.forEach(delay => {
    setTimeout(() => {
      if (!useMobileTerminalViewportMode()) return;
      if (!document.body) return;
      if (
        typeof keyboardOpen === 'boolean'
        && document.body.classList.contains('mobile-keyboard-open') !== keyboardOpen
      ) return;
      _refreshFollowingOutputsAfterLayout();
    }, delay);
  });
}

function syncMobileComposerKeyboard({ open = null } = {}) {
  if (typeof window === 'undefined') return;
  const offset = getMobileKeyboardOffset();
  const keyboardOpen = typeof syncMobileComposerKeyboardState === 'function'
    ? syncMobileComposerKeyboardState(offset, { open })
    : !!open;
  syncMobileViewportHeight({ keyboardOpen });
  queueMobileOutputTailRefresh({ keyboardOpen, delays: keyboardOpen ? [0] : [0, 80, 180, 320] });
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

function isTerminalWordChar(char) {
  return /[A-Za-z0-9]/.test(char || '');
}

function findWordBoundaryLeft(value, index) {
  let next = Math.max(0, index);
  while (next > 0 && !isTerminalWordChar(value[next - 1])) next--;
  while (next > 0 && isTerminalWordChar(value[next - 1])) next--;
  return next;
}

function findWordBoundaryRight(value, index) {
  let next = Math.min(value.length, index);
  while (next < value.length && !isTerminalWordChar(value[next])) next++;
  while (next < value.length && isTerminalWordChar(value[next])) next++;
  return next;
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
