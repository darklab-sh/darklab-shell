// Project Findings tab controller.
// Loaded before shell_chrome.js; shell chrome supplies the surrounding Projects state.

(function projectFindingsModule(global) {
  'use strict';

  function createProjectFindingsController(context) {
    const ctx = context || {};

    function reviewStateLabel(value) {
      const normalized = String(value || '').trim();
      const state = (ctx.findingReviewStates || []).find(item => item.value === normalized);
      return state ? state.label : normalized;
    }

    function groupKey(projectId, runLabel) {
      return `${String(projectId || '')}\x1f${String(runLabel || '')}`;
    }

    function groupCollapsed(projectId, runLabel) {
      return ctx.collapsedFindingGroups().has(groupKey(projectId, runLabel));
    }

    function collapsedGroupLabels(projectId = '') {
      const normalized = String(projectId || '');
      if (!normalized) return [];
      const prefix = `${normalized}\x1f`;
      return [...ctx.collapsedFindingGroups()]
        .filter(key => String(key || '').startsWith(prefix))
        .map(key => String(key).slice(prefix.length))
        .filter(Boolean);
    }

    function activeTeamScopeCan(capability) {
      return typeof global.activeTeamScopeCan === 'function'
        ? global.activeTeamScopeCan(capability)
        : true;
    }

    function teamScopeDeniedMessage(action) {
      return typeof global.teamScopeDeniedMessage === 'function'
        ? global.teamScopeDeniedMessage(action)
        : `View-only team members can't ${action}. Switch to Personal or ask for operator access.`;
    }

    function reviewControl(finding, projectId) {
      const control = document.createElement('select');
      const reviewState = String(finding.review_state || 'new');
      const allowed = activeTeamScopeCan('triage_findings');
      control.className = `form-select form-control-compact project-finding-review review-${reviewState}`;
      control.dataset.projectReviewState = '1';
      control.dataset.projectId = String(projectId || '');
      control.dataset.findingId = String(finding.id || '');
      control.dataset.previousReviewState = reviewState;
      control.setAttribute('aria-label', 'Finding review state');
      control.disabled = !allowed;
      if (!allowed) control.title = teamScopeDeniedMessage('triage team findings');
      (ctx.findingReviewStates || []).forEach(({ value, label }) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        control.appendChild(option);
      });
      control.value = reviewState;
      return control;
    }

    function rowAccessory(finding, projectId) {
      const wrap = document.createElement('div');
      wrap.className = 'project-finding-row-actions';
      if (finding && finding.id) {
        const edit = ctx.makeProjectButton('Edit', 'edit-finding-metadata', projectId);
        edit.dataset.findingId = String(finding.id || '');
        wrap.appendChild(edit);
        wrap.appendChild(reviewControl(finding, projectId));
      }
      return wrap;
    }

    function pruneSelection(findings) {
      const selectedFindingIds = ctx.selectedFindingIds();
      selectedFindingIds.forEach((findingId) => {
        if (!findings.some(finding => String(finding && finding.id || '') === findingId)) {
          selectedFindingIds.delete(findingId);
        }
      });
    }

    function renderBulkToolbar(projectId, findings) {
      const selectedFindingIds = ctx.selectedFindingIds();
      const toolbar = document.createElement('div');
      toolbar.className = 'project-finding-bulk-toolbar';
      const selectToggle = ctx.makeProjectButton(ctx.findingSelectMode() ? 'Done' : 'Select', 'toggle-project-finding-select', projectId);
      if (!ctx.findingSelectMode() && !activeTeamScopeCan('triage_findings')) {
        selectToggle.disabled = true;
        selectToggle.title = teamScopeDeniedMessage('triage team findings');
      }
      toolbar.appendChild(selectToggle);
      if (ctx.findingSelectMode()) {
        const count = document.createElement('span');
        count.className = 'project-finding-selection-count';
        count.setAttribute('aria-live', 'polite');
        count.textContent = `${selectedFindingIds.size} selected`;
        const selectAll = ctx.makeProjectButton('Select all', 'select-all-project-findings', projectId);
        selectAll.disabled = !findings.length;
        const clear = ctx.makeProjectButton('Clear', 'clear-project-findings', projectId);
        clear.disabled = !selectedFindingIds.size;
        const apply = document.createElement('select');
        apply.className = 'form-select form-control-compact project-finding-bulk-review';
        apply.dataset.projectFindingBulkReview = '1';
        apply.dataset.projectId = projectId;
        apply.setAttribute('aria-label', 'Bulk review state');
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = 'Set review...';
        apply.appendChild(placeholder);
        (ctx.findingReviewStates || []).forEach(({ value, label }) => {
          const option = document.createElement('option');
          option.value = value;
          option.textContent = label;
        apply.appendChild(option);
      });
        apply.disabled = !selectedFindingIds.size || !activeTeamScopeCan('triage_findings');
        if (!activeTeamScopeCan('triage_findings')) apply.title = teamScopeDeniedMessage('triage team findings');
        const del = ctx.makeProjectButton('Delete', 'bulk-delete-project-findings', projectId, 'destructive');
        del.disabled = !selectedFindingIds.size;
        toolbar.append(count, selectAll, clear, apply, del);
      }
      return toolbar;
    }

    function renderViewToggle(projectId) {
      const current = ctx.findingViewMode();
      const tools = document.createElement('div');
      tools.className = 'project-finding-view-tools';
      const wrap = document.createElement('div');
      wrap.className = 'project-finding-view-toggle';
      wrap.setAttribute('aria-label', 'Findings view');
      [
        { value: 'list', label: 'List' },
        { value: 'board', label: 'Board' },
      ].forEach(({ value, label }) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `toggle-btn project-finding-view-button${current === value ? ' is-active' : ''}`;
        btn.dataset.projectFindingViewMode = value;
        btn.dataset.projectId = projectId;
        btn.setAttribute('aria-pressed', current === value ? 'true' : 'false');
        btn.textContent = label;
        ctx.bindProjectRuntimePressable(btn);
        wrap.appendChild(btn);
      });
      const open = ctx.makeProjectButton('Open board', 'open-findings-board', projectId);
      open.classList.add('project-finding-board-open');
      tools.append(wrap, open);
      return tools;
    }

    function renderPagination(projectId, summary, findings, position = 'bottom') {
      const pagination = ctx.projectFindingPagination?.(projectId, summary) || {};
      const limit = Math.max(1, Number(pagination.limit || 50));
      const offset = Math.max(0, Number(pagination.offset || 0));
      const total = Math.max(0, Number(pagination.total || findings.length || 0));
      const loading = !!pagination.loading;
      if (total <= limit && offset === 0) return null;
      const start = total && findings.length ? offset + 1 : 0;
      const end = total && findings.length ? Math.min(total, offset + findings.length) : 0;
      const wrap = document.createElement('div');
      wrap.className = 'project-finding-pagination project-workspace-pagination';
      wrap.dataset.projectFindingsPagerPosition = position;
      const summaryNode = document.createElement('div');
      summaryNode.className = 'project-workspace-pagination-summary';
      summaryNode.textContent = `${start}-${end} of ${total} findings`;
      const controls = document.createElement('div');
      controls.className = 'project-workspace-pagination-controls';
      const prev = ctx.makeProjectButton('Previous', 'noop', projectId);
      prev.dataset.projectFindingsPage = 'prev';
      prev.dataset.projectFindingsPagerPosition = position;
      prev.disabled = loading || offset <= 0;
      const status = document.createElement('span');
      status.className = 'project-workspace-pagination-status';
      status.textContent = loading ? 'Loading...' : `Page ${Math.floor(offset / limit) + 1}`;
      const next = ctx.makeProjectButton('Next', 'noop', projectId);
      next.dataset.projectFindingsPage = 'next';
      next.dataset.projectFindingsPagerPosition = position;
      next.disabled = loading || offset + findings.length >= total;
      controls.append(prev, status, next);
      wrap.append(summaryNode, controls);
      return wrap;
    }

    function renderFindingRow(projectId, summary, finding) {
      const selectedFindingIds = ctx.selectedFindingIds();
      const selectMode = ctx.findingSelectMode();
      const lineIndex = Number(finding.line_number);
      const findingId = String(finding.id || '');
      const metaParts = [
        finding.run_command || finding.run_id,
        finding.scope || 'finding',
        ctx.projectFindingTargetText(summary, finding) || ctx.projectTargetLabel(summary, finding.target_id),
        `line ${finding.line_number || 0}`,
      ].filter(Boolean);
      const row = ctx.projectItemRow({
        title: finding.title || finding.raw_line,
        meta: metaParts.join(ctx.metaSeparator || ' - '),
        detail: finding.raw_line || '',
        badge: finding.review_state || finding.severity || '',
        chips: ctx.entityMetadataChips(finding),
        accessory: selectMode ? null : rowAccessory(finding, projectId),
        forceArticle: selectMode,
        action: finding.run_id ? {
          action: selectMode ? 'toggle-project-finding-row' : 'open-finding',
          dataset: {
            findingId,
            runId: String(finding.run_id || ''),
            runCommand: String(finding.run_command || ''),
            lineIndex: Number.isInteger(lineIndex) ? String(lineIndex) : '',
          },
        } : null,
      });
      if (selectMode) {
        row.classList.add('project-finding-select-row');
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'project-finding-select-checkbox';
        checkbox.checked = selectedFindingIds.has(findingId);
        checkbox.dataset.projectFindingSelect = findingId;
        checkbox.dataset.projectId = projectId;
        checkbox.setAttribute('aria-label', `Select ${finding.title || findingId}`);
        row.prepend(checkbox);
      }
      return row;
    }

    function renderFindings(container, projectId, summary) {
      const initialPagination = ctx.projectFindingPagination?.(projectId, summary) || {};
      if (!initialPagination.loaded && !ctx.hasFindings(projectId)) {
        container.appendChild(ctx.emptyProjectPanel('Loading findings...'));
        return;
      }
      const allFindings = ctx.projectFindingItems(projectId);
      const findings = ctx.filteredProjectFindings(projectId, summary);
      const pagination = initialPagination;
      const total = Math.max(0, Number(pagination.total || allFindings.length || 0));
      const viewMode = ctx.findingViewMode();
      pruneSelection(findings);
      container.appendChild(renderViewToggle(projectId));
      if (viewMode === 'board' && ctx.findingSelectMode()) {
        ctx.selectedFindingIds().clear();
        ctx.setFindingSelectMode(false);
      }
      if (viewMode !== 'board') {
        container.appendChild(renderBulkToolbar(projectId, findings));
      }
      if (!allFindings.length && total === 0) {
        container.appendChild(ctx.emptyProjectPanel('No persisted findings for linked runs or linked entities yet.'));
        return;
      }
      if (!findings.length) {
        const message = ctx.projectFindingServerFiltersActive(projectId, summary)
          ? 'No findings match the selected filters.'
          : 'No persisted findings for linked runs or linked entities yet.';
        container.appendChild(ctx.emptyProjectPanel(message));
        const pager = renderPagination(projectId, summary, findings, 'bottom');
        if (pager) container.appendChild(pager);
        return;
      }
      const topPager = renderPagination(projectId, summary, findings, 'top');
      if (topPager) container.appendChild(topPager);
      if (viewMode === 'board') {
        ctx.renderProjectFindingBoard(container, projectId, summary, ctx.projectFindingBoard(projectId, summary));
      } else {
        findings.forEach((finding) => {
          container.appendChild(renderFindingRow(projectId, summary, finding));
        });
      }
      const pager = renderPagination(projectId, summary, findings, 'bottom');
      if (pager) container.appendChild(pager);
    }

    return {
      reviewStateLabel,
      groupKey,
      groupCollapsed,
      collapsedGroupLabels,
      reviewControl,
      rowAccessory,
      renderFindings,
    };
  }

  global.DarklabProjectFindings = {
    createProjectFindingsController,
  };
})(globalThis);
