// ── Shared command execution + desktop input wrapper ──
// If no chunk arrives from the SSE stream for 45 seconds (> 2× the 20s server heartbeat),
// the connection has silently died. Surface a notice and reset the UI so the user isn't
// left with a perpetually-spinning tab. The command may still be running server-side;
// the result will appear in the history panel once it completes.
// Keyed by tabId so multiple concurrent tabs each have their own independent timer.
const _stalledTimeouts = new Map();
let _activeRunPollTimer = null;

// Pending session migration: set when the user runs 'session-token generate'
// or 'session-token set' and the current session has existing runs.  The next
// command typed is treated as the yes/no answer to the migration prompt.
let _pendingSessionMigration = null;

function _resetStalledTimeout(tabId) {
  clearTimeout(_stalledTimeouts.get(tabId));
  _stalledTimeouts.set(tabId, setTimeout(() => {
    const t = getTab(tabId);
    if (!t || t.killed) return;  // already handled
    appendLine('[connection stalled — command may still be running on the server]', 'notice', tabId);
    appendLine('[check the history panel for the result once it completes]', 'notice', tabId);
    if (tabId === activeTabId) setStatus('fail');
    setTabStatus(tabId, 'fail');
    stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
  }, 45000));
}

function _clearStalledTimeout(tabId) {
  clearTimeout(_stalledTimeouts.get(tabId));
  _stalledTimeouts.delete(tabId);
}

// ── Status pill ──
// The HUD STATUS pill is a binary running-or-not indicator; the outcome of
// the last run (exit code, killed) is surfaced by the adjacent LAST EXIT
// pill, so the text only ever reads RUNNING or IDLE. The class name still
// tracks the underlying state (ok/fail/killed/idle/running) so existing CSS
// and test assertions that key off the pill's class keep working.
//
// setStatus also mirrors terminal states into the LAST EXIT pill so synthetic
// failures (denied, rate-limited, transport errors) surface there without
// every caller having to wire the two pills up separately. Callers that have
// a real exit code (the SSE exit handler, kill) override afterwards.
function setStatus(s) {
  status.className = 'status-pill ' + s;
  status.textContent = s === 'running' ? 'RUNNING' : 'IDLE';
  if (typeof setHudLastExit === 'function') {
    if (s === 'ok') setHudLastExit(0);
    else if (s === 'fail') setHudLastExit(1);
    else if (s === 'killed') setHudLastExit('killed');
  }
}

// ── Run notifications ──

function _maybeNotify(command, codeOrStatus, elapsed) {
  if (typeof getRunNotifyPreference !== 'function' || getRunNotifyPreference() !== 'on') return;
  if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
  // Use only the command root (first word) so arguments — which may contain
  // bearer tokens, API keys, auth headers, or sensitive targets — are never
  // surfaced in OS notifications or on the lock screen.
  const root = (command || '').split(/\s+/)[0] || '';
  const title = root ? '$ ' + root : '$';
  const body = codeOrStatus === 'killed'
    ? (elapsed ? `killed after ${elapsed}` : 'killed')
    : (elapsed ? `exit ${codeOrStatus} in ${elapsed}` : `exit ${codeOrStatus}`);
  try { new Notification(title, { body }); } catch(e) {}
}

// ── Run timer ──

// Format a duration in seconds as a compact human-readable string.
// Examples: 32.6 → "32.6s", 125.0 → "2m 5.0s", 3812.3 → "1h 3m 32.3s"
function _formatElapsed(totalSecs) {
  if (totalSecs < 60) return totalSecs.toFixed(1) + 's';
  const h = Math.floor(totalSecs / 3600);
  const m = Math.floor((totalSecs % 3600) / 60);
  const s = (totalSecs % 60).toFixed(1);
  return h > 0 ? `${h}h ${m}m ${s}s` : `${m}m ${s}s`;
}

function startTimer(startMs = Date.now()) {
  timerStart = startMs;
  showRunTimer();
  timerInterval = setInterval(() => {
    runTimer.textContent = _formatElapsed((Date.now() - timerStart) / 1000);
  }, 100);
}

function stopTimer() {
  clearInterval(timerInterval);
  timerInterval = null;
  hideRunTimer();
}

function syncActiveRunTimer(tabId = activeTabId) {
  const t = getTab(tabId);
  if (!t || t.st !== 'running' || !t.runStart) {
    stopTimer();
    return;
  }
  startTimer(t.runStart);
}

function _activeReconnectTabs() {
  return tabs.filter(t => t && t.st === 'running' && t.reconnectedRun && t.historyRunId);
}

function _activeRunReconnectNotice(run) {
  const startedAt = new Date(run.started);
  const startedLabel = Number.isNaN(startedAt.getTime())
    ? 'unknown start time'
    : startedAt.toLocaleString();
  return [
    `[reconnected to active run started at ${startedLabel}]`,
    '[live output cannot be replayed after reload; this tab will restore the saved run automatically when it completes]',
  ];
}

