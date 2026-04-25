// ── Shared command execution + desktop input wrapper ──
// If no chunk arrives from the SSE stream for 45 seconds (> 2× the 20s server heartbeat),
// the connection has silently died. Surface a notice and reset the UI so the user isn't
// left with a perpetually-spinning tab. The command may still be running server-side;
// the result will appear in the history panel once it completes.
// Keyed by tabId so multiple concurrent tabs each have their own independent timer.
const _stalledTimeouts = new Map();
const _stalledRuns = new Set();
let _activeRunPollTimer = null;

// Pending terminal confirmation: used by transcript-owned yes/no flows such as
// session-token migration and token-clear confirmation. While set, the next
// typed answer is consumed as part of the active script-style prompt instead of
// as a normal shell command.
let _pendingTerminalConfirm = null;

function _resetStalledTimeout(tabId) {
  clearTimeout(_stalledTimeouts.get(tabId));
  _stalledTimeouts.set(tabId, setTimeout(() => {
    const t = getTab(tabId);
    if (!t || t.killed) return;  // already handled
    _stalledRuns.add(tabId);
    appendLine('[connection stalled — no stream activity arrived from the server for 45s]', 'denied', tabId);
    appendLine('[the command may still be running; if the stream resumes, live output will continue here]', 'denied', tabId);
    appendLine('[otherwise check the history panel for the final result once it completes]', 'denied', tabId);
    if (tabId === activeTabId) setStatus('fail');
    setTabStatus(tabId, 'fail');
    stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
  }, 45000));
}

function _clearStalledTimeout(tabId) {
  clearTimeout(_stalledTimeouts.get(tabId));
  _stalledTimeouts.delete(tabId);
  _stalledRuns.delete(tabId);
}

function _recoverStalledRun(tabId) {
  if (!_stalledRuns.has(tabId)) return;
  _stalledRuns.delete(tabId);
  appendLine('[connection re-established — live output resumed]', 'exit-ok', tabId);
  const t = getTab(tabId);
  if (!t || t.killed) return;
  if (tabId === activeTabId) {
    setStatus('running');
    syncActiveRunTimer(tabId);
  }
  setTabStatus(tabId, 'running');
  _setRunButtonDisabled(true);
  showTabKillBtn(tabId);
}

