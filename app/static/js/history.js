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
  projectId: 'all',
  starredOnly: false,
};
let _historyMobileAdvancedOpen = false;
let _historyProjectOptions = [];
let _historyProjectOptionsLoaded = false;
let _historyProjectOptionsLoading = null;
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
let _historyRunModalState = {
  run: null,
  details: null,
  findings: null,
  projectState: null,
  activeTab: 'summary',
  loadingDetails: false,
  loadingFindings: false,
  loadingProject: false,
  error: '',
};
let _historyRunModalToken = 0;

function _closeHistoryActionMenus(except = null) {
  document.querySelectorAll('.history-action-menu-wrap.open').forEach((wrap) => {
    if (except && wrap === except) return;
    wrap.classList.remove('open');
    wrap.querySelector('[data-action="history-menu"]')?.setAttribute('aria-expanded', 'false');
    _resetHistoryActionMenuPosition(wrap);
  });
}

function _closeHistoryRunActionMenus(except = null) {
  document.querySelectorAll('.history-run-action-menu-wrap.open').forEach((wrap) => {
    if (except && wrap === except) return;
    wrap.classList.remove('open');
    wrap.querySelector('.history-run-action-menu-trigger')?.setAttribute('aria-expanded', 'false');
  });
}

function _resetHistoryActionMenuPosition(wrap) {
  const menu = wrap?.querySelector?.('.history-action-menu');
  if (!menu) return;
  menu.style.position = '';
  menu.style.left = '';
  menu.style.top = '';
  menu.style.right = '';
  menu.style.bottom = '';
}

function _positionHistoryActionMenu(wrap) {
  const trigger = wrap?.querySelector?.('[data-action="history-menu"]');
  const menu = wrap?.querySelector?.('.history-action-menu');
  if (!trigger || !menu || typeof trigger.getBoundingClientRect !== 'function') return;
  const triggerRect = trigger.getBoundingClientRect();
  const menuWidth = Math.max(180, menu.offsetWidth || 180);
  const menuHeight = Math.max(1, menu.offsetHeight || 1);
  const viewportWidth = typeof window !== 'undefined' ? window.innerWidth : document.documentElement.clientWidth;
  const viewportHeight = typeof window !== 'undefined' ? window.innerHeight : document.documentElement.clientHeight;
  const gutter = 8;
  const preferredLeft = triggerRect.left;
  const left = Math.min(
    Math.max(gutter, preferredLeft),
    Math.max(gutter, viewportWidth - menuWidth - gutter),
  );
  const belowTop = triggerRect.bottom + 4;
  const aboveTop = triggerRect.top - menuHeight - 4;
  const top = belowTop + menuHeight <= viewportHeight - gutter
    ? belowTop
    : Math.max(gutter, aboveTop);
  menu.style.position = 'fixed';
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
  menu.style.right = 'auto';
  menu.style.bottom = 'auto';
}
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
let _historyCompareRowPairSequence = 0;
let _historyCompareUnitSequence = 0;
let _historyCompareRowHeightFrame = null;
let _historyCompareRowResizeObserver = null;

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
  _syncHistoryProjectFilterOptions();
  if (typeof historyStarredToggle !== 'undefined' && historyStarredToggle) historyStarredToggle.checked = !!_historyFilters.starredOnly;
  const runOnlyEnabled = _historyFilters.type !== 'snapshots';
  if (typeof historyRootInput !== 'undefined' && historyRootInput) historyRootInput.disabled = !runOnlyEnabled;
  if (typeof historyExitFilter !== 'undefined' && historyExitFilter) historyExitFilter.disabled = !runOnlyEnabled;
  if (typeof historyStarredToggle !== 'undefined' && historyStarredToggle) historyStarredToggle.disabled = !runOnlyEnabled;
  if (typeof syncAppSelect === 'function') {
    if (typeof historyTypeFilter !== 'undefined') syncAppSelect(historyTypeFilter);
    if (typeof historyExitFilter !== 'undefined') syncAppSelect(historyExitFilter);
    if (typeof historyDateFilter !== 'undefined') syncAppSelect(historyDateFilter);
    if (typeof historyProjectFilter !== 'undefined') syncAppSelect(historyProjectFilter);
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
  if (Number.isInteger(entry.line_number)) metadata.line_number = entry.line_number;
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
  return _historyCore.activeFilterItems({
    ..._historyFilters,
    projectLabel: _historyProjectLabelForId(_historyFilters.projectId),
  });
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
    projectId: _normalizeHistoryFilterValue(nextFilters.projectId) || 'all',
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
    projectId: 'all',
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

function _historyEntityLabelValues(entity) {
  const labels = entity && Array.isArray(entity.labels) ? entity.labels : [];
  return labels
    .map(label => String(label && typeof label === 'object' ? label.label : label || '').trim())
    .filter(Boolean);
}

function _historyEntityNoteBody(entity) {
  const note = entity && entity.note && typeof entity.note === 'object' ? entity.note : null;
  return note ? String(note.body || '').trim() : '';
}

function _appendHistoryMetadataBadges(parent, entity) {
  if (!parent) return;
  const labels = _historyEntityLabelValues(entity);
  const visibleLabels = labels.slice(0, 3);
  visibleLabels.forEach((label) => {
    const badge = document.createElement('span');
    badge.className = 'history-entry-label-badge badge badge-tone-muted';
    badge.textContent = label;
    badge.title = `label: ${label}`;
    parent.appendChild(badge);
  });
  if (labels.length > visibleLabels.length) {
    const overflow = document.createElement('span');
    overflow.className = 'history-entry-label-badge badge badge-tone-muted';
    overflow.textContent = `+${labels.length - visibleLabels.length}`;
    overflow.title = `${labels.length - visibleLabels.length} more labels`;
    parent.appendChild(overflow);
  }
  if (_historyEntityNoteBody(entity)) {
    const note = document.createElement('span');
    note.className = 'history-entry-note-badge badge badge-tone-cyan';
    note.textContent = 'note';
    note.title = 'note saved';
    parent.appendChild(note);
  }
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

function _historyProjectDisplayName(project) {
  if (!project || typeof project !== 'object') return '';
  return String(project.name || project.slug || project.id || '').trim();
}

function _historyProjectLabelForId(projectId) {
  const normalized = _normalizeHistoryFilterValue(projectId);
  if (!normalized || normalized === 'all') return '';
  const project = _historyProjectOptions.find(item => String(item && item.id || '') === normalized);
  return _historyProjectDisplayName(project) || normalized;
}

function _syncHistoryProjectFilterOptions() {
  if (typeof historyProjectFilter === 'undefined' || !historyProjectFilter) return;
  const selected = _normalizeHistoryFilterValue(_historyFilters.projectId) || 'all';
  historyProjectFilter.replaceChildren();
  const allOption = document.createElement('option');
  allOption.value = 'all';
  allOption.textContent = 'project: all';
  historyProjectFilter.appendChild(allOption);
  _historyProjectOptions.forEach((project) => {
    const projectId = String(project && project.id || '');
    if (!projectId) return;
    const option = document.createElement('option');
    option.value = projectId;
    option.textContent = `project: ${_historyProjectDisplayName(project) || projectId}`;
    historyProjectFilter.appendChild(option);
  });
  if (selected !== 'all' && !_historyProjectOptions.some(project => String(project && project.id || '') === selected)) {
    const stale = document.createElement('option');
    stale.value = selected;
    stale.textContent = `project: ${selected}`;
    historyProjectFilter.appendChild(stale);
  }
  historyProjectFilter.value = selected;
  if (typeof syncAppSelect === 'function') syncAppSelect(historyProjectFilter);
}

function _ensureHistoryProjectFilterOptions() {
  if (_historyProjectOptionsLoaded) return Promise.resolve(_historyProjectOptions);
  if (_historyProjectOptionsLoading) return _historyProjectOptionsLoading;
  _historyProjectOptionsLoading = apiFetch('/projects?include_archived=1', { cache: 'no-store' })
    .then((resp) => {
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return resp.json();
    })
    .then((data) => {
      _historyProjectOptions = (Array.isArray(data.projects) ? data.projects : [])
        .filter(project => project && project.id)
        .sort((a, b) => _historyProjectDisplayName(a).localeCompare(
          _historyProjectDisplayName(b),
          undefined,
          { sensitivity: 'base', numeric: true },
        ));
      _historyProjectOptionsLoaded = true;
      _syncHistoryProjectFilterOptions();
      return _historyProjectOptions;
    })
    .catch((err) => {
      if (typeof logClientError === 'function') logClientError('failed to load /projects for history filter', err);
      return _historyProjectOptions;
    })
    .finally(() => {
      _historyProjectOptionsLoading = null;
    });
  return _historyProjectOptionsLoading;
}

async function _historyLoadActiveProject() {
  if (typeof getActiveProjectContext === 'function') {
    const current = getActiveProjectContext();
    if (current && current.id) return current;
  }
  if (typeof refreshActiveProjectContext === 'function') {
    try {
      const refreshed = await refreshActiveProjectContext();
      if (refreshed && refreshed.id) return refreshed;
    } catch (_) {}
  }
  try {
    const resp = await apiFetch('/projects/active', { cache: 'no-store' });
    if (!resp.ok) return null;
    const data = await resp.json();
    return data && data.project && data.project.id ? data.project : null;
  } catch (_) {
    return null;
  }
}

async function _historyLoadProjects() {
  const resp = await apiFetch('/projects', { cache: 'no-store' });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  return (Array.isArray(data.projects) ? data.projects : [])
    .filter(project => project && project.id && project.status !== 'archived')
    .sort((a, b) => _historyProjectDisplayName(a).localeCompare(_historyProjectDisplayName(b)));
}

function _historyOrderProjectsForPicker(projects, activeProject = null) {
  const activeId = activeProject && activeProject.id ? String(activeProject.id) : '';
  return (Array.isArray(projects) ? projects : []).slice().sort((a, b) => {
    const aIsActive = activeId && String(a?.id || '') === activeId;
    const bIsActive = activeId && String(b?.id || '') === activeId;
    if (aIsActive !== bIsActive) return aIsActive ? -1 : 1;
    return _historyProjectDisplayName(a).localeCompare(_historyProjectDisplayName(b));
  });
}

async function _historyLinkRunToProject(run, project) {
  if (!run || !run.id) throw new Error('Run is missing its identifier.');
  if (!project || !project.id) throw new Error('Project is missing its identifier.');
  const resp = await apiFetch(`/projects/${encodeURIComponent(project.id)}/links`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ entity_type: 'run', entity_id: run.id, source: 'manual' }),
  });
  if (!resp.ok) {
    let detail = '';
    try {
      const data = await resp.json();
      detail = data && data.error ? data.error : '';
    } catch (_) {}
    throw new Error(detail || `HTTP ${resp.status}`);
  }
  if (typeof refreshProjectWorkspace === 'function') {
    try { await refreshProjectWorkspace(); } catch (_) {}
  }
  const name = _historyProjectDisplayName(project) || 'project';
  showToast(`Run added to ${name}`);
}

async function _historyAddRunToActiveProject(run) {
  const project = await _historyLoadActiveProject();
  if (!project || !project.id) {
    showToast('No active project selected', 'error');
    return;
  }
  await _historyLinkRunToProject(run, project);
}

function _historyProjectPickerContent(projects) {
  const wrap = document.createElement('div');
  wrap.className = 'history-project-picker';
  const select = document.createElement('select');
  select.className = 'form-select form-control-compact';
  select.setAttribute('aria-label', 'Project');
  projects.forEach((project) => {
    const option = document.createElement('option');
    option.value = String(project.id || '');
    option.textContent = _historyProjectDisplayName(project) || String(project.id || '');
    select.appendChild(option);
  });
  wrap.appendChild(select);
  const help = document.createElement('div');
  help.className = 'history-project-picker-help';
  help.textContent = 'Choose a project to link this run.';
  wrap.appendChild(help);
  return { wrap, select };
}

async function _historyAddRunToProject(run) {
  let projects;
  try {
    const [loadedProjects, activeProject] = await Promise.all([
      _historyLoadProjects(),
      _historyLoadActiveProject().catch(() => null),
    ]);
    projects = _historyOrderProjectsForPicker(loadedProjects, activeProject);
  } catch (_) {
    showToast('Failed to load projects', 'error');
    return;
  }
  if (!projects.length) {
    showToast('No projects available', 'error');
    return;
  }
  const { wrap, select } = _historyProjectPickerContent(projects);
  const choicePromise = showConfirm({
    body: 'Add this run to a project',
    content: wrap,
    tone: null,
    defaultFocus: select,
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'add', label: 'Add to project', role: 'primary' },
    ],
  });
  if (typeof enhanceAppSelects === 'function') {
    enhanceAppSelects(wrap);
    if (typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode()) {
      wrap.querySelector('.app-select-menu')?.classList.add('dropdown-up');
    }
  }
  const choice = await choicePromise;
  if (choice !== 'add') return;
  const project = projects.find(item => String(item.id || '') === select.value);
  try {
    await _historyLinkRunToProject(run, project);
  } catch (_) {
    showToast('Failed to add run to project', 'error');
  }
}