function restoreActiveRunsAfterReload(runs) {
  const items = Array.isArray(runs) ? runs : [];
  if (!items.length) {
    stopPollingActiveRunsAfterReload();
    return false;
  }

  let firstRestoredTabId = null;
  items.forEach((run, index) => {
    const bootstrapTab = index === 0 && tabs.length === 1 ? tabs[0] : null;
    const canReuseBootstrapTab = !!(bootstrapTab
      && bootstrapTab.st === 'idle'
      && !bootstrapTab.renamed
      && !bootstrapTab.command
      && !bootstrapTab.historyRunId
      && !bootstrapTab.draftInput
      && Array.isArray(bootstrapTab.rawLines)
      && bootstrapTab.rawLines.length === 0);
    const tabId = canReuseBootstrapTab ? bootstrapTab.id : createTab(run.command);
    if (!tabId) return;
    if (!firstRestoredTabId) firstRestoredTabId = tabId;
    clearTab(tabId);
    const t = getTab(tabId);
    if (!t) return;
    if (!t.renamed) setTabLabel(tabId, run.command);
    t.command = run.command;
    t.runId = run.run_id;
    t.historyRunId = run.run_id;
    t.reconnectedRun = true;
    t.killed = false;
    t.pendingKill = false;
    t.previewTruncated = false;
    t.fullOutputAvailable = false;
    t.fullOutputLoaded = false;
    t.runStart = Number.isNaN(Date.parse(run.started)) ? Date.now() : Date.parse(run.started);
    t.currentRunStartIndex = 0;
    t.followOutput = true;
    appendCommandEcho(run.command, tabId);
    _activeRunReconnectNotice(run).forEach(line => appendLine(line, 'notice', tabId));
    setTabStatus(tabId, 'running');
    showTabKillBtn(tabId);
  });

  if (firstRestoredTabId) activateTab(firstRestoredTabId);
  syncActiveRunTimer(activeTabId);
  startPollingActiveRunsAfterReload();
  return true;
}

function _restoreCompletedReconnectedRun(tab, run) {
  if (!tab || !run || typeof restoreHistoryRunIntoTab !== 'function') return Promise.resolve();
  return restoreHistoryRunIntoTab(run, { targetTabId: tab.id, hidePanelOnSuccess: false })
    .then(() => {
      const refreshed = getTab(tab.id);
      if (refreshed) refreshed.reconnectedRun = false;
      if (tab.id === activeTabId) stopTimer();
    })
    .catch(() => {
      appendLine('[reconnected run finished, but the saved result could not be restored automatically]', 'notice', tab.id);
      appendLine('[open the history panel to load the completed run]', 'notice', tab.id);
      setTabStatus(tab.id, 'fail');
      const refreshed = getTab(tab.id);
      if (refreshed) refreshed.reconnectedRun = false;
      if (tab.id === activeTabId) stopTimer();
    });
}

function pollActiveRunsAfterReload() {
  const reconnectTabs = _activeReconnectTabs();
  if (!reconnectTabs.length) {
    stopPollingActiveRunsAfterReload();
    return Promise.resolve();
  }

  return apiFetch('/history/active')
    .then(r => r.json())
    .then(data => {
      const activeIds = new Set((Array.isArray(data.runs) ? data.runs : []).map(run => run.run_id));
      return Promise.all(reconnectTabs.map(tab => {
        if (activeIds.has(tab.historyRunId)) return Promise.resolve();
        return apiFetch(`/history/${tab.historyRunId}?json&preview=1`)
          .then(r => r.ok ? r.json() : Promise.reject(new Error('run not ready')))
          .then(run => _restoreCompletedReconnectedRun(tab, run))
          .catch(() => Promise.resolve());
      }));
    })
    .finally(() => {
      if (!_activeReconnectTabs().length) stopPollingActiveRunsAfterReload();
    });
}

function startPollingActiveRunsAfterReload() {
  if (_activeRunPollTimer || !_activeReconnectTabs().length) return;
  _activeRunPollTimer = setInterval(() => {
    pollActiveRunsAfterReload().catch(err => _logRunnerError('active run reconnect poll failed', err));
  }, 5000);
}

function stopPollingActiveRunsAfterReload() {
  clearInterval(_activeRunPollTimer);
  _activeRunPollTimer = null;
}

function elapsedSeconds() {
  return timerStart ? (Date.now() - timerStart) / 1000 : null;
}

// ── Kill button ──
function getTabKillBtn(tabId) {
  return tabPanels ? tabPanels.querySelector(`.tab-kill-btn[data-tab="${tabId}"]`) : null;
}

function _showTabKillBtnFallback(tabId) {
  const btn = getTabKillBtn(tabId);
  setDisplayState(btn, true, 'inline-block');
}

function _hideTabKillBtnFallback(tabId) {
  const btn = getTabKillBtn(tabId);
  setDisplayState(btn, false, 'inline-block');
}

function _setRunButtonDisabled(disabled) {
  if (typeof syncRunButtonDisabled === 'function') {
    syncRunButtonDisabled();
    return;
  }
  if (typeof setRunButtonDisabled === 'function') {
    setRunButtonDisabled(disabled);
    return;
  }
  if (runBtn) runBtn.disabled = !!disabled;
}

function _describeRunnerFetchError(err, context = 'server') {
  return describeFetchError(err, context);
}

function _logRunnerError(context, err) {
  logClientError(context, err);
}

function _handleKillRequestFailure(err, tabId) {
  _logRunnerError('kill request failed', err);
  showToast('Failed to send kill request; command may still be running');
  appendLine('[kill request failed] ' + _describeRunnerFetchError(err), 'notice', tabId);
}

function _handleRunTransportFailure(err, tabId) {
  _logRunnerError('run request failed', err);
  appendLine('[connection error] ' + _describeRunnerFetchError(err), 'exit-fail', tabId);
  if (tabId === activeTabId) setStatus('fail');
  setTabStatus(tabId, 'fail');
  stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
}

