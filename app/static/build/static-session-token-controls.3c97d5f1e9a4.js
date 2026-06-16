import {
  reloadWorkflowCatalog
} from "./static-chunk-lydvfvd2.99b0b467db42.js";
import {
  flushRecentValues,
  getSessionId,
  hydrateCmdHistory,
  loadRecentValues,
  maskSessionToken,
  reloadSessionHistory,
  setSessionTokenHandlers,
  updateSessionId
} from "./static-chunk-woazwvu4.87340bdecc1f.js";
import {
  copyTextToClipboard,
  showToast
} from "./static-chunk-poi5czx6.3f5c94749765.js";
import "./static-chunk-lxs2zdd2.87dc9e4c1317.js";
import "./static-chunk-fik64llj.1291b1f4f79b.js";
import "./static-chunk-yu6ty7m2.96c3ee208a44.js";
import {
  applyMobileTextInputDefaults
} from "./static-chunk-sgyzdmxn.7d1842f12a94.js";
import "./static-chunk-tym5o2af.a748583ae389.js";
import {
  apiFetch,
  hasRuntimeHandler
} from "./static-chunk-i34eiczq.4bb950c346dc.js";

// app/static/js/features/preferences/session_token_controls.js
var SESSION_TOKEN_GLOBAL = typeof window !== "undefined" ? window : globalThis;
function _sessionTokenGlobalFunction(name) {
  const fn = SESSION_TOKEN_GLOBAL?.[name];
  return typeof fn === "function" ? fn : null;
}
function _sessionTokenApiFetch(...args) {
  const fetcher = (typeof hasRuntimeHandler === "function" && hasRuntimeHandler("apiFetch") && typeof apiFetch === "function" ? apiFetch : null) || _sessionTokenGlobalFunction("apiFetch");
  return fetcher ? fetcher(...args) : Promise.reject(new Error("apiFetch unavailable"));
}
function _sessionTokenCurrentId() {
  if (typeof getSessionId === "function") return getSessionId();
  return typeof SESSION_TOKEN_GLOBAL?.SESSION_ID !== "undefined" ? SESSION_TOKEN_GLOBAL.SESSION_ID : "";
}
function _sessionTokenUpdateSessionId(value) {
  if (typeof updateSessionId === "function") updateSessionId(value);
}
function _sessionTokenMask(value) {
  const mask = typeof maskSessionToken === "function" ? maskSessionToken : null;
  return mask ? mask(value) : String(value || "");
}
function _sessionTokenShowToast(message, tone = "success") {
  const toast = typeof showToast === "function" ? showToast : _sessionTokenGlobalFunction("showToast");
  if (!toast) return;
  if (tone === "success") toast(message);
  else toast(message, tone);
}
function _sessionTokenShowConfirm(options) {
  const confirm = _sessionTokenGlobalFunction("showConfirm");
  return confirm ? confirm(options) : Promise.resolve(false);
}
function _sessionTokenCopyText(value) {
  const copy = typeof copyTextToClipboard === "function" ? copyTextToClipboard : _sessionTokenGlobalFunction("copyTextToClipboard");
  return copy ? copy(value) : Promise.reject(new Error("Clipboard unavailable"));
}
function _sessionTokenApplyMobileTextInputDefaults(input) {
  const apply = typeof applyMobileTextInputDefaults === "function" ? applyMobileTextInputDefaults : _sessionTokenGlobalFunction("applyMobileTextInputDefaults");
  if (apply) {
    apply(input);
    return true;
  }
  return false;
}
function _sessionTokenLoadRecentValues() {
  const load = typeof loadRecentValues === "function" ? loadRecentValues : _sessionTokenGlobalFunction("loadRecentValues");
  return load ? load() : Promise.resolve(null);
}
function _sessionTokenFlushRecentValues() {
  const flush = typeof flushRecentValues === "function" ? flushRecentValues : _sessionTokenGlobalFunction("flushRecentValues");
  return flush ? flush() : Promise.resolve(null);
}
function _sessionTokenHydrateCmdHistory(runs) {
  const hydrate = typeof hydrateCmdHistory === "function" ? hydrateCmdHistory : _sessionTokenGlobalFunction("hydrateCmdHistory");
  if (hydrate) hydrate(runs);
}
function _sessionTokenReloadSessionHistory() {
  const reload = typeof reloadSessionHistory === "function" ? reloadSessionHistory : _sessionTokenGlobalFunction("reloadSessionHistory");
  return reload ? reload() : Promise.resolve(null);
}
function _sessionTokenReloadWorkflowCatalog() {
  const reload = typeof reloadWorkflowCatalog === "function" ? reloadWorkflowCatalog : _sessionTokenGlobalFunction("reloadWorkflowCatalog");
  return reload ? reload() : Promise.resolve(null);
}
function _updateOptionsSessionTokenStatus() {
  const el = document.getElementById("options-session-token-status");
  if (!el) return;
  const token = localStorage.getItem("session_token");
  const hasToken = Boolean(token);
  el.textContent = hasToken ? _sessionTokenMask(token) : "No session token — anonymous session";
  el.classList.toggle("is-active", hasToken);
  const generateBtn = document.getElementById("options-session-token-generate-btn");
  const rotateBtn = document.getElementById("options-session-token-rotate-btn");
  const clearBtn = document.getElementById("options-session-token-clear-btn");
  const copyBtn = document.getElementById("options-session-token-copy-btn");
  if (generateBtn) generateBtn.style.display = hasToken ? "none" : "";
  if (rotateBtn) rotateBtn.style.display = hasToken ? "" : "none";
  if (clearBtn) clearBtn.style.display = hasToken ? "" : "none";
  if (copyBtn) copyBtn.style.display = hasToken ? "" : "none";
  _optionsTokenShowMsg("");
}
function _optionsTokenSetBusy(busy) {
  [
    "options-session-token-generate-btn",
    "options-session-token-set-btn",
    "options-session-token-rotate-btn",
    "options-session-token-clear-btn"
  ].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = busy;
  });
}
function _optionsTokenShowMsg(msg, isError = false) {
  const el = document.getElementById("options-session-token-msg");
  if (!el) return;
  el.textContent = msg;
  el.style.display = msg ? "" : "none";
  el.classList.toggle("is-error", isError);
}
function _optionsTokenToast(message, tone = "success") {
  const text = String(message || "").trim();
  if (!text) return;
  const toast = typeof showToast === "function" ? showToast : _sessionTokenGlobalFunction("showToast");
  if (toast && tone === "success") toast(text);
  else if (toast) toast(text, tone);
  else _optionsTokenShowMsg(text, tone === "error");
}
async function _waitForMigrateChoice(msg) {
  return await _sessionTokenShowConfirm({
    body: msg,
    actions: [
      { id: "cancel", label: "Cancel", role: "cancel" },
      { id: "skip", label: "Skip", role: "secondary" },
      { id: "yes", label: "Yes, migrate", role: "primary" }
    ]
  });
}
function _optionsMigrationCountLabel(runCount = 0, workspaceFileCount = 0, workflowCount = 0, recentValueCount = 0) {
  const parts = [];
  if (runCount > 0) parts.push(`${runCount} run(s)`);
  if (workspaceFileCount > 0) parts.push(`${workspaceFileCount} workspace file(s)`);
  if (workflowCount > 0) parts.push(`${workflowCount} workflow(s)`);
  if (recentValueCount > 0) parts.push(`${recentValueCount} recent value(s)`);
  if (!parts.length) return "no runs, workspace files, workflows, or recent values";
  if (parts.length === 1) return parts[0];
  return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}
