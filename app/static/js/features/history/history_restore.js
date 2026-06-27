// History run restore and source-line highlight helpers.
import { getTab as importedGetTab, getTabs as importedGetTabs } from '../../core/state.js';
import {
  apiFetch as importedRuntimeApiFetch,
  hasRuntimeHandler as importedHasRuntimeHandler,
} from '../../runtime_bridge.js';
import {
  appendLine as importedAppendLine,
  hasPendingOutputBatch as importedHasPendingOutputBatch,
  renderCommandOutcomeSummary as importedRenderCommandOutcomeSummary,
} from '../../output.js';
import {
  clearTab as importedClearTab,
  createTab as importedCreateTab,
  getOutput as importedGetOutput,
  setTabStatus as importedSetTabStatus,
} from '../../tabs.js';
import {
  _historyExitClass as importedHistoryExitClass,
  _historyExitLabel as importedHistoryExitLabel,
} from './history_rows.js';
import { setHistoryRestoreHandlers as importedSetHistoryRestoreHandlers } from './history_restore_bridge.js';

const HISTORY_RESTORE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _historyRestoreGlobalFunction(name) {
  const fn = HISTORY_RESTORE_GLOBAL && HISTORY_RESTORE_GLOBAL[name];
  return typeof fn === 'function' ? fn : null;
}

function _historyRestoreTabs() {
  const getTabsFn = (typeof importedGetTabs !== 'undefined' && importedGetTabs)
    || _historyRestoreGlobalFunction('getTabs');
  if (typeof getTabsFn === 'function') return getTabsFn();
  const stateTabs = HISTORY_RESTORE_GLOBAL.tabs;
  return Array.isArray(stateTabs) ? stateTabs : [];
}

function _historyRestoreGetTab(tabId) {
  const getTabFn = (typeof importedGetTab !== 'undefined' && importedGetTab)
    || _historyRestoreGlobalFunction('getTab');
  return typeof getTabFn === 'function' ? getTabFn(tabId) : null;
}

function _historyRestoreGetOutput(tabId) {
  const getOutputForTab = (typeof importedGetOutput !== 'undefined' && importedGetOutput)
    || _historyRestoreGlobalFunction('getOutput');
  return typeof getOutputForTab === 'function' ? getOutputForTab(tabId) : null;
}

function _historyRestoreCreateTab(label) {
  const create = (typeof importedCreateTab !== 'undefined' && importedCreateTab)
    || _historyRestoreGlobalFunction('createTab');
  return typeof create === 'function' ? create(label) : null;
}

function _historyRestoreClearTab(tabId) {
  const clear = (typeof importedClearTab !== 'undefined' && importedClearTab)
    || _historyRestoreGlobalFunction('clearTab');
  if (typeof clear === 'function') clear(tabId);
}

function _historyRestoreAppendLine(text, cls, tabId, metadata = null) {
  const append = (typeof importedAppendLine !== 'undefined' && importedAppendLine)
    || _historyRestoreGlobalFunction('appendLine');
  if (typeof append === 'function') append(text, cls, tabId, metadata);
}

function _historyRestoreSetTabStatus(tabId, status) {
  const setStatus = (typeof importedSetTabStatus !== 'undefined' && importedSetTabStatus)
    || _historyRestoreGlobalFunction('setTabStatus');
  if (typeof setStatus === 'function') setStatus(tabId, status);
}

function _historyRestoreApiFetch(url, options) {
  const api = (
    typeof importedRuntimeApiFetch === 'function'
    && typeof importedHasRuntimeHandler === 'function'
    && importedHasRuntimeHandler('apiFetch')
  )
    ? importedRuntimeApiFetch
    : _historyRestoreGlobalFunction('apiFetch');
  if (typeof api === 'function') return options === undefined ? api(url) : api(url, options);
  return options === undefined ? fetch(url) : fetch(url, options);
}

function _historyRestoreAppendCommandEcho(tabId, command) {
  const append = _historyRestoreGlobalFunction('_appendHistoryCommandEcho');
  if (typeof append === 'function') {
    append(tabId, command);
    return;
  }
  _historyRestoreAppendLine(command, 'prompt-echo', tabId);
}

function _historyRestoreOutputLineMetadata(entry) {
  if (!entry || typeof entry !== 'object') return null;
  const metadata = {};
  if (Array.isArray(entry.signals) && entry.signals.length) metadata.signals = entry.signals;
  if (typeof entry.kind === 'string' && entry.kind) metadata.kind = entry.kind;
  if (typeof entry.role === 'string' && entry.role) metadata.role = entry.role;
  if (Number.isInteger(entry.line_index)) metadata.line_index = entry.line_index;
  if (Number.isInteger(entry.line_number)) metadata.line_number = entry.line_number;
  if (typeof entry.command_root === 'string' && entry.command_root) metadata.command_root = entry.command_root;
  if (typeof entry.target === 'string' && entry.target) metadata.target = entry.target;
  if (entry.template_provenance && typeof entry.template_provenance === 'object') {
    metadata.template_provenance = entry.template_provenance;
  }
  if (entry.source_detail && typeof entry.source_detail === 'object') {
    metadata.source_detail = entry.source_detail;
  }
  return Object.keys(metadata).length ? metadata : null;
}

function _historyRestoreAppendOutputLine(entry, tabId) {
  const append = _historyRestoreGlobalFunction('_appendHistoryOutputLine');
  if (typeof append === 'function') {
    append(entry, tabId);
    return;
  }
  if (entry && typeof entry === 'object') {
    const text = String(entry.text || '');
    const cls = String(entry.cls || '');
    const metadata = _historyRestoreOutputLineMetadata(entry);
    _historyRestoreAppendLine(text, cls, tabId, metadata);
    return;
  }
  _historyRestoreAppendLine(String(entry || ''), '', tabId);
}