async function _readRunErrorMessage(res) {
  const contentType = (res.headers && typeof res.headers.get === 'function' && res.headers.get('content-type')) || '';
  try {
    if (contentType.includes('application/json') && typeof res.json === 'function') {
      const data = await res.json();
      if (data && typeof data.error === 'string' && data.error.trim()) return data.error.trim();
    } else if (typeof res.text === 'function') {
      const text = (await res.text()).trim();
      if (text) return text;
    }
  } catch (err) {
    _logRunnerError('failed to parse /run error response', err);
  }
  return '';
}

function _previewTruncationNotice(outputLineCount, fullOutputAvailable) {
  const shown = APP_CONFIG.max_output_lines || outputLineCount || 0;
  const total = outputLineCount || shown;
  if (fullOutputAvailable) {
    return `[preview truncated — only the last ${shown} lines are shown here, but the full output had ${total} lines. To view the full output, use either permalink button now; after another command, use this command's history permalink]`;
  }
  return `[preview truncated — only the last ${shown} lines are shown here, but the full output had ${total} lines. Full output persistence is disabled or unavailable]`;
}

function appendCommandEcho(cmd, tabId) {
  appendLine(cmd, 'prompt-echo', tabId);
}

function appendPromptNewline(tabId) {
  appendLine('', 'prompt-echo', tabId);
}

function _clearDesktopInput() {
  setComposerValue('', 0, 0);
}

function interruptPromptLine(tabId = activeTabId) {
  const t = getTab(tabId);
  if (t && t.st === 'running') return false;
  appendPromptNewline(tabId);
  _clearDesktopInput();
  refocusComposerAfterAction();
  if (tabId === activeTabId) setStatus('idle');
  return true;
}

// ── Kill confirmation modal ──
function confirmKill(tabId) {
  pendingKillTabId = tabId;
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  showConfirm({
    body: {
      text: 'Kill the running process in this tab?',
      note: 'This sends SIGTERM to the entire process group.',
    },
    tone: 'danger',
    actions: [
      { id: 'cancel',  label: 'Cancel', role: 'cancel' },
      { id: 'confirm', label: '■ Kill', role: 'primary', tone: 'danger' },
    ],
  }).then((result) => {
    const targetId = pendingKillTabId;
    pendingKillTabId = null;
    if (result === 'confirm' && targetId) doKill(targetId);
  });
}

function doKill(tabId) {
  const t = getTab(tabId);
  if (!t || t.st !== 'running') return;
  const secs = elapsedSeconds();
  if (t.runId) {
    // runId already available — send kill immediately
    apiFetch('/kill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: t.runId })
    }).catch(err => _handleKillRequestFailure(err, tabId));
    t.runId = null;
  } else {
    // runId not yet available (SSE 'started' hasn't arrived) — flag it so the
    // started handler sends the kill request as soon as the run_id is known
    t.pendingKill = true;
  }
  t.killed = true;
  t.reconnectedRun = false;
  stopTimer();
  appendLine(`[killed by user${secs != null ? ' after ' + _formatElapsed(secs) : ''}]`, 'exit-fail', tabId);
  _maybeNotify(t.command, 'killed', secs != null ? _formatElapsed(secs) : null);
  if (typeof setHudLastExit === 'function') setHudLastExit('killed');
  setTabStatus(tabId, 'killed');
  hideTabKillBtn(tabId);
  if (tabId === activeTabId) {
    setStatus('killed');
    _setRunButtonDisabled(false);
  }
  if (typeof _maybeMountDeferredPrompt === 'function') {
    _maybeMountDeferredPrompt(tabId);
  }
}

// ── Run command ──
// submitCommand(rawCmd) is the shared entry point for executing a command
// string. It does not read from or write to any DOM input — the caller
// supplies the value and owns input cleanup afterward.
//
// Return values (callers use these to decide what to do with their input):
//   'settle'  — empty input during welcome; caller should focus without clearing
//   true      — command submitted; caller should clear input and focus
//   false     — rejected or blocked; caller should leave input as-is
function _parseSyntheticPostFilterCommand(cmd) {
  if (!cmd || !cmd.includes('|')) return false;
  if (cmd.includes('`') || cmd.includes('$(')) return null;
  const tokens = [];
  const re = /"[^"]*"|'[^']*'|&&|\|\|?|;;?|>>?|<|[^\s|&;<>]+/g;
  let match = re.exec(cmd);
  while (match) {
    tokens.push(match[0]);
    match = re.exec(cmd);
  }
  if (!tokens.length) return null;
  if (tokens.filter(token => token === '|').length !== 1) return null;
  if (tokens.some(token => ['&&', '||', ';', ';;', '>', '>>', '<', '&'].includes(token))) return null;
  const pipeIndex = tokens.indexOf('|');
  const stageTokens = tokens.slice(pipeIndex + 1);
  if (pipeIndex <= 0 || !stageTokens.length) return null;
  const helper = String(stageTokens[0]).toLowerCase();

  if (helper === 'grep') {
    let patternSeen = false;
    for (const token of stageTokens.slice(1)) {
      if (!patternSeen && /^-[^-]/.test(token)) {
        for (const flag of token.slice(1)) {
          if (!['i', 'v', 'E'].includes(flag)) return null;
        }
        continue;
      }
      if (patternSeen) return null;
      patternSeen = true;
    }
    return patternSeen ? { kind: 'grep' } : null;
  }

  if (helper === 'head' || helper === 'tail') {
    if (stageTokens.length === 1) return { kind: helper };
    if (stageTokens.length === 2 && /^-\d+$/.test(stageTokens[1])) {
      return { kind: helper, count: Number(stageTokens[1].slice(1)) };
    }
    if (stageTokens.length !== 3 || stageTokens[1] !== '-n' || !/^\d+$/.test(stageTokens[2])) {
      return null;
    }
    return { kind: helper, count: Number(stageTokens[2]) };
  }

  if (helper === 'wc') {
    if (stageTokens.length === 2 && stageTokens[1] === '-l') {
      return { kind: 'wc_l' };
    }
    return null;
  }

  if (helper === 'sort') {
    if (stageTokens.length === 1) return { kind: 'sort' };
    if (stageTokens.length === 2) {
      const flag = stageTokens[1];
      if (/^-[rnu]+$/.test(flag) && new Set(flag.slice(1)).size === flag.length - 1) {
        const chars = new Set(flag.slice(1));
        if ([...chars].every(c => 'rnu'.includes(c))) {
          return { kind: 'sort', reverse: chars.has('r'), numeric: chars.has('n'), unique: chars.has('u') };
        }
      }
    }
    return null;
  }

  if (helper === 'uniq') {
    if (stageTokens.length === 1) return { kind: 'uniq' };
    if (stageTokens.length === 2 && stageTokens[1] === '-c') return { kind: 'uniq', count: true };
    return null;
  }

  return null;
}

