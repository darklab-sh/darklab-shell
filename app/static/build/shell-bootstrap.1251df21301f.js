;
/* /static/js/controller.js */
// ── Desktop UI controller ──
// Bootstraps the page, wires listeners, and coordinates the feature helpers.

renderThemeSelectionOptions();
var initialThemeName = _savedThemeName();
var initialTheme = initialThemeName ? _findThemeEntry(initialThemeName) : null;
var resolvedInitialTheme = initialTheme || _defaultThemeEntry();
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
  if (typeof ensureWorkflowCatalogLoaded === 'function') {
    ensureWorkflowCatalogLoaded().catch(err => {
      logClientError('failed to load /workflows while opening modal', err);
    });
  }
  if (typeof markInteractionSurfaceReady === 'function') {
    markInteractionSurfaceReady('workflows', workflowsOverlay, document.getElementById('workflows-modal'));
  }
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
  if (typeof applyFaqHashTarget === 'function') applyFaqHashTarget();
  if (typeof markInteractionSurfaceReady === 'function') {
    markInteractionSurfaceReady('faq', faqOverlay, document.getElementById('faq-modal'));
  }
}

function closeFaq() {
  if (typeof clearFaqHash === 'function') clearFaqHash();
  hideFaqOverlay();
  refocusComposerAfterAction({ defer: true });
}

function closeCommandRegistryPanel() {
  if (typeof closeCommandRegistry === 'function') closeCommandRegistry();
}

function openShortcuts() {
  _closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  if (typeof showShortcutsOverlay === 'function') showShortcutsOverlay();
  if (typeof markInteractionSurfaceReady === 'function') {
    markInteractionSurfaceReady('shortcuts', shortcutsOverlay, document.getElementById('shortcuts-modal'));
  }
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
    if (typeof resetHistorySelectionOnClose === 'function') resetHistorySelectionOnClose();
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
  const projectWorkspaceModal = document.getElementById('project-workspace-modal');
  const providerStatusModal = document.getElementById('provider-status-modal');
  const atlasSurface = document.getElementById('atlas-surface');
  const schedulesModal = document.getElementById('schedules-modal');
  const watchersModal = document.getElementById('watchers-modal');

  bindMobileSheet(mobileMenu,         { onClose: () => hideMobileMenu() });
  bindMobileSheet(historyPanel,       { onClose: () => hideHistoryPanel() });
  bindMobileSheet(workflowsModal,     { onClose: () => closeWorkflows() });
  bindMobileSheet(workspaceModal,     { onClose: () => { if (typeof closeWorkspace === 'function') closeWorkspace(); } });
  bindMobileSheet(workflowEditor,     { onClose: () => { if (typeof closeWorkflowEditor === 'function') closeWorkflowEditor(); } });
  bindMobileSheet(faqModal,           { onClose: () => closeFaq() });
  bindMobileSheet(document.getElementById('command-registry-modal'), { onClose: () => closeCommandRegistryPanel() });
  bindMobileSheet(projectWorkspaceModal, { onClose: () => { if (typeof closeProjectWorkspace === 'function') closeProjectWorkspace(); } });
  bindMobileSheet(optionsModal,       { onClose: () => closeOptions() });
  bindMobileSheet(providerStatusModal, { onClose: () => { if (typeof closeProviderStatusModal === 'function') closeProviderStatusModal(); } });
  bindMobileSheet(atlasSurface,       { onClose: () => { if (typeof closeAtlas === 'function') closeAtlas(); } });
  bindMobileSheet(schedulesModal,     { onClose: () => { if (typeof closeSchedulesModal === 'function') closeSchedulesModal(); } });
  bindMobileSheet(watchersModal,      { onClose: () => { if (typeof closeWatchersModal === 'function') closeWatchersModal(); } });
}

