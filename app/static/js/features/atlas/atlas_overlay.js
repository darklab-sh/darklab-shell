// Session Entity Atlas overlay controller.

(function initAtlasOverlay(global) {
  const tabsApi = global.DarklabAtlasTabs || {};
  const detailApi = global.DarklabAtlasDetail || {};
  const metadataApi = global.DarklabEntityMetadata || {};

  const overlay = document.getElementById('atlas-overlay');
  const surface = document.getElementById('atlas-surface');
  const shell = surface?.querySelector?.('.atlas-shell') || document.querySelector('.atlas-shell');
  const closeBtn = document.querySelector('.atlas-close');
  const tabsHost = document.getElementById('atlas-tabs');
  const subtitle = document.getElementById('atlas-subtitle');
  const searchInput = document.getElementById('atlas-search');
  const findingStatusFilter = document.getElementById('atlas-finding-status-filter');
  const orphanFilter = document.getElementById('atlas-orphan-filter');
  const exportWrap = document.getElementById('atlas-export-wrap');
  const exportMenuBtn = document.getElementById('atlas-export-menu-btn');
  const exportCsvBtn = document.getElementById('atlas-export-csv-btn');
  const exportJsonlBtn = document.getElementById('atlas-export-jsonl-btn');
  const refreshBtn = document.getElementById('atlas-refresh-btn');
  const findingBulkRow = document.getElementById('atlas-finding-bulk-row');
  const selectToggle = document.getElementById('atlas-select-toggle');
  const findingSelectionSummary = document.getElementById('atlas-finding-selection-summary');
  const findingSelectAllBtn = document.getElementById('atlas-finding-select-all');
  const findingClearSelectionBtn = document.getElementById('atlas-finding-clear-selection');
  const findingBulkStatus = document.getElementById('atlas-finding-bulk-status');
  const findingBulkApplyBtn = document.getElementById('atlas-finding-bulk-apply');
  const bulkDeleteBtn = document.getElementById('atlas-bulk-delete');
  const listHost = document.getElementById('atlas-list');
  const detailHost = document.getElementById('atlas-detail');
  const pagination = document.getElementById('atlas-pagination');
  const paginationSummary = document.getElementById('atlas-pagination-summary');
  const prevBtn = document.getElementById('atlas-prev-btn');
  const nextBtn = document.getElementById('atlas-next-btn');

  const state = {
    activeTab: 'findings',
    summary: null,
    entities: [],
    findings: [],
    findingCounts: {},
    selectedFindingId: '',
    selectedFindingIds: new Set(),
    selectedEntityIds: new Set(),
    selectMode: false,
    bulkInFlight: false,
    findingStatus: '',
    orphanFilter: 'hide',
    total: 0,
    limit: 50,
    offset: 0,
    query: '',
    projectId: '',
    projectName: '',
    loading: false,
    selectedId: '',
    requestedEntityValue: '',
    refreshIntelOnSelect: false,
    addActiveProjectOnSelect: false,
    detail: null,
    detailLoading: false,
    searchTimer: null,
    refreshSeq: 0,
  };

  function api() {
    if (typeof global.apiFetch === 'function') return global.apiFetch;
    if (typeof apiFetch === 'function') return apiFetch;
    return fetch;
  }

  function showToastSafe(message, tone = 'info') {
    if (typeof global.showToast === 'function') global.showToast(message, tone);
  }

  function broadcastProjectWorkspaceChange(reason, projectId) {
    const payload = {
      reason: String(reason || 'updated'),
      project_id: String(projectId || ''),
      changed_at: Date.now(),
    };
    if (typeof global.emitUiEvent === 'function') {
      global.emitUiEvent('app:project-workspace-changed', payload);
      global.emitUiEvent('app:project-workspace-mutated', payload);
    }
    try {
      if (typeof localStorage !== 'undefined' && localStorage && typeof localStorage.setItem === 'function') {
        localStorage.setItem('darklab_project_workspace_changed', JSON.stringify(payload));
      }
    } catch (_) {
      // Cross-tab refresh is best-effort; the local Atlas refresh still completes.
    }
  }

  function text(value, fallback = '') {
    return detailApi.text ? detailApi.text(value, fallback) : (String(value ?? '').trim() || fallback);
  }

  function countLabel(count, singular, plural) {
    const numeric = Number(count || 0);
    return `${numeric.toLocaleString()} ${numeric === 1 ? singular : plural}`;
  }

  const findingStates = [
    ['new', 'New'],
    ['reviewed', 'Reviewed'],
    ['important', 'Important'],
    ['false_positive', 'False positive'],
    ['needs_followup', 'Follow-up'],
  ];

  function isOpen() {
    return !!(overlay && overlay.classList.contains('open'));
  }

  function show() {
    if (!overlay) return;
    overlay.classList.remove('u-hidden');
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
  }

  function hide({ refocus = true } = {}) {
    if (!overlay) return;
    resetSelection({ selectMode: false, render: false });
    overlay.classList.add('u-hidden');
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    if (refocus && typeof global.refocusComposerAfterAction === 'function') {
      global.refocusComposerAfterAction({ defer: true });
    }
  }

  async function openAtlas(options = {}) {
    if (typeof global._closeMajorOverlays === 'function') global._closeMajorOverlays();
    if (typeof global.blurVisibleComposerInputIfMobile === 'function') global.blurVisibleComposerInputIfMobile();
    if (options && options.tab) state.activeTab = tabsApi.tabById?.(options.tab)?.id || state.activeTab;
    state.projectId = String(options && options.projectId || '');
    state.projectName = String(options && options.projectName || '').trim();
    state.requestedEntityValue = String(options && options.entityValue || '').trim();
    state.refreshIntelOnSelect = !!(options && options.refreshIntel);
    state.addActiveProjectOnSelect = !!(options && options.addActiveProject);
    if (state.requestedEntityValue) {
      state.query = state.requestedEntityValue;
      if (searchInput) searchInput.value = state.query;
    } else {
      state.query = '';
      if (searchInput) searchInput.value = '';
    }
    state.selectedId = '';
    state.selectedFindingId = '';
    resetSelection({ selectMode: false, render: false });
    state.detail = null;
    show();
    if (typeof global.markInteractionSurfaceReady === 'function') {
      global.markInteractionSurfaceReady('atlas', overlay, surface);
    }
    render();
    await refreshAtlas({ resetOffset: true });
  }

  function closeAtlas(options = {}) {
    hide(options);
  }

  function currentTab() {
    return tabsApi.tabById ? tabsApi.tabById(state.activeTab) : { id: 'findings', type: '', label: 'Findings' };
  }

  function activeSelectionSet(tab = currentTab()) {
    return tab.id === 'findings' ? state.selectedFindingIds : state.selectedEntityIds;
  }

  function visibleSelectableItems(tab = currentTab()) {
    return tab.id === 'findings' ? state.findings : state.entities;
  }

  function resetSelection({ selectMode = state.selectMode, render = true } = {}) {
    state.selectMode = !!selectMode;
    state.bulkInFlight = false;
    state.selectedFindingIds.clear();
    state.selectedEntityIds.clear();
    if (render) render();
  }

  function setSelectMode(enabled) {
    state.selectMode = !!enabled;
    if (!state.selectMode) {
      state.selectedFindingIds.clear();
      state.selectedEntityIds.clear();
    }
    render();
  }

  function toggleItemSelection(item, checked = null) {
    if (!item || !item.id || state.bulkInFlight) return;
    const selected = activeSelectionSet();
    const id = String(item.id);
    const shouldSelect = checked === null ? !selected.has(id) : !!checked;
    if (shouldSelect) selected.add(id);
    else selected.delete(id);
    render();
  }

  function selectAllVisibleItems() {
    if (!state.selectMode || state.bulkInFlight) return;
    const selected = activeSelectionSet();
    const items = visibleSelectableItems().filter(item => item && item.id);
    const allSelected = items.length > 0 && items.every(item => selected.has(String(item.id)));
    items.forEach((item) => {
      const id = String(item.id);
      if (allSelected) selected.delete(id);
      else selected.add(id);
    });
    render();
  }

  function renderTabs() {
    if (!tabsHost) return;
    tabsHost.replaceChildren();
    (tabsApi.tabs || []).forEach(tab => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'toggle-btn history-run-tab atlas-tab';
      button.dataset.atlasTab = tab.id;
      button.setAttribute('role', 'tab');
      button.setAttribute('aria-selected', tab.id === state.activeTab ? 'true' : 'false');
      button.setAttribute('aria-pressed', tab.id === state.activeTab ? 'true' : 'false');
      button.classList.toggle('active', tab.id === state.activeTab);
      button.classList.toggle('is-active', tab.id === state.activeTab);
      const label = document.createElement('span');
      label.textContent = tab.label;
      const count = document.createElement('span');
      count.className = 'atlas-tab-count';
      count.textContent = String(tabsApi.countForTab ? tabsApi.countForTab(tab, state.summary) : 0);
      button.append(label, count);
      button.addEventListener('click', () => {
        if (state.activeTab === tab.id) return;
        state.activeTab = tab.id;
        state.offset = 0;
        state.selectedId = '';
        state.selectedFindingId = '';
        resetSelection({ selectMode: state.selectMode, render: false });
        state.requestedEntityValue = '';
        state.refreshIntelOnSelect = false;
        state.addActiveProjectOnSelect = false;
        state.detail = null;
        render();
        refreshAtlas({ resetOffset: true });
      });
      tabsHost.appendChild(button);
    });
  }

  function renderSubtitle() {
    if (!subtitle) return;
    const total = tabsApi.totalEntityCount ? tabsApi.totalEntityCount(state.summary) : Number(state.summary?.total || 0);
    const base = `${total.toLocaleString()} ${total === 1 ? 'entity' : 'entities'}`;
    const findingCount = Number(state.summary?.findings || 0);
    const summary = `${base} · ${findingCount.toLocaleString()} ${findingCount === 1 ? 'finding' : 'findings'}`;
    subtitle.textContent = state.projectId && state.projectName ? `${summary} · ${state.projectName}` : summary;
  }

  function populateFindingControls() {
    const option = (label, value) => {
      const item = document.createElement('option');
      item.value = value;
      item.textContent = label;
      return item;
    };
    if (findingStatusFilter && !findingStatusFilter.dataset.populated) {
      findingStatusFilter.appendChild(option('All findings', ''));
      findingStates.forEach(([value, label]) => findingStatusFilter.appendChild(option(label, value)));
      findingStatusFilter.dataset.populated = '1';
    }
    if (findingBulkStatus && !findingBulkStatus.dataset.populated) {
      findingStates.forEach(([value, label]) => findingBulkStatus.appendChild(option(label, value)));
      findingBulkStatus.value = 'reviewed';
      findingBulkStatus.dataset.populated = '1';
    }
    if (orphanFilter && !orphanFilter.dataset.populated) {
      orphanFilter.appendChild(option('Hide orphaned', 'hide'));
      orphanFilter.appendChild(option('Show all', 'all'));
      orphanFilter.appendChild(option('Only orphaned', 'only'));
      orphanFilter.value = state.orphanFilter;
      orphanFilter.dataset.populated = '1';
    }
    syncSelectDisplay(findingStatusFilter);
    syncSelectDisplay(findingBulkStatus);
    syncSelectDisplay(orphanFilter);
  }

  function syncSelectDisplay(select) {
    if (!select) return;
    if (typeof global.syncAppSelect === 'function') {
      global.syncAppSelect(select);
    }
  }

  function setSelectVisibility(select, hidden) {
    if (!select) return;
    select.classList.toggle('u-hidden', hidden);
    const enhancedWrap = select.nextElementSibling;
    if (enhancedWrap && enhancedWrap.classList?.contains('app-select')) {
      enhancedWrap.classList.toggle('u-hidden', hidden);
    }
  }

  function renderFindingControls() {
    populateFindingControls();
    const tab = currentTab();
    const findingsActive = tab.id === 'findings';
    const visibleItems = visibleSelectableItems(tab).filter(item => item && item.id);
    const selected = activeSelectionSet(tab);
    const selectedCount = selected.size;
    const allSelected = visibleItems.length > 0 && visibleItems.every(item => selected.has(String(item.id)));
    const someSelected = visibleItems.some(item => selected.has(String(item.id)));
    setSelectVisibility(findingStatusFilter, !findingsActive);
    setSelectVisibility(findingBulkStatus, !findingsActive || !state.selectMode);
    findingBulkApplyBtn?.classList.toggle('u-hidden', !findingsActive || !state.selectMode);
    exportWrap?.classList.toggle('u-hidden', findingsActive);
    findingBulkRow?.classList.toggle('u-hidden', !state.selectMode && !visibleItems.length);
    if (selectToggle) {
      selectToggle.checked = !!state.selectMode;
      selectToggle.disabled = state.bulkInFlight;
    }
    if (findingStatusFilter) {
      findingStatusFilter.value = state.findingStatus;
      syncSelectDisplay(findingStatusFilter);
    }
    syncSelectDisplay(findingBulkStatus);
    if (orphanFilter) {
      orphanFilter.value = state.orphanFilter;
      syncSelectDisplay(orphanFilter);
    }
    if (findingSelectionSummary) {
      findingSelectionSummary.textContent = `${selectedCount.toLocaleString()} selected`;
      findingSelectionSummary.setAttribute('aria-live', 'polite');
    }
    if (findingSelectAllBtn) {
      findingSelectAllBtn.classList.toggle('u-hidden', !state.selectMode);
      findingSelectAllBtn.textContent = allSelected && someSelected ? 'Deselect all' : 'Select all';
      findingSelectAllBtn.disabled = !state.selectMode || !visibleItems.length || state.loading || state.bulkInFlight;
      findingSelectAllBtn.setAttribute('aria-pressed', allSelected && someSelected ? 'true' : someSelected ? 'mixed' : 'false');
    }
    if (findingClearSelectionBtn) {
      findingClearSelectionBtn.classList.toggle('u-hidden', !state.selectMode);
      findingClearSelectionBtn.disabled = !selectedCount || state.loading || state.bulkInFlight;
    }
    if (findingBulkApplyBtn) findingBulkApplyBtn.disabled = !selectedCount || state.loading || state.bulkInFlight;
    if (bulkDeleteBtn) {
      bulkDeleteBtn.classList.toggle('u-hidden', !state.selectMode);
      bulkDeleteBtn.disabled = !selectedCount || state.loading || state.bulkInFlight;
    }
  }

  function findingStatusLabel(value) {
    const found = findingStates.find(([stateValue]) => stateValue === String(value || ''));
    return found ? found[1] : text(value, 'New');
  }

  function findingRow(finding) {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'chrome-row chrome-row-clickable atlas-finding-queue-row';
    row.classList.toggle('is-selecting', state.selectMode);
    row.classList.toggle(
      'is-selected',
      state.selectMode
        ? state.selectedFindingIds.has(String(finding.id || ''))
        : finding.id === state.selectedFindingId,
    );
    row.dataset.findingId = finding.id;

    const main = document.createElement('span');
    main.className = 'atlas-entity-main';
    const title = document.createElement('span');
    title.className = 'atlas-finding-title';
    title.textContent = text(finding.title || finding.raw_line, finding.id);
    const meta = document.createElement('span');
    meta.className = 'atlas-muted';
    meta.textContent = [
      findingStatusLabel(finding.review_state || finding.status),
      text(finding.severity),
      text(finding.tool_root),
      text(finding.entity_value || finding.subject_key),
    ].filter(Boolean).join(' · ');
    main.append(title, meta);

    const badges = document.createElement('span');
    badges.className = 'atlas-entity-badges';
    badges.appendChild(badge(findingStatusLabel(finding.review_state || finding.status), 'green'));
    if (finding.occurrence_count) badges.appendChild(badge(countLabel(finding.occurrence_count, 'hit', 'hits'), 'muted'));
    if (state.selectMode) {
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'atlas-finding-select atlas-row-select';
      checkbox.checked = state.selectedFindingIds.has(String(finding.id || ''));
      checkbox.setAttribute('aria-label', `Select finding: ${finding.title || finding.id}`);
      checkbox.addEventListener('click', (event) => {
        event.stopPropagation();
        toggleItemSelection(finding, checkbox.checked);
      });
      row.appendChild(checkbox);
    }
    row.append(main, badges);
    row.addEventListener('click', () => {
      if (state.selectMode) {
        toggleItemSelection(finding);
        return;
      }
      selectFinding(finding.id);
    });
    return row;
  }

  function renderList() {
    if (!listHost) return;
    listHost.replaceChildren();
    const tab = currentTab();
    if (state.loading) {
      listHost.appendChild(rowMessage('Loading Atlas...'));
      return;
    }
    if (tab.id === 'findings') {
      if (!state.findings.length) {
        listHost.appendChild(rowMessage(state.query || state.findingStatus ? 'No matching findings' : 'No findings queued'));
        return;
      }
      state.findings.forEach(finding => listHost.appendChild(findingRow(finding)));
      return;
    }
    if (!state.entities.length) {
      listHost.appendChild(rowMessage(state.query ? 'No matching entities' : 'No entities yet'));
      return;
    }
    state.entities.forEach(entity => {
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'chrome-row chrome-row-clickable atlas-entity-row';
      row.classList.toggle('is-selecting', state.selectMode);
      row.classList.toggle(
        'is-selected',
        state.selectMode
          ? state.selectedEntityIds.has(String(entity.id || ''))
          : entity.id === state.selectedId,
      );
      row.dataset.entityId = entity.id;

      const main = document.createElement('span');
      main.className = 'atlas-entity-main';
      const value = document.createElement('span');
      value.className = 'atlas-entity-value';
      value.textContent = text(entity.canonical_value, entity.id);
      const meta = document.createElement('span');
      meta.className = 'atlas-muted';
      const runCount = Number(entity.run_count || 0);
      const occurrenceCount = Number(entity.occurrence_count || 0);
      meta.textContent = `${countLabel(occurrenceCount, 'hit', 'hits')} · ${countLabel(runCount, 'run', 'runs')}`;
      main.append(value, meta);

      const badges = document.createElement('span');
      badges.className = 'atlas-entity-badges';
      if (entity.project_link_count) badges.appendChild(badge(`${entity.project_link_count} projects`, 'green'));
      const labels = Array.isArray(entity.labels) ? entity.labels : [];
      labels.slice(0, 2).forEach(label => badges.appendChild(badge(text(label.label || label), 'muted')));

      if (state.selectMode) {
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'atlas-row-select';
        checkbox.checked = state.selectedEntityIds.has(String(entity.id || ''));
        checkbox.setAttribute('aria-label', `Select entity: ${entity.canonical_value || entity.id}`);
        checkbox.addEventListener('click', (event) => {
          event.stopPropagation();
          toggleItemSelection(entity, checkbox.checked);
        });
        row.appendChild(checkbox);
      }
      row.append(main, badges);
      row.addEventListener('click', () => {
        if (state.selectMode) {
          toggleItemSelection(entity);
          return;
        }
        selectEntity(entity.id);
      });
      listHost.appendChild(row);
    });
  }

  function badge(label, tone) {
    const el = document.createElement('span');
    el.className = `badge ${tone === 'green' ? 'badge-tone-green' : 'badge-tone-muted'}`;
    el.textContent = label;
    return el;
  }

  function rowMessage(message) {
    const row = document.createElement('div');
    row.className = 'atlas-empty';
    row.textContent = message;
    return row;
  }

  function renderPagination() {
    if (!pagination || !paginationSummary || !prevBtn || !nextBtn) return;
    const showPager = state.total > state.limit || state.offset > 0;
    pagination.classList.toggle('u-hidden', !showPager);
    if (!showPager) {
      paginationSummary.textContent = '';
      prevBtn.disabled = true;
      nextBtn.disabled = true;
      return;
    }
    const start = state.total ? state.offset + 1 : 0;
    const end = Math.min(state.offset + state.limit, state.total);
    paginationSummary.textContent = `${start}-${end} of ${state.total.toLocaleString()}`;
    prevBtn.disabled = state.offset <= 0 || state.loading;
    nextBtn.disabled = state.offset + state.limit >= state.total || state.loading;
  }

  function renderDetail() {
    if (!detailHost) return;
    if (state.detailLoading) {
      detailHost.replaceChildren(rowMessage('Loading entity...'));
      return;
    }
    if (currentTab().id === 'findings') {
      const finding = state.findings.find(item => String(item.id || '') === state.selectedFindingId);
      detailApi.renderFindingDetail?.(detailHost, finding, {
        onReviewState: (item, reviewState) => updateFindingReviewState(item, reviewState),
        onSeeRun: (item) => openSourceRun({
          id: item.run_id,
          run_id: item.run_id,
          command: item.run_command,
          run_kind: item.run_kind,
        }),
        onOpenEntity: (item) => openEntityFromFinding(item),
        onDeleteFinding: (item) => confirmDeleteFinding(item),
      });
      return;
    }
    const activeProject = typeof global.getActiveProjectContext === 'function'
      ? global.getActiveProjectContext()
      : null;
    detailApi.renderDetail?.(detailHost, state.detail, {
      activeProject,
      isLinkedToActiveProject: (entity) => {
        const activeId = activeProject && activeProject.id ? String(activeProject.id) : '';
        return !!activeId && (Array.isArray(entity.project_links) ? entity.project_links : [])
          .some(link => String(link.project_id || '') === activeId);
      },
      onRefreshIntel: () => refreshIntel(),
      onAddToActiveProject: () => addToActiveProject(),
      onRemoveProjectLink: (link) => removeProjectLink(link),
      onSaveMetadata: (payload) => saveMetadata(payload),
      onSeeRun: (run) => openSourceRun(run),
      onDeleteEntity: () => confirmDeleteEntity(),
    });
  }

  function render() {
    renderShellMode();
    renderSubtitle();
    renderFindingControls();
    renderTabs();
    renderList();
    renderPagination();
    renderDetail();
  }

  function renderShellMode() {
    shell?.setAttribute('data-atlas-mode', currentTab().id === 'findings' ? 'findings' : 'entity');
  }

  async function refreshAtlas({ resetOffset = false } = {}) {
    if (!overlay || !isOpen()) return;
    if (resetOffset) state.offset = 0;
    const requestId = state.refreshSeq + 1;
    state.refreshSeq = requestId;
    const requestedTab = currentTab();
    const isStale = () => (
      requestId !== state.refreshSeq
      || !isOpen()
      || currentTab().id !== requestedTab.id
    );
    state.loading = true;
    render();
    try {
      const summaryParams = new URLSearchParams({ orphan_filter: state.orphanFilter });
      const summaryResp = await api()(`/atlas?${summaryParams.toString()}`, { cache: 'no-store' });
      if (!summaryResp.ok) throw new Error(`HTTP ${summaryResp.status}`);
      if (isStale()) return;
      state.summary = await summaryResp.json();
      if (isStale()) return;
      const tab = requestedTab;
      if (tab.id === 'findings') {
        const params = new URLSearchParams({
          limit: String(state.limit),
          offset: String(state.offset),
        });
        if (state.query) params.set('q', state.query);
        if (state.projectId) params.set('project_id', state.projectId);
        if (state.findingStatus) params.append('review_state', state.findingStatus);
        params.set('orphan_filter', state.orphanFilter);
        const listResp = await api()(`/atlas/findings?${params.toString()}`, { cache: 'no-store' });
        if (!listResp.ok) throw new Error(`HTTP ${listResp.status}`);
        if (isStale()) return;
        const data = await listResp.json();
        if (isStale()) return;
        state.entities = [];
        state.findings = Array.isArray(data.findings) ? data.findings : [];
        state.findingCounts = data.counts && typeof data.counts === 'object' ? data.counts : {};
        state.total = Number(data.total || 0);
        state.selectedFindingIds.forEach((findingId) => {
          if (!state.findings.some(finding => String(finding.id || '') === findingId)) {
            state.selectedFindingIds.delete(findingId);
          }
        });
        state.selectedEntityIds.clear();
        if (!state.selectedFindingId && state.findings[0]) state.selectedFindingId = state.findings[0].id;
        if (state.selectedFindingId && !state.findings.some(item => String(item.id || '') === state.selectedFindingId)) {
          state.selectedFindingId = state.findings[0]?.id || '';
        }
        state.detail = null;
      } else {
        state.findings = [];
        state.selectedFindingId = '';
        state.selectedFindingIds.clear();
        const params = new URLSearchParams({
          type: tab.type,
          limit: String(state.limit),
          offset: String(state.offset),
        });
        if (state.query) params.set('q', state.query);
        if (state.projectId) params.set('project_id', state.projectId);
        params.set('orphan_filter', state.orphanFilter);
        const listResp = await api()(`/atlas/entities?${params.toString()}`, { cache: 'no-store' });
        if (!listResp.ok) throw new Error(`HTTP ${listResp.status}`);
        if (isStale()) return;
        const data = await listResp.json();
        if (isStale()) return;
        state.entities = Array.isArray(data.entities) ? data.entities : [];
        state.total = Number(data.total || 0);
        if (!state.selectedId && state.requestedEntityValue) {
          const requested = state.requestedEntityValue.toLowerCase();
          const match = state.entities.find(entity => (
            String(entity.canonical_value || entity.value || '').toLowerCase() === requested
          ));
          if (match) state.selectedId = match.id;
          else {
            state.refreshIntelOnSelect = false;
            state.addActiveProjectOnSelect = false;
          }
        }
        if (!state.selectedId && !state.requestedEntityValue && state.entities[0]) state.selectedId = state.entities[0].id;
        state.selectedEntityIds.forEach((entityId) => {
          if (!state.entities.some(entity => String(entity.id || '') === entityId)) {
            state.selectedEntityIds.delete(entityId);
          }
        });
      }
      if (isStale()) return;
      state.loading = false;
      render();
      if (state.selectedId) await loadDetail(state.selectedId, { renderLoading: false });
      else state.detail = null;
      if (state.selectedId && state.refreshIntelOnSelect) {
        state.refreshIntelOnSelect = false;
        await refreshIntel();
      }
      if (state.selectedId && state.addActiveProjectOnSelect) {
        state.addActiveProjectOnSelect = false;
        await addToActiveProject();
      }
    } catch (err) {
      if (typeof global.logClientError === 'function') global.logClientError('failed to load /atlas', err);
      showToastSafe('Failed to load Atlas', 'error');
    } finally {
      if (!isStale()) {
        state.loading = false;
        render();
      }
    }
  }

  async function selectEntity(entityId) {
    state.selectedId = String(entityId || '');
    renderList();
    await loadDetail(state.selectedId);
  }

  function selectFinding(findingId) {
    state.selectedFindingId = String(findingId || '');
    renderList();
    renderDetail();
  }

  async function updateFindingReviewState(finding, reviewState) {
    const findingId = String(finding && finding.id || '');
    if (!findingId || !reviewState) return;
    try {
      const resp = await api()(`/findings/${encodeURIComponent(findingId)}/review`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ review_state: reviewState }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      showToastSafe('Finding updated', 'success');
      await refreshAtlas();
    } catch (err) {
      if (typeof global.logClientError === 'function') global.logClientError('failed to update atlas finding', err);
      showToastSafe('Failed to update finding', 'error');
    }
  }

  async function bulkUpdateFindings() {
    const reviewState = String(findingBulkStatus?.value || '').trim();
    const findingIds = [...state.selectedFindingIds];
    if (!findingIds.length || !reviewState) return;
    try {
      const resp = await api()('/atlas/findings/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ finding_ids: findingIds, review_state: reviewState }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json().catch(() => ({}));
      const updated = Number(data?.counts?.updated || 0);
      const notFound = Number(data?.counts?.not_found || 0);
      showToastSafe(
        notFound ? `Updated ${updated} findings · ${notFound} not found` : `Updated ${updated} findings`,
        notFound ? 'warning' : 'success',
      );
      state.selectedFindingIds.clear();
      await refreshAtlas();
    } catch (err) {
      if (typeof global.logClientError === 'function') global.logClientError('failed to bulk update atlas findings', err);
      showToastSafe('Failed to update findings', 'error');
    }
  }

  function bulkDeleteNoun(tab, count) {
    if (tab.id === 'findings') return count === 1 ? 'finding' : 'findings';
    return count === 1 ? 'entity' : 'entities';
  }

  function bulkDeleteMessage(tab, counts = {}) {
    const deleted = Number(counts.deleted || 0);
    const notFound = Number(counts.not_found || 0);
    const findingsDeleted = Number(counts.findings_deleted || 0);
    const parts = [`Deleted ${deleted.toLocaleString()} ${bulkDeleteNoun(tab, deleted)}`];
    if (findingsDeleted) {
      parts.push(`${findingsDeleted.toLocaleString()} attached ${findingsDeleted === 1 ? 'finding' : 'findings'} removed`);
    }
    if (notFound) parts.push(`${notFound.toLocaleString()} not found`);
    return parts.join(' - ');
  }

  function setBulkBusy(busy) {
    state.bulkInFlight = !!busy;
    render();
  }

  async function bulkDeleteSelectedItems() {
    const tab = currentTab();
    const isFindings = tab.id === 'findings';
    const selected = activeSelectionSet(tab);
    const ids = [...selected];
    if (!ids.length || typeof global.showConfirm !== 'function') return;
    const noun = bulkDeleteNoun(tab, ids.length);
    const note = isFindings
      ? 'This removes the selected findings and cannot be undone.'
      : 'This removes the selected entities and any findings attached to them. This cannot be undone.';
    const choice = await global.showConfirm({
      body: {
        text: `Delete ${ids.length.toLocaleString()} Atlas ${noun}?`,
        note,
      },
      tone: 'warning',
      actions: [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'delete', label: 'Delete', role: 'destructive', tone: 'warning' },
      ],
      refocusOnResolve: false,
    });
    if (choice !== 'delete') return;
    setBulkBusy(true);
    try {
      const url = isFindings ? '/atlas/findings/bulk-delete' : '/atlas/entities/bulk-delete';
      const body = isFindings ? { finding_ids: ids } : { entity_ids: ids };
      const resp = await api()(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json().catch(() => ({}));
      selected.clear();
      const counts = data && typeof data === 'object' && data.counts ? data.counts : {};
      showToastSafe(bulkDeleteMessage(tab, counts), Number(counts.not_found || 0) ? 'warning' : 'success');
      state.selectedId = '';
      state.selectedFindingId = '';
      state.detail = null;
      await refreshAtlas({ resetOffset: state.offset >= state.total - ids.length });
    } catch (err) {
      if (typeof global.logClientError === 'function') global.logClientError('failed to bulk delete atlas rows', err);
      showToastSafe('Failed to delete selected Atlas rows', 'error');
    } finally {
      setBulkBusy(false);
    }
  }

  function openEntityFromFinding(finding) {
    const entityId = String(finding && finding.entity_id || '');
    const entityType = String(finding && finding.entity_type || '');
    if (!entityId || !entityType) return;
    state.activeTab = entityType;
    state.selectedId = entityId;
    state.selectedFindingId = '';
    resetSelection({ selectMode: state.selectMode, render: false });
    state.query = '';
    if (searchInput) searchInput.value = '';
    refreshAtlas({ resetOffset: true });
  }

  async function loadDetail(entityId, { renderLoading = true } = {}) {
    if (!entityId) return;
    state.detailLoading = !!renderLoading;
    if (renderLoading) renderDetail();
    try {
      const resp = await api()(`/atlas/entities/${encodeURIComponent(entityId)}`, { cache: 'no-store' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const detail = await resp.json();
      if (String(state.selectedId || '') !== String(entityId || '') || currentTab().id === 'findings') return;
      state.detail = detail;
    } catch (err) {
      if (String(state.selectedId || '') !== String(entityId || '')) return;
      state.detail = null;
      if (typeof global.logClientError === 'function') global.logClientError('failed to load atlas entity', err);
      showToastSafe('Failed to load entity', 'error');
    } finally {
      if (String(state.selectedId || '') === String(entityId || '')) {
        state.detailLoading = false;
        render();
      }
    }
  }

  async function refreshIntel() {
    if (!state.selectedId) return;
    try {
      const resp = await api()(`/atlas/entities/${encodeURIComponent(state.selectedId)}/refresh_intel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      showToastSafe('Intel refreshed', 'success');
      await loadDetail(state.selectedId);
    } catch (err) {
      if (typeof global.logClientError === 'function') global.logClientError('failed to refresh atlas intel', err);
      showToastSafe('Failed to refresh intel', 'error');
    }
  }

  function cleanupLabel(cleanup) {
    const entities = Number(cleanup?.entities || 0);
    const findings = Number(cleanup?.findings || 0);
    return `${entities.toLocaleString()} ${entities === 1 ? 'entity' : 'entities'} and `
      + `${findings.toLocaleString()} ${findings === 1 ? 'finding' : 'findings'}`;
  }

  function deleteCleanupContent(preview, checkboxId) {
    const cleanup = preview?.sibling_cleanup || {};
    if (!preview?.source_run_id || !cleanup.has_cleanup) return null;
    const wrap = document.createElement('div');
    wrap.className = 'atlas-delete-cleanup-option';
    const label = document.createElement('label');
    label.className = 'form-check';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = checkboxId;
    checkbox.checked = false;
    const textNode = document.createElement('span');
    textNode.textContent = 'Also remove non-curated Atlas items only created by the same run';
    label.append(checkbox, textNode);
    const note = document.createElement('div');
    note.className = 'atlas-muted';
    const curated = Number(cleanup.curated_total || 0);
    note.textContent = `This will remove ${cleanupLabel(cleanup)}.`;
    wrap.append(label, note);
    if (curated > 0) {
      const curatedNote = document.createElement('div');
      curatedNote.className = 'atlas-muted';
      curatedNote.textContent = `${curated.toLocaleString()} curated ${curated === 1 ? 'item' : 'items'} will be kept.`;
      wrap.appendChild(curatedNote);
    }
    return wrap;
  }

  async function confirmDeleteEntity() {
    const entityId = String(state.selectedId || '');
    if (!entityId || typeof global.showConfirm !== 'function') return;
    try {
      const previewResp = await api()(`/atlas/entities/${encodeURIComponent(entityId)}/delete-preview`, { cache: 'no-store' });
      if (!previewResp.ok) throw new Error(`HTTP ${previewResp.status}`);
      const preview = (await previewResp.json()).preview || {};
      const checkboxId = `atlas-delete-cleanup-${Date.now()}`;
      const content = deleteCleanupContent(preview, checkboxId);
      const attachedFindings = Number((preview.attached_finding_ids || []).length || 0);
      const note = attachedFindings
        ? `This also removes ${attachedFindings.toLocaleString()} ${attachedFindings === 1 ? 'finding' : 'findings'} attached to this entity.`
        : 'This cannot be undone.';
      const choice = await global.showConfirm({
        body: { text: 'Delete this Atlas entity?', note },
        content,
        tone: 'danger',
        refocusOnResolve: false,
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'delete', label: 'Delete', role: 'destructive' },
        ],
      });
      if (choice !== 'delete') return;
      const prune = !!content?.querySelector?.('input')?.checked;
      const resp = await api()(`/atlas/entities/${encodeURIComponent(entityId)}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prune_source_run: prune }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      showToastSafe(prune ? 'Entity and related Atlas items deleted' : 'Entity deleted', 'success');
      state.selectedId = '';
      state.detail = null;
      await refreshAtlas({ resetOffset: state.offset >= state.total - 1 });
    } catch (err) {
      if (typeof global.logClientError === 'function') global.logClientError('failed to delete atlas entity', err);
      showToastSafe('Failed to delete Atlas entity', 'error');
    }
  }

  async function confirmDeleteFinding(finding) {
    const findingId = String(finding?.id || state.selectedFindingId || '');
    if (!findingId || typeof global.showConfirm !== 'function') return;
    try {
      const previewResp = await api()(`/atlas/findings/${encodeURIComponent(findingId)}/delete-preview`, { cache: 'no-store' });
      if (!previewResp.ok) throw new Error(`HTTP ${previewResp.status}`);
      const preview = (await previewResp.json()).preview || {};
      const checkboxId = `atlas-delete-cleanup-${Date.now()}`;
      const content = deleteCleanupContent(preview, checkboxId);
      const choice = await global.showConfirm({
        body: { text: 'Delete this Atlas finding?', note: 'This cannot be undone.' },
        content,
        tone: 'danger',
        refocusOnResolve: false,
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'delete', label: 'Delete', role: 'destructive' },
        ],
      });
      if (choice !== 'delete') return;
      const prune = !!content?.querySelector?.('input')?.checked;
      const resp = await api()(`/atlas/findings/${encodeURIComponent(findingId)}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prune_source_run: prune }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      showToastSafe(prune ? 'Finding and related Atlas items deleted' : 'Finding deleted', 'success');
      state.selectedFindingId = '';
      state.selectedFindingIds.delete(findingId);
      await refreshAtlas({ resetOffset: state.offset >= state.total - 1 });
    } catch (err) {
      if (typeof global.logClientError === 'function') global.logClientError('failed to delete atlas finding', err);
      showToastSafe('Failed to delete Atlas finding', 'error');
    }
  }

  function openSourceRun(run) {
    const runId = String(run && (run.id || run.run_id) || '');
    if (!runId || typeof global.openHistoryRunDetails !== 'function') return;
    global.openHistoryRunDetails({ ...run, id: runId });
  }

  function exportDownloadName(format) {
    const tab = currentTab();
    const type = tab && tab.type ? String(tab.type) : 'entities';
    const suffix = new Date().toISOString().replace(/[:.]/g, '-');
    return `darklab-atlas-${type}-${suffix}.${format}`;
  }

  function filenameFromDisposition(value) {
    const match = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(String(value || ''));
    if (!match) return '';
    try {
      return decodeURIComponent(match[1].replace(/"$/u, ''));
    } catch (_) {
      return match[1].replace(/"$/u, '');
    }
  }

  async function exportEntities(format) {
    if (currentTab().id === 'findings') {
      showToastSafe('Switch to an entity tab before exporting', 'error');
      return;
    }
    if (typeof global.downloadBlobAsAttachment !== 'function') {
      showToastSafe('Downloads are not available', 'error');
      return;
    }
    const params = new URLSearchParams();
    params.set('format', format);
    const tab = currentTab();
    if (tab.type) params.set('type', tab.type);
    if (state.query) params.set('q', state.query);
    if (state.projectId) params.set('project_id', state.projectId);
    params.set('orphan_filter', state.orphanFilter);
    try {
      const resp = await api()(`/atlas/entities/export?${params.toString()}`, { cache: 'no-store' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const blob = await resp.blob();
      const filename = filenameFromDisposition(resp.headers?.get?.('content-disposition')) || exportDownloadName(format);
      global.downloadBlobAsAttachment(blob, filename);
      showToastSafe(`Atlas ${format.toUpperCase()} export started`, 'success');
    } catch (err) {
      if (typeof global.logClientError === 'function') global.logClientError('failed to export atlas entities', err);
      showToastSafe('Failed to export Atlas entities', 'error');
    }
  }

  async function addToActiveProject() {
    const activeProject = typeof global.getActiveProjectContext === 'function'
      ? global.getActiveProjectContext()
      : null;
    const projectId = activeProject && activeProject.id ? String(activeProject.id) : '';
    if (!projectId || !state.selectedId) {
      showToastSafe('No active project', 'error');
      return;
    }
    try {
      const resp = await api()(`/atlas/entities/${encodeURIComponent(state.selectedId)}/project_links`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      showToastSafe('Added to active project', 'success');
      broadcastProjectWorkspaceChange('atlas_entity_linked', projectId);
      if (typeof global.refreshActiveProjectContext === 'function') {
        await global.refreshActiveProjectContext().catch(() => null);
      }
      await refreshAtlas();
    } catch (err) {
      if (typeof global.logClientError === 'function') global.logClientError('failed to link atlas entity', err);
      showToastSafe('Failed to add entity to project', 'error');
    }
  }

  async function removeProjectLink(link) {
    const projectId = String(link && link.project_id || '');
    if (!projectId || !state.selectedId) return;
    try {
      const resp = await api()(
        `/atlas/entities/${encodeURIComponent(state.selectedId)}/project_links/${encodeURIComponent(projectId)}`,
        { method: 'DELETE' },
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      showToastSafe('Removed from project', 'success');
      broadcastProjectWorkspaceChange('atlas_entity_unlinked', projectId);
      await refreshAtlas();
    } catch (err) {
      if (typeof global.logClientError === 'function') global.logClientError('failed to unlink atlas entity', err);
      showToastSafe('Failed to remove project link', 'error');
    }
  }

  async function saveMetadata(payload) {
    if (!state.selectedId || !metadataApi.syncEntityLabels || !metadataApi.syncEntityNote) return;
    try {
      const labels = metadataApi.parseLabelInput
        ? metadataApi.parseLabelInput(payload.labels)
        : String(payload.labels || '').split(',').map(item => item.trim()).filter(Boolean);
      await metadataApi.syncEntityLabels('atlas_entity', state.selectedId, labels);
      await metadataApi.syncEntityNote('atlas_entity', state.selectedId, payload.note || '');
      showToastSafe('Metadata saved', 'success');
      await refreshAtlas();
    } catch (err) {
      if (typeof global.logClientError === 'function') global.logClientError('failed to save atlas metadata', err);
      showToastSafe('Failed to save metadata', 'error');
    }
  }

  function bindEvents() {
    closeBtn?.addEventListener('click', () => closeAtlas());
    refreshBtn?.addEventListener('click', () => refreshAtlas());
    prevBtn?.addEventListener('click', () => {
      state.offset = Math.max(0, state.offset - state.limit);
      refreshAtlas();
    });
    nextBtn?.addEventListener('click', () => {
      state.offset += state.limit;
      refreshAtlas();
    });
    searchInput?.addEventListener('input', () => {
      state.query = String(searchInput.value || '').trim();
      state.requestedEntityValue = '';
      state.refreshIntelOnSelect = false;
      state.addActiveProjectOnSelect = false;
      state.selectedFindingIds.clear();
      state.selectedEntityIds.clear();
      clearTimeout(state.searchTimer);
      state.searchTimer = setTimeout(() => refreshAtlas({ resetOffset: true }), 180);
    });
    findingStatusFilter?.addEventListener('change', () => {
      state.findingStatus = String(findingStatusFilter.value || '');
      state.selectedFindingId = '';
      state.selectedFindingIds.clear();
      state.selectedEntityIds.clear();
      refreshAtlas({ resetOffset: true });
    });
    orphanFilter?.addEventListener('change', () => {
      state.orphanFilter = String(orphanFilter.value || 'hide') || 'hide';
      state.selectedId = '';
      state.selectedFindingId = '';
      state.selectedFindingIds.clear();
      state.selectedEntityIds.clear();
      state.detail = null;
      refreshAtlas({ resetOffset: true });
    });
    selectToggle?.addEventListener('change', () => {
      setSelectMode(!!selectToggle.checked);
    });
    findingSelectAllBtn?.addEventListener('click', () => {
      selectAllVisibleItems();
    });
    findingClearSelectionBtn?.addEventListener('click', () => {
      activeSelectionSet().clear();
      render();
    });
    findingBulkApplyBtn?.addEventListener('click', () => {
      bulkUpdateFindings();
    });
    bulkDeleteBtn?.addEventListener('click', () => {
      bulkDeleteSelectedItems();
    });
    exportMenuBtn?.addEventListener('click', (event) => {
      event.stopPropagation();
      const open = !exportWrap?.classList.contains('open');
      exportWrap?.classList.toggle('open', open);
      exportMenuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    exportCsvBtn?.addEventListener('click', () => {
      exportWrap?.classList.remove('open');
      exportMenuBtn?.setAttribute('aria-expanded', 'false');
      exportEntities('csv');
    });
    exportJsonlBtn?.addEventListener('click', () => {
      exportWrap?.classList.remove('open');
      exportMenuBtn?.setAttribute('aria-expanded', 'false');
      exportEntities('jsonl');
    });
    if (typeof global.bindOutsideClickClose === 'function' && exportWrap) {
      global.bindOutsideClickClose(exportWrap, {
        triggers: exportMenuBtn,
        isOpen: () => exportWrap.classList.contains('open'),
        onClose: () => {
          exportWrap.classList.remove('open');
          exportMenuBtn?.setAttribute('aria-expanded', 'false');
        },
      });
    }
    if (typeof global.bindDismissible === 'function' && overlay) {
      global.bindDismissible(overlay, {
        level: 'panel',
        isOpen,
        onClose: () => closeAtlas(),
        closeButtons: closeBtn,
        closeOnBackdrop: true,
      });
    }
  }

  bindEvents();

  global.openAtlas = openAtlas;
  global.closeAtlas = closeAtlas;
  global.isAtlasOverlayOpen = isOpen;
  global.refreshAtlasOverlay = refreshAtlas;
})(typeof window !== 'undefined' ? window : globalThis);
