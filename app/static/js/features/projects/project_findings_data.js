(function projectFindingsDataModule(global) {
  'use strict';

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

    async function load(projectId, options = {}) {
      const normalized = String(projectId || '');
      if (!normalized) return;
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
          ctx.renderProjectExplorer();
          if (ctx.mobileView?.() === 'detail' && normalizedProjectId() === normalized) {
            ctx.renderProjectMobileDetail();
          }
          if (ctx.projectPackageWizardActive?.(normalized)) {
            ctx.renderProjectPackageWizardModal();
          }
        }
      });
      return findingsLoadingPromise;
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
      filteredItems,
      hasFilteredKey,
      invalidate,
      invalidateFiltered,
      items,
      load,
      loaded,
      loadingId,
      page,
      setPageOffset,
      setCachedReviewState,
      loadFiltered,
    };
  }

  global.DarklabProjectFindingsData = {
    createProjectFindingsDataController,
  };
})(globalThis);
