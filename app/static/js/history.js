// ── Shared history drawer logic ──
const _historyCore = typeof DarklabHistoryCore !== 'undefined' ? DarklabHistoryCore : null;
const _historyCompareCore = typeof DarklabHistoryCompareCore !== 'undefined' ? DarklabHistoryCompareCore : null;

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
let _historySelection = {
  selectMode: false,
  selected: new Map(),
  visibleRuns: [],
  bulkInFlight: false,
};
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
let _historyCompareRowPairSequence = 0;
let _historyCompareUnitSequence = 0;
let _historyCompareRowHeightFrame = null;
let _historyCompareRowResizeObserver = null;

function _historyCompareCoreCall(name, ...args) {
  const helper = _historyCompareCore && _historyCompareCore[name];
  if (typeof helper !== 'function') throw new Error(`DarklabHistoryCompareCore.${name} is unavailable`);
  return helper(...args);
}

function _compareFormatDate(value) {
  return _historyCompareCoreCall('compareFormatDate', value);
}

function _compareDateGroupLabel(value) {
  return _historyCompareCoreCall('compareDateGroupLabel', value);
}

function _compareFormatDuration(seconds) {
  return _historyCompareCoreCall('compareFormatDuration', seconds);
}

function _compareFormatDelta(value, suffix = '') {
  return _historyCompareCoreCall('compareFormatDelta', value, suffix);
}

function _historyCompareTotalChangedLines(totals = {}) {
  return _historyCompareCoreCall('totalChangedLines', totals);
}

function _historyCompareOmittedTotal(truncated = {}) {
  return _historyCompareCoreCall('omittedTotal', truncated);
}

function _historyCompareLineLimit(limits = {}) {
  return _historyCompareCoreCall('lineLimit', limits);
}

function _historyCompareCoerceViewMode(value) {
  return _historyCompareCoreCall('coerceViewMode', value);
}

function _historyCompareCoerceContext(value) {
  return _historyCompareCoreCall('coerceContext', value);
}

function _historyCompareStoredViewMode() {
  return _historyCompareCoreCall('storedViewMode');
}

function _historyCompareStoredContext() {
  return _historyCompareCoreCall('storedContext');
}

function _historyCompareViewportMode() {
  return _historyCompareCoreCall('viewportMode');
}

function _historyCompareUsesMobileLayout() {
  return _historyCompareCoreCall('usesMobileLayout');
}

function _historyCompareResolveViewMode(value = null) {
  return _historyCompareCoreCall('resolveViewMode', value);
}

function _historyCompareViewModeOptions() {
  return _historyCompareCoreCall('viewModeOptions');
}

function _historyCompareContextLimit(value = null) {
  return _historyCompareCoreCall('contextLimit', value);
}

function _historyCompareNumber(value, fallback = null) {
  return _historyCompareCoreCall('number', value, fallback);
}

function _historyCompareCssEscape(value) {
  return _historyCompareCoreCall('cssEscape', value);
}

function _historyCompareBucketTone(bucket = {}) {
  return _historyCompareCoreCall('bucketTone', bucket);
}

function _historyCompareBuildAnchorMap(data = {}) {
  return _historyCompareCoreCall('buildAnchorMap', data);
}

function _historyCompareAnchorTone(items = []) {
  return _historyCompareCoreCall('anchorTone', items);
}

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
    _historyClearSelection({ render: false });
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

function _historyIsSelectableRun(run) {
  if (!run || String(run.type || 'run') !== 'run') return false;
  return !!run.finished || run.exit_code !== null && typeof run.exit_code !== 'undefined';
}

function _historySelectedRuns() {
  return Array.from(_historySelection.selected.values());
}

