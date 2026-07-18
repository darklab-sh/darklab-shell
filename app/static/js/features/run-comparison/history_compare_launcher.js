// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// ── Run comparison launcher ──────────────────────────────────────────────
// Loaded after history.js so it can reuse History drawer state, route helpers,
// and the result renderer while owning the "choose another run" flow.
import { showToast as importedShowToast } from '../../core/utils.js';
import {
  compareDateGroupLabel as importedCompareDateGroupLabel,
  compareFormatDate as importedCompareFormatDate,
  orderedRunIds as importedOrderedRunIds,
} from './history_compare_core.js';
import {
  closeHistoryCompareOverlay as importedCloseHistoryCompareOverlay,
  _ensureHistoryCompareOverlay as importedEnsureHistoryCompareOverlay,
  _openHistoryCompareOverlay as importedOpenHistoryCompareOverlay,
} from './history_compare_overlay.js';
import { fetchAndRenderHistoryComparison as importedFetchAndRenderHistoryComparison } from './history_compare_bridge.js';
import { setHistoryCompareHandlers as importedSetHistoryCompareHandlers } from './history_compare_bridge.js';
import {
  apiFetch as importedRuntimeApiFetch,
  hasRuntimeHandler as importedHasRuntimeHandler,
  logClientError as importedRuntimeLogClientError,
} from '../../runtime_bridge.js';
import { openWorkflows as importedOpenWorkflows } from '../../controller_action_bridge.js';
import { bindPressable as importedBindPressable } from '../../ui/ui_pressable.js';

const HISTORY_COMPARE_LAUNCHER_GLOBAL = typeof window !== 'undefined' ? window : globalThis;
const HISTORY_COMPARE_CANDIDATES_ROUTE = '/history/<run_id>/compare-candidates';
const HISTORY_COMPARE_MANUAL_CANDIDATES_ROUTE = '/history';

function _historyCompareLauncherFormatDate(value) {
  return typeof importedCompareFormatDate === 'function' ? importedCompareFormatDate(value) : '';
}

function _historyCompareLauncherDateGroupLabel(value) {
  return typeof importedCompareDateGroupLabel === 'function' ? importedCompareDateGroupLabel(value) : 'Other';
}

function _historyCompareLauncherShowToast(message, tone = 'success') {
  if (typeof importedShowToast === 'function') importedShowToast(message, tone);
}

function _historyCompareLauncherOpenOverlay(options = {}) {
  const open = (typeof importedOpenHistoryCompareOverlay !== 'undefined' && importedOpenHistoryCompareOverlay)
    || HISTORY_COMPARE_LAUNCHER_GLOBAL._openHistoryCompareOverlay;
  if (typeof open === 'function') open(options);
}

function _historyCompareLauncherEnsureOverlay() {
  const ensure = (typeof importedEnsureHistoryCompareOverlay !== 'undefined' && importedEnsureHistoryCompareOverlay)
    || HISTORY_COMPARE_LAUNCHER_GLOBAL._ensureHistoryCompareOverlay;
  return typeof ensure === 'function' ? ensure() : null;
}

function _historyCompareLauncherApiFetch() {
  const fetcher = (
    typeof importedHasRuntimeHandler === 'function'
    && importedHasRuntimeHandler('apiFetch')
    && typeof importedRuntimeApiFetch === 'function'
      ? importedRuntimeApiFetch
      : null
  ) || (typeof HISTORY_COMPARE_LAUNCHER_GLOBAL.apiFetch === 'function' ? HISTORY_COMPARE_LAUNCHER_GLOBAL.apiFetch : null);
  if (!fetcher) throw new Error('apiFetch is not available');
  return fetcher;
}

function _historyCompareLauncherRequestError(error, stage, status = 0) {
  const normalized = error instanceof Error ? error : new Error('Comparison choice request failed');
  if (!normalized.compareRequestStage) normalized.compareRequestStage = stage;
  if (!normalized.httpStatus && status) normalized.httpStatus = status;
  return normalized;
}

