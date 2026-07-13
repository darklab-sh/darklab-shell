// Workflows modal, editor, terminal command, and runtime autocomplete support.
import {
  emitUiEvent as importedEmitUiEvent,
  getActiveTabId as importedGetActiveTabId,
  onUiEvent as importedOnUiEvent,
} from '../../core/state.js';
import { showToast as importedShowToast } from '../../core/utils.js';
import {
  appendLine as importedAppendLine,
  hasPendingOutputBatch as importedHasPendingOutputBatch,
} from '../../output.js';
import {
  _finalizeClientSideCommandStatus as importedFinalizeClientSideCommandStatus,
  _persistClientSideRun as importedPersistClientSideRun,
  _recordSuccessfulLocalCommand as importedRecordSuccessfulLocalCommand,
  _setPendingTerminalConfirm as importedSetPendingTerminalConfirm,
  attachActiveRunFromMonitor as importedAttachActiveRunFromMonitor,
  appendCommandEcho as importedAppendCommandEcho,
  setStatus as importedSetStatus,
  submitComposerCommand as importedSubmitComposerCommand,
} from '../../runner.js';
import {
  activateTab as importedActivateTab,
  clearTab as importedClearTab,
  setTabStatus as importedSetTabStatus,
} from '../../tabs.js';
import { showConfirm as importedShowConfirm } from '../../ui/ui_confirm.js';
import { bindPressable as importedBindPressable } from '../../ui/ui_pressable.js';
import { cancelWelcome as importedCancelWelcome, welcomeOwnsTab as importedWelcomeOwnsTab } from '../../welcome.js';
import { useMobileTerminalViewportMode as importedUseMobileTerminalViewportMode } from '../mobile/mobile_shell_layout.js';
import { wireFaqCommandChips as importedWireFaqCommandChips } from '../command-registry/faq_helpers.js';
import { _workspaceCommandTokens as importedWorkspaceCommandTokens } from '../runner/runner_workspace.js';
import {
  _runtimeContextSpec as importedRuntimeContextSpec,
  _runtimeHint as importedRuntimeHint,
  _runtimePlaceholderHint as importedRuntimePlaceholderHint,
} from '../autocomplete/runtime_context.js';
import { closeMajorOverlays as importedCloseMajorOverlays } from '../../ui/overlay_actions_bridge.js';
import {
  openHistoryRunDetails as importedOpenHistoryRunDetails,
} from '../history/history_run_modal_state_bridge.js';
import {
  apiFetch as importedRuntimeApiFetch,
  hasRuntimeHandler as importedHasRuntimeHandler,
} from '../../runtime_bridge.js';
import {
  cancelWorkflowExecution as importedCancelWorkflowExecution,
  createWorkflowExecution as importedCreateWorkflowExecution,
  createWorkflowExecutionController as importedCreateWorkflowExecutionController,
  getWorkflowExecution as importedGetWorkflowExecution,
  listWorkflowExecutions as importedListWorkflowExecutions,
  workflowExecutionIsActive,
} from './workflow_executions.js';
import {
  createWorkflowCatalogStore,
  workflowCliName,
} from './workflow_catalog.js';
import { createWorkflowEditorController } from './workflow_editor.js';
import {
  appendWorkflowInputSourcePicker,
  buildRenderedWorkflow,
  getWorkflowInputValues,
  loadWorkflowInputValues,
  persistWorkflowInputValues,
  sanitizeWorkflowInputValue,
} from './workflow_parameters.js';
import { setWorkflowHandlers as importedSetWorkflowHandlers } from './workflows_bridge.js';

const WORKFLOWS_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _workflowGlobalFunction(name) {
  const fn = WORKFLOWS_GLOBAL && WORKFLOWS_GLOBAL[name];
  return typeof fn === 'function' ? fn : null;
}

function _workflowActiveTabId() {
  if (typeof importedGetActiveTabId === 'function') return importedGetActiveTabId();
  const readActiveTabId = _workflowGlobalFunction('getActiveTabId');
  if (readActiveTabId) return readActiveTabId();
  return WORKFLOWS_GLOBAL?.APP_STATE?.activeTabId || null;
}

function _workflowAppendLine(text, cls = '', tabId = _workflowActiveTabId()) {
  const append = (typeof importedAppendLine === 'function' && importedAppendLine)
    || _workflowGlobalFunction('appendLine');
  if (append) append(text, cls, tabId);
}

function _workflowBindPressable(el, opts) {
  const bind = (typeof importedBindPressable === 'function' && importedBindPressable)
    || _workflowGlobalFunction('bindPressable');
  return bind ? bind(el, opts) : null;
}

function _workflowCloseMajorOverlays() {
  const close = (typeof importedCloseMajorOverlays === 'function' && importedCloseMajorOverlays)
    || _workflowGlobalFunction('_closeMajorOverlays');
  if (close) close();
  const workflowOverlay = document.getElementById('workflows-overlay');
  if (workflowOverlay && workflowOverlay.classList.contains('open')) {
    workflowOverlay.classList.remove('open');
    workflowOverlay.classList.add('u-hidden');
    workflowOverlay.setAttribute('aria-hidden', 'true');
  }
}

function _workflowWireFaqCommandChips(root) {
  const wire = (typeof importedWireFaqCommandChips === 'function' && importedWireFaqCommandChips)
    || _workflowGlobalFunction('wireFaqCommandChips');
  if (wire) wire(root);
}

function _workflowApiFetch(...args) {
  const fetcher = (
    typeof importedHasRuntimeHandler === 'function'
    && importedHasRuntimeHandler('apiFetch')
    && typeof importedRuntimeApiFetch === 'function'
      ? importedRuntimeApiFetch
      : null
  ) || _workflowGlobalFunction('apiFetch');
  if (!fetcher) throw new Error('apiFetch is unavailable');
  return fetcher(...args);
}

const workflowExecutionController = typeof importedCreateWorkflowExecutionController === 'function'
  ? importedCreateWorkflowExecutionController({
    apiFetch: _workflowApiFetch,
    attachActiveRun: importedAttachActiveRunFromMonitor,
    bindPressable: _workflowBindPressable,
    closeOverlays: _workflowCloseMajorOverlays,
    openRunDetails: importedOpenHistoryRunDetails,
    showConfirm: importedShowConfirm,
    showToast: importedShowToast,
  })
  : null;

function refreshWorkflowExecutions(options = {}) {
  return workflowExecutionController?.refresh(options) || Promise.resolve([]);
}

function _workflowRuntimeHint(value, description = '', insertValue = null) {
  const hint = (typeof importedRuntimeHint === 'function' && importedRuntimeHint)
    || _workflowGlobalFunction('_runtimeHint');
  return hint ? hint(value, description, insertValue) : { value, description, ...(insertValue != null ? { insertValue } : {}) };
}

function _workflowRuntimePlaceholderHint(value, description = '') {
  const hint = (typeof importedRuntimePlaceholderHint === 'function' && importedRuntimePlaceholderHint)
    || _workflowGlobalFunction('_runtimePlaceholderHint');
  if (hint) return hint(value, description);
  return { value, description, hintOnly: true };
}

function _workflowRuntimeContextSpec(spec = {}) {
  const contextSpec = (typeof importedRuntimeContextSpec === 'function' && importedRuntimeContextSpec)
    || _workflowGlobalFunction('_runtimeContextSpec');
  return contextSpec ? contextSpec(spec) : spec;
}

const _workflowRunQueueByTab = new Map();
const workflowCatalogStore = createWorkflowCatalogStore({
  apiFetch: _workflowApiFetch,
  onItems: renderWorkflowItems,
});