function _shouldSuppressStreamOutputLine(tab, line) {
  if (!tab || typeof line !== 'string') return false;
  const root = String(tab.command || '').trim().split(/\s+/, 1)[0].toLowerCase();
  if (root !== 'nc') return false;
  return /^Warning: inverse host lookup failed for /i.test(line);
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
  if (typeof emitUiEvent === 'function') {
    emitUiEvent('app:status-changed', { status: s });
    if (s === 'ok') emitUiEvent('app:last-exit-changed', { value: 0 });
    else if (s === 'fail') emitUiEvent('app:last-exit-changed', { value: 1 });
    else if (s === 'killed') emitUiEvent('app:last-exit-changed', { value: 'killed' });
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
    const tabId = canReuseBootstrapTab ? bootstrapTab.id : createTab();
    if (!tabId) return;
    if (!firstRestoredTabId) firstRestoredTabId = tabId;
    clearTab(tabId);
    const t = getTab(tabId);
    if (!t) return;
    if (typeof setTabRunningCommand === 'function') {
      setTabRunningCommand(tabId, run.command);
    } else {
      if (!t.renamed) setTabLabel(tabId, run.command);
      t.command = run.command;
    }
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

function _streamOutputMetadata(msg) {
  if (!msg || typeof msg !== 'object') return null;
  const metadata = {};
  if (Array.isArray(msg.signals) && msg.signals.length) metadata.signals = msg.signals;
  if (Number.isInteger(msg.line_index)) metadata.line_index = msg.line_index;
  if (typeof msg.command_root === 'string' && msg.command_root) metadata.command_root = msg.command_root;
  if (typeof msg.target === 'string' && msg.target) metadata.target = msg.target;
  return Object.keys(metadata).length ? metadata : null;
}

function _appendStreamLine(text, cls, tabId, msg) {
  const metadata = _streamOutputMetadata(msg);
  if (metadata) appendLine(text, cls, tabId, metadata);
  else appendLine(text, cls, tabId);
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
  if (typeof emitUiEvent === 'function') emitUiEvent('app:last-exit-changed', { value: 'killed' });
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
  if (tokens.some(token => ['&&', '||', ';', ';;', '>', '>>', '<', '&'].includes(token))) return null;
  const pipeIndexes = tokens
    .map((token, index) => (token === '|' ? index : -1))
    .filter(index => index !== -1);
  if (!pipeIndexes.length || pipeIndexes[0] <= 0) return null;

  function unquoteToken(token) {
    const value = String(token || '');
    if (value.length >= 2) {
      const first = value[0];
      if ((first === '"' || first === "'") && value[value.length - 1] === first) {
        return value.slice(1, -1);
      }
    }
    return value;
  }

  function parseStage(stageTokens) {
    if (!stageTokens.length) return null;
    const normalizedStageTokens = stageTokens.map(unquoteToken);
    const helper = String(normalizedStageTokens[0]).toLowerCase();

    if (helper === 'grep') {
      let pattern = null;
      const options = { ignoreCase: false, invertMatch: false, extended: false };
      for (const token of normalizedStageTokens.slice(1)) {
        if (pattern === null && /^-[^-]/.test(token)) {
          for (const flag of token.slice(1)) {
            if (!['i', 'v', 'E'].includes(flag)) return null;
            if (flag === 'i') options.ignoreCase = true;
            if (flag === 'v') options.invertMatch = true;
            if (flag === 'E') options.extended = true;
          }
          continue;
        }
        if (pattern !== null) return null;
        pattern = token;
      }
      return pattern !== null ? { kind: 'grep', pattern, ...options } : null;
    }

    if (helper === 'head' || helper === 'tail') {
      if (normalizedStageTokens.length === 1) return { kind: helper, count: 10 };
      if (normalizedStageTokens.length === 2 && /^-\d+$/.test(normalizedStageTokens[1])) {
        return { kind: helper, count: Number(normalizedStageTokens[1].slice(1)) };
      }
      if (
        normalizedStageTokens.length !== 3
        || normalizedStageTokens[1] !== '-n'
        || !/^\d+$/.test(normalizedStageTokens[2])
      ) {
        return null;
      }
      return { kind: helper, count: Number(normalizedStageTokens[2]) };
    }

    if (helper === 'wc') {
      if (normalizedStageTokens.length === 2 && normalizedStageTokens[1] === '-l') {
        return { kind: 'wc_l' };
      }
      return null;
    }

    if (helper === 'sort') {
      if (normalizedStageTokens.length === 1) {
        return { kind: 'sort', reverse: false, numeric: false, unique: false };
      }
      if (normalizedStageTokens.length === 2) {
        const flag = normalizedStageTokens[1];
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
      if (normalizedStageTokens.length === 1) return { kind: 'uniq', count: false };
      if (normalizedStageTokens.length === 2 && normalizedStageTokens[1] === '-c') {
        return { kind: 'uniq', count: true };
      }
      return null;
    }

    return null;
  }

  const stages = [];
  let stageStart = pipeIndexes[0] + 1;
  for (const pipeIndex of pipeIndexes.slice(1).concat(tokens.length)) {
    const stageTokens = tokens.slice(stageStart, pipeIndex);
    const stage = parseStage(stageTokens);
    if (!stage) return null;
    stages.push(stage);
    stageStart = pipeIndex + 1;
  }

  return {
    kind: stages[0] ? stages[0].kind : null,
    baseCommand: tokens.slice(0, pipeIndexes[0]).map(unquoteToken).join(' '),
    stages,
  };
}

function _applySyntheticPostFilterLines(lineItems, spec) {
  const stages = spec && Array.isArray(spec.stages) ? spec.stages : [];
  let items = Array.isArray(lineItems) ? lineItems.slice() : [];

  function textOf(item) {
    return String(item && item.text !== undefined ? item.text : item || '');
  }

  function plainItem(text) {
    return { text: String(text), cls: '' };
  }

  for (const stage of stages) {
    const kind = stage && stage.kind;
    if (kind === 'grep') {
      let matches;
      if (stage.extended) {
        let regex;
        try {
          regex = new RegExp(String(stage.pattern || ''), stage.ignoreCase ? 'i' : '');
        } catch (err) {
          return [{ text: `[error] Invalid synthetic grep regex: ${err.message}`, cls: 'exit-fail' }];
        }
        matches = (line) => regex.test(line);
      } else {
        const needle = String(stage.pattern || '');
        const normalizedNeedle = stage.ignoreCase ? needle.toLowerCase() : needle;
        matches = (line) => {
          const haystack = stage.ignoreCase ? line.toLowerCase() : line;
          return haystack.includes(normalizedNeedle);
        };
      }
      items = items.filter((item) => {
        const matched = matches(textOf(item));
        return stage.invertMatch ? !matched : matched;
      });
    } else if (kind === 'head') {
      items = items.slice(0, Math.max(0, Number(stage.count || 0)));
    } else if (kind === 'tail') {
      const count = Math.max(0, Number(stage.count || 0));
      items = count > 0 ? items.slice(-count) : [];
    } else if (kind === 'wc_l') {
      items = [plainItem(String(items.length))];
    } else if (kind === 'sort') {
      const numeric = !!stage.numeric;
      const sorted = items.slice().sort((a, b) => {
        const aText = textOf(a).trimStart();
        const bText = textOf(b).trimStart();
        if (numeric) {
          const aMatch = aText.match(/^[-+]?\d+\.?\d*/);
          const bMatch = bText.match(/^[-+]?\d+\.?\d*/);
          const aNum = aMatch ? Number(aMatch[0]) : Number.NEGATIVE_INFINITY;
          const bNum = bMatch ? Number(bMatch[0]) : Number.NEGATIVE_INFINITY;
          return aNum - bNum;
        }
        return aText.toLowerCase().localeCompare(bText.toLowerCase());
      });
      if (stage.reverse) sorted.reverse();
      items = sorted;
      if (stage.unique) {
        const seen = new Set();
        items = items.filter((item) => {
          const key = textOf(item);
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
      }
    } else if (kind === 'uniq') {
      const result = [];
      let previous = null;
      let count = 0;
      const flush = () => {
        if (previous === null) return;
        result.push(stage.count ? plainItem(`${String(count).padStart(7)} ${previous}`) : plainItem(previous));
      };
      items.forEach((item) => {
        const text = textOf(item);
        if (text === previous) {
          count += 1;
          return;
        }
        flush();
        previous = text;
        count = 1;
      });
      flush();
      items = result;
    }
  }
  return items;
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

function _isClientSideUiCommand(cmd) {
  const root = String(cmd || '').trim().split(/\s+/, 1)[0].toLowerCase();
  return root === 'theme' || root === 'config';
}

function _workspaceDeleteTarget(cmd) {
  const parts = String(cmd || '').trim().split(/\s+/).filter(Boolean);
  const root = (parts[0] || '').toLowerCase();
  if (root === 'rm' && parts.length === 2) return parts[1];
  if (root === 'workspace' && parts.length === 3 && ['rm', 'delete'].includes((parts[1] || '').toLowerCase())) {
    return parts[2];
  }
  return '';
}

function _isWorkspaceDeleteCommand(cmd) {
  return !!_workspaceDeleteTarget(cmd);
}

function _historySafeCommand(cmd) {
  const value = String(cmd || '').trim();
  if (!value) return '';
  return value.replace(
    /\b(session-token\s+(?:set|revoke)\s+)(tok_[A-Za-z0-9]+|[0-9a-f]{8}-[0-9a-f-]{28,})\b/i,
    (_match, prefix, token) => `${prefix}${maskSessionToken(token)}`,
  );
}

function _recordSuccessfulLocalCommand(cmd) {
  if (typeof addToRecentPreview !== 'function') return;
  const value = _historySafeCommand(cmd);
  if (value) addToRecentPreview(value);
}

function _clientSideRunExitCodeFromStatus(statusValue) {
  return statusValue === 'fail' ? 1 : 0;
}

function _finalizeClientSideCommandStatus(tabId, statusValue) {
  const failed = statusValue === 'fail';
  const exitCode = failed ? 1 : 0;
  const finalStatus = failed ? 'fail' : 'ok';
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  if (tab) {
    tab.exitCode = exitCode;
    tab.runId = null;
    tab.reconnectedRun = false;
  }
  if (tabId === activeTabId) setStatus(finalStatus);
  setTabStatus(tabId, finalStatus);
  if (typeof emitUiEvent === 'function') emitUiEvent('app:last-exit-changed', { value: exitCode });
}

function _persistClientSideRun(command, lineItems, statusValue) {
  const safeCommand = _historySafeCommand(command);
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
      exit_code: _clientSideRunExitCodeFromStatus(statusValue),
      lines,
    }),
  }).then((resp) => {
    if (!resp || !resp.ok) throw new Error(String(resp && resp.status || 'unknown'));
    if (typeof isHistoryPanelOpen === 'function' && isHistoryPanelOpen()) refreshHistoryPanel();
  }).catch((err) => {
    if (typeof logClientError === 'function') logClientError('client-side run persistence failed', err);
  });
}

function _persistSessionTokenRun(command, lineItems, statusValue = 'ok') {
  _persistClientSideRun(command, lineItems, statusValue);
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
        `migrated — ${data.migrated_runs} run(s), ${data.migrated_snapshots} snapshot(s), ${data.migrated_stars ?? 0} starred command(s), and saved user options when the destination had none`,
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

function _setPendingTerminalConfirm(config) {
  _pendingTerminalConfirm = config || null;
  if (typeof setComposerPromptMode === 'function') {
    setComposerPromptMode(_pendingTerminalConfirm ? 'confirm' : null);
  }
}

function hasPendingTerminalConfirm() {
  return !!_pendingTerminalConfirm;
}

async function _runPendingTerminalConfirmHandler(promptTabId, handler) {
  const originalSetStatus = setStatus;
  let finalStatus = 'idle';
  try {
    setStatus = (statusValue) => {
      finalStatus = statusValue;
      originalSetStatus(statusValue);
    };
    await Promise.resolve(typeof handler === 'function' ? handler() : undefined);
  } finally {
    setStatus = originalSetStatus;
  }
  _finalizeClientSideCommandStatus(promptTabId, finalStatus);
}

function cancelPendingTerminalConfirm(tabId = activeTabId) {
  if (!_pendingTerminalConfirm) return false;
  const pending = _pendingTerminalConfirm;
  const promptTabId = pending.tabId || tabId || activeTabId;
  _setPendingTerminalConfirm(null);
  const cancelHandler = typeof pending.onCancel === 'function'
    ? pending.onCancel
    : (typeof pending.onNo === 'function' ? pending.onNo : null);
  _runPendingTerminalConfirmHandler(promptTabId, cancelHandler).catch((err) => {
    appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', promptTabId);
    setStatus('fail');
    _finalizeClientSideCommandStatus(promptTabId, 'fail');
  });
  refocusComposerAfterAction();
  return true;
}

function _appendSessionTokenSetLines(token, tabId) {
  appendLine(`session token set: ${maskSessionToken(token)}`, '', tabId);
  appendLine('reload other tabs to apply the new session token', '', tabId);
}

function _clearVisibleSessionHistoryState() {
  if (typeof hydrateCmdHistory === 'function') hydrateCmdHistory([]);
}

async function _activateSessionTokenIdentity(token) {
  localStorage.setItem('session_token', token);
  updateSessionId(token);
  await _seedLocalStorageStarsToServer();
  if (typeof reloadSessionHistory === 'function') await reloadSessionHistory().catch(() => {});
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
      const countResp = await apiFetch('/session/run-count');
      if (countResp.ok) runCount = (await countResp.json()).count || 0;
    } catch (_) {}

    appendLine(`session token generated:  ${maskSessionToken(newToken)}`, '', tabId);
    appendLine('stored in localStorage as session_token', '', tabId);
    appendLine('use session-token set <value> on another device to continue your session', '', tabId);
    appendLine('warning: your session token grants full access to your session history — treat it like a password', 'notice', tabId);

    if (runCount > 0) {
      // Defer identity switch until the user answers the migration prompt so a
      // failed /session/migrate does not strand runs on the old session while
      // the active identity is already the new token.
      appendLine(`you have ${runCount} run(s) in your previous session. migrate history to your new session token?`, '', tabId);
      _setPendingTerminalConfirm({
        tabId,
        onYes: async () => {
          const migrated = await _doSessionMigration(oldSessionId, newToken, tabId);
          if (migrated) {
            localStorage.setItem('session_token', newToken);
            updateSessionId(newToken);
            await _seedLocalStorageStarsToServer();
            if (typeof reloadSessionHistory === 'function') await reloadSessionHistory().catch(() => {});
            _recordSuccessfulLocalCommand('session-token generate');
            _persistSessionTokenRun('session-token generate', [
              { text: `session token generated:  ${maskSessionToken(newToken)}` },
              { text: 'history migrated to the new session token' },
            ]);
          }
          setStatus('idle');
        },
        onNo: async () => {
          localStorage.setItem('session_token', newToken);
          updateSessionId(newToken);
          await _seedLocalStorageStarsToServer();
          if (typeof reloadSessionHistory === 'function') await reloadSessionHistory().catch(() => {});
          _recordSuccessfulLocalCommand('session-token generate');
          appendLine('History migration skipped.', '', tabId);
          _persistSessionTokenRun('session-token generate', [
            { text: `session token generated:  ${maskSessionToken(newToken)}` },
            { text: 'History migration skipped.' },
          ]);
          setStatus('idle');
        },
      });
      setStatus('idle');
    } else {
      localStorage.setItem('session_token', newToken);
      updateSessionId(newToken);
      await _seedLocalStorageStarsToServer();
      if (typeof reloadSessionHistory === 'function') reloadSessionHistory().catch(() => {});
      _recordSuccessfulLocalCommand('session-token generate');
      _persistSessionTokenRun('session-token generate', [
        { text: `session token generated:  ${maskSessionToken(newToken)}` },
        { text: 'stored in localStorage as session_token' },
      ]);
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
    const countResp = await apiFetch('/session/run-count');
    if (countResp.ok) runCount = (await countResp.json()).count || 0;
  } catch (_) {}

  if (runCount > 0) {
    // Defer identity switch until the user answers the migration prompt so a
    // failed /session/migrate does not strand runs on the old session while
    // the active identity is already the new token.
    appendLine(`you have ${runCount} run(s) in your current session. migrate history to this session token?`, '', tabId);
    _setPendingTerminalConfirm({
      tabId,
      onYes: async () => {
        const migrated = await _doSessionMigration(oldSessionId, value, tabId);
        if (migrated) {
          await _activateSessionTokenIdentity(value);
          _appendSessionTokenSetLines(value, tabId);
          _recordSuccessfulLocalCommand(`session-token set ${value}`);
          _persistSessionTokenRun(`session-token set ${value}`, [
            { text: `session token set: ${maskSessionToken(value)}` },
            { text: 'reload other tabs to apply the new session token' },
          ]);
        }
        setStatus('idle');
      },
      onNo: async () => {
        await _activateSessionTokenIdentity(value);
        _appendSessionTokenSetLines(value, tabId);
        _recordSuccessfulLocalCommand(`session-token set ${value}`);
        appendLine('History migration skipped.', '', tabId);
        _persistSessionTokenRun(`session-token set ${value}`, [
          { text: `session token set: ${maskSessionToken(value)}` },
          { text: 'reload other tabs to apply the new session token' },
          { text: 'History migration skipped.' },
        ]);
        setStatus('idle');
      },
      onCancel: async () => {
        appendLine('Session token set canceled.', '', tabId);
        setStatus('idle');
      },
    });
    setStatus('idle');
  } else {
    await _activateSessionTokenIdentity(value);
    _appendSessionTokenSetLines(value, tabId);
    _recordSuccessfulLocalCommand(`session-token set ${value}`);
    _persistSessionTokenRun(`session-token set ${value}`, [
      { text: `session token set: ${maskSessionToken(value)}` },
      { text: 'reload other tabs to apply the new session token' },
    ]);
    setStatus('ok');
  }
}

async function _sessionTokenCopy(tabId) {
  const token = localStorage.getItem('session_token');
  if (!token) {
    appendLine('no session token is set — already using an anonymous session', '', tabId);
    setStatus('idle');
    return;
  }
  try {
    await copyTextToClipboard(token);
    appendLine(`session token copied to clipboard: ${maskSessionToken(token)}`, '', tabId);
    _recordSuccessfulLocalCommand('session-token copy');
    _persistSessionTokenRun('session-token copy', [
      { text: `session token copied to clipboard: ${maskSessionToken(token)}` },
    ]);
    setStatus('ok');
  } catch (err) {
    appendLine('[error] failed to copy the session token to clipboard', 'exit-fail', tabId);
    logClientError('session-token copy', err);
    setStatus('fail');
  }
}

async function _sessionTokenClear(tabId) {
  if (!localStorage.getItem('session_token')) {
    appendLine('no session token is set — already using an anonymous session', '', tabId);
    setStatus('idle');
    return;
  }
  appendLine('warning: clearing the active session token removes it from this browser', 'notice', tabId);
  appendLine("run 'session-token copy' first if you want to save the current token before clearing it", 'notice', tabId);
  appendLine('clear the active session token and revert to an anonymous session?', '', tabId);
  _setPendingTerminalConfirm({
    tabId,
    onYes: async () => {
      localStorage.removeItem('session_token');
      const uuid = localStorage.getItem('session_id') || SESSION_ID;
      updateSessionId(uuid);
      _clearVisibleSessionHistoryState();
      if (typeof reloadSessionHistory === 'function') await reloadSessionHistory().catch(() => {});
      appendLine(`session token cleared — reverted to anonymous session (${maskSessionToken(uuid)})`, '', tabId);
      appendLine('your session token data remains in the server database', '', tabId);
      _recordSuccessfulLocalCommand('session-token clear');
      _persistSessionTokenRun('session-token clear', [
        { text: `session token cleared — reverted to anonymous session (${maskSessionToken(uuid)})` },
        { text: 'your session token data remains in the server database' },
      ]);
      setStatus('ok');
    },
    onNo: async () => {
      appendLine('Session token clear canceled.', '', tabId);
      setStatus('idle');
    },
  });
  setStatus('idle');
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
      `migrated — ${migrateData.migrated_runs} run(s), ${migrateData.migrated_snapshots} snapshot(s), ${migrateData.migrated_stars ?? 0} starred command(s), and saved user options when the destination had none`,
      '', tabId
    );
    appendLine('old session token is now inactive — reload other tabs to use the new token', '', tabId);
    _recordSuccessfulLocalCommand('session-token rotate');
    _persistSessionTokenRun('session-token rotate', [
      { text: `session token rotated: ${maskSessionToken(newToken)}` },
      {
        text: `migrated — ${migrateData.migrated_runs} run(s), ${migrateData.migrated_snapshots} snapshot(s), `
          + `${migrateData.migrated_stars ?? 0} starred command(s), and saved user options when the destination had none`,
      },
      { text: 'old session token is now inactive — reload other tabs to use the new token' },
    ]);
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
    _recordSuccessfulLocalCommand('session-token list');
    _persistSessionTokenRun('session-token list', [
      { text: data.token ? `session token  ${maskSessionToken(data.token)}` : `session  ${maskSessionToken(SESSION_ID)}`, cls: 'fake-kv' },
      { text: data.token ? 'status          active' : 'status          anonymous (no session token set)', cls: 'fake-kv' },
    ]);
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
      _clearVisibleSessionHistoryState();
      if (typeof reloadSessionHistory === 'function') reloadSessionHistory().catch(() => {});
      appendLine(`reverted to anonymous session (${maskSessionToken(uuid)})`, '', tabId);
    } else {
      appendLine('token removed from server — any device using it is now on an empty anonymous session', '', tabId);
    }
    _recordSuccessfulLocalCommand(`session-token revoke ${token}`);
    _persistSessionTokenRun(`session-token revoke ${token}`, [
      { text: `session token revoked: ${maskSessionToken(token)}` },
    ]);
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
  } else if (sub === 'copy') {
    await _sessionTokenCopy(tabId);
  } else if (sub === 'set') {
    const value = parts.slice(2).join(' ').trim();
    await _sessionTokenSet(value, tabId);
  } else if (sub === 'clear') {
    await _sessionTokenClear(tabId);
  } else if (sub === 'rotate') {
    await _sessionTokenRotate(tabId);
  } else if (sub === 'list') {
    await _sessionTokenList(tabId);
  } else if (sub === 'revoke') {
    const value = parts.slice(2).join(' ').trim();
    await _sessionTokenRevoke(value, tabId);
  } else {
    appendLine(`session-token: unknown subcommand '${sub}'`, 'exit-fail', tabId);
    appendLine('usage: session-token [generate | copy | set <value> | clear | rotate | list | revoke <token>]', '', tabId);
    setStatus('fail');
  }
}

