// Session Entity Atlas overlay controller.

(function initAtlasOverlay(global) {
  const tabsApi = global.DarklabAtlasTabs || {};
  const detailApi = global.DarklabAtlasDetail || {};
  const entityRowApi = global.DarklabAtlasEntityRow || {};
  const metadataApi = global.DarklabEntityMetadata || {};

  const overlay = document.getElementById('atlas-overlay');
  const surface = document.getElementById('atlas-surface');
  const shell = surface?.querySelector?.('.atlas-shell') || document.querySelector('.atlas-shell');
  const closeBtn = document.querySelector('.atlas-close');
  const tabsHost = document.getElementById('atlas-tabs');
  const subtitle = document.getElementById('atlas-subtitle');
  const searchInput = document.getElementById('atlas-search');
  const runFilterSearch = document.getElementById('atlas-run-filter-search');
  const runFilterSelect = document.getElementById('atlas-run-filter-select');
  const runFilterChip = document.getElementById('atlas-run-filter-chip');
  const findingStatusFilter = document.getElementById('atlas-finding-status-filter');
  const orphanFilter = document.getElementById('atlas-orphan-filter');
  const suppressionFilter = document.getElementById('atlas-suppression-filter');
  const savedViewSelect = document.getElementById('atlas-saved-view-select');
  const savedViewSaveBtn = document.getElementById('atlas-saved-view-save');
  const savedViewUpdateBtn = document.getElementById('atlas-saved-view-update');
  const savedViewDeleteBtn = document.getElementById('atlas-saved-view-delete');
  const exportWrap = document.getElementById('atlas-export-wrap');
  const exportMenuBtn = document.getElementById('atlas-export-menu-btn');
  const exportCsvBtn = document.getElementById('atlas-export-csv-btn');
  const exportJsonlBtn = document.getElementById('atlas-export-jsonl-btn');
  const refreshBtn = document.getElementById('atlas-refresh-btn');
  const clearFiltersBtn = document.getElementById('atlas-clear-filters-btn');
  const findingBulkRow = document.getElementById('atlas-finding-bulk-row');
  const selectToggle = document.getElementById('atlas-select-toggle');
  const findingSelectionSummary = document.getElementById('atlas-finding-selection-summary');
  const findingSelectAllBtn = document.getElementById('atlas-finding-select-all');
  const findingClearSelectionBtn = document.getElementById('atlas-finding-clear-selection');
  const findingBulkStatus = document.getElementById('atlas-finding-bulk-status');
  const findingBulkApplyBtn = document.getElementById('atlas-finding-bulk-apply');
  const bulkSuppressionBtn = document.getElementById('atlas-bulk-suppression');
  const bulkDeleteBtn = document.getElementById('atlas-bulk-delete');
  const listHost = document.getElementById('atlas-list');
  const detailHost = document.getElementById('atlas-detail');
  const pagination = document.getElementById('atlas-pagination');
  const paginationSummary = document.getElementById('atlas-pagination-summary');
  const prevBtn = document.getElementById('atlas-prev-btn');
  const nextBtn = document.getElementById('atlas-next-btn');

  function ensureBulkActionLayout() {
    const row = findingBulkRow?.querySelector?.('.atlas-bulk-action-row');
    if (!row) return;
    let selectionControls = row.querySelector('.atlas-bulk-selection-controls');
    if (!selectionControls) {
      selectionControls = document.createElement('div');
      selectionControls.className = 'atlas-bulk-selection-controls';
      row.prepend(selectionControls);
    }
    let mutationControls = row.querySelector('.atlas-bulk-mutation-controls');
    if (!mutationControls) {
      mutationControls = document.createElement('div');
      mutationControls.className = 'atlas-bulk-mutation-controls';
      row.appendChild(mutationControls);
    }
    const selectControl = selectToggle?.closest?.('label') || selectToggle;
    [
      selectControl,
      findingSelectAllBtn,
      findingClearSelectionBtn,
      findingSelectionSummary,
    ].forEach((el) => {
      if (el && el.parentElement !== selectionControls) selectionControls.appendChild(el);
    });
    [
      findingBulkStatus,
      findingBulkApplyBtn,
      bulkSuppressionBtn,
      bulkDeleteBtn,
    ].forEach((el) => {
      if (el && el.parentElement !== mutationControls) mutationControls.appendChild(el);
    });
  }

  const state = {
    activeTab: 'findings',
    summary: null,
    baseSummary: null,
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
    suppressionFilter: 'hide',
    total: 0,
    limit: 50,
    offset: 0,
    query: '',
    projectId: '',
    projectName: '',
    launchProjectId: '',
    launchProjectName: '',
    runId: '',
    runLabel: '',
    runOptions: [],
    runOptionsLoaded: false,
    runOptionsLoading: false,
    runOptionsQuery: '',
    runSearchTimer: null,
    savedViews: [],
    selectedSavedViewId: '',
    savedViewsLoaded: false,
    savedViewsLoading: false,
    loading: false,
    selectedId: '',
    requestedEntityValue: '',
    requestedView: '',
    requestedViewStarted: 0,
    refreshIntelOnSelect: false,
    addActiveProjectOnSelect: false,
    detail: null,
    detailLoading: false,
    detailOffsets: { runs: 0, findings: 0 },
    searchTimer: null,
    refreshSeq: 0,
  };

  function api() {
    if (typeof global.apiFetch === 'function') return global.apiFetch;
    if (typeof apiFetch === 'function') return apiFetch;
    return fetch;
  }

  let atlasLoadController = null;
  let detailLoadController = null;

  function isAbortError(err) {
    return err && (err.name === 'AbortError' || err.code === 20);
  }

  function newAbortController() {
    if (typeof global.AbortController !== 'function') return null;
    return new global.AbortController();
  }

  function requestOptions(controller, extra = {}) {
    if (controller && controller.signal) return { ...extra, signal: controller.signal };
    return extra;
  }

  function abortAtlasLoad() {
    if (atlasLoadController) atlasLoadController.abort();
    atlasLoadController = null;
  }

  function abortDetailLoad() {
    if (detailLoadController) detailLoadController.abort();
    detailLoadController = null;
  }

  function abortReadRequests() {
    abortAtlasLoad();
    abortDetailLoad();
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

  function selectorValue(value) {
    if (typeof CSS !== 'undefined' && CSS && typeof CSS.escape === 'function') {
      return CSS.escape(String(value));
    }
    return String(value || '').replace(/["\\]/g, '\\$&');
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
    if (typeof global.syncModalOverlayState === 'function') global.syncModalOverlayState();
  }

  function hide({ refocus = true } = {}) {
    if (!overlay) return;
    abortReadRequests();
    resetSelection({ selectMode: false, render: false });
    overlay.classList.add('u-hidden');
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    if (typeof global.syncModalOverlayState === 'function') global.syncModalOverlayState();
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
    state.launchProjectId = state.projectId;
    state.launchProjectName = state.projectName;
    state.runId = String(options && options.runId || '').trim();
    state.runLabel = String(options && options.runLabel || '').trim();
    state.runOptionsQuery = '';
    state.requestedEntityValue = String(options && options.entityValue || '').trim();
    state.requestedView = ['detail', 'list'].includes(String(options && options.forceView || ''))
      ? String(options.forceView)
      : 'list';
    state.requestedViewStarted = state.requestedView === 'detail' ? Date.now() : 0;
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
    state.detailOffsets = { runs: 0, findings: 0 };
    resetSelection({ selectMode: false, render: false });
    state.detail = null;
    if (global.DarklabAtlasMobile && typeof global.DarklabAtlasMobile.resetTransientState === 'function') {
      global.DarklabAtlasMobile.resetTransientState();
    }
    show();
    if (typeof global.markInteractionSurfaceReady === 'function') {
      global.markInteractionSurfaceReady('atlas', overlay, surface);
    }
    render();
    loadSavedViews().catch((err) => {
      if (typeof global.logClientError === 'function') global.logClientError('failed to load atlas saved views', err);
    });
    loadRunOptions().catch((err) => {
      if (typeof global.logClientError === 'function') global.logClientError('failed to load atlas run filters', err);
    });
    await refreshAtlas({ resetOffset: true });
  }

  function closeAtlas(options = {}) {
    state.requestedView = '';
    state.requestedViewStarted = 0;
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

  function setActiveAtlasTab(tabId, { focus = false } = {}) {
    const nextTab = String(tabId || '');
    if (!nextTab) return false;
    if (state.activeTab === nextTab) {
      if (focus) tabsHost?.querySelector(`[data-atlas-tab="${selectorValue(nextTab)}"]`)?.focus({ preventScroll: true });
      return true;
    }
    const exists = (tabsApi.tabs || []).some(tab => String(tab.id || '') === nextTab);
    if (!exists) return false;
    state.activeTab = nextTab;
    state.offset = 0;
    state.selectedId = '';
    state.selectedFindingId = '';
    state.detailOffsets = { runs: 0, findings: 0 };
    resetSelection({ selectMode: state.selectMode, render: false });
    state.requestedEntityValue = '';
    state.requestedView = '';
    state.requestedViewStarted = 0;
    state.refreshIntelOnSelect = false;
    state.addActiveProjectOnSelect = false;
    state.detail = null;
    render();
    if (focus) {
      window.setTimeout(() => {
        tabsHost?.querySelector(`[data-atlas-tab="${selectorValue(nextTab)}"]`)?.focus({ preventScroll: true });
      }, 0);
    }
    refreshAtlas({ resetOffset: true });
    return true;
  }

  function cycleAtlasTab(offset = 1) {
    if (!isOpen()) return false;
    const tabs = (tabsApi.tabs || []).filter(tab => tab && tab.id);
    if (tabs.length < 2) return false;
    const currentIndex = Math.max(0, tabs.findIndex(tab => String(tab.id || '') === String(state.activeTab || '')));
    const nextIndex = (currentIndex + Number(offset || 1) + tabs.length) % tabs.length;
    return setActiveAtlasTab(tabs[nextIndex].id);
  }

  function renderTabs() {
    if (!tabsHost) return;
    tabsHost.replaceChildren();
    (tabsApi.tabs || []).forEach(tab => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'tab-strip-item atlas-tab';
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
      count.textContent = `(${tabCountText(tab)})`;
      button.append(label, count);
      button.addEventListener('click', () => {
        setActiveAtlasTab(tab.id);
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
    if (suppressionFilter && !suppressionFilter.dataset.populated) {
      suppressionFilter.appendChild(option('Visible rows', 'hide'));
      suppressionFilter.appendChild(option('Show all', 'all'));
      suppressionFilter.appendChild(option('Only suppressed', 'only'));
      suppressionFilter.value = state.suppressionFilter;
      suppressionFilter.dataset.populated = '1';
    }
    if (savedViewSelect && !savedViewSelect.dataset.populated) {
      savedViewSelect.appendChild(option('Saved views', ''));
      savedViewSelect.dataset.populated = '1';
    }
    if (runFilterSelect && !runFilterSelect.dataset.populated) {
      runFilterSelect.appendChild(option('Filter by run', ''));
      runFilterSelect.dataset.populated = '1';
    }
    syncSelectDisplay(findingStatusFilter);
    syncSelectDisplay(findingBulkStatus);
    syncSelectDisplay(runFilterSelect);
    syncSelectDisplay(orphanFilter);
    syncSelectDisplay(suppressionFilter);
    syncSelectDisplay(savedViewSelect);
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
    if (suppressionFilter) {
      suppressionFilter.value = state.suppressionFilter;
      syncSelectDisplay(suppressionFilter);
    }
    renderSavedViewControls();
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
    if (bulkSuppressionBtn) {
      bulkSuppressionBtn.classList.toggle('u-hidden', !state.selectMode);
      bulkSuppressionBtn.textContent = state.suppressionFilter === 'only' ? 'Restore' : 'Suppress';
      bulkSuppressionBtn.disabled = !selectedCount || state.loading || state.bulkInFlight;
    }
    if (bulkDeleteBtn) {
      bulkDeleteBtn.classList.toggle('u-hidden', !state.selectMode);
      bulkDeleteBtn.disabled = !selectedCount || state.loading || state.bulkInFlight;
    }
  }

  function normalizeSavedViews(value) {
    return Array.isArray(value) ? value.filter(item => item && item.id && item.name) : [];
  }

  function normalizeRunOptions(value) {
    return Array.isArray(value)
      ? value.map(item => ({
        id: String(item && (item.id || item.run_id) || '').trim(),
        run_id: String(item && (item.run_id || item.id) || '').trim(),
        command: String(item && item.command || '').trim(),
        started: String(item && item.started || '').trim(),
        entity_count: Number(item && item.entity_count || 0),
        finding_count: Number(item && item.finding_count || 0),
      })).filter(item => item.id)
      : [];
  }

  function runOptionLabel(run) {
    const command = String(run && run.command || '').trim() || 'Run';
    const entityCount = Number(run && run.entity_count || 0);
    const findingCount = Number(run && run.finding_count || 0);
    const counts = [];
    if (entityCount) counts.push(`${entityCount.toLocaleString()} ent`);
    if (findingCount) counts.push(`${findingCount.toLocaleString()} fnd`);
    return counts.length ? `${command} (${counts.join(', ')})` : command;
  }

  function selectedRunOption() {
    const selectedId = String(state.runId || '');
    return state.runOptions.find(run => String(run.id || '') === selectedId) || null;
  }

  function renderRunFilterControls() {
    if (runFilterSearch && runFilterSearch.value !== state.runOptionsQuery) {
      runFilterSearch.value = state.runOptionsQuery || '';
    }
    if (!runFilterSelect) return;
    const optionRows = [...state.runOptions];
    if (state.runId && !optionRows.some(run => String(run.id || '') === state.runId)) {
      optionRows.unshift({
        id: state.runId,
        run_id: state.runId,
        command: state.runLabel || state.runId,
        entity_count: 0,
        finding_count: 0,
      });
    }
    const nextValues = ['', ...optionRows.map(run => String(run.id || ''))].join('\n');
    const currentValues = Array.from(runFilterSelect.options || []).map(option => option.value).join('\n');
    if (nextValues !== currentValues) {
      runFilterSelect.replaceChildren();
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = state.runOptionsLoading ? 'Loading runs...' : 'Filter by run';
      runFilterSelect.appendChild(placeholder);
      optionRows.forEach((run) => {
        const option = document.createElement('option');
        option.value = String(run.id || '');
        option.textContent = runOptionLabel(run);
        option.dataset.runCommand = String(run.command || '');
        runFilterSelect.appendChild(option);
      });
    } else if (runFilterSelect.options[0]) {
      runFilterSelect.options[0].textContent = state.runOptionsLoading ? 'Loading runs...' : 'Filter by run';
    }
    runFilterSelect.value = state.runId || '';
    runFilterSelect.disabled = state.runOptionsLoading;
    syncSelectDisplay(runFilterSelect);
  }

  function currentSavedViewState(name = '') {
    return {
      name: String(name || '').trim(),
      tab: currentTab().id || 'findings',
      filters: {
        query: String(state.query || '').trim(),
        orphan_filter: String(state.orphanFilter || 'hide'),
        suppression_filter: String(state.suppressionFilter || 'hide'),
        finding_status: String(state.findingStatus || ''),
        project_id: String(state.projectId || ''),
        project_name: String(state.projectName || ''),
        run_id: String(state.runId || ''),
        run_label: String(state.runLabel || ''),
        sort: '',
      },
    };
  }

  function selectedSavedView() {
    const selectedId = String(state.selectedSavedViewId || '');
    return state.savedViews.find(view => String(view.id || '') === selectedId) || null;
  }

  function renderSavedViewControls() {
    if (!savedViewSelect) return;
    const selectedId = selectedSavedView() ? state.selectedSavedViewId : '';
    if (selectedId !== state.selectedSavedViewId) state.selectedSavedViewId = '';
    const currentOptions = Array.from(savedViewSelect.options || []).map(option => option.value).join('\n');
    const nextValues = ['', ...state.savedViews.map(view => String(view.id || ''))].join('\n');
    if (currentOptions !== nextValues) {
      savedViewSelect.replaceChildren();
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = state.savedViewsLoading ? 'Loading views...' : 'Saved views';
      savedViewSelect.appendChild(placeholder);
      state.savedViews.forEach((view) => {
        const option = document.createElement('option');
        option.value = String(view.id || '');
        option.textContent = String(view.name || 'Saved view');
        savedViewSelect.appendChild(option);
      });
    } else if (savedViewSelect.options[0]) {
      savedViewSelect.options[0].textContent = state.savedViewsLoading ? 'Loading views...' : 'Saved views';
    }
    savedViewSelect.value = state.selectedSavedViewId || '';
    savedViewSelect.disabled = state.savedViewsLoading;
    syncSelectDisplay(savedViewSelect);
    if (savedViewSaveBtn) savedViewSaveBtn.disabled = state.savedViewsLoading;
    if (savedViewUpdateBtn) savedViewUpdateBtn.disabled = !state.selectedSavedViewId || state.savedViewsLoading;
    if (savedViewDeleteBtn) savedViewDeleteBtn.disabled = !state.selectedSavedViewId || state.savedViewsLoading;
  }

  function savedViewNameContent(defaultValue = '') {
    const wrap = document.createElement('div');
    wrap.className = 'atlas-saved-view-prompt';
    const label = document.createElement('label');
    label.className = 'form-field';
    const labelText = document.createElement('span');
    labelText.textContent = 'Name';
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'form-control form-control-compact';
    input.maxLength = 60;
    input.value = defaultValue;
    input.setAttribute('aria-label', 'Saved view name');
    label.append(labelText, input);
    wrap.appendChild(label);
    window.setTimeout(() => {
      input.focus({ preventScroll: true });
      input.select();
    }, 0);
    return { content: wrap, input };
  }

  async function promptSavedViewName(defaultName = '', title = 'Save Atlas view') {
    if (typeof global.showConfirm !== 'function') return '';
    const { content, input } = savedViewNameContent(defaultName);
    const choice = await global.showConfirm({
      title,
      body: {
        text: title,
        note: 'Saved views remember search, filters, review state, source run, and project scope.',
      },
      content,
      actions: [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'save', label: 'Save', role: 'primary' },
      ],
      refocusOnResolve: false,
    });
    if (choice !== 'save') return '';
    return String(input.value || '').trim();
  }

  async function loadSavedViews({ force = false } = {}) {
    if (state.savedViewsLoaded && !force) return state.savedViews;
    state.savedViewsLoading = true;
    renderSavedViewControls();
    try {
      const resp = await api()('/atlas/views', { cache: 'no-store' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      state.savedViews = normalizeSavedViews(data.views);
      state.savedViewsLoaded = true;
      if (state.selectedSavedViewId && !selectedSavedView()) state.selectedSavedViewId = '';
      return state.savedViews;
    } catch (err) {
      if (typeof global.logClientError === 'function') global.logClientError('failed to load atlas saved views', err);
      showToastSafe('Failed to load saved Atlas views', 'error');
      return state.savedViews;
    } finally {
      state.savedViewsLoading = false;
      renderSavedViewControls();
    }
  }

  async function loadRunOptions({ query = state.runOptionsQuery, force = false } = {}) {
    const normalizedQuery = String(query || '').trim();
    if (
      !force
      && state.runOptionsLoaded
      && normalizedQuery === state.runOptionsQuery
      && (!state.runId || state.runOptions.some(run => String(run.id || '') === String(state.runId || '')))
    ) {
      return state.runOptions;
    }
    state.runOptionsQuery = normalizedQuery;
    state.runOptionsLoading = true;
    renderRunFilterControls();
    try {
      const params = new URLSearchParams({ limit: '30' });
      if (normalizedQuery) params.set('q', normalizedQuery);
      if (state.runId) params.set('run_id', state.runId);
      const resp = await api()(`/atlas/runs?${params.toString()}`, { cache: 'no-store' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      state.runOptions = normalizeRunOptions(data.runs);
      state.runOptionsLoaded = true;
      const selected = selectedRunOption();
      if (selected && selected.command && !state.runLabel) state.runLabel = selected.command;
      return state.runOptions;
    } catch (err) {
      if (typeof global.logClientError === 'function') global.logClientError('failed to load atlas run filters', err);
      return state.runOptions;
    } finally {
      state.runOptionsLoading = false;
      renderRunFilterControls();
    }
  }

  function updateSavedViewsFromResponse(data) {
    state.savedViews = normalizeSavedViews(data?.views);
    if (data?.view?.id) state.selectedSavedViewId = String(data.view.id || '');
    if (state.selectedSavedViewId && !selectedSavedView()) state.selectedSavedViewId = '';
    state.savedViewsLoaded = true;
    render();
  }

  async function saveCurrentView() {
    const name = await promptSavedViewName('', 'Save Atlas view');
    if (!name) return;
    try {
      const resp = await api()('/atlas/views', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(currentSavedViewState(name)),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      updateSavedViewsFromResponse(data);
      showToastSafe('Atlas view saved', 'success');
    } catch (err) {
      if (typeof global.logClientError === 'function') global.logClientError('failed to save atlas view', err);
      showToastSafe('Failed to save Atlas view', 'error');
    }
  }

  async function updateCurrentSavedView() {
    const current = selectedSavedView();
    if (!current) return;
    const name = await promptSavedViewName(current.name || '', 'Update Atlas view');
    if (!name) return;
    try {
      const resp = await api()(`/atlas/views/${encodeURIComponent(current.id)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(currentSavedViewState(name)),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      updateSavedViewsFromResponse(data);
      showToastSafe('Atlas view updated', 'success');
    } catch (err) {
      if (typeof global.logClientError === 'function') global.logClientError('failed to update atlas view', err);
      showToastSafe('Failed to update Atlas view', 'error');
    }
  }

  async function deleteCurrentSavedView() {
    const current = selectedSavedView();
    if (!current || typeof global.showConfirm !== 'function') return;
    try {
      const choice = await global.showConfirm({
        body: { text: `Delete "${current.name}"?`, note: 'This only removes the saved view. Atlas data is unchanged.' },
        tone: 'warning',
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'delete', label: 'Delete', role: 'destructive', tone: 'warning' },
        ],
        refocusOnResolve: false,
      });
      if (choice !== 'delete') return;
      const resp = await api()(`/atlas/views/${encodeURIComponent(current.id)}`, { method: 'DELETE' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      state.selectedSavedViewId = '';
      updateSavedViewsFromResponse(data);
      showToastSafe('Atlas view deleted', 'success');
    } catch (err) {
      if (typeof global.logClientError === 'function') global.logClientError('failed to delete atlas view', err);
      showToastSafe('Failed to delete Atlas view', 'error');
    }
  }

  function applySavedView(viewId) {
    const view = state.savedViews.find(item => String(item.id || '') === String(viewId || ''));
    if (!view) {
      state.selectedSavedViewId = '';
      renderSavedViewControls();
      return;
    }
    const filters = view.filters && typeof view.filters === 'object' ? view.filters : {};
    state.selectedSavedViewId = String(view.id || '');
    state.query = String(filters.query || '').trim();
    state.orphanFilter = String(filters.orphan_filter || 'hide') || 'hide';
    state.suppressionFilter = String(filters.suppression_filter || 'hide') || 'hide';
    state.findingStatus = String(filters.finding_status || '');
    state.projectId = String(filters.project_id || '');
    state.projectName = String(filters.project_name || '');
    state.runId = String(filters.run_id || '').trim();
    state.runLabel = String(filters.run_label || '').trim();
    state.runOptionsQuery = '';
    if (searchInput) searchInput.value = state.query;
    state.selectedId = '';
    state.selectedFindingId = '';
    state.detailOffsets = { runs: 0, findings: 0 };
    resetSelection({ selectMode: state.selectMode, render: false });
    state.detail = null;
    state.requestedEntityValue = '';
    state.requestedView = '';
    state.requestedViewStarted = 0;
    state.refreshIntelOnSelect = false;
    state.addActiveProjectOnSelect = false;
    render();
    loadRunOptions({ force: true }).catch((err) => {
      if (typeof global.logClientError === 'function') global.logClientError('failed to load atlas run filters', err);
    });
    refreshAtlas({ resetOffset: true });
  }

  function findingStatusLabel(value) {
    const found = findingStates.find(([stateValue]) => stateValue === String(value || ''));
    return found ? found[1] : text(value, 'New');
  }

  function activateRowOnKeyboard(row, handler) {
    row.setAttribute('role', 'button');
    row.tabIndex = 0;
    row.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      handler();
    });
  }

  function appendSelectionCheckbox(row, item, selectedIds, label, className = 'atlas-row-select') {
    const selectLabel = document.createElement('label');
    selectLabel.className = 'atlas-row-select-label';
    selectLabel.addEventListener('click', event => event.stopPropagation());
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.className = className;
    checkbox.checked = selectedIds.has(String(item.id || ''));
    checkbox.setAttribute('aria-label', label);
    checkbox.addEventListener('change', () => {
      toggleItemSelection(item, checkbox.checked);
    });
    selectLabel.appendChild(checkbox);
    row.appendChild(selectLabel);
  }

  function suppressionIconLabel(item, noun = 'row') {
    return item && item.suppressed ? `Restore ${noun}` : `Suppress ${noun}`;
  }

  function createSuppressionIconButton(item, noun, handler) {
    const btn = document.createElement('button');
    const label = suppressionIconLabel(item, noun);
    btn.type = 'button';
    btn.className = 'btn btn-ghost btn-icon-only btn-compact atlas-row-suppression-action';
    btn.title = label;
    btn.setAttribute('aria-label', label);
    btn.textContent = item && item.suppressed ? '↺' : '⊘';
    btn.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      handler?.();
    });
    return btn;
  }

  function findingRow(finding) {
    const row = document.createElement('div');
    row.className = 'chrome-row chrome-row-clickable atlas-finding-queue-row';
    row.classList.toggle('is-suppressed', !!finding.suppressed);
    row.classList.toggle('is-selecting', state.selectMode);
    row.classList.toggle(
      'is-selected',
      state.selectMode
        ? state.selectedFindingIds.has(String(finding.id || ''))
        : finding.id === state.selectedFindingId,
    );
    row.classList.toggle('has-row-action', !state.selectMode);
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
    if (finding.suppressed) badges.appendChild(badge('suppressed', 'muted'));
    badges.appendChild(badge(findingStatusLabel(finding.review_state || finding.status), 'green'));
    if (finding.occurrence_count) badges.appendChild(badge(countLabel(finding.occurrence_count, 'hit', 'hits'), 'muted'));
    if (state.selectMode) {
      appendSelectionCheckbox(
        row,
        finding,
        state.selectedFindingIds,
        `Select finding: ${finding.title || finding.id}`,
        'atlas-finding-select atlas-row-select',
      );
    }
    row.append(main, badges);
    if (!state.selectMode) {
      row.appendChild(createSuppressionIconButton(
        finding,
        'finding',
        () => updateSuppression(finding, !finding.suppressed),
      ));
    }
    const handleActivation = () => {
      if (state.selectMode) {
        toggleItemSelection(finding);
        return;
      }
      selectFinding(finding.id);
    };
    row.addEventListener('click', handleActivation);
    if (!state.selectMode) activateRowOnKeyboard(row, handleActivation);
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
      const handleActivation = () => {
        if (state.selectMode) {
          toggleItemSelection(entity);
          return;
        }
        selectEntity(entity.id);
      };
      const row = entityRowApi.renderAtlasEntityRow({
        entity,
        selected: state.selectMode
          ? state.selectedEntityIds.has(String(entity.id || ''))
          : entity.id === state.selectedId,
        selecting: state.selectMode,
        selectMode: state.selectMode,
        text,
        countLabel,
        badge,
        appendSelectionControl: state.selectMode
          ? (targetRow) => appendSelectionCheckbox(
              targetRow,
              entity,
              state.selectedEntityIds,
              `Select entity: ${entity.canonical_value || entity.id}`,
            )
          : null,
        rowAction: state.selectMode
          ? null
          : createSuppressionIconButton(
              entity,
              'entity',
              () => updateSuppression(entity, !entity.suppressed),
            ),
        onActivate: handleActivation,
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
        onSuppressFinding: (item) => updateSuppression(item, !item.suppressed),
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
      onCleanRunAtlas: (run) => confirmCleanRunAtlas(run),
      onDeleteEntity: () => confirmDeleteEntity(),
      onSuppressEntity: (entity) => updateSuppression(entity, !entity.suppressed),
      onPageRuns: (offset) => pageEntityDetail('runs', offset),
      onPageFindings: (offset) => pageEntityDetail('findings', offset),
    });
  }

  const mobileRenderers = [];

  function registerMobileRenderer(fn) {
    if (typeof fn !== 'function') return;
    if (!mobileRenderers.includes(fn)) mobileRenderers.push(fn);
  }

  function render() {
    renderShellMode();
    renderSubtitle();
    renderFindingControls();
    renderRunFilterControls();
    renderRunFilterChip();
    renderTabs();
    renderList();
    renderPagination();
    renderDetail();
    for (const fn of mobileRenderers) {
      try { fn(state, atlasController); } catch (err) {
        if (typeof global.logClientError === 'function') global.logClientError('atlas mobile render failed', err);
      }
    }
  }

  function renderShellMode() {
    shell?.setAttribute('data-atlas-mode', currentTab().id === 'findings' ? 'findings' : 'entity');
  }

  function clearRunFilter() {
    applyRunFilter('', '');
  }

  function clearAtlasFilters() {
    clearTimeout(state.searchTimer);
    clearTimeout(state.runSearchTimer);
    state.query = '';
    state.runId = '';
    state.runLabel = '';
    state.runOptionsQuery = '';
    state.findingStatus = '';
    state.orphanFilter = 'hide';
    state.suppressionFilter = 'hide';
    state.projectId = state.launchProjectId;
    state.projectName = state.launchProjectName;
    state.selectedSavedViewId = '';
    state.selectedId = '';
    state.selectedFindingId = '';
    state.requestedEntityValue = '';
    state.requestedView = '';
    state.requestedViewStarted = 0;
    state.refreshIntelOnSelect = false;
    state.addActiveProjectOnSelect = false;
    state.detailOffsets = { runs: 0, findings: 0 };
    state.detail = null;
    resetSelection({ selectMode: false, render: false });
    if (searchInput) searchInput.value = '';
    if (runFilterSearch) runFilterSearch.value = '';
    render();
    loadRunOptions({ query: '', force: true }).catch((err) => {
      if (typeof global.logClientError === 'function') global.logClientError('failed to load atlas run filters', err);
    });
    refreshAtlas({ resetOffset: true });
  }

  function applyRunFilter(runId, runLabel = '') {
    state.runId = '';
    state.runLabel = '';
    const normalizedRunId = String(runId || '').trim();
    if (normalizedRunId) {
      const matched = state.runOptions.find(run => String(run.id || '') === normalizedRunId);
      state.runId = normalizedRunId;
      state.runLabel = String(runLabel || matched?.command || normalizedRunId).trim();
    }
    state.runOptionsQuery = '';
    state.selectedFindingId = '';
    state.selectedFindingIds.clear();
    state.selectedId = '';
    state.selectedEntityIds.clear();
    state.detailOffsets = { runs: 0, findings: 0 };
    state.detail = null;
    state.requestedEntityValue = '';
    state.requestedView = '';
    state.requestedViewStarted = 0;
    state.refreshIntelOnSelect = false;
    state.addActiveProjectOnSelect = false;
    renderRunFilterControls();
    refreshAtlas({ resetOffset: true });
  }

  function truncateRunFilterLabel(value) {
    const text = String(value || '').trim() || 'run';
    if (text.length <= 17) return text;
    return `${text.slice(0, 14).trimEnd()}...`;
  }

  function formatTabCount(value) {
    return Math.max(0, Number(value || 0)).toLocaleString();
  }

  function tabCountText(tab) {
    const filtered = tabsApi.countForTab ? tabsApi.countForTab(tab, state.summary) : 0;
    const total = tabsApi.countForTab ? tabsApi.countForTab(tab, state.baseSummary || state.summary) : filtered;
    if (state.runId) return `${formatTabCount(filtered)}/${formatTabCount(total)}`;
    return formatTabCount(filtered);
  }

  function renderRunFilterChip() {
    if (!runFilterChip) return;
    runFilterChip.replaceChildren();
    const hasRunFilter = !!state.runId;
    runFilterChip.classList.toggle('u-hidden', !hasRunFilter);
    if (!hasRunFilter) return;
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'chip chip-removable';
    chip.textContent = `Run: ${truncateRunFilterLabel(state.runLabel || state.runId)} ×`;
    chip.title = state.runLabel ? `${state.runLabel} (${state.runId})` : state.runId;
    chip.addEventListener('click', clearRunFilter);
    runFilterChip.appendChild(chip);
  }

  async function refreshAtlas({ resetOffset = false } = {}) {
    if (!overlay || !isOpen()) return;
    if (resetOffset) state.offset = 0;
    const requestId = state.refreshSeq + 1;
    state.refreshSeq = requestId;
    abortReadRequests();
    const controller = newAbortController();
    atlasLoadController = controller;
    const requestedTab = currentTab();
    const isStale = () => (
      requestId !== state.refreshSeq
      || !isOpen()
      || currentTab().id !== requestedTab.id
    );
    state.loading = true;
    render();
    try {
      const summaryParams = new URLSearchParams({
        orphan_filter: state.orphanFilter,
        suppression_filter: state.suppressionFilter,
      });
      if (state.runId) summaryParams.set('run_id', state.runId);
      const summaryResp = await api()(
        `/atlas?${summaryParams.toString()}`,
        requestOptions(controller, { cache: 'no-store' }),
      );
      if (!summaryResp.ok) throw new Error(`HTTP ${summaryResp.status}`);
      if (isStale()) return;
      state.summary = await summaryResp.json();
      if (isStale()) return;
      if (state.runId) {
        const baseSummaryParams = new URLSearchParams({
          orphan_filter: state.orphanFilter,
          suppression_filter: state.suppressionFilter,
        });
        const baseSummaryResp = await api()(
          `/atlas?${baseSummaryParams.toString()}`,
          requestOptions(controller, { cache: 'no-store' }),
        );
        if (!baseSummaryResp.ok) throw new Error(`HTTP ${baseSummaryResp.status}`);
        if (isStale()) return;
        state.baseSummary = await baseSummaryResp.json();
        if (isStale()) return;
      } else {
        state.baseSummary = state.summary;
      }
      const tab = requestedTab;
      if (tab.id === 'findings') {
        const params = new URLSearchParams({
          limit: String(state.limit),
          offset: String(state.offset),
        });
        if (state.query) params.set('q', state.query);
        if (state.projectId) params.set('project_id', state.projectId);
        if (state.runId) params.set('run_id', state.runId);
        if (state.findingStatus) params.append('review_state', state.findingStatus);
        params.set('orphan_filter', state.orphanFilter);
        params.set('suppression_filter', state.suppressionFilter);
        const listResp = await api()(
          `/atlas/findings?${params.toString()}`,
          requestOptions(controller, { cache: 'no-store' }),
        );
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
        if (state.runId) params.set('run_id', state.runId);
        params.set('orphan_filter', state.orphanFilter);
        params.set('suppression_filter', state.suppressionFilter);
        const listResp = await api()(
          `/atlas/entities?${params.toString()}`,
          requestOptions(controller, { cache: 'no-store' }),
        );
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
          if (match) {
            state.selectedId = match.id;
            state.detailOffsets = { runs: 0, findings: 0 };
          }
          else {
            state.refreshIntelOnSelect = false;
            state.addActiveProjectOnSelect = false;
          }
        }
        if (!state.selectedId && !state.requestedEntityValue && state.entities[0]) {
          state.selectedId = state.entities[0].id;
          state.detailOffsets = { runs: 0, findings: 0 };
        }
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
      if (isAbortError(err)) return;
      if (typeof global.logClientError === 'function') global.logClientError('failed to load /atlas', err);
      showToastSafe('Failed to load Atlas', 'error');
    } finally {
      if (atlasLoadController === controller) atlasLoadController = null;
      if (!isStale()) {
        state.loading = false;
        render();
      }
    }
  }

  async function selectEntity(entityId) {
    state.selectedId = String(entityId || '');
    state.detailOffsets = { runs: 0, findings: 0 };
    renderList();
    await loadDetail(state.selectedId);
  }

  async function pageEntityDetail(kind, offset) {
    if (!state.selectedId || !['runs', 'findings'].includes(String(kind || ''))) return;
    state.detailOffsets = {
      runs: Math.max(0, Number(state.detailOffsets?.runs || 0)),
      findings: Math.max(0, Number(state.detailOffsets?.findings || 0)),
      [kind]: Math.max(0, Number(offset || 0)),
    };
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

  async function bulkUpdateFindings(reviewStateOverride = '') {
    const reviewState = String(reviewStateOverride || findingBulkStatus?.value || '').trim();
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

  async function updateSuppression(item, suppressed) {
    const tab = currentTab();
    const isFindings = tab.id === 'findings';
    const itemId = String(item && item.id || '');
    if (!itemId) return;
    const url = isFindings
      ? `/atlas/findings/${encodeURIComponent(itemId)}/suppression`
      : `/atlas/entities/${encodeURIComponent(itemId)}/suppression`;
    try {
      const resp = await api()(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ suppressed: !!suppressed }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      showToastSafe(suppressed ? 'Atlas row suppressed' : 'Atlas row restored', 'success');
      await refreshAtlas();
    } catch (err) {
      if (typeof global.logClientError === 'function') global.logClientError('failed to update atlas suppression', err);
      showToastSafe('Failed to update Atlas row', 'error');
    }
  }

  async function bulkUpdateSuppression(suppressed) {
    if (state.bulkInFlight) return;
    const tab = currentTab();
    const isFindings = tab.id === 'findings';
    const selected = activeSelectionSet(tab);
    const ids = [...selected];
    if (!ids.length) return;
    setBulkBusy(true);
    try {
      const url = isFindings ? '/atlas/findings/suppression' : '/atlas/entities/suppression';
      const body = isFindings
        ? { finding_ids: ids, suppressed: !!suppressed }
        : { entity_ids: ids, suppressed: !!suppressed };
      const resp = await api()(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json().catch(() => ({}));
      selected.clear();
      const updated = Number(data?.counts?.updated || 0);
      const notFound = Number(data?.counts?.not_found || 0);
      const verb = suppressed ? 'Suppressed' : 'Restored';
      showToastSafe(
        notFound ? `${verb} ${updated} rows - ${notFound} not found` : `${verb} ${updated} rows`,
        notFound ? 'warning' : 'success',
      );
      await refreshAtlas({ resetOffset: suppressed && state.suppressionFilter === 'hide' });
    } catch (err) {
      if (typeof global.logClientError === 'function') global.logClientError('failed to bulk update atlas suppression', err);
      showToastSafe('Failed to update selected Atlas rows', 'error');
    } finally {
      setBulkBusy(false);
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
    if (state.bulkInFlight) return;
    const tab = currentTab();
    const isFindings = tab.id === 'findings';
    const selected = activeSelectionSet(tab);
    const ids = [...selected];
    if (!ids.length || typeof global.showConfirm !== 'function') return;
    setBulkBusy(true);
    const noun = bulkDeleteNoun(tab, ids.length);
    const note = isFindings
      ? 'This removes the selected findings and cannot be undone.'
      : 'This removes the selected entities and any findings attached to them. This cannot be undone.';
    try {
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
    state.detailOffsets = { runs: 0, findings: 0 };
    resetSelection({ selectMode: state.selectMode, render: false });
    state.query = '';
    if (searchInput) searchInput.value = '';
    refreshAtlas({ resetOffset: true });
  }

  async function loadDetail(entityId, { renderLoading = true } = {}) {
    if (!entityId) return;
    abortDetailLoad();
    const controller = newAbortController();
    detailLoadController = controller;
    state.detailLoading = !!renderLoading;
    if (renderLoading) renderDetail();
    try {
      const params = new URLSearchParams();
      const runsOffset = Math.max(0, Number(state.detailOffsets?.runs || 0));
      const findingsOffset = Math.max(0, Number(state.detailOffsets?.findings || 0));
      if (runsOffset) params.set('runs_offset', String(runsOffset));
      if (findingsOffset) params.set('findings_offset', String(findingsOffset));
      const query = params.toString();
      const resp = await api()(
        `/atlas/entities/${encodeURIComponent(entityId)}${query ? `?${query}` : ''}`,
        requestOptions(controller, { cache: 'no-store' }),
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const detail = await resp.json();
      if (String(state.selectedId || '') !== String(entityId || '') || currentTab().id === 'findings') return;
      state.detail = detail;
    } catch (err) {
      if (isAbortError(err)) return;
      if (String(state.selectedId || '') !== String(entityId || '')) return;
      state.detail = null;
      if (typeof global.logClientError === 'function') global.logClientError('failed to load atlas entity', err);
      showToastSafe('Failed to load entity', 'error');
    } finally {
      if (detailLoadController === controller) detailLoadController = null;
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

  function curatedCleanupLabel(cleanup) {
    const entities = Number(cleanup?.curated_entities || 0);
    const findings = Number(cleanup?.curated_findings || 0);
    return `${entities.toLocaleString()} curated ${entities === 1 ? 'entity' : 'entities'} and `
      + `${findings.toLocaleString()} curated ${findings === 1 ? 'finding' : 'findings'}`;
  }

  function deleteCleanupContent(preview, checkboxId) {
    const cleanup = preview?.sibling_cleanup || {};
    const curated = Number(cleanup.curated_total || 0);
    if (!preview?.source_run_id || (!cleanup.has_cleanup && curated <= 0)) return null;
    const wrap = document.createElement('div');
    wrap.className = 'atlas-delete-cleanup-option';
    if (cleanup.has_cleanup) {
      const label = document.createElement('label');
      label.className = 'form-check';
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.id = checkboxId;
      checkbox.checked = false;
      checkbox.dataset.atlasDeleteCleanup = '1';
      const textNode = document.createElement('span');
      textNode.textContent = 'Also remove disposable Atlas items only sourced by the same run';
      label.append(checkbox, textNode);
      const note = document.createElement('div');
      note.className = 'atlas-muted';
      note.textContent = `This will remove ${cleanupLabel(cleanup)}.`;
      wrap.append(label, note);
    }
    if (curated > 0) {
      const curatedLabel = document.createElement('label');
      curatedLabel.className = 'form-check';
      const curatedCheckbox = document.createElement('input');
      curatedCheckbox.type = 'checkbox';
      curatedCheckbox.checked = false;
      curatedCheckbox.dataset.atlasDeleteCuratedCleanup = '1';
      const curatedText = document.createElement('span');
      curatedText.textContent = 'Also delete curated single-source Atlas items';
      curatedLabel.append(curatedCheckbox, curatedText);
      const curatedNote = document.createElement('div');
      curatedNote.className = 'atlas-muted';
      curatedNote.textContent = `${curatedCleanupLabel(cleanup)} will be kept unless this is checked. Curated means project-linked, project-visible, reviewed, labeled, or noted.`;
      wrap.append(curatedLabel);
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
      const prune = !!content?.querySelector?.('[data-atlas-delete-cleanup]')?.checked
        || !!content?.querySelector?.('[data-atlas-delete-curated-cleanup]')?.checked;
      const pruneCurated = !!content?.querySelector?.('[data-atlas-delete-curated-cleanup]')?.checked;
      const resp = await api()(`/atlas/entities/${encodeURIComponent(entityId)}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prune_source_run: prune, prune_curated_source_run: pruneCurated }),
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
      const prune = !!content?.querySelector?.('[data-atlas-delete-cleanup]')?.checked
        || !!content?.querySelector?.('[data-atlas-delete-curated-cleanup]')?.checked;
      const pruneCurated = !!content?.querySelector?.('[data-atlas-delete-curated-cleanup]')?.checked;
      const resp = await api()(`/atlas/findings/${encodeURIComponent(findingId)}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prune_source_run: prune, prune_curated_source_run: pruneCurated }),
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

  async function confirmCleanRunAtlas(run) {
    const runId = String(run && (run.id || run.run_id) || '');
    if (!runId || typeof global.showConfirm !== 'function') return;
    try {
      const previewResp = await api()(`/atlas/runs/${encodeURIComponent(runId)}/cleanup-preview`, { cache: 'no-store' });
      if (!previewResp.ok) throw new Error(`HTTP ${previewResp.status}`);
      const cleanup = (await previewResp.json()).cleanup || {};
      const curated = Number(cleanup.curated_total || 0);
      const removalNote = cleanup.has_cleanup
        ? `This will remove ${cleanupLabel(cleanup)} that only came from this run.`
        : 'No disposable same-run Atlas items were found.';
      const content = document.createElement('div');
      content.className = 'atlas-delete-cleanup-option';
      const primaryNote = document.createElement('div');
      primaryNote.className = 'atlas-muted';
      primaryNote.textContent = removalNote;
      content.appendChild(primaryNote);
      if (curated > 0) {
        const curatedLabel = document.createElement('label');
        curatedLabel.className = 'form-check';
        const curatedCheckbox = document.createElement('input');
        curatedCheckbox.type = 'checkbox';
        curatedCheckbox.checked = false;
        curatedCheckbox.dataset.atlasCleanCurated = '1';
        const curatedText = document.createElement('span');
        curatedText.textContent = 'Also delete curated single-source Atlas items';
        curatedLabel.append(curatedCheckbox, curatedText);
        const curatedNote = document.createElement('div');
        curatedNote.className = 'atlas-muted';
        curatedNote.textContent = `${curatedCleanupLabel(cleanup)} will be kept unless this is checked. Curated means project-linked, project-visible, reviewed, labeled, or noted.`;
        content.append(curatedLabel, curatedNote);
      } else {
        const keptNote = document.createElement('div');
        keptNote.className = 'atlas-muted';
        keptNote.textContent = 'Rows that still have other sources will stay in Atlas.';
        content.appendChild(keptNote);
      }
      const choice = await global.showConfirm({
        body: {
          text: 'Clean this run from Atlas?',
          note: 'The run transcript stays in History. Atlas source links from this run will be removed.',
        },
        content,
        tone: 'danger',
        refocusOnResolve: false,
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'clean', label: 'Clean Atlas', role: 'destructive' },
        ],
      });
      if (choice !== 'clean') return;
      const includeCurated = !!content.querySelector('[data-atlas-clean-curated]')?.checked;
      const resp = await api()(`/atlas/runs/${encodeURIComponent(runId)}/cleanup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ include_curated: includeCurated }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const result = (await resp.json()).cleanup || {};
      showToastSafe('Atlas cleaned for run', 'success');
      if (Number(result.deleted_entities || 0) > 0) {
        state.selectedId = '';
        state.detail = null;
      }
      await refreshAtlas({ resetOffset: false });
      if (state.selectedId) await loadDetail(state.selectedId, { renderLoading: false });
    } catch (err) {
      if (typeof global.logClientError === 'function') global.logClientError('failed to clean atlas run sources', err);
      showToastSafe('Failed to clean Atlas for run', 'error');
    }
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
    if (state.runId) params.set('run_id', state.runId);
    params.set('orphan_filter', state.orphanFilter);
    params.set('suppression_filter', state.suppressionFilter);
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
    clearFiltersBtn?.addEventListener('click', () => clearAtlasFilters());
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
    runFilterSearch?.addEventListener('input', () => {
      state.runOptionsQuery = String(runFilterSearch.value || '').trim();
      clearTimeout(state.runSearchTimer);
      state.runSearchTimer = setTimeout(() => {
        loadRunOptions({ query: state.runOptionsQuery, force: true });
      }, 180);
    });
    runFilterSearch?.addEventListener('focus', () => {
      loadRunOptions({ query: state.runOptionsQuery, force: !state.runOptionsLoaded });
    });
    runFilterSelect?.addEventListener('change', () => {
      const selected = runFilterSelect.selectedOptions?.[0] || null;
      applyRunFilter(
        runFilterSelect.value,
        selected?.dataset?.runCommand || selected?.textContent || '',
      );
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
      state.detailOffsets = { runs: 0, findings: 0 };
      state.selectedFindingIds.clear();
      state.selectedEntityIds.clear();
      state.detail = null;
      refreshAtlas({ resetOffset: true });
    });
    suppressionFilter?.addEventListener('change', () => {
      state.suppressionFilter = String(suppressionFilter.value || 'hide') || 'hide';
      state.selectedId = '';
      state.selectedFindingId = '';
      state.detailOffsets = { runs: 0, findings: 0 };
      state.selectedFindingIds.clear();
      state.selectedEntityIds.clear();
      state.detail = null;
      refreshAtlas({ resetOffset: true });
    });
    savedViewSelect?.addEventListener('change', () => {
      applySavedView(savedViewSelect.value);
    });
    savedViewSaveBtn?.addEventListener('click', () => {
      saveCurrentView();
    });
    savedViewUpdateBtn?.addEventListener('click', () => {
      updateCurrentSavedView();
    });
    savedViewDeleteBtn?.addEventListener('click', () => {
      deleteCurrentSavedView();
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
    bulkSuppressionBtn?.addEventListener('click', () => {
      bulkUpdateSuppression(state.suppressionFilter === 'only' ? false : true);
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

  ensureBulkActionLayout();
  bindEvents();

  // Controller surface exposed to companion modules (atlas_mobile.js).
  // The surface intentionally hides DOM-binding helpers and keeps the
  // mutation API around state, navigation, actions, and re-render hooks.
  const atlasController = {
    state,
    tabsApi,
    detailApi,
    metadataApi,
    findingStates,
    isOpen,
    currentTab,
    setActiveAtlasTab,
    cycleAtlasTab,
    selectEntity,
    pageEntityDetail,
    selectFinding,
    refreshAtlas,
    clearAtlasFilters,
    refreshIntel,
    addToActiveProject,
    removeProjectLink,
    saveMetadata,
    confirmDeleteEntity,
    confirmDeleteFinding,
    confirmCleanRunAtlas,
    updateFindingReviewState,
    updateSuppression,
    openEntityFromFinding,
    openSourceRun,
    exportEntities,
    loadRunOptions,
    applyRunFilter,
    loadSavedViews,
    applySavedView,
    saveCurrentView,
    updateCurrentSavedView,
    deleteCurrentSavedView,
    setSelectMode,
    selectAllVisibleItems,
    bulkUpdateFindings,
    bulkUpdateSuppression,
    bulkDeleteSelectedItems,
    activeSelectionSet,
    visibleSelectableItems,
    toggleItemSelection,
    rowMessage,
    badge,
    text,
    countLabel,
    registerMobileRenderer,
  };

  global.DarklabAtlasOverlay = atlasController;
  global.openAtlas = openAtlas;
  global.closeAtlas = closeAtlas;
  global.isAtlasOverlayOpen = isOpen;
  global.refreshAtlasOverlay = refreshAtlas;
  global.cycleAtlasTab = cycleAtlasTab;
})(typeof window !== 'undefined' ? window : globalThis);
