;
/* /static/js/core/run_output_model.js */
var DarklabRunOutputModel = (function (global) {
  'use strict';

  const LINE_EVENT_SCHEMA_VERSION = 1;
  const LINE_KIND_VALUES = Object.freeze(['info', 'notice', 'warn', 'error']);
  const LINE_ROLE_VALUES = Object.freeze([
    'body',
    'prompt-echo',
    'section-header',
    'kv',
    'help-row',
    'pty-marker',
    'progress',
    'status-line',
    'success',
    'denied',
    'exit-ok',
    'exit-fail',
  ]);
  const LINE_SIGNAL_VALUES = Object.freeze(['findings', 'warnings', 'errors', 'summaries']);
  const LINE_NOISE_KIND_VALUES = Object.freeze(['progress', 'status', 'boilerplate']);

  const LineKind = Object.freeze({
    INFO: 'info',
    NOTICE: 'notice',
    WARN: 'warn',
    ERROR: 'error',
  });

  const LineRole = Object.freeze({
    BODY: 'body',
    PROMPT_ECHO: 'prompt-echo',
    SECTION_HEADER: 'section-header',
    KV: 'kv',
    HELP_ROW: 'help-row',
    PTY_MARKER: 'pty-marker',
    PROGRESS: 'progress',
    STATUS_LINE: 'status-line',
    SUCCESS: 'success',
    DENIED: 'denied',
    EXIT_OK: 'exit-ok',
    EXIT_FAIL: 'exit-fail',
  });

  const LineSignal = Object.freeze({
    FINDINGS: 'findings',
    WARNINGS: 'warnings',
    ERRORS: 'errors',
    SUMMARIES: 'summaries',
  });

  const LineNoiseKind = Object.freeze({
    PROGRESS: 'progress',
    STATUS: 'status',
    BOILERPLATE: 'boilerplate',
  });

  const LEGACY_KIND_BY_CLS = Object.freeze({
    '': LineKind.INFO,
    output: LineKind.INFO,
    out: LineKind.INFO,
    cmd: LineKind.INFO,
    notice: LineKind.NOTICE,
    'builtin-note': LineKind.NOTICE,
    'welcome-output': LineKind.NOTICE,
    warn: LineKind.WARN,
    warning: LineKind.WARN,
    error: LineKind.ERROR,
  });

  const LEGACY_ROLE_BY_CLS = Object.freeze({
    '': LineRole.BODY,
    output: LineRole.BODY,
    out: LineRole.BODY,
    notice: LineRole.BODY,
    warn: LineRole.BODY,
    warning: LineRole.BODY,
    error: LineRole.BODY,
    'builtin-note': LineRole.BODY,
    'builtin-spacer': LineRole.BODY,
    'welcome-output': LineRole.BODY,
    cmd: LineRole.PROMPT_ECHO,
    'prompt-echo': LineRole.PROMPT_ECHO,
    'builtin-section': LineRole.SECTION_HEADER,
    'builtin-kv': LineRole.KV,
    'builtin-help-row': LineRole.HELP_ROW,
    'builtin-faq-q': LineRole.HELP_ROW,
    'builtin-faq-a': LineRole.HELP_ROW,
    'pty-marker': LineRole.PTY_MARKER,
    progress: LineRole.PROGRESS,
    'status-line': LineRole.STATUS_LINE,
    'builtin-success': LineRole.SUCCESS,
    denied: LineRole.DENIED,
    'exit-ok': LineRole.EXIT_OK,
    'exit-fail': LineRole.EXIT_FAIL,
  });

  const KIND_LEGACY_CLS = Object.freeze({
    info: '',
    notice: 'notice',
    warn: 'warn',
    error: 'error',
  });

  const ROLE_LEGACY_CLS = Object.freeze({
    body: '',
    'prompt-echo': 'prompt-echo',
    'section-header': 'builtin-section',
    kv: 'builtin-kv',
    'help-row': 'builtin-help-row',
    'pty-marker': 'pty-marker',
    progress: 'progress',
    'status-line': 'status-line',
    success: 'builtin-success',
    denied: 'denied',
    'exit-ok': 'exit-ok',
    'exit-fail': 'exit-fail',
  });

  const NOISE_KIND_BY_ROLE = Object.freeze({
    progress: LineNoiseKind.PROGRESS,
    'status-line': LineNoiseKind.STATUS,
  });

  function legacyClsTokens(value) {
    const text = String(value || '').trim();
    if (!text) return [''];
    return text.split(/\s+/).filter(Boolean);
  }

  function legacyClsToKind(value) {
    const tokens = legacyClsTokens(value);
    for (const token of tokens) {
      if (Object.prototype.hasOwnProperty.call(LEGACY_KIND_BY_CLS, token)) return LEGACY_KIND_BY_CLS[token];
    }
    return LineKind.INFO;
  }

  function legacyClsToRole(value) {
    const tokens = legacyClsTokens(value);
    for (const token of tokens) {
      if (Object.prototype.hasOwnProperty.call(LEGACY_ROLE_BY_CLS, token)) return LEGACY_ROLE_BY_CLS[token];
    }
    return LineRole.BODY;
  }

  function collectUnknown(unknownCollector, family, value) {
    if (typeof unknownCollector === 'function') unknownCollector(family, String(value));
  }

  function enumValue(values, value, fallback, family, unknownCollector) {
    if (value === undefined || value === null || value === '') return fallback;
    const stringValue = String(value);
    if (values.includes(stringValue)) return stringValue;
    collectUnknown(unknownCollector, family, stringValue);
    return fallback;
  }

  function optionalInt(value) {
    if (value === undefined || value === null || typeof value === 'boolean') return null;
    const parsed = Number.parseInt(String(value), 10);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function entityFromWire(payload) {
    if (!payload || typeof payload !== 'object') return null;
    const type = String(payload.type || '').trim();
    const canonicalValue = String(payload.canonical_value || '').trim();
    if (!type || !canonicalValue) return null;
    let start = optionalInt(payload.start);
    let end = optionalInt(payload.end);
    if (start === null || end === null) {
      start = null;
      end = null;
    }
    return {
      type,
      value: String(payload.value || '').trim() || canonicalValue,
      canonical_value: canonicalValue,
      confidence: String(payload.confidence || '').trim() || 'medium',
      source_line: optionalInt(payload.source_line),
      start,
      end,
    };
  }

  function entityToWire(entity) {
    const payload = {
      type: entity.type,
      value: entity.value,
      canonical_value: entity.canonical_value,
      confidence: entity.confidence,
    };
    if (entity.source_line !== null && entity.source_line !== undefined) payload.source_line = entity.source_line;
    if (entity.start !== null && entity.start !== undefined) payload.start = entity.start;
    if (entity.end !== null && entity.end !== undefined) payload.end = entity.end;
    return payload;
  }

  function signalsFromWire(value, unknownCollector) {
    if (!Array.isArray(value)) return [];
    const signals = [];
    value.forEach((item) => {
      const signal = String(item);
      if (LINE_SIGNAL_VALUES.includes(signal)) {
        signals.push(signal);
      } else {
        collectUnknown(unknownCollector, 'signal', signal);
      }
    });
    return signals;
  }

  function entitiesFromWire(value) {
    if (!Array.isArray(value)) return [];
    return value.map(entityFromWire).filter(Boolean);
  }

  function legacyClsForEvent(event) {
    if (event.legacy_cls) return String(event.legacy_cls);
    const role = event.role || LineRole.BODY;
    if (role !== LineRole.BODY) return ROLE_LEGACY_CLS[role] || '';
    return KIND_LEGACY_CLS[event.kind || LineKind.INFO] || '';
  }

  function noiseKindForRole(role) {
    return NOISE_KIND_BY_ROLE[role] || null;
  }

  function noiseKindForEvent(event) {
    if (!event || (Array.isArray(event.signals) && event.signals.length)) return null;
    if (event.kind === LineKind.WARN || event.kind === LineKind.ERROR) return null;
    if (event.noise_kind) return event.noise_kind;
    return noiseKindForRole(event.role || LineRole.BODY);
  }

  function isNoiseLineEvent(event) {
    return noiseKindForEvent(event) !== null;
  }

  function legacyPayload(event) {
    const payload = {
      text: String(event.text || ''),
      cls: legacyClsForEvent(event),
      tsC: String(event.ts_clock || event.tsC || ''),
      tsE: String(event.ts_elapsed || event.tsE || ''),
    };
    if (Array.isArray(event.signals) && event.signals.length) payload.signals = event.signals.slice();
    if (event.line_index !== null && event.line_index !== undefined) payload.line_index = event.line_index;
    if (event.command_root) payload.command_root = String(event.command_root);
    if (event.target) payload.target = String(event.target);
    if (Array.isArray(event.entities) && event.entities.length) payload.entities = event.entities.map(entityToWire);
    const noiseKind = noiseKindForEvent(event);
    if (noiseKind) {
      payload.noise_kind = noiseKind;
      if (event.noise_reason) payload.noise_reason = String(event.noise_reason);
    }
    return payload;
  }

  function fromWireLineEvent(payload, unknownCollector) {
    const item = payload && typeof payload === 'object' ? payload : {};
    const clsValue = item.cls || '';
    const kind = enumValue(LINE_KIND_VALUES, item.kind, legacyClsToKind(clsValue), 'kind', unknownCollector);
    const role = enumValue(LINE_ROLE_VALUES, item.role, legacyClsToRole(clsValue), 'role', unknownCollector);
    const noiseKind = enumValue(
      LINE_NOISE_KIND_VALUES,
      item.noise_kind,
      noiseKindForRole(role),
      'noise_kind',
      unknownCollector,
    );
    return {
      text: String(item.text || ''),
      kind,
      role,
      legacy_cls: String(clsValue || ''),
      ts_clock: String(item.tsC || ''),
      ts_elapsed: String(item.tsE || ''),
      signals: signalsFromWire(item.signals, unknownCollector),
      line_index: optionalInt(item.line_index),
      command_root: String(item.command_root || ''),
      target: String(item.target || ''),
      entities: entitiesFromWire(item.entities),
      noise_kind: noiseKind,
      noise_reason: noiseKind ? String(item.noise_reason || '') : '',
    };
  }

  function toLegacyWireLineEvent(event) {
    return legacyPayload(event || {});
  }

  function toWireLineEvent(event) {
    const payload = legacyPayload(event || {});
    payload.v = LINE_EVENT_SCHEMA_VERSION;
    payload.kind = (event && event.kind) || LineKind.INFO;
    payload.role = (event && event.role) || LineRole.BODY;
    return payload;
  }

  function eventSearchText(event) {
    return String((event && event.text) || '');
  }

  const api = Object.freeze({
    LINE_EVENT_SCHEMA_VERSION,
    LINE_KIND_VALUES,
    LINE_NOISE_KIND_VALUES,
    LINE_ROLE_VALUES,
    LINE_SIGNAL_VALUES,
    LineKind,
    LineNoiseKind,
    LineRole,
    LineSignal,
    eventSearchText,
    fromWireLineEvent,
    isNoiseLineEvent,
    legacyClsToKind,
    legacyClsToRole,
    noiseKindForEvent,
    noiseKindForRole,
    toLegacyWireLineEvent,
    toWireLineEvent,
  });

  global.DarklabRunOutputModel = api;
  return api;
})(typeof window !== 'undefined' ? window : globalThis);
;
;
/* /static/js/export_html.js */
// ── Shared HTML export helpers ───────────────────────────────────────────────
// Single source of truth for all export formatting (save html, save pdf,
// permalink save html). All callers go through these helpers so the rendered
// output is consistent across every save surface.
(function () {
  // HTML export deliberately inlines the runtime theme variables so downloaded
  // files preserve the active palette without depending on the live app shell.
  const EXPORT_FONT_FILES = [
    { family: 'JetBrains Mono', weight: 300, filename: 'JetBrainsMono-300.ttf' },
    { family: 'JetBrains Mono', weight: 400, filename: 'JetBrainsMono-400.ttf' },
    { family: 'JetBrains Mono', weight: 700, filename: 'JetBrainsMono-700.ttf' },
    { family: 'Syne', weight: 700, filename: 'Syne-700.ttf' },
    { family: 'Syne', weight: 800, filename: 'Syne-800.ttf' },
  ];
  const EXPORT_THEME_VAR_NAMES = [
    '--bg',
    '--surface',
    '--border',
    '--border-bright',
    '--text',
    '--muted',
    '--green',
    '--green-dim',
    '--green-glow',
    '--amber',
    '--red',
    '--blue',
    '--theme-panel-bg',
    '--theme-panel-border',
    '--theme-panel-shadow',
    '--theme-terminal-bar-bg',
    '--terminal-font-size',
    '--terminal-line-height',
  ];
  function runOutputModel() {
    return window.DarklabRunOutputModel || null;
  }

  function fallbackLineEvent(line) {
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
    const model = runOutputModel();
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
    return fallbackLineEvent(line || {});
  }

  function lineLegacyClass(event) {
    const model = runOutputModel();
    if (model && typeof model.toLegacyWireLineEvent === 'function') {
      return String(model.toLegacyWireLineEvent(event || {}).cls || '');
    }
    return String(event && (event.legacy_cls || event.cls || (event.role !== 'body' ? event.role : event.kind !== 'info' ? event.kind : '')) || '');
  }

  function isPromptEchoEvent(event) {
    return String(event && event.role || '') === 'prompt-echo';
  }

  function isPlainEvent(event) {
    const role = String(event && event.role || 'body');
    const kind = String(event && event.kind || 'info');
    return ['exit-ok', 'exit-fail', 'denied'].includes(role) || kind === 'notice';
  }

  function escapeExportHtml(text) {
    return String(text ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function escapeExportAttr(text) {
    return escapeExportHtml(text)
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderExportPromptEcho(text) {
    const raw = String(text || '');
    const firstSpace = raw.indexOf(' ');
    const prefix = firstSpace === -1 ? raw : raw.slice(0, firstSpace);
    const remainder = firstSpace === -1 ? '' : raw.slice(firstSpace + 1);
    return '<span class="prompt-prefix">' + escapeExportHtml(prefix) + '</span>'
      + (remainder ? escapeExportHtml(' ' + remainder) : '');
  }

  function exportEntityRanges(text, entities) {
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
    const raw = String(text || '');
    const ranges = exportEntityRanges(raw, entities);
    if (!ranges.length) return ansiToHtml(raw);
    let cursor = 0;
    let html = '';
    ranges.forEach((range) => {
      if (range.start > cursor) html += ansiToHtml(raw.slice(cursor, range.start));
      const entity = range.entity || {};
      const entityType = String(entity.type || '');
      const entityValue = String(entity.canonical_value || entity.value || raw.slice(range.start, range.end));
      const tokenText = raw.slice(range.start, range.end);
      html += '<span class="export-entity-token"'
        + ' data-entity-type="' + escapeExportAttr(entityType) + '"'
        + ' data-entity-value="' + escapeExportAttr(entityValue) + '"'
        + ' title="Entity: ' + escapeExportAttr(entityValue) + '">'
        + ansiToHtml(tokenText)
        + '</span>';
      cursor = range.end;
    });
    if (cursor < raw.length) html += ansiToHtml(raw.slice(cursor));
    return html;
  }

  function exportLineBadgeHtml(line) {
    const kind = String(line && line.kind || 'info');
    const signals = Array.isArray(line && line.signals) ? line.signals.map(String) : [];
    if (kind === 'error') return '<span class="line-severity-badge line-severity-error">error</span>';
    if (kind === 'warn') return '<span class="line-severity-badge line-severity-warn">warn</span>';
    if (signals.includes('findings')) return '<span class="line-severity-badge line-severity-finding">finding</span>';
    return '';
  }

  function buildExportLineSummary(rawLines) {
    const summary = {
      findings: 0,
      warnings: 0,
      errors: 0,
      entityTypes: {},
    };
    rawLines.forEach((rawLine) => {
      const line = lineEventFromWire(rawLine);
      const signals = Array.isArray(line.signals) ? line.signals.map(String) : [];
      if (signals.includes('findings')) summary.findings += 1;
      if (line.kind === 'warn') summary.warnings += 1;
      if (line.kind === 'error') summary.errors += 1;
      (Array.isArray(line.entities) ? line.entities : []).forEach((entity) => {
        const type = String(entity && entity.type || '').trim();
        if (type) summary.entityTypes[type] = (summary.entityTypes[type] || 0) + 1;
      });
    });
    return summary;
  }

  function buildExportSummaryHtml(summary) {
    const chips = [];
    if (summary.findings) chips.push(`findings ${summary.findings}`);
    if (summary.errors) chips.push(`errors ${summary.errors}`);
    if (summary.warnings) chips.push(`warnings ${summary.warnings}`);
    Object.entries(summary.entityTypes || {})
      .sort((a, b) => a[0].localeCompare(b[0]))
      .slice(0, 8)
      .forEach(([type, count]) => chips.push(`${type} ${count}`));
    if (!chips.length) return '';
    return '<section class="export-findings-summary">'
      + chips.map(chip => `<span>${escapeExportHtml(chip)}</span>`).join('')
      + '</section>';
  }

  function renderExportLineContent(line, ansiToHtml) {
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
    return exportLineBadgeHtml(lineEvent) + content;
  }

  function exportTimestamp() {
    return new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  }

  function buildExportMetaLine({ label = '', createdText = '' }) {
    const trimmedLabel = String(label || '').trim();
    const trimmedCreated = String(createdText || '').trim();
    if (trimmedLabel && trimmedCreated) return `${trimmedLabel} · ${trimmedCreated}`;
    return trimmedLabel || trimmedCreated;
  }

  function normalizeExportTranscriptLine(line) {
    if (typeof line === 'string') {
      return lineEventFromWire({ text: line });
    }
    if (line && typeof line.text === 'string') {
      return lineEventFromWire(line);
    }
    return null;
  }

  function normalizeExportTranscriptLines(lines, { stripTruncationNotices = false } = {}) {
    return (Array.isArray(lines) ? lines : [])
      .map(normalizeExportTranscriptLine)
      .filter((line) => {
        if (!line) return false;
        if (!stripTruncationNotices) return true;
        return !/^\[(?:preview|tab output) truncated/i.test(String(line.text || ''));
      });
  }

  function isCommandOutcomeSummaryLine(line) {
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
    const core = window.DarklabOutputCore || null;
    if (!core || typeof core.buildCommandOutcomeSummary !== 'function') return null;
    const normalizer = typeof core.normalizeCommandOutcomeSummary === 'function'
      ? core.normalizeCommandOutcomeSummary
      : (value) => value;
    return normalizer(core.buildCommandOutcomeSummary(command, rawLines));
  }

  function commandOutcomeSummaryToLines(summary) {
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
    const normalized = normalizeExportTranscriptLines(rawLines);
    if (!enabled || normalized.some(isCommandOutcomeSummaryLine)) return normalized;
    const summary = buildExportCommandOutcomeSummary(command, normalized);
    if (!summary) return normalized;
    return normalized.concat(commandOutcomeSummaryToLines(summary));
  }

  function normalizeExportRunMeta(runMeta) {
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
  }) {
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

  function getThemeExportVars() {
    const registryCurrent = window.ThemeRegistry
      && window.ThemeRegistry.current
      && window.ThemeRegistry.current.vars
      && typeof window.ThemeRegistry.current.vars === 'object'
      ? window.ThemeRegistry.current.vars
      : null;
    if (registryCurrent && Object.keys(registryCurrent).length) return registryCurrent;
    const current = window.ThemeCssVars && window.ThemeCssVars.current;
    if (current && typeof current === 'object' && Object.keys(current).length) return current;
    const source = window.ThemeCssVars && window.ThemeCssVars.fallback;
    if (source && typeof source === 'object') return source;
    const target = document.documentElement;
    const computed = getComputedStyle(target);
    const fallback = {};
    for (const name of EXPORT_THEME_VAR_NAMES) {
      const value = computed.getPropertyValue(name).trim();
      if (value) fallback[name] = value;
    }
    if (Object.keys(fallback).length) return fallback;
    return {};
  }

  function getThemeExportColorScheme() {
    const registryCurrent = window.ThemeRegistry && window.ThemeRegistry.current;
    if (registryCurrent && typeof registryCurrent.color_scheme === 'string' && registryCurrent.color_scheme.trim()) {
      return registryCurrent.color_scheme.trim();
    }
    const colorSchemeMeta = document.querySelector('meta[name="color-scheme"]');
    if (colorSchemeMeta && typeof colorSchemeMeta.content === 'string' && colorSchemeMeta.content.trim()) {
      return colorSchemeMeta.content.trim();
    }
    const docScheme = document.documentElement && document.documentElement.style
      ? document.documentElement.style.colorScheme
      : '';
    if (typeof docScheme === 'string' && docScheme.trim()) return docScheme.trim();
    return 'light dark';
  }

  // ── Line rendering ────────────────────────────────────────────────────────
  // Shared helper used by all save surfaces (html, pdf prep, permalink).
  // rawLines: array of { text, cls, tsC?, ... }
  // getPrefix: (line, index) => string — caller controls what goes in the gutter
  // ansiToHtml: (text) => html string — caller supplies the ansi_up instance
  // Returns { linesHtml, prefixWidth } where prefixWidth is in characters.
  function buildExportLinesHtml(rawLines, { getPrefix = () => '', ansiToHtml }) {
    const prefixes = rawLines.map((line, i) => getPrefix(line, i));
    const prefixWidth = Math.max(0, ...prefixes.map(p => p.length));
    const summary = buildExportLineSummary(rawLines);
    const linesHtml = rawLines.map((rawLine, i) => {
      const line = lineEventFromWire(rawLine);
      const cls = lineLegacyClass(line);
      const prefix = prefixes[i];
      const prefixSpan = prefix
        ? `<span class="perm-prefix">${escapeExportHtml(prefix)}</span>`
        : '';
      const content = renderExportLineContent(line, ansiToHtml);
      return `<span class="line${cls ? ' ' + cls : ''}">${prefixSpan}<span class="perm-content">${content}</span></span>`;
    }).join('');
    return { linesHtml, prefixWidth, summary, summaryHtml: buildExportSummaryHtml(summary) };
  }

  // ── Header / run-meta model ───────────────────────────────────────────────
  // Shared by permalink save html, tab save html, and PDF prep so the browser
  // surfaces and the PDF renderer all consume the same content ordering.
  function buildExportRunMetaItems(runMeta) {
    if (!runMeta) return [];
    const items = [];
    const { exitCode, duration, lines, version } = runMeta;
    if (exitCode !== null && exitCode !== undefined) {
      items.push({
        kind: 'badge',
        tone: exitCode === 0 ? 'ok' : 'fail',
        text: `exit ${exitCode}`,
      });
    }
    if (duration) items.push({ kind: 'item', text: String(duration) });
    if (lines)    items.push({ kind: 'item', text: String(lines) });
    if (version)  items.push({ kind: 'item', text: `v${version}` });
    return items;
  }

  function buildExportHeaderModel({ appName, metaLine = '', runMeta = null }) {
    return {
      appName: String(appName || ''),
      metaLine: metaLine ? String(metaLine) : '',
      runMetaItems: buildExportRunMetaItems(runMeta),
    };
  }

  function buildExportRunMetaHtml(runMetaOrItems) {
    const items = Array.isArray(runMetaOrItems)
      ? runMetaOrItems
      : buildExportRunMetaItems(runMetaOrItems);
    return items.map((item) => {
      if (item.kind === 'badge') {
        const cls = item.tone === 'ok' ? 'meta-badge-ok' : 'meta-badge-fail';
        return `<span class="meta-badge ${cls}">${escapeExportHtml(item.text)}</span>`;
      }
      return `<span class="meta-item">${escapeExportHtml(item.text)}</span>`;
    }).join('');
  }

  function buildTerminalExportHeaderHtml(headerModel, { includeHighlightToggle = false } = {}) {
    const titleHtml = `<h1 class="export-title">${escapeExportHtml(headerModel.appName)}</h1>`;
    const metaHtml = headerModel.metaLine
      ? `<div class="export-meta">${escapeExportHtml(headerModel.metaLine)}</div>`
      : '';
    const runMetaHtml = headerModel.runMetaItems.length
      ? `<div class="export-run-meta">${buildExportRunMetaHtml(headerModel.runMetaItems)}</div>`
      : '';
    const actionsHtml = includeHighlightToggle
      ? `<div class="export-header-actions">
    <button type="button" class="export-highlight-toggle" data-export-toggle-highlights aria-pressed="true">highlights: on</button>
  </div>`
      : '';
    return `<header class="export-header">
  <div class="export-header-copy">
    ${titleHtml}
    ${metaHtml}
    ${runMetaHtml}
  </div>
  ${actionsHtml}
</header>`;
  }

  function buildTerminalExportScript() {
    return `<script>
(function () {
  var btn = document.querySelector('[data-export-toggle-highlights]');
  if (!btn) return;
  function sync() {
    var off = document.body.classList.contains('structured-highlights-off');
    btn.textContent = 'highlights: ' + (off ? 'off' : 'on');
    btn.setAttribute('aria-pressed', off ? 'false' : 'true');
  }
  btn.addEventListener('click', function () {
    document.body.classList.toggle('structured-highlights-off');
    sync();
  });
  sync();
}());
</script>`;
  }

  // ── Styles ────────────────────────────────────────────────────────────────
  // Produces the full inline CSS for an export document. exportCss is the
  // content of terminal_export.css (fetched and passed by the caller).
  // prefixWidth sets the --perm-prefix-width custom property.
  function buildTerminalExportStyles(fontFacesCss = '', prefixWidth = 0, exportCss = '') {
    const themeVars = getThemeExportVars();
    const themeDecls = Object.entries(themeVars)
      .map(([name, value]) => `    ${name}: ${value};`)
      .join('\n');
    return `${fontFacesCss}
  :root {
${themeDecls}
    --perm-prefix-width: ${prefixWidth}ch;
  }
  *, *::before, *::after { box-sizing: border-box; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  html, body { height: 100%; margin: 0; }
  body {
    display: flex;
    flex-direction: column;
    background: var(--bg);
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    font-size: var(--terminal-font-size, 14px);
    line-height: var(--terminal-line-height, 1.65);
  }
  ${exportCss}`;
  }

  // ── Document builder ──────────────────────────────────────────────────────
  // appName   — displayed in the header (green, letter-spaced)
  // title     — used in <title> tag
  // metaLine  — subtitle shown below app name in muted/uppercase style
  // runMeta   — optional { exitCode, duration, lines, version } for badge row
  // linesHtml — pre-built via buildExportLinesHtml
  // prefixWidth — gutter width in ch (for --perm-prefix-width)
  // fontFacesCss — @font-face declarations (base64 fonts)
  function buildTerminalExportHtml({
    appName,
    title,
    metaLine = '',
    runMeta = null,
    linesHtml = '',
    summaryHtml = '',
    prefixWidth = 0,
    fontFacesCss = '',
    exportCss = '',
    includeHighlightToggle = true,
    highlights = 'on',
  }) {
    const colorScheme = getThemeExportColorScheme();
    const headerModel = buildExportHeaderModel({ appName, metaLine, runMeta });
    const styles = buildTerminalExportStyles(fontFacesCss, prefixWidth, exportCss);
    const bodyClass = highlights === 'off' ? ' class="structured-highlights-off"' : '';
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="color-scheme" content="${escapeExportHtml(colorScheme)}">
<title>${escapeExportHtml(title)} — ${escapeExportHtml(appName)}</title>
<style>
${styles}
</style>
</head>
<body${bodyClass}>
${buildTerminalExportHeaderHtml(headerModel, { includeHighlightToggle })}
${summaryHtml || ''}
<main class="export-output nice-scroll">
${linesHtml}
</main>
${includeHighlightToggle ? buildTerminalExportScript() : ''}
</body>
</html>`;
  }

  let _cachedTerminalExportCss = null;

  async function fetchTerminalExportCss() {
    if (_cachedTerminalExportCss !== null) return _cachedTerminalExportCss;
    try {
      const res = await fetch('/static/css/terminal_export.css');
      _cachedTerminalExportCss = res.ok ? await res.text() : '';
    } catch (_) {
      _cachedTerminalExportCss = '';
    }
    return _cachedTerminalExportCss;
  }

  async function fetchVendorFontFacesCss() {
    const chunks = [];
    for (const font of EXPORT_FONT_FILES) {
      const res = await fetch(`/vendor/fonts/${font.filename}`);
      if (!res.ok) continue;
      const buf = await res.arrayBuffer();
      const bytes = new Uint8Array(buf);
      let binary = '';
      const chunkSize = 0x8000;
      for (let i = 0; i < bytes.length; i += chunkSize) {
        binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
      }
      const dataUrl = `url(data:font/ttf;base64,${btoa(binary)}) format('truetype')`;
      chunks.push(
        "@font-face {"
        + ` font-family: '${font.family}';`
        + " font-style: normal;"
        + ` font-weight: ${font.weight};`
        + " font-display: swap;"
        + ` src: ${dataUrl};`
        + " }"
      );
    }
    return chunks.join('\n');
  }

  window.ExportHtmlUtils = {
    exportTimestamp,
    buildExportMetaLine,
    normalizeExportTranscriptLine,
    normalizeExportTranscriptLines,
    appendCommandOutcomeSummaryLines,
    buildExportCommandOutcomeSummary,
    commandOutcomeSummaryToLines,
    isCommandOutcomeSummaryLine,
    normalizeExportRunMeta,
    lineEventFromWire,
    lineLegacyClass,
    isPromptEchoEvent,
    isPlainEvent,
    buildExportDocumentModel,
    escapeExportHtml,
    escapeExportAttr,
    renderExportPromptEcho,
    renderExportEntityContent,
    renderExportLineContent,
    buildExportLinesHtml,
    buildExportLineSummary,
    buildExportRunMetaItems,
    buildExportHeaderModel,
    buildExportRunMetaHtml,
    buildTerminalExportHeaderHtml,
    buildTerminalExportHtml,
    buildTerminalExportStyles,
    getThemeExportVars,
    getThemeExportColorScheme,
    fetchVendorFontFacesCss,
    fetchTerminalExportCss,
  };
})();
;
;
/* /static/js/core/session_core.js */
// ── Session identity pure helpers ─────────────────────────────────────────
// Loaded before session.js. Kept in a small namespace so unit tests and the
// classic browser bundle can share the same pure transforms without extracting
// them from the full session script.
(function (global) {
  function _cryptoApi(preferred) {
    if (preferred && typeof preferred === 'object') return preferred;
    if (global && global.crypto) return global.crypto;
    if (typeof crypto !== 'undefined') return crypto;
    return null;
  }

  function generateUUID(preferredCrypto) {
    const primary = _cryptoApi(preferredCrypto);
    if (primary && typeof primary.randomUUID === 'function') {
      try { return primary.randomUUID(); } catch (_) {}
    }
    const fallback = primary && typeof primary.getRandomValues === 'function'
      ? primary
      : _cryptoApi(null);
    if (!fallback || typeof fallback.getRandomValues !== 'function') {
      throw new Error('crypto.getRandomValues is unavailable');
    }
    const bytes = new Uint8Array(16);
    fallback.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, value => value.toString(16).padStart(2, '0'));
    return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10).join('')}`;
  }

  function getOrCreateStorageValue(storage, key, createValue) {
    let value = storage.getItem(key);
    if (!value) {
      value = createValue();
      storage.setItem(key, value);
    }
    return value;
  }

  function resolveSessionId(storage, sessionUuid) {
    return storage.getItem('session_token') || sessionUuid;
  }

  function maskSessionToken(token) {
    if (typeof token !== 'string' || !token) return '(none)';
    if (token.startsWith('tok_')) return 'tok_' + token.slice(4, 8) + '••••';
    return token.slice(0, 8) + '••••••••';
  }

  function describeFetchError(err, context = 'server') {
    const offlineMessage = `Unable to contact the ${context} right now. Please try again in a moment. If this keeps happening, contact the shell operator.`;
    const message = (err && typeof err.message === 'string') ? err.message.trim() : '';
    if (!message) return offlineMessage;
    const lower = message.toLowerCase();
    if (
      lower.includes('networkerror')
      || lower.includes('failed to fetch')
      || lower.includes('network down')
      || lower.includes('load failed')
    ) {
      return offlineMessage;
    }
    return `Request to the ${context} failed: ${message}`;
  }

  function withSessionHeaders(options = {}, sessionId, clientId) {
    return {
      ...options,
      headers: Object.assign({}, options.headers || {}, {
        'X-Session-ID': sessionId,
        'X-Client-ID': clientId,
      }),
    };
  }

  global.DarklabSessionCore = Object.freeze({
    generateUUID,
    getOrCreateStorageValue,
    resolveSessionId,
    maskSessionToken,
    describeFetchError,
    withSessionHeaders,
  });
})(typeof window !== 'undefined' ? window : globalThis);
;
;
/* /static/js/session.js */
// ── Shared utility module ──
// Session identity: check for a persistent session token first (set by
// 'session-token generate' / 'session-token set'), then fall back to the
// auto-generated UUID.  The UUID is always preserved so clearing a session
// token reverts to the original anonymous session rather than losing identity.
var SessionCore = window.DarklabSessionCore;

function _generateUUID() {
  return SessionCore.generateUUID(typeof crypto !== 'undefined' ? crypto : window.crypto);
}

var _sessionUuid = SessionCore.getOrCreateStorageValue(localStorage, 'session_id', _generateUUID);

var CLIENT_ID = SessionCore.getOrCreateStorageValue(localStorage, 'client_id', _generateUUID);

var SESSION_ID = SessionCore.resolveSessionId(localStorage, _sessionUuid);

// Update SESSION_ID at runtime after a session token is set, changed, or
// cleared.  Called by the session-token terminal commands after they update
// localStorage — avoids a page reload to apply the new identity.
function updateSessionId(newId) {
  SESSION_ID = newId || SessionCore.resolveSessionId(localStorage, _sessionUuid);
  if (typeof loadSessionPreferences === 'function') {
    loadSessionPreferences().catch(() => {});
  }
  if (typeof loadSessionVariables === 'function') {
    loadSessionVariables().catch(() => {});
  }
  if (typeof loadRecentValues === 'function') {
    loadRecentValues().catch(() => {});
  }
  if (typeof loadScheduleAutocompleteHints === 'function') {
    loadScheduleAutocompleteHints().catch(() => {});
  }
  if (typeof loadWatcherAutocompleteHints === 'function') {
    loadWatcherAutocompleteHints().catch(() => {});
  }
  if (typeof refreshWorkspaceFileCache === 'function') {
    refreshWorkspaceFileCache().catch(() => {});
  }
  if (typeof refreshTeamScopes === 'function') {
    refreshTeamScopes().catch(() => {});
  }
  if (typeof window.refreshActiveProjectContext === 'function') {
    window.refreshActiveProjectContext().catch(() => {});
  }
  if (typeof invalidateOptionsSecrets === 'function') {
    invalidateOptionsSecrets();
  }
  if (typeof refreshOptionsSecrets === 'function' && typeof isOptionsOverlayOpen === 'function' && isOptionsOverlayOpen()) {
    refreshOptionsSecrets({ force: true }).catch(() => {});
  }
}

// Keep SESSION_ID current in other open tabs when session_token changes in
// localStorage (the storage event only fires in tabs that did not make the
// change, so this does not double-apply in the tab that called updateSessionId).
// Also reload starred commands, recent chips, and the options-panel token
// display so passive tabs reflect the new session identity immediately.
window.addEventListener('storage', (e) => {
  if (e.key === 'session_token') {
    SESSION_ID = e.newValue || _sessionUuid;
    if (typeof reloadSessionHistory === 'function') reloadSessionHistory().catch(() => {});
    if (typeof loadSessionPreferences === 'function') loadSessionPreferences().catch(() => {});
    if (typeof loadSessionVariables === 'function') loadSessionVariables().catch(() => {});
    if (typeof loadRecentValues === 'function') loadRecentValues().catch(() => {});
    if (typeof loadScheduleAutocompleteHints === 'function') loadScheduleAutocompleteHints().catch(() => {});
    if (typeof loadWatcherAutocompleteHints === 'function') loadWatcherAutocompleteHints().catch(() => {});
    if (typeof refreshWorkspaceFileCache === 'function') refreshWorkspaceFileCache().catch(() => {});
    if (typeof refreshTeamScopes === 'function') refreshTeamScopes().catch(() => {});
    if (typeof window.refreshActiveProjectContext === 'function') window.refreshActiveProjectContext().catch(() => {});
    if (typeof _updateOptionsSessionTokenStatus === 'function') _updateOptionsSessionTokenStatus();
    if (typeof invalidateOptionsSecrets === 'function') invalidateOptionsSecrets();
    if (typeof refreshOptionsSecrets === 'function' && typeof isOptionsOverlayOpen === 'function' && isOptionsOverlayOpen()) {
      refreshOptionsSecrets({ force: true }).catch(() => {});
    }
  }
});

// Return a display-safe masked version of a session token or UUID.
// tok_a1b2c3d4... → tok_a1b2••••
// uuid...         → 8-char-prefix••••••••
function maskSessionToken(token) {
  return SessionCore.maskSessionToken(token);
}

// Wrapper around fetch that always includes the session ID header so every API
// request stays scoped to the same anonymous browser session.
function apiFetch(url, options = {}) {
  const requestOptions = SessionCore.withSessionHeaders(options, SESSION_ID, CLIENT_ID);
  const teamId = typeof getActiveTeamId === 'function' ? getActiveTeamId() : '';
  if (teamId) {
    requestOptions.headers = Object.assign({}, requestOptions.headers || {}, { 'X-Team-ID': teamId });
  }
  return fetch(url, requestOptions);
}

function describeFetchError(err, context = 'server') {
  return SessionCore.describeFetchError(err, context);
}

function logClientError(context, err, details = null) {
  if (typeof console !== 'undefined' && typeof console.warn === 'function') {
    console.warn(`[client] ${context}`, err);
  }
  const message = (err && typeof err.message === 'string') ? err.message : String(err || '');
  const body = { context, message };
  if (details && typeof details === 'object' && !Array.isArray(details)) {
    body.details = details;
  }
  apiFetch('/log', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).catch(() => {});
}
;
;
/* /static/js/features/team_scope.js */
(function initTeamScope(global) {
  if (typeof document === 'undefined') return;

  const trigger = document.getElementById('team-scope-trigger');
  const hudLabel = document.getElementById('team-scope-label');
  const mobileLabel = document.getElementById('mobile-team-scope-label');
  const mobileScopeRow = mobileLabel?.closest?.('.mobile-scope-row') || mobileLabel?.closest?.('[data-menu-action="scope"]');
  const overlay = document.getElementById('team-scope-overlay');
  const modal = document.getElementById('team-scope-modal');
  const currentEl = document.getElementById('team-scope-current');
  const statusEl = document.getElementById('team-scope-status');
  const announcerEl = document.getElementById('team-scope-announcer');
  const listEl = document.getElementById('team-scope-list');
  const closeBtn = overlay?.querySelector?.('.team-scope-close');
  const grabHandle = overlay?.querySelector?.('.sheet-grab');
  const STORAGE_PREFIX = 'active_team_id:';
  const PERSONAL_SCOPE_OPTION = 'personal';
  const MENU_ID = 'team-scope-menu';
  let teams = [];
  let activeTeamId = '';
  let refreshing = null;
  let teamScopesResolved = false;
  let scopeLoadError = false;
  let dismissibleBound = false;
  let menu = null;
  let menuList = null;
  let menuNote = null;
  let menuOutsideBound = false;

  function storageKey() {
    const sessionId = typeof SESSION_ID !== 'undefined' ? SESSION_ID : 'anonymous';
    return `${STORAGE_PREFIX}${sessionId || 'anonymous'}`;
  }

  function storageKeySuffix(key = storageKey()) {
    const value = String(key || '');
    const suffix = value.startsWith(STORAGE_PREFIX) ? value.slice(STORAGE_PREFIX.length) : value;
    return suffix.length > 8 ? suffix.slice(-8) : suffix;
  }

  function errorMessage(err) {
    if (err && typeof err.message === 'string') return err.message;
    return String(err || '');
  }

  function logTeamScopeClientEvent(event, fields = {}, level = 'debug') {
    if (typeof apiFetch !== 'function') return;
    apiFetch('/log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event,
        level,
        context: event,
        message: JSON.stringify(fields),
      }),
    }).catch(() => {});
  }

  function logStorageUnavailable(operation, key, err) {
    logTeamScopeClientEvent('TEAM_SCOPE_STORAGE_UNAVAILABLE', {
      operation,
      key_suffix: storageKeySuffix(key),
      message: errorMessage(err),
    });
  }

  function logRefreshFailure(surface, err) {
    const details = {
      surface,
      team_id: activeTeamId || '',
      message: errorMessage(err),
    };
    if (typeof logClientError === 'function') {
      const wrapped = err instanceof Error ? err : new Error(details.message);
      logClientError(`TEAM_SCOPE_REFRESH_FAILED ${JSON.stringify({
        surface: details.surface,
        team_id: details.team_id,
      })}`, wrapped);
      return;
    }
    logTeamScopeClientEvent('TEAM_SCOPE_REFRESH_FAILED', details, 'warning');
  }

  function getStoredTeamId() {
    const key = storageKey();
    try { return localStorage.getItem(key) || ''; } catch (err) {
      logStorageUnavailable('read', key, err);
      return '';
    }
  }

  function storeTeamId(teamId) {
    const key = storageKey();
    try {
      if (teamId) localStorage.setItem(key, teamId);
      else localStorage.removeItem(key);
    } catch (err) {
      logStorageUnavailable(teamId ? 'write' : 'remove', key, err);
    }
  }

  function normalizeTeamId(teamId) {
    const value = String(teamId || '').trim();
    return value === PERSONAL_SCOPE_OPTION ? '' : value;
  }

  function getActiveTeamId() {
    return activeTeamId || '';
  }

  function getActiveTeam() {
    if (!activeTeamId) return null;
    return teams.find(item => item.id === activeTeamId) || null;
  }

  function getActiveTeamCapabilities() {
    const team = getActiveTeam();
    return Array.isArray(team?.capabilities) ? team.capabilities : [];
  }

  function activeTeamScopeCan(capability) {
    if (!activeTeamId) return true;
    const wanted = String(capability || '').trim();
    if (!wanted) return true;
    return getActiveTeamCapabilities().includes(wanted);
  }

  function teamScopeDeniedMessage(action = 'make this change') {
    const text = String(action || 'make this change').trim() || 'make this change';
    return `View-only team members can't ${text}. Switch to Personal or ask for operator access.`;
  }

  function activeLabel() {
    return activeScopeState().label;
  }

  function activeScopeState() {
    if (!activeTeamId) return { label: 'Personal', tone: '' };
    const team = teams.find(item => item.id === activeTeamId);
    if (team) return { label: team.name, tone: '' };
    if (scopeLoadError) return { label: 'Team unavailable', tone: 'error' };
    if (!teamScopesResolved || refreshing) return { label: 'Loading...', tone: 'loading' };
    return { label: 'Team unavailable', tone: 'error' };
  }

  function applyScopeTone(el, tone = '') {
    if (!el) return;
    el.classList.toggle('is-loading', tone === 'loading');
    el.classList.toggle('is-error', tone === 'error');
  }

  function optionLabel(team) {
    return team.name || team.slug || 'Team';
  }

  function showStatus(message = '', tone = '') {
    if (!statusEl) return;
    statusEl.textContent = String(message || '');
    statusEl.classList.toggle('u-hidden', !message);
    statusEl.classList.toggle('is-error', tone === 'error');
  }

  function announceScopeChange(label) {
    if (!announcerEl) return;
    announcerEl.textContent = '';
    window.setTimeout(() => {
      announcerEl.textContent = `Active scope changed to ${label}.`;
    }, 0);
  }

  function renderButton(team = null) {
    const active = team ? team.id === activeTeamId : !activeTeamId;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `dropdown-item dropdown-item-touch team-scope-option${active ? ' is-active' : ''}`;
    button.dataset.teamScopeOption = team ? team.id : PERSONAL_SCOPE_OPTION;
    button.setAttribute('role', 'option');
    button.setAttribute('aria-selected', active ? 'true' : 'false');

    const main = document.createElement('span');
    main.className = 'team-scope-option-main';
    const name = document.createElement('span');
    name.className = 'team-scope-option-name';
    name.textContent = team ? optionLabel(team) : 'Personal';
    main.appendChild(name);
    if (team?.role) {
      const meta = document.createElement('span');
      meta.className = 'team-scope-option-meta';
      meta.textContent = team.role;
      main.appendChild(meta);
    }

    const marker = document.createElement('span');
    marker.className = 'team-scope-option-marker';
    marker.textContent = active ? 'active' : 'select';
    button.append(main, marker);
    return button;
  }

  function renderMenuButton(team = null) {
    const active = team ? team.id === activeTeamId : !activeTeamId;
    const label = team ? optionLabel(team) : 'Personal';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'dropdown-item dropdown-item-compact team-scope-menu-option';
    button.dataset.teamScopeMenuOption = team ? team.id : PERSONAL_SCOPE_OPTION;
    button.setAttribute('role', 'menuitemradio');
    button.setAttribute('aria-checked', active ? 'true' : 'false');
    button.textContent = active ? `${label} (active)` : label;
    button.title = active ? `Active scope: ${label}` : `Switch to ${label}`;
    button.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      setActiveTeamId(button.dataset.teamScopeMenuOption || '', { source: 'selector' });
      closeScopeMenu();
    });
    return button;
  }

  function isModalOpen() {
    return !!(overlay && overlay.classList.contains('open'));
  }

  function isScopeMenuOpen() {
    return !!(menu && !menu.classList.contains('u-hidden'));
  }

  function setScopeMenuNote(text = '') {
    if (!menuNote) return;
    menuNote.textContent = String(text || '');
    menuNote.classList.toggle('u-hidden', !text);
  }

  function renderMenuOptions() {
    if (!menuList) return;
    menuList.replaceChildren();
    menuList.appendChild(renderMenuButton(null));
    teams.forEach(team => {
      menuList.appendChild(renderMenuButton(team));
    });
    if (refreshing && !teamScopesResolved) setScopeMenuNote('Loading teams...');
    else if (!teams.length) setScopeMenuNote('No teams yet.');
    else setScopeMenuNote('');
  }

  function renderOptions() {
    if (listEl) {
      listEl.innerHTML = '';
      listEl.appendChild(renderButton(null));
      teams.forEach(team => {
        listEl.appendChild(renderButton(team));
      });
    }
    renderMenuOptions();
  }

  function render() {
    const state = activeScopeState();
    const label = state.label;
    if (hudLabel) hudLabel.textContent = label;
    if (mobileLabel) mobileLabel.textContent = label;
    if (currentEl) currentEl.textContent = label;
    applyScopeTone(trigger, state.tone);
    applyScopeTone(mobileScopeRow, state.tone);
    applyScopeTone(currentEl, state.tone);
    if (trigger) trigger.title = `Active scope: ${label}`;
    renderOptions();
  }

  function reloadScopedSurfaces() {
    [
      ['history', () => (typeof reloadSessionHistory === 'function' ? reloadSessionHistory() : null)],
      ['recent_values', () => (typeof loadRecentValues === 'function' ? loadRecentValues() : null)],
      ['workspace_files', () => (typeof refreshWorkspaceFileCache === 'function' ? refreshWorkspaceFileCache() : null)],
      ['active_project', () => (typeof window.refreshActiveProjectContext === 'function' ? window.refreshActiveProjectContext() : null)],
      ['options_secrets', () => (typeof global.invalidateOptionsSecrets === 'function' ? global.invalidateOptionsSecrets() : null)],
      ['active_runs', () => (typeof refreshActiveRuns === 'function' ? refreshActiveRuns() : null)],
      ['status_monitor', () => (typeof window.refreshStatusMonitor === 'function' ? window.refreshStatusMonitor() : null)],
    ].forEach(([surface, refresh]) => {
      try {
        const result = refresh();
        if (result && typeof result.catch === 'function') {
          result.catch(err => logRefreshFailure(surface, err));
        }
      } catch (err) {
        logRefreshFailure(surface, err);
      }
    });
  }

  function setActiveTeamId(teamId, { persist = true, emit = true, allowPending = false, source = 'direct' } = {}) {
    const normalized = normalizeTeamId(teamId);
    if (activeTeamId === normalized) return true;
    const knownTeam = !normalized || teams.some(team => team.id === normalized);
    if (!knownTeam && !allowPending) return false;
    activeTeamId = normalized;
    if (normalized && !knownTeam) {
      teamScopesResolved = false;
      scopeLoadError = false;
    }
    if (persist) storeTeamId(activeTeamId);
    render();
    const label = activeLabel();
    if (emit) {
      logTeamScopeClientEvent('TEAM_SCOPE_CHANGED', {
        team_id: activeTeamId,
        scope: activeTeamId ? 'team' : 'personal',
        persisted: !!persist,
        source,
      });
      document.dispatchEvent(new CustomEvent('app:scope-changed', {
        detail: { team_id: activeTeamId, label },
      }));
      announceScopeChange(label);
      reloadScopedSurfaces();
    }
    if (normalized && !knownTeam) {
      refreshTeamScopes().catch(() => {});
    }
    return true;
  }

  function isOpen() {
    return isModalOpen() || isScopeMenuOpen();
  }

  function positionScopeMenu() {
    if (!menu || !trigger || !isScopeMenuOpen()) return;
    const anchor = trigger.closest?.('.hud-cell') || trigger;
    const rect = anchor.getBoundingClientRect();
    const menuWidth = menu.offsetWidth || 260;
    const viewportWidth = global.innerWidth || document.documentElement.clientWidth || 0;
    const left = Math.max(8, Math.min(rect.left, Math.max(8, viewportWidth - menuWidth - 8)));
    menu.style.left = `${left}px`;
    menu.style.bottom = `${Math.max(8, (global.innerHeight || 0) - rect.top - 1)}px`;
  }

  function closeScopeMenu({ restoreFocus = false } = {}) {
    if (!menu) return;
    menu.classList.add('u-hidden');
    trigger?.classList.remove('open');
    trigger?.setAttribute('aria-expanded', 'false');
    setScopeMenuNote('');
    if (restoreFocus && trigger && typeof trigger.focus === 'function') {
      trigger.focus({ preventScroll: true });
    }
  }

  function focusScopeMenuItem(delta) {
    if (!menu) return;
    const items = Array.from(menu.querySelectorAll('.dropdown-item:not([disabled])'));
    if (!items.length) return;
    const currentIdx = items.indexOf(document.activeElement);
    const fallbackIdx = delta > 0 ? -1 : 0;
    const nextIdx = (currentIdx >= 0 ? currentIdx : fallbackIdx) + delta;
    items[(nextIdx + items.length) % items.length]?.focus({ preventScroll: true });
  }

  function ensureScopeMenu() {
    if (menu) return menu;
    const popup = document.createElement('div');
    popup.id = MENU_ID;
    popup.className = 'hud-project-menu team-scope-menu dropdown-surface dropdown-up u-hidden';
    popup.setAttribute('role', 'menu');
    popup.setAttribute('aria-label', 'Active data scope');

    const section = document.createElement('div');
    section.className = 'hud-project-menu-section';
    popup.appendChild(section);

    const note = document.createElement('div');
    note.className = 'hud-project-menu-note u-hidden';
    popup.appendChild(note);

    popup.addEventListener('click', event => event.stopPropagation());
    popup.addEventListener('keydown', event => {
      event.stopPropagation();
      if (event.key === 'Escape') {
        event.preventDefault();
        closeScopeMenu({ restoreFocus: true });
      } else if (event.key === 'ArrowDown') {
        event.preventDefault();
        focusScopeMenuItem(1);
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        focusScopeMenuItem(-1);
      } else if (event.key === 'Tab') {
        closeScopeMenu();
      }
    });

    document.body.appendChild(popup);
    menu = popup;
    menuList = section;
    menuNote = note;

    if (typeof global.bindOutsideClickClose === 'function') {
      global.bindOutsideClickClose(menu, {
        capture: true,
        triggers: trigger,
        isOpen: isScopeMenuOpen,
        onClose: () => closeScopeMenu(),
      });
    } else if (!menuOutsideBound) {
      menuOutsideBound = true;
      document.addEventListener('click', event => {
        if (!isScopeMenuOpen()) return;
        const target = event.target;
        if (target instanceof Node && (menu.contains(target) || trigger?.contains?.(target))) return;
        closeScopeMenu();
      }, true);
    }
    return menu;
  }

  function setOverlayAccessible(open) {
    if (!overlay) return;
    if (!open && typeof overlay.contains === 'function' && overlay.contains(document.activeElement)) {
      document.activeElement?.blur?.();
    }
    overlay.setAttribute('aria-hidden', open ? 'false' : 'true');
    overlay.toggleAttribute('inert', !open);
  }

  function closeTeamScopeSelector({ refocus = true } = {}) {
    closeScopeMenu();
    if (!overlay) return;
    setOverlayAccessible(false);
    overlay.classList.add('u-hidden');
    overlay.classList.remove('open');
    showStatus('');
    if (typeof global.syncModalOverlayState === 'function') global.syncModalOverlayState();
    if (refocus && typeof global.refocusComposerAfterAction === 'function') {
      global.refocusComposerAfterAction({ defer: true });
    }
  }

  function showTeamScopeSelector() {
    if (!overlay) return false;
    closeScopeMenu();
    bindModalDismissal();
    if (typeof global._closeMajorOverlays === 'function') global._closeMajorOverlays();
    if (typeof global.blurVisibleComposerInputIfMobile === 'function') global.blurVisibleComposerInputIfMobile();
    setOverlayAccessible(true);
    overlay.classList.remove('u-hidden');
    overlay.classList.add('open');
    showStatus('');
    render();
    if (typeof global.syncModalOverlayState === 'function') global.syncModalOverlayState();
    const active = listEl?.querySelector?.('.team-scope-option.is-active');
    (active || closeBtn || modal)?.focus?.({ preventScroll: true });
    return true;
  }

  function toggleScopeMenu(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    if (isScopeMenuOpen()) {
      closeScopeMenu({ restoreFocus: true });
      return true;
    }
    if (typeof global._closeMajorOverlays === 'function') global._closeMajorOverlays();
    closeTeamScopeSelector({ refocus: false });
    ensureScopeMenu();
    render();
    menu.classList.remove('u-hidden');
    trigger?.classList.add('open');
    trigger?.setAttribute('aria-expanded', 'true');
    positionScopeMenu();
    requestAnimationFrame(positionScopeMenu);
    const active = menu.querySelector?.('[aria-checked="true"]');
    const first = menu.querySelector?.('.dropdown-item:not([disabled])');
    (active || first || menu)?.focus?.({ preventScroll: true });
    refreshTeamScopes().catch(() => {});
    return true;
  }

  function bindModalDismissal() {
    if (!overlay || dismissibleBound) return;
    dismissibleBound = true;
    const closeButtons = Array.from(overlay.querySelectorAll('.team-scope-close'));
    if (typeof global.bindDismissible === 'function') {
      global.bindDismissible(overlay, {
        level: 'modal',
        isOpen,
        onClose: closeTeamScopeSelector,
        closeButtons,
      });
    } else {
      closeButtons.forEach(button => {
        button.addEventListener('click', () => closeTeamScopeSelector());
      });
      overlay.addEventListener('click', event => {
        if (event.target === overlay) closeTeamScopeSelector();
      });
    }
    if (typeof global.bindMobileSheet === 'function' && modal) {
      global.bindMobileSheet(modal, { onClose: closeTeamScopeSelector });
    } else {
      grabHandle?.addEventListener('click', () => closeTeamScopeSelector());
    }
  }

  function normalizeTeams(payload) {
    const rows = Array.isArray(payload?.teams) ? payload.teams : [];
    return rows.map((team) => ({
      id: String(team.id || ''),
      name: String(team.name || team.slug || 'Team'),
      slug: String(team.slug || ''),
      role: String(team.member?.role || ''),
      capabilities: Array.isArray(team.member?.capabilities)
        ? team.member.capabilities.map(item => String(item || '')).filter(Boolean)
        : [],
    })).filter(team => team.id);
  }

  function replaceTeamScopes(payload) {
    teams = normalizeTeams(payload);
    const stored = normalizeTeamId(getStoredTeamId());
    activeTeamId = teams.some(team => team.id === stored) ? stored : '';
    teamScopesResolved = true;
    scopeLoadError = false;
    if (!activeTeamId) storeTeamId('');
    render();
    document.dispatchEvent(new CustomEvent('app:scope-capabilities-changed', {
      detail: { team_id: activeTeamId },
    }));
    return teams;
  }

  async function refreshTeamScopes() {
    if (refreshing) return refreshing;
    const storedBeforeRefresh = normalizeTeamId(getStoredTeamId());
    if (storedBeforeRefresh && !activeTeamId) activeTeamId = storedBeforeRefresh;
    scopeLoadError = false;
    if (activeTeamId && !teams.some(team => team.id === activeTeamId)) {
      teamScopesResolved = false;
    }
    render();
    if (typeof apiFetch !== 'function') {
      teamScopesResolved = true;
      scopeLoadError = !!activeTeamId;
      render();
      return Promise.resolve([]);
    }
    refreshing = apiFetch('/session/teams', { cache: 'no-store' })
      .then(async (resp) => {
        if (resp.status === 401) {
          teams = [];
          teamScopesResolved = true;
          scopeLoadError = false;
          showStatus('');
          setActiveTeamId('', { persist: true, emit: false });
          render();
          return teams;
        }
        const payload = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(payload.error || resp.statusText || resp.status);
        return replaceTeamScopes(payload);
      })
      .catch((err) => {
        logRefreshFailure('teams', err);
        teams = [];
        if (!activeTeamId) activeTeamId = normalizeTeamId(getStoredTeamId());
        teamScopesResolved = true;
        scopeLoadError = !!activeTeamId;
        render();
        if (isModalOpen()) showStatus('Could not load teams.', 'error');
        if (isScopeMenuOpen()) setScopeMenuNote('Could not load teams.');
        return teams;
      })
      .finally(() => { refreshing = null; });
    return refreshing;
  }

  trigger?.addEventListener('click', toggleScopeMenu);
  trigger?.addEventListener('keydown', event => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') toggleScopeMenu(event);
    else if (event.key === 'Escape' && isScopeMenuOpen()) {
      event.preventDefault();
      closeScopeMenu({ restoreFocus: true });
    }
  });

  listEl?.addEventListener('click', event => {
    const option = event.target.closest?.('[data-team-scope-option]');
    if (!option) return;
    event.preventDefault();
    if (setActiveTeamId(option.dataset.teamScopeOption || '', { source: 'selector' })) closeTeamScopeSelector();
  });

  global.getActiveTeamId = getActiveTeamId;
  global.getActiveTeam = getActiveTeam;
  global.getActiveTeamCapabilities = getActiveTeamCapabilities;
  global.activeTeamScopeCan = activeTeamScopeCan;
  global.teamScopeDeniedMessage = teamScopeDeniedMessage;
  global.setActiveTeamId = setActiveTeamId;
  global.refreshTeamScopes = refreshTeamScopes;
  global.replaceTeamScopes = replaceTeamScopes;
  global.isTeamScopeSelectorOpen = isOpen;
  global.openTeamScopeSelector = () => {
    const opened = showTeamScopeSelector();
    refreshTeamScopes().catch(() => {});
    return opened;
  };
  global.closeTeamScopeSelector = closeTeamScopeSelector;
  global.DarklabTeamScope = {
    getActiveTeamId,
    getActiveTeam,
    getActiveTeamCapabilities,
    activeTeamScopeCan,
    deniedMessage: teamScopeDeniedMessage,
    setActiveTeamId,
    refreshTeamScopes,
    replaceTeamScopes,
    isOpen,
    open: global.openTeamScopeSelector,
    close: closeTeamScopeSelector,
  };

  window.addEventListener('storage', (event) => {
    if (event.key === storageKey()) {
      const nextTeamId = normalizeTeamId(event.newValue);
      if (nextTeamId !== activeTeamId) {
        setActiveTeamId(nextTeamId, { persist: false, allowPending: true, source: 'storage' });
      }
    }
  });
  window.addEventListener('resize', positionScopeMenu);
  document.addEventListener('DOMContentLoaded', () => {
    bindModalDismissal();
    refreshTeamScopes().catch(() => {});
  });
})(window);
;
;
/* /static/js/core/state.js */
// ── Shared UI state ──
// The browser scripts still read/write these names directly, but the actual
// storage lives here so the app can move away from prompt-specific globals in
// a controlled way without changing every module at once.
(function initSharedState(global) {
  const defaults = {
    tabs: [],
    activeTabId: null,
    acSuggestions: [],
    acContextRegistry: {},
    acWordlists: [],
    acSpecialCommands: [],
    acBuiltinCommandRoots: [],
    sessionVariables: [],
    acFiltered: [],
    acIndex: -1,
    acSuppressInputOnce: false,
    searchMatches: [],
    searchMatchIdx: -1,
    searchCaseSensitive: false,
    searchRegexMode: false,
    searchScope: 'text',
    searchDiscoverabilityPrompted: false,
    searchSignalCounts: null,
    cmdHistory: [],
    recentPreviewHistory: [],
    _cmdHistoryNavIndex: -1,
    _cmdHistoryNavDraft: '',
    _suspendCmdHistoryNavReset: false,
    pendingHistAction: null,
    _welcomeActive: false,
    _welcomeDone: false,
    _welcomeTabId: null,
    _welcomeBanner: null,
    _welcomeLiveLine: null,
    _welcomeHintNode: null,
    _welcomeStatusNodes: [],
    _welcomePlan: null,
    _welcomeNextBlockIndex: 0,
    _welcomeSettleRequested: false,
    _welcomePromptAfterSettle: false,
    _welcomeBootPending: true,
    _composerValue: '',
    _composerSelectionStart: 0,
    _composerSelectionEnd: 0,
    _composerActiveInput: 'desktop',
    _mobileKeyboardOffsetBaseline: null,
    _mobileViewportClosedHeight: null,
    _mobileKeyboardLastOpenOffset: 0,
    timerInterval: null,
    timerStart: null,
    pendingKillTabId: null,
  };
  const state = global.APP_STATE || (global.APP_STATE = {});
  Object.assign(state, defaults);

  const bindings = [
    'tabs',
    'activeTabId',
    'acSuggestions',
    'acContextRegistry',
    'acWordlists',
    'acSpecialCommands',
    'acBuiltinCommandRoots',
    'sessionVariables',
    'acFiltered',
    'acIndex',
    'acSuppressInputOnce',
    'searchMatches',
    'searchMatchIdx',
    'searchCaseSensitive',
    'searchRegexMode',
    'searchScope',
    'searchDiscoverabilityPrompted',
    'searchSignalCounts',
    'cmdHistory',
    'recentPreviewHistory',
    '_cmdHistoryNavIndex',
    '_cmdHistoryNavDraft',
    '_suspendCmdHistoryNavReset',
    'pendingHistAction',
    '_welcomeActive',
    '_welcomeDone',
    '_welcomeTabId',
    '_welcomeBanner',
    '_welcomeLiveLine',
    '_welcomeHintNode',
    '_welcomeStatusNodes',
    '_welcomePlan',
    '_welcomeNextBlockIndex',
    '_welcomeSettleRequested',
    '_welcomePromptAfterSettle',
    '_welcomeBootPending',
    '_composerValue',
    '_composerSelectionStart',
    '_composerSelectionEnd',
    '_composerActiveInput',
    '_mobileKeyboardOffsetBaseline',
    '_mobileViewportClosedHeight',
    '_mobileKeyboardLastOpenOffset',
    'timerInterval',
    'timerStart',
    'pendingKillTabId',
  ];

  for (const name of bindings) {
    Object.defineProperty(global, name, {
      configurable: true,
      enumerable: true,
      get() {
        return state[name];
      },
      set(value) {
        state[name] = value;
      },
    });
  }

  global.getAppState = () => state;
  global.getComposerState = () => ({
    value: state._composerValue,
    selectionStart: state._composerSelectionStart,
    selectionEnd: state._composerSelectionEnd,
    activeInput: state._composerActiveInput,
  });
  global.setComposerState = (next = {}) => {
    if (Object.prototype.hasOwnProperty.call(next, 'value')) {
      state._composerValue = String(next.value ?? '');
    }
    if (Object.prototype.hasOwnProperty.call(next, 'selectionStart')) {
      state._composerSelectionStart = Math.max(0, Number(next.selectionStart) || 0);
    }
    if (Object.prototype.hasOwnProperty.call(next, 'selectionEnd')) {
      state._composerSelectionEnd = Math.max(0, Number(next.selectionEnd) || 0);
    }
    if (Object.prototype.hasOwnProperty.call(next, 'activeInput')) {
      state._composerActiveInput = next.activeInput === 'mobile' ? 'mobile' : 'desktop';
    }
    return global.getComposerState();
  };
  global.resetComposerState = () => {
    state._composerValue = defaults._composerValue;
    state._composerSelectionStart = defaults._composerSelectionStart;
    state._composerSelectionEnd = defaults._composerSelectionEnd;
    state._composerActiveInput = defaults._composerActiveInput;
    return global.getComposerState();
  };
  global.APP_STATE_API = {
    getState: () => state,
    reset: () => Object.assign(state, defaults),
    getTabs: () => state.tabs,
    setTabs: (v) => { state.tabs = v; },
    getActiveTabId: () => state.activeTabId,
    setActiveTabId: (v) => { state.activeTabId = v; },
    getActiveTab: () => state.tabs.find(t => t.id === state.activeTabId),
    getTab: (id) => state.tabs.find(t => t.id === id),
    getComposerState: () => global.getComposerState(),
    setComposerState: (next) => global.setComposerState(next),
    resetComposerState: () => global.resetComposerState(),
  };

  // ── Tab accessors ──
  // Use these instead of reading/writing tabs and activeTabId directly.
  // Direct access still works (via the property descriptors above), but these
  // setters make mutation sites explicit and provide a stable boundary for
  // future refactoring.
  global.getTabs = () => state.tabs;
  global.setTabs = (v) => { state.tabs = v; };
  global.getActiveTabId = () => state.activeTabId;
  global.setActiveTabId = (v) => { state.activeTabId = v; };
  global.getActiveTab = () => state.tabs.find(t => t.id === state.activeTabId);
  global.getTab = (id) => state.tabs.find(t => t.id === id);

  // ── UI event helpers ──
  // Keep cross-module state sync explicit: publishers emit document-level
  // CustomEvents and subscribers opt in with add/remove listeners instead of
  // monkey-patching each other's globals after load.
  global.emitUiEvent = (name, detail = {}) => {
    if (typeof document === 'undefined' || typeof document.dispatchEvent !== 'function') return false;
    document.dispatchEvent(new CustomEvent(name, { detail }));
    return true;
  };
  global.onUiEvent = (name, handler, options) => {
    if (typeof document === 'undefined' || typeof document.addEventListener !== 'function' || typeof handler !== 'function') {
      return () => {};
    }
    document.addEventListener(name, handler, options);
    return () => document.removeEventListener(name, handler, options);
  };

})(globalThis);
;
;
/* /static/js/core/utils.js */
// ── Shared utility module ──

