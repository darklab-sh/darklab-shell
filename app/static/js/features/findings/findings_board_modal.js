// First-class findings triage board modal.
// Reuses the shared project findings board adapter so list and board surfaces
// keep the same review-state grouping rules.
import { emitUiEvent as importedEmitUiEvent } from '../../core/state.js';
import { closeMajorOverlays as importedCloseMajorOverlays } from '../../ui/overlay_actions_bridge.js';
import { logClientError as importedLogClientError } from '../../runtime_bridge.js';
import { apiFetch as importedApiFetch } from '../../session.js';
import { bindDismissible as importedBindDismissible } from '../../ui/ui_dismissible.js';
import {
  blurVisibleComposerInputIfMobile as importedBlurVisibleComposerInputIfMobile,
  refocusComposerAfterAction as importedRefocusComposerAfterAction,
  syncModalOverlayState as importedSyncModalOverlayState,
} from '../../ui/ui_helpers.js';
import { restoreHistoryRunIntoTab as importedRestoreHistoryRunIntoTab } from '../history/history_restore.js';
import { DarklabProjectFindingsData as importedProjectFindingsData } from '../projects/project_findings_data.js';
import {
  DarklabTeamScope as importedTeamScope,
  activeTeamScopeCan as importedActiveTeamScopeCan,
  teamScopeDeniedMessage as importedTeamScopeDeniedMessage,
} from '../team_scope.js';
import { DarklabFindingTriageEditor as importedFindingTriageEditor } from './finding_triage_bridge.js';

let exportedOpenFindingsBoard = null;
let exportedCloseFindingsBoard = null;
let exportedIsFindingsBoardOpen = null;

