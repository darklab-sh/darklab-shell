// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Durable workflow execution requests and Recent Executions rendering.

const ACTIVE_WORKFLOW_EXECUTION_STATUSES = new Set(['queued', 'running', 'canceling']);

async function workflowExecutionRequest(apiFetch, url, options = undefined, fallback = 'Workflow request failed') {
  const response = await apiFetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || fallback);
  return payload;
}

function createWorkflowExecution(apiFetch, workflow, values, tabId = '') {
  return workflowExecutionRequest(apiFetch, '/workflow-executions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      workflow_id: workflow.id,
      inputs: values || {},
      tab_id: tabId || '',
    }),
  }, 'Failed to start workflow');
}

async function listWorkflowExecutions(apiFetch, limit = 10, workflowId = '') {
  const workflowFilter = String(workflowId || '').trim();
  const filterQuery = workflowFilter ? `&workflow_id=${encodeURIComponent(workflowFilter)}` : '';
  const payload = await workflowExecutionRequest(
    apiFetch,
    `/workflow-executions?limit=${Math.max(1, Math.min(Number(limit) || 10, 100))}${filterQuery}`,
    undefined,
    'Failed to load workflow executions',
  );
  return Array.isArray(payload.executions) ? payload.executions : [];
}

function getWorkflowExecution(apiFetch, executionId) {
  return workflowExecutionRequest(
    apiFetch,
    `/workflow-executions/${encodeURIComponent(executionId)}`,
    undefined,
    'Workflow execution not found',
  );
}

function cancelWorkflowExecution(apiFetch, executionId) {
  return workflowExecutionRequest(
    apiFetch,
    `/workflow-executions/${encodeURIComponent(executionId)}/cancel`,
    { method: 'POST' },
    'Failed to cancel workflow execution',
  );
}

function workflowExecutionIsActive(execution) {
  return ACTIVE_WORKFLOW_EXECUTION_STATUSES.has(String(execution?.status || '').toLowerCase());
}

function workflowTimestampMs(value) {
  const raw = String(value || '').trim();
  if (!raw) return 0;
  const normalized = raw.includes('T') ? raw : raw.replace(' ', 'T');
  const zoned = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized) ? normalized : `${normalized}Z`;
  const parsed = Date.parse(zoned);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatWorkflowExecutionElapsed(execution, nowMs = Date.now()) {
  const startedMs = workflowTimestampMs(execution?.created);
  if (!startedMs) return 'elapsed unavailable';
  const finishedMs = workflowTimestampMs(execution?.finished);
  const elapsedSeconds = Math.max(0, Math.floor(((finishedMs || nowMs) - startedMs) / 1000));
  if (elapsedSeconds < 60) return `${elapsedSeconds}s`;
  const minutes = Math.floor(elapsedSeconds / 60);
  const seconds = elapsedSeconds % 60;
  if (minutes < 60) return `${minutes}m ${String(seconds).padStart(2, '0')}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${String(minutes % 60).padStart(2, '0')}m`;
}

function workflowExecutionStatusTone(status) {
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'completed' || normalized === 'succeeded') return 'badge-tone-green';
  if (normalized === 'failed') return 'badge-tone-red';
  if (ACTIVE_WORKFLOW_EXECUTION_STATUSES.has(normalized) || normalized === 'launching') {
    return 'badge-tone-amber';
  }
  return 'badge-tone-muted';
}

function workflowExecutionStatusLabel(status) {
  const normalized = String(status || 'unknown').replace(/_/g, ' ');
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function bindWorkflowExecutionButton(button, onActivate, bindPressable) {
  const activate = async () => {
    if (button.disabled) return;
    button.disabled = true;
    try {
      await onActivate();
    } finally {
      if (button.isConnected) button.disabled = false;
    }
  };
  if (typeof bindPressable === 'function') {
    bindPressable(button, { onActivate: activate, refocusComposer: false });
  } else {
    button.addEventListener('click', activate);
  }
}

function workflowExecutionActionButton(label, className, title, onActivate, bindPressable) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = className;
  button.textContent = label;
  button.title = title;
  button.setAttribute('aria-label', title);
  bindWorkflowExecutionButton(button, onActivate, bindPressable);
  return button;
}