function _createHistoryActionMenu(run, { includeDelete = false } = {}) {
  const wrap = document.createElement('div');
  wrap.className = 'history-action-menu-wrap save-menu-wrap save-menu-down';
  const trigger = document.createElement('button');
  trigger.className = 'history-action-btn btn btn-secondary btn-compact';
  trigger.type = 'button';
  trigger.dataset.action = 'history-menu';
  trigger.textContent = 'more';
  trigger.setAttribute('aria-label', 'More history actions');
  trigger.setAttribute('aria-expanded', 'false');
  const menu = document.createElement('div');
  menu.className = 'history-action-menu save-menu dropdown-surface';
  const items = [
    ['edit-metadata', 'edit'],
    ['permalink', 'permalink'],
    ['compare', 'compare'],
    ['add-active-project', 'add to active project'],
    ['add-project', 'add to project'],
    ['copy-run-id', 'copy run id'],
  ];
  if (includeDelete) items.push(['delete', 'delete']);
  items.forEach(([action, label]) => {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'dropdown-item dropdown-item-compact';
    item.dataset.action = action;
    item.dataset.runId = String(run.id || '');
    item.textContent = label;
    menu.appendChild(item);
  });
  wrap.append(trigger, menu);
  return wrap;
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
  _appendHistoryMetadataBadges(meta, run);
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
  const artifactCount = Number(run.artifact_count || (Array.isArray(run.artifacts) ? run.artifacts.length : 0));
  if (Number.isFinite(artifactCount) && artifactCount > 0) {
    const artifactEl = document.createElement('span');
    artifactEl.className = 'history-entry-artifacts';
    artifactEl.textContent = artifactCount === 1 ? '1 artifact' : `${artifactCount} artifacts`;
    meta.appendChild(artifactEl);
  }
  const exitEl = document.createElement('span');
  exitEl.className = exitCls;
  exitEl.textContent = _historyExitLabel(run.exit_code);
  meta.appendChild(exitEl);
  entry.appendChild(meta);

  const actions = document.createElement('div');
  actions.className = 'history-actions';
  const isMobile = typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode();

  const copyCommandBtn = document.createElement('button');
  copyCommandBtn.className = 'history-action-btn btn btn-secondary btn-compact';
  copyCommandBtn.type = 'button';
  copyCommandBtn.dataset.action = 'copy-command';
  copyCommandBtn.textContent = 'copy command';
  actions.appendChild(copyCommandBtn);

  const restoreBtn = document.createElement('button');
  restoreBtn.className = 'history-action-btn btn btn-secondary btn-compact';
  restoreBtn.type = 'button';
  restoreBtn.dataset.action = 'restore';
  restoreBtn.textContent = 'restore';
  actions.appendChild(restoreBtn);

  if (!isMobile) {
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'history-action-btn btn btn-secondary btn-compact';
    deleteBtn.type = 'button';
    deleteBtn.dataset.action = 'delete';
    deleteBtn.textContent = 'delete';
    actions.appendChild(deleteBtn);
  }

  actions.appendChild(_createHistoryActionMenu(run, { includeDelete: isMobile }));

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
  _appendHistoryMetadataBadges(meta, snapshot);
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

  const editBtn = document.createElement('button');
  editBtn.className = 'history-action-btn btn btn-secondary btn-compact';
  editBtn.type = 'button';
  editBtn.dataset.action = 'edit-metadata';
  editBtn.textContent = 'edit';
  actions.appendChild(editBtn);

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
  if (action === 'edit-metadata') return true;
  const mobileMode = typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode();
  if (!mobileMode) return false;
  return action === 'permalink';
}

function _historyEditEntityMetadata(entityType, entity) {
  const editor = typeof globalThis !== 'undefined' ? globalThis.openEntityMetadataEditor : null;
  if (typeof editor !== 'function') {
    showToast('Metadata editor is not available', 'error');
    return;
  }
  editor(entityType, entity, {
    onSaved: async () => {
      refreshHistoryPanel();
      showToast('Metadata saved');
    },
  });
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
        <div class="history-compare-heading">
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
  // Close (and unportal) any open dropdowns before hiding the overlay,
  // otherwise a portaled menu would remain visible in document.body.
  _closeHistoryCompareActionMenus();
  if (typeof closeAppSelects === 'function') closeAppSelects();
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

function _ensureHistoryRunOverlay() {
  let overlay = document.getElementById('history-run-overlay');
  if (overlay) return overlay;

  overlay = document.createElement('div');
  overlay.id = 'history-run-overlay';
  overlay.className = 'modal-overlay mobile-sheet-overlay u-hidden history-run-overlay';
  overlay.innerHTML = `
    <section id="history-run-modal" class="history-run-modal mobile-sheet-surface" role="dialog" aria-modal="true" aria-labelledby="history-run-title">
      <div class="sheet-grab gesture-handle" role="button" tabindex="0" aria-label="Close run details"></div>
      <div class="history-run-header surface-header">
        <div class="history-run-heading">
          <div id="history-run-title" class="history-run-title">RUN DETAILS</div>
          <div id="history-run-subtitle" class="history-run-subtitle"></div>
        </div>
        <button type="button" class="close-btn history-run-close" aria-label="Close run details">✕</button>
      </div>
      <div class="history-run-tabs" role="tablist" aria-label="Run details sections">
        <button type="button" class="toggle-btn history-run-tab" data-history-run-tab="summary" role="tab">Summary</button>
        <button type="button" class="toggle-btn history-run-tab" data-history-run-tab="output" role="tab">Output</button>
        <button type="button" class="toggle-btn history-run-tab" data-history-run-tab="findings" role="tab">Findings</button>
        <button type="button" class="toggle-btn history-run-tab" data-history-run-tab="artifacts" role="tab">Artifacts</button>
      </div>
      <div id="history-run-body" class="history-run-body surface-body nice-scroll"></div>
    </section>
  `;
  document.body.appendChild(overlay);
  overlay.addEventListener('click', e => {
    if (e.target === overlay) closeHistoryRunOverlay();
    const menuTrigger = e.target.closest?.('.history-run-action-menu-trigger');
    if (menuTrigger) {
      e.preventDefault();
      e.stopPropagation();
      const wrap = menuTrigger.closest('.history-run-action-menu-wrap');
      if (!wrap) return;
      const open = !wrap.classList.contains('open');
      _closeHistoryRunActionMenus(open ? wrap : null);
      wrap.classList.toggle('open', open);
      menuTrigger.setAttribute('aria-expanded', open ? 'true' : 'false');
      return;
    }
    const tab = e.target.closest?.('[data-history-run-tab]');
    if (tab) {
      _closeHistoryRunActionMenus();
      _historyRunModalState.activeTab = String(tab.dataset.historyRunTab || 'summary');
      _renderHistoryRunModal();
      return;
    }
    const action = e.target.closest?.('[data-history-run-action]');
    if (action) {
      _closeHistoryRunActionMenus();
      _handleHistoryRunModalAction(String(action.dataset.historyRunAction || ''));
    }
  });
  overlay.querySelectorAll('.history-run-close, .sheet-grab').forEach(el => {
    el.addEventListener('click', () => closeHistoryRunOverlay());
    el.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        closeHistoryRunOverlay();
      }
    });
  });
  if (typeof bindDismissible === 'function') {
    bindDismissible(overlay, {
      level: 'modal',
      isOpen: () => overlay.classList.contains('open'),
      onClose: closeHistoryRunOverlay,
      closeButtons: overlay.querySelectorAll('.history-run-close, .sheet-grab'),
    });
  }
  return overlay;
}

function closeHistoryRunOverlay() {
  const overlay = document.getElementById('history-run-overlay');
  if (!overlay) return;
  overlay.classList.remove('open');
  overlay.classList.add('u-hidden');
  overlay.setAttribute('aria-hidden', 'true');
  _historyRunModalToken += 1;
  _closeHistoryRunActionMenus();
}

function _openHistoryRunOverlay() {
  const overlay = _ensureHistoryRunOverlay();
  overlay.classList.remove('u-hidden');
  overlay.classList.add('open');
  overlay.setAttribute('aria-hidden', 'false');
}

function isHistoryRunOverlayOpen() {
  const overlay = document.getElementById('history-run-overlay');
  return !!(overlay && overlay.classList.contains('open'));
}

function _historyRunDisplay(run = _historyRunModalState.run) {
  return run && run.command ? String(run.command) : 'run';
}

function _historyRunPrimary() {
  return _historyRunModalState.details || _historyRunModalState.run || {};
}

function _historyRunOutputEntries(run) {
  if (Array.isArray(run.output_entries)) {
    return run.output_entries.map(entry => ({
      text: String(entry && typeof entry === 'object' ? entry.text || '' : entry || ''),
      cls: String(entry && typeof entry === 'object' ? entry.cls || '' : ''),
    }));
  }
  if (Array.isArray(run.output)) {
    return run.output.map(line => ({ text: String(line || ''), cls: '' }));
  }
  if (run.output_preview) {
    return String(run.output_preview).split(/\r?\n/).map(line => ({ text: line, cls: '' }));
  }
  return [];
}

function _historyRunMetaRow(label, value) {
  const row = document.createElement('div');
  row.className = 'history-run-meta-row';
  const key = document.createElement('span');
  key.textContent = label;
  const val = document.createElement('strong');
  val.textContent = value == null || value === '' ? '—' : String(value);
  row.append(key, val);
  return row;
}

function _historyRunActionButton(label, action, { disabled = false, tone = 'secondary' } = {}) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = `btn btn-${tone} btn-compact`;
  btn.dataset.historyRunAction = action;
  btn.textContent = label;
  btn.disabled = !!disabled;
  return btn;
}

function _historyRunActionMenu() {
  const wrap = document.createElement('div');
  wrap.className = 'history-run-action-menu-wrap save-menu-wrap';
  const trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'btn btn-secondary btn-compact history-run-action-menu-trigger';
  trigger.textContent = 'Actions';
  trigger.setAttribute('aria-haspopup', 'menu');
  trigger.setAttribute('aria-expanded', 'false');
  const menu = document.createElement('div');
  menu.className = 'history-run-action-menu save-menu dropdown-surface';
  menu.setAttribute('role', 'menu');
  [
    ['copy-command', 'Copy command'],
    ['edit-metadata', 'Edit metadata'],
    ['add-active-project', 'Add to active project'],
    ['add-project', 'Add to project'],
    ['copy-run-id', 'Copy run ID'],
  ].forEach(([action, label]) => {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'dropdown-item dropdown-item-compact';
    item.dataset.historyRunAction = action;
    item.setAttribute('role', 'menuitem');
    item.textContent = label;
    menu.appendChild(item);
  });
  wrap.append(trigger, menu);
  return wrap;
}

function _historyRunSectionHeader(title, action = null) {
  const header = document.createElement('div');
  header.className = 'history-run-section-header';
  const heading = document.createElement('h3');
  heading.textContent = title;
  header.appendChild(heading);
  if (action) header.appendChild(action);
  return header;
}

function _historyRunField(label, content) {
  const row = document.createElement('div');
  row.className = 'history-run-field';
  const key = document.createElement('span');
  key.className = 'history-run-field-label';
  key.textContent = label;
  const value = document.createElement('div');
  value.className = 'history-run-field-value';
  if (typeof content === 'string') {
    value.textContent = content;
  } else if (content) {
    value.appendChild(content);
  }
  row.append(key, value);
  return row;
}

function _renderHistoryRunSummary(body, run) {
  const summary = document.createElement('div');
  summary.className = 'history-run-summary-grid';
  summary.append(
    _historyRunMetaRow('Status', _historyExitLabel(run.exit_code)),
    _historyRunMetaRow('Started', run.started ? new Date(run.started).toLocaleString() : ''),
    _historyRunMetaRow('Finished', run.finished ? new Date(run.finished).toLocaleString() : ''),
    _historyRunMetaRow('Duration', _historyElapsedLabel(run)),
    _historyRunMetaRow('Lines', run.output_line_count ? Number(run.output_line_count).toLocaleString() : ''),
    _historyRunMetaRow('Findings', Number(run.finding_count || (_historyRunModalState.findings || []).length || 0).toLocaleString()),
    _historyRunMetaRow('Artifacts', Number(run.artifact_count || (Array.isArray(run.artifacts) ? run.artifacts.length : 0) || 0).toLocaleString()),
  );
  body.appendChild(summary);

  const context = document.createElement('div');
  context.className = 'history-run-context-grid';

  const metadata = document.createElement('div');
  metadata.className = 'history-run-section';
  metadata.appendChild(_historyRunSectionHeader(
    'Metadata',
    _historyRunActionButton('Edit', 'edit-metadata'),
  ));

  const metadataFields = document.createElement('div');
  metadataFields.className = 'history-run-field-list';
  const chips = document.createElement('div');
  chips.className = 'history-run-chip-row';
  _historyEntityLabelValues(run).forEach((label) => {
    const chip = document.createElement('span');
    chip.className = 'badge badge-tone-muted';
    chip.textContent = label;
    chips.appendChild(chip);
  });
  if (!chips.childElementCount) {
    const empty = document.createElement('span');
    empty.className = 'history-run-muted';
    empty.textContent = 'No labels saved.';
    chips.appendChild(empty);
  }
  metadataFields.appendChild(_historyRunField('Labels', chips));
  const noteText = document.createElement('p');
  noteText.className = 'history-run-muted history-run-note-preview';
  noteText.textContent = _historyEntityNoteBody(run) || 'No notes saved.';
  metadataFields.appendChild(_historyRunField('Notes', noteText));
  metadata.appendChild(metadataFields);
  context.appendChild(metadata);

  const project = document.createElement('div');
  project.className = 'history-run-section';
  const projectState = _historyRunModalState.projectState;
  const canAddToProject = !!(
    projectState
    && projectState.project
    && !projectState.attached
    && !_historyRunModalState.loadingProject
  );
  project.appendChild(_historyRunSectionHeader(
    'Current project',
    canAddToProject ? _historyRunActionButton('Add', 'add-active-project') : null,
  ));
  const projectFields = document.createElement('div');
  projectFields.className = 'history-run-field-list';
  const projectStatus = document.createElement('span');
  projectStatus.className = 'badge badge-tone-muted';
  let projectName = '—';
  if (_historyRunModalState.loadingProject) {
    projectStatus.textContent = 'Checking';
  } else if (!projectState || !projectState.project) {
    projectStatus.textContent = 'No active project';
  } else if (projectState.attached) {
    projectStatus.className = 'badge badge-tone-cyan';
    projectStatus.textContent = 'Attached';
    projectName = _historyProjectDisplayName(projectState.project);
  } else {
    projectStatus.textContent = 'Not attached';
    projectName = _historyProjectDisplayName(projectState.project);
  }
  projectFields.appendChild(_historyRunField('Status', projectStatus));
  projectFields.appendChild(_historyRunField('Project', projectName));
  project.appendChild(projectFields);
  context.appendChild(project);
  body.appendChild(context);

  const actions = document.createElement('div');
  actions.className = 'history-run-actions history-run-primary-actions';
  actions.append(
    _historyRunActionButton('Restore', 'restore'),
    _historyRunActionButton('Delete', 'delete'),
    _historyRunActionButton('Permalink', 'permalink'),
    _historyRunActionButton('Compare', 'compare'),
    _historyRunActionMenu(),
  );
  body.appendChild(actions);
}