function _historyCssEscape(value) {
  if (typeof CSS !== 'undefined' && CSS && typeof CSS.escape === 'function') {
    return CSS.escape(String(value));
  }
  return String(value).replace(/["\\]/g, '\\$&');
}

function _historyClearSelection({ render = true } = {}) {
  _historySelection.selected.clear();
  if (render) _renderHistoryBulkToolbar();
}

function _historyResetSelectionOnClose() {
  _historySelection.selectMode = false;
  _historySelection.selected.clear();
  _historySelection.bulkInFlight = false;
  _historySelection.visibleRuns = [];
  _closeHistoryActionMenus();
  _closeHistoryBulkActionMenu();
  _renderHistoryBulkToolbar();
}

function _historySetSelectMode(enabled, { render = true } = {}) {
  _historySelection.selectMode = !!enabled;
  if (!_historySelection.selectMode) _historySelection.selected.clear();
  if (render) {
    _renderHistoryBulkToolbar();
    refreshHistoryPanel();
  }
}

function _historyToggleRunSelection(run, checked = null) {
  if (!_historyIsSelectableRun(run) || _historySelection.bulkInFlight) return;
  const runId = String(run.id || '');
  if (!runId) return;
  const shouldSelect = checked === null ? !_historySelection.selected.has(runId) : !!checked;
  if (shouldSelect) _historySelection.selected.set(runId, run);
  else _historySelection.selected.delete(runId);
  _renderHistoryBulkToolbar();
  const checkbox = historyList?.querySelector?.(`[data-history-select-run-id="${_historyCssEscape(runId)}"]`);
  if (checkbox) checkbox.checked = _historySelection.selected.has(runId);
}

function _historySelectAllVisibleRuns() {
  if (_historySelection.bulkInFlight) return;
  _historySelection.visibleRuns.forEach((run) => {
    if (_historyIsSelectableRun(run) && run.id) {
      _historySelection.selected.set(String(run.id), run);
    }
  });
  refreshHistoryPanel();
}

function _historySetBulkBusy(busy) {
  _historySelection.bulkInFlight = !!busy;
  _renderHistoryBulkToolbar();
  if (historyList) {
    historyList.querySelectorAll('[data-action], .history-entry-select-row input').forEach((el) => {
      if ('disabled' in el) el.disabled = !!busy;
    });
  }
}

function _historyBulkCountsFromResponse(data) {
  return data && typeof data === 'object' && data.counts && typeof data.counts === 'object'
    ? data.counts
    : {};
}

function _historyBulkToast(message, counts = {}) {
  const hasPartial = Number(counts.rejected || 0) > 0 || Number(counts.not_linked || 0) > 0;
  if (hasPartial) showToast(message, 'success', { label: 'dismiss', onClick: () => {} });
  else showToast(message);
}

function _historyBulkReasonSummary(results = []) {
  if (!Array.isArray(results)) return '';
  const rejected = results.filter(item => item && item.status === 'rejected');
  if (!rejected.length) return '';
  const reasons = rejected.reduce((acc, item) => {
    const reason = String(item.reason || '').trim();
    acc.set(reason, (acc.get(reason) || 0) + 1);
    return acc;
  }, new Map());
  const labels = {
    running: 'still running',
    not_owned: 'not available in this session',
    policy_blocked: 'blocked by policy',
  };
  return Array.from(reasons.entries()).map(([reason, count]) => {
    const label = labels[reason] || 'skipped';
    return `${count} ${label}`;
  }).join(' - ');
}

function _historyBulkResultText(action, projectName, counts = {}) {
  if (action === 'add') {
    const added = Number(counts.added || 0);
    const already = Number(counts.already_linked || 0);
    const rejected = Number(counts.rejected || 0) + Number(counts.not_found || 0);
    const pieces = [`Added ${added} ${added === 1 ? 'run' : 'runs'} to ${projectName}`];
    if (already) pieces.push(`${already} already linked`);
    if (rejected) pieces.push(`${rejected} skipped`);
    return pieces.join(' - ');
  }
  if (action === 'remove') {
    const removed = Number(counts.removed || 0);
    const notLinked = Number(counts.not_linked || 0);
    const rejected = Number(counts.rejected || 0) + Number(counts.not_found || 0);
    const pieces = [`Removed ${removed} ${removed === 1 ? 'run' : 'runs'} from ${projectName}`];
    if (notLinked) pieces.push(`${notLinked} not linked`);
    if (rejected) pieces.push(`${rejected} skipped`);
    return pieces.join(' - ');
  }
  const deleted = Number(counts.deleted || 0);
  const rejected = Number(counts.rejected || 0) + Number(counts.not_found || 0);
  const pieces = [`Deleted ${deleted} ${deleted === 1 ? 'run' : 'runs'}`];
  if (rejected) pieces.push(`${rejected} skipped`);
  return pieces.join(' - ');
}

function _historySelectedRunIds() {
  return _historySelectedRuns().map(run => String(run.id || '')).filter(Boolean);
}

async function _historyRefreshAfterBulk() {
  try {
    await refreshHistoryPanel();
  } catch (_) {
    showToast('Bulk action finished, but history could not refresh. Refresh to see the latest state.', 'error');
  }
}

function _closeHistoryBulkActionMenu() {
  const toolbar = typeof historyBulkToolbar !== 'undefined' ? historyBulkToolbar : null;
  const wrap = toolbar?.querySelector?.('.history-bulk-actions-wrap.open');
  if (!wrap) return;
  wrap.classList.remove('open');
  wrap.querySelector('[data-action="history-bulk-menu"]')?.setAttribute('aria-expanded', 'false');
}

function _historyProjectOptionsForSelectedLinks() {
  const projectsById = new Map();
  _historySelectedRuns().forEach((run) => {
    const links = Array.isArray(run.project_links) ? run.project_links : [];
    links.forEach((link) => {
      const project = typeof _historyProjectFromLink === 'function' ? _historyProjectFromLink(link) : null;
      if (project && project.id) projectsById.set(String(project.id), project);
    });
  });
  return Array.from(projectsById.values()).sort((a, b) => _historyProjectDisplayName(a).localeCompare(
    _historyProjectDisplayName(b),
    undefined,
    { sensitivity: 'base', numeric: true },
  ));
}

async function _historyBulkPostProject(project, action) {
  const runIds = _historySelectedRunIds();
  if (!project || !project.id || !runIds.length) return;
  _historySetBulkBusy(true);
  try {
    const resp = await apiFetch(`/projects/${encodeURIComponent(project.id)}/links`, {
      method: action === 'remove' ? 'DELETE' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entity_type: 'run', entity_ids: runIds, source: 'manual' }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const counts = _historyBulkCountsFromResponse(data);
    const projectName = _historyProjectDisplayName(project) || 'project';
    _historySelection.selected.clear();
    const reasonSummary = _historyBulkReasonSummary(data.results);
    const message = [_historyBulkResultText(action, projectName, counts), reasonSummary].filter(Boolean).join(' - ');
    _historyBulkToast(message, counts);
    if (typeof refreshProjectWorkspace === 'function') {
      try { await refreshProjectWorkspace(); } catch (_) {}
    }
    await _historyRefreshAfterBulk();
  } catch (_) {
    showToast(action === 'remove' ? 'Failed to remove selected runs from project' : 'Failed to add selected runs to project', 'error');
  } finally {
    _historySetBulkBusy(false);
  }
}

async function _historyBulkAddToActiveProject() {
  const project = await _historyLoadActiveProject();
  if (!project || !project.id) {
    showToast('No active project selected', 'error');
    return;
  }
  await _historyBulkPostProject(project, 'add');
}

async function _historyBulkChooseProject(action) {
  const selectedCount = _historySelection.selected.size;
  let projects;
  if (action === 'remove') {
    projects = _historyProjectOptionsForSelectedLinks();
  } else {
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
  }
  if (!projects.length) {
    showToast(action === 'remove' ? 'Selected runs are not linked to any project' : 'No projects available', 'error');
    return;
  }
  const { wrap, select } = _historyProjectPickerContent(projects);
  const help = wrap.querySelector('.history-project-picker-help');
  if (help) {
    help.textContent = action === 'remove'
      ? 'Choose the project to remove selected runs from.'
      : 'Choose a project to link selected runs.';
  }
  const choicePromise = showConfirm({
    body: action === 'remove'
      ? `Remove ${selectedCount} selected ${selectedCount === 1 ? 'run' : 'runs'} from project`
      : `Add ${selectedCount} selected ${selectedCount === 1 ? 'run' : 'runs'} to project`,
    content: wrap,
    tone: null,
    defaultFocus: select,
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: action, label: action === 'remove' ? 'Remove from project' : 'Add to project', role: action === 'remove' ? 'secondary' : 'primary' },
    ],
  });
  if (typeof enhanceAppSelects === 'function') {
    enhanceAppSelects(wrap);
    if (typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode()) {
      wrap.querySelector('.app-select-menu')?.classList.add('dropdown-up');
    }
  }
  const choice = await choicePromise;
  if (choice !== action) return;
  const project = projects.find(item => String(item.id || '') === select.value);
  await _historyBulkPostProject(project, action);
}

async function _historyBulkDeleteSelectedRuns() {
  const runIds = _historySelectedRunIds();
  if (!runIds.length) return;
  const count = runIds.length;
  const choice = await showConfirm({
    body: {
      text: `Delete ${count} selected ${count === 1 ? 'run' : 'runs'}?`,
      note: 'This removes the selected run history and cannot be undone.',
    },
    tone: 'warning',
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'delete', label: 'Delete', role: 'destructive', tone: 'warning' },
    ],
  });
  if (choice !== 'delete') return;
  _historySetBulkBusy(true);
  try {
    const resp = await apiFetch('/history/bulk-delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_ids: runIds }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const counts = _historyBulkCountsFromResponse(data);
    _historySelection.selected.clear();
    const reasonSummary = _historyBulkReasonSummary(data.results);
    const message = [_historyBulkResultText('delete', '', counts), reasonSummary].filter(Boolean).join(' - ');
    _historyBulkToast(message, counts);
    await _historyRefreshAfterBulk();
  } catch (_) {
    showToast('Failed to delete selected runs', 'error');
  } finally {
    _historySetBulkBusy(false);
  }
}

