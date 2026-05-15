// Session Entity Atlas overlay controller.

(function initAtlasOverlay(global) {
  const tabsApi = global.DarklabAtlasTabs || {};
  const detailApi = global.DarklabAtlasDetail || {};
  const metadataApi = global.DarklabEntityMetadata || {};

  const overlay = document.getElementById('atlas-overlay');
  const surface = document.getElementById('atlas-surface');
  const closeBtn = document.querySelector('.atlas-close');
  const tabsHost = document.getElementById('atlas-tabs');
  const subtitle = document.getElementById('atlas-subtitle');
  const searchInput = document.getElementById('atlas-search');
  const refreshBtn = document.getElementById('atlas-refresh-btn');
  const listHost = document.getElementById('atlas-list');
  const detailHost = document.getElementById('atlas-detail');
  const pagination = document.getElementById('atlas-pagination');
  const paginationSummary = document.getElementById('atlas-pagination-summary');
  const prevBtn = document.getElementById('atlas-prev-btn');
  const nextBtn = document.getElementById('atlas-next-btn');

  const state = {
    activeTab: 'ip',
    summary: null,
    entities: [],
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
  };

  function api() {
    if (typeof global.apiFetch === 'function') return global.apiFetch;
    if (typeof apiFetch === 'function') return apiFetch;
    return fetch;
  }

  function showToastSafe(message, tone = 'info') {
    if (typeof global.showToast === 'function') global.showToast(message, tone);
  }

  function text(value, fallback = '') {
    return detailApi.text ? detailApi.text(value, fallback) : (String(value ?? '').trim() || fallback);
  }

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
    return tabsApi.tabById ? tabsApi.tabById(state.activeTab) : { id: 'ip', type: 'ip', label: 'Hosts/IPs' };
  }

  function renderTabs() {
    if (!tabsHost) return;
    tabsHost.replaceChildren();
    (tabsApi.tabs || []).forEach(tab => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'toggle-btn atlas-tab';
      button.dataset.atlasTab = tab.id;
      button.setAttribute('role', 'tab');
      button.setAttribute('aria-selected', tab.id === state.activeTab ? 'true' : 'false');
      button.classList.toggle('active', tab.id === state.activeTab);
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
    subtitle.textContent = state.projectId && state.projectName ? `${base} · ${state.projectName}` : base;
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
      listHost.appendChild(rowMessage('No findings queued'));
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
      row.classList.toggle('is-selected', entity.id === state.selectedId);
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
      meta.textContent = `${occurrenceCount.toLocaleString()} hits · ${runCount.toLocaleString()} runs`;
      main.append(value, meta);

      const badges = document.createElement('span');
      badges.className = 'atlas-entity-badges';
      if (entity.project_link_count) badges.appendChild(badge(`${entity.project_link_count} projects`, 'green'));
      const labels = Array.isArray(entity.labels) ? entity.labels : [];
      labels.slice(0, 2).forEach(label => badges.appendChild(badge(text(label.label || label), 'muted')));

      row.append(main, badges);
      row.addEventListener('click', () => selectEntity(entity.id));
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
    const tab = currentTab();
    const showPager = tab.id !== 'findings' && (state.total > state.limit || state.offset > 0);
    pagination.classList.toggle('u-hidden', !showPager);
    if (!showPager) return;
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
    });
  }

  function render() {
    renderSubtitle();
    renderTabs();
    renderList();
    renderPagination();
    renderDetail();
  }

  async function refreshAtlas({ resetOffset = false } = {}) {
    if (!overlay || !isOpen()) return;
    if (resetOffset) state.offset = 0;
    state.loading = true;
    render();
    try {
      const summaryResp = await api()('/atlas', { cache: 'no-store' });
      if (!summaryResp.ok) throw new Error(`HTTP ${summaryResp.status}`);
      state.summary = await summaryResp.json();
      const tab = currentTab();
      if (tab.id === 'findings') {
        state.entities = [];
        state.total = 0;
      } else {
        const params = new URLSearchParams({
          type: tab.type,
          limit: String(state.limit),
          offset: String(state.offset),
        });
        if (state.query) params.set('q', state.query);
        if (state.projectId) params.set('project_id', state.projectId);
        const listResp = await api()(`/atlas/entities?${params.toString()}`, { cache: 'no-store' });
        if (!listResp.ok) throw new Error(`HTTP ${listResp.status}`);
        const data = await listResp.json();
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
      }
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
      state.loading = false;
      render();
    }
  }

  async function selectEntity(entityId) {
    state.selectedId = String(entityId || '');
    renderList();
    await loadDetail(state.selectedId);
  }

  async function loadDetail(entityId, { renderLoading = true } = {}) {
    if (!entityId) return;
    state.detailLoading = !!renderLoading;
    if (renderLoading) renderDetail();
    try {
      const resp = await api()(`/atlas/entities/${encodeURIComponent(entityId)}`, { cache: 'no-store' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      state.detail = await resp.json();
    } catch (err) {
      state.detail = null;
      if (typeof global.logClientError === 'function') global.logClientError('failed to load atlas entity', err);
      showToastSafe('Failed to load entity', 'error');
    } finally {
      state.detailLoading = false;
      render();
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

  function openSourceRun(run) {
    const runId = String(run && (run.id || run.run_id) || '');
    if (!runId || typeof global.openHistoryRunDetails !== 'function') return;
    global.openHistoryRunDetails({ ...run, id: runId });
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
      clearTimeout(state.searchTimer);
      state.searchTimer = setTimeout(() => refreshAtlas({ resetOffset: true }), 180);
    });
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
