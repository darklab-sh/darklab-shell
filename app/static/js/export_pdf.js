// ── Shared PDF export helpers ─────────────────────────────────────────────────
// Single source of truth for terminal PDF export. Both save-from-tab (tabs.js)
// and save-from-permalink (permalink.html) funnel through here.
(function () {
  const PDF_FONT_SPECS = [
    { filename: 'JetBrainsMono-400.ttf', family: 'JetBrains Mono', style: 'normal' },
    { filename: 'JetBrainsMono-700.ttf', family: 'JetBrains Mono', style: 'bold' },
  ];
  let _cachedPdfFontFiles = null;

  function parseCssColor(cssColor) {
    // Normalise any CSS color string to [r, g, b] by painting it onto a canvas.
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 1;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#888'; // sentinel — lets us detect parse failures
    ctx.fillStyle = cssColor;
    ctx.fillRect(0, 0, 1, 1);
    const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data;
    return [r, g, b];
  }

  function themeColors() {
    const themeVars = window.ExportHtmlUtils
      && typeof window.ExportHtmlUtils.getThemeExportVars === 'function'
      ? window.ExportHtmlUtils.getThemeExportVars()
      : null;
    const cs = getComputedStyle(document.documentElement);
    const v = (name) => {
      if (themeVars && typeof themeVars[name] === 'string' && themeVars[name].trim()) return themeVars[name].trim();
      return cs.getPropertyValue(name).trim();
    };
    return {
      bg:      parseCssColor(v('--bg')),
      surface: parseCssColor(v('--surface')),
      border:  parseCssColor(v('--border')),
      panelBorder: parseCssColor(v('--theme-panel-border') || v('--border')),
      text:    parseCssColor(v('--text')),
      muted:   parseCssColor(v('--muted')),
      green:   parseCssColor(v('--green')),
      greenDim: parseCssColor(v('--green-dim') || v('--green')),
      red:     parseCssColor(v('--red')),
      amber:   parseCssColor(v('--amber')),
      blue:    parseCssColor(v('--blue')),
    };
  }

  function mixColor(a, b, ratio) {
    const mix = typeof ratio === 'number' ? ratio : 0.5;
    return [
      Math.round(a[0] + (b[0] - a[0]) * mix),
      Math.round(a[1] + (b[1] - a[1]) * mix),
      Math.round(a[2] + (b[2] - a[2]) * mix),
    ];
  }

  function withSegmentFont(doc, fontFamily, segment, fn) {
    const style = segment.fontStyle || 'normal';
    doc.setFont(fontFamily, style);
    return fn();
  }

  function measureSegmentText(doc, fontFamily, segment, text) {
    return withSegmentFont(doc, fontFamily, segment, () => doc.getTextWidth(text));
  }

  function parseAnsiSegments(rawText, defaultColor, ansiToHtml) {
    const html = ansiToHtml(rawText);
    const div = document.createElement('div');
    div.innerHTML = html;
    const segments = [];
    for (const node of div.childNodes) {
      const text = node.textContent;
      if (!text) continue;
      if (node.nodeType === Node.ELEMENT_NODE && node.style.color) {
        segments.push({ text, color: parseCssColor(node.style.color), fontStyle: 'normal' });
      } else {
        segments.push({ text, color: defaultColor, fontStyle: 'normal' });
      }
    }
    return segments;
  }

  function buildPdfLineSegments({ text, cls, colors, ansiToHtml }) {
    const stripped = text.replace(/\x1b\[[0-9;]*[A-Za-z]/g, '');
    if (cls === 'exit-ok') return [{ text: stripped, color: colors.green, fontStyle: 'normal' }];
    if (cls === 'exit-fail') return [{ text: stripped, color: colors.red, fontStyle: 'normal' }];
    if (cls === 'denied') return [{ text: stripped, color: colors.amber, fontStyle: 'normal' }];
    if (cls === 'notice') return [{ text: stripped, color: colors.blue, fontStyle: 'normal' }];
    if (cls === 'prompt-echo') {
      const firstSpace = text.indexOf(' ');
      const prompt = firstSpace === -1 ? text : text.slice(0, firstSpace);
      const rest = firstSpace === -1 ? '' : text.slice(firstSpace);
      const segments = [{ text: prompt, color: colors.blue, fontStyle: 'bold' }];
      if (rest) segments.push({ text: rest, color: colors.text, fontStyle: 'normal' });
      return segments;
    }
    return parseAnsiSegments(text, colors.text, ansiToHtml);
  }

  function splitSegmentTokens(segment) {
    const parts = segment.text.match(/\S+|\s+/g) || [''];
    return parts.map((text) => ({ text, color: segment.color, fontStyle: segment.fontStyle }));
  }

  function wrapPdfSegments(doc, fontFamily, segments, maxWidth) {
    const lines = [];
    let currentLine = [];
    let currentWidth = 0;

    function pushCurrentLine() {
      lines.push(currentLine);
      currentLine = [];
      currentWidth = 0;
    }

    function pushToken(token) {
      if (!token.text) return;
      const width = measureSegmentText(doc, fontFamily, token, token.text);
      if (currentWidth > 0 && currentWidth + width > maxWidth) {
        pushCurrentLine();
      }
      currentLine.push(token);
      currentWidth += width;
    }

    function pushTokenSplit(token) {
      let chunk = '';
      for (const ch of token.text) {
        const next = chunk + ch;
        const nextWidth = measureSegmentText(doc, token, next);
        if (chunk && currentWidth + nextWidth > maxWidth) {
          pushToken({ ...token, text: chunk });
          chunk = ch;
          if (!currentLine.length && measureSegmentText(doc, fontFamily, token, chunk) > maxWidth) {
            pushToken({ ...token, text: chunk });
            chunk = '';
          }
          continue;
        }
        chunk = next;
      }
      if (chunk) pushToken({ ...token, text: chunk });
    }

    for (const segment of segments) {
      for (const token of splitSegmentTokens(segment)) {
        const width = measureSegmentText(doc, fontFamily, token, token.text);
        if (width <= maxWidth) {
          pushToken(token);
        } else {
          pushTokenSplit(token);
        }
      }
    }

    if (currentLine.length || !lines.length) pushCurrentLine();
    return lines;
  }

  function renderWrappedPdfLine(doc, fontFamily, wrappedLine, startX, y) {
    let x = startX;
    for (const segment of wrappedLine) {
      if (!segment.text) continue;
      withSegmentFont(doc, fontFamily, segment, () => {
        doc.setTextColor(...segment.color);
        doc.text(segment.text, x, y);
        x += doc.getTextWidth(segment.text);
      });
    }
  }

  async function _fetchPdfFontFiles() {
    if (_cachedPdfFontFiles) return _cachedPdfFontFiles;
    const entries = await Promise.all(PDF_FONT_SPECS.map(async (font) => {
      const res = await fetch(`/vendor/fonts/${font.filename}`);
      if (!res.ok) throw new Error(`Failed to load PDF font: ${font.filename}`);
      const buf = await res.arrayBuffer();
      const bytes = new Uint8Array(buf);
      let binary = '';
      const chunkSize = 0x8000;
      for (let i = 0; i < bytes.length; i += chunkSize) {
        binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
      }
      return { ...font, binary };
    }));
    _cachedPdfFontFiles = entries;
    return entries;
  }

  async function ensurePdfFonts(doc) {
    if (typeof doc.addFileToVFS !== 'function' || typeof doc.addFont !== 'function') return false;
    const fonts = await _fetchPdfFontFiles();
    for (const font of fonts) {
      doc.addFileToVFS(font.filename, font.binary);
      doc.addFont(font.filename, font.family, font.style);
    }
    return true;
  }

  function hasRenderableSegments(segments) {
    return segments.some((segment) => segment && segment.text);
  }

  // Build a complete terminal-style PDF document.
  //
  // opts:
  //   jsPDF      — jsPDF constructor (callers extract from window.jspdf)
  //   appName    — displayed in the header (green, letter-spaced)
  //   metaLine   — subtitle shown below app name (label + date string)
  //   runMeta    — optional { exitCode, duration, lines, version }
  //   rawLines   — array of { text, cls }
  //   getPrefix  — (line, i) => string for the gutter column
  //   ansiToHtml — (text) => html string from an AnsiUp instance
  //
  // Returns a Promise resolving to the jsPDF doc (caller calls doc.save(filename)).
  async function buildTerminalExportPdf({ jsPDF, appName, metaLine, runMeta, rawLines, getPrefix, ansiToHtml }) {
    const doc = new jsPDF({ unit: 'pt', format: 'a4' });
    const embeddedFontsReady = await ensurePdfFonts(doc).catch(() => false);
    const monoFontFamily = embeddedFontsReady ? 'JetBrains Mono' : 'courier';
    const colors = themeColors();
    const headerModel = window.ExportHtmlUtils
      && typeof window.ExportHtmlUtils.buildExportHeaderModel === 'function'
      ? window.ExportHtmlUtils.buildExportHeaderModel({ appName, metaLine, runMeta })
      : {
          appName: String(appName || ''),
          metaLine: metaLine ? String(metaLine) : '',
          runMetaItems: [],
        };
    const pageW = doc.internal.pageSize.getWidth();
    const pageH = doc.internal.pageSize.getHeight();

    // Layout constants — 8.5pt ≈ 13px/96dpi; leading = 8.5 * 1.65
    const fontSize = 8.5;
    const leading = 14;
    const outputBoxX = 1;
    const outputBoxPadX = 20;
    const outputBoxPadTop = 16;
    const outputBoxPadBottom = 20;

    // Header layout — baselines measured from page top
    // Tuned against terminal_export.css: 16px top/bottom padding, 20px title,
    // 4px title→meta gap, 3px meta→badge spacing.
    const hPad = 12;
    const hAppNamePt = 15;
    const hMetaPt = 7.5;
    const hBadgePt = 7.5;
    const hAppNameY = hPad + hAppNamePt;
    const hMetaY    = hAppNameY + 13;
    const hBadgeY   = hMetaY + 12;
    const headerH   = Math.ceil(hBadgeY) + 16;

    // Content pages use surface (lighter); header bar uses bg (darker) — matches HTML export
    const fillBg = () => {
      doc.setFillColor(...colors.surface);
      doc.rect(0, 0, pageW, pageH, 'F');
    };

    fillBg();

    // Header background — darker than content, like the terminal bar
    doc.setFillColor(...colors.bg);
    doc.rect(0, 0, pageW, headerH, 'F');

    // App name — normal weight + char spacing to simulate CSS letter-spacing
    doc.setFont(monoFontFamily, 'normal');
    doc.setFontSize(hAppNamePt);
    doc.setTextColor(...colors.green);
    doc.setCharSpace(2);
    doc.text(headerModel.appName, outputBoxPadX, hAppNameY);
    doc.setCharSpace(0);

    if (headerModel.metaLine) {
      doc.setFontSize(hMetaPt);
      doc.setTextColor(...colors.muted);
      doc.text(headerModel.metaLine, outputBoxPadX, hMetaY);
    }

    // Badge row
    doc.setFontSize(hBadgePt);
    let badgeX = outputBoxPadX;
    const badgePadX = 6;
    const badgePadY = 2.5;

    const renderBadge = (text, color, bordered, borderColor) => {
      const tw = doc.getTextWidth(text);
      if (bordered) {
        // Draw border box like the HTML meta-badge.
        // Use cap height (0.72 em) not full em so padding is even above and below the glyphs.
        const capH  = hBadgePt * 0.68;
        const descH = hBadgePt * 0.22;
        doc.setDrawColor(...(borderColor || color));
        doc.setLineWidth(0.4);
        doc.rect(
          badgeX,
          hBadgeY - capH - badgePadY,
          tw + badgePadX * 2,
          capH + descH + badgePadY * 2,
          'S',
        );
        doc.setFont(monoFontFamily, 'bold');
        doc.setTextColor(...color);
        doc.text(text, badgeX + badgePadX, hBadgeY + 0.9);
        doc.setFont(monoFontFamily, 'normal');
        badgeX += tw + badgePadX * 2 + 8;
      } else {
        doc.setTextColor(...color);
        doc.text(text, badgeX, hBadgeY);
        badgeX += tw + 10;
      }
    };

    for (const item of headerModel.runMetaItems) {
      if (item.kind === 'badge') {
        renderBadge(
          item.text,
          item.tone === 'ok' ? colors.green : colors.red,
          true,
          item.tone === 'ok' ? colors.greenDim : colors.red,
        );
      } else {
        renderBadge(item.text.toUpperCase(), colors.muted, false, null);
      }
    }

    const outputBorderColor = mixColor(colors.panelBorder, colors.text, 0.09);

    // Separator line between header and content
    doc.setDrawColor(...outputBorderColor);
    doc.setLineWidth(0.55);
    doc.line(0, headerH, pageW, headerH);
    doc.rect(outputBoxX, headerH, pageW - outputBoxX * 2, pageH - headerH, 'S');

    // Content
    doc.setFont(monoFontFamily, 'normal');
    doc.setFontSize(fontSize);

    // Fixed-width prefix gutter
    const prefixes = rawLines.map((line, i) => getPrefix(line, i));
    const longestPrefix = prefixes.reduce((a, b) => a.length >= b.length ? a : b, '');
    const prefixColW = longestPrefix ? doc.getTextWidth(longestPrefix) + 10 : 0;

    let y = headerH + outputBoxPadTop + fontSize;
    const newPage = () => {
      doc.addPage();
      fillBg();
      doc.setDrawColor(...outputBorderColor);
      doc.setLineWidth(0.55);
      doc.rect(outputBoxX, 0, pageW - outputBoxX * 2, pageH, 'S');
      y = outputBoxPadTop + fontSize;
    };
    const checkPage = () => { if (y + leading > pageH - outputBoxPadBottom) newPage(); };

    for (let i = 0; i < rawLines.length; i++) {
      const { text, cls } = rawLines[i];
      checkPage();
      let x = outputBoxPadX;

      // Prefix gutter (timestamps / line numbers) — fixed column width
      if (prefixColW) {
        const prefix = prefixes[i];
        if (prefix) {
          doc.setTextColor(...colors.muted);
          doc.text(prefix, x, y);
        }
        x += prefixColW;
      }

      const contentW = (pageW - outputBoxPadX * 2) - (x - outputBoxPadX);

      const segments = buildPdfLineSegments({ text, cls, colors, ansiToHtml });
      if (!prefixes[i] && !hasRenderableSegments(segments)) continue;
      const wrappedLines = wrapPdfSegments(doc, monoFontFamily, segments, contentW);

      for (let lineIndex = 0; lineIndex < wrappedLines.length; lineIndex++) {
        checkPage();
        renderWrappedPdfLine(doc, monoFontFamily, wrappedLines[lineIndex], x, y);
        y += leading;
      }
    }

    return doc;
  }

  window.ExportPdfUtils = {
    parseCssColor,
    themeColors,
    buildTerminalExportPdf,
  };
})();