function _optionsMigrationResultText(data = {}) {
  const workspaceFiles = Number(data.migrated_workspace_files || 0);
  const skippedWorkspaceFiles = Number(data.skipped_workspace_files || 0);
  const workspaceDirs = Number(data.migrated_workspace_directories || 0);
  const skippedWorkspaceDirs = Number(data.skipped_workspace_directories || 0);
  const recentValues = Number(data.migrated_recent_values || 0);
  const workspaceParts = [`${workspaceFiles} workspace file(s)`];
  if (workspaceDirs > 0) workspaceParts.push(`${workspaceDirs} folder(s)`);
  if (skippedWorkspaceFiles > 0) workspaceParts.push(`${skippedWorkspaceFiles} workspace file(s) skipped`);
  if (skippedWorkspaceDirs > 0) workspaceParts.push(`${skippedWorkspaceDirs} folder(s) skipped`);
  return `Migrated ${data.migrated_runs} run(s), ${data.migrated_snapshots} snapshot(s), ${data.migrated_stars ?? 0} starred command(s), ${data.migrated_workflows ?? 0} workflow(s), ${recentValues} recent value(s), ${workspaceParts.join(", ")}, and saved user options when the destination had none.`;
}
async function _clearActiveSessionToken() {
  localStorage.removeItem("session_token");
  const uuid = localStorage.getItem("session_id") || _sessionTokenCurrentId();
  _sessionTokenUpdateSessionId(uuid);
  await _sessionTokenLoadRecentValues().catch(() => {
  });
  _sessionTokenHydrateCmdHistory([]);
  await _sessionTokenReloadSessionHistory().catch(() => {
  });
  _sessionTokenReloadWorkflowCatalog().catch(() => {
  });
  _updateOptionsSessionTokenStatus();
  return uuid;
}
async function confirmClearSessionToken() {
  const token = localStorage.getItem("session_token");
  if (!token) return { cleared: false, anonymousSessionId: null };
  if (!_sessionTokenGlobalFunction("showConfirm")) {
    const uuid2 = await _clearActiveSessionToken();
    return { cleared: true, anonymousSessionId: uuid2 };
  }
  const choice = await _sessionTokenShowConfirm({
    body: {
      text: "Clear the current session token from this browser?",
      note: "If you have not saved it elsewhere, you will not be able to recover it from the app, and history tied to it will no longer be accessible from this browser."
    },
    tone: "danger",
    actions: [
      {
        id: "copy",
        label: "Copy token",
        role: "secondary",
        onActivate: async () => {
          try {
            await _sessionTokenCopyText(token);
            _sessionTokenShowToast("Token copied to clipboard");
          } catch (_) {
            _sessionTokenShowToast("Failed to copy token", "error");
          }
          return false;
        }
      },
      { id: "cancel", label: "Cancel", role: "cancel" },
      { id: "clear", label: "Clear token", role: "destructive" }
    ]
  });
  if (choice !== "clear") return { cleared: false, anonymousSessionId: null };
  const uuid = await _clearActiveSessionToken();
  return { cleared: true, anonymousSessionId: uuid };
}
document.getElementById("options-session-token-copy-btn")?.addEventListener("click", async () => {
  await _sessionTokenFlushRecentValues().catch(() => {
  });
  const token = localStorage.getItem("session_token");
  if (!token) return;
  _sessionTokenCopyText(token).then(() => _sessionTokenShowToast("Token copied to clipboard")).catch(() => _sessionTokenShowToast("Failed to copy token", "error"));
});
document.getElementById("options-session-token-generate-btn")?.addEventListener("click", async () => {
  const oldSessionId = _sessionTokenCurrentId();
  _optionsTokenSetBusy(true);
  _optionsTokenShowMsg("");
  try {
    const resp = await _sessionTokenApiFetch("/session/token/generate");
    if (!resp.ok) {
      const d = await resp.json().catch(() => ({}));
      _optionsTokenToast(`Failed to generate token — ${d.error || resp.status}`, "error");
      return;
    }
    const { session_token: newToken } = await resp.json();
    await _sessionTokenFlushRecentValues().catch(() => {
    });
    let runCount = 0;
    let workspaceFileCount = 0;
    let workflowCount = 0;
    let recentValueCount = 0;
    try {
      const countResp = await _sessionTokenApiFetch("/session/run-count");
      if (countResp.ok) {
        const countData = await countResp.json();
        runCount = countData.count || 0;
        workspaceFileCount = countData.workspace_files || 0;
        workflowCount = countData.workflow_count || 0;
        recentValueCount = countData.recent_value_count || 0;
      }
    } catch (_) {
    }
    if (runCount > 0 || workspaceFileCount > 0 || workflowCount > 0 || recentValueCount > 0) {
      const migrateChoice = await _waitForMigrateChoice(
        `You have ${_optionsMigrationCountLabel(runCount, workspaceFileCount, workflowCount, recentValueCount)} in your previous session. Migrate history, files, workflows, and recent values to the new token?`
      );
      if (migrateChoice !== "skip" && migrateChoice !== "yes") return;
      if (migrateChoice === "yes") {
        const migrateResp = await fetch("/session/migrate", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Session-ID": oldSessionId },
          body: JSON.stringify({ from_session_id: oldSessionId, to_session_id: newToken })
        }).catch(() => null);
        if (!migrateResp?.ok) {
          const d = await migrateResp?.json().catch(() => ({})) ?? {};
          _optionsTokenToast(`Migration failed — ${d.error || "network error"}. Token not activated.`, "error");
          return;
        }
        const migrateData = await migrateResp.json().catch(() => ({}));
        _optionsTokenToast(_optionsMigrationResultText(migrateData));
      }
    }
    localStorage.setItem("session_token", newToken);
    _sessionTokenUpdateSessionId(newToken);
    await _sessionTokenLoadRecentValues().catch(() => {
    });
    const seedStars = _sessionTokenGlobalFunction("_seedLocalStorageStarsToServer");
    if (seedStars) await seedStars();
    await _sessionTokenReloadSessionHistory().catch(() => {
    });
    _sessionTokenReloadWorkflowCatalog().catch(() => {
    });
    _updateOptionsSessionTokenStatus();
    const refreshWorkspaceFiles = _sessionTokenGlobalFunction("refreshWorkspaceFiles");
    if (refreshWorkspaceFiles) refreshWorkspaceFiles().catch(() => {
    });
    _sessionTokenCopyText(newToken).then(() => _sessionTokenShowToast("New token copied to clipboard")).catch(() => {
    });
  } catch (err) {
    _optionsTokenToast(`Error: ${err.message || "network error"}`, "error");
  } finally {
    _optionsTokenSetBusy(false);
  }
});
document.getElementById("options-session-token-set-btn")?.addEventListener("click", async () => {
  _optionsTokenShowMsg("");
  if (!_sessionTokenGlobalFunction("showConfirm")) return;
  const input = document.createElement("input");
  input.type = "text";
  input.id = "session-token-set-input";
  input.className = "options-token-input modal-token-input";
  input.placeholder = "tok_... or UUID";
  if (!_sessionTokenApplyMobileTextInputDefaults(input)) {
    input.autocomplete = "off";
    input.autocapitalize = "none";
    input.autocorrect = "off";
    input.spellcheck = false;
    input.inputMode = "text";
  }
  const errEl = document.createElement("div");
  errEl.id = "session-token-set-error";
  errEl.className = "options-session-token-msg is-error";
  errEl.style.display = "none";
  input.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    document.querySelector('#confirm-host [data-confirm-action-id="apply"]')?.click();
  });
  let value = "";
  const choice = await _sessionTokenShowConfirm({
    body: {
      text: "Enter a session token to switch to.",
      note: "Accepts tok_... format or a UUID from another session."
    },
    content: [input, errEl],
    defaultFocus: input,
    actions: [
      { id: "cancel", label: "Cancel", role: "cancel" },
      {
        id: "apply",
        label: "Apply",
        role: "primary",
        onActivate: async () => {
          value = (input.value || "").trim();
          const isTok = value.startsWith("tok_");
          const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
          if (!value || !isTok && !isUuid) {
            errEl.textContent = "Invalid token — expected tok_... or a UUID";
            errEl.style.display = "";
            return false;
          }
          if (isTok) {
            let verifyErr = null;
            try {
              const vResp = await _sessionTokenApiFetch("/session/token/verify", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token: value })
              });
              const vData = await vResp.json().catch(() => ({}));
              if (!vResp.ok) {
                verifyErr = "Token verification failed — server returned an error";
              } else if (vData.exists === false) {
                verifyErr = "Token not found — this token was not issued by this server";
              }
            } catch (_) {
              verifyErr = "Token verification failed — server is unreachable";
            }
            if (verifyErr !== null) {
              errEl.textContent = verifyErr;
              errEl.style.display = "";
              return false;
            }
          }
          errEl.style.display = "none";
          return true;
        }
      }
    ]
  });
  if (choice !== "apply") return;
  const oldSessionId = _sessionTokenCurrentId();
  _optionsTokenSetBusy(true);
  _optionsTokenShowMsg("");
  try {
    await _sessionTokenFlushRecentValues().catch(() => {
    });
    let runCount = 0;
    let workspaceFileCount = 0;
    let workflowCount = 0;
    let recentValueCount = 0;
    try {
      const countResp = await _sessionTokenApiFetch("/session/run-count");
      if (countResp.ok) {
        const countData = await countResp.json();
        runCount = countData.count || 0;
        workspaceFileCount = countData.workspace_files || 0;
        workflowCount = countData.workflow_count || 0;
        recentValueCount = countData.recent_value_count || 0;
      }
    } catch (_) {
    }
    if (runCount > 0 || workspaceFileCount > 0 || workflowCount > 0 || recentValueCount > 0) {
      const migrateChoice = await _waitForMigrateChoice(
        `You have ${_optionsMigrationCountLabel(runCount, workspaceFileCount, workflowCount, recentValueCount)} in your current session. Migrate history, files, workflows, and recent values to this token?`
      );
      if (migrateChoice !== "skip" && migrateChoice !== "yes") return;
      if (migrateChoice === "yes") {
        const migrateResp = await fetch("/session/migrate", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Session-ID": oldSessionId },
          body: JSON.stringify({ from_session_id: oldSessionId, to_session_id: value })
        }).catch(() => null);
        if (!migrateResp?.ok) {
          const d = await migrateResp?.json().catch(() => ({})) ?? {};
          _optionsTokenToast(`Migration failed — ${d.error || "network error"}. Token not activated.`, "error");
          return;
        }
        const migrateData = await migrateResp.json().catch(() => ({}));
        _optionsTokenToast(_optionsMigrationResultText(migrateData));
      }
    }
    localStorage.setItem("session_token", value);
    _sessionTokenUpdateSessionId(value);
    await _sessionTokenLoadRecentValues().catch(() => {
    });
    const seedStars = _sessionTokenGlobalFunction("_seedLocalStorageStarsToServer");
    if (seedStars) await seedStars();
    await _sessionTokenReloadSessionHistory().catch(() => {
    });
    _sessionTokenReloadWorkflowCatalog().catch(() => {
    });
    _updateOptionsSessionTokenStatus();
    const refreshWorkspaceFiles = _sessionTokenGlobalFunction("refreshWorkspaceFiles");
    if (refreshWorkspaceFiles) refreshWorkspaceFiles().catch(() => {
    });
    _sessionTokenShowToast("Session token applied");
  } catch (err) {
    _optionsTokenToast(`Error: ${err.message || "network error"}`, "error");
  } finally {
    _optionsTokenSetBusy(false);
  }
});
document.getElementById("options-session-token-rotate-btn")?.addEventListener("click", async () => {
  const oldSessionId = _sessionTokenCurrentId();
  _optionsTokenSetBusy(true);
  _optionsTokenShowMsg("");
  try {
    const genResp = await _sessionTokenApiFetch("/session/token/generate");
    if (!genResp.ok) {
      const d = await genResp.json().catch(() => ({}));
      _optionsTokenToast(`Failed to generate token — ${d.error || genResp.status}`, "error");
      return;
    }
    const { session_token: newToken } = await genResp.json();
    const migrateResp = await fetch("/session/migrate", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Session-ID": oldSessionId },
      body: JSON.stringify({ from_session_id: oldSessionId, to_session_id: newToken })
    });
    const migrateData = await migrateResp.json().catch(() => ({}));
    if (!migrateResp.ok || !migrateData.ok) {
      _optionsTokenToast(`Migration failed — token not rotated: ${migrateData.error || migrateResp.status}`, "error");
      return;
    }
    _optionsTokenToast(_optionsMigrationResultText(migrateData));
    localStorage.setItem("session_token", newToken);
    _sessionTokenUpdateSessionId(newToken);
    await _sessionTokenLoadRecentValues().catch(() => {
    });
    await _sessionTokenReloadSessionHistory().catch(() => {
    });
    _sessionTokenReloadWorkflowCatalog().catch(() => {
    });
    _updateOptionsSessionTokenStatus();
    const refreshWorkspaceFiles = _sessionTokenGlobalFunction("refreshWorkspaceFiles");
    if (refreshWorkspaceFiles) refreshWorkspaceFiles().catch(() => {
    });
    _sessionTokenCopyText(newToken).then(() => _sessionTokenShowToast("New token copied to clipboard")).catch(() => _sessionTokenShowToast("Token rotated"));
  } catch (err) {
    _optionsTokenToast(`Error: ${err.message || "network error"}`, "error");
  } finally {
    _optionsTokenSetBusy(false);
  }
});
document.getElementById("options-session-token-clear-btn")?.addEventListener("click", async () => {
  const result = await confirmClearSessionToken();
  if (result.cleared) _sessionTokenShowToast("Session token cleared");
});
if (typeof setSessionTokenHandlers === "function") {
  setSessionTokenHandlers({
    updateOptionsSessionTokenStatus: _updateOptionsSessionTokenStatus
  });
}
export {
  _updateOptionsSessionTokenStatus
};
