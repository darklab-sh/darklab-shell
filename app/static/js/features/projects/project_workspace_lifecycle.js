// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Project workspace loading and selection lifecycle.
// Loaded before shell_chrome.js; shell chrome supplies state accessors and render hooks.

let exportedDarklabProjectWorkspaceLifecycle = null;

(function projectWorkspaceLifecycleModule(global) {
  'use strict';

  function createProjectWorkspaceLifecycleController(context) {
    const ctx = context || {};

    function selectedProject() {
      const selectedId = String(ctx.selectedProjectId() || '');
      if (!selectedId) return null;
      const summary = ctx.projectSummaries().get(selectedId);
      if (summary && summary.project && typeof summary.project === 'object') return summary.project;
      return ctx.projectRows().find(project => String(project.id || '') === selectedId) || null;
    }

    function timestampMs() {
      if (typeof performance !== 'undefined' && typeof performance.now === 'function') return performance.now();
      return Date.now();
    }

    function durationMs(startedAt) {
      return Math.max(0, Math.round(timestampMs() - Number(startedAt || 0)));
    }

    function logWorkspaceEvent(context, err, details = {}) {
      if (typeof ctx.logClientError !== 'function') return;
      ctx.logClientError(context, err, details);
    }

    function logProjectSummaryLoadFailed(projectId, err, details = {}) {
      logWorkspaceEvent('project summary load failed', err, {
        event: 'PROJECT_SUMMARY_LOAD_FAILED',
        level: 'warning',
        project_id: String(projectId || '').slice(0, 160),
        partial_summary_present: !!projectSummary(projectId)?.partial,
        ...details,
      });
    }

    function projectSummary(projectId = ctx.selectedProjectId()) {
      return ctx.projectSummaries().get(String(projectId || '')) || null;
    }

    function summaryFromListRow(project) {
      const counts = project && project.counts && typeof project.counts === 'object' ? project.counts : {};
      const findingSummary = project && project.finding_summary && typeof project.finding_summary === 'object'
        ? project.finding_summary
        : { review_states: {}, severities: {} };
      return {
        project,
        counts,
        finding_summary: findingSummary,
        links: [],
        targets: [],
        entities: [],
        runs: [],
        artifacts: [],
        packages: [],
        partial: true,
      };
    }

    function setSummary(projectId, summary) {
      const normalized = String(projectId || '');
      if (!normalized) return;
      if (typeof ctx.setProjectSummary === 'function') {
        ctx.setProjectSummary(normalized, summary);
        return;
      }
      const summaries = ctx.projectSummaries();
      summaries.set(normalized, summary);
      ctx.setProjectSummaries(summaries);
    }

    function seedListSummaries(projects) {
      const summaries = new Map();
      (Array.isArray(projects) ? projects : []).forEach((project) => {
        const projectId = String(project && project.id || '');
        if (projectId) summaries.set(projectId, summaryFromListRow(project));
      });
      ctx.setProjectSummaries(summaries);
    }

    function ensureSelectedProject() {
      const projectIds = ctx.projectRows().map(project => String(project.id || '')).filter(Boolean);
      const currentId = String(ctx.selectedProjectId() || '');
      if (currentId && projectIds.includes(currentId)) return;
      const activeProject = ctx.activeProject();
      const activeId = activeProject && activeProject.id ? String(activeProject.id) : '';
      ctx.setSelectedProjectId(activeId && projectIds.includes(activeId) ? activeId : (projectIds[0] || ''));
    }

    async function loadProjectSummaries(projects) {
      await Promise.all((Array.isArray(projects) ? projects : []).map(async (project) => {
        const projectId = String(project.id || '');
        if (!projectId) return;
        try {
          const resp = await ctx.apiFetch(`/projects/${encodeURIComponent(projectId)}/summary`, { cache: 'no-store' });
          if (!resp.ok) {
            logProjectSummaryLoadFailed(projectId, new Error(`HTTP ${resp.status}`), {
              status: Number(resp.status || 0),
              source: 'list_summaries',
            });
            return;
          }
          setSummary(projectId, await resp.json());
        } catch (err) {
          logProjectSummaryLoadFailed(projectId, err, { source: 'list_summaries' });
        }
      }));
    }

    async function ensureProjectSummary(projectId = ctx.selectedProjectId()) {
      const normalized = String(projectId || '');
      if (!normalized) return null;
      const existing = projectSummary(normalized);
      if (existing && !existing.partial && !existing.load_error) return existing;
      const project = ctx.projectRows().find(item => String(item && item.id || '') === normalized);
      if (project && !existing) setSummary(normalized, summaryFromListRow(project));
      const markSummaryLoadError = () => {
        const fallback = projectSummary(normalized) || (project ? summaryFromListRow(project) : null);
        if (fallback) {
          setSummary(normalized, { ...fallback, load_error: true });
        }
        return null;
      };
      try {
        const resp = await ctx.apiFetch(`/projects/${encodeURIComponent(normalized)}/summary`, { cache: 'no-store' });
        if (!resp.ok) {
          logProjectSummaryLoadFailed(normalized, new Error(`HTTP ${resp.status}`), {
            status: Number(resp.status || 0),
            source: 'selected_summary',
          });
          return markSummaryLoadError();
        }
        const summary = await resp.json();
        setSummary(normalized, summary);
        return summary;
      } catch (err) {
        logProjectSummaryLoadFailed(normalized, err, { source: 'selected_summary' });
        return markSummaryLoadError();
      }
    }

    async function refreshProjectWorkspace(options = {}) {
      if (!ctx.projectWorkspaceBody || typeof ctx.apiFetch !== 'function') return;
      ctx.setProjectWorkspaceLoading(true);
      ctx.renderProjectWorkspace();
      try {
        const startedAt = timestampMs();
        const pagination = ctx.projectPagination?.() || {};
        const limit = Math.max(1, Number(pagination.limit || 50));
        const offset = Math.max(0, Number(pagination.offset || 0));
        const query = new URLSearchParams({
          include_archived: '1',
          include_counts: '1',
          limit: String(limit),
          offset: String(offset),
        });
        const initialLoad = options && options.initialLoad && typeof options.initialLoad === 'object'
          ? options.initialLoad
          : null;
        const canUseInitialLoad = !!(
          initialLoad
          && Number(initialLoad.limit) === limit
          && Number(initialLoad.offset) === offset
          && initialLoad.projectsResp
        );
        const projectsRequest = canUseInitialLoad
          ? initialLoad.projectsResp
          : ctx.apiFetch(`/projects?${query.toString()}`, { cache: 'no-store' });
        const activeProjectRequest = canUseInitialLoad && initialLoad.activeContext
          ? initialLoad.activeContext
          : ctx.loadActiveProjectContext();
        const projectsStage = Promise.resolve(projectsRequest).catch((err) => {
          logWorkspaceEvent('project workspace initial load failed', err, {
            event: 'PROJECT_WORKSPACE_INITIAL_LOAD_FAILED',
            level: 'error',
            stage: 'projects',
            limit,
            offset,
            used_initial_load: canUseInitialLoad,
            duration_ms: durationMs(startedAt),
          });
          if (err && typeof err === 'object') err.__darklabProjectWorkspaceLogged = true;
          throw err;
        });
        const activeProjectStage = Promise.resolve(activeProjectRequest).catch((err) => {
          logWorkspaceEvent('project active context preload failed', err, {
            event: 'PROJECT_ACTIVE_CONTEXT_PRELOAD_FAILED',
            level: 'warning',
            stage: 'active_context',
            limit,
            offset,
            used_initial_load: canUseInitialLoad,
            duration_ms: durationMs(startedAt),
          });
          return null;
        });
        const [projectsResp] = await Promise.all([
          projectsStage,
          activeProjectStage,
        ]);
        if (!projectsResp.ok) {
          const err = new Error(`HTTP ${projectsResp.status}`);
          err.__darklabProjectWorkspaceLogged = true;
          logWorkspaceEvent('project workspace initial load failed', err, {
            event: 'PROJECT_WORKSPACE_INITIAL_LOAD_FAILED',
            level: 'error',
            stage: 'projects',
            status: Number(projectsResp.status || 0),
            limit,
            offset,
            used_initial_load: canUseInitialLoad,
            duration_ms: durationMs(startedAt),
          });
          throw err;
        }
        const data = await projectsResp.json();
        const rows = Array.isArray(data.projects) ? data.projects : [];
        const total = Number(data.total || rows.length || 0);
        if (!rows.length && total > 0 && offset > 0) {
          logWorkspaceEvent('project workspace page offset adjusted', null, {
            event: 'PROJECT_WORKSPACE_PAGE_OFFSET_ADJUSTED',
            level: 'debug',
            limit,
            offset,
            total,
            duration_ms: durationMs(startedAt),
          });
          ctx.setProjectPagination?.({ limit, offset: Math.max(0, total - limit), total });
          ctx.setProjectWorkspaceLoading(false);
          await refreshProjectWorkspace();
          return;
        }
        ctx.setProjectRows(rows);
        ctx.setProjectPagination?.({
          limit: Number(data.limit || limit),
          offset: Number(data.offset || offset),
          total,
        });
        seedListSummaries(rows);
        ctx.invalidateProjectTargetPage?.();
        ctx.invalidateProjectFindings();
        ctx.invalidateProjectRuns?.();
        ctx.invalidateProjectEntities?.();
        ctx.invalidateProjectArtifacts?.();
        ctx.invalidateProjectWebSurface?.();
        ctx.invalidateProjectAssessment?.();
        ctx.invalidateProjectOverview?.();
        ctx.invalidateProjectMonitoring?.();
        ensureSelectedProject();
        if (ctx.workspaceTab?.() !== 'details') {
          await ensureProjectSummary();
        }
        ctx.setProjectWorkspaceMessage('');
      } catch (err) {
        if (!err || typeof err !== 'object' || err.__darklabProjectWorkspaceLogged !== true) {
          logWorkspaceEvent('project workspace initial load failed', err, {
            event: 'PROJECT_WORKSPACE_INITIAL_LOAD_FAILED',
            level: 'error',
            stage: 'projects',
          });
        }
        ctx.setProjectRows([]);
        ctx.setProjectSummaries(new Map());
        ctx.setProjectPagination?.({ limit: 50, offset: 0, total: 0 });
        ctx.setProjectWorkspaceMessage('Could not load projects.', { error: true });
      } finally {
        ctx.setProjectWorkspaceLoading(false);
        ctx.syncProjectNotesForm();
        ctx.renderProjectWorkspace();
      }
    }

    return {
      ensureSelectedProject,
      ensureProjectSummary,
      loadProjectSummaries,
      projectSummary,
      refreshProjectWorkspace,
      selectedProject,
    };
  }

  const DarklabProjectWorkspaceLifecycle = {
    createProjectWorkspaceLifecycleController,
  };
  exportedDarklabProjectWorkspaceLifecycle = DarklabProjectWorkspaceLifecycle;
})(globalThis);

export {
  exportedDarklabProjectWorkspaceLifecycle as DarklabProjectWorkspaceLifecycle,};
