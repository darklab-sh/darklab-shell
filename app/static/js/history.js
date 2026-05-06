// ── Shared history/permalink logic ──
// Stars are server-backed via /session/starred. A local in-memory cache
// (_starredCache) avoids blocking the UI on every render. Until the cache
// loads, render code sees an empty Set rather than reading localStorage —
// a stale localStorage value from before stars moved server-side would
// silently mask the user's server-side stars.
const _historyCore = typeof DarklabHistoryCore !== 'undefined' ? DarklabHistoryCore : null;

let _starredCache = null; // null = not yet loaded from server

function _getStarred() {
  return _starredCache !== null ? _starredCache : new Set();
}

function _saveStarred(set) {
  _starredCache = new Set(set);
}

function _toggleStar(cmd) {
  const s = _getStarred();
  const adding = !s.has(cmd);
  if (adding) s.add(cmd); else s.delete(cmd);
  _starredCache = s;
  // fire-and-forget server sync — UI is already updated optimistically
  apiFetch('/session/starred', {
    method: adding ? 'POST' : 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command: cmd }),
  }).catch(() => {});
}

async function loadStarredFromServer() {
  try {
    const resp = await apiFetch('/session/starred');
    if (!resp.ok) return;
    const data = await resp.json();
    _starredCache = new Set(data.commands || []);
  } catch (_) {}
}

async function reloadSessionHistory() {
  await loadStarredFromServer();
  try {
    const limit = Math.max(1, Number(APP_CONFIG.recent_commands_limit) || 50);
    const resp = await apiFetch(`/history/commands?limit=${encodeURIComponent(String(limit))}`);
    if (resp.ok) {
      const data = await resp.json();
      hydrateCmdHistory(data.runs || []);
    }
  } catch (_) {}
  if (typeof isHistoryPanelOpen === 'function' && isHistoryPanelOpen()) refreshHistoryPanel();
}

// History drawer filters are deliberately simple in the first pass:
// server-backed search/filtering for persisted run attributes, plus a local
// starred-only toggle backed by the server cache.
let _historyFilterRefreshTimer = null;
let _historyFilters = {
  type: 'all',
  q: '',
  commandRoot: '',
  exitCode: 'all',
  dateRange: 'all',
  starredOnly: false,
};
let _historyMobileAdvancedOpen = false;
let _historyRootSuggestions = [];
let _historyRootFiltered = [];
let _historyRootIndex = -1;
let _historyRootSuppressInputOnce = false;
let _historyRootInputFocused = false;
let _historyPaging = {
  page: 1,
  pageSize: (typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.history_panel_limit)
    ? Math.max(1, Number(APP_CONFIG.history_panel_limit) || 50)
    : 50,
  totalCount: 0,
  pageCount: 0,
  hasPrev: false,
  hasNext: false,
};
let _historyCompareState = {
  source: null,
  candidates: [],
  manualCandidates: [],
  manualLoaded: false,
  manualRequestId: 0,
  manualPage: 1,
  manualHasNext: false,
  manualLoading: false,
  manualCollapsedGroups: new Set(),
  selected: null,
  manualQuery: '',
};

function _normalizeHistoryFilterValue(value) {
  return _historyCore.normalizeFilterValue(value);
}

function _syncHistoryFilterControls() {
  if (typeof historySearchInput !== 'undefined' && historySearchInput) historySearchInput.value = _historyFilters.q;
  if (typeof historyMobileFiltersToggle !== 'undefined' && historyMobileFiltersToggle) {
    const activeCount = _historyActiveFilterItems().length;
    const baseLabel = _historyMobileAdvancedOpen ? 'hide filters' : 'filters';
    historyMobileFiltersToggle.textContent = activeCount > 0 ? `${baseLabel} (${activeCount})` : baseLabel;
    historyMobileFiltersToggle.setAttribute('aria-expanded', _historyMobileAdvancedOpen ? 'true' : 'false');
  }
  if (typeof historyPanel !== 'undefined' && historyPanel) {
    historyPanel.classList.toggle('mobile-history-filters-open', !!_historyMobileAdvancedOpen);
  }
  if (typeof historyTypeFilter !== 'undefined' && historyTypeFilter) historyTypeFilter.value = _historyFilters.type;
  if (typeof historyRootInput !== 'undefined' && historyRootInput) historyRootInput.value = _historyFilters.commandRoot;
  if (typeof historyExitFilter !== 'undefined' && historyExitFilter) historyExitFilter.value = _historyFilters.exitCode;
  if (typeof historyDateFilter !== 'undefined' && historyDateFilter) historyDateFilter.value = _historyFilters.dateRange;
  if (typeof historyStarredToggle !== 'undefined' && historyStarredToggle) historyStarredToggle.checked = !!_historyFilters.starredOnly;
  const runOnlyEnabled = _historyFilters.type !== 'snapshots';
  if (typeof historyRootInput !== 'undefined' && historyRootInput) historyRootInput.disabled = !runOnlyEnabled;
  if (typeof historyExitFilter !== 'undefined' && historyExitFilter) historyExitFilter.disabled = !runOnlyEnabled;
  if (typeof historyStarredToggle !== 'undefined' && historyStarredToggle) historyStarredToggle.disabled = !runOnlyEnabled;
  if (typeof syncAppSelect === 'function') {
    if (typeof historyTypeFilter !== 'undefined') syncAppSelect(historyTypeFilter);
    if (typeof historyExitFilter !== 'undefined') syncAppSelect(historyExitFilter);
    if (typeof historyDateFilter !== 'undefined') syncAppSelect(historyDateFilter);
  }
  if (typeof histClearAllBtn !== 'undefined' && histClearAllBtn) {
    histClearAllBtn.classList.toggle('u-hidden', _historyFilters.type === 'snapshots');
  }
}

function _historyHasActiveServerFilters() {
  return _historyCore.hasActiveServerFilters(_historyFilters);
}

function _historyHasAnyFilters() {
  return _historyCore.hasAnyFilters(_historyFilters);
}

function _historyResetRunOnlyFilters() {
  _historyFilters = _historyCore.resetRunOnlyFilters(_historyFilters);
}

function _historyLabelForType(type = _historyFilters.type) {
  return _historyCore.labelForType(type);
}

function _historySummaryLabel(totalCount = _historyPaging.totalCount) {
  return _historyCore.summaryLabel(_historyFilters.type, totalCount);
}

function _historyCommandRootsFromRuns(runs) {
  return _historyCore.commandRootsFromRuns(runs);
}

function _renderHistoryRootSuggestions(runs) {
  const nextSuggestions = _historyCommandRootsFromRuns(runs);
  const currentQuery = typeof historyRootInput !== 'undefined' && historyRootInput
    ? _normalizeHistoryFilterValue(historyRootInput.value)
    : _historyFilters.commandRoot;
  if (_historyRootInputFocused && currentQuery) {
    // The server-side command_root filter is exact-root oriented. While the
    // user is typing a partial root, a refresh can legitimately return no
    // matching rows; do not let that transient response erase the suggestion
    // pool the user is actively choosing from.
    const merged = new Set([..._historyRootSuggestions, ...nextSuggestions]);
    _historyRootSuggestions = [...merged].sort((a, b) => a.localeCompare(b));
  } else {
    _historyRootSuggestions = nextSuggestions;
  }
  _historyRefreshRootDropdown();
}

function _appendHistoryCommandEcho(tabId, command) {
  if (typeof appendCommandEcho === 'function') {
    appendCommandEcho(command, tabId);
    return;
  }
  appendLine(command, 'prompt-echo', tabId);
}

function _historyOutputLineMetadata(entry) {
  if (!entry || typeof entry !== 'object') return null;
  const metadata = {};
  if (Array.isArray(entry.signals) && entry.signals.length) metadata.signals = entry.signals;
  if (Number.isInteger(entry.line_index)) metadata.line_index = entry.line_index;
  if (typeof entry.command_root === 'string' && entry.command_root) metadata.command_root = entry.command_root;
  if (typeof entry.target === 'string' && entry.target) metadata.target = entry.target;
  return Object.keys(metadata).length ? metadata : null;
}

function _appendHistoryOutputLine(entry, tabId) {
  if (entry && typeof entry === 'object') {
    const text = String(entry.text || '');
    const cls = String(entry.cls || '');
    const metadata = _historyOutputLineMetadata(entry);
    if (metadata) appendLine(text, cls, tabId, metadata);
    else appendLine(text, cls, tabId);
    return;
  }
  appendLine(String(entry || ''), '', tabId);
}

function _hideHistoryRootDropdown() {
  if (typeof historyRootDropdown === 'undefined' || !historyRootDropdown) return;
  historyRootDropdown.replaceChildren();
  historyRootDropdown.classList.add('u-hidden');
  _historyRootFiltered = [];
  _historyRootIndex = -1;
}

function _historyRootMatches(query) {
  return _historyCore.rootMatches(_historyRootSuggestions, query, 12);
}

function _acceptHistoryRootSuggestion(root) {
  _historyRootSuppressInputOnce = true;
  if (typeof historyRootInput !== 'undefined' && historyRootInput) historyRootInput.value = root;
  _hideHistoryRootDropdown();
  _setHistoryFilter('commandRoot', root);
  if (typeof historyRootInput !== 'undefined' && historyRootInput) {
    setTimeout(() => focusElement(historyRootInput, { preventScroll: true }), 0);
  }
}

function _renderHistoryRootDropdown(items, query) {
  if (typeof historyRootDropdown === 'undefined' || !historyRootDropdown) return;
  historyRootDropdown.replaceChildren();
  if (!items.length) {
    _hideHistoryRootDropdown();
    return;
  }
  const normalizedQuery = _normalizeHistoryFilterValue(query).toLowerCase();
  if (items.length === 1 && normalizedQuery && items[0].toLowerCase() === normalizedQuery) {
    _hideHistoryRootDropdown();
    return;
  }
  const mobileMode = typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode();
  historyRootDropdown.classList.toggle('ac-mobile', mobileMode);
  items.forEach((root, index) => {
    const item = document.createElement('div');
    item.className = 'ac-item dropdown-item dropdown-item-dense'
      + (index === _historyRootIndex ? ' ac-active dropdown-item-active' : '');
    const matchIndex = normalizedQuery ? root.toLowerCase().indexOf(normalizedQuery) : -1;
    if (matchIndex >= 0 && normalizedQuery) {
      item.innerHTML = escapeHtml(root.slice(0, matchIndex))
        + '<span class="ac-match">' + escapeHtml(root.slice(matchIndex, matchIndex + normalizedQuery.length)) + '</span>'
        + escapeHtml(root.slice(matchIndex + normalizedQuery.length));
    } else {
      item.textContent = root;
    }
    item.addEventListener('mousedown', e => {
      e.preventDefault();
      e.stopPropagation();
      _acceptHistoryRootSuggestion(root);
    });
    item.addEventListener('touchstart', e => {
      e.preventDefault();
      e.stopPropagation();
      _acceptHistoryRootSuggestion(root);
    }, { passive: false });
    historyRootDropdown.appendChild(item);
  });
  historyRootDropdown.classList.remove('u-hidden');
}