function _historyRestoreExitLabel(exitCode) {
  const label = (typeof importedHistoryExitLabel !== 'undefined' && importedHistoryExitLabel)
    || _historyRestoreGlobalFunction('_historyExitLabel');
  return typeof label === 'function' ? label(exitCode) : `exit ${exitCode ?? 'unknown'}`;
}

function _historyRestoreExitClass(exitCode) {
  const cls = (typeof importedHistoryExitClass !== 'undefined' && importedHistoryExitClass)
    || _historyRestoreGlobalFunction('_historyExitClass');
  return typeof cls === 'function' ? cls(exitCode) : '';
}

function _historyRestoreRenderCommandOutcomeSummary(tabId, outcome) {
  const render = (typeof importedRenderCommandOutcomeSummary !== 'undefined' && importedRenderCommandOutcomeSummary)
    || _historyRestoreGlobalFunction('renderCommandOutcomeSummary');
  if (typeof render === 'function') render(tabId, outcome);
}

function _historyRunIdentity(run) {
  return String(run?.id || run?.run_id || '').trim();
}

function _tabForHistoryRun(run) {
  const runId = _historyRunIdentity(run);
  if (!runId) return null;
  return _historyRestoreTabs().find(t => (
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
  const out = _historyRestoreGetOutput(tabId);
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
  const tab = _historyRestoreGetTab(tabId);
  if (tab) {
    tab.followOutput = false;
  }
  if (!_scrollHistoryHighlightIntoView(out, line) && typeof line.scrollIntoView === 'function') {
    line.scrollIntoView({ block: 'center' });
  }
  return true;
}

function _historyHasPendingOutput(tabId) {
  const hasPending = (typeof importedHasPendingOutputBatch !== 'undefined' && importedHasPendingOutputBatch)
    || _historyRestoreGlobalFunction('hasPendingOutputBatch');
  return typeof hasPending === 'function' && hasPending(tabId);
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
  const tab = _historyRestoreGetTab(tabId);
  if (!tab) return;
  tab.suppressStatusMonitorPeekHold = true;
  const setTimer = typeof window !== 'undefined' && typeof window.setTimeout === 'function'
    ? window.setTimeout.bind(window)
    : (typeof setTimeout === 'function' ? setTimeout : null);
  if (!setTimer) return;
  setTimer(() => {
    const live = _historyRestoreGetTab(tabId);
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
  const existing = targetTabId ? _historyRestoreGetTab(targetTabId) : _tabForHistoryRun(run);
  const canUpgradeExisting = !!(existing && run.full_output_available && existing.previewTruncated);
  const restoreUrl = run.full_output_available
    ? `/history/${run.id}?json`
    : `/history/${run.id}?json&preview=1`;

  return _historyRestoreApiFetch(restoreUrl)
    .then(r => r.json())
    .then(fullRun => {
      const previewNotice = fullRun.preview_notice || null;
      const tabId = targetTabId || (canUpgradeExisting ? existing.id : _historyRestoreCreateTab(fullRun.command));
      if (!tabId) throw new Error('failed to create restore tab');
      _historyRestoreClearTab(tabId);
      const t = _historyRestoreGetTab(tabId);
      if (t) {
        t.command = fullRun.command;
        t.runId = null;
        t.historyRunId = fullRun.id || run.id;
        t.exitCode = fullRun.exit_code;
        t.previewTruncated = !!previewNotice;
        t.fullOutputAvailable = !!fullRun.full_output_available;
        t.fullOutputLoaded = !!fullRun.full_output_available && !previewNotice;
        t.reconnectedRun = false;
        t.commandOutcomeSummary = fullRun.command_outcome_summary || fullRun.output_outcome_summary || null;
      }
      _historyRestoreAppendCommandEcho(tabId, fullRun.command);
      const outputLines = Array.isArray(fullRun.output_entries) ? fullRun.output_entries : (fullRun.output || []);
      outputLines.forEach(line => _historyRestoreAppendOutputLine(line, tabId));
      if (previewNotice) _historyRestoreAppendLine(previewNotice, 'notice', tabId);
      _historyRestoreAppendLine(
        `[history — ${_historyRestoreExitLabel(fullRun.exit_code)}]`,
        _historyRestoreExitClass(fullRun.exit_code),
        tabId
      );
      _historyRestoreRenderCommandOutcomeSummary(tabId, t && t.commandOutcomeSummary);
      _suppressHistoryRestoreStatusPeek(tabId);
      _historyRestoreSetTabStatus(tabId, fullRun.exit_code === 0 ? 'ok' : 'fail');
      const hideKill = _historyRestoreGlobalFunction('hideTabKillBtn');
      if (hideKill) hideKill(tabId);
      const hidePanel = _historyRestoreGlobalFunction('hideHistoryPanel');
      if (hidePanelOnSuccess && hidePanel) hidePanel();
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

if (typeof importedSetHistoryRestoreHandlers === 'function') {
  importedSetHistoryRestoreHandlers({
    restoreHistoryRun,
    restoreHistoryRunIntoTab,
  });
}

export {
  _highlightRestoredHistoryLine,
  _historyHasPendingOutput,
  _historyRunIdentity,
  _scheduleRestoredHistoryLineHighlight,
  _scrollHistoryHighlightIntoView,
  _suppressHistoryRestoreStatusPeek,
  _tabForHistoryRun,
  restoreHistoryRun,
  restoreHistoryRunIntoTab,
};
