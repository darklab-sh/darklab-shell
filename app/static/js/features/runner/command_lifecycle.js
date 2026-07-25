// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Shared result and completion contract for terminal commands. Execution stays
// with the browser or server; this module owns the shape handed to the terminal
// once that execution is ready to settle.

const COMMAND_RESULT_STATUSES = new Set(['idle', 'ok', 'fail', 'killed']);
const COMMAND_RESULT_PERSISTENCE = new Set(['none', 'client', 'server']);
const MAX_COMPLETION_KEYS = 4096;
let commandExecutionSequence = 0;

function normalizeCommandLine(line) {
  const value = line && typeof line === 'object' && !Array.isArray(line)
    ? line
    : { text: line };
  const normalized = {
    text: String(value.text ?? ''),
    cls: String(value.cls || ''),
  };
  if (typeof value.kind === 'string' && value.kind) normalized.kind = value.kind;
  if (typeof value.role === 'string' && value.role) normalized.role = value.role;
  if (value.metadata && typeof value.metadata === 'object' && !Array.isArray(value.metadata)) {
    normalized.metadata = value.metadata;
  }
  if (value.rendered === true) normalized.rendered = true;
  return normalized;
}

function commandExitCode(status, exitCode = null) {
  if (exitCode !== null && exitCode !== undefined && exitCode !== '') {
    const parsed = Number(exitCode);
    if (Number.isInteger(parsed)) return parsed;
  }
  if (status === 'fail') return 1;
  if (status === 'killed') return -15;
  return 0;
}

function commandStatus(status, exitCode = null) {
  const value = COMMAND_RESULT_STATUSES.has(status) ? status : '';
  if (value === 'killed') return 'killed';
  if (value === 'fail') return 'fail';
  if (value === 'ok') return 'ok';
  return commandExitCode(value, exitCode) === 0 ? 'ok' : 'fail';
}

function normalizeCommandEffects(effects) {
  if (!effects || typeof effects !== 'object' || Array.isArray(effects)) return {};
  return Object.fromEntries(
    Object.entries(effects).filter(([, enabled]) => enabled === true),
  );
}

function normalizeCommandResult(result = {}, defaults = {}) {
  const source = result && typeof result === 'object' && !Array.isArray(result)
    ? result
    : {};
  const base = defaults && typeof defaults === 'object' && !Array.isArray(defaults)
    ? defaults
    : {};
  const rawStatus = String(source.status || base.status || 'idle').toLowerCase();
  const rawExitCode = source.exitCode ?? base.exitCode ?? null;
  const status = commandStatus(rawStatus, rawExitCode);
  const exitCode = commandExitCode(status, rawExitCode);
  const persistenceValue = String(source.persistence || base.persistence || 'none').toLowerCase();
  const persistence = COMMAND_RESULT_PERSISTENCE.has(persistenceValue)
    ? persistenceValue
    : 'none';
  const command = String(source.command ?? base.command ?? '').trim();
  const safeCommand = String(source.safeCommand ?? base.safeCommand ?? command).trim();
  const tabId = String(source.tabId ?? base.tabId ?? '');
  const completionKey = String(
    source.completionKey
      ?? base.completionKey
      ?? `${source.source || base.source || 'command'}:${tabId}:${safeCommand}`,
  );
  const lines = (
    Array.isArray(source.lines)
      ? source.lines
      : (Array.isArray(base.lines) ? base.lines : [])
  )
    .map(normalizeCommandLine);
  const metadata = (
    source.metadata && typeof source.metadata === 'object' && !Array.isArray(source.metadata)
      ? source.metadata
      : (
          base.metadata && typeof base.metadata === 'object' && !Array.isArray(base.metadata)
            ? base.metadata
            : {}
        )
  );
  return {
    command,
    safeCommand,
    tabId,
    source: String(source.source || base.source || 'browser'),
    completionKey,
    lines,
    status,
    exitCode,
    persistence,
    recordRecent: (source.recordRecent ?? base.recordRecent) === true,
    renderExit: (source.renderExit ?? base.renderExit) === true,
    elapsed: String(source.elapsed ?? base.elapsed ?? ''),
    suppressExitLine: (source.suppressExitLine ?? base.suppressExitLine) === true,
    effects: normalizeCommandEffects(source.effects || base.effects),
    metadata,
  };
}

