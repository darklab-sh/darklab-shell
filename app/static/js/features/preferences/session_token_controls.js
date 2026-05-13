// ── Session token options panel ──

function _updateOptionsSessionTokenStatus() {
  const el = document.getElementById('options-session-token-status');
  if (!el) return;
  const token = localStorage.getItem('session_token');
  const hasToken = Boolean(token);
  el.textContent = hasToken ? maskSessionToken(token) : 'No session token — anonymous session';
  el.classList.toggle('is-active', hasToken);
  // Generate only when no token; Rotate, Clear, Copy only when one is active.
  const generateBtn = document.getElementById('options-session-token-generate-btn');
  const rotateBtn   = document.getElementById('options-session-token-rotate-btn');
  const clearBtn    = document.getElementById('options-session-token-clear-btn');
  const copyBtn     = document.getElementById('options-session-token-copy-btn');
  if (generateBtn) generateBtn.style.display = hasToken ? 'none' : '';
  if (rotateBtn)   rotateBtn.style.display   = hasToken ? '' : 'none';
  if (clearBtn)    clearBtn.style.display    = hasToken ? '' : 'none';
  if (copyBtn)     copyBtn.style.display     = hasToken ? '' : 'none';
  _optionsTokenShowMsg('');
}

function _optionsTokenSetBusy(busy) {
  ['options-session-token-generate-btn', 'options-session-token-set-btn',
   'options-session-token-rotate-btn',   'options-session-token-clear-btn'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.disabled = busy;
  });
}

function _optionsTokenShowMsg(msg, isError = false) {
  const el = document.getElementById('options-session-token-msg');
  if (!el) return;
  el.textContent = msg;
  el.style.display = msg ? '' : 'none';
  el.classList.toggle('is-error', isError);
}

async function _waitForMigrateChoice(msg) {
  if (typeof showConfirm !== 'function') return false;
  return await showConfirm({
    body: msg,
    actions: [
      { id: 'cancel', label: 'Cancel',       role: 'cancel' },
      { id: 'skip',   label: 'Skip',         role: 'secondary' },
      { id: 'yes',    label: 'Yes, migrate', role: 'primary' },
    ],
  });
}

function _optionsMigrationCountLabel(runCount = 0, workspaceFileCount = 0, workflowCount = 0, recentDomainCount = 0) {
  const parts = [];
  if (runCount > 0) parts.push(`${runCount} run(s)`);
  if (workspaceFileCount > 0) parts.push(`${workspaceFileCount} workspace file(s)`);
  if (workflowCount > 0) parts.push(`${workflowCount} workflow(s)`);
  if (recentDomainCount > 0) parts.push(`${recentDomainCount} recent domain(s)`);
  if (!parts.length) return 'no runs, workspace files, workflows, or recent domains';
  if (parts.length === 1) return parts[0];
  return `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`;
}

function _optionsMigrationResultText(data = {}) {
  const workspaceFiles = Number(data.migrated_workspace_files || 0);
  const skippedWorkspaceFiles = Number(data.skipped_workspace_files || 0);
  const workspaceDirs = Number(data.migrated_workspace_directories || 0);
  const skippedWorkspaceDirs = Number(data.skipped_workspace_directories || 0);
  const recentDomains = Number(data.migrated_recent_domains || 0);
  const workspaceParts = [`${workspaceFiles} workspace file(s)`];
  if (workspaceDirs > 0) workspaceParts.push(`${workspaceDirs} folder(s)`);
  if (skippedWorkspaceFiles > 0) workspaceParts.push(`${skippedWorkspaceFiles} workspace file(s) skipped`);
  if (skippedWorkspaceDirs > 0) workspaceParts.push(`${skippedWorkspaceDirs} folder(s) skipped`);
  return `Migrated ${data.migrated_runs} run(s), ${data.migrated_snapshots} snapshot(s), `
    + `${data.migrated_stars ?? 0} starred command(s), ${data.migrated_workflows ?? 0} workflow(s), `
    + `${recentDomains} recent domain(s), `
    + `${workspaceParts.join(', ')}, `
    + 'and saved user options when the destination had none.';
}