function _historyRefreshRootDropdown() {
  const query = typeof historyRootInput !== 'undefined' && historyRootInput ? historyRootInput.value : _historyFilters.commandRoot;
  _historyRootFiltered = _historyRootMatches(query);
  if (_historyRootIndex >= _historyRootFiltered.length) _historyRootIndex = _historyRootFiltered.length - 1;
  _renderHistoryRootDropdown(_historyRootFiltered, query);
}

function _historyActiveFilterItems() {
  return _historyCore.activeFilterItems(_historyFilters);
}

function _historySetPage(nextPage, { refresh = true } = {}) {
  const page = Math.max(1, Number(nextPage) || 1);
  if (_historyPaging.page !== page) {
    _historyPaging.page = page;
  }
  if (refresh) refreshHistoryPanel();
}

function _historyRenderPagination(visibleCount = 0) {
  if (typeof historyPagination === 'undefined' || !historyPagination) return;
  if (typeof historyPaginationSummary === 'undefined' || !historyPaginationSummary) return;
  if (typeof historyPaginationControls === 'undefined' || !historyPaginationControls) return;

  const { page, pageSize, totalCount, pageCount } = _historyPaging;
  const totalLabel = _historySummaryLabel(totalCount);
  if (totalCount > 0) {
    const start = ((page - 1) * pageSize) + 1;
    const count = Math.max(0, Number(visibleCount) || 0);
    const end = count > 0 ? Math.min(totalCount, start + count - 1) : start;
    historyPaginationSummary.textContent = `Showing ${start}-${end} of ${totalCount} ${totalLabel}`;
  } else {
    historyPaginationSummary.textContent = `Showing 0 of 0 ${_historySummaryLabel(0)}`;
  }

  historyPaginationControls.replaceChildren();

  const prevPage = page > 1 ? page - 1 : 1;
  const prevBtn = document.createElement('button');
  prevBtn.type = 'button';
  prevBtn.className = 'btn btn-secondary btn-compact history-pagination-chevron';
  prevBtn.textContent = '‹ Prev';
  prevBtn.disabled = page <= 1;
  prevBtn.setAttribute('aria-label', 'Previous page');
  prevBtn.addEventListener('click', () => _historySetPage(prevPage));
  historyPaginationControls.appendChild(prevBtn);

  const pageLabel = document.createElement('span');
  pageLabel.className = 'history-pagination-status';
  pageLabel.textContent = `Page ${pageCount > 0 ? page : 0} of ${pageCount}`;
  pageLabel.setAttribute('aria-live', 'polite');
  historyPaginationControls.appendChild(pageLabel);

  const nextPage = pageCount > page ? page + 1 : page;
  const nextBtn = document.createElement('button');
  nextBtn.type = 'button';
  nextBtn.className = 'btn btn-secondary btn-compact history-pagination-chevron';
  nextBtn.textContent = 'Next ›';
  nextBtn.disabled = page >= pageCount;
  nextBtn.setAttribute('aria-label', 'Next page');
  nextBtn.addEventListener('click', () => _historySetPage(nextPage));
  historyPaginationControls.appendChild(nextBtn);

  historyPagination.classList.remove('u-hidden');
}

function _renderHistoryActiveFilters() {
  if (typeof historyActiveFilters === 'undefined' || !historyActiveFilters) return;
  historyActiveFilters.replaceChildren();
  const items = _historyActiveFilterItems();
  historyActiveFilters.classList.toggle('u-hidden', !items.length);
  items.forEach(item => {
    const chip = document.createElement('div');
    chip.className = 'history-active-filter-chip chip chip-removable';
    chip.dataset.filterKey = item.key;
    const label = document.createElement('span');
    label.textContent = item.label;
    chip.appendChild(label);
    const removeBtn = document.createElement('button');
    removeBtn.className = 'history-active-filter-remove';
    removeBtn.type = 'button';
    removeBtn.setAttribute('aria-label', `Remove ${item.label} filter`);
    removeBtn.textContent = '✕';
    removeBtn.addEventListener('click', e => {
      e.preventDefault();
      e.stopPropagation();
      const resetValue = item.key === 'starredOnly' ? false : (item.key === 'q' || item.key === 'commandRoot' ? '' : 'all');
      _setHistoryFilter(item.key, resetValue);
    });
    chip.appendChild(removeBtn);
    historyActiveFilters.appendChild(chip);
  });
}

function _buildHistoryRequestUrl() {
  return _historyCore.buildRequestUrl(_historyFilters, _historyPaging);
}

function _applyHistoryClientFilters(runs) {
  return Array.isArray(runs) ? runs.slice() : [];
}

function _renderHistoryEmptyState() {
  if (typeof historyList === 'undefined' || !historyList) return;
  const empty = document.createElement('div');
  empty.className = 'history-empty-state';
  const title = document.createElement('div');
  title.className = 'history-empty-state-title';
  const typeLabel = _historyLabelForType();
  title.textContent = _historyHasAnyFilters()
    ? `No matching ${typeLabel}.`
    : _historyFilters.type === 'snapshots'
      ? 'No snapshots yet.'
      : _historyFilters.type === 'runs'
        ? 'No runs yet.'
        : 'No history yet.';
  empty.appendChild(title);

  const detail = document.createElement('div');
  detail.className = 'history-empty-state-detail';
  detail.textContent = _historyHasAnyFilters()
    ? 'Adjust or clear the current filters to widen the history results.'
    : _historyFilters.type === 'snapshots'
      ? 'Saved snapshots will appear here for this browser session.'
      : _historyFilters.type === 'runs'
        ? 'Completed commands will appear here for this browser session.'
        : 'Completed commands and saved snapshots will appear here for this browser session.';
  empty.appendChild(detail);
  historyList.appendChild(empty);
  if (typeof historyPagination !== 'undefined' && historyPagination) {
    historyPagination.classList.remove('u-hidden');
  }
}

function _scheduleHistoryPanelRefresh() {
  if (_historyFilterRefreshTimer) clearTimeout(_historyFilterRefreshTimer);
  _historyFilterRefreshTimer = setTimeout(() => {
    _historyFilterRefreshTimer = null;
    refreshHistoryPanel();
  }, 120);
}

function _setHistoryFilter(key, value, { debounce = false } = {}) {
  if (key === 'starredOnly') _historyFilters.starredOnly = !!value;
  else _historyFilters[key] = _normalizeHistoryFilterValue(value) || (key === 'q' || key === 'commandRoot' ? '' : 'all');
  if (key === 'type' && _historyFilters.type === 'snapshots') _historyResetRunOnlyFilters();
  _historyPaging.page = 1;
  if (debounce) _scheduleHistoryPanelRefresh();
  else refreshHistoryPanel();
}

function openHistoryWithFilters(filters = {}) {
  const selection = window.getSelection?.();
  if (selection && typeof selection.removeAllRanges === 'function') {
    selection.removeAllRanges();
  }
  const nextFilters = {
    ..._historyFilters,
    ...filters,
  };
  if (Object.prototype.hasOwnProperty.call(filters, 'commandRoot')) {
    nextFilters.commandRoot = _normalizeHistoryFilterValue(filters.commandRoot);
    if (nextFilters.commandRoot && (!filters.type || filters.type === 'all')) {
      nextFilters.type = 'runs';
    }
  }
  _historyFilters = {
    type: _normalizeHistoryFilterValue(nextFilters.type) || 'all',
    q: _normalizeHistoryFilterValue(nextFilters.q),
    commandRoot: _normalizeHistoryFilterValue(nextFilters.commandRoot),
    exitCode: _normalizeHistoryFilterValue(nextFilters.exitCode) || 'all',
    dateRange: _normalizeHistoryFilterValue(nextFilters.dateRange) || 'all',
    starredOnly: !!nextFilters.starredOnly,
  };
  _historyPaging.page = 1;
  _syncHistoryFilterControls();
  _renderHistoryActiveFilters();
  _hideHistoryRootDropdown();
  if (typeof toggleHistoryPanelSurface === 'function') {
    toggleHistoryPanelSurface(true);
  } else {
    if (typeof showHistoryPanel === 'function') showHistoryPanel();
    refreshHistoryPanel();
  }
  return true;
}

function clearHistoryFilters() {
  _historyFilters = {
    type: 'all',
    q: '',
    commandRoot: '',
    exitCode: 'all',
    dateRange: 'all',
    starredOnly: false,
  };
  _historyPaging.page = 1;
  _syncHistoryFilterControls();
  _renderHistoryActiveFilters();
  _hideHistoryRootDropdown();
  refreshHistoryPanel();
}

function resetHistoryMobileFilters() {
  _historyMobileAdvancedOpen = false;
  _syncHistoryFilterControls();
  _hideHistoryRootDropdown();
}

function toggleHistoryMobileFilters(force = null) {
  const next = force === null ? !_historyMobileAdvancedOpen : !!force;
  _historyMobileAdvancedOpen = next;
  _syncHistoryFilterControls();
  return _historyMobileAdvancedOpen;
}


// ── Command history chips ──

function _activeTabCommandHistoryState() {
  const tab = typeof getActiveTab === 'function' ? getActiveTab() : null;
  if (!tab) return null;
  if (!Array.isArray(tab.commandHistory)) tab.commandHistory = [];
  if (!Number.isInteger(tab.historyNavIndex)) tab.historyNavIndex = -1;
  if (typeof tab.historyNavDraft !== 'string') tab.historyNavDraft = '';
  return tab;
}

function _historyLimit() {
  return _historyCore.historyLimit(APP_CONFIG);
}

