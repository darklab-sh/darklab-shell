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
  refocusComposerAfterAction({ defer: true });
});

lnBtn.addEventListener('click', () => {
  applyLineNumberPreference(typeof lnMode !== 'undefined' ? (lnMode === 'on' ? 'off' : 'on') : 'on');
  refocusComposerAfterAction({ defer: true });
});

function openWorkflows() {
  _closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  showWorkflowsOverlay();
}

function closeWorkflows() {
  hideWorkflowsOverlay();
  if (typeof emitUiEvent === 'function') emitUiEvent('app:workflows-closed', {});
  refocusComposerAfterAction({ defer: true });
}

function openFaq() {
  _closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  showFaqOverlay();
}

function closeFaq() {
  hideFaqOverlay();
  refocusComposerAfterAction({ defer: true });
}

function openShortcuts() {
  _closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  if (typeof showShortcutsOverlay === 'function') showShortcutsOverlay();
}

function closeShortcuts() {
  if (typeof hideShortcutsOverlay === 'function') hideShortcutsOverlay();
  refocusComposerAfterAction({ defer: true });
}

function toggleHistoryPanelSurface(force = null) {
  _closeMajorOverlays();
  const isOpen = togglePanelOverlay(historyPanel, force);
  if (isOpen) {
    if (typeof resetHistoryMobileFilters === 'function') resetHistoryMobileFilters();
    if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
    refreshHistoryPanel();
  } else {
    refocusComposerAfterAction({ defer: true });
  }
  return isOpen;
}

window.toggleHistoryPanelSurface = toggleHistoryPanelSurface;

function renderShortcuts(data) {
  const listEl = document.getElementById('shortcuts-list');
  if (!listEl) return;
  listEl.textContent = '';
  const sections = Array.isArray(data && data.sections) ? data.sections : [];
  for (const section of sections) {
    const items = Array.isArray(section && section.items) ? section.items : [];
    if (!items.length) continue;
    const sectionEl = document.createElement('div');
    sectionEl.className = 'shortcuts-section';
    const headingEl = document.createElement('div');
    headingEl.className = 'shortcut-section-title';
    headingEl.textContent = section.title || '';
    sectionEl.appendChild(headingEl);
    const pairsEl = document.createElement('div');
    pairsEl.className = 'shortcuts-pairs';
    for (const item of items) {
      const keyEl = document.createElement('div');
      keyEl.className = 'shortcut-key';
      keyEl.textContent = item.key || '';
      const descEl = document.createElement('div');
      descEl.className = 'shortcut-desc';
      descEl.textContent = item.description || '';
      pairsEl.appendChild(keyEl);
      pairsEl.appendChild(descEl);
    }
    sectionEl.appendChild(pairsEl);
    listEl.appendChild(sectionEl);
  }
}

function setupMobileSheetDragClose() {
  // All sheet drag/tap/keyboard close behavior lives in mobile_sheet.js so the
  // wiring per sheet stays a one-liner and behavior cannot drift between them.
  if (typeof bindMobileSheet !== 'function') return;
  const faqModal = document.getElementById('faq-modal');
  const optionsModal = document.getElementById('options-modal');
  const workspaceModal = document.getElementById('workspace-modal');
  const workflowsModal = document.getElementById('workflows-modal');
  const workflowEditor = document.getElementById('workflow-editor-form');

  bindMobileSheet(mobileMenu,         { onClose: () => hideMobileMenu() });
  bindMobileSheet(historyPanel,       { onClose: () => hideHistoryPanel() });
  bindMobileSheet(workflowsModal,     { onClose: () => closeWorkflows() });
  bindMobileSheet(workspaceModal,     { onClose: () => { if (typeof closeWorkspace === 'function') closeWorkspace(); } });
  bindMobileSheet(workflowEditor,     { onClose: () => { if (typeof closeWorkflowEditor === 'function') closeWorkflowEditor(); } });
  bindMobileSheet(faqModal,           { onClose: () => closeFaq() });
  bindMobileSheet(optionsModal,       { onClose: () => closeOptions() });
}