function _renderHistoryRunOutput(body, run) {
  const output = _historyRunOutputEntries(run);
  if (!output.length && _historyRunModalState.loadingDetails) {
    const loading = document.createElement('div');
    loading.className = 'history-run-empty';
    loading.textContent = 'Loading output preview...';
    body.appendChild(loading);
    return;
  }
  if (!output.length) {
    const empty = document.createElement('div');
    empty.className = 'history-run-empty';
    empty.textContent = 'No saved output preview is available.';
    body.appendChild(empty);
    return;
  }
  const pre = document.createElement('pre');
  pre.className = 'history-run-output';
  pre.textContent = output.map(entry => entry.text).join('\n');
  body.appendChild(pre);
  if (run.preview_notice) {
    const notice = document.createElement('div');
    notice.className = 'history-run-notice';
    notice.textContent = run.preview_notice;
    body.appendChild(notice);
  }
}

function _renderHistoryRunFindings(body) {
  if (_historyRunModalState.loadingFindings && _historyRunModalState.findings == null) {
    const loading = document.createElement('div');
    loading.className = 'history-run-empty';
    loading.textContent = 'Loading findings...';
    body.appendChild(loading);
    return;
  }
  const findings = Array.isArray(_historyRunModalState.findings) ? _historyRunModalState.findings : [];
  if (!findings.length) {
    const empty = document.createElement('div');
    empty.className = 'history-run-empty';
    empty.textContent = 'No structured findings recorded for this run.';
    body.appendChild(empty);
    return;
  }
  const list = document.createElement('div');
  list.className = 'history-run-list';
  findings.forEach((finding) => {
    const item = document.createElement('div');
    item.className = 'history-run-list-item';
    const title = document.createElement('div');
    title.className = 'history-run-list-title';
    title.textContent = finding.title || finding.raw_line || 'Finding';
    const meta = document.createElement('div');
    meta.className = 'history-run-list-meta';
    const parts = [
      finding.severity ? `severity: ${finding.severity}` : '',
      finding.review_state ? `review: ${finding.review_state}` : '',
      Number.isFinite(Number(finding.line_number)) ? `line ${Number(finding.line_number) + 1}` : '',
      finding.scope ? `scope: ${finding.scope}` : '',
    ].filter(Boolean);
    meta.textContent = parts.join(' · ');
    item.append(title, meta);
    if (finding.raw_line && finding.raw_line !== finding.title) {
      const raw = document.createElement('code');
      raw.className = 'history-run-finding-raw';
      raw.textContent = finding.raw_line;
      item.appendChild(raw);
    }
    list.appendChild(item);
  });
  body.appendChild(list);
}

function _renderHistoryRunArtifacts(body, run) {
  const artifacts = Array.isArray(run.artifacts) ? run.artifacts : [];
  if (_historyRunModalState.loadingDetails && !artifacts.length) {
    const loading = document.createElement('div');
    loading.className = 'history-run-empty';
    loading.textContent = 'Loading artifacts...';
    body.appendChild(loading);
    return;
  }
  if (!artifacts.length) {
    const empty = document.createElement('div');
    empty.className = 'history-run-empty';
    empty.textContent = 'No workspace artifacts recorded for this run.';
    body.appendChild(empty);
    return;
  }
  const list = document.createElement('div');
  list.className = 'history-run-list';
  artifacts.forEach((artifact) => {
    const item = document.createElement('div');
    item.className = 'history-run-list-item';
    const title = document.createElement('div');
    title.className = 'history-run-list-title';
    title.textContent = artifact.display_name || artifact.workspace_path || 'artifact';
    const meta = document.createElement('div');
    meta.className = 'history-run-list-meta';
    meta.textContent = [
      artifact.kind || '',
      artifact.workspace_path || '',
      artifact.byte_size ? `${Number(artifact.byte_size).toLocaleString()} bytes` : '',
    ].filter(Boolean).join(' · ');
    item.append(title, meta);
    list.appendChild(item);
  });
  body.appendChild(list);
}

function _renderHistoryRunModal() {
  const overlay = _ensureHistoryRunOverlay();
  const run = _historyRunPrimary();
  const subtitle = overlay.querySelector('#history-run-subtitle');
  if (subtitle) subtitle.textContent = _historyRunDisplay(run);
  overlay.querySelectorAll('[data-history-run-tab]').forEach((tab) => {
    const active = String(tab.dataset.historyRunTab || '') === _historyRunModalState.activeTab;
    tab.classList.toggle('is-active', active);
    tab.setAttribute('aria-selected', active ? 'true' : 'false');
    tab.setAttribute('aria-pressed', active ? 'true' : 'false');
  });
  const findingsTab = overlay.querySelector('[data-history-run-tab="findings"]');
  if (findingsTab) {
    const count = Array.isArray(_historyRunModalState.findings)
      ? _historyRunModalState.findings.length
      : Number(run.finding_count || 0);
    findingsTab.textContent = count ? `Findings (${count})` : 'Findings';
  }
  const artifactsTab = overlay.querySelector('[data-history-run-tab="artifacts"]');
  if (artifactsTab) {
    const count = Number(run.artifact_count || (Array.isArray(run.artifacts) ? run.artifacts.length : 0) || 0);
    artifactsTab.textContent = count ? `Artifacts (${count})` : 'Artifacts';
  }
  const body = overlay.querySelector('#history-run-body');
  if (!body) return;
  body.replaceChildren();
  if (_historyRunModalState.error) {
    const error = document.createElement('div');
    error.className = 'history-run-notice is-error';
    error.textContent = _historyRunModalState.error;
    body.appendChild(error);
  }
  if (_historyRunModalState.activeTab === 'output') _renderHistoryRunOutput(body, run);
  else if (_historyRunModalState.activeTab === 'findings') _renderHistoryRunFindings(body);
  else if (_historyRunModalState.activeTab === 'artifacts') _renderHistoryRunArtifacts(body, run);
  else _renderHistoryRunSummary(body, run);
}

async function _loadHistoryRunDetails(runId, token) {
  _historyRunModalState.loadingDetails = true;
  _renderHistoryRunModal();
  try {
    const resp = await apiFetch(`/history/${encodeURIComponent(runId)}?json&preview=1`, { cache: 'no-store' });
    if (resp.ok === false) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (token !== _historyRunModalToken) return;
    _historyRunModalState.details = { ...(_historyRunModalState.run || {}), ...(data || {}) };
  } catch (_) {
    if (token === _historyRunModalToken) _historyRunModalState.error = 'Could not load run details.';
  } finally {
    if (token === _historyRunModalToken) {
      _historyRunModalState.loadingDetails = false;
      _renderHistoryRunModal();
    }
  }
}

async function _loadHistoryRunFindings(runId, token) {
  _historyRunModalState.loadingFindings = true;
  _renderHistoryRunModal();
  try {
    const resp = await apiFetch(`/entities/run/${encodeURIComponent(runId)}/findings`, { cache: 'no-store' });
    if (resp.ok === false) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (token !== _historyRunModalToken) return;
    _historyRunModalState.findings = Array.isArray(data.findings) ? data.findings : [];
  } catch (_) {
    if (token === _historyRunModalToken) {
      _historyRunModalState.findings = [];
      _historyRunModalState.error = 'Could not load run findings.';
    }
  } finally {
    if (token === _historyRunModalToken) {
      _historyRunModalState.loadingFindings = false;
      _renderHistoryRunModal();
    }
  }
}

async function _loadHistoryRunProjectState(runId, token) {
  _historyRunModalState.loadingProject = true;
  _renderHistoryRunModal();
  try {
    const project = await _historyLoadActiveProject();
    if (token !== _historyRunModalToken) return;
    if (!project || !project.id) {
      _historyRunModalState.projectState = { project: null, attached: false };
      return;
    }
    const resp = await apiFetch(`/projects/${encodeURIComponent(project.id)}/summary`, { cache: 'no-store' });
    if (resp.ok === false) throw new Error(`HTTP ${resp.status}`);
    const summary = await resp.json();
    const runs = Array.isArray(summary.runs) ? summary.runs : [];
    _historyRunModalState.projectState = {
      project,
      attached: runs.some(item => String(item && item.id || '') === String(runId || '')),
    };
  } catch (_) {
    if (token === _historyRunModalToken) _historyRunModalState.projectState = { project: null, attached: false };
  } finally {
    if (token === _historyRunModalToken) {
      _historyRunModalState.loadingProject = false;
      _renderHistoryRunModal();
    }
  }
}

function openHistoryRunDetails(run) {
  if (!run || !run.id) return;
  _historyRunModalToken += 1;
  const token = _historyRunModalToken;
  _historyRunModalState = {
    run,
    details: null,
    findings: null,
    projectState: null,
    activeTab: 'summary',
    loadingDetails: false,
    loadingFindings: false,
    loadingProject: false,
    error: '',
  };
  _openHistoryRunOverlay();
  _renderHistoryRunModal();
  _loadHistoryRunDetails(run.id, token);
  _loadHistoryRunFindings(run.id, token);
  _loadHistoryRunProjectState(run.id, token);
}

async function _handleHistoryRunModalAction(action) {
  const run = _historyRunPrimary();
  if (!run || !run.id) return;
  if (action === 'use-command') {
    const cmd = run.command || '';
    if (typeof setComposerValue === 'function') setComposerValue(cmd, cmd.length, cmd.length);
    closeHistoryRunOverlay();
    if (typeof hideHistoryPanel === 'function') hideHistoryPanel();
    if (typeof refocusComposerAfterAction === 'function') refocusComposerAfterAction({ preventScroll: true });
    resetCmdHistoryNav();
  } else if (action === 'restore') {
    closeHistoryRunOverlay();
    const existing = _tabForHistoryRun(run);
    const canUpgradeExisting = !!(existing && run.full_output_available && existing.previewTruncated);
    if (existing && !canUpgradeExisting) {
      activateTab(existing.id);
      if (typeof hideHistoryPanel === 'function') hideHistoryPanel();
      return;
    }
    _setHistoryLoadState(true);
    restoreHistoryRunIntoTab(run, {
      targetTabId: canUpgradeExisting ? existing.id : null,
      hidePanelOnSuccess: true,
    })
      .catch(() => showToast('Failed to load run'))
      .finally(() => _setHistoryLoadState(false));
  } else if (action === 'copy-command') {
    copyTextToClipboard(run.command || '')
      .then(() => showToast('Command copied'))
      .catch(() => showToast('Failed to copy command', 'error'));
  } else if (action === 'permalink') {
    const url = `${location.origin}/history/${run.id}`;
    shareUrl(url).catch(() => showToast('Failed to copy link', 'error'));
  } else if (action === 'compare') {
    closeHistoryRunOverlay();
    openHistoryCompareLauncher(run);
  } else if (action === 'delete') {
    closeHistoryRunOverlay();
    confirmHistAction('delete', run.id, run.command);
  } else if (action === 'edit-metadata') {
    _historyEditEntityMetadata('run', run);
  } else if (action === 'add-active-project') {
    const projectState = _historyRunModalState.projectState;
    const project = projectState && projectState.project;
    if (!project || projectState.attached) return;
    try {
      await _historyLinkRunToProject(run, project);
      _historyRunModalState.projectState = { project, attached: true };
      _renderHistoryRunModal();
      refreshHistoryPanel();
    } catch (_) {
      showToast('Failed to add run to active project', 'error');
    }
  } else if (action === 'add-project') {
    try {
      await _historyAddRunToProject(run);
      refreshHistoryPanel();
    } catch (_) {
      showToast('Failed to add run to project', 'error');
    }
  } else if (action === 'copy-run-id') {
    copyTextToClipboard(run.id)
      .then(() => showToast('Run ID copied'))
      .catch(() => showToast('Failed to copy run ID', 'error'));
  }
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

function _historyCompareTotalChangedLines(totals = {}) {
  return Number(totals.changed_line_count || 0)
    + Number(totals.added_line_count || 0)
    + Number(totals.removed_line_count || 0);
}

function _historyCompareOmittedTotal(truncated = {}) {
  const lineOmitted = truncated && truncated.lines_omitted ? truncated.lines_omitted : {};
  return Number(truncated.hunks_omitted || 0) + Number(lineOmitted.total || 0);
}

function _historyCompareLineLimit(limits = {}) {
  const limit = Number(limits.line_display_truncate || 0);
  return Number.isFinite(limit) && limit > 0 ? limit : 4000;
}

function _historyComparePreferenceCore() {
  return (typeof PreferenceCore !== 'undefined' && PreferenceCore)
    || (typeof DarklabPreferenceCore !== 'undefined' && DarklabPreferenceCore)
    || null;
}

function _historyCompareCoerceViewMode(value) {
  const core = _historyComparePreferenceCore();
  if (core && typeof core.coerceCompareViewMode === 'function') return core.coerceCompareViewMode(value);
  return ['auto', 'side_by_side', 'unified', 'changes_only', 'findings_only'].includes(value) ? value : 'auto';
}

function _historyCompareCoerceContext(value) {
  const core = _historyComparePreferenceCore();
  if (core && typeof core.coerceCompareContextMode === 'function') return core.coerceCompareContextMode(value);
  const normalized = String(value || '').trim().toLowerCase();
  return ['3', '10', 'all'].includes(normalized) ? normalized : '3';
}

function _historyCompareStoredViewMode() {
  if (typeof getCompareViewModePreference === 'function') return _historyCompareCoerceViewMode(getCompareViewModePreference());
  if (typeof getPreference === 'function') return _historyCompareCoerceViewMode(getPreference('pref_compare_view_mode'));
  return 'auto';
}

function _historyCompareStoredContext() {
  if (typeof getCompareContextPreference === 'function') return _historyCompareCoerceContext(getCompareContextPreference());
  if (typeof getPreference === 'function') return _historyCompareCoerceContext(getPreference('pref_compare_context'));
  return '3';
}

function _historyCompareViewportMode() {
  if (typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode()) return 'unified';
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    try {
      if (window.matchMedia('(max-width: 760px)').matches) return 'unified';
    } catch (_) {}
  }
  return 'side_by_side';
}