function _historyCompareLauncherFetchJson(url) {
  let request;
  try {
    request = _historyCompareLauncherApiFetch()(url);
  } catch (error) {
    return Promise.reject(_historyCompareLauncherRequestError(error, 'runtime'));
  }
  return Promise.resolve(request)
    .catch(error => Promise.reject(_historyCompareLauncherRequestError(error, 'request')))
    .then(response => {
      const status = Number(response?.status || 0) || 0;
      let payload;
      try {
        payload = response.json();
      } catch (error) {
        return Promise.reject(_historyCompareLauncherRequestError(error, 'decode', status));
      }
      return Promise.resolve(payload)
        .catch(error => Promise.reject(_historyCompareLauncherRequestError(error, 'decode', status)))
        .then(data => {
          if (!data || typeof data !== 'object' || Array.isArray(data)) {
            throw _historyCompareLauncherRequestError(
              new Error('Comparison choice response was invalid'),
              'decode',
              status,
            );
          }
          if (response?.ok === false || data?.error) {
            throw _historyCompareLauncherRequestError(
              new Error('Comparison choice request was rejected'),
              'response',
              status,
            );
          }
          return data;
        });
    });
}

function _historyCompareLauncherLogRequestFailure(context, event, error, sourceRunId, route) {
  const logger = (
    typeof importedRuntimeLogClientError === 'function'
    && typeof importedHasRuntimeHandler === 'function'
    && importedHasRuntimeHandler('logClientError')
  )
    ? importedRuntimeLogClientError
    : (typeof HISTORY_COMPARE_LAUNCHER_GLOBAL.logClientError === 'function'
      ? HISTORY_COMPARE_LAUNCHER_GLOBAL.logClientError
      : null);
  if (!logger) return;
  const status = Number(error?.httpStatus || error?.status || 0) || 0;
  const level = status >= 400 && status < 500 ? 'warning' : 'error';
  const safeError = new Error(status ? `Request failed with status ${status}` : 'Request failed');
  safeError.name = String(error?.name || 'Error').slice(0, 120);
  logger(context, safeError, {
    event,
    level,
    stage: String(error?.compareRequestStage || 'request'),
    status,
    run_id: String(sourceRunId || ''),
    route,
  });
}

function _historyCompareLauncherFetchAndRender(leftId, rightId, options) {
  if (typeof importedFetchAndRenderHistoryComparison === 'function') {
    const hasBridgeHandler = typeof importedFetchAndRenderHistoryComparison.hasHandler !== 'function'
      || importedFetchAndRenderHistoryComparison.hasHandler();
    if (hasBridgeHandler) {
      return importedFetchAndRenderHistoryComparison(leftId, rightId, options);
    }
  }
  const globalFetchAndRender = HISTORY_COMPARE_LAUNCHER_GLOBAL.fetchAndRenderHistoryComparison;
  return typeof globalFetchAndRender === 'function'
    ? globalFetchAndRender(leftId, rightId, options)
    : undefined;
}

function _historyCompareLauncherOrderedRunIds(source, candidate) {
  return typeof importedOrderedRunIds === 'function'
    ? importedOrderedRunIds(source, candidate)
    : [candidate?.id, source?.id];
}

function _historyCompareLauncherOpenWorkflow(executionId) {
  if (typeof importedCloseHistoryCompareOverlay === 'function') {
    importedCloseHistoryCompareOverlay({ restoreFocus: false });
  }
  if (typeof importedOpenWorkflows === 'function') importedOpenWorkflows({ executionId });
}

function _historyCompareLauncherRunLabels(source, candidate) {
  if (!candidate?.id) return { source: 'Selected run', candidate: 'Comparison run' };
  const [, currentId] = _historyCompareLauncherOrderedRunIds(source, candidate);
  return currentId === source?.id
    ? { source: 'Current run', candidate: 'Baseline' }
    : { source: 'Baseline', candidate: 'Current run' };
}

