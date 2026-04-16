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
    '--theme-terminal-bar-border',
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

  // ── Run-meta badge row ────────────────────────────────────────────────────
  // runMeta: { exitCode, duration, lines, version } — all fields optional/null
  function _buildRunMetaHtml(runMeta) {
    if (!runMeta) return '';
    const parts = [];
    const { exitCode, duration, lines, version } = runMeta;
    if (exitCode !== null && exitCode !== undefined) {
      const cls = exitCode === 0 ? 'meta-badge-ok' : 'meta-badge-fail';
      parts.push(`<span class="meta-badge ${cls}">exit ${exitCode}</span>`);
    }
    if (duration) parts.push(`<span class="meta-item">${escapeExportHtml(String(duration))}</span>`);
    if (lines)    parts.push(`<span class="meta-item">${escapeExportHtml(String(lines))}</span>`);
    if (version)  parts.push(`<span class="meta-item">v${escapeExportHtml(String(version))}</span>`);
    return parts.join('');
  }

  // ── Styles ────────────────────────────────────────────────────────────────
  // Produces the full inline CSS for an export document, matching the
  // permalink-page layout. prefixWidth sets the gutter column width in ch.
  function buildTerminalExportStyles(fontFacesCss = '', prefixWidth = 0) {
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
    font-size: 13px;
    line-height: 1.65;
  }
  .export-header {
    display: flex;
    align-items: baseline;
    gap: 14px;
    padding: 16px 20px;
    border-bottom: 1px solid var(--theme-terminal-bar-border, var(--border));
    background: var(--theme-terminal-bar-bg, var(--bg));
    flex-wrap: wrap;
  }
  .export-header-copy {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .export-title {
    font-size: 20px;
    font-weight: 300;
    letter-spacing: 4px;
    color: var(--green);
    text-shadow: 0 0 20px var(--green-glow);
  }
  .export-meta {
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 1.5px;
  }
  .export-run-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    margin-top: 3px;
  }
  .meta-badge {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 1px 7px;
    border-radius: 2px;
    border: 1px solid;
  }
  .meta-badge-ok   { color: var(--green); border-color: var(--green-dim); }
  .meta-badge-fail { color: var(--red);   border-color: var(--red); }
  .meta-item {
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 1.5px;
    text-transform: uppercase;
  }
  .export-output {
    flex: 1;
    padding: 16px 20px 20px;
    white-space: pre-wrap;
    word-break: break-all;
    overflow-wrap: anywhere;
    background: var(--theme-panel-bg, var(--surface));
    border: 1px solid var(--theme-panel-border, var(--border));
  }
  .line { display: block; }
  .line.exit-ok   { color: var(--green); font-weight: 700; }
  .line.exit-fail { color: var(--red);   font-weight: 700; }
  .line.denied    { color: var(--amber); font-weight: 700; }
  .line.notice    { color: var(--blue);  font-style: italic; }
  .perm-prefix {
    display: inline-block;
    min-width: var(--perm-prefix-width, 0ch);
    margin-right: 14px;
    color: var(--muted);
    font-size: 10px;
    user-select: none;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .perm-content { display: inline; }
  .prompt-prefix { color: var(--blue); font-weight: 700; margin-right: 8px; }`;
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
  }) {
    const colorScheme = getThemeExportColorScheme();
    const runMetaHtml = _buildRunMetaHtml(runMeta);
    const styles = buildTerminalExportStyles(fontFacesCss, prefixWidth);
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
<header class="export-header">
  <div class="export-header-copy">
    <div class="export-title">${escapeExportHtml(appName)}</div>
    ${metaLine ? `<div class="export-meta">${escapeExportHtml(metaLine)}</div>` : ''}
    ${runMetaHtml ? `<div class="export-run-meta">${runMetaHtml}</div>` : ''}
  </div>
</header>
<main class="export-output">
${linesHtml}
</main>
</body>
</html>`;
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
    escapeExportHtml,
    renderExportPromptEcho,
    buildExportLinesHtml,
    buildTerminalExportHtml,
    buildTerminalExportStyles,
    fetchVendorFontFacesCss,
  };
})();