function applyWorkflowStepPreviews(card, workflow, values) {
  const rendered = buildRenderedWorkflow(workflow, values);
  const stepsEl = card.querySelector('.workflow-steps');
  if (!stepsEl) return rendered;
  stepsEl.querySelectorAll('.workflow-step').forEach((stepEl, index) => {
    const chip = stepEl.querySelector('.workflow-step-cmd');
    const runBtn = stepEl.querySelector('.workflow-step-run');
    const state = stepEl.querySelector('.workflow-step-preview-state');
    const renderedStep = rendered.steps[index];
    const renderedCmd = renderedStep?.renderedCmd || '';
    const displayCmd = renderedStep?.displayCmd || renderedCmd;
    const waitsForCapture = !!renderedStep?.pendingCaptureNames?.length;
    const usesSensitiveInput = !!renderedStep?.sensitiveInputNames?.length;
    const runnable = rendered.ready && !!renderedCmd && !waitsForCapture && !usesSensitiveInput;
    if (chip) {
      chip.textContent = rendered.ready ? (displayCmd || renderedStep?.cmd || '') : (renderedStep?.cmd || '');
      if (runnable) {
        chip.title = 'Click to load into prompt';
        chip.dataset.faqCommand = renderedCmd;
        chip.classList.remove('is-disabled');
      } else {
        chip.title = waitsForCapture
          ? 'Capture values are filled during the playbook'
          : (usesSensitiveInput
            ? 'Sensitive values run only with Run all'
            : 'Fill required workflow inputs to load this step');
        delete chip.dataset.faqCommand;
        chip.classList.add('is-disabled');
      }
    }
    if (runBtn) {
      runBtn.dataset.workflowStepCmd = runnable ? renderedCmd : '';
      runBtn.disabled = !runnable;
      runBtn.setAttribute('aria-disabled', runBtn.disabled ? 'true' : 'false');
      runBtn.title = waitsForCapture
        ? 'This step runs after its capture values are available'
        : (usesSensitiveInput
          ? 'Sensitive values run only with Run all'
          : (runBtn.disabled ? 'Fill required workflow inputs to run this step' : 'Run this step'));
      runBtn.setAttribute('aria-label', runnable ? `Run: ${displayCmd}` : 'Run this step');
    }
    if (state) {
      state.textContent = waitsForCapture
        ? `During playbook: ${renderedStep.pendingCaptureNames.map(name => `{{${name}}}`).join(', ')}`
        : 'Inputs known';
      state.classList.toggle('is-capture-pending', waitsForCapture);
    }
  });
  return rendered;
}

async function startServerWorkflowExecution(
  workflow,
  values,
  tabId = _workflowActiveTabId(),
  { announceInTerminal = false } = {},
) {
  if (typeof importedCreateWorkflowExecution !== 'function') {
    throw new Error('Workflow execution is unavailable');
  }
  const payload = await importedCreateWorkflowExecution(
    _workflowApiFetch,
    workflow,
    values,
    tabId,
  );
  const execution = payload.execution || {};
  if (announceInTerminal) {
    const executionId = String(execution.id || '').trim();
    const inputCount = Object.keys(values || {}).length;
    const inputSummary = inputCount
      ? ` with ${inputCount} input${inputCount === 1 ? '' : 's'}`
      : '';
    const executionSummary = executionId ? `execution ${executionId} started` : 'execution started';
    const statusHint = executionId ? ` Check progress with workflow status ${executionId}.` : '';
    _workflowAppendLine(
      `[workflow] ${workflow.title}: ${executionSummary}${inputSummary}.${statusHint}`,
      'notice',
      tabId,
    );
  }
  if (typeof importedShowToast === 'function') importedShowToast('Workflow started');
  const workflowsOverlay = document.getElementById('workflows-overlay');
  if (!announceInTerminal && workflowsOverlay?.classList.contains('open')) {
    setWorkflowWorkspaceView('executions', { refreshExecutions: false });
  }
  refreshWorkflowExecutions().catch(() => {});
  return payload;
}

function runWorkflowCommands(commands) {
  const runnable = (commands || []).map((cmd) => String(cmd || '').trim()).filter(Boolean);
  if (!runnable.length) return;
  const targetTabId = _workflowActiveTabId();
  if (!targetTabId) return;
  const welcomeOwnsTab = (typeof importedWelcomeOwnsTab === 'function' && importedWelcomeOwnsTab)
    || _workflowGlobalFunction('welcomeOwnsTab');
  if (typeof welcomeOwnsTab === 'function' && welcomeOwnsTab(targetTabId)) {
    const cancelWelcome = (typeof importedCancelWelcome === 'function' && importedCancelWelcome)
      || _workflowGlobalFunction('cancelWelcome');
    const clearTab = (typeof importedClearTab === 'function' && importedClearTab)
      || _workflowGlobalFunction('clearTab');
    const setTabStatus = (typeof importedSetTabStatus === 'function' && importedSetTabStatus)
      || _workflowGlobalFunction('setTabStatus');
    if (cancelWelcome) cancelWelcome(targetTabId);
    if (clearTab) clearTab(targetTabId);
    if (setTabStatus) setTabStatus(targetTabId, 'idle');
  }
  _workflowCloseMajorOverlays();
  _workflowRunQueueByTab.set(targetTabId, {
    commands: runnable.slice(),
    nextIndex: 1,
    total: runnable.length,
  });
  const activateTab = (typeof importedActivateTab === 'function' && importedActivateTab)
    || _workflowGlobalFunction('activateTab');
  if (activateTab) activateTab(targetTabId);
  if (runnable.length > 1) {
    _workflowAppendLine(`[workflow] Running ${runnable.length} steps sequentially in this tab.`, 'notice', targetTabId);
  }
  const submitComposerCommand = (typeof importedSubmitComposerCommand === 'function' && importedSubmitComposerCommand)
    || _workflowGlobalFunction('submitComposerCommand');
  if (submitComposerCommand) {
    submitComposerCommand(runnable[0], {
      dismissKeyboard: true,
      focusAfterSubmit: true,
    });
  }
}

function _runNextWorkflowQueueStep(tabId) {
  const queue = _workflowRunQueueByTab.get(tabId);
  if (!queue) return;
  const nextCommand = queue.commands[queue.nextIndex];
  if (!nextCommand) {
    _workflowRunQueueByTab.delete(tabId);
    _workflowAppendLine('[workflow] Completed all queued steps.', 'exit-ok', tabId);
    return;
  }
  queue.nextIndex += 1;
  _workflowAppendLine(`[workflow] Continuing with step ${queue.nextIndex}/${queue.total}.`, 'notice', tabId);
  const activateTab = (typeof importedActivateTab === 'function' && importedActivateTab)
    || _workflowGlobalFunction('activateTab');
  if (activateTab) activateTab(tabId, { focusComposer: false });
  const submitComposerCommand = (typeof importedSubmitComposerCommand === 'function' && importedSubmitComposerCommand)
    || _workflowGlobalFunction('submitComposerCommand');
  if (submitComposerCommand) {
    submitComposerCommand(nextCommand, {
      dismissKeyboard: false,
      focusAfterSubmit: false,
    });
  }
}

function _scheduleNextWorkflowQueueStep(tabId) {
  const waitForFlush = () => {
    if (!_workflowRunQueueByTab.has(tabId)) return;
    const hasPendingOutputBatch = (typeof importedHasPendingOutputBatch === 'function' && importedHasPendingOutputBatch)
      || _workflowGlobalFunction('hasPendingOutputBatch');
    if (hasPendingOutputBatch && hasPendingOutputBatch(tabId)) {
      setTimeout(waitForFlush, 20);
      return;
    }
    _runNextWorkflowQueueStep(tabId);
  };
  setTimeout(waitForFlush, 0);
}