function _commandRecallHistory(tab) {
  return _historyCore.commandRecallHistory(tab, cmdHistory, _historyLimit());
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

function _makeOverflowChip(_count) {
  const chip = document.createElement('button');
  chip.className = 'hist-chip hist-chip-overflow chip chip-action';
  chip.textContent = '+ more';
  chip.title = 'Open history panel';
  chip.addEventListener('click', () => {
    if (!historyPanel) return;
    if (typeof resetHistoryMobileFilters === 'function') resetHistoryMobileFilters();
    showHistoryPanel();
    if (typeof refreshHistoryPanel === 'function') refreshHistoryPanel();
  });
  return chip;
}

function _applyDesktopChipOverflow() {
  const chips = Array.from(histRow.querySelectorAll('.hist-chip:not(.hist-chip-overflow)'));
  if (!chips.length) return;

  // getBoundingClientRect forces a synchronous layout so positions are accurate.
  // In jsdom all rects are zero so the guard below falls through cleanly.
  const firstTop = chips[0].getBoundingClientRect().top;

  // Find the first chip that has wrapped to a second row.
  let overflowIdx = chips.length;
  for (let i = 1; i < chips.length; i++) {
    if (chips[i].getBoundingClientRect().top > firstTop + 2) {
      overflowIdx = i;
      break;
    }
  }
  if (overflowIdx === chips.length) return; // all chips fit on one row

  // Remove overflowing chips and add the history shortcut chip.
  for (let i = chips.length - 1; i >= overflowIdx; i--) {
    histRow.removeChild(chips[i]);
  }
  const overflowChip = _makeOverflowChip();
  histRow.appendChild(overflowChip);

  // If the overflow chip itself wrapped (getBoundingClientRect forces another reflow),
  // keep pulling regular chips until the overflow chip sits on the first row.
  while (overflowChip.getBoundingClientRect().top > firstTop + 2) {
    const regularChips = Array.from(histRow.querySelectorAll('.hist-chip:not(.hist-chip-overflow)'));
    const lastRegularChip = regularChips[regularChips.length - 1];
    if (!lastRegularChip) break;
    histRow.removeChild(lastRegularChip);
  }
}

function _emitHistoryRendered() {
  if (typeof emitUiEvent === 'function') {
    emitUiEvent('app:history-rendered', {
      cmdHistory: Array.isArray(cmdHistory) ? cmdHistory.slice() : [],
      recentPreviewHistory: Array.isArray(recentPreviewHistory) ? recentPreviewHistory.slice() : [],
    });
  }
}

function renderHistory() {
  while (histRow.children.length > 1) histRow.removeChild(histRow.lastChild);
  if (!cmdHistory.length) {
    hideHistoryRow();
    _emitHistoryRendered();
    return;
  }
  showHistoryRow();

  const starred = _getStarred();
  // Starred commands first, then remaining in recency order
  const sorted = [
    ...cmdHistory.filter(c => starred.has(c)),
    ...cmdHistory.filter(c => !starred.has(c)),
  ];

  const isMobile = typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode();
  const visible = isMobile ? sorted.slice(0, 3) : sorted;

  visible.forEach(cmd => {
    const isStarred = starred.has(cmd);
    const chip = document.createElement('button');
    chip.className = 'hist-chip chip chip-action' + (isStarred ? ' starred' : '');
    chip.title = cmd;

    const textEl = document.createElement('span');
    textEl.textContent = cmd;

    if (!isMobile) {
      const starEl = document.createElement('span');
      starEl.className = 'chip-star';
      starEl.textContent = isStarred ? '★' : '☆';
      starEl.title = isStarred ? 'Unstar' : 'Star';
      starEl.addEventListener('click', e => {
        e.stopPropagation();
        _toggleStar(cmd);
        renderHistory();
      });
      chip.appendChild(starEl);
    }

    chip.appendChild(textEl);
    chip.addEventListener('click', () => {
      blurActiveElement();
      setComposerValue(cmd, cmd.length, cmd.length);
      if (refocusComposerAfterAction({ preventScroll: true })) return;
      resetCmdHistoryNav();
    });
    histRow.appendChild(chip);
  });

  if (isMobile && visible.length < sorted.length) {
    histRow.appendChild(_makeOverflowChip());
  } else if (!isMobile) {
    _applyDesktopChipOverflow();
  }

  _emitHistoryRendered();
}

// Re-measure chip overflow when the window is resized on desktop.
if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  window.addEventListener('resize', () => {
    if (typeof useMobileTerminalViewportMode === 'function' && !useMobileTerminalViewportMode()) {
      renderHistory();
    }
  });
}


function _historyRelativeTime(startedAt, now = new Date()) {
  return _historyCore.relativeTime(startedAt, now);
}

function _historyMetaKindBadge(kind, label = kind.toUpperCase()) {
  const badge = document.createElement('span');
  const tone = kind === 'run' ? 'badge-tone-green' : 'badge-tone-muted';
  badge.className = `history-entry-kind history-entry-kind-${kind} badge ${tone}`;
  badge.textContent = label;
  return badge;
}

function _historyExitCodeNumber(exitCode) {
  return _historyCore.exitCodeNumber(exitCode);
}

function _historyIsGracefulTerminationExitCode(exitCode) {
  return _historyCore.isGracefulTerminationExitCode(exitCode);
}

function _historyIsFailedExitCode(exitCode) {
  return _historyCore.isFailedExitCode(exitCode);
}

function _historyExitLabel(exitCode) {
  return _historyCore.exitLabel(exitCode);
}

function _historyExitClass(exitCode) {
  return _historyCore.exitClass(exitCode);
}

function _historyElapsedSeconds(run) {
  return _historyCore.elapsedSeconds(run);
}

function _historyElapsedLabel(run) {
  return _historyCore.elapsedLabel(run);
}

function _createHistoryEntry(run, isStarred) {
  const entry = document.createElement('div');
  entry.className = 'history-entry chrome-row chrome-row-clickable' + (isStarred ? ' starred row-accent-amber' : '');
  const exitCls = _historyExitClass(run.exit_code);
  const startedAt = new Date(run.started);
  const now = new Date();
  const validDate = !Number.isNaN(startedAt.getTime());
  const time = startedAt.toLocaleTimeString();
  const showDate = validDate && (
    startedAt.getFullYear() !== now.getFullYear()
    || startedAt.getMonth() !== now.getMonth()
    || startedAt.getDate() !== now.getDate()
  );

  const header = document.createElement('div');
  header.className = 'history-entry-header';

  const starBtn = document.createElement('button');
  starBtn.className = 'history-entry-star' + (isStarred ? ' starred' : '');
  starBtn.dataset.action = 'star';
  starBtn.type = 'button';
  const starLabel = isStarred
    ? 'Unstar — stop pinning this command to the top of history'
    : 'Star — keep this command pinned at the top of history';
  starBtn.setAttribute('aria-label', starLabel);
  starBtn.title = starLabel;
  starBtn.textContent = isStarred ? '★' : '☆';
  header.appendChild(starBtn);

  const cmd = document.createElement('div');
  cmd.className = 'history-entry-cmd';
  cmd.textContent = run.command || '';
  header.appendChild(cmd);
  entry.appendChild(header);

  const meta = document.createElement('div');
  meta.className = 'history-entry-meta';
  meta.appendChild(_historyMetaKindBadge('run'));
  const timeEl = document.createElement('span');
  timeEl.textContent = time;
  meta.appendChild(timeEl);
  if (showDate) {
    const dateEl = document.createElement('span');
    dateEl.className = 'history-entry-date';
    dateEl.textContent = startedAt.toLocaleDateString();
    meta.appendChild(dateEl);
  }
  const elapsedLabel = _historyElapsedLabel(run);
  if (elapsedLabel) {
    const elapsedEl = document.createElement('span');
    elapsedEl.className = 'history-entry-elapsed';
    elapsedEl.textContent = elapsedLabel;
    meta.appendChild(elapsedEl);
  }
  const exitEl = document.createElement('span');
  exitEl.className = exitCls;
  exitEl.textContent = _historyExitLabel(run.exit_code);
  meta.appendChild(exitEl);
  entry.appendChild(meta);

  const actions = document.createElement('div');
  actions.className = 'history-actions';

  const restoreBtn = document.createElement('button');
  restoreBtn.className = 'history-action-btn btn btn-secondary btn-compact';
  restoreBtn.type = 'button';
  restoreBtn.dataset.action = 'restore';
  restoreBtn.textContent = 'restore';
  actions.appendChild(restoreBtn);

  const permalinkBtn = document.createElement('button');
  permalinkBtn.className = 'history-action-btn btn btn-secondary btn-compact';
  permalinkBtn.type = 'button';
  permalinkBtn.dataset.action = 'permalink';
  permalinkBtn.textContent = 'permalink';
  actions.appendChild(permalinkBtn);

  const compareBtn = document.createElement('button');
  compareBtn.className = 'history-action-btn btn btn-secondary btn-compact';
  compareBtn.type = 'button';
  compareBtn.dataset.action = 'compare';
  compareBtn.textContent = 'compare';
  actions.appendChild(compareBtn);

  const deleteBtn = document.createElement('button');
  deleteBtn.className = 'history-action-btn btn btn-secondary btn-compact';
  deleteBtn.type = 'button';
  deleteBtn.dataset.action = 'delete';
  deleteBtn.textContent = 'delete';
  actions.appendChild(deleteBtn);

  entry.appendChild(actions);
  return entry;
}

function _createSnapshotHistoryEntry(snapshot) {
  const entry = document.createElement('div');
  entry.className = 'history-entry history-entry-snapshot chrome-row chrome-row-clickable';

  const header = document.createElement('div');
  header.className = 'history-entry-header';

  const title = document.createElement('div');
  title.className = 'history-entry-cmd';
  title.textContent = snapshot.label || 'snapshot';
  header.appendChild(title);
  entry.appendChild(header);

  const meta = document.createElement('div');
  meta.className = 'history-entry-meta';
  meta.appendChild(_historyMetaKindBadge('snapshot'));
  const createdAt = new Date(snapshot.created);
  const timeEl = document.createElement('span');
  timeEl.textContent = Number.isNaN(createdAt.getTime())
    ? ''
    : _historyRelativeTime(createdAt);
  if (!Number.isNaN(createdAt.getTime())) timeEl.title = createdAt.toLocaleString();
  meta.appendChild(timeEl);
  entry.appendChild(meta);

  const actions = document.createElement('div');
  actions.className = 'history-actions';

  const openBtn = document.createElement('button');
  openBtn.className = 'history-action-btn btn btn-secondary btn-compact';
  openBtn.type = 'button';
  openBtn.dataset.action = 'open';
  openBtn.textContent = 'open';
  actions.appendChild(openBtn);

  const linkBtn = document.createElement('button');
  linkBtn.className = 'history-action-btn btn btn-secondary btn-compact';
  linkBtn.type = 'button';
  linkBtn.dataset.action = 'link';
  linkBtn.textContent = 'copy link';
  actions.appendChild(linkBtn);

  const deleteBtn = document.createElement('button');
  deleteBtn.className = 'history-action-btn btn btn-secondary btn-compact';
  deleteBtn.type = 'button';
  deleteBtn.dataset.action = 'delete';
  deleteBtn.textContent = 'delete';
  actions.appendChild(deleteBtn);

  entry.appendChild(actions);
  return entry;
}

function _snapshotUrl(snapshot) {
  return `${location.origin}/share/${snapshot.id}`;
}

