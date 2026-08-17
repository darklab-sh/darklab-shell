// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Terminal client for Project-scoped probe catalogs, plans, and confirmed runs.

import { apiFetch, logClientError } from '../../runtime_bridge.js';
import {
  getActiveProjectContext,
  refreshActiveProjectContext,
} from '../projects/project_context_bridge.js';
import {
  _readAutocompleteProjects,
} from '../autocomplete/suggestions.js';
import { setProbeTerminalHandler } from './probe_terminal_bridge.js';

const PROBE_CLIENT_FAILURE_EVENT = 'PROJECT_PROBE_CLIENT_REQUEST_FAILED';
const PROBE_CLIENT_PHASES = new Set(['project', 'catalog', 'resolve', 'plan', 'launch']);
const PROBE_PROJECT_ID_RE = /^prj_[A-Za-z0-9_-]{1,64}$/;
const PROBE_ERROR_NAME_RE = /^[A-Za-z][A-Za-z0-9]{0,63}$/;

function _probeErrorStatus(error) {
  const status = Number(error?.status || error?.statusCode || 0);
  return Number.isInteger(status) && status >= 100 && status <= 599 ? status : 0;
}

function _probeNetworkDegraded(error) {
  const name = String(error?.name || '');
  const message = String(error?.message || error || '').toLowerCase();
  return name === 'AbortError'
    || name === 'NetworkError'
    || /failed to fetch|fetch failed|networkerror|network request failed/.test(message);
}

function _probeClientLogLevel(error) {
  return _probeErrorStatus(error) || _probeNetworkDegraded(error) ? 'warning' : 'error';
}

function logProbeClientFailure(error, { phase = '', projectId = '' } = {}) {
  const payload = {
    page: 'probe_terminal',
    event: PROBE_CLIENT_FAILURE_EVENT,
    level: _probeClientLogLevel(error),
    source: 'browser_terminal',
    phase: PROBE_CLIENT_PHASES.has(phase) ? phase : 'unknown',
  };
  if (PROBE_PROJECT_ID_RE.test(projectId)) payload.project_id = projectId;
  const status = _probeErrorStatus(error);
  if (status) payload.status = status;
  const errorName = String(error?.name || 'Error');
  payload.error_name = PROBE_ERROR_NAME_RE.test(errorName) ? errorName : 'Error';
  const safeError = new Error('Probe request failed');
  safeError.name = payload.error_name;
  if (status) safeError.status = status;
  logClientError(PROBE_CLIENT_FAILURE_EVENT, safeError, payload);
}

const PROBE_USAGE = [
  'Usage:',
  '  probe list [--project <project-slug-or-id>] [--service <service>] [--target-type <domain|ip|url>]',
  '  probe plan <action> <target> --project <project-slug-or-id> [--http-profile <profile-name-or-id>] [--nmap-profile <profile>] [--nuclei-profile <profile>]',
  '  probe plan <action> --entity-id <entity-id> --project <project-slug-or-id> [--http-profile <profile-name-or-id>] [--nmap-profile <profile>] [--nuclei-profile <profile>]',
  '  probe run <action> <target> --project <project-slug-or-id> [--http-profile <profile-name-or-id>] [--nmap-profile <profile>] [--nuclei-profile <profile>]',
  '  probe run <action> --entity-id <entity-id> --project <project-slug-or-id> [--http-profile <profile-name-or-id>] [--nmap-profile <profile>] [--nuclei-profile <profile>]',
];

function _probeCommandTokens(command) {
  const tokens = [];
  const pattern = /"[^"]*"|'[^']*'|\S+/g;
  let match = pattern.exec(String(command || '').trim());
  while (match) {
    const value = match[0];
    const quoted = value.length >= 2 && (
      (value[0] === '"' && value[value.length - 1] === '"')
      || (value[0] === "'" && value[value.length - 1] === "'")
    );
    tokens.push(quoted ? value.slice(1, -1) : value);
    match = pattern.exec(String(command || '').trim());
  }
  return tokens;
}

function _parseFlags(tokens, allowed) {
  const values = {};
  const positional = [];
  const errors = [];
  for (let index = 0; index < tokens.length; index += 1) {
    const token = String(tokens[index] || '');
    if (!token.startsWith('--')) {
      positional.push(token);
      continue;
    }
    const separator = token.indexOf('=');
    const name = separator >= 0 ? token.slice(0, separator) : token;
    const key = allowed[name];
    if (!key) {
      errors.push(`unknown option '${name}'`);
      continue;
    }
    if (Object.prototype.hasOwnProperty.call(values, key)) {
      errors.push(`option '${name}' was provided more than once`);
      continue;
    }
    const value = separator >= 0 ? token.slice(separator + 1) : String(tokens[index + 1] || '');
    if (!value || (separator < 0 && value.startsWith('--'))) {
      errors.push(`option '${name}' requires a value`);
      continue;
    }
    values[key] = value;
    if (separator < 0) index += 1;
  }
  return { values, positional, errors };
}