function _historyCompareUsesMobileLayout() {
  return _historyCompareViewportMode() === 'unified';
}

function _historyCompareResolveViewMode(value = null) {
  const mode = _historyCompareCoerceViewMode(value || _historyCompareStoredViewMode());
  const viewportMode = _historyCompareViewportMode();
  if (mode === 'auto') return viewportMode;
  if (mode === 'side_by_side' && viewportMode === 'unified') return 'unified';
  return mode;
}

function _historyCompareViewModeOptions() {
  const options = [
    ['side_by_side', 'Side-by-side'],
    ['unified', 'Unified'],
    ['changes_only', 'Changes only'],
    ['findings_only', 'Findings only'],
  ];
  if (_historyCompareViewportMode() === 'unified') {
    return options.filter(([value]) => value !== 'side_by_side');
  }
  return options;
}

function _historyCompareContextLimit(value = null) {
  const context = _historyCompareCoerceContext(value || _historyCompareStoredContext());
  if (context === 'all') return null;
  return Number(context);
}

function _historyCompareNumber(value, fallback = null) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function _historyCompareCssEscape(value) {
  const text = String(value);
  if (typeof CSS !== 'undefined' && CSS && typeof CSS.escape === 'function') return CSS.escape(text);
  return text.replace(/["\\]/g, '\\$&');
}

function _historyCompareBucketTone(bucket = {}) {
  const changed = Number(bucket.changed || 0);
  const added = Number(bucket.added || 0);
  const removed = Number(bucket.removed || 0);
  const equal = Number(bucket.equal || 0);
  if (changed > 0) return 'changed';
  if (added > 0 || removed > 0) return added > removed ? 'added' : 'removed';
  if (equal > 0) return 'equal';
  return 'empty';
}

function _historyCompareBuildAnchorMap(data = {}) {
  const map = { a: new Map(), b: new Map() };
  const findingObjects = data.objects?.findings || {};
  const addAnchor = (side, item) => {
    const index = _historyCompareNumber(item?.compare_line_index);
    if (index === null) return;
    const existing = map[side].get(index) || [];
    existing.push(item);
    map[side].set(index, existing);
  };
  (Array.isArray(findingObjects.added) ? findingObjects.added : []).forEach(item => addAnchor('b', item));
  (Array.isArray(findingObjects.removed) ? findingObjects.removed : []).forEach(item => addAnchor('a', item));
  return map;
}

function _historyCompareAnchorTone(items = []) {
  const severities = items.map(item => String(item?.severity || '').toLowerCase());
  if (severities.some(value => value === 'critical' || value === 'high')) return 'high';
  if (severities.some(value => value === 'medium')) return 'medium';
  return 'info';
}

function _historyCompareFindPaneRow(side, compareLineIndex) {
  const overlay = document.getElementById('history-compare-overlay');
  const pane = overlay?.querySelector(`.history-compare-pane[data-side="${side}"]`);
  const index = String(compareLineIndex);
  const row = pane?.querySelector(`.history-compare-row[data-compare-line-index="${_historyCompareCssEscape(index)}"]`);
  return { pane, row };
}

function _historyComparePulseRows(rows = []) {
  rows.filter(Boolean).forEach(row => {
    row.classList.remove('history-compare-line-pulse');
    void row.offsetWidth; // restart the short pulse when the same row is targeted repeatedly
    row.classList.add('history-compare-line-pulse');
    setTimeout(() => row.classList.remove('history-compare-line-pulse'), 900);
  });
}

function _historyCompareScrollPaneRowIntoView(pane, row) {
  if (!pane || !row) return;
  const paneRect = typeof pane.getBoundingClientRect === 'function' ? pane.getBoundingClientRect() : null;
  const rowRect = typeof row.getBoundingClientRect === 'function' ? row.getBoundingClientRect() : null;
  const paneHeight = Number(pane.clientHeight || paneRect?.height || 0);
  const rowHeight = Number(rowRect?.height || row.offsetHeight || 0);
  const relativeTop = Number(rowRect?.top || 0) - Number(paneRect?.top || 0);
  if (paneHeight > 0 && Number.isFinite(relativeTop)) {
    pane.scrollTop = Math.max(0, pane.scrollTop + relativeTop - Math.max(0, (paneHeight - rowHeight) / 2));
    return;
  }
  pane.scrollTop = Number(row.offsetTop || 0);
}

function _historyCompareScrollToLine(side, compareLineIndex, { emit = true } = {}) {
  const primary = _historyCompareFindPaneRow(side, compareLineIndex);
  if (!primary.row || !primary.pane) return false;
  const otherSide = side === 'a' ? 'b' : 'a';
  const pair = primary.row.dataset.comparePair || '';
  const secondary = pair
    ? {
        pane: document.querySelector(`#history-compare-overlay .history-compare-pane[data-side="${otherSide}"]`),
        row: document.querySelector(
          `#history-compare-overlay .history-compare-pane[data-side="${otherSide}"] `
          + `.history-compare-row[data-compare-pair="${_historyCompareCssEscape(pair)}"]`,
        ),
      }
    : _historyCompareFindPaneRow(otherSide, compareLineIndex);
  _historyCompareScrollPaneRowIntoView(primary.pane, primary.row);
  if (secondary.pane) secondary.pane.scrollTop = primary.pane.scrollTop;
  _historyComparePulseRows([primary.row, secondary.row]);
  if (emit && typeof emitUiEvent === 'function') {
    emitUiEvent('app:compare-anchor-scroll', {
      side,
      compare_line_index: compareLineIndex,
    });
  }
  return true;
}

function _historyCompareScrollToRow(row, { emit = false } = {}) {
  if (!(row instanceof Element)) return false;
  const side = row.closest('.history-compare-pane')?.dataset.side || 'a';
  const lineIndex = _historyCompareNumber(row.dataset.compareLineIndex);
  if (lineIndex !== null) return _historyCompareScrollToLine(side, lineIndex, { emit });
  const pair = row.dataset.comparePair || '';
  if (!pair) return false;
  const pairedChanged = document.querySelector(
    `#history-compare-overlay .history-compare-row[data-compare-pair="${_historyCompareCssEscape(pair)}"][data-compare-line-index]`,
  );
  if (!pairedChanged) return false;
  const pairedSide = pairedChanged.closest('.history-compare-pane')?.dataset.side || side;
  return _historyCompareScrollToLine(
    pairedSide,
    _historyCompareNumber(pairedChanged.dataset.compareLineIndex, 0),
    { emit },
  );
}

function _historyCompareRenderedChangeTargets() {
  const changedTones = new Set(['changed', 'added', 'removed']);
  const byPair = new Map();
  [...document.querySelectorAll('#history-compare-overlay .history-compare-row[data-compare-unit-index]')]
    .map(row => ({
      row,
      index: _historyCompareNumber(row.dataset.compareUnitIndex, 0),
      tone: row.dataset.compareUnitTone || '',
      isSpacer: row.classList.contains('history-compare-row-spacer'),
    }))
    .filter(item => changedTones.has(item.tone))
    .forEach(item => {
      const pair = item.row.dataset.comparePair || `unit-${item.index}`;
      const existing = byPair.get(pair);
      if (!existing || (existing.isSpacer && !item.isSpacer)) byPair.set(pair, item);
    });
  return [...byPair.values()]
    .sort((a, b) => a.index - b.index || Number(a.isSpacer) - Number(b.isSpacer));
}

function _historyCompareScrollToBucket(bucket) {
  const start = _historyCompareNumber(bucket?.start, 0);
  const end = Math.max(start + 1, _historyCompareNumber(bucket?.end, start + 1));
  const rows = _historyCompareRenderedChangeTargets();
  const inBucket = rows.filter(item => item.index >= start && item.index < end);
  const target = inBucket.find(item => !item.isSpacer) || inBucket[0]
    || rows.find(item => item.index >= start && !item.isSpacer)
    || rows.find(item => item.index >= start)
    || rows.find(item => !item.isSpacer)
    || rows[0];
  if (!target || !target.row) return false;
  return _historyCompareScrollToRow(target.row, { emit: false });
}

function _renderHistoryCompareLineText(line, segments = null, limits = {}) {
  const code = document.createElement('code');
  const rawText = String((line && line.text) || '');
  const limit = _historyCompareLineLimit(limits);
  const truncated = rawText.length > limit;
  const visibleText = truncated ? rawText.slice(0, limit) : rawText;
  const safeSegments = Array.isArray(segments) ? segments : [];
  if (safeSegments.length && !truncated) {
    _appendHistoryCompareSegments(code, safeSegments, rawText);
  } else {
    code.textContent = visibleText;
  }
  if (truncated) {
    const expander = document.createElement('button');
    expander.type = 'button';
    expander.className = 'chip chip-action history-compare-line-expander';
    expander.textContent = `... +${(rawText.length - limit).toLocaleString()} chars`;
    expander.addEventListener('click', event => {
      event.stopPropagation();
      const split = expander.closest?.('.history-compare-split');
      code.textContent = rawText;
      expander.remove();
      _scheduleHistoryCompareRowPairHeightSync(split);
    });
    const wrap = document.createElement('span');
    wrap.className = 'history-compare-line-text-wrap';
    wrap.appendChild(code);
    wrap.appendChild(expander);
    return wrap;
  }
  return code;
}

function _renderHistoryComparePaneRow(line, {
  sideLabel = '',
  signClass = '',
  rowClass = '',
  segments = null,
  limits = {},
  side = '',
  compareLineIndex = null,
  anchorItems = [],
} = {}) {
  const row = document.createElement('div');
  row.className = `history-compare-row${rowClass ? ` ${rowClass}` : ''}`;
  if (side) row.dataset.side = side;
  if (Number.isFinite(compareLineIndex)) row.dataset.compareLineIndex = String(compareLineIndex);
  const mark = document.createElement('span');
  mark.className = `history-compare-line-mark${signClass ? ` ${signClass}` : ''}`;
  mark.textContent = sideLabel;
  row.appendChild(mark);
  const anchorSlot = document.createElement('span');
  anchorSlot.className = 'history-compare-line-anchor-slot';
  const safeAnchors = Array.isArray(anchorItems) ? anchorItems : [];
  if (safeAnchors.length && Number.isFinite(compareLineIndex)) {
    const marker = document.createElement('button');
    marker.type = 'button';
    marker.className = `btn btn-ghost history-compare-finding-marker is-${_historyCompareAnchorTone(safeAnchors)}`;
    marker.setAttribute('aria-label', 'Jump to linked finding');
    marker.addEventListener('click', event => {
      event.stopPropagation();
      const findingRow = document.querySelector(
        `.history-compare-object-row[data-object-kind="finding"][data-compare-side="${side}"][data-compare-line-index="${_historyCompareCssEscape(compareLineIndex)}"]`,
      );
      if (typeof findingRow?.scrollIntoView === 'function') {
        findingRow.scrollIntoView({ block: 'center', inline: 'nearest' });
      }
      if (findingRow) {
        findingRow.classList.remove('history-compare-line-pulse');
        void findingRow.offsetWidth;
        findingRow.classList.add('history-compare-line-pulse');
        setTimeout(() => findingRow.classList.remove('history-compare-line-pulse'), 900);
      }
    });
    anchorSlot.appendChild(marker);
  }
  row.appendChild(anchorSlot);
  row.appendChild(_renderHistoryCompareLineText(line, segments, limits));
  return row;
}

function _renderHistoryCompareSpacer(label = '') {
  const row = document.createElement('div');
  row.className = 'history-compare-row history-compare-row-spacer';
  row.setAttribute('aria-hidden', 'true');
  const mark = document.createElement('span');
  mark.textContent = label;
  row.appendChild(mark);
  row.appendChild(document.createElement('span'));
  row.appendChild(document.createElement('span'));
  return row;
}

function _historyCompareRowHeight(row) {
  if (!row) return 0;
  const rect = typeof row.getBoundingClientRect === 'function' ? row.getBoundingClientRect() : null;
  return Math.ceil(Math.max(Number(rect?.height || 0), Number(row.offsetHeight || 0)));
}

function _historyCompareUsesStackedMobilePanes(wrap) {
  const mobile = typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode();
  const stacked = wrap?.classList?.contains('is-unified') || wrap?.classList?.contains('is-changes-only');
  return Boolean(mobile && stacked);
}

function _clearHistoryCompareRowPairHeights(wrap) {
  wrap?.querySelectorAll?.('.history-compare-row[data-compare-pair]').forEach(row => {
    row.style.minHeight = '';
  });
}

function _syncHistoryCompareRowPairHeights(wrap) {
  if (!wrap || !wrap.isConnected) return;
  if (_historyCompareUsesStackedMobilePanes(wrap)) {
    _clearHistoryCompareRowPairHeights(wrap);
    return;
  }
  const pairs = new Map();
  wrap.querySelectorAll('.history-compare-row[data-compare-pair]').forEach(row => {
    row.style.minHeight = '';
    const key = row.dataset.comparePair || '';
    if (!key) return;
    const rows = pairs.get(key) || [];
    rows.push(row);
    pairs.set(key, rows);
  });
  pairs.forEach(rows => {
    if (rows.length < 2) return;
    const height = Math.max(...rows.map(_historyCompareRowHeight));
    if (!height) return;
    rows.forEach(row => {
      row.style.minHeight = `${height}px`;
    });
  });
}

function _scheduleHistoryCompareRowPairHeightSync(wrap) {
  if (!wrap) return;
  if (_historyCompareRowHeightFrame !== null) {
    const cancel = typeof cancelAnimationFrame === 'function' ? cancelAnimationFrame : clearTimeout;
    cancel(_historyCompareRowHeightFrame);
  }
  const raf = typeof requestAnimationFrame === 'function' ? requestAnimationFrame : callback => setTimeout(callback, 0);
  _historyCompareRowHeightFrame = raf(() => {
    _historyCompareRowHeightFrame = null;
    _syncHistoryCompareRowPairHeights(wrap);
  });
}

function _bindHistoryCompareRowPairHeightSync(wrap) {
  if (_historyCompareRowResizeObserver) {
    _historyCompareRowResizeObserver.disconnect();
    _historyCompareRowResizeObserver = null;
  }
  if (typeof ResizeObserver === 'function' && wrap) {
    _historyCompareRowResizeObserver = new ResizeObserver(() => _scheduleHistoryCompareRowPairHeightSync(wrap));
    _historyCompareRowResizeObserver.observe(wrap);
  }
  _scheduleHistoryCompareRowPairHeightSync(wrap);
}

function _appendHistoryCompareRowPair(leftPane, rightPane, leftRow, rightRow, unitTone = '') {
  const pair = String(_historyCompareRowPairSequence);
  _historyCompareRowPairSequence += 1;
  leftRow.dataset.comparePair = pair;
  rightRow.dataset.comparePair = pair;
  if (unitTone) {
    const unit = String(_historyCompareUnitSequence);
    _historyCompareUnitSequence += 1;
    leftRow.dataset.compareUnitIndex = unit;
    rightRow.dataset.compareUnitIndex = unit;
    leftRow.dataset.compareUnitTone = unitTone;
    rightRow.dataset.compareUnitTone = unitTone;
  }
  leftPane.appendChild(leftRow);
  rightPane.appendChild(rightRow);
}

function _advanceHistoryCompareUnits(count) {
  _historyCompareUnitSequence += Math.max(0, Number(count || 0));
}

function _historyCompareReplaceRenderEvents(hunk) {
  const events = [];
  (hunk.changed_pairs || []).forEach(pair => {
    events.push({
      type: 'pair',
      leftIndex: Number(pair.left_index),
      rightIndex: Number(pair.right_index),
      pair,
    });
  });
  (hunk.left_unpaired || []).forEach(index => {
    events.push({ type: 'left', leftIndex: Number(index), rightIndex: null });
  });
  (hunk.right_unpaired || []).forEach(index => {
    events.push({ type: 'right', leftIndex: null, rightIndex: Number(index) });
  });

  const pending = events.filter(event => (
    (event.leftIndex === null || Number.isFinite(event.leftIndex))
    && (event.rightIndex === null || Number.isFinite(event.rightIndex))
  ));
  const ordered = [];
  const nextSideIndex = (side) => {
    const key = side === 'left' ? 'leftIndex' : 'rightIndex';
    const indexes = pending
      .map(event => event[key])
      .filter(index => Number.isFinite(index));
    return indexes.length ? Math.min(...indexes) : null;
  };
  while (pending.length) {
    const nextLeft = nextSideIndex('left');
    const nextRight = nextSideIndex('right');
    let index = pending.findIndex(event => (
      (event.leftIndex === null || event.leftIndex === nextLeft)
      && (event.rightIndex === null || event.rightIndex === nextRight)
    ));
    if (index < 0) {
      index = pending
        .map((event, eventIndex) => ({
          eventIndex,
          order: Math.max(
            Number.isFinite(event.leftIndex) ? event.leftIndex : -1,
            Number.isFinite(event.rightIndex) ? event.rightIndex : -1,
          ),
        }))
        .sort((a, b) => a.order - b.order || a.eventIndex - b.eventIndex)[0].eventIndex;
    }
    ordered.push(pending.splice(index, 1)[0]);
  }
  return ordered;
}

function _historyCompareFoldRange(hunk, side) {
  const context = hunk && hunk.context ? hunk.context : {};
  const leading = context.leading && Array.isArray(context.leading[side]) ? context.leading[side] : [];
  const trailing = context.trailing && Array.isArray(context.trailing[side]) ? context.trailing[side] : [];
  const bounds = hunk && hunk[side] ? hunk[side] : {};
  return {
    start: Number(bounds.start || 0) + leading.length,
    end: Math.max(Number(bounds.start || 0) + leading.length, Number(bounds.end || 0) - trailing.length),
  };
}

function _historyCompareLineUrl(data, side, start, end) {
  const params = new URLSearchParams();
  params.set('left', data.left_run_id || data.left?.id || '');
  params.set('right', data.right_run_id || data.right?.id || '');
  params.set('side', side === 'left' ? 'a' : 'b');
  params.set('start', String(start));
  params.set('end', String(end));
  if (data.project_id) params.set('project_id', data.project_id);
  if (data.baseline_label) params.set('baseline_label', data.baseline_label);
  return `/history/compare/lines?${params.toString()}`;
}

function _fetchHistoryCompareFoldSide(data, hunk, side) {
  const range = _historyCompareFoldRange(hunk, side);
  if (range.start >= range.end) return Promise.resolve([]);
  const collected = [];
  const loadPage = start => apiFetch(_historyCompareLineUrl(data, side, start, range.end))
    .then(resp => resp.json())
    .then(payload => {
      if (payload.error) throw new Error(payload.error);
      const lines = Array.isArray(payload.lines) ? payload.lines : [];
      collected.push(...lines);
      const nextStart = Number(payload.end);
      if (
        payload.truncated
        && !payload.range_clamped
        && Number.isFinite(nextStart)
        && nextStart > start
        && nextStart < range.end
      ) {
        return loadPage(nextStart);
      }
      return collected;
    });
  return loadPage(range.start);
}

function _historyCompareSliceContextLines(lines, edge, contextLimit) {
  const safeLines = Array.isArray(lines) ? lines : [];
  if (contextLimit === null) return safeLines;
  const limit = Math.max(0, Number(contextLimit || 0));
  if (!limit) return [];
  return edge === 'leading' ? safeLines.slice(-limit) : safeLines.slice(0, limit);
}

function _appendHistoryCompareEqualHunk(leftPane, rightPane, hunk, data, rerender, anchorMap, options = {}) {
  const limits = data.limits || {};
  const contextLimit = Object.prototype.hasOwnProperty.call(options, 'contextLimit') ? options.contextLimit : 3;
  const changesOnly = !!options.changesOnly;
  const context = hunk.context || {};
  const appendLines = (leftLines, rightLines, leftStart = 0, rightStart = 0) => {
    const count = Math.max(leftLines.length, rightLines.length);
    for (let index = 0; index < count; index += 1) {
      const leftCompareIndex = Number(leftStart) + index;
      const rightCompareIndex = Number(rightStart) + index;
      _appendHistoryCompareRowPair(
        leftPane,
        rightPane,
        leftLines[index]
          ? _renderHistoryComparePaneRow(leftLines[index], {
              sideLabel: 'A',
              rowClass: 'is-equal',
              limits,
              side: 'a',
              compareLineIndex: leftCompareIndex,
              anchorItems: anchorMap?.a?.get(leftCompareIndex) || [],
            })
          : _renderHistoryCompareSpacer('A'),
        rightLines[index]
          ? _renderHistoryComparePaneRow(rightLines[index], {
              sideLabel: 'B',
              rowClass: 'is-equal',
              limits,
              side: 'b',
              compareLineIndex: rightCompareIndex,
              anchorItems: anchorMap?.b?.get(rightCompareIndex) || [],
            })
          : _renderHistoryCompareSpacer('B'),
        'equal',
      );
    }
  };
  const makeFoldRow = (button) => {
    const row = document.createElement('div');
    row.className = 'history-compare-row history-compare-row-fold';
    row.appendChild(document.createElement('span'));
    row.appendChild(document.createElement('span'));
    row.appendChild(button);
    return row;
  };
  const makeFoldButtonPair = (label, expand) => {
    const foldButtons = [];
    const setFoldButtons = (disabled, text) => {
      foldButtons.forEach(button => {
        button.disabled = disabled;
        button.textContent = text;
      });
    };
    const makeFoldButton = () => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn btn-secondary btn-compact history-compare-fold';
      button.textContent = label;
      button.addEventListener('click', () => expand(setFoldButtons));
      foldButtons.push(button);
      return button;
    };
    _appendHistoryCompareRowPair(leftPane, rightPane, makeFoldRow(makeFoldButton()), makeFoldRow(makeFoldButton()));
  };
  if (Array.isArray(hunk.left?.lines) || Array.isArray(hunk.right?.lines)) {
    const leftLines = hunk.left?.lines || [];
    const rightLines = hunk.right?.lines || [];
    const leftStart = _historyCompareNumber(hunk.left?.start, 0);
    const rightStart = _historyCompareNumber(hunk.right?.start, 0);
    const total = Math.max(leftLines.length, rightLines.length);
    if (changesOnly) {
      _advanceHistoryCompareUnits(total);
    } else if (contextLimit === null || total <= contextLimit * 2) {
      appendLines(leftLines, rightLines, leftStart, rightStart);
    } else {
      const leadingCount = Math.max(0, contextLimit);
      const trailingCount = Math.max(0, contextLimit);
      appendLines(leftLines.slice(0, leadingCount), rightLines.slice(0, leadingCount), leftStart, rightStart);
      const omitted = Math.max(0, total - leadingCount - trailingCount);
      if (omitted > 0) {
        if (hunk._expanded) {
          makeFoldButtonPair('▾ Hide unchanged lines', () => {
            hunk._expanded = false;
            rerender();
          });
          appendLines(
            leftLines.slice(leadingCount, total - trailingCount),
            rightLines.slice(leadingCount, total - trailingCount),
            leftStart + leadingCount,
            rightStart + leadingCount,
          );
        } else {
          makeFoldButtonPair(`▸ Show ${omitted.toLocaleString()} unchanged line(s)`, () => {
            hunk._expanded = true;
            rerender();
          });
          _advanceHistoryCompareUnits(omitted);
        }
      }
      appendLines(
        leftLines.slice(total - trailingCount),
        rightLines.slice(total - trailingCount),
        leftStart + Math.max(leadingCount, total - trailingCount),
        rightStart + Math.max(leadingCount, total - trailingCount),
      );
    }
    return;
  }
  const leftStart = _historyCompareNumber(hunk.left?.start, 0);
  const rightStart = _historyCompareNumber(hunk.right?.start, 0);
  const rawLeadingLeft = context.leading?.left || [];
  const rawLeadingRight = context.leading?.right || [];
  const rawTrailingLeft = context.trailing?.left || [];
  const rawTrailingRight = context.trailing?.right || [];
  const leadingLeft = changesOnly ? [] : _historyCompareSliceContextLines(rawLeadingLeft, 'leading', contextLimit);
  const leadingRight = changesOnly ? [] : _historyCompareSliceContextLines(rawLeadingRight, 'leading', contextLimit);
  const trailingLeft = changesOnly ? [] : _historyCompareSliceContextLines(rawTrailingLeft, 'trailing', contextLimit);
  const trailingRight = changesOnly ? [] : _historyCompareSliceContextLines(rawTrailingRight, 'trailing', contextLimit);
  appendLines(
    leadingLeft,
    leadingRight,
    leftStart + Math.max(0, rawLeadingLeft.length - leadingLeft.length),
    rightStart + Math.max(0, rawLeadingRight.length - leadingRight.length),
  );
  if (hunk._expanded) {
    const collapse = () => {
      hunk._expanded = false;
      rerender();
    };
    const makeCollapseButton = () => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn btn-secondary btn-compact history-compare-fold';
      button.textContent = '▾ Hide unchanged lines';
      button.addEventListener('click', collapse);
      return button;
    };
    _appendHistoryCompareRowPair(leftPane, rightPane, makeFoldRow(makeCollapseButton()), makeFoldRow(makeCollapseButton()));
    appendLines(
      hunk._expandedLeft || [],
      hunk._expandedRight || [],
      leftStart + leadingLeft.length,
      rightStart + leadingRight.length,
    );
    _advanceHistoryCompareUnits(
      Number(context.omitted || 0) - Math.max(
        Array.isArray(hunk._expandedLeft) ? hunk._expandedLeft.length : 0,
        Array.isArray(hunk._expandedRight) ? hunk._expandedRight.length : 0,
      ),
    );
  } else if (Number(context.omitted || 0) > 0) {
    const label = `▸ Show ${Number(context.omitted).toLocaleString()} unchanged line(s)`;
    const expand = (setFoldButtons) => {
      if (hunk._loading) return;
      hunk._loading = true;
      setFoldButtons(true, 'Loading unchanged lines...');
      const leftPromise = hunk._expandedLeft
        ? Promise.resolve(hunk._expandedLeft)
        : _fetchHistoryCompareFoldSide(data, hunk, 'left');
      const rightPromise = hunk._expandedRight
        ? Promise.resolve(hunk._expandedRight)
        : _fetchHistoryCompareFoldSide(data, hunk, 'right');
      Promise.all([leftPromise, rightPromise])
        .then(([leftLines, rightLines]) => {
          hunk._expandedLeft = leftLines;
          hunk._expandedRight = rightLines;
          hunk._expanded = true;
          hunk._loading = false;
          rerender();
        })
        .catch(() => {
          hunk._loading = false;
          setFoldButtons(false, label);
          showToast('Failed to load unchanged lines', 'error');
        });
    };
    makeFoldButtonPair(label, expand);
    _advanceHistoryCompareUnits(context.omitted);
  }
  appendLines(
    trailingLeft,
    trailingRight,
    _historyCompareNumber(hunk.left?.end, leftStart) - trailingLeft.length,
    _historyCompareNumber(hunk.right?.end, rightStart) - trailingRight.length,
  );
}