const workflowOnUiEvent = (typeof importedOnUiEvent === 'function' && importedOnUiEvent)
  || _workflowGlobalFunction('onUiEvent');
if (typeof workflowOnUiEvent === 'function') {
  workflowOnUiEvent('app:tab-status-changed', (e) => {
    const tabId = e?.detail?.id;
    const status = e?.detail?.status;
    if (!tabId || !_workflowRunQueueByTab.has(tabId) || status === 'running') return;
    if (status === 'killed') {
      _workflowRunQueueByTab.delete(tabId);
      _workflowAppendLine('[workflow] Queue stopped because the current step was killed.', 'denied', tabId);
      return;
    }
    _scheduleNextWorkflowQueueStep(tabId);
  });
  workflowOnUiEvent('app:workflows-opened', () => {
    syncWorkflowWorkspaceFromOverlay();
  });
  workflowOnUiEvent('app:workflows-closed', () => {
    workflowExecutionController?.onPanelClose();
  });
  workflowOnUiEvent('app:scope-changed', () => {
    selectedWorkflowId = '';
    workflowCatalogQuery = '';
    workflowCatalogSource = 'all';
    mobileWorkflowDetailOpen = false;
    workflowExecutionController?.onScopeChanged().catch(() => {});
  });
}

function renderWorkflowInputCard(card, workflow) {
  const inputs = Array.isArray(workflow?.inputs) ? workflow.inputs : [];
  if (!inputs.length) return null;

  const panel = document.createElement('div');
  panel.className = 'workflow-input-panel';

  const intro = document.createElement('div');
  intro.className = 'workflow-input-intro';
  intro.textContent = 'Fill in your target to preview the exact commands before loading or running a step.';
  panel.appendChild(intro);

  const grid = document.createElement('div');
  grid.className = 'workflow-input-grid';
  panel.appendChild(grid);

  const values = loadWorkflowInputValues(workflow);
  const hint = document.createElement('div');
  hint.className = 'workflow-input-hint';
  const actions = document.createElement('div');
  actions.className = 'workflow-input-actions';

  const runAllBtn = document.createElement('button');
  runAllBtn.type = 'button';
  runAllBtn.className = 'btn btn-secondary btn-compact workflow-run-all';
  runAllBtn.textContent = 'Run all';
  runAllBtn.title = 'Run each rendered workflow step sequentially in this tab';
  actions.appendChild(runAllBtn);

  panel.appendChild(actions);

  inputs.forEach((input) => {
    const field = document.createElement('label');
    field.className = 'workflow-input-field';

    const label = document.createElement('span');
    label.className = 'workflow-input-label';
    label.textContent = input.label || input.id || '';
    field.appendChild(label);

    const control = document.createElement('input');
    control.className = 'form-control workflow-input-control';
    control.type = input.sensitive ? 'password' : 'text';
    control.autocomplete = 'off';
    control.autocapitalize = 'none';
    control.autocorrect = 'off';
    control.spellcheck = false;
    control.inputMode = input.type === 'port' ? 'numeric' : 'text';
    control.placeholder = input.placeholder || '';
    control.value = values[input.id] || '';
    control.dataset.workflowInputId = input.id;
    if (input.required) {
      control.required = true;
      control.setAttribute('aria-required', 'true');
    }
    field.appendChild(control);

    if (input.help) {
      const help = document.createElement('span');
      help.className = 'workflow-input-help';
      help.textContent = input.help;
      field.appendChild(help);
    }

    grid.appendChild(field);
    appendWorkflowInputSourcePicker(field, input, control);
  });

  panel.appendChild(hint);

  const applyRenderedState = () => {
    const rendered = applyWorkflowStepPreviews(card, workflow, values);
    runAllBtn.disabled = !(rendered.ready && rendered.steps.some((step) => step.renderedCmd));
    runAllBtn.setAttribute('aria-disabled', runAllBtn.disabled ? 'true' : 'false');
    const hasSensitiveValues = rendered.steps.some((step) => step.sensitiveInputNames?.length);
    hint.textContent = rendered.ready
      ? (hasSensitiveValues
        ? 'Sensitive values stay masked and run only with Run all.'
        : 'Rendered commands are live. Click a chip to load it, use ▶ to run one step, or Run all to execute the full workflow here in sequence.')
      : 'Fill the required fields to render runnable commands.';
    _workflowWireFaqCommandChips(card);
    wireWorkflowStepRunButtons(card);
  };

  _workflowBindPressable(runAllBtn, {
    onActivate: async () => {
      const rendered = buildRenderedWorkflow(workflow, values);
      if (!rendered.ready) return;
      if (
        Number(workflow.version || 1) === 2
        || inputs.some(input => input?.sensitive)
      ) {
        runAllBtn.disabled = true;
        try {
          persistWorkflowInputValues(workflow, values);
          await startServerWorkflowExecution(workflow, values);
        } catch (err) {
          if (typeof importedShowToast === 'function') {
            importedShowToast(err.message || 'Failed to start workflow', 'error');
          }
        } finally {
          applyRenderedState();
        }
        return;
      }
      runWorkflowCommands(rendered.steps.map((step) => step.renderedCmd));
    },
  });

  grid.querySelectorAll('.workflow-input-control').forEach((control) => {
    control.addEventListener('input', () => {
      const input = inputs.find((item) => item.id === control.dataset.workflowInputId);
      values[control.dataset.workflowInputId || ''] = sanitizeWorkflowInputValue(input, control.value);
      if (input?.type === 'port' && control.value !== values[control.dataset.workflowInputId || '']) {
        control.value = values[control.dataset.workflowInputId || ''];
      }
      persistWorkflowInputValues(workflow, values);
      applyRenderedState();
    });
  });

  panel._workflowApplyRenderedState = applyRenderedState;
  return panel;
}

const workflowEditorController = createWorkflowEditorController({
  apiFetch: _workflowApiFetch,
  onSaved: (workflow) => {
    const savedWorkflowId = String(workflow?.id || '');
    if (!savedWorkflowId) return;
    selectedWorkflowId = savedWorkflowId;
    mobileWorkflowDetailOpen = isMobileWorkflowSheetMode();
    const overlay = document.getElementById('workflows-overlay');
    if (overlay) overlay.dataset.workflowId = savedWorkflowId;
  },
  reloadCatalog: reloadWorkflowCatalog,
  showToast: importedShowToast,
});

function openWorkflowEditor(workflow = null) {
  workflowEditorController.open(workflow);
}

function closeWorkflowEditor() {
  workflowEditorController.close();
}

