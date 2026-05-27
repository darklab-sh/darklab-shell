// Mobile Atlas controller — list-detail drill-in surface that composes
// the same state, action handlers, and detail renderers as the desktop
// Atlas overlay (atlas_overlay.js).
//
// The desktop layout is a two-pane split (list left, detail right). The
// mobile layout is a three-view stack (list view, entity-detail view,
// finding-detail view) where only one view is visible at a time and the
// user navigates via row tap + Back. Rather than fork the renderers, this
// module:
//
//   1. Subscribes to the shared atlas controller via
//      `controller.registerMobileRenderer(fn)` so it re-renders whenever
//      the overlay state changes.
//   2. Owns its own `view` state (list / entity / finding) and Back-stack
//      behavior since the desktop layout has no equivalent concept.
//   3. Re-uses `controller.detailApi.renderDetail` / `renderFindingDetail`
//      for the detail body — the renderers are host-agnostic and the
//      mobile body just passes a different host element.
//
// The module sets `body.atlas-mobile-ready` once it has wired itself up;
// atlas-mobile.css keys off that class so the dedicated mobile surface owns
// the small-screen path while desktop keeps the two-pane layout.

(function initAtlasMobile(global) {
  const controller = global.DarklabAtlasOverlay;
  const entityRowApi = global.DarklabAtlasEntityRow || {};
  if (!controller || typeof controller.registerMobileRenderer !== 'function') {
    // Atlas overlay didn't initialize (likely a non-Atlas page). Nothing
    // to do; the mobile module is dormant.
    return;
  }

  const root = document.getElementById('atlas-mobile-root');
  if (!root) return;

  const listView = document.getElementById('atlas-mobile-list-view');
  const entityView = document.getElementById('atlas-mobile-entity-view');
  const findingView = document.getElementById('atlas-mobile-finding-view');
  const tabsHost = document.getElementById('atlas-mobile-tabs');
  const toolsHost = document.getElementById('atlas-mobile-tools');
  const bulkBar = document.getElementById('atlas-mobile-bulk-bar');
  const listHost = document.getElementById('atlas-mobile-list');
  const paginationHost = document.getElementById('atlas-mobile-pagination');
  const entityTopbar = document.getElementById('atlas-mobile-entity-topbar');
  const entityBody = document.getElementById('atlas-mobile-entity-body');
  const entityFooter = document.getElementById('atlas-mobile-entity-footer');
  const findingTopbar = document.getElementById('atlas-mobile-finding-topbar');
  const findingBody = document.getElementById('atlas-mobile-finding-body');
  const findingFooter = document.getElementById('atlas-mobile-finding-footer');

  const required = [
    listView, entityView, findingView, tabsHost, toolsHost, bulkBar,
    listHost, paginationHost, entityTopbar, entityBody, entityFooter,
    findingTopbar, findingBody, findingFooter,
  ];
  if (required.some(el => !el)) return;

  const tabStripEdgeOpts = { wrapSelector: '.atlas-mobile-tabs-wrap' };

  const view = {
    name: 'list',
    filtersDisclosure: null,
    filtersOpen: false,
    lastActionSheetTab: '',
    suppressNextClick: false,
    requestedViewTimer: null,
  };

  function isMobileMode() {
    return !!(document.body && document.body.classList.contains('mobile-terminal-mode'));
  }

  function setView(name) {
    if (view.name === name) return;
    view.name = name;
    listView.classList.toggle('u-hidden', name !== 'list');
    entityView.classList.toggle('u-hidden', name !== 'entity');
    findingView.classList.toggle('u-hidden', name !== 'finding');
    if (name === 'list') {
      // Scroll the list back into view rather than restoring detail scroll.
      window.requestAnimationFrame(() => {
        try { listHost.scrollTop = listHost.scrollTop; } catch (_) {}
      });
    } else if (name === 'entity' && entityBody) {
      entityBody.scrollTop = 0;
    } else if (name === 'finding' && findingBody) {
      findingBody.scrollTop = 0;
    }
  }

  function clampCount(value) {
    const n = Number(value || 0);
    if (!Number.isFinite(n) || n <= 0) return '0';
    return n > 999 ? '999+' : String(n);
  }

  function tabCountFor(tab, state) {
    const api = controller.tabsApi || {};
    if (!api.countForTab) return '0';
    const filtered = api.countForTab(tab, state.summary);
    const total = api.countForTab(tab, state.baseSummary || state.summary);
    if (String(state.runId || '')) return `${clampCount(filtered)}/${clampCount(total)}`;
    return clampCount(filtered);
  }

  function truncateRunFilterLabel(value) {
    const text = String(value || '').trim() || 'run';
    if (text.length <= 17) return text;
    return `${text.slice(0, 14).trimEnd()}...`;
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

  function selectorValue(value) {
    if (typeof CSS !== 'undefined' && CSS && typeof CSS.escape === 'function') {
      return CSS.escape(String(value));
    }
    return String(value || '').replace(/["\\]/g, '\\$&');
  }

  function renderTabs(state) {
    if (!tabsHost) return;
    const tabs = (controller.tabsApi && controller.tabsApi.tabs) || [];
    tabsHost.replaceChildren();
    tabs.forEach(tab => {
      const button = document.createElement('button');
      button.type = 'button';
      const active = String(tab.id) === String(state.activeTab);
      button.className = 'tab-strip-item atlas-tab atlas-mobile-tab' + (active ? ' is-active' : '');
      button.dataset.atlasMobileTab = tab.id;
      button.setAttribute('role', 'tab');
      button.setAttribute('aria-selected', active ? 'true' : 'false');
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
      const label = document.createElement('span');
      label.textContent = tab.label;
      const count = document.createElement('span');
      count.className = 'atlas-tab-count';
      count.textContent = `(${tabCountFor(tab, state)})`;
      button.append(label, count);
      button.addEventListener('click', () => {
        if (typeof global.closeActionSheet === 'function') global.closeActionSheet({ restoreFocus: false });
        if (String(tab.id) !== String(state.activeTab)) {
          controller.setActiveAtlasTab(tab.id);
        }
        setView('list');
      });
      tabsHost.appendChild(button);
    });
    if (typeof global.syncActiveTabStripScroll === 'function') {
      global.syncActiveTabStripScroll(tabsHost, tabStripEdgeOpts);
    }
  }

  let toolsBuilt = false;
  let toolsSearchInput = null;
  let toolsOverflowBtn = null;
  let filtersToggle = null;
  let filtersToggleLabel = null;
  let filtersPanel = null;
  let mobileOrphanFilter = null;
  let mobileSuppressionFilter = null;
  let mobileFindingStatusFilter = null;
  let mobileRunFilterSearch = null;
  let mobileRunFilterSelect = null;
  let mobileSavedViewSelect = null;
  let orphanChipHost = null;
  let bulkStatusSelect = null;
  let searchTimer = null;
  let runSearchTimer = null;

  function findingStates() {
    return Array.isArray(controller.findingStates) ? controller.findingStates : [
      ['new', 'New'],
      ['reviewed', 'Reviewed'],
      ['important', 'Important'],
      ['false_positive', 'False positive'],
      ['needs_followup', 'Follow-up'],
    ];
  }

  function option(label, value) {
    const item = document.createElement('option');
    item.value = value;
    item.textContent = label;
    return item;
  }

  function activeFilterCount(state) {
    let count = 0;
    if (String(state.findingStatus || '')) count += 1;
    if (String(state.orphanFilter || 'hide') !== 'hide') count += 1;
    if (String(state.suppressionFilter || 'hide') !== 'hide') count += 1;
    if (String(state.runId || '')) count += 1;
    return count;
  }

  function resetMobileFilterSelections(state) {
    state.selectedFindingIds.clear();
    state.selectedEntityIds.clear();
    state.selectedId = '';
    state.selectedFindingId = '';
    state.detail = null;
  }

  function buildToolsOnce() {
    if (toolsBuilt) return;
    toolsHost.replaceChildren();
    const row = document.createElement('div');
    row.className = 'atlas-mobile-tools-row';

    const search = document.createElement('input');
    search.type = 'search';
    search.id = 'atlas-mobile-search';
    search.className = 'form-control form-control-compact atlas-mobile-search';
    search.placeholder = 'search atlas';
    search.autocomplete = 'off';
    search.setAttribute('autocapitalize', 'none');
    search.setAttribute('autocorrect', 'off');
    search.setAttribute('spellcheck', 'false');
    search.setAttribute('inputmode', 'text');
    search.setAttribute('aria-label', 'Search Atlas entities');
    search.addEventListener('input', () => {
      controller.state.query = String(search.value || '').trim();
      controller.state.requestedEntityValue = '';
      controller.state.refreshIntelOnSelect = false;
      controller.state.addActiveProjectOnSelect = false;
      controller.state.selectedFindingIds.clear();
      controller.state.selectedEntityIds.clear();
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => controller.refreshAtlas({ resetOffset: true }), 180);
    });
    toolsSearchInput = search;
    row.appendChild(search);

    const refresh = document.createElement('button');
    refresh.type = 'button';
    refresh.className = 'btn btn-secondary btn-compact atlas-mobile-refresh-btn';
    refresh.textContent = 'Refresh';
    refresh.setAttribute('aria-label', 'Refresh Atlas');
    refresh.addEventListener('click', () => controller.refreshAtlas());
    row.appendChild(refresh);

    const overflow = document.createElement('button');
    overflow.type = 'button';
    overflow.className = 'btn btn-ghost btn-compact atlas-mobile-action-menu-trigger atlas-mobile-overflow-btn';
    overflow.textContent = '☰';
    overflow.setAttribute('aria-label', 'More Atlas actions');
    overflow.addEventListener('click', () => openListOverflowSheet(overflow));
    toolsOverflowBtn = overflow;
    row.appendChild(overflow);

    const filterRow = document.createElement('div');
    filterRow.className = 'atlas-mobile-tools-row atlas-mobile-filter-row';
    const filterToggle = document.createElement('button');
    filterToggle.type = 'button';
    filterToggle.className = 'btn btn-secondary btn-compact atlas-mobile-filters-toggle';
    filterToggle.setAttribute('aria-controls', 'atlas-mobile-filters-panel');
    const filterLabel = document.createElement('span');
    filterLabel.textContent = '▸ Filters';
    filterToggle.appendChild(filterLabel);
    filtersToggle = filterToggle;
    filtersToggleLabel = filterLabel;

    const panel = document.createElement('div');
    panel.id = 'atlas-mobile-filters-panel';
    panel.className = 'atlas-mobile-filters-panel is-hidden';
    panel.hidden = true;

    const savedViewRow = document.createElement('div');
    savedViewRow.className = 'atlas-mobile-saved-view-row';
    const savedViewSelect = document.createElement('select');
    savedViewSelect.className = 'form-select form-control-compact atlas-mobile-saved-view-select';
    savedViewSelect.setAttribute('aria-label', 'Saved Atlas views');
    savedViewSelect.dataset.portalMenu = 'true';
    savedViewSelect.appendChild(option('Saved views', ''));
    savedViewSelect.addEventListener('change', () => controller.applySavedView(savedViewSelect.value));
    mobileSavedViewSelect = savedViewSelect;
    const saveView = document.createElement('button');
    saveView.type = 'button';
    saveView.className = 'btn btn-secondary btn-compact';
    saveView.textContent = 'Save';
    saveView.addEventListener('click', () => controller.saveCurrentView());
    const updateView = document.createElement('button');
    updateView.type = 'button';
    updateView.className = 'btn btn-ghost btn-compact atlas-mobile-saved-view-update';
    updateView.textContent = 'Update';
    updateView.disabled = true;
    updateView.addEventListener('click', () => controller.updateCurrentSavedView());
    const deleteView = document.createElement('button');
    deleteView.type = 'button';
    deleteView.className = 'btn btn-ghost btn-compact atlas-mobile-saved-view-delete';
    deleteView.textContent = 'Delete';
    deleteView.disabled = true;
    deleteView.addEventListener('click', () => controller.deleteCurrentSavedView());
    savedViewRow.append(savedViewSelect, saveView, updateView, deleteView);

    const orphanSelect = document.createElement('select');
    orphanSelect.className = 'form-select form-control-compact atlas-mobile-orphan-filter';
    orphanSelect.setAttribute('aria-label', 'Filter Atlas rows by source run');
    orphanSelect.dataset.portalMenu = 'true';
    orphanSelect.append(
      option('Hide orphaned', 'hide'),
      option('Show all', 'all'),
      option('Only orphaned', 'only'),
    );
    orphanSelect.addEventListener('change', () => {
      controller.state.orphanFilter = String(orphanSelect.value || 'hide') || 'hide';
      resetMobileFilterSelections(controller.state);
      controller.refreshAtlas({ resetOffset: true });
    });
    mobileOrphanFilter = orphanSelect;

    const suppressionSelect = document.createElement('select');
    suppressionSelect.className = 'form-select form-control-compact atlas-mobile-suppression-filter';
    suppressionSelect.setAttribute('aria-label', 'Filter Atlas rows by suppression state');
    suppressionSelect.dataset.portalMenu = 'true';
    suppressionSelect.append(
      option('Visible rows', 'hide'),
      option('Show all', 'all'),
      option('Only suppressed', 'only'),
    );
    suppressionSelect.addEventListener('change', () => {
      controller.state.suppressionFilter = String(suppressionSelect.value || 'hide') || 'hide';
      resetMobileFilterSelections(controller.state);
      controller.refreshAtlas({ resetOffset: true });
    });
    mobileSuppressionFilter = suppressionSelect;

    const runSearch = document.createElement('input');
    runSearch.type = 'search';
    runSearch.className = 'form-control form-control-compact atlas-mobile-run-filter-search';
    runSearch.placeholder = 'search runs';
    runSearch.autocomplete = 'off';
    runSearch.setAttribute('autocapitalize', 'none');
    runSearch.setAttribute('autocorrect', 'off');
    runSearch.setAttribute('spellcheck', 'false');
    runSearch.setAttribute('inputmode', 'text');
    runSearch.setAttribute('aria-label', 'Search runs for Atlas filter');
    runSearch.addEventListener('input', () => {
      controller.state.runOptionsQuery = String(runSearch.value || '').trim();
      clearTimeout(runSearchTimer);
      runSearchTimer = setTimeout(() => {
        Promise.resolve(controller.loadRunOptions?.({ query: controller.state.runOptionsQuery, force: true }))
          .then(() => render(controller.state));
      }, 180);
    });
    runSearch.addEventListener('focus', () => {
      Promise.resolve(controller.loadRunOptions?.({
        query: controller.state.runOptionsQuery,
        force: !controller.state.runOptionsLoaded,
      })).then(() => render(controller.state));
    });
    mobileRunFilterSearch = runSearch;

    const runSelect = document.createElement('select');
    runSelect.className = 'form-select form-control-compact atlas-mobile-run-filter-select';
    runSelect.setAttribute('aria-label', 'Filter Atlas by source run');
    runSelect.dataset.portalMenu = 'true';
    runSelect.appendChild(option('Filter by run', ''));
    runSelect.addEventListener('change', () => {
      const selected = runSelect.selectedOptions?.[0] || null;
      controller.applyRunFilter?.(
        runSelect.value,
        selected?.dataset?.runCommand || selected?.textContent || '',
      );
    });
    mobileRunFilterSelect = runSelect;

    const findingSelect = document.createElement('select');
    findingSelect.className = 'form-select form-control-compact atlas-mobile-finding-status-filter';
    findingSelect.setAttribute('aria-label', 'Filter Atlas findings by status');
    findingSelect.dataset.portalMenu = 'true';
    findingSelect.appendChild(option('All findings', ''));
    findingStates().forEach(([value, label]) => findingSelect.appendChild(option(label, value)));
    findingSelect.addEventListener('change', () => {
      controller.state.findingStatus = String(findingSelect.value || '');
      resetMobileFilterSelections(controller.state);
      controller.refreshAtlas({ resetOffset: true });
    });
    mobileFindingStatusFilter = findingSelect;

    panel.append(savedViewRow, runSearch, runSelect, orphanSelect, suppressionSelect, findingSelect);
    filtersPanel = panel;
    filterRow.append(filterToggle, panel);

    const chipHost = document.createElement('div');
    chipHost.className = 'atlas-mobile-orphan-chip-host u-hidden';
    orphanChipHost = chipHost;

    toolsHost.append(row, filterRow, chipHost);
    if (typeof global.bindDisclosure === 'function') {
      view.filtersDisclosure = global.bindDisclosure(filterToggle, {
        panel,
        openClass: 'open',
        hiddenClass: 'is-hidden',
        onToggle: (open) => {
          view.filtersOpen = !!open;
          panel.hidden = !open;
        },
      });
      panel.hidden = true;
    }
    if (typeof global.enhanceAppSelects === 'function') {
      global.enhanceAppSelects(panel);
    }
    toolsBuilt = true;
  }

  function syncTools(state) {
    buildToolsOnce();
    if (toolsSearchInput && toolsSearchInput.value !== state.query) {
      toolsSearchInput.value = state.query || '';
    }
    const filterCount = activeFilterCount(state);
    if (filtersToggleLabel) {
      const prefix = view.filtersOpen ? '▾' : '▸';
      filtersToggleLabel.textContent = `${prefix} Filters${filterCount ? ` (${filterCount})` : ''}`;
    }
    if (mobileOrphanFilter && mobileOrphanFilter.value !== state.orphanFilter) {
      mobileOrphanFilter.value = state.orphanFilter || 'hide';
      if (typeof global.syncAppSelect === 'function') global.syncAppSelect(mobileOrphanFilter);
    }
    if (mobileSuppressionFilter && mobileSuppressionFilter.value !== state.suppressionFilter) {
      mobileSuppressionFilter.value = state.suppressionFilter || 'hide';
      if (typeof global.syncAppSelect === 'function') global.syncAppSelect(mobileSuppressionFilter);
    }
    if (mobileRunFilterSearch && mobileRunFilterSearch.value !== state.runOptionsQuery) {
      mobileRunFilterSearch.value = state.runOptionsQuery || '';
    }
    if (mobileRunFilterSelect) {
      const optionRows = [...(state.runOptions || [])];
      if (state.runId && !optionRows.some(run => String(run.id || '') === String(state.runId || ''))) {
        optionRows.unshift({
          id: state.runId,
          run_id: state.runId,
          command: state.runLabel || state.runId,
          entity_count: 0,
          finding_count: 0,
        });
      }
      const values = ['', ...optionRows.map(run => String(run.id || ''))].join('\n');
      const currentValues = Array.from(mobileRunFilterSelect.options || []).map(option => option.value).join('\n');
      if (values !== currentValues) {
        mobileRunFilterSelect.replaceChildren();
        mobileRunFilterSelect.appendChild(option(state.runOptionsLoading ? 'Loading runs...' : 'Filter by run', ''));
        optionRows.forEach((run) => {
          const item = option(runOptionLabel(run), run.id || '');
          item.dataset.runCommand = String(run.command || '');
          mobileRunFilterSelect.appendChild(item);
        });
      } else if (mobileRunFilterSelect.options[0]) {
        mobileRunFilterSelect.options[0].textContent = state.runOptionsLoading ? 'Loading runs...' : 'Filter by run';
      }
      mobileRunFilterSelect.value = state.runId || '';
      mobileRunFilterSelect.disabled = !!state.runOptionsLoading;
      if (typeof global.syncAppSelect === 'function') global.syncAppSelect(mobileRunFilterSelect);
    }
    if (mobileFindingStatusFilter) {
      const findingsActive = controller.currentTab().id === 'findings';
      mobileFindingStatusFilter.classList.toggle('u-hidden', !findingsActive);
      const enhancedWrap = mobileFindingStatusFilter.nextElementSibling;
      if (enhancedWrap?.classList?.contains('app-select')) enhancedWrap.classList.toggle('u-hidden', !findingsActive);
      if (mobileFindingStatusFilter.value !== state.findingStatus) {
        mobileFindingStatusFilter.value = state.findingStatus || '';
        if (typeof global.syncAppSelect === 'function') global.syncAppSelect(mobileFindingStatusFilter);
      }
    }
    if (mobileSavedViewSelect) {
      const selectedId = controller.state.selectedSavedViewId || '';
      const values = ['', ...(controller.state.savedViews || []).map(view => String(view.id || ''))].join('\n');
      const currentValues = Array.from(mobileSavedViewSelect.options || []).map(option => option.value).join('\n');
      if (values !== currentValues) {
        mobileSavedViewSelect.replaceChildren();
        mobileSavedViewSelect.appendChild(option(controller.state.savedViewsLoading ? 'Loading views...' : 'Saved views', ''));
        (controller.state.savedViews || []).forEach((view) => {
          mobileSavedViewSelect.appendChild(option(view.name || 'Saved view', view.id || ''));
        });
      } else if (mobileSavedViewSelect.options[0]) {
        mobileSavedViewSelect.options[0].textContent = controller.state.savedViewsLoading ? 'Loading views...' : 'Saved views';
      }
      mobileSavedViewSelect.value = selectedId;
      mobileSavedViewSelect.disabled = !!controller.state.savedViewsLoading;
      const updateBtn = filtersPanel?.querySelector?.('.atlas-mobile-saved-view-update');
      const deleteBtn = filtersPanel?.querySelector?.('.atlas-mobile-saved-view-delete');
      if (updateBtn) updateBtn.disabled = !selectedId || !!controller.state.savedViewsLoading;
      if (deleteBtn) deleteBtn.disabled = !selectedId || !!controller.state.savedViewsLoading;
      if (typeof global.syncAppSelect === 'function') global.syncAppSelect(mobileSavedViewSelect);
    }
    renderOrphanChip(state);
    if (toolsOverflowBtn) toolsOverflowBtn.disabled = !!state.loading;
  }

  function renderOrphanChip(state) {
    if (!orphanChipHost) return;
    orphanChipHost.replaceChildren();
    const chips = [];
    if (String(state.orphanFilter || 'hide') === 'only') {
      chips.push(['orphans only · clear', () => { controller.state.orphanFilter = 'hide'; }]);
    }
    if (String(state.suppressionFilter || 'hide') === 'only') {
      chips.push(['suppressed only · clear', () => { controller.state.suppressionFilter = 'hide'; }]);
    }
    if (String(state.runId || '')) {
      chips.push([`Run: ${truncateRunFilterLabel(state.runLabel || state.runId)} ×`, () => {
        controller.state.runId = '';
        controller.state.runLabel = '';
      }]);
    }
    orphanChipHost.classList.toggle('u-hidden', !chips.length);
    chips.forEach(([label, action]) => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'chip chip-removable atlas-mobile-orphan-chip';
      chip.textContent = label;
      chip.addEventListener('click', () => {
        action();
        resetMobileFilterSelections(controller.state);
        controller.refreshAtlas({ resetOffset: true });
      });
      orphanChipHost.appendChild(chip);
    });
  }

  function copyText(value, label = 'Copied') {
    const text = String(value || '').trim();
    if (!text) return;
    const copier = typeof global.copyTextToClipboard === 'function'
      ? global.copyTextToClipboard(text)
      : navigator.clipboard?.writeText?.(text);
    Promise.resolve(copier)
      .then(() => {
        if (typeof global.showToast === 'function') global.showToast(label, 'success');
      })
      .catch(() => {
        if (typeof global.showToast === 'function') global.showToast('Copy failed', 'error');
      });
  }

  function firstSourceRun(item) {
    const links = Array.isArray(item?.run_links) ? item.run_links : [];
    const first = links[0] || null;
    const runId = String(item?.run_id || item?.source_run_id || first?.run_id || first?.id || '');
    return runId ? { ...first, id: runId, run_id: runId, command: item?.run_command || first?.command || '' } : null;
  }

  function openMetadataEditorForEntity(entity) {
    if (typeof global.openEntityMetadataEditor !== 'function') return;
    global.openEntityMetadataEditor('atlas_entity', entity, {
      onSaved: () => controller.refreshAtlas(),
    });
  }

  function openSourceRunFromItem(item) {
    const run = firstSourceRun(item);
    if (run) controller.openSourceRun(run);
  }

  function openListOverflowSheet(returnFocus) {
    if (typeof global.openActionSheet !== 'function') return;
    const tab = controller.currentTab();
    const items = [];
    if (tab.id !== 'findings') {
      items.push(
        { label: 'Export CSV', action: () => controller.exportEntities('csv') },
        { label: 'Export JSONL', action: () => controller.exportEntities('jsonl') },
      );
    }
    items.push({
      label: controller.state.selectMode ? 'Exit select mode' : 'Select mode',
      action: () => controller.setSelectMode(!controller.state.selectMode),
    });
    items.push({ divider: true });
    items.push({ label: 'Refresh Atlas', action: () => controller.refreshAtlas() });
    view.lastActionSheetTab = tab.id;
    global.openActionSheet({
      title: 'Atlas actions',
      items,
      returnFocus,
      onClose: () => { view.lastActionSheetTab = ''; },
    });
  }

  function entityActionItems(entity) {
    const activeProject = typeof global.getActiveProjectContext === 'function'
      ? global.getActiveProjectContext()
      : null;
    const activeId = activeProject && activeProject.id ? String(activeProject.id) : '';
    const items = [
      { label: 'Copy value', action: () => copyText(entity.canonical_value || entity.value || '', 'Entity copied') },
    ];
    if (activeId && !entity.project_link_count) {
      items.push({
        label: 'Add to active project',
        action: () => {
          controller.state.selectedId = String(entity.id || '');
          return controller.addToActiveProject();
        },
      });
    }
    items.push(
      {
        label: controller.state.intelRefreshing ? 'Refreshing intel...' : 'Refresh intel',
        disabled: !!controller.state.intelRefreshing,
        action: () => {
          controller.state.selectedId = String(entity.id || '');
          return controller.refreshIntel();
        },
      },
      { label: 'See source run', disabled: !firstSourceRun(entity), action: () => openSourceRunFromItem(entity) },
      { label: 'Add label', action: () => openMetadataEditorForEntity(entity) },
      { label: 'Edit note', action: () => openMetadataEditorForEntity(entity) },
      { label: entity.suppressed ? 'Restore' : 'Suppress', action: () => controller.updateSuppression(entity, !entity.suppressed) },
      { divider: true },
      {
        label: 'Delete',
        tone: 'danger',
        action: () => {
          controller.state.selectedId = String(entity.id || '');
          return controller.confirmDeleteEntity();
        },
      },
    );
    return items;
  }

  function findingActionItems(finding) {
    return [
      { label: 'Copy title', action: () => copyText(finding.title || finding.raw_line || '', 'Finding copied') },
      { label: 'Mark reviewed', action: () => controller.updateFindingReviewState(finding, 'reviewed') },
      { label: 'Mark important', action: () => controller.updateFindingReviewState(finding, 'important') },
      { label: 'Mark false positive', action: () => controller.updateFindingReviewState(finding, 'false_positive') },
      {
        label: 'Open entity',
        disabled: !finding.entity_id || !finding.entity_type,
        action: () => {
          controller.openEntityFromFinding(finding);
          setView('entity');
        },
      },
      { label: 'See source run', disabled: !firstSourceRun(finding), action: () => openSourceRunFromItem(finding) },
      { label: finding.suppressed ? 'Restore' : 'Suppress', action: () => controller.updateSuppression(finding, !finding.suppressed) },
      { divider: true },
      {
        label: 'Delete',
        tone: 'danger',
        action: () => {
          controller.state.selectedFindingId = String(finding.id || '');
          return controller.confirmDeleteFinding(finding);
        },
      },
    ];
  }

  function openEntityActionSheet(entity, returnFocus, title = 'Atlas entity actions') {
    if (!entity || typeof global.openActionSheet !== 'function') return;
    view.lastActionSheetTab = controller.currentTab().id;
    global.openActionSheet({
      title,
      items: entityActionItems(entity),
      returnFocus,
      onClose: () => { view.lastActionSheetTab = ''; },
    });
  }

  function openFindingActionSheet(finding, returnFocus, title = 'Atlas finding actions') {
    if (!finding || typeof global.openActionSheet !== 'function') return;
    view.lastActionSheetTab = controller.currentTab().id;
    global.openActionSheet({
      title,
      items: findingActionItems(finding),
      returnFocus,
      onClose: () => { view.lastActionSheetTab = ''; },
    });
  }

  function rowMessage(text) {
    if (controller.rowMessage) return controller.rowMessage(text);
    const row = document.createElement('div');
    row.className = 'atlas-empty';
    row.textContent = text;
    return row;
  }

  function activeSelectionSet(state) {
    return controller.currentTab().id === 'findings' ? state.selectedFindingIds : state.selectedEntityIds;
  }

  function visibleSelectableItems(state) {
    return controller.currentTab().id === 'findings' ? (state.findings || []) : (state.entities || []);
  }

  function appendMobileSelectionCheckbox(row, item, state, label) {
    const selected = activeSelectionSet(state);
    const wrap = document.createElement('span');
    wrap.className = 'atlas-mobile-row-select';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = selected.has(String(item.id || ''));
    checkbox.setAttribute('aria-label', label);
    checkbox.addEventListener('click', event => event.stopPropagation());
    checkbox.addEventListener('change', () => controller.toggleItemSelection(item, checkbox.checked));
    wrap.appendChild(checkbox);
    row.prepend(wrap);
  }

  function renderBulkBar(state) {
    bulkBar.replaceChildren();
    const tab = controller.currentTab();
    const visibleItems = visibleSelectableItems(state).filter(item => item && item.id);
    const selected = activeSelectionSet(state);
    const selectedCount = selected.size;
    const show = !!state.selectMode && visibleItems.length > 0;
    bulkBar.classList.toggle('u-hidden', !show);
    listHost.classList.toggle('is-selecting', !!state.selectMode);
    document.body.classList.toggle('atlas-mobile-selecting', !!state.selectMode);
    if (!show) return;

    const selectAll = document.createElement('button');
    selectAll.type = 'button';
    selectAll.className = 'btn btn-secondary btn-compact';
    selectAll.textContent = 'Select all';
    selectAll.disabled = state.loading || state.bulkInFlight;
    selectAll.addEventListener('click', () => controller.selectAllVisibleItems());

    const clear = document.createElement('button');
    clear.type = 'button';
    clear.className = 'btn btn-ghost btn-compact';
    clear.textContent = 'Clear';
    clear.disabled = !selectedCount || state.loading || state.bulkInFlight;
    clear.addEventListener('click', () => {
      selected.clear();
      renderMobile(state);
    });

    bulkBar.append(selectAll, clear);

    if (tab.id === 'findings') {
      const review = document.createElement('select');
      review.className = 'form-select form-control-compact atlas-mobile-bulk-status';
      review.setAttribute('aria-label', 'Bulk finding review state');
      review.dataset.portalMenu = 'true';
      findingStates().forEach(([value, label]) => review.appendChild(option(label, value)));
      review.value = bulkStatusSelect?.value || 'reviewed';
      review.addEventListener('change', () => { bulkStatusSelect = review; });
      bulkStatusSelect = review;
      const apply = document.createElement('button');
      apply.type = 'button';
      apply.className = 'btn btn-secondary btn-compact';
      apply.textContent = 'Apply';
      apply.disabled = !selectedCount || state.loading || state.bulkInFlight;
      apply.addEventListener('click', () => controller.bulkUpdateFindings(review.value));
      bulkBar.append(review, apply);
    }

    const suppress = document.createElement('button');
    suppress.type = 'button';
    suppress.className = 'btn btn-secondary btn-compact';
    suppress.textContent = state.suppressionFilter === 'only' ? 'Restore' : 'Suppress';
    suppress.disabled = !selectedCount || state.loading || state.bulkInFlight;
    suppress.addEventListener('click', () => controller.bulkUpdateSuppression(state.suppressionFilter === 'only' ? false : true));
    bulkBar.appendChild(suppress);

    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'btn btn-secondary btn-danger btn-compact';
    del.textContent = 'Delete';
    del.disabled = !selectedCount || state.loading || state.bulkInFlight;
    del.addEventListener('click', () => controller.bulkDeleteSelectedItems());
    const summary = document.createElement('span');
    summary.className = 'atlas-mobile-bulk-summary';
    summary.textContent = `${selectedCount.toLocaleString()} selected`;
    bulkBar.append(del, summary);

    if (typeof global.enhanceAppSelects === 'function') global.enhanceAppSelects(bulkBar);
  }

  function renderEntityRow(entity, state) {
    const handleActivation = () => {
      if (view.suppressNextClick) {
        view.suppressNextClick = false;
        return;
      }
      if (state.selectMode) {
        controller.toggleItemSelection(entity);
        return;
      }
      controller.selectEntity(entity.id);
      setView('entity');
    };
    const row = entityRowApi.renderAtlasEntityRow({
      entity,
      selected: state.selectMode
        ? state.selectedEntityIds.has(String(entity.id || ''))
        : String(entity.id) === String(state.selectedId),
      selectMode: state.selectMode,
      mobile: true,
      text: controller.text,
      countLabel: controller.countLabel,
      badge: controller.badge,
      appendSelectionControl: state.selectMode
        ? targetRow => appendMobileSelectionCheckbox(targetRow, entity, state, `Select entity: ${entity.canonical_value || entity.id}`)
        : null,
      onActivate: handleActivation,
    });
    return row;
  }

  function renderFindingRow(finding, state) {
    const row = document.createElement('div');
    row.className = 'chrome-row chrome-row-clickable atlas-finding-queue-row atlas-mobile-row';
    if (String(finding.id) === String(state.selectedFindingId)) row.classList.add('is-selected');
    row.dataset.atlasMobileFindingId = finding.id;
    row.tabIndex = 0;
    row.setAttribute('role', state.selectMode ? 'checkbox' : 'button');
    if (state.selectMode) row.setAttribute('aria-checked', String(state.selectedFindingIds.has(String(finding.id || ''))));
    row.setAttribute('aria-label', `Open finding ${finding.title || finding.id}`);

    const main = document.createElement('span');
    main.className = 'atlas-entity-main';
    const title = document.createElement('span');
    title.className = 'atlas-finding-title';
    title.textContent = controller.text(finding.title || finding.raw_line, finding.id);
    const meta = document.createElement('span');
    meta.className = 'atlas-muted';
    const severity = finding.severity ? String(finding.severity).toLowerCase() : '';
    const reviewState = finding.review_state ? String(finding.review_state).toLowerCase() : 'new';
    const metaParts = [];
    if (finding.suppressed) metaParts.push('suppressed');
    if (severity) metaParts.push(severity);
    metaParts.push(reviewState);
    const occurrences = Number(finding.occurrence_count || 0);
    if (occurrences > 0) metaParts.push(`${controller.countLabel(occurrences, 'hit', 'hits')}`);
    meta.textContent = metaParts.join(' · ');
    main.append(title, meta);

    const badges = document.createElement('span');
    badges.className = 'atlas-entity-badges';
    if (finding.suppressed) badges.appendChild(controller.badge('suppressed', 'muted'));
    const severityTone = severity === 'high' || severity === 'critical' ? 'red' : 'muted';
    if (severity) badges.appendChild(controller.badge(severity, severityTone));

    const chev = document.createElement('span');
    chev.className = 'atlas-mobile-row-chev drill-chev';
    chev.setAttribute('aria-hidden', 'true');
    chev.textContent = '›';

    row.append(main, badges, chev);
    if (state.selectMode) {
      appendMobileSelectionCheckbox(row, finding, state, `Select finding: ${finding.title || finding.id}`);
    }
    row.addEventListener('click', () => {
      if (view.suppressNextClick) {
        view.suppressNextClick = false;
        return;
      }
      if (state.selectMode) {
        controller.toggleItemSelection(finding);
        return;
      }
      controller.selectFinding(finding.id);
      setView('finding');
    });
    row.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      row.click();
    });
    return row;
  }

  function renderList(state) {
    listHost.replaceChildren();
    if (state.loading) {
      listHost.appendChild(rowMessage('Loading Atlas...'));
      return;
    }
    const tab = controller.currentTab();
    if (tab.id === 'findings') {
      const findings = state.findings || [];
      if (!findings.length) {
        listHost.appendChild(rowMessage(state.query || state.findingStatus ? 'No matching findings' : 'No findings queued'));
        return;
      }
      findings.forEach(f => listHost.appendChild(renderFindingRow(f, state)));
      return;
    }
    const entities = state.entities || [];
    if (!entities.length) {
      listHost.appendChild(rowMessage(state.query ? 'No matching entities' : 'No entities yet'));
      return;
    }
    entities.forEach(e => listHost.appendChild(renderEntityRow(e, state)));
  }

  function itemFromMobileRow(row, state) {
    if (!row) return null;
    const findingId = String(row.dataset.atlasMobileFindingId || '');
    if (findingId) return (state.findings || []).find(item => String(item.id || '') === findingId) || null;
    const entityId = String(row.dataset.atlasMobileEntityId || '');
    if (entityId) return (state.entities || []).find(item => String(item.id || '') === entityId) || null;
    return null;
  }

  function openRowActionSheet(row) {
    const item = itemFromMobileRow(row, controller.state);
    if (!item) return;
    view.suppressNextClick = true;
    if (row.dataset.atlasMobileFindingId) openFindingActionSheet(item, row);
    else openEntityActionSheet(item, row);
  }

  function bindRowLongPress() {
    let timer = null;
    let startX = 0;
    let startY = 0;
    let targetRow = null;
    function clear() {
      if (timer) window.clearTimeout(timer);
      timer = null;
      targetRow = null;
    }
    listHost.addEventListener('touchstart', (event) => {
      const row = event.target.closest?.('.atlas-mobile-row');
      if (!row || controller.state.selectMode) return;
      const touch = event.touches && event.touches[0];
      if (!touch) return;
      startX = touch.clientX;
      startY = touch.clientY;
      targetRow = row;
      timer = window.setTimeout(() => {
        if (!targetRow) return;
        openRowActionSheet(targetRow);
        timer = null;
      }, 500);
    }, { passive: true });
    listHost.addEventListener('touchmove', (event) => {
      if (!timer) return;
      const touch = event.touches && event.touches[0];
      if (!touch) return;
      if (Math.abs(touch.clientX - startX) > 8 || Math.abs(touch.clientY - startY) > 8) clear();
    }, { passive: true });
    listHost.addEventListener('touchend', clear, { passive: true });
    listHost.addEventListener('touchcancel', clear, { passive: true });
    listHost.addEventListener('contextmenu', (event) => {
      const row = event.target.closest?.('.atlas-mobile-row');
      if (!row || controller.state.selectMode) return;
      event.preventDefault();
      openRowActionSheet(row);
    });
  }

  function renderPagination(state) {
    paginationHost.replaceChildren();
    const showPager = state.total > state.limit || state.offset > 0;
    paginationHost.classList.toggle('u-hidden', !showPager);
    if (!showPager) return;
    const start = state.total ? state.offset + 1 : 0;
    const end = Math.min(state.offset + state.limit, state.total);
    const summary = document.createElement('span');
    summary.className = 'atlas-mobile-pagination-summary atlas-muted';
    summary.textContent = `${start}-${end} of ${state.total.toLocaleString()}`;
    const prev = document.createElement('button');
    prev.type = 'button';
    prev.className = 'btn btn-secondary btn-compact';
    prev.textContent = 'Previous';
    prev.disabled = state.offset <= 0 || state.loading;
    prev.addEventListener('click', () => {
      controller.state.offset = Math.max(0, controller.state.offset - controller.state.limit);
      controller.refreshAtlas();
    });
    const next = document.createElement('button');
    next.type = 'button';
    next.className = 'btn btn-secondary btn-compact';
    next.textContent = 'Next';
    next.disabled = state.offset + state.limit >= state.total || state.loading;
    next.addEventListener('click', () => {
      controller.state.offset = controller.state.offset + controller.state.limit;
      controller.refreshAtlas();
    });
    const pager = document.createElement('div');
    pager.className = 'atlas-mobile-pagination-actions';
    pager.append(prev, next);
    paginationHost.append(summary, pager);
  }

  function renderEntityTopbar(state) {
    entityTopbar.replaceChildren();
    const back = document.createElement('button');
    back.type = 'button';
    back.className = 'btn btn-ghost btn-compact atlas-mobile-back-btn';
    back.setAttribute('aria-label', 'Back to Atlas list');
    back.textContent = '‹ Back';
    back.addEventListener('click', () => setView('list'));

    const detail = state.detail || {};
    const entity = detail.entity || detail;
    const titleWrap = document.createElement('div');
    titleWrap.className = 'atlas-mobile-detail-title-wrap';
    const title = document.createElement('div');
    title.className = 'atlas-mobile-detail-title';
    title.textContent = controller.text(entity.canonical_value, entity.id || '—');
    titleWrap.appendChild(title);
    if (entity.type) {
      const sub = document.createElement('div');
      sub.className = 'atlas-mobile-detail-subtitle';
      sub.textContent = String(entity.type);
      titleWrap.appendChild(sub);
    }

    entityTopbar.append(back, titleWrap);
    const isOrphan = Array.isArray(entity.run_links) && entity.run_links.length === 0;
    if (isOrphan) {
      const orphan = document.createElement('span');
      orphan.className = 'badge badge-tone-amber atlas-mobile-orphan-badge';
      orphan.textContent = 'orphan';
      entityTopbar.appendChild(orphan);
    }
    const more = document.createElement('button');
    more.type = 'button';
    more.className = 'btn btn-ghost btn-compact atlas-mobile-action-menu-trigger atlas-mobile-detail-more';
    more.textContent = '☰';
    more.setAttribute('aria-label', 'More entity actions');
    more.addEventListener('click', () => {
      const entity = state.detail?.entity || state.detail || {};
      openEntityActionSheet(entity, more, 'Atlas entity actions');
    });
    entityTopbar.appendChild(more);
  }

  function renderEntityBody(state) {
    if (state.detailLoading) {
      entityBody.replaceChildren(rowMessage('Loading entity...'));
      return;
    }
    if (!state.detail) {
      entityBody.replaceChildren(rowMessage('Select an entity to see details.'));
      return;
    }
    const activeProject = typeof global.getActiveProjectContext === 'function'
      ? global.getActiveProjectContext()
      : null;
    if (controller.detailApi && typeof controller.detailApi.renderDetail === 'function') {
      controller.detailApi.renderDetail(entityBody, state.detail, {
        activeProject,
        isLinkedToActiveProject: (entity) => {
          const activeId = activeProject && activeProject.id ? String(activeProject.id) : '';
          return !!activeId && (Array.isArray(entity.project_links) ? entity.project_links : [])
            .some(link => String(link.project_id || '') === activeId);
        },
        // Mobile suppresses the inline action row at the top of the body;
        // the sticky footer below is the single source of action truth on
        // mobile so the user does not see duplicate buttons.
        hideInlineActions: true,
        intelRefreshing: !!state.intelRefreshing,
        onRefreshIntel: () => controller.refreshIntel(),
        onAddToActiveProject: () => controller.addToActiveProject(),
        onRemoveProjectLink: (link) => controller.removeProjectLink(link),
        onSaveMetadata: (payload) => controller.saveMetadata(payload),
        onSeeRun: (run) => controller.openSourceRun(run),
        onCleanRunAtlas: (run) => controller.confirmCleanRunAtlas?.(run),
        onDeleteEntity: () => controller.confirmDeleteEntity(),
        onSuppressEntity: (entity) => controller.updateSuppression(entity, !entity.suppressed),
        onPageRuns: (offset) => controller.pageEntityDetail?.('runs', offset),
        onPageFindings: (offset) => controller.pageEntityDetail?.('findings', offset),
      });
    } else {
      entityBody.replaceChildren(rowMessage('Entity detail renderer unavailable.'));
    }
  }

  function renderEntityFooter(state) {
    entityFooter.replaceChildren();
    if (!state.detail || state.detailLoading) return;
    const entity = state.detail.entity || {};
    const activeProject = typeof global.getActiveProjectContext === 'function'
      ? global.getActiveProjectContext()
      : null;
    const activeId = activeProject && activeProject.id ? String(activeProject.id) : '';
    const links = Array.isArray(entity.project_links) ? entity.project_links : [];
    const activeLink = activeId
      ? links.find(link => String(link.project_id || '') === activeId)
      : null;

    const refresh = document.createElement('button');
    refresh.type = 'button';
    refresh.className = 'btn btn-secondary btn-compact';
    refresh.disabled = !!state.intelRefreshing;
    refresh.setAttribute('aria-busy', state.intelRefreshing ? 'true' : 'false');
    refresh.textContent = state.intelRefreshing ? 'Refreshing...' : 'Refresh intel';
    refresh.addEventListener('click', () => controller.refreshIntel());
    entityFooter.appendChild(refresh);

    if (activeId) {
      const link = document.createElement('button');
      link.type = 'button';
      // Same role as the other footer buttons so visual weight stays even.
      link.className = 'btn btn-secondary btn-compact';
      if (activeLink) {
        link.textContent = 'Unlink active project';
        link.addEventListener('click', () => controller.removeProjectLink(activeLink));
      } else {
        link.textContent = 'Add to active project';
        link.addEventListener('click', () => controller.addToActiveProject());
      }
      entityFooter.appendChild(link);
    }

    const suppression = document.createElement('button');
    suppression.type = 'button';
    suppression.className = 'btn btn-secondary btn-compact';
    suppression.textContent = entity.suppressed ? 'Restore' : 'Suppress';
    suppression.addEventListener('click', () => controller.updateSuppression(entity, !entity.suppressed));
    entityFooter.appendChild(suppression);

    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'btn btn-secondary btn-danger btn-compact';
    del.textContent = 'Delete';
    del.addEventListener('click', () => controller.confirmDeleteEntity());
    entityFooter.appendChild(del);
  }

  function renderFindingTopbar(state) {
    findingTopbar.replaceChildren();
    const back = document.createElement('button');
    back.type = 'button';
    back.className = 'btn btn-ghost btn-compact atlas-mobile-back-btn';
    back.setAttribute('aria-label', 'Back to Atlas list');
    back.textContent = '‹ Back';
    back.addEventListener('click', () => setView('list'));

    const finding = (state.findings || []).find(f => String(f.id) === String(state.selectedFindingId)) || null;
    const titleWrap = document.createElement('div');
    titleWrap.className = 'atlas-mobile-detail-title-wrap';
    const title = document.createElement('div');
    title.className = 'atlas-mobile-detail-title';
    title.textContent = controller.text(finding && (finding.title || finding.raw_line), 'Finding');
    titleWrap.appendChild(title);
    if (finding && finding.severity) {
      const sub = document.createElement('div');
      sub.className = 'atlas-mobile-detail-subtitle';
      sub.textContent = String(finding.severity).toLowerCase();
      titleWrap.appendChild(sub);
    }
    findingTopbar.append(back, titleWrap);
    const more = document.createElement('button');
    more.type = 'button';
    more.className = 'btn btn-ghost btn-compact atlas-mobile-action-menu-trigger atlas-mobile-detail-more';
    more.textContent = '☰';
    more.setAttribute('aria-label', 'More finding actions');
    more.disabled = !finding;
    more.addEventListener('click', () => {
      if (finding) openFindingActionSheet(finding, more, 'Atlas finding actions');
    });
    findingTopbar.appendChild(more);
  }

  function renderFindingBody(state) {
    if (state.detailLoading) {
      findingBody.replaceChildren(rowMessage('Loading finding...'));
      return;
    }
    const finding = (state.findings || []).find(f => String(f.id) === String(state.selectedFindingId)) || null;
    if (!finding) {
      findingBody.replaceChildren(rowMessage('Finding not found.'));
      return;
    }
    if (controller.detailApi && typeof controller.detailApi.renderFindingDetail === 'function') {
      controller.detailApi.renderFindingDetail(findingBody, finding, {
        hideInlineActions: true,
        onReviewState: (item, reviewState) => controller.updateFindingReviewState(item, reviewState),
        onSeeRun: (item) => controller.openSourceRun({
          id: item.run_id,
          run_id: item.run_id,
          command: item.run_command,
          run_kind: item.run_kind,
        }),
        onOpenEntity: (item) => {
          controller.openEntityFromFinding(item);
          setView('entity');
        },
        onDeleteFinding: (item) => controller.confirmDeleteFinding(item),
        onSuppressFinding: (item) => controller.updateSuppression(item, !item.suppressed),
      });
    } else {
      findingBody.replaceChildren(rowMessage('Finding renderer unavailable.'));
    }
  }

  function renderFindingFooter(state) {
    findingFooter.replaceChildren();
    const finding = (state.findings || []).find(f => String(f.id) === String(state.selectedFindingId)) || null;
    if (!finding) return;

    // Move the review-state picker from the body into the footer so mobile
    // users keep that control after the inline action row is suppressed.
    // Opt into the app-native select enhancement so the dropdown matches
    // the rest of the shell instead of using the browser-native control.
    // `portalMenu` lets the open menu escape the footer's overflow and the
    // updated portal positioner in ui_helpers flips it above the trigger
    // when there is no room below (which is the case here — the footer is
    // pinned to the bottom of the viewport).
    if (controller.detailApi && typeof controller.detailApi.reviewStateSelect === 'function') {
      const select = controller.detailApi.reviewStateSelect(
        finding.review_state || finding.status,
        (reviewState) => controller.updateFindingReviewState(finding, reviewState),
      );
      if (select) {
        select.classList.add('atlas-mobile-footer-select');
        select.dataset.portalMenu = 'true';
        findingFooter.appendChild(select);
        if (typeof global.enhanceAppSelects === 'function') {
          global.enhanceAppSelects(findingFooter);
        }
      }
    }

    const seeRun = document.createElement('button');
    seeRun.type = 'button';
    seeRun.className = 'btn btn-secondary btn-compact';
    seeRun.textContent = 'See source run';
    seeRun.addEventListener('click', () => controller.openSourceRun({
      id: finding.run_id,
      run_id: finding.run_id,
      command: finding.run_command,
      run_kind: finding.run_kind,
    }));
    findingFooter.appendChild(seeRun);

    const suppression = document.createElement('button');
    suppression.type = 'button';
    suppression.className = 'btn btn-secondary btn-compact';
    suppression.textContent = finding.suppressed ? 'Restore' : 'Suppress';
    suppression.addEventListener('click', () => controller.updateSuppression(finding, !finding.suppressed));
    findingFooter.appendChild(suppression);

    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'btn btn-secondary btn-danger btn-compact';
    del.textContent = 'Delete';
    del.addEventListener('click', () => controller.confirmDeleteFinding(finding));
    findingFooter.appendChild(del);
  }

  function syncViewAfterStateChange(state) {
    // If the user is in entity view but the selected entity vanished
    // (deleted, filtered out by orphan toggle, etc.), bounce back to list.
    if (view.name === 'entity' && !state.selectedId) setView('list');
    if (view.name === 'finding' && !state.selectedFindingId) setView('list');
  }

  function syncRequestedView(state) {
    if (!isMobileMode()) return;
    if (state.requestedView === 'list') {
      setView('list');
      state.requestedView = '';
      state.requestedViewStarted = 0;
      return;
    }
    if (state.requestedView !== 'detail') return;
    if (state.selectedId && state.detail) {
      setView('entity');
      state.requestedView = '';
      state.requestedViewStarted = 0;
      return;
    }
    if (controller.currentTab().id === 'findings' && state.selectedFindingId) {
      setView('finding');
      state.requestedView = '';
      state.requestedViewStarted = 0;
      return;
    }
    const started = Number(state.requestedViewStarted || 0);
    if (started && Date.now() - started > 1500) {
      state.requestedView = '';
      state.requestedViewStarted = 0;
      setView('list');
      if (typeof global.showToast === 'function') {
        global.showToast('Entity not found in Atlas — showing list', 'warning');
      }
    }
  }

  function renderMobile(state) {
    if (!isMobileMode()) {
      root.classList.add('u-hidden');
      document.body.classList.remove('atlas-mobile-selecting');
      return;
    }
    root.classList.remove('u-hidden');
    if (!document.body.classList.contains('atlas-mobile-ready')) {
      document.body.classList.add('atlas-mobile-ready');
    }
    if (view.lastActionSheetTab && view.lastActionSheetTab !== controller.currentTab().id) {
      if (typeof global.closeActionSheet === 'function') global.closeActionSheet({ restoreFocus: false });
      view.lastActionSheetTab = '';
    }

    renderTabs(state);
    syncTools(state);
    renderBulkBar(state);
    renderList(state);
    renderPagination(state);
    renderEntityTopbar(state);
    renderEntityBody(state);
    renderEntityFooter(state);
    renderFindingTopbar(state);
    renderFindingBody(state);
    renderFindingFooter(state);

    syncViewAfterStateChange(state);
    syncRequestedView(state);
  }

  // Scroll-edge sync on the mobile tab strip.
  if (typeof global.bindTabStripEdgeListener === 'function') {
    global.bindTabStripEdgeListener(tabsHost, tabStripEdgeOpts);
  }
  bindRowLongPress();

  // Watch body class to remove `atlas-mobile-ready` when leaving mobile.
  function syncReadyClass() {
    if (!isMobileMode() && document.body.classList.contains('atlas-mobile-ready')) {
      document.body.classList.remove('atlas-mobile-ready');
    }
  }
  if (typeof MutationObserver !== 'undefined') {
    const observer = new MutationObserver(() => syncReadyClass());
    observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
  }

  controller.registerMobileRenderer(renderMobile);

  global.DarklabAtlasMobile = {
    setView,
    currentView: () => view.name,
    resetTransientState: () => {
      setView('list');
      view.filtersDisclosure?.close?.();
      view.filtersOpen = false;
      if (filtersPanel) filtersPanel.hidden = true;
      if (typeof global.closeActionSheet === 'function') global.closeActionSheet({ restoreFocus: false });
    },
  };
})(typeof window !== 'undefined' ? window : globalThis);