function escapeHtml(t) {
  return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function normalizeRedactionRules(rules) {
  if (!Array.isArray(rules)) return [];
  return rules
    .filter(rule => rule && typeof rule === 'object')
    .map(rule => {
      const pattern = typeof rule.pattern === 'string' ? rule.pattern : '';
      if (!pattern.trim()) return null;
      const replacement = typeof rule.replacement === 'string' ? rule.replacement : '[redacted]';
      const flags = typeof rule.flags === 'string'
        ? Array.from(new Set(rule.flags.toLowerCase().split('').filter(ch => ch === 'i' || ch === 'm'))).join('')
        : '';
      try {
        return {
          label: typeof rule.label === 'string' ? rule.label.trim() : '',
          pattern,
          replacement,
          flags,
          regex: new RegExp(pattern, `g${flags}`),
        };
      } catch (_) {
        return null;
      }
    })
    .filter(Boolean);
}

function applyRedactionRules(text, rules) {
  let value = String(text ?? '');
  for (const rule of normalizeRedactionRules(rules)) {
    value = value.replace(rule.regex, rule.replacement);
  }
  return value;
}

function redactLineEntries(entries, rules) {
  return (Array.isArray(entries) ? entries : [])
    .map(item => {
      if (typeof item === 'string') return applyRedactionRules(item, rules);
      if (!item || typeof item !== 'object' || typeof item.text !== 'string') return null;
      return {
        ...item,
        text: applyRedactionRules(item.text, rules),
      };
    })
    .filter(Boolean);
}

var RAW_ONLY_INTEL_PLACEHOLDER = 'Intel data omitted from share';

function _isRawOnlyIntelEntry(item) {
  return !!(item && typeof item === 'object' && String(item.command_root || '').trim().toLowerCase() === 'intel');
}

function _rawOnlyPlaceholderEntry(source = {}) {
  const entry = {
    text: RAW_ONLY_INTEL_PLACEHOLDER,
    cls: 'notice',
    raw_only: true,
    command_root: 'intel',
  };
  if (typeof source.tsC === 'string') entry.tsC = source.tsC;
  if (typeof source.tsE === 'string') entry.tsE = source.tsE;
  if (Number.isInteger(source.line_number)) entry.line_number = source.line_number;
  return entry;
}

function omitRawOnlyLineEntries(entries) {
  const omitted = [];
  let inIntelGroup = false;
  for (const item of Array.isArray(entries) ? entries : []) {
    if (_isRawOnlyIntelEntry(item)) {
      if (!inIntelGroup) {
        omitted.push(_rawOnlyPlaceholderEntry(item));
        inIntelGroup = true;
      }
      continue;
    }
    inIntelGroup = false;
    if (typeof item === 'string') omitted.push(item);
    else if (item && typeof item === 'object') omitted.push({ ...item });
  }
  return omitted;
}

// Render a small Markdown subset for MOTD: **bold**, `code`, [text](url), newlines.
// escapeHtml is applied first to prevent XSS, then patterns are applied so the
// operator notice stays useful without needing a full Markdown parser.
function renderMotd(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/\n/g, '<br>');
}

