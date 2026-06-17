// ── Shared HTML export helpers ───────────────────────────────────────────────
// Single source of truth for all export formatting (save html, save pdf,
// permalink save html). All callers go through these helpers so the rendered
// output is consistent across every save surface.
import { DarklabOutputCore as importedOutputCore } from './core/output_core.js';
import { DarklabRunOutputModel as importedRunOutputModel } from './core/run_output_model.js';
import { _getThemeRegistry as importedGetThemeRegistry } from './features/theme/theme.js';

let ExportHtmlUtils = null;

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
    return (typeof importedRunOutputModel !== 'undefined' && importedRunOutputModel)
      || null;
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
    const core = (typeof importedOutputCore !== 'undefined' && importedOutputCore)
      || null;
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
    const themeRegistry = typeof importedGetThemeRegistry === 'function' ? importedGetThemeRegistry() : null;
    const registryCurrent = themeRegistry
      && themeRegistry.current
      && themeRegistry.current.vars
      && typeof themeRegistry.current.vars === 'object'
      ? themeRegistry.current.vars
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
    const themeRegistry = typeof importedGetThemeRegistry === 'function' ? importedGetThemeRegistry() : null;
    const registryCurrent = themeRegistry && themeRegistry.current;
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

  ExportHtmlUtils = {
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
  if (typeof window !== 'undefined') {
    window.ExportHtmlUtils = ExportHtmlUtils;
  }
})();

const {
  appendCommandOutcomeSummaryLines,
  buildExportCommandOutcomeSummary,
  buildExportDocumentModel,
  buildExportHeaderModel,
  buildExportLineSummary,
  buildExportLinesHtml,
  buildExportMetaLine,
  buildExportRunMetaHtml,
  buildExportRunMetaItems,
  buildTerminalExportHeaderHtml,
  buildTerminalExportHtml,
  buildTerminalExportStyles,
  commandOutcomeSummaryToLines,
  escapeExportAttr,
  escapeExportHtml,
  exportTimestamp,
  fetchTerminalExportCss,
  fetchVendorFontFacesCss,
  getThemeExportColorScheme,
  getThemeExportVars,
  isCommandOutcomeSummaryLine,
  isPlainEvent,
  isPromptEchoEvent,
  lineEventFromWire,
  lineLegacyClass,
  normalizeExportRunMeta,
  normalizeExportTranscriptLine,
  normalizeExportTranscriptLines,
  renderExportEntityContent,
  renderExportLineContent,
  renderExportPromptEcho,
} = ExportHtmlUtils;

export {
  ExportHtmlUtils,
  appendCommandOutcomeSummaryLines,
  buildExportCommandOutcomeSummary,
  buildExportDocumentModel,
  buildExportHeaderModel,
  buildExportLineSummary,
  buildExportLinesHtml,
  buildExportMetaLine,
  buildExportRunMetaHtml,
  buildExportRunMetaItems,
  buildTerminalExportHeaderHtml,
  buildTerminalExportHtml,
  buildTerminalExportStyles,
  commandOutcomeSummaryToLines,
  escapeExportAttr,
  escapeExportHtml,
  exportTimestamp,
  fetchTerminalExportCss,
  fetchVendorFontFacesCss,
  getThemeExportColorScheme,
  getThemeExportVars,
  isCommandOutcomeSummaryLine,
  isPlainEvent,
  isPromptEchoEvent,
  lineEventFromWire,
  lineLegacyClass,
  normalizeExportRunMeta,
  normalizeExportTranscriptLine,
  normalizeExportTranscriptLines,
  renderExportEntityContent,
  renderExportLineContent,
  renderExportPromptEcho,
};