function setupDismissibleOverlays() {
  // Each overlay/modal surface is registered with bindDismissible so
  // backdrop click + explicit close button + Escape are owned by one
  // helper (app/static/js/ui_dismissible.js). The Escape cascade
  // dispatcher (closeTopmostDismissible) enforces modal > sheet > panel
  // priority declaratively instead of the hand-rolled if-chain this
  // setup replaces.
  if (typeof bindDismissible !== 'function') return;
  const shortcutsOverlayEl = document.getElementById('shortcuts-overlay');
  const shortcutsCloseBtn = shortcutsOverlayEl?.querySelector('.shortcuts-close');
  const workflowEditorOverlay = document.getElementById('workflow-editor-overlay');
  const workflowEditorCloseBtns = workflowEditorOverlay?.querySelectorAll('.workflow-editor-close');

  bindDismissible(_uiOverlayRefs.workflowsOverlay, {
    level: 'panel',
    isOpen: isWorkflowsOverlayOpen,
    onClose: closeWorkflows,
    closeButtons: workflowsCloseBtn,
  });
  bindDismissible(_uiOverlayRefs.workspaceOverlay, {
    level: 'panel',
    isOpen: () => typeof isWorkspaceOverlayOpen === 'function' && isWorkspaceOverlayOpen(),
    onClose: () => { if (typeof closeWorkspace === 'function') closeWorkspace(); },
    closeButtons: typeof workspaceCloseBtn !== 'undefined' ? workspaceCloseBtn : null,
  });
  bindDismissible(_uiOverlayRefs.workspaceViewerOverlay, {
    level: 'modal',
    isOpen: () => (
      typeof workspaceViewerOverlay !== 'undefined'
      && workspaceViewerOverlay
      && !workspaceViewerOverlay.classList.contains('u-hidden')
    ),
    onClose: () => { if (typeof hideWorkspaceViewer === 'function') hideWorkspaceViewer(); },
    closeButtons: typeof workspaceCloseViewerBtn !== 'undefined' ? workspaceCloseViewerBtn : null,
  });
  bindDismissible(_uiOverlayRefs.workspaceEditorOverlay, {
    level: 'modal',
    isOpen: () => (
      typeof workspaceEditorOverlay !== 'undefined'
      && workspaceEditorOverlay
      && !workspaceEditorOverlay.classList.contains('u-hidden')
    ),
    onClose: () => { if (typeof hideWorkspaceEditor === 'function') hideWorkspaceEditor(); },
    closeButtons: typeof workspaceCancelEditBtn !== 'undefined' ? workspaceCancelEditBtn : null,
  });
  bindDismissible(workflowEditorOverlay, {
    level: 'modal',
    isOpen: () => !!(workflowEditorOverlay && !workflowEditorOverlay.classList.contains('u-hidden')),
    onClose: () => { if (typeof closeWorkflowEditor === 'function') closeWorkflowEditor(); },
    closeButtons: workflowEditorCloseBtns,
  });
  bindDismissible(_uiOverlayRefs.faqOverlay, {
    level: 'panel',
    isOpen: isFaqOverlayOpen,
    onClose: closeFaq,
    closeButtons: faqCloseBtn,
  });
  bindDismissible(_uiOverlayRefs.themeOverlay, {
    level: 'panel',
    isOpen: isThemeOverlayOpen,
    onClose: closeThemeSelector,
    closeButtons: themeCloseBtn,
  });
  bindDismissible(_uiOverlayRefs.optionsOverlay, {
    level: 'panel',
    isOpen: isOptionsOverlayOpen,
    onClose: closeOptions,
    closeButtons: optionsCloseBtn,
  });
  bindDismissible(shortcutsOverlayEl, {
    level: 'panel',
    isOpen: isShortcutsOverlayOpen,
    onClose: closeShortcuts,
    closeButtons: shortcutsCloseBtn,
  });
  bindDismissible(historyPanel, {
    level: 'panel',
    isOpen: isHistoryPanelOpen,
    onClose: () => {
      if (typeof resetHistoryMobileFilters === 'function') resetHistoryMobileFilters();
      hideHistoryPanel();
    },
    closeButtons: historyCloseBtn,
    // historyPanel is an aside, not a modal backdrop — outside click
    // dismissal is handled by the ambient-click listener in the global
    // click handler below, not by backdrop-click here.
    closeOnBackdrop: false,
  });
}

function setupModalFocusTraps() {
  // Keep Tab / Shift+Tab cycling inside each modal card while its overlay is
  // open — otherwise focus falls through to the rail / tabs / HUD behind the
  // backdrop. #confirm-host wires its own focus trap per-open through
  // showConfirm() because the card's focusables change between shows; the
  // four app-level modals have persistent DOM, so a one-shot idempotent bind
  // at startup is equivalent. bindFocusTrap is a no-op when the card is
  // hidden (display: none on the overlay wrapper), so the listener is only
  // reachable while the modal is open.
  if (typeof bindFocusTrap !== 'function') return;
  const ids = ['options-modal', 'theme-modal', 'faq-modal', 'workspace-modal', 'workflows-modal', 'workflow-editor-form'];
  ids.forEach((id) => {
    const card = document.getElementById(id);
    if (card) bindFocusTrap(card);
  });
}

