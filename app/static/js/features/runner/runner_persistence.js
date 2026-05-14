// Client-side saved-run persistence for local runner commands.

window.DarklabRunnerPersistence = (() => {
  function create({
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

    function persistClientSideRun(command, lineItems, statusValue) {
      const safeCommand = historySafeCommand(command);
      if (!safeCommand || typeof apiFetch !== 'function') return;
      const lines = (Array.isArray(lineItems) ? lineItems : []).map((line) => ({
        text: String(line && line.text !== undefined ? line.text : line || ''),
        cls: String(line && line.cls || ''),
      }));
      apiFetch('/run/client', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          command: safeCommand,
          exit_code: exitCodeFromStatus(statusValue),
          lines,
        }),
      }).then((resp) => {
        if (!resp || !resp.ok) throw new Error(String(resp && resp.status || 'unknown'));
        if (
          typeof isHistoryPanelOpen === 'function'
          && isHistoryPanelOpen()
          && typeof refreshHistoryPanel === 'function'
        ) {
          refreshHistoryPanel();
        }
      }).catch((err) => {
        if (typeof logClientError === 'function') {
          logClientError('client-side run persistence failed', err);
        }
      });
    }

    return {
      historySafeCommand,
      exitCodeFromStatus,
      persistClientSideRun,
    };
  }

  return { create };
})();
