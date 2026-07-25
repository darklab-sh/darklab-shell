// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Client-side saved-run persistence for local runner commands.

function createRunnerPersistence({
  apiFetch,
  maskSessionToken,
  isHistoryPanelOpen,
  refreshHistoryPanel,
  logClientError,
} = {}) {
  function historySafeCommand(cmd) {
    const value = String(cmd || '').trim();
    if (!value) return '';
    const mask = typeof maskSessionToken === 'function' ? maskSessionToken : token => token;
    return value.replace(
      /\b(session-token\s+(?:set|revoke)\s+)(tok_[A-Za-z0-9]+|[0-9a-f]{8}-[0-9a-f-]{28,})\b/i,
      (_match, prefix, token) => `${prefix}${mask(token)}`,
    ).replace(
      /^(\s*secret\s+set\s+\S+)(?:\s+.+)$/i,
      (_match, prefix) => prefix,
    );
  }

  function exitCodeFromStatus(statusValue) {
    return statusValue === 'fail' ? 1 : 0;
  }

  function persistClientSideRun(command, lineItems, statusValue, tabId = '') {
    const safeCommand = historySafeCommand(command);
    if (!safeCommand || typeof apiFetch !== 'function') return Promise.resolve(null);
    const lines = (Array.isArray(lineItems) ? lineItems : []).map((line) => {
      const entry = {
        text: String(line && line.text !== undefined ? line.text : line || ''),
        cls: String(line && line.cls || ''),
      };
      if (typeof line?.kind === 'string' && line.kind) entry.kind = line.kind;
      if (typeof line?.role === 'string' && line.role) entry.role = line.role;
      return entry;
    });
    return apiFetch('/run/client', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command: safeCommand,
        exit_code: exitCodeFromStatus(statusValue),
        lines,
        tab_id: String(tabId || ''),
      }),
    }).then(async (resp) => {
      if (!resp || !resp.ok) throw new Error(String(resp && resp.status || 'unknown'));
      const payload = typeof resp.json === 'function'
        ? await resp.json().catch(() => ({}))
        : {};
      const savedRun = (
        payload?.run
        && typeof payload.run === 'object'
        && !Array.isArray(payload.run)
      ) ? payload.run : payload;
      if (
        typeof isHistoryPanelOpen === 'function'
        && isHistoryPanelOpen()
        && typeof refreshHistoryPanel === 'function'
      ) {
        refreshHistoryPanel();
      }
      return savedRun;
    }).catch((err) => {
      if (typeof logClientError === 'function') {
        logClientError('client-side run persistence failed', err);
      }
      return null;
    });
  }

  return {
    historySafeCommand,
    exitCodeFromStatus,
    persistClientSideRun,
  };
}

const DarklabRunnerPersistence = { create: createRunnerPersistence };

if (typeof window !== 'undefined') {
}

export {
  DarklabRunnerPersistence,
  createRunnerPersistence,
};