function setupMobileComposer() {
  // The mobile composer reuses the same shared input state as desktop, but its
  // focus/keyboard handling has to be managed separately for mobile browsers.
  const composerInputs = typeof getComposerInputs === 'function' ? getComposerInputs() : {};
  const mobileInput = composerInputs.mobile || null;
  if (!mobileInput || !mobileRunBtn) return;
  bindMobileComposerSubmitAndInputListeners(mobileInput);
  bindMobileComposerKeyboardListeners(mobileInput);
  if (mobileShellTranscript) {
    const closeKeyboardFromTranscript = e => {
      const interactiveTarget = e && e.target && e.target.closest
        && e.target.closest('button, a, input, textarea, select, [contenteditable="true"], .hist-chip');
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
  if (typeof window !== 'undefined') window.APP_CONFIG = APP_CONFIG;
  document.title = cfg.app_name;
  if (headerTitle) headerTitle.textContent = cfg.app_name;
  const wmVersion = cfg.version ? ` v${cfg.version}` : '';
  const projectText = `${cfg.project_name || 'darklab_shell'}${wmVersion}`;
  document.querySelectorAll('.menu-footer, .rail-nav-version').forEach(el => {
    el.textContent = projectText;
    if (cfg.project_readme) el.href = cfg.project_readme;
  });
  syncThemeSelectionControls();
  updateNewTabBtn();
  renderFaqLimits(cfg);
  if (cfg.diag_enabled) {
    const railDiagBtn = document.getElementById('rail-diag-btn');
    if (railDiagBtn) railDiagBtn.classList.remove('u-hidden');
    const mobileDiagBtn = _uiOverlayRefs.mobileMenu?.querySelector('button[data-menu-action="diag"]');
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

// Mobile menu action dispatch. The click wiring below routes data-menu-action
// buttons through this shared action body.
function dispatchMobileMenuAction(action, btn = null) {
  if (action === 'search') {
    const visible = isSearchBarOpen();
    if (visible) {
      hideSearchBar();
      clearSearch();
    } else {
      openSearchFromSignal();
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
  if (action === 'ts-toggle') {
    // The ts-toggle button is wired as a disclosure in mobile_chrome.js —
    // bindDisclosure owns the aria-expanded / submenu visibility toggle via
    // the pressable's own click handler. The dispatcher here returns early
    // so the menu is not closed as a side effect (ts-toggle is the only
    // menu action that keeps the sheet open).
    return;
  }
  if (action === 'ts-set') {
    applyTimestampPreference(btn?.dataset.tsMode || 'off');
    refocusComposerAfterAction({ defer: true });
  }
  if (action === 'ln') {
    applyLineNumberPreference(typeof lnMode !== 'undefined' ? (lnMode === 'on' ? 'off' : 'on') : 'on');
    refocusComposerAfterAction({ defer: true });
  }
  if (action === 'clear') {
    // On desktop the clear button lives in `.terminal-actions` per-tab. On
    // mobile that row is compressed, so clear moves into the hamburger menu
    // (mobile.css hides the per-tab clear under `body.mobile-terminal-mode`).
    // Behaviour matches the HUD / per-tab clear: cancel welcome settle if it's
    // still running on this tab, then clear the output while preserving run
    // state so a mid-run clear doesn't abandon the SSE stream.
    if (activeTabId) {
      if (typeof cancelWelcome === 'function') cancelWelcome(activeTabId);
      if (typeof clearTab === 'function') clearTab(activeTabId, { preserveRunState: true });
    }
    refocusComposerAfterAction({ defer: true });
  }
  if (action === 'options') openOptions();
  if (action === 'theme') openThemeSelector();
  if (action === 'workflows') openWorkflows();
  if (action === 'workspace' && typeof openWorkspace === 'function') openWorkspace();
  if (action === 'faq') openFaq();
  if (action === 'diag') window.location.href = '/diag';
}

_uiOverlayRefs.mobileMenu?.querySelectorAll('button[data-menu-action]').forEach(btn => {
  btn.addEventListener('click', () => {
    const action = btn.dataset.menuAction;
    // ts-toggle keeps the sheet open; its whole purpose is to expand an inline
    // sub-menu beneath the timestamps row. Every other action closes the sheet
    // as it transitions to another surface.
    if (action !== 'ts-toggle') hideMobileMenu();
    dispatchMobileMenuAction(action, btn);
  });
});

// ── Keyboard shortcuts overlay (`?` trigger) ──

// Global `?` handler. Opens the shortcuts overlay from anywhere on the page,
// including text-input-like surfaces (the composer, search boxes, modal
// inputs), but only when the field is empty. Once any text is present, `?`
// types normally so args like `curl "https://example.com/api?foo=bar"` are
// not interfered with. Skipped while the welcome animation is active; the
// welcome flow consumes every printable key to settle its own intro state.
// Registered in capture phase so we can inspect the input value BEFORE the
// browser inserts the character, and call stopImmediatePropagation() to
// prevent the `#cmd` keydown handler's press-and-hold manual-insertion
// path (which preventDefault's the native insert and re-inserts the key
// itself) from re-adding the `?` after we've routed it to the overlay.
document.addEventListener('keydown', e => {
  if (e.key !== '?') return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (typeof _welcomeActive !== 'undefined' && _welcomeActive) return;
  const ae = document.activeElement;
  if (ae) {
    const tag = (ae.tagName || '').toLowerCase();
    const isEditable = ae.isContentEditable;
    const isTextInput =
      tag === 'textarea' ||
      (tag === 'input' && !/^(checkbox|radio|button|submit|reset|range|color|file)$/i.test(ae.type || '')) ||
      isEditable;
    if (tag === 'select') return;
    if (isTextInput) {
      if (
        (ae === cmdInput || ae === mobileCmdInput)
        && typeof syncFocusedComposerState === 'function'
      ) {
        syncFocusedComposerState(ae);
      }
      const raw = isEditable ? (ae.textContent || '') : (ae.value || '');
      if (raw.length > 0) return;
    }
  }
  e.preventDefault();
  e.stopImmediatePropagation();
  if (typeof isShortcutsOverlayOpen === 'function' && isShortcutsOverlayOpen()) {
    closeShortcuts();
  } else {
    openShortcuts();
  }
}, true);
// Theme + Options: backdrop + close button dismissal is registered via
// bindDismissible in setupDismissibleOverlays(); only the open triggers
// live here.
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
optionsNotifyToggle?.addEventListener('change', e => {
  applyRunNotifyPreference(e.target.checked ? 'on' : 'off');
});
optionsHudClockSelect?.addEventListener('change', e => {
  applyHudClockPreference(e.target.value);
});

// Session token options panel — UI-native controls

function _updateOptionsSessionTokenStatus() {
  const el = document.getElementById('options-session-token-status');
  if (!el) return;
  const token = localStorage.getItem('session_token');
  const hasToken = Boolean(token);
  el.textContent = hasToken ? maskSessionToken(token) : 'No session token — anonymous session';
  el.classList.toggle('is-active', hasToken);
  // Generate only when no token; Rotate, Clear, Copy only when one is active.
  const generateBtn = document.getElementById('options-session-token-generate-btn');
  const rotateBtn   = document.getElementById('options-session-token-rotate-btn');
  const clearBtn    = document.getElementById('options-session-token-clear-btn');
  const copyBtn     = document.getElementById('options-session-token-copy-btn');
  if (generateBtn) generateBtn.style.display = hasToken ? 'none' : '';
  if (rotateBtn)   rotateBtn.style.display   = hasToken ? '' : 'none';
  if (clearBtn)    clearBtn.style.display    = hasToken ? '' : 'none';
  if (copyBtn)     copyBtn.style.display     = hasToken ? '' : 'none';
  _optionsTokenShowMsg('');
}

function _optionsTokenSetBusy(busy) {
  ['options-session-token-generate-btn', 'options-session-token-set-btn',
   'options-session-token-rotate-btn',   'options-session-token-clear-btn'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.disabled = busy;
  });
}

function _optionsTokenShowMsg(msg, isError = false) {
  const el = document.getElementById('options-session-token-msg');
  if (!el) return;
  el.textContent = msg;
  el.style.display = msg ? '' : 'none';
  el.classList.toggle('is-error', isError);
}

async function _waitForMigrateChoice(msg) {
  if (typeof showConfirm !== 'function') return false;
  return await showConfirm({
    body: msg,
    actions: [
      { id: 'cancel', label: 'Cancel',       role: 'cancel' },
      { id: 'skip',   label: 'Skip',         role: 'secondary' },
      { id: 'yes',    label: 'Yes, migrate', role: 'primary' },
    ],
  });
}

function _optionsMigrationCountLabel(runCount = 0, workspaceFileCount = 0, workflowCount = 0) {
  const parts = [];
  if (runCount > 0) parts.push(`${runCount} run(s)`);
  if (workspaceFileCount > 0) parts.push(`${workspaceFileCount} workspace file(s)`);
  if (workflowCount > 0) parts.push(`${workflowCount} workflow(s)`);
  if (!parts.length) return 'no runs, workspace files, or workflows';
  if (parts.length === 1) return parts[0];
  return `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`;
}

function _optionsMigrationResultText(data = {}) {
  const workspaceFiles = Number(data.migrated_workspace_files || 0);
  const skippedWorkspaceFiles = Number(data.skipped_workspace_files || 0);
  const workspaceDirs = Number(data.migrated_workspace_directories || 0);
  const skippedWorkspaceDirs = Number(data.skipped_workspace_directories || 0);
  const workspaceParts = [`${workspaceFiles} workspace file(s)`];
  if (workspaceDirs > 0) workspaceParts.push(`${workspaceDirs} folder(s)`);
  if (skippedWorkspaceFiles > 0) workspaceParts.push(`${skippedWorkspaceFiles} workspace file(s) skipped`);
  if (skippedWorkspaceDirs > 0) workspaceParts.push(`${skippedWorkspaceDirs} folder(s) skipped`);
  return `Migrated ${data.migrated_runs} run(s), ${data.migrated_snapshots} snapshot(s), `
    + `${data.migrated_stars ?? 0} starred command(s), ${data.migrated_workflows ?? 0} workflow(s), `
    + `${workspaceParts.join(', ')}, `
    + 'and saved user options when the destination had none.';
}

async function _clearActiveSessionToken() {
  localStorage.removeItem('session_token');
  const uuid = localStorage.getItem('session_id') || SESSION_ID;
  updateSessionId(uuid);
  if (typeof hydrateCmdHistory === 'function') hydrateCmdHistory([]);
  if (typeof reloadSessionHistory === 'function') await reloadSessionHistory().catch(() => {});
  if (typeof reloadWorkflowCatalog === 'function') reloadWorkflowCatalog().catch(() => {});
  _updateOptionsSessionTokenStatus();
  return uuid;
}

async function confirmClearSessionToken() {
  const token = localStorage.getItem('session_token');
  if (!token) return { cleared: false, anonymousSessionId: null };
  if (typeof showConfirm !== 'function') {
    const uuid = await _clearActiveSessionToken();
    return { cleared: true, anonymousSessionId: uuid };
  }

  const choice = await showConfirm({
    body: {
      text: 'Clear the current session token from this browser?',
      note: 'If you have not saved it elsewhere, you will not be able to recover it from the app, and history tied to it will no longer be accessible from this browser.',
    },
    tone: 'danger',
    actions: [
      {
        id: 'copy',
        label: 'Copy token',
        role: 'secondary',
        onActivate: async () => {
          try {
            await copyTextToClipboard(token);
            showToast('Token copied to clipboard');
          } catch (_) {
            showToast('Failed to copy token', 'error');
          }
          return false;
        },
      },
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'clear', label: 'Clear token', role: 'destructive' },
    ],
  });

  if (choice !== 'clear') return { cleared: false, anonymousSessionId: null };
  const uuid = await _clearActiveSessionToken();
  return { cleared: true, anonymousSessionId: uuid };
}

document.getElementById('options-session-token-copy-btn')?.addEventListener('click', () => {
  const token = localStorage.getItem('session_token');
  if (!token) return;
  copyTextToClipboard(token)
    .then(() => showToast('Token copied to clipboard'))
    .catch(() => showToast('Failed to copy token', 'error'));
});

document.getElementById('options-session-token-generate-btn')?.addEventListener('click', async () => {
  const oldSessionId = SESSION_ID;
  _optionsTokenSetBusy(true);
  _optionsTokenShowMsg('');
  try {
    const resp = await apiFetch('/session/token/generate');
    if (!resp.ok) {
      const d = await resp.json().catch(() => ({}));
      _optionsTokenShowMsg(`Failed to generate token — ${d.error || resp.status}`, true);
      return;
    }
    const { session_token: newToken } = await resp.json();

    // Count runs/files on OLD session before switching identity.
    let runCount = 0;
    let workspaceFileCount = 0;
    let workflowCount = 0;
    try {
      const countResp = await apiFetch('/session/run-count');
      if (countResp.ok) {
        const countData = await countResp.json();
        runCount = countData.count || 0;
        workspaceFileCount = countData.workspace_files || 0;
        workflowCount = countData.workflow_count || 0;
      }
    } catch (_) {}

    // Migrate BEFORE switching identity so a failed /session/migrate does not
    // leave the user on the new token with their runs still on the old session.
    if (runCount > 0 || workspaceFileCount > 0 || workflowCount > 0) {
      const migrateChoice = await _waitForMigrateChoice(
        `You have ${_optionsMigrationCountLabel(runCount, workspaceFileCount, workflowCount)} in your previous session. Migrate history, files, and workflows to the new token?`
      );
      if (migrateChoice !== 'skip' && migrateChoice !== 'yes') return;
      if (migrateChoice === 'yes') {
        const migrateResp = await fetch('/session/migrate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Session-ID': oldSessionId },
          body: JSON.stringify({ from_session_id: oldSessionId, to_session_id: newToken }),
        }).catch(() => null);
        if (!migrateResp?.ok) {
          const d = await migrateResp?.json().catch(() => ({})) ?? {};
          _optionsTokenShowMsg(`Migration failed — ${d.error || 'network error'}. Token not activated.`, true);
          return;
        }
        const migrateData = await migrateResp.json().catch(() => ({}));
        _optionsTokenShowMsg(_optionsMigrationResultText(migrateData));
      }
    }

    localStorage.setItem('session_token', newToken);
    updateSessionId(newToken);
    if (typeof _seedLocalStorageStarsToServer === 'function') await _seedLocalStorageStarsToServer();
    if (typeof reloadSessionHistory === 'function') await reloadSessionHistory().catch(() => {});
    if (typeof reloadWorkflowCatalog === 'function') reloadWorkflowCatalog().catch(() => {});
    _updateOptionsSessionTokenStatus();
    if (typeof refreshWorkspaceFiles === 'function') refreshWorkspaceFiles().catch(() => {});
    copyTextToClipboard(newToken)
      .then(() => showToast('New token copied to clipboard'))
      .catch(() => {});
  } catch (err) {
    _optionsTokenShowMsg(`Error: ${err.message || 'network error'}`, true);
  } finally {
    _optionsTokenSetBusy(false);
  }
});

// Set token modal — showConfirm with input + inline error content slot.
// Apply is gated by onActivate (format check + /session/token/verify),
// so validation errors keep the modal open instead of firing the real flow.
document.getElementById('options-session-token-set-btn')?.addEventListener('click', async () => {
  _optionsTokenShowMsg('');
  if (typeof showConfirm !== 'function') return;

  const input = document.createElement('input');
  input.type = 'text';
  input.id = 'session-token-set-input';
  input.className = 'options-token-input modal-token-input';
  input.placeholder = 'tok_... or UUID';
  if (typeof applyMobileTextInputDefaults === 'function') {
    applyMobileTextInputDefaults(input);
  } else {
    input.autocomplete = 'off';
    input.autocapitalize = 'none';
    input.autocorrect = 'off';
    input.spellcheck = false;
    input.inputMode = 'text';
  }

  const errEl = document.createElement('div');
  errEl.id = 'session-token-set-error';
  errEl.className = 'options-session-token-msg is-error';
  errEl.style.display = 'none';

  // Enter in the input triggers Apply. Preventing default stops the enter from
  // bubbling into a synthetic click on the first button (Cancel).
  input.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    document.querySelector('#confirm-host [data-confirm-action-id="apply"]')?.click();
  });

  let value = '';
  const choice = await showConfirm({
    body: {
      text: 'Enter a session token to switch to.',
      note: 'Accepts tok_... format or a UUID from another session.',
    },
    content: [input, errEl],
    defaultFocus: input,
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      {
        id: 'apply',
        label: 'Apply',
        role: 'primary',
        onActivate: async () => {
          value = (input.value || '').trim();
          const isTok  = value.startsWith('tok_');
          const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
          if (!value || (!isTok && !isUuid)) {
            errEl.textContent = 'Invalid token — expected tok_... or a UUID';
            errEl.style.display = '';
            return false;
          }
          // For tok_ tokens, verify server-side existence before switching.
          // A typo would otherwise silently create a brand-new empty session.
          // Fail closed: any failure (network error, non-OK response, missing
          // exists flag) blocks the switch rather than allowing an unverified
          // token through.
          if (isTok) {
            let verifyErr = null;
            try {
              const vResp = await apiFetch('/session/token/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: value }),
              });
              const vData = await vResp.json().catch(() => ({}));
              if (!vResp.ok) {
                verifyErr = 'Token verification failed — server returned an error';
              } else if (vData.exists === false) {
                verifyErr = 'Token not found — this token was not issued by this server';
              }
            } catch (_) {
              verifyErr = 'Token verification failed — server is unreachable';
            }
            if (verifyErr !== null) {
              errEl.textContent = verifyErr;
              errEl.style.display = '';
              return false;
            }
          }
          errEl.style.display = 'none';
          return true;
        },
      },
    ],
  });

  if (choice !== 'apply') return;

  const oldSessionId = SESSION_ID;
  _optionsTokenSetBusy(true);
  _optionsTokenShowMsg('');
  try {
    let runCount = 0;
    let workspaceFileCount = 0;
    let workflowCount = 0;
    try {
      const countResp = await apiFetch('/session/run-count');
      if (countResp.ok) {
        const countData = await countResp.json();
        runCount = countData.count || 0;
        workspaceFileCount = countData.workspace_files || 0;
        workflowCount = countData.workflow_count || 0;
      }
    } catch (_) {}

    // Migrate BEFORE switching identity so a failed /session/migrate does not
    // leave the user on the new token with their runs still on the old session.
    if (runCount > 0 || workspaceFileCount > 0 || workflowCount > 0) {
      const migrateChoice = await _waitForMigrateChoice(
        `You have ${_optionsMigrationCountLabel(runCount, workspaceFileCount, workflowCount)} in your current session. Migrate history, files, and workflows to this token?`
      );
      if (migrateChoice !== 'skip' && migrateChoice !== 'yes') return;
      if (migrateChoice === 'yes') {
        const migrateResp = await fetch('/session/migrate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Session-ID': oldSessionId },
          body: JSON.stringify({ from_session_id: oldSessionId, to_session_id: value }),
        }).catch(() => null);
        if (!migrateResp?.ok) {
          const d = await migrateResp?.json().catch(() => ({})) ?? {};
          _optionsTokenShowMsg(`Migration failed — ${d.error || 'network error'}. Token not activated.`, true);
          return;
        }
        const migrateData = await migrateResp.json().catch(() => ({}));
        _optionsTokenShowMsg(_optionsMigrationResultText(migrateData));
      }
    }

    localStorage.setItem('session_token', value);
    updateSessionId(value);
    if (typeof _seedLocalStorageStarsToServer === 'function') await _seedLocalStorageStarsToServer();
    if (typeof reloadSessionHistory === 'function') await reloadSessionHistory().catch(() => {});
    if (typeof reloadWorkflowCatalog === 'function') reloadWorkflowCatalog().catch(() => {});
    _updateOptionsSessionTokenStatus();
    if (typeof refreshWorkspaceFiles === 'function') refreshWorkspaceFiles().catch(() => {});
    showToast('Session token applied');
  } catch (err) {
    _optionsTokenShowMsg(`Error: ${err.message || 'network error'}`, true);
  } finally {
    _optionsTokenSetBusy(false);
  }
});