function openSnapshotLink(snapshot) {
  if (!snapshot || !snapshot.id) return;
  const url = _snapshotUrl(snapshot);
  if (typeof window !== 'undefined' && window && typeof window.open === 'function') {
    window.open(url, '_blank', 'noopener,noreferrer');
  }
}

function _historyActionKeepsPanelOpen(action) {
  if (action === 'star') return true;
  if (action === 'compare') return true;
  const mobileMode = typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode();
  if (!mobileMode) return false;
  return action === 'permalink';
}

function _compareFormatDate(value) {
  return _historyCore.compareFormatDate(value);
}

function _compareDateGroupLabel(value) {
  return _historyCore.compareDateGroupLabel(value);
}

function _compareFormatDuration(seconds) {
  return _historyCore.compareFormatDuration(seconds);
}

function _compareFormatDelta(value, suffix = '') {
  return _historyCore.compareFormatDelta(value, suffix);
}

function _ensureHistoryCompareOverlay() {
  let overlay = document.getElementById('history-compare-overlay');
  if (overlay) return overlay;

  overlay = document.createElement('div');
  overlay.id = 'history-compare-overlay';
  overlay.className = 'modal-overlay mobile-sheet-overlay u-hidden history-compare-overlay';
  overlay.innerHTML = `
    <section id="history-compare-modal" class="history-compare-modal mobile-sheet-surface" role="dialog" aria-modal="true" aria-labelledby="history-compare-title">
      <div class="sheet-grab gesture-handle" role="button" tabindex="0" aria-label="Close run comparison"></div>
      <div class="history-compare-header surface-header">
        <div>
          <div id="history-compare-title" class="history-compare-title">COMPARE RUNS</div>
          <div id="history-compare-subtitle" class="history-compare-subtitle"></div>
        </div>
        <button type="button" class="close-btn history-compare-close" aria-label="Close run comparison">✕</button>
      </div>
      <div id="history-compare-body" class="history-compare-body surface-body nice-scroll"></div>
    </section>
  `;
  document.body.appendChild(overlay);
  overlay.addEventListener('click', e => {
    if (e.target === overlay) closeHistoryCompareOverlay();
  });
  overlay.querySelectorAll('.history-compare-close, .sheet-grab').forEach(el => {
    el.addEventListener('click', () => closeHistoryCompareOverlay());
    el.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        closeHistoryCompareOverlay();
      }
    });
  });
  if (typeof bindDismissible === 'function') {
    bindDismissible(overlay, {
      level: 'modal',
      isOpen: () => overlay.classList.contains('open'),
      onClose: closeHistoryCompareOverlay,
      closeButtons: overlay.querySelectorAll('.history-compare-close, .sheet-grab'),
    });
  }
  return overlay;
}

function closeHistoryCompareOverlay() {
  const overlay = document.getElementById('history-compare-overlay');
  if (!overlay) return;
  overlay.classList.remove('open');
  overlay.classList.add('u-hidden');
  overlay.setAttribute('aria-hidden', 'true');
  if (typeof refocusComposerAfterAction === 'function') {
    refocusComposerAfterAction({ preventScroll: true });
  }
}

function _openHistoryCompareOverlay() {
  const overlay = _ensureHistoryCompareOverlay();
  overlay.classList.remove('u-hidden');
  overlay.classList.add('open');
  overlay.setAttribute('aria-hidden', 'false');
}

function isHistoryCompareOverlayOpen() {
  const overlay = document.getElementById('history-compare-overlay');
  return !!(overlay && overlay.classList.contains('open'));
}

function _historyCompareRunCard(run, label, extra = '') {
  const card = document.createElement('div');
  card.className = 'history-compare-run-card';
  const eyebrow = document.createElement('div');
  eyebrow.className = 'history-compare-run-eyebrow';
  eyebrow.textContent = label;
  card.appendChild(eyebrow);
  const command = document.createElement('div');
  command.className = 'history-compare-run-command';
  command.textContent = run && run.command ? run.command : 'unknown command';
  card.appendChild(command);
  const meta = document.createElement('div');
  meta.className = 'history-compare-run-meta';
  const parts = [];
  if (run && run.started) parts.push(_compareFormatDate(run.started));
  if (run && run.exit_code !== undefined && run.exit_code !== null) parts.push(`exit ${run.exit_code}`);
  if (run && Number.isFinite(Number(run.output_line_count))) parts.push(`${Number(run.output_line_count).toLocaleString()} lines`);
  if (extra) parts.push(extra);
  meta.textContent = parts.join(' · ');
  card.appendChild(meta);
  return card;
}

function _renderHistoryCompareLauncher() {
  const overlay = _ensureHistoryCompareOverlay();
  const body = overlay.querySelector('#history-compare-body');
  const subtitle = overlay.querySelector('#history-compare-subtitle');
  if (!body) return;
  body.replaceChildren();
  const source = _historyCompareState.source;
  subtitle.textContent = source && source.command ? source.command : 'Choose two completed runs to compare';

  if (!source) {
    const empty = document.createElement('div');
    empty.className = 'history-compare-empty';
    empty.textContent = 'Choose a source run from history first.';
    body.appendChild(empty);
    return;
  }

  const sourceCard = _historyCompareRunCard(source, 'Run A');
  body.appendChild(sourceCard);

  const suggested = _historyCompareState.selected || _historyCompareState.candidates[0] || null;
  const suggestedWrap = document.createElement('div');
  suggestedWrap.className = 'history-compare-section';
  const suggestedTitle = document.createElement('div');
  suggestedTitle.className = 'history-compare-section-title';
  suggestedTitle.textContent = 'Suggested match';
  suggestedWrap.appendChild(suggestedTitle);
  if (suggested) {
    suggestedWrap.appendChild(_historyCompareRunCard(
      suggested,
      'Run B',
      suggested.confidence_label || '',
    ));
    const primary = document.createElement('button');
    primary.type = 'button';
    primary.className = 'btn btn-primary btn-compact history-compare-primary';
    primary.textContent = 'Compare with suggested run';
    primary.addEventListener('click', () => fetchAndRenderHistoryComparison(source.id, suggested.id));
    suggestedWrap.appendChild(primary);
  } else {
    const empty = document.createElement('div');
    empty.className = 'history-compare-empty';
    empty.textContent = 'No earlier similar run found. Choose a run manually.';
    suggestedWrap.appendChild(empty);
  }
  body.appendChild(suggestedWrap);

  const manual = document.createElement('div');
  manual.className = 'history-compare-section';
  const manualTitle = document.createElement('div');
  manualTitle.className = 'history-compare-section-title';
  manualTitle.textContent = 'Choose another run';
  manual.appendChild(manualTitle);
  const search = document.createElement('input');
  search.className = 'form-control history-compare-search';
  search.type = 'text';
  search.placeholder = 'search history';
  search.value = _historyCompareState.manualQuery || '';
  search.autocomplete = 'off';
  search.spellcheck = false;
  search.addEventListener('input', e => {
    _historyCompareState.manualQuery = e.target.value;
    _loadHistoryCompareManualCandidates(source, e.target.value);
  });
  manual.appendChild(search);
  const list = document.createElement('div');
  list.className = 'history-compare-candidate-list';
  list.dataset.compareCandidateList = '1';
  manual.appendChild(list);
  body.appendChild(manual);
  _renderHistoryCompareCandidateList();
}

let _historyCompareManualTimer = null;

function _loadHistoryCompareManualCandidates(source, query = '') {
  if (_historyCompareManualTimer) clearTimeout(_historyCompareManualTimer);
  _historyCompareState.manualPage = 1;
  _historyCompareState.manualHasNext = false;
  _historyCompareState.manualLoading = false;
  _historyCompareState.manualCollapsedGroups = new Set();
  const requestId = (_historyCompareState.manualRequestId || 0) + 1;
  _historyCompareState.manualRequestId = requestId;
  _historyCompareManualTimer = setTimeout(() => {
    _historyCompareManualTimer = null;
    _fetchHistoryCompareManualCandidates(source, query, { requestId, page: 1, append: false });
  }, 120);
}

function _fetchHistoryCompareManualCandidates(source, query = '', { requestId = null, page = 1, append = false } = {}) {
  if (!source || !source.id || _historyCompareState.manualLoading) return;
  const activeRequestId = requestId || _historyCompareState.manualRequestId || 0;
  _historyCompareState.manualLoading = true;
  _renderHistoryCompareCandidateList();
  const params = new URLSearchParams();
  params.set('type', 'runs');
  params.set('page_size', '20');
  params.set('include_total', '1');
  params.set('page', String(page));
  const trimmed = String(query || '').trim();
  if (trimmed) {
    params.set('scope', 'command');
    params.set('q', trimmed);
  }
  else if (source && source.command_root) params.set('command_root', source.command_root);
  apiFetch(`/history?${params.toString()}`)
    .then(resp => resp.json())
    .then(data => {
      if (_historyCompareState.manualRequestId !== activeRequestId) return;
      const items = Array.isArray(data.items) ? data.items : (Array.isArray(data.runs) ? data.runs : []);
      const ranked = _historyCompareState.candidates || [];
      const seenRanked = new Set(ranked.map(item => item.id));
      const existing = append ? new Set((_historyCompareState.manualCandidates || []).map(item => item.id)) : new Set();
      const manualItems = items
        .filter(item => item && item.type !== 'snapshot' && item.id && item.id !== source.id && !existing.has(item.id))
        .map(item => ({
          ...item,
          confidence_label: seenRanked.has(item.id) ? ((ranked.find(candidate => candidate.id === item.id) || {}).confidence_label || '') : '',
        }));
      _historyCompareState.manualCandidates = append
        ? [...(_historyCompareState.manualCandidates || []), ...manualItems]
        : manualItems;
      _historyCompareState.manualLoaded = true;
      _historyCompareState.manualPage = Number(data.page) || page;
      _historyCompareState.manualHasNext = !!data.has_next;
      _historyCompareState.manualLoading = false;
      _renderHistoryCompareCandidateList();
    })
    .catch(() => {
      if (_historyCompareState.manualRequestId === activeRequestId) {
        _historyCompareState.manualLoading = false;
        _renderHistoryCompareCandidateList();
      }
      showToast('Failed to load comparison choices', 'error');
    });
}