async function _clearActiveSessionToken() {
  localStorage.removeItem('session_token');
  const uuid = localStorage.getItem('session_id') || SESSION_ID;
  updateSessionId(uuid);
  if (typeof loadRecentDomains === 'function') await loadRecentDomains().catch(() => {});
  if (typeof hydrateCmdHistory === 'function') hydrateCmdHistory([]);
  if (typeof reloadSessionHistory === 'function') await reloadSessionHistory().catch(() => {});
  if (typeof reloadWorkflowCatalog === 'function') reloadWorkflowCatalog().catch(() => {});
  _updateOptionsSessionTokenStatus();
  return uuid;
}

async function confirmClearSessionToken() {
  const token = localStorage.getItem('session_token');
  if (!token) return { cleared: false, anonymousSessionId: null };
  if (typeof showConfirm !== 'function') {
    const uuid = await _clearActiveSessionToken();
    return { cleared: true, anonymousSessionId: uuid };
  }

  const choice = await showConfirm({
    body: {
      text: 'Clear the current session token from this browser?',
      note: 'If you have not saved it elsewhere, you will not be able to recover it from the app, and history tied to it will no longer be accessible from this browser.',
    },
    tone: 'danger',
    actions: [
      {
        id: 'copy',
        label: 'Copy token',
        role: 'secondary',
        onActivate: async () => {
          try {
            await copyTextToClipboard(token);
            showToast('Token copied to clipboard');
          } catch (_) {
            showToast('Failed to copy token', 'error');
          }
          return false;
        },
      },
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'clear', label: 'Clear token', role: 'destructive' },
    ],
  });

  if (choice !== 'clear') return { cleared: false, anonymousSessionId: null };
  const uuid = await _clearActiveSessionToken();
  return { cleared: true, anonymousSessionId: uuid };
}

document.getElementById('options-session-token-copy-btn')?.addEventListener('click', async () => {
  if (typeof flushRecentDomains === 'function') {
    await flushRecentDomains().catch(() => {});
  }
  const token = localStorage.getItem('session_token');
  if (!token) return;
  copyTextToClipboard(token)
    .then(() => showToast('Token copied to clipboard'))
    .catch(() => showToast('Failed to copy token', 'error'));
});

document.getElementById('options-session-token-generate-btn')?.addEventListener('click', async () => {
  const oldSessionId = SESSION_ID;
  _optionsTokenSetBusy(true);
  _optionsTokenShowMsg('');
  try {
    const resp = await apiFetch('/session/token/generate');
    if (!resp.ok) {
      const d = await resp.json().catch(() => ({}));
      _optionsTokenShowMsg(`Failed to generate token — ${d.error || resp.status}`, true);
      return;
    }
    const { session_token: newToken } = await resp.json();

    if (typeof flushRecentDomains === 'function') {
      await flushRecentDomains().catch(() => {});
    }

    // Count runs/files on OLD session before switching identity.
    let runCount = 0;
    let workspaceFileCount = 0;
    let workflowCount = 0;
    let recentDomainCount = 0;
    try {
      const countResp = await apiFetch('/session/run-count');
      if (countResp.ok) {
        const countData = await countResp.json();
        runCount = countData.count || 0;
        workspaceFileCount = countData.workspace_files || 0;
        workflowCount = countData.workflow_count || 0;
        recentDomainCount = countData.recent_domain_count || 0;
      }
    } catch (_) {}

    // Migrate BEFORE switching identity so a failed /session/migrate does not
    // leave the user on the new token with their runs still on the old session.
    if (runCount > 0 || workspaceFileCount > 0 || workflowCount > 0 || recentDomainCount > 0) {
      const migrateChoice = await _waitForMigrateChoice(
        `You have ${_optionsMigrationCountLabel(runCount, workspaceFileCount, workflowCount, recentDomainCount)} in your previous session. Migrate history, files, workflows, and recent domains to the new token?`
      );
      if (migrateChoice !== 'skip' && migrateChoice !== 'yes') return;
      if (migrateChoice === 'yes') {
        const migrateResp = await fetch('/session/migrate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Session-ID': oldSessionId },
          body: JSON.stringify({ from_session_id: oldSessionId, to_session_id: newToken }),
        }).catch(() => null);
        if (!migrateResp?.ok) {
          const d = await migrateResp?.json().catch(() => ({})) ?? {};
          _optionsTokenShowMsg(`Migration failed — ${d.error || 'network error'}. Token not activated.`, true);
          return;
        }
        const migrateData = await migrateResp.json().catch(() => ({}));
        _optionsTokenShowMsg(_optionsMigrationResultText(migrateData));
      }
    }

    localStorage.setItem('session_token', newToken);
    updateSessionId(newToken);
    if (typeof loadRecentDomains === 'function') await loadRecentDomains().catch(() => {});
    if (typeof _seedLocalStorageStarsToServer === 'function') await _seedLocalStorageStarsToServer();
    if (typeof reloadSessionHistory === 'function') await reloadSessionHistory().catch(() => {});
    if (typeof reloadWorkflowCatalog === 'function') reloadWorkflowCatalog().catch(() => {});
    _updateOptionsSessionTokenStatus();
    if (typeof refreshWorkspaceFiles === 'function') refreshWorkspaceFiles().catch(() => {});
    copyTextToClipboard(newToken)
      .then(() => showToast('New token copied to clipboard'))
      .catch(() => {});
  } catch (err) {
    _optionsTokenShowMsg(`Error: ${err.message || 'network error'}`, true);
  } finally {
    _optionsTokenSetBusy(false);
  }
});

