// Project list controller.
// Loaded before shell_chrome.js; shell chrome supplies the surrounding Projects state.

(function projectListModule(global) {
  'use strict';

  function createProjectListController(context) {
    const ctx = context || {};

    function isArchived(project) {
      return String(project && project.status || '') === 'archived';
    }

    function orderedRows(activeId, rows = ctx.projectRows()) {
      const normalizedActiveId = String(activeId || '');
      return (Array.isArray(rows) ? rows : []).slice().sort((left, right) => {
        const leftId = String(left && left.id || '');
        const rightId = String(right && right.id || '');
        if (leftId === normalizedActiveId && rightId !== normalizedActiveId) return -1;
        if (rightId === normalizedActiveId && leftId !== normalizedActiveId) return 1;
        return ctx.projectDisplayName(left).localeCompare(
          ctx.projectDisplayName(right),
          undefined,
          { sensitivity: 'base', numeric: true },
        );
      });
    }

    function listSection(label) {
      const heading = document.createElement('div');
      heading.className = 'project-workspace-section-label';
      heading.textContent = label;
      return heading;
    }

    function renderPagination(host = ctx.projectWorkspacePagination, { compact = false } = {}) {
      if (!host) return;
      const pagination = ctx.projectPagination?.() || {};
      const limit = Math.max(1, Number(pagination.limit || 50));
      const offset = Math.max(0, Number(pagination.offset || 0));
      const total = Math.max(0, Number(pagination.total || 0));
      const showPager = total > limit || offset > 0;
      host.replaceChildren();
      host.classList.toggle('u-hidden', !showPager);
      if (!showPager) return;
      const start = total ? offset + 1 : 0;
      const end = Math.min(offset + limit, total);
      const currentPage = Math.floor(offset / limit) + 1;
      const pageCount = Math.max(1, Math.ceil(total / limit));

      const summary = document.createElement('div');
      summary.className = 'project-workspace-pagination-summary';
      summary.textContent = `${start}-${end} of ${total.toLocaleString()} projects`;

      const controls = document.createElement('div');
      controls.className = 'project-workspace-pagination-controls';
      const prev = document.createElement('button');
      prev.type = 'button';
      prev.className = 'btn btn-ghost btn-compact';
      prev.dataset.projectPage = 'prev';
      prev.disabled = offset <= 0 || ctx.projectWorkspaceLoading();
      prev.setAttribute('aria-label', 'Previous projects page');
      prev.textContent = '‹';
      const status = document.createElement('span');
      status.className = 'project-workspace-pagination-status';
      status.textContent = compact ? `${currentPage}/${pageCount}` : `Page ${currentPage} of ${pageCount}`;
      const next = document.createElement('button');
      next.type = 'button';
      next.className = 'btn btn-ghost btn-compact';
      next.dataset.projectPage = 'next';
      next.disabled = offset + limit >= total || ctx.projectWorkspaceLoading();
      next.setAttribute('aria-label', 'Next projects page');
      next.textContent = '›';
      controls.append(prev, status, next);
      host.append(summary, controls);
    }

    function renderListRow(project, activeId) {
      const projectId = String(project.id || '');
      const summary = ctx.projectSummary(projectId);
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'control-row project-workspace-row'
        + (projectId === activeId ? ' is-active' : '')
        + (projectId === ctx.selectedProjectId() ? ' is-selected' : '');
      row.dataset.projectId = projectId;
      row.dataset.projectAction = 'select';
      ctx.bindProjectRuntimePressable(row);

      const main = document.createElement('div');
      main.className = 'project-workspace-main';
      const title = document.createElement('div');
      title.className = 'project-workspace-title-row';
      const name = document.createElement('span');
      name.className = 'project-workspace-name';
      name.textContent = String(project.name || project.slug || projectId);
      title.appendChild(name);
      const statusText = projectId === activeId
        ? 'active'
        : (isArchived(project) ? 'archived' : '');
      if (statusText) {
        const status = document.createElement('span');
        status.className = 'project-workspace-status' + (projectId === activeId ? ' is-active' : '');
        status.textContent = statusText;
        title.appendChild(status);
      }
      const countsWrap = document.createElement('div');
      countsWrap.className = 'project-workspace-counts';
      ctx.projectCountEntries(summary)
        .filter(item => ['runs', 'findings', 'artifacts', 'packages'].includes(item.id))
        .forEach((item) => {
          const chip = document.createElement('span');
          chip.className = 'project-workspace-count';
          chip.textContent = `${item.value} ${item.label}`;
          countsWrap.appendChild(chip);
        });
      main.append(title, countsWrap);
      ctx.appendProjectLabelChips(main, project, { className: 'project-workspace-label-chips' });
      row.appendChild(main);
      return row;
    }

    function renderList() {
      const body = ctx.projectWorkspaceBody;
      if (!body) return;
      body.replaceChildren();
      renderPagination();
      if (ctx.projectWorkspaceLoading()) {
        body.appendChild(ctx.emptyProjectPanel('Loading projects...'));
        return;
      }
      const rows = ctx.projectRows();
      if (!rows.length) {
        body.appendChild(ctx.emptyProjectPanel('No projects yet. Create one to start grouping related work.'));
        return;
      }
      const activeProject = ctx.activeProject();
      const activeId = activeProject && activeProject.id ? String(activeProject.id) : '';
      const currentProjects = rows.filter(project => !isArchived(project));
      const archivedProjects = rows.filter(project => isArchived(project));
      const hasArchived = archivedProjects.length > 0;
      if (hasArchived && currentProjects.length) body.appendChild(listSection('Current'));
      orderedRows(activeId, currentProjects).forEach((project) => {
        body.appendChild(renderListRow(project, activeId));
      });
      if (hasArchived) {
        body.appendChild(listSection('Archived'));
        orderedRows('', archivedProjects).forEach((project) => {
          body.appendChild(renderListRow(project, activeId));
        });
      }
    }

    function mobileCountEntries(summary) {
      return ctx.projectCountEntries(summary)
        .filter(item => item.id !== 'artifacts' || ctx.projectArtifactsVisible())
        .filter(item => ['runs', 'entities', 'findings', 'artifacts', 'targets', 'packages'].includes(item.id));
    }

    function renderMobileListRow(project, activeId) {
      const projectId = String(project.id || '');
      const summary = ctx.projectSummary(projectId);
      const row = document.createElement('article');
      row.className = 'panel-row project-mobile-row'
        + (projectId === activeId ? ' is-active' : '')
        + (projectId === ctx.selectedProjectId() ? ' is-selected' : '');
      row.dataset.projectId = projectId;

      const main = document.createElement('button');
      main.type = 'button';
      main.className = 'control-row project-mobile-row-main';
      main.dataset.projectMobileAction = 'open-project';
      main.dataset.projectId = projectId;
      main.setAttribute('aria-label', `Open ${ctx.projectDisplayName(project)}`);
      ctx.bindProjectRuntimePressable(main);

      const title = document.createElement('span');
      title.className = 'project-mobile-title-row';
      const titleButton = document.createElement('span');
      titleButton.className = 'project-mobile-title-target';
      const name = document.createElement('span');
      name.className = 'project-mobile-name';
      name.textContent = String(project.name || project.slug || projectId);
      titleButton.appendChild(name);
      title.appendChild(titleButton);
      const statusText = projectId === activeId
        ? 'active'
        : (isArchived(project) ? 'archived' : '');
      if (statusText) {
        const status = document.createElement('span');
        status.className = 'project-workspace-status' + (projectId === activeId ? ' is-active' : '');
        status.textContent = statusText;
        title.appendChild(status);
      }

      const chips = document.createElement('div');
      chips.className = 'project-mobile-counts';
      const countEntries = mobileCountEntries(summary).filter(item => Number(item.value || 0) > 0);
      if (!countEntries.length) {
        const empty = document.createElement('span');
        empty.className = 'project-mobile-empty-hint';
        empty.textContent = 'No linked runs yet';
        chips.appendChild(empty);
      }
      countEntries.forEach((item) => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'btn btn-ghost btn-compact project-mobile-count-chip';
        chip.dataset.projectMobileTab = item.tab || 'details';
        chip.dataset.projectId = projectId;
        chip.textContent = `${item.value} ${item.label}`;
        chip.setAttribute('aria-label', `Open ${item.label} for ${ctx.projectDisplayName(project)}`);
        ctx.bindProjectRuntimePressable(chip);
        chips.appendChild(chip);
      });

      main.appendChild(title);
      ctx.appendProjectMobileLabelChips(main, project);

      const affordances = document.createElement('div');
      affordances.className = 'project-mobile-affordances';
      const menu = document.createElement('button');
      menu.type = 'button';
      menu.className = 'btn btn-ghost btn-compact project-mobile-menu-btn';
      menu.dataset.projectMobileAction = 'project-menu';
      menu.dataset.projectId = projectId;
      menu.setAttribute('aria-label', `Project actions for ${ctx.projectDisplayName(project)}`);
      menu.textContent = ctx.mobileMenuText || 'Menu';
      ctx.bindProjectRuntimePressable(menu);
      const chevron = document.createElement('span');
      chevron.className = 'project-mobile-chevron';
      chevron.setAttribute('aria-hidden', 'true');
      chevron.textContent = ctx.mobileChevronText || '>';
      affordances.append(menu, chevron);

      row.append(main, chips, affordances);
      return row;
    }

    function mobileSection(label, count, { open = true } = {}) {
      const wrap = document.createElement('div');
      wrap.className = 'project-mobile-section-heading';
      const text = document.createElement('span');
      text.textContent = `${label}${count ? ` (${count})` : ''}`;
      wrap.appendChild(text);
      if (label === 'Archived') {
        const toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'btn btn-ghost btn-compact';
        toggle.dataset.projectMobileAction = 'toggle-archived';
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        toggle.textContent = open ? 'Hide' : 'Show';
        ctx.bindProjectRuntimePressable(toggle);
        wrap.appendChild(toggle);
      }
      return wrap;
    }

    return {
      isArchived,
      orderedRows,
      listSection,
      renderListRow,
      renderList,
      renderPagination,
      mobileCountEntries,
      renderMobileListRow,
      mobileSection,
    };
  }

  global.DarklabProjectList = {
    createProjectListController,
  };
})(globalThis);