async function deleteUserWorkflow(workflow) {
  if (!workflow || workflow.source !== 'user' || !workflow.id) return;
  let confirmed = true;
  const showConfirm = (typeof importedShowConfirm === 'function' && importedShowConfirm)
    || _workflowGlobalFunction('showConfirm');
  if (showConfirm) {
    const choice = await showConfirm({
      body: `Delete workflow "${workflow.title}"?`,
      tone: 'danger',
      actions: [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'delete', label: 'Delete', role: 'destructive' },
      ],
    });
    confirmed = choice === 'delete';
  }
  if (!confirmed) return;
  try {
    const resp = await _workflowApiFetch(`/session/workflows/${encodeURIComponent(workflow.id)}`, { method: 'DELETE' });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.error || `HTTP ${resp.status}`);
    }
    const currentItems = workflowCatalogStore.getItems();
    const deletedIndex = currentItems.findIndex(item => item.id === workflow.id);
    const nextItems = currentItems.filter(item => item.id !== workflow.id);
    const nextWorkflow = nextItems[Math.min(Math.max(deletedIndex, 0), nextItems.length - 1)] || null;
    selectedWorkflowId = String(nextWorkflow?.id || '');
    mobileWorkflowDetailOpen = !!nextWorkflow;
    const overlay = document.getElementById('workflows-overlay');
    if (overlay) {
      if (selectedWorkflowId) overlay.dataset.workflowId = selectedWorkflowId;
      else delete overlay.dataset.workflowId;
    }
    await reloadWorkflowCatalog();
    const showToast = (typeof importedShowToast === 'function' && importedShowToast)
      || _workflowGlobalFunction('showToast');
    if (showToast) showToast('Workflow deleted');
  } catch (err) {
    const showToast = (typeof importedShowToast === 'function' && importedShowToast)
      || _workflowGlobalFunction('showToast');
    if (showToast) showToast(err.message || 'Failed to delete workflow', 'error');
  }
}

function isMobileWorkflowSheetMode() {
  const useMobile = (typeof importedUseMobileTerminalViewportMode === 'function' && importedUseMobileTerminalViewportMode)
    || _workflowGlobalFunction('useMobileTerminalViewportMode');
  return !!(useMobile && useMobile());
}

function emitWorkflowCatalogRendered(items, enabled = true) {
  const emitUiEvent = (typeof importedEmitUiEvent === 'function' && importedEmitUiEvent)
    || _workflowGlobalFunction('emitUiEvent');
  if (enabled && emitUiEvent) {
    emitUiEvent('app:workflows-rendered', {
      items: items.slice(),
    });
  }
}

let selectedWorkflowId = '';
let workflowCatalogQuery = '';
let workflowCatalogSource = 'all';
let mobileWorkflowDetailOpen = false;

function workflowSourceLabel(workflow) {
  if (workflow?.source !== 'user') return 'built-in';
  return workflow.team_id ? 'team' : 'saved';
}

function workflowCatalogGroup(workflow) {
  if (workflow?.source !== 'user') return 'Built-ins';
  return workflow.team_id ? 'Team workflows' : 'My workflows';
}

function ensureWorkflowWorkspace() {
  const body = document.querySelector('.workflows-body');
  if (!body) return null;
  let workflowsPanel = body.querySelector('[data-workflows-panel="workflows"]');
  if (!workflowsPanel) {
    workflowsPanel = document.createElement('section');
    workflowsPanel.className = 'workflows-view-panel';
    workflowsPanel.dataset.workflowsPanel = 'workflows';
    body.appendChild(workflowsPanel);
  }
  let executionsPanel = body.querySelector('[data-workflows-panel="executions"]');
  if (!executionsPanel) {
    executionsPanel = document.createElement('section');
    executionsPanel.className = 'workflows-view-panel workflows-executions-panel nice-scroll';
    executionsPanel.dataset.workflowsPanel = 'executions';
    executionsPanel.hidden = true;
    body.appendChild(executionsPanel);
  }
  return { body, workflowsPanel, executionsPanel };
}

function setWorkflowWorkspaceView(view, { refreshExecutions = true } = {}) {
  const workspace = ensureWorkflowWorkspace();
  if (!workspace) return;
  const activeView = view === 'executions' ? 'executions' : 'workflows';
  const overlay = document.getElementById('workflows-overlay');
  if (overlay) overlay.dataset.workflowView = activeView;
  document.querySelectorAll('[data-workflows-view]').forEach((tab) => {
    const active = tab.dataset.workflowsView === activeView;
    tab.classList.toggle('is-active', active);
    tab.setAttribute('aria-selected', active ? 'true' : 'false');
    tab.tabIndex = active ? 0 : -1;
  });
  workspace.workflowsPanel.hidden = activeView !== 'workflows';
  workspace.executionsPanel.hidden = activeView !== 'executions';
  if (activeView === 'executions') {
    if (refreshExecutions) workflowExecutionController?.onPanelOpen().catch(() => {});
    else workflowExecutionController?.render();
  } else {
    workflowExecutionController?.onPanelClose();
  }
}

function wireWorkflowWorkspaceTabs() {
  document.querySelectorAll('[data-workflows-view]').forEach((tab) => {
    if (tab.dataset.workflowTabWired === '1') return;
    tab.dataset.workflowTabWired = '1';
    _workflowBindPressable(tab, {
      onActivate: () => setWorkflowWorkspaceView(tab.dataset.workflowsView),
      refocusComposer: false,
    });
    tab.addEventListener('keydown', (event) => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const tabs = Array.from(document.querySelectorAll('[data-workflows-view]'));
      const currentIndex = Math.max(0, tabs.indexOf(tab));
      const nextIndex = event.key === 'Home'
        ? 0
        : (event.key === 'End'
          ? tabs.length - 1
          : (currentIndex + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length);
      const nextTab = tabs[nextIndex];
      setWorkflowWorkspaceView(nextTab?.dataset.workflowsView);
      nextTab?.focus();
    });
  });
}

function syncWorkflowWorkspaceFromOverlay() {
  const overlay = document.getElementById('workflows-overlay');
  const selectionRequested = overlay?.dataset.workflowSelectionRequested === '1';
  const requestedWorkflowId = String(
    overlay?.dataset.workflowRequestedId || overlay?.dataset.workflowId || '',
  ).trim();
  if (selectionRequested && requestedWorkflowId) {
    selectedWorkflowId = requestedWorkflowId;
    workflowCatalogQuery = '';
    workflowCatalogSource = 'all';
  }
  if (overlay) {
    delete overlay.dataset.workflowRequestedId;
    overlay.dataset.workflowSelectionRequested = '0';
  }
  mobileWorkflowDetailOpen = isMobileWorkflowSheetMode() && selectionRequested && !!requestedWorkflowId;
  renderWorkflowItems(workflowCatalogStore.getItems(), { emitCatalogEvent: false });
  wireWorkflowWorkspaceTabs();
  setWorkflowWorkspaceView(overlay?.dataset.workflowView || 'workflows');
}

