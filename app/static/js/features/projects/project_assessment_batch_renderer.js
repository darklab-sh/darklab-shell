// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Shared desktop/mobile assessment-plan preview and durable batch monitor.

import { hasRetryableBatchProgress } from './project_assessment_batch_retry.js';

const STATUS_LABELS = Object.freeze({
  queued: 'Queued',
  launching: 'Launching',
  running: 'Running',
  canceling: 'Canceling',
  completed: 'Completed',
  succeeded: 'Succeeded',
  failed: 'Failed',
  unavailable: 'Unavailable',
  canceled: 'Canceled',
  skipped: 'Skipped',
  could_not_cancel: 'Could not cancel',
  pending: 'Pending',
});

const REASON_LABELS = Object.freeze({
  already_covered: 'Already covered',
  manual_excluded: 'Manually excluded',
  selection_excluded: 'Outside this selection',
  policy_excluded: 'Policy excluded',
  action_excluded: 'Individual action only',
  credentialed_action: 'Credentialed action',
  feature_unavailable: 'Feature unavailable',
  plan_unavailable: 'Plan unavailable',
  target_unavailable: 'Target unavailable',
  target_changed: 'Target changed',
  evidence_unavailable: 'Evidence unavailable',
  retry_check_missing: 'No longer in this assessment',
});

function element(tag, className = '', text = '') {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== '') node.textContent = String(text);
  return node;
}

function badge(label, tone = '') {
  return element('span', `badge badge-tone-${tone || 'muted'}`, label);
}

function statusTone(status) {
  if (['completed', 'succeeded'].includes(status)) return 'green';
  if (['failed', 'could_not_cancel'].includes(status)) return 'red';
  if (['queued', 'pending', 'launching', 'running', 'canceling'].includes(status)) return 'amber';
  return '';
}

function formatDuration(seconds) {
  const value = Math.max(0, Number(seconds || 0));
  if (value >= 3600) return `${Math.ceil(value / 3600)} hr`;
  if (value >= 60) return `${Math.ceil(value / 60)} min`;
  return `${value} sec`;
}

function formatRefreshAge(value) {
  const timestamp = Date.parse(String(value || ''));
  if (!Number.isFinite(timestamp)) return 'Unknown';
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (seconds >= 86400) return `${Math.floor(seconds / 86400)}d ago`;
  if (seconds >= 3600) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds >= 60) return `${Math.floor(seconds / 60)}m ago`;
  return 'Just now';
}

function shortDigest(value) {
  const digest = String(value || '');
  return digest.length > 24 ? `${digest.slice(0, 15)}…${digest.slice(-8)}` : (digest || 'Unavailable');
}

function summaryCard(label, value, note = '') {
  const card = element('div', 'project-assessment-batch-summary-card');
  card.append(element('span', '', label), element('strong', '', value));
  if (note) card.appendChild(element('small', '', note));
  return card;
}

