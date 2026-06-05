(function projectFindingsDataModule(global) {
  'use strict';

  const BOARD_WORKFLOW_STATES = Object.freeze(['new', 'reviewed', 'false_positive', 'needs_followup']);
  const BOARD_WORKFLOW_STATE_SET = new Set(BOARD_WORKFLOW_STATES);
  const BOARD_STATE_LABELS = Object.freeze({
    new: 'New',
    reviewed: 'Reviewed',
    false_positive: 'False positive',
    needs_followup: 'Follow-up',
  });
  const BOARD_DEFAULT_STATE = 'new';
  const BOARD_IMPORTANT_STATE = 'important';
  const BOARD_IMPORTANT_COLUMN = 'reviewed';
  const BOARD_COLUMN_LIMIT = 50;

  function normalizedBoardLimit(value) {
    const limit = Math.floor(Number(value || BOARD_COLUMN_LIMIT));
    return Number.isFinite(limit) && limit > 0 ? limit : BOARD_COLUMN_LIMIT;
  }

  function boardWorkflowState(value) {
    const reviewState = typeof value === 'object' && value !== null
      ? value.review_state
      : value;
    const normalized = String(reviewState || BOARD_DEFAULT_STATE);
    if (normalized === BOARD_IMPORTANT_STATE) return BOARD_IMPORTANT_COLUMN;
    return BOARD_WORKFLOW_STATE_SET.has(normalized) ? normalized : BOARD_DEFAULT_STATE;
  }

  function boardTargetIds(finding = {}) {
    const ids = new Set();
    if (finding.target_id) ids.add(String(finding.target_id));
    if (Array.isArray(finding.target_ids)) {
      finding.target_ids.forEach((targetId) => {
        if (targetId) ids.add(String(targetId));
      });
    }
    return [...ids];
  }

  function boardLabels(finding = {}) {
    return Array.isArray(finding.labels)
      ? finding.labels.map(label => String(label || '')).filter(Boolean)
      : [];
  }

  function boardCardFromFinding(finding = {}, order = 0) {
    const source = finding && typeof finding === 'object' ? finding : {};
    const reviewState = String(source.review_state || BOARD_DEFAULT_STATE);
    const title = String(source.title || source.raw_line || '');
    const lineNumber = Number(source.line_number);
    return {
      id: String(source.id || ''),
      finding: source,
      order: Number(order || 0),
      review_state: reviewState,
      workflow_state: boardWorkflowState(reviewState),
      important: reviewState === BOARD_IMPORTANT_STATE,
      title,
      raw_line: String(source.raw_line || ''),
      severity: String(source.severity || ''),
      scope: String(source.scope || ''),
      run_id: String(source.run_id || ''),
      run_command: String(source.run_command || ''),
      line_number: Number.isInteger(lineNumber) ? lineNumber : null,
      target_id: String(source.target_id || ''),
      target_ids: boardTargetIds(source),
      labels: boardLabels(source),
      note: String(source.note || ''),
      source_run_exists: source.source_run_exists !== false,
      orphan_source: source.source_run_exists === false,
    };
  }

  function emptyBoardColumns() {
    return BOARD_WORKFLOW_STATES.map(state => ({
      state,
      label: BOARD_STATE_LABELS[state],
      cards: [],
      total: 0,
      truncated: false,
    }));
  }

  function boardColumnsFromFindings(findingsList = [], options = {}) {
    const limit = normalizedBoardLimit(options.limit);
    const rows = Array.isArray(findingsList) ? findingsList : [];
    const columns = emptyBoardColumns();
    const byState = new Map(columns.map(column => [column.state, column]));
    const counts = BOARD_WORKFLOW_STATES.reduce((acc, state) => {
      acc[state] = 0;
      return acc;
    }, {});

    rows.forEach((finding, index) => {
      const card = boardCardFromFinding(finding, index);
      const state = card.workflow_state;
      const column = byState.get(state) || byState.get(BOARD_DEFAULT_STATE);
      column.total += 1;
      counts[column.state] += 1;
      if (column.cards.length < limit) {
        column.cards.push(card);
      } else {
        column.truncated = true;
      }
    });

    return {
      columns,
      counts,
      total: rows.length,
      limit,
      truncated: columns.some(column => column.truncated),
    };
  }

  function createProjectFindingsDataController(context) {
    const ctx = context || {};
    let findings = new Map();
    let findingsPagination = new Map();
    let filteredFindings = new Map();
    let filteredFindingsPagination = new Map();
    let findingsLoadingId = '';
    let findingsLoadingPromise = null;
    let filteredFindingsLoadingKey = '';
    const pageLimit = Math.max(1, Number(ctx.pageLimit || 50));

    function normalizedProjectId(projectId = '') {
      return String(projectId || ctx.selectedProjectId?.() || '');
    }

    function items(projectId = '') {
      return findings.get(normalizedProjectId(projectId)) || [];
    }

    function page(projectId = '', summary = ctx.projectSummary?.(projectId)) {
      const normalized = normalizedProjectId(projectId);
      const filteredKey = ctx.findingFilteredKey?.(normalized, summary) || '';
      if (filteredKey && filteredFindingsPagination.has(filteredKey)) {
        return filteredFindingsPagination.get(filteredKey);
      }
      if (filteredKey) {
        return {
          limit: pageLimit,
          offset: 0,
          total: 0,
          has_more: false,
          loaded: false,
          loading: false,
          group_counts: {},
          collapsed_group_counts: {},
          group_order: [],
          collapsed_signature: collapsedGroupSignature(normalized),
        };
      }
      return findingsPagination.get(normalized) || {
        limit: pageLimit,
        offset: 0,
        total: findings.has(normalized) ? items(normalized).length : 0,
        has_more: false,
        loaded: findings.has(normalized),
        loading: false,
        group_counts: {},
        collapsed_group_counts: {},
        group_order: [],
        collapsed_signature: collapsedGroupSignature(normalized),
      };
    }

    function setPageOffset(projectId = '', summary = ctx.projectSummary?.(projectId), offset = 0) {
      const normalized = normalizedProjectId(projectId);
      if (!normalized) return;
      const filteredKey = ctx.findingFilteredKey?.(normalized, summary) || '';
      const targetMap = filteredKey ? filteredFindingsPagination : findingsPagination;
      const key = filteredKey || normalized;
      const current = targetMap.get(key) || {
        limit: pageLimit,
        offset: 0,
        total: 0,
        has_more: false,
        loaded: false,
        loading: false,
        group_counts: {},
        collapsed_group_counts: {},
        group_order: [],
      };
      targetMap.set(key, {
        ...current,
        offset: Math.max(0, Number(offset || 0)),
        loaded: false,
        loading: true,
      });
    }

    function loaded(projectId = '') {
      return findings.has(normalizedProjectId(projectId));
    }

    function loadingId() {
      return findingsLoadingId;
    }

    function filteredItems(key = '') {
      return filteredFindings.get(String(key || '')) || [];
    }

    function hasFilteredKey(key = '') {
      return filteredFindings.has(String(key || ''));
    }

    function boardItems(projectId = '', summary = ctx.projectSummary?.(projectId)) {
      const normalized = normalizedProjectId(projectId);
      if (!normalized) return [];
      if (typeof ctx.filteredProjectFindings === 'function') {
        const filtered = ctx.filteredProjectFindings(normalized, summary);
        if (Array.isArray(filtered)) return filtered;
      }
      return items(normalized);
    }

    function board(projectId = '', summary = ctx.projectSummary?.(projectId), options = {}) {
      return boardColumnsFromFindings(boardItems(projectId, summary), options);
    }

    function collapsedGroupLabels(projectId = '') {
      const labels = typeof ctx.collapsedFindingGroupLabels === 'function'
        ? ctx.collapsedFindingGroupLabels(projectId)
        : [];
      return Array.isArray(labels)
        ? labels.map(label => String(label || '')).filter(Boolean)
        : [];
    }

    function collapsedGroupSignature(projectId = '') {
      return collapsedGroupLabels(projectId).join('\x1e');
    }

    function appendFindingListOptions(params, currentPage = {}) {
      params.set('include_group_counts', '0');
      const knownTotal = Math.max(0, Number(currentPage.total || 0));
      if (knownTotal > 0) {
        params.set('include_total', '0');
        params.set('known_total', String(knownTotal));
      }
    }

    function mergedGroupOrder(previousOrder = [], nextOrder = []) {
      const ordered = [];
      const seen = new Set();
      [...(Array.isArray(previousOrder) ? previousOrder : []), ...(Array.isArray(nextOrder) ? nextOrder : [])]
        .map(label => String(label || ''))
        .filter(Boolean)
        .forEach((label) => {
          if (seen.has(label)) return;
          seen.add(label);
          ordered.push(label);
        });
      return ordered;
    }

    function collapsedCountsFromPage(projectId, pageData = {}) {
      const labels = new Set(collapsedGroupLabels(projectId));
      const counts = {};
      const currentCollapsedCounts = pageData.collapsed_group_counts && typeof pageData.collapsed_group_counts === 'object'
        ? pageData.collapsed_group_counts
        : {};
      const currentGroupCounts = pageData.group_counts && typeof pageData.group_counts === 'object'
        ? pageData.group_counts
        : {};
      labels.forEach((label) => {
        const count = Number(currentCollapsedCounts[label] ?? currentGroupCounts[label] ?? 0);
        if (count > 0) counts[label] = count;
      });
      return counts;
    }

    function invalidateFiltered(projectId = '') {
      const normalized = String(projectId || '');
      if (!normalized) {
        filteredFindings = new Map();
        filteredFindingsPagination = new Map();
        filteredFindingsLoadingKey = '';
        return;
      }
      const prefix = `${normalized}::`;
      [...filteredFindings.keys()].forEach((key) => {
        if (String(key).startsWith(prefix)) filteredFindings.delete(key);
      });
      [...filteredFindingsPagination.keys()].forEach((key) => {
        if (String(key).startsWith(prefix)) filteredFindingsPagination.delete(key);
      });
      if (filteredFindingsLoadingKey.startsWith(prefix)) {
        filteredFindingsLoadingKey = '';
      }
    }

    function invalidate(projectId = '') {
      const normalized = String(projectId || '');
      if (normalized) {
        findings.delete(normalized);
        findingsPagination.delete(normalized);
        invalidateFiltered(normalized);
      } else {
        findings = new Map();
        findingsPagination = new Map();
        invalidateFiltered();
      }
    }

    function setCachedReviewState(projectId, findingId, reviewState) {
      const normalized = String(projectId || '');
      const normalizedFindingId = String(findingId || '');
      const current = findings.get(normalized);
      if (!normalized || !normalizedFindingId || !Array.isArray(current)) return;
      findings.set(normalized, current.map(finding => {
        if (String(finding && finding.id || '') !== normalizedFindingId) return finding;
        return { ...finding, review_state: reviewState };
      }));
      filteredFindings.forEach((items, key) => {
        if (!String(key).startsWith(`${normalized}::`)) return;
        filteredFindings.set(key, items.map(finding => {
          if (String(finding && finding.id || '') !== normalizedFindingId) return finding;
          return { ...finding, review_state: reviewState };
        }));
      });
    }

    function updateCachedFinding(projectId, findingId, updates) {
      const normalized = String(projectId || '');
      const normalizedFindingId = String(findingId || '');
      const updatePayload = updates && typeof updates === 'object' ? updates : {};
      const current = findings.get(normalized);
      if (!normalized || !normalizedFindingId || !Array.isArray(current)) return;
      const updateRow = finding => (
        String(finding && finding.id || '') === normalizedFindingId
          ? { ...finding, ...updatePayload }
          : finding
      );
      findings.set(normalized, current.map(updateRow));
      filteredFindings.forEach((items, key) => {
        if (!String(key).startsWith(`${normalized}::`)) return;
        filteredFindings.set(key, items.map(updateRow));
      });
    }

    async function load(projectId, options = {}) {
      const normalized = String(projectId || '');
      if (!normalized) return;
      if (options.allPages) return loadAll(normalized, options);
      const currentPage = findingsPagination.get(normalized) || { limit: pageLimit, offset: 0, total: 0, has_more: false };
      const offset = Math.max(0, Number(
        Object.prototype.hasOwnProperty.call(options, 'offset') ? options.offset : currentPage.offset,
      ) || 0);
      const collapsedSignature = collapsedGroupSignature(normalized);
      if (
        findings.has(normalized)
        && currentPage.offset === offset
        && currentPage.loaded
        && currentPage.collapsed_signature === collapsedSignature
      ) return;
      if (findingsLoadingId === normalized && findingsLoadingPromise) {
        return findingsLoadingPromise;
      }
      findingsPagination.set(normalized, {
        ...currentPage,
        limit: Number(currentPage.limit || pageLimit),
        offset,
        loaded: false,
        loading: true,
        collapsed_signature: collapsedSignature,
      });
      findingsLoadingId = normalized;
      findingsLoadingPromise = Promise.resolve().then(async () => {
        if (!options.skipInitialRender) {
          ctx.renderProjectExplorer();
          if (ctx.mobileView?.() === 'detail' && normalizedProjectId() === normalized) {
            ctx.renderProjectMobileDetail();
          }
        }
        try {
          const params = new URLSearchParams();
          params.set('limit', String(pageLimit));
          params.set('offset', String(offset));
          appendFindingListOptions(params, currentPage);
          const resp = await ctx.apiFetch(`/projects/${encodeURIComponent(normalized)}/findings?${params.toString()}`, { cache: 'no-store' });
          if (!resp.ok) throw await ctx.projectResponseError(resp, 'Could not load project findings.');
          const data = await resp.json();
          const collapsedCounts = {
            ...collapsedCountsFromPage(normalized, currentPage),
            ...(data.collapsed_group_counts && typeof data.collapsed_group_counts === 'object'
              ? data.collapsed_group_counts
              : {}),
          };
          findings.set(normalized, Array.isArray(data.findings) ? data.findings : []);
          findingsPagination.set(normalized, {
            limit: Number(data.limit || pageLimit),
            offset: Number(data.offset || offset),
            total: Number(data.total || currentPage.total || 0),
            has_more: !!data.has_more,
            loaded: true,
            loading: false,
            group_counts: data.group_counts && typeof data.group_counts === 'object' ? data.group_counts : {},
            collapsed_group_counts: collapsedCounts,
            group_order: mergedGroupOrder(currentPage.group_order, data.group_order),
            collapsed_signature: collapsedSignature,
          });
        } catch (err) {
          findings.set(normalized, []);
          findingsPagination.set(normalized, {
            limit: pageLimit,
            offset,
            total: 0,
            has_more: false,
            loaded: true,
            loading: false,
            group_counts: {},
            collapsed_group_counts: {},
            group_order: [],
            collapsed_signature: collapsedSignature,
          });
          ctx.setProjectWorkspaceMessage(
            err && err.message ? err.message : 'Could not load project findings.',
            { error: true },
          );
          ctx.logClientError?.('failed to load project findings', err);
        } finally {
          if (findingsLoadingId === normalized) {
            findingsLoadingId = '';
            findingsLoadingPromise = null;
          }
          if (!options.skipFinalRender) {
            ctx.renderProjectExplorer();
            if (ctx.mobileView?.() === 'detail' && normalizedProjectId() === normalized) {
              ctx.renderProjectMobileDetail();
            }
            if (ctx.projectPackageWizardActive?.(normalized)) {
              ctx.renderProjectPackageWizardModal();
            }
          }
        }
      });
      return findingsLoadingPromise;
    }

    async function loadAll(projectId, options = {}) {
      const normalized = normalizedProjectId(projectId);
      if (!normalized) return [];
      const currentItems = items(normalized);
      const currentPage = findingsPagination.get(normalized) || { total: 0, loaded: false };
      const knownTotal = Number(currentPage.total || 0);
      if (currentPage.loaded && currentItems.length && (!knownTotal || currentItems.length >= knownTotal)) {
        return currentItems;
      }
      const collected = [];
      let offset = 0;
      let total = 0;
      do {
        const params = new URLSearchParams({ limit: '200', offset: String(offset) });
        const resp = await ctx.apiFetch(`/projects/${encodeURIComponent(normalized)}/findings?${params.toString()}`, {
          cache: 'no-store',
        });
        if (!resp.ok) throw await ctx.projectResponseError(resp, 'Could not load project findings.');
        const data = await resp.json();
        const rows = Array.isArray(data.findings) ? data.findings : [];
        collected.push(...rows);
        total = Number(data.total || collected.length);
        offset += rows.length;
        if (!rows.length) break;
      } while (collected.length < total);
      findings.set(normalized, collected);
      findingsPagination.set(normalized, {
        limit: pageLimit,
        offset: 0,
        total: total || collected.length,
        has_more: false,
        loaded: true,
        loading: false,
        group_counts: {},
        collapsed_group_counts: {},
        group_order: [],
        collapsed_signature: collapsedGroupSignature(normalized),
      });
      if (!options.skipFinalRender) {
        ctx.renderProjectExplorer?.();
        if (ctx.mobileView?.() === 'detail' && normalizedProjectId() === normalized) {
          ctx.renderProjectMobileDetail?.();
        }
      }
      return collected;
    }

    async function loadFiltered(projectId, summary = ctx.projectSummary?.(projectId), options = {}) {
      const normalized = String(projectId || '');
      const key = ctx.findingFilteredKey(normalized, summary);
      if (!normalized || !key || filteredFindingsLoadingKey === key) return;
      const currentPage = filteredFindingsPagination.get(key) || { limit: pageLimit, offset: 0, total: 0, has_more: false };
      const offset = Math.max(0, Number(
        Object.prototype.hasOwnProperty.call(options, 'offset') ? options.offset : currentPage.offset,
      ) || 0);
      const collapsedSignature = collapsedGroupSignature(normalized);
      if (
        filteredFindings.has(key)
        && currentPage.offset === offset
        && currentPage.loaded
        && currentPage.collapsed_signature === collapsedSignature
      ) return;
      const params = ctx.findingServerFilterParams(normalized, summary);
      params.set('limit', String(pageLimit));
      params.set('offset', String(offset));
      appendFindingListOptions(params, currentPage);
      filteredFindingsLoadingKey = key;
      filteredFindingsPagination.set(key, {
        ...currentPage,
        limit: Number(currentPage.limit || pageLimit),
        offset,
        loaded: false,
        loading: true,
        collapsed_signature: collapsedSignature,
      });
      if (!options.skipInitialRender) {
        ctx.renderProjectExplorer();
        if (ctx.mobileView?.() === 'detail' && normalizedProjectId() === normalized) {
          ctx.renderProjectMobileDetail();
        }
      }
      try {
        const query = params.toString();
        const url = `/projects/${encodeURIComponent(normalized)}/findings${query ? `?${query}` : ''}`;
        const resp = await ctx.apiFetch(url, { cache: 'no-store' });
        if (!resp.ok) throw await ctx.projectResponseError(resp, 'Could not load filtered project findings.');
        const data = await resp.json();
        const collapsedCounts = {
          ...collapsedCountsFromPage(normalized, currentPage),
          ...(data.collapsed_group_counts && typeof data.collapsed_group_counts === 'object'
            ? data.collapsed_group_counts
            : {}),
        };
        filteredFindings.set(
          key,
          Array.isArray(data.findings) ? data.findings : ctx.filteredProjectFindings(normalized, summary),
        );
        filteredFindingsPagination.set(key, {
          limit: Number(data.limit || pageLimit),
          offset: Number(data.offset || offset),
          total: Number(data.total || currentPage.total || 0),
          has_more: !!data.has_more,
          loaded: true,
          loading: false,
          group_counts: data.group_counts && typeof data.group_counts === 'object' ? data.group_counts : {},
          collapsed_group_counts: collapsedCounts,
          group_order: mergedGroupOrder(currentPage.group_order, data.group_order),
          collapsed_signature: collapsedSignature,
        });
      } catch (err) {
        filteredFindings.set(key, ctx.filteredProjectFindings(normalized, summary));
        filteredFindingsPagination.set(key, {
          limit: pageLimit,
          offset,
          total: filteredFindings.get(key)?.length || 0,
          has_more: false,
          loaded: true,
          loading: false,
          group_counts: {},
          collapsed_group_counts: {},
          group_order: [],
          collapsed_signature: collapsedSignature,
        });
        ctx.setProjectWorkspaceMessage(
          err && err.message ? err.message : 'Could not load filtered project findings.',
          { error: true },
        );
        ctx.logClientError?.('failed to load filtered project findings', err);
      } finally {
        if (filteredFindingsLoadingKey === key) filteredFindingsLoadingKey = '';
        ctx.renderProjectExplorer();
        if (ctx.mobileView?.() === 'detail' && normalizedProjectId() === normalized) {
          ctx.renderProjectMobileDetail();
        }
      }
    }

    return {
      board,
      boardColumnsFromFindings,
      boardItems,
      boardWorkflowState,
      filteredItems,
      hasFilteredKey,
      invalidate,
      invalidateFiltered,
      items,
      load,
      loadAll,
      loaded,
      loadingId,
      page,
      setPageOffset,
      setCachedReviewState,
      updateCachedFinding,
      loadFiltered,
    };
  }

  global.DarklabProjectFindingsData = {
    BOARD_COLUMN_LIMIT,
    BOARD_WORKFLOW_STATES,
    boardCardFromFinding,
    boardColumnsFromFindings,
    boardWorkflowState,
    createProjectFindingsDataController,
  };
})(globalThis);
