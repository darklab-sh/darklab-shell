function _resetPreservedSingleTabState(tab) {
  if (!tab) return;
  if (typeof resetAnsiRendererForTab === 'function') resetAnsiRendererForTab(tab.id);
  tab.command = '';
  tab.runId = null;
  tab.historyRunId = null;
  tab.lastEventId = '';
  tab.attachMode = '';
  tab.reconnectedRun = false;
  tab.runStart = null;
  tab.currentRunStartIndex = null;
  tab.exitCode = null;
  tab.previewTruncated = false;
  tab.fullOutputAvailable = false;
  tab.fullOutputLoaded = false;
  tab.followOutput = true;
  tab.outputUserScrollUntil = 0;
  tab.suppressOutputScrollTracking = false;
  tab.deferPromptMount = false;
  tab.closing = false;
  tab.killed = false;
  tab.pendingKill = false;
  tab.renamed = false;
  tab.workspaceCwd = '';
  tab.draftInput = '';
  tab.commandHistory = [];
  tab.historyNavIndex = -1;
  tab.historyNavDraft = '';
  tab._outputLineCounter = 0;
  _clearTabRunningLabelTimer(tab);
  tab.runningLabel = '';
}

function _activateNeighborAfterClose(idx, id) {
  if (activeTabId !== id) return;
  const nextId = _getNeighborTabIdAfterClose(Math.min(idx, tabs.length), id);
  if (nextId) activateTab(nextId, { focusComposer: false });
  if (typeof document !== 'undefined'
    && document.body
    && document.body.classList
    && document.body.classList.contains('mobile-terminal-mode')
    && typeof window !== 'undefined'
    && typeof window.scrollTo === 'function') {
    setTimeout(() => {
      try {
        window.scrollTo({ top: 0, behavior: 'auto' });
      } catch (_) {
        // jsdom does not implement scrollTo; browsers do.
      }
    }, 0);
  }
}

function _removeClosedTabView(id, idx) {
  tabs.splice(idx, 1);
  if (typeof dropAnsiRendererForTab === 'function') dropAnsiRendererForTab(id);
  _getTabEl(id)?.remove();
  _getTabPanelEl(id)?.remove();
  _activateNeighborAfterClose(idx, id);
  updateNewTabBtn();
  updateTabScrollButtons();
  if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
  if (typeof emitUiEvent === 'function') {
    emitUiEvent('app:tab-closed', { id, activeTabId });
  }
}

function detachRunningTabAndClose(id) {
  const idx = tabs.findIndex(t => t.id === id);
  if (idx < 0) return false;
  const tab = tabs[idx];
  if (!tab || tab.st !== 'running') return false;
  const runId = tab.runId || tab.historyRunId || '';
  if (typeof markActiveRunDetachedForRestore === 'function') markActiveRunDetachedForRestore(runId);
  if (typeof detachRunStreamForTab === 'function') detachRunStreamForTab(id);
  if (typeof detachInteractivePtyForTab === 'function') detachInteractivePtyForTab(id);
  tab.closing = false;
  if (tabs.length === 1) {
    _resetPreservedSingleTabState(tab);
    clearTab(id);
    setTabLabel(id, createDefaultTabLabel(1));
    blurActiveElement();
    if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
    if (typeof emitUiEvent === 'function') {
      emitUiEvent('app:tab-detached', { id, activeTabId, preservedSingleTab: true });
      emitUiEvent('app:tab-closed', { id, activeTabId, preservedSingleTab: true });
    }
    return true;
  }
  _removeClosedTabView(id, idx);
  if (typeof emitUiEvent === 'function') emitUiEvent('app:tab-detached', { id, activeTabId });
  return true;
}

function _deferRunningTabCloseForKill(id, idx) {
  const closingTab = tabs[idx];
  if (!closingTab || closingTab.st !== 'running') return false;
  closingTab.closing = true;
  if (typeof doKill === 'function') doKill(id);
  if (activeTabId === id && tabs.length > 1) {
    const nextId = _getNeighborTabIdAfterClose(idx, id);
    if (nextId) activateTab(nextId, { focusComposer: false });
  }
  if (typeof syncRunButtonDisabled === 'function') syncRunButtonDisabled();
  updateNewTabBtn();
  updateTabScrollButtons();
  if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
  if (typeof emitUiEvent === 'function') {
    emitUiEvent('app:tab-closing-deferred', { id, activeTabId });
  }
  return true;
}

