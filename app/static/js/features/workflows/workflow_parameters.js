// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Workflow parameter persistence, value sources, and browser-side previews.

import { getAppState as importedGetAppState } from '../../core/state.js';
import { getSessionId as importedGetSessionId } from '../../runtime_bridge.js';
import { getActiveTeamId as importedGetActiveTeamId } from '../team_scope.js';
import {
  _readProjectTargets as importedReadProjectTargets,
  _readRecentValues as importedReadRecentValues,
} from '../autocomplete/suggestions.js';
import {
  getWorkspaceAutocompleteFileHints as importedGetWorkspaceAutocompleteFileHints,
  refreshWorkspaceFileCache as importedRefreshWorkspaceFileCache,
} from '../workspace/workspace_autocomplete_cache.js';
import { workflowStorageKey } from './workflow_catalog.js';

const WORKFLOW_TOKEN_RE = /{{\s*([a-z][a-z0-9_]*)\s*}}/g;
const WORKFLOW_INPUT_STATE_KEY = 'workflow_input_state_v2';
const LEGACY_WORKFLOW_INPUT_STATE_KEY = 'workflow_input_state_v1';

function workflowInputStorageKey(workflow) {
  const teamId = String(workflow?.team_id || importedGetActiveTeamId?.() || '').trim();
  const ownerKey = teamId
    ? `team:${teamId}`
    : `personal:${String(importedGetSessionId?.() || 'anonymous').trim() || 'anonymous'}`;
  return `${ownerKey}::${workflowStorageKey(workflow)}`;
}