function _appendHistoryCompareReplaceHunk(leftPane, rightPane, hunk, data, anchorMap) {
  const limits = data.limits || {};
  const leftLines = hunk.left?.lines || [];
  const rightLines = hunk.right?.lines || [];
  const leftStart = _historyCompareNumber(hunk.left?.start, 0);
  const rightStart = _historyCompareNumber(hunk.right?.start, 0);
  _historyCompareReplaceRenderEvents(hunk).forEach(event => {
    if (event.type === 'pair') {
      const pair = event.pair || {};
      const leftLine = leftLines[pair.left_index] || {};
      const rightLine = rightLines[pair.right_index] || {};
      const segments = pair.segments || {};
      const leftCompareIndex = leftStart + Number(pair.left_index || 0);
      const rightCompareIndex = rightStart + Number(pair.right_index || 0);
      _appendHistoryCompareRowPair(
        leftPane,
        rightPane,
        _renderHistoryComparePaneRow(leftLine, {
          sideLabel: 'A',
          signClass: 'history-compare-line-removed',
          rowClass: 'is-replace',
          segments: segments.left,
          limits,
          side: 'a',
          compareLineIndex: leftCompareIndex,
          anchorItems: anchorMap?.a?.get(leftCompareIndex) || [],
        }),
        _renderHistoryComparePaneRow(rightLine, {
          sideLabel: 'B',
          signClass: 'history-compare-line-added',
          rowClass: 'is-replace',
          segments: segments.right,
          limits,
          side: 'b',
          compareLineIndex: rightCompareIndex,
          anchorItems: anchorMap?.b?.get(rightCompareIndex) || [],
        }),
        'changed',
      );
    } else if (event.type === 'left') {
      const leftCompareIndex = leftStart + Number(event.leftIndex || 0);
      _appendHistoryCompareRowPair(
        leftPane,
        rightPane,
        _renderHistoryComparePaneRow(leftLines[event.leftIndex] || {}, {
          sideLabel: '-',
          signClass: 'history-compare-line-removed',
          rowClass: 'is-delete',
          limits,
          side: 'a',
          compareLineIndex: leftCompareIndex,
          anchorItems: anchorMap?.a?.get(leftCompareIndex) || [],
        }),
        _renderHistoryCompareSpacer(),
        'removed',
      );
    } else if (event.type === 'right') {
      const rightCompareIndex = rightStart + Number(event.rightIndex || 0);
      _appendHistoryCompareRowPair(
        leftPane,
        rightPane,
        _renderHistoryCompareSpacer(),
        _renderHistoryComparePaneRow(rightLines[event.rightIndex] || {}, {
          sideLabel: '+',
          signClass: 'history-compare-line-added',
          rowClass: 'is-insert',
          limits,
          side: 'b',
          compareLineIndex: rightCompareIndex,
          anchorItems: anchorMap?.b?.get(rightCompareIndex) || [],
        }),
        'added',
      );
    }
  });
}