document.getElementById('options-session-token-rotate-btn')?.addEventListener('click', async () => {
  const oldSessionId = SESSION_ID;
  _optionsTokenSetBusy(true);
  _optionsTokenShowMsg('');
  try {
    const genResp = await apiFetch('/session/token/generate');
    if (!genResp.ok) {
      const d = await genResp.json().catch(() => ({}));
      _optionsTokenShowMsg(`Failed to generate token — ${d.error || genResp.status}`, true);
      return;
    }
    const { session_token: newToken } = await genResp.json();

    // Migrate BEFORE updating SESSION_ID so the old identity is sent in the header.
    const migrateResp = await fetch('/session/migrate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Session-ID': oldSessionId },
      body: JSON.stringify({ from_session_id: oldSessionId, to_session_id: newToken }),
    });
    const migrateData = await migrateResp.json().catch(() => ({}));
    if (!migrateResp.ok || !migrateData.ok) {
      _optionsTokenShowMsg(`Migration failed — token not rotated: ${migrateData.error || migrateResp.status}`, true);
      return;
    }
    _optionsTokenShowMsg(_optionsMigrationResultText(migrateData));

    localStorage.setItem('session_token', newToken);
    updateSessionId(newToken);
    if (typeof reloadSessionHistory === 'function') await reloadSessionHistory().catch(() => {});
    if (typeof reloadWorkflowCatalog === 'function') reloadWorkflowCatalog().catch(() => {});

    _updateOptionsSessionTokenStatus();
    if (typeof refreshWorkspaceFiles === 'function') refreshWorkspaceFiles().catch(() => {});
    copyTextToClipboard(newToken)
      .then(() => showToast('New token copied to clipboard'))
      .catch(() => showToast('Token rotated'));
  } catch (err) {
    _optionsTokenShowMsg(`Error: ${err.message || 'network error'}`, true);
  } finally {
    _optionsTokenSetBusy(false);
  }
});

