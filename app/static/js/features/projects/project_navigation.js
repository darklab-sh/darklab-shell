// Project workspace navigation controller.
// Loaded before shell_chrome.js; shell chrome supplies the surrounding Projects state.

(function projectNavigationModule(global) {
  'use strict';

  function createProjectNavigationController(context) {
    const ctx = context || {};
    const mobileTabEdgeOptions = { wrapSelector: '.project-mobile-tabs-wrap' };

    function tabCountText(projectId, summary, tabId, total) {
      const totalCount = Number(total || 0);
      const targetFiltersActive = ctx.projectTargetFilterActive(projectId, summary);
      const runFiltersActive = ctx.projectRunFilterActive(projectId, summary);

      if (tabId === 'findings') {
        if (!ctx.projectFindingServerFiltersActive(projectId, summary)) {
          return String(totalCount);
        }
        const page = ctx.projectFindingPagination?.(projectId, summary) || {};
        const filteredTotal = Number(page.total || ctx.filteredProjectFindings(projectId, summary).length);
        if (!page.loaded && !filteredTotal) return String(totalCount);
        return `${filteredTotal}/${totalCount}`;
      }

      if (tabId === 'runs') {
        if (!targetFiltersActive && !runFiltersActive) return String(totalCount);
        if (targetFiltersActive && !ctx.projectFindingsLoaded(projectId)) return String(totalCount);
        return `${ctx.filteredProjectRuns(projectId, summary).length}/${totalCount}`;
      }

      if (tabId === 'artifacts') {
        if (!targetFiltersActive && !runFiltersActive) return String(totalCount);
        if (targetFiltersActive && !ctx.projectFindingsLoaded(projectId)) return String(totalCount);
        return `${ctx.filteredProjectArtifacts(projectId, summary).length}/${totalCount}`;
      }

      return String(totalCount);
    }

    function mobileTabItems(projectId, summary) {
      const counts = ctx.projectCounts(summary);
      const clamp = (value) => {
        const count = Number(value || 0);
        if (!Number.isFinite(count) || count <= 0) return '0';
        return count > 999 ? '999+' : String(count);
      };
      return [
        { id: 'details', label: 'Details' },
        { id: 'runs', label: 'Runs', count: clamp(counts.runs) },
        { id: 'entities', label: 'Entities', count: clamp(counts.entities) },
        { id: 'findings', label: 'Findings', count: clamp(counts.findings) },
        ctx.projectArtifactsVisible()
          ? { id: 'artifacts', label: 'Artifacts', count: clamp(counts.artifacts) }
          : null,
        { id: 'packages', label: 'Packages', count: clamp(counts.packages) },
      ].filter(Boolean);
    }

    function renderProjectHeader(project, summary) {
      const header = document.createElement('div');
      header.className = 'project-explorer-header';
      const titleWrap = document.createElement('div');
      titleWrap.className = 'project-explorer-title-wrap';
      const title = document.createElement('div');
      title.className = 'project-explorer-title';
      title.textContent = ctx.projectDisplayName(project);
      const meta = document.createElement('div');
      meta.className = 'project-explorer-meta';
      meta.textContent = [
        String(project.slug || project.id || ''),
        String(project.id || ''),
      ].filter(Boolean).join(ctx.metaSeparator || ' - ');
      titleWrap.append(title, meta);
      ctx.appendProjectLabelChips(titleWrap, project);

      const activeProject = ctx.activeProject();
      const activeId = activeProject && activeProject.id ? String(activeProject.id) : '';
      const actions = document.createElement('div');
      actions.className = 'project-explorer-actions';
      if (String(project.id || '') === activeId) {
        const pill = document.createElement('span');
        pill.className = 'project-explorer-active-pill';
        pill.textContent = 'active';
        actions.appendChild(pill);
        actions.appendChild(ctx.makeProjectButton('Clear active', 'clear', String(project.id || '')));
      } else if (project.status !== 'archived') {
        actions.appendChild(ctx.makeProjectButton('Use as active', 'use', String(project.id || '')));
      }
      if (project.status !== 'archived') {
        actions.appendChild(ctx.makeProjectButton('Archive', 'archive', String(project.id || '')));
      } else {
        actions.appendChild(ctx.makeProjectButton('Unarchive', 'unarchive', String(project.id || '')));
      }
      if (typeof global.openAtlas === 'function') {
        actions.appendChild(ctx.makeProjectButton('Open in Atlas', 'open-atlas', String(project.id || '')));
      }
      actions.appendChild(ctx.makeProjectButton('Delete', 'delete', String(project.id || ''), 'destructive'));
      header.append(titleWrap, actions);

      const tabs = document.createElement('div');
      tabs.className = 'project-explorer-tabs tab-strip';
      tabs.setAttribute('role', 'tablist');
      tabs.setAttribute('aria-label', 'Project sections');
      const tabCounts = ctx.projectCounts(summary);
      const projectId = String(project.id || '');
      const tabItems = [
        { id: 'details', label: 'Details' },
        { id: 'runs', label: 'Runs', count: tabCountText(projectId, summary, 'runs', tabCounts.runs) },
        { id: 'entities', label: 'Entities', count: tabCountText(projectId, summary, 'entities', tabCounts.entities) },
        { id: 'findings', label: 'Findings', count: tabCountText(projectId, summary, 'findings', tabCounts.findings) },
        ctx.projectArtifactsVisible()
          ? { id: 'artifacts', label: 'Artifacts', count: tabCountText(projectId, summary, 'artifacts', tabCounts.artifacts) }
          : null,
        { id: 'packages', label: 'Packages', count: tabCounts.packages },
      ].filter(Boolean);
      tabItems.forEach(({ id, label, count }) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'tab-strip-item project-explorer-tab' + (ctx.projectWorkspaceTab() === id ? ' is-active' : '');
        btn.dataset.projectTab = id;
        btn.setAttribute('role', 'tab');
        btn.setAttribute('aria-selected', ctx.projectWorkspaceTab() === id ? 'true' : 'false');
        btn.setAttribute('aria-pressed', ctx.projectWorkspaceTab() === id ? 'true' : 'false');
        btn.textContent = count === undefined ? label : `${label} (${count})`;
        ctx.bindProjectRuntimePressable(btn);
        tabs.appendChild(btn);
      });
      return [header, tabs];
    }

    function renderMobileDetailTopbar(project, activeId) {
      if (!ctx.projectMobileDetailTopbar) return;
      ctx.projectMobileDetailTopbar.replaceChildren();
      const back = document.createElement('button');
      back.type = 'button';
      back.className = 'btn btn-ghost btn-compact project-mobile-back-btn';
      back.dataset.projectMobileAction = 'back-to-list';
      back.setAttribute('aria-label', 'Back to project list');
      back.textContent = ctx.mobileBackText || '< Back';
      ctx.bindProjectRuntimePressable(back);

      const titleWrap = document.createElement('div');
      titleWrap.className = 'project-mobile-detail-title-wrap';
      const title = document.createElement('div');
      title.className = 'project-mobile-detail-title';
      title.textContent = project ? ctx.projectDisplayName(project) : 'Project';
      titleWrap.appendChild(title);
      const statusText = project && String(project.id || '') === activeId
        ? 'active'
        : (project && ctx.projectIsArchived(project) ? 'archived' : '');
      const statusSlot = document.createElement('div');
      statusSlot.className = 'project-mobile-detail-status-slot';
      if (statusText) {
        const status = document.createElement('span');
        status.className = 'project-workspace-status' + (statusText === 'active' ? ' is-active' : '');
        status.textContent = statusText;
        statusSlot.appendChild(status);
      }

      ctx.projectMobileDetailTopbar.append(back, titleWrap, statusSlot);
    }

    function renderMobileTabs(projectId, summary) {
      if (!ctx.projectMobileTabs) return;
      ctx.projectMobileTabs.replaceChildren();
      const items = mobileTabItems(projectId, summary);
      if (!items.some(item => item.id === ctx.projectWorkspaceTab())) ctx.setProjectWorkspaceTab('details');
      items.forEach((item) => {
        const tab = document.createElement('button');
        tab.type = 'button';
        tab.className = 'tab-strip-item project-mobile-tab' + (ctx.projectWorkspaceTab() === item.id ? ' is-active' : '');
        tab.dataset.projectMobileDetailTab = item.id;
        tab.setAttribute('role', 'tab');
        tab.setAttribute('aria-selected', ctx.projectWorkspaceTab() === item.id ? 'true' : 'false');
        tab.setAttribute('aria-pressed', ctx.projectWorkspaceTab() === item.id ? 'true' : 'false');
        const label = document.createElement('span');
        label.className = 'project-mobile-tab-label';
        label.textContent = item.label;
        tab.appendChild(label);
        if (item.count !== undefined) {
          const count = document.createElement('span');
          count.className = 'project-mobile-tab-count';
          count.textContent = item.count;
          tab.appendChild(count);
        }
        ctx.bindProjectRuntimePressable(tab);
        ctx.projectMobileTabs.appendChild(tab);
      });
      syncMobileActiveTabScroll();
    }

    function syncMobileActiveTabScroll() {
      if (typeof global.syncActiveTabStripScroll === 'function') {
        global.syncActiveTabStripScroll(ctx.projectMobileTabs, mobileTabEdgeOptions);
      }
    }

    function syncMobileTabEdges() {
      if (typeof global.syncTabStripEdges === 'function') {
        global.syncTabStripEdges(ctx.projectMobileTabs, mobileTabEdgeOptions);
      }
    }

    function focusWorkspaceTab(tabId) {
      const nextTab = String(tabId || '');
      window.setTimeout(() => {
        const buttons = Array.from(ctx.projectWorkspaceModal?.querySelectorAll('[data-project-tab], [data-project-mobile-detail-tab]') || []);
        const target = buttons.find(button => (
          String(button.dataset.projectTab || button.dataset.projectMobileDetailTab || '') === nextTab
        ));
        target?.focus({ preventScroll: true });
        syncMobileActiveTabScroll();
      }, 0);
    }

    return {
      tabCountText,
      mobileTabItems,
      renderProjectHeader,
      renderMobileDetailTopbar,
      renderMobileTabs,
      syncMobileActiveTabScroll,
      syncMobileTabEdges,
      focusWorkspaceTab,
    };
  }

  global.DarklabProjectNavigation = {
    createProjectNavigationController,
  };
})(globalThis);