function _renderHistoryCompareCandidateList() {
  const list = document.querySelector('[data-compare-candidate-list="1"]');
  const source = _historyCompareState.source;
  if (!list || !source) return;
  const search = document.querySelector('.history-compare-search');
  const searchWasFocused = search && document.activeElement === search;
  list.replaceChildren();
  const sourceCandidates = _historyCompareState.manualLoaded
    ? (_historyCompareState.manualCandidates || [])
    : (_historyCompareState.candidates || []);
  const candidates = sourceCandidates
    .filter(item => item && item.id && item.id !== source.id);
  if (!candidates.length) {
    const empty = document.createElement('div');
    empty.className = 'history-compare-empty';
    empty.textContent = _historyCompareState.manualLoading ? 'Loading runs...' : 'No runs found for the current search.';
    list.appendChild(empty);
    if (searchWasFocused && typeof search.focus === 'function') {
      search.focus({ preventScroll: true });
    }
    return;
  }
  const groups = [];
  const groupByLabel = new Map();
  candidates.forEach(candidate => {
    const groupLabel = _compareDateGroupLabel(candidate.started || candidate.created);
    let group = groupByLabel.get(groupLabel);
    if (!group) {
      group = { label: groupLabel, items: [] };
      groupByLabel.set(groupLabel, group);
      groups.push(group);
    }
    group.items.push(candidate);
  });
  groups.forEach(group => {
    const collapsed = _historyCompareState.manualCollapsedGroups.has(group.label);
    const groupEl = document.createElement('div');
    groupEl.className = 'history-compare-candidate-group';

    const headerBtn = document.createElement('button');
    headerBtn.type = 'button';
    headerBtn.className = 'history-compare-candidate-day';
    headerBtn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    const icon = document.createElement('span');
    icon.className = 'history-compare-candidate-day-icon disclosure-chev';
    icon.textContent = '▸';
    headerBtn.appendChild(icon);
    const label = document.createElement('span');
    label.className = 'history-compare-candidate-day-label';
    label.textContent = group.label;
    headerBtn.appendChild(label);
    const count = document.createElement('span');
    count.className = 'history-compare-candidate-day-count';
    count.textContent = String(group.items.length);
    headerBtn.appendChild(count);
    groupEl.appendChild(headerBtn);

    const rows = document.createElement('div');
    rows.className = 'history-compare-candidate-group-rows';
    rows.hidden = collapsed;
    group.items.forEach(candidate => {
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'history-compare-candidate history-entry chrome-row chrome-row-clickable';
      row.dataset.runId = candidate.id;
      const rowHeader = document.createElement('span');
      rowHeader.className = 'history-entry-header';
      const cmd = document.createElement('span');
      cmd.className = 'history-entry-cmd history-compare-candidate-command';
      cmd.textContent = candidate.command || '';
      rowHeader.appendChild(cmd);
      row.appendChild(rowHeader);
      const meta = document.createElement('span');
      meta.className = 'history-entry-meta history-compare-candidate-meta';
      meta.textContent = [
        candidate.confidence_label || '',
        candidate.started ? _compareFormatDate(candidate.started) : '',
        candidate.exit_code !== undefined && candidate.exit_code !== null ? `exit ${candidate.exit_code}` : '',
      ].filter(Boolean).join(' · ');
      row.appendChild(meta);
      row.addEventListener('click', () => fetchAndRenderHistoryComparison(source.id, candidate.id));
      rows.appendChild(row);
    });
    headerBtn.addEventListener('click', () => {
      const nextCollapsed = !rows.hidden;
      rows.hidden = nextCollapsed;
      headerBtn.setAttribute('aria-expanded', nextCollapsed ? 'false' : 'true');
      if (nextCollapsed) _historyCompareState.manualCollapsedGroups.add(group.label);
      else _historyCompareState.manualCollapsedGroups.delete(group.label);
    });
    groupEl.appendChild(rows);
    list.appendChild(groupEl);
  });
  if (_historyCompareState.manualLoaded && (_historyCompareState.manualHasNext || _historyCompareState.manualLoading)) {
    const more = document.createElement('button');
    more.type = 'button';
    more.className = 'btn btn-secondary btn-compact history-compare-load-more';
    more.disabled = !!_historyCompareState.manualLoading;
    more.textContent = _historyCompareState.manualLoading ? 'Loading...' : 'Load More';
    more.addEventListener('click', () => {
      _fetchHistoryCompareManualCandidates(source, _historyCompareState.manualQuery, {
        requestId: _historyCompareState.manualRequestId,
        page: (_historyCompareState.manualPage || 1) + 1,
        append: true,
      });
    });
    list.appendChild(more);
  }
  if (searchWasFocused && typeof search.focus === 'function') {
    search.focus({ preventScroll: true });
  }
}

function openHistoryCompareLauncher(run) {
  if (!run || !run.id) return;
  _historyCompareState = {
    source: {
      ...run,
      command_root: (run.command || '').trim().split(/\s+/, 1)[0] || '',
    },
    candidates: [],
    manualCandidates: [],
    manualLoaded: false,
    manualRequestId: 0,
    manualPage: 1,
    manualHasNext: false,
    manualLoading: false,
    manualCollapsedGroups: new Set(),
    selected: null,
    manualQuery: '',
  };
  _openHistoryCompareOverlay();
  const body = document.querySelector('#history-compare-body');
  if (body) {
    body.replaceChildren();
    const loading = document.createElement('div');
    loading.className = 'history-compare-empty';
    loading.textContent = 'Finding comparable runs...';
    body.appendChild(loading);
  }
  apiFetch(`/history/${encodeURIComponent(run.id)}/compare-candidates`)
    .then(resp => resp.json())
    .then(data => {
      if (data.error) throw new Error(data.error);
      _historyCompareState.source = data.source || _historyCompareState.source;
      _historyCompareState.candidates = Array.isArray(data.candidates) ? data.candidates : [];
      _historyCompareState.selected = data.suggested || _historyCompareState.candidates[0] || null;
      _renderHistoryCompareLauncher();
      _loadHistoryCompareManualCandidates(_historyCompareState.source, '');
    })
    .catch(() => {
      _historyCompareState.candidates = [];
      _historyCompareState.selected = null;
      _renderHistoryCompareLauncher();
      showToast('Failed to load comparison choices', 'error');
    });
}

function _compareMetricCell(label, value, tone = '') {
  const cell = document.createElement('div');
  cell.className = `history-compare-metric${tone ? ` ${tone}` : ''}`;
  const labelEl = document.createElement('div');
  labelEl.className = 'history-compare-metric-label';
  labelEl.textContent = label;
  const valueEl = document.createElement('div');
  valueEl.className = 'history-compare-metric-value';
  valueEl.textContent = value;
  cell.appendChild(labelEl);
  cell.appendChild(valueEl);
  return cell;
}

function _renderHistoryCompareLines(title, lines, omitted, sign) {
  const section = document.createElement('details');
  section.className = 'history-compare-lines';
  section.open = true;
  const summary = document.createElement('summary');
  summary.textContent = `${title} (${lines.length}${omitted ? `+${omitted}` : ''})`;
  section.appendChild(summary);
  if (!lines.length) {
    const empty = document.createElement('div');
    empty.className = 'history-compare-empty';
    empty.textContent = `No ${title.toLowerCase()}.`;
    section.appendChild(empty);
    return section;
  }
  const list = document.createElement('div');
  list.className = 'history-compare-line-list';
  lines.forEach(line => {
    const row = document.createElement('div');
    row.className = 'history-compare-line';
    const mark = document.createElement('span');
    mark.className = sign === '+' ? 'history-compare-line-added' : 'history-compare-line-removed';
    mark.textContent = sign;
    row.appendChild(mark);
    const text = document.createElement('code');
    text.textContent = line.text || '';
    row.appendChild(text);
    list.appendChild(row);
  });
  section.appendChild(list);
  if (omitted) {
    const note = document.createElement('div');
    note.className = 'history-compare-truncation';
    note.textContent = `${omitted.toLocaleString()} additional changed line(s) omitted.`;
    section.appendChild(note);
  }
  return section;
}

function _appendHistoryCompareSegments(parent, segments, fallbackText) {
  const safeSegments = Array.isArray(segments) ? segments : [];
  if (!safeSegments.length) {
    parent.textContent = fallbackText || '';
    return;
  }
  safeSegments.forEach(segment => {
    const span = document.createElement('span');
    span.textContent = segment && typeof segment.text === 'string' ? segment.text : '';
    if (segment && segment.changed) span.className = 'history-compare-line-delta';
    parent.appendChild(span);
  });
}

function _renderHistoryCompareChangedLines(lines) {
  const section = document.createElement('details');
  section.className = 'history-compare-lines history-compare-changed-lines';
  section.open = true;
  const summary = document.createElement('summary');
  summary.textContent = `Changed lines (${lines.length})`;
  section.appendChild(summary);
  if (!lines.length) {
    const empty = document.createElement('div');
    empty.className = 'history-compare-empty';
    empty.textContent = 'No changed lines.';
    section.appendChild(empty);
    return section;
  }
  const list = document.createElement('div');
  list.className = 'history-compare-line-list history-compare-changed-list';
  lines.forEach(line => {
    const pair = document.createElement('div');
    pair.className = 'history-compare-changed-pair';

    const removed = line && line.removed ? line.removed : {};
    const added = line && line.added ? line.added : {};
    [
      { label: 'A', cls: 'history-compare-line-removed', line: removed },
      { label: 'B', cls: 'history-compare-line-added', line: added },
    ].forEach(item => {
      const row = document.createElement('div');
      row.className = 'history-compare-line';
      const mark = document.createElement('span');
      mark.className = item.cls;
      mark.textContent = item.label;
      row.appendChild(mark);
      const text = document.createElement('code');
      _appendHistoryCompareSegments(text, item.line.segments, item.line.text || '');
      row.appendChild(text);
      pair.appendChild(row);
    });

    list.appendChild(pair);
  });
  section.appendChild(list);
  return section;
}

function _historyCompareHasTabCapacity(count) {
  const maxTabs = Number((typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.max_tabs) || 0);
  if (!maxTabs || maxTabs <= 0 || typeof tabs === 'undefined' || !Array.isArray(tabs)) return true;
  return tabs.length + Number(count || 0) <= maxTabs;
}

function _restoreBothHistoryCompareRuns(left, right) {
  if (!left || !right) return Promise.reject(new Error('missing comparison runs'));
  if (!_historyCompareHasTabCapacity(2)) {
    showToast('Not enough tab capacity to restore both runs', 'error');
    return Promise.reject(new Error('not enough tab capacity'));
  }
  const leftTabId = createTab(`A: ${left.command || 'run'}`);
  if (!leftTabId) return Promise.reject(new Error('failed to create Run A tab'));
  const rightTabId = createTab(`B: ${right.command || 'run'}`);
  if (!rightTabId) return Promise.reject(new Error('failed to create Run B tab'));
  return Promise.all([
    restoreHistoryRunIntoTab(left, { targetTabId: leftTabId, hidePanelOnSuccess: false }),
    restoreHistoryRunIntoTab(right, { targetTabId: rightTabId, hidePanelOnSuccess: false }),
  ]).then(() => {
    if (typeof activateTab === 'function') activateTab(rightTabId, { focusComposer: false });
    return [leftTabId, rightTabId];
  });
}