function _isSyntheticPostFilterCommand(cmd) {
  return !!_parseSyntheticPostFilterCommand(cmd);
}

function _isSyntheticSortCommand(cmd) {
  const parsed = _parseSyntheticPostFilterCommand(cmd);
  return !!(parsed && parsed.kind === 'sort');
}

function _isSyntheticUniqCommand(cmd) {
  const parsed = _parseSyntheticPostFilterCommand(cmd);
  return !!(parsed && parsed.kind === 'uniq');
}

function _isSyntheticGrepCommand(cmd) {
  const parsed = _parseSyntheticPostFilterCommand(cmd);
  return !!(parsed && parsed.kind === 'grep');
}

function _isSyntheticHeadCommand(cmd) {
  const parsed = _parseSyntheticPostFilterCommand(cmd);
  return !!(parsed && parsed.kind === 'head');
}

function _isSyntheticTailCommand(cmd) {
  const parsed = _parseSyntheticPostFilterCommand(cmd);
  return !!(parsed && parsed.kind === 'tail');
}

function _isSyntheticWcLineCountCommand(cmd) {
  const parsed = _parseSyntheticPostFilterCommand(cmd);
  return !!(parsed && parsed.kind === 'wc_l');
}

function _isExactSpecialBuiltInCommand(cmd) {
  const normalized = String(cmd || '').trim().toLowerCase().replace(/\s+/g, ' ');
  const known = (typeof acSpecialCommands !== 'undefined' && acSpecialCommands) || [];
  if (known.includes(normalized)) return true;
  // Fork bomb variants use non-standard whitespace; match the regex as a fallback
  // for the brief window before acSpecialCommands loads from /autocomplete.
  return /^:\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:$/.test(String(cmd || '').trim());
}

// ── Session token client-side command handlers ─────────────────────────────

function _isSessionTokenSubcommand(cmd) {
  // Only intercept subcommand variants; bare 'session-token' (status) goes to
  // the server so it can be handled as a normal fake command with ANSI styling.
  const lower = (cmd || '').trim().toLowerCase();
  return lower.startsWith('session-token ');
}

async function _doSessionMigration(fromId, toId, tabId) {
  // Use an explicit fetch (not apiFetch) so X-Session-ID is the OLD session ID
  // regardless of what SESSION_ID has been updated to.
  // Returns true on success so the caller switches identity only after a
  // successful migration — leaving the old session active on failure.
  let succeeded = false;
  try {
    const resp = await fetch('/session/migrate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-ID': fromId,
      },
      body: JSON.stringify({ from_session_id: fromId, to_session_id: toId }),
    });
    const data = await resp.json().catch(() => ({}));
    if (resp.ok && data.ok) {
      appendLine(
        `migrated — ${data.migrated_runs} run(s), ${data.migrated_snapshots} snapshot(s), ${data.migrated_stars ?? 0} starred command(s)`,
        '', tabId
      );
      succeeded = true;
    } else {
      appendLine(`[migration failed] ${data.error || resp.status}`, 'exit-fail', tabId);
    }
  } catch (err) {
    appendLine(`[migration failed] ${err.message || 'network error'}`, 'exit-fail', tabId);
    logClientError('session-token migrate', err);
  }
  return succeeded;
}

async function _seedLocalStorageStarsToServer() {
  // Migrate any stars stored in localStorage (legacy or anonymous-session
  // fallback) to the current server session, then clear the localStorage entry.
  // Only the successfully seeded commands are removed; any that fail are kept
  // in localStorage so they are not silently lost on a flaky network.
  let localStars;
  try { localStars = new Set(JSON.parse(localStorage.getItem('starred') || '[]')); }
  catch { localStars = new Set(); }
  if (!localStars.size) {
    // Clear the leftover key (typically a stale empty array from before stars
    // moved server-side) so it does not linger in localStorage indefinitely.
    localStorage.removeItem('starred');
    return;
  }
  const cmds = [...localStars];
  const results = await Promise.allSettled(cmds.map(async cmd => {
    const resp = await apiFetch('/session/starred', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: cmd }),
    });
    if (!resp.ok) throw new Error(String(resp.status));
    return cmd;
  }));
  const failed = cmds.filter((_, i) => results[i].status === 'rejected');
  if (failed.length === 0) {
    localStorage.removeItem('starred');
  } else {
    localStorage.setItem('starred', JSON.stringify(failed));
  }
  if (typeof loadStarredFromServer === 'function') await loadStarredFromServer();
}

