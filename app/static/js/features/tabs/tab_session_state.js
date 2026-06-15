// ── Tab session persistence and restore ──

import {
  tabPanels as importedTabPanels,
  tabsBar as importedTabsBar,
} from '../../core/dom.js';
import { DarklabOutputCore as importedOutputCore } from '../../core/output_core.js';
import {
  getActiveTab as importedGetActiveTab,
  getActiveTabId as importedGetActiveTabId,
  getTab as importedGetTab,
  getTabs as importedGetTabs,
  setActiveTabId as importedSetActiveTabId,
  setTabs as importedSetTabs,
  setWelcomeState as importedSetWelcomeState,
} from '../../core/state.js';
import {
  _restoreOutputTailAfterLayout as importedRestoreOutputTailAfterLayout,
  renderRestoredTabOutput as importedRenderRestoredTabOutput,
} from '../../output.js';
import {
  activateTab as importedActivateTab,
  createDefaultTabLabel as importedCreateDefaultTabLabel,
  createTab as importedCreateTab,
  getOutput as importedGetOutput,
  mountShellPrompt as importedMountShellPrompt,
  setTabStatus as importedSetTabStatus,
  unmountShellPrompt as importedUnmountShellPrompt,
} from '../../tabs_bridge.js';
import { getComposerValue as importedGetComposerValue } from '../../ui/ui_helpers.js';

const TAB_SESSION_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _tabSessionGlobalFunction(name) {
  const fn = TAB_SESSION_GLOBAL && TAB_SESSION_GLOBAL[name];
  return typeof fn === 'function' ? fn : null;
}

const TAB_SESSION_STATE_KEY = `tab_session_state:${TAB_SESSION_GLOBAL.SESSION_ID || 'session'}`;
let _tabSessionPersistTimer = null;
let _tabSessionRestoreInProgress = false;

if (
  TAB_SESSION_GLOBAL
  && typeof Object.defineProperty === 'function'
  && !Object.prototype.hasOwnProperty.call(TAB_SESSION_GLOBAL, '_tabSessionRestoreInProgress')
) {
  Object.defineProperty(TAB_SESSION_GLOBAL, '_tabSessionRestoreInProgress', {
    configurable: true,
    get() { return _tabSessionRestoreInProgress; },
    set(value) { _tabSessionRestoreInProgress = value === true; },
  });
}

function setTabSessionRestoreInProgress(value) {
  _tabSessionRestoreInProgress = value === true;
  return _tabSessionRestoreInProgress;
}

function _tabSessionTabsBar() {
  return (typeof importedTabsBar !== 'undefined' && importedTabsBar)
    || TAB_SESSION_GLOBAL.tabsBar
    || null;
}

function _tabSessionTabPanels() {
  return (typeof importedTabPanels !== 'undefined' && importedTabPanels)
    || TAB_SESSION_GLOBAL.tabPanels
    || null;
}

function _tabSessionGetTabs() {
  const getTabs = _tabSessionGlobalFunction('getTabs');
  if (getTabs) return getTabs();
  if (typeof importedGetTabs !== 'undefined' && typeof importedGetTabs === 'function') return importedGetTabs();
  return Array.isArray(TAB_SESSION_GLOBAL.tabs) ? TAB_SESSION_GLOBAL.tabs : [];
}

function _tabSessionSetTabs(nextTabs) {
  const setTabsFn = _tabSessionGlobalFunction('setTabs');
  if (setTabsFn) {
    setTabsFn(nextTabs);
    return;
  }
  if (typeof importedSetTabs !== 'undefined' && typeof importedSetTabs === 'function') {
    importedSetTabs(nextTabs);
    return;
  }
}

function _tabSessionGetActiveTabId() {
  const getActiveId = _tabSessionGlobalFunction('getActiveTabId');
  if (getActiveId) return getActiveId();
  if (typeof importedGetActiveTabId !== 'undefined' && typeof importedGetActiveTabId === 'function') {
    return importedGetActiveTabId();
  }
  return TAB_SESSION_GLOBAL.activeTabId || null;
}

function _tabSessionSetActiveTabId(tabId) {
  const setActive = _tabSessionGlobalFunction('setActiveTabId');
  if (setActive) {
    setActive(tabId);
    return;
  }
  if (typeof importedSetActiveTabId !== 'undefined' && typeof importedSetActiveTabId === 'function') {
    importedSetActiveTabId(tabId);
    return;
  }
}

function _tabSessionGetTab(tabId) {
  const getTabFn = _tabSessionGlobalFunction('getTab');
  if (getTabFn) return getTabFn(tabId);
  if (typeof importedGetTab !== 'undefined' && typeof importedGetTab === 'function') return importedGetTab(tabId);
  return null;
}