function parseProbeCommand(command) {
  const tokens = _probeCommandTokens(command);
  const subcommand = String(tokens[1] || '').toLowerCase();
  if (!subcommand || ['help', '--help', '-h'].includes(subcommand)) {
    return { subcommand: 'help', errors: [] };
  }
  if (subcommand === 'list') {
    const parsed = _parseFlags(tokens.slice(2), {
      '--project': 'projectId',
      '--service': 'service',
      '--target-type': 'targetType',
    });
    if (parsed.values.targetType && !['domain', 'ip', 'url'].includes(parsed.values.targetType)) {
      parsed.errors.push("option '--target-type' must be domain, ip, or url");
    }
    if (parsed.positional.length) parsed.errors.push('probe list does not accept positional values');
    return {
      subcommand,
      projectId: parsed.values.projectId || '',
      service: parsed.values.service || '',
      targetType: parsed.values.targetType || '',
      errors: parsed.errors,
    };
  }
  if (!['plan', 'run'].includes(subcommand)) {
    return { subcommand, errors: [`unknown subcommand '${subcommand}'`] };
  }
  const parsed = _parseFlags(tokens.slice(2), {
    '--project': 'projectId',
    '--entity-id': 'entityId',
    '--http-profile': 'httpProfileId',
    '--nmap-profile': 'nmapProfile',
    '--nuclei-profile': 'nucleiProfile',
  });
  const [actionId = '', targetValue = '', ...extra] = parsed.positional;
  if (extra.length) parsed.errors.push(`probe ${subcommand} accepts one action and one target`);
  if (!actionId) parsed.errors.push(`probe ${subcommand} requires an action`);
  if (!parsed.values.projectId) parsed.errors.push(`probe ${subcommand} requires --project`);
  if (targetValue && parsed.values.entityId) {
    parsed.errors.push('provide either an exact target or --entity-id, not both');
  }
  if (!targetValue && !parsed.values.entityId) {
    parsed.errors.push(`probe ${subcommand} requires an exact target or --entity-id`);
  }
  return {
    subcommand,
    actionId,
    targetValue,
    projectId: parsed.values.projectId || '',
    entityId: parsed.values.entityId || '',
    httpProfileId: parsed.values.httpProfileId || '',
    nmapProfile: parsed.values.nmapProfile || '',
    nucleiProfile: parsed.values.nucleiProfile || '',
    errors: parsed.errors,
  };
}

async function _responseJson(response, phase) {
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(data?.error || `HTTP ${response.status}`);
    error.name = 'ProbeRequestError';
    error.status = response.status;
    error.probePhase = phase;
    throw error;
  }
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    const error = new Error('Probe response was not a JSON object');
    error.name = 'ProbeResponseError';
    error.probePhase = phase;
    throw error;
  }
  return data;
}

function _responseObject(data, key, phase) {
  const value = data?.[key];
  if (value && typeof value === 'object' && !Array.isArray(value)) return value;
  const error = new Error(`Probe response did not include ${key}`);
  error.name = 'ProbeResponseError';
  error.probePhase = phase;
  throw error;
}

function formatProbeCatalog(catalog) {
  const lines = ['Probe actions:'];
  (catalog.actions || []).forEach((action) => {
    const availability = action.availability?.available
      ? ''
      : ` — unavailable: ${action.availability?.reason || action.availability?.code || 'not available'}`;
    const exclusions = (action.exclusions || []).length
      ? ` — excludes: ${action.exclusions.join(', ')}`
      : '';
    lines.push(`  ${action.id}  ${action.label} [${action.policy_level}] (${(action.target_types || []).join(', ')})${availability}${exclusions}`);
  });
  if ((catalog.service_recommendations || []).length) {
    lines.push('Service recommendations:');
    catalog.service_recommendations.forEach((item) => {
      const profile = item.nmap_profile ? `, profile ${item.nmap_profile}` : '';
      const rationale = item.rationale ? ` — ${item.rationale}` : '';
      lines.push(`  ${item.action_id}${profile}  ${item.label}${rationale}`);
    });
  }
  const profiles = (items) => (items || []).map((item) => {
    if (item.availability?.available !== false) return item.key;
    const reason = item.availability?.reason || item.availability?.code || 'not available';
    return `${item.key} (unavailable: ${reason})`;
  }).join(', ') || 'none';
  lines.push(`Nmap profiles: ${profiles(catalog.nmap_profiles)}`);
  lines.push(`Nuclei profiles: ${profiles(catalog.nuclei_profiles)}`);
  lines.push(`Excluded from probes: ${(catalog.exclusions || []).join(', ') || 'none'}`);
  return lines;
}

