// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { setProjectContextHandlers } from '../../../app/static/js/features/projects/project_context_bridge.js';
import {
  formatProbeCatalog,
  formatProbePlan,
  handleProbeTerminalCommand,
  parseProbeCommand,
} from '../../../app/static/js/features/probes/probe_terminal.js';
import { setRuntimeHandlers } from '../../../app/static/js/runtime_bridge.js';


function response(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn(async () => payload),
  };
}

function execution() {
  return {
    appendLine: vi.fn(),
    setPersistence: vi.fn(),
    setRecordRecent: vi.fn(),
    setStatus: vi.fn(),
  };
}

describe('Project probe terminal', () => {
  let clientLog;

  beforeEach(() => {
    clientLog = vi.fn();
    setRuntimeHandlers({ logClientError: clientLog });
    setProjectContextHandlers({
      getActiveProjectContext: () => ({ id: 'prj_active' }),
      refreshActiveProjectContext: async () => ({ id: 'prj_active' }),
    });
  });

  it('parses exact-target and entity-id plans without weakening the selector contract', () => {
    expect(parseProbeCommand('probe plan nmap example.test --project prj_1 --nmap-profile tls')).toMatchObject({
      subcommand: 'plan',
      actionId: 'nmap',
      targetValue: 'example.test',
      projectId: 'prj_1',
      nmapProfile: 'tls',
      errors: [],
    });
    expect(parseProbeCommand('probe plan ping --entity-id ent_1 --project=prj_1')).toMatchObject({
      entityId: 'ent_1',
      projectId: 'prj_1',
      errors: [],
    });
    expect(parseProbeCommand(
      'probe run httpx --entity-id ent_1 --project prj_1 --http-profile hpr_1',
    )).toMatchObject({
      actionId: 'httpx',
      httpProfileId: 'hpr_1',
      errors: [],
    });
    expect(parseProbeCommand(
      'probe run httpx --entity-id ent_1 --project prj_1 --http-profile "Protected probe application"',
    )).toMatchObject({
      actionId: 'httpx',
      httpProfileId: 'Protected probe application',
      errors: [],
    });
    expect(parseProbeCommand('probe plan ping example.test --entity-id ent_1 --project prj_1').errors)
      .toContain('provide either an exact target or --entity-id, not both');
    expect(parseProbeCommand('probe list --unknown value').errors)
      .toContain("unknown option '--unknown'");
    expect(parseProbeCommand(
      'probe list --project prj_2 --service https --target-type url',
    )).toMatchObject({
      subcommand: 'list',
      projectId: 'prj_2',
      service: 'https',
      targetType: 'url',
      errors: [],
    });
    expect(parseProbeCommand('probe list --target-type cidr').errors)
      .toContain("option '--target-type' must be domain, ip, or url");
    expect(parseProbeCommand('probe run ping --entity-id ent_1 --project=prj_1')).toMatchObject({
      subcommand: 'run',
      entityId: 'ent_1',
      projectId: 'prj_1',
      errors: [],
    });
  });

  it('formats catalogs and plans as compact terminal-native output', () => {
    expect(formatProbeCatalog({
      actions: [{
        id: 'ping', label: 'Ping', policy_level: 'safe', target_types: ['domain', 'ip'],
        exclusions: ['raw_packets'],
        availability: { available: true },
      }],
      nmap_profiles: [{ key: 'safe' }],
      nuclei_profiles: [{
        key: 'intrusive',
        availability: {
          available: false,
          code: 'intrusive_actions_disabled',
          reason: "Intrusive probe actions aren't enabled.",
        },
      }],
      service_recommendations: [{
        action_id: 'nmap', nmap_profile: 'smb', label: 'Review SMB',
        rationale: 'Confirm the discovered SMB surface.',
      }],
      exclusions: ['zap', 'oast_allocation'],
    })).toEqual([
      'Probe actions:',
      '  ping  Ping [safe] (domain, ip) — excludes: raw_packets',
      'Service recommendations:',
      '  nmap, profile smb  Review SMB — Confirm the discovered SMB surface.',
      'Nmap profiles: safe',
      "Nuclei profiles: intrusive (unavailable: Intrusive probe actions aren't enabled.)",
      'Excluded from probes: zap, oast_allocation',
    ]);
    const lines = formatProbePlan({
      project_id: 'prj_1',
      action: { id: 'ping', label: 'Ping' },
      target: { entity_id: 'ent_1', type: 'domain', value: 'example.test' },
      policy_level: 'safe',
      display_command: 'ping -c 4 example.test',
      bounds: { summary: 'Four probes.', request_limit: 4, time_limit_seconds: 15, credential_use: 'none' },
      http_profile: {
        id: 'hpr_1', name: 'User session', role: 'user',
        scope: {
          allowed_hosts: ['example.test'], scope_roots: ['https://example.test/app'],
          include_paths: ['/app'], exclude_paths: ['/app/private'],
        },
      },
      expected_evidence: ['run'],
      plan_digest: 'a'.repeat(64),
      availability: { available: false, code: 'feature_unavailable' },
      feature_gates: ['ping'],
    });
    expect(lines).toContain('  Command: ping -c 4 example.test');
    expect(lines).toContain('  HTTP profile: User session (user)');
    expect(lines).toContain(
      '  HTTP scope: hosts example.test; roots https://example.test/app; include /app; exclude /app/private',
    );
    expect(lines.indexOf('  Credentials: none')).toBeLessThan(
      lines.indexOf('  HTTP profile: User session (user)'),
    );
    expect(lines.indexOf('  HTTP profile: User session (user)')).toBeLessThan(
      lines.indexOf('  Evidence: run'),
    );
    expect(lines).toContain(`  Approval digest: ${'a'.repeat(12)}`);
    expect(lines).toContain('  Missing features: ping');
    expect(lines.join('\n')).not.toContain('a'.repeat(64));
  });

  it('loads an explicit or active Project catalog without creating a client History record', async () => {
    const apiFetch = vi.fn(async (url) => response(url === '/projects?include_archived=1' ? {
      projects: [
        { id: 'prj_explicit', slug: 'explicit-case', name: 'Explicit Case', status: 'active' },
        { id: 'prj_archived', slug: 'archived-case', name: 'Archived Case', status: 'archived' },
      ],
    } : {
      catalog: {
        actions: [], nmap_profiles: [], nuclei_profiles: [], service_recommendations: [],
      },
    }));
    setRuntimeHandlers({ apiFetch });
    const commandExecution = execution();

    await handleProbeTerminalCommand('probe list --service https', 'tab-1', commandExecution);

    expect(apiFetch).toHaveBeenCalledWith(
      '/projects/prj_active/probes?service=https',
      { cache: 'no-store' },
    );
    expect(commandExecution.setPersistence).toHaveBeenCalledWith('none');
    expect(commandExecution.setRecordRecent).toHaveBeenCalledWith(false);
    expect(commandExecution.setStatus).toHaveBeenCalledWith('ok');

    await handleProbeTerminalCommand(
      'probe list --project explicit-case --service http --target-type url',
      'tab-1',
      commandExecution,
    );
    expect(apiFetch).toHaveBeenLastCalledWith(
      '/projects/prj_explicit/probes?service=http&target_type=url',
      { cache: 'no-store' },
    );
  });

  it('resolves an exact target before requesting an entity-anchored plan', async () => {
    const apiFetch = vi.fn(async (url) => {
      if (url === '/projects?include_archived=1') {
        return response({
          projects: [{ id: 'prj_1', slug: 'project-one', name: 'Project One', status: 'active' }],
        });
      }
      if (url.endsWith('/targets/resolve')) {
        return response({ target: { entity_id: 'ent_1', type: 'domain', value: 'example.test' } });
      }
      return response({
        plan: {
          project_id: 'prj_1',
          action: { id: 'ping', label: 'Ping' },
          target: { entity_id: 'ent_1', type: 'domain', value: 'example.test' },
          policy_level: 'safe',
          display_command: 'ping -c 4 example.test',
          bounds: { summary: 'Four probes.', request_limit: 4, time_limit_seconds: 15, credential_use: 'none' },
          expected_evidence: ['run'],
          plan_digest: 'b'.repeat(64),
          availability: { available: true },
        },
      });
    });
    setRuntimeHandlers({ apiFetch });
    const commandExecution = execution();

    await handleProbeTerminalCommand(
      'probe plan ping example.test --project project-one',
      'tab-mobile',
      commandExecution,
    );

    expect(apiFetch.mock.calls[1]).toEqual([
      '/projects/prj_1/probes/targets/resolve',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_value: 'example.test' }),
        cache: 'no-store',
      },
    ]);
    expect(apiFetch.mock.calls[1][0]).not.toContain('example.test');
    expect(apiFetch.mock.calls[2][0]).toContain(
      '/projects/prj_1/probes/plan?action_id=ping&entity_id=ent_1',
    );
    expect(commandExecution.appendLine).toHaveBeenCalledWith(
      '  Command: ping -c 4 example.test',
      'builtin-help-row',
      'tab-mobile',
    );
    expect(commandExecution.setPersistence).toHaveBeenCalledWith('none');
    expect(commandExecution.setRecordRecent).toHaveBeenCalledWith(false);
  });

  it('reports server failures without persisting the read command', async () => {
    setRuntimeHandlers({
      apiFetch: vi.fn(async () => response({ error: 'Project not found operator-secret' }, 404)),
    });
    const commandExecution = execution();
    await handleProbeTerminalCommand('probe list', 'tab-1', commandExecution);
    expect(commandExecution.appendLine).toHaveBeenCalledWith(
      '[probe] Project not found operator-secret',
      'exit-fail',
      'tab-1',
    );
    expect(commandExecution.setStatus).toHaveBeenCalledWith('fail');
    expect(commandExecution.setPersistence).toHaveBeenCalledWith('none');
    expect(clientLog).toHaveBeenCalledWith(
      'PROJECT_PROBE_CLIENT_REQUEST_FAILED',
      expect.objectContaining({
        name: 'ProbeRequestError',
        message: 'Probe request failed',
        status: 404,
      }),
      {
        page: 'probe_terminal',
        event: 'PROJECT_PROBE_CLIENT_REQUEST_FAILED',
        level: 'warning',
        source: 'browser_terminal',
        phase: 'catalog',
        project_id: 'prj_active',
        status: 404,
        error_name: 'ProbeRequestError',
      },
    );
    expect(JSON.stringify(clientLog.mock.calls)).not.toContain('operator-secret');
  });

  it('reports an invalid success payload as a client response-shape error', async () => {
    setRuntimeHandlers({ apiFetch: vi.fn(async () => response([])) });
    const commandExecution = execution();

    await handleProbeTerminalCommand('probe list', 'tab-1', commandExecution);

    expect(commandExecution.setStatus).toHaveBeenCalledWith('fail');
    expect(clientLog).toHaveBeenCalledWith(
      'PROJECT_PROBE_CLIENT_REQUEST_FAILED',
      expect.objectContaining({ name: 'ProbeResponseError' }),
      expect.objectContaining({
        level: 'error',
        phase: 'catalog',
        project_id: 'prj_active',
        error_name: 'ProbeResponseError',
      }),
    );
  });

  it('previews before confirmation and launches only after an origin-tab yes', async () => {
    const plan = {
      project_id: 'prj_1',
      action: { id: 'httpx', label: 'HTTPx' },
      target: { entity_id: 'ent_1', type: 'url', value: 'https://example.test/app' },
      policy_level: 'safe',
      display_command: 'httpx -u https://example.test/app -sf [protected]',
      bounds: {
        summary: 'One protected HTTP request.', request_limit: 1,
        time_limit_seconds: 30, credential_use: 'protected_http_profile',
      },
      expected_evidence: ['run'],
      http_profile: {
        id: 'hpr_1', name: 'User session', role: 'user', revision: 1,
        scope: {
          allowed_hosts: ['example.test'], scope_roots: ['https://example.test/app'],
          include_paths: ['/app'], exclude_paths: ['/app/private'],
        },
      },
      plan_digest: 'c'.repeat(64),
      availability: { available: true },
      launchable: true,
    };
    const apiFetch = vi.fn(async (url, options = {}) => {
      if (url === '/projects?include_archived=1') {
        return response({
          projects: [{ id: 'prj_1', slug: 'project-one', name: 'Project One', status: 'active' }],
        });
      }
      if (options.method === 'POST') {
        return response({
          project_id: 'prj_1',
          run: { run_id: 'run_1', command: plan.display_command, stream: '/runs/run_1/stream' },
        }, 202);
      }
      return response({ plan });
    });
    setRuntimeHandlers({ apiFetch });
    const commandExecution = execution();
    let pending;
    const bindStartedRun = vi.fn();

    await handleProbeTerminalCommand(
      'probe run httpx --entity-id ent_1 --project project-one --http-profile hpr_1',
      'tab-origin',
      commandExecution,
      {
        workspaceCwd: 'evidence',
        requestConfirmation: config => { pending = config; },
        bindStartedRun,
      },
    );

    expect(commandExecution.appendLine).toHaveBeenCalledWith(
      'Run this probe? Type yes or no.',
      'notice',
      'tab-origin',
    );
    expect(apiFetch).toHaveBeenCalledTimes(2);
    expect(pending.kind).toBe('probe');
    expect(pending.tabId).toBe('tab-origin');
    expect(commandExecution.setPersistence).toHaveBeenCalledWith('none');
    expect(commandExecution.setRecordRecent).toHaveBeenCalledWith(true);
    const launched = await pending.onYes();
    await pending.onComplete(launched);
    expect(apiFetch).toHaveBeenLastCalledWith(
      '/projects/prj_1/probes/run',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          action_id: 'httpx',
          entity_id: 'ent_1',
          http_profile_id: 'hpr_1',
          nmap_profile: '',
          nuclei_profile: 'safe',
          confirmed: true,
          plan_digest: 'c'.repeat(64),
          tab_id: 'tab-origin',
          workspace_cwd: 'evidence',
        }),
      }),
    );
    expect(bindStartedRun).toHaveBeenCalledWith(launched, 'tab-origin');
    expect(commandExecution.setStatus).not.toHaveBeenCalledWith('ok');
  });

  it('settles a declined probe and stops unauthorized plans before confirmation', async () => {
    const apiFetch = vi.fn(async () => response({
      plan: {
        project_id: 'prj_1', action: { id: 'ping', label: 'Ping' },
        target: { entity_id: 'ent_1', type: 'domain', value: 'example.test' },
        policy_level: 'safe', display_command: 'ping -c 4 example.test',
        bounds: {}, expected_evidence: [], plan_digest: 'd'.repeat(64),
        availability: { available: true }, launchable: true,
      },
    }));
    setRuntimeHandlers({ apiFetch });
    const commandExecution = execution();
    let pending;
    await handleProbeTerminalCommand(
      'probe run ping --entity-id ent_1 --project prj_1',
      'tab-1',
      commandExecution,
      { requestConfirmation: config => { pending = config; }, bindStartedRun: vi.fn() },
    );
    pending.onNo();
    expect(apiFetch).toHaveBeenCalledTimes(1);
    expect(commandExecution.appendLine).toHaveBeenCalledWith(
      'Probe launch canceled.',
      '',
      'tab-1',
    );

    const deniedExecution = execution();
    let deniedPending;
    setRuntimeHandlers({
      apiFetch: vi.fn(async () => response({
        plan: {
          project_id: 'prj_1', action: { id: 'ping', label: 'Ping' },
          target: { entity_id: 'ent_1', type: 'domain', value: 'example.test' },
          policy_level: 'safe', display_command: 'ping -c 4 example.test',
          bounds: {}, expected_evidence: [], plan_digest: 'f'.repeat(64),
          availability: { available: true }, launchable: true,
          launch_authorization: {
            authorized: false,
            required_capabilities: ['run_commands'],
            missing_capabilities: ['run_commands'],
            reason: "Your Team role doesn't allow probe launches in this scope.",
          },
        },
      })),
    });
    await handleProbeTerminalCommand(
      'probe run ping --entity-id ent_1 --project prj_1',
      'tab-viewer',
      deniedExecution,
      {
        requestConfirmation: config => { deniedPending = config; },
        bindStartedRun: vi.fn(),
      },
    );
    expect(deniedPending).toBeUndefined();
    expect(deniedExecution.appendLine).toHaveBeenCalledWith(
      "  Launch permission: Your Team role doesn't allow probe launches in this scope.",
      'builtin-help-row',
      'tab-viewer',
    );
    expect(deniedExecution.appendLine).not.toHaveBeenCalledWith(
      'Run this probe? Type yes or no.',
      expect.anything(),
      'tab-viewer',
    );
    expect(deniedExecution.setStatus).toHaveBeenCalledWith('fail');
  });

  it('reports a confirmed launch failure with only bounded probe context', async () => {
    const plan = {
      project_id: 'prj_1', action: { id: 'httpx', label: 'HTTPx' },
      target: { entity_id: 'ent_1', type: 'url', value: 'https://operator-secret.test' },
      policy_level: 'safe', display_command: 'httpx -u https://operator-secret.test',
      bounds: {}, expected_evidence: [], plan_digest: 'e'.repeat(64),
      availability: { available: true }, launchable: true,
    };
    const apiFetch = vi.fn(async (_url, options = {}) => {
      if (options.method === 'POST') {
        return response({ error: 'profile hpr_operator_secret failed' }, 503);
      }
      return response({ plan });
    });
    setRuntimeHandlers({ apiFetch });
    const commandExecution = execution();
    let pending;
    await handleProbeTerminalCommand(
      'probe run httpx --entity-id ent_1 --project prj_1 --http-profile hpr_operator_secret',
      'tab-1',
      commandExecution,
      { requestConfirmation: config => { pending = config; }, bindStartedRun: vi.fn() },
    );

    await expect(pending.onYes()).rejects.toThrow('profile hpr_operator_secret failed');

    expect(clientLog).toHaveBeenCalledWith(
      'PROJECT_PROBE_CLIENT_REQUEST_FAILED',
      expect.objectContaining({ name: 'ProbeRequestError', message: 'Probe request failed' }),
      expect.objectContaining({
        level: 'warning', phase: 'launch', project_id: 'prj_1', status: 503,
      }),
    );
    expect(JSON.stringify(clientLog.mock.calls)).not.toMatch(
      /operator-secret|hpr_operator_secret|httpx -u|\/probes\/run/,
    );
  });
});