function _historyBuildBulkActionMenu(disabled) {
  const wrap = document.createElement('div');
  wrap.className = 'history-bulk-actions-wrap save-menu-wrap save-menu-down';
  const trigger = document.createElement('button');
  trigger.className = 'history-action-btn btn btn-secondary btn-compact';
  trigger.type = 'button';
  trigger.dataset.action = 'history-bulk-menu';
  trigger.textContent = 'Actions';
  trigger.setAttribute('aria-expanded', 'false');
  trigger.disabled = disabled;
  const menu = document.createElement('div');
  menu.className = 'history-bulk-actions-menu save-menu dropdown-surface';
  const activeProject = typeof getActiveProjectContext === 'function' ? getActiveProjectContext() : null;
  [
    ['bulk-add-active-project', 'add to active project'],
    ['bulk-add-project', 'add to project'],
    ['bulk-remove-project', 'remove from project'],
    ['bulk-delete', 'delete'],
  ].forEach(([action, label]) => {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'dropdown-item dropdown-item-compact';
    item.dataset.action = action;
    item.textContent = label;
    item.disabled = disabled || (action === 'bulk-add-active-project' && !(activeProject && activeProject.id));
    if (action === 'bulk-add-active-project' && !(activeProject && activeProject.id)) {
      item.title = 'Select an active project first.';
    }
    menu.appendChild(item);
  });
  wrap.append(trigger, menu);
  return wrap;
}

