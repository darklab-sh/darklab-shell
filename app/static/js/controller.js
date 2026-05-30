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
let promptUsernameAutosaveTimer = null;
const PROMPT_USERNAME_AUTOSAVE_DELAY_MS = 300;
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
applyPromptUsernamePreference(getPromptUsernamePreference(), false);
syncOptionsControls();
const sessionPreferencesLoad = typeof loadSessionPreferences === 'function'
  ? loadSessionPreferences().catch(err => {
    logClientError('failed to apply session preferences', err);
  })
  : Promise.resolve();

const commandHistoryLimit = encodeURIComponent(String(APP_CONFIG.recent_commands_limit || 50));
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
