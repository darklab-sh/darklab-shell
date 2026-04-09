// ── Shared command execution + desktop input wrapper ──
// If no chunk arrives from the SSE stream for 45 seconds (> 2× the 20s server heartbeat),
// the connection has silently died. Surface a notice and reset the UI so the user isn't
// left with a perpetually-spinning tab. The command may still be running server-side;
// the result will appear in the history panel once it completes.
// Keyed by tabId so multiple concurrent tabs each have their own independent timer.
const _stalledTimeouts = new Map();

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
function setStatus(s) {
  status.className = 'status-pill ' + s;
  const labels = { idle: 'IDLE', running: 'RUNNING', ok: 'EXIT 0', fail: 'ERROR', killed: 'KILLED' };
  status.textContent = labels[s] || s;
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

function startTimer() {
  timerStart = Date.now();
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

function focusComposerInputAfterRun() {
  if (typeof focusAnyComposerInput === 'function' && focusAnyComposerInput()) return;
}

function interruptPromptLine(tabId = activeTabId) {
  const t = getTab(tabId);
  if (t && t.st === 'running') return false;
  appendPromptNewline(tabId);
  _clearDesktopInput();
  focusComposerInputAfterRun();
  if (tabId === activeTabId) setStatus('idle');
  return true;
}

// ── Kill confirmation modal ──
function confirmKill(tabId) {
  pendingKillTabId = tabId;
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  showKillOverlay();
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
  stopTimer();
  appendLine(`[killed by user${secs != null ? ' after ' + _formatElapsed(secs) : ''}]`, 'exit-fail', tabId);
  setTabStatus(tabId, 'killed');
  hideTabKillBtn(tabId);
  if (tabId === activeTabId) {
    setStatus('killed');
    _setRunButtonDisabled(false);
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
function submitCommand(rawCmd) {
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
  if (shellOps.test(cmd)) {
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
                  if (i < arr.length - 1 || line) appendLine(line, '', tabId);
                });
              } else if (msg.type === 'exit') {
                _clearStalledTimeout(tabId);
                const t = getTab(tabId);
                if (t) {
                  t.exitCode = msg.code;
                  t.runId = null;
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
                if (t) t.syntheticClear = false;
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
    if (focusAfterSubmit) focusComposerInputAfterRun();
    if (dismissKeyboard && typeof dismissMobileKeyboardAfterSubmit === 'function') {
      dismissMobileKeyboardAfterSubmit();
    }
  } else if (result === 'settle') {
    focusComposerInputAfterRun();
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
  submitComposerCommand(cmdInput.value, { dismissKeyboard: true });
}
