// ── Shared HTML export helpers ───────────────────────────────────────────────
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

  function buildTerminalExportStyles(fontFacesCss = '') {
    const themeVars = getThemeExportVars();
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
  .header {
    margin-bottom: 20px;
    padding: 16px 18px;
    border: 1px solid var(--theme-terminal-bar-border, var(--border));
    background: var(--theme-terminal-bar-bg, var(--bg));
    border-radius: 4px 4px 0 0;
  }
  .app-name { color: var(--green); font-size: 18px; letter-spacing: 3px; margin-bottom: 6px; }
  .meta { color: var(--muted); font-size: 11px; }
  .output {
    white-space: pre-wrap;
    word-break: break-all;
    background: var(--theme-panel-bg, var(--surface));
    border: 1px solid var(--theme-panel-border, var(--border));
    border-top: none;
    border-radius: 0 0 4px 4px;
    padding: 16px 18px 18px;
    box-shadow: 0 12px 28px color-mix(in srgb, var(--theme-panel-shadow, transparent) 74%, transparent);
  }
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
    fontFacesCss = '',
  }) {
    const colorScheme = getThemeExportColorScheme();
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="color-scheme" content="${escapeExportHtml(colorScheme)}">
<title>${escapeExportHtml(title)} — ${escapeExportHtml(appName)}</title>
<style>
${buildTerminalExportStyles(fontFacesCss)}
</style>
</head>
<body>
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
