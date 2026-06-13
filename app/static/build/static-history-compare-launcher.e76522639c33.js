// ── Run comparison launcher ──────────────────────────────────────────────
// Loaded after history.js so it can reuse History drawer state, route helpers,
// and the result renderer while owning the "choose another run" flow.

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
  const source = window._historyCompareState.source;
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

  const suggested = window._historyCompareState.selected || window._historyCompareState.candidates[0] || null;
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
    primary.addEventListener('click', () => window.fetchAndRenderHistoryComparison(source.id, suggested.id));
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
  search.value = window._historyCompareState.manualQuery || '';
  search.autocomplete = 'off';
  search.spellcheck = false;
  search.addEventListener('input', e => {
    window._historyCompareState.manualQuery = e.target.value;
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
  window._historyCompareState.manualPage = 1;
  window._historyCompareState.manualHasNext = false;
  window._historyCompareState.manualLoading = false;
  window._historyCompareState.manualCollapsedGroups = new Set();
  const requestId = (window._historyCompareState.manualRequestId || 0) + 1;
  window._historyCompareState.manualRequestId = requestId;
  _historyCompareManualTimer = setTimeout(() => {
    _historyCompareManualTimer = null;
    _fetchHistoryCompareManualCandidates(source, query, { requestId, page: 1, append: false });
  }, 120);
}

function _fetchHistoryCompareManualCandidates(source, query = '', { requestId = null, page = 1, append = false } = {}) {
  if (!source || !source.id || window._historyCompareState.manualLoading) return;
  const activeRequestId = requestId || window._historyCompareState.manualRequestId || 0;
  window._historyCompareState.manualLoading = true;
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
      if (window._historyCompareState.manualRequestId !== activeRequestId) return;
      const items = Array.isArray(data.items) ? data.items : (Array.isArray(data.runs) ? data.runs : []);
      const ranked = window._historyCompareState.candidates || [];
      const seenRanked = new Set(ranked.map(item => item.id));
      const existing = append ? new Set((window._historyCompareState.manualCandidates || []).map(item => item.id)) : new Set();
      const manualItems = items
        .filter(item => item && item.type !== 'snapshot' && item.id && item.id !== source.id && !existing.has(item.id))
        .map(item => ({
          ...item,
          confidence_label: seenRanked.has(item.id) ? ((ranked.find(candidate => candidate.id === item.id) || {}).confidence_label || '') : '',
        }));
      window._historyCompareState.manualCandidates = append
        ? [...(window._historyCompareState.manualCandidates || []), ...manualItems]
        : manualItems;
      window._historyCompareState.manualLoaded = true;
      window._historyCompareState.manualPage = Number(data.page) || page;
      window._historyCompareState.manualHasNext = !!data.has_next;
      window._historyCompareState.manualLoading = false;
      _renderHistoryCompareCandidateList();
    })
    .catch(() => {
      if (window._historyCompareState.manualRequestId === activeRequestId) {
        window._historyCompareState.manualLoading = false;
        _renderHistoryCompareCandidateList();
      }
      showToast('Failed to load comparison choices', 'error');
    });
}

function _renderHistoryCompareCandidateList() {
  const list = document.querySelector('[data-compare-candidate-list="1"]');
  const source = window._historyCompareState.source;
  if (!list || !source) return;
  const search = document.querySelector('.history-compare-search');
  const searchWasFocused = search && document.activeElement === search;
  list.replaceChildren();
  const sourceCandidates = window._historyCompareState.manualLoaded
    ? (window._historyCompareState.manualCandidates || [])
    : (window._historyCompareState.candidates || []);
  const candidates = sourceCandidates
    .filter(item => item && item.id && item.id !== source.id);
  if (!candidates.length) {
    const empty = document.createElement('div');
    empty.className = 'history-compare-empty';
    empty.textContent = window._historyCompareState.manualLoading ? 'Loading runs...' : 'No runs found for the current search.';
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
    const collapsed = window._historyCompareState.manualCollapsedGroups.has(group.label);
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
      row.addEventListener('click', () => window.fetchAndRenderHistoryComparison(source.id, candidate.id));
      rows.appendChild(row);
    });
    headerBtn.addEventListener('click', () => {
      const nextCollapsed = !rows.hidden;
      rows.hidden = nextCollapsed;
      headerBtn.setAttribute('aria-expanded', nextCollapsed ? 'false' : 'true');
      if (nextCollapsed) window._historyCompareState.manualCollapsedGroups.add(group.label);
      else window._historyCompareState.manualCollapsedGroups.delete(group.label);
    });
    groupEl.appendChild(rows);
    list.appendChild(groupEl);
  });
  if (window._historyCompareState.manualLoaded && (window._historyCompareState.manualHasNext || window._historyCompareState.manualLoading)) {
    const more = document.createElement('button');
    more.type = 'button';
    more.className = 'btn btn-secondary btn-compact history-compare-load-more';
    more.disabled = !!window._historyCompareState.manualLoading;
    more.textContent = window._historyCompareState.manualLoading ? 'Loading...' : 'Load More';
    more.addEventListener('click', () => {
      _fetchHistoryCompareManualCandidates(source, window._historyCompareState.manualQuery, {
        requestId: window._historyCompareState.manualRequestId,
        page: (window._historyCompareState.manualPage || 1) + 1,
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
  window._historyCompareState = {
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
      window._historyCompareState.source = data.source || window._historyCompareState.source;
      window._historyCompareState.candidates = Array.isArray(data.candidates) ? data.candidates : [];
      window._historyCompareState.selected = data.suggested || window._historyCompareState.candidates[0] || null;
      _renderHistoryCompareLauncher();
      _loadHistoryCompareManualCandidates(window._historyCompareState.source, '');
    })
    .catch(() => {
      window._historyCompareState.candidates = [];
      window._historyCompareState.selected = null;
      _renderHistoryCompareLauncher();
      showToast('Failed to load comparison choices', 'error');
    });
}

window._historyCompareRunCard = _historyCompareRunCard;
window._renderHistoryCompareLauncher = _renderHistoryCompareLauncher;
window._loadHistoryCompareManualCandidates = _loadHistoryCompareManualCandidates;
window._fetchHistoryCompareManualCandidates = _fetchHistoryCompareManualCandidates;
window._renderHistoryCompareCandidateList = _renderHistoryCompareCandidateList;
window.openHistoryCompareLauncher = openHistoryCompareLauncher;
