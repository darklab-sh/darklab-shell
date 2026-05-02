// ── Shared command execution + desktop input wrapper ──
// If no chunk arrives from the SSE stream for 45 seconds (> 2× the 20s server heartbeat),
// verify the backend's active-run registry before changing the tab state. Tiny heartbeat
// frames can be buffered by browsers, WSGI, proxies, or Docker networking, so "quiet stream"
// is not the same thing as "dead process".
// Keyed by tabId so multiple concurrent tabs each have their own independent timer.
const _stalledTimeouts = new Map();
const _stalledRuns = new Set();
const _runStreamStateByTabId = new Map();
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
    const runGeneration = _tabRunGeneration(tabId);
    if (!runGeneration) return;
    _isRunStillActive(runGeneration).then(active => {
      const latest = getTab(tabId);
      if (!latest || latest.killed || _tabRunGeneration(tabId) !== runGeneration) return;
      if (active) {
        _markStalledButRunning(tabId);
        _resetStalledTimeout(tabId);
        return;
      }
      _markStalledAndInactive(tabId);
    });
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
  if (t.attachMode !== 'read-only') showTabKillBtn(tabId);
}

function _activeRunIdsFromPayload(data) {
  return new Set((Array.isArray(data && data.runs) ? data.runs : [])
    .map(run => run && run.run_id)
    .filter(Boolean));
}

function _tabRunGeneration(tabId) {
  const t = getTab(tabId);
  return t && (t.runId || t.historyRunId) || '';
}

function _isRunStillActive(runId) {
  if (!runId || typeof apiFetch !== 'function') return Promise.resolve(false);
  return apiFetch('/history/active')
    .then(r => (r && r.ok !== false && typeof r.json === 'function') ? r.json() : null)
    .then(data => _activeRunIdsFromPayload(data).has(runId))
    .catch(err => {
      _logRunnerError('active run stall check failed', err);
      return false;
    });
}

function _isTabRunStillActive(tabId) {
  return _isRunStillActive(_tabRunGeneration(tabId));
}

function _markStalledButRunning(tabId) {
  const firstNotice = !_stalledRuns.has(tabId);
  _stalledRuns.add(tabId);
  if (firstNotice) {
    appendLine('[stream quiet — no output or heartbeat reached the browser for 45s]', 'notice', tabId);
    appendLine('[process is still running; Kill remains available and live output will continue here if the stream resumes]', 'notice', tabId);
  }
  if (tabId === activeTabId) {
    setStatus('running');
    syncActiveRunTimer(tabId);
  }
  setTabStatus(tabId, 'running');
  _setRunButtonDisabled(true);
  const t = getTab(tabId);
  if (!t || t.attachMode !== 'read-only') showTabKillBtn(tabId);
}

function _markStalledAndInactive(tabId) {
  const firstNotice = !_stalledRuns.has(tabId);
  _stalledRuns.add(tabId);
  if (firstNotice) {
    appendLine('[connection stalled — no stream activity arrived from the server for 45s]', 'denied', tabId);
  }
  appendLine('[process is no longer listed as active; check the history panel for the final result]', 'denied', tabId);
  if (tabId === activeTabId) setStatus('fail');
  setTabStatus(tabId, 'fail');
  stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
}

function _handleStreamEndedWithoutExit(tabId) {
  _clearStalledTimeout(tabId);
  return _isTabRunStillActive(tabId).then(active => {
    const t = getTab(tabId);
    if (!t || t.killed) return;
    if (active) {
      appendLine('[live stream detached — process is still running]', 'notice', tabId);
      appendLine('[this tab will restore the saved result automatically when the run completes]', 'notice', tabId);
      t.reconnectedRun = true;
      t.historyRunId = t.historyRunId || t.runId;
      setTabStatus(tabId, 'running');
      if (tabId === activeTabId) {
        setStatus('running');
        syncActiveRunTimer(tabId);
      }
      _setRunButtonDisabled(true);
      showTabKillBtn(tabId);
      startPollingActiveRunsAfterReload();
      return;
    }
    stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
  });
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
    '[restored available output; live output will continue here]',
  ];
}

function _shouldAutoRestoreActiveRun(run) {
  if (!run || typeof run !== 'object') return false;
  if (run.owned_by_this_client) return true;
  if (run.owner_stale) return true;
  return !run.has_live_owner;
}

function _startedAtLabel(started) {
  const startedAt = new Date(started);
  return Number.isNaN(startedAt.getTime())
    ? 'unknown start time'
    : startedAt.toLocaleString();
}

function restoreActiveRunsAfterReload(runs) {
  const items = (Array.isArray(runs) ? runs : []).filter(_shouldAutoRestoreActiveRun);
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
    t.lastEventId = '';
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
    _subscribeRunStream(run.run_id, tabId, { after: run.last_event_id || '' });
  });

  if (firstRestoredTabId) activateTab(firstRestoredTabId);
  syncActiveRunTimer(activeTabId);
  return true;
}

function _attachActiveRunToTab(run, tabId, { mode = 'owner' } = {}) {
  if (!run || !tabId) return false;
  clearTab(tabId);
  const t = getTab(tabId);
  if (!t) return false;
  if (typeof setTabRunningCommand === 'function') {
    setTabRunningCommand(tabId, run.command);
  } else {
    if (!t.renamed) setTabLabel(tabId, run.command);
    t.command = run.command;
  }
  t.runId = run.run_id;
  t.historyRunId = run.run_id;
  t.lastEventId = '';
  t.attachMode = mode;
  t.reconnectedRun = mode !== 'read-only';
  t.killed = false;
  t.pendingKill = false;
  t.previewTruncated = false;
  t.fullOutputAvailable = false;
  t.fullOutputLoaded = false;
  t.runStart = Number.isNaN(Date.parse(run.started)) ? Date.now() : Date.parse(run.started);
  t.currentRunStartIndex = 0;
  t.followOutput = true;
  appendCommandEcho(run.command, tabId);
  const startedLabel = _startedAtLabel(run.started);
  appendLine(
    mode === 'read-only'
      ? `[attached read-only to active run started at ${startedLabel}]`
      : `[attached to active run started at ${startedLabel}]`,
    'notice',
    tabId,
  );
  appendLine('[restored available output; live output will continue here]', 'notice', tabId);
  setTabStatus(tabId, 'running');
  if (tabId === activeTabId) {
    setStatus('running');
    syncActiveRunTimer(tabId);
  }
  if (mode === 'read-only') hideTabKillBtn(tabId);
  else showTabKillBtn(tabId);
  _setRunButtonDisabled(true);
  _subscribeRunStream(run.run_id, tabId, { after: run.last_event_id || '' });
  return true;
}

function attachActiveRunFromMonitor(run, { takeover = false } = {}) {
  if (!run || !run.run_id) return Promise.resolve(false);
  const tabId = createTab();
  if (!tabId) return Promise.resolve(false);
  activateTab(tabId, { focusComposer: false });

  const attach = () => _attachActiveRunToTab(run, tabId, { mode: takeover ? 'owner' : 'read-only' });
  if (!takeover) return Promise.resolve(attach());

  return apiFetch(`/runs/${encodeURIComponent(run.run_id)}/owner`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tab_id: tabId }),
  }).then(resp => {
    if (!resp.ok) {
      return _readRunErrorMessage(resp).then(message => {
        appendLine(`[server error] ${message || 'Could not take over this run.'}`, 'exit-fail', tabId);
        setTabStatus(tabId, 'fail');
        if (tabId === activeTabId) setStatus('fail');
        return false;
      });
    }
    return attach();
  }).catch(err => {
    appendLine(`[network error] ${_describeRunnerFetchError(err, 'server')}`, 'exit-fail', tabId);
    setTabStatus(tabId, 'fail');
    if (tabId === activeTabId) setStatus('fail');
    return false;
  });
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

