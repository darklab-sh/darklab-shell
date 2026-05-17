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

    function reviewControl(finding, projectId) {
      const control = document.createElement('select');
      const reviewState = String(finding.review_state || 'new');
      control.className = `form-select form-control-compact project-finding-review review-${reviewState}`;
      control.dataset.projectReviewState = '1';
      control.dataset.projectId = String(projectId || '');
      control.dataset.findingId = String(finding.id || '');
      control.dataset.previousReviewState = reviewState;
      control.setAttribute('aria-label', 'Finding review state');
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
        apply.disabled = !selectedFindingIds.size;
        const del = ctx.makeProjectButton('Delete', 'bulk-delete-project-findings', projectId, 'destructive');
        del.disabled = !selectedFindingIds.size;
        toolbar.append(count, selectAll, clear, apply, del);
      }
      return toolbar;
    }

    function renderFindingRow(projectId, summary, finding) {
      const selectedFindingIds = ctx.selectedFindingIds();
      const selectMode = ctx.findingSelectMode();
      const lineIndex = Number(finding.line_number);
      const findingId = String(finding.id || '');
      const metaParts = [
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
      if (ctx.findingsLoadingId() === projectId && !ctx.hasFindings(projectId)) {
        container.appendChild(ctx.emptyProjectPanel('Loading findings...'));
        return;
      }
      const allFindings = ctx.projectFindingItems(projectId);
      const findings = ctx.filteredProjectFindings(projectId, summary);
      pruneSelection(findings);
      container.appendChild(renderBulkToolbar(projectId, findings));
      if (!allFindings.length) {
        container.appendChild(ctx.emptyProjectPanel('No persisted findings for linked runs or linked entities yet.'));
        return;
      }
      if (!findings.length) {
        const message = ctx.projectFindingServerFiltersActive(projectId, summary)
          ? 'No findings match the selected filters.'
          : 'No persisted findings for linked runs or linked entities yet.';
        container.appendChild(ctx.emptyProjectPanel(message));
        return;
      }
      ctx.groupBy(findings, finding => finding.run_command || finding.run_id).forEach((items, runLabel) => {
        const group = document.createElement('section');
        group.className = 'project-explorer-group project-findings-group';
        const collapsed = groupCollapsed(projectId, runLabel);
        group.classList.toggle('is-collapsed', collapsed);
        const title = document.createElement('button');
        title.type = 'button';
        title.className = 'toggle-btn project-explorer-group-toggle';
        title.dataset.projectFindingGroupToggle = '1';
        title.dataset.projectId = projectId;
        title.dataset.projectFindingGroup = runLabel;
        title.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        ctx.bindProjectRuntimePressable(title);
        const caret = document.createElement('span');
        caret.className = 'project-explorer-group-caret';
        caret.setAttribute('aria-hidden', 'true');
        caret.textContent = ctx.groupCaret || '';
        const label = document.createElement('span');
        label.className = 'project-explorer-group-title';
        label.textContent = runLabel;
        const count = document.createElement('span');
        count.className = 'project-explorer-group-count';
        count.textContent = `${items.length} finding${items.length === 1 ? '' : 's'}`;
        title.append(caret, label, count);
        group.appendChild(title);
        const body = document.createElement('div');
        body.className = 'project-explorer-group-body';
        body.hidden = collapsed;
        items.forEach((finding) => {
          body.appendChild(renderFindingRow(projectId, summary, finding));
        });
        group.appendChild(body);
        container.appendChild(group);
      });
    }

    return {
      reviewStateLabel,
      groupKey,
      groupCollapsed,
      reviewControl,
      rowAccessory,
      renderFindings,
    };
  }

  global.DarklabProjectFindings = {
    createProjectFindingsController,
  };
})(globalThis);