async function _sessionTokenGenerate(tabId) {
  const oldSessionId = SESSION_ID;
  try {
    const resp = await apiFetch('/session/token/generate');
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      appendLine(`[error] Failed to generate session token — ${data.error || resp.status}`, 'exit-fail', tabId);
      setStatus('fail');
      return;
    }
    const data = await resp.json();
    const newToken = data.session_token;

    // Check run count on old session before switching identity.
    let runCount = 0;
    try {
      const histResp = await apiFetch('/history');
      if (histResp.ok) {
        const histData = await histResp.json();
        runCount = (histData.runs || []).length;
      }
    } catch (_) {}

    appendLine(`session token generated:  ${maskSessionToken(newToken)}`, '', tabId);
    appendLine('stored in localStorage as session_token', '', tabId);
    appendLine('use session-token set <value> on another device to continue your session', '', tabId);
    appendLine('warning: your session token grants full access to your session history — treat it like a password', 'notice', tabId);

    if (runCount > 0) {
      // Defer identity switch until the user answers the migration prompt so a
      // failed /session/migrate does not strand runs on the old session while
      // the active identity is already the new token.
      appendLine(`you have ${runCount} run(s) in your previous session. migrate history to your new session token? [yes/no]`, '', tabId);
      _pendingSessionMigration = { from: oldSessionId, to: newToken };
      setStatus('idle');
    } else {
      localStorage.setItem('session_token', newToken);
      updateSessionId(newToken);
      await _seedLocalStorageStarsToServer();
      if (typeof reloadSessionHistory === 'function') reloadSessionHistory().catch(() => {});
      setStatus('ok');
    }
  } catch (err) {
    appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', tabId);
    logClientError('session-token generate', err);
    setStatus('fail');
  }
}

async function _sessionTokenSet(value, tabId) {
  if (!value) {
    appendLine('usage: session-token set <token>', '', tabId);
    setStatus('fail');
    return;
  }
  const isTok = value.startsWith('tok_');
  const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
  if (!isTok && !isUuid) {
    appendLine(`[error] invalid session token format — expected tok_... or a UUID`, 'exit-fail', tabId);
    setStatus('fail');
    return;
  }

  // For tok_ tokens, verify server-side existence before switching.
  // A typo would otherwise silently create a brand-new empty session.
  // Fail closed: any failure (network error, non-OK response, missing exists flag)
  // blocks the switch rather than allowing an unverified token through.
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
        verifyErr = 'token verification failed — server returned an error';
      } else if (vData.exists === false) {
        verifyErr = 'session token not found — this token was not issued by this server';
      }
    } catch (_) {
      verifyErr = 'token verification failed — server is unreachable';
    }
    if (verifyErr !== null) {
      appendLine(`[error] ${verifyErr}`, 'exit-fail', tabId);
      setStatus('fail');
      return;
    }
  }

  const oldSessionId = SESSION_ID;

  // Check current session's run count before switching identity.
  let runCount = 0;
  try {
    const histResp = await apiFetch('/history');
    if (histResp.ok) {
      const histData = await histResp.json();
      runCount = (histData.runs || []).length;
    }
  } catch (_) {}

  appendLine(`session token set: ${maskSessionToken(value)}`, '', tabId);
  appendLine('reload other tabs to apply the new session token', '', tabId);

  if (runCount > 0) {
    // Defer identity switch until the user answers the migration prompt so a
    // failed /session/migrate does not strand runs on the old session while
    // the active identity is already the new token.
    appendLine(`you have ${runCount} run(s) in your current session. migrate history to this session token? [yes/no]`, '', tabId);
    _pendingSessionMigration = { from: oldSessionId, to: value };
    setStatus('idle');
  } else {
    localStorage.setItem('session_token', value);
    updateSessionId(value);
    await _seedLocalStorageStarsToServer();
    if (typeof reloadSessionHistory === 'function') reloadSessionHistory().catch(() => {});
    setStatus('ok');
  }
}

function _sessionTokenClear(tabId) {
  if (!localStorage.getItem('session_token')) {
    appendLine('no session token is set — already using an anonymous session', '', tabId);
    setStatus('idle');
    return;
  }
  localStorage.removeItem('session_token');
  const uuid = localStorage.getItem('session_id') || SESSION_ID;
  updateSessionId(uuid);
  if (typeof reloadSessionHistory === 'function') reloadSessionHistory().catch(() => {});
  appendLine(`session token cleared — reverted to anonymous session (${maskSessionToken(uuid)})`, '', tabId);
  appendLine('your session token data remains in the server database', '', tabId);
  setStatus('ok');
}