function renderWorkflowDetail(workflow, container) {
  container.replaceChildren();
  if (!workflow) {
    const empty = document.createElement('div');
    empty.className = 'workflow-detail-empty';
    empty.textContent = 'Choose a workflow to see its inputs and steps.';
    container.appendChild(empty);
    return;
  }

  const card = document.createElement('article');
  card.className = 'workflow-card workflow-detail';
  card.dataset.workflowId = String(workflow.id || '');
  if (workflow.source === 'user') card.classList.add('is-user-workflow');

  const mobileBack = document.createElement('button');
  mobileBack.type = 'button';
  mobileBack.className = 'btn btn-ghost btn-compact workflow-detail-back';
  mobileBack.textContent = '‹ Workflows';
  mobileBack.addEventListener('click', () => {
    mobileWorkflowDetailOpen = false;
    renderWorkflowItems(workflowCatalogStore.getItems(), { emitCatalogEvent: false });
  });
  card.appendChild(mobileBack);

  const header = document.createElement('div');
  header.className = 'workflow-detail-header';
  const heading = document.createElement('div');
  heading.className = 'workflow-card-heading';
  const titleEl = document.createElement('h2');
  titleEl.className = 'workflow-title';
  titleEl.textContent = workflow.title || '';
  heading.appendChild(titleEl);
  const badge = document.createElement('span');
  badge.className = 'workflow-source-badge';
  badge.textContent = workflowSourceLabel(workflow);
  heading.appendChild(badge);
  header.appendChild(heading);

  if (workflow.source === 'user') {
    const actions = document.createElement('div');
    actions.className = 'workflow-card-actions';
    const editBtn = document.createElement('button');
    editBtn.type = 'button';
    editBtn.className = 'btn btn-secondary btn-compact workflow-edit-btn';
    editBtn.textContent = 'Edit';
    editBtn.addEventListener('click', () => openWorkflowEditor(workflow));
    actions.appendChild(editBtn);
    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'btn btn-ghost btn-compact workflow-delete-btn';
    deleteBtn.textContent = 'Delete';
    deleteBtn.addEventListener('click', () => deleteUserWorkflow(workflow));
    actions.appendChild(deleteBtn);
    header.appendChild(actions);
  }
  card.appendChild(header);

  const cardBody = document.createElement('div');
  cardBody.className = 'workflow-card-body';
  if (workflow.description) {
    const desc = document.createElement('div');
    desc.className = 'workflow-desc';
    desc.textContent = workflow.description;
    cardBody.appendChild(desc);
  }

  if (Number(workflow.version || 1) === 2 && !(workflow.inputs || []).length) {
    const runActions = document.createElement('div');
    runActions.className = 'workflow-input-actions';
    const runPlaybookBtn = document.createElement('button');
    runPlaybookBtn.type = 'button';
    runPlaybookBtn.className = 'btn btn-secondary btn-compact workflow-run-all';
    runPlaybookBtn.textContent = 'Run all';
    runPlaybookBtn.title = 'Start this workflow execution';
    _workflowBindPressable(runPlaybookBtn, {
      onActivate: async () => {
        runPlaybookBtn.disabled = true;
        try {
          await startServerWorkflowExecution(workflow, {});
        } catch (err) {
          if (typeof importedShowToast === 'function') {
            importedShowToast(err.message || 'Failed to start workflow', 'error');
          }
        } finally {
          runPlaybookBtn.disabled = false;
        }
      },
    });
    runActions.appendChild(runPlaybookBtn);
    cardBody.appendChild(runActions);
  }

  const inputPanel = renderWorkflowInputCard(card, workflow);
  if (inputPanel) cardBody.appendChild(inputPanel);
  const steps = workflow.steps || [];
  if (steps.length) {
    const stepsEl = document.createElement('ol');
    stepsEl.className = 'workflow-steps';
    steps.forEach((step) => {
      const li = document.createElement('li');
      li.className = 'workflow-step';
      const main = document.createElement('div');
      main.className = 'workflow-step-main';
      const chip = document.createElement('span');
      chip.className = 'allowed-chip faq-chip workflow-step-cmd chip chip-action';
      chip.textContent = step.cmd || '';
      if (inputPanel) {
        chip.title = 'Fill required workflow inputs to load this step';
        chip.classList.add('is-disabled');
      } else {
        chip.title = 'Click to load into prompt';
        chip.dataset.faqCommand = step.cmd || '';
      }
      main.appendChild(chip);
      const runBtn = document.createElement('button');
      runBtn.type = 'button';
      runBtn.className = 'btn btn-ghost btn-compact btn-icon-only workflow-step-run';
      runBtn.textContent = '▶';
      runBtn.title = inputPanel ? 'Fill required workflow inputs to run this step' : 'Run this step';
      runBtn.setAttribute('aria-label', inputPanel ? 'Run this step' : `Run: ${step.cmd || ''}`);
      runBtn.dataset.workflowStepCmd = inputPanel ? '' : (step.cmd || '');
      runBtn.disabled = !!inputPanel;
      runBtn.setAttribute('aria-disabled', runBtn.disabled ? 'true' : 'false');
      main.appendChild(runBtn);
      if (Number(workflow.version || 1) === 2) {
        const previewState = document.createElement('span');
        previewState.className = 'workflow-step-preview-state';
        main.appendChild(previewState);
      }
      li.appendChild(main);
      if (step.note) {
        const note = document.createElement('span');
        note.className = 'workflow-step-note';
        note.textContent = step.note;
        li.appendChild(note);
      }
      stepsEl.appendChild(li);
    });
    cardBody.appendChild(stepsEl);
  }
  card.appendChild(cardBody);
  container.appendChild(card);

  if (inputPanel && typeof inputPanel._workflowApplyRenderedState === 'function') {
    inputPanel._workflowApplyRenderedState();
  } else if (Number(workflow.version || 1) === 2) {
    applyWorkflowStepPreviews(card, workflow, {});
  }
  _workflowWireFaqCommandChips(card);
  wireWorkflowStepRunButtons(card);
}

function renderWorkflowItems(items, { emitCatalogEvent = true } = {}) {
  const list = Array.isArray(items) ? items : [];
  workflowCatalogStore.setItems(list);
  const workspace = ensureWorkflowWorkspace();
  if (!workspace) return;
  const panel = workspace.workflowsPanel;
  panel.replaceChildren();
  const shell = document.createElement('div');
  shell.className = `workflow-workspace${mobileWorkflowDetailOpen ? ' is-detail-open' : ''}`;
  const catalogPane = document.createElement('aside');
  catalogPane.className = 'workflow-catalog-pane';
  catalogPane.setAttribute('aria-label', 'Workflow catalog');
  const toolbar = document.createElement('div');
  toolbar.className = 'workflow-catalog-toolbar';
  const search = document.createElement('input');
  search.type = 'search';
  search.className = 'form-control workflow-catalog-search';
  search.placeholder = 'Search workflows';
  search.setAttribute('aria-label', 'Search workflows');
  search.value = workflowCatalogQuery;
  search.addEventListener('input', () => {
    workflowCatalogQuery = search.value;
    renderWorkflowItems(workflowCatalogStore.getItems(), { emitCatalogEvent: false });
    document.querySelector('.workflow-catalog-search')?.focus({ preventScroll: true });
  });
  const source = document.createElement('select');
  source.className = 'form-select workflow-catalog-source';
  source.setAttribute('aria-label', 'Filter workflows by source');
  [['all', 'All sources'], ['saved', 'Saved'], ['built-in', 'Built-ins']].forEach(([value, label]) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    source.appendChild(option);
  });
  source.value = workflowCatalogSource;
  source.addEventListener('change', () => {
    workflowCatalogSource = source.value;
    renderWorkflowItems(workflowCatalogStore.getItems(), { emitCatalogEvent: false });
  });
  toolbar.append(search, source);
  catalogPane.appendChild(toolbar);

  const normalizedQuery = workflowCatalogQuery.trim().toLowerCase();
  const filtered = list.filter((workflow) => {
    const sourceMatches = workflowCatalogSource === 'all'
      || (workflowCatalogSource === 'saved' && workflow.source === 'user')
      || (workflowCatalogSource === 'built-in' && workflow.source !== 'user');
    const text = `${workflow.title || ''} ${workflow.description || ''}`.toLowerCase();
    return sourceMatches && (!normalizedQuery || text.includes(normalizedQuery));
  });
  if (!filtered.some(workflow => String(workflow.id || '') === selectedWorkflowId)) {
    selectedWorkflowId = String(filtered[0]?.id || '');
  }
  const selectedWorkflow = filtered.find(workflow => String(workflow.id || '') === selectedWorkflowId) || null;
  const overlay = document.getElementById('workflows-overlay');
  if (overlay) {
    if (selectedWorkflowId) overlay.dataset.workflowId = selectedWorkflowId;
    else delete overlay.dataset.workflowId;
  }

  const catalogList = document.createElement('div');
  catalogList.className = 'workflow-catalog-list nice-scroll';
  if (!filtered.length) {
    const empty = document.createElement('div');
    empty.className = 'workflow-catalog-empty';
    empty.textContent = list.length ? 'No workflows match these filters.' : 'No workflows are available.';
    catalogList.appendChild(empty);
  } else {
    let lastGroup = '';
    filtered.forEach((workflow) => {
      const group = workflowCatalogGroup(workflow);
      if (group !== lastGroup) {
        const label = document.createElement('div');
        label.className = 'workflow-section-label';
        label.textContent = group;
        catalogList.appendChild(label);
        lastGroup = group;
      }
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'btn btn-ghost panel-row panel-row-clickable workflow-catalog-item';
      row.dataset.workflowId = String(workflow.id || '');
      const selected = String(workflow.id || '') === selectedWorkflowId;
      row.classList.toggle('is-selected', selected);
      if (selected) row.setAttribute('aria-current', 'true');
      const rowMain = document.createElement('span');
      rowMain.className = 'workflow-catalog-item-main';
      const rowTitle = document.createElement('span');
      rowTitle.className = 'workflow-catalog-item-title';
      rowTitle.textContent = workflow.title || '';
      const rowDescription = document.createElement('span');
      rowDescription.className = 'workflow-catalog-item-description';
      rowDescription.textContent = workflow.description || 'No description';
      rowMain.append(rowTitle, rowDescription);
      const rowSource = document.createElement('span');
      rowSource.className = 'workflow-source-badge';
      rowSource.textContent = workflowSourceLabel(workflow);
      row.append(rowMain, rowSource);
      row.addEventListener('click', () => {
        selectedWorkflowId = String(workflow.id || '');
        mobileWorkflowDetailOpen = isMobileWorkflowSheetMode();
        if (overlay) overlay.dataset.workflowId = selectedWorkflowId;
        renderWorkflowItems(workflowCatalogStore.getItems(), { emitCatalogEvent: false });
      });
      catalogList.appendChild(row);
    });
  }
  catalogPane.appendChild(catalogList);
  const detailPane = document.createElement('section');
  detailPane.className = 'workflow-detail-pane nice-scroll';
  detailPane.setAttribute('aria-label', 'Selected workflow');
  shell.append(catalogPane, detailPane);
  panel.appendChild(shell);
  renderWorkflowDetail(selectedWorkflow, detailPane);
  wireWorkflowWorkspaceTabs();
  setWorkflowWorkspaceView(overlay?.dataset.workflowView || 'workflows', { refreshExecutions: false });

  emitWorkflowCatalogRendered(list, emitCatalogEvent);
}

