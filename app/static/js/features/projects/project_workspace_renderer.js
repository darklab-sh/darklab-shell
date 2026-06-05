// Project workspace renderer.
// Loaded before shell_chrome.js; shell chrome supplies project state and tab renderers.

(function projectWorkspaceRendererModule(global) {
  'use strict';

  function createProjectWorkspaceRendererController(context) {
    const ctx = context || {};

    function tabsScrollState(body) {
      const strip = body?.querySelector?.('.project-explorer-tabs');
      if (!strip) return { left: 0, pinnedRight: false };
      const left = Math.max(0, Number(strip.scrollLeft || 0));
      const maxLeft = Math.max(0, Number(strip.scrollWidth || 0) - Number(strip.clientWidth || 0));
      const active = strip.querySelector('.project-explorer-tab.is-active');
      const activeLeft = Number(active?.offsetLeft || 0);
      const activeRight = activeLeft + Number(active?.offsetWidth || 0);
      const viewRight = left + Number(strip.clientWidth || 0);
      const activeLastVisible = !!active && !active.nextElementSibling && activeLeft >= left && activeRight <= viewRight;
      return {
        left,
        pinnedRight: maxLeft > 0 && (left >= maxLeft - 2 || activeLastVisible),
      };
    }

    function restoreTabsScrollState(tabs, state) {
      const strip = tabs?.querySelector?.('.project-explorer-tabs');
      if (!strip || !state) return;
      const maxLeft = Math.max(0, Number(strip.scrollWidth || 0) - Number(strip.clientWidth || 0));
      strip.scrollLeft = state.pinnedRight ? maxLeft : Math.max(0, Number(state.left || 0));
    }

    function renderExplorer() {
      const body = ctx.projectExplorerBody;
      if (!body) return;
      const currentTab = ctx.workspaceTab();
      const previousTabsScroll = tabsScrollState(body);
      body.classList.toggle('project-explorer-body-details', currentTab === 'details');
      body.replaceChildren();
      ctx.ensureSelectedProject();
      const project = ctx.selectedProject();
      const summary = ctx.projectSummary();
      if (ctx.projectWorkspaceLoading()) {
        body.appendChild(ctx.emptyProjectPanel('Loading project explorer...'));
        return;
      }
      if (!project) {
        body.appendChild(ctx.emptyProjectPanel('Create or select a project to explore related work.'));
        ctx.syncProjectForms(null);
        return;
      }
      ctx.syncProjectForms(project);
      if (ctx.workspaceTab() === 'artifacts' && !ctx.projectArtifactsVisible()) {
        ctx.setWorkspaceTab('details');
      }
      const projectId = String(project.id || '');
      const [header, tabs] = ctx.renderProjectHeader(project, summary, {
        initialTabsScrollLeft: previousTabsScroll.left,
      });
      const activeTab = ctx.workspaceTab();
      const filterBar = ['runs', 'entities', 'findings', 'artifacts'].includes(activeTab)
        ? ctx.renderProjectFilterBar(projectId, summary)
        : null;
      body.append(header);
      body.appendChild(tabs);
      restoreTabsScrollState(tabs, previousTabsScroll);
      if (filterBar) body.appendChild(filterBar);
      const content = document.createElement('div');
      content.className = 'project-explorer-tab-panel';
      if (activeTab === 'details') {
        content.classList.add('project-explorer-tab-panel-details');
        ctx.renderProjectDetails(content, project, summary);
      } else if (activeTab === 'runs') ctx.renderProjectRuns(content, projectId, summary);
      else if (activeTab === 'entities') ctx.renderProjectEntities(content, projectId, summary);
      else if (activeTab === 'findings') ctx.renderProjectFindings(content, projectId, summary);
      else if (activeTab === 'artifacts') ctx.renderProjectArtifacts(content, projectId, summary);
      else if (activeTab === 'packages') ctx.renderProjectPackages(content, projectId, summary);
      else if (activeTab === 'report') ctx.renderProjectReport(content, projectId, summary);
      body.appendChild(content);
      ctx.enhanceAppSelects?.(content);
      if (filterBar) ctx.enhanceAppSelects?.(filterBar);
      if (filterBar) {
        ctx.syncProjectFilterSortDivider(filterBar);
        ctx.scheduleProjectFilterSortDividerSync(filterBar);
      }
      const findingFiltersActive = ctx.projectFindingServerFiltersActive(projectId, summary);
      if (
        ctx.workspaceTab() === 'findings'
        || ['runs', 'artifacts'].includes(ctx.workspaceTab())
        || ctx.projectPackageWizardActive(projectId)
      ) {
        if (!(ctx.workspaceTab() === 'findings' && findingFiltersActive)) {
          ctx.loadProjectFindings(projectId).catch(() => {});
        }
      }
      if (
        ctx.workspaceTab() === 'findings'
        && findingFiltersActive
      ) {
        ctx.loadProjectFilteredFindings(projectId, summary).catch(() => {});
      }
    }

    function renderWorkspace() {
      if (ctx.projectWorkspaceSubtitle) {
        const pagination = ctx.projectPagination?.() || {};
        const count = Number(pagination.total || ctx.projectRows().length || 0);
        ctx.projectWorkspaceSubtitle.textContent = count
          ? `${count} project workspace${count === 1 ? '' : 's'} in this session.`
          : 'Select a project to review its targets, runs, findings, artifacts, and packages.';
      }
      ctx.renderProjectList();
      ctx.renderProjectMobile();
      renderExplorer();
      ctx.renderProjectPackageWizardModal();
    }

    function cycleTab(offset = 1) {
      if (!ctx.isProjectWorkspaceOpen()) return false;
      const project = ctx.selectedProject();
      if (!project) return false;
      const projectId = String(project.id || '');
      const summary = ctx.projectSummary(projectId);
      const items = ctx.projectMobileTabItems(projectId, summary);
      if (items.length < 2) return false;
      const currentIndex = Math.max(0, items.findIndex(item => item.id === ctx.workspaceTab()));
      const nextIndex = (currentIndex + Number(offset || 1) + items.length) % items.length;
      const nextTab = items[nextIndex].id || 'details';
      if (!nextTab || nextTab === ctx.workspaceTab()) return false;
      ctx.flushProjectNotesAutosave().catch(() => {});
      ctx.setWorkspaceTab(nextTab);
      if (ctx.workspaceTab() !== 'details') ctx.closeProjectTargetEditor();
      ctx.closeProjectEntityEditor();
      ctx.setProjectWorkspaceMessage('');
      if (ctx.mobileView() === 'detail' && ctx.projectMobileDetailBody) ctx.projectMobileDetailBody.scrollTop = 0;
      renderWorkspace();
      ctx.focusProjectWorkspaceTab(nextTab);
      return true;
    }

    return {
      cycleTab,
      renderExplorer,
      renderWorkspace,
    };
  }

  global.DarklabProjectWorkspaceRenderer = {
    createProjectWorkspaceRendererController,
  };
})(globalThis);