function renderWorkflowExecutionStep(step, options) {
  const row = document.createElement('li');
  row.className = 'workflow-execution-step';

  const summary = document.createElement('div');
  summary.className = 'workflow-execution-step-summary';
  const name = document.createElement('span');
  name.className = 'workflow-execution-step-name';
  name.textContent = String(step?.step_id || 'step');
  const status = document.createElement('span');
  status.className = `badge ${workflowExecutionStatusTone(step?.status)}`;
  status.textContent = workflowExecutionStatusLabel(step?.status);
  summary.append(name, status);

  if (step?.selected_transition) {
    const transition = document.createElement('span');
    transition.className = 'workflow-execution-transition';
    const reason = step.transition_reason ? ` (${String(step.transition_reason).replace(/_/g, ' ')})` : '';
    transition.textContent = `to ${step.selected_transition}${reason}`;
    summary.appendChild(transition);
  }

  const captureNames = Array.isArray(step?.capture_names) ? step.capture_names.filter(Boolean) : [];
  if (captureNames.length) {
    const captures = document.createElement('span');
    captures.className = 'workflow-execution-captures';
    captures.textContent = `Captured: ${captureNames.join(', ')}`;
    summary.appendChild(captures);
  }
  row.appendChild(summary);

  const runId = String(step?.run_id || '').trim();
  if (runId) {
    const run = document.createElement('div');
    run.className = 'workflow-execution-run';
    const runLabel = document.createElement('code');
    runLabel.textContent = runId;
    run.appendChild(runLabel);
    if (step.status === 'running' || step.status === 'launching') {
      run.appendChild(workflowExecutionActionButton(
        'Attach',
        'btn btn-secondary btn-compact',
        `Attach to run ${runId}`,
        () => options.onAttachRun?.(runId),
        options.bindPressable,
      ));
    } else {
      run.appendChild(workflowExecutionActionButton(
        'Open',
        'btn btn-ghost btn-compact',
        `Open run ${runId}`,
        () => options.onOpenRun?.(runId),
        options.bindPressable,
      ));
    }
    row.appendChild(run);
  }
  return row;
}

function renderWorkflowExecutionRow(execution, options) {
  const row = document.createElement('article');
  const active = workflowExecutionIsActive(execution);
  const accent = execution?.status === 'completed'
    ? ' row-accent-green'
    : (active ? ' row-accent-amber' : '');
  row.className = `workflow-execution-row panel-row${accent}`;
  row.dataset.workflowExecutionId = String(execution?.id || '');
  row.tabIndex = -1;

  const header = document.createElement('div');
  header.className = 'workflow-execution-row-header';
  const identity = document.createElement('div');
  identity.className = 'workflow-execution-identity';
  const title = document.createElement('h3');
  title.textContent = String(execution?.title || 'Workflow');
  const id = document.createElement('code');
  id.textContent = String(execution?.id || '');
  identity.append(title, id);
  const badge = document.createElement('span');
  badge.className = `badge ${workflowExecutionStatusTone(execution?.status)}`;
  badge.textContent = workflowExecutionStatusLabel(execution?.status);
  header.append(identity, badge);
  row.appendChild(header);

  const meta = document.createElement('div');
  meta.className = 'workflow-execution-meta';
  const current = execution?.current_step_id
    ? `Current step: ${execution.current_step_id}`
    : 'No active step';
  meta.textContent = `${current} | Elapsed: ${formatWorkflowExecutionElapsed(execution, options.nowMs)}`;
  row.appendChild(meta);

  if (execution?.failure_detail) {
    const failure = document.createElement('div');
    failure.className = 'workflow-execution-failure';
    failure.textContent = String(execution.failure_detail);
    row.appendChild(failure);
  }

  const steps = Array.isArray(execution?.steps) ? execution.steps : [];
  if (steps.length) {
    const stepList = document.createElement('ol');
    stepList.className = 'workflow-execution-steps';
    steps.forEach(step => stepList.appendChild(renderWorkflowExecutionStep(step, options)));
    row.appendChild(stepList);
  }

  if (active) {
    const actions = document.createElement('div');
    actions.className = 'workflow-execution-actions';
    actions.appendChild(workflowExecutionActionButton(
      'Cancel',
      'btn btn-destructive btn-warning btn-compact',
      `Cancel ${execution?.title || 'workflow execution'}`,
      () => options.onCancel?.(execution),
      options.bindPressable,
    ));
    row.appendChild(actions);
  }
  return row;
}