function _renderHistoryBulkToolbar() {
  if (typeof historyBulkToolbar === 'undefined' || !historyBulkToolbar) return;
  historyBulkToolbar.replaceChildren();
  const visibleSelectable = _historySelection.visibleRuns.filter(_historyIsSelectableRun);
  const shouldShow = _historySelection.selectMode || visibleSelectable.length > 0;
  historyBulkToolbar.classList.toggle('u-hidden', !shouldShow);
  if (!shouldShow) return;

  const toggleLabel = document.createElement('label');
  toggleLabel.className = 'history-filter-toggle history-bulk-toggle control-row form-control-compact';
  const toggle = document.createElement('input');
  toggle.type = 'checkbox';
  toggle.checked = !!_historySelection.selectMode;
  toggle.disabled = _historySelection.bulkInFlight;
  const toggleText = document.createElement('span');
  toggleText.textContent = 'select';
  toggleLabel.append(toggle, toggleText);
  toggle.addEventListener('change', () => _historySetSelectMode(toggle.checked));
  historyBulkToolbar.appendChild(toggleLabel);

  const count = document.createElement('span');
  count.className = 'history-bulk-count';
  const selectedCount = _historySelection.selected.size;
  count.textContent = `${selectedCount} selected`;
  count.setAttribute('aria-live', 'polite');
  historyBulkToolbar.appendChild(count);

  const allSelected = visibleSelectable.length > 0
    && visibleSelectable.every(run => _historySelection.selected.has(String(run.id || '')));
  const someSelected = visibleSelectable.some(run => _historySelection.selected.has(String(run.id || '')));
  const selectAll = document.createElement('button');
  selectAll.className = 'history-action-btn btn btn-secondary btn-compact';
  selectAll.type = 'button';
  selectAll.textContent = allSelected && someSelected ? 'Selected all' : 'Select all';
  selectAll.disabled = !_historySelection.selectMode || !visibleSelectable.length || _historySelection.bulkInFlight;
  selectAll.setAttribute('aria-pressed', allSelected && someSelected ? 'true' : someSelected ? 'mixed' : 'false');
  selectAll.addEventListener('click', () => _historySelectAllVisibleRuns());
  historyBulkToolbar.appendChild(selectAll);

  const clear = document.createElement('button');
  clear.className = 'history-action-btn btn btn-secondary btn-compact';
  clear.type = 'button';
  clear.textContent = 'Clear';
  clear.disabled = selectedCount === 0 || _historySelection.bulkInFlight;
  clear.addEventListener('click', () => {
    _historyClearSelection({ render: false });
    refreshHistoryPanel();
  });
  historyBulkToolbar.appendChild(clear);

  const actions = _historyBuildBulkActionMenu(selectedCount === 0 || _historySelection.bulkInFlight);
  historyBulkToolbar.appendChild(actions);
  bindPressable(actions.querySelector('[data-action="history-bulk-menu"]'), {
    refocusComposer: false,
    onActivate: (event) => {
      event.preventDefault();
      event.stopPropagation();
      const open = !actions.classList.contains('open');
      actions.classList.toggle('open', open);
      actions.querySelector('[data-action="history-bulk-menu"]')?.setAttribute('aria-expanded', open ? 'true' : 'false');
    },
  });
  bindPressable(actions.querySelector('[data-action="bulk-add-active-project"]'), {
    refocusComposer: false,
    onActivate: () => {
      _closeHistoryBulkActionMenu();
      _historyBulkAddToActiveProject();
    },
  });
  bindPressable(actions.querySelector('[data-action="bulk-add-project"]'), {
    refocusComposer: false,
    onActivate: () => {
      _closeHistoryBulkActionMenu();
      _historyBulkChooseProject('add');
    },
  });
  bindPressable(actions.querySelector('[data-action="bulk-remove-project"]'), {
    refocusComposer: false,
    onActivate: () => {
      _closeHistoryBulkActionMenu();
      _historyBulkChooseProject('remove');
    },
  });
  bindPressable(actions.querySelector('[data-action="bulk-delete"]'), {
    refocusComposer: false,
    onActivate: () => {
      _closeHistoryBulkActionMenu();
      _historyBulkDeleteSelectedRuns();
    },
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
  _historyClearSelection({ render: false });
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
  _historyClearSelection({ render: false });
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
  _historyClearSelection({ render: false });
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


window.openHistoryWithFilters = openHistoryWithFilters;
window.resetHistorySelectionOnClose = _historyResetSelectionOnClose;

function refreshHistoryPanel() {
  // The panel is populated on demand so we always fetch the latest persisted
  // history instead of assuming the in-memory tab state is authoritative.
  _ensureHistoryProjectFilterOptions().catch(() => {});
  _syncHistoryFilterControls();
  _renderHistoryActiveFilters();
  return apiFetch(_buildHistoryRequestUrl()).then(r => r.json()).then(data => {
    historyList.replaceChildren();
    _historyPaging.page = Math.max(1, Number(data.page) || _historyPaging.page || 1);
    _historyPaging.pageSize = Math.max(1, Number(data.page_size) || _historyPaging.pageSize || 1);
    _historyPaging.totalCount = Math.max(0, Number(data.total_count ?? data.items?.length ?? data.runs?.length ?? 0) || 0);
    _historyPaging.pageCount = Math.max(0, Number(data.page_count) || 0);
    _historyPaging.hasPrev = !!data.has_prev;
    _historyPaging.hasNext = !!data.has_next;
    const visibleItems = _applyHistoryClientFilters(Array.isArray(data.items) ? data.items : data.runs);
    _historySelection.visibleRuns = visibleItems.filter(item => item && String(item.type || 'run') === 'run');
    _renderHistoryBulkToolbar();
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
            copySnapshotLink(item).catch(() => showToast('Failed to copy link', 'error'));
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
      const selectable = _historyIsSelectableRun(run);
      const selected = _historySelection.selected.has(String(run.id || ''));
      const entry = _createHistoryEntry(run, isStarred, {
        selectMode: _historySelection.selectMode,
        selectable,
        selected,
      });

      // Click anywhere on the entry (except buttons) to inspect the run. The
      // modal keeps restore and re-run affordances available without hiding
      // structured findings behind project-only views.
      entry.addEventListener('click', e => {
        if (e.target.closest('[data-action]')) return;
        const renderedForSelection = entry.classList.contains('history-entry-selecting')
          || !!entry.querySelector('[data-action="select-run"]');
        if (_historySelection.selectMode || renderedForSelection) {
          e.preventDefault();
          e.stopImmediatePropagation();
          _historyToggleRunSelection(run);
          return;
        }
        openHistoryRunDetails(run);
      });

      const selectionBox = entry.querySelector('[data-action="select-run"]');
      if (selectionBox) {
        selectionBox.addEventListener('change', e => {
          e.stopPropagation();
          _historyToggleRunSelection(run, e.target.checked);
        });
      }

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
          copyHistoryRunPermalink(run).catch(() => showToast('Failed to copy link', 'error'));
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
      bindPressable(entry.querySelector('[data-action="remove-project"]'), {
        refocusComposer: false,
        onActivate: () => {
          _closeHistoryActionMenus();
          _historyRemoveRunFromProject(run).catch(() => showToast('Failed to remove run from project', 'error'));
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
    if (event.target && event.target.closest && event.target.closest('.history-bulk-actions-wrap')) return;
    if (event.target && event.target.closest && event.target.closest('.history-compare-actions-menu-wrap')) return;
    if (event.target && event.target.closest && event.target.closest('.history-run-action-menu-wrap')) return;
    _closeHistoryActionMenus();
    _closeHistoryBulkActionMenu();
    _closeHistoryCompareActionMenus();
    _closeHistoryRunActionMenus();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      _closeHistoryActionMenus();
      _closeHistoryBulkActionMenu();
      _closeHistoryCompareActionMenus();
      _closeHistoryRunActionMenus();
    }
  });
}
if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  window.addEventListener('resize', () => {
    _closeHistoryActionMenus();
    _closeHistoryBulkActionMenu();
    _closeHistoryCompareActionMenus();
    _closeHistoryRunActionMenus();
  });
  window.addEventListener('scroll', () => {
    _closeHistoryActionMenus();
    _closeHistoryBulkActionMenu();
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
