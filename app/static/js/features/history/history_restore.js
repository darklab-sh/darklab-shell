// History run restore and source-line highlight helpers.

function _historyRunIdentity(run) {
  return String(run?.id || run?.run_id || '').trim();
}

function _tabForHistoryRun(run) {
  const runId = _historyRunIdentity(run);
  if (!runId) return null;
  return tabs.find(t => (
    t && (String(t.historyRunId || '') === runId || String(t.runId || '') === runId)
  )) || null;
}

function _scrollHistoryHighlightIntoView(out, line) {
  if (!out || !line || typeof out.contains !== 'function' || !out.contains(line)) return false;
  if (
    typeof out.getBoundingClientRect !== 'function'
    || typeof line.getBoundingClientRect !== 'function'
  ) return false;
  const outRect = out.getBoundingClientRect();
  const lineRect = line.getBoundingClientRect();
  const targetTop = Number(lineRect.top) - Number(outRect.top);
  const lineHeight = Number(lineRect.height) || Number(line.offsetHeight) || 0;
  const outHeight = Number(out.clientHeight) || Number(outRect.height) || 0;
  if (!Number.isFinite(targetTop) || outHeight <= 0) return false;
  out.scrollTop += targetTop - (outHeight / 2) + (lineHeight / 2);
  return true;
}

function _highlightRestoredHistoryLine(tabId, { lineNumber = null, lineIndex = null } = {}) {
  const out = typeof getOutput === 'function' ? getOutput(tabId) : null;
  if (!out) return false;
  const cssEscape = value => (
    typeof CSS !== 'undefined' && CSS && typeof CSS.escape === 'function'
      ? CSS.escape(String(value))
      : String(value).replace(/"/g, '\\"')
  );
  const normalizedLineNumber = Number(lineNumber || 0);
  const normalizedLineIndex = Number(lineIndex);
  const selector = normalizedLineNumber > 0
    ? `.line[data-line-number="${cssEscape(normalizedLineNumber)}"]`
    : (Number.isInteger(normalizedLineIndex) ? `.line[data-line-index="${cssEscape(normalizedLineIndex)}"]` : '');
  if (!selector) return false;
  const line = out.querySelector(selector);
  if (!line) return false;
  out.querySelectorAll('.line.history-source-highlight').forEach(node => {
    node.classList.remove('history-source-highlight');
  });
  line.classList.add('history-source-highlight');
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  if (tab) {
    tab.followOutput = false;
  }
  if (!_scrollHistoryHighlightIntoView(out, line) && typeof line.scrollIntoView === 'function') {
    line.scrollIntoView({ block: 'center' });
  }
  return true;
}

function _historyHasPendingOutput(tabId) {
  return typeof hasPendingOutputBatch === 'function' && hasPendingOutputBatch(tabId);
}

function _scheduleRestoredHistoryLineHighlight(tabId, options) {
  const startedAt = Date.now();
  const runFinalLayoutPasses = () => {
    const run = () => _highlightRestoredHistoryLine(tabId, options);
    if (typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(() => window.requestAnimationFrame(run));
    }
    window.setTimeout(run, 48);
    window.setTimeout(run, 120);
    window.setTimeout(run, 300);
  };
  const retryUntilOutputSettles = () => {
    const highlighted = _highlightRestoredHistoryLine(tabId, options);
    const pending = _historyHasPendingOutput(tabId);
    if ((!highlighted || pending) && Date.now() - startedAt < 2000) {
      window.setTimeout(retryUntilOutputSettles, pending ? 32 : 50);
      return;
    }
    runFinalLayoutPasses();
  };
  window.setTimeout(retryUntilOutputSettles, 0);
}

function _suppressHistoryRestoreStatusPeek(tabId) {
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  if (!tab) return;
  tab.suppressStatusMonitorPeekHold = true;
  const setTimer = typeof window !== 'undefined' && typeof window.setTimeout === 'function'
    ? window.setTimeout.bind(window)
    : (typeof setTimeout === 'function' ? setTimeout : null);
  if (!setTimer) return;
  setTimer(() => {
    const live = typeof getTab === 'function' ? getTab(tabId) : null;
    if (live) delete live.suppressStatusMonitorPeekHold;
  }, 0);
}

function restoreHistoryRunIntoTab(run, {
  targetTabId = null,
  hidePanelOnSuccess = true,
  highlightLineNumber = null,
  highlightLineIndex = null,
} = {}) {
  if (!run || !run.id) return Promise.reject(new Error('missing run id'));
  const existing = targetTabId ? getTab(targetTabId) : _tabForHistoryRun(run);
  const canUpgradeExisting = !!(existing && run.full_output_available && existing.previewTruncated);
  const restoreUrl = run.full_output_available
    ? `/history/${run.id}?json`
    : `/history/${run.id}?json&preview=1`;

  return apiFetch(restoreUrl)
    .then(r => r.json())
    .then(fullRun => {
      const previewNotice = fullRun.preview_notice || null;
      const tabId = targetTabId || (canUpgradeExisting ? existing.id : createTab(fullRun.command));
      if (!tabId) throw new Error('failed to create restore tab');
      if (typeof clearTab === 'function') clearTab(tabId);
      const t = getTab(tabId);
      if (t) {
        t.command = fullRun.command;
        t.runId = null;
        t.historyRunId = fullRun.id || run.id;
        t.exitCode = fullRun.exit_code;
        t.previewTruncated = !!previewNotice;
        t.fullOutputAvailable = !!fullRun.full_output_available;
        t.fullOutputLoaded = !!fullRun.full_output_available && !previewNotice;
        t.reconnectedRun = false;
      }
      _appendHistoryCommandEcho(tabId, fullRun.command);
      const outputLines = Array.isArray(fullRun.output_entries) ? fullRun.output_entries : (fullRun.output || []);
      outputLines.forEach(line => _appendHistoryOutputLine(line, tabId));
      if (previewNotice) appendLine(previewNotice, 'notice', tabId);
      appendLine(
        `[history — ${_historyExitLabel(fullRun.exit_code)}]`,
        _historyExitClass(fullRun.exit_code),
        tabId
      );
      _suppressHistoryRestoreStatusPeek(tabId);
      if (typeof setTabStatus === 'function') {
        setTabStatus(tabId, fullRun.exit_code === 0 ? 'ok' : 'fail');
      }
      if (typeof hideTabKillBtn === 'function') hideTabKillBtn(tabId);
      if (hidePanelOnSuccess) hideHistoryPanel();
      if (highlightLineNumber || Number.isInteger(highlightLineIndex)) {
        _scheduleRestoredHistoryLineHighlight(tabId, {
          lineNumber: highlightLineNumber,
          lineIndex: highlightLineIndex,
        });
      }
      return tabId;
    });
}

function restoreHistoryRun(runOrId, options = {}) {
  const run = typeof runOrId === 'object' && runOrId !== null
    ? runOrId
    : { id: String(runOrId || ''), full_output_available: true };
  return restoreHistoryRunIntoTab(run, {
    hidePanelOnSuccess: false,
    ...options,
  });
}

window.restoreHistoryRun = restoreHistoryRun;
