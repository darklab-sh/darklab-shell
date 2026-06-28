// Command recall history shared by the prompt, mobile composer, and History chips.
import { getAppConfig as importedGetAppConfig } from '../../core/config.js';
import { cmdInput as importedCmdInput } from '../../core/dom.js';
import { DarklabHistoryCore as importedHistoryCore } from '../../core/history_core.js';
import {
  getActiveTab as importedGetActiveTab,
  getAppState as importedGetAppState,
} from '../../core/state.js';
import {
  getComposerValue as importedGetComposerValue,
  setComposerValue as importedSetComposerValue,
} from '../../ui/ui_helpers.js';
import {
  exitHistSearch as importedExitHistSearch,
  isHistSearchMode as importedIsHistSearchMode,
} from './history_search.js';
import { renderHistory as importedRenderHistory } from './history_panel_bridge.js';
import { setHistoryRecallHandlers as importedSetHistoryRecallHandlers } from './history_recall_bridge.js';

const HISTORY_RECALL_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _historyRecallCore() {
  return (typeof importedHistoryCore !== 'undefined' && importedHistoryCore)
    || null;
}

function _historyRecallState() {
  if (typeof importedGetAppState === 'function') return importedGetAppState();
  if (typeof HISTORY_RECALL_GLOBAL.APP_STATE_API?.getState === 'function') return HISTORY_RECALL_GLOBAL.APP_STATE_API.getState();
  return HISTORY_RECALL_GLOBAL.APP_STATE || null;
}

function _historyRecallAppConfig() {
  if (typeof importedGetAppConfig === 'function') return importedGetAppConfig();
  return HISTORY_RECALL_GLOBAL.APP_CONFIG || {};
}

function _historyRecallCmdHistory() {
  const state = _historyRecallState();
  if (state && Array.isArray(state.cmdHistory)) return state.cmdHistory;
  return [];
}

function _historyRecallSetCmdHistory(next) {
  const value = Array.isArray(next) ? next : [];
  const state = _historyRecallState();
  if (state) state.cmdHistory = value;
  return value;
}

function _historyRecallRecentPreviewHistory() {
  const state = _historyRecallState();
  if (state && Array.isArray(state.recentPreviewHistory)) return state.recentPreviewHistory;
  return [];
}

function _historyRecallSetRecentPreviewHistory(next) {
  const value = Array.isArray(next) ? next : [];
  const state = _historyRecallState();
  if (state) state.recentPreviewHistory = value;
  return value;
}

function _historyRecallNavIndex() {
  const state = _historyRecallState();
  if (state && Number.isInteger(state._cmdHistoryNavIndex)) return state._cmdHistoryNavIndex;
  return -1;
}

function _historyRecallSetNavState(next = {}) {
  const state = _historyRecallState();
  if (Object.prototype.hasOwnProperty.call(next, 'index')) {
    const index = Number.isInteger(next.index) ? next.index : -1;
    if (state) state._cmdHistoryNavIndex = index;
  }
  if (Object.prototype.hasOwnProperty.call(next, 'draft')) {
    const draft = String(next.draft ?? '');
    if (state) state._cmdHistoryNavDraft = draft;
  }
  if (Object.prototype.hasOwnProperty.call(next, 'suspendReset')) {
    const suspendReset = !!next.suspendReset;
    if (state) state._suspendCmdHistoryNavReset = suspendReset;
  }
}

function _historyRecallNavDraft() {
  const state = _historyRecallState();
  if (state && typeof state._cmdHistoryNavDraft === 'string') return state._cmdHistoryNavDraft;
  return '';
}

function _historyRecallComposerValue() {
  const getter = (typeof importedGetComposerValue !== 'undefined' && importedGetComposerValue)
    || HISTORY_RECALL_GLOBAL.getComposerValue;
  const input = (typeof importedCmdInput !== 'undefined' && importedCmdInput)
    || HISTORY_RECALL_GLOBAL.cmdInput;
  if (input && typeof input.value === 'string' && input.value) return input.value;
  return typeof getter === 'function' ? getter() : (input ? input.value : '');
}

function _historyRecallSetComposerValue(value) {
  const setter = (typeof importedSetComposerValue !== 'undefined' && importedSetComposerValue)
    || HISTORY_RECALL_GLOBAL.setComposerValue;
  if (typeof setter === 'function') setter(value);
}

function _historyRecallIsSearchMode() {
  const isMode = (typeof importedIsHistSearchMode !== 'undefined' && importedIsHistSearchMode)
    || HISTORY_RECALL_GLOBAL.isHistSearchMode;
  return typeof isMode === 'function' ? isMode() : false;
}

function _historyRecallExitSearch() {
  const exitSearch = (typeof importedExitHistSearch !== 'undefined' && importedExitHistSearch)
    || HISTORY_RECALL_GLOBAL.exitHistSearch;
  if (typeof exitSearch === 'function') exitSearch(false);
}