function readWorkflowInputState() {
  if (typeof localStorage === 'undefined') return {};
  try {
    localStorage.removeItem(LEGACY_WORKFLOW_INPUT_STATE_KEY);
    const raw = localStorage.getItem(WORKFLOW_INPUT_STATE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch (_err) {
    return {};
  }
}

function writeWorkflowInputState(nextState) {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(WORKFLOW_INPUT_STATE_KEY, JSON.stringify(nextState || {}));
  } catch (_err) {
    // The form still works in memory when browser storage is unavailable.
  }
}

function sanitizeWorkflowInputValue(input, value) {
  const raw = String(value == null ? '' : value).trim();
  if (!input || !raw) return raw;
  if (input.type === 'port') return raw.replace(/[^\d]/g, '');
  return raw;
}

function getWorkflowInputValues(workflow) {
  const values = {};
  const inputs = Array.isArray(workflow?.inputs) ? workflow.inputs : [];
  inputs.forEach((input) => {
    values[input.id] = sanitizeWorkflowInputValue(input, input.default || '');
  });
  return values;
}

function loadWorkflowInputValues(workflow) {
  const base = getWorkflowInputValues(workflow);
  const state = readWorkflowInputState();
  const storageKey = workflowInputStorageKey(workflow);
  const saved = state[storageKey];
  if (!saved || typeof saved !== 'object') return base;
  const next = { ...base };
  const retained = {};
  Object.entries(saved).forEach(([key, value]) => {
    const input = (workflow?.inputs || []).find((item) => item.id === key);
    if (!input || input.sensitive) return;
    const normalized = sanitizeWorkflowInputValue(input, value);
    next[key] = normalized;
    retained[key] = normalized;
  });
  if (JSON.stringify(retained) !== JSON.stringify(saved)) {
    const nextState = { ...state };
    if (Object.keys(retained).length) nextState[storageKey] = retained;
    else delete nextState[storageKey];
    writeWorkflowInputState(nextState);
  }
  return next;
}

function persistWorkflowInputValues(workflow, values) {
  const state = readWorkflowInputState();
  const nextState = { ...state };
  const storageKey = workflowInputStorageKey(workflow);
  const retained = {};
  (workflow?.inputs || []).forEach((input) => {
    if (!input?.id || input.sensitive) return;
    retained[input.id] = sanitizeWorkflowInputValue(input, values?.[input.id]);
  });
  if (Object.keys(retained).length) nextState[storageKey] = retained;
  else delete nextState[storageKey];
  writeWorkflowInputState(nextState);
}

function workflowInputSourceOptions(input) {
  const type = String(input?.type || 'text');
  const options = [];
  const projectTargets = importedReadProjectTargets?.() || [];
  const allowedProjectTypes = {
    target: new Set(['domain', 'host', 'ip', 'cidr', 'url', 'port_set', 'target']),
    domain: new Set(['domain']),
    host: new Set(['domain', 'ip', 'host']),
    url: new Set(['url']),
  }[type];
  if (allowedProjectTypes) {
    projectTargets.forEach((target) => {
      if (!allowedProjectTypes.has(String(target?.type || 'target'))) return;
      options.push({ value: target.value, description: 'Project target' });
    });
  }
  const recentValues = importedReadRecentValues?.() || {};
  const recentKinds = {
    target: ['domain', 'ip', 'url', 'port_set'],
    domain: ['domain'],
    host: ['domain', 'ip'],
    url: ['url'],
    port_set: ['port_set'],
  }[type] || [];
  recentKinds.forEach((kind) => {
    (Array.isArray(recentValues?.[kind]) ? recentValues[kind] : []).forEach((value) => {
      options.push({ value, description: 'Recent value' });
    });
  });
  if (type === 'workspace_path' || type === 'wordlist') {
    const files = importedGetWorkspaceAutocompleteFileHints?.() || [];
    files.forEach(item => options.push({ value: item.value, description: 'Files' }));
  }
  if (type === 'wordlist') {
    const state = importedGetAppState?.() || {};
    (Array.isArray(state?.acWordlists) ? state.acWordlists : []).forEach((item) => {
      options.push({
        value: item?.value,
        description: item?.description || 'Packaged wordlist',
      });
    });
  }
  const seen = new Set();
  return options.filter((item) => {
    const value = String(item?.value || '').trim();
    const key = value.toLowerCase();
    if (!value || seen.has(key)) return false;
    seen.add(key);
    item.value = value;
    return true;
  });
}

function appendWorkflowInputSourcePicker(field, input, control) {
  const renderPicker = () => {
    if (!field.parentElement || field.querySelector('.workflow-input-source-picker')) return;
    const options = workflowInputSourceOptions(input);
    if (!options.length) return;
    const picker = document.createElement('select');
    picker.className = 'form-select workflow-input-source-picker';
    picker.setAttribute('aria-label', `Choose a saved value for ${input.label || input.id}`);
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = input.type === 'wordlist'
      ? 'Choose a wordlist'
      : (input.type === 'workspace_path' ? 'Choose a Files entry' : 'Choose a saved value');
    picker.appendChild(placeholder);
    options.forEach((item) => {
      const option = document.createElement('option');
      option.value = item.value;
      option.textContent = item.description ? `${item.value} · ${item.description}` : item.value;
      picker.appendChild(option);
    });
    picker.addEventListener('change', () => {
      if (!picker.value) return;
      control.value = picker.value;
      control.dispatchEvent(new Event('input', { bubbles: true }));
      picker.value = '';
    });
    field.appendChild(picker);
  };
  if (input.type === 'workspace_path' || input.type === 'wordlist') {
    const refresh = importedRefreshWorkspaceFileCache?.() || Promise.resolve();
    Promise.resolve(refresh).catch(() => null).then(renderPicker);
  } else {
    renderPicker();
  }
}

function renderWorkflowCommandTemplate(template, values) {
  return String(template || '').replace(WORKFLOW_TOKEN_RE, (match, token) => (
    Object.prototype.hasOwnProperty.call(values || {}, token) ? values[token] : match
  ));
}

function workflowTemplateTokens(template) {
  return new Set([...String(template || '').matchAll(WORKFLOW_TOKEN_RE)].map(match => match[1]));
}

function workflowInputsReady(workflow, values) {
  const inputs = Array.isArray(workflow?.inputs) ? workflow.inputs : [];
  return inputs.every((input) => !input.required || String(values[input.id] || '').trim().length > 0);
}

function buildRenderedWorkflow(workflow, values) {
  const renderedValues = { ...(values || {}) };
  const sensitiveInputNames = new Set(
    (Array.isArray(workflow?.inputs) ? workflow.inputs : [])
      .filter(input => input?.sensitive)
      .map(input => String(input.id || '')),
  );
  const displayValues = { ...renderedValues };
  sensitiveInputNames.forEach((name) => {
    if (Object.prototype.hasOwnProperty.call(displayValues, name)) displayValues[name] = '[hidden]';
  });
  const ready = workflowInputsReady(workflow, renderedValues);
  const steps = Array.isArray(workflow?.steps) ? workflow.steps : [];
  const captureNames = new Set();
  return {
    ready,
    steps: steps.map((step) => {
      const usedTokens = workflowTemplateTokens(step.cmd || '');
      const pendingCaptureNames = [...usedTokens].filter(token => captureNames.has(token));
      const usedSensitiveInputNames = [...usedTokens].filter(token => sensitiveInputNames.has(token));
      const renderedStep = {
        ...step,
        pendingCaptureNames,
        sensitiveInputNames: usedSensitiveInputNames,
        displayCmd: renderWorkflowCommandTemplate(step.cmd || '', displayValues).trim(),
        renderedCmd: renderWorkflowCommandTemplate(step.cmd || '', renderedValues).trim(),
      };
      (Array.isArray(step.captures) ? step.captures : []).forEach((capture) => {
        if (capture?.name) captureNames.add(String(capture.name));
      });
      return renderedStep;
    }),
  };
}

export {
  appendWorkflowInputSourcePicker,
  buildRenderedWorkflow,
  getWorkflowInputValues,
  loadWorkflowInputValues,
  persistWorkflowInputValues,
  renderWorkflowCommandTemplate,
  sanitizeWorkflowInputValue,
};