function createCommandExecution({
  command = '',
  safeCommand = command,
  tabId = '',
  source = 'browser',
  persistence = 'client',
  recordRecent = true,
  streamLine = null,
  streamPendingLine = null,
} = {}) {
  commandExecutionSequence += 1;
  const state = {
    command: String(command || '').trim(),
    safeCommand: String(safeCommand || command || '').trim(),
    tabId: String(tabId || ''),
    source: String(source || 'browser'),
    completionKey: `client:${commandExecutionSequence}`,
    persistence,
    recordRecent,
    status: 'idle',
    exitCode: null,
    lines: [],
    effects: {},
    pending: false,
    delegated: false,
    completed: false,
  };

  function appendLine(text, cls = '', _tabId = state.tabId, metadata = null) {
    const line = normalizeCommandLine({ text, cls, metadata });
    if (typeof streamLine === 'function') {
      streamLine(line, state.tabId);
      line.rendered = true;
    } else if (state.pending && typeof streamPendingLine === 'function') {
      streamPendingLine(line, state.tabId);
      line.rendered = true;
    }
    state.lines.push(line);
    return line;
  }

  function captureRenderedLine(text, cls = '', metadata = null) {
    const line = normalizeCommandLine({
      text,
      cls,
      metadata,
      rendered: true,
    });
    state.lines.push(line);
    return line;
  }

  function setStatus(status, exitCode = null) {
    state.status = COMMAND_RESULT_STATUSES.has(status) ? status : 'idle';
    if (exitCode !== null && exitCode !== undefined && exitCode !== '') {
      const parsed = Number(exitCode);
      if (Number.isInteger(parsed)) state.exitCode = parsed;
    }
  }

  function setRecordRecent(enabled) {
    state.recordRecent = enabled === true;
  }

  function setSafeCommand(value) {
    const safeCommand = String(value || '').trim();
    if (safeCommand) state.safeCommand = safeCommand;
  }

  function setPersistence(value) {
    state.persistence = COMMAND_RESULT_PERSISTENCE.has(value) ? value : 'none';
  }

  function requestEffect(name, enabled = true) {
    const key = String(name || '').trim();
    if (key) state.effects[key] = enabled === true;
  }

  function setPending(enabled = true) {
    state.pending = enabled === true;
  }

  function delegate() {
    state.delegated = true;
    state.persistence = 'none';
    state.recordRecent = false;
  }

  function toResult(overrides = {}) {
    return normalizeCommandResult({
      ...state,
      ...overrides,
      lines: Array.isArray(overrides.lines) ? overrides.lines : state.lines,
      effects: { ...state.effects, ...(overrides.effects || {}) },
    });
  }

  return {
    appendLine,
    captureRenderedLine,
    delegate,
    isCompleted: () => state.completed,
    isDelegated: () => state.delegated,
    isPending: () => state.pending,
    markCompleted: () => { state.completed = true; },
    requestEffect,
    setPending,
    setPersistence,
    setRecordRecent,
    setSafeCommand,
    setStatus,
    state,
    toResult,
  };
}

function createCommandCompletionCoordinator({
  renderLine = null,
  renderExit = null,
  applyStatus = null,
  recordRecent = null,
  persistClient = null,
  afterComplete = null,
  onError = null,
} = {}) {
  const completedKeys = new Set();

  async function complete(value, defaults = {}) {
    const result = normalizeCommandResult(value, defaults);
    if (completedKeys.has(result.completionKey)) {
      return { completed: false, result };
    }
    completedKeys.add(result.completionKey);
    if (completedKeys.size > MAX_COMPLETION_KEYS) {
      completedKeys.delete(completedKeys.values().next().value);
    }

    try {
      if (typeof renderLine === 'function') {
        result.lines.filter(line => line.rendered !== true).forEach((line) => {
          renderLine(line, result);
        });
      }
      if (result.renderExit && !result.suppressExitLine && typeof renderExit === 'function') {
        renderExit(result);
      }
      if (typeof applyStatus === 'function') applyStatus(result);
      let savedRun = null;
      if (result.persistence === 'client' && typeof persistClient === 'function') {
        savedRun = await Promise.resolve(persistClient(result));
        if (savedRun && typeof savedRun === 'object' && !Array.isArray(savedRun)) {
          result.savedRun = savedRun;
          const savedCommand = String(savedRun.command || '').trim();
          if (savedCommand) result.safeCommand = savedCommand;
        }
      }
      if (result.recordRecent && result.safeCommand && typeof recordRecent === 'function') {
        recordRecent(result.safeCommand, result, savedRun);
      }
      if (typeof afterComplete === 'function') {
        await Promise.resolve(afterComplete(result));
      }
      return { completed: true, result };
    } catch (error) {
      if (typeof onError === 'function') onError(error, result);
      return { completed: true, result, error };
    }
  }

  return {
    complete,
    hasCompleted: key => completedKeys.has(String(key || '')),
  };
}

const DarklabCommandLifecycle = {
  commandExitCode,
  commandStatus,
  createCommandCompletionCoordinator,
  createCommandExecution,
  normalizeCommandLine,
  normalizeCommandResult,
};

export {
  DarklabCommandLifecycle,
  commandExitCode,
  commandStatus,
  createCommandCompletionCoordinator,
  createCommandExecution,
  normalizeCommandLine,
  normalizeCommandResult,
};