function _activeTabCommandHistoryState() {
  const getActive = (typeof importedGetActiveTab !== 'undefined' && importedGetActiveTab)
    || (typeof HISTORY_RECALL_GLOBAL.APP_STATE_API?.getActiveTab === 'function'
        ? HISTORY_RECALL_GLOBAL.APP_STATE_API.getActiveTab
        : null);
  const tab = typeof getActive === 'function' ? getActive() : null;
  if (!tab) return null;
  if (!Array.isArray(tab.commandHistory)) tab.commandHistory = [];
  if (!Number.isInteger(tab.historyNavIndex)) tab.historyNavIndex = -1;
  if (typeof tab.historyNavDraft !== 'string') tab.historyNavDraft = '';
  return tab;
}

function _historyRecallRenderHistory() {
  if (typeof importedRenderHistory === 'function') {
    importedRenderHistory();
    return;
  }
  if (typeof HISTORY_RECALL_GLOBAL.renderHistory === 'function') HISTORY_RECALL_GLOBAL.renderHistory();
}

function _historyLimit() {
  return _historyRecallCore().historyLimit(_historyRecallAppConfig());
}

function _commandRecallHistory(tab) {
  return _historyRecallCore().commandRecallHistory(tab, _historyRecallCmdHistory(), _historyLimit());
}

function resetCmdHistoryNav() {
  const tab = _activeTabCommandHistoryState();
  if (tab) {
    tab.historyNavIndex = -1;
    tab.historyNavDraft = '';
  } else {
    _historyRecallSetNavState({ index: -1, draft: '' });
  }
  if (_historyRecallIsSearchMode()) {
    _historyRecallExitSearch();
  }
}

function navigateCmdHistory(delta) {
  const tab = _activeTabCommandHistoryState();
  const history = tab ? _commandRecallHistory(tab) : _historyRecallCmdHistory();
  if (!history.length) return false;

  if (delta > 0) {
    const currentIndex = tab ? tab.historyNavIndex : _historyRecallNavIndex();
    if (currentIndex === -1) {
      const draft = _historyRecallComposerValue();
      if (tab) {
        tab.historyNavDraft = draft;
        tab.historyNavIndex = 0;
      } else {
        _historyRecallSetNavState({ draft, index: 0 });
      }
    } else if (currentIndex < history.length - 1) {
      if (tab) tab.historyNavIndex++;
      else _historyRecallSetNavState({ index: currentIndex + 1 });
    } else {
      return true;
    }
    _historyRecallSetNavState({ suspendReset: true });
    _historyRecallSetComposerValue(history[tab ? tab.historyNavIndex : _historyRecallNavIndex()]);
    return true;
  }

  if (delta < 0) {
    const currentIndex = tab ? tab.historyNavIndex : _historyRecallNavIndex();
    if (currentIndex === -1) return false;
    if (currentIndex > 0) {
      if (tab) tab.historyNavIndex--;
      else _historyRecallSetNavState({ index: currentIndex - 1 });
      _historyRecallSetNavState({ suspendReset: true });
      _historyRecallSetComposerValue(history[tab ? tab.historyNavIndex : _historyRecallNavIndex()]);
      return true;
    }
    _historyRecallSetNavState({ suspendReset: true });
    _historyRecallSetComposerValue(tab ? tab.historyNavDraft : _historyRecallNavDraft());
    resetCmdHistoryNav();
    return true;
  }

  return false;
}

function addToHistory(cmd) {
  const limit = _historyLimit();
  const history = _historyRecallCmdHistory();
  _historyRecallSetCmdHistory([cmd, ...history.filter(c => c !== cmd)].slice(0, limit));
  const tab = _activeTabCommandHistoryState();
  if (tab) {
    tab.commandHistory = [cmd, ...tab.commandHistory.filter(c => c !== cmd)].slice(0, limit);
  }
  resetCmdHistoryNav();
  _historyRecallRenderHistory();
}

function addToRecentPreview(cmd) {
  const config = _historyRecallAppConfig();
  const previewHistory = _historyRecallRecentPreviewHistory();
  _historyRecallSetRecentPreviewHistory(
    [cmd, ...previewHistory.filter(c => c !== cmd)]
      .slice(0, config.recent_commands_limit),
  );
  _historyRecallRenderHistory();
}

function hydrateCmdHistory(runs) {
  const items = Array.isArray(runs) ? runs : [];
  const seen = new Set();
  const config = _historyRecallAppConfig();
  _historyRecallSetCmdHistory(items
    .map(run => run && typeof run.command === 'string' ? run.command : '')
    .filter(cmd => {
      if (!cmd || seen.has(cmd)) return false;
      seen.add(cmd);
      return true;
    })
    .slice(0, config.recent_commands_limit));
  const previewSeen = new Set();
  _historyRecallSetRecentPreviewHistory(items
    .map(run => run && typeof run.command === 'string' ? run.command : '')
    .filter(cmd => {
      if (!cmd || previewSeen.has(cmd)) return false;
      previewSeen.add(cmd);
      return true;
    })
    .slice(0, config.recent_commands_limit));
  resetCmdHistoryNav();
  _historyRecallRenderHistory();
}

if (typeof window !== 'undefined') {
}

if (typeof importedSetHistoryRecallHandlers === 'function') {
  importedSetHistoryRecallHandlers({ resetCmdHistoryNav });
}

export {
  _activeTabCommandHistoryState,
  _commandRecallHistory,
  _historyLimit,
  addToHistory,
  addToRecentPreview,
  hydrateCmdHistory,
  navigateCmdHistory,
  resetCmdHistoryNav,
};
