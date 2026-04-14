// ── Shared history/permalink logic ──
// Stored in localStorage as a JSON array of command strings.
// Stars float starred items to the top of both the chips row and history panel.

function _getStarred() {
  try { return new Set(JSON.parse(localStorage.getItem('starred') || '[]')); }
  catch { return new Set(); }
}
function _saveStarred(set) {
  localStorage.setItem('starred', JSON.stringify([...set]));
}
function _toggleStar(cmd) {
  const s = _getStarred();
  if (s.has(cmd)) s.delete(cmd); else s.add(cmd);
  _saveStarred(s);
}

// History drawer filters are deliberately simple in the first pass:
// server-backed search/filtering for persisted run attributes, plus a local
// starred-only toggle that continues to use the existing localStorage model.
let _historyFilterRefreshTimer = null;
let _historyFilters = {
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

function _normalizeHistoryFilterValue(value) {
  return typeof value === 'string' ? value.trim() : '';
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
  if (typeof historyRootInput !== 'undefined' && historyRootInput) historyRootInput.value = _historyFilters.commandRoot;
  if (typeof historyExitFilter !== 'undefined' && historyExitFilter) historyExitFilter.value = _historyFilters.exitCode;
  if (typeof historyDateFilter !== 'undefined' && historyDateFilter) historyDateFilter.value = _historyFilters.dateRange;
  if (typeof historyStarredToggle !== 'undefined' && historyStarredToggle) historyStarredToggle.checked = !!_historyFilters.starredOnly;
}

function _historyHasActiveServerFilters() {
  return Boolean(
    _historyFilters.q
    || _historyFilters.commandRoot
    || _historyFilters.exitCode !== 'all'
    || _historyFilters.dateRange !== 'all'
  );
}

function _historyHasAnyFilters() {
  return _historyHasActiveServerFilters() || !!_historyFilters.starredOnly;
}

function _historyCommandRootsFromRuns(runs) {
  const roots = new Set();
  for (const run of Array.isArray(runs) ? runs : []) {
    const root = typeof run === 'string'
      ? run.trim()
      : (run && typeof run.command === 'string' ? run.command.trim().split(/\s+/, 1)[0] : '');
    if (root) roots.add(root);
  }
  return [...roots].sort((a, b) => a.localeCompare(b));
}

function _renderHistoryRootSuggestions(runs) {
  _historyRootSuggestions = _historyCommandRootsFromRuns(runs);
  _historyRefreshRootDropdown();
}

function _appendHistoryCommandEcho(tabId, command) {
  if (typeof appendCommandEcho === 'function') {
    appendCommandEcho(command, tabId);
    return;
  }
  appendLine(command, 'prompt-echo', tabId);
}

function _hideHistoryRootDropdown() {
  if (typeof historyRootDropdown === 'undefined' || !historyRootDropdown) return;
  historyRootDropdown.replaceChildren();
  historyRootDropdown.classList.add('u-hidden');
  _historyRootFiltered = [];
  _historyRootIndex = -1;
}

function _historyRootMatches(query) {
  const value = _normalizeHistoryFilterValue(query).toLowerCase();
  if (!value) return [];
  return _historyRootSuggestions
    .filter(root => root.toLowerCase().startsWith(value))
    .slice(0, 12);
}

function _acceptHistoryRootSuggestion(root) {
  _historyRootSuppressInputOnce = true;
  if (typeof historyRootInput !== 'undefined' && historyRootInput) historyRootInput.value = root;
  _hideHistoryRootDropdown();
  _setHistoryFilter('commandRoot', root);
  if (typeof historyRootInput !== 'undefined' && historyRootInput && typeof historyRootInput.focus === 'function') {
    setTimeout(() => historyRootInput.focus({ preventScroll: true }), 0);
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
    item.className = 'ac-item' + (index === _historyRootIndex ? ' ac-active' : '');
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
  const items = [];
  if (_historyFilters.q) items.push({ key: 'q', label: `search: ${_historyFilters.q}` });
  if (_historyFilters.commandRoot) items.push({ key: 'commandRoot', label: `root: ${_historyFilters.commandRoot}` });
  if (_historyFilters.exitCode === '0') items.push({ key: 'exitCode', label: 'exit: 0' });
  else if (_historyFilters.exitCode === 'nonzero') items.push({ key: 'exitCode', label: 'exit: non-zero' });
  else if (_historyFilters.exitCode === 'incomplete') items.push({ key: 'exitCode', label: 'exit: incomplete' });
  if (_historyFilters.dateRange !== 'all') items.push({ key: 'dateRange', label: `date: ${_historyFilters.dateRange}` });
  if (_historyFilters.starredOnly) items.push({ key: 'starredOnly', label: 'starred' });
  return items;
}

function _renderHistoryActiveFilters() {
  if (typeof historyActiveFilters === 'undefined' || !historyActiveFilters) return;
  historyActiveFilters.replaceChildren();
  const items = _historyActiveFilterItems();
  historyActiveFilters.classList.toggle('u-hidden', !items.length);
  items.forEach(item => {
    const chip = document.createElement('div');
    chip.className = 'history-active-filter-chip';
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
  const params = new URLSearchParams();
  if (_historyFilters.q) params.set('q', _historyFilters.q);
  if (_historyFilters.commandRoot) params.set('command_root', _historyFilters.commandRoot);
  if (_historyFilters.exitCode !== 'all') params.set('exit_code', _historyFilters.exitCode);
  if (_historyFilters.dateRange !== 'all') params.set('date_range', _historyFilters.dateRange);
  const query = params.toString();
  return query ? `/history?${query}` : '/history';
}

function _applyHistoryClientFilters(runs) {
  const items = Array.isArray(runs) ? runs.slice() : [];
  const starred = _getStarred();
  const filtered = _historyFilters.starredOnly
    ? items.filter(run => starred.has(run.command))
    : items;
  return [
    ...filtered.filter(run => starred.has(run.command)),
    ...filtered.filter(run => !starred.has(run.command)),
  ];
}

function _renderHistoryEmptyState() {
  if (typeof historyList === 'undefined' || !historyList) return;
  const empty = document.createElement('div');
  empty.className = 'history-empty-state';
  const title = document.createElement('div');
  title.className = 'history-empty-state-title';
  title.textContent = _historyHasAnyFilters() ? 'No matching runs.' : 'No runs yet.';
  empty.appendChild(title);

  const detail = document.createElement('div');
  detail.className = 'history-empty-state-detail';
  detail.textContent = _historyHasAnyFilters()
    ? 'Adjust or clear the current filters to widen the history results.'
    : 'Completed commands will appear here for this browser session.';
  empty.appendChild(detail);
  historyList.appendChild(empty);
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
  if (debounce) _scheduleHistoryPanelRefresh();
  else refreshHistoryPanel();
}

function clearHistoryFilters() {
  _historyFilters = {
    q: '',
    commandRoot: '',
    exitCode: 'all',
    dateRange: 'all',
    starredOnly: false,
  };
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

function resetCmdHistoryNav() {
  _cmdHistoryNavIndex = -1;
  _cmdHistoryNavDraft = '';
  if (typeof isHistSearchMode === 'function' && isHistSearchMode()) {
    exitHistSearch(false);
  }
}

function navigateCmdHistory(delta) {
  if (!cmdHistory.length) return false;

  if (delta > 0) {
    if (_cmdHistoryNavIndex === -1) {
      _cmdHistoryNavDraft = (typeof getComposerValue === 'function')
        ? getComposerValue()
        : (cmdInput ? cmdInput.value : '');
      _cmdHistoryNavIndex = 0;
    } else if (_cmdHistoryNavIndex < cmdHistory.length - 1) {
      _cmdHistoryNavIndex++;
    } else {
      return true;
    }
    _suspendCmdHistoryNavReset = true;
    setComposerValue(cmdHistory[_cmdHistoryNavIndex]);
    return true;
  }

  if (delta < 0) {
    if (_cmdHistoryNavIndex === -1) return false;
    if (_cmdHistoryNavIndex > 0) {
      _cmdHistoryNavIndex--;
      _suspendCmdHistoryNavReset = true;
      setComposerValue(cmdHistory[_cmdHistoryNavIndex]);
      return true;
    }
    _suspendCmdHistoryNavReset = true;
    setComposerValue(_cmdHistoryNavDraft);
    resetCmdHistoryNav();
    return true;
  }

  return false;
}

function addToHistory(cmd) {
  cmdHistory = [cmd, ...cmdHistory.filter(c => c !== cmd)].slice(0, APP_CONFIG.recent_commands_limit);
  resetCmdHistoryNav();
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
  resetCmdHistoryNav();
  renderHistory();
}

function _makeOverflowChip(_count) {
  const chip = document.createElement('button');
  chip.className = 'hist-chip hist-chip-overflow';
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

function renderHistory() {
  while (histRow.children.length > 1) histRow.removeChild(histRow.lastChild);
  if (!cmdHistory.length) { hideHistoryRow(); return; }
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
    chip.className = 'hist-chip' + (isStarred ? ' starred' : '');
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
      chip.blur();
      setComposerValue(cmd, cmd.length, cmd.length);
      if (typeof focusAnyComposerInput === 'function' && focusAnyComposerInput({ preventScroll: true })) return;
      resetCmdHistoryNav();
    });
    histRow.appendChild(chip);
  });

  if (isMobile && visible.length < sorted.length) {
    histRow.appendChild(_makeOverflowChip());
  } else if (!isMobile) {
    _applyDesktopChipOverflow();
  }
}

// Re-measure chip overflow when the window is resized on desktop.
if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  window.addEventListener('resize', () => {
    if (typeof useMobileTerminalViewportMode === 'function' && !useMobileTerminalViewportMode()) {
      renderHistory();
    }
  });
}


function _setHistoryDeleteMessage(title, detail) {
  const msg = histDelMsg;
  if (!msg) return;
  msg.replaceChildren();
  msg.appendChild(document.createTextNode(title));
  msg.appendChild(document.createElement('br'));
  const note = document.createElement('span');
  note.className = 'history-delete-note';
  note.textContent = detail;
  msg.appendChild(note);
}

function _createHistoryEntry(run, isStarred) {
  const entry = document.createElement('div');
  entry.className = 'history-entry' + (isStarred ? ' starred' : '');
  const exitCls = run.exit_code === 0 ? 'exit-ok' : 'exit-fail';
  const startedAt = new Date(run.started);
  const now = new Date();
  const time = startedAt.toLocaleTimeString();
  const showDate = !Number.isNaN(startedAt.getTime()) && (
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
  starBtn.setAttribute('aria-label', isStarred ? 'Unstar command' : 'Star command');
  starBtn.textContent = isStarred ? '★' : '☆';
  header.appendChild(starBtn);

  const cmd = document.createElement('div');
  cmd.className = 'history-entry-cmd';
  cmd.textContent = run.command || '';
  header.appendChild(cmd);
  entry.appendChild(header);

  const meta = document.createElement('div');
  meta.className = 'history-entry-meta';
  const timeEl = document.createElement('span');
  timeEl.textContent = time;
  meta.appendChild(timeEl);
  if (showDate) {
    const dateEl = document.createElement('span');
    dateEl.className = 'history-entry-date';
    dateEl.textContent = startedAt.toLocaleDateString();
    meta.appendChild(dateEl);
  }
  const exitEl = document.createElement('span');
  exitEl.className = exitCls;
  exitEl.textContent = `exit ${run.exit_code}`;
  meta.appendChild(exitEl);
  entry.appendChild(meta);

  const actions = document.createElement('div');
  actions.className = 'history-actions';

  const copyBtn = document.createElement('button');
  copyBtn.className = 'history-action-btn';
  copyBtn.dataset.action = 'copy';
  copyBtn.textContent = 'copy';
  actions.appendChild(copyBtn);

  const permalinkBtn = document.createElement('button');
  permalinkBtn.className = 'history-action-btn';
  permalinkBtn.dataset.action = 'permalink';
  permalinkBtn.textContent = 'permalink';
  actions.appendChild(permalinkBtn);

  const deleteBtn = document.createElement('button');
  deleteBtn.className = 'history-action-btn';
  deleteBtn.dataset.action = 'delete';
  deleteBtn.textContent = 'delete';
  actions.appendChild(deleteBtn);

  entry.appendChild(actions);
  return entry;
}

function _historyActionKeepsPanelOpen(action) {
  if (action === 'star') return true;
  const mobileMode = typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode();
  if (!mobileMode) return false;
  return action === 'copy' || action === 'permalink';
}


// ── Run history panel ──
let pendingHistAction = null;

function confirmHistAction(type, id, command) {
  pendingHistAction = { type, id, command };
  const msg      = histDelMsg;
  const confirm  = histDelConfirmBtn;
  if (type === 'clear') {
    _setHistoryDeleteMessage('Clear run history?', 'This cannot be undone.');
    showHistoryDeleteNonfav();
    confirm.textContent   = 'Delete all';
  } else {
    _setHistoryDeleteMessage('Remove this run from history?', 'This cannot be undone.');
    hideHistoryDeleteNonfav();
    confirm.textContent   = 'Delete';
  }
  showHistoryDeleteOverlay();
}

function executeHistAction(type) {
  const action  = type || (pendingHistAction && pendingHistAction.type);
  const id      = pendingHistAction && pendingHistAction.id;
  const command = pendingHistAction && pendingHistAction.command;
  pendingHistAction = null;
  if (action === 'delete') {
    apiFetch(`/history/${id}`, { method: 'DELETE' }).then(() => {
      // Remove from starred set and chips — deleted history should not stay pinned
      const s = _getStarred();
      s.delete(command);
      _saveStarred(s);
      cmdHistory = cmdHistory.filter(c => c !== command);
      renderHistory();
      refreshHistoryPanel();
    }).catch(() => showToast('Failed to delete run'));
  } else if (action === 'clear-nonfav') {
    apiFetch('/history')
      .then(r => r.json())
      .then(data => {
        const starred   = _getStarred();
        const toDelete  = data.runs.filter(r => !starred.has(r.command));
        const deleteCmds = new Set(toDelete.map(r => r.command));
        // Remove deleted commands from chips; starred commands remain
        cmdHistory = cmdHistory.filter(c => !deleteCmds.has(c));
        renderHistory();
        return Promise.all(toDelete.map(r => apiFetch(`/history/${r.id}`, { method: 'DELETE' })));
      })
      .then(() => refreshHistoryPanel())
      .catch(() => showToast('Failed to clear history'));
  } else {
    apiFetch('/history', { method: 'DELETE' }).then(() => {
      // Wipe all starred state and chips — nothing left in history to pin
      _saveStarred(new Set());
      cmdHistory = [];
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

function restoreHistoryRunIntoTab(run, { targetTabId = null, hidePanelOnSuccess = true } = {}) {
  if (!run || !run.id) return Promise.reject(new Error('missing run id'));
  const existing = targetTabId ? getTab(targetTabId) : tabs.find(t => t.command === run.command);
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
      (fullRun.output || []).forEach(line => appendLine(line, '', tabId));
      if (previewNotice) appendLine(previewNotice, 'notice', tabId);
      appendLine(
        `[history — exit ${fullRun.exit_code}]`,
        fullRun.exit_code === 0 ? 'exit-ok' : 'exit-fail',
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

function refreshHistoryPanel() {
  // The panel is populated on demand so we always fetch the latest persisted
  // history instead of assuming the in-memory tab state is authoritative.
  _syncHistoryFilterControls();
  _renderHistoryActiveFilters();
  apiFetch(_buildHistoryRequestUrl()).then(r => r.json()).then(data => {
    historyList.replaceChildren();
    _renderHistoryRootSuggestions(Array.isArray(data.roots) ? data.roots : data.runs);
    const sorted = _applyHistoryClientFilters(data.runs);
    const starred = _getStarred();
    if (!sorted.length) {
      _renderHistoryEmptyState();
      return;
    }

    sorted.forEach(run => {
      const isStarred = starred.has(run.command);
      const entry = _createHistoryEntry(run, isStarred);

      // Click anywhere on the entry (except buttons) to load into a new tab,
      // or switch to the existing tab if this command is already loaded there.
      entry.addEventListener('click', e => {
        if (e.target.closest('[data-action]')) return;

        // If a tab already has this command and already has the full output,
        // switch to it instead of duplicating. If the tab is still showing a
        // truncated preview and the full artifact exists, upgrade that tab in
        // place so the restored view stays consistent.
        const existing = tabs.find(t => t.command === run.command);
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
      });

      entry.querySelector('[data-action="star"]').addEventListener('click', e => {
        e.preventDefault();
        e.stopPropagation();
        const wasStarred = _getStarred().has(run.command);
        _toggleStar(run.command);
        // If the command is being starred and isn't in the chips list, add it
        if (!wasStarred && !cmdHistory.includes(run.command)) {
          cmdHistory = [run.command, ...cmdHistory].slice(0, APP_CONFIG.recent_commands_limit);
        }
        if (!_historyActionKeepsPanelOpen('star')) hideHistoryPanel();
        refreshHistoryPanel();
        renderHistory(); // keep chips in sync
      });

      entry.querySelector('[data-action="copy"]').addEventListener('click', () => {
        copyTextToClipboard(run.command)
          .then(() => showToast('Command copied to clipboard'))
          .catch(() => showToast('Failed to copy command', 'error'));
        const btn = entry.querySelector('[data-action="copy"]');
        if (btn && typeof btn.blur === 'function') setTimeout(() => btn.blur(), 0);
        if (!_historyActionKeepsPanelOpen('copy')) hideHistoryPanel();
      });

      entry.querySelector('[data-action="permalink"]').addEventListener('click', () => {
        const url = `${location.origin}/history/${run.id}`;
        copyTextToClipboard(url)
          .then(() => showToast('Link copied to clipboard'))
          .catch(() => showToast('Failed to copy link', 'error'));
        const btn = entry.querySelector('[data-action="permalink"]');
        if (btn && typeof btn.blur === 'function') setTimeout(() => btn.blur(), 0);
        if (!_historyActionKeepsPanelOpen('permalink')) hideHistoryPanel();
      });
      entry.querySelector('[data-action="delete"]').addEventListener('click', () => {
        confirmHistAction('delete', run.id, run.command);
        hideHistoryPanel();
        const btn = entry.querySelector('[data-action="delete"]');
        if (btn && typeof btn.blur === 'function') setTimeout(() => btn.blur(), 0);
      });

      historyList.appendChild(entry);
    });
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
    _historyRootIndex = -1;
    _historyRefreshRootDropdown();
  });
  historyRootInput.addEventListener('blur', () => {
    setTimeout(() => _hideHistoryRootDropdown(), 0);
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

function isHistSearchMode() { return _histSearchMode; }

function _histSearchMatches() {
  if (!cmdHistory.length) return [];
  const q = _histSearchQuery.toLowerCase();
  if (!q) return cmdHistory.slice(0, 20);
  return cmdHistory.filter(c => c.toLowerCase().includes(q)).slice(0, 20);
}

function _hideHistSearchDropdown() {
  if (histSearchDropdown) histSearchDropdown.classList.add('u-hidden');
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
      item.className = 'hist-search-item' + (i === _histSearchIndex ? ' active' : '');
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

  // Position above the prompt line, like the ac-dropdown does
  histSearchDropdown.classList.remove('u-hidden');
  if (shellPromptWrap) {
    const rect = shellPromptWrap.getBoundingClientRect();
    histSearchDropdown.style.position = 'fixed';
    histSearchDropdown.style.left = rect.left + 'px';
    histSearchDropdown.style.width = rect.width + 'px';
    const dropH = histSearchDropdown.offsetHeight;
    histSearchDropdown.style.top = (rect.top - dropH - 4) + 'px';
  }
}

function enterHistSearch() {
  if (_histSearchMode) {
    // Ctrl+R again: cycle to next match
    const matches = _histSearchMatches();
    if (matches.length > 0) {
      _histSearchIndex = (_histSearchIndex + 1) % matches.length;
      if (typeof setComposerValue === 'function') {
        setComposerValue(matches[_histSearchIndex], matches[_histSearchIndex].length, matches[_histSearchIndex].length, { dispatch: false });
      }
      _renderHistSearch();
    }
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
  if (typeof acHide === 'function') acHide();
}

function handleHistSearchInput(value) {
  _histSearchQuery = value;
  _histSearchIndex = -1;
  const matches = _histSearchMatches();
  if (matches.length > 0) {
    _histSearchIndex = 0;
  }
  _renderHistSearch();
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
    // Accept the selected match (if any) then run it. If nothing matched, keep
    // the typed query in the input and run that instead of restoring the pre-draft.
    if (_histSearchIndex >= 0) {
      exitHistSearch(true);
    } else {
      exitHistSearch(false, { keepCurrent: true });
    }
    const currentValue = (typeof getComposerValue === 'function') ? getComposerValue() : '';
    if (typeof submitComposerCommand === 'function') {
      submitComposerCommand(currentValue, { dismissKeyboard: true });
    } else if (typeof runCommand === 'function') {
      runCommand();
    }
    return true;
  }
  if (e.key === 'Tab') {
    e.preventDefault();
    // Accept the selected match without running; fall back to keeping the query.
    if (_histSearchIndex >= 0) {
      exitHistSearch(true);
    } else {
      exitHistSearch(false, { keepCurrent: true });
    }
    return true;
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    const matches = _histSearchMatches();
    if (matches.length > 0) {
      _histSearchIndex = (_histSearchIndex + 1) % matches.length;
      if (typeof setComposerValue === 'function') {
        setComposerValue(matches[_histSearchIndex], matches[_histSearchIndex].length, matches[_histSearchIndex].length, { dispatch: false });
      }
      _renderHistSearch();
    }
    return true;
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    const matches = _histSearchMatches();
    if (matches.length > 0) {
      _histSearchIndex = _histSearchIndex <= 0 ? matches.length - 1 : _histSearchIndex - 1;
      if (typeof setComposerValue === 'function') {
        setComposerValue(matches[_histSearchIndex], matches[_histSearchIndex].length, matches[_histSearchIndex].length, { dispatch: false });
      }
      _renderHistSearch();
    }
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