// Set token modal — showConfirm with input + inline error content slot.
// Apply is gated by onActivate (format check + /session/token/verify),
// so validation errors keep the modal open instead of firing the real flow.
document.getElementById('options-session-token-set-btn')?.addEventListener('click', async () => {
  _optionsTokenShowMsg('');
  if (typeof showConfirm !== 'function') return;

  const input = document.createElement('input');
  input.type = 'text';
  input.id = 'session-token-set-input';
  input.className = 'options-token-input modal-token-input';
  input.placeholder = 'tok_... or UUID';
  if (typeof applyMobileTextInputDefaults === 'function') {
    applyMobileTextInputDefaults(input);
  } else {
    input.autocomplete = 'off';
    input.autocapitalize = 'none';
    input.autocorrect = 'off';
    input.spellcheck = false;
    input.inputMode = 'text';
  }

  const errEl = document.createElement('div');
  errEl.id = 'session-token-set-error';
  errEl.className = 'options-session-token-msg is-error';
  errEl.style.display = 'none';

  // Enter in the input triggers Apply. Preventing default stops the enter from
  // bubbling into a synthetic click on the first button (Cancel).
  input.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    document.querySelector('#confirm-host [data-confirm-action-id="apply"]')?.click();
  });

  let value = '';
  const choice = await showConfirm({
    body: {
      text: 'Enter a session token to switch to.',
      note: 'Accepts tok_... format or a UUID from another session.',
    },
    content: [input, errEl],
    defaultFocus: input,
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      {
        id: 'apply',
        label: 'Apply',
        role: 'primary',
        onActivate: async () => {
          value = (input.value || '').trim();
          const isTok  = value.startsWith('tok_');
          const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
          if (!value || (!isTok && !isUuid)) {
            errEl.textContent = 'Invalid token — expected tok_... or a UUID';
            errEl.style.display = '';
            return false;
          }
          // For tok_ tokens, verify server-side existence before switching.
          // A typo would otherwise silently create a brand-new empty session.
          // Fail closed: any failure (network error, non-OK response, missing
          // exists flag) blocks the switch rather than allowing an unverified
          // token through.
          if (isTok) {
            let verifyErr = null;
            try {
              const vResp = await apiFetch('/session/token/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: value }),
              });
              const vData = await vResp.json().catch(() => ({}));
              if (!vResp.ok) {
                verifyErr = 'Token verification failed — server returned an error';
              } else if (vData.exists === false) {
                verifyErr = 'Token not found — this token was not issued by this server';
              }
            } catch (_) {
              verifyErr = 'Token verification failed — server is unreachable';
            }
            if (verifyErr !== null) {
              errEl.textContent = verifyErr;
              errEl.style.display = '';
              return false;
            }
          }
          errEl.style.display = 'none';
          return true;
        },
      },
    ],
  });

  if (choice !== 'apply') return;

  const oldSessionId = SESSION_ID;
  _optionsTokenSetBusy(true);
  _optionsTokenShowMsg('');
  try {
    if (typeof flushRecentDomains === 'function') {
      await flushRecentDomains().catch(() => {});
    }

    let runCount = 0;
    let workspaceFileCount = 0;
    let workflowCount = 0;
    let recentDomainCount = 0;
    try {
      const countResp = await apiFetch('/session/run-count');
      if (countResp.ok) {
        const countData = await countResp.json();
        runCount = countData.count || 0;
        workspaceFileCount = countData.workspace_files || 0;
        workflowCount = countData.workflow_count || 0;
        recentDomainCount = countData.recent_domain_count || 0;
      }
    } catch (_) {}

    // Migrate BEFORE switching identity so a failed /session/migrate does not
    // leave the user on the new token with their runs still on the old session.
    if (runCount > 0 || workspaceFileCount > 0 || workflowCount > 0 || recentDomainCount > 0) {
      const migrateChoice = await _waitForMigrateChoice(
        `You have ${_optionsMigrationCountLabel(runCount, workspaceFileCount, workflowCount, recentDomainCount)} in your current session. Migrate history, files, workflows, and recent domains to this token?`
      );
      if (migrateChoice !== 'skip' && migrateChoice !== 'yes') return;
      if (migrateChoice === 'yes') {
        const migrateResp = await fetch('/session/migrate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Session-ID': oldSessionId },
          body: JSON.stringify({ from_session_id: oldSessionId, to_session_id: value }),
        }).catch(() => null);
        if (!migrateResp?.ok) {
          const d = await migrateResp?.json().catch(() => ({})) ?? {};
          _optionsTokenShowMsg(`Migration failed — ${d.error || 'network error'}. Token not activated.`, true);
          return;
        }
        const migrateData = await migrateResp.json().catch(() => ({}));
        _optionsTokenShowMsg(_optionsMigrationResultText(migrateData));
      }
    }

    localStorage.setItem('session_token', value);
    updateSessionId(value);
    if (typeof loadRecentDomains === 'function') await loadRecentDomains().catch(() => {});
    if (typeof _seedLocalStorageStarsToServer === 'function') await _seedLocalStorageStarsToServer();
    if (typeof reloadSessionHistory === 'function') await reloadSessionHistory().catch(() => {});
    if (typeof reloadWorkflowCatalog === 'function') reloadWorkflowCatalog().catch(() => {});
    _updateOptionsSessionTokenStatus();
    if (typeof refreshWorkspaceFiles === 'function') refreshWorkspaceFiles().catch(() => {});
    showToast('Session token applied');
  } catch (err) {
    _optionsTokenShowMsg(`Error: ${err.message || 'network error'}`, true);
  } finally {
    _optionsTokenSetBusy(false);
  }
});