function _historyCompareLauncherStart(source, candidate) {
  if (!source?.id || !candidate?.id) return;
  const [leftId, rightId] = _historyCompareLauncherOrderedRunIds(source, candidate);
  _historyCompareLauncherFetchAndRender(leftId, rightId, {
    initialViewMode: window._historyCompareState.initialViewMode || '',
  });
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
  if (run && run.started) parts.push(_historyCompareLauncherFormatDate(run.started));
  if (run && run.exit_code !== undefined && run.exit_code !== null) parts.push(`exit ${run.exit_code}`);
  if (run && Number.isFinite(Number(run.output_line_count))) parts.push(`${Number(run.output_line_count).toLocaleString()} lines`);
  if (extra) parts.push(extra);
  meta.textContent = parts.join(' · ');
  card.appendChild(meta);
  const provenance = run?.workflow_execution;
  const executionId = String(provenance?.execution_id || run?.workflow_execution_id || '').trim();
  if (provenance && executionId) {
    const workflow = document.createElement('div');
    workflow.className = 'history-compare-run-workflow';
    const stepId = String(provenance?.step?.step_id || run?.workflow_step_id || '').trim();
    const identity = document.createElement('span');
    identity.className = 'history-compare-run-workflow-label';
    identity.textContent = [provenance.title || 'Playbook', stepId].filter(Boolean).join(' · ');
    workflow.appendChild(identity);
    const open = document.createElement('button');
    open.type = 'button';
    open.className = 'btn btn-ghost btn-compact history-compare-run-workflow-link';
    open.textContent = 'View playbook';
    open.title = `Open workflow execution ${executionId}`;
    const openWorkflow = () => _historyCompareLauncherOpenWorkflow(executionId);
    if (typeof importedBindPressable === 'function') {
      importedBindPressable(open, { onActivate: openWorkflow, refocusComposer: false });
    } else {
      open.addEventListener('click', openWorkflow);
    }
    workflow.appendChild(open);
    card.appendChild(workflow);
  }
  return card;
}

