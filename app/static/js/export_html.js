// ── Shared HTML export helpers ───────────────────────────────────────────────
(function () {
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
    '--terminal-font-size',
    '--terminal-line-height',
  ];

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

  function getThemeExportVars(themeClass = '') {
    const source = window.ThemeCssVars && window.ThemeCssVars[themeClass === 'light' ? 'light' : 'dark'];
    if (source && typeof source === 'object') return source;
    const target = themeClass === 'light' && document.body && document.body.classList.contains('light')
      ? document.body
      : document.documentElement;
    const computed = getComputedStyle(target);
    const fallback = {};
    for (const name of EXPORT_THEME_VAR_NAMES) {
      const value = computed.getPropertyValue(name).trim();
      if (value) fallback[name] = value;
    }
    if (Object.keys(fallback).length) return fallback;
    return {};
  }

  function buildTerminalExportStyles(themeClass = '', fontFacesCss = '') {
    const themeVars = getThemeExportVars(themeClass);
    const themeDecls = Object.entries(themeVars)
      .map(([name, value]) => `    ${name}: ${value};`)
      .join('\n');
    return `${fontFacesCss}
  :root {
${themeDecls}
  }
  *, *::before, *::after { box-sizing: border-box; }
  body {
    background: var(--bg); color: var(--text);
    font-family: 'JetBrains Mono', monospace; font-size: 13px;
    padding: 28px 32px; margin: 0; line-height: 1.65;
  }
  body.light { color: var(--text); }
  .header {
    margin-bottom: 20px; padding-bottom: 14px;
    border-bottom: 1px solid var(--border);
  }
  body.light .header { border-bottom-color: var(--border-bright); }
  .app-name { color: var(--green); font-size: 18px; letter-spacing: 3px; margin-bottom: 6px; }
  .meta { color: var(--muted); font-size: 11px; }
  .output { white-space: pre-wrap; word-break: break-all; }
  .line { display: block; }
  .line.exit-ok   { color: var(--green); font-weight: 700; margin-top: 8px; }
  .line.exit-fail { color: var(--red); font-weight: 700; margin-top: 8px; }
  .line.denied    { color: var(--amber); font-weight: 700; }
  .line.notice    { color: var(--blue); font-style: italic; }
  .ts {
    display: inline-block; min-width: 58px; text-align: right;
    color: var(--muted); font-size: 10px; user-select: none;
    padding-right: 8px; margin-right: 6px;
    border-right: 1px solid var(--border);
    font-variant-numeric: tabular-nums;
  }
  .prompt-prefix { color: var(--blue); font-weight: 700; margin-right: 8px; }`;
  }

  function buildTerminalExportHtml({
    appName,
    title,
    metaHtml = '',
    linesHtml = '',
    themeClass = '',
    fontFacesCss = '',
  }) {
    const bodyClass = themeClass ? ` class="${themeClass}"` : '';
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>${escapeExportHtml(title)} — ${escapeExportHtml(appName)}</title>
<style>
${buildTerminalExportStyles(themeClass, fontFacesCss)}
</style>
</head>
<body${bodyClass}>
<div class="header">
  <div class="app-name">${escapeExportHtml(appName)}</div>
  ${metaHtml ? `<div class="meta">${metaHtml}</div>` : ''}
</div>
<div class="output">
${linesHtml}
</div>
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
    buildTerminalExportHtml,
    buildTerminalExportStyles,
    fetchVendorFontFacesCss,
  };
})();