function renderWorkflowExecutionsSection(container, state = {}, options = {}) {
  const previous = container.querySelector('.workflow-executions');
  const section = document.createElement('section');
  section.className = 'workflow-executions';
  section.setAttribute('aria-labelledby', 'workflow-executions-title');

  const header = document.createElement('div');
  header.className = 'workflow-executions-header';
  const heading = document.createElement('h2');
  heading.id = 'workflow-executions-title';
  heading.textContent = 'Recent executions';
  const refresh = workflowExecutionActionButton(
    '↻',
    'btn btn-ghost btn-icon-only btn-compact workflow-executions-refresh',
    'Refresh workflow executions',
    () => options.onRefresh?.(),
    options.bindPressable,
  );
  header.append(heading, refresh);
  section.appendChild(header);

  const status = document.createElement('div');
  status.className = 'workflow-executions-status';
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  const executions = Array.isArray(state.executions) ? state.executions : [];
  if (state.loading && !executions.length) status.textContent = 'Loading executions...';
  else if (state.error) status.textContent = String(state.error);
  else if (!executions.length) status.textContent = 'No workflow executions yet.';
  else status.textContent = `${executions.length} recent execution${executions.length === 1 ? '' : 's'}`;
  section.appendChild(status);

  if (executions.length) {
    const list = document.createElement('div');
    list.className = 'workflow-execution-list';
    executions.forEach(execution => list.appendChild(renderWorkflowExecutionRow(execution, options)));
    section.appendChild(list);
  }
  if (previous) previous.replaceWith(section);
  else container.prepend(section);
  return section;
}