document.getElementById('options-session-token-clear-btn')?.addEventListener('click', async () => {
  const result = await confirmClearSessionToken();
  if (result.cleared) showToast('Session token cleared');
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

apiFetch('/shortcuts').then(r => r.json()).then(data => {
  renderShortcuts(data || {});
}).catch(err => {
  logClientError('failed to load /shortcuts', err);
});

const workflowsLoad = typeof reloadWorkflowCatalog === 'function'
  ? reloadWorkflowCatalog()
  : apiFetch('/workflows').then(r => r.json()).then(data => {
      const items = data.items || [];
      renderWorkflowItems(items);
    });
workflowsLoad.catch(err => {
  logClientError('failed to load /workflows', err);
});

loadStarredFromServer().catch(err => {
  logClientError('failed to load /session/starred', err);
});

// Migrate any legacy stars from localStorage to the server, and clean up the
// stale key for users who never trigger a session change.
if (typeof _seedLocalStorageStarsToServer === 'function') {
  _seedLocalStorageStarsToServer().catch(err => {
    logClientError('failed to seed localStorage stars', err);
  });
}

// ── Tabs ──
setupTabScrollControls();
applyTimestampPreference(getPreference('pref_timestamps') || 'off', false);
applyLineNumberPreference(getPreference('pref_line_numbers') || 'off', false);
applyWelcomeIntroPreference(getWelcomeIntroPreference(), false);
applyShareRedactionDefaultPreference(getShareRedactionDefaultPreference(), false);
applyHudClockPreference(getHudClockPreference(), false);
syncOptionsControls();
if (typeof loadSessionPreferences === 'function') {
  loadSessionPreferences().catch(err => {
    logClientError('failed to apply session preferences', err);
  });
}

const commandHistoryLimit = encodeURIComponent(String(APP_CONFIG.recent_commands_limit || 50));
Promise.all([
  apiFetch(`/history/commands?limit=${commandHistoryLimit}`).then(r => r.json()).catch(err => {
    logClientError('failed to load /history/commands', err);
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
  if (!restoredTabs && !restoredActiveRuns && (!Array.isArray(tabs) || tabs.length === 0)) {
    createTab(typeof createDefaultTabLabel === 'function' ? createDefaultTabLabel(1) : 'shell 1');
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
  refocusComposerAfterAction({ defer: true });
}, 0);
syncMobileViewportState();
setupMobileSheetDragClose();
setupDismissibleOverlays();
setupModalFocusTraps();

newTabBtn.addEventListener('click', () => {
  createShortcutTab();
});

function openSearchFromSignal(scope = null) {
  const normalizedScope = scope || null;
  if (
    normalizedScope
    && typeof isSearchBarOpen === 'function'
    && isSearchBarOpen()
    && searchScope === normalizedScope
  ) {
    navigateSearch(1);
    refocusComposerAfterAction({ defer: true });
    return;
  }
  if (typeof prepareSearchBarForScope === 'function' && normalizedScope) {
    prepareSearchBarForScope(normalizedScope);
  } else if (typeof prepareSearchBarForOpen === 'function') {
    prepareSearchBarForOpen();
  }
  showSearchBar();
  if (searchScope === 'text') focusElement(searchInput);
  else refocusComposerAfterAction({ defer: true });
  runSearch();
}

// ── Search ──
searchToggleBtn.addEventListener('click', () => {
  const visible = isSearchBarOpen();
  if (visible) {
    hideSearchBar();
    clearSearch();
  } else {
    openSearchFromSignal();
  }
});

if (typeof searchSummaryBtn !== 'undefined' && searchSummaryBtn) {
  searchSummaryBtn.addEventListener('click', () => {
    if (typeof summarizeCurrentOutputSignals === 'function') summarizeCurrentOutputSignals();
    refocusComposerAfterAction({ defer: true });
  });
}

searchInput.addEventListener('input', () => {
  if (typeof scheduleRunSearch === 'function') scheduleRunSearch();
  else runSearch();
});
searchPrevBtn.addEventListener('click', () => navigateSearch(-1));
searchNextBtn.addEventListener('click', () => navigateSearch(1));
if (typeof searchScopeButtons !== 'undefined' && Array.isArray(searchScopeButtons)) {
  searchScopeButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      setSearchScope(btn.dataset.searchScope || 'text');
      if (searchScope === 'text') focusElement(searchInput);
      else refocusComposerAfterAction({ defer: true });
    });
  });
}
searchCloseBtn?.addEventListener('click', () => {
  hideSearchBar();
  clearSearch();
});
searchInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    e.preventDefault();
    navigateSearch(e.shiftKey ? -1 : 1);
  }
  if (e.key === 'Escape') {
    hideSearchBar();
    clearSearch();
    refocusComposerAfterAction({ defer: true });
  }
});

