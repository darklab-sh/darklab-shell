// Command recall history shared by the prompt, mobile composer, and History chips.
function _historyRecallCore() {
  return (typeof window !== 'undefined' && window.DarklabHistoryCore)
    || (typeof DarklabHistoryCore !== 'undefined' ? DarklabHistoryCore : null);
}

function _activeTabCommandHistoryState() {
  const tab = typeof getActiveTab === 'function' ? getActiveTab() : null;
  if (!tab) return null;
  if (!Array.isArray(tab.commandHistory)) tab.commandHistory = [];
  if (!Number.isInteger(tab.historyNavIndex)) tab.historyNavIndex = -1;
  if (typeof tab.historyNavDraft !== 'string') tab.historyNavDraft = '';
  return tab;
}

function _historyLimit() {
  return _historyRecallCore().historyLimit(APP_CONFIG);
}

function _commandRecallHistory(tab) {
  return _historyRecallCore().commandRecallHistory(tab, cmdHistory, _historyLimit());
}

function resetCmdHistoryNav() {
  const tab = _activeTabCommandHistoryState();
  if (tab) {
    tab.historyNavIndex = -1;
    tab.historyNavDraft = '';
  } else {
    _cmdHistoryNavIndex = -1;
    _cmdHistoryNavDraft = '';
  }
  if (typeof isHistSearchMode === 'function' && isHistSearchMode()) {
    exitHistSearch(false);
  }
}

function navigateCmdHistory(delta) {
  const tab = _activeTabCommandHistoryState();
  const history = tab ? _commandRecallHistory(tab) : cmdHistory;
  if (!history.length) return false;

  if (delta > 0) {
    const currentIndex = tab ? tab.historyNavIndex : _cmdHistoryNavIndex;
    if (currentIndex === -1) {
      const draft = (typeof getComposerValue === 'function')
        ? getComposerValue()
        : (cmdInput ? cmdInput.value : '');
      if (tab) {
        tab.historyNavDraft = draft;
        tab.historyNavIndex = 0;
      } else {
        _cmdHistoryNavDraft = draft;
        _cmdHistoryNavIndex = 0;
      }
    } else if (currentIndex < history.length - 1) {
      if (tab) tab.historyNavIndex++;
      else _cmdHistoryNavIndex++;
    } else {
      return true;
    }
    _suspendCmdHistoryNavReset = true;
    setComposerValue(history[tab ? tab.historyNavIndex : _cmdHistoryNavIndex]);
    return true;
  }

  if (delta < 0) {
    const currentIndex = tab ? tab.historyNavIndex : _cmdHistoryNavIndex;
    if (currentIndex === -1) return false;
    if (currentIndex > 0) {
      if (tab) tab.historyNavIndex--;
      else _cmdHistoryNavIndex--;
      _suspendCmdHistoryNavReset = true;
      setComposerValue(history[tab ? tab.historyNavIndex : _cmdHistoryNavIndex]);
      return true;
    }
    _suspendCmdHistoryNavReset = true;
    setComposerValue(tab ? tab.historyNavDraft : _cmdHistoryNavDraft);
    resetCmdHistoryNav();
    return true;
  }

  return false;
}

function addToHistory(cmd) {
  const limit = _historyLimit();
  cmdHistory = [cmd, ...cmdHistory.filter(c => c !== cmd)].slice(0, limit);
  const tab = _activeTabCommandHistoryState();
  if (tab) {
    tab.commandHistory = [cmd, ...tab.commandHistory.filter(c => c !== cmd)].slice(0, limit);
  }
  resetCmdHistoryNav();
  renderHistory();
}

function addToRecentPreview(cmd) {
  recentPreviewHistory = [cmd, ...recentPreviewHistory.filter(c => c !== cmd)]
    .slice(0, APP_CONFIG.recent_commands_limit);
  renderHistory();
}

function hydrateCmdHistory(runs) {
  const items = Array.isArray(runs) ? runs : [];
  const seen = new Set();
  cmdHistory = items
    .map(run => run && typeof run.command === 'string' ? run.command : '')
    .filter(cmd => {
      if (!cmd || seen.has(cmd)) return false;
      seen.add(cmd);
      return true;
    })
    .slice(0, APP_CONFIG.recent_commands_limit);
  const previewSeen = new Set();
  recentPreviewHistory = items
    .map(run => run && typeof run.command === 'string' ? run.command : '')
    .filter(cmd => {
      if (!cmd || previewSeen.has(cmd)) return false;
      previewSeen.add(cmd);
      return true;
    })
    .slice(0, APP_CONFIG.recent_commands_limit);
  resetCmdHistoryNav();
  renderHistory();
}

if (typeof window !== 'undefined') {
  Object.assign(window, {
    _activeTabCommandHistoryState,
    _historyLimit,
    _commandRecallHistory,
    resetCmdHistoryNav,
    navigateCmdHistory,
    addToHistory,
    addToRecentPreview,
    hydrateCmdHistory,
  });
}
