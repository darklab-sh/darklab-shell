// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Lightweight export facade for the shell. The full HTML/PDF formatter is
// loaded only when an export action needs it.
import { DarklabOutputCore as importedOutputCore } from './core/output_core.js';
import { DarklabRunOutputModel as importedRunOutputModel } from './core/run_output_model.js';
import { loadExportHtmlUtils as importedLoadExportHtmlUtils } from './core/lazy_assets.js';

const EXPORT_HTML_GLOBAL = typeof window !== 'undefined' ? window : globalThis;
let loadedExportHtmlUtils = null;

function _currentExportHtmlUtils() {
  const globalUtils = EXPORT_HTML_GLOBAL && EXPORT_HTML_GLOBAL.ExportHtmlUtils;
  if (globalUtils && globalUtils !== ExportHtmlUtils) return globalUtils;
  return loadedExportHtmlUtils && loadedExportHtmlUtils !== ExportHtmlUtils
    ? loadedExportHtmlUtils
    : null;
}

function _delegateExportHtmlMethod(name, fallback) {
  const utils = _currentExportHtmlUtils();
  const fn = utils && utils[name];
  return typeof fn === 'function' ? fn.bind(utils) : fallback;
}

function _runOutputModel() {
  return (typeof importedRunOutputModel !== 'undefined' && importedRunOutputModel) || null;
}

function _outputCore() {
  return (typeof importedOutputCore !== 'undefined' && importedOutputCore) || null;
}

function _fallbackLineEvent(line) {
  const cls = String(line && line.cls || '');
  return {
    text: String(line && line.text || ''),
    cls,
    kind: String(line && line.kind || (cls === 'notice' ? 'notice' : 'info')),
    role: String(line && line.role || (['prompt-echo', 'denied', 'exit-ok', 'exit-fail'].includes(cls) ? cls : 'body')),
    tsC: String(line && line.tsC || ''),
    tsE: String(line && line.tsE || ''),
    signals: Array.isArray(line && line.signals) ? line.signals.map(signal => String(signal || '')).filter(Boolean) : [],
    entities: Array.isArray(line && line.entities) ? line.entities : [],
    line_number: Number.isInteger(line && line.line_number) ? line.line_number : undefined,
  };
}

function lineEventFromWire(line) {
  const delegated = _delegateExportHtmlMethod('lineEventFromWire', null);
  if (delegated) return delegated(line);
  const model = _runOutputModel();
  if (model && typeof model.fromWireLineEvent === 'function') {
    const event = model.fromWireLineEvent(line || {});
    event.cls = lineLegacyClass(event);
    event.tsC = event.ts_clock || '';
    event.tsE = event.ts_elapsed || '';
    event.signals = Array.isArray(event.signals) ? event.signals : [];
    event.entities = Array.isArray(event.entities) ? event.entities : [];
    if (Number.isInteger(line && line.line_number)) event.line_number = line.line_number;
    return event;
  }
  return _fallbackLineEvent(line || {});
}

function lineLegacyClass(event) {
  const delegated = _delegateExportHtmlMethod('lineLegacyClass', null);
  if (delegated) return delegated(event);
  const model = _runOutputModel();
  if (model && typeof model.toLegacyWireLineEvent === 'function') {
    return String(model.toLegacyWireLineEvent(event || {}).cls || '');
  }
  return String(event && (event.legacy_cls || event.cls || (event.role !== 'body' ? event.role : event.kind !== 'info' ? event.kind : '')) || '');
}

function isPromptEchoEvent(event) {
  const delegated = _delegateExportHtmlMethod('isPromptEchoEvent', null);
  if (delegated) return delegated(event);
  return String(event && event.role || '') === 'prompt-echo';
}

function isPlainEvent(event) {
  const delegated = _delegateExportHtmlMethod('isPlainEvent', null);
  if (delegated) return delegated(event);
  const role = String(event && event.role || 'body');
  const kind = String(event && event.kind || 'info');
  return ['exit-ok', 'exit-fail', 'denied'].includes(role) || kind === 'notice';
}