searchCaseBtn.addEventListener('click', () => {
  searchCaseSensitive = !searchCaseSensitive;
  searchCaseBtn.setAttribute('aria-pressed', searchCaseSensitive ? 'true' : 'false');
  runSearch();
});

searchRegexBtn.addEventListener('click', () => {
  searchRegexMode = !searchRegexMode;
  searchRegexBtn.setAttribute('aria-pressed', searchRegexMode ? 'true' : 'false');
  runSearch();
});

// ── Run history panel ──
// history panel close button + outside-area dismissal are registered via
// bindDismissible in setupDismissibleOverlays().

// ── History delete modal ──
// The modal itself lives in ui_confirm.js — confirmHistAction() builds
// the action list and resolves the choice. Only the entry-point button
// for the bulk clear path lives here.
histClearAllBtn.addEventListener('click', () => {
  confirmHistAction('clear');
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
// - Alt+Shift+ArrowLeft / Alt+Shift+ArrowRight for tab cycling
// - Alt+P for permalink, Alt+Shift+C for copy
// Confirmation dialogs (kill, history-delete, share-redaction, ...) use
// default-focus-on-cancel so Enter resolves to the safe action via the
// browser's native button activation. Escape is routed through the
// dismissible dispatcher below.
// Browser-native combos like Ctrl/Cmd+T or Ctrl/Cmd+W remain environment-dependent.
function hasActiveTerminalConfirm() {
  return typeof hasPendingTerminalConfirm === 'function' && hasPendingTerminalConfirm();
}

function isAnyPanelOverlayOpen() {
  return (typeof isFaqOverlayOpen === 'function' && isFaqOverlayOpen())
    || (typeof isWorkflowsOverlayOpen === 'function' && isWorkflowsOverlayOpen())
    || (typeof isWorkspaceOverlayOpen === 'function' && isWorkspaceOverlayOpen())
    || (typeof isHistoryCompareOverlayOpen === 'function' && isHistoryCompareOverlayOpen())
    || (typeof isOptionsOverlayOpen === 'function' && isOptionsOverlayOpen())
    || (typeof isThemeOverlayOpen === 'function' && isThemeOverlayOpen());
}

document.addEventListener('keydown', e => {
  // Unified Escape dispatch: closes the topmost open dismissible
  // (modal > sheet > panel) via the registry populated by
  // setupDismissibleOverlays(). Replaces the per-overlay if-chain that
  // used to live here.
  if (e.key === 'Escape' && typeof closeTopmostDismissible === 'function' && closeTopmostDismissible()) {
    e.preventDefault();
    return;
  }
  // When a major panel is open, swallow non-chrome keys so shortcuts
  // don't dispatch behind the overlay. Chrome shortcuts (Alt+H, Alt+G,
  // Alt+, etc.) still fire so the opening chord can also close the
  // surface.
  if (
    isFaqOverlayOpen()
    || isOptionsOverlayOpen()
    || isThemeOverlayOpen()
    || isWorkflowsOverlayOpen()
    || isHistoryPanelOpen()
    || (typeof isHistoryCompareOverlayOpen === 'function' && isHistoryCompareOverlayOpen())
  ) {
    if (handleChromeShortcut(e)) return;
    return;
  }
  if (_welcomeActive && welcomeOwnsTab(activeTabId)) {
    const isCtrlC = e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'c' || e.key === 'C');
    const isSpace = e.key === ' ' || e.code === 'Space';
    const isPrintable = !e.metaKey && !e.ctrlKey && !e.altKey && !isEditableTarget(e.target) && e.key.length === 1;
    if (isCtrlC) {
      _welcomePromptAfterSettle = true;
      requestWelcomeSettle(activeTabId);
      refocusComposerAfterAction({ defer: true });
      e.preventDefault();
      return;
    }
    if (e.key === 'Escape' || e.key === 'Enter' || isSpace) {
      requestWelcomeSettle(activeTabId);
      refocusComposerAfterAction({ defer: true });
      e.preventDefault();
      return;
    }
    if (isPrintable) {
      requestWelcomeSettle(activeTabId);
      refocusComposerAfterAction({ defer: true });
      setComposerValue((typeof getComposerValue === 'function' ? getComposerValue() : '') + e.key);
      e.preventDefault();
      return;
    }
  }
  if (handleTabShortcut(e)) return;
  if (handleActionShortcut(e)) return;
  if (handleChromeShortcut(e)) return;
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'c' || e.key === 'C')) {
    if (e.target === cmdInput) return;
    const editable = isEditableTarget(e.target);
    if (editable) return;
    if (_welcomeActive && welcomeOwnsTab(activeTabId)) {
      _welcomePromptAfterSettle = true;
      requestWelcomeSettle(activeTabId);
      refocusComposerAfterAction({ defer: true });
      e.preventDefault();
      return;
    }
    const activeTab = getActiveTab();
    if (activeTab && activeTab.st === 'running') {
      confirmKill(activeTabId);
    } else if (hasActiveTerminalConfirm()) {
      cancelPendingTerminalConfirm(activeTabId);
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
    refocusComposerAfterAction({ defer: true });
    setComposerValue((typeof getComposerValue === 'function' ? getComposerValue() : '') + e.key);
    e.preventDefault();
    return;
  }
  if (e.key === 'Enter' && _welcomeActive && welcomeOwnsTab(activeTabId)) {
    if ((typeof getComposerValue === 'function' ? getComposerValue() : '').trim()) return;
    requestWelcomeSettle(activeTabId);
    refocusComposerAfterAction({ defer: true });
    e.preventDefault();
    return;
  }
  if (e.key === 'Escape' && _welcomeActive && welcomeOwnsTab(activeTabId)) {
    requestWelcomeSettle(activeTabId);
    refocusComposerAfterAction({ defer: true });
    e.preventDefault();
    return;
  }
  if (e.key === 'Escape') {
    // Dismissibles are closed by the unified Escape dispatch at the top
    // of this handler; only the search-bar and search-term clears
    // remain, since those are not registered surfaces.
    hideSearchBar();
    clearSearch();
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
    && !(typeof isHistoryCompareOverlayOpen === 'function' && isHistoryCompareOverlayOpen())
    && !(typeof isConfirmOpen === 'function' && isConfirmOpen())
  ) {
    e.preventDefault();
    refocusComposerAfterAction({ preventScroll: true });
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
  refocusComposerAfterAction({ preventScroll: true });
  if (isCtrlR) {
    if (typeof enterHistSearch === 'function') enterHistSearch();
    return true;
  }
  if (e.key === 'ArrowDown') {
    if (hasActiveTerminalConfirm()) {
      if (typeof acHide === 'function') acHide();
      return true;
    }
    if (isAcDropdownOpen() && acFiltered.length) {
      acIndex = (acIndex + 1) % acFiltered.length;
      if (typeof acShow === 'function') acShow(acFiltered);
    } else if (typeof navigateCmdHistory === 'function' && navigateCmdHistory(-1)) {
      if (typeof acHide === 'function') acHide();
    }
    return true;
  }
  if (e.key === 'ArrowUp') {
    if (hasActiveTerminalConfirm()) {
      if (typeof acHide === 'function') acHide();
      return true;
    }
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

function _isMajorSurfaceOpenForPromptPaste() {
  return (
    isFaqOverlayOpen()
    || isOptionsOverlayOpen()
    || isThemeOverlayOpen()
    || isWorkflowsOverlayOpen()
    || (typeof isWorkspaceOverlayOpen === 'function' && isWorkspaceOverlayOpen())
    || (typeof isHistoryCompareOverlayOpen === 'function' && isHistoryCompareOverlayOpen())
    || isHistoryPanelOpen()
    || (typeof isConfirmOpen === 'function' && isConfirmOpen())
  );
}

document.addEventListener('paste', e => {
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

// ── Global click: dismiss history panel, autocomplete ──
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
    exemptSelectors: ['.hist-chip-overflow', '[data-action="history"]', '#history-compare-overlay'],
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

// ── Autocomplete ──
apiFetch('/autocomplete').then(r => r.json()).then(data => {
  acSuggestions = data.suggestions || [];
  acContextRegistry = data.context || {};
  acWordlists = Array.isArray(data.wordlists) ? data.wordlists : [];
  acSpecialCommands = data.special_commands || [];
  acBuiltinCommandRoots = data.builtin_command_roots || [];
  if (typeof loadSessionVariables === 'function') loadSessionVariables().catch(() => {});
  if (typeof scheduleSearchDiscoverabilityRefresh === 'function') scheduleSearchDiscoverabilityRefresh();
  else if (typeof refreshSearchDiscoverabilityUi === 'function') refreshSearchDiscoverabilityUi();
}).catch(err => {
  logClientError('failed to load /autocomplete', err);
});

cmdInput.addEventListener('input', () => {
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
  // Keep the active tab's draft current so activateTab can read it directly
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

  if (e.altKey && !e.ctrlKey && !e.metaKey && eventMatchesLetter(e, 'b')) {
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

  if (e.altKey && !e.ctrlKey && !e.metaKey && eventMatchesLetter(e, 'f')) {
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
    if (!hasActiveTerminalConfirm() && acIndex >= 0 && acFiltered[acIndex]) {
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
    if (hasActiveTerminalConfirm()) {
      acHide();
      return;
    }
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
    if (hasActiveTerminalConfirm()) {
      acHide();
      return;
    }
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

if (typeof _applyComposerPromptMode === 'function') _applyComposerPromptMode();
syncShellPrompt();
if (typeof syncRunButtonDisabled === 'function') syncRunButtonDisabled();

setupMobileComposer();