function createWorkflowExecutionController({
  apiFetch,
  attachActiveRun,
  bindPressable,
  closeOverlays,
  openRunDetails,
  showConfirm,
  showToast,
  listLimit = 10,
  pollMs = 3000,
  setTimer = setTimeout,
  clearTimer = clearTimeout,
} = {}) {
  let executions = [];
  let loading = false;
  let error = '';
  let requestVersion = 0;
  let pollTimer = null;
  let workflowFilter = '';

  const panelOpen = () => {
    const overlay = document.getElementById('workflows-overlay');
    if (!overlay || !overlay.classList.contains('open')) return false;
    const view = String(overlay.dataset.workflowView || '').trim();
    return !view || view === 'executions';
  };

  const currentWorkflowFilter = () => {
    const overlay = document.getElementById('workflows-overlay');
    return String(overlay?.dataset.workflowExecutionWorkflowId || '').trim();
  };

  const toast = (message, tone = '') => {
    if (typeof showToast === 'function') showToast(message, tone);
  };

  const openRun = (runId) => {
    if (typeof openRunDetails !== 'function') {
      toast('Run Details is unavailable', 'error');
      return false;
    }
    if (typeof closeOverlays === 'function') closeOverlays();
    openRunDetails({ id: runId });
    return true;
  };

  const attachRun = async (runId) => {
    try {
      const payload = await workflowExecutionRequest(
        apiFetch,
        '/history/active',
        undefined,
        'Failed to load active runs',
      );
      const run = (Array.isArray(payload.runs) ? payload.runs : []).find(item => (
        String(item?.run_id || '') === String(runId || '')
      ));
      if (!run) return openRun(runId);
      if (typeof attachActiveRun !== 'function') throw new Error('Run attachment is unavailable');
      if (typeof closeOverlays === 'function') closeOverlays();
      await attachActiveRun(run);
      return true;
    } catch (attachError) {
      toast(attachError?.message || 'Failed to attach workflow run', 'error');
      return false;
    }
  };

  const clearPoll = () => {
    if (pollTimer === null) return;
    clearTimer(pollTimer);
    pollTimer = null;
  };

  const render = () => {
    const body = document.querySelector('.workflows-executions-panel')
      || document.querySelector('.workflows-body');
    if (!body) return null;
    const section = renderWorkflowExecutionsSection(body, { executions, loading, error }, {
      bindPressable,
      nowMs: Date.now(),
      onRefresh: () => refresh(),
      onCancel: execution => cancelFromPanel(execution),
      onAttachRun: attachRun,
      onOpenRun: openRun,
    });
    const overlay = document.getElementById('workflows-overlay');
    const focusExecutionId = String(overlay?.dataset.workflowExecutionFocus || '').trim();
    if (focusExecutionId) {
      const escapedId = typeof CSS !== 'undefined' && typeof CSS.escape === 'function'
        ? CSS.escape(focusExecutionId)
        : focusExecutionId.replace(/["\\]/g, '\\$&');
      const row = section.querySelector(`[data-workflow-execution-id="${escapedId}"]`);
      if (row) {
        delete overlay.dataset.workflowExecutionFocus;
        row.scrollIntoView?.({ block: 'nearest' });
        row.focus({ preventScroll: true });
      }
    }
    return section;
  };

  const schedulePoll = () => {
    clearPoll();
    if (!panelOpen() || !executions.some(workflowExecutionIsActive)) return;
    pollTimer = setTimer(() => {
      pollTimer = null;
      if (!panelOpen()) return;
      refresh({ quiet: true }).catch(() => {});
    }, pollMs);
  };

  const refresh = async ({ quiet = false } = {}) => {
    if (typeof apiFetch !== 'function') return [];
    const nextWorkflowFilter = currentWorkflowFilter();
    const filterChanged = nextWorkflowFilter !== workflowFilter;
    if (filterChanged) {
      workflowFilter = nextWorkflowFilter;
      executions = [];
      loading = false;
      error = '';
      clearPoll();
    }
    const currentRequest = ++requestVersion;
    loading = true;
    if (!quiet || filterChanged) error = '';
    render();
    try {
      const nextExecutions = await listWorkflowExecutions(apiFetch, listLimit, workflowFilter);
      if (currentRequest !== requestVersion) return executions;
      executions = nextExecutions;
      error = '';
      return executions;
    } catch (requestError) {
      if (currentRequest === requestVersion) {
        error = requestError?.message || 'Failed to load workflow executions';
      }
      return executions;
    } finally {
      if (currentRequest === requestVersion) {
        loading = false;
        render();
        schedulePoll();
      }
    }
  };

  const cancelFromPanel = async (execution) => {
    const executionId = String(execution?.id || '').trim();
    if (!executionId) return;
    let confirmed = true;
    if (typeof showConfirm === 'function') {
      const choice = await showConfirm({
        body: `Cancel workflow execution "${execution?.title || executionId}"? The active step will be stopped.`,
        tone: 'warning',
        actions: [
          { id: 'keep', label: 'Keep running', role: 'cancel' },
          { id: 'cancel-execution', label: 'Cancel execution', role: 'destructive', tone: 'warning' },
        ],
      });
      confirmed = choice === 'cancel-execution';
    }
    if (!confirmed) return;
    try {
      await cancelWorkflowExecution(apiFetch, executionId);
      toast('Workflow execution canceled');
      await refresh();
    } catch (cancelError) {
      toast(cancelError?.message || 'Failed to cancel workflow execution', 'error');
    }
  };

  return {
    getExecutions: () => executions.slice(),
    isLoading: () => loading,
    onPanelClose: clearPoll,
    onPanelOpen: () => refresh({ quiet: executions.length > 0 }),
    onScopeChanged: () => {
      requestVersion += 1;
      executions = [];
      loading = false;
      error = '';
      clearPoll();
      render();
      return panelOpen() ? refresh() : Promise.resolve([]);
    },
    refresh,
    render,
    refreshIfOpen: () => (
      panelOpen() && !loading
        ? refresh({ quiet: executions.length > 0 })
        : Promise.resolve(executions)
    ),
  };
}

export {
  cancelWorkflowExecution,
  createWorkflowExecutionController,
  createWorkflowExecution,
  formatWorkflowExecutionElapsed,
  getWorkflowExecution,
  listWorkflowExecutions,
  renderWorkflowExecutionsSection,
  workflowExecutionIsActive,
};