async function reloadWorkflowCatalog() {
  return workflowCatalogStore.reload();
}

function ensureWorkflowCatalogLoaded() {
  return workflowCatalogStore.ensureLoaded();
}

function activateWorkflowStepRun(cmd) {
  if (!cmd) return;
  _workflowCloseMajorOverlays();
  const submitComposerCommand = (typeof importedSubmitComposerCommand === 'function' && importedSubmitComposerCommand)
    || _workflowGlobalFunction('submitComposerCommand');
  if (submitComposerCommand) {
    submitComposerCommand(cmd, { dismissKeyboard: true });
  }
}

function wireWorkflowStepRunButtons(root) {
  if (!root) return;
  root.querySelectorAll('.workflow-step-run[data-workflow-step-cmd]').forEach(btn => {
    _workflowBindPressable(btn, {
      onActivate: () => activateWorkflowStepRun(btn.dataset.workflowStepCmd || ''),
    });
  });
}

function _workflowCommandTokens(cmd) {
  const workspaceCommandTokens = (typeof importedWorkspaceCommandTokens === 'function' && importedWorkspaceCommandTokens)
    || _workflowGlobalFunction('_workspaceCommandTokens');
  if (workspaceCommandTokens) return workspaceCommandTokens(cmd);
  const tokens = [];
  const re = /"[^"]*"|'[^']*'|\S+/g;
  let match = re.exec(String(cmd || '').trim());
  while (match) {
    let token = match[0];
    if (token.length >= 2 && ((token[0] === '"' && token[token.length - 1] === '"') || (token[0] === "'" && token[token.length - 1] === "'"))) {
      token = token.slice(1, -1);
    }
    tokens.push(token);
    match = re.exec(String(cmd || '').trim());
  }
  return tokens;
}

function _workflowCliAppend(text, cls = '', tabId = _workflowActiveTabId()) {
  _workflowAppendLine(text, cls, tabId);
}

function _workflowCliSetStatus(status) {
  const setStatus = (typeof importedSetStatus === 'function' && importedSetStatus)
    || _workflowGlobalFunction('setStatus');
  if (setStatus) setStatus(status);
}

function _workflowCliRecord(cmd) {
  const record = (typeof importedRecordSuccessfulLocalCommand === 'function' && importedRecordSuccessfulLocalCommand)
    || _workflowGlobalFunction('_recordSuccessfulLocalCommand');
  if (record) record(cmd);
}

function _workflowCliPersist(cmd, lines, status = 'ok') {
  const persist = (typeof importedPersistClientSideRun === 'function' && importedPersistClientSideRun)
    || _workflowGlobalFunction('_persistClientSideRun');
  if (persist) persist(cmd, lines, status);
}

function _workflowCliFinish(cmd, lines, status = 'ok', tabId = _workflowActiveTabId(), { record = false } = {}) {
  if (record && status !== 'fail') _workflowCliRecord(cmd);
  _workflowCliPersist(cmd, lines, status);
  const finalize = (typeof importedFinalizeClientSideCommandStatus === 'function' && importedFinalizeClientSideCommandStatus)
    || _workflowGlobalFunction('_finalizeClientSideCommandStatus');
  if (finalize) {
    finalize(tabId, status);
  } else {
    _workflowCliSetStatus(status);
  }
}

function _workflowFind(selector) {
  return workflowCatalogStore.find(selector);
}

function _workflowCliUsageLines() {
  return [
    'Usage: workflow [list | show <name> | run <name> [--input value ...] | runs | status <execution-id> | cancel <execution-id>]',
    'Examples:',
    '  workflow list',
    '  workflow show dns-troubleshooting',
    '  workflow run dns-troubleshooting --domain darklab.sh',
    '  workflow runs',
    '  workflow status wfx_...',
  ];
}

function _workflowParseRunArgs(args) {
  const selectors = [];
  const values = {};
  const errors = [];
  for (let index = 0; index < args.length; index += 1) {
    const token = String(args[index] || '');
    if (token.startsWith('--')) {
      const eq = token.indexOf('=');
      const rawName = eq >= 0 ? token.slice(2, eq) : token.slice(2);
      const name = rawName.replace(/-/g, '_').toLowerCase();
      if (!name) {
        errors.push(`invalid flag '${token}'`);
        continue;
      }
      let value = eq >= 0 ? token.slice(eq + 1) : '';
      if (eq < 0) {
        index += 1;
        value = args[index] || '';
      }
      if (!String(value || '').trim()) errors.push(`missing value for --${rawName}`);
      values[name] = value;
    } else {
      selectors.push(token);
    }
  }
  return { selector: selectors.join(' '), values, errors };
}

function _workflowRedactedRunCommand(parts, sensitiveNames) {
  const redacted = [];
  for (let index = 0; index < parts.length; index += 1) {
    const token = String(parts[index] || '');
    if (!token.startsWith('--')) {
      redacted.push(token);
      continue;
    }
    const eq = token.indexOf('=');
    const rawName = eq >= 0 ? token.slice(2, eq) : token.slice(2);
    const name = rawName.replace(/-/g, '_').toLowerCase();
    if (!sensitiveNames.has(name)) {
      redacted.push(token);
      continue;
    }
    if (eq >= 0) {
      redacted.push(`--${rawName}=[redacted]`);
    } else {
      redacted.push(token, '[redacted]');
      index += 1;
    }
  }
  return redacted.join(' ');
}