function _tabSessionGetActiveTab() {
  const getActive = _tabSessionGlobalFunction('getActiveTab');
  if (getActive) return getActive();
  if (typeof importedGetActiveTab !== 'undefined' && typeof importedGetActiveTab === 'function') {
    return importedGetActiveTab();
  }
  return null;
}

function _tabSessionSetWelcomeState(nextState) {
  const setWelcome = _tabSessionGlobalFunction('setWelcomeState');
  if (setWelcome) {
    setWelcome(nextState);
    return;
  }
  if (typeof importedSetWelcomeState !== 'undefined' && typeof importedSetWelcomeState === 'function') {
    importedSetWelcomeState(nextState);
    return;
  }
}

function _tabSessionGetComposerValue() {
  const getComposer = _tabSessionGlobalFunction('getComposerValue');
  if (getComposer) return getComposer();
  if (typeof importedGetComposerValue !== 'undefined' && typeof importedGetComposerValue === 'function') {
    return importedGetComposerValue();
  }
  return TAB_SESSION_GLOBAL.cmdInput ? TAB_SESSION_GLOBAL.cmdInput.value || '' : '';
}

function _tabSessionCreateDefaultTabLabel(index) {
  const createLabel = _tabSessionGlobalFunction('createDefaultTabLabel');
  if (createLabel) return createLabel(index);
  if (typeof importedCreateDefaultTabLabel !== 'undefined' && typeof importedCreateDefaultTabLabel === 'function') {
    return importedCreateDefaultTabLabel(index);
  }
  return `shell ${index}`;
}

function _tabSessionCreateTab(label) {
  const create = _tabSessionGlobalFunction('createTab');
  if (create) return create(label);
  if (typeof importedCreateTab !== 'undefined' && typeof importedCreateTab === 'function') return importedCreateTab(label);
  return null;
}

function _tabSessionRenderRestoredTabOutput(tabId, rawLines) {
  const render = (typeof importedRenderRestoredTabOutput !== 'undefined' && importedRenderRestoredTabOutput)
    || _tabSessionGlobalFunction('renderRestoredTabOutput');
  if (typeof render === 'function') render(tabId, rawLines);
}

function _tabSessionSetTabStatus(tabId, status) {
  const setStatus = (typeof importedSetTabStatus !== 'undefined' && importedSetTabStatus)
    || _tabSessionGlobalFunction('setTabStatus');
  if (typeof setStatus === 'function') setStatus(tabId, status);
}

function _tabSessionActivateTab(tabId, options) {
  const activate = (typeof importedActivateTab !== 'undefined' && importedActivateTab)
    || _tabSessionGlobalFunction('activateTab');
  if (typeof activate === 'function') activate(tabId, options);
}

function _tabSessionMountShellPrompt(tabId, force = false) {
  const mount = (typeof importedMountShellPrompt !== 'undefined' && importedMountShellPrompt)
    || _tabSessionGlobalFunction('mountShellPrompt');
  if (typeof mount === 'function') mount(tabId, force);
}

function _tabSessionUnmountShellPrompt() {
  const unmount = (typeof importedUnmountShellPrompt !== 'undefined' && importedUnmountShellPrompt)
    || _tabSessionGlobalFunction('unmountShellPrompt');
  if (typeof unmount === 'function') unmount();
}

function _tabSessionGetOutput(tabId) {
  const getOutputForTab = (typeof importedGetOutput !== 'undefined' && importedGetOutput)
    || _tabSessionGlobalFunction('getOutput');
  return typeof getOutputForTab === 'function' ? getOutputForTab(tabId) : null;
}

function _tabSessionRestoreOutputTailAfterLayout(outputEl, tab) {
  const restoreTail = (typeof importedRestoreOutputTailAfterLayout !== 'undefined' && importedRestoreOutputTailAfterLayout)
    || _tabSessionGlobalFunction('_restoreOutputTailAfterLayout');
  if (typeof restoreTail === 'function') restoreTail(outputEl, tab);
}

function _tabSessionOutputCore() {
  return (typeof importedOutputCore !== 'undefined' && importedOutputCore)
    || TAB_SESSION_GLOBAL.DarklabOutputCore
    || null;
}

function _snapshotTabRawLines(rawLines) {
  if (!Array.isArray(rawLines)) return [];
  return rawLines.map(line => ({
    text: String(line && line.text || ''),
    cls: String(line && line.cls || ''),
    kind: String(line && line.kind || ''),
    role: String(line && line.role || ''),
    tsC: String(line && line.tsC || ''),
    tsE: String(line && line.tsE || ''),
    signals: Array.isArray(line && line.signals)
      ? line.signals.map(signal => String(signal || '')).filter(Boolean)
      : [],
    line_index: Number.isInteger(line && line.line_index) ? line.line_index : undefined,
    line_number: Number.isInteger(line && line.line_number) ? line.line_number : undefined,
    command_root: String(line && line.command_root || ''),
    target: String(line && line.target || ''),
    entities: _tabSessionOutputCore()
      && typeof _tabSessionOutputCore().normalizeEntities === 'function'
      ? _tabSessionOutputCore().normalizeEntities(line && line.entities)
      : [],
  }));
}

