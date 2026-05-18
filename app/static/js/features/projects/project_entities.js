// Project Entities tab controller.
// Loaded before shell_chrome.js; shell chrome supplies the surrounding Projects state.

(function initProjectEntities(global) {
  if (typeof document === 'undefined') return;
  const entityRowApi = global.DarklabAtlasEntityRow || {};

  function _entityItems(summary) {
    return summary && Array.isArray(summary.entities) ? summary.entities : [];
  }

  function _entityTabs() {
    const atlasTabs = global.DarklabAtlasTabs && Array.isArray(global.DarklabAtlasTabs.tabs)
      ? global.DarklabAtlasTabs.tabs
      : [
          { id: 'ip', label: 'Hosts/IPs', type: 'ip' },
          { id: 'domain', label: 'Domains', type: 'domain' },
          { id: 'hash', label: 'Hashes', type: 'hash' },
          { id: 'cve', label: 'CVEs', type: 'cve' },
          { id: 'url', label: 'URLs', type: 'url' },
        ];
    return atlasTabs.filter(tab => tab && tab.id !== 'findings' && tab.type);
  }

  function _entityTypeLabel(type) {
    if (global.DarklabAtlasTabs && typeof global.DarklabAtlasTabs.labelForType === 'function') {
      return global.DarklabAtlasTabs.labelForType(type);
    }
    const fallback = _entityTabs().find(tab => tab.type === String(type || ''));
    return fallback ? fallback.label : String(type || 'Entity');
  }

  function _entityIntelProviders(entity) {
    const raw = entity && entity.intel_providers;
    if (Array.isArray(raw)) {
      return raw.map(provider => String(provider || '').trim()).filter(Boolean);
    }
    return String(raw || '').split(',').map(provider => provider.trim()).filter(Boolean);
  }

  function _entityIntelSummary(entity, formatDate) {
    const providers = _entityIntelProviders(entity);
    const count = Number(entity && entity.intel_provider_count || providers.length || 0);
    if (count <= 0) return '';
    const providerText = providers.length
      ? providers.slice(0, 3).join(', ') + (providers.length > 3 ? ` +${providers.length - 3}` : '')
      : `${count} provider${count === 1 ? '' : 's'}`;
    const refreshed = entity && entity.intel_last_refreshed
      ? ` · refreshed ${formatDate(entity.intel_last_refreshed)}`
      : '';
    return `intel: ${providerText}${refreshed}`;
  }

  function _entityCounts(summary) {
    const counts = {};
    _entityTabs().forEach((tab) => { counts[tab.type] = 0; });
    _entityItems(summary).forEach((entity) => {
      const type = String(entity && entity.type || '');
      counts[type] = Number(counts[type] || 0) + 1;
    });
    return counts;
  }

  function createProjectEntitiesController(context) {
    const ctx = context || {};
    const pages = new Map();
    const pageLimit = 50;

    function activeTab() {
      return String(ctx.getActiveTab?.() || 'ip');
    }

    function pageKey(projectId) {
      return `${String(projectId || '')}:${activeTab()}`;
    }

    function page(projectId) {
      const key = pageKey(projectId);
      if (!pages.has(key)) pages.set(key, {
        entities: [],
        total: 0,
        countsByType: {},
        limit: pageLimit,
        offset: 0,
        loading: false,
        loaded: false,
        error: '',
      });
      return pages.get(key);
    }

    function setPageOffset(projectId, offset = 0) {
      const state = page(projectId);
      state.offset = Math.max(0, Number(offset || 0));
      state.limit = pageLimit;
      state.loading = true;
      state.loaded = false;
    }

    function resetPages() {
      pages.clear();
    }

    function linkedIds(projectId) {
      const normalized = String(projectId || '');
      const summary = ctx.getSummary?.(normalized);
      return new Set(
        (Array.isArray(summary?.links) ? summary.links : [])
          .filter(link => String(link && link.entity_type || '') === 'atlas_entity')
          .map(link => String(link && link.entity_id || ''))
          .filter(Boolean),
      );
    }

    function invalidate(projectId = '') {
      const normalized = String(projectId || '');
      if (!normalized) {
        pages.clear();
        return;
      }
      [...pages.keys()].forEach((key) => {
        if (key.startsWith(`${normalized}:`)) pages.delete(key);
      });
    }

    function selectedIds() {
      return ctx.getSelectedIds?.() || new Set();
    }

    function pickerState() {
      return ctx.getPicker?.() || null;
    }

    function setPickerState(nextState) {
      ctx.setPicker?.(nextState || null);
    }

    function selectMode() {
      return !!ctx.getSelectMode?.();
    }

    function items(summary) {
      const projectId = String(summary?.project?.id || ctx.getSelectedProjectId?.() || '');
      return page(projectId).entities || _entityItems(summary);
    }

    function tabs() {
      return _entityTabs();
    }

    function typeLabel(type) {
      return _entityTypeLabel(type);
    }

    function intelSummary(entity) {
      return _entityIntelSummary(entity, ctx.formatDate || (value => String(value || '')));
    }

    function counts(summary) {
      const projectId = String(summary?.project?.id || ctx.getSelectedProjectId?.() || '');
      const loadedCounts = page(projectId).countsByType;
      if (loadedCounts && Object.keys(loadedCounts).length) return loadedCounts;
      return summary && summary.entity_counts && typeof summary.entity_counts === 'object'
        ? summary.entity_counts
        : _entityCounts(summary);
    }

    function activeType() {
      const currentTabs = tabs();
      const current = currentTabs.find(tab => tab.id === activeTab()) || currentTabs[0] || { type: '' };
      return current.type || '';
    }

    function itemsForActiveTab(summary) {
      const projectId = String(summary?.project?.id || ctx.getSelectedProjectId?.() || '');
      return page(projectId).entities || [];
    }

    function pagedItemsForActiveTab(projectId) {
      return page(projectId).entities || [];
    }

    async function load(projectId, options = {}) {
      const normalizedProjectId = String(projectId || ctx.getSelectedProjectId?.() || '');
      if (!normalizedProjectId) return null;
      const state = page(normalizedProjectId);
      if (Object.prototype.hasOwnProperty.call(options, 'offset')) {
        state.offset = Math.max(0, Number(options.offset || 0));
      }
      state.limit = pageLimit;
      state.loading = true;
      state.error = '';
      const params = new URLSearchParams({
        limit: String(state.limit),
        offset: String(state.offset),
      });
      const type = activeType();
      if (type) params.set('type', type);
      try {
        const resp = await ctx.apiFetch(`/projects/${encodeURIComponent(normalizedProjectId)}/entities?${params.toString()}`, {
          cache: 'no-store',
        });
        if (!resp.ok) throw await ctx.projectResponseError(resp, 'Could not load project entities.');
        const data = await resp.json();
        state.entities = Array.isArray(data.entities) ? data.entities : [];
        state.total = Number(data.total || 0);
        state.limit = Number(data.limit || pageLimit);
        state.offset = Number(data.offset || 0);
        state.countsByType = data.counts_by_type && typeof data.counts_by_type === 'object' ? data.counts_by_type : {};
        const fallbackSummary = ctx.getSummary?.(normalizedProjectId);
        const fallbackEntities = _entityItems(fallbackSummary)
          .filter(entity => !type || String(entity && entity.type || '') === type);
        if (!state.entities.length && fallbackEntities.length) {
          state.entities = fallbackEntities.slice(state.offset, state.offset + state.limit);
          state.total = fallbackEntities.length;
          state.countsByType = _entityCounts(fallbackSummary);
        }
        state.loaded = true;
        return state;
      } catch (err) {
        state.error = err && err.message ? err.message : 'Could not load project entities.';
        ctx.setProjectWorkspaceMessage?.(state.error, { error: true });
        if (typeof ctx.logClientError === 'function') ctx.logClientError('failed to load project entities', err);
        return state;
      } finally {
        state.loading = false;
        if (!options.skipFinalRender) {
          ctx.renderProjectExplorer?.();
          if (ctx.mobileView?.() === 'detail') ctx.renderProjectMobileDetail?.();
        }
      }
    }

    function byId(summary, entityId) {
      const normalized = String(entityId || '').trim();
      if (!normalized) return null;
      const projectId = String(summary?.project?.id || ctx.getSelectedProjectId?.() || '');
      return (page(projectId).entities || []).find(item => String(item && item.id || '') === normalized) || null;
    }

    function chips(entity) {
      const chipItems = ctx.entityMetadataChips?.(entity) || [];
      const intelCount = Number(entity && entity.intel_provider_count || 0);
      if (intelCount > 0) {
        const providers = _entityIntelProviders(entity);
        if (providers.length) {
          providers.slice(0, 3).forEach(provider => chipItems.push({ label: provider, kind: 'label' }));
          if (providers.length > 3) chipItems.push({ label: `+${providers.length - 3} providers`, kind: 'label' });
        } else {
          chipItems.push({ label: `intel: ${intelCount} provider${intelCount === 1 ? '' : 's'}`, kind: 'label' });
        }
      }
      const runCount = Number(entity && entity.run_count || 0);
      if (runCount > 0) {
        chipItems.push({ label: `${runCount} run${runCount === 1 ? '' : 's'}`, kind: 'note' });
      }
      return chipItems;
    }

    function rowAccessory(projectId, entity) {
      const entityId = String(entity && entity.id || '');
      const value = String(entity && (entity.canonical_value || entity.value) || '');
      const type = String(entity && entity.type || '');
      const wrap = document.createElement('div');
      wrap.className = 'project-entity-row-actions';
      const open = ctx.makeProjectButton('Open in Atlas', 'open-project-entity', projectId);
      open.dataset.entityId = entityId;
      open.dataset.entityValue = value;
      open.dataset.entityType = type;
      const unlink = ctx.makeProjectButton('Unlink', 'unlink-project-entity', projectId, 'destructive');
      unlink.dataset.entityId = entityId;
      unlink.dataset.entityValue = value;
      wrap.append(open, unlink);
      return wrap;
    }

    function renderTypeTabs(projectId, summary) {
      const wrap = document.createElement('div');
      wrap.className = 'project-entity-type-tabs tab-strip';
      wrap.setAttribute('role', 'tablist');
      wrap.setAttribute('aria-label', 'Project entity types');
      const entityCounts = counts(summary);
      tabs().forEach((tab) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        const active = activeTab() === tab.id;
        btn.className = 'tab-strip-item project-entity-type-tab' + (active ? ' is-active' : '');
        btn.dataset.projectEntityTab = tab.id;
        btn.dataset.projectId = projectId;
        btn.setAttribute('role', 'tab');
        btn.setAttribute('aria-selected', active ? 'true' : 'false');
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        const label = document.createElement('span');
        label.className = 'project-entity-type-tab-label';
        label.textContent = tab.label;
        const count = document.createElement('span');
        count.className = 'project-entity-type-tab-count';
        count.textContent = Number(entityCounts[tab.type] || 0).toLocaleString();
        btn.append(label, count);
        ctx.bindProjectRuntimePressable?.(btn);
        wrap.appendChild(btn);
      });
      return wrap;
    }

    function renderToolbar(projectId, visibleEntities) {
      const toolbar = document.createElement('div');
      toolbar.className = 'project-entity-toolbar';
      const actions = document.createElement('div');
      actions.className = 'project-entity-toolbar-actions';
      actions.append(
        ctx.makeProjectButton('Add entity', 'open-entity-picker', projectId, 'primary'),
        ctx.makeProjectButton('Export CSV', 'export-project-entities-csv', projectId),
        ctx.makeProjectButton('Export JSONL', 'export-project-entities-jsonl', projectId),
      );
      const select = document.createElement('div');
      select.className = 'project-entity-select-actions';
      const toggle = ctx.makeProjectButton(selectMode() ? 'Done' : 'Select', 'toggle-project-entity-select', projectId);
      select.appendChild(toggle);
      if (selectMode()) {
        const currentSelected = selectedIds();
        const count = document.createElement('span');
        count.className = 'project-entity-selection-count';
        count.setAttribute('aria-live', 'polite');
        count.textContent = `${currentSelected.size} selected`;
        const selectAll = ctx.makeProjectButton('Select all', 'select-all-project-entities', projectId);
        selectAll.disabled = !visibleEntities.length;
        const clear = ctx.makeProjectButton('Clear', 'clear-project-entities', projectId);
        clear.disabled = !currentSelected.size;
        const unlink = ctx.makeProjectButton('Unlink', 'bulk-unlink-project-entities', projectId, 'destructive');
        unlink.disabled = !currentSelected.size;
        select.append(count, selectAll, clear, unlink);
      }
      toolbar.append(actions, select);
      return toolbar;
    }

    function renderPagination(projectId, total, position = 'bottom') {
      const state = page(projectId);
      const offset = Number(state.offset || 0);
      const limit = Math.max(1, Number(state.limit || pageLimit));
      const loading = !!state.loading;
      if (total <= limit && offset === 0) return null;
      const wrap = document.createElement('div');
      wrap.className = 'project-workspace-pagination project-entity-pagination';
      wrap.dataset.projectEntitiesPagerPosition = position;
      const start = total ? offset + 1 : 0;
      const end = Math.min(total, offset + limit);
      const summary = document.createElement('div');
      summary.className = 'project-workspace-pagination-summary';
      summary.textContent = `${start.toLocaleString()}-${end.toLocaleString()} of ${total.toLocaleString()} entities`;
      const controls = document.createElement('div');
      controls.className = 'project-workspace-pagination-controls';
      const prev = ctx.makeProjectButton('Previous', 'noop', projectId);
      prev.dataset.projectEntitiesPage = 'prev';
      prev.dataset.projectEntitiesPagerPosition = position;
      prev.disabled = loading || offset <= 0;
      const status = document.createElement('span');
      status.className = 'project-workspace-pagination-status';
      status.textContent = loading ? 'Loading...' : `Page ${Math.floor(offset / limit) + 1}`;
      const next = ctx.makeProjectButton('Next', 'noop', projectId);
      next.dataset.projectEntitiesPage = 'next';
      next.dataset.projectEntitiesPagerPosition = position;
      next.disabled = loading || offset + limit >= total;
      controls.append(prev, status, next);
      wrap.append(summary, controls);
      return wrap;
    }

    function openInAtlas(projectId, summary, entity) {
      const openAtlas = ctx.openAtlas || global.openAtlas;
      if (typeof openAtlas !== 'function' || !entity) return;
      const project = summary && summary.project && typeof summary.project === 'object' ? summary.project : null;
      const tab = tabs().find(item => item.type === String(entity.type || ''));
      ctx.closeProjectWorkspace?.({ refocus: false });
      void openAtlas({
        source: 'project-workspace',
        projectId,
        projectName: project ? ctx.projectDisplayName(project) : '',
        tab: tab ? tab.id : String(entity.type || ''),
        entityValue: String(entity.canonical_value || entity.value || ''),
        forceView: 'detail',
      });
    }

    function closePicker() {
      document.getElementById('project-entity-picker-overlay')?.remove();
      setPickerState(null);
    }

    function pickerLinkedIds(projectId) {
      const summary = ctx.getSummary?.(String(projectId || ''));
      return new Set(items(summary).map(entity => String(entity && entity.id || '')).filter(Boolean));
    }

    async function loadPickerRows() {
      const state = pickerState();
      if (!state) return;
      state.loading = true;
      renderPicker();
      const params = new URLSearchParams({ limit: '100', orphan_filter: 'all' });
      if (state.type) params.set('type', state.type);
      if (state.query) params.set('q', state.query);
      try {
        const resp = await ctx.apiFetch(`/atlas/entities?${params.toString()}`, { cache: 'no-store' });
        if (!resp.ok) throw await ctx.projectResponseError(resp, 'Could not load Atlas entities.');
        const data = await resp.json();
        const linked = pickerLinkedIds(state.projectId);
        state.rows = (Array.isArray(data.entities) ? data.entities : [])
          .filter(entity => !linked.has(String(entity && entity.id || '')));
      } catch (err) {
        state.rows = [];
        ctx.setProjectWorkspaceMessage(err && err.message ? err.message : 'Could not load Atlas entities.', { error: true });
        if (typeof global.logClientError === 'function') global.logClientError('failed to load project entity picker', err);
      } finally {
        state.loading = false;
        renderPicker();
      }
    }

    function openPicker(projectId) {
      const currentTabs = tabs();
      const active = currentTabs.find(tab => tab.id === activeTab()) || currentTabs[0] || { type: '' };
      setPickerState({
        projectId: String(projectId || ''),
        query: '',
        type: active.type || '',
        rows: [],
        selected: new Set(),
        loading: false,
      });
      renderPicker();
      loadPickerRows().catch(() => {});
    }

    function renderPicker() {
      const state = pickerState();
      if (!state) return;
      let overlay = document.getElementById('project-entity-picker-overlay');
      if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'project-entity-picker-overlay';
        overlay.className = 'project-entity-picker-overlay';
        document.body.appendChild(overlay);
      }
      overlay.replaceChildren();
      const modal = document.createElement('div');
      modal.className = 'project-entity-picker-modal';
      modal.setAttribute('role', 'dialog');
      modal.setAttribute('aria-modal', 'true');
      modal.setAttribute('aria-label', 'Add Atlas entities to project');
      const header = document.createElement('div');
      header.className = 'project-entity-picker-header';
      const title = document.createElement('h3');
      title.textContent = 'Add Atlas entities';
      const close = document.createElement('button');
      close.type = 'button';
      close.className = 'btn btn-ghost btn-icon';
      close.dataset.projectEntityPickerClose = '1';
      close.setAttribute('aria-label', 'Close');
      close.textContent = '×';
      header.append(title, close);
      const filters = document.createElement('div');
      filters.className = 'project-entity-picker-filters';
      const search = document.createElement('input');
      search.type = 'search';
      search.className = 'form-control';
      search.placeholder = 'Search Atlas entities';
      search.value = state.query;
      search.dataset.projectEntityPickerSearch = '1';
      const type = document.createElement('select');
      type.className = 'form-select';
      type.dataset.projectEntityPickerType = '1';
      const all = document.createElement('option');
      all.value = '';
      all.textContent = 'All entity types';
      type.appendChild(all);
      tabs().forEach((tab) => {
        const option = document.createElement('option');
        option.value = tab.type;
        option.textContent = tab.label;
        option.selected = tab.type === state.type;
        type.appendChild(option);
      });
      filters.append(search, type);
      const body = document.createElement('div');
      body.className = 'project-entity-picker-body';
      if (state.loading) {
        body.appendChild(ctx.emptyProjectPanel('Loading Atlas entities...'));
      } else if (!state.rows.length) {
        body.appendChild(ctx.emptyProjectPanel('No unlinked Atlas entities match this search.'));
      } else {
        state.rows.forEach((entity) => {
          const entityId = String(entity.id || '');
          const value = String(entity.canonical_value || entity.value || '');
          const label = document.createElement('label');
          label.className = 'project-entity-picker-row panel-row';
          const checkbox = document.createElement('input');
          checkbox.type = 'checkbox';
          checkbox.dataset.projectEntityPickerSelect = entityId;
          checkbox.checked = state.selected.has(entityId);
          const textWrap = document.createElement('span');
          textWrap.className = 'project-entity-picker-row-text';
          const name = document.createElement('strong');
          name.textContent = value || entityId;
          const meta = document.createElement('span');
          meta.textContent = typeLabel(entity.type);
          textWrap.append(name, meta);
          label.append(checkbox, textWrap);
          body.appendChild(label);
        });
      }
      const footer = document.createElement('div');
      footer.className = 'project-entity-picker-footer';
      const count = document.createElement('span');
      count.className = 'project-entity-picker-count';
      count.textContent = `${state.selected.size} selected`;
      const cancel = ctx.makeProjectButton('Cancel', 'entity-picker-cancel', state.projectId);
      const add = ctx.makeProjectButton('Add selected', 'entity-picker-add', state.projectId, 'primary');
      add.disabled = state.selected.size === 0;
      footer.append(count, cancel, add);
      modal.append(header, filters, body, footer);
      overlay.appendChild(modal);
      if (document.activeElement === document.body || !modal.contains(document.activeElement)) search.focus();
    }

    function renderEntities(container, projectId, summary) {
      const state = page(projectId);
      const visibleEntities = pagedItemsForActiveTab(projectId, summary);
      const totalEntities = Number(summary?.counts?.entities || 0);
      const activeTotal = Number(state.total || counts(summary)[activeType()] || 0);
      const currentSelected = selectedIds();
      currentSelected.forEach((entityId) => {
        if (!visibleEntities.some(entity => String(entity && entity.id || '') === entityId)) {
          currentSelected.delete(entityId);
        }
      });
      container.appendChild(renderTypeTabs(projectId, summary));
      container.appendChild(renderToolbar(projectId, visibleEntities));
      if (!totalEntities) {
        container.appendChild(ctx.emptyProjectPanel('No Atlas entities are linked to this project yet.'));
        return;
      }
      if (!state.loaded && !state.loading) {
        load(projectId).catch(() => {});
      }
      if (state.loading && !visibleEntities.length) {
        container.appendChild(ctx.emptyProjectPanel('Loading project entities...'));
        return;
      }
      if (state.error && !visibleEntities.length) {
        container.appendChild(ctx.emptyProjectPanel(state.error));
        return;
      }
      if (!activeTotal) {
        const activeType = tabs().find(tab => tab.id === activeTab())?.type || '';
        container.appendChild(ctx.emptyProjectPanel(`No ${typeLabel(activeType).toLowerCase()} linked yet.`));
        return;
      }
      const topPager = renderPagination(projectId, activeTotal, 'top');
      if (topPager) container.appendChild(topPager);
      visibleEntities.forEach((entity) => {
        const entityId = String(entity.id || '');
        const value = String(entity.canonical_value || entity.value || '');
        const hitCount = Number(entity.occurrence_count || entity.seen_count || 0);
        const metaParts = [
          typeLabel(entity.type),
          `${hitCount.toLocaleString()} hit${hitCount === 1 ? '' : 's'}`,
          entity.last_seen ? `last seen ${ctx.formatDate(entity.last_seen)}` : '',
        ].filter(Boolean);
        const detailParts = [
          entity.source_run_id ? `source run ${ctx.shortProjectRunId(entity.source_run_id)}` : '',
          intelSummary(entity),
        ].filter(Boolean);
        const checkbox = selectMode() ? document.createElement('input') : null;
        if (checkbox) {
          checkbox.type = 'checkbox';
          checkbox.className = 'project-entity-select-checkbox';
          checkbox.checked = currentSelected.has(entityId);
          checkbox.dataset.projectEntitySelect = entityId;
          checkbox.dataset.projectId = projectId;
          checkbox.setAttribute('aria-label', `Select ${value || entityId}`);
        }
        const row = entityRowApi.renderProjectEntityRow({
          entity,
          projectId,
          title: value || entityId,
          meta: metaParts.join(' · '),
          detail: detailParts.join(' · '),
          chips: chips(entity),
          accessory: rowAccessory(projectId, entity),
          checkbox,
          selected: currentSelected.has(entityId),
          chipClass: ctx.entityMetadataChipClass,
          bindPressable: ctx.bindProjectRuntimePressable,
          action: {
            action: selectMode() ? 'toggle-project-entity-row' : 'open-project-entity',
            dataset: { projectId, entityId, entityValue: value, entityType: String(entity.type || '') },
          },
        });
        container.appendChild(row);
      });
      const bottomPager = renderPagination(projectId, activeTotal, 'bottom');
      if (bottomPager) container.appendChild(bottomPager);
    }

    function renderMobileEntitiesTab(projectId, summary) {
      const fragment = document.createDocumentFragment();
      const toolbar = document.createElement('div');
      toolbar.className = 'project-mobile-tab-toolbar';
      toolbar.append(
        ctx.makeProjectButton('Add entity', 'open-entity-picker', projectId, 'primary'),
        ctx.makeProjectButton('Export CSV', 'export-project-entities-csv', projectId),
      );
      fragment.appendChild(toolbar);
      fragment.appendChild(renderTypeTabs(projectId, summary));
      const state = page(projectId);
      const visibleEntities = pagedItemsForActiveTab(projectId, summary);
      const totalEntities = Number(summary?.counts?.entities || 0);
      const activeTotal = Number(state.total || counts(summary)[activeType()] || 0);
      if (!totalEntities) {
        fragment.appendChild(ctx.projectMobileEmptyPanel('No Atlas entities are linked to this project yet.', [
          ctx.makeProjectButton('Add entity', 'open-entity-picker', projectId, 'primary'),
        ]));
        return fragment;
      }
      if (!state.loaded && !state.loading) {
        load(projectId).catch(() => {});
      }
      if (state.loading && !visibleEntities.length) {
        fragment.appendChild(ctx.emptyProjectPanel('Loading project entities...'));
        return fragment;
      }
      if (state.error && !visibleEntities.length) {
        fragment.appendChild(ctx.emptyProjectPanel(state.error));
        return fragment;
      }
      if (!activeTotal) {
        fragment.appendChild(ctx.emptyProjectPanel('No entities match this type.'));
        return fragment;
      }
      const topPager = renderPagination(projectId, activeTotal, 'top');
      if (topPager) fragment.appendChild(topPager);
      const list = document.createElement('div');
      list.className = 'project-mobile-content-list';
      visibleEntities.forEach((entity) => {
        const entityId = String(entity.id || '');
        const value = String(entity.canonical_value || entity.value || '');
        const hitCount = Number(entity.occurrence_count || entity.seen_count || 0);
        const actions = [
          { label: 'Open in Atlas', action: 'open-project-entity', dataset: { entityId, entityValue: value, entityType: entity.type } },
          { label: 'Unlink', action: 'unlink-project-entity', tone: 'danger', dataset: { entityId, entityValue: value } },
        ];
        list.appendChild(ctx.projectMobileContentRow({
          title: value || entityId,
          meta: typeLabel(entity.type),
          detail: [
            `${hitCount.toLocaleString()} hit${hitCount === 1 ? '' : 's'}`,
            intelSummary(entity),
          ].filter(Boolean),
          chips: chips(entity),
          action: {
            action: 'open-project-entity',
            dataset: { projectId, entityId, entityValue: value, entityType: String(entity.type || '') },
          },
          accessory: ctx.projectMobileActionMenu(projectId, `Entity actions for ${value || entityId}`, actions),
        }));
      });
      fragment.appendChild(list);
      const bottomPager = renderPagination(projectId, activeTotal, 'bottom');
      if (bottomPager) fragment.appendChild(bottomPager);
      return fragment;
    }

    function handlePickerInput(event) {
      const search = event.target.closest?.('[data-project-entity-picker-search]');
      const state = pickerState();
      if (!search || !state) return false;
      state.query = String(search.value || '');
      window.clearTimeout(state.searchTimer);
      state.searchTimer = window.setTimeout(() => {
        loadPickerRows().catch(() => {});
      }, 200);
      return true;
    }

    function handlePickerChange(event) {
      const state = pickerState();
      const pickerType = event.target.closest?.('[data-project-entity-picker-type]');
      if (pickerType && state) {
        state.type = String(pickerType.value || '');
        state.selected.clear();
        loadPickerRows().catch(() => {});
        return true;
      }
      const pickerSelect = event.target.closest?.('[data-project-entity-picker-select]');
      if (pickerSelect && state) {
        const entityId = String(pickerSelect.dataset.projectEntityPickerSelect || '');
        if (entityId) {
          if (pickerSelect.checked) state.selected.add(entityId);
          else state.selected.delete(entityId);
        }
        renderPicker();
        return true;
      }
      return false;
    }

    async function handlePickerClick(event) {
      const state = pickerState();
      if (!state) return false;
      const overlay = document.getElementById('project-entity-picker-overlay');
      if (!overlay || !overlay.contains(event.target)) return false;
      const close = event.target.closest?.('[data-project-entity-picker-close]');
      const cancel = event.target.closest?.('[data-project-action="entity-picker-cancel"]');
      if (close || cancel) {
        event.preventDefault();
        closePicker();
        return true;
      }
      const add = event.target.closest?.('[data-project-action="entity-picker-add"]');
      if (add) {
        event.preventDefault();
        const entityIds = [...state.selected];
        if (!entityIds.length) return true;
        try {
          await ctx.projectWorkspaceRequest(`/projects/${encodeURIComponent(state.projectId)}/links`, {
            method: 'POST',
            body: JSON.stringify({ entity_type: 'atlas_entity', entity_ids: entityIds }),
          });
          closePicker();
          ctx.setWorkspaceTab?.('entities');
          await ctx.refreshProjectWorkspace();
          ctx.setProjectWorkspaceMessage(`${entityIds.length} ${entityIds.length === 1 ? 'entity' : 'entities'} added to project.`);
        } catch (err) {
          ctx.setProjectWorkspaceMessage(err && err.message ? err.message : 'Could not add Atlas entities.', { error: true });
        }
        return true;
      }
      return false;
    }

    function setActiveTab(tabId) {
      ctx.setActiveTab?.(String(tabId || 'ip'));
      resetPages();
    }

    function toggleSelected(entityId, checked = null) {
      const normalized = String(entityId || '');
      if (!normalized) return;
      const currentSelected = selectedIds();
      if (checked === true) currentSelected.add(normalized);
      else if (checked === false) currentSelected.delete(normalized);
      else if (currentSelected.has(normalized)) currentSelected.delete(normalized);
      else currentSelected.add(normalized);
    }

    function selectAllForActiveTab(summary) {
      pagedItemsForActiveTab(ctx.getSelectedProjectId?.() || '', summary).forEach((entity) => {
        if (entity && entity.id) selectedIds().add(String(entity.id));
      });
    }

    function clearSelection() {
      selectedIds().clear();
    }

    function setSelectMode(nextMode) {
      ctx.setSelectMode?.(!!nextMode);
    }

    function exportEntities(projectId, format) {
      const normalizedFormat = String(format || '') === 'jsonl' ? 'jsonl' : 'csv';
      const params = new URLSearchParams({ format: normalizedFormat, project_id: projectId, orphan_filter: 'all' });
      const tab = tabs().find(item => item.id === activeTab());
      if (tab && tab.type) params.set('type', tab.type);
      return ctx.projectWorkspaceRequest(`/atlas/entities/export?${params.toString()}`, { cache: 'no-store' })
        .then(resp => resp.blob())
        .then((blob) => {
          const filename = `darklab-project-entities-${projectId}.${normalizedFormat}`;
          ctx.downloadBlobAsAttachment(blob, filename, `Project ${normalizedFormat.toUpperCase()} export started.`);
        });
    }

    return {
      items,
      tabs,
      typeLabel,
      intelSummary,
      counts,
      itemsForActiveTab,
      pagedItemsForActiveTab,
      byId,
      load,
      invalidate,
      chips,
      renderTypeTabs,
      renderEntities,
      renderMobileEntitiesTab,
      openInAtlas,
      closePicker,
      loadPickerRows,
      openPicker,
      renderPicker,
      handlePickerInput,
      handlePickerChange,
      handlePickerClick,
      setActiveTab,
      page,
      setPageOffset,
      toggleSelected,
      selectAllForActiveTab,
      clearSelection,
      setSelectMode,
      exportEntities,
    };
  }

  global.DarklabProjectEntities = {
    createProjectEntitiesController,
  };
})(globalThis);
