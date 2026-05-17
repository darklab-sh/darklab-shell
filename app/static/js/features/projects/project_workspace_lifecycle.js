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

    function ensureSelectedProject() {
      const projectIds = ctx.projectRows().map(project => String(project.id || '')).filter(Boolean);
      const currentId = String(ctx.selectedProjectId() || '');
      if (currentId && projectIds.includes(currentId)) return;
      const activeProject = ctx.activeProject();
      const activeId = activeProject && activeProject.id ? String(activeProject.id) : '';
      ctx.setSelectedProjectId(activeId && projectIds.includes(activeId) ? activeId : (projectIds[0] || ''));
    }

    async function loadProjectSummaries(projects) {
      const summaries = new Map();
      await Promise.all((Array.isArray(projects) ? projects : []).map(async (project) => {
        const projectId = String(project.id || '');
        if (!projectId) return;
        try {
          const resp = await ctx.apiFetch(`/projects/${encodeURIComponent(projectId)}/summary`, { cache: 'no-store' });
          if (!resp.ok) return;
          summaries.set(projectId, await resp.json());
        } catch (err) {
          ctx.logClientError('failed to load project summary', err);
        }
      }));
      ctx.setProjectSummaries(summaries);
    }

    async function refreshProjectWorkspace() {
      if (!ctx.projectWorkspaceBody || typeof ctx.apiFetch !== 'function') return;
      ctx.setProjectWorkspaceLoading(true);
      ctx.renderProjectWorkspace();
      try {
        const [projectsResp] = await Promise.all([
          ctx.apiFetch('/projects?include_archived=1', { cache: 'no-store' }),
          ctx.loadActiveProjectContext(),
        ]);
        if (!projectsResp.ok) throw new Error(`HTTP ${projectsResp.status}`);
        const data = await projectsResp.json();
        const rows = Array.isArray(data.projects) ? data.projects : [];
        ctx.setProjectRows(rows);
        ctx.invalidateProjectFindings();
        await loadProjectSummaries(rows);
        ensureSelectedProject();
        ctx.setProjectWorkspaceMessage('');
      } catch (err) {
        ctx.setProjectRows([]);
        ctx.setProjectSummaries(new Map());
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