function _appendHistoryCompareOneSidedHunk(leftPane, rightPane, hunk, data, anchorMap) {
  const limits = data.limits || {};
  const op = hunk.op;
  const lines = op === 'insert' ? (hunk.right?.lines || []) : (hunk.left?.lines || []);
  const leftStart = _historyCompareNumber(hunk.left?.start, 0);
  const rightStart = _historyCompareNumber(hunk.right?.start, 0);
  lines.forEach((line, index) => {
    const leftCompareIndex = leftStart + index;
    const rightCompareIndex = rightStart + index;
    _appendHistoryCompareRowPair(
      leftPane,
      rightPane,
      op === 'delete'
        ? _renderHistoryComparePaneRow(line, {
            sideLabel: '-',
            signClass: 'history-compare-line-removed',
            rowClass: 'is-delete',
            limits,
            side: 'a',
            compareLineIndex: leftCompareIndex,
            anchorItems: anchorMap?.a?.get(leftCompareIndex) || [],
          })
        : _renderHistoryCompareSpacer(),
      op === 'insert'
        ? _renderHistoryComparePaneRow(line, {
            sideLabel: '+',
            signClass: 'history-compare-line-added',
            rowClass: 'is-insert',
            limits,
            side: 'b',
            compareLineIndex: rightCompareIndex,
            anchorItems: anchorMap?.b?.get(rightCompareIndex) || [],
          })
        : _renderHistoryCompareSpacer(),
      op === 'insert' ? 'added' : 'removed',
    );
  });
}

function _appendHistoryCompareOmittedRows(leftPane, rightPane, hunk) {
  const omitted = hunk.lines_omitted || {};
  if (!Number(omitted.total || 0)) return;
  const row = document.createElement('div');
  row.className = 'history-compare-row history-compare-row-omitted';
  row.textContent = `${Number(omitted.total).toLocaleString()} changed line(s) omitted in this block.`;
  _appendHistoryCompareRowPair(leftPane, rightPane, row.cloneNode(true), row);
}

function _historyCompareChangeBucketIndexes(data = {}) {
  const buckets = Array.isArray(data.density_buckets) ? data.density_buckets : [];
  return buckets
    .map((bucket, index) => ({ bucket, index, tone: _historyCompareBucketTone(bucket) }))
    .filter(item => ['changed', 'added', 'removed'].includes(item.tone))
    .map(item => item.index);
}

function _historyCompareGoToChangeBucket(data, direction) {
  const targets = _historyCompareRenderedChangeTargets();
  if (!targets.length) return false;
  const currentIndex = data._activeChangeTargetPair
    ? targets.findIndex(item => (item.row.dataset.comparePair || '') === data._activeChangeTargetPair)
    : -1;
  const nextPosition = direction < 0
    ? (currentIndex <= 0 ? targets.length - 1 : currentIndex - 1)
    : (currentIndex < 0 || currentIndex >= targets.length - 1 ? 0 : currentIndex + 1);
  const target = targets[nextPosition];
  data._activeChangeTargetPair = target.row.dataset.comparePair || '';
  data._activeChangeBucketIndex = Number(target.index);
  return _historyCompareScrollToRow(target.row, { emit: false });
}

function _renderHistoryCompareNav(data = {}) {
  const nav = document.createElement('div');
  nav.className = 'history-compare-nav';
  const makeButton = (label, direction) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn-secondary btn-compact history-compare-nav-btn';
    button.textContent = label;
    button.disabled = !_historyCompareChangeBucketIndexes(data).length;
    button.addEventListener('click', () => _historyCompareGoToChangeBucket(data, direction));
    if (typeof bindPressable === 'function') bindPressable(button);
    return button;
  };
  nav.appendChild(makeButton('Prev change', -1));
  nav.appendChild(makeButton('Next change', 1));
  return nav;
}

function _renderHistoryCompareMinimap(buckets = []) {
  const rail = document.createElement('div');
  rail.className = 'history-compare-minimap';
  rail.setAttribute('aria-hidden', 'true');
  (Array.isArray(buckets) ? buckets : []).forEach((bucket, index) => {
    const segment = document.createElement('div');
    const tone = _historyCompareBucketTone(bucket);
    segment.className = `history-compare-minimap-segment is-${tone}`;
    segment.dataset.bucketIndex = String(index);
    segment.dataset.bucketStart = String(bucket.start ?? 0);
    segment.dataset.bucketEnd = String(bucket.end ?? 0);
    segment.addEventListener('click', () => _historyCompareScrollToBucket(bucket));
    rail.appendChild(segment);
  });
  return rail;
}

function _historyCompareApplyViewMode(mode, data) {
  const nextMode = _historyCompareCoerceViewMode(mode);
  data._compareViewModeRaw = nextMode;
  if (typeof applyCompareViewModePreference === 'function') applyCompareViewModePreference(nextMode);
  _renderHistoryComparison(data);
}

function _historyCompareApplyContext(mode, data) {
  const nextMode = _historyCompareCoerceContext(mode);
  data._compareContext = nextMode;
  if (typeof applyCompareContextPreference === 'function') applyCompareContextPreference(nextMode);
  _renderHistoryComparison(data);
}

function _closeHistoryCompareActionMenus(except = null) {
  document.querySelectorAll('.history-compare-actions-menu-wrap.open').forEach((wrap) => {
    if (except && wrap === except) return;
    wrap.classList.remove('open');
    wrap.querySelector('.history-compare-actions-trigger')?.setAttribute('aria-expanded', 'false');
    const menu = wrap._portaledMenu;
    if (menu && typeof unportalDropdownMenu === 'function') unportalDropdownMenu(menu);
    wrap._portaledMenu = null;
  });
}

function _renderHistoryCompareDisplayControls(data, viewMode) {
  const controls = document.createElement('div');
  controls.className = 'history-compare-controls';

  const rawMode = _historyCompareCoerceViewMode(data._compareViewModeRaw || _historyCompareStoredViewMode());
  const resolvedMode = _historyCompareResolveViewMode(rawMode);
  const viewSelect = document.createElement('select');
  viewSelect.className = 'form-select history-compare-view-select';
  viewSelect.setAttribute('aria-label', 'Run comparison view mode');
  viewSelect.dataset.portalMenu = 'true';
  _historyCompareViewModeOptions().forEach(([value, label]) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    viewSelect.appendChild(option);
  });
  viewSelect.value = resolvedMode;
  viewSelect.addEventListener('change', () => _historyCompareApplyViewMode(viewSelect.value, data));
  controls.appendChild(viewSelect);

  const resetHidden = rawMode === 'auto' || rawMode === _historyCompareViewportMode();
  const reset = document.createElement('button');
  reset.type = 'button';
  reset.className = 'btn btn-ghost btn-icon-only history-compare-reset-view';
  reset.setAttribute('aria-label', 'Reset comparison view to default');
  reset.title = 'Reset comparison view to default';
  const resetIcon = document.createElement('span');
  resetIcon.className = 'history-compare-reset-icon';
  resetIcon.setAttribute('aria-hidden', 'true');
  resetIcon.textContent = '↻';
  reset.appendChild(resetIcon);
  reset.hidden = resetHidden;
  reset.classList.toggle('u-hidden', resetHidden);
  reset.addEventListener('click', () => _historyCompareApplyViewMode('auto', data));
  controls.appendChild(reset);

  const contextControls = _renderHistoryCompareContextControls(data, viewMode);
  if (contextControls) controls.appendChild(contextControls);

  if (typeof enhanceAppSelects === 'function') {
    enhanceAppSelects(controls);
  }
  return controls;
}

function _renderHistoryCompareContextControls(data, viewMode) {
  if (viewMode === 'changes_only' || viewMode === 'findings_only') return null;
  const selected = _historyCompareCoerceContext(data._compareContext || _historyCompareStoredContext());
  const contextSelect = document.createElement('select');
  contextSelect.className = 'form-select history-compare-context-select';
  contextSelect.setAttribute('aria-label', 'Run comparison context');
  contextSelect.dataset.portalMenu = 'true';
  [
    ['3', 'Context: ±3'],
    ['10', 'Context: ±10'],
    ['all', 'Context: All'],
  ].forEach(([value, label]) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    contextSelect.appendChild(option);
  });
  contextSelect.value = selected;
  contextSelect.addEventListener('change', () => _historyCompareApplyContext(contextSelect.value, data));
  return contextSelect;
}

