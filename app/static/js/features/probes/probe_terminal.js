// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Terminal client for Project-scoped probe catalogs, plans, and confirmed runs.

import { apiFetch } from '../../runtime_bridge.js';
import {
  getActiveProjectContext,
  refreshActiveProjectContext,
} from '../projects/project_context_bridge.js';
import { setProbeTerminalHandler } from './probe_terminal_bridge.js';

const PROBE_USAGE = [
  'Usage:',
  '  probe list [--service <service>]',
  '  probe plan <action> <target> --project <project-id> [--http-profile <profile-id>] [--nmap-profile <profile>] [--nuclei-profile <profile>]',
  '  probe plan <action> --entity-id <entity-id> --project <project-id> [--http-profile <profile-id>] [--nmap-profile <profile>] [--nuclei-profile <profile>]',
  '  probe run <action> <target> --project <project-id> [--http-profile <profile-id>] [--nmap-profile <profile>] [--nuclei-profile <profile>]',
  '  probe run <action> --entity-id <entity-id> --project <project-id> [--http-profile <profile-id>] [--nmap-profile <profile>] [--nuclei-profile <profile>]',
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
    const parsed = _parseFlags(tokens.slice(2), { '--service': 'service' });
    if (parsed.positional.length) parsed.errors.push('probe list does not accept positional values');
    return { subcommand, service: parsed.values.service || '', errors: parsed.errors };
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

async function _responseJson(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function formatProbeCatalog(catalog) {
  const lines = ['Probe actions:'];
  (catalog.actions || []).forEach((action) => {
    const availability = action.availability?.available
      ? ''
      : ` — unavailable: ${action.availability?.reason || action.availability?.code || 'not available'}`;
    lines.push(`  ${action.id}  ${action.label} [${action.policy_level}] (${(action.target_types || []).join(', ')})${availability}`);
  });
  if ((catalog.service_recommendations || []).length) {
    lines.push('Service recommendations:');
    catalog.service_recommendations.forEach((item) => {
      const profile = item.nmap_profile ? `, profile ${item.nmap_profile}` : '';
      lines.push(`  ${item.action_id}${profile}  ${item.label}`);
    });
  }
  lines.push(`Nmap profiles: ${(catalog.nmap_profiles || []).map(item => item.key).join(', ') || 'none'}`);
  lines.push(`Nuclei profiles: ${(catalog.nuclei_profiles || []).map(item => item.key).join(', ') || 'none'}`);
  return lines;
}

function formatProbePlan(plan) {
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
    `  Digest: ${plan.plan_digest || ''}`,
  ];
  if (!plan.availability?.available) {
    lines.push(`  Unavailable: ${plan.availability?.reason || plan.availability?.code || 'not available'}`);
  }
  return lines;
}

async function _activeProjectId() {
  const current = getActiveProjectContext();
  if (current?.id) return String(current.id);
  const refreshed = await refreshActiveProjectContext({ force: true });
  return String(refreshed?.id || '');
}

async function _loadCatalog(parsed) {
  const projectId = await _activeProjectId();
  if (!projectId) throw new Error('select an active Project before listing probes');
  const query = new URLSearchParams();
  if (parsed.service) query.set('service', parsed.service);
  const suffix = query.size ? `?${query}` : '';
  const response = await apiFetch(`/projects/${encodeURIComponent(projectId)}/probes${suffix}`, { cache: 'no-store' });
  return (await _responseJson(response)).catalog || {};
}

async function _loadPlan(parsed) {
  let entityId = parsed.entityId;
  if (!entityId) {
    const targetQuery = new URLSearchParams({ value: parsed.targetValue });
    const targetResponse = await apiFetch(
      `/projects/${encodeURIComponent(parsed.projectId)}/probes/targets/resolve?${targetQuery}`,
      { cache: 'no-store' },
    );
    entityId = String((await _responseJson(targetResponse)).target?.entity_id || '');
  }
  const query = new URLSearchParams({ action_id: parsed.actionId, entity_id: entityId });
  if (parsed.nmapProfile) query.set('nmap_profile', parsed.nmapProfile);
  if (parsed.nucleiProfile) query.set('nuclei_profile', parsed.nucleiProfile);
  if (parsed.httpProfileId) query.set('http_profile_id', parsed.httpProfileId);
  const response = await apiFetch(
    `/projects/${encodeURIComponent(parsed.projectId)}/probes/plan?${query}`,
    { cache: 'no-store' },
  );
  return (await _responseJson(response)).plan || {};
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
  return _responseJson(response);
}

async function handleProbeTerminalCommand(command, tabId, execution, launchAdapter = {}) {
  if (!execution) throw new Error('Probe terminal commands require a command execution');
  execution.setPersistence('none');
  execution.setRecordRecent(false);
  const append = (line, className = '') => execution.appendLine(line, className, tabId);
  const parsed = parseProbeCommand(command);
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
      append('Run this probe? Type yes or no.', 'notice');
      launchAdapter.requestConfirmation({
        tabId,
        execution,
        onYes: async () => {
          const launched = await _launchPlan(parsed, plan, tabId, launchAdapter);
          execution.setStatus('ok');
          return launched;
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
