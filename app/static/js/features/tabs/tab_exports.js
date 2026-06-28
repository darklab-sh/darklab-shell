// Tab transcript copy, export, and permalink actions.
import { getAppConfig as importedGetAppConfig } from '../../core/config.js';
import { getTab as importedGetTab } from '../../core/state.js';
import {
  copyTextToClipboard as importedCopyTextToClipboard,
  downloadBlobAsAttachment as importedDownloadBlobAsAttachment,
  escapeHtml as importedEscapeHtml,
  omitRawOnlyLineEntries as importedOmitRawOnlyLineEntries,
  redactLineEntries as importedRedactLineEntries,
  shareUrl as importedShareUrl,
  showToast as importedShowToast,
} from '../../core/utils.js';
import { getCommandOutcomeSummariesPreference as importedGetCommandOutcomeSummariesPreference } from '../preferences/preferences.js';
import {
  activeTeamScopeCan as importedActiveTeamScopeCan,
  teamScopeDeniedMessage as importedTeamScopeDeniedMessage,
} from '../team_scope.js';
import { apiFetch as importedRuntimeApiFetch } from '../../runtime_bridge.js';
import {
  createAnsiUpRenderer as importedCreateAnsiUpRenderer,
  getLineNumberMode as importedGetLineNumberMode,
  getTimestampMode as importedGetTimestampMode,
} from '../../output.js';
import { refocusComposerAfterAction as importedRefocusComposerAfterAction } from '../../ui/ui_helpers.js';
import {
  confirmPermalinkRedactionChoice as importedConfirmPermalinkRedactionChoice,
  hasShareRedactionHandler as importedHasShareRedactionHandler,
} from './share_redaction_bridge.js';

const TAB_EXPORT_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _tabExportGlobalFunction(name) {
  const fn = TAB_EXPORT_GLOBAL && TAB_EXPORT_GLOBAL[name];
  return typeof fn === 'function' ? fn : null;
}

var ExportHtmlUtils = TAB_EXPORT_GLOBAL.ExportHtmlUtils || null;

function _refreshTabExportHtmlUtils() {
  ExportHtmlUtils = TAB_EXPORT_GLOBAL.ExportHtmlUtils || ExportHtmlUtils || null;
  return ExportHtmlUtils;
}

function _tabExportConfig() {
  if (typeof importedGetAppConfig !== 'undefined' && typeof importedGetAppConfig === 'function') {
    return importedGetAppConfig() || {};
  }
  return TAB_EXPORT_GLOBAL.APP_CONFIG || {};
}

function _tabExportGetTab(id) {
  const getTabFn = (typeof importedGetTab !== 'undefined' && importedGetTab)
    || _tabExportGlobalFunction('getTab');
  return typeof getTabFn === 'function' ? getTabFn(id) : null;
}

function _tabExportShowToast(...args) {
  const show = (typeof importedShowToast !== 'undefined' && importedShowToast)
    || _tabExportGlobalFunction('showToast');
  if (typeof show === 'function') show(...args);
}

function _tabExportRefocusComposer(options = { preventScroll: true }) {
  const refocus = (typeof importedRefocusComposerAfterAction !== 'undefined' && importedRefocusComposerAfterAction)
    || _tabExportGlobalFunction('refocusComposerAfterAction');
  if (typeof refocus === 'function') refocus(options);
}

function _tabExportCopyTextToClipboard(text) {
  const copy = (typeof importedCopyTextToClipboard !== 'undefined' && importedCopyTextToClipboard)
    || _tabExportGlobalFunction('copyTextToClipboard');
  return typeof copy === 'function' ? copy(text) : Promise.reject(new Error('clipboard unavailable'));
}

function _tabExportDownloadBlobAsAttachment(blob, filename) {
  const download = (typeof importedDownloadBlobAsAttachment !== 'undefined' && importedDownloadBlobAsAttachment)
    || _tabExportGlobalFunction('downloadBlobAsAttachment');
  if (typeof download === 'function') download(blob, filename);
}