function setupDismissibleOverlays() {
  // Each overlay/modal surface is registered with bindDismissible so
  // backdrop click + explicit close button + Escape are owned by one
  // helper (app/static/js/ui/ui_dismissible.js). The Escape cascade
  // dispatcher (closeTopmostDismissible) enforces modal > sheet > panel
  // priority declaratively instead of the hand-rolled if-chain this
  // setup replaces.
  if (typeof bindDismissible !== 'function') return;
  const shortcutsOverlayEl = document.getElementById('shortcuts-overlay');
  const shortcutsCloseBtn = shortcutsOverlayEl?.querySelector('.shortcuts-close');
  const workflowEditorOverlay = document.getElementById('workflow-editor-overlay');
  const workflowEditorCloseBtns = workflowEditorOverlay?.querySelectorAll('.workflow-editor-close');
  const projectWorkspaceOverlay = document.getElementById('project-workspace-overlay');
  const projectWorkspaceCloseBtn = projectWorkspaceOverlay?.querySelector('.project-workspace-close');
  const providerStatusOverlay = document.getElementById('provider-status-overlay');
  const providerStatusCloseBtn = providerStatusOverlay?.querySelector('.provider-status-close');

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
  bindDismissible(_uiOverlayRefs.commandRegistryOverlay, {
    level: 'panel',
    isOpen: () => typeof isCommandRegistryOverlayOpen === 'function' && isCommandRegistryOverlayOpen(),
    onClose: closeCommandRegistryPanel,
    closeButtons: typeof commandRegistryCloseBtn !== 'undefined' ? commandRegistryCloseBtn : null,
  });
  bindDismissible(projectWorkspaceOverlay, {
    level: 'panel',
    isOpen: () => typeof isProjectWorkspaceOpen === 'function' && isProjectWorkspaceOpen(),
    onClose: () => { if (typeof closeProjectWorkspace === 'function') closeProjectWorkspace(); },
    closeButtons: projectWorkspaceCloseBtn,
  });
  bindDismissible(commandCatalogOverlay, {
    level: 'modal',
    isOpen: () => typeof isCommandCatalogOverlayOpen === 'function' && isCommandCatalogOverlayOpen(),
    onClose: () => { if (typeof closeCommandCatalogModal === 'function') closeCommandCatalogModal(); },
    closeButtons: commandCatalogCloseBtn,
  });
  bindDismissible(providerStatusOverlay, {
    level: 'modal',
    isOpen: () => typeof isProviderStatusModalOpen === 'function' && isProviderStatusModalOpen(),
    onClose: () => { if (typeof closeProviderStatusModal === 'function') closeProviderStatusModal(); },
    closeButtons: providerStatusCloseBtn,
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
  // app-level modals have persistent DOM, so a one-shot idempotent bind
  // at startup is equivalent. bindFocusTrap is a no-op when the card is
  // hidden (display: none on the overlay wrapper), so the listener is only
  // reachable while the modal is open.
  if (typeof bindFocusTrap !== 'function') return;
  const ids = [
    'options-modal',
    'theme-modal',
    'faq-modal',
    'command-registry-modal',
    'provider-status-modal',
    'findings-board-modal',
    'finding-triage-modal',
    'atlas-import-modal',
    'project-workspace-modal',
    'project-target-editor-modal',
    'project-package-manifest-modal',
    'project-package-wizard-modal',
    'project-entity-editor-modal',
    'workspace-modal',
    'workflows-modal',
    'workflow-editor-form',
    'schedules-modal',
    'watchers-modal',
    'team-scope-modal',
  ];
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
  const railWordmarkTitle = document.getElementById('rail-wordmark-title');
  if (railWordmarkTitle) {
    railWordmarkTitle.textContent = cfg.app_name;
    railWordmarkTitle.title = cfg.app_name;
  }
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

// Theme + Options: backdrop + close button dismissal is registered via
// bindDismissible in setupDismissibleOverlays(); only the open triggers
// live here.
optionsTabs?.addEventListener('click', e => {
  const tab = e.target.closest?.('[data-options-tab]');
  if (!tab) return;
  activateOptionsTab(tab.dataset.optionsTab, { persist: true, focus: true });
});
optionsTabs?.addEventListener('keydown', e => {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
  const tabs = Array.from(optionsTabs.querySelectorAll('[data-options-tab]'));
  const currentIndex = tabs.indexOf(document.activeElement);
  if (!tabs.length || currentIndex < 0) return;
  e.preventDefault();
  let nextIndex = currentIndex;
  if (e.key === 'Home') nextIndex = 0;
  else if (e.key === 'End') nextIndex = tabs.length - 1;
  else if (e.key === 'ArrowRight') nextIndex = (currentIndex + 1) % tabs.length;
  else nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
  const nextTab = tabs[nextIndex];
  activateOptionsTab(nextTab.dataset.optionsTab, { persist: true, focus: true });
});
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
optionsCommandOutcomeSummariesToggle?.addEventListener('change', e => {
  applyCommandOutcomeSummariesPreference(e.target.checked ? 'on' : 'off');
});
optionsProjectAutoLinkExternalRunsToggle?.addEventListener('change', e => {
  applyProjectAutoLinkExternalRunsPreference(e.target.checked ? 'on' : 'off');
});
optionsProjectAutoLinkRunEntitiesToggle?.addEventListener('change', e => {
  applyProjectAutoLinkRunEntitiesPreference(e.target.checked ? 'on' : 'off');
});
optionsHudClockSelect?.addEventListener('change', e => {
  applyHudClockPreference(e.target.value);
});
optionsCompareViewModeSelect?.addEventListener('change', e => {
  applyCompareViewModePreference(e.target.value);
});
optionsCompareContextSelect?.addEventListener('change', e => {
  applyCompareContextPreference(e.target.value);
});
var promptUsernameAutosaveTimer = null;
var PROMPT_USERNAME_AUTOSAVE_DELAY_MS = 300;
function clearPromptUsernameAutosave() {
  if (!promptUsernameAutosaveTimer) return;
  clearTimeout(promptUsernameAutosaveTimer);
  promptUsernameAutosaveTimer = null;
}
function schedulePromptUsernameAutosave(value) {
  clearPromptUsernameAutosave();
  promptUsernameAutosaveTimer = setTimeout(() => {
    promptUsernameAutosaveTimer = null;
    applyPromptUsernamePreference(value);
  }, PROMPT_USERNAME_AUTOSAVE_DELAY_MS);
}
optionsPromptUsernameInput?.addEventListener('input', () => {
  if (typeof hidePromptUsernameSavedIndicator === 'function') hidePromptUsernameSavedIndicator();
  if (syncPromptUsernameValidation()) schedulePromptUsernameAutosave(optionsPromptUsernameInput.value);
  else clearPromptUsernameAutosave();
});
optionsPromptUsernameInput?.addEventListener('change', e => {
  if (syncPromptUsernameValidation()) {
    clearPromptUsernameAutosave();
    applyPromptUsernamePreference(e.target.value);
  }
});

apiFetch('/allowed-commands').then(r => r.json()).then(data => {
  allowedCommandsFaqData = data;
  renderAllowedCommandsFaq(data);
}).catch(err => {
  logClientError('failed to load /allowed-commands', err);
});

apiFetch('/commands/catalog').then(r => r.json()).then(data => {
  commandRegistryData = data;
  if (typeof isCommandRegistryOverlayOpen === 'function' && isCommandRegistryOverlayOpen()) {
    renderCommandRegistry();
  }
}).catch(err => {
  logClientError('failed to load /commands/catalog', err);
  commandRegistryData = { restricted: false, commands: [], groups: [] };
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

var workflowsLoad = typeof reloadWorkflowCatalog === 'function'
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
applyPromptUsernamePreference(getPromptUsernamePreference(), false);
syncOptionsControls();
var sessionPreferencesLoad = typeof loadSessionPreferences === 'function'
  ? loadSessionPreferences().catch(err => {
    logClientError('failed to apply session preferences', err);
  })
  : Promise.resolve();

var commandHistoryLimit = encodeURIComponent(String(APP_CONFIG.recent_commands_limit || 50));
Promise.all([
  sessionPreferencesLoad,
  apiFetch(`/history/commands?limit=${commandHistoryLimit}`).then(r => r.json()).catch(err => {
    logClientError('failed to load /history/commands', err);
    return { runs: [] };
  }),
  apiFetch('/history/active').then(r => r.json()).catch(err => {
    logClientError('failed to load /history/active', err);
    return { runs: [] };
  }),
]).then(([, historyData, activeData]) => {
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
    || (typeof isSchedulesOverlayOpen === 'function' && isSchedulesOverlayOpen())
    || (typeof isWatchersOverlayOpen === 'function' && isWatchersOverlayOpen())
    || (typeof isHistoryCompareOverlayOpen === 'function' && isHistoryCompareOverlayOpen())
    || (typeof isHistoryRunOverlayOpen === 'function' && isHistoryRunOverlayOpen())
    || (typeof isOptionsOverlayOpen === 'function' && isOptionsOverlayOpen())
    || (typeof isThemeOverlayOpen === 'function' && isThemeOverlayOpen());
}

document.addEventListener('keydown', e => {
  if (e.defaultPrevented) return;
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
    || (typeof isWorkspaceOverlayOpen === 'function' && isWorkspaceOverlayOpen())
    || (typeof isSchedulesOverlayOpen === 'function' && isSchedulesOverlayOpen())
    || (typeof isWatchersOverlayOpen === 'function' && isWatchersOverlayOpen())
    || isHistoryPanelOpen()
    || (typeof isAtlasOverlayOpen === 'function' && isAtlasOverlayOpen())
    || (typeof isHistoryCompareOverlayOpen === 'function' && isHistoryCompareOverlayOpen())
    || (typeof isHistoryRunOverlayOpen === 'function' && isHistoryRunOverlayOpen())
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
    typeof isActiveTabRunning === 'function'
    && isActiveTabRunning()
    && !(typeof isConfirmOpen === 'function' && isConfirmOpen())
    && !isEditableTarget(e.target)
    && !e.metaKey
    && !e.ctrlKey
    && !e.altKey
    && (e.key.length === 1 || e.key === 'Enter' || e.key === 'Tab' || e.key === 'Backspace' || e.key === 'Delete')
  ) {
    if (typeof acHide === 'function') acHide();
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
    && !(typeof isWorkspaceOverlayOpen === 'function' && isWorkspaceOverlayOpen())
    && !(typeof isSchedulesOverlayOpen === 'function' && isSchedulesOverlayOpen())
    && !(typeof isWatchersOverlayOpen === 'function' && isWatchersOverlayOpen())
    && !(typeof isHistoryCompareOverlayOpen === 'function' && isHistoryCompareOverlayOpen())
    && !(typeof isHistoryRunOverlayOpen === 'function' && isHistoryRunOverlayOpen())
    && !(typeof isConfirmOpen === 'function' && isConfirmOpen())
  ) {
    e.preventDefault();
    refocusComposerAfterAction({ preventScroll: true });
    const value = typeof getComposerValue === 'function' ? getComposerValue() : (cmdInput.value || '');
    const { start, end } = getCmdSelection(value);
    replaceCmdRange(value, start, end, e.key);
  }
});

function acAutocompleteIsHintOnly(item) {
  if (typeof acIsHintOnly === 'function') return acIsHintOnly(item);
  return !!(item && typeof item === 'object' && item.hintOnly);
}

function acAutocompleteSelectableItems(items) {
  if (typeof acSelectableItems === 'function') return acSelectableItems(items);
  return (Array.isArray(items) ? items : []).filter(item => !acAutocompleteIsHintOnly(item));
}

function acAutocompleteSelectableIndexes(items) {
  if (typeof acSelectableIndexes === 'function') return acSelectableIndexes(items);
  return (Array.isArray(items) ? items : [])
    .map((item, index) => (acAutocompleteIsHintOnly(item) ? -1 : index))
    .filter(index => index >= 0);
}

function acAutocompleteNextSelectableIndex(items, currentIndex, direction = 1) {
  if (typeof acNextSelectableIndex === 'function') {
    return acNextSelectableIndex(items, currentIndex, direction);
  }
  const indexes = acAutocompleteSelectableIndexes(items);
  if (!indexes.length) return -1;
  const currentPos = indexes.indexOf(currentIndex);
  if (currentPos < 0) return direction < 0 ? indexes[indexes.length - 1] : indexes[0];
  const nextPos = direction < 0
    ? (currentPos <= 0 ? indexes.length - 1 : currentPos - 1)
    : ((currentPos + 1) % indexes.length);
  return indexes[nextPos];
}

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
    if (isAcDropdownOpen() && acAutocompleteSelectableItems(acFiltered).length) {
      acIndex = acAutocompleteNextSelectableIndex(acFiltered, acIndex, 1);
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
    if (isAcDropdownOpen() && acAutocompleteSelectableItems(acFiltered).length) {
      acIndex = acAutocompleteNextSelectableIndex(acFiltered, acIndex, -1);
      if (typeof acShow === 'function') acShow(acFiltered);
    } else if (typeof navigateCmdHistory === 'function' && navigateCmdHistory(1)) {
      if (typeof acHide === 'function') acHide();
    }
    return true;
  }
  if (e.key === 'Enter') {
    if (acIndex >= 0 && acFiltered[acIndex] && !acAutocompleteIsHintOnly(acFiltered[acIndex])) {
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
;
;
/* /static/js/features/terminal/composer_controller.js */
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

var _promptPointerSelectionState = null;
var _suppressPromptFocusUntil = 0;
var _pendingPromptFocusTimer = null;

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
  if (typeof loadRecentValues === 'function') loadRecentValues().catch(() => {});
  if (typeof loadProjectAutocompleteTargets === 'function') loadProjectAutocompleteTargets().catch(() => {});
  if (typeof loadScheduleAutocompleteHints === 'function') loadScheduleAutocompleteHints().catch(() => {});
  if (typeof loadWatcherAutocompleteHints === 'function') loadWatcherAutocompleteHints().catch(() => {});
  if (typeof refreshWorkspaceFileCache === 'function') refreshWorkspaceFileCache().catch(() => {});
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
;
;
/* /static/js/shell_chrome.js */
// ── Shell chrome controller ──
// Owns the desktop rail (Recent, Workflows, nav) and the bottom HUD.
// Loaded after dom.js, state.js, ui_helpers.js, history.js, tabs.js, app.js,
// project_details.js, project_list.js, project_navigation.js, project_entity_editor.js,
// project_active_context.js, project_workspace_constants.js, project_workspace_state.js, project_workspace_lifecycle.js, project_workspace_renderer.js, project_workspace_bootstrap.js, project_shared_ui.js, project_nested_sheets.js, project_mobile_compare.js, project_mobile_shell.js, project_mobile_detail.js,
// project_entities.js, project_findings.js, project_findings_board.js, findings_board_modal.js, project_artifacts.js, project_packages.js, and controller.js
// so the helpers and overlays it delegates to are already defined.

(function initShellChrome(global) {
  if (typeof document === 'undefined') return;

  // ── Elements ────────────────────────────────────────────────────
  const rail              = document.getElementById('rail');
  if (!rail) return; // mobile-only DOM build; nothing to do

  const railCollapseBtn   = document.getElementById('rail-collapse-btn');
  const railResizeHandle  = document.getElementById('rail-resize-handle');
  const railSplitArea     = document.getElementById('rail-split-area');
  const railSplitter      = document.getElementById('rail-splitter');
  const railSectionRecent = document.getElementById('rail-section-recent');
  const railRecentBody    = document.getElementById('rail-recent-list');
  const railRecentCount   = document.getElementById('rail-recent-count');
  const railRecentHeader  = document.getElementById('rail-recent-header');
  const railSectionWorkflows = document.getElementById('rail-section-workflows');
  const railWorkflowsBody = document.getElementById('rail-workflows-list');
  const railWorkflowsHeader = document.getElementById('rail-workflows-header');
  const railWorkflowsCount = document.getElementById('rail-workflows-count');
  const railNav           = document.getElementById('rail-nav');
  const railMoreBtn       = document.getElementById('rail-more-btn');
  const railMoreMenu      = document.getElementById('rail-more-menu');

  const hud               = document.getElementById('hud');
  const hudLastExitEl     = document.getElementById('hud-last-exit');
  const hudTabsEl         = document.getElementById('hud-tabs');
  const hudLatencyEl      = document.getElementById('hud-latency');
  const hudSessionEl      = document.getElementById('hud-session');
  const hudProjectCell    = document.getElementById('hud-project-cell');
  const hudProjectEl      = document.getElementById('hud-project');
  const hudUptimeEl       = document.getElementById('hud-uptime');
  const hudClockEl        = document.getElementById('hud-clock');
  const hudDbEl           = document.getElementById('hud-db');
  const hudRedisEl        = document.getElementById('hud-redis');
  const projectWorkspaceOverlay = document.getElementById('project-workspace-overlay');
  const projectWorkspaceModal = document.getElementById('project-workspace-modal');
  const projectWorkspaceBody = document.getElementById('project-workspace-body');
  const projectWorkspacePagination = document.getElementById('project-workspace-pagination');
  const projectExplorerBody = document.getElementById('project-explorer-body');
  const projectWorkspaceSubtitle = document.getElementById('project-workspace-subtitle');
  const projectWorkspaceCreateForm = document.getElementById('project-workspace-create-form');
  const projectWorkspaceNameInput = document.getElementById('project-workspace-name');
  const projectMobileRoot = document.getElementById('project-mobile-root');
  const projectMobileListView = document.getElementById('project-mobile-list-view');
  const projectMobileBody = document.getElementById('project-mobile-body');
  const projectMobilePagination = document.getElementById('project-mobile-pagination');
  const projectMobileSummary = document.getElementById('project-mobile-summary');
  const projectMobileCreateForm = document.getElementById('project-mobile-create-form');
  const projectMobileNameInput = document.getElementById('project-mobile-name');
  const projectMobileDetailView = document.getElementById('project-mobile-detail-view');
  const projectMobileDetailTopbar = document.getElementById('project-mobile-detail-topbar');
  const projectMobileTabs = document.getElementById('project-mobile-tabs');
  const projectMobileDetailBody = document.getElementById('project-mobile-detail-body');
  const projectTargetEditorOverlay = document.getElementById('project-target-editor-overlay');
  const projectTargetEditorTitle = document.getElementById('project-target-editor-title');
  const projectTargetCreateForm = document.getElementById('project-target-create-form');
  const projectTargetTypeSelect = document.getElementById('project-target-type');
  const projectTargetValueInput = document.getElementById('project-target-value');
  const projectTargetValueHelp = document.getElementById('project-target-value-help');
  const projectTargetValueError = document.getElementById('project-target-value-error');
  const projectTargetLabelInput = document.getElementById('project-target-label');
  const projectTargetNotesInput = document.getElementById('project-target-notes');
  const projectTargetSubmitButton = document.getElementById('project-target-submit');
  const projectPackageManifestOverlay = document.getElementById('project-package-manifest-overlay');
  const projectPackageManifestTitle = document.getElementById('project-package-manifest-title');
  const projectPackageManifestSummary = document.getElementById('project-package-manifest-summary');
  const projectPackageManifestJson = document.getElementById('project-package-manifest-json');
  const projectPackageWizardOverlay = document.getElementById('project-package-wizard-overlay');
  const projectPackageWizardBody = document.getElementById('project-package-wizard-body');
  const projectEntityEditorOverlay = document.getElementById('project-entity-editor-overlay');
  const projectEntityEditorTitle = document.getElementById('project-entity-editor-title');
  const projectEntityEditorSubtitle = document.getElementById('project-entity-editor-subtitle');
  const projectEntityEditorForm = document.getElementById('project-entity-editor-form');
  const projectEntityLabelsInput = document.getElementById('project-entity-labels');
  const projectEntityNoteInput = document.getElementById('project-entity-note');
  const projectEntityActivityRoot = document.getElementById('project-entity-activity');
  const projectEntitySubmitButton = document.getElementById('project-entity-submit');
  const projectNotesForm = document.getElementById('project-notes-form');
  const projectNotesInput = document.getElementById('project-notes-input');
  const projectLabelsForm = document.getElementById('project-labels-form');
  const projectLabelsInput = document.getElementById('project-labels-input');
  const projectLabelsSaveButton = document.getElementById('project-labels-save-btn');
  const projectWorkspaceMessage = document.getElementById('project-workspace-message');
  const EntityMetadataClient = (
    typeof window !== 'undefined' && window.DarklabEntityMetadata
  ) || (
    typeof global !== 'undefined' && global.DarklabEntityMetadata
  ) || (
    typeof globalThis !== 'undefined' && globalThis.DarklabEntityMetadata
  ) || {};

  // ── Prefs (cookie-backed) ───────────────────────────────────────
  const PREF_COLLAPSED = 'pref_rail_collapsed';
  const PREF_WIDTH     = 'pref_rail_width';
  const PREF_RECENT    = 'pref_rail_recent_open';
  const PREF_WORKFLOWS = 'pref_rail_workflows_open';

  const MIN_W = 180, MAX_W = 360, DEFAULT_W = 214;
  const NARROW_BRAND_W = 200;
  const MIN_SECTION_H = 80;
  const PROJECT_TARGET_HELPERS = global.ProjectTargetValidation || window.ProjectTargetValidation;
  if (!PROJECT_TARGET_HELPERS) throw new Error('ProjectTargetValidation is unavailable');
  const PROJECT_TARGET_TYPES = PROJECT_TARGET_HELPERS.TARGET_TYPES;
  const PROJECT_WORKSPACE_CONSTANTS = global.DarklabProjectWorkspaceConstants || window.DarklabProjectWorkspaceConstants;
  if (!PROJECT_WORKSPACE_CONSTANTS) throw new Error('DarklabProjectWorkspaceConstants is unavailable');

  const readBool = (name, dflt) => {
    const v = typeof getPreference === 'function' ? getPreference(name) : '';
    if (v === '1' || v === 'true') return true;
    if (v === '0' || v === 'false') return false;
    return dflt;
  };
  const writePref = (name, value) => {
    if (typeof setPreferenceCookie === 'function') setPreferenceCookie(name, String(value));
  };

  // ── State ────────────────────────────────────────────────────────
  const ui = {
    collapsed: readBool(PREF_COLLAPSED, false),
    railW: (() => {
      const raw = typeof getPreference === 'function' ? parseInt(getPreference(PREF_WIDTH), 10) : NaN;
      return Number.isFinite(raw) ? Math.max(MIN_W, Math.min(MAX_W, raw)) : DEFAULT_W;
    })(),
    recentOpen: readBool(PREF_RECENT, true),
    workflowsOpen: readBool(PREF_WORKFLOWS, true),
    recentHeight: null, // null → auto-size next time Workflows opens
  };

  let allWorkflows = [];
  const projectWorkspaceStateFactory = global.DarklabProjectWorkspaceState
    && global.DarklabProjectWorkspaceState.createProjectWorkspaceState;
  if (typeof projectWorkspaceStateFactory !== 'function') throw new Error('DarklabProjectWorkspaceState is unavailable');
  const projectWorkspaceState = projectWorkspaceStateFactory();
  // ── Layout application ──────────────────────────────────────────
  function applyCollapsed() {
    rail.classList.toggle('rail-collapsed', ui.collapsed);
    rail.classList.toggle('rail-narrow-brand', !ui.collapsed && ui.railW <= NARROW_BRAND_W);
    rail.style.setProperty('--rail-w', ui.collapsed ? '44px' : `${ui.railW}px`);
    if (railCollapseBtn) {
      railCollapseBtn.textContent = ui.collapsed ? '»' : '«';
      const label = ui.collapsed ? 'Expand sidebar (Alt+\\)' : 'Collapse sidebar (Alt+\\)';
      railCollapseBtn.title = label;
      railCollapseBtn.setAttribute('aria-label', label);
    }
  }

  function applyWidth() {
    rail.classList.toggle('rail-narrow-brand', !ui.collapsed && ui.railW <= NARROW_BRAND_W);
    if (!ui.collapsed) rail.style.setProperty('--rail-w', `${ui.railW}px`);
  }

  function applySectionsState() {
    if (!railSplitArea) return;
    railSectionRecent?.classList.toggle('closed', !ui.recentOpen);
    railSectionWorkflows?.classList.toggle('closed', !ui.workflowsOpen);

    const bothOpen = ui.recentOpen && ui.workflowsOpen;
    railSplitArea.classList.toggle('both-open', bothOpen);
    railSplitArea.classList.toggle('workflows-closed', !ui.workflowsOpen);
    railSplitArea.classList.toggle('recent-fixed', bothOpen && ui.recentHeight != null);

    if (railSplitter) railSplitter.hidden = !bothOpen;

    if (bothOpen && ui.recentHeight != null) {
      railSplitArea.style.setProperty('--recent-h', `${ui.recentHeight}px`);
    } else {
      railSplitArea.style.removeProperty('--recent-h');
    }
  }

  // ── Collapse ─────────────────────────────────────────────────────
  function setCollapsed(next) {
    ui.collapsed = !!next;
    applyCollapsed();
    writePref(PREF_COLLAPSED, ui.collapsed ? '1' : '0');
  }
  railCollapseBtn?.addEventListener('click', () => setCollapsed(!ui.collapsed));

  // ── Horizontal drag ──────────────────────────────────────────────
  let railDrag = null;
  function beginRailDrag(clientX) {
    railDrag = { startX: clientX, startW: ui.railW };
    rail.classList.add('rail-dragging');
    document.body.style.cursor = 'ew-resize';
    document.body.style.userSelect = 'none';
  }
  railResizeHandle?.addEventListener('mousedown', e => {
    if (ui.collapsed) return;
    e.preventDefault();
    beginRailDrag(e.clientX);
  });

  // ── Splitter drag ────────────────────────────────────────────────
  let splitterDrag = null;
  function beginSplitterDrag(clientY) {
    if (!railSplitArea) return;
    splitterDrag = { rect: railSplitArea.getBoundingClientRect() };
    rail.classList.add('rail-dragging');
    document.body.style.cursor = 'ns-resize';
    document.body.style.userSelect = 'none';
  }
  railSplitter?.addEventListener('mousedown', e => {
    e.preventDefault();
    beginSplitterDrag(e.clientY);
  });

  function clampRecentHeight(pixels) {
    if (!railSplitArea) return pixels;
    const areaH = railSplitArea.getBoundingClientRect().height;
    return Math.max(MIN_SECTION_H, Math.min(areaH - MIN_SECTION_H - 6, pixels));
  }

  window.addEventListener('mousemove', e => {
    if (railDrag) {
      const next = Math.max(MIN_W, Math.min(MAX_W, railDrag.startW + (e.clientX - railDrag.startX)));
      ui.railW = next;
      applyWidth();
    } else if (splitterDrag) {
      const offsetY = e.clientY - splitterDrag.rect.top;
      ui.recentHeight = clampRecentHeight(offsetY);
      applySectionsState();
    }
  });

  window.addEventListener('mouseup', () => {
    if (railDrag) {
      railDrag = null;
      writePref(PREF_WIDTH, ui.railW);
    }
    if (splitterDrag) splitterDrag = null;
    rail.classList.remove('rail-dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });

  // ── Section toggles ──────────────────────────────────────────────
  // Rail section headers own their open/closed state via bindDisclosure.
  // `panel: null` + `openClass: null` lets applySectionsState stay the sole
  // writer of the `.closed` class on the section element (it has to
  // coordinate both sections plus the splitter and sizing vars, so letting
  // the helper also toggle classes would produce double-writes). The helper
  // still owns aria-expanded on the header and the post-activation focus
  // contract.
  function onRecentToggle(open) {
    ui.recentOpen = open;
    writePref(PREF_RECENT, open ? '1' : '0');
    applySectionsState();
  }
  function onWorkflowsToggle(open) {
    ui.workflowsOpen = open;
    writePref(PREF_WORKFLOWS, open ? '1' : '0');
    applySectionsState();
  }

  if (railRecentHeader) {
    bindDisclosure(railRecentHeader, {
      panel: null,
      openClass: null,
      initialOpen: ui.recentOpen,
      onToggle: onRecentToggle,
    });
  }
  if (railWorkflowsHeader) {
    bindDisclosure(railWorkflowsHeader, {
      panel: null,
      openClass: null,
      initialOpen: ui.workflowsOpen,
      onToggle: onWorkflowsToggle,
    });
  }

  // ── Recent list rendering ───────────────────────────────────────
  function renderRailRecent() {
    if (!railRecentBody) return;
    const items = Array.isArray(global.recentPreviewHistory) ? global.recentPreviewHistory : [];
    railRecentBody.replaceChildren();
    if (railRecentCount) railRecentCount.textContent = String(items.length);

    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'rail-section-empty';
      empty.textContent = 'no commands yet';
      railRecentBody.appendChild(empty);
      return;
    }
    // Partition starred-first while preserving original recency order within
    // each group. The star toggle lives in the history drawer / mobile sheet
    // (one source of truth); the rail only reflects the state via ordering
    // and an amber left-edge stripe.
    const starred = typeof global._getStarred === 'function' ? global._getStarred() : new Set();
    const ordered = [
      ...items.filter(cmd => starred.has(cmd)),
      ...items.filter(cmd => !starred.has(cmd)),
    ];
    ordered.forEach(cmd => {
      const isStarred = starred.has(cmd);
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'rail-item' + (isStarred ? ' starred' : '');
      row.title = cmd;
      const text = document.createElement('span');
      text.className = 'rail-item-text';
      text.textContent = cmd;
      row.appendChild(text);
      row.addEventListener('click', () => {
        if (typeof setComposerValue === 'function') {
          setComposerValue(cmd, cmd.length, cmd.length);
        }
        refocusComposerAfterAction({ preventScroll: true });
        if (typeof resetCmdHistoryNav === 'function') resetCmdHistoryNav();
      });
      railRecentBody.appendChild(row);
    });
  }

  // ── Workflows list rendering ────────────────────────────────────
  function renderRailWorkflows(items) {
    allWorkflows = Array.isArray(items) ? items.slice() : [];
    if (railWorkflowsCount) railWorkflowsCount.textContent = String(allWorkflows.length);
    if (!railWorkflowsBody) return;
    railWorkflowsBody.replaceChildren();
    if (!allWorkflows.length) {
      const empty = document.createElement('div');
      empty.className = 'rail-section-empty';
      empty.textContent = 'no workflows';
      railWorkflowsBody.appendChild(empty);
      return;
    }
    allWorkflows.forEach((wf, idx) => {
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'rail-item';
      const label = wf.title || wf.name || `workflow ${idx + 1}`;
      row.title = [label, wf.description].filter(Boolean).join('\n');
      const glyph = document.createElement('span');
      glyph.className = 'drill-chev';
      glyph.setAttribute('aria-hidden', 'true');
      glyph.textContent = '›';
      const text = document.createElement('span');
      text.className = 'rail-item-text';
      text.textContent = label;
      row.appendChild(glyph);
      row.appendChild(text);
      row.addEventListener('click', () => openScopedWorkflow(idx));
      railWorkflowsBody.appendChild(row);
    });
  }

  function openScopedWorkflow(idx) {
    const item = allWorkflows[idx];
    if (!item) return;
    if (typeof renderWorkflowItems === 'function') {
      renderWorkflowItems([item], { emitCatalogEvent: false });
    }
    if (typeof openWorkflows === 'function') {
      openWorkflows();
    } else if (typeof showWorkflowsOverlay === 'function') {
      showWorkflowsOverlay();
    }
  }

  // ── Nav menu ─────────────────────────────────────────────────────
  // The visible rail is the desktop source of truth. Route clicks directly
  // into the shared action layer.
  function positionRailMoreMenu() {
    if (!railMoreBtn || !railMoreMenu || railMoreMenu.classList.contains('u-hidden')) return;
    if (typeof railMoreBtn.getBoundingClientRect !== 'function') return;
    const triggerRect = railMoreBtn.getBoundingClientRect();
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1024;
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 768;
    const gutter = 8;
    const menuWidth = Math.max(railMoreMenu.offsetWidth || 220, 180);
    const menuHeight = Math.max(railMoreMenu.offsetHeight || railMoreMenu.getBoundingClientRect?.().height || 1, 1);
    const maxMenuHeight = Math.max(120, viewportHeight - (gutter * 2));
    const effectiveMenuHeight = Math.min(menuHeight, maxMenuHeight);
    const desiredArrowFromBottom = 32;
    const triggerCenterY = triggerRect.top + (triggerRect.height / 2);
    const preferredTop = triggerCenterY - Math.max(28, effectiveMenuHeight - desiredArrowFromBottom);
    const top = Math.min(
      Math.max(gutter, preferredTop),
      Math.max(gutter, viewportHeight - effectiveMenuHeight - gutter),
    );
    const left = Math.min(
      Math.max(gutter, triggerRect.right + 8),
      Math.max(gutter, viewportWidth - menuWidth - gutter),
    );
    const arrowLimit = Math.max(18, effectiveMenuHeight - 18);
    const arrowY = Math.min(arrowLimit, Math.max(18, triggerCenterY - top - 4));
    railMoreMenu.style.position = 'fixed';
    railMoreMenu.style.left = `${left}px`;
    railMoreMenu.style.top = `${top}px`;
    railMoreMenu.style.right = 'auto';
    railMoreMenu.style.bottom = 'auto';
    railMoreMenu.style.maxHeight = `${maxMenuHeight}px`;
    railMoreMenu.style.overflowY = menuHeight > maxMenuHeight ? 'auto' : '';
    railMoreMenu.style.setProperty('--rail-more-arrow-y', `${arrowY}px`);
  }

  function closeRailMoreMenu() {
    if (!railMoreBtn || !railMoreMenu) return;
    railMoreBtn.setAttribute('aria-expanded', 'false');
    railMoreMenu.classList.add('u-hidden');
    railMoreMenu.style.position = '';
    railMoreMenu.style.left = '';
    railMoreMenu.style.top = '';
    railMoreMenu.style.right = '';
    railMoreMenu.style.bottom = '';
    railMoreMenu.style.maxHeight = '';
    railMoreMenu.style.overflowY = '';
    railMoreMenu.style.removeProperty('--rail-more-arrow-y');
  }

  function openRailMoreMenu() {
    if (!railMoreBtn || !railMoreMenu) return;
    railMoreBtn.setAttribute('aria-expanded', 'true');
    railMoreMenu.classList.remove('u-hidden');
    positionRailMoreMenu();
    railMoreMenu.querySelector('[data-action]:not(.u-hidden)')?.focus?.();
  }

  function toggleRailMoreMenu() {
    if (railMoreBtn?.getAttribute('aria-expanded') === 'true') {
      closeRailMoreMenu();
    } else {
      openRailMoreMenu();
    }
  }

  railNav?.addEventListener('click', e => {
    const item = e.target.closest?.('[data-action]');
    if (!item) return;
    const action = item.dataset.action;
    if (action === 'diag') {
      closeRailMoreMenu();
      return; // native <a> navigation
    }
    e.preventDefault();
    if (action === 'rail-more') {
      toggleRailMoreMenu();
      return;
    }
    closeRailMoreMenu();
    if (action === 'history' && typeof global.toggleHistoryPanelSurface === 'function') {
      global.toggleHistoryPanelSurface();
      return;
    }
    if (action === 'atlas' && typeof global.openAtlas === 'function') {
      void global.openAtlas({ source: 'rail' });
      return;
    }
    if (action === 'findings-board' && typeof global.openFindingsBoard === 'function') {
      void global.openFindingsBoard({ source: 'rail' });
      return;
    }
    if (action === 'status-monitor' && typeof global.openStatusMonitor === 'function') {
      void global.openStatusMonitor({ source: 'rail' });
      return;
    }
    if (action === 'command-registry' && typeof global.openCommandRegistry === 'function') {
      global.openCommandRegistry();
      return;
    }
    if (action === 'schedules' && typeof global.openSchedulesModal === 'function') {
      void global.openSchedulesModal();
      return;
    }
    if (action === 'watchers' && typeof global.openWatchersModal === 'function') {
      void global.openWatchersModal();
      return;
    }
    if (action === 'projects' && typeof global.openProjectWorkspace === 'function') {
      void global.openProjectWorkspace();
      return;
    }
    if (action === 'options' && typeof global.openOptions === 'function') {
      global.openOptions();
      return;
    }
    if (action === 'theme' && typeof global.openThemeSelector === 'function') {
      global.openThemeSelector();
      return;
    }
    if (action === 'workspace' && typeof global.openWorkspace === 'function') {
      global.openWorkspace();
      return;
    }
    if (action === 'faq' && typeof global.openFaq === 'function') {
      global.openFaq();
    }
  });

  document.addEventListener('click', event => {
    if (!railMoreMenu || railMoreMenu.classList.contains('u-hidden')) return;
    const target = event.target;
    if (target instanceof Node && railNav?.contains(target)) return;
    closeRailMoreMenu();
  });

  railNav?.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      closeRailMoreMenu();
      railMoreBtn?.focus?.();
    }
  });

  window.addEventListener('resize', positionRailMoreMenu);

  let hudProjectMenu = null;
  let hudProjectMenuSearchInput = null;
  let hudProjectMenuProjects = null;
  let hudProjectMenuNote = null;
  let hudProjectMenuSearchTimer = null;
  let hudProjectMenuRequestId = 0;

  function _isHudProjectMenuOpen() {
    return !!(hudProjectMenu && !hudProjectMenu.classList.contains('u-hidden'));
  }

  function _openProjectsFromHudMenu(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    closeHudProjectMenu();
    if (typeof global.openProjectWorkspace === 'function') {
      void global.openProjectWorkspace();
    }
  }

  function _canCreateProjectFromHud() {
    return typeof global.activeTeamScopeCan === 'function' ? global.activeTeamScopeCan('mutate_projects') : true;
  }

  function _projectCreateDeniedTitle() {
    return typeof global.teamScopeDeniedMessage === 'function'
      ? global.teamScopeDeniedMessage('create team projects')
      : "View-only team members can't create team projects. Switch to Personal or ask for operator access.";
  }

  function _showHudProjectToast(message, tone = 'info') {
    if (typeof showToast === 'function') showToast(message, tone);
  }

  async function _hudProjectResponseMessage(resp, fallback) {
    try {
      const data = await resp.json();
      return data?.error || data?.message || fallback;
    } catch (_) {
      return fallback;
    }
  }

  function _createHudProjectMenuButton({ label, action, title = '', disabled = false, selected = false, onActivate }) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'dropdown-item dropdown-item-compact';
    btn.dataset.action = action || '';
    btn.setAttribute('role', selected ? 'menuitemradio' : 'menuitem');
    if (selected) btn.setAttribute('aria-checked', 'true');
    btn.textContent = label;
    if (title) btn.title = title;
    if (disabled) {
      btn.disabled = true;
      btn.setAttribute('aria-disabled', 'true');
    }
    if (typeof bindPressable === 'function') {
      bindPressable(btn, {
        refocusComposer: false,
        onActivate,
      });
    } else if (typeof onActivate === 'function') {
      btn.addEventListener('click', onActivate);
    }
    return btn;
  }

  function _positionHudProjectMenu() {
    if (!hudProjectMenu || !hudProjectCell || !_isHudProjectMenuOpen()) return;
    const rect = hudProjectCell.getBoundingClientRect();
    const menuWidth = hudProjectMenu.offsetWidth || 260;
    const viewportWidth = global.innerWidth || document.documentElement.clientWidth || 0;
    const left = Math.max(8, Math.min(rect.left, Math.max(8, viewportWidth - menuWidth - 8)));
    hudProjectMenu.style.left = `${left}px`;
    hudProjectMenu.style.bottom = `${Math.max(8, (global.innerHeight || 0) - rect.top - 1)}px`;
  }

  function closeHudProjectMenu({ restoreFocus = false } = {}) {
    if (!hudProjectMenu) return;
    if (hudProjectMenuSearchTimer) {
      global.clearTimeout?.(hudProjectMenuSearchTimer);
      hudProjectMenuSearchTimer = null;
    }
    hudProjectMenuRequestId += 1;
    hudProjectMenu.classList.add('u-hidden');
    hudProjectCell?.classList.remove('open');
    hudProjectCell?.setAttribute('aria-expanded', 'false');
    if (restoreFocus && hudProjectCell && typeof hudProjectCell.focus === 'function') {
      hudProjectCell.focus({ preventScroll: true });
    }
  }

  function _focusHudProjectMenuItem(delta) {
    if (!hudProjectMenu) return;
    const items = Array.from(hudProjectMenu.querySelectorAll('.dropdown-item:not([disabled])'));
    if (!items.length) return;
    const currentIdx = items.indexOf(document.activeElement);
    const fallbackIdx = delta > 0 ? -1 : 0;
    const nextIdx = (currentIdx >= 0 ? currentIdx : fallbackIdx) + delta;
    items[(nextIdx + items.length) % items.length]?.focus({ preventScroll: true });
  }

  function _setHudProjectMenuNote(text) {
    if (!hudProjectMenuNote) return;
    hudProjectMenuNote.textContent = text || '';
    hudProjectMenuNote.classList.toggle('u-hidden', !text);
  }

  function _scheduleHudProjectMenuLoad(query) {
    if (hudProjectMenuSearchTimer) {
      global.clearTimeout?.(hudProjectMenuSearchTimer);
      hudProjectMenuSearchTimer = null;
    }
    hudProjectMenuSearchTimer = global.setTimeout?.(() => {
      hudProjectMenuSearchTimer = null;
      void _loadHudProjectMenu(query);
    }, 120) || null;
  }

  async function _selectHudProject(project, event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    if (!project || !project.id) return;
    try {
      const resp = await apiFetch('/projects/active', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: project.id }),
      });
      if (!resp.ok) throw new Error(await _hudProjectResponseMessage(resp, 'Unable to set active project.'));
      const data = await resp.json();
      _setActiveProject(data?.project || project);
      closeHudProjectMenu();
      _showHudProjectToast('Active project updated.');
    } catch (err) {
      const message = err?.message || 'Unable to set active project.';
      _setHudProjectMenuNote(message);
      if (typeof logClientError === 'function') logClientError('failed to set active project from HUD switcher', err);
      _showHudProjectToast(message, 'error');
    }
  }

  async function _clearHudProject(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    try {
      const resp = await apiFetch('/projects/active', { method: 'DELETE' });
      if (!resp.ok) throw new Error(await _hudProjectResponseMessage(resp, 'Unable to clear active project.'));
      _setActiveProject(null);
      closeHudProjectMenu();
      _showHudProjectToast('Active project cleared.');
    } catch (err) {
      const message = err?.message || 'Unable to clear active project.';
      _setHudProjectMenuNote(message);
      if (typeof logClientError === 'function') logClientError('failed to clear active project from HUD switcher', err);
      _showHudProjectToast(message, 'error');
    }
  }

  function _openCreateProjectFromHudMenu(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    if (!_canCreateProjectFromHud()) {
      const message = _projectCreateDeniedTitle();
      _setHudProjectMenuNote(message);
      _showHudProjectToast(message, 'error');
      return;
    }
    closeHudProjectMenu();
    if (typeof global.openProjectWorkspace === 'function') {
      void global.openProjectWorkspace();
    }
  }

  function _renderHudProjectMenuProjects(projects, query = '') {
    if (!hudProjectMenuProjects) return;
    hudProjectMenuProjects.textContent = '';
    const activeProject = _activeProject();
    const activeProjectId = activeProject?.id ? String(activeProject.id) : '';
    const rows = Array.isArray(projects) ? projects : [];

    if (activeProjectId) {
      hudProjectMenuProjects.appendChild(_createHudProjectMenuButton({
        label: 'No project',
        action: 'clear-active-project',
        title: 'Clear active project',
        onActivate: _clearHudProject,
      }));
    }

    rows.forEach((project) => {
      if (!project || !project.id) return;
      const name = _projectDisplayName(project) || String(project.id);
      const selected = String(project.id) === activeProjectId;
      hudProjectMenuProjects.appendChild(_createHudProjectMenuButton({
        label: selected ? `${name} (active)` : name,
        action: 'select-project',
        title: selected ? `Active project: ${name}` : `Set active project: ${name}`,
        selected,
        onActivate: event => _selectHudProject(project, event),
      }));
    });

    if (!hudProjectMenuProjects.children.length) {
      _setHudProjectMenuNote(query ? 'No matching projects.' : 'No projects yet.');
    } else {
      _setHudProjectMenuNote('');
    }
    _positionHudProjectMenu();
  }

  async function _loadHudProjectMenu(query = '') {
    if (!hudProjectMenuProjects) return;
    const requestId = ++hudProjectMenuRequestId;
    const trimmedQuery = String(query || '').trim();
    const params = new URLSearchParams({ mode: 'switcher', limit: '8' });
    if (trimmedQuery) params.set('q', trimmedQuery);
    if (!hudProjectMenuProjects.children.length) {
      _setHudProjectMenuNote('Loading projects...');
    }
    try {
      const resp = await apiFetch(`/projects?${params.toString()}`, { cache: 'no-store' });
      if (requestId !== hudProjectMenuRequestId) return;
      if (!resp.ok) throw new Error(await _hudProjectResponseMessage(resp, 'Unable to load projects.'));
      const data = await resp.json();
      if (requestId !== hudProjectMenuRequestId) return;
      _renderHudProjectMenuProjects(data?.projects || [], trimmedQuery);
    } catch (err) {
      if (requestId !== hudProjectMenuRequestId) return;
      const message = err?.message || 'Unable to load projects.';
      hudProjectMenuProjects.textContent = '';
      _setHudProjectMenuNote(message);
      if (typeof logClientError === 'function') logClientError('failed to load HUD project switcher', err);
    }
  }

  function _refreshHudProjectCreateAction() {
    const createBtn = hudProjectMenu?.querySelector('[data-action="create-project"]');
    if (!createBtn) return;
    const allowed = _canCreateProjectFromHud();
    createBtn.disabled = !allowed;
    createBtn.setAttribute('aria-disabled', allowed ? 'false' : 'true');
    createBtn.title = allowed ? 'Open Projects to create a project' : _projectCreateDeniedTitle();
  }

  function _ensureHudProjectMenu() {
    if (hudProjectMenu) return hudProjectMenu;
    const menu = document.createElement('div');
    menu.id = 'hud-project-menu';
    menu.className = 'hud-project-menu dropdown-surface dropdown-up u-hidden';
    menu.setAttribute('role', 'menu');
    menu.setAttribute('aria-label', 'Active project switcher');

    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'hud-project-search';
    search.placeholder = 'search projects';
    search.setAttribute('aria-label', 'Search projects');
    search.autocomplete = 'off';
    search.spellcheck = false;
    search.addEventListener('click', event => event.stopPropagation());
    search.addEventListener('input', event => {
      event.stopPropagation();
      _scheduleHudProjectMenuLoad(search.value);
    });
    search.addEventListener('keydown', event => {
      event.stopPropagation();
      if (event.key === 'Escape') {
        event.preventDefault();
        closeHudProjectMenu({ restoreFocus: true });
      } else if (event.key === 'ArrowDown') {
        event.preventDefault();
        _focusHudProjectMenuItem(1);
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        _focusHudProjectMenuItem(-1);
      } else if (event.key === 'Tab') {
        closeHudProjectMenu();
      }
    });
    menu.appendChild(search);

    const projectsSection = document.createElement('div');
    projectsSection.className = 'hud-project-menu-section';
    menu.appendChild(projectsSection);

    const note = document.createElement('div');
    note.className = 'hud-project-menu-note u-hidden';
    menu.appendChild(note);

    const divider = document.createElement('div');
    divider.className = 'hud-project-menu-divider';
    menu.appendChild(divider);

    const createProject = _createHudProjectMenuButton({
      label: 'Create project',
      action: 'create-project',
      title: 'Open Projects to create a project',
      disabled: !_canCreateProjectFromHud(),
      onActivate: _openCreateProjectFromHudMenu,
    });
    menu.appendChild(createProject);

    const openProjects = _createHudProjectMenuButton({
      label: 'Open Projects',
      action: 'open-projects',
      onActivate: _openProjectsFromHudMenu,
    });
    menu.appendChild(openProjects);

    menu.addEventListener('click', event => event.stopPropagation());
    menu.addEventListener('keydown', event => {
      event.stopPropagation();
      if (event.key === 'Escape') {
        event.preventDefault();
        closeHudProjectMenu({ restoreFocus: true });
      } else if (event.key === 'ArrowDown') {
        event.preventDefault();
        _focusHudProjectMenuItem(1);
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        _focusHudProjectMenuItem(-1);
      } else if (event.key === 'Tab') {
        closeHudProjectMenu();
      }
    });

    document.body.appendChild(menu);
    hudProjectMenu = menu;
    hudProjectMenuSearchInput = search;
    hudProjectMenuProjects = projectsSection;
    hudProjectMenuNote = note;

    if (typeof bindOutsideClickClose === 'function') {
      bindOutsideClickClose(menu, {
        capture: true,
        triggers: hudProjectCell,
        isOpen: _isHudProjectMenuOpen,
        onClose: () => closeHudProjectMenu(),
      });
    }
    return hudProjectMenu;
  }

  function toggleHudProjectMenu(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    _closeHudSaveMenu();
    _ensureHudProjectMenu();
    if (_isHudProjectMenuOpen()) {
      closeHudProjectMenu({ restoreFocus: true });
      return;
    }
    hudProjectMenu.classList.remove('u-hidden');
    hudProjectCell?.classList.add('open');
    hudProjectCell?.setAttribute('aria-expanded', 'true');
    _refreshHudProjectCreateAction();
    if (hudProjectMenuSearchInput) hudProjectMenuSearchInput.value = '';
    _renderHudProjectMenuProjects([], '');
    void _loadHudProjectMenu('');
    _positionHudProjectMenu();
    requestAnimationFrame(_positionHudProjectMenu);
    hudProjectMenuSearchInput?.focus({ preventScroll: true });
  }

  if (hudProjectCell && typeof bindPressable === 'function') {
    bindPressable(hudProjectCell, {
      refocusComposer: false,
      onActivate: toggleHudProjectMenu,
    });
  } else {
    hudProjectCell?.addEventListener('click', toggleHudProjectMenu);
    hudProjectCell?.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') toggleHudProjectMenu(event);
    });
  }
  global.addEventListener?.('resize', _positionHudProjectMenu);
  global.addEventListener?.('scroll', _positionHudProjectMenu, true);
  document.addEventListener?.('app:active-project-changed', () => {
    if (!_isHudProjectMenuOpen()) return;
    _refreshHudProjectCreateAction();
    void _loadHudProjectMenu(hudProjectMenuSearchInput?.value || '');
  });
  document.addEventListener?.('app:scope-changed', () => {
    closeHudProjectMenu();
    loadActiveProjectContext().catch(() => {});
  });
  document.addEventListener?.('app:scope-capabilities-changed', () => {
    _refreshHudProjectCreateAction();
  });

  // ── HUD action buttons ──────────────────────────────────────────
  // Desktop-only mirror of the per-tab `.terminal-actions` footer. Each
  // button resolves the active tab at click time so no per-tab wiring is
  // needed; the per-tab footer still exists in the DOM for mobile.
  const hudActions = document.getElementById('hud-actions');
  let hudKillBtn = null;
  let hudShareSnapshotBtn = null;

  function _currentTabId() {
    return (typeof getActiveTabId === 'function') ? getActiveTabId() : null;
  }

  function _closeHudSaveMenu() {
    document.querySelectorAll('.hud-save-wrap.open').forEach(w => w.classList.remove('open'));
  }

  function _makeHudBtn(label, action, onClick, cls = 'btn btn-secondary btn-compact', title = '') {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = cls;
    btn.textContent = label;
    if (action) btn.dataset.action = action;
    if (title) btn.title = title;
    // save-menu is a disclosure trigger: suppress auto-refocus so the dropdown
    // retains user attention. Every other HUD button returns focus to the
    // composer after activation.
    const isDisclosure = action === 'save-menu';
    bindPressable(btn, {
      refocusComposer: !isDisclosure,
      onActivate: e => {
        e.preventDefault();
        onClick(e, btn);
      },
    });
    return btn;
  }

  function _bindProjectRuntimePressable(el, options = {}) {
    if (el && typeof bindPressable === 'function') {
      bindPressable(el, { onActivate: () => {}, refocusComposer: false, ...options });
    }
    return el;
  }

  function _canCreateHudShareSnapshot() {
    return typeof activeTeamScopeCan === 'function' ? activeTeamScopeCan('manage_history') : true;
  }

  function _hudShareSnapshotDeniedTitle() {
    return typeof teamScopeDeniedMessage === 'function'
      ? teamScopeDeniedMessage('create team history snapshots')
      : "View-only team members can't create team history snapshots. Switch to Personal or ask for operator access.";
  }

  function _refreshHudShareSnapshotState() {
    if (!hudShareSnapshotBtn) return;
    const allowed = _canCreateHudShareSnapshot();
    hudShareSnapshotBtn.disabled = !allowed;
    hudShareSnapshotBtn.title = allowed
      ? 'Share tab as permalink (Option+P / Alt+P)'
      : _hudShareSnapshotDeniedTitle();
  }

  function buildHudActions() {
    if (!hudActions) return;
    hudActions.replaceChildren();

    hudKillBtn = _makeHudBtn('\u25A0 Kill', 'kill', () => {
      const id = _currentTabId();
      if (id && typeof confirmKill === 'function') confirmKill(id);
    }, 'btn btn-destructive btn-compact u-hidden', 'Kill current run');
    hudActions.appendChild(hudKillBtn);

    hudShareSnapshotBtn = _makeHudBtn('share snapshot', 'permalink', () => {
      const id = _currentTabId();
      if (id && typeof permalinkTab === 'function') permalinkTab(id);
    }, 'btn btn-secondary btn-compact', 'Share tab as permalink (Option+P / Alt+P)');
    hudActions.appendChild(hudShareSnapshotBtn);
    _refreshHudShareSnapshotState();

    hudActions.appendChild(_makeHudBtn('copy', 'copy', () => {
      const id = _currentTabId();
      if (id && typeof copyTab === 'function') copyTab(id);
    }, 'btn btn-secondary btn-compact', 'Copy tab output (Option+Shift+C)'));

    // Save menu — shares .save-menu markup so existing CSS applies.
    const saveWrap = document.createElement('div');
    saveWrap.className = 'hud-save-wrap';
    const saveBtn = _makeHudBtn('save', 'save-menu', () => {
      closeHudProjectMenu();
      saveWrap.classList.toggle('open');
    }, 'btn btn-secondary btn-compact', 'Save tab output (txt / html / pdf)');
    const saveMenu = document.createElement('div');
    saveMenu.className = 'save-menu dropdown-surface dropdown-up';
    [
      ['Plain text (.txt)',   'save-txt',  () => { const id = _currentTabId(); if (id && typeof saveTab === 'function') saveTab(id); }],
      ['Styled HTML (.html)', 'save-html', () => { const id = _currentTabId(); if (id && typeof exportTabHtml === 'function') exportTabHtml(id); }],
      ['PDF document (.pdf)', 'save-pdf',  () => { const id = _currentTabId(); if (id && typeof exportTabPdf === 'function') exportTabPdf(id); }],
    ].forEach(([label, action, fn]) => {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'dropdown-item dropdown-item-compact';
      item.textContent = label;
      item.dataset.action = action;
      bindPressable(item, {
        onActivate: e => {
          e.preventDefault();
          e.stopPropagation();
          saveWrap.classList.remove('open');
          fn();
        },
      });
      saveMenu.appendChild(item);
    });
    saveWrap.appendChild(saveBtn);
    saveWrap.appendChild(saveMenu);
    hudActions.appendChild(saveWrap);

    hudActions.appendChild(_makeHudBtn('clear', 'clear', () => {
      const id = _currentTabId();
      if (!id) return;
      if (typeof cancelWelcome === 'function') cancelWelcome(id);
      if (typeof clearTab === 'function') clearTab(id, { preserveRunState: true });
    }, 'btn btn-secondary btn-compact', 'Clear active tab (Ctrl+L)'));

    bindOutsideClickClose(saveWrap, {
      triggers: saveBtn,
      isOpen: () => saveWrap.classList.contains('open'),
      onClose: () => _closeHudSaveMenu(),
    });
  }

  function _setHudKillVisible(show) {
    if (!hudKillBtn) return;
    hudKillBtn.classList.toggle('u-hidden', !show);
  }

  function refreshHudActions(tabId) {
    const id = tabId || _currentTabId();
    const tab = (typeof getTab === 'function') ? getTab(id) : null;
    _setHudKillVisible(!!(tab && tab.st === 'running'));
    _refreshHudShareSnapshotState();
  }

  buildHudActions();
  document.addEventListener('app:scope-changed', () => {
    _refreshHudShareSnapshotState();
  });
  document.addEventListener('app:scope-capabilities-changed', () => {
    _refreshHudShareSnapshotState();
  });

  // ── HUD metrics ─────────────────────────────────────────────────
  // Live-updating pills on the left side of the HUD. State is owned here;
  // setters are exposed on `global` so runner.js and session.js can push in.
  const STATUS_POLL_VISIBLE_MS = 3000;
  const STATUS_POLL_HIDDEN_MS  = 15000;
  const CLOCK_TICK_MS          = 1000;
  const LAT_WARN_MS            = 250;
  const LAT_BAD_MS             = 500;

  const hudState = {
    lastExit: null,     // number | 'killed' | null
    latencyMs: null,    // number | null
    serverUptime: null, // seconds as reported by /status
    serverUptimeAt: 0,  // performance.now() when serverUptime was recorded
    db: null,           // 'ok' | 'down' | null
    redis: null,        // 'ok' | 'down' | 'none' | null
  };
  let hudStatusPollTimer = null;

  function _setValueColor(el, variant) {
    if (!el) return;
    el.classList.remove('hud-value-green', 'hud-value-amber', 'hud-value-red', 'hud-muted');
    if (variant) el.classList.add(variant);
  }

  function _formatUptime(totalSeconds) {
    if (!Number.isFinite(totalSeconds) || totalSeconds < 0) return '—';
    const s = Math.floor(totalSeconds);
    if (s < 60) return `${s}s`;
    if (s < 3600) {
      const m = Math.floor(s / 60);
      const r = s % 60;
      return r ? `${m}m ${r}s` : `${m}m`;
    }
    if (s < 86400) {
      const h = Math.floor(s / 3600);
      const m = Math.floor((s % 3600) / 60);
      return m ? `${h}h ${m}m` : `${h}h`;
    }
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    return h ? `${d}d ${h}h` : `${d}d`;
  }

  function _formatUtcClock(ms) {
    const d = new Date(Number.isFinite(ms) ? ms : Date.now());
    const pad = n => String(n).padStart(2, '0');
    return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} UTC`;
  }

  function _formatOffsetLabel(minutesEastOfUtc) {
    const totalMinutes = Number.isFinite(minutesEastOfUtc) ? minutesEastOfUtc : 0;
    if (totalMinutes === 0) return 'UTC';
    const sign = totalMinutes >= 0 ? '+' : '-';
    const absMinutes = Math.abs(totalMinutes);
    const hours = String(Math.floor(absMinutes / 60)).padStart(2, '0');
    const minutes = String(absMinutes % 60).padStart(2, '0');
    return `GMT${sign}${hours}:${minutes}`;
  }

  function _getLocalClockLabel(d) {
    try {
      const tzName = new Intl.DateTimeFormat([], { timeZoneName: 'short' })
        .formatToParts(d)
        .find(part => part.type === 'timeZoneName')
        ?.value
        ?.trim();
      if (tzName && !/^GMT(?:[+-]\d{1,2}(?::\d{2})?)?$/i.test(tzName) && !/^UTC(?:[+-]\d{1,2}(?::\d{2})?)?$/i.test(tzName)) {
        return tzName;
      }
    } catch (_) {
      // Fall through to the numeric offset label below.
    }
    return _formatOffsetLabel(-d.getTimezoneOffset());
  }

  function _formatLocalClock(ms) {
    const d = new Date(Number.isFinite(ms) ? ms : Date.now());
    const pad = n => String(n).padStart(2, '0');
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())} ${_getLocalClockLabel(d)}`;
  }

  function _renderLastExit() {
    if (!hudLastExitEl) return;
    const v = hudState.lastExit;
    const list = Array.isArray(global.tabs) ? global.tabs : [];
    const activeRunning = list.some(t => t && t.id === global.activeTabId && t.st === 'running');
    if (v === null || v === undefined) {
      hudLastExitEl.textContent = '—';
      _setValueColor(hudLastExitEl, 'hud-muted');
    } else if (v === 'killed') {
      hudLastExitEl.textContent = 'KILLED';
      _setValueColor(hudLastExitEl, activeRunning ? 'hud-muted' : 'hud-value-red');
    } else if (v === 0) {
      hudLastExitEl.textContent = '0';
      _setValueColor(hudLastExitEl, activeRunning ? 'hud-muted' : 'hud-value-green');
    } else {
      hudLastExitEl.textContent = String(v);
      _setValueColor(hudLastExitEl, activeRunning ? 'hud-muted' : 'hud-value-red');
    }
  }

  function _renderLatency() {
    if (!hudLatencyEl) return;
    const ms = hudState.latencyMs;
    if (ms === null || ms === undefined) {
      hudLatencyEl.textContent = '— ms';
      _setValueColor(hudLatencyEl, 'hud-muted');
      return;
    }
    hudLatencyEl.textContent = `${Math.round(ms)} ms`;
    if (ms >= LAT_BAD_MS) _setValueColor(hudLatencyEl, 'hud-value-red');
    else if (ms >= LAT_WARN_MS) _setValueColor(hudLatencyEl, 'hud-value-amber');
    else _setValueColor(hudLatencyEl, 'hud-value-green');
  }

  function _renderTabs() {
    if (!hudTabsEl) return;
    const list = Array.isArray(global.tabs) ? global.tabs : [];
    const running = list.reduce((n, t) => n + (t && t.st === 'running' ? 1 : 0), 0);
    const total = list.length;
    if (!total) hudTabsEl.textContent = '0';
    else if (running > 0) hudTabsEl.textContent = `${total} · ${running} active`;
    else hudTabsEl.textContent = String(total);
    _setValueColor(hudTabsEl, running > 0 ? 'hud-value-amber' : 'hud-muted');
  }

  function _renderSession() {
    if (!hudSessionEl) return;
    // Read directly from window storage: SESSION_ID in session.js is declared
    // with `let` so it is not attached to window; localStorage is the
    // underlying source of truth and updates synchronously across all paths
    // that change the active session token.
    let token = '';
    try { token = global.localStorage?.getItem('session_token') || ''; } catch (_) {}
    if (token && token.startsWith('tok_')) {
      const masked = (typeof maskSessionToken === 'function') ? maskSessionToken(token) : token;
      hudSessionEl.textContent = masked;
      hudSessionEl.title = `Active session token (${masked})`;
      _setValueColor(hudSessionEl, 'hud-value-green');
    } else {
      hudSessionEl.textContent = 'ANON';
      hudSessionEl.title = 'Anonymous UUID session — generate a token in Options to carry history across devices';
      _setValueColor(hudSessionEl, 'hud-muted');
    }
  }

  let projectSharedUiController = null;

  function _projectSharedUiController() {
    if (projectSharedUiController) return projectSharedUiController;
    const factory = global.DarklabProjectSharedUi && global.DarklabProjectSharedUi.createProjectSharedUiController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectSharedUi is unavailable');
    projectSharedUiController = factory({
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      downloadBlobAsAttachment,
      downloadUrlAsAttachment,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
    });
    return projectSharedUiController;
  }

  function _projectDisplayName(project) {
    return _projectSharedUiController().displayName(project);
  }

  let projectActiveContextController = null;

  function _projectActiveContextController() {
    if (projectActiveContextController) return projectActiveContextController;
    const factory = global.DarklabProjectActiveContext
      && global.DarklabProjectActiveContext.createProjectActiveContextController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectActiveContext is unavailable');
    projectActiveContextController = factory({
      apiFetch,
      emitUiEvent: (eventName, detail) => {
        if (typeof emitUiEvent === 'function') emitUiEvent(eventName, detail);
      },
      hudProjectCell,
      hudProjectEl,
      isProjectWorkspaceOpen,
      logClientError: (message, err, details) => {
        if (typeof logClientError === 'function') logClientError(message, err, details);
      },
      projectDisplayName: _projectDisplayName,
      railNav,
      refreshProjectWorkspace,
      setValueColor: _setValueColor,
      showToast: typeof showToast === 'function' ? showToast : null,
      syncProjectNotesForm: _syncProjectNotesForm,
    });
    return projectActiveContextController;
  }

  function _activeProject() {
    return _projectActiveContextController().project();
  }

  function _setActiveProject(project) {
    return _projectActiveContextController().setProject(project);
  }

  function _renderActiveProject() {
    _projectActiveContextController().render();
  }

  async function loadActiveProjectContext() {
    return _projectActiveContextController().load();
  }

  let projectWorkspaceShellController = null;

  function _projectWorkspaceShellController() {
    if (projectWorkspaceShellController) return projectWorkspaceShellController;
    const factory = global.DarklabProjectWorkspaceShell
      && global.DarklabProjectWorkspaceShell.createProjectWorkspaceShellController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectWorkspaceShell is unavailable');
    projectWorkspaceShellController = factory({
      EntityMetadataClient,
      blurVisibleComposerInputIfMobile: () => {
        if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
      },
      closeMajorOverlays: () => {
        if (typeof global._closeMajorOverlays === 'function') global._closeMajorOverlays();
      },
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectMobileActionSheet: _closeProjectMobileActionSheet,
      closeProjectMobileCompareSheet: _closeProjectMobileCompareSheet,
      closeProjectPackageManifest: _closeProjectPackageManifest,
      closeProjectPackageWizard: _closeProjectPackageWizard,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      emitUiEvent: (eventName, detail) => {
        if (typeof emitUiEvent === 'function') emitUiEvent(eventName, detail);
      },
      flushProjectNotesAutosave: _flushProjectNotesAutosave,
      markInteractionSurfaceReady: (surfaceName, overlay, modal) => {
        if (typeof markInteractionSurfaceReady === 'function') markInteractionSurfaceReady(surfaceName, overlay, modal);
      },
      projectEntitiesController: _projectEntitiesController,
      projectWorkspaceBody,
      projectWorkspaceBroadcastKey: PROJECT_WORKSPACE_CONSTANTS.workspaceBroadcastKey,
      projectMobileCreateForm,
      projectMobileNameInput,
      projectWorkspaceCreateForm,
      projectWorkspaceMessage,
      projectWorkspaceModal,
      projectWorkspaceNameInput,
      projectWorkspaceOverlay,
      refocusComposerAfterAction: (options) => {
        if (typeof refocusComposerAfterAction === 'function') refocusComposerAfterAction(options);
      },
      refreshProjectWorkspace,
      selectedProjectId: () => projectWorkspaceState.selectedId(),
      setProjectMobileCreateOpen: _setProjectMobileCreateOpen,
      setProjectPaginationOffset: _setProjectPaginationOffset,
      setProjectWorkspaceTab: projectWorkspaceState.setTab,
      setSelectedProjectId: projectWorkspaceState.setSelectedId,
      showToast: typeof showToast === 'function' ? showToast : null,
    });
    return projectWorkspaceShellController;
  }

  let projectWorkspaceActionsController = null;

  function _projectWorkspaceActionsController() {
    if (projectWorkspaceActionsController) return projectWorkspaceActionsController;
    const factory = global.DarklabProjectWorkspaceActions
      && global.DarklabProjectWorkspaceActions.createProjectWorkspaceActionsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectWorkspaceActions is unavailable');
    projectWorkspaceActionsController = factory({
      EntityMetadataClient,
      apiFetch,
      projectRunItems: _projectRunItems,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      refreshProjectWorkspace,
      selectedProjectId: () => projectWorkspaceState.selectedId(),
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      showConfirm: typeof showConfirm === 'function' ? showConfirm : null,
    });
    return projectWorkspaceActionsController;
  }

  function isProjectWorkspaceOpen() {
    return _projectWorkspaceShellController().isOpen();
  }

  function _setProjectWorkspaceMessage(text = '', { error = false, toast = true } = {}) {
    _projectWorkspaceShellController().setMessage(text, { error, toast });
  }

  async function _projectResponseError(resp, fallback) {
    return _projectWorkspaceShellController().responseError(resp, fallback);
  }

  function _selectedProject() {
    return _projectWorkspaceLifecycleController().selectedProject();
  }

  function _projectSummary(projectId = projectWorkspaceState.selectedId()) {
    return _projectWorkspaceLifecycleController().projectSummary(projectId);
  }

  function _ensureSelectedProject() {
    _projectWorkspaceLifecycleController().ensureSelectedProject();
  }

  function _projectCounts(summary) {
    return _projectSharedUiController().counts(summary);
  }

  function _projectCountEntries(summary) {
    return _projectSharedUiController().countEntries(summary);
  }

  function _projectTargetItems(summary) {
    return _projectSharedUiController().targetItems(summary);
  }

  let projectEntitiesController = null;

  function _projectEntitiesController() {
    if (projectEntitiesController) return projectEntitiesController;
    const factory = global.DarklabProjectEntities && global.DarklabProjectEntities.createProjectEntitiesController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectEntities is unavailable');
    projectEntitiesController = factory({
      apiFetch,
      getSummary: projectId => projectWorkspaceState.summary(projectId),
      getActiveTab: projectWorkspaceState.entityTab,
      setActiveTab: projectWorkspaceState.setEntityTab,
      getSelectMode: projectWorkspaceState.entitySelectMode,
      setSelectMode: projectWorkspaceState.setEntitySelectMode,
      getSelectedIds: projectWorkspaceState.selectedEntityIds,
      getPicker: projectWorkspaceState.entityPicker,
      setPicker: projectWorkspaceState.setEntityPicker,
      getSelectedProjectId: projectWorkspaceState.selectedId,
      projectRows: projectWorkspaceState.rows,
      projectIsArchived: _projectIsArchived,
      formatDate: _formatProjectDate,
      shortProjectRunId: _shortProjectRunId,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      projectMobileEmptyPanel: _projectMobileEmptyPanel,
      projectItemRow: _projectItemRow,
      projectMobileContentRow: _projectMobileContentRow,
      projectMobileActionMenu: _projectMobileActionMenu,
      entityMetadataChips: _entityMetadataChips,
      projectTargetItems: _projectTargetItems,
      projectTargetFilterSet: _projectTargetFilterSet,
      projectRunFilterSet: _projectRunFilterSet,
      projectResponseError: _projectResponseError,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      refreshProjectWorkspace,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      mobileView: () => _projectMobileShellController().currentView(),
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      showConfirm: typeof showConfirm === 'function' ? showConfirm : null,
      logClientError: (message, err) => {
        if (typeof logClientError === 'function') logClientError(message, err);
      },
      downloadBlobAsAttachment: _downloadBlobAsAttachment,
      downloadUrlAsAttachment: _downloadUrlAsAttachment,
      closeProjectWorkspace,
      openAtlas: global.openAtlas,
      projectDisplayName: _projectDisplayName,
      setWorkspaceTab: projectWorkspaceState.setTab,
    });
    return projectEntitiesController;
  }

  let projectPackagesController = null;

  function _projectPackagesController() {
    if (projectPackagesController) return projectPackagesController;
    const factory = global.DarklabProjectPackages && global.DarklabProjectPackages.createProjectPackagesController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectPackages is unavailable');
    projectPackagesController = factory({
      apiFetch,
      EntityMetadataClient,
      manifestOverlay: projectPackageManifestOverlay,
      manifestTitle: projectPackageManifestTitle,
      manifestSummary: projectPackageManifestSummary,
      manifestJson: projectPackageManifestJson,
      wizardOverlay: projectPackageWizardOverlay,
      wizardBody: projectPackageWizardBody,
      getSelectedProjectId: projectWorkspaceState.selectedId,
      selectedProject: _selectedProject,
      projectSummary: _projectSummary,
      projectRunItems: _projectRunItems,
      projectArtifactItems: _projectArtifactItems,
      loadAllProjectArtifacts: _loadAllProjectArtifacts,
      projectTargetItems: _projectTargetItems,
      projectFindingItems: _projectFindingItems,
      projectFindingsLoaded: _projectFindingsLoaded,
      loadProjectFindings: _loadProjectFindings,
      projectFilesEnabled: _projectFilesEnabled,
      projectArtifactStatus: _projectArtifactStatus,
      projectArtifactDetail: _projectArtifactDetail,
      projectTargetFilterLabel: _projectTargetFilterLabel,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      entityMetadataChips: _entityMetadataChips,
      projectProvenanceSummary: _projectProvenanceSummary,
      projectProvenanceSummaryElement: _projectProvenanceSummaryElement,
      formatDate: _formatProjectDate,
      formatBytes: _formatProjectBytes,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      projectMobileEmptyPanel: _projectMobileEmptyPanel,
      projectMobileContentRow: _projectMobileContentRow,
      projectMobileActionMenu: _projectMobileActionMenu,
      projectItemRow: _projectItemRow,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      refreshProjectWorkspace,
      renderProjectExplorer: _renderProjectExplorer,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      downloadBlobAsAttachment: _downloadBlobAsAttachment,
      downloadUrlAsAttachment: _downloadUrlAsAttachment,
      setWorkspaceTab: projectWorkspaceState.setTab,
      syncProjectWorkspaceNestedSuppression: _syncProjectWorkspaceNestedSuppression,
      focusProjectNestedSheet: _focusProjectNestedSheet,
      installProjectMobileKeyboardGuards: _installProjectMobileKeyboardGuards,
    });
    return projectPackagesController;
  }

  let projectReportController = null;

  let projectActivityController = null;

  function _projectActivityController() {
    if (projectActivityController) return projectActivityController;
    const factory = global.DarklabProjectActivity && global.DarklabProjectActivity.createProjectActivityController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectActivity is unavailable');
    projectActivityController = factory({
      projectWorkspaceRequest: _projectWorkspaceRequest,
      projectResponseError: _projectResponseError,
      formatDate: _formatProjectDate,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      renderProjectExplorer: _renderProjectExplorer,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      openProjectObject: _openProjectObject,
    });
    return projectActivityController;
  }

  function _projectReportController() {
    if (projectReportController) return projectReportController;
    const factory = global.DarklabProjectReport && global.DarklabProjectReport.createProjectReportController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectReport is unavailable');
    projectReportController = factory({
      apiFetch,
      getSelectedProjectId: projectWorkspaceState.selectedId,
      selectedProject: _selectedProject,
      projectSummary: _projectSummary,
      projectRunItems: _projectRunItems,
      projectArtifactItems: _projectArtifactItems,
      loadAllProjectArtifacts: _loadAllProjectArtifacts,
      projectTargetItems: _projectTargetItems,
      projectFindingItems: _projectFindingItems,
      loadProjectFindings: _loadProjectFindings,
      projectArtifactDetail: _projectArtifactDetail,
      formatDate: _formatProjectDate,
      projectProvenanceSummaryElement: _projectProvenanceSummaryElement,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      mobileView: () => _projectMobileShellController().currentView(),
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      downloadUrlAsAttachment: _downloadUrlAsAttachment,
      showConfirm: typeof showConfirm === 'function' ? showConfirm : null,
      logClientError: (message, err) => {
        if (typeof logClientError === 'function') logClientError(message, err);
      },
    });
    return projectReportController;
  }

  let projectFiltersController = null;

  function _projectFiltersController() {
    if (projectFiltersController) return projectFiltersController;
    const factory = global.DarklabProjectFilters && global.DarklabProjectFilters.createProjectFiltersController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectFilters is unavailable');
    projectFiltersController = factory({
      getSelectedProjectId: projectWorkspaceState.selectedId,
      projectWorkspaceModal: () => projectWorkspaceModal,
      projectExplorerBody: () => projectExplorerBody,
      projectWorkspaceTab: projectWorkspaceState.tab,
      projectSummary: _projectSummary,
      findingReviewStates: PROJECT_WORKSPACE_CONSTANTS.findingReviewStates,
      findingSeverityRank: PROJECT_WORKSPACE_CONSTANTS.findingSeverityRank,
      findingReviewRank: PROJECT_WORKSPACE_CONSTANTS.findingReviewRank,
      projectFindingSortOptions: PROJECT_WORKSPACE_CONSTANTS.findingSortOptions,
      projectFindingNoteStateOptions: PROJECT_WORKSPACE_CONSTANTS.findingNoteStateOptions,
      projectFindingOrphanOptions: PROJECT_WORKSPACE_CONSTANTS.findingOrphanOptions,
      projectFindingScopeOptions: PROJECT_WORKSPACE_CONSTANTS.findingScopeOptions,
      projectFindingSeverityOptions: PROJECT_WORKSPACE_CONSTANTS.findingSeverityOptions,
      projectTargetItems: _projectTargetItems,
      projectTargetLabel: _projectTargetLabel,
      projectRunItems: _projectRunItems,
      projectRunById: _projectRunById,
      shortProjectRunId: _shortProjectRunId,
      projectFindingItems: _projectFindingItems,
      projectFilteredFindingItems: key => _projectFindingsDataController().filteredItems(key),
      hasProjectFilteredFindingsKey: key => _projectFindingsDataController().hasFilteredKey(key),
      projectArtifactItems: _projectArtifactItems,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      findingReviewStateLabel: _findingReviewStateLabel,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
    });
    return projectFiltersController;
  }

  let projectFindingsDataController = null;

  function _projectFindingsDataController() {
    if (projectFindingsDataController) return projectFindingsDataController;
    const factory = global.DarklabProjectFindingsData && global.DarklabProjectFindingsData.createProjectFindingsDataController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectFindingsData is unavailable');
    projectFindingsDataController = factory({
      apiFetch,
      selectedProjectId: projectWorkspaceState.selectedId,
      mobileView: () => _projectMobileShellController().currentView(),
      projectSummary: _projectSummary,
      findingFilteredKey: _projectFindingFilteredKey,
      findingServerFilterParams: _projectFindingServerFilterParams,
      collapsedFindingGroupLabels: _projectCollapsedFindingGroupLabels,
      filteredProjectFindings: _filteredProjectFindings,
      pageLimit: 50,
      projectResponseError: _projectResponseError,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      renderProjectPackageWizardModal: _renderProjectPackageWizardModal,
      projectPackageWizardActive: _projectPackageWizardActive,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      logClientError: (message, err) => {
        if (typeof logClientError === 'function') logClientError(message, err);
      },
    });
    return projectFindingsDataController;
  }

  let projectFindingsController = null;

  let projectFindingsBoardController = null;

  function _projectFindingsBoardController() {
    if (projectFindingsBoardController) return projectFindingsBoardController;
    const factory = global.DarklabProjectFindingsBoard
      && global.DarklabProjectFindingsBoard.createProjectFindingsBoardController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectFindingsBoard is unavailable');
    projectFindingsBoardController = factory({
      entityMetadataChipClass: _entityMetadataChipClass,
      entityMetadataChips: _entityMetadataChips,
      projectFindingTargetText: _projectFindingTargetText,
      projectTargetLabel: _projectTargetLabel,
      makeProjectButton: _makeProjectButton,
      reviewControl: (finding, projectId) => _projectFindingsController().reviewControl(finding, projectId),
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      metaSeparator: ' · ',
    });
    return projectFindingsBoardController;
  }

  function _projectFindingsController() {
    if (projectFindingsController) return projectFindingsController;
    const factory = global.DarklabProjectFindings && global.DarklabProjectFindings.createProjectFindingsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectFindings is unavailable');
    projectFindingsController = factory({
      findingReviewStates: PROJECT_WORKSPACE_CONSTANTS.findingReviewStates,
      collapsedFindingGroups: projectWorkspaceState.collapsedFindingGroups,
      collapsedFindingGroupLabels: _projectCollapsedFindingGroupLabels,
      findingsLoadingId: () => _projectFindingsDataController().loadingId(),
      hasFindings: projectId => _projectFindingsDataController().loaded(projectId),
      findingViewMode: projectWorkspaceState.findingViewMode,
      findingSelectMode: projectWorkspaceState.findingSelectMode,
      selectedFindingIds: projectWorkspaceState.selectedFindingIds,
      projectFindingPagination: (projectId, summary) => _projectFindingsDataController().page(projectId, summary),
      projectFindingItems: _projectFindingItems,
      projectFindingBoard: (projectId, summary, options) => _projectFindingsDataController().board(projectId, summary, options),
      filteredProjectFindings: _filteredProjectFindings,
      projectFindingServerFiltersActive: _projectFindingServerFiltersActive,
      findingsBoardAvailable: () => !(document.body && document.body.classList.contains('mobile-terminal-mode')),
      projectFindingTargetText: _projectFindingTargetText,
      projectTargetLabel: _projectTargetLabel,
      entityMetadataChips: _entityMetadataChips,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      renderProjectFindingBoard: (container, projectId, summary, board) => (
        _projectFindingsBoardController().renderBoard(container, projectId, summary, board)
      ),
      setFindingSelectMode: projectWorkspaceState.setFindingSelectMode,
      projectItemRow: _projectItemRow,
      groupBy: _groupBy,
      metaSeparator: ' · ',
      groupCaret: '▾',
    });
    return projectFindingsController;
  }

  let projectArtifactsController = null;

  function _projectArtifactsController() {
    if (projectArtifactsController) return projectArtifactsController;
    const factory = global.DarklabProjectArtifacts && global.DarklabProjectArtifacts.createProjectArtifactsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectArtifacts is unavailable');
    projectArtifactsController = factory({
      apiFetch,
      projectResponseError: _projectResponseError,
      collapsedArtifactGroups: projectWorkspaceState.collapsedArtifactGroups,
      filesEnabled: () => !!(typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.workspace_enabled === true),
      selectedProjectId: projectWorkspaceState.selectedId,
      projectTargetFilterActive: _projectTargetFilterActive,
      projectFindingsLoaded: _projectFindingsLoaded,
      filteredProjectArtifacts: _filteredProjectArtifacts,
      projectRunFilterSet: _projectRunFilterSet,
      projectTargetFilterSet: _projectTargetFilterSet,
      projectTargetItems: _projectTargetItems,
      projectRunById: _projectRunById,
      shortProjectRunId: _shortProjectRunId,
      entityMetadataChips: _entityMetadataChips,
      formatDate: _formatProjectDate,
      formatBytes: _formatProjectBytes,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      projectItemRow: _projectItemRow,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      mobileView: () => _projectMobileShellController().currentView(),
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      logClientError: (message, err) => {
        if (typeof logClientError === 'function') logClientError(message, err);
      },
      groupBy: _groupBy,
      downloadBlobAsAttachment: _downloadBlobAsAttachment,
      downloadUrlAsAttachment: _downloadUrlAsAttachment,
      metaSeparator: ' · ',
      groupCaret: '▾',
    });
    return projectArtifactsController;
  }

  let projectDetailsController = null;

  function _projectDetailsController() {
    if (projectDetailsController) return projectDetailsController;
    const factory = global.DarklabProjectDetails && global.DarklabProjectDetails.createProjectDetailsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectDetails is unavailable');
    projectDetailsController = factory({
      apiFetch,
      entityMetadataClient: EntityMetadataClient,
      projectNotesForm,
      projectNotesInput,
      projectLabelsForm,
      projectLabelsInput,
      projectLabelsSaveButton,
      projectWorkspaceTab: projectWorkspaceState.tab,
      selectedProject: _selectedProject,
      selectedProjectId: projectWorkspaceState.selectedId,
      projectRows: projectWorkspaceState.rows,
      setProjectRows: projectWorkspaceState.setRows,
      projectSummary: _projectSummary,
      setProjectSummary: projectWorkspaceState.setSummary,
      activeProject: _activeProject,
      setActiveProject: _setActiveProject,
      projectDisplayName: _projectDisplayName,
      projectTargetItems: _projectTargetItems,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      entityMetadataChipClass: _entityMetadataChipClass,
      projectMetaRow: _projectMetaRow,
      formatDate: _formatProjectDate,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      renderProjectTargets: _renderProjectTargets,
      projectResponseError: _projectResponseError,
      syncEntityLabels: _syncEntityLabels,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      renderProjectList: _renderProjectList,
      renderProjectExplorer: _renderProjectExplorer,
      renderActiveProject: _renderActiveProject,
      projectNotesAutosaveDelayMs: PROJECT_WORKSPACE_CONSTANTS.projectNotesAutosaveDelayMs,
    });
    return projectDetailsController;
  }

  let projectListController = null;

  function _projectListController() {
    if (projectListController) return projectListController;
    const factory = global.DarklabProjectList && global.DarklabProjectList.createProjectListController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectList is unavailable');
    projectListController = factory({
      projectWorkspaceBody,
      projectWorkspaceLoading: projectWorkspaceState.loading,
      projectRows: projectWorkspaceState.rows,
      selectedProjectId: projectWorkspaceState.selectedId,
      activeProject: _activeProject,
      projectSummary: _projectSummary,
      projectCountEntries: _projectCountEntries,
      projectArtifactsVisible: _projectArtifactsVisible,
      projectDisplayName: _projectDisplayName,
      appendProjectLabelChips: _appendProjectLabelChips,
      appendProjectMobileLabelChips: _appendProjectMobileLabelChips,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      mobileMenuText: '☰',
      mobileChevronText: '›',
      projectPagination: projectWorkspaceState.pagination,
      projectWorkspacePagination,
    });
    return projectListController;
  }

  let projectNavigationController = null;

  function _projectNavigationController() {
    if (projectNavigationController) return projectNavigationController;
    const factory = global.DarklabProjectNavigation && global.DarklabProjectNavigation.createProjectNavigationController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectNavigation is unavailable');
    projectNavigationController = factory({
      projectWorkspaceModal,
      projectMobileDetailTopbar,
      projectMobileTabs,
      activeProject: _activeProject,
      projectWorkspaceTab: projectWorkspaceState.tab,
      setProjectWorkspaceTab: projectWorkspaceState.setTab,
      projectCounts: _projectCounts,
      projectDisplayName: _projectDisplayName,
      projectIsArchived: _projectIsArchived,
      projectArtifactsVisible: _projectArtifactsVisible,
      projectTargetFilterActive: _projectTargetFilterActive,
      projectRunFilterActive: _projectRunFilterActive,
      projectFindingsLoaded: _projectFindingsLoaded,
      projectEntityTabCountText: (projectId, summary, total) => (
        _projectEntitiesController().tabCountText(projectId, summary, total)
      ),
      projectFindingPagination: _projectFindingPagination,
      projectFindingServerFiltersActive: _projectFindingServerFiltersActive,
      filteredProjectFindings: _filteredProjectFindings,
      filteredProjectRuns: _filteredProjectRuns,
      filteredProjectArtifacts: _filteredProjectArtifacts,
      appendProjectLabelChips: _appendProjectLabelChips,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      metaSeparator: ' · ',
      mobileBackText: '‹ Back',
    });
    return projectNavigationController;
  }

  let projectNestedSheetsController = null;

  function _projectNestedSheetsController() {
    if (projectNestedSheetsController) return projectNestedSheetsController;
    const factory = global.DarklabProjectNestedSheets && global.DarklabProjectNestedSheets.createProjectNestedSheetsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectNestedSheets is unavailable');
    projectNestedSheetsController = factory({
      projectWorkspaceModal,
      projectTargetEditorOverlay,
      projectEntityEditorOverlay,
      projectPackageManifestOverlay,
      projectPackageWizardOverlay,
      isProjectTargetEditorOpen: () => !!(projectTargetEditorOverlay && projectTargetEditorOverlay.classList.contains('open')),
      isProjectEntityEditorOpen: () => !!(projectEntityEditorOverlay && projectEntityEditorOverlay.classList.contains('open')),
      isProjectPackageManifestOpen: () => !!(projectPackageManifestOverlay && projectPackageManifestOverlay.classList.contains('open')),
      isProjectPackageWizardOpen: () => !!(projectPackageWizardOverlay && projectPackageWizardOverlay.classList.contains('open')),
    });
    return projectNestedSheetsController;
  }

  let projectWorkspaceRendererController = null;

  function _projectWorkspaceRendererController() {
    if (projectWorkspaceRendererController) return projectWorkspaceRendererController;
    const factory = global.DarklabProjectWorkspaceRenderer
      && global.DarklabProjectWorkspaceRenderer.createProjectWorkspaceRendererController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectWorkspaceRenderer is unavailable');
    projectWorkspaceRendererController = factory({
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      emptyProjectPanel: _emptyProjectPanel,
      enhanceAppSelects: typeof global.enhanceAppSelects === 'function' ? global.enhanceAppSelects : null,
      ensureSelectedProject: _ensureSelectedProject,
      flushProjectNotesAutosave: _flushProjectNotesAutosave,
      focusProjectWorkspaceTab: _focusProjectWorkspaceTab,
      isProjectWorkspaceOpen,
      loadProjectFilteredFindings: _loadProjectFilteredFindings,
      loadProjectFindings: _loadProjectFindings,
      mobileView: () => _projectMobileShellController().currentView(),
      projectArtifactsVisible: _projectArtifactsVisible,
      projectExplorerBody,
      projectFindingServerFiltersActive: _projectFindingServerFiltersActive,
      projectFindingsLoaded: _projectFindingsLoaded,
      projectMobileDetailBody,
      projectMobileTabItems: _projectMobileTabItems,
      projectPackageWizardActive: _projectPackageWizardActive,
      projectPagination: projectWorkspaceState.pagination,
      projectRows: projectWorkspaceState.rows,
      projectSummary: _projectSummary,
      projectTargetFilterActive: _projectTargetFilterActive,
      projectWorkspaceLoading: projectWorkspaceState.loading,
      projectWorkspaceSubtitle,
      renderProjectArtifacts: _renderProjectArtifacts,
      renderProjectDetails: _renderProjectDetails,
      renderProjectEntities: _renderProjectEntities,
      renderProjectFilterBar: _renderProjectFilterBar,
      renderProjectFindings: _renderProjectFindings,
      renderProjectHeader: _renderProjectHeader,
      renderProjectList: _renderProjectList,
      renderProjectMobile: _renderProjectMobile,
      renderProjectActivity: _renderProjectActivity,
      renderProjectPackages: _renderProjectPackages,
      renderProjectPackageWizardModal: _renderProjectPackageWizardModal,
      renderProjectReport: _renderProjectReport,
      renderProjectRuns: _renderProjectRuns,
      scheduleProjectFilterSortDividerSync: _scheduleProjectFilterSortDividerSync,
      selectedProject: _selectedProject,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      setWorkspaceTab: projectWorkspaceState.setTab,
      syncProjectFilterSortDivider: _syncProjectFilterSortDivider,
      syncProjectForms: _syncProjectForms,
      workspaceTab: projectWorkspaceState.tab,
    });
    return projectWorkspaceRendererController;
  }

  let projectWorkspaceBootstrapController = null;

  function _projectWorkspaceBootstrapController() {
    if (projectWorkspaceBootstrapController) return projectWorkspaceBootstrapController;
    const factory = global.DarklabProjectWorkspaceBootstrap
      && global.DarklabProjectWorkspaceBootstrap.createProjectWorkspaceBootstrapController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectWorkspaceBootstrap is unavailable');
    const bindDismissibleFn = global && typeof global.bindDismissible === 'function'
      ? global.bindDismissible
      : (typeof bindDismissible === 'function' ? bindDismissible : null);
    const bindMobileSheetFn = global && typeof global.bindMobileSheet === 'function'
      ? global.bindMobileSheet
      : (typeof bindMobileSheet === 'function' ? bindMobileSheet : null);
    projectWorkspaceBootstrapController = factory({
      bindDismissible: bindDismissibleFn,
      bindMobileSheet: bindMobileSheetFn,
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectPackageManifest: _closeProjectPackageManifest,
      closeProjectPackageWizard: _closeProjectPackageWizard,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      closeProjectWorkspace,
      isProjectEntityEditorOpen,
      isProjectPackageManifestOpen,
      isProjectPackageWizardOpen,
      isProjectTargetEditorOpen,
      projectDetailsController: _projectDetailsController,
      projectEntityEditorController: _projectEntityEditorController,
      projectEntityEditorOverlay,
      projectMobileTabs,
      projectPackageManifestOverlay,
      projectPackageWizardOverlay,
      projectActivityController: _projectActivityController,
      projectPackagesController: _projectPackagesController,
      projectTargetEditorOverlay,
      projectTargetsController: _projectTargetsController,
      projectWorkspaceEventsController: _projectWorkspaceEventsController,
      projectWorkspaceOverlay,
      projectWorkspaceShellController: _projectWorkspaceShellController,
      syncProjectMobileTabEdges: _syncProjectMobileTabEdges,
    });
    return projectWorkspaceBootstrapController;
  }

  let projectTargetsController = null;

  function _projectTargetsController() {
    if (projectTargetsController) return projectTargetsController;
    const factory = global.DarklabProjectTargets && global.DarklabProjectTargets.createProjectTargetsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectTargets is unavailable');
    projectTargetsController = factory({
      EntityMetadataClient,
      targetHelpers: PROJECT_TARGET_HELPERS,
      overlay: projectTargetEditorOverlay,
      form: projectTargetCreateForm,
      typeSelect: projectTargetTypeSelect,
      valueInput: projectTargetValueInput,
      valueHelp: projectTargetValueHelp,
      valueError: projectTargetValueError,
      labelInput: projectTargetLabelInput,
      notesInput: projectTargetNotesInput,
      title: projectTargetEditorTitle,
      submitButton: projectTargetSubmitButton,
      getLastTargetType: projectWorkspaceState.lastTargetType,
      setLastTargetType: projectWorkspaceState.setLastTargetType,
      setEditingTargetId: projectWorkspaceState.setEditingTargetId,
      selectedProjectId: projectWorkspaceState.selectedId,
      activeProject: _activeProject,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      entityMetadataChips: _entityMetadataChips,
      entityMetadataChipClass: _entityMetadataChipClass,
      makeProjectButton: _makeProjectButton,
      emptyProjectPanel: _emptyProjectPanel,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      syncEntityLabels: _syncEntityLabels,
      syncEntityNote: _syncEntityNote,
      refreshProjectWorkspace,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectWorkspace: _renderProjectWorkspace,
      invalidateProjectTargetPage: projectId => _projectDetailsController().invalidateTargetPage(projectId),
      loadProjectTargetPage: (projectId, options) => _projectDetailsController().loadTargetPage(projectId, options),
      renderProjectMobileDetail: _renderProjectMobileDetail,
      loadProjectAutocompleteTargets: () => {
        if (typeof loadProjectAutocompleteTargets === 'function') {
          loadProjectAutocompleteTargets().catch(() => {});
        }
      },
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      syncProjectWorkspaceNestedSuppression: _syncProjectWorkspaceNestedSuppression,
      installProjectMobileKeyboardGuards: _installProjectMobileKeyboardGuards,
      focusProjectNestedSheet: _focusProjectNestedSheet,
    });
    return projectTargetsController;
  }

  let projectRunsController = null;

  function _projectRunsController() {
    if (projectRunsController) return projectRunsController;
    const factory = global.DarklabProjectRuns && global.DarklabProjectRuns.createProjectRunsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectRuns is unavailable');
    projectRunsController = factory({
      apiFetch,
      projectResponseError: _projectResponseError,
      projectExplorerBody: () => projectExplorerBody,
      projectRunItems: _projectRunItems,
      projectComparableRuns: _projectComparableRuns,
      projectFindingItems: _projectFindingItems,
      projectFindingsLoaded: _projectFindingsLoaded,
      projectArtifactItems: _projectArtifactItems,
      projectArtifactsVisible: _projectArtifactsVisible,
      projectTargetFilterActive: _projectTargetFilterActive,
      projectRunFilterActive: _projectRunFilterActive,
      filteredProjectRuns: _filteredProjectRuns,
      entityLabelValues: _entityLabelValues,
      entityMetadataChips: _entityMetadataChips,
      formatDate: _formatProjectDate,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      projectItemRow: _projectItemRow,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      mobileView: () => _projectMobileShellController().currentView(),
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      logClientError: (message, err) => {
        if (typeof logClientError === 'function') logClientError(message, err);
      },
    });
    return projectRunsController;
  }

  let projectMobileCompareController = null;

  function _projectMobileCompareController() {
    if (projectMobileCompareController) return projectMobileCompareController;
    const factory = global.DarklabProjectMobileCompare && global.DarklabProjectMobileCompare.createProjectMobileCompareController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectMobileCompare is unavailable');
    projectMobileCompareController = factory({
      projectWorkspaceModal,
      projectSummary: projectWorkspaceState.summary,
      projectComparableRuns: _projectComparableRuns,
      projectRunBaselineLabelOptions: _projectRunBaselineLabelOptions,
      projectRunCompareOptionText: _projectRunCompareOptionText,
      entityLabelValues: _entityLabelValues,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      compareProjectRuns: _compareProjectRuns,
      closeProjectWorkspace,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
    });
    return projectMobileCompareController;
  }

  let projectMobileShellController = null;

  function _projectMobileShellController() {
    if (projectMobileShellController) return projectMobileShellController;
    const factory = global.DarklabProjectMobileShell && global.DarklabProjectMobileShell.createProjectMobileShellController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectMobileShell is unavailable');
    projectMobileShellController = factory({
      activeProject: _activeProject,
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      emptyProjectPanel: _emptyProjectPanel,
      mobileSection: _projectMobileSection,
      orderedProjectRows: _orderedProjectRows,
      projectIsArchived: _projectIsArchived,
      projectMobileBody,
      projectMobileCreateForm,
      projectMobileDetailView,
      projectMobileListView,
      projectMobileNameInput,
      projectMobilePagination,
      projectMobileRoot,
      projectMobileSummary,
      projectPagination: projectWorkspaceState.pagination,
      projectRows: projectWorkspaceState.rows,
      projectPagination: projectWorkspaceState.pagination,
      projectWorkspaceLoading: projectWorkspaceState.loading,
      renderMobileListRow: _renderProjectMobileListRow,
      renderProjectPagination: _renderProjectPagination,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      renderProjectWorkspace: _renderProjectWorkspace,
      selectedProjectId: projectWorkspaceState.selectedId,
      ensureProjectSummary: _ensureProjectSummary,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      setSelectedProjectId: projectWorkspaceState.setSelectedId,
      setWorkspaceTab: projectWorkspaceState.setTab,
    });
    return projectMobileShellController;
  }

  let projectMobileDetailController = null;

  function _projectMobileDetailController() {
    if (projectMobileDetailController) return projectMobileDetailController;
    const factory = global.DarklabProjectMobileDetail && global.DarklabProjectMobileDetail.createProjectMobileDetailController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectMobileDetail is unavailable');
    projectMobileDetailController = factory({
      projectWorkspaceModal,
      projectMobileDetailView,
      projectMobileDetailBody,
      projectMobileTabs,
      notePreviewLimit: PROJECT_WORKSPACE_CONSTANTS.mobileNotePreviewLimit,
      selectedProjectId: projectWorkspaceState.selectedId,
      setSelectedProjectId: projectWorkspaceState.setSelectedId,
      projectWorkspaceTab: projectWorkspaceState.tab,
      projectWorkspaceLoading: projectWorkspaceState.loading,
      activeProject: _activeProject,
      projectRows: projectWorkspaceState.rows,
      projectSummary: _projectSummary,
      projectCounts: _projectCounts,
      projectDisplayName: _projectDisplayName,
      projectTargetItems: _projectTargetItems,
      projectRunItems: _projectRunItems,
      projectRunById: _projectRunById,
      projectComparableRuns: _projectComparableRuns,
      projectArtifactItems: _projectArtifactItems,
      pagedProjectArtifactItems: _pagedProjectArtifactItems,
      projectArtifactPagination: _projectArtifactPagination,
      projectArtifactServerFilterKey: _projectArtifactServerFilterKey,
      loadProjectArtifacts: _loadProjectArtifacts,
      projectFindingItems: _projectFindingItems,
      projectFindingsLoaded: _projectFindingsLoaded,
      projectFindingsLoadingId: () => _projectFindingsDataController().loadingId(),
      hasProjectFindings: (projectId) => _projectFindingsDataController().loaded(projectId),
      projectFindingPagination: (projectId, summary) => _projectFindingsDataController().page(projectId, summary),
      projectFindingServerFiltersActive: _projectFindingServerFiltersActive,
      projectFindingGroupCollapsed: _projectFindingGroupCollapsed,
      collapsedFindingGroupLabels: _projectCollapsedFindingGroupLabels,
      projectArtifactGroupCollapsed: _projectArtifactGroupCollapsed,
      projectTargetFilterActive: _projectTargetFilterActive,
      projectRunFilterActive: _projectRunFilterActive,
      projectRunPagination: _projectRunPagination,
      loadProjectRuns: _loadProjectRuns,
      projectArtifactsVisible: _projectArtifactsVisible,
      projectArtifactStatus: _projectArtifactStatus,
      projectArtifactStatusLabel: _projectArtifactStatusLabel,
      projectArtifactDetailLines: _projectArtifactDetailLines,
      projectFindingTargetText: _projectFindingTargetText,
      projectTargetLabel: _projectTargetLabel,
      projectRunFindingCount: _projectRunFindingCount,
      projectRunArtifactCount: _projectRunArtifactCount,
      filteredProjectRuns: _filteredProjectRuns,
      filteredProjectFindings: _filteredProjectFindings,
      filteredProjectArtifacts: _filteredProjectArtifacts,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      entityMetadataChips: _entityMetadataChips,
      entityMetadataChipClass: _entityMetadataChipClass,
      formatDate: _formatProjectDate,
      shortProjectRunId: _shortProjectRunId,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      findingReviewControl: _findingReviewControl,
      renderProjectMobileDetailTopbar: _renderProjectMobileDetailTopbar,
      renderProjectMobileTabs: _renderProjectMobileTabs,
      renderProjectMobileEntitiesTab: (projectId, summary) => _projectEntitiesController().renderMobileEntitiesTab(projectId, summary),
      renderProjectMobilePackagesTab: (projectId, summary) => _projectPackagesController().renderMobilePackagesTab(projectId, summary),
      renderProjectMobileReportTab: (projectId, summary) => _projectReportController().renderMobileReportTab(projectId, summary),
      renderProjectMobileActivityTab: (projectId, summary) => _projectActivityController().renderMobileActivityTab(projectId, summary),
      setProjectMobileView: _setProjectMobileView,
      loadProjectFindings: _loadProjectFindings,
      loadProjectFilteredFindings: _loadProjectFilteredFindings,
      groupBy: _groupBy,
      mobileMenuText: '☰',
      caretText: '▾',
      metaSeparator: ' · ',
    });
    return projectMobileDetailController;
  }

  let projectEntityEditorController = null;

  function _projectEntityEditorController() {
    if (projectEntityEditorController) return projectEntityEditorController;
    const factory = global.DarklabProjectEntityEditor && global.DarklabProjectEntityEditor.createProjectEntityEditorController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectEntityEditor is unavailable');
    projectEntityEditorController = factory({
      overlay: projectEntityEditorOverlay,
      title: projectEntityEditorTitle,
      subtitle: projectEntityEditorSubtitle,
      form: projectEntityEditorForm,
      labelsInput: projectEntityLabelsInput,
      noteInput: projectEntityNoteInput,
      activityRoot: projectEntityActivityRoot,
      submitButton: projectEntitySubmitButton,
      parseLabelInput: EntityMetadataClient.parseLabelInput,
      entityTitleForEditor: _entityTitleForEditor,
      entityEditorLabelForType: _entityEditorLabelForType,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      syncEntityLabels: _syncEntityLabels,
      syncEntityNote: _syncEntityNote,
      projectResponseError: _projectResponseError,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      openProjectActivity: _openProjectActivity,
      refreshProjectWorkspace,
      invalidateProjectFindings: _invalidateProjectFindings,
      invalidateProjectTargetPage: projectId => _projectDetailsController().invalidateTargetPage(projectId),
      loadProjectFindings: _loadProjectFindings,
      renderProjectExplorer: _renderProjectExplorer,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      syncProjectWorkspaceNestedSuppression: _syncProjectWorkspaceNestedSuppression,
      installProjectMobileKeyboardGuards: _installProjectMobileKeyboardGuards,
      focusProjectNestedSheet: _focusProjectNestedSheet,
    });
    return projectEntityEditorController;
  }

  let projectWorkspaceLifecycleController = null;

  function _projectWorkspaceLifecycleController() {
    if (projectWorkspaceLifecycleController) return projectWorkspaceLifecycleController;
    const factory = global.DarklabProjectWorkspaceLifecycle
      && global.DarklabProjectWorkspaceLifecycle.createProjectWorkspaceLifecycleController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectWorkspaceLifecycle is unavailable');
    projectWorkspaceLifecycleController = factory({
      apiFetch,
      projectWorkspaceBody,
      selectedProjectId: projectWorkspaceState.selectedId,
      setSelectedProjectId: projectWorkspaceState.setSelectedId,
      projectRows: projectWorkspaceState.rows,
      setProjectRows: projectWorkspaceState.setRows,
      projectPagination: projectWorkspaceState.pagination,
      setProjectPagination: projectWorkspaceState.setPagination,
      projectSummaries: projectWorkspaceState.summaries,
      setProjectSummary: projectWorkspaceState.setSummary,
      setProjectSummaries: projectWorkspaceState.setSummaries,
      projectWorkspaceLoading: projectWorkspaceState.loading,
      setProjectWorkspaceLoading: projectWorkspaceState.setLoading,
      workspaceTab: projectWorkspaceState.tab,
      activeProject: _activeProject,
      loadActiveProjectContext,
      invalidateProjectFindings: _invalidateProjectFindings,
      invalidateProjectRuns: _invalidateProjectRuns,
      invalidateProjectEntities: (projectId = '') => _projectEntitiesController().invalidate(projectId),
      invalidateProjectArtifacts: (projectId = '') => _projectArtifactsController().invalidate?.(projectId),
      renderProjectWorkspace: _renderProjectWorkspace,
      syncProjectNotesForm: _syncProjectNotesForm,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      logClientError: (message, err) => {
        if (typeof logClientError === 'function') logClientError(message, err);
      },
    });
    return projectWorkspaceLifecycleController;
  }

  let projectWorkspaceEventsController = null;

  function _projectWorkspaceEventsController() {
    if (projectWorkspaceEventsController) return projectWorkspaceEventsController;
    const factory = global.DarklabProjectWorkspaceEvents
      && global.DarklabProjectWorkspaceEvents.createProjectWorkspaceEventsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectWorkspaceEvents is unavailable');
    projectWorkspaceEventsController = factory({
      activeProject: _activeProject,
      artifactGroupKey: _projectArtifactGroupKey,
      avoidProjectRunCompareLabelSelfTarget: _avoidProjectRunCompareLabelSelfTarget,
      clearEditingTargetIf: projectWorkspaceState.clearEditingTargetIf,
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectFilterMenus: _closeProjectFilterMenus,
      closeProjectPackageManifest: _closeProjectPackageManifest,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      closeProjectWorkspace,
      compareProjectRuns: _compareProjectRuns,
      confirmProjectDelete: _confirmProjectDelete,
      confirmProjectDestructive: _confirmProjectDestructive,
      confirmProjectPackageDelete: _confirmProjectPackageDelete,
      confirmProjectRunUnlink: _confirmProjectRunUnlink,
      confirmProjectTargetDelete: _confirmProjectTargetDelete,
      downloadProjectArtifact: _downloadProjectArtifact,
      downloadProjectPackage: _downloadProjectPackage,
      entitiesController: _projectEntitiesController,
      entitySelectMode: projectWorkspaceState.entitySelectMode,
      filteredProjectFindings: _filteredProjectFindings,
      filtersController: _projectFiltersController,
      findingGroupKey: _projectFindingGroupKey,
      findingSelectMode: projectWorkspaceState.findingSelectMode,
      flushProjectNotesAutosave: _flushProjectNotesAutosave,
      invalidateProjectFindings: _invalidateProjectFindings,
      isProjectWorkspaceOpen,
      linkLastRunToProject: _linkLastRunToProject,
      ensureProjectSummary: _ensureProjectSummary,
      loadProjectRuns: _loadProjectRuns,
      loadProjectAutocompleteTargets: () => {
        if (typeof loadProjectAutocompleteTargets === 'function') {
          loadProjectAutocompleteTargets().catch(() => {});
        }
      },
      loadProjectFilteredFindings: _loadProjectFilteredFindings,
      loadProjectFindings: _loadProjectFindings,
      loadProjectTargetPage: (projectId, options) => _projectDetailsController().loadTargetPage(projectId, options),
      mobileView: () => _projectMobileShellController().currentView(),
      openProjectEntityEditor: _openProjectEntityEditor,
      openProjectEntityInAtlas: _openProjectEntityInAtlas,
      openProjectEntityPicker: _openProjectEntityPicker,
      openProjectMobileActionSheet: _openProjectMobileActionSheet,
      openProjectMobileCompareSheet: _openProjectMobileCompareSheet,
      openProjectPackageManifest: _openProjectPackageManifest,
      openProjectPackageWizardFromPackage: _openProjectPackageWizardFromPackage,
      openProjectTargetEditor: _openProjectTargetEditor,
      packagesController: _projectPackagesController,
      previewProjectArtifact: _previewProjectArtifact,
      reportController: _projectReportController,
      activityController: _projectActivityController,
      projectArtifactItems: _projectArtifactItems,
      projectArtifactPagination: _projectArtifactPagination,
      projectDisplayName: _projectDisplayName,
      projectExplorerBody,
      projectFindingPagination: _projectFindingPagination,
      projectFindingItems: _projectFindingItems,
      projectFindingCommandFilterSet: _projectFindingCommandFilterSet,
      projectFindingLabelFilterSet: _projectFindingLabelFilterSet,
      projectFindingServerFiltersActive: _projectFindingServerFiltersActive,
      projectFindingSeverityFilterSet: _projectFindingSeverityFilterSet,
      projectFindingScopeFilterSet: _projectFindingScopeFilterSet,
      projectFindingStatusFilterSet: _projectFindingStatusFilterSet,
      projectMobileDetailBody,
      projectMobileListView,
      projectMobileProjectActions: _projectMobileProjectActions,
      projectPackageById: _projectPackageById,
      projectPagination: projectWorkspaceState.pagination,
      projectRows: projectWorkspaceState.rows,
      projectRunPagination: _projectRunPagination,
      projectRunFilterSet: _projectRunFilterSet,
      projectRunItems: _projectRunItems,
      projectSummary: _projectSummary,
      projectTargetFilterSet: _projectTargetFilterSet,
      projectTargetPage: projectId => _projectDetailsController().targetPage(projectId),
      projectTargetById: (projectId, targetId) => _projectDetailsController().targetById(projectId, targetId),
      removeCachedProjectTarget: (projectId, targetId) => _projectDetailsController().removeCachedTarget(projectId, targetId),
      updateCachedProjectTarget: (projectId, targetId, updates) => _projectDetailsController().updateCachedTarget(projectId, targetId, updates),
      projectTargetItems: _projectTargetItems,
      projectWorkspaceModal,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      refreshProjectWorkspace,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobile: _renderProjectMobile,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      renderProjectWorkspace: _renderProjectWorkspace,
      selectedEntityIds: projectWorkspaceState.selectedEntityIds,
      selectedFindingIds: projectWorkspaceState.selectedFindingIds,
      selectedProjectId: projectWorkspaceState.selectedId,
      selectProjectFromMobile: _selectProjectFromMobile,
      setFindingViewMode: projectWorkspaceState.setFindingViewMode,
      setProjectFindingPageOffset: _setProjectFindingPageOffset,
      setProjectArtifactPageOffset: _setProjectArtifactPageOffset,
      setProjectRunPageOffset: _setProjectRunPageOffset,
      setProjectPaginationOffset: _setProjectPaginationOffset,
      setCachedFindingReviewState: _setCachedFindingReviewState,
      updateCachedProjectFinding: _updateCachedProjectFinding,
      setFindingSelectMode: projectWorkspaceState.setFindingSelectMode,
      setProjectMobileCreateOpen: _setProjectMobileCreateOpen,
      setProjectMobileView: _setProjectMobileView,
      setProjectPackageDownloadBusy: _setProjectPackageDownloadBusy,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      setProjectRunCompareMode: _setProjectRunCompareMode,
      setSelectedProjectId: projectWorkspaceState.setSelectedId,
      setWorkspaceTab: projectWorkspaceState.setTab,
      syncProjectRunCompareMode: _syncProjectRunCompareMode,
      toggleArtifactGroup: projectWorkspaceState.toggleArtifactGroup,
      toggleFindingGroup: projectWorkspaceState.toggleFindingGroup,
      toggleMobileArchivedOpen: () => {
        _projectMobileShellController().setArchivedOpen(!_projectMobileShellController().isArchivedOpen());
      },
      workspaceTab: projectWorkspaceState.tab,
    });
    return projectWorkspaceEventsController;
  }

  function _projectTargetById(summary, targetId) {
    return _projectFiltersController().targetById(summary, targetId);
  }

  function _projectTargetFilterLabel(target) {
    return _projectFiltersController().targetFilterLabel(target);
  }

  function _targetFilterableProjectTab() {
    return _projectFiltersController().targetFilterableProjectTab(projectWorkspaceState.tab());
  }

  function _projectTargetFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().targetFilterSet(projectId);
  }

  function _projectTargetFilterIds(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().targetFilterIds(projectId, summary);
  }

  function _projectTargetFilterActive(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().targetFilterActive(projectId, summary);
  }

  function _projectRunFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().runFilterSet(projectId);
  }

  function _projectRunFilterIds(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().runFilterIds(projectId, summary);
  }

  function _projectRunFilterActive(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().runFilterActive(projectId, summary);
  }

  function _projectRunFilterLabel(run) {
    return _projectFiltersController().runFilterLabel(run);
  }

  function _projectRunFilterChipLabel(run) {
    return _projectFiltersController().runFilterChipLabel(run);
  }

  function _projectFindingStatusFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingStatusFilterSet(projectId);
  }

  function _projectFindingCommandFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingCommandFilterSet(projectId);
  }

  function _projectFindingSeverityFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingSeverityFilterSet(projectId);
  }

  function _projectFindingScopeFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingScopeFilterSet(projectId);
  }

  function _projectFindingStatusFilterValues(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingStatusFilterValues(projectId);
  }

  function _projectFindingStatusFilterActive(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingStatusFilterActive(projectId);
  }

  function _projectFindingLabelFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingLabelFilterSet(projectId);
  }

  function _projectFindingLabelOptions(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingLabelOptions(projectId);
  }

  function _projectFindingLabelFilterValues(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingLabelFilterValues(projectId);
  }

  function _projectFindingLabelFilterActive(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingLabelFilterActive(projectId);
  }

  function _projectFindingNoteStateValue(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingNoteStateValue(projectId);
  }

  function _projectFindingNoteStateFilterActive(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingNoteStateFilterActive(projectId);
  }

  function _projectFindingOrphanFilterValue(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingOrphanFilterValue(projectId);
  }

  function _projectFindingOrphanFilterActive(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingOrphanFilterActive(projectId);
  }

  function _projectFindingSortValue(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingSortValue(projectId);
  }

  function _projectFindingTargetText(summary, finding) {
    return _projectFiltersController().findingTargetText(summary, finding);
  }

  function _sortProjectFindings(findings, projectId, summary) {
    return _projectFiltersController().sortProjectFindings(findings, projectId, summary);
  }

  function _findingReviewStateLabel(value) {
    return _projectFindingsController().reviewStateLabel(value);
  }

  function _projectFindingGroupKey(projectId, runLabel) {
    return _projectFindingsController().groupKey(projectId, runLabel);
  }

  function _projectFindingGroupCollapsed(projectId, runLabel) {
    return _projectFindingsController().groupCollapsed(projectId, runLabel);
  }

  function _projectCollapsedFindingGroupLabels(projectId = projectWorkspaceState.selectedId()) {
    return _projectFindingsController().collapsedGroupLabels(projectId);
  }

  function _projectArtifactGroupKey(projectId, runId) {
    return _projectArtifactsController().groupKey(projectId, runId);
  }

  function _projectArtifactGroupCollapsed(projectId, runId) {
    return _projectArtifactsController().groupCollapsed(projectId, runId);
  }

  function _projectRunItems(summary) {
    return _projectSharedUiController().runItems(summary);
  }

  function _projectRunPagination(projectId = projectWorkspaceState.selectedId()) {
    return _projectRunsController().page(projectId);
  }

  function _setProjectRunPageOffset(projectId = projectWorkspaceState.selectedId(), offset = 0) {
    _projectRunsController().setPageOffset(projectId, offset);
  }

  async function _loadProjectRuns(projectId = projectWorkspaceState.selectedId(), options = {}) {
    await _projectRunsController().load(projectId, options);
  }

  function _invalidateProjectRuns(projectId = '') {
    _projectRunsController().invalidate(projectId);
  }

  function _projectRunById(summary, runId) {
    return _projectSharedUiController().runById(summary, runId);
  }

  function _projectComparableRuns(summary) {
    return _projectSharedUiController().comparableRuns(summary);
  }

  function _shortProjectRunId(runId) {
    return _projectSharedUiController().shortRunId(runId);
  }

  function _projectArtifactItems(summary) {
    return _projectArtifactsController().items(summary);
  }

  function _projectArtifactPagination(projectId = projectWorkspaceState.selectedId()) {
    return _projectArtifactsController().page(projectId);
  }

  function _setProjectArtifactPageOffset(projectId = projectWorkspaceState.selectedId(), offset = 0) {
    _projectArtifactsController().setPageOffset(projectId, offset);
  }

  function _pagedProjectArtifactItems(projectId = projectWorkspaceState.selectedId(), artifacts = []) {
    return _projectArtifactsController().pagedItems(projectId, artifacts);
  }

  async function _loadProjectArtifacts(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId), options = {}) {
    return _projectArtifactsController().load(projectId, summary, options);
  }

  async function _loadAllProjectArtifacts(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectArtifactsController().loadAll(projectId, summary);
  }

  function _projectFilesEnabled() {
    return _projectArtifactsController().filesEnabled();
  }

  function _projectArtifactsVisible() {
    return _projectArtifactsController().artifactsVisible();
  }

  function _projectArtifactStatus(artifact) {
    return _projectArtifactsController().status(artifact);
  }

  function _projectArtifactStatusLabel(artifact) {
    return _projectArtifactsController().statusLabel(artifact);
  }

  function _projectArtifactAccessory(projectId, artifact) {
    return _projectArtifactsController().accessory(projectId, artifact);
  }

  function _entityLabelValues(entity) {
    return _projectSharedUiController().entityLabelValues(entity);
  }

  function _entityNoteBody(entity) {
    return _projectSharedUiController().entityNoteBody(entity);
  }

  function _entityMetadataChips(entity) {
    return _projectSharedUiController().entityMetadataChips(entity);
  }

  function _entityMetadataChipClass(kind = 'label') {
    return _projectSharedUiController().entityMetadataChipClass(kind);
  }

  function _projectProvenanceSummary(manifest, options) {
    return _projectSharedUiController().projectProvenanceSummary(manifest, options);
  }

  function _projectProvenanceSummaryElement(manifest, options) {
    return _projectSharedUiController().projectProvenanceSummaryElement(manifest, options);
  }

  function _appendProjectLabelChips(parent, project, { className = 'project-label-chips' } = {}) {
    _projectDetailsController().appendLabelChips(parent, project, { className });
  }

  function _appendProjectMobileLabelChips(parent, project) {
    _projectDetailsController().appendMobileLabelChips(parent, project);
  }

  function _entityTitleForEditor(entityType, entity) {
    return _projectSharedUiController().entityTitleForEditor(entityType, entity);
  }

  function _entityEditorLabelForType(entityType) {
    return _projectSharedUiController().entityEditorLabelForType(entityType);
  }

  function _projectArtifactDetail(artifact) {
    return _projectArtifactsController().detail(artifact);
  }

  function _projectArtifactDetailLines(artifact) {
    return _projectArtifactsController().detailLines(artifact);
  }

  function _projectArtifactDownloadName(artifactPath = '', fallback = 'artifact') {
    return _projectArtifactsController().downloadName(artifactPath, fallback);
  }

  function _downloadBlobAsAttachment(blob, filename, successMessage = '') {
    _projectSharedUiController().downloadBlobAsAttachment(blob, filename, successMessage);
  }

  function _downloadUrlAsAttachment(url, filename = '', successMessage = '') {
    _projectSharedUiController().downloadUrlAsAttachment(url, filename, successMessage);
  }

  function _syncProjectWorkspaceNestedSuppression() {
    _projectNestedSheetsController().syncWorkspaceSuppression();
  }

  function _focusProjectNestedSheet(overlay, preferred = null) {
    _projectNestedSheetsController().focusNestedSheet(overlay, preferred);
  }

  function _syncProjectMobileFocusedField() {
    _projectNestedSheetsController().syncMobileFocusedField();
  }

  function _installProjectMobileKeyboardGuards() {
    _projectNestedSheetsController().installKeyboardGuards();
  }

  function _closeProjectPackageManifest() {
    _projectPackagesController().closeManifest();
  }

  function isProjectPackageManifestOpen() {
    return _projectPackagesController().isManifestOpen();
  }

  function _openProjectPackageManifest(pkg) {
    _projectPackagesController().openManifest(pkg);
  }

  async function _previewProjectArtifact(projectId, artifactId) {
    await _projectArtifactsController().preview(projectId, artifactId);
  }

  async function _downloadProjectArtifact(projectId, artifactId, artifactPath = '') {
    await _projectArtifactsController().download(projectId, artifactId, artifactPath);
  }

  function _projectPackageItems(summary) {
    return _projectPackagesController().items(summary);
  }

  function _projectPackageWizardActive(projectId = projectWorkspaceState.selectedId()) {
    return _projectPackagesController().isWizardActive(projectId);
  }

  function isProjectPackageWizardOpen() {
    return _projectPackagesController().isWizardOpen();
  }

  function isProjectEntityEditorOpen() {
    return _projectEntityEditorController().isOpen();
  }

  function _closeProjectEntityEditor() {
    _projectEntityEditorController().close();
  }

  function _openProjectEntityEditor(projectId, entityType, entity, options = {}) {
    _projectEntityEditorController().open(projectId, entityType, entity, options);
  }

  global.openEntityMetadataEditor = function openEntityMetadataEditor(entityType, entity, options = {}) {
    const projectId = options && Object.prototype.hasOwnProperty.call(options, 'projectId')
      ? options.projectId
      : '';
    _openProjectEntityEditor(projectId, entityType, entity, options);
  };

  function _renderProjectPackageWizardModal(options = {}) {
    _projectPackagesController().renderWizardModal(options);
  }

  function _openProjectPackageWizard(projectId, preset = 'evidence') {
    _projectPackagesController().openWizard(projectId, preset);
  }

  function _openProjectPackageWizardFromPackage(projectId, pkg) {
    _projectPackagesController().openWizardFromPackage(projectId, pkg);
  }

  function _closeProjectPackageWizard(options = {}) {
    _projectPackagesController().closeWizard(options);
  }

  function _projectPackageById(summary, packageId) {
    return _projectPackagesController().byId(summary, packageId);
  }

  function _setProjectPackageDownloadBusy(button, busy) {
    _projectPackagesController().setDownloadBusy(button, busy);
  }

  async function _downloadProjectPackage(projectId, pkg) {
    await _projectPackagesController().downloadPackage(projectId, pkg);
  }

  function _projectFindingItems(projectId = projectWorkspaceState.selectedId()) {
    return _projectFindingsDataController().items(projectId);
  }

  function _projectFindingsLoaded(projectId = projectWorkspaceState.selectedId()) {
    return _projectFindingsDataController().loaded(projectId);
  }

  function _projectFindingPagination(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFindingsDataController().page(projectId, summary);
  }

  function _setProjectFindingPageOffset(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId), offset = 0) {
    _projectFindingsDataController().setPageOffset(projectId, summary, offset);
  }

  function _projectFindingServerFilterParams(projectId, summary = _projectSummary(projectId)) {
    return _projectFiltersController().findingServerFilterParams(projectId, summary);
  }

  function _projectArtifactServerFilterParams(projectId, summary = _projectSummary(projectId)) {
    return _projectArtifactsController().serverFilterParams(projectId, summary);
  }

  function _projectArtifactServerFilterKey(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectArtifactsController().serverFilterKey(projectId, summary);
  }

  function _projectFindingServerFiltersActive(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().findingServerFiltersActive(projectId, summary);
  }

  function _projectFindingFilteredKey(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().findingFilteredKey(projectId, summary);
  }

  function _projectFilteredFindingItems(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().filteredFindingItems(projectId, summary);
  }

  function _invalidateProjectFilteredFindings(projectId = '') {
    _projectFindingsDataController().invalidateFiltered(projectId);
  }

  function _invalidateProjectFindings(projectId = '') {
    _projectFindingsDataController().invalidate(projectId);
  }

  function _projectTargetLabel(summary, targetId) {
    return _projectSharedUiController().targetLabel(summary, targetId);
  }

  function _formatProjectDate(value) {
    return _projectSharedUiController().formatDate(value);
  }

  function _formatProjectBytes(value) {
    return _projectSharedUiController().formatBytes(value);
  }

  function _emptyProjectPanel(text) {
    return _projectSharedUiController().emptyPanel(text);
  }

  function _projectMetaRow(label, value) {
    return _projectSharedUiController().metaRow(label, value);
  }

  function _projectItemRow({ title, meta = '', detail = '', badge = '', chips = [], action = null, accessory = null, forceArticle = false }) {
    return _projectSharedUiController().itemRow({ title, meta, detail, badge, chips, action, accessory, forceArticle });
  }

  function _findingReviewControl(finding, projectId) {
    return _projectFindingsController().reviewControl(finding, projectId);
  }

  function _findingRowAccessory(finding, projectId) {
    return _projectFindingsController().rowAccessory(finding, projectId);
  }

  function _openProjectTargetEditor(projectId, target = null) {
    _projectTargetsController().openEditor(projectId, target);
  }

  function _closeProjectTargetEditor(options = {}) {
    _projectTargetsController().closeEditor(options);
  }

  function isProjectTargetEditorOpen() {
    return _projectTargetsController().isOpen();
  }

  function _projectTargetDisplayRow(projectId, target) {
    return _projectTargetsController().targetDisplayRow(projectId, target);
  }

  function _projectRunRemoveControl(projectId, run) {
    return _projectRunsController().runRemoveControl(projectId, run);
  }

  function _projectRunFindingCount(projectId, runId, run = null) {
    return _projectRunsController().runFindingCount(projectId, runId, run);
  }

  function _projectRunArtifactCount(summary, runId, run = null) {
    return _projectRunsController().runArtifactCount(summary, runId, run);
  }

  function _projectRunControls(projectId, run, summary) {
    return _projectRunsController().runControls(projectId, run, summary);
  }

  function _projectRunBaselineLabelOptions(runs) {
    return _projectRunsController().baselineLabelOptions(runs);
  }

  function _projectRunCompareOptionText(run) {
    return _projectRunsController().compareOptionText(run);
  }

  function _syncProjectRunCompareMode(wrap) {
    _projectRunsController().syncCompareMode(wrap);
  }

  function _setProjectRunCompareMode(modeButton, event = null) {
    _projectRunsController().setCompareMode(modeButton, event);
  }

  function _avoidProjectRunCompareLabelSelfTarget(container, label) {
    _projectRunsController().avoidCompareLabelSelfTarget(container, label);
  }

  function _compareProjectRuns(projectId, leftId, mode, targetValue, controls = null) {
    _projectRunsController().compareRuns(projectId, leftId, mode, targetValue, controls);
  }

  function _renderProjectRunCompareControls(runs) {
    return _projectRunsController().renderCompareControls(runs);
  }

  function _renderProjectTargets(projectId, targets) {
    return _projectTargetsController().renderTargets(projectId, targets);
  }

  function _setProjectFilterMenuOpen(menu, open) {
    _projectFiltersController().setFilterMenuOpen(menu, open);
  }

  function _closeProjectFilterMenus(exceptMenu = null) {
    _projectFiltersController().closeFilterMenus(exceptMenu);
  }

  function _renderProjectFilterBar(projectId, summary) {
    return _projectFiltersController().renderFilterBar(projectId, summary);
  }

  function _syncProjectFilterSortDivider(root) {
    _projectFiltersController().syncFilterSortDivider(root);
  }

  function _scheduleProjectFilterSortDividerSync(root) {
    _projectFiltersController().scheduleFilterSortDividerSync(root);
  }

  function _projectRunDirectTargetIds(run) {
    return _projectFiltersController().runDirectTargetIds(run);
  }

  function _projectFindingTargetIds(finding) {
    return _projectFiltersController().findingTargetIds(finding);
  }

  function _projectRunIdsMatchingTargets(projectId, filterIds) {
    return _projectFiltersController().runIdsMatchingTargets(projectId, filterIds);
  }

  function _projectRunMatchesTargetFilters(run, projectId, filterIds, matchingRunIds) {
    return _projectFiltersController().runMatchesTargetFilters(run, projectId, filterIds, matchingRunIds);
  }

  function _filteredProjectRuns(projectId, summary) {
    return _projectFiltersController().filteredRuns(projectId, summary);
  }

  function _filteredProjectFindings(projectId, summary) {
    return _projectFiltersController().filteredFindings(projectId, summary);
  }

  function _filteredProjectArtifacts(projectId, summary) {
    return _projectFiltersController().filteredArtifacts(projectId, summary);
  }

  function _groupBy(items, keyFn) {
    return _projectSharedUiController().groupBy(items, keyFn);
  }

  async function _loadProjectFindings(projectId, options = {}) {
    return _projectFindingsDataController().load(projectId, options);
  }

  async function _loadProjectFilteredFindings(projectId, summary = _projectSummary(projectId), options = {}) {
    await _projectFindingsDataController().loadFiltered(projectId, summary, options);
  }

  function _syncProjectForms(project = _selectedProject()) {
    _projectDetailsController().syncForms(project);
  }

  function _syncProjectNotesForm() {
    _projectDetailsController().syncNotesForm();
  }

  function _flushProjectNotesAutosave() {
    return _projectDetailsController().flushNotesAutosave();
  }

  function _makeProjectButton(label, action, projectId, role = 'secondary', tone = '') {
    return _projectSharedUiController().makeButton(label, action, projectId, role, tone);
  }

  function _projectIsArchived(project) {
    return _projectListController().isArchived(project);
  }

  function _orderedProjectRows(activeId, rows = projectWorkspaceState.rows()) {
    return _projectListController().orderedRows(activeId, rows);
  }

  function _renderProjectList() {
    _projectListController().renderList();
  }

  function _projectMobileTabItems(projectId, summary) {
    return _projectNavigationController().mobileTabItems(projectId, summary);
  }

  function _syncProjectMobileActiveTabScroll() {
    _projectNavigationController().syncMobileActiveTabScroll();
  }

  function _syncProjectMobileTabEdges() {
    _projectNavigationController().syncMobileTabEdges();
  }

  function _renderProjectMobileListRow(project, activeId) {
    return _projectListController().renderMobileListRow(project, activeId);
  }

  function _renderProjectPagination(host, options = {}) {
    return _projectListController().renderPagination(host, options);
  }

  function _projectMobileSection(label, count, { open = true } = {}) {
    return _projectListController().mobileSection(label, count, { open });
  }

  function _setProjectMobileCreateOpen(open, { focus = false } = {}) {
    _projectMobileShellController().setCreateOpen(open, { focus });
  }

  function _setProjectMobileView(view) {
    _projectMobileShellController().setView(view);
  }

  function _selectProjectFromMobile(projectId, tab = '') {
    _projectMobileShellController().selectProject(projectId, tab);
  }

  function _projectMobileProjectActions(project) {
    return _projectMobileShellController().projectActions(project);
  }

  function _renderProjectMobileDetailTopbar(project, activeId) {
    _projectNavigationController().renderMobileDetailTopbar(project, activeId);
  }

  function _renderProjectMobileTabs(projectId, summary) {
    _projectNavigationController().renderMobileTabs(projectId, summary);
  }

  function _projectMobileActionMenu(projectId, label, actions = []) {
    return _projectMobileDetailController().actionMenu(projectId, label, actions);
  }

  function _closeProjectMobileActionSheet({ restoreFocus = true } = {}) {
    _projectMobileDetailController().closeActionSheet({ restoreFocus });
  }

  function _openProjectMobileActionSheet(projectId, label, actions = [], returnFocus = null) {
    _projectMobileDetailController().openActionSheet(projectId, label, actions, returnFocus);
  }

  function _closeProjectMobileCompareSheet({ restoreFocus = true } = {}) {
    _projectMobileCompareController().close({ restoreFocus });
  }

  function _openProjectMobileCompareSheet(projectId, returnFocus = null) {
    _projectMobileCompareController().open(projectId, returnFocus);
  }

  function _projectMobileContentRow({
    title,
    meta = '',
    detail = '',
    badge = '',
    chips = [],
    action = null,
    accessory = null,
    className = '',
  }) {
    return _projectMobileDetailController().contentRow({
      title,
      meta,
      detail,
      badge,
      chips,
      action,
      accessory,
      className,
    });
  }

  function _projectMobileEmptyPanel(text, actions = []) {
    return _projectMobileDetailController().emptyPanel(text, actions);
  }

  function _renderProjectMobileDetail() {
    _projectMobileDetailController().renderDetail();
  }

  function _renderProjectMobile() {
    _projectMobileShellController().renderMobile();
  }

  function _renderProjectHeader(project, summary, options = {}) {
    return _projectNavigationController().renderProjectHeader(project, summary, options);
  }

  function _focusProjectWorkspaceTab(tabId) {
    _projectNavigationController().focusWorkspaceTab(tabId);
  }

  function cycleProjectWorkspaceTab(offset = 1) {
    return _projectWorkspaceRendererController().cycleTab(offset);
  }

  function _renderProjectDetails(container, project, summary) {
    _projectDetailsController().renderDetails(container, project, summary);
  }

  function _renderProjectRuns(container, projectId, summary) {
    _projectRunsController().renderRuns(container, projectId, summary);
  }

  function _openProjectEntityInAtlas(projectId, summary, entity) {
    _projectEntitiesController().openInAtlas(projectId, summary, entity);
  }

  function _openProjectEntityPicker(projectId) {
    _projectEntitiesController().openPicker(projectId);
  }

  function _renderProjectEntities(container, projectId, summary) {
    _projectEntitiesController().renderEntities(container, projectId, summary);
  }

  function _renderProjectFindings(container, projectId, summary) {
    _projectFindingsController().renderFindings(container, projectId, summary);
  }

  function _renderProjectArtifacts(container, projectId, summary) {
    _projectArtifactsController().renderArtifacts(container, projectId, summary);
  }

  function _renderProjectPackages(container, projectId, summary) {
    _projectPackagesController().renderPackages(container, projectId, summary);
  }

  function _renderProjectActivity(container, projectId, summary) {
    _projectActivityController().renderActivity(container, projectId, summary);
  }

  function _openProjectObject(projectId, { tab = '', targetType = '', targetId = '' } = {}) {
    const normalizedProjectId = String(projectId || projectWorkspaceState.selectedId() || '').trim();
    const normalizedTab = String(tab || '').trim();
    if (!normalizedProjectId || !normalizedTab) return;
    if (normalizedTab === 'activity') {
      _openProjectActivity(normalizedProjectId, { targetType, targetId });
      return;
    }
    projectWorkspaceState.setTab(normalizedTab);
    _renderProjectExplorer();
  }

  function _openProjectActivity(projectId, { targetId = '', targetType = '' } = {}) {
    const normalizedProjectId = String(projectId || projectWorkspaceState.selectedId() || '').trim();
    if (!normalizedProjectId) return;
    const st = _projectActivityController().stateFor(normalizedProjectId);
    st.filters.target_id = String(targetId || '').trim();
    st.filters.target_type = String(targetType || '').trim();
    st.offset = 0;
    st.loaded = false;
    _closeProjectEntityEditor();
    projectWorkspaceState.setTab('activity');
    _renderProjectExplorer();
    _projectActivityController().load(normalizedProjectId).catch(() => {});
  }

  function _renderProjectReport(container, projectId, summary) {
    _projectReportController().renderReport(container, projectId, summary);
  }

  function _renderProjectExplorer() {
    _projectWorkspaceRendererController().renderExplorer();
  }

  function _renderProjectWorkspace() {
    _projectWorkspaceRendererController().renderWorkspace();
  }

  async function _loadProjectSummaries(projects) {
    await _projectWorkspaceLifecycleController().loadProjectSummaries(projects);
  }

  async function _ensureProjectSummary(projectId = projectWorkspaceState.selectedId()) {
    return _projectWorkspaceLifecycleController().ensureProjectSummary(projectId);
  }

  function _setProjectPaginationOffset(offset) {
    projectWorkspaceState.setPaginationOffset(offset);
  }

  async function refreshProjectWorkspace() {
    await _projectWorkspaceLifecycleController().refreshProjectWorkspace();
  }

  function _scheduleProjectWorkspaceExternalRefresh() {
    _projectWorkspaceShellController().scheduleExternalRefresh();
  }

  function _notifyProjectWorkspaceChanged(reason = 'updated', projectId = '', { local = true } = {}) {
    _projectWorkspaceShellController().notifyChanged(reason, projectId, { local });
  }

  _projectActiveContextController().bindTargetDiscoveryEvent();

  async function openProjectWorkspace() {
    await _projectWorkspaceShellController().open();
  }

  function _autoPromoteProjectPickerContent(projects, preferredProjectId = '') {
    const wrap = document.createElement('div');
    wrap.className = 'history-project-picker';
    const select = document.createElement('select');
    select.className = 'form-select form-control-compact';
    select.setAttribute('aria-label', 'Project');
    projects.forEach((project) => {
      const option = document.createElement('option');
      option.value = String(project.id || '');
      option.textContent = _projectDisplayName(project) || String(project.id || '');
      select.appendChild(option);
    });
    if (preferredProjectId && projects.some(project => String(project.id || '') === preferredProjectId)) {
      select.value = preferredProjectId;
    }
    const help = document.createElement('div');
    help.className = 'history-project-picker-help';
    help.textContent = 'Choose a project for the new auto-promote rule.';
    wrap.append(select, help);
    return { wrap, select };
  }

  async function _promptAutoPromoteRuleProject(preferredProjectId = '') {
    if (typeof showConfirm !== 'function') return '';
    const resp = await apiFetch('/projects?include_archived=1&include_counts=0&limit=100&offset=0', { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const projects = (Array.isArray(data.projects) ? data.projects : [])
      .filter(project => String(project && project.status || 'active') !== 'archived');
    if (!projects.length) {
      if (typeof showToast === 'function') showToast('Create an active project before creating an auto-promote rule.', 'error');
      return '';
    }
    const activeProject = _activeProject();
    const preferredId = preferredProjectId
      || (activeProject && activeProject.id ? String(activeProject.id) : '');
    const ordered = _orderedProjectRows(preferredId, projects);
    const { wrap, select } = _autoPromoteProjectPickerContent(ordered, preferredId);
    const choicePromise = showConfirm({
      body: 'Create auto-promote rule from Atlas view',
      content: wrap,
      defaultFocus: select,
      actions: [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'create', label: 'Create rule', role: 'primary' },
      ],
      refocusOnResolve: false,
    });
    if (typeof enhanceAppSelects === 'function') {
      enhanceAppSelects(wrap);
      if (typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode()) {
        wrap.querySelector('.app-select-menu')?.classList.add('dropdown-up');
      }
    }
    const choice = await choicePromise;
    return choice === 'create' ? String(select.value || '') : '';
  }

  async function openProjectAutoPromoteRuleFromAtlas(draft = {}) {
    const activeProject = _activeProject();
    let projectId = String(draft.project_id || '').trim();
    if (!projectId && activeProject && activeProject.id) projectId = String(activeProject.id);
    if (!projectId) projectId = await _promptAutoPromoteRuleProject();
    if (!projectId) return false;
    await openProjectWorkspace();
    projectWorkspaceState.setSelectedId(projectId);
    projectWorkspaceState.setTab('entities');
    await _ensureProjectSummary(projectId);
    _projectEntitiesController().openAutoPromoteRuleFromAtlas(projectId, draft);
    _renderProjectWorkspace();
    _renderProjectExplorer();
    return true;
  }

  function closeProjectWorkspace({ refocus = true } = {}) {
    _projectWorkspaceShellController().close({ refocus });
  }

  async function _projectWorkspaceRequest(url, options = {}) {
    return _projectWorkspaceShellController().request(url, options);
  }

  async function _syncEntityLabels(entityType, entityId, nextLabels) {
    await _projectWorkspaceActionsController().syncEntityLabels(entityType, entityId, nextLabels);
  }

  async function _syncEntityNote(entityType, entityId, body) {
    await _projectWorkspaceActionsController().syncEntityNote(entityType, entityId, body);
  }

  async function _linkLastRunToProject(projectId, summary) {
    await _projectWorkspaceActionsController().linkLastRunToProject(projectId, summary);
  }

  async function _confirmProjectDestructive({ body, actionLabel, actionId, note }) {
    return _projectWorkspaceActionsController().confirmDestructive({ body, actionLabel, actionId, note });
  }

  function _confirmProjectTargetDelete(targetValue) {
    return _projectWorkspaceActionsController().confirmTargetDelete(targetValue);
  }

  function _confirmProjectRunUnlink(runCommand) {
    return _projectWorkspaceActionsController().confirmRunUnlink(runCommand);
  }

  function _confirmProjectPackageDelete(packageName) {
    return _projectWorkspaceActionsController().confirmPackageDelete(packageName);
  }

  function _confirmProjectDelete(projectName) {
    return _projectWorkspaceActionsController().confirmProjectDelete(projectName);
  }

  function _setCachedFindingReviewState(projectId, findingId, reviewState) {
    _projectFindingsDataController().setCachedReviewState(projectId, findingId, reviewState);
  }

  function _updateCachedProjectFinding(projectId, findingId, updates) {
    _projectFindingsDataController().updateCachedFinding(projectId, findingId, updates);
  }

  _projectWorkspaceBootstrapController().bindAll();

  function _renderUptime() {
    if (!hudUptimeEl) return;
    if (hudState.serverUptime === null) {
      hudUptimeEl.textContent = '—';
      _setValueColor(hudUptimeEl, 'hud-muted');
      return;
    }
    const deltaS = (performance.now() - hudState.serverUptimeAt) / 1000;
    hudUptimeEl.textContent = _formatUptime(hudState.serverUptime + deltaS);
    _setValueColor(hudUptimeEl, null);
  }

  function _renderClock() {
    if (!hudClockEl) return;
    const mode = typeof global.getHudClockPreference === 'function'
      ? global.getHudClockPreference()
      : 'utc';
    const now = Date.now();
    hudClockEl.textContent = mode === 'local' ? _formatLocalClock(now) : _formatUtcClock(now);
    if (mode === 'local') {
      try {
        const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'browser local time';
        hudClockEl.title = `Clock: local time (${zone}, ${_getLocalClockLabel(new Date(now))})`;
      } catch (_) {
        hudClockEl.title = 'Clock: local time';
      }
    } else {
      hudClockEl.title = 'Clock: UTC';
    }
    _setValueColor(hudClockEl, null);
  }

  function _renderDb() {
    if (!hudDbEl) return;
    if (hudState.db === 'ok') {
      hudDbEl.textContent = 'ONLINE';
      _setValueColor(hudDbEl, 'hud-value-green');
    } else if (hudState.db === 'down') {
      hudDbEl.textContent = 'OFFLINE';
      _setValueColor(hudDbEl, 'hud-value-red');
    } else {
      hudDbEl.textContent = '—';
      _setValueColor(hudDbEl, 'hud-muted');
    }
  }

  function _renderRedis() {
    if (!hudRedisEl) return;
    if (hudState.redis === 'ok') {
      hudRedisEl.textContent = 'ONLINE';
      _setValueColor(hudRedisEl, 'hud-value-green');
      hudRedisEl.title = 'Redis backend is reachable';
    } else if (hudState.redis === 'down') {
      hudRedisEl.textContent = 'OFFLINE';
      _setValueColor(hudRedisEl, 'hud-value-red');
      hudRedisEl.title = 'Redis configured but unreachable';
    } else if (hudState.redis === 'none') {
      hudRedisEl.textContent = 'N/A';
      _setValueColor(hudRedisEl, 'hud-muted');
      hudRedisEl.title = 'Redis not configured — rate limiting and process tracking run in-process';
    } else {
      hudRedisEl.textContent = '—';
      _setValueColor(hudRedisEl, 'hud-muted');
    }
  }

  async function pollHudStatus() {
    const t0 = performance.now();
    try {
      const resp = await fetch('/status', { cache: 'no-store', credentials: 'same-origin' });
      const t1 = performance.now();
      hudState.latencyMs = t1 - t0;
      if (resp.ok) {
        const data = await resp.json();
        if (typeof data.uptime === 'number') {
          hudState.serverUptime = data.uptime;
          hudState.serverUptimeAt = performance.now();
        }
        if (typeof data.db === 'string')    hudState.db = data.db;
        if (typeof data.redis === 'string') hudState.redis = data.redis;
      }
    } catch (_) {
      hudState.latencyMs = null;
      hudState.db = 'down';
      if (hudState.redis !== 'none') hudState.redis = 'down';
    }
    _renderLatency();
    _renderUptime();
    _renderDb();
    _renderRedis();
  }

  function _currentHudStatusPollMs() {
    return document.visibilityState === 'visible'
      ? STATUS_POLL_VISIBLE_MS
      : STATUS_POLL_HIDDEN_MS;
  }

  function _startHudStatusPoll({ pollNow = false } = {}) {
    if (hudStatusPollTimer) clearInterval(hudStatusPollTimer);
    hudStatusPollTimer = setInterval(pollHudStatus, _currentHudStatusPollMs());
    if (pollNow) pollHudStatus();
  }

  // Cross-tab SESSION_ID changes fire the 'storage' event, so refresh there
  // as well as on every poll (cheap) so token rotations reflect immediately.
  window.addEventListener('storage', e => {
    if (e.key === 'session_token') {
      _renderSession();
      loadActiveProjectContext().catch(() => {});
      return;
    }
    if (e.key === PROJECT_WORKSPACE_CONSTANTS.workspaceBroadcastKey && e.newValue) {
      _scheduleProjectWorkspaceExternalRefresh();
    }
  });
  document.addEventListener('visibilitychange', () => {
    _startHudStatusPoll({ pollNow: document.visibilityState === 'visible' });
  });
  window.addEventListener('resize', () => {
    _scheduleProjectFilterSortDividerSync(projectExplorerBody);
  });

  if (typeof onUiEvent === 'function') {
    onUiEvent('app:history-rendered', () => {
      try { renderRailRecent(); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:workflows-rendered', (e) => {
      try { renderRailWorkflows(e.detail && e.detail.items); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:workflows-closed', () => {
      if (typeof renderWorkflowItems === 'function') {
        try { renderWorkflowItems(allWorkflows); } catch (_) { /* non-critical */ }
      }
    });
    onUiEvent('app:tab-status-changed', () => {
      try { _renderTabs(); } catch (_) { /* non-critical */ }
      try { _renderLastExit(); } catch (_) { /* non-critical */ }
      try { refreshHudActions(); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:tab-activated', () => {
      try { _renderLastExit(); } catch (_) { /* non-critical */ }
      try { refreshHudActions(); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:tab-created', () => {
      try { _renderTabs(); } catch (_) { /* non-critical */ }
      try { refreshHudActions(); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:tab-closed', () => {
      try { _renderTabs(); } catch (_) { /* non-critical */ }
      try { refreshHudActions(); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:last-exit-changed', (e) => {
      hudState.lastExit = e.detail ? e.detail.value : null;
      try { _renderLastExit(); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:tab-kill-visibility-changed', (e) => {
      const tabId = e.detail && e.detail.tabId;
      const activeId = (typeof getActiveTabId === 'function') ? getActiveTabId() : null;
      if (tabId !== activeId) return;
      try { _setHudKillVisible(!!(e.detail && e.detail.visible)); } catch (_) { /* non-critical */ }
    });
  }

  // Initial render and pollers.
  _renderLastExit();
  _renderTabs();
  _renderSession();
  _renderClock();
  _renderLatency();
  _renderUptime();
  _renderDb();
  _renderRedis();
  _renderActiveProject();

  _startHudStatusPoll({ pollNow: true });
  setInterval(() => { _renderClock(); _renderUptime(); _renderSession(); }, CLOCK_TICK_MS);

  // ── Init ─────────────────────────────────────────────────────────
  applyCollapsed();
  applyWidth();
  applySectionsState();
  renderRailRecent();
  if (typeof ensureWorkflowCatalogLoaded === 'function') {
    ensureWorkflowCatalogLoaded()
      .then(items => renderRailWorkflows(items))
      .catch(() => {});
  }
  refreshHudActions();
  loadActiveProjectContext().catch(() => {});

  // Expose the workflows renderer for controller.js to call after /workflows loads.
  global.renderHudClock = _renderClock;
  global.toggleRailCollapsed = () => setCollapsed(!ui.collapsed);
  global.getActiveProjectContext = _activeProject;
  global.refreshActiveProjectContext = loadActiveProjectContext;
  global.openProjectWorkspace = openProjectWorkspace;
  global.openProjectAutoPromoteRuleFromAtlas = openProjectAutoPromoteRuleFromAtlas;
  global.closeProjectWorkspace = closeProjectWorkspace;
  global.isProjectWorkspaceOpen = isProjectWorkspaceOpen;
  global.cycleProjectWorkspaceTab = cycleProjectWorkspaceTab;
  global.closeProjectTargetEditor = _closeProjectTargetEditor;
  global.isProjectTargetEditorOpen = isProjectTargetEditorOpen;
  global.isProjectPackageManifestOpen = isProjectPackageManifestOpen;
  global.refreshProjectWorkspace = refreshProjectWorkspace;
  global.notifyProjectWorkspaceChanged = _notifyProjectWorkspaceChanged;

})(globalThis);
;
;
/* /static/js/features/mobile/mobile_running_indicator.js */
// Mobile non-active running-tab indicator.
//
// The mobile status pill reflects the active tab only; this surface gives a
// system-level signal that work is happening on a backgrounded tab.
(function initMobileRunningIndicator(global) {
  if (typeof document === 'undefined') return;

  function createMobileRunningIndicator({
    tabsBarEl = null,
    terminalBarEl = null,
  } = {}) {
    let runningChipEl = null;
    let runningChipCountEl = null;
    let edgeGlowLeftEl = null;
    let edgeGlowRightEl = null;
    let runningCycleIdx = 0;
    let runningSyncRaf = 0;
    let scrollSyncTimer = 0;

    function ensureMounts() {
      if (!terminalBarEl) return;
      if (!runningChipEl) {
        runningChipEl = document.createElement('button');
        runningChipEl.type = 'button';
        runningChipEl.id = 'mobile-running-chip';
        runningChipEl.className = 'mobile-running-chip u-hidden';
        runningChipEl.setAttribute('aria-label', 'Cycle to next running tab');
        runningChipEl.title = 'Cycle to next running tab';
        const dot = document.createElement('span');
        dot.className = 'mobile-running-dot';
        dot.setAttribute('aria-hidden', 'true');
        dot.textContent = '●';
        runningChipCountEl = document.createElement('span');
        runningChipCountEl.className = 'mobile-running-count';
        runningChipCountEl.textContent = '0';
        runningChipEl.append(dot, runningChipCountEl);
        runningChipEl.addEventListener('click', onRunningChipTap);
        terminalBarEl.appendChild(runningChipEl);
      }
      // Edge glows are position:fixed overlays parented to body so they never
      // live inside the tabs-bar flex/scroll chain, which destabilizes iOS
      // Safari momentum scroll.
      if (!edgeGlowLeftEl && document.body) {
        edgeGlowLeftEl = document.createElement('span');
        edgeGlowLeftEl.className = 'tab-edge-glow tab-edge-glow-left';
        edgeGlowLeftEl.setAttribute('aria-hidden', 'true');
        document.body.appendChild(edgeGlowLeftEl);
      }
      if (!edgeGlowRightEl && document.body) {
        edgeGlowRightEl = document.createElement('span');
        edgeGlowRightEl.className = 'tab-edge-glow tab-edge-glow-right';
        edgeGlowRightEl.setAttribute('aria-hidden', 'true');
        document.body.appendChild(edgeGlowRightEl);
      }
    }

    function runningNonActiveTabs() {
      if (!tabsBarEl) return [];
      const tabsList = (typeof global.getTabs === 'function') ? global.getTabs() : null;
      if (!Array.isArray(tabsList)) return [];
      const activeId = (typeof global.getActiveTabId === 'function') ? global.getActiveTabId() : null;
      const byId = new Map(tabsList.map(t => [t.id, t]));
      // Tab-row order is the visual order, not the array order. Drag-reorder
      // mutates the DOM but not the underlying tabs array.
      const orderedIds = Array.from(tabsBarEl.querySelectorAll('.tab')).map(n => n.dataset.id);
      return orderedIds
        .map(id => byId.get(id))
        .filter(t => !!t && t.st === 'running' && t.id !== activeId);
    }

    function scrollTabIntoView(id) {
      if (!tabsBarEl || !id) return;
      const node = tabsBarEl.querySelector(`.tab[data-id="${id}"]`);
      if (!node) return;
      const tabRect = node.getBoundingClientRect();
      const barRect = tabsBarEl.getBoundingClientRect();
      const visibleLeft = tabRect.left >= barRect.left;
      const visibleRight = tabRect.right <= barRect.right;
      if (visibleLeft && visibleRight) return;
      const tabLeftInContent = tabRect.left - barRect.left + tabsBarEl.scrollLeft;
      const centered = tabLeftInContent - (barRect.width - tabRect.width) / 2;
      const maxScroll = Math.max(0, tabsBarEl.scrollWidth - tabsBarEl.clientWidth);
      tabsBarEl.scrollLeft = Math.max(0, Math.min(maxScroll, centered));
    }

    function onRunningChipTap() {
      const running = runningNonActiveTabs();
      if (running.length === 0) return;
      const next = running[runningCycleIdx % running.length];
      runningCycleIdx += 1;
      const activate = (typeof global.activateTab === 'function') ? global.activateTab : null;
      if (activate) activate(next.id, { focusComposer: false });
      // activateTab uses smooth scroll, but iOS Safari can drop the first call
      // on a cold horizontal scroll container. Direct scrollLeft always lands.
      scrollTabIntoView(next.id);
    }

    function hideEdgeGlows() {
      if (edgeGlowLeftEl) edgeGlowLeftEl.classList.remove('is-active');
      if (edgeGlowRightEl) edgeGlowRightEl.classList.remove('is-active');
    }

    function syncEdgeGlows(running) {
      if (!tabsBarEl || !edgeGlowLeftEl || !edgeGlowRightEl) return;
      if (!running || running.length === 0) { hideEdgeGlows(); return; }
      const barRect = tabsBarEl.getBoundingClientRect();
      const top = Math.round(barRect.top) + 'px';
      const height = Math.round(barRect.height) + 'px';
      edgeGlowLeftEl.style.top = top;
      edgeGlowLeftEl.style.height = height;
      edgeGlowLeftEl.style.left = Math.round(barRect.left) + 'px';
      edgeGlowRightEl.style.top = top;
      edgeGlowRightEl.style.height = height;
      edgeGlowRightEl.style.left = Math.round(barRect.right - 22) + 'px';
      let leftActive = false;
      let rightActive = false;
      for (const t of running) {
        const node = tabsBarEl.querySelector(`.tab[data-id="${t.id}"]`);
        if (!node) continue;
        const r = node.getBoundingClientRect();
        if (r.left < barRect.left + 4) leftActive = true;
        if (r.right > barRect.right - 4) rightActive = true;
      }
      edgeGlowLeftEl.classList.toggle('is-active', leftActive);
      edgeGlowRightEl.classList.toggle('is-active', rightActive);
    }

    function applyRunningState() {
      if (!terminalBarEl || !tabsBarEl) return;
      const isMobile = !!(document.body && document.body.classList.contains('mobile-terminal-mode'));
      if (!isMobile) {
        if (runningChipEl) runningChipEl.classList.add('u-hidden');
        hideEdgeGlows();
        return;
      }
      ensureMounts();
      const running = runningNonActiveTabs();
      const count = running.length;
      if (count === 0) {
        runningChipEl.classList.add('u-hidden');
        hideEdgeGlows();
        runningCycleIdx = 0;
        return;
      }
      runningChipEl.classList.remove('u-hidden');
      runningChipCountEl.textContent = String(count);
      syncEdgeGlows(running);
    }

    function sync() {
      if (runningSyncRaf) return;
      runningSyncRaf = (typeof requestAnimationFrame === 'function'
        ? requestAnimationFrame
        : (cb) => setTimeout(cb, 16))(() => {
        runningSyncRaf = 0;
        applyRunningState();
      });
    }

    if (terminalBarEl && tabsBarEl) {
      ensureMounts();
      global.addEventListener?.('resize', sync);
      tabsBarEl.addEventListener('scroll', () => {
        if (scrollSyncTimer) clearTimeout(scrollSyncTimer);
        scrollSyncTimer = setTimeout(sync, 120);
      }, { passive: true });
    }
    if (typeof global.onUiEvent === 'function') {
      global.onUiEvent('app:tab-created', () => sync());
      global.onUiEvent('app:tab-closed', () => sync());
      global.onUiEvent('app:tab-status-changed', () => sync());
      global.onUiEvent('app:tab-activated', () => sync());
      global.onUiEvent('app:tab-order-changed', () => sync());
    }
    sync();

    return { sync };
  }

  global.DarklabMobileRunningIndicator = {
    create: createMobileRunningIndicator,
  };
})(typeof window !== 'undefined' ? window : this);
;
;
/* /static/js/mobile_chrome.js */
// ── Mobile chrome controller ──
// Owns the mobile-only UI: progress bar, recent peek row,
// bottom-sheet menu from the hamburger, and the keyboard-aware edit helper
// row. Loaded after dom.js, state.js, ui_helpers.js, history.js, tabs.js,
// app.js, controller.js, shell_chrome.js so every helper it delegates to is
// already defined.

(function initMobileChrome(global) {
  if (typeof document === 'undefined') return;

  // Bail on desktop-only builds: every mobile-specific node below is absent
  // when the page is rendered without the mobile shell.
  const mobileShell = document.getElementById('mobile-shell');
  if (!mobileShell) return;

  // ── Elements ────────────────────────────────────────────────────
  const mobileShellChrome     = document.getElementById('mobile-shell-chrome');
  const mobileComposer        = document.getElementById('mobile-composer');
  const mobileKillBtn         = document.getElementById('mobile-kill-btn');
  const statusPillEl          = document.getElementById('status');
  const recentPeek            = document.getElementById('mobile-recent-peek');
  const recentPeekCount       = document.getElementById('mobile-recent-peek-count');
  const recentPeekPreview     = document.getElementById('mobile-recent-peek-preview');
  const recentsSheet          = document.getElementById('mobile-recents-sheet');
  const recentsSheetScrim     = document.getElementById('mobile-recents-sheet-scrim');
  const recentsSheetClearBtn  = document.getElementById('mobile-recents-clear');
  const recentsSheetSearch    = document.getElementById('mobile-recents-search');
  const recentsPagination     = document.getElementById('mobile-recents-pagination');
  const recentsPaginationSummary = document.getElementById('mobile-recents-pagination-summary');
  const recentsPaginationControls = document.getElementById('mobile-recents-pagination-controls');
  const recentsSheetList      = document.getElementById('mobile-recents-list');
  const menuSheet             = document.getElementById('mobile-menu-sheet');
  const menuSheetScrim        = document.getElementById('mobile-menu-sheet-scrim');
  const menuLnState           = document.getElementById('mobile-menu-ln-state');
  const menuTsState           = document.getElementById('mobile-menu-ts-state');
  const menuWorkflowsCount    = document.getElementById('mobile-menu-workflows-count');
  const menuSchedulesCount    = document.getElementById('mobile-menu-schedules-count');
  const menuWatchersCount     = document.getElementById('mobile-menu-watchers-count');
  const menuHistoryCount      = document.getElementById('mobile-menu-history-count');
  const menuAtlasHint         = document.getElementById('mobile-menu-atlas-hint');
  const menuFilesHint         = document.getElementById('mobile-menu-files-hint');
  const menuProjectHint       = document.getElementById('mobile-menu-project-hint');
  const menuThemeHint         = document.getElementById('mobile-menu-theme-hint');
  const kbHelper              = document.getElementById('mobile-kb-helper');

  // ── Progress bar mounted programmatically ──────────────────────
  // Placed inside #mobile-shell-chrome so the teleport logic in app.js that
  // moves the tab bar in and out on viewport changes does not clobber them.
  let progressBar  = null;

  function ensureChromeMounts() {
    if (!mobileShellChrome) return;
    if (!progressBar) {
      progressBar = document.createElement('div');
      progressBar.id = 'mobile-progress-bar';
      progressBar.className = 'shell-progress-bar u-hidden';
      mobileShellChrome.appendChild(progressBar);
    }
  }
  ensureChromeMounts();

  // ── Helpers ─────────────────────────────────────────────────────
  const show = (el) => el && el.classList && el.classList.remove('u-hidden');
  const hide = (el) => el && el.classList && el.classList.add('u-hidden');
  const isRunning = () => !!(statusPillEl && statusPillEl.classList && statusPillEl.classList.contains('running'));
  const STATUS_MONITOR_PEEK_PULSE_KEY = 'status_monitor_mobile_peek_seen';
  let _statusMonitorPeekHoldUntil = 0;
  let _statusMonitorPeekTimer = 0;

  // ── 2A+2B: Status-driven progress bar and composer ring ─────────
  function syncRunState() {
    const running = isRunning();
    if (running) {
      show(progressBar);
      if (mobileComposer && mobileComposer.classList) mobileComposer.classList.add('is-running');
    } else {
      hide(progressBar);
      if (mobileComposer && mobileComposer.classList) mobileComposer.classList.remove('is-running');
    }
    // Mobile only: the desktop pill intentionally shows only IDLE/RUNNING
    // (HUD LAST EXIT carries the rest), but with no HUD on mobile, an IDLE
    // label sitting inside a red killed/fail pill reads as a bug. Reflect the
    // terminal state in the pill text so the color and label agree. Gated on
    // body.mobile-terminal-mode so the desktop pill stays binary when the
    // mobile DOM is present but the shell is rendering desktop chrome.
    if (statusPillEl && statusPillEl.classList && document.body.classList.contains('mobile-terminal-mode')) {
      if (statusPillEl.classList.contains('killed')) statusPillEl.textContent = 'KILLED';
      else if (statusPillEl.classList.contains('fail')) statusPillEl.textContent = 'FAILED';
    }
  }

  if (mobileKillBtn) {
    mobileKillBtn.addEventListener('click', () => {
      const tabId = typeof global.getActiveTabId === 'function' ? global.getActiveTabId() : null;
      if (tabId && typeof confirmKill === 'function') confirmKill(tabId);
    });
  }
  if (typeof onUiEvent === 'function') {
    onUiEvent('app:status-changed', () => syncRunState());
  }
  syncRunState();

  // ── Mobile non-active running-state indicator ──
  const runningIndicatorDisabled = (() => {
    try {
      const q = (typeof location !== 'undefined' && location.search) ? location.search : '';
      return /[?&]ri=(?:off|0)\b/.test(q);
    } catch (_) { return false; }
  })();
  const tabsBarEl = runningIndicatorDisabled ? null : document.getElementById('tabs-bar');
  global.DarklabMobileRunningIndicator?.create({
    tabsBarEl,
    terminalBarEl: tabsBarEl ? tabsBarEl.closest('.terminal-bar') : null,
  });

  // ── 2C: Menu sheet ───────────────────────────────────────────────
  function setActionHint(el, text) {
    if (el) el.textContent = text || '';
  }
  function setTogglePressed(labelEl, value) {
    if (!labelEl) return;
    const btn = labelEl.closest('button[data-menu-action]');
    if (!btn) return;
    // Any value other than empty/off counts as "on" — line numbers toggles on/off,
    // but timestamps cycles through off / elapsed / clock so we can't match /^on$/.
    const normalized = typeof value === 'string' ? value.trim().toLowerCase() : '';
    const on = normalized && normalized !== 'off';
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
  }
  function refreshMenuStateHints() {
    // Read current modes from body classes — the canonical source of truth set
    // by output.js / app.js when the user toggles either preference.
    const cls = (document.body && document.body.classList) || null;
    const lnValue = cls && cls.contains('ln-on') ? 'on' : 'off';
    let tsValue = 'off';
    if (cls && cls.contains('ts-elapsed')) tsValue = 'elapsed';
    else if (cls && cls.contains('ts-clock')) tsValue = 'clock';
    setActionHint(menuLnState, lnValue);
    setTogglePressed(menuLnState, lnValue);
    setActionHint(menuTsState, tsValue);
    setTogglePressed(menuTsState, tsValue);
    // Sync the timestamps sub-menu: pressed state on the currently-selected
    // mode, unpressed on the other two. Aria-pressed drives the radio styling.
    menuSheet?.querySelectorAll('[data-menu-action="ts-set"]').forEach((btn) => {
      const isActive = btn.dataset.tsMode === tsValue;
      btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
  }
  function refreshWorkflowsCount(items) {
    if (!menuWorkflowsCount) return;
    const list = Array.isArray(items) ? items : [];
    menuWorkflowsCount.textContent = list.length ? `${list.length} saved` : '';
  }
  function setSavedCount(el, count) {
    if (!el) return;
    const total = Math.max(0, Number(count || 0));
    el.textContent = total > 0 ? `${total} saved` : '';
  }
  function pluralCount(count, singular, plural = `${singular}s`) {
    const total = Math.max(0, Number(count || 0));
    if (!total) return '';
    return `${total} ${total === 1 ? singular : plural}`;
  }
  let schedulesCountRequestSeq = 0;
  function refreshSchedulesCount(items = null) {
    if (!menuSchedulesCount) return;
    if (Array.isArray(items)) {
      setSavedCount(menuSchedulesCount, items.length);
      return;
    }
    if (typeof global.apiFetch !== 'function') return;
    const requestSeq = ++schedulesCountRequestSeq;
    global.apiFetch('/schedules', { cache: 'no-store' })
      .then(resp => resp && resp.ok === false ? Promise.reject(new Error(`HTTP ${resp.status}`)) : resp.json())
      .then(data => {
        if (requestSeq !== schedulesCountRequestSeq) return;
        setSavedCount(menuSchedulesCount, Array.isArray(data?.schedules) ? data.schedules.length : 0);
      })
      .catch((err) => {
        if (typeof logClientError === 'function') logClientError('failed to load schedules count for mobile menu', err);
      });
  }
  let watchersCountRequestSeq = 0;
  function refreshWatchersCount(items = null) {
    if (!menuWatchersCount) return;
    if (Array.isArray(items)) {
      setSavedCount(menuWatchersCount, items.length);
      return;
    }
    if (typeof global.apiFetch !== 'function') return;
    const requestSeq = ++watchersCountRequestSeq;
    global.apiFetch('/watchers', { cache: 'no-store' })
      .then(resp => resp && resp.ok === false ? Promise.reject(new Error(`HTTP ${resp.status}`)) : resp.json())
      .then(data => {
        if (requestSeq !== watchersCountRequestSeq) return;
        setSavedCount(menuWatchersCount, Array.isArray(data?.watchers) ? data.watchers.length : 0);
      })
      .catch((err) => {
        if (typeof logClientError === 'function') logClientError('failed to load watchers count for mobile menu', err);
      });
  }
  let historyCountRequestSeq = 0;
  function setMenuHistoryCount(count) {
    const total = Number(count || 0);
    menuHistoryCount.textContent = total > 0 ? `${total} saved` : '';
  }
  function _recentsTotalCountFromCache() {
    if (!_recentsLoaded) return null;
    const total = Number(_recentsPaging.totalCount || 0);
    return Number.isFinite(total) ? Math.max(0, total) : 0;
  }
  function refreshHistoryCount() {
    if (!menuHistoryCount) return;
    const runs = readCmdHistory();
    setMenuHistoryCount(runs.length);
    const requestSeq = ++historyCountRequestSeq;
    _recentsRefresh({ render: false })
      .then(() => {
        if (requestSeq !== historyCountRequestSeq) return;
        const total = _recentsTotalCountFromCache();
        if (total !== null) setMenuHistoryCount(total);
      })
      .catch(() => {});
  }
  let atlasHintRequestSeq = 0;
  function refreshAtlasHint() {
    if (!menuAtlasHint || typeof global.apiFetch !== 'function') return;
    const requestSeq = ++atlasHintRequestSeq;
    global.apiFetch('/atlas?orphan_filter=hide&suppression_filter=hide', { cache: 'no-store' })
      .then(resp => resp && resp.ok === false ? Promise.reject(new Error(`HTTP ${resp.status}`)) : resp.json())
      .then(data => {
        if (requestSeq !== atlasHintRequestSeq) return;
        const total = Math.max(0, Number(data?.total || 0));
        const findings = Math.max(0, Number(data?.findings || 0));
        menuAtlasHint.textContent = total
          ? pluralCount(total, 'entity', 'entities')
          : pluralCount(findings, 'finding');
      })
      .catch((err) => {
        if (typeof logClientError === 'function') logClientError('failed to load Atlas count for mobile menu', err);
      });
  }
  let filesHintRequestSeq = 0;
  function refreshFilesHint() {
    if (!menuFilesHint || typeof global.apiFetch !== 'function') return;
    const requestSeq = ++filesHintRequestSeq;
    global.apiFetch('/workspace/files', { cache: 'no-store' })
      .then(resp => resp && resp.ok === false ? Promise.reject(new Error(`HTTP ${resp.status}`)) : resp.json())
      .then(data => {
        if (requestSeq !== filesHintRequestSeq) return;
        const usageCount = Number(data?.usage?.file_count);
        const files = Number.isFinite(usageCount) ? usageCount : (Array.isArray(data?.files) ? data.files.length : 0);
        menuFilesHint.textContent = pluralCount(files, 'file');
      })
      .catch((err) => {
        if (typeof logClientError === 'function') logClientError('failed to load Files count for mobile menu', err);
      });
  }
  function _projectHintName(project) {
    if (!project || typeof project !== 'object') return '';
    return String(project.name || project.slug || project.id || '').trim();
  }
  function refreshProjectHint(project) {
    if (!menuProjectHint) return;
    const current = project || (
      typeof global.getActiveProjectContext === 'function'
        ? global.getActiveProjectContext()
        : null
    );
    const name = _projectHintName(current);
    menuProjectHint.textContent = name;
    menuProjectHint.title = name ? `Active project: ${name}` : '';
  }
  function refreshProjectHintFromServer() {
    refreshProjectHint();
    if (typeof global.refreshActiveProjectContext !== 'function') return;
    global.refreshActiveProjectContext()
      .then(project => refreshProjectHint(project))
      .catch((err) => {
        if (typeof logClientError === 'function') logClientError('failed to load active project for mobile menu', err);
      });
  }
  function refreshThemeHint() {
    if (!menuThemeHint) return;
    const name = (document.body && document.body.dataset && document.body.dataset.theme) || '';
    menuThemeHint.textContent = name;
  }
  // Bind the timestamps sub-menu as a disclosure so aria-expanded and the
  // submenu's u-hidden class stay coordinated. The handle is also used by
  // openMenuSheet() to reset the sub-menu to collapsed each time the sheet
  // opens (so the user never returns to a previously-expanded surface).
  const tsToggleBtn = menuSheet?.querySelector('[data-menu-action="ts-toggle"]');
  const tsSubmenuEl = document.getElementById('mobile-menu-ts-submenu');
  const tsDisclosure = tsToggleBtn ? bindDisclosure(tsToggleBtn, {
    panel: tsSubmenuEl,
    openClass: null,
    hiddenClass: 'u-hidden',
  }) : null;

  function openMenuSheet() {
    refreshMenuStateHints();
    refreshThemeHint();
    refreshHistoryCount();
    refreshAtlasHint();
    refreshFilesHint();
    refreshSchedulesCount();
    refreshWatchersCount();
    refreshProjectHintFromServer();
    tsDisclosure?.close();
    show(menuSheetScrim);
    show(menuSheet);
  }
  function closeMenuSheet() {
    hide(menuSheet);
    hide(menuSheetScrim);
  }
  function isMenuSheetOpen() {
    return !!(menuSheet && menuSheet.classList && !menuSheet.classList.contains('u-hidden'));
  }

  // Take over the shared mobile-menu helpers so every caller (hamburger click,
  // outside-click dismissal, overlay coordination) opens the new sheet instead.
  global.showMobileMenu = openMenuSheet;
  global.hideMobileMenu = closeMenuSheet;
  global.isMobileMenuOpen = isMenuSheetOpen;

  function openMobileHistorySurface() {
    if (typeof global.resetHistoryMobileFilters === 'function') {
      global.resetHistoryMobileFilters();
    }
    if (typeof global.openHistoryWithFilters === 'function') {
      global.openHistoryWithFilters();
    } else if (typeof global.dispatchMobileMenuAction === 'function') {
      global.dispatchMobileMenuAction('history', null);
    } else {
      showRecentsSheet();
    }
  }

  // Mobile routes both History entry points to the full History panel so the
  // quick path and menu path expose the same filtering and bulk controls.
  menuSheet?.querySelectorAll('button[data-menu-action]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const action = btn.dataset.menuAction;
      if (action === 'history') {
        e.stopImmediatePropagation();
        closeMenuSheet();
        openMobileHistorySurface();
      }
    }, true);
  });
  // Scrim click + Escape are owned by bindDismissible
  // (ui_dismissible.js) so every sheet/panel/modal surface uses the same
  // registry-driven close cascade instead of hand-rolled wiring.
  if (typeof global.bindDismissible === 'function') {
    global.bindDismissible(menuSheet, {
      level: 'sheet',
      isOpen: isMenuSheetOpen,
      onClose: closeMenuSheet,
      backdropEl: menuSheetScrim,
    });
  }

  // ── 2D: Recent peek ─────────────────────────────────────────────
  function readCmdHistory() {
    const h = global.recentPreviewHistory;
    return Array.isArray(h) ? h : [];
  }
  function _prefersReducedMotion() {
    try {
      return !!(global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches);
    } catch (_) {
      return false;
    }
  }
  function _formatPeekElapsed(runStart) {
    const start = Number(runStart);
    if (!Number.isFinite(start) || start <= 0) return '';
    const seconds = Math.max(0, Math.floor((Date.now() - start) / 1000));
    const minutes = Math.floor(seconds / 60);
    const remainder = String(seconds % 60).padStart(2, '0');
    return `${minutes}:${remainder}`;
  }
  function _syncStatusMonitorPeekTimer(activeRunning) {
    if (activeRunning) {
      if (!_statusMonitorPeekTimer) {
        _statusMonitorPeekTimer = window.setInterval(() => {
          try { renderRecentPeek(); } catch (_) { /* non-critical */ }
        }, 1000);
      }
      return;
    }
    if (_statusMonitorPeekTimer) {
      window.clearInterval(_statusMonitorPeekTimer);
      _statusMonitorPeekTimer = 0;
    }
  }
  function renderRecentPeek() {
    if (!recentPeek) return;
    const activeTab = typeof global.getActiveTab === 'function' ? global.getActiveTab() : null;
    const activeRunning = !!(activeTab && activeTab.st === 'running');
    _syncStatusMonitorPeekTimer(activeRunning);
    const holdStatusMonitor = !activeRunning && _statusMonitorPeekHoldUntil && Date.now() < _statusMonitorPeekHoldUntil;
    if (activeRunning || holdStatusMonitor) {
      recentPeek.dataset.peekMode = 'status-monitor';
      recentPeek.setAttribute('aria-label', 'Open Status Monitor');
      const elapsed = activeRunning ? _formatPeekElapsed(activeTab.runStart) : '';
      if (recentPeekCount) recentPeekCount.textContent = activeRunning ? (elapsed || 'live') : 'done';
      if (recentPeekPreview) {
        recentPeekPreview.textContent = activeRunning
          ? String(activeTab.command || 'active command')
          : 'final state available';
      }
      const label = recentPeek.querySelector('.recent-peek-label');
      if (label) label.textContent = 'Status Monitor';
      show(recentPeek);
      if (activeRunning && !_prefersReducedMotion()) {
        try {
          if (sessionStorage.getItem(STATUS_MONITOR_PEEK_PULSE_KEY) !== '1') {
            sessionStorage.setItem(STATUS_MONITOR_PEEK_PULSE_KEY, '1');
            recentPeek.classList.add('recent-peek-status-monitor-wiggle');
            window.setTimeout(() => recentPeek.classList.remove('recent-peek-status-monitor-wiggle'), 1900);
          }
        } catch (_) {
          if (recentPeek.dataset.statusMonitorWiggled !== '1') {
            recentPeek.dataset.statusMonitorWiggled = '1';
            recentPeek.classList.add('recent-peek-status-monitor-wiggle');
            window.setTimeout(() => recentPeek.classList.remove('recent-peek-status-monitor-wiggle'), 1900);
          }
        }
      }
      return;
    }
    recentPeek.dataset.peekMode = 'recents';
    recentPeek.setAttribute('aria-label', 'Show recent commands');
    const label = recentPeek.querySelector('.recent-peek-label');
    if (label) label.textContent = 'Recent';
    const items = readCmdHistory();
    if (!items.length) { hide(recentPeek); return; }
    if (recentPeekCount) recentPeekCount.textContent = String(items.length);
    if (recentPeekPreview) recentPeekPreview.textContent = items.slice(0, 3).join(' · ');
    show(recentPeek);
  }

  // ── 2D+: Pull-up recents sheet ─────────────────────────────────
  // Populated on open from the /history API so the list reflects persisted
  // runs (not just the in-memory cmdHistory chip list). Row click rehydrates
  // the composer; per-row actions reuse the existing history.js helpers.
  let _recentsItems = [];
  let _recentsSearchQuery = '';
  let _recentsLoaded = false;
  let _recentsFetchInFlight = null;
  let _recentsRequestSeq = 0;
  const _recentsFilterState = { type: 'all', root: '', exit: 'all', date: 'all', starred: false };
  const _recentsPaging = {
    page: 1,
    pageSize: (typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.history_panel_limit)
      ? Math.max(1, Number(APP_CONFIG.history_panel_limit) || 50)
      : 50,
    totalCount: 0,
    pageCount: 0,
    hasPrev: false,
    hasNext: false,
  };

  function _recentsParseDate(iso) {
    if (!iso) return null;
    try {
      const d = new Date(iso);
      return Number.isNaN(d.getTime()) ? null : d;
    } catch (_) { return null; }
  }
  function _recentsFiltersActiveCount() {
    let n = 0;
    if (_recentsFilterState.type !== 'all') n++;
    if (_recentsFilterState.root.trim()) n++;
    if (_recentsFilterState.exit !== 'all') n++;
    if (_recentsFilterState.date !== 'all') n++;
    if (_recentsFilterState.starred) n++;
    return n;
  }
  function _recentsStarred() {
    try {
      if (typeof global._getStarred === 'function') return global._getStarred();
    } catch (_) { /* non-critical */ }
    return new Set();
  }
  function _recentsHasActiveFilters() {
    return Boolean(
      _recentsSearchQuery.trim()
      || _recentsFilterState.type !== 'all'
      || _recentsFilterState.root.trim()
      || _recentsFilterState.exit !== 'all'
      || _recentsFilterState.date !== 'all'
      || _recentsFilterState.starred
    );
  }
  function _recentsBuildHistoryRequestUrl() {
    const params = new URLSearchParams();
    params.set('page', String(_recentsPaging.page || 1));
    params.set('page_size', String(_recentsPaging.pageSize || 1));
    params.set('include_total', '1');
    if (_recentsFilterState.type !== 'all') params.set('type', _recentsFilterState.type);
    if (_recentsSearchQuery.trim()) params.set('q', _recentsSearchQuery.trim());
    if (_recentsFilterState.root.trim()) params.set('command_root', _recentsFilterState.root.trim());
    if (_recentsFilterState.exit === 'success') params.set('exit_code', '0');
    else if (_recentsFilterState.exit === 'failed') params.set('exit_code', 'nonzero');
    if (_recentsFilterState.date === 'today') params.set('date_range', '24h');
    else if (_recentsFilterState.date === 'week') params.set('date_range', '7d');
    if (_recentsFilterState.starred) params.set('starred_only', '1');
    const query = params.toString();
    return query ? `/history?${query}` : '/history';
  }
  function _recentsSetPage(nextPage, { refresh = true } = {}) {
    _recentsPaging.page = Math.max(1, Number(nextPage) || 1);
    if (refresh) _recentsRefresh();
  }
  function _recentsRenderPagination(visibleCount = 0) {
    if (!recentsPagination || !recentsPaginationSummary || !recentsPaginationControls) return;
    const { page, pageSize, totalCount, pageCount } = _recentsPaging;
    const totalLabel = _recentsFilterState.type === 'runs'
      ? (totalCount === 1 ? 'stored run' : 'stored runs')
      : _recentsFilterState.type === 'snapshots'
        ? (totalCount === 1 ? 'stored snapshot' : 'stored snapshots')
        : (totalCount === 1 ? 'stored item' : 'stored items');
    if (totalCount > 0) {
      const start = ((page - 1) * pageSize) + 1;
      const count = Math.max(0, Number(visibleCount) || 0);
      const end = count > 0 ? Math.min(totalCount, start + count - 1) : start;
      recentsPaginationSummary.textContent = `Showing ${start}-${end} of ${totalCount} ${totalLabel}`;
    } else {
      recentsPaginationSummary.textContent = `Showing 0 of 0 ${totalLabel}`;
    }

    recentsPaginationControls.replaceChildren();

    const prevPage = page > 1 ? page - 1 : 1;
    const prevBtn = document.createElement('button');
    prevBtn.type = 'button';
    prevBtn.className = 'btn btn-secondary btn-compact history-pagination-chevron';
    prevBtn.textContent = '‹ Prev';
    prevBtn.disabled = page <= 1;
    prevBtn.setAttribute('aria-label', 'Previous page');
    prevBtn.addEventListener('click', () => _recentsSetPage(prevPage));
    recentsPaginationControls.appendChild(prevBtn);

    const pageLabel = document.createElement('span');
    pageLabel.className = 'history-pagination-status';
    pageLabel.textContent = `Page ${pageCount > 0 ? page : 0} of ${pageCount}`;
    pageLabel.setAttribute('aria-live', 'polite');
    recentsPaginationControls.appendChild(pageLabel);

    const nextPage = pageCount > page ? page + 1 : page;
    const nextBtn = document.createElement('button');
    nextBtn.type = 'button';
    nextBtn.className = 'btn btn-secondary btn-compact history-pagination-chevron';
    nextBtn.textContent = 'Next ›';
    nextBtn.disabled = page >= pageCount;
    nextBtn.setAttribute('aria-label', 'Next page');
    nextBtn.addEventListener('click', () => _recentsSetPage(nextPage));
    recentsPaginationControls.appendChild(nextBtn);

    recentsPagination.classList.remove('u-hidden');
  }
  function _recentsMakeAction(label, handler, role = 'secondary') {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `sheet-item-action btn btn-${role} btn-compact`;
    btn.textContent = label;
    bindPressable(btn, {
      clearPressStyle: true,
      onActivate: (e) => {
        e.stopPropagation();
        try { handler(); } catch (_) { /* non-critical */ }
      },
    });
    return btn;
  }
  function _recentsCloseActionMenus(except = null) {
    recentsSheetList?.querySelectorAll('.sheet-item-action-menu-wrap.open').forEach((wrap) => {
      if (except && wrap === except) return;
      wrap.classList.remove('open');
      wrap.querySelector('.sheet-item-action-menu-trigger')?.setAttribute('aria-expanded', 'false');
      _recentsResetActionMenuPosition(wrap);
    });
  }
  function _recentsResetActionMenuPosition(wrap) {
    const menu = wrap?.querySelector?.('.sheet-item-action-menu');
    if (!menu) return;
    menu.style.position = '';
    menu.style.left = '';
    menu.style.top = '';
    menu.style.right = '';
    menu.style.bottom = '';
    menu.style.width = '';
    menu.style.maxHeight = '';
    menu.style.overflowY = '';
    wrap.classList.add('save-menu-down');
  }
  function _recentsPositionActionMenu(wrap) {
    const trigger = wrap?.querySelector?.('.sheet-item-action-menu-trigger');
    const menu = wrap?.querySelector?.('.sheet-item-action-menu');
    if (!trigger || !menu || typeof trigger.getBoundingClientRect !== 'function') return;
    const triggerRect = trigger.getBoundingClientRect();
    const sheetRect = recentsSheet?.getBoundingClientRect?.();
    const viewportHeight = typeof window !== 'undefined'
      ? window.innerHeight
      : document.documentElement.clientHeight;
    const gutter = 8;
    const lowerBound = Math.min(viewportHeight || 0, sheetRect?.bottom || viewportHeight || 0) - gutter;
    const upperBound = Math.max(0, sheetRect?.top || 0) + gutter;
    const spaceBelow = Math.max(0, lowerBound - triggerRect.bottom);
    const spaceAbove = Math.max(0, triggerRect.top - upperBound);
    const viewportWidth = typeof window !== 'undefined'
      ? window.innerWidth
      : document.documentElement.clientWidth;
    const menuWidth = Math.max(190, menu.offsetWidth || 190);
    const menuHeight = Math.max(1, menu.scrollHeight || menu.offsetHeight || 1);
    const openDown = spaceBelow >= menuHeight || spaceBelow >= spaceAbove;
    wrap.classList.toggle('save-menu-down', openDown);
    const availableSpace = openDown ? spaceBelow : spaceAbove;
    const left = Math.min(
      Math.max(gutter, triggerRect.right - menuWidth),
      Math.max(gutter, (viewportWidth || menuWidth) - menuWidth - gutter),
    );
    const top = openDown
      ? triggerRect.bottom + 4
      : Math.max(gutter, triggerRect.top - Math.min(menuHeight, Math.max(44, availableSpace)) - 4);
    menu.style.position = 'fixed';
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
    menu.style.right = 'auto';
    menu.style.bottom = 'auto';
    menu.style.width = `${menuWidth}px`;
    if (menuHeight > availableSpace && availableSpace > 0) {
      menu.style.maxHeight = `${Math.max(44, availableSpace)}px`;
      menu.style.overflowY = 'auto';
    } else {
      menu.style.maxHeight = '';
      menu.style.overflowY = '';
    }
  }
  function _recentsCopyCommand(run) {
    const command = run?.command || '';
    if (typeof global.copyTextToClipboard !== 'function') return;
    global.copyTextToClipboard(command)
      .then(() => global.showToast && global.showToast('Command copied'))
      .catch(() => global.showToast && global.showToast('Failed to copy command', 'error'));
  }
  function _recentsCanManageHistory() {
    return typeof global.activeTeamScopeCan === 'function'
      ? global.activeTeamScopeCan('manage_history')
      : true;
  }
  function _recentsCanMutateProjects() {
    return typeof global.activeTeamScopeCan === 'function'
      ? global.activeTeamScopeCan('mutate_projects')
      : true;
  }
  function _recentsRunActionMenu(run) {
    const wrap = document.createElement('div');
    wrap.className = 'sheet-item-action-menu-wrap save-menu-wrap save-menu-down';
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'sheet-item-action sheet-item-action-menu-trigger btn btn-secondary btn-compact';
    trigger.textContent = 'more';
    trigger.setAttribute('aria-label', 'More run actions');
    trigger.setAttribute('aria-haspopup', 'menu');
    trigger.setAttribute('aria-expanded', 'false');
    const menu = document.createElement('div');
    menu.className = 'sheet-item-action-menu save-menu dropdown-surface';
    menu.setAttribute('role', 'menu');
    const addItem = (label, handler) => {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'dropdown-item dropdown-item-compact';
      item.setAttribute('role', 'menuitem');
      item.textContent = label;
      item.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        _recentsCloseActionMenus();
        handler();
      });
      menu.appendChild(item);
    };
    addItem('permalink', () => {
      if (!run.id) return;
      const url = `${location.origin}/history/${run.id}`;
      if (typeof global.shareUrl === 'function') {
        global.shareUrl(url).catch(() => global.showToast && global.showToast('Share failed', 'error'));
      }
    });
    addItem('compare', () => {
      if (typeof global.openHistoryCompareLauncher === 'function') {
        global.openHistoryCompareLauncher(run);
        closeRecentsSheet();
      }
    });
    if (_recentsCanManageHistory()) {
      addItem('edit', () => {
        if (typeof global._historyEditEntityMetadata === 'function') global._historyEditEntityMetadata('run', run);
      });
    }
    if (_recentsCanMutateProjects()) {
      addItem('add to active project', () => {
        if (typeof global._historyAddRunToActiveProject === 'function') {
          global._historyAddRunToActiveProject(run)
            .catch(() => global.showToast && global.showToast('Failed to add run to active project', 'error'));
        }
      });
      addItem('add to project', () => {
        if (typeof global._historyAddRunToProject === 'function') {
          global._historyAddRunToProject(run)
            .catch(() => global.showToast && global.showToast('Failed to add run to project', 'error'));
        }
      });
    }
    addItem('copy run id', () => {
      if (typeof global.copyTextToClipboard === 'function') {
        global.copyTextToClipboard(run.id)
          .then(() => global.showToast && global.showToast('Run ID copied'))
          .catch(() => global.showToast && global.showToast('Failed to copy run ID', 'error'));
      }
    });
    if (_recentsCanManageHistory()) {
      addItem('delete', () => {
        if (run.id && typeof global.confirmHistAction === 'function') {
          global.confirmHistAction('delete', run.id, run.command, 'run');
        }
      });
    }
    bindPressable(trigger, {
      refocusComposer: false,
      clearPressStyle: true,
      onActivate: (event) => {
        event.preventDefault();
        event.stopPropagation();
        const open = !wrap.classList.contains('open');
        _recentsCloseActionMenus(open ? wrap : null);
        wrap.classList.toggle('open', open);
        trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (open) {
          _recentsPositionActionMenu(wrap);
        } else {
          _recentsResetActionMenuPosition(wrap);
        }
      },
    });
    wrap.append(trigger, menu);
    return wrap;
  }
  function _recentsMakeKindBadge(kind, label = kind.toUpperCase()) {
    const badge = document.createElement('span');
    const tone = kind === 'run' ? 'badge-tone-green' : 'badge-tone-muted';
    badge.className = `sheet-item-kind sheet-item-kind-${kind} badge ${tone}`;
    badge.textContent = label;
    return badge;
  }
  const RECENTS_GRACEFUL_TERMINATION_EXIT_CODES = new Set([-15]);
  function _recentsExitCodeNumber(exitCode) {
    if (exitCode === null || exitCode === undefined || exitCode === '') return null;
    const number = Number(exitCode);
    return Number.isFinite(number) ? number : null;
  }
  function _recentsIsGracefulTerminationExitCode(exitCode) {
    const code = _recentsExitCodeNumber(exitCode);
    return code !== null && RECENTS_GRACEFUL_TERMINATION_EXIT_CODES.has(code);
  }
  function _recentsIsFailedExitCode(exitCode) {
    const code = _recentsExitCodeNumber(exitCode);
    return code !== null && code !== 0 && !RECENTS_GRACEFUL_TERMINATION_EXIT_CODES.has(code);
  }
  function _recentsExitLabel(exitCode) {
    const code = _recentsExitCodeNumber(exitCode);
    if (code === null) return '—';
    return _recentsIsGracefulTerminationExitCode(code) ? 'terminated' : `exit ${code}`;
  }
  function _recentsSnapshotUrl(item) {
    return `${location.origin}/share/${item.id}`;
  }
  function _recentsOpenSnapshot(item) {
    if (!item || !item.id || typeof window === 'undefined' || !window || typeof window.open !== 'function') return;
    window.open(_recentsSnapshotUrl(item), '_blank', 'noopener,noreferrer');
  }
  function _recentsRenderList() {
    if (!recentsSheetList) return;
    recentsSheetList.replaceChildren();
    const starred = _recentsStarred();
    if (!_recentsItems.length) {
      const empty = document.createElement('div');
      empty.className = 'sheet-item chrome-row';
      empty.style.color = 'var(--muted)';
      empty.style.opacity = '0.7';
      empty.style.justifyContent = 'center';
      empty.style.alignItems = 'center';
      empty.textContent = _recentsHasActiveFilters()
        ? 'no matches'
        : _recentsFilterState.type === 'snapshots'
          ? 'no snapshots yet'
          : _recentsFilterState.type === 'runs'
            ? 'no recent commands'
            : 'no history yet';
      recentsSheetList.appendChild(empty);
      _recentsRenderPagination(0);
      return;
    }
    _recentsItems.forEach((entryData) => {
      const isRun = entryData.type !== 'snapshot';
      const run = isRun ? entryData : null;
      const snapshot = isRun ? null : entryData;
      const cmd = run?.command || '';
      const isStarred = isRun && starred.has(cmd);
      const item = document.createElement('div');
      item.className = 'sheet-item chrome-row';
      if (cmd) item.dataset.cmd = cmd;

      const head = document.createElement('div');
      head.className = 'sheet-item-head';
      const star = document.createElement('span');
      star.className = 'sheet-item-star' + (isStarred ? ' starred' : '');
      if (isRun) {
        star.textContent = isStarred ? '★' : '☆';
        star.setAttribute('role', 'button');
        star.setAttribute('tabindex', '0');
        const starLabel = isStarred
          ? 'Unstar — stop pinning this command to the top'
          : 'Star — keep this command pinned at the top';
        star.setAttribute('aria-label', starLabel);
        star.title = starLabel;
        bindPressable(star, {
          refocusComposer: false,
          clearPressStyle: true,
          onActivate: (e) => {
            e.stopPropagation();
            if (typeof global._toggleStar === 'function') {
              try { global._toggleStar(cmd); } catch (_) { /* non-critical */ }
            }
            _recentsRenderList();
            if (_recentsFilterState.starred) _recentsRefresh();
          },
        });
      } else {
        star.textContent = '⬚';
        star.setAttribute('aria-hidden', 'true');
      }
      const cmdEl = document.createElement('span');
      cmdEl.className = 'sheet-item-cmd';
      cmdEl.textContent = isRun ? cmd : (snapshot.label || 'snapshot');
      head.appendChild(star);
      head.appendChild(cmdEl);

      const meta = document.createElement('div');
      meta.className = 'sheet-item-meta';
      meta.appendChild(_recentsMakeKindBadge(isRun ? 'run' : 'snapshot'));
      const timeEl = document.createElement('span');
      timeEl.className = 'sheet-item-time';
      const parsed = _recentsParseDate(isRun ? run.started : snapshot.created);
      const relFn = typeof _historyRelativeTime === 'function' ? _historyRelativeTime : null;
      timeEl.textContent = parsed && relFn ? relFn(parsed) : '';
      if (parsed) timeEl.title = parsed.toLocaleString();
      meta.appendChild(timeEl);
      if (isRun) {
        const exitEl = document.createElement('span');
        const exitCode = (run.exit_code ?? null);
        exitEl.className = 'sheet-item-exit' + (_recentsIsFailedExitCode(exitCode) ? ' nonzero' : '');
        exitEl.textContent = _recentsExitLabel(exitCode);
        meta.appendChild(exitEl);
      }

      const actions = document.createElement('div');
      actions.className = 'sheet-item-actions';
      if (isRun) {
        actions.appendChild(_recentsMakeAction('copy command', () => _recentsCopyCommand(run)));
        actions.appendChild(_recentsMakeAction('restore', () => {
          if (typeof global.restoreHistoryRunIntoTab !== 'function') return;
          const cmdEl2 = item.querySelector('.sheet-item-cmd');
          if (cmdEl2) cmdEl2.textContent = 'loading…';
          global.restoreHistoryRunIntoTab(run, { hidePanelOnSuccess: false })
            .then(() => closeRecentsSheet())
            .catch(() => {
              if (cmdEl2) cmdEl2.textContent = cmd;
              if (typeof global.showToast === 'function') global.showToast('Failed to load run');
            });
        }));
        actions.appendChild(_recentsRunActionMenu(run));
      } else {
        actions.appendChild(_recentsMakeAction('open', () => {
          _recentsOpenSnapshot(snapshot);
          closeRecentsSheet();
        }));
        actions.appendChild(_recentsMakeAction('copy link', () => {
          if (typeof global.shareUrl === 'function') {
            global.shareUrl(_recentsSnapshotUrl(snapshot))
              .catch(() => global.showToast && global.showToast('Share failed', 'error'));
          }
        }));
      }
      if (!isRun) {
        if (_recentsCanManageHistory()) {
          actions.appendChild(_recentsMakeAction('delete', () => {
            if (!entryData.id) return;
            if (typeof global.confirmHistAction === 'function') {
              global.confirmHistAction('delete', entryData.id, snapshot.label, 'snapshot');
            }
          }));
        }
      }

      item.appendChild(head);
      item.appendChild(meta);
      item.appendChild(actions);

      item.addEventListener('click', (e) => {
        if (e.target.closest('.sheet-item-action, .sheet-item-star, .sheet-item-action-menu-wrap')) return;
        _recentsCloseActionMenus();
        if (!isRun) {
          _recentsOpenSnapshot(snapshot);
          closeRecentsSheet();
          return;
        }
        if (typeof global.openHistoryRunDetails === 'function') {
          global.openHistoryRunDetails(run);
          closeRecentsSheet();
          return;
        }
        if (typeof global.setComposerValue === 'function') global.setComposerValue(cmd, cmd.length, cmd.length);
        closeRecentsSheet();
      });

      recentsSheetList.appendChild(item);
    });
    _recentsRenderPagination(_recentsItems.length);
  }
  function _recentsRenderLoading() {
    if (!recentsSheetList) return;
    recentsSheetList.replaceChildren();
    const loading = document.createElement('div');
    loading.className = 'sheet-item chrome-row';
    loading.style.color = 'var(--muted)';
    loading.style.opacity = '0.7';
    loading.style.justifyContent = 'center';
    loading.style.alignItems = 'center';
    loading.textContent = 'loading history...';
    recentsSheetList.appendChild(loading);
    _recentsRenderPagination(0);
  }
  function _recentsRefresh({ render = true } = {}) {
    if (typeof global.apiFetch !== 'function') return Promise.resolve([]);
    const requestUrl = _recentsBuildHistoryRequestUrl();
    const requestSeq = ++_recentsRequestSeq;
    const request = global.apiFetch(requestUrl)
      .then(r => r.json())
      .then(data => {
        if (requestSeq !== _recentsRequestSeq) return _recentsItems;
        _recentsPaging.page = Math.max(1, Number(data.page) || _recentsPaging.page || 1);
        _recentsPaging.pageSize = Math.max(1, Number(data.page_size) || _recentsPaging.pageSize || 1);
        _recentsPaging.totalCount = Math.max(0, Number(data.total_count ?? data.items?.length ?? data.runs?.length ?? 0) || 0);
        _recentsPaging.pageCount = Math.max(0, Number(data.page_count) || 0);
        _recentsPaging.hasPrev = !!data.has_prev;
        _recentsPaging.hasNext = !!data.has_next;
        _recentsItems = Array.isArray(data.items) ? data.items : (Array.isArray(data.runs) ? data.runs : []);
        _recentsLoaded = true;
        if (render || isRecentsSheetOpen()) _recentsRenderList();
        return _recentsItems;
      })
      .catch(() => {
        if (requestSeq !== _recentsRequestSeq) return _recentsItems;
        _recentsItems = [];
        _recentsLoaded = false;
        _recentsPaging.totalCount = 0;
        _recentsPaging.pageCount = 0;
        _recentsPaging.hasPrev = false;
        _recentsPaging.hasNext = false;
        if (render || isRecentsSheetOpen()) _recentsRenderList();
        return [];
      });
    _recentsFetchInFlight = request.finally(() => {
      if (_recentsFetchInFlight === request && requestSeq === _recentsRequestSeq) _recentsFetchInFlight = null;
    });
    return _recentsFetchInFlight;
  }
  function _recentsPrefetch() {
    if (_recentsLoaded || _recentsFetchInFlight) return _recentsFetchInFlight || Promise.resolve(_recentsItems);
    return _recentsRefresh({ render: false });
  }
  function showRecentsSheet() {
    if (!recentsSheet) return;
    _recentsSearchQuery = '';
    if (recentsSheetSearch) recentsSheetSearch.value = '';
    if (typeof global.blurVisibleComposerInputIfMobile === 'function') {
      try { global.blurVisibleComposerInputIfMobile(); } catch (_) { /* non-critical */ }
    }
    // Reset filter UI each open so users don't inherit stale state.
    _recentsFilterState.type = 'all';
    _recentsFilterState.root = '';
    _recentsFilterState.exit = 'all';
    _recentsFilterState.date = 'all';
    _recentsFilterState.starred = false;
    _recentsPaging.page = 1;
    if (recentsFiltersToggle) recentsFiltersToggle.setAttribute('aria-expanded', 'false');
    if (recentsFiltersExpanded) recentsFiltersExpanded.classList.add('u-hidden');
    _recentsSyncFilterUI();
    _recentsRenderLoading();
    show(recentsSheetScrim);
    show(recentsSheet);
    _recentsRefresh();
  }
  function closeRecentsSheet() {
    _closeRecentsDropdowns();
    _recentsCloseActionMenus();
    hide(recentsSheet);
    hide(recentsSheetScrim);
  }
  function isRecentsSheetOpen() {
    return !!(recentsSheet && recentsSheet.classList && !recentsSheet.classList.contains('u-hidden'));
  }

  // Scrim click + Escape are owned by bindDismissible so
  // the sheet participates in the unified modal > sheet > panel Escape
  // cascade (see ui_dismissible.js).
  if (typeof global.bindDismissible === 'function') {
    global.bindDismissible(recentsSheet, {
      level: 'sheet',
      isOpen: isRecentsSheetOpen,
      onClose: closeRecentsSheet,
      backdropEl: recentsSheetScrim,
    });
  }
  if (recentsSheetClearBtn) {
    bindPressable(recentsSheetClearBtn, {
      refocusComposer: false,
      clearPressStyle: true,
      onActivate: () => {
        if (!_recentsCanManageHistory()) return;
        if (typeof global.confirmHistAction === 'function') {
          global.confirmHistAction('clear');
        }
      },
    });
  }

  if (typeof onUiEvent === 'function') {
    onUiEvent('app:history-panel-refreshed', () => {
      if (isRecentsSheetOpen()) _recentsRefresh();
    });
  }
  _recentsPrefetch();

  let _recentsSearchTimer = null;
  recentsSheetSearch?.addEventListener('input', (e) => {
    _recentsSearchQuery = e.target.value || '';
    if (_recentsSearchTimer) clearTimeout(_recentsSearchTimer);
    _recentsSearchTimer = setTimeout(() => {
      _recentsPaging.page = 1;
      _recentsRefresh();
    }, 100);
  });

  recentsSheetList?.addEventListener('touchmove', () => {
    if (recentsSheetSearch && document.activeElement === recentsSheetSearch) {
      recentsSheetSearch.blur();
    }
  }, { passive: true });

  // Drag/tap/keyboard close behavior is provided by the shared bindMobileSheet
  // helper (see app/static/js/ui/mobile_sheet.js) so the recents sheet matches
  // every other mobile bottom sheet.
  if (typeof global.bindMobileSheet === 'function') {
    global.bindMobileSheet(recentsSheet, { onClose: closeRecentsSheet });
  }

  const recentsFiltersToggle   = document.getElementById('mobile-recents-filters-toggle');
  const recentsFiltersExpanded = document.getElementById('mobile-recents-filters-expanded');
  const recentsFiltersClear    = document.getElementById('mobile-recents-filters-clear');
  const recentsFilterRoot      = document.getElementById('mobile-recents-filter-root');
  const recentsFilterStarred   = recentsSheet?.querySelector('[data-recents-filter="starred"]') || null;
  const recentsDropdowns       = Array.from(recentsSheet?.querySelectorAll('[data-recents-dropdown]') || []);
  const recentsChipsEl         = document.getElementById('mobile-recents-chips');
  const _dropdownLabels = {
    type: { all: 'all', runs: 'runs', snapshots: 'snapshots' },
    exit: { all: 'all', success: 'success (0)', failed: 'failed' },
    date: { all: 'all', today: 'today', week: 'this week' },
  };
  // Short labels used inside the active-filter chips (desktop uses the same
  // pattern: shorter inside chips than inside the filter rows).
  const _chipLabels = {
    type: { runs: 'runs', snapshots: 'snapshots' },
    exit: { success: 'exit 0', failed: 'failed' },
    date: { today: 'today', week: 'past week' },
  };

  function _recentsResetRunOnlyFilters() {
    _recentsFilterState.root = '';
    _recentsFilterState.exit = 'all';
    _recentsFilterState.starred = false;
  }

  function _clearOneFilter(key) {
    if (key === 'type')    _recentsFilterState.type = 'all';
    if (key === 'root')    _recentsFilterState.root = '';
    if (key === 'exit')    _recentsFilterState.exit = 'all';
    if (key === 'date')    _recentsFilterState.date = 'all';
    if (key === 'starred') _recentsFilterState.starred = false;
    _recentsSyncFilterUI();
    _recentsPaging.page = 1;
    _recentsRefresh();
  }

  function _renderRecentsChips() {
    if (!recentsChipsEl) return;
    recentsChipsEl.replaceChildren();
    const push = (key, text) => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'filter-chip chip chip-removable';
      chip.dataset.chipKey = key;
      chip.setAttribute('aria-label', `Clear filter ${text}`);
      const label = document.createElement('span');
      label.textContent = text;
      const x = document.createElement('span');
      x.className = 'filter-chip-x';
      x.textContent = '×';
      chip.append(label, x);
      bindPressable(chip, {
        refocusComposer: false,
        clearPressStyle: true,
        onActivate: () => _clearOneFilter(key),
      });
      recentsChipsEl.appendChild(chip);
    };
    const s = _recentsFilterState;
    if (s.type !== 'all')      push('type',    _chipLabels.type[s.type] || s.type);
    if (s.root.trim())        push('root',    `command: ${s.root.trim()}`);
    if (s.exit !== 'all')     push('exit',    _chipLabels.exit[s.exit] || s.exit);
    if (s.date !== 'all')     push('date',    _chipLabels.date[s.date] || s.date);
    if (s.starred)            push('starred', 'starred');
  }

  function _closeRecentsDropdowns(except) {
    recentsDropdowns.forEach(wrap => {
      if (wrap === except) return;
      wrap.classList.remove('open');
      wrap.querySelector('.sheet-filter-dropdown')?.setAttribute('aria-expanded', 'false');
    });
  }

  function _recentsSyncFilterUI() {
    const runOnlyEnabled = _recentsFilterState.type !== 'snapshots';
    if (recentsSheetClearBtn) {
      const showClear = runOnlyEnabled && _recentsCanManageHistory();
      recentsSheetClearBtn.classList.toggle('u-hidden', !showClear);
      recentsSheetClearBtn.disabled = !showClear;
    }
    if (recentsFilterRoot) {
      recentsFilterRoot.value = _recentsFilterState.root;
      recentsFilterRoot.closest('.sheet-filter-row')?.classList.toggle('active', !!_recentsFilterState.root.trim());
      recentsFilterRoot.disabled = !runOnlyEnabled;
    }
    recentsDropdowns.forEach(wrap => {
      const key = wrap.dataset.recentsDropdown;
      const val = _recentsFilterState[key] || 'all';
      const labelMap = _dropdownLabels[key] || {};
      const labelEl = wrap.querySelector('[data-dropdown-label]');
      const trigger = wrap.querySelector('.sheet-filter-dropdown');
      if (labelEl) labelEl.textContent = labelMap[val] || val;
      wrap.classList.toggle('active', val !== 'all');
      if (trigger) trigger.disabled = !runOnlyEnabled && key === 'exit';
      wrap.querySelectorAll('[data-dropdown-value]').forEach(opt => {
        const active = opt.dataset.dropdownValue === val;
        opt.setAttribute('aria-selected', active ? 'true' : 'false');
        opt.classList.toggle('dropdown-item-active', active);
      });
    });
    if (recentsFilterStarred) {
      recentsFilterStarred.setAttribute('aria-pressed', _recentsFilterState.starred ? 'true' : 'false');
      recentsFilterStarred.disabled = !runOnlyEnabled;
    }
    if (recentsFiltersToggle) {
      const count = _recentsFiltersActiveCount();
      const open = recentsFiltersToggle.getAttribute('aria-expanded') === 'true';
      const labelEl = recentsFiltersToggle.querySelector('.sheet-filter-toggle-label');
      const text = (open ? 'hide filters' : 'filters') + (count ? ` (${count})` : '');
      if (labelEl) labelEl.textContent = text;
      else recentsFiltersToggle.textContent = text;
    }
    _renderRecentsChips();
  }

  if (recentsFiltersToggle) {
    bindDisclosure(recentsFiltersToggle, {
      panel: recentsFiltersExpanded,
      openClass: null,
      hiddenClass: 'u-hidden',
      clearPressStyle: true,
      onToggle: (open) => {
        if (!open) _closeRecentsDropdowns();
        // _recentsSyncFilterUI() rewrites the toggle label ("filters" vs
        // "hide filters") using the just-synced aria-expanded value, so it
        // must run after the helper's sync(), which is already the order
        // onToggle fires in.
        _recentsSyncFilterUI();
      },
    });
  }

  let _recentsRootTimer = null;
  recentsFilterRoot?.addEventListener('input', (e) => {
    _recentsFilterState.root = e.target.value || '';
    if (_recentsRootTimer) clearTimeout(_recentsRootTimer);
    _recentsRootTimer = setTimeout(() => {
      _recentsSyncFilterUI();
      _recentsPaging.page = 1;
      _recentsRefresh();
    }, 100);
  });

  recentsDropdowns.forEach(wrap => {
    const key = wrap.dataset.recentsDropdown;
    const trigger = wrap.querySelector('.sheet-filter-dropdown');
    if (trigger) {
      bindPressable(trigger, {
        refocusComposer: false,
        clearPressStyle: true,
        onActivate: () => {
          const open = wrap.classList.contains('open');
          _closeRecentsDropdowns(open ? null : wrap);
          wrap.classList.toggle('open', !open);
          trigger.setAttribute('aria-expanded', !open ? 'true' : 'false');
        },
      });
    }
    wrap.querySelectorAll('[data-dropdown-value]').forEach(opt => {
      bindPressable(opt, {
        refocusComposer: false,
        clearPressStyle: true,
        onActivate: () => {
          _recentsFilterState[key] = opt.dataset.dropdownValue;
          if (key === 'type' && _recentsFilterState.type === 'snapshots') _recentsResetRunOnlyFilters();
          wrap.classList.remove('open');
          trigger?.setAttribute('aria-expanded', 'false');
          _recentsSyncFilterUI();
          _recentsPaging.page = 1;
          _recentsRefresh();
        },
      });
    });
  });

  // Close dropdowns on ambient click anywhere in the recents sheet that
  // doesn't land inside a dropdown. bindOutsideClickClose owns the trigger
  // exemption: clicks on the dropdown triggers / option items bubble up but
  // are skipped because they're inside [data-recents-dropdown].
  if (recentsSheet && typeof bindOutsideClickClose === 'function') {
    bindOutsideClickClose(null, {
      scope: recentsSheet,
      isOpen: () => recentsDropdowns.some(w => w.classList.contains('open')),
      onClose: () => _closeRecentsDropdowns(),
      exemptSelectors: ['[data-recents-dropdown]'],
    });
  }

  if (recentsFilterStarred) {
    bindPressable(recentsFilterStarred, {
      refocusComposer: false,
      clearPressStyle: true,
      onActivate: () => {
        _recentsFilterState.starred = !_recentsFilterState.starred;
        _recentsSyncFilterUI();
        _recentsPaging.page = 1;
        _recentsRefresh();
      },
    });
  }

  if (recentsFiltersClear) {
    bindPressable(recentsFiltersClear, {
      refocusComposer: false,
      clearPressStyle: true,
      onActivate: () => {
        _recentsFilterState.type = 'all';
        _recentsFilterState.root = '';
        _recentsFilterState.exit = 'all';
        _recentsFilterState.date = 'all';
        _recentsFilterState.starred = false;
        _recentsPaging.page = 1;
        _closeRecentsDropdowns();
        _recentsSyncFilterUI();
        _recentsRefresh();
      },
    });
  }

  // Escape-to-close is owned by bindDismissible's unified dispatcher
  // (closeTopmostDismissible). The sheets are registered above so they
  // participate in the same modal > sheet > panel cascade as every
  // other surface.

  // Peek: tap opens the sheet; vertical swipe-up also opens it.
  function openPeekSurface(event) {
    if (event && typeof event.stopPropagation === 'function') event.stopPropagation();
    if (recentPeek && recentPeek.dataset.peekMode === 'status-monitor') {
      if (typeof global.openStatusMonitor === 'function') void global.openStatusMonitor({ source: 'mobile-peek' });
      return;
    }
    openMobileHistorySurface();
  }
  if (recentPeek) {
    // role="button" div — Enter/Space handled by bindPressable; opt into
    // clearPressStyle so the :hover/:active residue on touch doesn't stick
    // after activation (native blur is a no-op on non-focusable elements).
    bindPressable(recentPeek, {
      refocusComposer: false,
      clearPressStyle: true,
      onActivate: openPeekSurface,
    });
  }

  if (recentPeek) {
    let peekStartY = null;
    recentPeek.addEventListener('pointerdown', (e) => { peekStartY = e.clientY; });
    recentPeek.addEventListener('pointermove', (e) => {
      if (peekStartY === null) return;
      const dy = peekStartY - e.clientY;
      if (dy > 8) {
        peekStartY = null;
        openPeekSurface();
      }
    });
    const endPeekDrag = () => { peekStartY = null; };
    recentPeek.addEventListener('pointerup', endPeekDrag);
    recentPeek.addEventListener('pointercancel', endPeekDrag);
  }

  if (typeof onUiEvent === 'function') {
    onUiEvent('app:history-rendered', () => {
      try { renderRecentPeek(); } catch (_) { /* non-critical */ }
      if (isMenuSheetOpen()) {
        try { refreshHistoryCount(); } catch (_) { /* non-critical */ }
      }
    });
    onUiEvent('app:tab-status-changed', (e) => {
      const activeId = typeof global.getActiveTabId === 'function' ? global.getActiveTabId() : null;
      const activeTab = typeof global.getActiveTab === 'function' ? global.getActiveTab() : null;
      const detail = e && e.detail ? e.detail : {};
      const suppressStatusMonitorHold = !!(activeTab && activeTab.suppressStatusMonitorPeekHold);
      if (detail.id === activeId && detail.status && detail.status !== 'running' && suppressStatusMonitorHold) {
        _statusMonitorPeekHoldUntil = 0;
      } else if (detail.id === activeId && detail.status && detail.status !== 'running') {
        _statusMonitorPeekHoldUntil = Date.now() + 2500;
        window.setTimeout(() => {
          try { renderRecentPeek(); } catch (_) { /* non-critical */ }
        }, 2550);
      }
      try { renderRecentPeek(); } catch (_) { /* non-critical */ }
      if (isMenuSheetOpen()) {
        try { refreshHistoryCount(); } catch (_) { /* non-critical */ }
      }
    });
    onUiEvent('app:tab-activated', () => {
      _statusMonitorPeekHoldUntil = 0;
      try { renderRecentPeek(); } catch (_) { /* non-critical */ }
    });
  }
  renderRecentPeek();

  // Mirror the workflows list count into the menu-sheet hint so "workflows"
  // advertises how many are available without opening the overlay.
  if (typeof onUiEvent === 'function') {
    onUiEvent('app:workflows-rendered', (e) => {
      try { refreshWorkflowsCount(e.detail && e.detail.items); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:schedules-rendered', (e) => {
      try { refreshSchedulesCount(e.detail && e.detail.items); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:watchers-rendered', (e) => {
      try { refreshWatchersCount(e.detail && e.detail.items); } catch (_) { /* non-critical */ }
    });
    onUiEvent('app:active-project-changed', (e) => {
      try { refreshProjectHint(e.detail && e.detail.project); } catch (_) { /* non-critical */ }
    });
  }

  // ── 2E: Keyboard helper row ─────────────────────────────────────
  function syncKbHelper() {
    const open = !!(document.body && document.body.classList
                    && document.body.classList.contains('mobile-keyboard-open'));
    if (open) {
      show(kbHelper);
    } else {
      hide(kbHelper);
    }
  }
  if (typeof onUiEvent === 'function') {
    onUiEvent('app:mobile-keyboard-state', () => syncKbHelper());
  }
  syncKbHelper();

  // Invoke the shared edit action directly. preventDefault on pointerdown keeps
  // the composer input from losing focus when a helper key is tapped.
  kbHelper?.querySelectorAll('button[data-kb-action]').forEach(btn => {
    const action = btn.dataset.kbAction;
    const fire = () => {
      if (typeof global.performMobileEditAction === 'function') {
        try { global.performMobileEditAction(action); } catch (_) { /* non-critical */ }
      }
    };
    btn.addEventListener('pointerdown', (e) => { e.preventDefault(); fire(); });
    btn.addEventListener('mousedown',   (e) => { e.preventDefault(); });
    btn.addEventListener('click',       (e) => { e.preventDefault(); });
  });

  // ── Pull-to-refresh suppression ───────────────────────────────────
  // The CSS rule `overscroll-behavior-y: contain` (in mobile-chrome.css) does
  // not actually disable iOS Safari's or Firefox mobile's native pull-to-
  // refresh in this layout. Both engines only honour the property when the
  // element it is set on is itself a non-trivial scroll container — and the
  // mobile shell deliberately keeps body content within the viewport so the
  // body never grows tall enough to scroll. The browsers therefore treat the
  // downward swipe as a navigation-level gesture before any container can
  // claim it.
  //
  // The fix is a delegated touchmove guard: when in mobile-terminal-mode, walk
  // the touch target's ancestor chain looking for a scrollable element that
  // can absorb the gesture. If one exists and isn't already at the boundary
  // for the current direction, let the gesture through. Otherwise call
  // preventDefault on the touchmove so the browser cannot interpret it as
  // pull-to-refresh / overscroll bounce. This intentionally does not interfere
  // with the sheet drag handlers in mobile_sheet.js, which run on Pointer
  // Events with setPointerCapture and `touch-action: none` on the grab — those
  // already bypass the browser's default touch handling.
  let _touchStartX = null;
  let _touchStartY = null;
  document.addEventListener('touchstart', (e) => {
    if (e.touches.length === 1) {
      _touchStartX = e.touches[0].clientX;
      _touchStartY = e.touches[0].clientY;
    } else {
      _touchStartX = null;
      _touchStartY = null;
    }
  }, { passive: true });
  document.addEventListener('touchmove', (e) => {
    if (!document.body.classList.contains('mobile-terminal-mode')) return;
    if (_touchStartY == null || e.touches.length !== 1) return;
    const dy = e.touches[0].clientY - _touchStartY;
    const dx = e.touches[0].clientX - _touchStartX;
    if (dy === 0) return;
    // Predominantly horizontal gestures are never pull-to-refresh
    // candidates; bailing out here lets horizontal scroll containers
    // (e.g. the mobile tab bar, with overflow-y:hidden so the vertical
    // walk below wouldn't find them) receive the full gesture.
    if (Math.abs(dx) >= Math.abs(dy)) return;
    let el = e.target;
    while (el && el !== document.body && el !== document.documentElement) {
      if (el.scrollHeight > el.clientHeight) {
        const oy = getComputedStyle(el).overflowY;
        if (oy === 'auto' || oy === 'scroll') {
          // Scrolling down (dy > 0) is only "would-overscroll" at scrollTop 0.
          // Scrolling up (dy < 0) is only "would-overscroll" at the bottom.
          if (dy > 0 && el.scrollTop > 0) return;
          if (dy < 0 && el.scrollTop + el.clientHeight < el.scrollHeight) return;
          break;
        }
      }
      el = el.parentElement;
    }
    if (e.cancelable) e.preventDefault();
  }, { passive: false });

})(typeof window !== 'undefined' ? window : this);
;
