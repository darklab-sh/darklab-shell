// Project mobile shell controller.
// Loaded before shell_chrome.js; shell chrome supplies the surrounding Projects state.

(function projectMobileShellModule(global) {
  'use strict';

  function createProjectMobileShellController(context) {
    const ctx = context || {};
    let createOpen = false;
    let view = 'list';
    let archivedOpen = false;

    function currentView() {
      return view;
    }

    function isCreateOpen() {
      return createOpen;
    }

    function isArchivedOpen() {
      return archivedOpen;
    }

    function setArchivedOpen(open) {
      archivedOpen = !!open;
    }

    function setCreateOpen(open, { focus = false } = {}) {
      createOpen = !!open;
      if (createOpen) view = 'create';
      else if (view === 'create') view = 'list';
      syncVisibleView();
      if (focus && createOpen && ctx.projectMobileNameInput) {
        window.setTimeout(() => ctx.projectMobileNameInput.focus(), 0);
      }
    }

    function setView(nextView) {
      const normalized = ['list', 'create', 'detail'].includes(nextView) ? nextView : 'list';
      view = normalized;
      createOpen = normalized === 'create';
      syncVisibleView();
    }

    function syncVisibleView() {
      if (ctx.projectMobileListView) ctx.projectMobileListView.classList.toggle('u-hidden', view !== 'list');
      if (ctx.projectMobileCreateForm) ctx.projectMobileCreateForm.classList.toggle('u-hidden', view !== 'create');
      if (ctx.projectMobileDetailView) ctx.projectMobileDetailView.classList.toggle('u-hidden', view !== 'detail');
    }

    function selectProject(projectId, tab = '') {
      const nextProjectId = String(projectId || '').trim();
      if (!nextProjectId) return;
      const currentProjectId = String(ctx.selectedProjectId?.() || '');
      const sameProject = nextProjectId === currentProjectId;
      ctx.setSelectedProjectId(nextProjectId);
      if (tab) ctx.setWorkspaceTab(tab);
      else if (!sameProject) ctx.setWorkspaceTab('details');
      ctx.closeProjectTargetEditor();
      ctx.closeProjectEntityEditor();
      ctx.setProjectWorkspaceMessage('');
      setView('detail');
      ctx.renderProjectWorkspace();
    }

    function projectActions(project) {
      const projectId = String(project && project.id || '');
      if (!projectId) return [];
      const activeProject = ctx.activeProject?.();
      const activeId = activeProject && activeProject.id ? String(activeProject.id) : '';
      const actions = [];
      if (projectId === activeId) {
        actions.push({ label: 'Unmark active', action: 'clear' });
      } else if (!ctx.projectIsArchived(project)) {
        actions.push({ label: 'Mark active', action: 'use' });
      }
      actions.push({ label: 'Edit metadata', action: 'edit-project-metadata' });
      actions.push(ctx.projectIsArchived(project)
        ? { label: 'Unarchive', action: 'unarchive' }
        : { label: 'Archive', action: 'archive' });
      actions.push({ label: 'Delete', action: 'delete', tone: 'danger' });
      return actions;
    }

    function renderMobile() {
      if (!ctx.projectMobileRoot || !ctx.projectMobileBody) return;
      const rows = ctx.projectRows();
      if (ctx.projectMobileSummary) {
        const count = rows.length;
        ctx.projectMobileSummary.textContent = count
          ? `${count} project${count === 1 ? '' : 's'} in this session`
          : 'Create a project to group related work';
      }
      if (view === 'detail' && !ctx.selectedProjectId()) view = 'list';
      setView(view);
      ctx.projectMobileBody.replaceChildren();
      ctx.renderProjectMobileDetail();
      if (ctx.projectWorkspaceLoading()) {
        ctx.projectMobileBody.appendChild(ctx.emptyProjectPanel('Loading projects...'));
        return;
      }
      if (!rows.length) {
        archivedOpen = false;
        ctx.projectMobileBody.appendChild(ctx.emptyProjectPanel('No projects yet. Create one to start grouping related work.'));
        return;
      }

      const activeProject = ctx.activeProject?.();
      const activeId = activeProject && activeProject.id ? String(activeProject.id) : '';
      const currentProjects = rows.filter(project => !ctx.projectIsArchived(project));
      const archivedProjects = rows.filter(project => ctx.projectIsArchived(project));
      const hasArchived = archivedProjects.length > 0;
      if (hasArchived && currentProjects.length) {
        ctx.projectMobileBody.appendChild(ctx.mobileSection('Current', currentProjects.length));
      }
      ctx.orderedProjectRows(activeId, currentProjects).forEach(project => {
        ctx.projectMobileBody.appendChild(ctx.renderMobileListRow(project, activeId));
      });
      if (hasArchived) {
        ctx.projectMobileBody.appendChild(ctx.mobileSection('Archived', archivedProjects.length, { open: archivedOpen }));
        if (archivedOpen) {
          ctx.orderedProjectRows('', archivedProjects).forEach(project => {
            ctx.projectMobileBody.appendChild(ctx.renderMobileListRow(project, activeId));
          });
        }
      }
    }

    return {
      currentView,
      isArchivedOpen,
      isCreateOpen,
      projectActions,
      renderMobile,
      selectProject,
      setArchivedOpen,
      setCreateOpen,
      setView,
    };
  }

  global.DarklabProjectMobileShell = {
    createProjectMobileShellController,
  };
})(globalThis);