async function _sessionTokenRotate(tabId) {
  const oldSessionId = SESSION_ID;
  try {
    const resp = await apiFetch('/session/token/generate');
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      appendLine(`[error] Failed to generate session token — ${data.error || resp.status}`, 'exit-fail', tabId);
      setStatus('fail');
      return;
    }
    const data = await resp.json();
    const newToken = data.session_token;

    // Migrate BEFORE updating SESSION_ID so the old ID is sent as X-Session-ID
    const migrateResp = await fetch('/session/migrate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-ID': oldSessionId,
      },
      body: JSON.stringify({ from_session_id: oldSessionId, to_session_id: newToken }),
    });
    const migrateData = await migrateResp.json().catch(() => ({}));

    if (!migrateResp.ok || !migrateData.ok) {
      appendLine(`[error] migration failed — session token NOT rotated: ${migrateData.error || migrateResp.status}`, 'exit-fail', tabId);
      appendLine('your previous session token is still active', '', tabId);
      setStatus('fail');
      return;
    }

    localStorage.setItem('session_token', newToken);
    updateSessionId(newToken);
    if (typeof reloadSessionHistory === 'function') reloadSessionHistory().catch(() => {});

    appendLine(`session token rotated: ${maskSessionToken(newToken)}`, '', tabId);
    appendLine(
      `migrated — ${migrateData.migrated_runs} run(s), ${migrateData.migrated_snapshots} snapshot(s), ${migrateData.migrated_stars ?? 0} starred command(s)`,
      '', tabId
    );
    appendLine('old session token is now inactive — reload other tabs to use the new token', '', tabId);
    setStatus('ok');
  } catch (err) {
    appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', tabId);
    logClientError('session-token rotate', err);
    setStatus('fail');
  }
}

async function _sessionTokenList(tabId) {
  try {
    const resp = await apiFetch('/session/token/info');
    if (!resp.ok) {
      appendLine('[error] failed to load session token info', 'exit-fail', tabId);
      setStatus('fail');
      return;
    }
    const data = await resp.json();
    const w = 14;
    const kv = (k, v) => k.padEnd(w) + '  ' + v;
    if (data.token) {
      appendLine(kv('session token', maskSessionToken(data.token)), 'fake-kv', tabId);
      appendLine(kv('status', 'active'), 'fake-kv', tabId);
      if (data.created) appendLine(kv('created', data.created + ' UTC'), 'fake-kv', tabId);
      appendLine(kv('storage', 'localStorage (session_token)'), 'fake-kv', tabId);
    } else {
      appendLine(kv('session', maskSessionToken(SESSION_ID)), 'fake-kv', tabId);
      appendLine(kv('status', 'anonymous (no session token set)'), 'fake-kv', tabId);
      appendLine(kv('tip', "run 'session-token generate' to create a persistent token"), 'fake-kv', tabId);
    }
    setStatus('ok');
  } catch (err) {
    appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', tabId);
    logClientError('session-token list', err);
    setStatus('fail');
  }
}

