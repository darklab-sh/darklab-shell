// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// The first tab depends on action defaults and active runs, not recall history.
// Scope changes invalidate every outstanding response, even a change back.
export function startShellSession({ loadPreferences, loadActive, loadHistory, hydrate, restore, onError }) {
  let revision = 0;
  let restored = false;
  const recover = (context, fallback) => error => {
    onError(context, error);
    return fallback;
  };
  function start() {
    const current = ++revision;
    const history = loadHistory().catch(recover('failed to load /history/commands', { runs: [] }));
    const ready = Promise.all([
      loadPreferences().catch(recover('failed to apply session preferences', null)),
      loadActive().catch(recover('failed to load /history/active', { runs: [] })),
    ]).then(([, active]) => {
      if (current !== revision) return;
      restore(active.runs || []);
      restored = true;
    });
    // Also wait for restoration so late recall cannot reset the restored draft.
    void Promise.all([ready, history]).then(([, data]) => {
      if (current === revision) hydrate(data.runs || []);
    }).catch(recover('failed to restore shell session', null));
    return ready;
  }
  return {
    ready: start(),
    scopeChanged: () => {
      revision += 1;
      if (!restored) void start();
    },
  };
}