function confirmCloseRunningTab(id) {
  const idx = tabs.findIndex(t => t.id === id);
  const tab = tabs[idx];
  if (!tab || tab.st !== 'running') return Promise.resolve(false);
  const canDetach = !!(tab.runId || tab.historyRunId);
  const kill = () => _deferRunningTabCloseForKill(id, idx);
  if (typeof showConfirm !== 'function') {
    return Promise.resolve(canDetach ? detachRunningTabAndClose(id) : kill());
  }
  const actions = [
    ...(canDetach ? [{ id: 'detach', label: 'Keep running', role: 'primary' }] : []),
    { id: 'kill', label: 'Kill run', role: 'destructive' },
    { id: 'cancel', label: 'Cancel', role: 'cancel' },
  ];
  return showConfirm({
    body: {
      text: 'Close this running tab?',
      note: canDetach
        ? 'Keep running detaches this tab only. The command keeps running and can be reopened from Status Monitor.'
        : 'The command is still starting, so it cannot be detached yet.',
    },
    tone: 'danger',
    actions,
  }).then(result => {
    if (result === 'detach') return detachRunningTabAndClose(id);
    if (result === 'kill') return kill();
    return false;
  });
}

function closeTab(id) {
  // Closing a tab may need to preserve run state until the kill flow or output
  // persistence finishes, so final removal is sometimes deferred.
  cancelWelcome(id);
  const idx = tabs.findIndex(t => t.id === id);
  if (typeof _cancelPendingOutputBatch === 'function') _cancelPendingOutputBatch(id);
  const closingTab = tabs[idx];
  if (closingTab) {
    closingTab._outputFollowToken = (closingTab._outputFollowToken || 0) + 1;
    closingTab.suppressOutputScrollTracking = false;
    closingTab.deferPromptMount = false;
  }
  if (closingTab && closingTab.st === 'running') {
    confirmCloseRunningTab(id);
    return;
  }
  if (tabs.length === 1) {
    // Last tab: reset to blank instead of closing
    _resetPreservedSingleTabState(tabs[0]);
    clearTab(id);
    setTabLabel(id, createDefaultTabLabel(1));
    if (typeof useMobileTerminalViewportMode === 'function'
      && useMobileTerminalViewportMode()
      && typeof blurVisibleComposerInputIfMobile === 'function') {
      setTimeout(() => blurVisibleComposerInputIfMobile(), 0);
    }
    blurActiveElement();
    if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
    if (typeof emitUiEvent === 'function') {
      emitUiEvent('app:tab-closed', { id, activeTabId, preservedSingleTab: true });
    }
    return;
  }
  _removeClosedTabView(id, idx);
}

function finalizeClosingTab(id) {
  const idx = tabs.findIndex(t => t.id === id);
  if (idx < 0) return false;
  const tab = tabs[idx];
  if (!tab || !tab.closing) return false;

  if (tabs.length === 1) {
    _resetPreservedSingleTabState(tab);
    clearTab(id);
    setTabLabel(id, createDefaultTabLabel(1));
    if (typeof document !== 'undefined'
      && document.body
      && document.body.classList
      && document.body.classList.contains('mobile-terminal-mode')
      && typeof blurVisibleComposerInputIfMobile === 'function') {
      setTimeout(() => blurVisibleComposerInputIfMobile(), 0);
    }
    if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
    return true;
  }

  tabs.splice(idx, 1);
  if (typeof dropAnsiRendererForTab === 'function') dropAnsiRendererForTab(id);
  _getTabEl(id)?.remove();
  _getTabPanelEl(id)?.remove();
  if (activeTabId === id && tabs.length) {
    const nextId = _getNeighborTabIdAfterClose(Math.min(idx, tabs.length), id);
    if (nextId) activateTab(nextId, { focusComposer: false });
  }
  updateNewTabBtn();
  updateTabScrollButtons();
  if (typeof syncRunButtonDisabled === 'function') syncRunButtonDisabled();
  if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
  return true;
}