function _copyTextFallback(text) {
  return new Promise((resolve, reject) => {
    if (typeof document === 'undefined' || !document.body) {
      reject(new Error('Clipboard is not available'));
      return;
    }
    const textarea = document.createElement('textarea');
    textarea.value = String(text);
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.top = '-9999px';
    textarea.style.left = '-9999px';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    let copied = false;
    try {
      copied = typeof document.execCommand === 'function' && document.execCommand('copy');
    } catch (_) {
      copied = false;
    }
    textarea.remove();
    if (copied) resolve(true);
    else reject(new Error('Copy command failed'));
  });
}

async function copyTextToClipboard(text) {
  const value = String(text ?? '');
  if (!value) throw new Error('Cannot copy empty text');
  if (typeof navigator !== 'undefined' && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch (_) {
      // Fall through to the legacy copy command fallback below.
    }
  }
  return _copyTextFallback(value);
}

function downloadBlobAsAttachment(blob, filename, options = {}) {
  const opts = options && typeof options === 'object' ? options : {};
  const { revokeDelayMs = 2000, container = null } = opts;
  if (typeof URL === 'undefined' || typeof URL.createObjectURL !== 'function') {
    throw new Error('Blob downloads are not available');
  }
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename || 'download';
  const parent = container && typeof container.appendChild === 'function' ? container : document.body;
  parent.appendChild(anchor);
  anchor.click();
  anchor.remove();

  if (typeof URL.revokeObjectURL !== 'function') return;
  let revoked = false;
  const revoke = () => {
    if (revoked) return;
    revoked = true;
    URL.revokeObjectURL(url);
  };
  if (typeof window !== 'undefined' && typeof window.setTimeout === 'function') {
    window.setTimeout(revoke, revokeDelayMs);
  } else if (typeof setTimeout === 'function') {
    setTimeout(revoke, revokeDelayMs);
  }
  if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
    window.addEventListener('pagehide', revoke, { once: true });
  }
}

