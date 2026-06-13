// Mobile hamburger-menu action dispatch.
//
// controller.js owns the click wiring; this module owns the action body so the
// bootstrap file does not keep growing every time a mobile menu item is added.
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
    // mobile_chrome.js wires this row as a disclosure; keeping the sheet open
    // is the point of the action.
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
    if (activeTabId) {
      if (typeof cancelWelcome === 'function') cancelWelcome(activeTabId);
      if (typeof clearTab === 'function') clearTab(activeTabId, { preserveRunState: true });
    }
    refocusComposerAfterAction({ defer: true });
  }
  if (action === 'options') openOptions();
  if (action === 'scope' && typeof openTeamScopeSelector === 'function') openTeamScopeSelector();
  if (action === 'projects' && typeof openProjectWorkspace === 'function') void openProjectWorkspace();
  if (action === 'atlas' && typeof openAtlas === 'function') void openAtlas({ source: 'mobile-menu' });
  if (action === 'status-monitor' && typeof openStatusMonitor === 'function') {
    void openStatusMonitor({ source: 'mobile-menu' });
  }
  if (action === 'command-registry' && typeof window.openCommandRegistry === 'function') window.openCommandRegistry();
  if (action === 'theme') openThemeSelector();
  if (action === 'workflows') openWorkflows();
  if (action === 'schedules' && typeof openSchedulesModal === 'function') void openSchedulesModal();
  if (action === 'watchers' && typeof openWatchersModal === 'function') void openWatchersModal();
  if (action === 'findings-board' && typeof openFindingsBoard === 'function') void openFindingsBoard({ source: 'mobile-menu' });
  if (action === 'workspace' && typeof openWorkspace === 'function') openWorkspace();
  if (action === 'faq') openFaq();
  if (action === 'diag') window.location.href = '/diag';
}

if (typeof window !== 'undefined') {
  window.dispatchMobileMenuAction = dispatchMobileMenuAction;
}
