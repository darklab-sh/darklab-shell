// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { fromScript } from './helpers/extract.js'
import { createRunnerPersistence } from '../../../app/static/js/features/runner/runner_persistence.js'

const { DarklabCommandLifecycle } = fromScript(
  'app/static/js/features/runner/command_lifecycle.js',
  'DarklabCommandLifecycle',
)

const {
  createCommandCompletionCoordinator,
  createCommandExecution,
  normalizeCommandResult,
} = DarklabCommandLifecycle

describe('terminal command result contract', () => {
  it('normalizes lines, status, persistence, and enabled refresh effects', () => {
    expect(normalizeCommandResult({
      command: 'theme list',
      safeCommand: 'theme list',
      tabId: 'tab-1',
      lines: [
        'Available themes:',
        { text: 'theme_dark_amber', cls: 'builtin-help-row', kind: 'text' },
      ],
      status: 'idle',
      persistence: 'client',
      effects: {
        refreshWorkspace: true,
        refreshVariables: false,
      },
    })).toMatchObject({
      command: 'theme list',
      safeCommand: 'theme list',
      tabId: 'tab-1',
      lines: [
        { text: 'Available themes:', cls: '' },
        {
          text: 'theme_dark_amber',
          cls: 'builtin-help-row',
          kind: 'text',
        },
      ],
      status: 'ok',
      exitCode: 0,
      persistence: 'client',
      effects: { refreshWorkspace: true },
    })
    expect(normalizeCommandResult({ status: 'fail' })).toMatchObject({
      status: 'fail',
      exitCode: 1,
    })
    expect(normalizeCommandResult({
      lines: 'not-an-array',
      metadata: 'not-an-object',
      recordRecent: 'true',
    })).toMatchObject({
      lines: [],
      metadata: {},
      recordRecent: false,
    })
  })

  it('collects buffered handler output and command-specific completion policy', () => {
    const execution = createCommandExecution({
      command: 'workflow list',
      safeCommand: 'workflow list',
      tabId: 'tab-1',
      recordRecent: false,
    })

    execution.appendLine('Workflows:', 'builtin-section')
    execution.setRecordRecent(true)
    execution.requestEffect('refreshWorkflows')
    execution.setStatus('ok')

    expect(execution.toResult()).toMatchObject({
      completionKey: expect.stringMatching(/^client:/),
      lines: [{ text: 'Workflows:', cls: 'builtin-section' }],
      status: 'ok',
      exitCode: 0,
      recordRecent: true,
      effects: { refreshWorkflows: true },
    })
  })
})

describe('terminal completion coordinator', () => {
  it('renders, records, persists, and applies completion exactly once', async () => {
    const renderLine = vi.fn()
    const applyStatus = vi.fn()
    const recordRecent = vi.fn()
    const persistClient = vi.fn(() => Promise.resolve({
      id: 'client-run-1',
      command: 'secret set SHODAN_API_KEY',
      exit_code: 0,
    }))
    const afterComplete = vi.fn()
    const coordinator = createCommandCompletionCoordinator({
      renderLine,
      applyStatus,
      recordRecent,
      persistClient,
      afterComplete,
    })
    const result = normalizeCommandResult({
      completionKey: 'client:one',
      command: 'secret set SHODAN_API_KEY value',
      safeCommand: 'secret set shodan_api_key',
      tabId: 'tab-1',
      lines: [{ text: 'Secret set canceled.' }],
      status: 'ok',
      persistence: 'client',
      recordRecent: true,
    })

    expect((await coordinator.complete(result)).completed).toBe(true)
    expect((await coordinator.complete(result)).completed).toBe(false)

    expect(renderLine).toHaveBeenCalledOnce()
    expect(applyStatus).toHaveBeenCalledOnce()
    expect(recordRecent).toHaveBeenCalledOnce()
    expect(recordRecent).toHaveBeenCalledWith(
      'secret set SHODAN_API_KEY',
      expect.objectContaining({
        savedRun: expect.objectContaining({ id: 'client-run-1' }),
      }),
      expect.objectContaining({ id: 'client-run-1' }),
    )
    expect(persistClient).toHaveBeenCalledOnce()
    expect(afterComplete).toHaveBeenCalledOnce()
  })

  it('does not redraw streamed lines or re-persist server-owned runs', async () => {
    const renderLine = vi.fn()
    const persistClient = vi.fn()
    const coordinator = createCommandCompletionCoordinator({
      renderLine,
      persistClient,
    })

    await coordinator.complete({
      completionKey: 'run:one',
      command: 'ping darklab.sh',
      safeCommand: 'ping darklab.sh',
      tabId: 'tab-1',
      lines: [{ text: 'already streamed', rendered: true }],
      status: 'fail',
      exitCode: 2,
      persistence: 'server',
    })

    expect(renderLine).not.toHaveBeenCalled()
    expect(persistClient).not.toHaveBeenCalled()
  })
})

describe('browser-owned run persistence', () => {
  it('returns the canonical saved run and refreshes open history once', async () => {
    const savedRun = {
      id: 'client-run-1',
      command: 'secret set SHODAN_API_KEY',
      exit_code: 0,
    }
    const apiFetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        ok: true,
        run_id: savedRun.id,
        output_line_count: 1,
        run: savedRun,
      }),
    }))
    const refreshHistoryPanel = vi.fn()
    const persistence = createRunnerPersistence({
      apiFetch,
      maskSessionToken: token => `${token.slice(0, 8)}…`,
      isHistoryPanelOpen: () => true,
      refreshHistoryPanel,
    })

    await expect(persistence.persistClientSideRun(
      'secret set SHODAN_API_KEY plain-secret-value',
      [{ text: 'SHODAN_API_KEY stored.', cls: 'builtin-success' }],
      'ok',
      'tab-1',
    )).resolves.toEqual(savedRun)

    const request = apiFetch.mock.calls[0][1]
    expect(JSON.parse(request.body)).toEqual({
      command: 'secret set SHODAN_API_KEY',
      exit_code: 0,
      lines: [{ text: 'SHODAN_API_KEY stored.', cls: 'builtin-success' }],
      tab_id: 'tab-1',
    })
    expect(refreshHistoryPanel).toHaveBeenCalledOnce()
  })
})