function _renderHistoryComparison(data) {
  const overlay = _ensureHistoryCompareOverlay();
  const body = overlay.querySelector('#history-compare-body');
  const subtitle = overlay.querySelector('#history-compare-subtitle');
  if (!body) return;
  body.replaceChildren();
  subtitle.textContent = 'Changed output only';

  const runs = document.createElement('div');
  runs.className = 'history-compare-run-grid';
  runs.appendChild(_historyCompareRunCard(data.left, 'Run A'));
  runs.appendChild(_historyCompareRunCard(data.right, 'Run B'));
  body.appendChild(runs);

  const deltas = data.deltas || {};
  const metrics = document.createElement('div');
  metrics.className = 'history-compare-metrics';
  metrics.appendChild(_compareMetricCell('Exit', deltas.exit_code_changed ? `${deltas.exit_code.left} -> ${deltas.exit_code.right}` : `unchanged · ${deltas.exit_code?.right ?? 'n/a'}`, deltas.exit_code_changed ? 'is-changed' : ''));
  metrics.appendChild(_compareMetricCell('Duration', _compareFormatDelta((deltas.duration_seconds && deltas.duration_seconds.delta) || 0, 's')));
  metrics.appendChild(_compareMetricCell('Lines', _compareFormatDelta((deltas.output_lines && deltas.output_lines.delta) || 0)));
  metrics.appendChild(_compareMetricCell('Findings', _compareFormatDelta((deltas.findings && deltas.findings.delta) || 0)));
  body.appendChild(metrics);

  if (data.truncated && (data.truncated.left || data.truncated.right || data.truncated.changed_lines)) {
    const note = document.createElement('div');
    note.className = 'history-compare-truncation';
    note.textContent = 'Comparison is partial because one or both outputs were truncated or the changed-line list hit its display limit.';
    body.appendChild(note);
  }

  const actions = document.createElement('div');
  actions.className = 'history-compare-actions';
  const restoreA = document.createElement('button');
  restoreA.type = 'button';
  restoreA.className = 'btn btn-secondary btn-compact';
  restoreA.textContent = 'Restore A';
  restoreA.addEventListener('click', () => restoreHistoryRunIntoTab(data.left, { hidePanelOnSuccess: false }).then(() => closeHistoryCompareOverlay()).catch(() => showToast('Failed to restore run', 'error')));
  actions.appendChild(restoreA);
  const restoreB = document.createElement('button');
  restoreB.type = 'button';
  restoreB.className = 'btn btn-secondary btn-compact';
  restoreB.textContent = 'Restore B';
  restoreB.addEventListener('click', () => restoreHistoryRunIntoTab(data.right, { hidePanelOnSuccess: false }).then(() => closeHistoryCompareOverlay()).catch(() => showToast('Failed to restore run', 'error')));
  actions.appendChild(restoreB);
  const restoreBoth = document.createElement('button');
  restoreBoth.type = 'button';
  restoreBoth.className = 'btn btn-secondary btn-compact';
  restoreBoth.textContent = 'Restore Both';
  restoreBoth.addEventListener('click', () => {
    restoreBoth.disabled = true;
    _restoreBothHistoryCompareRuns(data.left, data.right)
      .then(() => closeHistoryCompareOverlay())
      .catch(err => {
        restoreBoth.disabled = false;
        if (err && err.message === 'not enough tab capacity') return;
        showToast('Failed to restore both runs', 'error');
      });
  });
  actions.appendChild(restoreBoth);
  const copy = document.createElement('button');
  copy.type = 'button';
  copy.className = 'btn btn-secondary btn-compact';
  copy.textContent = 'Copy summary';
  copy.addEventListener('click', () => {
    const summary = [
      `Compare: ${data.left.command} -> ${data.right.command}`,
      `Exit: ${deltas.exit_code?.left ?? 'n/a'} -> ${deltas.exit_code?.right ?? 'n/a'}`,
      `Lines: ${_compareFormatDelta(deltas.output_lines?.delta || 0)}`,
      `Findings: ${_compareFormatDelta(deltas.findings?.delta || 0)}`,
      `Changed: ${(data.sections?.changed || []).length}`,
      `Added: ${(data.sections?.added || []).length}`,
      `Removed: ${(data.sections?.removed || []).length}`,
    ].join('\n');
    copyTextToClipboard(summary)
      .then(() => showToast('Comparison summary copied'))
      .catch(() => showToast('Failed to copy summary', 'error'));
  });
  actions.appendChild(copy);
  body.appendChild(actions);

  const sections = data.sections || {};
  const changedLines = sections.changed || [];
  const addedLines = sections.added || [];
  const removedLines = sections.removed || [];
  const addedOmitted = sections.added_omitted || 0;
  const removedOmitted = sections.removed_omitted || 0;
  if (changedLines.length) {
    body.appendChild(_renderHistoryCompareChangedLines(changedLines));
  }
  if (addedLines.length || addedOmitted) {
    body.appendChild(_renderHistoryCompareLines('Added lines', addedLines, addedOmitted, '+'));
  }
  if (removedLines.length || removedOmitted) {
    body.appendChild(_renderHistoryCompareLines('Removed lines', removedLines, removedOmitted, '-'));
  }
  if (!changedLines.length && !addedLines.length && !removedLines.length && !addedOmitted && !removedOmitted) {
    const empty = document.createElement('div');
    empty.className = 'history-compare-empty';
    empty.textContent = 'No changed output.';
    body.appendChild(empty);
  }
}

function fetchAndRenderHistoryComparison(leftId, rightId) {
  if (!leftId || !rightId) return;
  const body = document.querySelector('#history-compare-body');
  if (body) {
    body.replaceChildren();
    const loading = document.createElement('div');
    loading.className = 'history-compare-empty';
    loading.textContent = 'Comparing runs...';
    body.appendChild(loading);
  }
  apiFetch(`/history/compare?left=${encodeURIComponent(leftId)}&right=${encodeURIComponent(rightId)}`)
    .then(resp => resp.json())
    .then(data => {
      if (data.error) throw new Error(data.error);
      _renderHistoryComparison(data);
    })
    .catch(() => {
      _renderHistoryCompareLauncher();
      showToast('Failed to compare runs', 'error');
    });
}


// ── Run history panel ──
let pendingHistAction = null;

function confirmHistAction(type, id, command, itemType = 'run') {
  pendingHistAction = { type, id, command, itemType };
  const isBulk = type === 'clear';
  const body = isBulk
    ? { text: 'Delete all runs and snapshots?', note: 'This cannot be undone.' }
    : itemType === 'snapshot'
      ? { text: 'Remove this snapshot from history?', note: 'This cannot be undone.' }
      : { text: 'Remove this run from history?', note: 'This cannot be undone.' };
  const actions = isBulk
    ? [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'nonfav', label: 'Delete Non-Favorites', role: 'secondary', tone: 'warning' },
        { id: 'all',    label: 'Delete all', role: 'destructive', tone: 'warning' },
      ]
    : [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'one',    label: 'Delete', role: 'destructive', tone: 'warning' },
      ];
  showConfirm({ body, tone: 'warning', actions }).then((choice) => {
    if (!choice || choice === 'cancel') {
      pendingHistAction = null;
      return;
    }
    if (choice === 'nonfav') executeHistAction('clear-nonfav');
    else if (choice === 'all') executeHistAction();
    else if (choice === 'one') executeHistAction('delete');
  });
}

function executeHistAction(type) {
  const action  = type || (pendingHistAction && pendingHistAction.type);
  const id      = pendingHistAction && pendingHistAction.id;
  const command = pendingHistAction && pendingHistAction.command;
  const itemType = pendingHistAction && pendingHistAction.itemType;
  pendingHistAction = null;
  if (action === 'delete') {
    const deleteUrl = itemType === 'snapshot' ? `/share/${id}` : `/history/${id}`;
    apiFetch(deleteUrl, { method: 'DELETE' }).then(() => {
      if (itemType === 'snapshot') {
        refreshHistoryPanel();
        return;
      }
      // Remove from starred set and chips — deleted history should not stay pinned
      const s = _getStarred();
      if (s.has(command)) {
        s.delete(command);
        _saveStarred(s);
        apiFetch('/session/starred', {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ command }),
        }).catch(() => {});
      }
      cmdHistory = cmdHistory.filter(c => c !== command);
      recentPreviewHistory = recentPreviewHistory.filter(c => c !== command);
      renderHistory();
      refreshHistoryPanel();
    }).catch(() => showToast('Failed to delete run'));
  } else if (action === 'clear-nonfav') {
    apiFetch('/history?type=runs')
      .then(r => r.json())
      .then(data => {
        const starred   = _getStarred();
        const toDelete  = data.runs.filter(r => !starred.has(r.command));
        const deleteCmds = new Set(toDelete.map(r => r.command));
        // Remove deleted commands from chips; starred commands remain
        cmdHistory = cmdHistory.filter(c => !deleteCmds.has(c));
        recentPreviewHistory = recentPreviewHistory.filter(c => !deleteCmds.has(c));
        renderHistory();
        return Promise.all(toDelete.map(r => apiFetch(`/history/${r.id}`, { method: 'DELETE' })));
      })
      .then(() => refreshHistoryPanel())
      .catch(() => showToast('Failed to clear history'));
  } else {
    apiFetch('/history', { method: 'DELETE' }).then(() => {
      // Wipe all starred state and chips — nothing left in history to pin
      _saveStarred(new Set());
      apiFetch('/session/starred', { method: 'DELETE' }).catch(() => {});
      cmdHistory = [];
      recentPreviewHistory = [];
      renderHistory();
      refreshHistoryPanel();
    }).catch(() => showToast('Failed to clear history'));
  }
}

function _setHistoryLoadState(loading) {
  if (!historyLoadOverlay) return;
  if (loading) showHistoryLoadOverlay();
  else hideHistoryLoadOverlay();
}

function _historyRunIdentity(run) {
  return String(run?.id || run?.run_id || '').trim();
}

function _tabForHistoryRun(run) {
  const runId = _historyRunIdentity(run);
  if (!runId) return null;
  return tabs.find(t => (
    t && (String(t.historyRunId || '') === runId || String(t.runId || '') === runId)
  )) || null;
}

