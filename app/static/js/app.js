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