function createProjectAssessmentBatchRenderer(context, actions) {
  const ctx = context || {};
  const act = actions || {};

  function bind(button, handler) {
    ctx.bindProjectRuntimePressable?.(button, { onActivate: handler });
    return button;
  }

  function heading(title, description) {
    const wrap = element('div', 'project-assessment-section-heading');
    const copy = element('div');
    copy.append(element('h3', '', title), element('p', '', description));
    wrap.appendChild(copy);
    return wrap;
  }

  function actionButton(label, handler, { primary = false, disabled = false } = {}) {
    const button = element('button', `btn ${primary ? 'btn-primary' : 'btn-secondary'}`, label);
    button.type = 'button';
    button.disabled = disabled;
    return bind(button, handler);
  }

  function errorPanel(message) {
    if (!message) return null;
    const panel = element('div', 'project-assessment-batch-error', message);
    panel.setAttribute('role', 'alert');
    return panel;
  }

  function targetRows(detail) {
    return Array.isArray(detail?.target_rollups) ? detail.target_rollups : [];
  }

  function categoryRows(detail) {
    return Array.isArray(detail?.category_rollups) ? detail.category_rollups : [];
  }

  function selectionToolbar(projectId, assessmentId, st, detail) {
    const wrap = element('div', 'project-assessment-batch-selection');
    const targets = targetRows(detail);
    const categories = categoryRows(detail);
    const hints = new Map(
      (st.preview?.summary?.target_review_hints || []).map(item => [String(item?.target_entity_id || ''), item]),
    );

    const targetGroup = element('fieldset', 'project-assessment-batch-selector');
    targetGroup.appendChild(element('legend', '', `Targets (${targets.length})`));
    const targetActions = element('div', 'project-assessment-batch-selector-actions');
    targetActions.append(
      actionButton('Select all', () => act.setSelection(projectId, assessmentId, 'excludedTargetIds', []), { disabled: !targets.length }),
      actionButton('Clear', () => act.setSelection(
        projectId,
        assessmentId,
        'excludedTargetIds',
        targets.map(item => item?.target_entity_id),
      ), { disabled: !targets.length }),
    );
    targetGroup.appendChild(targetActions);
    const targetList = element('div', 'project-assessment-batch-option-list nice-scroll');
    targets.forEach((target) => {
      const id = String(target?.target_entity_id || '');
      const row = element('label', 'project-assessment-batch-option');
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = !st.selection.excludedTargetIds.has(id);
      input.addEventListener('change', () => {
        const excluded = new Set(st.selection.excludedTargetIds);
        if (input.checked) excluded.delete(id); else excluded.add(id);
        act.setSelection(projectId, assessmentId, 'excludedTargetIds', [...excluded]);
      });
      const copy = element('span');
      copy.append(
        element('strong', '', target?.target_value || id),
        element('small', '', `${target?.target_type || 'target'} · ${Number(target?.total_checks || 0)} checks`),
      );
      row.append(input, copy);
      const hint = hints.get(id);
      if (hint) {
        const hintLabel = (hint?.hints || []).map(item => item?.reason).filter(Boolean).join(' ');
        const marker = badge('Review scope', 'amber');
        if (hintLabel) marker.title = hintLabel;
        row.appendChild(marker);
      }
      targetList.appendChild(row);
    });
    targetGroup.appendChild(targetList);

    const categoryGroup = element('fieldset', 'project-assessment-batch-selector');
    categoryGroup.appendChild(element('legend', '', `Categories (${categories.length})`));
    const categoryActions = element('div', 'project-assessment-batch-selector-actions');
    categoryActions.append(
      actionButton('Select all', () => act.setSelection(projectId, assessmentId, 'excludedCategories', []), { disabled: !categories.length }),
      actionButton('Clear', () => act.setSelection(
        projectId,
        assessmentId,
        'excludedCategories',
        categories.map(item => item?.category),
      ), { disabled: !categories.length }),
    );
    categoryGroup.appendChild(categoryActions);
    const categoryList = element('div', 'project-assessment-batch-option-list');
    categories.forEach((category) => {
      const value = String(category?.category || '');
      const row = element('label', 'project-assessment-batch-option');
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = !st.selection.excludedCategories.has(value);
      input.addEventListener('change', () => {
        const excluded = new Set(st.selection.excludedCategories);
        if (input.checked) excluded.delete(value); else excluded.add(value);
        act.setSelection(projectId, assessmentId, 'excludedCategories', [...excluded]);
      });
      const copy = element('span');
      copy.append(
        element('strong', '', value || 'Uncategorized'),
        element('small', '', `${Number(category?.applicable_checks || 0)} applicable checks`),
      );
      row.append(input, copy);
      categoryList.appendChild(row);
    });
    categoryGroup.appendChild(categoryList);
    wrap.append(targetGroup, categoryGroup);
    return wrap;
  }

  function settings(projectId, assessmentId, st) {
    const box = element('div', 'project-assessment-batch-settings');
    const standard = element('label', 'project-assessment-batch-standard');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = st.selection.includeStandard;
    checkbox.addEventListener('change', () => {
      act.setSelection(projectId, assessmentId, 'includeStandard', checkbox.checked);
    });
    const copy = element('span');
    copy.append(
      element('strong', '', 'Include standard checks'),
      element('small', '', 'Off by default. Standard commands require a separate confirmation before start.'),
    );
    standard.append(checkbox, copy);
    box.appendChild(standard);

    const details = element('details', 'project-assessment-batch-advanced');
    const summary = element('summary', '', 'Batch limits');
    details.appendChild(summary);
    const controls = element('div', 'project-assessment-batch-limit-grid');
    const selectField = (label, key, values, current) => {
      const field = element('label');
      field.appendChild(element('span', '', label));
      const select = element('select', 'form-select');
      values.forEach((value) => {
        const option = element('option', '', value);
        option.value = String(value);
        option.selected = Number(current) === Number(value);
        select.appendChild(option);
      });
      select.addEventListener('change', () => {
        act.setSelection(projectId, assessmentId, key, Number(select.value));
      });
      field.appendChild(select);
      return field;
    };
    controls.append(
      selectField('Command limit', 'itemLimit', [128, 256, 512], st.selection.itemLimit),
      selectField('This batch', 'maxParallel', [1, 2, 3, 4, 5, 6, 7, 8], st.selection.maxParallel),
      selectField('Your batches', 'maxOwnerParallel', [4, 8, 16, 24, 32], st.selection.maxOwnerParallel),
      selectField('All batches', 'maxInstanceParallel', [8, 16, 32, 48, 64], st.selection.maxInstanceParallel),
    );
    details.appendChild(controls);
    box.appendChild(details);
    return box;
  }

  function previewSummary(preview) {
    const summary = preview?.summary || {};
    const grid = element('div', 'project-assessment-batch-summary-grid');
    grid.append(
      summaryCard('Commands', preview?.selected_item_count || 0, `${preview?.candidate_item_count || 0} eligible`),
      summaryCard('Targets', summary?.selected_target_count || 0),
      summaryCard('Potential coverage', summary?.potential_covered_check_count || 0, 'Checks still prove coverage independently'),
      summaryCard(
        'Estimated window',
        `${formatDuration(summary?.estimated_min_seconds)}–${formatDuration(summary?.estimated_max_seconds)}`,
        summary?.estimate_label || 'Estimate only',
      ),
    );
    return grid;
  }

  function exclusions(summary) {
    const reasons = Object.entries(summary?.reason_counts || {}).filter(([, count]) => Number(count) > 0);
    if (!reasons.length) return null;
    const panel = element('div', 'project-assessment-batch-exclusions');
    panel.appendChild(element('strong', '', 'Not included in this plan'));
    const list = element('div', 'project-assessment-batch-chip-list');
    reasons.forEach(([reason, count]) => {
      list.appendChild(badge(`${REASON_LABELS[reason] || reason}: ${count}`, 'muted'));
    });
    panel.appendChild(list);
    return panel;
  }

  function nucleiPreflight(summary) {
    const preflight = summary?.nuclei_preflight;
    if (!preflight) return null;
    const state = String(preflight.state || 'unavailable');
    const panel = element('aside', `project-assessment-batch-preflight is-${state}`);
    const top = element('div', 'project-assessment-batch-preflight-heading');
    top.append(
      element('strong', '', 'Managed Nuclei template preflight'),
      badge(state, preflight.launchable ? (state === 'stale' ? 'amber' : 'green') : 'red'),
    );
    const grid = element('div', 'project-assessment-batch-preflight-grid');
    const detail = (label, value, { code = false } = {}) => {
      const item = element('div');
      item.append(element('span', '', label), element(code ? 'code' : 'strong', '', value));
      return item;
    };
    grid.append(
      detail('Planned commands', Number(preflight.command_count || 0)),
      detail('Template release', preflight.release_version || 'Unknown'),
      detail('Refreshed', formatRefreshAge(preflight.refreshed_at)),
      detail('Validation', preflight.validation_state || 'not run'),
      detail('Nuclei version', preflight.nuclei_version || 'Unknown'),
      detail('Snapshot digest', shortDigest(preflight.content_digest), { code: true }),
    );
    panel.append(top, grid);
    if (state === 'stale') {
      panel.appendChild(element(
        'p',
        '',
        'The cache passed validation but is older than the maintained freshness window. Update it and rebuild the preview when network access is available, or explicitly continue with this pinned snapshot.',
      ));
    } else if (!preflight.launchable) {
      panel.appendChild(element(
        'p',
        '',
        "Nuclei work can't start until an operator repairs or updates the managed template cache and rebuilds this preview.",
      ));
    }
    if (ctx.canRunCommands?.() === false || preflight.refresh_enabled === false) {
      panel.appendChild(element(
        'p',
        '',
        preflight.operator_action || 'Ask an operator with Run commands access to update the managed templates.',
      ));
    }
    return panel;
  }

  function commandItem(item, { monitor = false } = {}) {
    const row = element('article', 'project-assessment-batch-command');
    const top = element('div', 'project-assessment-batch-command-heading');
    const title = element('div');
    title.append(
      element('strong', '', item?.action?.id || item?.action_id || 'Command'),
      element('small', '', `${item?.target?.value || 'Project target'} · ${item?.target?.type || 'target'}`),
    );
    const policy = String(item?.policy_level || 'safe');
    const previewLabel = item?.selected === false ? `${policy} · not selected` : policy;
    top.append(title, badge(
      monitor ? (STATUS_LABELS[item?.status] || item?.status || 'Pending') : previewLabel,
      monitor ? statusTone(item?.status) : (item?.selected === false ? 'muted' : (policy === 'standard' ? 'amber' : 'green')),
    ));
    row.append(top, element('code', 'project-assessment-batch-command-text', item?.display_command || ''));
    const meta = [];
    if (monitor) {
      meta.push(`Attempt ${Number(item?.attempt || 1)}`);
      meta.push(`${Number(item?.check_count || 0)} mapped checks`);
      if (item?.reason_code) meta.push(`Reason: ${item.reason_code}`);
    } else {
      meta.push(`${Number(item?.check_mappings?.length || 0)} mapped checks`);
      if (item?.bounds?.summary) meta.push(item.bounds.summary);
      if (item?.duration_bound_seconds) meta.push(`Up to ${formatDuration(item.duration_bound_seconds)}`);
    }
    row.appendChild(element('small', 'project-assessment-batch-command-meta', meta.filter(Boolean).join(' · ')));
    if (monitor && item?.run_id && typeof ctx.openHistoryRunDetails === 'function') {
      const open = actionButton('Open run', () => ctx.openHistoryRunDetails({
        id: String(item.run_id),
        command: String(item?.display_command || ''),
      }));
      open.classList.add('btn-compact');
      open.dataset.assessmentBatchFocusKey = `open-run:${String(item.run_id)}`;
      row.appendChild(open);
    }
    return row;
  }

  function commandList(projectId, assessmentId, st, { monitor = false } = {}) {
    const items = monitor ? st.batchItems : st.previewItems;
    const list = element('div', 'project-assessment-batch-command-list');
    items.forEach(item => list.appendChild(commandItem(item, { monitor })));
    const cursor = monitor ? st.batchItemsCursor : st.previewItemsCursor;
    const loading = monitor ? st.batchItemsLoading : st.previewItemsLoading;
    if (cursor !== null) {
      const more = actionButton(
        loading ? 'Loading…' : 'Load more commands',
        () => monitor
          ? act.loadMoreBatchItems(projectId, assessmentId)
          : act.loadMorePreviewItems(projectId, assessmentId),
        { disabled: loading },
      );
      more.classList.add('btn-compact');
      list.appendChild(more);
    }
    return list;
  }

  function renderPlanner(projectId, assessment, detail, st) {
    const body = element('div', 'project-assessment-batch-planner');
    body.append(
      element('p', 'project-assessment-batch-guidance', 'Safe checks are selected by default. Intrusive, destructive, credentialed, ZAP, OAST, takeover-confirmation, and Schemathesis actions stay individual.'),
      selectionToolbar(projectId, assessment.id, st, detail),
      settings(projectId, assessment.id, st),
    );
    const selectedTargets = targetRows(detail).length - st.selection.excludedTargetIds.size;
    const selectedCategories = categoryRows(detail).length - st.selection.excludedCategories.size;
    const emptySelection = selectedTargets <= 0 || selectedCategories <= 0;
    const previewActions = element('div', 'project-assessment-batch-actions');
    previewActions.appendChild(actionButton(
      st.previewing ? 'Building preview…' : (st.preview ? 'Refresh preview' : 'Preview assessment plan'),
      () => act.createPreview(projectId, assessment.id),
      { primary: true, disabled: st.previewing || st.starting || emptySelection },
    ));
    body.appendChild(previewActions);
    if (emptySelection) body.appendChild(element('p', 'project-assessment-batch-selection-note', 'Select at least one target and category to build a plan.'));
    if (st.previewDirty) {
      body.appendChild(element('p', 'project-assessment-batch-stale', 'Selection changed. Refresh the preview before starting.'));
    }
    if (!st.preview) return body;
    const retry = Boolean(st.preview?.source_batch_id);
    if (retry) {
      body.appendChild(element(
        'p',
        'project-assessment-batch-guidance',
        'This retry preview rebuilds only failed, unavailable, interrupted, or unlaunched source work. Commands that already succeeded remain unchanged.',
      ));
    }
    body.append(previewSummary(st.preview));
    const preflight = nucleiPreflight(st.preview.summary);
    if (preflight) body.appendChild(preflight);
    const excluded = exclusions(st.preview.summary);
    if (excluded) body.appendChild(excluded);
    const commandHeading = element('div', 'project-assessment-batch-command-list-heading');
    commandHeading.append(
      element('strong', '', 'Exact commands'),
      element('small', '', `${st.previewItems.length} of ${st.preview.candidate_item_count || 0} shown`),
    );
    body.append(commandHeading, commandList(projectId, assessment.id, st));
    const startActions = element('div', 'project-assessment-batch-actions');
    const canRun = ctx.canRunCommands?.() !== false;
    const emptyRetry = retry && Number(st.preview?.selected_item_count || 0) === 0;
    const nucleiBlocked = st.preview?.summary?.nuclei_preflight?.launchable === false;
    const nucleiSummary = st.preview?.summary?.nuclei_preflight || null;
    const canRefreshNuclei = canRun
      && nucleiSummary
      && nucleiSummary.refresh_enabled !== false
      && (nucleiBlocked || nucleiSummary.state === 'stale');
    if (canRefreshNuclei) {
      startActions.appendChild(actionButton(
        st.refreshingTemplates ? 'Updating templates…' : 'Update templates and rebuild preview',
        button => act.refreshNucleiTemplates(projectId, assessment.id, button),
        {
          primary: nucleiBlocked,
          disabled: st.refreshingTemplates || st.starting || st.previewDirty,
        },
      ));
    }
    const start = actionButton(
      st.starting ? 'Starting…' : (retry ? 'Start retry' : 'Run assessment plan'),
      button => act.startBatch(projectId, assessment.id, button),
      {
        primary: true,
        disabled: st.starting || st.refreshingTemplates || st.previewDirty || !canRun || emptyRetry || nucleiBlocked,
      },
    );
    if (!canRun) start.title = 'View-only team members can preview plans but cannot start commands.';
    startActions.appendChild(start);
    if (emptyRetry) startActions.appendChild(element('small', '', 'Nothing can be retried from this batch right now.'));
    if (nucleiBlocked) startActions.appendChild(element('small', '', 'Nuclei template preflight must pass before this plan can start.'));
    if (!canRun) startActions.appendChild(element('small', '', 'Read-only: ask for operator access to start this batch.'));
    body.appendChild(startActions);
    return body;
  }

  function progressGrid(batch) {
    const progress = batch?.progress || {};
    const grid = element('div', 'project-assessment-batch-summary-grid');
    grid.append(
      summaryCard('Settled', `${Number(progress?.settled || 0)} / ${Number(progress?.total || batch?.item_count || 0)}`),
      summaryCard('Active', Number(progress?.running || 0) + Number(progress?.launching || 0)),
      summaryCard('Succeeded', Number(progress?.succeeded || 0)),
      summaryCard('Needs attention', Number(progress?.failed || 0) + Number(progress?.unavailable || 0) + Number(progress?.could_not_cancel || 0)),
    );
    return grid;
  }

  function activity(st) {
    if (!st.events.length) return null;
    const panel = element('div', 'project-assessment-batch-activity');
    panel.appendChild(element('strong', '', 'Recent activity'));
    const list = element('ol');
    panel.appendChild(list);
    st.events.slice(-20).reverse().forEach((event) => {
      const label = STATUS_LABELS[event?.status] || event?.event_type || 'Update';
      const parts = [label];
      if (event?.item_ordinal !== null && event?.item_ordinal !== undefined) parts.push(`command ${Number(event.item_ordinal) + 1}`);
      if (event?.reason_code) parts.push(event.reason_code);
      const item = element('li');
      item.append(element('span', '', parts.join(' · ')), element('time', '', ctx.formatDate?.(event?.created) || event?.created || ''));
      list.appendChild(item);
    });
    return panel;
  }

  function batchDiagnostics(batch) {
    const diagnostics = Array.isArray(batch?.diagnostics) ? batch.diagnostics : [];
    const diagnosis = diagnostics.find(item => item?.code === 'nuclei_template_loading_failed');
    if (!diagnosis) return null;
    const panel = element('aside', 'project-assessment-batch-diagnostic is-error');
    const top = element('div', 'project-assessment-batch-diagnostic-heading');
    top.append(
      element('strong', '', diagnosis?.title || "Nuclei couldn't load the managed templates"),
      badge(`${Number(diagnosis?.affected_command_count || 0)} affected`, 'red'),
    );
    panel.append(top, element('p', '', diagnosis?.message || 'Update the managed templates before retrying these commands.'));
    return panel;
  }

  function renderMonitor(projectId, assessment, st) {
    const batch = st.batch;
    const body = element('div', 'project-assessment-batch-monitor');
    const top = element('div', 'project-assessment-batch-monitor-heading');
    const title = element('div');
    title.append(
      element('strong', '', 'Assessment batch'),
      element('small', '', `${batch?.batch_id || ''} · started ${ctx.formatDate?.(batch?.created) || batch?.created || 'recently'}${batch?.source_batch_id ? ` · retry of ${batch.source_batch_id}` : ''}`),
    );
    top.append(title, badge(STATUS_LABELS[batch?.status] || batch?.status || 'Unknown', statusTone(batch?.status)));
    body.append(top, progressGrid(batch));
    if (batch?.status === 'canceling') {
      body.appendChild(element('p', 'project-assessment-batch-canceling', 'Cancellation was requested. No new commands will start; active commands may still be settling.'));
    }
    const progress = batch?.progress || {};
    const rollup = [
      ['Pending', progress.pending],
      ['Launching', progress.launching],
      ['Running', progress.running],
      ['Succeeded', progress.succeeded],
      ['Failed', progress.failed],
      ['Unavailable', progress.unavailable],
      ['Canceled', progress.canceled],
      ['Skipped', progress.skipped],
      ['Could not cancel', progress.could_not_cancel],
    ].filter(([, value]) => Number(value) > 0);
    const chips = element('div', 'project-assessment-batch-chip-list');
    rollup.forEach(([label, value]) => chips.appendChild(badge(`${label}: ${value}`, 'muted')));
    body.appendChild(chips);
    const diagnosticPanel = batchDiagnostics(batch);
    if (diagnosticPanel) body.appendChild(diagnosticPanel);

    if (st.batches.length > 1) {
      const field = element('label', 'project-assessment-batch-history-select');
      field.appendChild(element('span', '', 'Assessment batch'));
      const select = element('select', 'form-select');
      st.batches.forEach((item) => {
        const option = element('option', '', `${STATUS_LABELS[item?.status] || item?.status} · ${ctx.formatDate?.(item?.created) || item?.created || item?.batch_id}`);
        option.value = String(item?.batch_id || '');
        option.selected = option.value === st.selectedBatchId;
        select.appendChild(option);
      });
      select.addEventListener('change', () => act.selectBatch(projectId, assessment.id, select.value));
      select.dataset.assessmentBatchFocusKey = 'batch-history';
      field.appendChild(select);
      body.appendChild(field);
    }

    const commandHeading = element('div', 'project-assessment-batch-command-list-heading');
    commandHeading.append(
      element('strong', '', 'Commands'),
      element('small', '', `${st.batchItems.length} of ${batch?.item_count || 0} shown`),
    );
    body.append(commandHeading, commandList(projectId, assessment.id, st, { monitor: true }));
    const activityPanel = activity(st);
    if (activityPanel) body.appendChild(activityPanel);

    const controls = element('div', 'project-assessment-batch-actions');
    const active = ['queued', 'running'].includes(String(batch?.status || ''));
    if (active) {
      const canRun = ctx.canRunCommands?.() !== false;
      const cancel = actionButton(
        st.canceling ? 'Canceling…' : 'Cancel batch',
        button => act.cancelBatch(projectId, assessment.id, button),
        { disabled: st.canceling || !canRun },
      );
      cancel.dataset.assessmentBatchFocusKey = 'cancel-batch';
      if (!canRun) cancel.title = 'View-only team members cannot cancel assessment batches.';
      controls.appendChild(cancel);
    } else if (!['canceling'].includes(String(batch?.status || '')) && assessment?.status === 'active') {
      if (hasRetryableBatchProgress(batch)) {
        const templateDiagnosis = (Array.isArray(batch?.diagnostics) ? batch.diagnostics : [])
          .find(item => item?.recommended_action === 'refresh_nuclei_templates_and_retry');
        const canRun = ctx.canRunCommands?.() !== false;
        if (templateDiagnosis && canRun) {
          controls.appendChild(actionButton(
            st.previewing || st.refreshingTemplates
              ? 'Updating templates and building retry…'
              : 'Update templates and retry failed commands',
            button => act.updateTemplatesAndRetryBatch(projectId, assessment.id, button),
            {
              primary: true,
              disabled: st.previewing || st.refreshingTemplates || st.starting,
            },
          ));
        } else {
          controls.appendChild(actionButton(
            st.previewing ? 'Building retry preview…' : 'Retry failed or unfinished',
            () => act.retryBatch(projectId, assessment.id),
            { primary: true, disabled: st.previewing },
          ));
        }
      }
      controls.appendChild(actionButton('New assessment plan', () => act.newPlan(projectId, assessment.id)));
    }
    if (controls.childElementCount) body.appendChild(controls);
    return body;
  }

  function render(projectId, assessment, detail, st) {
    const section = element('section', 'project-assessment-section project-assessment-batch');
    section.dataset.projectId = String(projectId || '');
    section.dataset.assessmentId = String(assessment?.id || '');
    const active = assessment?.status === 'active';
    section.appendChild(heading(
      active ? 'Run assessment plan' : 'Assessment batch history',
      active
        ? 'Preview and run a bounded set of safe assessment commands, then monitor durable progress here.'
        : 'Review the commands and durable outcome from this cycle without starting new work.',
    ));
    const error = errorPanel(st.error);
    if (error) section.appendChild(error);
    if (st.loading && !st.loaded) {
      section.appendChild(ctx.emptyProjectPanel?.('Loading assessment batches…') || element('p', '', 'Loading assessment batches…'));
      return section;
    }
    if (st.planning || !st.batch) {
      section.appendChild(renderPlanner(projectId, assessment, detail, st));
      return section;
    }
    section.appendChild(renderMonitor(projectId, assessment, st));
    return section;
  }

  return { render };
}

export { createProjectAssessmentBatchRenderer };