function restoreHistoryRunIntoTab(run, { targetTabId = null, hidePanelOnSuccess = true } = {}) {
  if (!run || !run.id) return Promise.reject(new Error('missing run id'));
  const existing = targetTabId ? getTab(targetTabId) : _tabForHistoryRun(run);
  const canUpgradeExisting = !!(existing && run.full_output_available && existing.previewTruncated);
  const restoreUrl = run.full_output_available
    ? `/history/${run.id}?json`
    : `/history/${run.id}?json&preview=1`;

  return apiFetch(restoreUrl)
    .then(r => r.json())
    .then(fullRun => {
      const previewNotice = fullRun.preview_notice || null;
      const tabId = targetTabId || (canUpgradeExisting ? existing.id : createTab(fullRun.command));
      if (!tabId) throw new Error('failed to create restore tab');
      if (typeof clearTab === 'function') clearTab(tabId);
      const t = getTab(tabId);
      if (t) {
        t.command = fullRun.command;
        t.runId = null;
        t.historyRunId = fullRun.id || run.id;
        t.exitCode = fullRun.exit_code;
        t.previewTruncated = !!previewNotice;
        t.fullOutputAvailable = !!fullRun.full_output_available;
        t.fullOutputLoaded = !!fullRun.full_output_available && !previewNotice;
        t.reconnectedRun = false;
      }
      _appendHistoryCommandEcho(tabId, fullRun.command);
      const outputLines = Array.isArray(fullRun.output_entries) ? fullRun.output_entries : (fullRun.output || []);
      outputLines.forEach(line => _appendHistoryOutputLine(line, tabId));
      if (previewNotice) appendLine(previewNotice, 'notice', tabId);
      appendLine(
        `[history — ${_historyExitLabel(fullRun.exit_code)}]`,
        _historyExitClass(fullRun.exit_code),
        tabId
      );
      if (typeof setTabStatus === 'function') {
        setTabStatus(tabId, fullRun.exit_code === 0 ? 'ok' : 'fail');
      }
      if (typeof hideTabKillBtn === 'function') hideTabKillBtn(tabId);
      if (hidePanelOnSuccess) hideHistoryPanel();
      return tabId;
    });
}

function restoreHistoryRun(runOrId, options = {}) {
  const run = typeof runOrId === 'object' && runOrId !== null
    ? runOrId
    : { id: String(runOrId || ''), full_output_available: true };
  return restoreHistoryRunIntoTab(run, {
    hidePanelOnSuccess: false,
    ...options,
  });
}

window.openHistoryWithFilters = openHistoryWithFilters;
window.restoreHistoryRun = restoreHistoryRun;

function refreshHistoryPanel() {
  // The panel is populated on demand so we always fetch the latest persisted
  // history instead of assuming the in-memory tab state is authoritative.
  _syncHistoryFilterControls();
  _renderHistoryActiveFilters();
  apiFetch(_buildHistoryRequestUrl()).then(r => r.json()).then(data => {
    historyList.replaceChildren();
    _historyPaging.page = Math.max(1, Number(data.page) || _historyPaging.page || 1);
    _historyPaging.pageSize = Math.max(1, Number(data.page_size) || _historyPaging.pageSize || 1);
    _historyPaging.totalCount = Math.max(0, Number(data.total_count ?? data.items?.length ?? data.runs?.length ?? 0) || 0);
    _historyPaging.pageCount = Math.max(0, Number(data.page_count) || 0);
    _historyPaging.hasPrev = !!data.has_prev;
    _historyPaging.hasNext = !!data.has_next;
    const visibleItems = _applyHistoryClientFilters(Array.isArray(data.items) ? data.items : data.runs);
    _renderHistoryRootSuggestions(_historyFilters.type === 'snapshots' ? [] : (Array.isArray(data.roots) ? data.roots : data.runs));
    if (!visibleItems.length) {
      _historyRenderPagination(0);
      _renderHistoryEmptyState();
      if (typeof emitUiEvent === 'function') {
        emitUiEvent('app:history-panel-refreshed', {
          items: [],
          runs: [],
          roots: Array.isArray(data.roots) ? data.roots.slice() : [],
          paging: { ..._historyPaging },
          filters: { ..._historyFilters },
        });
      }
      return;
    }

    const starred = _getStarred();
    visibleItems.forEach(item => {
      if (item.type === 'snapshot') {
        const entry = _createSnapshotHistoryEntry(item);
        entry.addEventListener('click', e => {
          if (e.target.closest('[data-action]')) return;
          openSnapshotLink(item);
          hideHistoryPanel();
        });

        bindPressable(entry.querySelector('[data-action="open"]'), {
          onActivate: () => {
            openSnapshotLink(item);
            hideHistoryPanel();
          },
        });
        bindPressable(entry.querySelector('[data-action="link"]'), {
          onActivate: () => {
            shareUrl(_snapshotUrl(item)).catch(() => showToast('Failed to copy link', 'error'));
            if (!_historyActionKeepsPanelOpen('permalink')) hideHistoryPanel();
          },
        });
        bindPressable(entry.querySelector('[data-action="delete"]'), {
          onActivate: () => {
            confirmHistAction('delete', item.id, item.label || 'snapshot', 'snapshot');
          },
        });
        historyList.appendChild(entry);
        return;
      }

      const run = item;
      const isStarred = starred.has(run.command);
      const entry = _createHistoryEntry(run, isStarred);

      // Click anywhere on the entry (except buttons) to load the command into
      // the composer for re-run. Full tab-restore is available via the
      // dedicated `restore` action button.
      entry.addEventListener('click', e => {
        if (e.target.closest('[data-action]')) return;
        const cmd = run.command || '';
        if (typeof setComposerValue === 'function') {
          setComposerValue(cmd, cmd.length, cmd.length);
        }
        hideHistoryPanel();
        if (typeof refocusComposerAfterAction === 'function') {
          refocusComposerAfterAction({ preventScroll: true });
        }
        resetCmdHistoryNav();
      });

      bindPressable(entry.querySelector('[data-action="star"]'), {
        onActivate: () => {
          const wasStarred = _getStarred().has(run.command);
          _toggleStar(run.command);
          if (!wasStarred && !cmdHistory.includes(run.command)) {
            cmdHistory = [run.command, ...cmdHistory].slice(0, APP_CONFIG.recent_commands_limit);
          }
          if (!_historyActionKeepsPanelOpen('star')) hideHistoryPanel();
          refreshHistoryPanel();
          renderHistory();
        },
      });

      bindPressable(entry.querySelector('[data-action="restore"]'), {
        onActivate: () => {
          const existing = _tabForHistoryRun(run);
          const canUpgradeExisting = !!(existing && run.full_output_available && existing.previewTruncated);
          if (existing && !canUpgradeExisting) {
            activateTab(existing.id);
            hideHistoryPanel();
            return;
          }
          const cmdEl = entry.querySelector('.history-entry-cmd');
          cmdEl.textContent = 'loading…';
          _setHistoryLoadState(true);
          restoreHistoryRunIntoTab(run, {
            targetTabId: canUpgradeExisting ? existing.id : null,
            hidePanelOnSuccess: true,
          })
            .catch(() => {
              entry.querySelector('.history-entry-cmd').textContent = run.command;
              showToast('Failed to load run');
            })
            .finally(() => _setHistoryLoadState(false));
        },
      });

      bindPressable(entry.querySelector('[data-action="permalink"]'), {
        onActivate: () => {
          const url = `${location.origin}/history/${run.id}`;
          shareUrl(url).catch(() => showToast('Failed to copy link', 'error'));
          if (!_historyActionKeepsPanelOpen('permalink')) hideHistoryPanel();
        },
      });
      bindPressable(entry.querySelector('[data-action="compare"]'), {
        refocusComposer: false,
        onActivate: () => {
          openHistoryCompareLauncher(run);
          if (!_historyActionKeepsPanelOpen('compare')) hideHistoryPanel();
        },
      });
      bindPressable(entry.querySelector('[data-action="delete"]'), {
        onActivate: () => {
          confirmHistAction('delete', run.id, run.command);
        },
      });

      historyList.appendChild(entry);
    });
    _historyRenderPagination(visibleItems.length);
    if (typeof emitUiEvent === 'function') {
      emitUiEvent('app:history-panel-refreshed', {
        items: visibleItems.slice(),
        runs: visibleItems.filter(item => item.type === 'run').slice(),
        roots: Array.isArray(data.roots) ? data.roots.slice() : [],
        paging: { ..._historyPaging },
        filters: { ..._historyFilters },
      });
    }
  });
}

if (typeof historySearchInput !== 'undefined' && historySearchInput) {
  historySearchInput.addEventListener('input', e => {
    _setHistoryFilter('q', e.target.value, { debounce: true });
  });
}

if (typeof historyMobileFiltersToggle !== 'undefined' && historyMobileFiltersToggle) {
  historyMobileFiltersToggle.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    toggleHistoryMobileFilters();
  });
}

if (typeof historyRootInput !== 'undefined' && historyRootInput) {
  historyRootInput.addEventListener('input', e => {
    if (_historyRootSuppressInputOnce) {
      _historyRootSuppressInputOnce = false;
      return;
    }
    _historyRootIndex = -1;
    _historyRefreshRootDropdown();
    _setHistoryFilter('commandRoot', e.target.value, { debounce: true });
  });
  historyRootInput.addEventListener('focus', () => {
    _historyRootInputFocused = true;
    _historyRootIndex = -1;
    _historyRefreshRootDropdown();
  });
  historyRootInput.addEventListener('blur', () => {
    setTimeout(() => {
      _historyRootInputFocused = false;
      _hideHistoryRootDropdown();
    }, 0);
  });
  historyRootInput.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      e.preventDefault();
      _hideHistoryRootDropdown();
      return;
    }
    if (e.key === 'ArrowDown') {
      if (!_historyRootFiltered.length) return;
      e.preventDefault();
      _historyRootIndex = (_historyRootIndex + 1) % _historyRootFiltered.length;
      _renderHistoryRootDropdown(_historyRootFiltered, historyRootInput.value);
      return;
    }
    if (e.key === 'ArrowUp') {
      if (!_historyRootFiltered.length) return;
      e.preventDefault();
      _historyRootIndex = _historyRootIndex <= 0 ? _historyRootFiltered.length - 1 : _historyRootIndex - 1;
      _renderHistoryRootDropdown(_historyRootFiltered, historyRootInput.value);
      return;
    }
    if (e.key === 'Enter' && _historyRootIndex >= 0 && _historyRootFiltered[_historyRootIndex]) {
      e.preventDefault();
      _acceptHistoryRootSuggestion(_historyRootFiltered[_historyRootIndex]);
    }
  });
}

if (typeof historyTypeFilter !== 'undefined' && historyTypeFilter) {
  historyTypeFilter.addEventListener('change', e => {
    _setHistoryFilter('type', e.target.value);
  });
}

if (typeof historyExitFilter !== 'undefined' && historyExitFilter) {
  historyExitFilter.addEventListener('change', e => {
    _setHistoryFilter('exitCode', e.target.value);
  });
}

if (typeof historyDateFilter !== 'undefined' && historyDateFilter) {
  historyDateFilter.addEventListener('change', e => {
    _setHistoryFilter('dateRange', e.target.value);
  });
}

