(function projectFindingsDataModule(global) {
  'use strict';

  function createProjectFindingsDataController(context) {
    const ctx = context || {};
    let findings = new Map();
    let filteredFindings = new Map();
    let findingsLoadingId = '';
    let findingsLoadingPromise = null;
    let filteredFindingsLoadingKey = '';

    function normalizedProjectId(projectId = '') {
      return String(projectId || ctx.selectedProjectId?.() || '');
    }

    function items(projectId = '') {
      return findings.get(normalizedProjectId(projectId)) || [];
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

    function invalidateFiltered(projectId = '') {
      const normalized = String(projectId || '');
      if (!normalized) {
        filteredFindings = new Map();
        filteredFindingsLoadingKey = '';
        return;
      }
      const prefix = `${normalized}::`;
      [...filteredFindings.keys()].forEach((key) => {
        if (String(key).startsWith(prefix)) filteredFindings.delete(key);
      });
      if (filteredFindingsLoadingKey.startsWith(prefix)) {
        filteredFindingsLoadingKey = '';
      }
    }

    function invalidate(projectId = '') {
      const normalized = String(projectId || '');
      if (normalized) {
        findings.delete(normalized);
        invalidateFiltered(normalized);
      } else {
        findings = new Map();
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
      invalidateFiltered(normalized);
    }

    async function load(projectId) {
      const normalized = String(projectId || '');
      if (!normalized || findings.has(normalized)) return;
      if (findingsLoadingId === normalized && findingsLoadingPromise) {
        return findingsLoadingPromise;
      }
      findingsLoadingId = normalized;
      findingsLoadingPromise = Promise.resolve().then(async () => {
        ctx.renderProjectExplorer();
        if (ctx.mobileView?.() === 'detail' && normalizedProjectId() === normalized) {
          ctx.renderProjectMobileDetail();
        }
        try {
          const resp = await ctx.apiFetch(`/projects/${encodeURIComponent(normalized)}/findings`, { cache: 'no-store' });
          if (!resp.ok) throw await ctx.projectResponseError(resp, 'Could not load project findings.');
          const data = await resp.json();
          findings.set(normalized, Array.isArray(data.findings) ? data.findings : []);
        } catch (err) {
          findings.set(normalized, []);
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

    async function loadFiltered(projectId, summary = ctx.projectSummary?.(projectId)) {
      const normalized = String(projectId || '');
      const key = ctx.findingFilteredKey(normalized, summary);
      if (!normalized || !key || filteredFindings.has(key) || filteredFindingsLoadingKey === key) return;
      const params = ctx.findingServerFilterParams(normalized, summary);
      filteredFindingsLoadingKey = key;
      try {
        const query = params.toString();
        const url = `/projects/${encodeURIComponent(normalized)}/findings${query ? `?${query}` : ''}`;
        const resp = await ctx.apiFetch(url, { cache: 'no-store' });
        if (!resp.ok) throw await ctx.projectResponseError(resp, 'Could not load filtered project findings.');
        const data = await resp.json();
        filteredFindings.set(
          key,
          Array.isArray(data.findings) ? data.findings : ctx.filteredProjectFindings(normalized, summary),
        );
      } catch (err) {
        filteredFindings.set(key, ctx.filteredProjectFindings(normalized, summary));
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
      setCachedReviewState,
      loadFiltered,
    };
  }

  global.DarklabProjectFindingsData = {
    createProjectFindingsDataController,
  };
})(globalThis);