function _historyCompareSummaryText(data, deltas = {}) {
  const totalsForCopy = data.totals || {};
  return [
    `Compare: ${data.left.command} -> ${data.right.command}`,
    `Exit: ${deltas.exit_code?.left ?? 'n/a'} -> ${deltas.exit_code?.right ?? 'n/a'}`,
    `Lines: ${_compareFormatDelta(deltas.output_lines?.delta || 0)}`,
    `Findings: ${_compareFormatDelta(deltas.findings?.delta || 0)}`,
    `Changed: ${Number(totalsForCopy.changed_line_count || 0)}`,
    `Added: ${Number(totalsForCopy.added_line_count || 0)}`,
    `Removed: ${Number(totalsForCopy.removed_line_count || 0)}`,
    `Unchanged: ${Number(totalsForCopy.equal_line_count || 0)}`,
  ].join('\n');
}

function _renderHistoryCompareActionsMenu(data, deltas = {}) {
  const wrap = document.createElement('div');
  wrap.className = 'history-compare-actions-menu-wrap save-menu-wrap save-menu-down';
  const trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'btn btn-secondary btn-compact history-compare-actions-trigger';
  trigger.textContent = 'Actions';
  trigger.setAttribute('aria-haspopup', 'menu');
  trigger.setAttribute('aria-expanded', 'false');
  const menu = document.createElement('div');
  menu.className = 'history-compare-actions-menu save-menu dropdown-surface';
  menu.setAttribute('role', 'menu');
  const addItem = (label, onClick) => {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'dropdown-item dropdown-item-compact';
    item.setAttribute('role', 'menuitem');
    item.textContent = label;
    item.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      _closeHistoryCompareActionMenus();
      onClick(item);
    });
    menu.appendChild(item);
    return item;
  };
  addItem('Restore A', () => {
    restoreHistoryRunIntoTab(data.left, { hidePanelOnSuccess: false })
      .then(() => closeHistoryCompareOverlay())
      .catch(() => showToast('Failed to restore run', 'error'));
  });
  addItem('Restore B', () => {
    restoreHistoryRunIntoTab(data.right, { hidePanelOnSuccess: false })
      .then(() => closeHistoryCompareOverlay())
      .catch(() => showToast('Failed to restore run', 'error'));
  });
  addItem('Restore Both', (item) => {
    item.disabled = true;
    _restoreBothHistoryCompareRuns(data.left, data.right)
      .then(() => closeHistoryCompareOverlay())
      .catch(err => {
        item.disabled = false;
        if (err && err.message === 'not enough tab capacity') return;
        showToast('Failed to restore both runs', 'error');
      });
  });
  addItem('Copy summary', () => {
    copyTextToClipboard(_historyCompareSummaryText(data, deltas))
      .then(() => showToast('Comparison summary copied'))
      .catch(() => showToast('Failed to copy summary', 'error'));
  });
  wrap.dataset.portalMenu = 'true';
  trigger.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    const open = !wrap.classList.contains('open');
    _closeHistoryCompareActionMenus(open ? wrap : null);
    wrap.classList.toggle('open', open);
    trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open && typeof portalDropdownMenu === 'function') {
      portalDropdownMenu(wrap, trigger, menu);
      wrap._portaledMenu = menu;
    } else if (!open && typeof unportalDropdownMenu === 'function') {
      unportalDropdownMenu(menu);
      wrap._portaledMenu = null;
    }
  });
  if (typeof bindPressable === 'function') bindPressable(trigger);
  wrap.append(trigger, menu);
  return wrap;
}

function _renderHistoryCompareSplitPane(data, options = {}) {
  const viewMode = options.viewMode || 'side_by_side';
  const wrap = document.createElement('div');
  wrap.className = `history-compare-split is-${viewMode.replace(/_/g, '-')}`;
  wrap.dataset.compareViewMode = viewMode;
  const anchorMap = _historyCompareBuildAnchorMap(data);
  const leftPane = document.createElement('div');
  leftPane.className = 'history-compare-pane nice-scroll';
  leftPane.dataset.side = 'a';
  const rightPane = document.createElement('div');
  rightPane.className = 'history-compare-pane nice-scroll';
  rightPane.dataset.side = 'b';
  const renderPanes = () => {
    leftPane.replaceChildren();
    rightPane.replaceChildren();
    _historyCompareRowPairSequence = 0;
    _historyCompareUnitSequence = 0;
    const leftTitle = document.createElement('div');
    leftTitle.className = 'history-compare-pane-title';
    leftTitle.textContent = 'Run A';
    const rightTitle = document.createElement('div');
    rightTitle.className = 'history-compare-pane-title';
    rightTitle.textContent = 'Run B';
    leftPane.appendChild(leftTitle);
    rightPane.appendChild(rightTitle);
    (Array.isArray(data.hunks) ? data.hunks : []).forEach(hunk => {
      if (!hunk || !hunk.op) return;
      if (hunk.op === 'equal') {
        _appendHistoryCompareEqualHunk(leftPane, rightPane, hunk, data, renderPanes, anchorMap, {
          contextLimit: options.contextLimit,
          changesOnly: viewMode === 'changes_only',
        });
      }
      else if (hunk.op === 'replace') _appendHistoryCompareReplaceHunk(leftPane, rightPane, hunk, data, anchorMap);
      else if (hunk.op === 'insert' || hunk.op === 'delete') _appendHistoryCompareOneSidedHunk(leftPane, rightPane, hunk, data, anchorMap);
      _appendHistoryCompareOmittedRows(leftPane, rightPane, hunk);
    });
    if (Number(data.truncated?.hunks_omitted || 0) > 0) {
      const placeholder = document.createElement('div');
      placeholder.className = 'history-compare-row history-compare-row-omitted history-compare-surplus';
      placeholder.textContent = `${Number(data.truncated.hunks_omitted).toLocaleString()} additional changed hunk(s) omitted.`;
      _appendHistoryCompareRowPair(leftPane, rightPane, placeholder.cloneNode(true), placeholder);
    }
    _scheduleHistoryCompareRowPairHeightSync(wrap);
  };
  renderPanes();
  if (!(typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode())) {
    let syncing = false;
    const sync = (source, target) => {
      if (syncing || !source || !target) return;
      syncing = true;
      const raf = typeof requestAnimationFrame === 'function'
        ? requestAnimationFrame
        : callback => setTimeout(callback, 0);
      raf(() => {
        target.scrollTop = source.scrollTop;
        syncing = false;
      });
    };
    leftPane.addEventListener('scroll', () => sync(leftPane, rightPane));
    rightPane.addEventListener('scroll', () => sync(rightPane, leftPane));
  }
  wrap.appendChild(leftPane);
  wrap.appendChild(rightPane);
  wrap.appendChild(_renderHistoryCompareMinimap(data.density_buckets || []));
  _bindHistoryCompareRowPairHeightSync(wrap);
  return wrap;
}

function _historyCompareCountsSubtitle(totals = {}) {
  const total = Number(totals.left_total_lines || 0);
  const unchanged = Number(totals.equal_line_count || 0);
  const changed = Number(totals.changed_line_count || 0);
  const added = Number(totals.added_line_count || 0);
  const removed = Number(totals.removed_line_count || 0);
  return `${total.toLocaleString()} lines · ${unchanged.toLocaleString()} unchanged · `
    + `${changed.toLocaleString()} changed · ${added.toLocaleString()} added · `
    + `${removed.toLocaleString()} removed`;
}

function _renderHistoryCompareOmittedNote(truncated = {}) {
  const omitted = _historyCompareOmittedTotal(truncated);
  if (!omitted) return null;
  const note = document.createElement('div');
  note.className = 'history-compare-counts-note';
  note.textContent = `${omitted.toLocaleString()} changed line(s) or hunk(s) omitted by compare limits.`;
  return note;
}

function _historyCompareObjectText(item, kind) {
  if (!item || typeof item !== 'object') return '';
  if (kind === 'artifact') {
    return item.workspace_path || item.display_name || item.id || '';
  }
  return item.title || item.raw_line || item.id || '';
}

function _historyCompareObjectMeta(item, kind) {
  if (!item || typeof item !== 'object') return '';
  if (kind === 'artifact') {
    return [
      item.kind || 'file',
      item.byte_size !== undefined && item.byte_size !== null ? `${Number(item.byte_size).toLocaleString()} bytes` : '',
      item.detected_by || '',
    ].filter(Boolean).join(' · ');
  }
  return [
    item.severity || '',
    item.review_state || '',
    item.line_number !== undefined && item.line_number !== null ? `line ${item.line_number}` : '',
  ].filter(Boolean).join(' · ');
}