function downloadUrlAsAttachment(url, options = {}) {
  const href = String(url || '').trim();
  if (!href) throw new Error('Download URL is required');
  const opts = options && typeof options === 'object' ? options : {};
  const anchor = document.createElement('a');
  anchor.href = href;
  if (opts.filename) anchor.download = String(opts.filename);
  anchor.rel = 'noopener';
  const parent = opts.container && typeof opts.container.appendChild === 'function'
    ? opts.container
    : document.body;
  parent.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

async function shareUrl(url) {
  // navigator.share requires a user gesture and a secure context (HTTPS).
  // Because shareUrl is always called from inside a fetch .then() callback
  // (creating the snapshot), the transient activation has already expired by
  // the time we get here — a direct navigator.share() call will always fail
  // with NotAllowedError. Instead we always copy to clipboard first (reliable),
  // then surface a share button in the toast so the user can open the native
  // share sheet with a fresh gesture from that tap.
  const canShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function';
  try {
    await copyTextToClipboard(url);
  } catch (_) {
    // Clipboard unavailable — surface the URL in a native prompt as last resort.
    if (typeof window !== 'undefined' && typeof window.prompt === 'function') {
      window.prompt('Copy the link:', url);
    }
    return;
  }
  if (canShare) {
    showToast('Link copied to clipboard', 'success', {
      label: 'share ↗',
      onClick: () => { navigator.share({ url }).catch(() => {}); },
    });
  } else {
    showToast('Link copied to clipboard');
  }
}

function showToast(msg, tone = 'success', action = null) {
  // Toasts are transient UI feedback only; avoid stacking timers by resetting
  // the hide timer whenever a new message reuses the same element.
  const toast = document.getElementById('permalink-toast');
  const isError = tone === 'error' || /^(failed|unable|error|\[.*error\])/i.test(String(msg || ''));
  toast.classList.remove('toast-has-action');
  toast.textContent = msg;
  if (action && action.label && typeof action.onClick === 'function') {
    const btn = document.createElement('button');
    btn.className = 'toast-action-btn';
    btn.textContent = action.label;
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      toast.classList.remove('show');
      toast.classList.remove('toast-has-action');
      action.onClick();
    }, { once: true });
    toast.classList.add('toast-has-action');
    toast.appendChild(btn);
  }
  toast.classList.toggle('toast-error', isError);
  toast.classList.toggle('toast-success', !isError);
  toast.classList.add('show');
  setTimeout(() => {
    toast.classList.remove('show');
    toast.classList.remove('toast-has-action');
  }, action ? 5000 : 2500);
}
;