function formatProbePlan(plan) {
  const httpProfile = plan.http_profile || {};
  const httpScope = httpProfile.scope || {};
  const lines = [
    `Probe plan: ${plan.action?.label || plan.action?.id || 'Unknown action'}`,
    `  Project: ${plan.project_id}`,
    `  Target: ${plan.target?.value || ''} (${plan.target?.type || 'unknown'}, ${plan.target?.entity_id || 'no entity id'})`,
    `  Policy: ${plan.policy_level}`,
    `  Command: ${plan.display_command || 'Unavailable'}`,
    `  Bounds: ${plan.bounds?.summary || 'No command bounds available'}`,
    `  Requests: ${plan.bounds?.request_limit ?? 'tool bounded'}; time: ${plan.bounds?.time_limit_seconds ?? 'tool bounded'} seconds`,
    `  Credentials: ${plan.bounds?.credential_use || 'none'}`,
    `  Evidence: ${(plan.expected_evidence || []).join(', ') || 'run output'}`,
    `  Approval digest: ${String(plan.plan_digest || '').slice(0, 12)}`,
  ];
  if (httpProfile.id) {
    const values = key => (httpScope[key] || []).join(', ') || 'none';
    lines.splice(8, 0,
      `  HTTP profile: ${httpProfile.name || httpProfile.id} (${httpProfile.role || 'anonymous'})`,
      `  HTTP scope: hosts ${values('allowed_hosts')}; roots ${values('scope_roots')}; include ${values('include_paths')}; exclude ${values('exclude_paths')}`,
    );
  }
  if (!plan.availability?.available) {
    lines.push(`  Unavailable: ${plan.availability?.reason || plan.availability?.code || 'not available'}`);
  }
  if ((plan.feature_gates || []).length) {
    lines.push(`  Missing features: ${plan.feature_gates.join(', ')}`);
  }
  if (plan.launch_authorization?.authorized === false) {
    lines.push(`  Launch permission: ${plan.launch_authorization.reason || 'You do not have permission to launch this probe.'}`);
  }
  return lines;
}

async function _activeProjectId() {
  const current = getActiveProjectContext();
  if (current?.id) return String(current.id);
  const refreshed = await refreshActiveProjectContext({ force: true });
  return String(refreshed?.id || '');
}

function _activeProjectForReference(projectRef, projects = _readAutocompleteProjects()) {
  const normalized = String(projectRef || '').trim().toLowerCase();
  if (!normalized) return null;
  return (Array.isArray(projects) ? projects : []).find((project) => (
    String(project?.status || '').toLowerCase() === 'active'
    && (
      String(project?.id || '') === projectRef
      || String(project?.slug || '').toLowerCase() === normalized
    )
  )) || null;
}

async function _canonicalProjectId(projectRef) {
  const reference = String(projectRef || '').trim();
  if (PROBE_PROJECT_ID_RE.test(reference)) return reference;
  let project = _activeProjectForReference(reference);
  if (!project) {
    const response = await apiFetch('/projects?include_archived=1', { cache: 'no-store' });
    const data = await _responseJson(response, 'project');
    project = _activeProjectForReference(reference, data.projects);
  }
  const projectId = String(project?.id || '');
  if (PROBE_PROJECT_ID_RE.test(projectId)) return projectId;
  const error = new Error(`Project slug '${reference}' doesn't match an active Project.`);
  error.name = 'ProbeProjectReferenceError';
  error.probePhase = 'project';
  throw error;
}

async function _loadCatalog(parsed) {
  const projectRef = parsed.projectId || await _activeProjectId();
  if (!projectRef) throw new Error('select an active Project before listing probes');
  const projectId = await _canonicalProjectId(projectRef);
  parsed.projectId = projectId;
  const query = new URLSearchParams();
  if (parsed.service) query.set('service', parsed.service);
  if (parsed.targetType) query.set('target_type', parsed.targetType);
  const suffix = query.size ? `?${query}` : '';
  const response = await apiFetch(`/projects/${encodeURIComponent(projectId)}/probes${suffix}`, { cache: 'no-store' });
  return _responseObject(await _responseJson(response, 'catalog'), 'catalog', 'catalog');
}