document.getElementById('options-session-token-rotate-btn')?.addEventListener('click', async () => {
  const oldSessionId = SESSION_ID;
  _optionsTokenSetBusy(true);
  _optionsTokenShowMsg('');
  try {
    const genResp = await apiFetch('/session/token/generate');
    if (!genResp.ok) {
      const d = await genResp.json().catch(() => ({}));
      _optionsTokenShowMsg(`Failed to generate token — ${d.error || genResp.status}`, true);
      return;
    }
    const { session_token: newToken } = await genResp.json();

    // Migrate BEFORE updating SESSION_ID so the old identity is sent in the header.
    const migrateResp = await fetch('/session/migrate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Session-ID': oldSessionId },
      body: JSON.stringify({ from_session_id: oldSessionId, to_session_id: newToken }),
    });
    const migrateData = await migrateResp.json().catch(() => ({}));
    if (!migrateResp.ok || !migrateData.ok) {
      _optionsTokenShowMsg(`Migration failed — token not rotated: ${migrateData.error || migrateResp.status}`, true);
      return;
    }
    _optionsTokenShowMsg(_optionsMigrationResultText(migrateData));

    localStorage.setItem('session_token', newToken);
    updateSessionId(newToken);
    if (typeof loadRecentDomains === 'function') await loadRecentDomains().catch(() => {});
    if (typeof reloadSessionHistory === 'function') await reloadSessionHistory().catch(() => {});
    if (typeof reloadWorkflowCatalog === 'function') reloadWorkflowCatalog().catch(() => {});

    _updateOptionsSessionTokenStatus();
    if (typeof refreshWorkspaceFiles === 'function') refreshWorkspaceFiles().catch(() => {});
    copyTextToClipboard(newToken)
      .then(() => showToast('New token copied to clipboard'))
      .catch(() => showToast('Token rotated'));
  } catch (err) {
    _optionsTokenShowMsg(`Error: ${err.message || 'network error'}`, true);
  } finally {
    _optionsTokenSetBusy(false);
  }
});

document.getElementById('options-session-token-clear-btn')?.addEventListener('click', async () => {
  const result = await confirmClearSessionToken();
  if (result.cleared) showToast('Session token cleared');
});
