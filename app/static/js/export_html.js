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
  const PLAIN_CLASSES = new Set(['exit-ok', 'exit-fail', 'denied', 'notice']);

  function escapeExportHtml(text) {
    return String(text ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function renderExportPromptEcho(text) {
    const raw = String(text || '');
    const firstSpace = raw.indexOf(' ');
    const prefix = firstSpace === -1 ? raw : raw.slice(0, firstSpace);
    const remainder = firstSpace === -1 ? '' : raw.slice(firstSpace + 1);
    return '<span class="prompt-prefix">' + escapeExportHtml(prefix) + '</span>'
      + (remainder ? escapeExportHtml(' ' + remainder) : '');
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
      return { text: line, cls: '', tsC: '', tsE: '' };
    }
    if (line && typeof line.text === 'string') {
      return {
        text: line.text,
        cls: String(line.cls || ''),
        tsC: String(line.tsC || ''),
        tsE: String(line.tsE || ''),
        line_number: Number.isInteger(line.line_number) ? line.line_number : undefined,
      };
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
  }) {
    return {
      appName: String(appName || ''),
      title: String(title || ''),
      metaLine: buildExportMetaLine({ label, createdText }),
      runMeta: normalizeExportRunMeta(runMeta),
      rawLines: normalizeExportTranscriptLines(rawLines),
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
    const linesHtml = rawLines.map(({ text, cls }, i) => {
      const prefix = prefixes[i];
      const prefixSpan = prefix
        ? `<span class="perm-prefix">${escapeExportHtml(prefix)}</span>`
        : '';
      let content;
      if (cls === 'prompt-echo') {
        content = renderExportPromptEcho(text);
      } else if (PLAIN_CLASSES.has(cls)) {
        content = escapeExportHtml(text);
      } else {
        content = ansiToHtml(text);
      }
      return `<span class="line${cls ? ' ' + cls : ''}">${prefixSpan}<span class="perm-content">${content}</span></span>`;
    }).join('');
    return { linesHtml, prefixWidth };
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

  function buildTerminalExportHeaderHtml(headerModel) {
    const titleHtml = `<h1 class="export-title">${escapeExportHtml(headerModel.appName)}</h1>`;
    const metaHtml = headerModel.metaLine
      ? `<div class="export-meta">${escapeExportHtml(headerModel.metaLine)}</div>`
      : '';
    const runMetaHtml = headerModel.runMetaItems.length
      ? `<div class="export-run-meta">${buildExportRunMetaHtml(headerModel.runMetaItems)}</div>`
      : '';
    return `<header class="export-header">
  <div class="export-header-copy">
    ${titleHtml}
    ${metaHtml}
    ${runMetaHtml}
  </div>
</header>`;
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
    prefixWidth = 0,
    fontFacesCss = '',
    exportCss = '',
  }) {
    const colorScheme = getThemeExportColorScheme();
    const headerModel = buildExportHeaderModel({ appName, metaLine, runMeta });
    const styles = buildTerminalExportStyles(fontFacesCss, prefixWidth, exportCss);
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
<body>
${buildTerminalExportHeaderHtml(headerModel)}
<main class="export-output nice-scroll">
${linesHtml}
</main>
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
    normalizeExportRunMeta,
    buildExportDocumentModel,
    escapeExportHtml,
    renderExportPromptEcho,
    buildExportLinesHtml,
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