function _renderHistoryCompareLauncher() {
  const overlay = _historyCompareLauncherEnsureOverlay();
  if (!overlay) return;
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

  const suggested = window._historyCompareState.selected || window._historyCompareState.candidates[0] || null;
  const runLabels = _historyCompareLauncherRunLabels(source, suggested);
  const sourceCard = _historyCompareRunCard(source, runLabels.source);
  body.appendChild(sourceCard);

  const suggestedWrap = document.createElement('div');
  suggestedWrap.className = 'history-compare-section';
  const suggestedTitle = document.createElement('div');
  suggestedTitle.className = 'history-compare-section-title';
  suggestedTitle.textContent = 'Suggested match';
  suggestedWrap.appendChild(suggestedTitle);
  if (suggested) {
    suggestedWrap.appendChild(_historyCompareRunCard(
      suggested,
      runLabels.candidate,
      suggested.confidence_label || '',
    ));
    const primary = document.createElement('button');
    primary.type = 'button';
    primary.className = 'btn btn-primary btn-compact history-compare-primary';
    primary.textContent = 'Compare with suggested run';
    primary.addEventListener('click', () => _historyCompareLauncherStart(source, suggested));
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
  _historyCompareLauncherFetchJson(`/history?${params.toString()}`)
    .then(data => {
      if (window._historyCompareState.manualRequestId !== activeRequestId) return;
      const items = Array.isArray(data.items) ? data.items : (Array.isArray(data.runs) ? data.runs : []);
      const ranked = window._historyCompareState.candidates || [];
      const seenRanked = new Set(ranked.map(item => item.id));
      const existing = append ? new Set((window._historyCompareState.manualCandidates || []).map(item => item.id)) : new Set();
      const manualItems = items
        .filter(item => (
          item
          && item.type !== 'snapshot'
          && item.run_kind === 'external'
          && item.finished
          && item.id
          && item.id !== source.id
          && !existing.has(item.id)
        ))
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
    .catch(error => {
      if (window._historyCompareState.manualRequestId !== activeRequestId) return;
      window._historyCompareState.manualLoading = false;
      _renderHistoryCompareCandidateList();
      _historyCompareLauncherLogRequestFailure(
        'history compare manual candidates fetch failed',
        'HISTORY_COMPARE_MANUAL_CANDIDATES_FETCH_FAILED',
        error,
        source.id,
        HISTORY_COMPARE_MANUAL_CANDIDATES_ROUTE,
      );
      _historyCompareLauncherShowToast('Failed to load comparison choices', 'error');
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
    const groupLabel = _historyCompareLauncherDateGroupLabel(candidate.started || candidate.created);
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
        candidate.started ? _historyCompareLauncherFormatDate(candidate.started) : '',
        candidate.exit_code !== undefined && candidate.exit_code !== null ? `exit ${candidate.exit_code}` : '',
      ].filter(Boolean).join(' · ');
      row.appendChild(meta);
      row.addEventListener('click', () => _historyCompareLauncherStart(source, candidate));
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

function openHistoryCompareLauncher(run, options = {}) {
  if (!run || !run.id) return;
  if (_historyCompareManualTimer) {
    clearTimeout(_historyCompareManualTimer);
    _historyCompareManualTimer = null;
  }
  const state = window._historyCompareState;
  const requestId = Number(state.launcherRequestId || 0) + 1;
  state.launcherRequestId = requestId;
  state.manualRequestId = Number(state.manualRequestId || 0) + 1;
  state.source = { ...run };
  state.candidates = [];
  state.selected = null;
  state.manualCandidates = [];
  state.manualLoaded = false;
  state.manualLoading = false;
  state.manualCollapsedGroups = new Set();
  state.manualQuery = '';
  state.initialViewMode = String(options.initialViewMode || '').trim();
  _historyCompareLauncherOpenOverlay({ returnFocus: options.returnFocus || null });
  const body = document.querySelector('#history-compare-body');
  if (body) {
    body.replaceChildren();
    const loading = document.createElement('div');
    loading.className = 'history-compare-empty';
    loading.textContent = 'Finding comparable runs...';
    body.appendChild(loading);
  }
  _historyCompareLauncherFetchJson(`/history/${encodeURIComponent(run.id)}/compare-candidates`)
    .then(data => {
      if (window._historyCompareState.launcherRequestId !== requestId) return;
      window._historyCompareState.source = data.source || { ...run };
      window._historyCompareState.candidates = Array.isArray(data.candidates) ? data.candidates : [];
      window._historyCompareState.selected = data.suggested || window._historyCompareState.candidates[0] || null;
      _renderHistoryCompareLauncher();
      _loadHistoryCompareManualCandidates(window._historyCompareState.source, '');
    })
    .catch(error => {
      if (window._historyCompareState.launcherRequestId !== requestId) return;
      window._historyCompareState.candidates = [];
      window._historyCompareState.selected = null;
      _renderHistoryCompareLauncher();
      _historyCompareLauncherLogRequestFailure(
        'history compare candidates fetch failed',
        'HISTORY_COMPARE_CANDIDATES_FETCH_FAILED',
        error,
        run.id,
        HISTORY_COMPARE_CANDIDATES_ROUTE,
      );
      _historyCompareLauncherShowToast('Failed to load comparison choices', 'error');
    });
}

if (typeof importedSetHistoryCompareHandlers === 'function') {
  importedSetHistoryCompareHandlers({ openHistoryCompareLauncher });
}

export {
  _fetchHistoryCompareManualCandidates,
  _historyCompareRunCard,
  _historyCompareLauncherOrderedRunIds,
  _historyCompareLauncherStart,
  _loadHistoryCompareManualCandidates,
  _renderHistoryCompareCandidateList,
  _renderHistoryCompareLauncher,
  openHistoryCompareLauncher,
};
