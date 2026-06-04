// Project workspace in-browser state.
// Loaded before shell_chrome.js so chrome wiring can avoid owning modal state directly.

(function projectWorkspaceStateModule(global) {
  'use strict';

  const FINDING_VIEW_MODE_KEY = 'darklab_project_finding_view_mode';
  const FINDING_VIEW_MODES = new Set(['list', 'board']);

  function normalizedFindingViewMode(value) {
    const normalized = String(value || 'list');
    return FINDING_VIEW_MODES.has(normalized) ? normalized : 'list';
  }

  function sessionStore() {
    try {
      return global.sessionStorage || global.window?.sessionStorage || null;
    } catch (_) {
      return null;
    }
  }

  function readFindingViewMode() {
    try {
      return normalizedFindingViewMode(sessionStore()?.getItem(FINDING_VIEW_MODE_KEY));
    } catch (_) {
      return 'list';
    }
  }

  function writeFindingViewMode(value) {
    try {
      sessionStore()?.setItem(FINDING_VIEW_MODE_KEY, normalizedFindingViewMode(value));
    } catch (_) {
      // Session persistence is a convenience; the in-memory state remains authoritative.
    }
  }

  function createProjectWorkspaceState() {
    let rows = [];
    let summaries = new Map();
    let pagination = { limit: 50, offset: 0, total: 0 };
    let loading = false;
    let selectedId = '';
    let tab = 'details';
    let editingTargetId = '';
    let lastTargetType = 'domain';
    const collapsedFindingGroups = new Set();
    const collapsedArtifactGroups = new Set();
    let entityTab = 'ip';
    let entitySelectMode = false;
    const selectedEntityIds = new Set();
    let findingSelectMode = false;
    const selectedFindingIds = new Set();
    let findingViewMode = readFindingViewMode();
    let entityPicker = null;

    function setPagination(nextPagination = {}) {
      pagination = {
        limit: Number(nextPagination && nextPagination.limit || 50),
        offset: Number(nextPagination && nextPagination.offset || 0),
        total: Number(nextPagination && nextPagination.total || 0),
      };
    }

    function setPaginationOffset(offset) {
      pagination = {
        ...pagination,
        offset: Math.max(0, Number(offset || 0)),
      };
    }

    function setLastTargetType(targetType) {
      lastTargetType = String(targetType || lastTargetType || 'domain');
    }

    function toggleArtifactGroup(projectId, runId) {
      const key = `${String(projectId || '')}\x1f${String(runId || '')}`;
      if (collapsedArtifactGroups.has(key)) collapsedArtifactGroups.delete(key);
      else collapsedArtifactGroups.add(key);
    }

    function toggleFindingGroup(projectId, runLabel) {
      const key = `${String(projectId || '')}\x1f${String(runLabel || '')}`;
      if (collapsedFindingGroups.has(key)) collapsedFindingGroups.delete(key);
      else collapsedFindingGroups.add(key);
    }

    function clearEditingTargetIf(targetId) {
      if (editingTargetId === String(targetId || '')) editingTargetId = '';
    }

    return {
      rows: () => rows,
      setRows: (nextRows) => { rows = Array.isArray(nextRows) ? nextRows : []; },
      summaries: () => summaries,
      summary: (projectId) => summaries.get(String(projectId || '')) || null,
      setSummary: (projectId, summary) => { summaries.set(String(projectId || ''), summary); },
      setSummaries: (nextSummaries) => { summaries = nextSummaries instanceof Map ? nextSummaries : new Map(); },
      pagination: () => pagination,
      setPagination,
      setPaginationOffset,
      loading: () => loading,
      setLoading: (nextLoading) => { loading = !!nextLoading; },
      selectedId: () => selectedId,
      setSelectedId: (projectId) => { selectedId = String(projectId || ''); },
      tab: () => tab,
      setTab: (nextTab) => { tab = String(nextTab || 'details'); },
      editingTargetId: () => editingTargetId,
      setEditingTargetId: (targetId) => { editingTargetId = String(targetId || ''); },
      clearEditingTargetIf,
      lastTargetType: () => lastTargetType,
      setLastTargetType,
      collapsedFindingGroups: () => collapsedFindingGroups,
      collapsedArtifactGroups: () => collapsedArtifactGroups,
      toggleArtifactGroup,
      toggleFindingGroup,
      entityTab: () => entityTab,
      setEntityTab: (nextTab) => { entityTab = String(nextTab || 'ip'); },
      entitySelectMode: () => entitySelectMode,
      setEntitySelectMode: (enabled) => { entitySelectMode = !!enabled; },
      selectedEntityIds: () => selectedEntityIds,
      findingSelectMode: () => findingSelectMode,
      setFindingSelectMode: (enabled) => { findingSelectMode = !!enabled; },
      selectedFindingIds: () => selectedFindingIds,
      findingViewMode: () => findingViewMode,
      setFindingViewMode: (mode) => {
        findingViewMode = normalizedFindingViewMode(mode);
        writeFindingViewMode(findingViewMode);
      },
      entityPicker: () => entityPicker,
      setEntityPicker: (picker) => { entityPicker = picker; },
    };
  }

  global.DarklabProjectWorkspaceState = {
    createProjectWorkspaceState,
  };
})(globalThis);
