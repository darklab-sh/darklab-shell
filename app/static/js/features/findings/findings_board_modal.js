// First-class findings triage board modal.
// Reuses the shared project findings board adapter so list and board surfaces
// keep the same review-state grouping rules.

(function findingsBoardModalModule(global) {
  'use strict';

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
    draggedId: '',
  };

  function api() {
    return typeof apiFetch === 'function' ? apiFetch : global.apiFetch;
  }

  function boardApi() {
    return global.DarklabProjectFindingsData || {};
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
    if (typeof global.syncModalOverlayState === 'function') global.syncModalOverlayState();
    if (refocus && typeof global.refocusComposerAfterAction === 'function') {
      global.refocusComposerAfterAction({ defer: true });
    }
  }

  function show() {
    if (!overlay) return;
    overlay.classList.remove('u-hidden');
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    state.open = true;
    if (typeof global.syncModalOverlayState === 'function') global.syncModalOverlayState();
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

  function setFindingReviewState(findingId, reviewState) {
    const normalized = String(findingId || '');
    state.findings = state.findings.map(finding => (
      String(finding && finding.id || '') === normalized
        ? { ...finding, review_state: reviewState }
        : finding
    ));
  }

  function reviewSelect(finding) {
    const select = document.createElement('select');
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
    article.draggable = !!card.id;
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
      const important = document.createElement('span');
      important.className = 'project-finding-board-badge is-important';
      important.textContent = 'important';
      badges.appendChild(important);
    }
    if (card.severity) {
      const severity = document.createElement('span');
      severity.className = 'project-finding-board-badge';
      severity.textContent = card.severity;
      badges.appendChild(severity);
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
      ? boardApi().boardColumnsFromFindings(state.findings, { limit: COLUMN_LIMIT }).columns
      : [];
    const board = document.createElement('div');
    board.className = 'project-finding-board findings-board-grid';
    board.setAttribute('aria-label', 'Finding triage board');
    columns.forEach(column => board.appendChild(renderColumn(column)));
    bodyEl.appendChild(board);
  }

  async function loadFindings() {
    if (!state.endpoint) return;
    setBusy(true);
    showMessage('');
    render();
    try {
      const resp = await api()(state.endpoint, { cache: 'no-store' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      state.findings = Array.isArray(data.findings) ? data.findings : [];
      state.total = Number(data.total || state.findings.length || 0);
      state.hasMore = !!data.has_more;
    } catch (err) {
      state.findings = [];
      state.total = 0;
      state.hasMore = false;
      showMessage(err && err.message ? err.message : 'Could not load findings.', 'error');
      if (typeof global.logClientError === 'function') global.logClientError('failed to load findings board', err);
    } finally {
      setBusy(false);
      render();
    }
  }

  async function persistReviewState(findingId, reviewState, previousReviewState) {
    const finding = findingById(findingId);
    if (!finding || !reviewState || reviewState === previousReviewState) return;
    setFindingReviewState(findingId, reviewState);
    render();
    try {
      const resp = await api()(`/findings/${encodeURIComponent(findingId)}/review`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ review_state: reviewState }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json().catch(() => null);
      if (data && data.finding) setFindingReviewState(findingId, data.finding.review_state || reviewState);
      showMessage('');
      if (typeof global.emitUiEvent === 'function') {
        global.emitUiEvent('app:project-workspace-mutated', {
          reason: 'finding-review-updated',
          project_id: state.projectId,
          finding_id: findingId,
        });
      }
    } catch (err) {
      setFindingReviewState(findingId, previousReviewState || 'new');
      showMessage(err && err.message ? err.message : 'Could not update finding review state.', 'error');
      if (typeof global.logClientError === 'function') global.logClientError('failed to update findings board review state', err);
    } finally {
      render();
    }
  }

  async function openFindingsBoard(options = {}) {
    if (!overlay || !bodyEl) return false;
    if (typeof global._closeMajorOverlays === 'function') global._closeMajorOverlays();
    if (typeof global.blurVisibleComposerInputIfMobile === 'function') global.blurVisibleComposerInputIfMobile();
    state.endpoint = endpointFromOptions(options);
    state.findings = [];
    state.total = 0;
    state.hasMore = false;
    show();
    await loadFindings();
    return true;
  }

  if (overlay && typeof global.bindDismissible === 'function') {
    global.bindDismissible(overlay, {
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
      if (typeof global.restoreHistoryRunIntoTab === 'function') {
        const lineIndex = Number(action.dataset.lineIndex || '');
        void global.restoreHistoryRunIntoTab({
          id: action.dataset.runId || '',
          command: action.dataset.runCommand || '',
          full_output_available: true,
        }, {
          hidePanelOnSuccess: false,
          highlightLineIndex: Number.isInteger(lineIndex) ? lineIndex : null,
        });
      } else if (typeof global.dispatchEvent === 'function') {
        global.dispatchEvent(new CustomEvent(LINE_OPEN_EVENT, { detail: { runId: action.dataset.runId || '' } }));
      }
    }
  });
  bodyEl?.addEventListener('dragstart', event => {
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
    const column = event.target.closest?.('[data-findings-board-drop-state]');
    if (!column || !state.draggedId) return;
    event.preventDefault();
    column.classList.add('is-drop-target');
  });
  bodyEl?.addEventListener('dragleave', event => {
    event.target.closest?.('[data-findings-board-drop-state]')?.classList.remove('is-drop-target');
  });
  bodyEl?.addEventListener('drop', event => {
    const column = event.target.closest?.('[data-findings-board-drop-state]');
    if (!column) return;
    event.preventDefault();
    column.classList.remove('is-drop-target');
    const findingId = event.dataTransfer?.getData('text/plain') || state.draggedId;
    const reviewState = String(column.dataset.findingsBoardDropState || 'new');
    const previous = String(findingById(findingId)?.review_state || 'new');
    void persistReviewState(findingId, reviewState, previous);
  });

  global.openFindingsBoard = openFindingsBoard;
  global.closeFindingsBoard = closeFindingsBoard;
  global.isFindingsBoardOpen = isOpen;
})(globalThis);