async function _loadPlan(parsed) {
  parsed.projectId = await _canonicalProjectId(parsed.projectId);
  let entityId = parsed.entityId;
  if (!entityId) {
    const targetResponse = await apiFetch(
      `/projects/${encodeURIComponent(parsed.projectId)}/probes/targets/resolve`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_value: parsed.targetValue }),
        cache: 'no-store',
      },
    );
    const target = _responseObject(
      await _responseJson(targetResponse, 'resolve'), 'target', 'resolve',
    );
    entityId = String(target.entity_id || '');
  }
  const query = new URLSearchParams({ action_id: parsed.actionId, entity_id: entityId });
  if (parsed.nmapProfile) query.set('nmap_profile', parsed.nmapProfile);
  if (parsed.nucleiProfile) query.set('nuclei_profile', parsed.nucleiProfile);
  if (parsed.httpProfileId) query.set('http_profile_id', parsed.httpProfileId);
  const response = await apiFetch(
    `/projects/${encodeURIComponent(parsed.projectId)}/probes/plan?${query}`,
    { cache: 'no-store' },
  );
  return _responseObject(await _responseJson(response, 'plan'), 'plan', 'plan');
}

async function _launchPlan(parsed, plan, tabId, launchAdapter) {
  const response = await apiFetch(
    `/projects/${encodeURIComponent(parsed.projectId)}/probes/run`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action_id: parsed.actionId,
        entity_id: plan.target?.entity_id || parsed.entityId,
        http_profile_id: parsed.httpProfileId,
        nmap_profile: parsed.nmapProfile,
        nuclei_profile: parsed.nucleiProfile || 'safe',
        confirmed: true,
        plan_digest: plan.plan_digest,
        tab_id: tabId,
        workspace_cwd: launchAdapter.workspaceCwd || '',
      }),
    },
  );
  return _responseJson(response, 'launch');
}

async function handleProbeTerminalCommand(command, tabId, execution, launchAdapter = {}) {
  if (!execution) throw new Error('Probe terminal commands require a command execution');
  execution.setPersistence('none');
  const append = (line, className = '') => execution.appendLine(line, className, tabId);
  const parsed = parseProbeCommand(command);
  execution.setRecordRecent(parsed.subcommand === 'run' && parsed.errors.length === 0);
  if (parsed.errors.length) {
    parsed.errors.forEach(error => append(`[probe] ${error}`, 'exit-fail'));
    PROBE_USAGE.forEach(line => append(line));
    execution.setStatus('fail');
    return true;
  }
  if (parsed.subcommand === 'help') {
    PROBE_USAGE.forEach(line => append(line));
    execution.setStatus('ok');
    return true;
  }
  try {
    if (parsed.subcommand === 'run') {
      if (
        typeof launchAdapter.requestConfirmation !== 'function'
        || typeof launchAdapter.bindStartedRun !== 'function'
      ) {
        throw new Error('probe launch controls are not ready — reload the page and try again');
      }
      const plan = await _loadPlan(parsed);
      formatProbePlan(plan).forEach((line, index) => {
        append(line, index === 0 ? 'builtin-section' : 'builtin-help-row');
      });
      if (!plan.launchable) {
        execution.setStatus('fail');
        return true;
      }
      if (plan.launch_authorization?.authorized === false) {
        execution.setStatus('fail');
        return true;
      }
      append('Run this probe? Type yes or no.', 'notice');
      launchAdapter.requestConfirmation({
        kind: 'probe',
        tabId,
        execution,
        onYes: async () => {
          try {
            return await _launchPlan(parsed, plan, tabId, launchAdapter);
          } catch (error) {
            logProbeClientFailure(error, {
              phase: error?.probePhase || 'launch', projectId: parsed.projectId,
            });
            throw error;
          }
        },
        onNo: () => {
          append('Probe launch canceled.');
          execution.setStatus('idle');
        },
        onCancel: () => {
          append('Probe launch canceled.');
          execution.setStatus('idle');
        },
        onComplete: launched => launchAdapter.bindStartedRun(launched, tabId),
      });
      return true;
    }
    const lines = parsed.subcommand === 'list'
      ? formatProbeCatalog(await _loadCatalog(parsed))
      : formatProbePlan(await _loadPlan(parsed));
    lines.forEach((line, index) => append(line, index === 0 ? 'builtin-section' : 'builtin-help-row'));
    execution.setStatus('ok');
  } catch (error) {
    logProbeClientFailure(error, {
      phase: error?.probePhase || (parsed.subcommand === 'list' ? 'catalog' : 'plan'),
      projectId: parsed.projectId || '',
    });
    append(`[probe] ${error.message || 'request failed'}`, 'exit-fail');
    execution.setStatus('fail');
  }
  return true;
}

setProbeTerminalHandler(handleProbeTerminalCommand);

export {
  PROBE_USAGE,
  formatProbeCatalog,
  formatProbePlan,
  handleProbeTerminalCommand,
  parseProbeCommand,
};
