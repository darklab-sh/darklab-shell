// ── Shared HTML export helpers ───────────────────────────────────────────────
(function () {
  const EXPORT_FONT_FILES = [
    { family: 'JetBrains Mono', weight: 300, filename: 'JetBrainsMono-300.ttf' },
    { family: 'JetBrains Mono', weight: 400, filename: 'JetBrainsMono-400.ttf' },
    { family: 'JetBrains Mono', weight: 700, filename: 'JetBrainsMono-700.ttf' },
    { family: 'Syne', weight: 700, filename: 'Syne-700.ttf' },
    { family: 'Syne', weight: 800, filename: 'Syne-800.ttf' },
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

  function buildTerminalExportStyles(fontFacesCss = '') {
    return `${fontFacesCss}
  :root {
    --bg: #0d0d0d; --surface: #141414; --border: #2e2e2e; --border-bright: #2e2e2e;
    --green: #39ff14; --green-dim: #1a7a08; --green-glow: rgba(57,255,20,0.12);
    --amber: #ffb800; --red: #ff3c3c; --muted: #606060; --text: #e0e0e0;
  }
  body.light {
    --bg: #e7e6e1; --surface: #f2f0eb; --border: #b8b7b0; --border-bright: #a9a79f;
    --green: #2a5d18; --green-dim: #355f24; --green-glow: rgba(42,93,24,0.08);
    --amber: #b37000; --red: #cc2200; --muted: #45453f; --text: #101010;
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
  .line.notice    { color: #6ab0f5; font-style: italic; }
  .ts {
    display: inline-block; min-width: 58px; text-align: right;
    color: #505050; font-size: 10px; user-select: none;
    padding-right: 8px; margin-right: 6px;
    border-right: 1px solid var(--border);
    font-variant-numeric: tabular-nums;
  }
  .prompt-prefix { color: #6ab0f5; font-weight: 700; margin-right: 8px; }
  body.light .prompt-prefix { color: #335d83; }`;
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
${buildTerminalExportStyles(fontFacesCss)}
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