(function findingsBoardModalModule(global) {
  'use strict';
  const bindDismissible = (typeof importedBindDismissible !== 'undefined' && importedBindDismissible) || null;
  const blurVisibleComposerInputIfMobile = (typeof importedBlurVisibleComposerInputIfMobile !== 'undefined' && importedBlurVisibleComposerInputIfMobile) || null;
  const emitUiEvent = (typeof importedEmitUiEvent !== 'undefined' && importedEmitUiEvent) || null;
  const findingTriageEditor = (typeof importedFindingTriageEditor !== 'undefined' && importedFindingTriageEditor) || null;
  const projectFindingsData = (typeof importedProjectFindingsData !== 'undefined' && importedProjectFindingsData) || {};
  const refocusComposerAfterAction = (typeof importedRefocusComposerAfterAction !== 'undefined' && importedRefocusComposerAfterAction) || null;
  const restoreHistoryRunIntoTab = (typeof importedRestoreHistoryRunIntoTab !== 'undefined' && importedRestoreHistoryRunIntoTab) || null;
  const syncModalOverlayState = (typeof importedSyncModalOverlayState !== 'undefined' && importedSyncModalOverlayState) || null;
  const teamScope = (typeof importedTeamScope !== 'undefined' && importedTeamScope)
    || {
      activeTeamScopeCan: (typeof importedActiveTeamScopeCan !== 'undefined' && importedActiveTeamScopeCan)
        || null,
      deniedMessage: (typeof importedTeamScopeDeniedMessage !== 'undefined' && importedTeamScopeDeniedMessage)
        || null,
    };

  const overlay = document.getElementById('findings-board-overlay');
  const modal = document.getElementById('findings-board-modal');
  const closeBtn = overlay?.querySelector?.('.findings-board-close');
  const grabHandle = overlay?.querySelector?.('.sheet-grab');
  const titleEl = document.getElementById('findings-board-title');
  const subtitleEl = document.getElementById('findings-board-subtitle');
  const messageEl = document.getElementById('findings-board-message');
  const bodyEl = document.getElementById('findings-board-body');
  const refreshBtn = document.getElementById('findings-board-refresh-btn');

  const REVIEW_STATES = Object.freeze([
    ['new', 'New'],
    ['reviewed', 'Reviewed'],
    ['important', 'Important'],
    ['false_positive', 'False positive'],
    ['needs_followup', 'Follow-up'],
  ]);
  const COLUMN_LIMIT = 200;
  const PAGE_LIMIT = 200;
  const COLUMN_STATE_QUERIES = Object.freeze([
    { column: 'new', states: ['new'] },
    { column: 'reviewed', states: ['reviewed', 'important'] },
    { column: 'false_positive', states: ['false_positive'] },
    { column: 'needs_followup', states: ['needs_followup'] },
  ]);
  const LINE_OPEN_EVENT = 'app:findings-board-open-run';

  const state = {
    open: false,
    loading: false,
    source: 'all',
    scopeLabel: 'All findings',
    endpoint: '',
    projectId: '',
    projectName: '',
    findings: [],
    total: 0,
    hasMore: false,
    columnTotals: null,
    draggedId: '',
  };

  function api() {
    return importedApiFetch;
  }

  function boardApi() {
    return projectFindingsData || {};
  }

  function canTriageFindings() {
    return teamScope && typeof teamScope.activeTeamScopeCan === 'function'
      ? teamScope.activeTeamScopeCan('triage_findings')
      : true;
  }

  function triageDeniedMessage() {
    return teamScope && typeof teamScope.deniedMessage === 'function'
      ? teamScope.deniedMessage('triage team findings')
      : "View-only team members can't triage team findings. Switch to Personal or ask for operator access.";
  }

  function showMessage(message = '', tone = '') {
    if (!messageEl) return;
    messageEl.textContent = String(message || '');
    messageEl.classList.toggle('u-hidden', !message);
    messageEl.classList.toggle('is-error', tone === 'error');
  }

  function setBusy(busy) {
    state.loading = !!busy;
    modal?.setAttribute('aria-busy', busy ? 'true' : 'false');
    if (refreshBtn) refreshBtn.disabled = busy;
  }

  function isOpen() {
    return !!(overlay && overlay.classList.contains('open'));
  }

  function closeFindingsBoard({ refocus = true } = {}) {
    if (!overlay) return;
    state.open = false;
    state.draggedId = '';
    overlay.classList.add('u-hidden');
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    if (typeof syncModalOverlayState === 'function') syncModalOverlayState();
    if (refocus && typeof refocusComposerAfterAction === 'function') {
      refocusComposerAfterAction({ defer: true });
    }
  }

  function show() {
    if (!overlay) return;
    overlay.classList.remove('u-hidden');
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    state.open = true;
    if (typeof syncModalOverlayState === 'function') syncModalOverlayState();
    refreshBtn?.focus?.({ preventScroll: true });
  }

  function encodeParams(params = {}) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (Array.isArray(value)) {
        value.forEach(item => {
          if (item !== undefined && item !== null && String(item) !== '') query.append(key, String(item));
        });
        return;
      }
      if (value !== undefined && value !== null && String(value) !== '') query.set(key, String(value));
    });
    query.set('limit', String(PAGE_LIMIT));
    query.set('offset', '0');
    return query;
  }

  function endpointFromOptions(options = {}) {
    const projectId = String(options.projectId || '').trim();
    const source = String(options.source || '').trim();
    if (projectId && source !== 'atlas') {
      state.source = 'project';
      state.projectId = projectId;
      state.projectName = String(options.projectName || '').trim();
      state.scopeLabel = state.projectName ? `Project: ${state.projectName}` : 'Project findings';
      return `/projects/${encodeURIComponent(projectId)}/findings?${encodeParams()}`;
    }

    const params = {
      q: options.query || '',
      project_id: projectId,
      run_id: options.runId || '',
      orphan_filter: options.orphanFilter || 'hide',
      suppression_filter: options.suppressionFilter || 'hide',
    };
    if (options.reviewState) params.review_state = options.reviewState;
    state.source = source === 'atlas' ? 'atlas' : 'all';
    state.projectId = projectId;
    state.projectName = String(options.projectName || '').trim();
    if (projectId && state.projectName) state.scopeLabel = `Atlas: ${state.projectName}`;
    else if (options.runLabel) state.scopeLabel = `Atlas run: ${options.runLabel}`;
    else if (state.source === 'atlas') state.scopeLabel = 'Atlas findings';
    else state.scopeLabel = 'All findings';
    return `/atlas/findings?${encodeParams(params)}`;
  }

  function findingById(findingId) {
    const normalized = String(findingId || '');
    return state.findings.find(finding => String(finding && finding.id || '') === normalized) || null;
  }

  function endpointUrl(endpoint = '') {
    return new URL(String(endpoint || ''), global.location?.origin || 'http://localhost');
  }

  function endpointPath(url) {
    return `${url.pathname}${url.search || ''}`;
  }

  function hasReviewStateFilter(endpoint = '') {
    return endpointUrl(endpoint).searchParams.has('review_state');
  }

  function endpointWithReviewState(endpoint = '', reviewState = '') {
    const url = endpointUrl(endpoint);
    url.searchParams.delete('review_state');
    url.searchParams.set('review_state', String(reviewState || 'new'));
    url.searchParams.set('limit', String(PAGE_LIMIT));
    url.searchParams.set('offset', '0');
    return endpointPath(url);
  }

  function setFindingReviewState(findingId, reviewState) {
    const normalized = String(findingId || '');
    state.findings = state.findings.map(finding => (
      String(finding && finding.id || '') === normalized
        ? { ...finding, review_state: reviewState }
        : finding
    ));
  }

  function updateFindingTriage(findingId, triage) {
    const normalized = String(findingId || '');
    const compact = triage && typeof triage === 'object' ? triage : {};
    state.findings = state.findings.map(finding => (
      String(finding && finding.id || '') === normalized
        ? {
            ...finding,
            triage: compact,
            verification_status: String(compact.verification_status || finding.verification_status || 'not_started'),
          }
        : finding
    ));
  }

  function reviewSelect(finding) {
    const select = document.createElement('select');
    const allowed = canTriageFindings();
    select.className = 'form-select form-control-compact findings-board-review';
    select.dataset.findingsBoardReview = '1';
    select.dataset.findingId = String(finding.id || '');
    select.dataset.previousReviewState = String(finding.review_state || 'new');
    select.setAttribute('aria-label', 'Finding review state');
    REVIEW_STATES.forEach(([value, label]) => {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = label;
      select.appendChild(option);
    });
    select.value = String(finding.review_state || 'new');
    select.disabled = !allowed;
    if (!allowed) select.title = triageDeniedMessage();
    return select;
  }

  function cardMeta(finding) {
    return [
      finding.run_command || finding.run_id,
      finding.scope || 'finding',
      finding.entity_value || finding.subject_key || '',
      Number.isFinite(Number(finding.line_number)) ? `line ${Number(finding.line_number)}` : '',
    ].filter(Boolean).join(' · ');
  }

  function boardBadge(label, tone = 'muted') {
    const el = document.createElement('span');
    const toneClass = {
      amber: 'badge-tone-amber',
      red: 'badge-tone-red',
      green: 'badge-tone-green',
    }[tone] || 'badge-tone-muted';
    el.className = `badge ${toneClass}`;
    el.textContent = String(label || '');
    return el;
  }

  function severityTone(severity) {
    const normalized = String(severity || '').toLowerCase();
    return normalized === 'high' || normalized === 'critical' ? 'red' : 'muted';
  }

  function triageChips(finding) {
    const triage = finding && finding.triage && typeof finding.triage === 'object' ? finding.triage : null;
    if (!triage) return [];
    const chips = [];
    const status = String(triage.verification_status || finding.verification_status || 'not_started');
    if (status && status !== 'not_started') {
      const label = findingTriageEditor?.verificationStatusLabel?.(status) || status.replace(/_/g, ' ');
      const tone = findingTriageEditor?.verificationStatusTone?.(status) || 'muted';
      chips.push(boardBadge(label, tone));
    }
    if (triage.has_remediation) chips.push(boardBadge('remediation', 'muted'));
    if (triage.has_verification_steps) chips.push(boardBadge('verification steps', 'muted'));
    return chips;
  }

  function renderCard(card) {
    const finding = card.finding || {};
    const article = document.createElement('article');
    article.className = [
      'project-finding-board-card',
      'findings-board-card',
      `review-${card.review_state || 'new'}`,
      card.severity ? `severity-${card.severity}` : '',
    ].filter(Boolean).join(' ');
    article.tabIndex = 0;
    article.draggable = !!card.id && canTriageFindings();
    article.dataset.findingId = card.id;

    const header = document.createElement('div');
    header.className = 'project-finding-board-card-header';
    const title = document.createElement('div');
    title.className = 'project-finding-board-card-title';
    title.textContent = card.title || card.raw_line || card.id || 'Finding';
    header.appendChild(title);
    const badges = document.createElement('div');
    badges.className = 'project-finding-board-card-badges';
    if (card.important) {
      badges.appendChild(boardBadge('important', 'amber'));
    }
    if (card.severity) {
      badges.appendChild(boardBadge(card.severity, severityTone(card.severity)));
    }
    if (badges.children.length) header.appendChild(badges);
    article.appendChild(header);

    const meta = cardMeta(finding);
    if (meta) {
      const metaEl = document.createElement('div');
      metaEl.className = 'project-finding-board-card-meta';
      metaEl.textContent = meta;
      article.appendChild(metaEl);
    }
    if (card.raw_line && card.raw_line !== card.title) {
      const detail = document.createElement('div');
      detail.className = 'project-finding-board-card-detail';
      detail.textContent = card.raw_line;
      article.appendChild(detail);
    }

    const chips = triageChips(finding);
    if (chips.length) {
      const chipWrap = document.createElement('div');
      chipWrap.className = 'project-finding-board-card-chips';
      chips.forEach(chip => chipWrap.appendChild(chip));
      article.appendChild(chipWrap);
    }

    const actions = document.createElement('div');
    actions.className = 'project-finding-board-card-actions';
    if (finding.run_id) {
      const open = document.createElement('button');
      open.type = 'button';
      open.className = 'btn btn-secondary btn-compact';
      open.dataset.findingsBoardAction = 'open-run';
      open.dataset.runId = String(finding.run_id || '');
      open.dataset.runCommand = String(finding.run_command || '');
      open.dataset.lineIndex = Number.isInteger(card.line_number) ? String(card.line_number) : '';
      open.textContent = 'Open';
      actions.appendChild(open);
    }
    if (card.id) {
      const triage = document.createElement('button');
      triage.type = 'button';
      triage.className = 'btn btn-secondary btn-compact';
      triage.dataset.findingsBoardAction = 'edit-triage';
      triage.dataset.findingId = String(card.id || '');
      triage.textContent = 'Triage';
      actions.appendChild(triage);
    }
    actions.appendChild(reviewSelect(finding));
    article.appendChild(actions);
    return article;
  }

  function renderColumn(column) {
    const section = document.createElement('section');
    section.className = 'project-finding-board-column findings-board-column';
    section.dataset.findingsBoardDropState = column.state;
    section.setAttribute('aria-labelledby', `findings-board-${column.state}`);

    const header = document.createElement('div');
    header.className = 'project-finding-board-column-header';
    const title = document.createElement('h3');
    title.id = `findings-board-${column.state}`;
    title.textContent = column.label;
    const count = document.createElement('span');
    count.className = 'project-finding-board-column-count';
    count.textContent = String(column.total || 0);
    header.append(title, count);
    section.appendChild(header);

    const body = document.createElement('div');
    body.className = 'project-finding-board-column-body';
    if (column.cards.length) {
      column.cards.forEach(card => body.appendChild(renderCard(card)));
    } else {
      const empty = document.createElement('div');
      empty.className = 'project-finding-board-empty';
      empty.textContent = 'No findings';
      body.appendChild(empty);
    }
    if (column.truncated) {
      const truncated = document.createElement('div');
      truncated.className = 'project-finding-board-truncated';
      truncated.textContent = `Showing ${column.cards.length} of ${column.total}`;
      body.appendChild(truncated);
    }
    section.appendChild(body);
    return section;
  }

  function render() {
    if (!bodyEl) return;
    bodyEl.replaceChildren();
    if (titleEl) titleEl.textContent = 'FINDINGS BOARD';
    if (subtitleEl) {
      const total = Number(state.total || state.findings.length || 0);
      const suffix = state.hasMore ? ` · showing first ${state.findings.length}` : '';
      subtitleEl.textContent = `${state.scopeLabel} · ${total.toLocaleString()} ${total === 1 ? 'finding' : 'findings'}${suffix}`;
    }
    if (state.loading) {
      const loading = document.createElement('div');
      loading.className = 'findings-board-empty-state';
      loading.textContent = 'Loading findings...';
      bodyEl.appendChild(loading);
      return;
    }
    if (!state.findings.length) {
      const empty = document.createElement('div');
      empty.className = 'findings-board-empty-state';
      empty.textContent = 'No findings match this board scope.';
      bodyEl.appendChild(empty);
      return;
    }
    const columns = boardApi().boardColumnsFromFindings
      ? boardApi().boardColumnsFromFindings(state.findings, { limit: COLUMN_LIMIT }).columns.map((column) => {
          if (!state.columnTotals || typeof state.columnTotals !== 'object') return column;
          const total = Number(state.columnTotals[column.state] ?? column.total ?? 0);
          return {
            ...column,
            total,
            truncated: total > column.cards.length || !!column.truncated,
          };
        })
      : [];
    const board = document.createElement('div');
    board.className = 'project-finding-board findings-board-grid';
    board.setAttribute('aria-label', 'Finding triage board');
    columns.forEach(column => board.appendChild(renderColumn(column)));
    bodyEl.appendChild(board);
  }

  async function fetchFindings(endpoint) {
    const resp = await api()(endpoint, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
  }

  function applySinglePage(data = {}) {
    state.findings = Array.isArray(data.findings) ? data.findings : [];
    state.total = Number(data.total || state.findings.length || 0);
    state.hasMore = !!data.has_more;
    state.columnTotals = null;
  }

  async function loadSinglePageFindings() {
    const data = await fetchFindings(state.endpoint);
    applySinglePage(data);
  }

  async function loadColumnPageFindings() {
    const requests = COLUMN_STATE_QUERIES.flatMap(({ column, states }) => (
      states.map(reviewState => ({ column, endpoint: endpointWithReviewState(state.endpoint, reviewState) }))
    ));
    const pages = await Promise.all(requests.map(async request => ({
      ...request,
      data: await fetchFindings(request.endpoint),
    })));
    const seenIds = new Set();
    const findings = [];
    const columnTotals = COLUMN_STATE_QUERIES.reduce((acc, item) => {
      acc[item.column] = 0;
      return acc;
    }, {});
    let total = 0;
    let hasMore = false;
    pages.forEach(({ column, data }) => {
      const rows = Array.isArray(data.findings) ? data.findings : [];
      const pageTotal = Number(data.total || rows.length || 0);
      columnTotals[column] = Number(columnTotals[column] || 0) + pageTotal;
      total += pageTotal;
      hasMore = hasMore || !!data.has_more;
      rows.forEach((finding) => {
        const findingId = String(finding && finding.id || '');
        if (findingId && seenIds.has(findingId)) return;
        if (findingId) seenIds.add(findingId);
        findings.push(finding);
      });
    });
    state.findings = findings;
    state.total = total;
    state.hasMore = hasMore;
    state.columnTotals = columnTotals;
  }

  async function loadFindings() {
    if (!state.endpoint) return;
    setBusy(true);
    showMessage('');
    render();
    try {
      if (hasReviewStateFilter(state.endpoint)) await loadSinglePageFindings();
      else await loadColumnPageFindings();
    } catch (err) {
      state.findings = [];
      state.total = 0;
      state.hasMore = false;
      state.columnTotals = null;
      showMessage(err && err.message ? err.message : 'Could not load findings.', 'error');
      if (typeof importedLogClientError === 'function') importedLogClientError('failed to load findings board', err);
    } finally {
      setBusy(false);
      render();
    }
  }

  async function persistReviewState(findingId, reviewState, previousReviewState) {
    const finding = findingById(findingId);
    if (!finding || !reviewState || reviewState === previousReviewState) return;
    if (!canTriageFindings()) {
      setFindingReviewState(findingId, previousReviewState || 'new');
      showMessage(triageDeniedMessage(), 'error');
      render();
      return;
    }
    setFindingReviewState(findingId, reviewState);
    render();
    try {
      const projectScoped = state.source === 'project' && state.projectId;
      const resp = await api()(
        projectScoped
          ? `/projects/${encodeURIComponent(state.projectId)}/findings/review`
          : `/findings/${encodeURIComponent(findingId)}/review`,
        {
          method: projectScoped ? 'POST' : 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(
            projectScoped
              ? { finding_ids: [findingId], review_state: reviewState }
              : { review_state: reviewState },
          ),
        },
      );
      if (!resp.ok) {
        let message = `HTTP ${resp.status}`;
        try {
          const data = await resp.json();
          if (data && data.error === 'team_forbidden') message = triageDeniedMessage();
          else if (data && typeof data.message === 'string' && data.message.trim()) message = data.message.trim();
        } catch (_) {}
        throw new Error(message);
      }
      const data = await resp.json().catch(() => null);
      const authoritativeReviewState = data && data.finding
        ? data.finding.review_state
        : data?.review_state;
      setFindingReviewState(findingId, authoritativeReviewState || reviewState);
      if (projectScoped && data && Number(data.counts?.updated || 0) <= 0) {
        throw new Error('Finding was no longer available in this project.');
      }
      showMessage('');
      if (typeof emitUiEvent === 'function') {
        emitUiEvent('app:project-workspace-mutated', {
          reason: 'finding-review-updated',
          project_id: state.projectId,
          finding_id: findingId,
        });
      }
      render();
    } catch (err) {
      setFindingReviewState(findingId, previousReviewState || 'new');
      showMessage(err && err.message ? err.message : 'Could not update finding review state.', 'error');
      if (typeof importedLogClientError === 'function') importedLogClientError('failed to update findings board review state', err);
      render();
    }
  }
  async function openFindingTriage(findingId) {
    const finding = findingById(findingId);
    if (!finding) {
      showMessage('Finding is missing its details.', 'error');
      return;
    }
    if (!findingTriageEditor || typeof findingTriageEditor.open !== 'function') {
      showMessage('Finding triage editor is not available.', 'error');
      return;
    }
    showMessage('');
    await findingTriageEditor.open(finding, {
      canEdit: canTriageFindings(),
      onSaved: async (triage) => {
        const compact = typeof findingTriageEditor.compactTriage === 'function'
          ? findingTriageEditor.compactTriage(triage)
          : triage;
        updateFindingTriage(findingId, compact);
        render();
        showMessage('Finding triage saved.');
        if (typeof emitUiEvent === 'function') {
          emitUiEvent('app:project-workspace-mutated', {
            reason: 'finding-triage-updated',
            project_id: state.projectId,
            finding_id: findingId,
          });
        }
      },
    });
  }

  async function openFindingsBoard(options = {}) {
    if (!overlay || !bodyEl) return false;
    if (typeof importedCloseMajorOverlays === 'function') importedCloseMajorOverlays();
    if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
    state.endpoint = endpointFromOptions(options);
    state.findings = [];
    state.total = 0;
    state.hasMore = false;
    state.columnTotals = null;
    show();
    await loadFindings();
    return true;
  }

  if (overlay && typeof bindDismissible === 'function') {
    bindDismissible(overlay, {
      level: 'modal',
      isOpen,
      onClose: closeFindingsBoard,
      closeButtons: Array.from(overlay.querySelectorAll('.findings-board-close, .sheet-grab')),
    });
  } else {
    closeBtn?.addEventListener('click', () => closeFindingsBoard());
    grabHandle?.addEventListener('click', () => closeFindingsBoard());
    overlay?.addEventListener('click', event => {
      if (event.target === overlay) closeFindingsBoard();
    });
  }
  refreshBtn?.addEventListener('click', () => {
    void loadFindings();
  });
  bodyEl?.addEventListener('change', event => {
    const control = event.target.closest?.('[data-findings-board-review]');
    if (!control) return;
    event.preventDefault();
    const findingId = String(control.dataset.findingId || '');
    const reviewState = String(control.value || 'new');
    const previousReviewState = String(control.dataset.previousReviewState || 'new');
    control.dataset.previousReviewState = reviewState;
    void persistReviewState(findingId, reviewState, previousReviewState);
  });
  bodyEl?.addEventListener('click', event => {
    const action = event.target.closest?.('[data-findings-board-action]');
    if (!action) return;
    if (action.dataset.findingsBoardAction === 'open-run') {
      event.preventDefault();
      let opened = false;
      if (typeof restoreHistoryRunIntoTab === 'function') {
        const lineIndex = Number(action.dataset.lineIndex || '');
        void restoreHistoryRunIntoTab({
          id: action.dataset.runId || '',
          command: action.dataset.runCommand || '',
          full_output_available: true,
        }, {
          hidePanelOnSuccess: false,
          highlightLineIndex: Number.isInteger(lineIndex) ? lineIndex : null,
        });
        opened = true;
      } else if (typeof global.dispatchEvent === 'function') {
        global.dispatchEvent(new CustomEvent(LINE_OPEN_EVENT, { detail: { runId: action.dataset.runId || '' } }));
        opened = true;
      }
      if (opened) closeFindingsBoard({ refocus: false });
      return;
    }
    if (action.dataset.findingsBoardAction === 'edit-triage') {
      event.preventDefault();
      void openFindingTriage(String(action.dataset.findingId || ''));
    }
  });
  bodyEl?.addEventListener('dragstart', event => {
    if (!canTriageFindings()) {
      event.preventDefault();
      showMessage(triageDeniedMessage(), 'error');
      return;
    }
    const card = event.target.closest?.('[data-finding-id]');
    if (!card) return;
    state.draggedId = String(card.dataset.findingId || '');
    event.dataTransfer?.setData('text/plain', state.draggedId);
    card.classList.add('is-dragging');
  });
  bodyEl?.addEventListener('dragend', event => {
    event.target.closest?.('[data-finding-id]')?.classList.remove('is-dragging');
    state.draggedId = '';
    bodyEl.querySelectorAll('.is-drop-target').forEach(item => item.classList.remove('is-drop-target'));
  });
  bodyEl?.addEventListener('dragover', event => {
    if (!canTriageFindings()) return;
    const column = event.target.closest?.('[data-findings-board-drop-state]');
    if (!column || !state.draggedId) return;
    event.preventDefault();
    column.classList.add('is-drop-target');
  });
  bodyEl?.addEventListener('dragleave', event => {
    event.target.closest?.('[data-findings-board-drop-state]')?.classList.remove('is-drop-target');
  });
  bodyEl?.addEventListener('drop', event => {
    if (!canTriageFindings()) {
      event.preventDefault();
      state.draggedId = '';
      bodyEl.querySelectorAll('.is-drop-target').forEach(item => item.classList.remove('is-drop-target'));
      showMessage(triageDeniedMessage(), 'error');
      return;
    }
    const column = event.target.closest?.('[data-findings-board-drop-state]');
    if (!column) return;
    event.preventDefault();
    column.classList.remove('is-drop-target');
    const findingId = event.dataTransfer?.getData('text/plain') || state.draggedId;
    const reviewState = String(column.dataset.findingsBoardDropState || 'new');
    const previous = String(findingById(findingId)?.review_state || 'new');
    void persistReviewState(findingId, reviewState, previous);
  });

  exportedOpenFindingsBoard = openFindingsBoard;
  exportedCloseFindingsBoard = closeFindingsBoard;
  exportedIsFindingsBoardOpen = isOpen;
})(globalThis);

export {
  exportedOpenFindingsBoard as openFindingsBoard,
  exportedCloseFindingsBoard as closeFindingsBoard,
  exportedIsFindingsBoardOpen as isFindingsBoardOpen,
};