if (typeof historyStarredToggle !== 'undefined' && historyStarredToggle) {
  historyStarredToggle.addEventListener('change', e => {
    _setHistoryFilter('starredOnly', e.target.checked);
  });
}

if (typeof historyClearFiltersBtn !== 'undefined' && historyClearFiltersBtn) {
  historyClearFiltersBtn.addEventListener('click', () => clearHistoryFilters());
}

_syncHistoryFilterControls();


// ── Ctrl+R reverse-history search ──

let _histSearchMode = false;
let _histSearchQuery = '';
let _histSearchIndex = -1;
let _histSearchPreDraft = '';
let _histSearchRuns = null;     // null = not yet fetched; string[] = ready
let _histSearchFetchTimer = null;

function isHistSearchMode() { return _histSearchMode; }

function _histSearchMatches() {
  if (!_histSearchQuery) return [];
  // Always include client-side matches from the in-memory recents so the
  // dropdown can't "clear" on the user when a server fetch returns fewer
  // items (or is stale from a prior keystroke). This mirrors bash reverse-
  // i-search, which searches in-memory history. Server results extend this
  // list with older runs beyond the recents cap; both lists are re-filtered
  // against the current query to guard against race conditions.
  const q = _histSearchQuery.toLowerCase();
  const fromClient = cmdHistory.filter(c => c.toLowerCase().includes(q));
  const seen = new Set();
  const merged = [];
  for (const cmd of fromClient) {
    if (!seen.has(cmd)) { merged.push(cmd); seen.add(cmd); }
  }
  if (_histSearchRuns !== null) {
    for (const cmd of _histSearchRuns) {
      if (!seen.has(cmd) && cmd.toLowerCase().includes(q)) {
        merged.push(cmd);
        seen.add(cmd);
      }
    }
  }
  return merged.slice(0, 10);
}

// Fetch /history?q=<query> from the server (same endpoint as the drawer).
// The query filter is applied server-side before LIMIT, so searches match
// the full history — not just the most-recent-N unfiltered runs.
// scope=command keeps this bash-like: match typed command text only, not
// output text (which FTS would otherwise mix in and surface unrelated runs).
function _histSearchFetch(q) {
  const url = q
    ? `/history?type=runs&q=${encodeURIComponent(q)}&scope=command`
    : '/history?type=runs&scope=command';
  apiFetch(url).then(r => r.json()).then(data => {
    if (!_histSearchMode) return;
    _histSearchRuns = Array.isArray(data.runs)
      ? [...new Set(data.runs.map(r => r.command))]
      : [];
    _histSearchIndex = _histSearchRuns.length > 0 ? 0 : -1;
    _renderHistSearch();
  }).catch(() => {
    if (_histSearchRuns === null) _histSearchRuns = [];
  });
}

function _hideHistSearchDropdown() {
  if (histSearchDropdown) histSearchDropdown.classList.add('u-hidden');
}

function _moveHistSearchSelection(delta) {
  const matches = _histSearchMatches();
  if (!matches.length) return false;
  if (_histSearchIndex < 0) {
    _histSearchIndex = delta < 0 ? matches.length - 1 : 0;
  } else {
    _histSearchIndex = (_histSearchIndex + delta + matches.length) % matches.length;
  }
  _renderHistSearch();
  return true;
}

function _renderHistSearch() {
  // Reverse-i-search intentionally mirrors shell behavior: current query at the
  // top, most relevant match preselected, and wraparound keyboard navigation.
  if (!histSearchDropdown) return;
  const matches = _histSearchMatches();
  histSearchDropdown.replaceChildren();

  const header = document.createElement('div');
  header.className = 'hist-search-header';
  const label = document.createElement('span');
  label.className = 'hist-search-label';
  label.textContent = 'reverse-i-search: ';
  const querySpan = document.createElement('span');
  querySpan.className = 'hist-search-query';
  querySpan.textContent = _histSearchQuery || '';
  header.appendChild(label);
  header.appendChild(querySpan);
  histSearchDropdown.appendChild(header);

  if (!matches.length) {
    const empty = document.createElement('div');
    empty.className = 'hist-search-empty';
    empty.textContent = '(no matches)';
    histSearchDropdown.appendChild(empty);
  } else {
    matches.forEach((cmd, i) => {
      const item = document.createElement('div');
      item.className = 'hist-search-item dropdown-item dropdown-item-compact'
        + (i === _histSearchIndex ? ' active dropdown-item-active' : '');
      if (_histSearchQuery) {
        const lower = cmd.toLowerCase();
        const qi = lower.indexOf(_histSearchQuery.toLowerCase());
        if (qi >= 0) {
          item.appendChild(document.createTextNode(cmd.slice(0, qi)));
          const mark = document.createElement('mark');
          mark.className = 'hist-search-match';
          mark.textContent = cmd.slice(qi, qi + _histSearchQuery.length);
          item.appendChild(mark);
          item.appendChild(document.createTextNode(cmd.slice(qi + _histSearchQuery.length)));
        } else {
          item.textContent = cmd;
        }
      } else {
        item.textContent = cmd;
      }
      item.addEventListener('mousedown', e => {
        e.preventDefault();
        _histSearchIndex = i;
        exitHistSearch(true);
      });
      histSearchDropdown.appendChild(item);
    });
  }

  // Flip above/below based on available space, mirroring the ac-dropdown so
  // the list stays on-screen when the prompt is near the top of the viewport.
  histSearchDropdown.classList.remove('u-hidden');
  if (shellPromptWrap) {
    const rect = shellPromptWrap.getBoundingClientRect();
    histSearchDropdown.style.position = 'fixed';
    histSearchDropdown.style.left = rect.left + 'px';
    histSearchDropdown.style.width = rect.width + 'px';
    histSearchDropdown.style.bottom = 'auto';
    histSearchDropdown.style.maxHeight = '';
    const desired = histSearchDropdown.offsetHeight;
    const spaceBelow = Math.max(0, window.innerHeight - rect.bottom - 8);
    const spaceAbove = Math.max(0, rect.top - 8);
    const safetyPad = 20;
    const canFitBelow = spaceBelow >= (desired + safetyPad);
    const canFitAbove = spaceAbove >= (desired + safetyPad);
    const showAbove = canFitAbove && (!canFitBelow || spaceAbove >= spaceBelow);
    const available = showAbove ? spaceAbove : spaceBelow;
    const edgeBuffer = showAbove ? 20 : 30;
    const maxHeight = Math.max(0, available > edgeBuffer ? available - edgeBuffer : available);
    const visibleHeight = Math.max(0, Math.min(desired, maxHeight || desired));
    histSearchDropdown.style.maxHeight = `${Math.round(maxHeight)}px`;
    histSearchDropdown.style.top = showAbove
      ? `${Math.max(8, Math.round(rect.top - visibleHeight - 4))}px`
      : `${Math.max(8, Math.round(rect.bottom + 4))}px`;
  }
}

function enterHistSearch() {
  if (_histSearchMode) {
    // Ctrl+R again: cycle to next match
    _moveHistSearchSelection(1);
    return;
  }
  _histSearchMode = true;
  _histSearchQuery = '';
  _histSearchIndex = -1;
  _histSearchPreDraft = (typeof getComposerValue === 'function') ? getComposerValue() : (cmdInput ? cmdInput.value : '');
  // Clear the input so the user types a fresh query rather than appending to the draft.
  // The draft is preserved in _histSearchPreDraft and restored on Escape / Ctrl+G.
  if (typeof setComposerValue === 'function') {
    setComposerValue('', 0, 0, { dispatch: false });
  }
  if (typeof acHide === 'function') acHide();

  _histSearchRuns = null;
  _renderHistSearch();
}

function exitHistSearch(accept, { keepCurrent = false } = {}) {
  if (!_histSearchMode) return;
  _histSearchMode = false;
  _hideHistSearchDropdown();
  if (accept) {
    const matches = _histSearchMatches();
    const chosen = _histSearchIndex >= 0 ? matches[_histSearchIndex] : (matches[0] || _histSearchPreDraft);
    if (typeof setComposerValue === 'function') {
      setComposerValue(chosen, chosen.length, chosen.length);
    }
  } else if (!keepCurrent) {
    if (typeof setComposerValue === 'function') {
      setComposerValue(_histSearchPreDraft, _histSearchPreDraft.length, _histSearchPreDraft.length);
    }
  }
  _histSearchQuery = '';
  _histSearchIndex = -1;
  _histSearchPreDraft = '';
  _histSearchRuns = null;
  if (_histSearchFetchTimer) { clearTimeout(_histSearchFetchTimer); _histSearchFetchTimer = null; }
  if (typeof acHide === 'function') acHide();
}

function handleHistSearchInput(value) {
  _histSearchQuery = value;
  _histSearchIndex = -1;
  if (_histSearchFetchTimer) { clearTimeout(_histSearchFetchTimer); _histSearchFetchTimer = null; }
  if (!value) {
    _histSearchRuns = null;
    _renderHistSearch();
    return;
  }
  // Initialise index from the current pool (cmdHistory fallback or previous fetch results)
  // so keyboard navigation works immediately while the server fetch is in-flight.
  const matches = _histSearchMatches();
  if (matches.length > 0) _histSearchIndex = 0;
  _renderHistSearch();
  // Re-fetch with the new query so the server applies the filter before LIMIT.
  _histSearchFetchTimer = setTimeout(() => {
    _histSearchFetchTimer = null;
    _histSearchFetch(value);
  }, 120);
}

function handleHistSearchKey(e) {
  if (!_histSearchMode) return false;
  if (e.key === 'Escape') {
    e.preventDefault();
    exitHistSearch(false);
    return true;
  }
  if (e.key === 'Enter') {
    e.preventDefault();
    // Accept the selected match (if any) into the prompt without running it,
    // matching the autocomplete menu's Enter behavior.
    if (_histSearchIndex >= 0) {
      exitHistSearch(true);
    } else {
      exitHistSearch(false, { keepCurrent: true });
    }
    return true;
  }
  if (e.key === 'Tab' && !e.altKey && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    _moveHistSearchSelection(e.shiftKey ? -1 : 1);
    return true;
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    _moveHistSearchSelection(1);
    return true;
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    _moveHistSearchSelection(-1);
    return true;
  }
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'r' || e.key === 'R')) {
    e.preventDefault();
    enterHistSearch(); // cycle
    return true;
  }
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'g' || e.key === 'G')) {
    e.preventDefault();
    exitHistSearch(false);
    return true;
  }
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'c' || e.key === 'C')) {
    e.preventDefault();
    exitHistSearch(false, { keepCurrent: true });
    return true;
  }
  // Let printable characters and backspace fall through to the input event
  return false;
}