function _tabExportEscapeHtml(text) {
  const escape = (typeof importedEscapeHtml !== 'undefined' && importedEscapeHtml)
    || _tabExportGlobalFunction('escapeHtml');
  return typeof escape === 'function' ? escape(text) : String(text ?? '');
}

function _tabExportRedactLineEntries(lines, rules) {
  const redact = (typeof importedRedactLineEntries !== 'undefined' && importedRedactLineEntries)
    || _tabExportGlobalFunction('redactLineEntries');
  return typeof redact === 'function' ? redact(lines, rules) : (Array.isArray(lines) ? lines : []);
}

function _tabExportOmitRawOnlyLineEntries(lines) {
  const omit = (typeof importedOmitRawOnlyLineEntries !== 'undefined' && importedOmitRawOnlyLineEntries)
    || _tabExportGlobalFunction('omitRawOnlyLineEntries');
  return typeof omit === 'function' ? omit(lines) : (Array.isArray(lines) ? lines : []);
}

function _tabExportCommandOutcomeSummariesPreference() {
  const getPreference = (
    _tabExportGlobalFunction('getCommandOutcomeSummariesPreference')
  ) || (
    typeof importedGetCommandOutcomeSummariesPreference !== 'undefined'
    && importedGetCommandOutcomeSummariesPreference
  );
  return typeof getPreference === 'function' ? getPreference() : null;
}

function _tabExportCreateAnsiUpRenderer() {
  const createRenderer = (typeof importedCreateAnsiUpRenderer !== 'undefined' && importedCreateAnsiUpRenderer)
    || _tabExportGlobalFunction('createAnsiUpRenderer');
  return typeof createRenderer === 'function' ? createRenderer() : null;
}

function _tabExportActiveTeamScopeCan(capability) {
  const can = (typeof importedActiveTeamScopeCan !== 'undefined' && importedActiveTeamScopeCan)
    || null;
  return typeof can === 'function' ? can(capability) : true;
}

function _tabExportTeamScopeDeniedMessage(action) {
  const message = (typeof importedTeamScopeDeniedMessage !== 'undefined' && importedTeamScopeDeniedMessage)
    || null;
  return typeof message === 'function' ? message(action) : '';
}

function _tabExportShareUrl(url) {
  const share = (typeof importedShareUrl !== 'undefined' && importedShareUrl)
    || _tabExportGlobalFunction('shareUrl');
  return typeof share === 'function' ? share(url) : Promise.reject(new Error('share unavailable'));
}

function _tabExportApiFetch(url, options) {
  const api = (typeof importedRuntimeApiFetch === 'function' && importedRuntimeApiFetch)
    || _tabExportGlobalFunction('apiFetch');
  if (typeof api === 'function') return options === undefined ? api(url) : api(url, options);
  return options === undefined ? fetch(url) : fetch(url, options);
}

function _tabExportConfirmRedactionChoice() {
  const confirm = (
    typeof importedHasShareRedactionHandler === 'function'
    && importedHasShareRedactionHandler('confirmPermalinkRedactionChoice')
  ) ? importedConfirmPermalinkRedactionChoice : _tabExportGlobalFunction('confirmPermalinkRedactionChoice');
  return typeof confirm === 'function' ? confirm() : Promise.resolve(_shareRedactionEnabled() ? 'redacted' : 'raw');
}

function _tabExportLineNumberMode() {
  const readMode = (typeof importedGetLineNumberMode !== 'undefined' && importedGetLineNumberMode)
    || _tabExportGlobalFunction('getLineNumberMode');
  return typeof readMode === 'function' ? readMode() : TAB_EXPORT_GLOBAL.lnMode;
}

function _tabExportTimestampMode() {
  const readMode = (typeof importedGetTimestampMode !== 'undefined' && importedGetTimestampMode)
    || _tabExportGlobalFunction('getTimestampMode');
  return typeof readMode === 'function' ? readMode() : TAB_EXPORT_GLOBAL.tsMode;
}