function _snapshotTabCommandOutcomeSummary(summary) {
  if (!summary) return null;
  const outputCore = _tabSessionOutputCore();
  const normalized = outputCore
    && typeof outputCore.normalizeCommandOutcomeSummary === 'function'
    ? outputCore.normalizeCommandOutcomeSummary(summary)
    : null;
  return normalized ? {
    title: normalized.title,
    items: normalized.items,
  } : null;
}

function _flushActiveTabDraftForSessionState() {
  const activeTab = _tabSessionGetActiveTab();
  if (!activeTab || activeTab.st === 'running') return;
  activeTab.draftInput = _tabSessionGetComposerValue();
}

function _tabSessionSnapshot() {
  _flushActiveTabDraftForSessionState();
  const allTabs = _tabSessionGetTabs();
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
      commandOutcomeSummary: _snapshotTabCommandOutcomeSummary(tab.commandOutcomeSummary),
      rawLines: _snapshotTabRawLines(tab.rawLines),
    }));
  if (!persisted.length) return null;
  const activeIndex = persisted.findIndex((_, idx) => {
    const sourceTabs = allTabs.filter(tab => tab && !tab.closing);
    return sourceTabs[idx] && sourceTabs[idx].id === _tabSessionGetActiveTabId();
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

function _readStoredTabSessionState() {
  const direct = sessionStorage.getItem(TAB_SESSION_STATE_KEY);
  if (direct) return direct;
  try {
    for (let index = 0; index < sessionStorage.length; index += 1) {
      const key = sessionStorage.key(index);
      if (!String(key || '').startsWith('tab_session_state:')) continue;
      const value = sessionStorage.getItem(key);
      if (value) return value;
    }
  } catch (_) {}
  return null;
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
    parsed = JSON.parse(_readStoredTabSessionState() || 'null');
  } catch (_) {
    return false;
  }
  if (!parsed || parsed.version !== 1 || !Array.isArray(parsed.tabs) || !parsed.tabs.length) return false;

  _tabSessionRestoreInProgress = true;
  try {
    _tabSessionSetWelcomeState({ bootPending: false });
    _tabSessionUnmountShellPrompt();
    const bar = _tabSessionTabsBar();
    const panels = _tabSessionTabPanels();
    if (bar) {
      bar.querySelectorAll('.tab').forEach(node => node.remove());
    }
    if (panels) panels.innerHTML = '';
    _tabSessionSetTabs([]);
    _tabSessionSetActiveTabId(null);

    const restoredIds = [];
    const restoredRecords = [];
    parsed.tabs.forEach((item, index) => {
      const label = String(item && item.label || (
        _tabSessionCreateDefaultTabLabel(index + 1)
      ));
      const tabId = _tabSessionCreateTab(label);
      if (!tabId) return;
      const tab = _tabSessionGetTab(tabId);
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
      tab.commandOutcomeSummary = item && item.commandOutcomeSummary || null;
      _tabSessionRenderRestoredTabOutput(tabId, item && item.rawLines);
      const status = typeof item?.st === 'string' && item.st !== 'running' ? item.st : 'idle';
      _tabSessionSetTabStatus(tabId, status);
      const hideKill = _tabSessionGlobalFunction('hideTabKillBtn');
      if (hideKill) hideKill(tabId);
      restoredIds.push(tabId);
      restoredRecords.push({ tabId, item });
    });

    restoredRecords.forEach(({ tabId, item }) => {
      const tab = _tabSessionGetTab(tabId);
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
      tab.commandOutcomeSummary = item && item.commandOutcomeSummary || null;
    });

    if (!restoredIds.length) return false;
    const activeIndex = Math.max(0, Math.min(Number(parsed.activeIndex) || 0, restoredIds.length - 1));
    _tabSessionActivateTab(restoredIds[activeIndex], { focusComposer: false });
    _tabSessionMountShellPrompt(restoredIds[activeIndex], true);
    const activeTab = _tabSessionGetTab(restoredIds[activeIndex]);
    const activeOutput = _tabSessionGetOutput(restoredIds[activeIndex]);
    _tabSessionRestoreOutputTailAfterLayout(activeOutput, activeTab);
    return true;
  } finally {
    _tabSessionRestoreInProgress = false;
  }
}

export {
  TAB_SESSION_STATE_KEY,
  _flushActiveTabDraftForSessionState,
  _normalizeRestoredWorkspaceCwd,
  _snapshotTabCommandOutcomeSummary,
  _snapshotTabRawLines,
  _tabSessionRestoreInProgress,
  _tabSessionSnapshot,
  persistTabSessionStateNow,
  restoreTabSessionState,
  schedulePersistTabSessionState,
  setTabSessionRestoreInProgress,
};
