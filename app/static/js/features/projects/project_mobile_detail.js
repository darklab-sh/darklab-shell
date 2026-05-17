// Project mobile detail controller.
// Loaded before shell_chrome.js; shell chrome supplies the surrounding Projects state.

(function projectMobileDetailModule(global) {
  'use strict';

  function createProjectMobileDetailController(context) {
    const ctx = context || {};

    function notePreviewNode(note) {
      const fullNote = String(note || '');
      const limit = Number(ctx.notePreviewLimit || 0);
      const preview = limit > 0 && fullNote.length > limit
        ? `${fullNote.slice(0, limit).trimEnd()}...`
        : fullNote;
      const wrap = document.createElement('div');
      wrap.className = 'project-mobile-note-preview';
      const text = document.createElement('span');
      text.className = 'project-mobile-note-preview-text';
      text.textContent = preview;
      wrap.appendChild(text);
      if (limit > 0 && fullNote.length > limit) {
        let expanded = false;
        const toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'btn btn-ghost btn-compact project-mobile-note-toggle';
        toggle.dataset.projectMobileNoteToggle = '1';
        toggle.setAttribute('aria-expanded', 'false');
        toggle.textContent = 'Expand';
        toggle.addEventListener('click', () => {
          expanded = !expanded;
          text.textContent = expanded ? fullNote : preview;
          toggle.textContent = expanded ? 'Collapse' : 'Expand';
          toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        });
        ctx.bindProjectRuntimePressable(toggle);
        wrap.appendChild(toggle);
      }
      return wrap;
    }

    function summaryPanel(project, summary) {
      const panel = document.createElement('section');
      panel.className = 'project-mobile-detail-panel';
      const heading = document.createElement('h3');
      heading.textContent = 'Summary';
      panel.appendChild(heading);
      const projectId = String(project && project.id || '');
      if (projectId) {
        const menu = document.createElement('button');
        menu.type = 'button';
        menu.className = 'btn btn-ghost btn-compact project-mobile-summary-menu-btn';
        menu.dataset.projectMobileAction = 'project-menu';
        menu.dataset.projectId = projectId;
        menu.setAttribute('aria-label', `Project actions for ${ctx.projectDisplayName(project)}`);
        menu.textContent = ctx.mobileMenuText || 'Menu';
        ctx.bindProjectRuntimePressable(menu);
        panel.appendChild(menu);
      }
      const meta = document.createElement('div');
      meta.className = 'project-mobile-summary-grid';
      [
        ['Status', project.status || 'active'],
        ['Created', ctx.formatDate(project.created)],
        ['Updated', ctx.formatDate(project.updated)],
        ['Targets', String(Number(ctx.projectCounts(summary).targets || 0))],
      ].forEach(([label, value]) => {
        const item = document.createElement('div');
        item.className = 'project-mobile-summary-item';
        const key = document.createElement('span');
        key.textContent = label;
        const body = document.createElement('strong');
        body.textContent = value;
        item.append(key, body);
        meta.appendChild(item);
      });
      panel.appendChild(meta);
      const labels = ctx.entityLabelValues(project);
      if (labels.length) {
        const chips = document.createElement('div');
        chips.className = 'project-mobile-label-chips';
        labels.forEach((label) => {
          const chip = document.createElement('span');
          chip.className = ctx.entityMetadataChipClass('label');
          chip.textContent = label;
          chips.appendChild(chip);
        });
        panel.appendChild(chips);
      }
      const note = ctx.entityNoteBody(project);
      if (note) panel.appendChild(notePreviewNode(note));
      return panel;
    }

    function panel(titleText, { className = '' } = {}) {
      const section = document.createElement('section');
      section.className = `project-mobile-detail-panel${className ? ` ${className}` : ''}`;
      if (titleText) {
        const heading = document.createElement('h3');
        heading.textContent = titleText;
        section.appendChild(heading);
      }
      return section;
    }

    function sectionHeader(titleText, action = null) {
      const header = document.createElement('div');
      header.className = 'project-mobile-section-header';
      const title = document.createElement('h3');
      title.textContent = titleText;
      header.appendChild(title);
      if (action) header.appendChild(action);
      return header;
    }

    function actionMenu(projectId, label, actions = []) {
      const filteredActions = actions.filter(Boolean);
      if (!filteredActions.length) return null;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-ghost btn-compact project-mobile-row-menu-trigger';
      btn.setAttribute('aria-label', label || 'Row actions');
      btn.dataset.projectMobileAction = 'action-sheet';
      btn.dataset.projectId = String(projectId || '');
      btn.textContent = ctx.mobileMenuText || 'Menu';
      btn._projectMobileActionSheetLabel = label || 'Actions';
      btn._projectMobileActionSheetItems = filteredActions;
      ctx.bindProjectRuntimePressable(btn);
      return btn;
    }

    function closeActionSheet({ restoreFocus = true } = {}) {
      if (typeof global.closeActionSheet === 'function') global.closeActionSheet({ restoreFocus });
    }

    function actionSheetItem(projectId, item) {
      if (item.node) {
        const wrap = document.createElement('div');
        wrap.className = 'project-mobile-action-sheet-field';
        wrap.appendChild(item.node);
        return wrap;
      }
      const btn = ctx.makeProjectButton(
        item.label,
        item.action,
        String(projectId || ''),
        item.variant || 'ghost',
        item.tone || '',
      );
      btn.classList.add('project-mobile-action-sheet-item');
      if (item.tone === 'danger' || item.variant === 'destructive') btn.classList.add('is-danger');
      if (item.disabled) btn.disabled = true;
      if (item.title) btn.title = item.title;
      btn.addEventListener('click', () => closeActionSheet({ restoreFocus: false }));
      Object.entries(item.dataset || {}).forEach(([key, value]) => {
        btn.dataset[key] = String(value || '');
      });
      return btn;
    }

    function openActionSheet(projectId, label, actions = [], returnFocus = null) {
      const filteredActions = actions.filter(Boolean);
      if (!filteredActions.length || typeof global.openActionSheet !== 'function') return;
      global.openActionSheet({
        title: label || 'Actions',
        container: ctx.projectWorkspaceModal || document.body,
        returnFocus,
        items: filteredActions.map(item => ({ node: actionSheetItem(projectId, item) })),
      });
    }

    function contentRow({
      title,
      meta = '',
      detail = '',
      badge = '',
      chips = [],
      action = null,
      accessory = null,
      className = '',
    }) {
      const row = document.createElement('article');
      row.className = `project-mobile-content-row${className ? ` ${className}` : ''}`;
      const main = document.createElement(action ? 'button' : 'div');
      main.className = `project-mobile-content-main${action ? ' control-row' : ''}`;
      if (action) {
        main.type = 'button';
        main.dataset.projectAction = action.action;
        Object.entries(action.dataset || {}).forEach(([key, value]) => {
          main.dataset[key] = String(value || '');
        });
        ctx.bindProjectRuntimePressable(main);
      }
      const titleEl = document.createElement('div');
      titleEl.className = 'project-mobile-content-title';
      titleEl.textContent = String(title || '');
      main.appendChild(titleEl);
      if (meta) {
        const metaEl = document.createElement('div');
        metaEl.className = 'project-mobile-content-meta';
        metaEl.textContent = String(meta || '');
        main.appendChild(metaEl);
      }
      const detailLines = Array.isArray(detail) ? detail : (detail ? [detail] : []);
      detailLines.filter(line => String(line || '').trim()).forEach((line) => {
        const detailEl = document.createElement('div');
        detailEl.className = 'project-mobile-content-detail';
        detailEl.textContent = String(line || '');
        main.appendChild(detailEl);
      });
      if (Array.isArray(chips) && chips.length) {
        const chipWrap = document.createElement('div');
        chipWrap.className = 'project-mobile-row-chips';
        chips.forEach((chip) => {
          const chipEl = document.createElement('span');
          chipEl.className = ctx.entityMetadataChipClass(chip.kind);
          chipEl.textContent = String(chip.label || '');
          chipWrap.appendChild(chipEl);
        });
        main.appendChild(chipWrap);
      }
      row.appendChild(main);
      if (accessory && badge) {
        const accessoryWrap = document.createElement('div');
        accessoryWrap.className = 'project-mobile-row-accessory';
        const badgeEl = document.createElement('span');
        badgeEl.className = `project-mobile-row-badge is-${String(badge || '').trim().toLowerCase()}`;
        badgeEl.textContent = String(badge || '');
        accessoryWrap.append(accessory, badgeEl);
        row.appendChild(accessoryWrap);
      } else if (accessory) row.appendChild(accessory);
      else if (badge) {
        const badgeEl = document.createElement('span');
        badgeEl.className = `project-mobile-row-badge is-${String(badge || '').trim().toLowerCase()}`;
        badgeEl.textContent = String(badge || '');
        row.appendChild(badgeEl);
      }
      return row;
    }

    function emptyPanel(text, actions = []) {
      const empty = ctx.emptyProjectPanel(text);
      const filteredActions = actions.filter(Boolean);
      if (filteredActions.length) {
        const actionWrap = document.createElement('div');
        actionWrap.className = 'project-mobile-empty-actions';
        filteredActions.forEach(action => actionWrap.appendChild(action));
        empty.appendChild(actionWrap);
      }
      return empty;
    }

    function renderDetailsTab(project, summary) {
      const fragment = document.createDocumentFragment();
      fragment.appendChild(summaryPanel(project, summary));

      const targets = ctx.projectTargetItems(summary);
      const projectId = String(project.id || '');
      const addTarget = ctx.makeProjectButton('Add Target', 'new-target', projectId, 'primary');
      addTarget.classList.add('project-mobile-section-action');
      const targetPanel = panel('', { className: 'project-mobile-targets-panel' });
      targetPanel.appendChild(sectionHeader('Targets', addTarget));
      if (!targets.length) {
        targetPanel.appendChild(ctx.emptyProjectPanel('No project targets yet.'));
      } else {
        const list = document.createElement('div');
        list.className = 'project-mobile-content-list';
        targets.forEach((target) => {
          const targetId = String(target.id || '');
          const actions = [];
          if (String(target.review_state || '') === 'pending') {
            actions.push({ label: 'Confirm', action: 'confirm-target', dataset: { targetId, targetValue: target.value } });
            actions.push({ label: 'Dismiss', action: 'dismiss-target', dataset: { targetId, targetValue: target.value } });
          }
          actions.push(
            { label: 'Open in Atlas', action: 'open-project-entity', dataset: { entityId: targetId, entityValue: target.value, entityType: target.type } },
            { label: 'Edit', action: 'edit-target', dataset: { targetId, targetValue: target.value } },
            { label: 'Remove', action: 'delete-target', tone: 'danger', dataset: { targetId, targetValue: target.value } },
          );
          const chips = ctx.entityMetadataChips(target);
          if (String(target.review_state || '') === 'pending') chips.unshift({ label: 'auto', kind: 'label' });
          list.appendChild(contentRow({
            title: target.value || 'Target',
            meta: target.type || 'target',
            detail: target.source_run_id ? `source run ${ctx.shortProjectRunId(target.source_run_id)}` : '',
            chips,
            accessory: actionMenu(projectId, `Target actions for ${target.value || targetId}`, actions),
          }));
        });
        targetPanel.appendChild(list);
      }
      fragment.appendChild(targetPanel);
      return fragment;
    }

    function renderRunsTab(projectId, summary) {
      const fragment = document.createDocumentFragment();
      const comparableRuns = ctx.projectComparableRuns(summary);
      const compareRuns = ctx.makeProjectButton('Compare', 'mobile-compare-runs', projectId, comparableRuns.length >= 2 ? 'secondary' : 'ghost');
      compareRuns.disabled = comparableRuns.length < 2;
      if (compareRuns.disabled) compareRuns.setAttribute('aria-disabled', 'true');
      const linkLastRun = ctx.makeProjectButton('Link last run', 'link-last-run', projectId, 'primary');
      const toolbar = document.createElement('div');
      toolbar.className = 'project-mobile-tab-toolbar';
      toolbar.append(compareRuns, linkLastRun);
      fragment.appendChild(toolbar);

      const allRuns = ctx.projectRunItems(summary);
      const filterActive = ctx.projectTargetFilterActive(projectId, summary);
      if (filterActive && !ctx.projectFindingsLoaded(projectId)) {
        fragment.appendChild(ctx.emptyProjectPanel('Loading target associations...'));
        return fragment;
      }
      const runs = ctx.filteredProjectRuns(projectId, summary);
      if (!allRuns.length) {
        fragment.appendChild(emptyPanel('No linked runs yet.', [
          ctx.makeProjectButton('Link last run', 'link-last-run', projectId, 'primary'),
        ]));
        return fragment;
      }
      if (!runs.length) {
        fragment.appendChild(ctx.emptyProjectPanel('No linked runs match the selected filters.'));
        return fragment;
      }
      const list = document.createElement('div');
      list.className = 'project-mobile-content-list';
      runs.forEach((run) => {
        const runId = String(run.id || '');
        const exit = run.exit_code === null || run.exit_code === undefined ? 'running' : `exit ${run.exit_code}`;
        const findingCount = ctx.projectRunFindingCount(projectId, runId);
        const artifactCount = ctx.projectRunArtifactCount(summary, runId);
        const countParts = [`${findingCount} finding${findingCount === 1 ? '' : 's'}`];
        if (ctx.projectArtifactsVisible()) countParts.push(`${artifactCount} artifact${artifactCount === 1 ? '' : 's'}`);
        const runDetailLines = [
          `${exit}${ctx.metaSeparator || ' - '}${Number(run.output_line_count || 0)} output lines`,
          countParts.join(ctx.metaSeparator || ' - '),
        ];
        const actions = [
          { label: 'Edit metadata', action: 'edit-run-metadata', dataset: { runId, runCommand: run.command } },
          { label: 'Restore', action: 'open-run', dataset: { runId, runCommand: run.command } },
          { label: 'Remove', action: 'unlink-run', tone: 'danger', dataset: { runId, runCommand: run.command } },
        ];
        list.appendChild(contentRow({
          title: run.command || runId || 'Run',
          meta: ctx.formatDate(run.started),
          detail: runDetailLines,
          chips: ctx.entityMetadataChips(run),
          className: 'project-mobile-run-row',
          action: runId ? {
            action: 'open-run',
            dataset: { projectId, runId, runCommand: String(run.command || '') },
          } : null,
          accessory: runId ? actionMenu(projectId, `Run actions for ${run.command || runId}`, actions) : null,
        }));
      });
      fragment.appendChild(list);
      return fragment;
    }

    function findingReviewNode(finding, projectId) {
      const wrap = document.createElement('label');
      wrap.className = 'project-mobile-menu-field';
      const text = document.createElement('span');
      text.textContent = 'Review state';
      const select = ctx.findingReviewControl(finding, projectId);
      wrap.append(text, select);
      return wrap;
    }

    function renderFindingsTab(projectId, summary) {
      const fragment = document.createDocumentFragment();
      if (ctx.projectFindingsLoadingId() === projectId && !ctx.hasProjectFindings(projectId)) {
        fragment.appendChild(ctx.emptyProjectPanel('Loading findings...'));
        return fragment;
      }
      const allFindings = ctx.projectFindingItems(projectId);
      const findings = ctx.filteredProjectFindings(projectId, summary);
      if (!allFindings.length) {
        fragment.appendChild(ctx.emptyProjectPanel('No persisted findings for linked runs or linked entities yet.'));
        return fragment;
      }
      if (!findings.length) {
        fragment.appendChild(ctx.emptyProjectPanel('No findings match selected filters.'));
        return fragment;
      }
      ctx.groupBy(findings, finding => finding.run_command || finding.run_id).forEach((items, runLabel) => {
        const group = document.createElement('section');
        group.className = 'project-mobile-group project-findings-group';
        const collapsed = ctx.projectFindingGroupCollapsed(projectId, runLabel);
        group.classList.toggle('is-collapsed', collapsed);
        const title = document.createElement('button');
        title.type = 'button';
        title.className = 'toggle-btn project-mobile-group-toggle';
        title.dataset.projectFindingGroupToggle = '1';
        title.setAttribute('data-project-finding-group-toggle', '1');
        title.dataset.projectId = projectId;
        title.dataset.projectFindingGroup = runLabel;
        title.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        ctx.bindProjectRuntimePressable(title);
        const caret = document.createElement('span');
        caret.className = 'project-explorer-group-caret';
        caret.setAttribute('aria-hidden', 'true');
        caret.textContent = ctx.caretText || 'v';
        const label = document.createElement('span');
        label.className = 'project-mobile-group-title';
        label.textContent = runLabel;
        const count = document.createElement('span');
        count.className = 'project-mobile-group-count';
        count.textContent = `${items.length} finding${items.length === 1 ? '' : 's'}`;
        title.append(caret, label, count);
        group.appendChild(title);
        const groupBody = document.createElement('div');
        groupBody.className = 'project-mobile-group-body';
        groupBody.hidden = collapsed;
        items.forEach((finding) => {
          const lineIndex = Number(finding.line_number);
          const findingId = String(finding.id || '');
          const metaParts = [
            finding.scope || 'finding',
            ctx.projectFindingTargetText(summary, finding) || ctx.projectTargetLabel(summary, finding.target_id),
            `line ${finding.line_number || 0}`,
          ].filter(Boolean);
          groupBody.appendChild(contentRow({
            title: finding.title || finding.raw_line || 'Finding',
            meta: metaParts.join(ctx.metaSeparator || ' - '),
            detail: finding.raw_line || '',
            badge: finding.review_state || finding.severity || '',
            chips: ctx.entityMetadataChips(finding),
            action: finding.run_id ? {
              action: 'open-finding',
              dataset: {
                projectId,
                runId: String(finding.run_id || ''),
                runCommand: String(finding.run_command || ''),
                lineIndex: Number.isInteger(lineIndex) ? String(lineIndex) : '',
              },
            } : null,
            accessory: findingId ? actionMenu(projectId, `Finding actions for ${finding.title || findingId}`, [
              { node: findingReviewNode(finding, projectId) },
              { label: 'Edit metadata', action: 'edit-finding-metadata', dataset: { findingId } },
            ]) : null,
          }));
        });
        group.appendChild(groupBody);
        fragment.appendChild(group);
      });
      return fragment;
    }

    function renderArtifactsTab(projectId, summary) {
      const fragment = document.createDocumentFragment();
      const allArtifacts = ctx.projectArtifactItems(summary);
      const filterActive = ctx.projectTargetFilterActive(projectId, summary);
      if (filterActive && !ctx.projectFindingsLoaded(projectId)) {
        fragment.appendChild(ctx.emptyProjectPanel('Loading target associations...'));
        return fragment;
      }
      const artifacts = ctx.filteredProjectArtifacts(projectId, summary);
      if (!allArtifacts.length) {
        fragment.appendChild(ctx.emptyProjectPanel('No run artifacts have been captured for this project yet.'));
        return fragment;
      }
      if (!artifacts.length) {
        fragment.appendChild(ctx.emptyProjectPanel('No artifacts match the selected targets.'));
        return fragment;
      }
      ctx.groupBy(artifacts, artifact => artifact.run_id).forEach((items, runId) => {
        const group = document.createElement('section');
        group.className = 'project-mobile-group project-artifacts-group';
        const run = ctx.projectRunById(summary, runId);
        const command = String(run?.command || '').trim();
        const shortId = ctx.shortProjectRunId(runId);
        const collapsed = ctx.projectArtifactGroupCollapsed(projectId, runId);
        group.classList.toggle('is-collapsed', collapsed);
        const title = document.createElement('button');
        title.type = 'button';
        title.className = 'toggle-btn project-mobile-group-toggle';
        title.dataset.projectArtifactGroupToggle = '1';
        title.setAttribute('data-project-artifact-group-toggle', '1');
        title.dataset.projectId = projectId;
        title.dataset.projectArtifactGroup = String(runId || '');
        title.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        ctx.bindProjectRuntimePressable(title);
        const caret = document.createElement('span');
        caret.className = 'project-explorer-group-caret';
        caret.setAttribute('aria-hidden', 'true');
        caret.textContent = ctx.caretText || 'v';
        const label = document.createElement('span');
        label.className = 'project-mobile-group-title';
        label.textContent = `${command || 'Run'}${shortId ? ` (${shortId})` : ''}`;
        const count = document.createElement('span');
        count.className = 'project-mobile-group-count';
        count.textContent = `${items.length} artifact${items.length === 1 ? '' : 's'}`;
        title.append(caret, label, count);
        group.appendChild(title);
        const groupBody = document.createElement('div');
        groupBody.className = 'project-mobile-group-body';
        groupBody.hidden = collapsed;
        items.forEach((artifact) => {
          const artifactId = String(artifact.id || '');
          const status = ctx.projectArtifactStatus(artifact);
          const available = status !== 'missing' && status !== 'disabled';
          groupBody.appendChild(contentRow({
            title: artifact.display_name || artifact.workspace_path || 'Artifact',
            meta: artifact.workspace_path || '',
            detail: ctx.projectArtifactDetailLines(artifact),
            badge: ctx.projectArtifactStatusLabel(artifact),
            chips: ctx.entityMetadataChips(artifact),
            action: available && artifactId ? {
              action: 'artifact-preview',
              dataset: { projectId, artifactId, artifactPath: String(artifact.workspace_path || '') },
            } : null,
            accessory: artifactId ? actionMenu(projectId, `Artifact actions for ${artifact.display_name || artifactId}`, [
              { label: 'Edit metadata', action: 'edit-artifact-metadata', dataset: { artifactId } },
              {
                label: 'Preview',
                action: 'artifact-preview',
                disabled: !available,
                title: available ? 'Preview' : (artifact.file_status_detail || 'Workspace file is unavailable'),
                dataset: { artifactId, artifactPath: artifact.workspace_path },
              },
              {
                label: 'Download',
                action: 'artifact-download',
                disabled: !available,
                title: available ? 'Download' : (artifact.file_status_detail || 'Workspace file is unavailable'),
                dataset: { artifactId, artifactPath: artifact.workspace_path },
              },
            ]) : null,
          }));
        });
        group.appendChild(groupBody);
        fragment.appendChild(group);
      });
      return fragment;
    }

    function renderTabBody(project, summary) {
      if (!ctx.projectMobileDetailBody) return;
      ctx.projectMobileDetailBody.replaceChildren();
      if (!summary) {
        const retryPanel = ctx.emptyProjectPanel('Could not load this project. It may have been deleted.');
        const retry = document.createElement('button');
        retry.type = 'button';
        retry.className = 'btn btn-secondary btn-compact';
        retry.dataset.projectMobileAction = 'retry';
        retry.textContent = 'Retry';
        ctx.bindProjectRuntimePressable(retry);
        retryPanel.appendChild(retry);
        ctx.projectMobileDetailBody.appendChild(retryPanel);
        return;
      }
      if (ctx.projectWorkspaceTab() === 'details') {
        ctx.projectMobileDetailBody.appendChild(renderDetailsTab(project, summary));
        return;
      }
      const projectId = String(project.id || ctx.selectedProjectId() || '');
      if (ctx.projectWorkspaceTab() === 'runs') ctx.projectMobileDetailBody.appendChild(renderRunsTab(projectId, summary));
      else if (ctx.projectWorkspaceTab() === 'entities') ctx.projectMobileDetailBody.appendChild(ctx.renderProjectMobileEntitiesTab(projectId, summary));
      else if (ctx.projectWorkspaceTab() === 'findings') ctx.projectMobileDetailBody.appendChild(renderFindingsTab(projectId, summary));
      else if (ctx.projectWorkspaceTab() === 'artifacts') ctx.projectMobileDetailBody.appendChild(renderArtifactsTab(projectId, summary));
      else if (ctx.projectWorkspaceTab() === 'packages') ctx.projectMobileDetailBody.appendChild(ctx.renderProjectMobilePackagesTab(projectId, summary));
    }

    function renderDetail() {
      if (!ctx.projectMobileDetailView || !ctx.projectMobileDetailBody) return;
      const selectedId = String(ctx.selectedProjectId() || '');
      if (!selectedId) {
        ctx.setProjectMobileView('list');
        return;
      }
      const activeProject = ctx.activeProject();
      const activeId = activeProject && activeProject.id ? String(activeProject.id) : '';
      const summary = ctx.projectSummary(selectedId);
      const project = summary && summary.project && typeof summary.project === 'object'
        ? summary.project
        : ctx.projectRows().find(item => String(item.id || '') === selectedId);
      if (ctx.projectWorkspaceLoading()) {
        ctx.renderProjectMobileDetailTopbar(project || null, activeId);
        if (ctx.projectMobileTabs) ctx.projectMobileTabs.replaceChildren();
        ctx.projectMobileDetailBody.replaceChildren(ctx.emptyProjectPanel('Loading project...'));
        return;
      }
      if (!project) {
        ctx.setProjectMobileView('list');
        ctx.setSelectedProjectId('');
        return;
      }
      ctx.renderProjectMobileDetailTopbar(project, activeId);
      ctx.renderProjectMobileTabs(selectedId, summary);
      renderTabBody(project, summary);
      if (typeof global.enhanceAppSelects === 'function') {
        global.enhanceAppSelects(ctx.projectMobileDetailBody);
      }
      if (
        summary
        && (
          ctx.projectWorkspaceTab() === 'findings'
          || ctx.projectWorkspaceTab() === 'runs'
          || ctx.projectWorkspaceTab() === 'artifacts'
          || ctx.projectTargetFilterActive(selectedId, summary)
          || !ctx.projectFindingsLoaded(selectedId)
        )
      ) {
        ctx.loadProjectFindings(selectedId).catch(() => {});
      }
      if (
        summary
        && ctx.projectWorkspaceTab() === 'findings'
        && ctx.projectFindingsLoaded(selectedId)
        && ctx.projectFindingServerFiltersActive(selectedId, summary)
      ) {
        ctx.loadProjectFilteredFindings(selectedId, summary).catch(() => {});
      }
    }

    return {
      actionMenu,
      closeActionSheet,
      contentRow,
      emptyPanel,
      openActionSheet,
      renderDetail,
    };
  }

  global.DarklabProjectMobileDetail = {
    createProjectMobileDetailController,
  };
})(globalThis);
