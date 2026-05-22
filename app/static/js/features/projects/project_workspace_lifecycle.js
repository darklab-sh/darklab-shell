// Project workspace loading and selection lifecycle.
// Loaded before shell_chrome.js; shell chrome supplies state accessors and render hooks.

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
          if (!resp.ok) return;
          setSummary(projectId, await resp.json());
        } catch (err) {
          ctx.logClientError('failed to load project summary', err);
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
        if (!resp.ok) return markSummaryLoadError();
        const summary = await resp.json();
        setSummary(normalized, summary);
        return summary;
      } catch (err) {
        ctx.logClientError('failed to load project summary', err);
        return markSummaryLoadError();
      }
    }

    async function refreshProjectWorkspace() {
      if (!ctx.projectWorkspaceBody || typeof ctx.apiFetch !== 'function') return;
      ctx.setProjectWorkspaceLoading(true);
      ctx.renderProjectWorkspace();
      try {
        const pagination = ctx.projectPagination?.() || {};
        const limit = Math.max(1, Number(pagination.limit || 50));
        const offset = Math.max(0, Number(pagination.offset || 0));
        const query = new URLSearchParams({
          include_archived: '1',
          include_counts: '1',
          limit: String(limit),
          offset: String(offset),
        });
        const [projectsResp] = await Promise.all([
          ctx.apiFetch(`/projects?${query.toString()}`, { cache: 'no-store' }),
          ctx.loadActiveProjectContext(),
        ]);
        if (!projectsResp.ok) throw new Error(`HTTP ${projectsResp.status}`);
        const data = await projectsResp.json();
        const rows = Array.isArray(data.projects) ? data.projects : [];
        const total = Number(data.total || rows.length || 0);
        if (!rows.length && total > 0 && offset > 0) {
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
        ctx.invalidateProjectFindings();
        ctx.invalidateProjectRuns?.();
        ctx.invalidateProjectEntities?.();
        ctx.invalidateProjectArtifacts?.();
        ensureSelectedProject();
        if (ctx.workspaceTab?.() !== 'details') {
          await ensureProjectSummary();
        }
        ctx.setProjectWorkspaceMessage('');
      } catch (err) {
        ctx.setProjectRows([]);
        ctx.setProjectSummaries(new Map());
        ctx.setProjectPagination?.({ limit: 50, offset: 0, total: 0 });
        ctx.setProjectWorkspaceMessage('Could not load projects.', { error: true });
        ctx.logClientError('failed to load /projects', err);
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

  global.DarklabProjectWorkspaceLifecycle = {
    createProjectWorkspaceLifecycleController,
  };
})(globalThis);