function _workflowResolvedValues(workflow, provided = {}) {
  const values = getWorkflowInputValues(workflow);
  Object.entries(provided || {}).forEach(([key, value]) => {
    const input = (workflow.inputs || []).find(item => item.id === key);
    if (!input) return;
    values[key] = sanitizeWorkflowInputValue(input, value);
  });
  return values;
}

function _workflowMissingInputs(workflow, values) {
  return (workflow.inputs || []).filter(input => input.required && !String(values[input.id] || '').trim());
}

function _workflowRunResolved(workflow, values, tabId) {
  const rendered = buildRenderedWorkflow(workflow, values);
  if (!rendered.ready) {
    _workflowCliAppend('[workflow] Required inputs are missing.', 'exit-fail', tabId);
    _workflowCliSetStatus('fail');
    return;
  }
  const commands = rendered.steps.map(step => step.renderedCmd).filter(Boolean);
  if (!commands.length) {
    _workflowCliAppend('[workflow] No runnable steps.', 'exit-fail', tabId);
    _workflowCliSetStatus('fail');
    return;
  }
  persistWorkflowInputValues(workflow, values);
  if (Number(workflow.version || 1) === 2) {
    startServerWorkflowExecution(workflow, values, tabId, { announceInTerminal: true }).catch((err) => {
      _workflowCliAppend(`[workflow] ${err.message || 'Failed to start workflow'}`, 'exit-fail', tabId);
      _workflowCliSetStatus('fail');
    });
    return;
  }
  _workflowCliAppend(`[workflow] ${workflow.title}: ${commands.length} step(s) queued.`, 'notice', tabId);
  runWorkflowCommands(commands);
}

function _workflowPromptForInputs(workflow, values, missing, tabId) {
  const queue = missing.slice();
  const askNext = () => {
    const input = queue.shift();
    if (!input) {
      _workflowRunResolved(workflow, values, tabId);
      return;
    }
    const label = input.label || input.id;
    const hint = input.placeholder ? ` (${input.placeholder})` : '';
    _workflowCliAppend(`[workflow] ${label}${hint}:`, 'notice', tabId);
    const setPendingTerminalConfirm = (typeof importedSetPendingTerminalConfirm === 'function' && importedSetPendingTerminalConfirm)
      || _workflowGlobalFunction('_setPendingTerminalConfirm');
    if (!setPendingTerminalConfirm) {
      _workflowCliAppend(`[workflow] missing --${input.id.replace(/_/g, '-')}`, 'exit-fail', tabId);
      _workflowCliSetStatus('fail');
      return;
    }
    setPendingTerminalConfirm({
      kind: input.sensitive ? 'secret' : 'text',
      tabId,
      onAnswer: async (answer) => {
        const value = sanitizeWorkflowInputValue(input, answer);
        if (!value) {
          queue.unshift(input);
        } else {
          values[input.id] = value;
        }
        askNext();
      },
      onCancel: async () => {
        _workflowCliAppend('[workflow] canceled.', 'notice', tabId);
        _workflowCliSetStatus('idle');
      },
    });
    _workflowCliSetStatus('idle');
  };
  askNext();
}

async function handleWorkflowTerminalCommand(cmd, tabId = _workflowActiveTabId()) {
  const lines = [];
  const append = (text, cls = '') => {
    lines.push({ text, cls });
    _workflowCliAppend(text, cls, tabId);
  };
  const appendCommandEcho = (typeof importedAppendCommandEcho === 'function' && importedAppendCommandEcho)
    || _workflowGlobalFunction('appendCommandEcho');
  let echoed = false;
  const echoCommand = (command) => {
    if (!echoed && appendCommandEcho) appendCommandEcho(command, tabId);
    echoed = true;
  };
  if (!workflowCatalogStore.getItems().length) {
    try { await reloadWorkflowCatalog(); }
    catch (err) {
      echoCommand(cmd);
      append(`[workflow] failed to load workflows: ${err.message || 'network error'}`, 'exit-fail');
      _workflowCliFinish(cmd, lines, 'fail', tabId);
      return true;
    }
  }
  const parts = _workflowCommandTokens(cmd);
  const sub = String(parts[1] || 'list').toLowerCase();
  if (sub !== 'run') echoCommand(cmd);
  if (sub === 'help' || sub === '--help' || sub === '-h') {
    _workflowCliUsageLines().forEach(line => append(line, ''));
    _workflowCliFinish(cmd, lines, 'ok', tabId, { record: true });
    return true;
  }
  if (sub === 'list' || parts.length === 1) {
    append('Workflows:', 'builtin-section');
    workflowCatalogStore.getItems().forEach((workflow) => {
      const kind = workflow.source === 'user' ? 'user' : 'built-in';
      const idHint = workflow.source === 'user' && workflow.id ? `, id: ${workflow.id}` : '';
      append(`  ${workflowCliName(workflow)}  ${workflow.title} (${workflow.steps?.length || 0} steps, ${kind}${idHint})`, 'builtin-help-row');
    });
    _workflowCliFinish(cmd, lines, 'ok', tabId, { record: true });
    return true;
  }
  if (sub === 'show') {
    const selector = parts.slice(2).join(' ');
    const { workflow, error } = _workflowFind(selector);
    if (!workflow) {
      append(`[workflow] ${error}`, 'exit-fail');
      _workflowCliFinish(cmd, lines, 'fail', tabId);
      return true;
    }
    append(`${workflow.title} (${workflowCliName(workflow)})`, 'builtin-section');
    if (workflow.description) append(workflow.description, 'builtin-note');
    (workflow.inputs || []).forEach(input => append(`  --${input.id.replace(/_/g, '-')}  ${input.label || input.id}`, 'builtin-help-row'));
    (workflow.steps || []).forEach((step, index) => {
      append(`  ${index + 1}. ${step.cmd}`, 'builtin-help-row');
      if (step.note) append(`     ${step.note}`, 'builtin-note');
    });
    _workflowCliFinish(cmd, lines, 'ok', tabId, { record: true });
    return true;
  }
  if (sub === 'runs') {
    try {
      const executions = await importedListWorkflowExecutions(_workflowApiFetch, 20);
      append('Recent workflow executions:', 'builtin-section');
      if (!executions.length) append('  No workflow executions yet.', 'builtin-note');
      executions.forEach((execution) => {
        const step = execution.current_step_id ? `, step ${execution.current_step_id}` : '';
        append(`  ${execution.id}  ${execution.title} (${execution.status}${step})`, 'builtin-help-row');
      });
      _workflowCliFinish(cmd, lines, 'ok', tabId, { record: true });
    } catch (err) {
      append(`[workflow] ${err.message || 'Failed to load workflow executions'}`, 'exit-fail');
      _workflowCliFinish(cmd, lines, 'fail', tabId);
    }
    return true;
  }
  if (sub === 'status') {
    const executionId = String(parts[2] || '').trim();
    if (!executionId) {
      append('[workflow] execution id is required', 'exit-fail');
      _workflowCliFinish(cmd, lines, 'fail', tabId);
      return true;
    }
    try {
      const payload = await importedGetWorkflowExecution(_workflowApiFetch, executionId);
      const execution = payload.execution || {};
      append(`${execution.title || 'Workflow'} (${execution.id})`, 'builtin-section');
      append(`  Status: ${execution.status || 'unknown'}`, 'builtin-kv');
      (execution.steps || []).forEach((step) => {
        const run = step.run_id ? `, run ${step.run_id}` : '';
        const transition = step.selected_transition
          ? `, next ${step.selected_transition} (${step.transition_reason || 'selected'})`
          : '';
        const captures = Array.isArray(step.capture_names) && step.capture_names.length
          ? `, captures ${step.capture_names.join(', ')}`
          : '';
        append(`  ${step.step_id}: ${step.status}${run}${transition}${captures}`, 'builtin-help-row');
      });
      _workflowCliFinish(cmd, lines, 'ok', tabId, { record: true });
    } catch (err) {
      append(`[workflow] ${err.message || 'Failed to load workflow execution'}`, 'exit-fail');
      _workflowCliFinish(cmd, lines, 'fail', tabId);
    }
    return true;
  }
  if (sub === 'cancel') {
    const executionId = String(parts[2] || '').trim();
    if (!executionId) {
      append('[workflow] execution id is required', 'exit-fail');
      _workflowCliFinish(cmd, lines, 'fail', tabId);
      return true;
    }
    try {
      await importedCancelWorkflowExecution(_workflowApiFetch, executionId);
      append(`[workflow] ${executionId} canceled.`, 'notice');
      refreshWorkflowExecutions().catch(() => {});
      _workflowCliFinish(cmd, lines, 'ok', tabId, { record: true });
    } catch (err) {
      append(`[workflow] ${err.message || 'Failed to cancel workflow execution'}`, 'exit-fail');
      _workflowCliFinish(cmd, lines, 'fail', tabId);
    }
    return true;
  }
  if (sub === 'run') {
    const parsed = _workflowParseRunArgs(parts.slice(2));
    const { workflow, error } = _workflowFind(parsed.selector);
    if (!workflow) {
      echoCommand(cmd);
      if (parsed.errors.length) {
        parsed.errors.forEach(parseError => append(`[workflow] ${parseError}`, 'exit-fail'));
      } else {
        append(`[workflow] ${error}`, 'exit-fail');
      }
      _workflowCliFinish(cmd, lines, 'fail', tabId);
      return true;
    }
    const sensitiveNames = new Set(
      (workflow.inputs || []).filter(input => input.sensitive).map(input => input.id),
    );
    const inlineSensitiveNames = Object.keys(parsed.values).filter(name => sensitiveNames.has(name));
    const safeCommand = inlineSensitiveNames.length
      ? _workflowRedactedRunCommand(parts, sensitiveNames)
      : cmd;
    echoCommand(safeCommand);
    if (inlineSensitiveNames.length) {
      const flags = inlineSensitiveNames.map(name => `--${name.replace(/_/g, '-')}`).join(', ');
      append(`[workflow] Sensitive parameters can't be supplied inline (${flags}). Omit them to enter the values securely.`, 'exit-fail');
      _workflowCliFinish(safeCommand, lines, 'fail', tabId);
      return true;
    }
    if (parsed.errors.length) {
      parsed.errors.forEach(parseError => append(`[workflow] ${parseError}`, 'exit-fail'));
      _workflowCliFinish(cmd, lines, 'fail', tabId);
      return true;
    }
    const values = _workflowResolvedValues(workflow, parsed.values);
    const missing = _workflowMissingInputs(workflow, values);
    if (missing.length) {
      _workflowPromptForInputs(workflow, values, missing, tabId);
      return true;
    }
    _workflowRunResolved(workflow, values, tabId);
    return true;
  }
  append(`[workflow] unknown subcommand '${sub}'`, 'exit-fail');
  _workflowCliUsageLines().forEach(line => append(line, ''));
  _workflowCliFinish(cmd, lines, 'fail', tabId);
  return true;
}