function _renderHistoryCompareObjectSection(title, items, kind, sign) {
  const safeItems = Array.isArray(items) ? items : [];
  const section = document.createElement('details');
  section.className = 'history-compare-lines history-compare-object-section';
  section.open = true;
  const summary = document.createElement('summary');
  summary.textContent = `${title} (${safeItems.length})`;
  section.appendChild(summary);
  if (!safeItems.length) {
    const empty = document.createElement('div');
    empty.className = 'history-compare-empty';
    empty.textContent = `No ${title.toLowerCase()}.`;
    section.appendChild(empty);
    return section;
  }
  const list = document.createElement('div');
  list.className = 'history-compare-line-list';
  safeItems.forEach(item => {
    const compareLineIndex = _historyCompareNumber(item?.compare_line_index);
    const compareSide = sign === '+' ? 'b' : 'a';
    const row = compareLineIndex === null ? document.createElement('div') : document.createElement('button');
    if (row.tagName === 'BUTTON') {
      row.type = 'button';
      row.addEventListener('click', () => {
        _historyCompareScrollToLine(compareSide, compareLineIndex, { emit: true });
      });
      if (typeof bindPressable === 'function') bindPressable(row);
    }
    row.className = `history-compare-line history-compare-object-row${compareLineIndex === null ? '' : ' control-row'}`;
    row.dataset.objectKind = kind;
    row.dataset.compareSide = compareSide;
    if (compareLineIndex !== null) {
      row.dataset.compareLineIndex = String(compareLineIndex);
      row.classList.add('is-anchorable');
    }
    const mark = document.createElement('span');
    mark.className = sign === '+' ? 'history-compare-line-added' : 'history-compare-line-removed';
    mark.textContent = sign;
    row.appendChild(mark);
    const content = document.createElement('div');
    content.className = 'history-compare-object-content';
    const primary = document.createElement('code');
    primary.textContent = _historyCompareObjectText(item, kind);
    content.appendChild(primary);
    const meta = _historyCompareObjectMeta(item, kind);
    if (meta) {
      const metaEl = document.createElement('div');
      metaEl.className = 'history-compare-object-meta';
      metaEl.textContent = meta;
      content.appendChild(metaEl);
    }
    row.appendChild(content);
    list.appendChild(row);
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
  const rawViewMode = _historyCompareCoerceViewMode(data._compareViewModeRaw || _historyCompareStoredViewMode());
  const viewMode = _historyCompareResolveViewMode(rawViewMode);
  const contextMode = _historyCompareCoerceContext(data._compareContext || _historyCompareStoredContext());
  data._compareViewModeRaw = rawViewMode;
  data._compareContext = contextMode;
  const totals = data.totals || {};
  const changedOutputCount = _historyCompareTotalChangedLines(totals);
  subtitle.textContent = viewMode === 'findings_only'
    ? 'Changed findings and artifacts'
    : (changedOutputCount ? _historyCompareCountsSubtitle(totals) : 'Changed findings and artifacts');

  const runs = document.createElement('div');
  runs.className = 'history-compare-run-grid';
  runs.appendChild(_historyCompareRunCard(data.left, 'Run A'));
  runs.appendChild(_historyCompareRunCard(data.right, 'Run B'));
  body.appendChild(runs);

  const deltas = data.deltas || {};
  const metrics = document.createElement('div');
  metrics.className = 'history-compare-metrics';
  if (deltas.exit_code) {
    metrics.appendChild(_compareMetricCell(
      'Exit',
      deltas.exit_code_changed ? `${deltas.exit_code.left} -> ${deltas.exit_code.right}` : `unchanged · ${deltas.exit_code?.right ?? 'n/a'}`,
      deltas.exit_code_changed ? 'is-changed' : '',
    ));
  }
  if (deltas.duration_seconds) {
    metrics.appendChild(_compareMetricCell('Duration', _compareFormatDelta(deltas.duration_seconds.delta || 0, 's')));
  }
  if (deltas.output_lines) {
    metrics.appendChild(_compareMetricCell('Lines', _compareFormatDelta(deltas.output_lines.delta || 0)));
  }
  if (deltas.findings) {
    metrics.appendChild(_compareMetricCell('Findings', _compareFormatDelta(deltas.findings.delta || 0)));
  }
  if (data.left && data.right && (
    Number.isFinite(Number(data.left.persisted_finding_count))
    || Number.isFinite(Number(data.right.persisted_finding_count))
  )) {
    metrics.appendChild(_compareMetricCell(
      'Stored findings',
      _compareFormatDelta(Number(data.right.persisted_finding_count || 0) - Number(data.left.persisted_finding_count || 0)),
    ));
  }
  if (data.left && data.right && (
    Number.isFinite(Number(data.left.artifact_count))
    || Number.isFinite(Number(data.right.artifact_count))
  )) {
    metrics.appendChild(_compareMetricCell(
      'Artifacts',
      _compareFormatDelta(Number(data.right.artifact_count || 0) - Number(data.left.artifact_count || 0)),
    ));
  }
  body.appendChild(metrics);
  const omittedNote = _renderHistoryCompareOmittedNote(data.truncated || {});
  if (omittedNote) body.appendChild(omittedNote);

  const findingsTruncated = !!(
    data.truncated
    && data.truncated.findings
    && (data.truncated.findings.left || data.truncated.findings.right)
  );
  const artifactsTruncated = !!(
    data.truncated
    && data.truncated.artifacts
    && (data.truncated.artifacts.left || data.truncated.artifacts.right)
  );
  if (data.truncated && (
    data.truncated.left
    || data.truncated.right
    || data.truncated.changed_lines
    || findingsTruncated
    || artifactsTruncated
  )) {
    const note = document.createElement('div');
    note.className = 'history-compare-truncation';
    const limit = Number(data.truncated.item_limit || 0);
    note.textContent = findingsTruncated || artifactsTruncated
      ? `Comparison is partial because project findings or artifacts exceeded the per-run compare limit${limit ? ` of ${limit.toLocaleString()} items` : ''}.`
      : 'Comparison is partial because one or both outputs were truncated or the changed-line list hit its display limit.';
    body.appendChild(note);
  }

  const toolbar = document.createElement('div');
  toolbar.className = 'history-compare-toolbar';
  toolbar.appendChild(_renderHistoryCompareDisplayControls(data, viewMode));
  toolbar.appendChild(_renderHistoryCompareActionsMenu(data, deltas));
  toolbar.appendChild(_renderHistoryCompareNav(data));
  body.appendChild(toolbar);
  if (viewMode !== 'findings_only') {
    body.appendChild(_renderHistoryCompareSplitPane(data, {
      viewMode,
      contextLimit: _historyCompareContextLimit(contextMode),
    }));
  }

  const objects = data.objects || {};
  const findingObjects = objects.findings || {};
  const artifactObjects = objects.artifacts || {};
  const addedFindings = Array.isArray(findingObjects.added) ? findingObjects.added : [];
  const removedFindings = Array.isArray(findingObjects.removed) ? findingObjects.removed : [];
  const addedArtifacts = Array.isArray(artifactObjects.added) ? artifactObjects.added : [];
  const removedArtifacts = Array.isArray(artifactObjects.removed) ? artifactObjects.removed : [];
  if (addedFindings.length) body.appendChild(_renderHistoryCompareObjectSection('Added findings', addedFindings, 'finding', '+'));
  if (removedFindings.length) body.appendChild(_renderHistoryCompareObjectSection('Removed findings', removedFindings, 'finding', '-'));
  if (addedArtifacts.length) body.appendChild(_renderHistoryCompareObjectSection('Added artifacts', addedArtifacts, 'artifact', '+'));
  if (removedArtifacts.length) body.appendChild(_renderHistoryCompareObjectSection('Removed artifacts', removedArtifacts, 'artifact', '-'));
  if (
    !changedOutputCount
    && !addedFindings.length && !removedFindings.length && !addedArtifacts.length && !removedArtifacts.length
  ) {
    const empty = document.createElement('div');
    empty.className = 'history-compare-empty';
    empty.textContent = 'No changed output, findings, or artifacts.';
    body.appendChild(empty);
  }
}

function fetchAndRenderHistoryComparison(leftId, rightId, options = {}) {
  if (!leftId || !rightId) return;
  _openHistoryCompareOverlay();
  const body = document.querySelector('#history-compare-body');
  if (body) {
    body.replaceChildren();
    const loading = document.createElement('div');
    loading.className = 'history-compare-empty';
    loading.textContent = 'Comparing runs...';
    body.appendChild(loading);
  }
  const url = options.url || `/history/compare?left=${encodeURIComponent(leftId)}&right=${encodeURIComponent(rightId)}`;
  apiFetch(url)
    .then(resp => resp.json().catch(() => ({})).then(data => {
      if (!resp.ok || data.error) {
        const err = new Error(data.error || `Compare request failed (${resp.status || 'unknown'})`);
        err.compareRequestError = true;
        throw err;
      }
      return data;
    }))
    .then(data => {
      _renderHistoryComparison(data);
    })
    .catch(err => {
      if (typeof console !== 'undefined' && typeof console.error === 'function') {
        console.error('[history compare] failed', err);
      }
      if (_historyCompareState && _historyCompareState.source) _renderHistoryCompareLauncher();
      const detail = err && err.compareRequestError && err.message ? `: ${err.message}` : '';
      showToast(`Failed to compare runs${detail}`, 'error');
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

function _scrollHistoryHighlightIntoView(out, line) {
  if (!out || !line || typeof out.contains !== 'function' || !out.contains(line)) return false;
  if (
    typeof out.getBoundingClientRect !== 'function'
    || typeof line.getBoundingClientRect !== 'function'
  ) return false;
  const outRect = out.getBoundingClientRect();
  const lineRect = line.getBoundingClientRect();
  const targetTop = Number(lineRect.top) - Number(outRect.top);
  const lineHeight = Number(lineRect.height) || Number(line.offsetHeight) || 0;
  const outHeight = Number(out.clientHeight) || Number(outRect.height) || 0;
  if (!Number.isFinite(targetTop) || outHeight <= 0) return false;
  out.scrollTop += targetTop - (outHeight / 2) + (lineHeight / 2);
  return true;
}

function _highlightRestoredHistoryLine(tabId, { lineNumber = null, lineIndex = null } = {}) {
  const out = typeof getOutput === 'function' ? getOutput(tabId) : null;
  if (!out) return false;
  const cssEscape = value => (
    typeof CSS !== 'undefined' && CSS && typeof CSS.escape === 'function'
      ? CSS.escape(String(value))
      : String(value).replace(/"/g, '\\"')
  );
  const normalizedLineNumber = Number(lineNumber || 0);
  const normalizedLineIndex = Number(lineIndex);
  const selector = normalizedLineNumber > 0
    ? `.line[data-line-number="${cssEscape(normalizedLineNumber)}"]`
    : (Number.isInteger(normalizedLineIndex) ? `.line[data-line-index="${cssEscape(normalizedLineIndex)}"]` : '');
  if (!selector) return false;
  const line = out.querySelector(selector);
  if (!line) return false;
  out.querySelectorAll('.line.history-source-highlight').forEach(node => {
    node.classList.remove('history-source-highlight');
  });
  line.classList.add('history-source-highlight');
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  if (tab) {
    tab.followOutput = false;
  }
  if (!_scrollHistoryHighlightIntoView(out, line) && typeof line.scrollIntoView === 'function') {
    line.scrollIntoView({ block: 'center' });
  }
  return true;
}

function _historyHasPendingOutput(tabId) {
  return typeof hasPendingOutputBatch === 'function' && hasPendingOutputBatch(tabId);
}

function _scheduleRestoredHistoryLineHighlight(tabId, options) {
  const startedAt = Date.now();
  const runFinalLayoutPasses = () => {
    const run = () => _highlightRestoredHistoryLine(tabId, options);
    if (typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(() => window.requestAnimationFrame(run));
    }
    window.setTimeout(run, 48);
    window.setTimeout(run, 120);
    window.setTimeout(run, 300);
  };
  const retryUntilOutputSettles = () => {
    const highlighted = _highlightRestoredHistoryLine(tabId, options);
    const pending = _historyHasPendingOutput(tabId);
    if ((!highlighted || pending) && Date.now() - startedAt < 2000) {
      window.setTimeout(retryUntilOutputSettles, pending ? 32 : 50);
      return;
    }
    runFinalLayoutPasses();
  };
  window.setTimeout(retryUntilOutputSettles, 0);
}

function _suppressHistoryRestoreStatusPeek(tabId) {
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  if (!tab) return;
  tab.suppressStatusMonitorPeekHold = true;
  const setTimer = typeof window !== 'undefined' && typeof window.setTimeout === 'function'
    ? window.setTimeout.bind(window)
    : (typeof setTimeout === 'function' ? setTimeout : null);
  if (!setTimer) return;
  setTimer(() => {
    const live = typeof getTab === 'function' ? getTab(tabId) : null;
    if (live) delete live.suppressStatusMonitorPeekHold;
  }, 0);
}

function restoreHistoryRunIntoTab(run, {
  targetTabId = null,
  hidePanelOnSuccess = true,
  highlightLineNumber = null,
  highlightLineIndex = null,
} = {}) {
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
      _suppressHistoryRestoreStatusPeek(tabId);
      if (typeof setTabStatus === 'function') {
        setTabStatus(tabId, fullRun.exit_code === 0 ? 'ok' : 'fail');
      }
      if (typeof hideTabKillBtn === 'function') hideTabKillBtn(tabId);
      if (hidePanelOnSuccess) hideHistoryPanel();
      if (highlightLineNumber || Number.isInteger(highlightLineIndex)) {
        _scheduleRestoredHistoryLineHighlight(tabId, {
          lineNumber: highlightLineNumber,
          lineIndex: highlightLineIndex,
        });
      }
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
window.openHistoryRunDetails = openHistoryRunDetails;
window.closeHistoryRunOverlay = closeHistoryRunOverlay;
window.isHistoryRunOverlayOpen = isHistoryRunOverlayOpen;

function refreshHistoryPanel() {
  // The panel is populated on demand so we always fetch the latest persisted
  // history instead of assuming the in-memory tab state is authoritative.
  _ensureHistoryProjectFilterOptions().catch(() => {});
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
        bindPressable(entry.querySelector('[data-action="edit-metadata"]'), {
          refocusComposer: false,
          onActivate: () => {
            _historyEditEntityMetadata('snapshot', item);
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

      // Click anywhere on the entry (except buttons) to inspect the run. The
      // modal keeps restore and re-run affordances available without hiding
      // structured findings behind project-only views.
      entry.addEventListener('click', e => {
        if (e.target.closest('[data-action]')) return;
        openHistoryRunDetails(run);
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

      bindPressable(entry.querySelector('[data-action="copy-command"]'), {
        onActivate: () => {
          _closeHistoryActionMenus();
          copyTextToClipboard(run.command)
            .then(() => showToast('Command copied'))
            .catch(() => showToast('Failed to copy command', 'error'));
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

      bindPressable(entry.querySelector('[data-action="history-menu"]'), {
        refocusComposer: false,
        onActivate: (event) => {
          event.preventDefault();
          event.stopPropagation();
          const wrap = entry.querySelector('.history-action-menu-wrap');
          if (!wrap) return;
          const open = !wrap.classList.contains('open');
          _closeHistoryActionMenus(open ? wrap : null);
          wrap.classList.toggle('open', open);
          entry.querySelector('[data-action="history-menu"]')?.setAttribute('aria-expanded', open ? 'true' : 'false');
          if (open) _positionHistoryActionMenu(wrap);
          else _resetHistoryActionMenuPosition(wrap);
        },
      });
      bindPressable(entry.querySelector('[data-action="permalink"]'), {
        onActivate: () => {
          _closeHistoryActionMenus();
          const url = `${location.origin}/history/${run.id}`;
          shareUrl(url).catch(() => showToast('Failed to copy link', 'error'));
          if (!_historyActionKeepsPanelOpen('permalink')) hideHistoryPanel();
        },
      });
      bindPressable(entry.querySelector('[data-action="edit-metadata"]'), {
        refocusComposer: false,
        onActivate: () => {
          _closeHistoryActionMenus();
          _historyEditEntityMetadata('run', run);
        },
      });
      bindPressable(entry.querySelector('[data-action="compare"]'), {
        refocusComposer: false,
        onActivate: () => {
          _closeHistoryActionMenus();
          openHistoryCompareLauncher(run);
          if (!_historyActionKeepsPanelOpen('compare')) hideHistoryPanel();
        },
      });
      bindPressable(entry.querySelector('[data-action="add-active-project"]'), {
        onActivate: () => {
          _closeHistoryActionMenus();
          _historyAddRunToActiveProject(run).catch(() => showToast('Failed to add run to active project', 'error'));
        },
      });
      bindPressable(entry.querySelector('[data-action="add-project"]'), {
        refocusComposer: false,
        onActivate: () => {
          _closeHistoryActionMenus();
          _historyAddRunToProject(run).catch(() => showToast('Failed to add run to project', 'error'));
        },
      });
      bindPressable(entry.querySelector('[data-action="copy-run-id"]'), {
        onActivate: () => {
          _closeHistoryActionMenus();
          copyTextToClipboard(run.id)
            .then(() => showToast('Run ID copied'))
            .catch(() => showToast('Failed to copy run ID', 'error'));
        },
      });
      bindPressable(entry.querySelector('[data-action="delete"]'), {
        onActivate: () => {
          _closeHistoryActionMenus();
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

if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
  document.addEventListener('click', (event) => {
    if (event.target && event.target.closest && event.target.closest('.history-action-menu-wrap')) return;
    if (event.target && event.target.closest && event.target.closest('.history-compare-actions-menu-wrap')) return;
    if (event.target && event.target.closest && event.target.closest('.history-run-action-menu-wrap')) return;
    _closeHistoryActionMenus();
    _closeHistoryCompareActionMenus();
    _closeHistoryRunActionMenus();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      _closeHistoryActionMenus();
      _closeHistoryCompareActionMenus();
      _closeHistoryRunActionMenus();
    }
  });
}
if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  window.addEventListener('resize', () => {
    _closeHistoryActionMenus();
    _closeHistoryCompareActionMenus();
    _closeHistoryRunActionMenus();
  });
  window.addEventListener('scroll', () => {
    _closeHistoryActionMenus();
    _closeHistoryCompareActionMenus();
    _closeHistoryRunActionMenus();
  }, true);
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

if (typeof historyProjectFilter !== 'undefined' && historyProjectFilter) {
  historyProjectFilter.addEventListener('focus', () => {
    _ensureHistoryProjectFilterOptions().catch(() => {});
  });
  historyProjectFilter.addEventListener('change', e => {
    _setHistoryFilter('projectId', e.target.value);
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