async function _handleWorkspaceDeleteCommand(cmd, tabId) {
  const target = _workspaceDeleteTarget(cmd);
  appendCommandEcho(cmd);
  if (!target) {
    appendLine('Usage: workspace rm <file>', 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  appendLine(`delete workspace file '${target}'?`, '', tabId);
  _setPendingTerminalConfirm({
    tabId,
    onYes: async () => {
      try {
        const resp = await apiFetch(`/workspace/files?path=${encodeURIComponent(target)}`, { method: 'DELETE' });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          throw new Error(data && data.error ? data.error : `workspace delete failed (${resp.status})`);
        }
        appendLine(`workspace: removed ${target}`, '', tabId);
        if (typeof refreshWorkspaceFileCache === 'function') refreshWorkspaceFileCache();
        _recordSuccessfulLocalCommand(cmd);
        _persistClientSideRun(cmd, [{ text: `workspace: removed ${target}` }], 'ok');
        setStatus('ok');
      } catch (err) {
        appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', tabId);
        logClientError('workspace rm', err);
        setStatus('fail');
      }
    },
    onNo: async () => {
      appendLine('Workspace file delete canceled.', '', tabId);
      setStatus('idle');
    },
  });
  setStatus('idle');
}

async function _runClientSideCommandWithOptionalPipe(cmd, tabId, runBaseCommand) {
  const spec = _parseSyntheticPostFilterCommand(cmd);
  const baseCommand = spec ? (spec.baseCommand || cmd) : cmd;
  const capturedLines = [];
  const originalAppendLine = appendLine;
  const originalAppendCommandEcho = appendCommandEcho;
  const originalRecordSuccessfulLocalCommand = _recordSuccessfulLocalCommand;
  const originalPersistSessionTokenRun = _persistSessionTokenRun;
  const originalSetStatus = setStatus;
  let finalStatus = 'idle';

  appendCommandEcho(cmd, tabId);
  try {
    appendCommandEcho = () => {};
    _recordSuccessfulLocalCommand = () => {};
    _persistSessionTokenRun = () => {};
    setStatus = (statusValue) => {
      finalStatus = statusValue;
      originalSetStatus(statusValue);
    };
    appendLine = (text, cls = '', lineTabId = tabId) => {
      capturedLines.push({ text: String(text ?? ''), cls: String(cls || ''), tabId: lineTabId });
    };
    const result = runBaseCommand(baseCommand);
    if (!_pendingTerminalConfirm) await result;
  } finally {
    appendLine = originalAppendLine;
    appendCommandEcho = originalAppendCommandEcho;
    _recordSuccessfulLocalCommand = originalRecordSuccessfulLocalCommand;
    _persistSessionTokenRun = originalPersistSessionTokenRun;
    setStatus = originalSetStatus;
  }

  const outputLines = spec ? _applySyntheticPostFilterLines(capturedLines, spec) : capturedLines;
  outputLines.forEach((line) => {
    originalAppendLine(line.text, line.cls || '', tabId);
  });
  if (!_pendingTerminalConfirm) {
    _finalizeClientSideCommandStatus(tabId, finalStatus);
    if (finalStatus !== 'fail') _recordSuccessfulLocalCommand(cmd);
    _persistClientSideRun(cmd, outputLines, finalStatus);
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

  // Intercept yes/no answer to a pending terminal confirmation prompt.
  if (_pendingTerminalConfirm) {
    const answer = cmd.trim().toLowerCase();
    const pending = _pendingTerminalConfirm;
    const promptTabId = pending.tabId || activeTabId;
    appendCommandEcho(cmd, promptTabId);
    if (answer !== 'yes' && answer !== 'y' && answer !== 'no' && answer !== 'n') {
      appendLine('please answer yes or no', 'notice', promptTabId);
      return true;
    }
    _setPendingTerminalConfirm(null);
    if (answer === 'yes' || answer === 'y') {
      _runPendingTerminalConfirmHandler(promptTabId, pending.onYes).catch((err) => {
        appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', promptTabId);
        setStatus('fail');
        _finalizeClientSideCommandStatus(promptTabId, 'fail');
      });
    } else {
      _runPendingTerminalConfirmHandler(promptTabId, pending.onNo).catch((err) => {
        appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', promptTabId);
        setStatus('fail');
        _finalizeClientSideCommandStatus(promptTabId, 'fail');
      });
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
    const newId = createTab(typeof createDefaultTabLabel === 'function'
      ? createDefaultTabLabel()
      : 'shell ' + (tabs.length + 1));
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

  addToHistory(_historySafeCommand(cmd));

  // Session-token subcommands (generate / set / clear / rotate) run entirely
  // client-side.  The bare 'session-token' status command goes to the server.
  if (_isSessionTokenSubcommand(cmd)) {
    void _runClientSideCommandWithOptionalPipe(cmd, activeTabId, (baseCommand) => (
      _handleSessionTokenCommand(baseCommand, activeTabId)
    ));
    return true;
  }

  if (_isWorkspaceDeleteCommand(cmd)) {
    void _runClientSideCommandWithOptionalPipe(cmd, activeTabId, (baseCommand) => (
      _handleWorkspaceDeleteCommand(baseCommand, activeTabId)
    ));
    return true;
  }

  if (_isClientSideUiCommand(cmd)) {
    const root = cmd.trim().split(/\s+/, 1)[0].toLowerCase();
    if (root === 'theme' && typeof handleThemeCommand === 'function') {
      void _runClientSideCommandWithOptionalPipe(cmd, activeTabId, (baseCommand) => (
        handleThemeCommand(baseCommand, activeTabId)
      ));
      return true;
    }
    if (root === 'config' && typeof handleConfigCommand === 'function') {
      void _runClientSideCommandWithOptionalPipe(cmd, activeTabId, (baseCommand) => (
        handleConfigCommand(baseCommand, activeTabId)
      ));
      return true;
    }
    appendCommandEcho(cmd);
    appendLine(`[error] ${root} command is not ready — reload the page and try again`, 'exit-fail', activeTabId);
    setStatus('fail');
    return true;
  }

  // Re-lookup the active tab after the potential createTab() call above, which
  // may have changed activeTabId to point at the newly created tab.
  const _runTab = getActiveTab();
  if (typeof setTabRunningCommand === 'function') {
    setTabRunningCommand(activeTabId, cmd);
  } else {
    if (!_runTab || !_runTab.renamed) setTabLabel(activeTabId, cmd);
    if (_runTab) _runTab.command = cmd;
  }
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
        _recoverStalledRun(tabId);
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
                    t.unknownCommand = false;
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
                _appendStreamLine(msg.text, 'notice', tabId, msg);
              } else if (msg.type === 'clear') {
                clearTab(tabId);
                const t = getTab(tabId);
                if (t) t.syntheticClear = true;
              } else if (msg.type === 'output') {
                const t = getTab(tabId);
                if (t && typeof msg.text === 'string' && /^Unsupported fake command: /.test(msg.text)) {
                  t.unknownCommand = true;
                }
                msg.text.split('\n').forEach((line, i, arr) => {
                  if ((i < arr.length - 1 || line) && !_shouldSuppressStreamOutputLine(t, line)) {
                    _appendStreamLine(line, msg.cls || '', tabId, msg);
                  }
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
                } else {
                  appendLine(`[process exited with code ${msg.code}${dur}]`, 'exit-fail', tabId);
                  if (tabId === activeTabId) setStatus('fail');
                  setTabStatus(tabId, 'fail');
                }
                if (typeof addToRecentPreview === 'function' && t && t.command && !t.unknownCommand) {
                  addToRecentPreview(t.command);
                }
                if (t) t.syntheticClear = false;
                _maybeNotify(t ? t.command : '', msg.code, msg.elapsed ? msg.elapsed + 's' : null);
                if (typeof emitUiEvent === 'function') emitUiEvent('app:last-exit-changed', { value: msg.code });
                _setRunButtonDisabled(false); hideTabKillBtn(tabId);
                if (t && t.closing && typeof finalizeClosingTab === 'function') {
                  finalizeClosingTab(tabId);
                  if (isHistoryPanelOpen()) refreshHistoryPanel();
                  return;
                }
                if (isHistoryPanelOpen()) refreshHistoryPanel();
                if (typeof refreshWorkspaceFileCache === 'function') refreshWorkspaceFileCache();
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