async function _sessionTokenRevoke(token, tabId) {
  if (!token) {
    appendLine('usage: session-token revoke <token>', '', tabId);
    setStatus('fail');
    return;
  }
  if (!token.startsWith('tok_')) {
    appendLine('[error] only tok_ tokens can be revoked', 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  try {
    const resp = await apiFetch('/session/token/revoke', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      appendLine(`[error] ${data.error || resp.status}`, 'exit-fail', tabId);
      setStatus('fail');
      return;
    }
    const isCurrentToken = token === SESSION_ID;
    appendLine(`session token revoked: ${maskSessionToken(token)}`, '', tabId);
    if (isCurrentToken) {
      localStorage.removeItem('session_token');
      const uuid = localStorage.getItem('session_id') || SESSION_ID;
      updateSessionId(uuid);
      if (typeof reloadSessionHistory === 'function') reloadSessionHistory().catch(() => {});
      appendLine(`reverted to anonymous session (${maskSessionToken(uuid)})`, '', tabId);
    } else {
      appendLine('token removed from server — any device using it is now on an empty anonymous session', '', tabId);
    }
    setStatus('ok');
  } catch (err) {
    appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', tabId);
    logClientError('session-token revoke', err);
    setStatus('fail');
  }
}

async function _handleSessionTokenCommand(cmd, tabId) {
  const parts = cmd.trim().split(/\s+/);
  const sub = (parts[1] || '').toLowerCase();
  appendCommandEcho(cmd);
  if (sub === 'generate') {
    await _sessionTokenGenerate(tabId);
  } else if (sub === 'set') {
    const value = parts.slice(2).join(' ').trim();
    await _sessionTokenSet(value, tabId);
  } else if (sub === 'clear') {
    _sessionTokenClear(tabId);
  } else if (sub === 'rotate') {
    await _sessionTokenRotate(tabId);
  } else if (sub === 'list') {
    await _sessionTokenList(tabId);
  } else if (sub === 'revoke') {
    const value = parts.slice(2).join(' ').trim();
    await _sessionTokenRevoke(value, tabId);
  } else {
    appendLine(`session-token: unknown subcommand '${sub}'`, 'exit-fail', tabId);
    appendLine('usage: session-token [generate | set <value> | clear | rotate | list | revoke <token>]', '', tabId);
    setStatus('fail');
  }
}

// ── End session token handlers ───────────────────────────────────────────────

function submitCommand(rawCmd) {
  // This is the main run path: validate local state, open the SSE stream, then
  // feed output into the active tab while mirroring completion into persistence.
  const cmd = (rawCmd || '').trim();
  if (!cmd) {
    if (_welcomeActive && welcomeOwnsTab(activeTabId)) {
      requestWelcomeSettle(activeTabId);
      return 'settle';
    }
    const _activeTab = getActiveTab();
    if (_activeTab && _activeTab.st === 'running') return true;
    appendPromptNewline(activeTabId);
    setStatus('idle');
    return true;
  }

  // Intercept yes/no answer to a pending session migration prompt
  if (_pendingSessionMigration) {
    const answer = cmd.trim().toLowerCase();
    const pending = _pendingSessionMigration;
    _pendingSessionMigration = null;
    addToHistory(cmd);
    appendCommandEcho(cmd);
    if (answer === 'yes' || answer === 'y') {
      // _doSessionMigration returns true on success; switch identity only then
      // so a failed migrate leaves the old session active rather than stranding
      // the user on the new token with their runs still on the old session.
      _doSessionMigration(pending.from, pending.to, activeTabId).then(async (migrated) => {
        if (migrated) {
          localStorage.setItem('session_token', pending.to);
          updateSessionId(pending.to);
          await _seedLocalStorageStarsToServer();
          if (typeof reloadSessionHistory === 'function') reloadSessionHistory().catch(() => {});
        }
        setStatus('idle');
      });
    } else {
      // User declined migration — switch to new token without migrating runs.
      localStorage.setItem('session_token', pending.to);
      updateSessionId(pending.to);
      _seedLocalStorageStarsToServer().then(() => {
        if (typeof reloadSessionHistory === 'function') reloadSessionHistory().catch(() => {});
      });
      appendLine('History migration skipped.', '', activeTabId);
      setStatus('idle');
    }
    return true;
  }

  // If the active tab is currently running a command, open a new tab automatically
  // rather than streaming two commands' output on top of each other.
  // Use tab.st (set synchronously by setTabStatus) rather than tab.runId (set
  // asynchronously via SSE) to avoid a race condition where rapid Enter presses
  // fire before the server's 'started' message arrives.
  // If the welcome typeout is still running, cancel it and clear partial output
  if (welcomeOwnsTab(activeTabId)) {
    cancelWelcome(activeTabId);
    clearTab(activeTabId);
  }

  const activeTab = getActiveTab();
  if (activeTab && activeTab.st === 'running') {
    const newId = createTab('tab ' + (tabs.length + 1));
    if (!newId) return false; // tab limit reached — createTab already showed a toast
    // createTab calls activateTab internally, so activeTabId now points to the new tab
  }

  // Client-side validation mirrors server-side checks for immediate feedback
  const shellOps = /&&|\|\|?|;;?|`|\$\(|>>?|</;
  if (shellOps.test(cmd) && !_isSyntheticPostFilterCommand(cmd) && !_isExactSpecialBuiltInCommand(cmd)) {
    appendCommandEcho(cmd);
    appendLine('[denied] Shell operators (&&, |, ;, >, etc.) are not permitted.', 'denied');
    setStatus('fail');
    return false;
  }

  if (/(?<![\w:\/])\/data\b/.test(cmd) || /(?<![\w:\/])\/tmp\b/.test(cmd)) {
    appendCommandEcho(cmd);
    appendLine('[denied] Access to /data and /tmp is not permitted.', 'denied');
    setStatus('fail');
    return false;
  }

  addToHistory(cmd);

  // Session-token subcommands (generate / set / clear / rotate) run entirely
  // client-side.  The bare 'session-token' status command goes to the server.
  if (_isSessionTokenSubcommand(cmd)) {
    _handleSessionTokenCommand(cmd, activeTabId);
    return true;
  }

  // Re-lookup the active tab after the potential createTab() call above, which
  // may have changed activeTabId to point at the newly created tab.
  const _runTab = getActiveTab();
  if (!_runTab || !_runTab.renamed) setTabLabel(activeTabId, cmd);
  if (_runTab) _runTab.command = cmd;
  appendCommandEcho(cmd);
  // Set runStart after the prompt line so it doesn't receive an elapsed stamp
  if (_runTab) {
    _runTab.runStart = Date.now();
    _runTab.currentRunStartIndex = _runTab.rawLines.length;
    _runTab.previewTruncated = false;
    _runTab.fullOutputAvailable = false;
    _runTab.fullOutputLoaded = false;
    _runTab.historyRunId = null;
    _runTab.reconnectedRun = false;
    _runTab.followOutput = true;
    _runTab.deferPromptMount = false;
  }
  setStatus('running');
  setTabStatus(activeTabId, 'running');
  _setRunButtonDisabled(true);
  showTabKillBtn(activeTabId);
  startTimer();

  const tabId = activeTabId;

  apiFetch('/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command: cmd })
  }).then(res => {
    if (res.status === 403) {
      return res.json().then(data => {
        appendLine('[denied] ' + (data.error || 'Command not allowed.'), 'denied', tabId);
        setStatus('fail'); setTabStatus(tabId, 'fail');
        stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
      });
    }
    if (res.status === 429) {
      appendLine('[rate limited] Too many requests. Please wait a moment.', 'denied', tabId);
      setStatus('fail'); setTabStatus(tabId, 'fail');
      stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
      return;
    }
    if (!res.ok) {
      return _readRunErrorMessage(res).then(message => {
        const suffix = message ? ` ${message}` : '';
        appendLine(`[server error] The server could not start the command.${suffix}`, 'exit-fail', tabId);
        setStatus('fail'); setTabStatus(tabId, 'fail');
        stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
      });
    }
    if (!res.body || typeof res.body.getReader !== 'function') {
      appendLine('[server error] The server returned an invalid streaming response.', 'exit-fail', tabId);
      setStatus('fail'); setTabStatus(tabId, 'fail');
      stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    _resetStalledTimeout(tabId);

    function read() {
      reader.read().then(({ done, value }) => {
        if (done) { _clearStalledTimeout(tabId); stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId); return; }
        _resetStalledTimeout(tabId);
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop();
        parts.forEach(part => {
          if (part.startsWith('data: ')) {
            try {
              const msg = JSON.parse(part.slice(6));
              if (msg.type === 'started') {
                const t = getTab(tabId);
                if (t) {
                  t.runId = msg.run_id;
                  t.historyRunId = msg.run_id;
                  t.reconnectedRun = false;
                  if (t.pendingKill) {
                    // Kill was requested before runId was available — send it now
                    t.pendingKill = false;
                    apiFetch('/kill', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ run_id: t.runId })
                    }).catch(err => _handleKillRequestFailure(err, tabId));
                    t.runId = null;
                  } else {
                    t.killed = false;
                  }
                }
              } else if (msg.type === 'notice') {
                appendLine(msg.text, 'notice', tabId);
              } else if (msg.type === 'clear') {
                clearTab(tabId);
                const t = getTab(tabId);
                if (t) t.syntheticClear = true;
              } else if (msg.type === 'output') {
                msg.text.split('\n').forEach((line, i, arr) => {
                  if (i < arr.length - 1 || line) appendLine(line, msg.cls || '', tabId);
                });
              } else if (msg.type === 'exit') {
                _clearStalledTimeout(tabId);
                const t = getTab(tabId);
                if (t) {
                  t.exitCode = msg.code;
                  t.runId = null;
                  t.reconnectedRun = false;
                  t.deferPromptMount = true;
                  t.previewTruncated = !!msg.preview_truncated;
                  t.fullOutputAvailable = !!msg.full_output_available;
                  t.fullOutputLoaded = !msg.preview_truncated;
                }
                // If already killed by user, ignore the subsequent -15 exit code
                if (t && t.killed) {
                  t.killed = false;
                  stopTimer();
                  _setRunButtonDisabled(false); hideTabKillBtn(tabId);
                  if (t.closing && typeof finalizeClosingTab === 'function') {
                    finalizeClosingTab(tabId);
                    if (isHistoryPanelOpen()) refreshHistoryPanel();
                  }
                  if (isHistoryPanelOpen()) refreshHistoryPanel();
                  if (!(t && t.closing) && typeof _maybeMountDeferredPrompt === 'function') {
                    _maybeMountDeferredPrompt(tabId);
                  }
                  return;
                }
                const dur = msg.elapsed ? ` in ${msg.elapsed}s` : '';
                stopTimer();
                if (msg.preview_truncated) {
                  appendLine(_previewTruncationNotice(msg.output_line_count, msg.full_output_available), 'notice', tabId);
                }
                if (msg.code === 0) {
                  if (!(t && t.syntheticClear)) appendLine(`[process exited with code 0${dur}]`, 'exit-ok', tabId);
                  if (tabId === activeTabId) setStatus('ok');
                  setTabStatus(tabId, 'ok');
                  if (typeof addToRecentPreview === 'function' && t && t.command) {
                    addToRecentPreview(t.command);
                  }
                } else {
                  appendLine(`[process exited with code ${msg.code}${dur}]`, 'exit-fail', tabId);
                  if (tabId === activeTabId) setStatus('fail');
                  setTabStatus(tabId, 'fail');
                }
                if (t) t.syntheticClear = false;
                _maybeNotify(t ? t.command : '', msg.code, msg.elapsed ? msg.elapsed + 's' : null);
                if (typeof setHudLastExit === 'function') setHudLastExit(msg.code);
                _setRunButtonDisabled(false); hideTabKillBtn(tabId);
                if (t && t.closing && typeof finalizeClosingTab === 'function') {
                  finalizeClosingTab(tabId);
                  if (isHistoryPanelOpen()) refreshHistoryPanel();
                  return;
                }
                if (isHistoryPanelOpen()) refreshHistoryPanel();
                if (typeof _maybeMountDeferredPrompt === 'function') _maybeMountDeferredPrompt(tabId);
              } else if (msg.type === 'error') {
                _clearStalledTimeout(tabId);
                appendLine('[error] ' + msg.text, 'exit-fail', tabId);
                if (tabId === activeTabId) setStatus('fail');
                setTabStatus(tabId, 'fail');
                stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
              }
            } catch(e) {}
          }
        });
        read();
      });
    }
    read();
  }).catch(err => {
    _clearStalledTimeout(tabId);
    _handleRunTransportFailure(err, tabId);
  });
  return true;
}

function submitComposerCommand(rawCmd, { dismissKeyboard = false, focusAfterSubmit = true } = {}) {
  const result = submitCommand(rawCmd);
  if (result === true) {
    _clearDesktopInput();
    if (focusAfterSubmit) refocusComposerAfterAction();
    if (dismissKeyboard && typeof dismissMobileKeyboardAfterSubmit === 'function') {
      dismissMobileKeyboardAfterSubmit();
    }
  } else if (result === 'settle') {
    refocusComposerAfterAction();
  }
  return result;
}

function submitVisibleComposerCommand({ rawCmd = null, dismissKeyboard = false, focusAfterSubmit = true } = {}) {
  const value = typeof rawCmd === 'string'
    ? rawCmd
    : ((typeof getComposerValue === 'function') ? getComposerValue() : '');
  return submitComposerCommand(value, { dismissKeyboard, focusAfterSubmit });
}

function runCommand() {
  if (typeof isRunButtonDisabled === 'function' && isRunButtonDisabled()) return;
  const value = typeof getComposerValue === 'function' ? getComposerValue() : (cmdInput ? cmdInput.value : '');
  submitComposerCommand(value, { dismissKeyboard: true });
}