function escapeExportHtml(text) {
  const delegated = _delegateExportHtmlMethod('escapeExportHtml', null);
  if (delegated) return delegated(text);
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function escapeExportAttr(text) {
  const delegated = _delegateExportHtmlMethod('escapeExportAttr', null);
  if (delegated) return delegated(text);
  return escapeExportHtml(text)
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderExportPromptEcho(text) {
  const delegated = _delegateExportHtmlMethod('renderExportPromptEcho', null);
  if (delegated) return delegated(text);
  const raw = String(text || '');
  const firstSpace = raw.indexOf(' ');
  const prefix = firstSpace === -1 ? raw : raw.slice(0, firstSpace);
  const remainder = firstSpace === -1 ? '' : raw.slice(firstSpace + 1);
  return '<span class="prompt-prefix">' + escapeExportHtml(prefix) + '</span>'
    + (remainder ? escapeExportHtml(' ' + remainder) : '');
}

function _exportEntityRanges(text, entities) {
  const length = String(text || '').length;
  return (Array.isArray(entities) ? entities : [])
    .map((entity) => {
      const start = Number(entity && entity.start);
      const end = Number(entity && entity.end);
      if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start || end > length) {
        return null;
      }
      return { start, end, entity };
    })
    .filter(Boolean)
    .sort((a, b) => a.start - b.start || a.end - b.end)
    .reduce((ranges, range) => {
      const previous = ranges[ranges.length - 1];
      if (previous && range.start < previous.end) return ranges;
      ranges.push(range);
      return ranges;
    }, []);
}

function renderExportEntityContent(text, entities, ansiToHtml) {
  const delegated = _delegateExportHtmlMethod('renderExportEntityContent', null);
  if (delegated) return delegated(text, entities, ansiToHtml);
  const raw = String(text || '');
  const renderAnsi = typeof ansiToHtml === 'function' ? ansiToHtml : escapeExportHtml;
  const ranges = _exportEntityRanges(raw, entities);
  if (!ranges.length) return renderAnsi(raw);
  let cursor = 0;
  let html = '';
  ranges.forEach((range) => {
    if (range.start > cursor) html += renderAnsi(raw.slice(cursor, range.start));
    const entity = range.entity || {};
    const entityType = String(entity.type || '');
    const entityValue = String(entity.canonical_value || entity.value || raw.slice(range.start, range.end));
    const tokenText = raw.slice(range.start, range.end);
    html += '<span class="export-entity-token"'
      + ' data-entity-type="' + escapeExportAttr(entityType) + '"'
      + ' data-entity-value="' + escapeExportAttr(entityValue) + '"'
      + ' title="Entity: ' + escapeExportAttr(entityValue) + '">'
      + renderAnsi(tokenText)
      + '</span>';
    cursor = range.end;
  });
  if (cursor < raw.length) html += renderAnsi(raw.slice(cursor));
  return html;
}

function _exportLineBadgeHtml(line) {
  const kind = String(line && line.kind || 'info');
  const signals = Array.isArray(line && line.signals) ? line.signals.map(String) : [];
  if (kind === 'error') return '<span class="line-severity-badge line-severity-error">error</span>';
  if (kind === 'warn') return '<span class="line-severity-badge line-severity-warn">warn</span>';
  if (signals.includes('findings')) return '<span class="line-severity-badge line-severity-finding">finding</span>';
  return '';
}

function renderExportLineContent(line, ansiToHtml) {
  const delegated = _delegateExportHtmlMethod('renderExportLineContent', null);
  if (delegated) return delegated(line, ansiToHtml);
  const lineEvent = lineEventFromWire(line);
  const text = String(lineEvent.text || '');
  let content;
  if (isPromptEchoEvent(lineEvent)) {
    content = renderExportPromptEcho(text);
  } else if (isPlainEvent(lineEvent)) {
    content = escapeExportHtml(text);
  } else {
    content = renderExportEntityContent(text, lineEvent.entities, ansiToHtml);
  }
  return _exportLineBadgeHtml(lineEvent) + content;
}

function exportTimestamp() {
  const delegated = _delegateExportHtmlMethod('exportTimestamp', null);
  if (delegated) return delegated();
  return new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
}

function buildExportMetaLine({ label = '', createdText = '' } = {}) {
  const delegated = _delegateExportHtmlMethod('buildExportMetaLine', null);
  if (delegated) return delegated({ label, createdText });
  const trimmedLabel = String(label || '').trim();
  const trimmedCreated = String(createdText || '').trim();
  if (trimmedLabel && trimmedCreated) return `${trimmedLabel} · ${trimmedCreated}`;
  return trimmedLabel || trimmedCreated;
}

function normalizeExportTranscriptLine(line) {
  const delegated = _delegateExportHtmlMethod('normalizeExportTranscriptLine', null);
  if (delegated) return delegated(line);
  if (typeof line === 'string') return lineEventFromWire({ text: line });
  if (line && typeof line.text === 'string') return lineEventFromWire(line);
  return null;
}

function normalizeExportTranscriptLines(lines, { stripTruncationNotices = false } = {}) {
  const delegated = _delegateExportHtmlMethod('normalizeExportTranscriptLines', null);
  if (delegated) return delegated(lines, { stripTruncationNotices });
  return (Array.isArray(lines) ? lines : [])
    .map(normalizeExportTranscriptLine)
    .filter((line) => {
      if (!line) return false;
      if (!stripTruncationNotices) return true;
      return !/^\[(?:preview|tab output) truncated/i.test(String(line.text || ''));
    });
}

function isCommandOutcomeSummaryLine(line) {
  const delegated = _delegateExportHtmlMethod('isCommandOutcomeSummaryLine', null);
  if (delegated) return delegated(line);
  const cls = String(line && line.cls || line && line.legacy_cls || '');
  return cls.split(/\s+/).includes('command-outcome-summary')
    || Boolean(line && line.command_outcome_summary === true);
}

function commandOutcomeItemText(item) {
  if (!item || typeof item !== 'object') return '';
  const label = String(item.label || '').trim();
  const value = String(item.value || '').trim();
  if (label && value) return `${label}: ${value}`;
  return value || label;
}

function buildExportCommandOutcomeSummary(command, rawLines) {
  const delegated = _delegateExportHtmlMethod('buildExportCommandOutcomeSummary', null);
  if (delegated) return delegated(command, rawLines);
  const core = _outputCore();
  if (!core || typeof core.buildCommandOutcomeSummary !== 'function') return null;
  const normalizer = typeof core.normalizeCommandOutcomeSummary === 'function'
    ? core.normalizeCommandOutcomeSummary
    : (value) => value;
  return normalizer(core.buildCommandOutcomeSummary(command, rawLines));
}

function commandOutcomeSummaryToLines(summary) {
  const delegated = _delegateExportHtmlMethod('commandOutcomeSummaryToLines', null);
  if (delegated) return delegated(summary);
  if (!summary || !Array.isArray(summary.items) || !summary.items.length) return [];
  const lines = [];
  const title = String(summary.title || 'Command outcome').trim() || 'Command outcome';
  lines.push({
    text: title,
    cls: 'command-outcome-summary command-outcome-summary-title',
    command_outcome_summary: true,
  });
  summary.items.forEach((item) => {
    const text = commandOutcomeItemText(item);
    if (!text) return;
    lines.push({
      text,
      cls: 'command-outcome-summary command-outcome-summary-row',
      command_outcome_summary: true,
    });
  });
  return lines;
}

function appendCommandOutcomeSummaryLines(rawLines, { command = '', enabled = true } = {}) {
  const delegated = _delegateExportHtmlMethod('appendCommandOutcomeSummaryLines', null);
  if (delegated) return delegated(rawLines, { command, enabled });
  const normalized = normalizeExportTranscriptLines(rawLines);
  if (!enabled || normalized.some(isCommandOutcomeSummaryLine)) return normalized;
  const summary = buildExportCommandOutcomeSummary(command, normalized);
  if (!summary) return normalized;
  return normalized.concat(commandOutcomeSummaryToLines(summary));
}

function normalizeExportRunMeta(runMeta) {
  const delegated = _delegateExportHtmlMethod('normalizeExportRunMeta', null);
  if (delegated) return delegated(runMeta);
  if (!runMeta) return null;
  return {
    exitCode: runMeta.exitCode !== undefined ? runMeta.exitCode : runMeta.exit_code,
    duration: runMeta.duration || null,
    lines: runMeta.lines || null,
    version: runMeta.version || null,
  };
}

function buildExportDocumentModel({
  appName = '',
  title = '',
  label = '',
  createdText = '',
  runMeta = null,
  rawLines = [],
  command = '',
  includeCommandOutcomeSummary = false,
} = {}) {
  const delegated = _delegateExportHtmlMethod('buildExportDocumentModel', null);
  if (delegated) {
    return delegated({
      appName,
      title,
      label,
      createdText,
      runMeta,
      rawLines,
      command,
      includeCommandOutcomeSummary,
    });
  }
  return {
    appName: String(appName || ''),
    title: String(title || ''),
    metaLine: buildExportMetaLine({ label, createdText }),
    runMeta: normalizeExportRunMeta(runMeta),
    rawLines: includeCommandOutcomeSummary
      ? appendCommandOutcomeSummaryLines(rawLines, { command, enabled: true })
      : normalizeExportTranscriptLines(rawLines),
  };
}

function _requireLoadedMethod(name) {
  const delegated = _delegateExportHtmlMethod(name, null);
  if (delegated) return delegated;
  throw new Error(`Export HTML formatter is not loaded: ${name}`);
}

async function loadExportHtmlUtils() {
  const current = _currentExportHtmlUtils();
  if (current && typeof current.buildTerminalExportHtml === 'function') {
    loadedExportHtmlUtils = current;
    return current;
  }
  if (typeof importedLoadExportHtmlUtils !== 'function') {
    throw new Error('Export HTML formatter loader is not available.');
  }
  const loaded = await importedLoadExportHtmlUtils();
  loadedExportHtmlUtils = loaded && loaded.ExportHtmlUtils ? loaded.ExportHtmlUtils : loaded;
  return loadedExportHtmlUtils;
}

const ExportHtmlUtils = {
  isLazyExportHtmlBridge: true,
  appendCommandOutcomeSummaryLines,
  buildExportCommandOutcomeSummary,
  buildExportDocumentModel,
  buildExportMetaLine,
  commandOutcomeSummaryToLines,
  escapeExportAttr,
  escapeExportHtml,
  exportTimestamp,
  isCommandOutcomeSummaryLine,
  isPlainEvent,
  isPromptEchoEvent,
  lineEventFromWire,
  lineLegacyClass,
  normalizeExportRunMeta,
  normalizeExportTranscriptLine,
  normalizeExportTranscriptLines,
  buildExportHeaderModel: (...args) => _requireLoadedMethod('buildExportHeaderModel')(...args),
  buildExportLineSummary: (...args) => _requireLoadedMethod('buildExportLineSummary')(...args),
  buildExportLinesHtml: (...args) => _requireLoadedMethod('buildExportLinesHtml')(...args),
  buildExportRunMetaHtml: (...args) => _requireLoadedMethod('buildExportRunMetaHtml')(...args),
  buildExportRunMetaItems: (...args) => _requireLoadedMethod('buildExportRunMetaItems')(...args),
  buildTerminalExportHeaderHtml: (...args) => _requireLoadedMethod('buildTerminalExportHeaderHtml')(...args),
  buildTerminalExportHtml: (...args) => _requireLoadedMethod('buildTerminalExportHtml')(...args),
  buildTerminalExportStyles: (...args) => _requireLoadedMethod('buildTerminalExportStyles')(...args),
  fetchTerminalExportCss: (...args) => _requireLoadedMethod('fetchTerminalExportCss')(...args),
  fetchVendorFontFacesCss: (...args) => _requireLoadedMethod('fetchVendorFontFacesCss')(...args),
  getThemeExportColorScheme: (...args) => _requireLoadedMethod('getThemeExportColorScheme')(...args),
  getThemeExportVars: (...args) => _requireLoadedMethod('getThemeExportVars')(...args),
  renderExportEntityContent,
  renderExportLineContent,
  renderExportPromptEcho,
};

if (EXPORT_HTML_GLOBAL && !EXPORT_HTML_GLOBAL.ExportHtmlUtils) {
  EXPORT_HTML_GLOBAL.ExportHtmlUtils = ExportHtmlUtils;
}

export {
  ExportHtmlUtils,
  appendCommandOutcomeSummaryLines,
  buildExportCommandOutcomeSummary,
  buildExportDocumentModel,
  buildExportMetaLine,
  commandOutcomeSummaryToLines,
  escapeExportAttr,
  escapeExportHtml,
  exportTimestamp,
  isCommandOutcomeSummaryLine,
  isPlainEvent,
  isPromptEchoEvent,
  lineEventFromWire,
  lineLegacyClass,
  loadExportHtmlUtils,
  normalizeExportRunMeta,
  normalizeExportTranscriptLine,
  normalizeExportTranscriptLines,
  renderExportEntityContent,
  renderExportLineContent,
  renderExportPromptEcho,
};