function _workflowRuntimeHintFor(workflow) {
  const value = workflowCliName(workflow);
  return _workflowRuntimeHint(value, workflow.title || value, value);
}

function _workflowInputHint(input) {
  const item = _workflowRuntimePlaceholderHint(
    `<${input.id}>`,
    input.label || input.id,
  );
  const inputType = String(input.type || 'text').trim().toLowerCase();
  if (inputType !== 'text') {
    item.value_type = inputType === 'path' ? 'workspace_path' : inputType;
  }
  return item;
}

function _runtimeWorkflowContext() {
  const workflows = workflowCatalogStore.getItems();
  const workflowHints = workflows.map(_workflowRuntimeHintFor);
  const recentExecutions = workflowExecutionController?.getExecutions() || [];
  const executionHints = recentExecutions.map(execution => _workflowRuntimeHint(
    String(execution?.id || ''),
    `${execution?.title || 'Workflow'} (${execution?.status || 'unknown'})`,
  ));
  const activeExecutionHints = recentExecutions
    .filter(workflowExecutionIsActive)
    .map(execution => _workflowRuntimeHint(
      String(execution?.id || ''),
      `${execution?.title || 'Workflow'} (${execution?.status || 'unknown'})`,
    ));
  const flags = [];
  const expectsValue = [];
  const argHints = {
    list: [],
    show: workflowHints,
    run: workflowHints,
    runs: [],
    status: executionHints.length
      ? executionHints
      : [_workflowRuntimePlaceholderHint('<execution-id>', 'Workflow execution id')],
    cancel: activeExecutionHints.length
      ? activeExecutionHints
      : [_workflowRuntimePlaceholderHint('<execution-id>', 'Workflow execution id')],
    __positional__: [
      _workflowRuntimeHint('list', 'List workflows'),
      _workflowRuntimeHint('show', 'Show workflow steps', 'show '),
      _workflowRuntimeHint('run', 'Run a workflow', 'run '),
      _workflowRuntimeHint('runs', 'List recent workflow executions'),
      _workflowRuntimeHint('status', 'Show workflow execution status', 'status '),
      _workflowRuntimeHint('cancel', 'Cancel a workflow execution', 'cancel '),
    ],
  };
  const sequenceArgHints = {};
  const seenFlags = new Set();
  workflows.forEach((workflow) => {
    const workflowName = workflowCliName(workflow).toLowerCase();
    const workflowFlags = [];
    (workflow.inputs || []).forEach((input) => {
      const flag = `--${String(input.id || '').replace(/_/g, '-')}`;
      if (!seenFlags.has(flag)) {
        seenFlags.add(flag);
        flags.push({ value: flag, description: input.label || input.id });
        expectsValue.push(flag);
        argHints[flag] = [_workflowInputHint(input)];
      }
      workflowFlags.push(_workflowRuntimeHint(flag, input.label || input.id, `${flag} `));
    });
    sequenceArgHints[`run ${workflowName}`] = workflowFlags;
  });
  return _workflowRuntimeContextSpec({ flags, expectsValue, argHints, sequenceArgHints });
}

if (typeof window !== 'undefined') {
  const initialWorkflowItems = workflowCatalogStore.getItems();
  if (initialWorkflowItems.length) renderWorkflowItems(initialWorkflowItems, { emitCatalogEvent: false });
  if (typeof importedSetWorkflowHandlers === 'function') {
    importedSetWorkflowHandlers({
      renderWorkflowItems,
      reloadWorkflowCatalog,
      ensureWorkflowCatalogLoaded,
      handleWorkflowTerminalCommand,
      _runtimeWorkflowContext,
      openWorkflowEditor,
      closeWorkflowEditor,
    });
  }
}

export {
  renderWorkflowItems,
  reloadWorkflowCatalog,
  ensureWorkflowCatalogLoaded,
  handleWorkflowTerminalCommand,
  _runtimeWorkflowContext,
  openWorkflowEditor,
  closeWorkflowEditor,
};
