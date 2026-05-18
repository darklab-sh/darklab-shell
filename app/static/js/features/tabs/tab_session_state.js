// ── Tab session persistence and restore ──

const TAB_SESSION_STATE_KEY = `tab_session_state:${typeof SESSION_ID !== 'undefined' ? SESSION_ID : 'session'}`;
let _tabSessionPersistTimer = null;
let _tabSessionRestoreInProgress = false;

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
    entities: window.DarklabOutputCore && typeof window.DarklabOutputCore.normalizeEntities === 'function'
      ? window.DarklabOutputCore.normalizeEntities(line && line.entities)
      : [],
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
    .filter(tab => tab && !tab.closing)
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
      runId: String(tab.runId || ''),
      historyRunId: String(tab.historyRunId || ''),
      lastEventId: String(tab.lastEventId || ''),
      attachMode: String(tab.attachMode || ''),
      reconnectedRun: !!tab.reconnectedRun,
      runStart: Number.isFinite(Number(tab.runStart)) ? Number(tab.runStart) : null,
      currentRunStartIndex: Number.isFinite(Number(tab.currentRunStartIndex)) ? Number(tab.currentRunStartIndex) : null,
      previewTruncated: !!tab.previewTruncated,
      fullOutputAvailable: !!tab.fullOutputAvailable,
      fullOutputLoaded: !!tab.fullOutputLoaded,
      rawLines: _snapshotTabRawLines(tab.rawLines),
    }));
  if (!persisted.length) return null;
  const activeIndex = persisted.findIndex((_, idx) => {
    const sourceTabs = allTabs.filter(tab => tab && !tab.closing);
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
      tab.runId = String(item && item.runId || '');
      tab.historyRunId = String(item && item.historyRunId || '');
      tab.lastEventId = String(item && item.lastEventId || '');
      tab.attachMode = String(item && item.attachMode || '');
      tab.reconnectedRun = !!(item && item.reconnectedRun);
      tab.runStart = Number.isFinite(Number(item && item.runStart)) ? Number(item.runStart) : null;
      tab.currentRunStartIndex = Number.isFinite(Number(item && item.currentRunStartIndex))
        ? Number(item.currentRunStartIndex)
        : null;
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
      tab.runId = String(item && item.runId || '');
      tab.historyRunId = String(item && item.historyRunId || '');
      tab.lastEventId = String(item && item.lastEventId || '');
      tab.attachMode = String(item && item.attachMode || '');
      tab.reconnectedRun = !!(item && item.reconnectedRun);
      tab.runStart = Number.isFinite(Number(item && item.runStart)) ? Number(item.runStart) : null;
      tab.currentRunStartIndex = Number.isFinite(Number(item && item.currentRunStartIndex))
        ? Number(item.currentRunStartIndex)
        : null;
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