function _markReconnectedRunUnavailable(tab) {
  if (!tab) return;
  appendLine('[reconnected run is no longer active]', 'denied', tab.id);
  appendLine('[no saved result is available; the app may have restarted while the command was running]', 'denied', tab.id);
  setTabStatus(tab.id, 'fail');
  const refreshed = getTab(tab.id);
  if (refreshed) {
    refreshed.reconnectedRun = false;
    refreshed.runId = null;
  }
  if (tab.id === activeTabId) {
    setStatus('fail');
    stopTimer();
  }
  _setRunButtonDisabled(false);
  hideTabKillBtn(tab.id);
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
          .catch(() => _markReconnectedRunUnavailable(tab));
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

function _handleKillRequestDenied(message, tabId, runId) {
  const t = getTab(tabId);
  if (t) {
    t.runId = runId || t.runId;
    t.killed = false;
    t.pendingKill = false;
    t.attachMode = 'read-only';
    setTabStatus(tabId, 'running');
    hideTabKillBtn(tabId);
  }
  appendLine(`[kill request denied] ${message || 'This browser no longer controls that run.'}`, 'notice', tabId);
  if (tabId === activeTabId) {
    setStatus('running');
    _setRunButtonDisabled(true);
  }
}

function _currentClientId() {
  return typeof CLIENT_ID !== 'undefined' ? String(CLIENT_ID || '') : '';
}

function _handleRunOwnerChanged(msg, tabId) {
  const t = getTab(tabId);
  if (!t) return;
  const ownerClientId = String(msg.owner_client_id || '');
  const ownedByThisClient = !!(ownerClientId && ownerClientId === _currentClientId());
  if (ownedByThisClient) {
    t.attachMode = 'owner';
    if (t.st === 'running') showTabKillBtn(tabId);
    appendLine('[this browser now controls this run]', 'notice', tabId);
    return;
  }
  if (t.attachMode !== 'read-only') {
    appendLine('Run ownership moved to another browser. This tab is now read-only.', 'notice', tabId);
  }
  t.attachMode = 'read-only';
  t.killed = false;
  t.pendingKill = false;
  hideTabKillBtn(tabId);
}

function _markTabKilledByUser(tabId, secs, { suppressTranscript = false } = {}) {
  const t = getTab(tabId);
  if (!t) return;
  t.killed = true;
  t.reconnectedRun = false;
  t.lastEventId = '';
  t.attachMode = '';
  stopTimer();
  if (!t.closing && !suppressTranscript) {
    appendLine(`[killed by user${secs != null ? ' after ' + _formatElapsed(secs) : ''}]`, 'exit-fail', tabId);
  }
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
    _logRunnerError('failed to parse run error response', err);
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

function _brokerStreamUrl(runId, tabId, streamUrl = '', afterId = '') {
  const base = streamUrl || `/runs/${encodeURIComponent(runId)}/stream`;
  const params = [];
  if (tabId) params.push(`tab_id=${encodeURIComponent(tabId)}`);
  if (afterId) params.push(`after=${encodeURIComponent(afterId)}`);
  if (!params.length) return base;
  const separator = base.includes('?') ? '&' : '?';
  return `${base}${separator}${params.join('&')}`;
}

function _sseMessageFromChunk(part) {
  let eventId = '';
  const dataLines = [];
  String(part || '').split(/\r?\n/).forEach(line => {
    if (line.startsWith('id: ')) eventId = line.slice(4).trim();
    else if (line.startsWith('data: ')) dataLines.push(line.slice(6));
  });
  if (!dataLines.length) return null;
  const msg = JSON.parse(dataLines.join('\n'));
  if (eventId && msg && typeof msg === 'object' && !msg.event_id) msg.event_id = eventId;
  return msg;
}

function _markTabRunStarted(tabId, runId) {
  const t = getTab(tabId);
  if (!t || !runId) return;
  const sameRun = t.runId === runId || t.historyRunId === runId;
  t.runId = runId;
  t.historyRunId = runId;
  if (!sameRun) t.lastEventId = '';
  t.unknownCommand = false;
  t.reconnectedRun = false;
  if (t.pendingKill) {
    // Kill was requested before runId was available — send it now.
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

function _handleRunStreamMessage(msg, tabId) {
  if (!msg || typeof msg !== 'object') return;
  const t = getTab(tabId);
  if (t && msg.event_id) t.lastEventId = String(msg.event_id || '');
  if (msg.type === 'started') {
    _markTabRunStarted(tabId, msg.run_id);
  } else if (msg.type === 'notice') {
    _appendStreamLine(msg.text, 'notice', tabId, msg);
  } else if (msg.type === 'owner') {
    _handleRunOwnerChanged(msg, tabId);
  } else if (msg.type === 'clear') {
    clearTab(tabId);
    const t = getTab(tabId);
    if (t) t.syntheticClear = true;
  } else if (msg.type === 'output') {
    const t = getTab(tabId);
    if (t && typeof msg.text === 'string' && /^Unsupported fake command: /.test(msg.text)) {
      t.unknownCommand = true;
    }
    String(msg.text || '').split('\n').forEach((line, i, arr) => {
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
      t.lastEventId = '';
      t.attachMode = '';
      t.deferPromptMount = true;
      t.previewTruncated = !!msg.preview_truncated;
      t.fullOutputAvailable = !!msg.full_output_available;
      t.fullOutputLoaded = !msg.preview_truncated;
    }
    // If already killed by user, ignore the subsequent -15 exit code.
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
    if (t && /^var(?:\s|$)/i.test(String(t.command || '')) && typeof loadSessionVariables === 'function') {
      loadSessionVariables().catch(() => {});
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
}

function _sameTabRunStillActive(tabId, runId) {
  const t = getTab(tabId);
  return !!(
    t
    && t.st === 'running'
    && runId
    && (t.runId === runId || t.historyRunId === runId)
  );
}

function _streamResumeAfterId(tabId, state) {
  const t = getTab(tabId);
  return String((t && t.lastEventId) || (state && state.after) || '');
}

function _finishPausedRunStream(tabId, state) {
  const current = _runStreamStateByTabId.get(tabId);
  if (current !== state) return true;
  state.reader = null;
  state.starting = false;
  if (state.detached) {
    _runStreamStateByTabId.delete(tabId);
    return true;
  }
  if (!state.pausedForApi) return false;
  if (state.resumeAfterPause) {
    const runId = state.runId;
    const streamUrl = state.streamUrl || '';
    const after = _streamResumeAfterId(tabId, state);
    _runStreamStateByTabId.delete(tabId);
    if (_sameTabRunStillActive(tabId, runId)) {
      _subscribeRunStream(runId, tabId, { streamUrl, after });
    }
    return true;
  }
  return true;
}

function detachRunStreamForTab(tabId) {
  const state = _runStreamStateByTabId.get(tabId);
  if (!state) return false;
  state.detached = true;
  state.pausedForApi = false;
  state.resumeAfterPause = false;
  const reader = state.reader;
  state.reader = null;
  _runStreamStateByTabId.delete(tabId);
  _clearStalledTimeout(tabId);
  if (reader && typeof reader.cancel === 'function') {
    try {
      const cancelled = reader.cancel();
      if (cancelled && typeof cancelled.catch === 'function') cancelled.catch(() => {});
    } catch (_) {}
  }
  return true;
}

function pauseBackgroundRunStreamsForStatusMonitor() {
  const keepTabId = activeTabId;
  let paused = 0;
  _runStreamStateByTabId.forEach((state, tabId) => {
    if (!state || tabId === keepTabId || state.pausedForApi || state.detached) return;
    if (!_sameTabRunStillActive(tabId, state.runId)) {
      detachRunStreamForTab(tabId);
      return;
    }
    state.pausedForApi = true;
    state.resumeAfterPause = false;
    paused += 1;
    _clearStalledTimeout(tabId);
    const reader = state.reader;
    state.reader = null;
    state.starting = false;
    if (reader && typeof reader.cancel === 'function') {
      try {
        const cancelled = reader.cancel();
        if (cancelled && typeof cancelled.catch === 'function') cancelled.catch(() => {});
      } catch (_) {}
    }
  });
  return paused;
}

function resumeBackgroundRunStreamsAfterStatusMonitor() {
  _runStreamStateByTabId.forEach((state, tabId) => {
    if (!state || !state.pausedForApi || state.detached) return;
    if (state.reader) {
      state.resumeAfterPause = true;
      return;
    }
    const runId = state.runId;
    const streamUrl = state.streamUrl || '';
    const after = _streamResumeAfterId(tabId, state);
    _runStreamStateByTabId.delete(tabId);
    if (_sameTabRunStillActive(tabId, runId)) {
      _subscribeRunStream(runId, tabId, { streamUrl, after });
    }
  });
}

function _streamRunResponse(res, tabId, state = null) {
  if (!res.body || typeof res.body.getReader !== 'function') {
    appendLine('[server error] The server returned an invalid streaming response.', 'exit-fail', tabId);
    setStatus('fail'); setTabStatus(tabId, 'fail');
    stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const streamState = state || _runStreamStateByTabId.get(tabId) || {};
  streamState.reader = reader;
  streamState.starting = false;
  streamState.runId = streamState.runId || _tabRunGeneration(tabId);
  _runStreamStateByTabId.set(tabId, streamState);
  if (streamState.pausedForApi && !streamState.resumeAfterPause) {
    streamState.reader = null;
    try {
      const cancelled = reader.cancel();
      if (cancelled && typeof cancelled.catch === 'function') cancelled.catch(() => {});
    } catch (_) {}
    return;
  }
  let buffer = '';

  _resetStalledTimeout(tabId);

  function read() {
    reader.read().then(({ done, value }) => {
      if (done) {
        if (_finishPausedRunStream(tabId, streamState)) return;
        _runStreamStateByTabId.delete(tabId);
        _handleStreamEndedWithoutExit(tabId);
        return;
      }
      _recoverStalledRun(tabId);
      _resetStalledTimeout(tabId);
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop();
      parts.forEach(part => {
        try {
          const msg = _sseMessageFromChunk(part);
          if (msg) _handleRunStreamMessage(msg, tabId);
        } catch(e) {}
      });
      read();
    }).catch(err => {
      if (_finishPausedRunStream(tabId, streamState)) return;
      _runStreamStateByTabId.delete(tabId);
      appendLine(`[network error] ${_describeRunnerFetchError(err, 'server')}`, 'exit-fail', tabId);
      if (tabId === activeTabId) setStatus('fail');
      setTabStatus(tabId, 'fail');
      stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
    });
  }
  read();
}

function _subscribeRunStream(runId, tabId, { streamUrl = '', after = '' } = {}) {
  if (!runId || !tabId || typeof apiFetch !== 'function') return Promise.resolve(false);
  const existing = _runStreamStateByTabId.get(tabId);
  if (existing && (existing.reader || existing.starting) && !existing.pausedForApi && !existing.detached) {
    return Promise.resolve(true);
  }
  const streamState = {
    runId,
    tabId,
    streamUrl,
    after,
    reader: null,
    starting: true,
    pausedForApi: false,
    resumeAfterPause: false,
    detached: false,
  };
  _runStreamStateByTabId.set(tabId, streamState);
  return apiFetch(_brokerStreamUrl(runId, tabId, streamUrl, after))
    .then(streamRes => {
      if (streamState.detached) return false;
      if (!streamRes.ok) {
        _runStreamStateByTabId.delete(tabId);
        return _readRunErrorMessage(streamRes).then(message => {
          const suffix = message ? ` ${message}` : '';
          appendLine(`[server error] The server could not stream the command.${suffix}`, 'exit-fail', tabId);
          if (tabId === activeTabId) setStatus('fail');
          setTabStatus(tabId, 'fail');
          stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
          return false;
        });
      }
      _streamRunResponse(streamRes, tabId, streamState);
      return true;
    })
    .catch(err => {
      if (streamState.detached) return false;
      _runStreamStateByTabId.delete(tabId);
      appendLine(`[network error] ${_describeRunnerFetchError(err, 'server')}`, 'exit-fail', tabId);
      if (tabId === activeTabId) setStatus('fail');
      setTabStatus(tabId, 'fail');
      stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
      return false;
    });
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
      { id: 'confirm', label: '■ Kill', role: 'destructive' },
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
  if (t.attachMode === 'read-only') {
    appendLine('[read-only attach — take over the run before killing it]', 'notice', tabId);
    return;
  }
  const secs = elapsedSeconds();
  const suppressKilledTranscript = !!t.closing;
  if (t.runId) {
    // runId already available — send kill immediately
    const runId = t.runId;
    apiFetch('/kill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: runId })
    }).then(resp => {
      if (!resp) {
        _handleKillRequestFailure(new Error('Kill request failed'), tabId);
        return false;
      }
      if (!resp.ok) {
        return _readRunErrorMessage(resp).then(message => {
          if (resp && resp.status === 403) _handleKillRequestDenied(message, tabId, runId);
          else _handleKillRequestFailure(new Error(message || 'Kill request failed'), tabId);
          return false;
        });
      }
      const current = getTab(tabId);
      if (current) current.runId = null;
      _markTabKilledByUser(tabId, secs, { suppressTranscript: suppressKilledTranscript });
      return true;
    }).catch(err => _handleKillRequestFailure(err, tabId));
  } else {
    // runId not yet available (SSE 'started' hasn't arrived) — flag it so the
    // started handler sends the kill request as soon as the run_id is known
    t.pendingKill = true;
    _markTabKilledByUser(tabId, secs, { suppressTranscript: suppressKilledTranscript });
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

function _workspaceDeleteCommand(cmd) {
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  const fileAction = (parts[1] || 'delete').toLowerCase();
  const usage = root === 'file'
    ? `Usage: file ${fileAction} [-r|-f|-rf] <file-or-folder>`
    : 'Usage: rm [-r|-f|-rf] <file-or-folder>';
  const start = root === 'file' ? 2 : 1;
  if (root === 'file' && !['rm', 'delete'].includes((parts[1] || '').toLowerCase())) return null;
  if (root !== 'rm' && root !== 'file') return null;
  const args = parts.slice(start);
  const flags = [];
  const targets = [];
  args.forEach((part) => {
    if (/^-[rf]+$/.test(part)) flags.push(part);
    else if (String(part || '').startsWith('-')) targets.push(part);
    else targets.push(part);
  });
  const recursive = flags.some(flag => flag.includes('r'));
  const force = flags.some(flag => flag.includes('f'));
  const invalid = targets.length !== 1 || args.some(part => String(part || '').startsWith('-') && !/^-[rf]+$/.test(part));
  return {
    target: invalid ? '' : targets[0],
    recursive,
    force,
    usage,
    invalid,
  };
}

function _workspaceDeleteTarget(cmd) {
  const parsed = _workspaceDeleteCommand(cmd);
  return parsed && !parsed.invalid ? parsed.target : '';
}

function _workspaceListCommand(parts) {
  const root = (parts[0] || '').toLowerCase();
  const parseListArgs = (args, usage) => {
    let long = false;
    let recursive = false;
    const targets = [];
    let invalid = false;
    args.forEach((part) => {
      const value = String(part || '');
      if (/^-[lR]+$/.test(value)) {
        if (value.includes('l')) long = true;
        if (value.includes('R')) recursive = true;
      } else if (value.startsWith('-')) {
        invalid = true;
      } else {
        targets.push(part);
      }
    });
    if (targets.length > 1) invalid = true;
    return {
      target: targets[0] || '',
      long,
      recursive,
      usage,
      invalid,
    };
  };
  if (root === 'll') {
    const parsed = parseListArgs(parts.slice(1), 'Usage: ll [-R] [folder]');
    parsed.long = true;
    return parsed;
  }
  const usage = root === 'file' ? 'Usage: file list [-lR] [folder]' : 'Usage: ls [-lR] [folder]';
  const start = root === 'file' ? 2 : 1;
  if (root === 'file' && !['list', 'ls'].includes((parts[1] || '').toLowerCase())) return null;
  return parseListArgs(parts.slice(start), usage);
}

function _workspaceListTarget(parts) {
  const parsed = _workspaceListCommand(parts);
  if (parsed && !parsed.invalid) {
    return parsed.target;
  }
  return '';
}

function _workspaceEditorCommand(cmd) {
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  const action = (parts[1] || '').toLowerCase();
  if (root !== 'file' || !['add', 'edit'].includes(action)) return null;
  return { action, target: parts.length === 3 ? parts[2] : '', invalid: parts.length > 3 };
}

function _workspaceDownloadTarget(cmd) {
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  const action = (parts[1] || '').toLowerCase();
  if (root === 'file' && action === 'download' && parts.length === 3) return parts[2];
  return '';
}

function _workspaceCommandTokens(cmd) {
  const tokens = [];
  const re = /"[^"]*"|'[^']*'|\S+/g;
  let match = re.exec(String(cmd || '').trim());
  while (match) {
    let token = match[0];
    if (token.length >= 2 && ((token[0] === '"' && token[token.length - 1] === '"') || (token[0] === "'" && token[token.length - 1] === "'"))) {
      token = token.slice(1, -1);
    }
    tokens.push(token);
    match = re.exec(String(cmd || '').trim());
  }
  return tokens;
}

function _workspaceCwd(tabId = activeTabId) {
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  return _normalizeWorkspaceTerminalPath(tab && tab.workspaceCwd || '');
}

function _setWorkspaceCwd(tabId, path = '') {
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  const normalized = _normalizeWorkspaceTerminalPath(path);
  if (tab) tab.workspaceCwd = normalized;
  if (typeof _applyComposerPromptMode === 'function') _applyComposerPromptMode();
  if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
  return normalized;
}

function _workspaceDisplayPath(path = '') {
  if (typeof workspaceDisplayPath === 'function') return workspaceDisplayPath(_normalizeWorkspaceTerminalPath(path));
  const normalized = _normalizeWorkspaceTerminalPath(path);
  return normalized ? `/${normalized}` : '/';
}

function _normalizeWorkspaceTerminalPath(path = '') {
  const parts = String(path || '').split('/').map(part => String(part || '').trim()).filter(Boolean);
  return parts.join('/');
}

function _resolveWorkspaceCommandPath(rawPath = '', { cwd = _workspaceCwd(), defaultToCwd = false } = {}) {
  const text = String(rawPath ?? '').trim();
  const normalizedCwd = _normalizeWorkspaceTerminalPath(cwd);
  if (!text && defaultToCwd) return normalizedCwd;
  if (typeof normalizeWorkspaceCommandPath === 'function') {
    return _normalizeWorkspaceTerminalPath(normalizeWorkspaceCommandPath(text || '.', normalizedCwd));
  }
  const base = text.startsWith('/') ? [] : normalizedCwd.split('/').filter(Boolean);
  const parts = String(text || '.').split('/').filter(Boolean);
  for (const part of parts) {
    if (part === '.') continue;
    if (part === '..') {
      if (!base.length) throw new Error('path escapes the session workspace');
      base.pop();
    } else {
      base.push(part);
    }
  }
  return base.join('/');
}

function _workspacePathExists(path = '', kind = 'any') {
  const target = String(path || '').split('/').filter(Boolean).join('/');
  if (!target) return kind === 'directory' || kind === 'any';
  if (kind === 'directory' || kind === 'any') {
    const dirHints = typeof getWorkspaceAutocompleteDirectoryHints === 'function'
      ? getWorkspaceAutocompleteDirectoryHints()
      : [];
    if (dirHints.some(item => String(item && item.value || '') === target)) return true;
  }
  if (kind === 'file' || kind === 'any') {
    const fileHints = typeof getWorkspaceAutocompleteFileHints === 'function'
      ? getWorkspaceAutocompleteFileHints()
      : [];
    if (fileHints.some(item => String(item && item.value || '') === target)) return true;
  }
  return false;
}

function _resolveExistingWorkspaceCommandPath(rawPath = '', { cwd = _workspaceCwd(), kind = 'any', defaultToCwd = false } = {}) {
  const text = String(rawPath ?? '').trim();
  const target = _resolveWorkspaceCommandPath(text, { cwd, defaultToCwd });
  if (_workspacePathExists(target, kind)) return target;
  const normalizedRaw = String(text || '').split('/').filter(Boolean).join('/');
  if (text && !text.startsWith('/') && normalizedRaw && normalizedRaw !== target && _workspacePathExists(normalizedRaw, kind)) {
    return normalizedRaw;
  }
  return target;
}

async function _ensureWorkspaceCache() {
  if (typeof refreshWorkspaceFileCache === 'function') {
    await refreshWorkspaceFileCache();
  }
}

function _isWorkspaceDeleteCommand(cmd) {
  if (!(typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.workspace_enabled === true)) {
    return false;
  }
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  const action = (parts[1] || '').toLowerCase();
  return root === 'rm' || (root === 'file' && ['rm', 'delete'].includes(action));
}

function _isWorkspaceEditorCommand(cmd) {
  if (!(typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.workspace_enabled === true)) {
    return false;
  }
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  const action = (parts[1] || '').toLowerCase();
  return root === 'file' && ['add', 'edit'].includes(action);
}

function _isWorkspaceDownloadCommand(cmd) {
  if (!(typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.workspace_enabled === true)) {
    return false;
  }
  const parts = String(cmd || '').trim().split(/\s+/).filter(Boolean);
  return (parts[0] || '').toLowerCase() === 'file' && (parts[1] || '').toLowerCase() === 'download';
}

function _isWorkspaceTerminalCommand(cmd) {
  if (!(typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.workspace_enabled === true)) return false;
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  if (['cd', 'pwd', 'ls', 'll', 'cat', 'mkdir', 'grep', 'head', 'tail', 'wc', 'sort', 'uniq'].includes(root)) return true;
  if (root === 'file' && ['list', 'ls', 'show', 'add-dir', 'mkdir'].includes((parts[1] || '').toLowerCase())) return true;
  return false;
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
    tab.lastEventId = '';
    tab.attachMode = '';
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

function _sessionMigrationCountLabel(runCount = 0, workspaceFileCount = 0, workflowCount = 0) {
  const parts = [];
  if (runCount > 0) parts.push(`${runCount} run(s)`);
  if (workspaceFileCount > 0) parts.push(`${workspaceFileCount} workspace file(s)`);
  if (workflowCount > 0) parts.push(`${workflowCount} workflow(s)`);
  if (!parts.length) return 'no runs, workspace files, or workflows';
  if (parts.length === 1) return parts[0];
  return `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`;
}

function _sessionMigrationResultText(data = {}) {
  const workspaceFiles = Number(data.migrated_workspace_files || 0);
  const skippedWorkspaceFiles = Number(data.skipped_workspace_files || 0);
  const workspaceDirs = Number(data.migrated_workspace_directories || 0);
  const skippedWorkspaceDirs = Number(data.skipped_workspace_directories || 0);
  const workspaceParts = [
    `${workspaceFiles} workspace file(s)`,
  ];
  if (workspaceDirs > 0) workspaceParts.push(`${workspaceDirs} folder(s)`);
  if (skippedWorkspaceFiles > 0) workspaceParts.push(`${skippedWorkspaceFiles} workspace file(s) skipped`);
  if (skippedWorkspaceDirs > 0) workspaceParts.push(`${skippedWorkspaceDirs} folder(s) skipped`);
  return `migrated — ${data.migrated_runs} run(s), ${data.migrated_snapshots} snapshot(s), `
    + `${data.migrated_stars ?? 0} starred command(s), ${data.migrated_workflows ?? 0} workflow(s), `
    + `${workspaceParts.join(', ')}, `
    + 'and saved user options when the destination had none';
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
      appendLine(_sessionMigrationResultText(data), '', tabId);
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
  if (pending.kind === 'text') {
    Promise.resolve(typeof cancelHandler === 'function' ? cancelHandler() : undefined).catch((err) => {
      appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', promptTabId);
      setStatus('fail');
    });
    refocusComposerAfterAction();
    return true;
  }
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
  if (typeof refreshWorkspaceFiles === 'function') refreshWorkspaceFiles().catch(() => {});
  else if (typeof refreshWorkspaceFileCache === 'function') refreshWorkspaceFileCache().catch(() => {});
  if (typeof reloadWorkflowCatalog === 'function') reloadWorkflowCatalog().catch(() => {});
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

    // Check run/workspace counts on old session before switching identity.
    let runCount = 0;
    let workspaceFileCount = 0;
    let workflowCount = 0;
    try {
      const countResp = await apiFetch('/session/run-count');
      if (countResp.ok) {
        const countData = await countResp.json();
        runCount = countData.count || 0;
        workspaceFileCount = countData.workspace_files || 0;
        workflowCount = countData.workflow_count || 0;
      }
    } catch (_) {}

    appendLine(`session token generated:  ${maskSessionToken(newToken)}`, '', tabId);
    appendLine('stored in localStorage as session_token', '', tabId);
    appendLine('use session-token set <value> on another device to continue your session', '', tabId);
    appendLine('warning: your session token grants full access to your session history — treat it like a password', 'notice', tabId);

    if (runCount > 0 || workspaceFileCount > 0 || workflowCount > 0) {
      // Defer identity switch until the user answers the migration prompt so a
      // failed /session/migrate does not strand runs on the old session while
      // the active identity is already the new token.
      appendLine(
        `you have ${_sessionMigrationCountLabel(runCount, workspaceFileCount, workflowCount)} in your previous session. migrate history, files, and workflows to your new session token?`,
        '',
        tabId
      );
      _setPendingTerminalConfirm({
        tabId,
        onYes: async () => {
          const migrated = await _doSessionMigration(oldSessionId, newToken, tabId);
          if (migrated) {
            localStorage.setItem('session_token', newToken);
            updateSessionId(newToken);
            await _seedLocalStorageStarsToServer();
            if (typeof reloadSessionHistory === 'function') await reloadSessionHistory().catch(() => {});
            if (typeof reloadWorkflowCatalog === 'function') reloadWorkflowCatalog().catch(() => {});
            _recordSuccessfulLocalCommand('session-token generate');
            _persistSessionTokenRun('session-token generate', [
              { text: `session token generated:  ${maskSessionToken(newToken)}` },
              { text: 'history and files migrated to the new session token' },
            ]);
          }
          setStatus('idle');
        },
        onNo: async () => {
          localStorage.setItem('session_token', newToken);
          updateSessionId(newToken);
          await _seedLocalStorageStarsToServer();
          if (typeof reloadSessionHistory === 'function') await reloadSessionHistory().catch(() => {});
          if (typeof reloadWorkflowCatalog === 'function') reloadWorkflowCatalog().catch(() => {});
          _recordSuccessfulLocalCommand('session-token generate');
          appendLine('History and file migration skipped.', '', tabId);
          _persistSessionTokenRun('session-token generate', [
            { text: `session token generated:  ${maskSessionToken(newToken)}` },
            { text: 'History and file migration skipped.' },
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

  // Check current session's run/workspace counts before switching identity.
  let runCount = 0;
  let workspaceFileCount = 0;
  let workflowCount = 0;
  try {
    const countResp = await apiFetch('/session/run-count');
    if (countResp.ok) {
      const countData = await countResp.json();
      runCount = countData.count || 0;
      workspaceFileCount = countData.workspace_files || 0;
      workflowCount = countData.workflow_count || 0;
    }
  } catch (_) {}

  if (runCount > 0 || workspaceFileCount > 0 || workflowCount > 0) {
    // Defer identity switch until the user answers the migration prompt so a
    // failed /session/migrate does not strand runs on the old session while
    // the active identity is already the new token.
    appendLine(
      `you have ${_sessionMigrationCountLabel(runCount, workspaceFileCount, workflowCount)} in your current session. migrate history, files, and workflows to this session token?`,
      '',
      tabId
    );
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
        appendLine('History and file migration skipped.', '', tabId);
        _persistSessionTokenRun(`session-token set ${value}`, [
          { text: `session token set: ${maskSessionToken(value)}` },
          { text: 'reload other tabs to apply the new session token' },
          { text: 'History and file migration skipped.' },
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
      if (typeof reloadWorkflowCatalog === 'function') reloadWorkflowCatalog().catch(() => {});
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
    if (typeof refreshWorkspaceFiles === 'function') refreshWorkspaceFiles().catch(() => {});
    else if (typeof refreshWorkspaceFileCache === 'function') refreshWorkspaceFileCache().catch(() => {});
    if (typeof reloadWorkflowCatalog === 'function') reloadWorkflowCatalog().catch(() => {});

    appendLine(`session token rotated: ${maskSessionToken(newToken)}`, '', tabId);
    appendLine(_sessionMigrationResultText(migrateData), '', tabId);
    appendLine('old session token is now inactive — reload other tabs to use the new token', '', tabId);
    _recordSuccessfulLocalCommand('session-token rotate');
    _persistSessionTokenRun('session-token rotate', [
      { text: `session token rotated: ${maskSessionToken(newToken)}` },
      { text: _sessionMigrationResultText(migrateData) },
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
  appendLine(`revoke session token ${maskSessionToken(token)}?`, '', tabId);
  appendLine(
    "warning: this token's history and workspace files will not be recoverable from the app after revocation.",
    'warning',
    tabId
  );
  _setPendingTerminalConfirm({
    tabId,
    onYes: async () => {
      await _sessionTokenRevokeConfirmed(token, tabId);
    },
    onNo: async () => {
      appendLine('Session token revoke canceled.', '', tabId);
      setStatus('idle');
    },
    onCancel: async () => {
      appendLine('Session token revoke canceled.', '', tabId);
      setStatus('idle');
    },
  });
  setStatus('idle');
}

async function _sessionTokenRevokeConfirmed(token, tabId) {
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

function _workspacePlainLine(text = '') {
  return { text: String(text), cls: '' };
}

function _workspaceSplitLines(text = '') {
  const raw = String(text ?? '');
  if (!raw) return [];
  const lines = raw.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
  if (lines.length && lines[lines.length - 1] === '') lines.pop();
  return lines.map(line => _workspacePlainLine(line));
}

function _workspaceFileDescription(file) {
  const size = typeof _formatWorkspaceBytes === 'function'
    ? _formatWorkspaceBytes(file && file.size)
    : `${Number(file && file.size) || 0} B`;
  return `${String(file && file.name || file && file.path || '')}${file && file.mtime ? `\t${size}\t${file.mtime}` : `\t${size}`}`;
}

function _workspaceListLines(entries, target = '') {
  const rows = [];
  if (target) rows.push({ name: '../', type: 'dir', size: '-', modified: '' });
  (entries.folders || []).forEach(folder => {
    rows.push({
      name: `${String(folder && folder.name || folder && folder.path || '').replace(/\/+$/, '')}/`,
      type: 'dir',
      size: '-',
      modified: folder && folder.mtime ? String(folder.mtime) : '',
    });
  });
  (entries.files || []).forEach(file => {
    rows.push({
      name: String(file && file.name || file && file.path || ''),
      type: 'file',
      size: typeof _formatWorkspaceBytes === 'function'
        ? _formatWorkspaceBytes(file && file.size)
        : `${Number(file && file.size) || 0} B`,
      modified: file && file.mtime ? String(file.mtime) : '',
    });
  });
  if (!rows.length) return [_workspacePlainLine('(empty)')];
  const widths = {
    name: Math.max(...rows.map(row => row.name.length), 4),
    type: Math.max(...rows.map(row => row.type.length), 4),
    size: Math.max(...rows.map(row => row.size.length), 4),
  };
  return rows.map(row => _workspacePlainLine([
    row.name.padEnd(widths.name),
    row.type.padEnd(widths.type),
    row.size.padEnd(widths.size),
    row.modified,
  ].filter((part, index) => index < 3 || part).join('  ').trimEnd()));
}

function _workspaceShortListLines(entries) {
  const names = [];
  (entries.folders || []).forEach(folder => {
    const name = String(folder && folder.name || folder && folder.path || '').replace(/\/+$/, '');
    if (name) names.push(`${name}/`);
  });
  (entries.files || []).forEach(file => {
    const name = String(file && file.name || file && file.path || '');
    if (name) names.push(name);
  });
  if (!names.length) return [_workspacePlainLine('(empty)')];
  return [_workspacePlainLine(names.join(' '))];
}

function _workspaceListNames(entries) {
  const names = [];
  (entries.folders || []).forEach(folder => {
    const name = String(folder && folder.name || folder && folder.path || '').replace(/\/+$/, '');
    if (name) names.push(`${name}/`);
  });
  (entries.files || []).forEach(file => {
    const name = String(file && file.name || file && file.path || '');
    if (name) names.push(name);
  });
  return names;
}

function _workspaceRelativeListName(path = '', base = '', isDirectory = false) {
  const normalized = String(path || '').split('/').filter(Boolean).join('/');
  const normalizedBase = String(base || '').split('/').filter(Boolean).join('/');
  let relative = normalized;
  if (normalizedBase && normalized.startsWith(`${normalizedBase}/`)) {
    relative = normalized.slice(normalizedBase.length + 1);
  }
  relative = relative.split('/').filter(Boolean).join('/');
  if (!relative) return '';
  return isDirectory ? `${relative.replace(/\/+$/, '')}/` : relative;
}

function _workspaceDirectListEntries(entries, base = '') {
  const normalizedBase = String(base || '').split('/').filter(Boolean).join('/');
  const directFolders = new Map();
  const directFiles = [];
  const addDirectFolder = (path, fallbackName = '') => {
    const relative = _workspaceRelativeListName(path, normalizedBase, false)
      || String(fallbackName || '').replace(/\/+$/, '');
    const parts = relative.split('/').filter(Boolean);
    if (parts.length !== 1) return;
    const name = parts[0];
    const folderPath = normalizedBase ? `${normalizedBase}/${name}` : name;
    directFolders.set(folderPath, { name, path: folderPath });
  };
  (entries.folders || []).forEach(folder => {
    addDirectFolder(folder && folder.path, folder && folder.name);
  });
  (entries.files || []).forEach(file => {
    const path = String(file && file.path || '').split('/').filter(Boolean).join('/');
    const relative = _workspaceRelativeListName(path, normalizedBase, false);
    const parts = relative.split('/').filter(Boolean);
    if (parts.length > 1) {
      addDirectFolder(normalizedBase ? `${normalizedBase}/${parts[0]}` : parts[0], parts[0]);
    } else if (parts.length === 1) {
      directFiles.push({ ...file, path, name: parts[0] });
    }
  });
  return {
    folders: [...directFolders.values()].sort((a, b) => a.name.localeCompare(b.name)),
    files: directFiles.sort((a, b) => String(a.name || '').localeCompare(String(b.name || ''))),
  };
}

function _workspaceRecursiveEntries(base = '') {
  const folders = [];
  const files = [];
  const seenFolders = new Set();
  const queue = [String(base || '').split('/').filter(Boolean).join('/')];
  while (queue.length) {
    const current = queue.shift();
    const entries = typeof getWorkspaceDirectoryEntries === 'function'
      ? getWorkspaceDirectoryEntries(current)
      : { folders: [], files: [] };
    (entries.folders || []).forEach((folder) => {
      const path = String(folder && folder.path || '').split('/').filter(Boolean).join('/');
      if (!path || seenFolders.has(path)) return;
      seenFolders.add(path);
      folders.push({
        ...folder,
        path,
        name: _workspaceRelativeListName(path, base, true).replace(/\/+$/, ''),
      });
      queue.push(path);
    });
    (entries.files || []).forEach((file) => {
      const path = String(file && file.path || '').split('/').filter(Boolean).join('/');
      if (!path) return;
      files.push({
        ...file,
        path,
        name: _workspaceRelativeListName(path, base, false),
      });
    });
  }
  return { folders, files };
}

function _workspaceDeleteUsageForCommand(parsed) {
  return parsed && parsed.usage ? parsed.usage : 'Usage: rm [-r|-f|-rf] <file-or-folder>';
}

async function _workspaceReadLines(path) {
  const data = await readWorkspaceFile(path);
  return _workspaceSplitLines(data && data.text || '');
}

function _workspaceStandaloneFilterSpec(parts) {
  const root = (parts[0] || '').toLowerCase();
  if (root === 'grep') {
    if (parts.length < 3) return { error: 'Usage: grep [-i|-v|-E] <search> <file>' };
    const flags = [];
    let index = 1;
    while (index < parts.length - 2 && /^-[ivE]+$/.test(parts[index])) {
      flags.push(parts[index]);
      index += 1;
    }
    if (index !== parts.length - 2) return { error: 'Usage: grep [-i|-v|-E] <search> <file>' };
    const stage = _parseSyntheticPostFilterCommand(`cat x | grep ${flags.join(' ')} ${JSON.stringify(parts[index])}`);
    if (!stage) return { error: 'grep supports only -i, -v, and -E.' };
    return { path: parts[index + 1], spec: stage };
  }
  if (root === 'head' || root === 'tail') {
    if (parts.length < 2) return { error: `Usage: ${root} [-n N] <file>` };
    const file = parts[parts.length - 1];
    const option = parts.slice(1, -1).join(' ');
    const stage = _parseSyntheticPostFilterCommand(`cat x | ${root}${option ? ' ' + option : ''}`);
    if (!stage) return { error: `Usage: ${root} [-n N] <file>` };
    return { path: file, spec: stage };
  }
  if (root === 'wc') {
    if (parts.length !== 3 || parts[1] !== '-l') return { error: 'Usage: wc -l <file>' };
    return { path: parts[2], spec: _parseSyntheticPostFilterCommand('cat x | wc -l') };
  }
  if (root === 'sort') {
    if (parts.length < 2 || parts.length > 3) return { error: 'Usage: sort [-r|-n|-u|-rn] <file>' };
    const file = parts[parts.length - 1];
    const option = parts.length === 3 ? parts[1] : '';
    const stage = _parseSyntheticPostFilterCommand(`cat x | sort${option ? ' ' + option : ''}`);
    if (!stage) return { error: 'sort supports only -r, -n, and -u flags.' };
    return { path: file, spec: stage };
  }
  if (root === 'uniq') {
    if (parts.length < 2 || parts.length > 3) return { error: 'Usage: uniq [-c] <file>' };
    const file = parts[parts.length - 1];
    const option = parts.length === 3 ? parts[1] : '';
    const stage = _parseSyntheticPostFilterCommand(`cat x | uniq${option ? ' ' + option : ''}`);
    if (!stage) return { error: 'uniq supports only -c.' };
    return { path: file, spec: stage };
  }
  return null;
}

async function _runWorkspaceListCommand(parts, tabId) {
  const parsed = _workspaceListCommand(parts);
  if (!parsed || parsed.invalid) throw new Error(parsed?.usage || 'Usage: ls [-l] [folder]');
  const rawTarget = parsed.target;
  await _ensureWorkspaceCache();
  const target = _resolveExistingWorkspaceCommandPath(rawTarget, { cwd: _workspaceCwd(tabId), kind: 'directory', defaultToCwd: true });
  const entries = typeof getWorkspaceDirectoryEntries === 'function'
    ? getWorkspaceDirectoryEntries(target)
    : { folders: [], files: [] };
  const isRoot = !target;
  const directoryExists = isRoot || _workspacePathExists(target, 'directory');
  const fileHints = typeof getWorkspaceAutocompleteFileHints === 'function' ? getWorkspaceAutocompleteFileHints() : [];
  const file = fileHints.find(item => String(item.value || '') === target);
  if (!directoryExists && file) return [_workspacePlainLine(target)];
  if (!directoryExists) throw new Error(`folder not found: ${_workspaceDisplayPath(target)}`);
  const listingEntries = parsed.recursive ? _workspaceRecursiveEntries(target) : _workspaceDirectListEntries(entries, target);
  return parsed.long ? _workspaceListLines(listingEntries, target) : _workspaceShortListLines(listingEntries);
}

function _workspacePipeInputLinesForCommand(baseCommand, capturedLines, tabId) {
  const parts = _workspaceCommandTokens(baseCommand);
  const root = (parts[0] || '').toLowerCase();
  const action = (parts[1] || '').toLowerCase();
  if (!(root === 'ls' || root === 'll' || (root === 'file' && ['list', 'ls'].includes(action)))) {
    return capturedLines;
  }
  const parsed = _workspaceListCommand(parts);
  if (!parsed || parsed.invalid || parsed.long) return capturedLines;
  try {
    const rawTarget = parsed.target;
    const target = _resolveExistingWorkspaceCommandPath(rawTarget, {
      cwd: _workspaceCwd(tabId),
      kind: 'directory',
      defaultToCwd: true,
    });
    const isRoot = !target;
    const directoryExists = isRoot || _workspacePathExists(target, 'directory');
    const fileHints = typeof getWorkspaceAutocompleteFileHints === 'function' ? getWorkspaceAutocompleteFileHints() : [];
    const file = fileHints.find(item => String(item.value || '') === target);
    if (!directoryExists || file) return capturedLines;
    const entries = typeof getWorkspaceDirectoryEntries === 'function'
      ? getWorkspaceDirectoryEntries(target)
      : { folders: [], files: [] };
    const listingEntries = parsed.recursive ? _workspaceRecursiveEntries(target) : _workspaceDirectListEntries(entries, target);
    const names = _workspaceListNames(listingEntries);
    return names.length ? names.map(name => _workspacePlainLine(name)) : capturedLines;
  } catch (_) {
    return capturedLines;
  }
}

async function _handleWorkspaceTerminalCommand(cmd, tabId) {
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  const action = (parts[1] || '').toLowerCase();
  appendCommandEcho(cmd, tabId);
  try {
    let outputLines = [];
    if (root === 'pwd') {
      outputLines = [_workspacePlainLine(_workspaceDisplayPath(_workspaceCwd(tabId)))];
    } else if (root === 'cd') {
      if (parts.length > 2) throw new Error('Usage: cd [folder]');
      await _ensureWorkspaceCache();
      const target = _resolveExistingWorkspaceCommandPath(parts[1] || '/', { cwd: _workspaceCwd(tabId), kind: 'directory', defaultToCwd: false });
      if (target && !_workspacePathExists(target, 'directory')) {
        throw new Error(`folder not found: ${_workspaceDisplayPath(target)}`);
      }
      _setWorkspaceCwd(tabId, target);
      outputLines = [_workspacePlainLine(_workspaceDisplayPath(target))];
    } else if (root === 'ls' || root === 'll' || (root === 'file' && ['list', 'ls'].includes(action))) {
      outputLines = await _runWorkspaceListCommand(parts, tabId);
    } else if (root === 'cat' || (root === 'file' && action === 'show')) {
      const rawTarget = root === 'cat' ? parts[1] : parts[2];
      if (!rawTarget || (root === 'cat' ? parts.length !== 2 : parts.length !== 3)) {
        throw new Error(root === 'cat' ? 'Usage: cat <file>' : 'Usage: file show <file>');
      }
      await _ensureWorkspaceCache();
      const target = _resolveExistingWorkspaceCommandPath(rawTarget, { cwd: _workspaceCwd(tabId), kind: 'file' });
      outputLines = await _workspaceReadLines(target);
    } else if (root === 'mkdir' || (root === 'file' && ['add-dir', 'mkdir'].includes(action))) {
      const rawTarget = root === 'mkdir' ? parts[1] : parts[2];
      if (!rawTarget || (root === 'mkdir' ? parts.length !== 2 : parts.length !== 3)) {
        throw new Error(root === 'mkdir' ? 'Usage: mkdir <folder>' : 'Usage: file add-dir <folder>');
      }
      const target = _resolveWorkspaceCommandPath(rawTarget, { cwd: _workspaceCwd(tabId) });
      const data = await createWorkspaceDirectory(target);
      const path = data && data.directory && data.directory.path ? data.directory.path : target;
      outputLines = [_workspacePlainLine(`file: created folder ${path}`)];
    } else {
      const parsed = _workspaceStandaloneFilterSpec(parts);
      if (!parsed || parsed.error) throw new Error(parsed && parsed.error ? parsed.error : 'unsupported workspace command');
      await _ensureWorkspaceCache();
      const target = _resolveExistingWorkspaceCommandPath(parsed.path, { cwd: _workspaceCwd(tabId), kind: 'file' });
      const inputLines = await _workspaceReadLines(target);
      outputLines = _applySyntheticPostFilterLines(inputLines, parsed.spec);
    }
    outputLines.forEach(line => appendLine(line.text, line.cls || '', tabId));
    _recordSuccessfulLocalCommand(cmd);
    _persistClientSideRun(cmd, outputLines, 'ok');
    setStatus('ok');
  } catch (err) {
    appendLine(`[error] ${err.message || 'workspace command failed'}`, 'exit-fail', tabId);
    logClientError('workspace terminal command', err);
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
  const parsedDelete = _workspaceDeleteCommand(cmd);
  let target = parsedDelete && !parsedDelete.invalid ? parsedDelete.target : '';
  appendCommandEcho(cmd);
  if (!target) {
    appendLine(_workspaceDeleteUsageForCommand(parsedDelete), 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  let targetInfo = null;
  try {
    await _ensureWorkspaceCache();
    target = _resolveExistingWorkspaceCommandPath(target, { cwd: _workspaceCwd(tabId), kind: 'any' });
    const existsResp = await apiFetch(`/workspace/files/info?path=${encodeURIComponent(target)}`);
    if (!existsResp.ok) {
      const data = await existsResp.json().catch(() => ({}));
      throw new Error(data && data.error ? data.error : `file or folder was not found (${existsResp.status})`);
    }
    targetInfo = await existsResp.json().catch(() => ({}));
  } catch (err) {
    appendLine(`[error] ${err.message || 'file or folder was not found'}`, 'exit-fail', tabId);
    logClientError('file rm validate', err);
    setStatus('fail');
    return;
  }
  const isDirectory = targetInfo && targetInfo.kind === 'directory';
  const fileCount = Number(targetInfo && targetInfo.file_count) || 0;
  if (isDirectory && !(parsedDelete && parsedDelete.recursive)) {
    appendLine(`[error] ${target} is a folder; use rm -r ${target} or file delete -r ${target}`, 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  appendLine(`delete session ${isDirectory ? 'folder' : 'file'} '${target}'?`, '', tabId);
  if (isDirectory && fileCount > 0) {
    appendLine(`warning: this will also delete ${fileCount} ${fileCount === 1 ? 'file' : 'files'} in this folder.`, 'warning', tabId);
  }
  _setPendingTerminalConfirm({
    tabId,
    onYes: async () => {
      try {
        const resp = await apiFetch(`/workspace/files?path=${encodeURIComponent(target)}`, { method: 'DELETE' });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          throw new Error(data && data.error ? data.error : `file delete failed (${resp.status})`);
        }
        const removedText = isDirectory ? `file: removed folder ${target}` : `file: removed ${target}`;
        appendLine(removedText, '', tabId);
        if (typeof refreshWorkspaceFileCache === 'function') refreshWorkspaceFileCache();
        _recordSuccessfulLocalCommand(cmd);
        _persistClientSideRun(cmd, [{ text: removedText }], 'ok');
        setStatus('ok');
      } catch (err) {
        appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', tabId);
        logClientError('file rm', err);
        setStatus('fail');
      }
    },
    onNo: async () => {
      appendLine(`Session ${isDirectory ? 'folder' : 'file'} delete canceled.`, '', tabId);
      setStatus('idle');
    },
  });
  setStatus('idle');
}

async function _handleWorkspaceEditorCommand(cmd, tabId) {
  const parsed = _workspaceEditorCommand(cmd);
  appendCommandEcho(cmd);
  if (!parsed || parsed.invalid || (parsed.action === 'edit' && !parsed.target)) {
    const action = parsed?.action || 'add';
    const operand = action === 'add' ? '[file]' : '<file>';
    appendLine(`Usage: file ${action} ${operand}`, 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  if (typeof openWorkspaceEditorFromCommand !== 'function') {
    appendLine('[error] Files panel is not ready — reload the page and try again', 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  try {
    if (parsed.action === 'edit') await _ensureWorkspaceCache();
    const target = parsed.target
      ? (parsed.action === 'edit'
          ? _resolveExistingWorkspaceCommandPath(parsed.target, { cwd: _workspaceCwd(tabId), kind: 'file' })
          : _resolveWorkspaceCommandPath(parsed.target, { cwd: _workspaceCwd(tabId) }))
      : '';
    await openWorkspaceEditorFromCommand(parsed.action, target);
    const targetLabel = target ? ` ${target}` : '';
    appendLine(`file: opened${targetLabel} in the file editor`, '', tabId);
    _recordSuccessfulLocalCommand(cmd);
    _persistClientSideRun(cmd, [{ text: `file: opened${targetLabel} in the file editor` }], 'ok');
    setStatus('ok');
  } catch (err) {
    appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', tabId);
    logClientError(`file ${parsed.action}`, err);
    setStatus('fail');
  }
}

async function _handleWorkspaceDownloadCommand(cmd, tabId) {
  let target = _workspaceDownloadTarget(cmd);
  appendCommandEcho(cmd);
  if (!target) {
    appendLine('Usage: file download <file>', 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  if (typeof downloadWorkspaceFile !== 'function') {
    appendLine('[error] Files download is not ready — reload the page and try again', 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  try {
    await _ensureWorkspaceCache();
    target = _resolveExistingWorkspaceCommandPath(target, { cwd: _workspaceCwd(tabId), kind: 'file' });
    const downloaded = await downloadWorkspaceFile(target);
    if (!downloaded) throw new Error('file download failed');
    const text = `file: downloading ${target}`;
    appendLine(text, '', tabId);
    _recordSuccessfulLocalCommand(cmd);
    _persistClientSideRun(cmd, [{ text }], 'ok');
    setStatus('ok');
  } catch (err) {
    appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', tabId);
    logClientError('file download', err);
    setStatus('fail');
  }
}

async function _runClientSideCommandWithOptionalPipe(cmd, tabId, runBaseCommand) {
  const spec = _parseSyntheticPostFilterCommand(cmd);
  const baseCommand = spec ? (spec.baseCommand || cmd) : cmd;
  const capturedLines = [];
  const originalAppendLine = appendLine;
  const originalAppendLines = typeof appendLines === 'function' ? appendLines : null;
  const originalAppendCommandEcho = appendCommandEcho;
  const originalRecordSuccessfulLocalCommand = _recordSuccessfulLocalCommand;
  const originalPersistSessionTokenRun = _persistSessionTokenRun;
  const originalSetStatus = setStatus;
  let finalStatus = 'idle';
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  if (tab) {
    tab.command = cmd;
  }

  appendCommandEcho(cmd, tabId);
  try {
    appendCommandEcho = () => {};
    _recordSuccessfulLocalCommand = () => {};
    _persistSessionTokenRun = () => {};
    setStatus = (statusValue) => {
      finalStatus = statusValue;
      originalSetStatus(statusValue);
    };
    appendLine = (text, cls = '', lineTabId = tabId, metadata = null) => {
      capturedLines.push({
        text: String(text ?? ''),
        cls: String(cls || ''),
        tabId: lineTabId,
        metadata,
      });
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

  const pipeInputLines = spec ? _workspacePipeInputLinesForCommand(baseCommand, capturedLines, tabId) : capturedLines;
  const outputLines = spec ? _applySyntheticPostFilterLines(pipeInputLines, spec) : capturedLines;
  if (originalAppendLines) await originalAppendLines(outputLines, tabId);
  else {
    outputLines.forEach((line) => {
      if (line.metadata) originalAppendLine(line.text, line.cls || '', tabId, line.metadata);
      else originalAppendLine(line.text, line.cls || '', tabId);
    });
  }
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
    const pending = _pendingTerminalConfirm;
    const promptTabId = pending.tabId || activeTabId;
    appendCommandEcho(cmd, promptTabId);
    if (pending.kind === 'text') {
      _setPendingTerminalConfirm(null);
      Promise.resolve(typeof pending.onAnswer === 'function' ? pending.onAnswer(cmd) : undefined).catch((err) => {
        appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', promptTabId);
        setStatus('fail');
      });
      return true;
    }
    const answer = cmd.trim().toLowerCase();
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
  if (typeof rememberRecentDomainsFromCommand === 'function') {
    try { rememberRecentDomainsFromCommand(cmd); } catch (_) { /* autocomplete recents are best-effort */ }
  }

  // Session-token subcommands (generate / set / clear / rotate) run entirely
  // client-side.  The bare 'session-token' status command goes to the server.
  if (_isSessionTokenSubcommand(cmd)) {
    void _runClientSideCommandWithOptionalPipe(cmd, activeTabId, (baseCommand) => (
      _handleSessionTokenCommand(baseCommand, activeTabId)
    ));
    return true;
  }

  if (_isWorkspaceTerminalCommand(cmd)) {
    void _runClientSideCommandWithOptionalPipe(cmd, activeTabId, (baseCommand) => (
      _handleWorkspaceTerminalCommand(baseCommand, activeTabId)
    ));
    return true;
  }

  if (_isWorkspaceDeleteCommand(cmd)) {
    void _runClientSideCommandWithOptionalPipe(cmd, activeTabId, (baseCommand) => (
      _handleWorkspaceDeleteCommand(baseCommand, activeTabId)
    ));
    return true;
  }

  if (_isWorkspaceEditorCommand(cmd)) {
    void _runClientSideCommandWithOptionalPipe(cmd, activeTabId, (baseCommand) => (
      _handleWorkspaceEditorCommand(baseCommand, activeTabId)
    ));
    return true;
  }

  if (_isWorkspaceDownloadCommand(cmd)) {
    void _runClientSideCommandWithOptionalPipe(cmd, activeTabId, (baseCommand) => (
      _handleWorkspaceDownloadCommand(baseCommand, activeTabId)
    ));
    return true;
  }

  if (String(cmd || '').trim().toLowerCase().split(/\s+/, 1)[0] === 'workflow') {
    if (typeof handleWorkflowTerminalCommand === 'function') {
      void handleWorkflowTerminalCommand(cmd, activeTabId);
      return true;
    }
    appendCommandEcho(cmd);
    appendLine('[error] workflow command is not ready — reload the page and try again', 'exit-fail', activeTabId);
    setStatus('fail');
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
    _runTab.lastEventId = '';
    _runTab.attachMode = '';
    _runTab.followOutput = true;
    _runTab.deferPromptMount = false;
  }
  setStatus('running');
  setTabStatus(activeTabId, 'running');
  _setRunButtonDisabled(true);
  showTabKillBtn(activeTabId);
  startTimer();

  const tabId = activeTabId;

  apiFetch('/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command: cmd, tab_id: tabId })
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
    return res.json().then(data => {
      const runId = data && data.run_id;
      if (!runId) {
        appendLine('[server error] The server did not return a run id.', 'exit-fail', tabId);
        setStatus('fail'); setTabStatus(tabId, 'fail');
        stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
        return;
      }
      _markTabRunStarted(tabId, runId);
      return _subscribeRunStream(runId, tabId, { streamUrl: data.stream });
    });
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