function _getExportableRawLines(tab) {
  if (!tab || !Array.isArray(tab.rawLines)) return [];
  return tab.rawLines.filter(line => {
    if (!line || typeof line.text !== 'string') return false;
    const cls = ExportHtmlUtils && typeof ExportHtmlUtils.lineLegacyClass === 'function'
      ? ExportHtmlUtils.lineLegacyClass(ExportHtmlUtils.lineEventFromWire(line))
      : String(line.cls || '');
    if (['wlc-live'].includes(cls) || cls.startsWith('welcome-')) return false;
    const plain = line.text.replace(/\x1b\[[0-9;]*[A-Za-z]/g, '').trim();
    return plain.length > 0;
  });
}

function _getShareRedactionRules() {
  const config = _tabExportConfig();
  return config && Array.isArray(config.share_redaction_rules)
    ? config.share_redaction_rules
    : [];
}

function _shareRedactionEnabled() {
  const config = _tabExportConfig();
  return !(config && config.share_redaction_enabled === false);
}

function _getRedactedLines(lines) {
  return _tabExportRedactLineEntries(lines, _getShareRedactionRules());
}

function _refocusAfterTabAction(options = { preventScroll: true }) {
  _tabExportRefocusComposer(options);
}

function _stripTabExportAnsi(text) {
  return String(text ?? '').replace(/\x1b\[[0-9;]*[A-Za-z]/g, '');
}

function _commandOutcomeSummariesEnabledForExport() {
  const preference = _tabExportCommandOutcomeSummariesPreference();
  if (preference !== null && typeof preference !== 'undefined') {
    return preference !== 'off';
  }
  const cookie = typeof document !== 'undefined' ? String(document.cookie || '') : '';
  return !/(?:^|;\s*)pref_command_outcome_summaries=off(?:;|$)/.test(cookie);
}

function _appendTabCommandOutcomeSummaryLines(tab, lines) {
  if (!ExportHtmlUtils || typeof ExportHtmlUtils.appendCommandOutcomeSummaryLines !== 'function') {
    return _normalizeTabTranscriptLines(lines);
  }
  return ExportHtmlUtils.appendCommandOutcomeSummaryLines(lines, {
    command: tab && tab.command || '',
    enabled: _commandOutcomeSummariesEnabledForExport(),
  });
}

function copyTab(id) {
  _refreshTabExportHtmlUtils();
  const t = _tabExportGetTab(id);
  const lines = _getExportableRawLines(t);
  if (!lines.length) {
    _tabExportShowToast('No output to copy yet');
    _refocusAfterTabAction();
    return;
  }
  const exportLines = _appendTabCommandOutcomeSummaryLines(t, lines);
  const text = exportLines.map(line => _stripTabExportAnsi(line.text)).join('\n');
  _tabExportCopyTextToClipboard(text)
    .then(() => _tabExportShowToast('Copied to clipboard'))
    .catch(() => _tabExportShowToast('Failed to copy', 'error'))
    .finally(() => _refocusAfterTabAction());
}

// Reads from rawLines rather than DOM innerText so that CSS ::before timestamp
// content and ANSI escape codes don't appear in the saved file.
function saveTab(id) {
  _refreshTabExportHtmlUtils();
  const t = _tabExportGetTab(id);
  const lines = _getExportableRawLines(t);
  if (!lines.length) {
    _tabExportShowToast('No output to export');
    _refocusAfterTabAction();
    return;
  }
  const exportLines = _appendTabCommandOutcomeSummaryLines(t, lines);
  const text = exportLines.map(line => _stripTabExportAnsi(line.text)).join('\n');
  const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const blob = new Blob([text], { type: 'text/plain' });
  const config = _tabExportConfig();
  _tabExportDownloadBlobAsAttachment(blob, `${config.app_name || 'shell'}-${ts}.txt`);
  _refocusAfterTabAction();
}

// Returns the gutter prefix for a raw line, respecting the current tsMode/lnMode
// toggles so exports match what the user sees in the terminal.
function _exportPrefix(line, zeroBasedIndex) {
  if (ExportHtmlUtils
      && typeof ExportHtmlUtils.isCommandOutcomeSummaryLine === 'function'
      && ExportHtmlUtils.isCommandOutcomeSummaryLine(line)) {
    return '';
  }
  const parts = [];
  if (_tabExportLineNumberMode() === 'on') {
    const absoluteLineNumber = Number(line && line.line_number || 0);
    parts.push(String(absoluteLineNumber > 0 ? absoluteLineNumber : zeroBasedIndex + 1));
  }
  const timestampMode = _tabExportTimestampMode();
  if (timestampMode) {
    if (timestampMode === 'clock' && line.tsC) parts.push(line.tsC);
    else if (timestampMode === 'elapsed' && line.tsE) parts.push(line.tsE);
  }
  return parts.join(' ');
}

function _normalizeTabTranscriptLine(line) {
  if (ExportHtmlUtils && typeof ExportHtmlUtils.normalizeExportTranscriptLine === 'function') {
    return ExportHtmlUtils.normalizeExportTranscriptLine(line);
  }
  if (typeof line === 'string') {
    return { text: line, cls: '', tsC: '', tsE: '' };
  }
  if (line && typeof line.text === 'string') {
    return ExportHtmlUtils && typeof ExportHtmlUtils.lineEventFromWire === 'function'
      ? ExportHtmlUtils.lineEventFromWire(line)
      : {
        text: line.text,
        cls: String(line.cls || ''),
        tsC: String(line.tsC || ''),
        tsE: String(line.tsE || ''),
        line_number: Number.isInteger(line.line_number) ? line.line_number : undefined,
      };
  }
  return null;
}

function _normalizeTabTranscriptLines(lines, { stripTruncationNotices = false } = {}) {
  if (ExportHtmlUtils && typeof ExportHtmlUtils.normalizeExportTranscriptLines === 'function') {
    return ExportHtmlUtils.normalizeExportTranscriptLines(lines, { stripTruncationNotices });
  }
  return (Array.isArray(lines) ? lines : [])
    .map(_normalizeTabTranscriptLine)
    .filter(line => {
      if (!line) return false;
      if (!stripTruncationNotices) return true;
      return !/^\[(?:preview|tab output) truncated/i.test(String(line.text || ''));
    });
}

function _omitRawOnlyExportLines(lines) {
  return _tabExportOmitRawOnlyLineEntries(lines);
}

function _buildTabExportModel(tab, { createdText = null, omitRawOnly = false } = {}) {
  const config = _tabExportConfig();
  const normalizedCreatedText = String(createdText || new Date().toLocaleString());
  const rawLines = omitRawOnly ? _omitRawOnlyExportLines(tab && tab.rawLines) : (tab && tab.rawLines);
  if (ExportHtmlUtils && typeof ExportHtmlUtils.buildExportDocumentModel === 'function') {
    const normalizedRawLineCount = _normalizeTabTranscriptLines(rawLines).length;
    return ExportHtmlUtils.buildExportDocumentModel({
      appName: config.app_name || 'darklab_shell',
      title: String(tab && tab.label || ''),
      label: tab && tab.label,
      createdText: normalizedCreatedText,
      runMeta: {
        exitCode: tab ? tab.exitCode : null,
        duration: null,
        lines: `${normalizedRawLineCount} lines`,
        version: config.version || null,
      },
      rawLines,
      command: tab && tab.command || '',
      includeCommandOutcomeSummary: _commandOutcomeSummariesEnabledForExport(),
    });
  }
  const normalizedRawLines = _normalizeTabTranscriptLines(rawLines);
  const appName = config.app_name || 'darklab_shell';
  return {
    appName,
    title: String(tab && tab.label || ''),
    metaLine: ExportHtmlUtils.buildExportMetaLine({
      label: tab && tab.label,
      createdText: normalizedCreatedText,
    }),
    runMeta: {
      exitCode: tab ? tab.exitCode : null,
      duration: null,
      lines: `${normalizedRawLines.length} lines`,
      version: config.version || null,
    },
    rawLines: normalizedRawLines,
  };
}

async function exportTabHtml(id) {
  _refreshTabExportHtmlUtils();
  const t = _tabExportGetTab(id);
  if (!t || !t.rawLines.length) {
    _tabExportShowToast('No output to export');
    _refocusAfterTabAction();
    return;
  }
  if (!ExportHtmlUtils) {
    _tabExportShowToast('Failed to export html', 'error');
    _refocusAfterTabAction();
    return;
  }
  try {
    const exportModel = _buildTabExportModel(t, { omitRawOnly: true });
    const ansiRenderer = _tabExportCreateAnsiUpRenderer();
    const { linesHtml, prefixWidth, summaryHtml } = ExportHtmlUtils.buildExportLinesHtml(exportModel.rawLines, {
      getPrefix: (line, i) => _exportPrefix(line, i),
      ansiToHtml: (text) => ansiRenderer ? ansiRenderer.ansi_to_html(text) : _tabExportEscapeHtml(String(text ?? '')),
    });
    const [fontFacesCss, exportCss] = await Promise.all([
      ExportHtmlUtils.fetchVendorFontFacesCss().catch(() => ''),
      ExportHtmlUtils.fetchTerminalExportCss().catch(() => ''),
    ]);
    const html = ExportHtmlUtils.buildTerminalExportHtml({
      appName: exportModel.appName,
      title: exportModel.title,
      metaLine: exportModel.metaLine,
      runMeta: exportModel.runMeta,
      linesHtml,
      summaryHtml,
      prefixWidth,
      fontFacesCss,
      exportCss,
    });
    const blob = new Blob([html], { type: 'text/html' });
    _tabExportDownloadBlobAsAttachment(blob, `${exportModel.appName}-${ExportHtmlUtils.exportTimestamp()}.html`);
  } catch {
    _tabExportShowToast('Failed to export html', 'error');
  } finally {
    _refocusAfterTabAction();
  }
}

async function exportTabPdf(id) {
  _refreshTabExportHtmlUtils();
  const t = _tabExportGetTab(id);
  if (!t || !t.rawLines.length) {
    _tabExportShowToast('No output to export');
    _refocusAfterTabAction();
    return;
  }
  const loadPdfUtils = _tabExportGlobalFunction('loadExportPdfUtils');
  if (!loadPdfUtils) {
    _tabExportShowToast('PDF library not loaded', 'error');
    _refocusAfterTabAction();
    return;
  }
  try {
    const pdfUtils = await loadPdfUtils();
    const loadJsPdf = _tabExportGlobalFunction('loadJsPdf');
    const jsPDF = loadJsPdf
      ? await loadJsPdf()
      : await pdfUtils.loadJsPdf();
    const exportModel = _buildTabExportModel(t, { omitRawOnly: true });
    const ansiRenderer = _tabExportCreateAnsiUpRenderer();
    const doc = await pdfUtils.buildTerminalExportPdf({
      jsPDF,
      appName: exportModel.appName,
      metaLine: exportModel.metaLine,
      runMeta: exportModel.runMeta,
      rawLines: exportModel.rawLines,
      getPrefix: (line, i) => _exportPrefix(line, i),
      ansiToHtml: (text) => ansiRenderer ? ansiRenderer.ansi_to_html(text) : _tabExportEscapeHtml(String(text ?? '')),
    });
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    doc.save(`${exportModel.appName}-${ts}.pdf`);
  } catch {
    _tabExportShowToast('Failed to export pdf', 'error');
  } finally {
    _refocusAfterTabAction();
  }
}

function _shareLinesWithoutTruncationNotices(lines) {
  return _normalizeTabTranscriptLines(lines, { stripTruncationNotices: true });
}

function _extractLatestFullRunShareContent(tab, fullRun) {
  const rawLines = Array.isArray(tab.rawLines) ? tab.rawLines : [];
  const runStartIndex = typeof tab.currentRunStartIndex === 'number' && tab.currentRunStartIndex >= 0
    ? tab.currentRunStartIndex
    : rawLines.length;
  const exitIndex = (() => {
    for (let i = rawLines.length - 1; i >= 0; i -= 1) {
      const event = ExportHtmlUtils && typeof ExportHtmlUtils.lineEventFromWire === 'function'
        ? ExportHtmlUtils.lineEventFromWire(rawLines[i])
        : { role: String(rawLines[i] && rawLines[i].role || rawLines[i] && rawLines[i].cls || '') };
      if (['exit-ok', 'exit-fail'].includes(String(event.role || ''))) return i;
    }
    return rawLines.length;
  })();
  const fullOutput = Array.isArray(fullRun && fullRun.output_entries)
    ? fullRun.output_entries
    : _shareLinesWithoutTruncationNotices(fullRun && fullRun.output);

  return [
    ..._shareLinesWithoutTruncationNotices(rawLines.slice(0, runStartIndex)),
    ..._shareLinesWithoutTruncationNotices(fullOutput),
    ..._shareLinesWithoutTruncationNotices(rawLines.slice(exitIndex)),
  ];
}

function _shareSnapshotLabel(tab) {
  if (!tab) return 'snapshot';
  const customLabel = String(tab.label || '').trim();
  const latestCommand = String(tab.command || '').trim();
  if (tab.renamed && customLabel) return customLabel;
  return latestCommand || customLabel || 'snapshot';
}

function _canCreateShareSnapshot() {
  return _tabExportActiveTeamScopeCan('manage_history');
}

function _shareSnapshotDeniedMessage() {
  return _tabExportTeamScopeDeniedMessage('create team history snapshots')
    || "View-only team members can't create team history snapshots. Switch to Personal or ask for operator access.";
}

async function permalinkTab(id) {
  _refreshTabExportHtmlUtils();
  if (!_canCreateShareSnapshot()) {
    _tabExportShowToast(_shareSnapshotDeniedMessage(), 'error');
    _refocusAfterTabAction();
    return;
  }
  const t = _tabExportGetTab(id);
  if (!t || !t.rawLines.length) {
    _tabExportShowToast('No output to share yet');
    return;
  }
  const redactionMode = await _tabExportConfirmRedactionChoice();
  if (redactionMode !== 'raw' && redactionMode !== 'redacted') {
    _refocusAfterTabAction();
    return;
  }
  let shareContent = _shareLinesWithoutTruncationNotices(t.rawLines);
  if (t.fullOutputAvailable && !t.fullOutputLoaded && t.historyRunId) {
    try {
      const res = await _tabExportApiFetch(`/history/${t.historyRunId}?json`);
      const fullRun = await res.json();
      shareContent = _extractLatestFullRunShareContent(t, fullRun);
    } catch {
      shareContent = _shareLinesWithoutTruncationNotices(t.rawLines);
    }
  }
  const applyRedaction = redactionMode === 'redacted';
  if (applyRedaction) shareContent = _getRedactedLines(shareContent);
  _tabExportApiFetch('/share', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      label: _shareSnapshotLabel(t),
      content: shareContent,
      apply_redaction: applyRedaction,
      run_id: String(t.historyRunId || ''),
    })
  }).then(async (r) => {
    const data = await r.json();
    if (r.ok === false || !data || typeof data.url !== 'string') {
      throw new Error((data && (data.error || data.message)) || 'share failed');
    }
    return data;
  }).then(data => {
    const url = `${location.origin}${data.url}`;
    _tabExportShareUrl(url).catch(() => _tabExportShowToast('Failed to copy link', 'error'));
  }).catch(() => _tabExportShowToast('Failed to create permalink', 'error'))
    .finally(() => {
      _refocusAfterTabAction();
    });
}

export {
  _appendTabCommandOutcomeSummaryLines,
  _buildTabExportModel,
  _canCreateShareSnapshot,
  _commandOutcomeSummariesEnabledForExport,
  _exportPrefix,
  _extractLatestFullRunShareContent,
  _getExportableRawLines,
  _getRedactedLines,
  _getShareRedactionRules,
  _normalizeTabTranscriptLine,
  _normalizeTabTranscriptLines,
  _omitRawOnlyExportLines,
  _refocusAfterTabAction,
  _shareLinesWithoutTruncationNotices,
  _shareRedactionEnabled,
  _shareSnapshotDeniedMessage,
  _shareSnapshotLabel,
  _stripTabExportAnsi,
  copyTab,
  exportTabHtml,
  exportTabPdf,
  permalinkTab,
  saveTab,
};
