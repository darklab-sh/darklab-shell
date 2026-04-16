// ── Shared PDF export helpers ─────────────────────────────────────────────────
// Single source of truth for terminal PDF export. Both save-from-tab (tabs.js)
// and save-from-permalink (permalink.html) funnel through here.
(function () {
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
    const cs = getComputedStyle(document.documentElement);
    const v = (name) => cs.getPropertyValue(name).trim();
    return {
      bg:      parseCssColor(v('--bg')),
      surface: parseCssColor(v('--surface')),
      border:  parseCssColor(v('--border')),
      text:    parseCssColor(v('--text')),
      muted:   parseCssColor(v('--muted')),
      green:   parseCssColor(v('--green')),
      red:     parseCssColor(v('--red')),
      amber:   parseCssColor(v('--amber')),
      blue:    parseCssColor(v('--blue')),
    };
  }

  // Renders a single raw-text line (which may contain ANSI escapes) as a
  // sequence of coloured jsPDF text segments.
  function renderAnsiLine(doc, rawText, startX, y, defaultColor, ansiToHtml) {
    const html = ansiToHtml(rawText);
    const div = document.createElement('div');
    div.innerHTML = html;
    let x = startX;
    for (const node of div.childNodes) {
      const segment = node.textContent;
      if (!segment) continue;
      if (node.nodeType === Node.ELEMENT_NODE && node.style.color) {
        const [r, g, b] = parseCssColor(node.style.color);
        doc.setTextColor(r, g, b);
      } else {
        doc.setTextColor(...defaultColor);
      }
      doc.text(segment, x, y);
      x += doc.getTextWidth(segment);
    }
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
  // Returns the jsPDF doc (caller calls doc.save(filename)).
  function buildTerminalExportPdf({ jsPDF, appName, metaLine, runMeta, rawLines, getPrefix, ansiToHtml }) {
    const doc = new jsPDF({ unit: 'pt', format: 'a4' });
    const colors = themeColors();
    const pageW = doc.internal.pageSize.getWidth();
    const pageH = doc.internal.pageSize.getHeight();

    // Layout constants — 8.5pt ≈ 13px/96dpi; leading = 8.5 * 1.65
    const margin = 36;
    const fontSize = 8.5;
    const leading = 14;
    const maxLineW = pageW - margin * 2;

    // Header layout — baselines measured from page top
    // Baseline-to-baseline gaps match HTML flex-column proportions (~20pt title→meta, ~14pt meta→badge)
    const hPad = 18;
    const hAppNamePt = 13;
    const hMetaPt = 8;
    const hBadgePt = 7.5;
    const hAppNameY = hPad + hAppNamePt;         // 31
    const hMetaY    = hAppNameY + 20;            // 51
    const hBadgeY   = hMetaY + 14;              // 65
    const headerH   = Math.ceil(hBadgeY) + 14;  // 79

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
    doc.setFont('courier', 'normal');
    doc.setFontSize(hAppNamePt);
    doc.setTextColor(...colors.green);
    doc.setCharSpace(2);
    doc.text(appName, margin, hAppNameY);
    doc.setCharSpace(0);

    if (metaLine) {
      doc.setFontSize(hMetaPt);
      doc.setTextColor(...colors.muted);
      doc.text(metaLine, margin, hMetaY);
    }

    // Badge row
    doc.setFontSize(hBadgePt);
    let badgeX = margin;
    const badgePadX = 5;
    const badgePadY = 2;

    const renderBadge = (text, color, bordered) => {
      const tw = doc.getTextWidth(text);
      if (bordered) {
        // Draw border box like the HTML meta-badge.
        // Use cap height (0.72 em) not full em so padding is even above and below the glyphs.
        const capH  = hBadgePt * 0.72;
        const descH = hBadgePt * 0.20;
        doc.setDrawColor(...color);
        doc.setLineWidth(0.5);
        doc.rect(badgeX, hBadgeY - capH - badgePadY, tw + badgePadX * 2, capH + descH + badgePadY * 2, 'S');
        doc.setFont('courier', 'bold');
        doc.setTextColor(...color);
        doc.text(text, badgeX + badgePadX, hBadgeY);
        doc.setFont('courier', 'normal');
        badgeX += tw + badgePadX * 2 + 8;
      } else {
        doc.setTextColor(...color);
        doc.text(text, badgeX, hBadgeY);
        badgeX += tw + 10;
      }
    };

    if (runMeta) {
      const { exitCode, duration, lines, version } = runMeta;
      if (exitCode !== null && exitCode !== undefined) {
        renderBadge(`exit ${exitCode}`, exitCode === 0 ? colors.green : colors.red, true);
      }
      if (duration) renderBadge(String(duration).toUpperCase(), colors.muted, false);
      if (lines)    renderBadge(String(lines).toUpperCase(), colors.muted, false);
      if (version)  renderBadge(`v${version}`, colors.muted, false);
    }

    // Separator line between header and content
    doc.setDrawColor(...colors.border);
    doc.setLineWidth(0.5);
    doc.line(0, headerH, pageW, headerH);

    // Content
    doc.setFont('courier', 'normal');
    doc.setFontSize(fontSize);

    // Fixed-width prefix gutter
    const prefixes = rawLines.map((line, i) => getPrefix(line, i));
    const longestPrefix = prefixes.reduce((a, b) => a.length >= b.length ? a : b, '');
    const prefixColW = longestPrefix ? doc.getTextWidth(longestPrefix) + 10 : 0;

    let y = headerH + leading;
    const newPage = () => { doc.addPage(); fillBg(); y = margin + leading; };
    const checkPage = () => { if (y + leading > pageH - margin) newPage(); };

    for (let i = 0; i < rawLines.length; i++) {
      const { text, cls } = rawLines[i];
      checkPage();
      let x = margin;

      // Prefix gutter (timestamps / line numbers) — fixed column width
      if (prefixColW) {
        const prefix = prefixes[i];
        if (prefix) {
          doc.setTextColor(...colors.muted);
          doc.text(prefix, x, y);
        }
        x += prefixColW;
      }

      const stripped = text.replace(/\x1b\[[0-9;]*[A-Za-z]/g, '');
      const contentW = maxLineW - (x - margin);

      if (cls === 'exit-ok') {
        doc.setTextColor(...colors.green);
        doc.text(doc.splitTextToSize(stripped, contentW), x, y);
      } else if (cls === 'exit-fail') {
        doc.setTextColor(...colors.red);
        doc.text(doc.splitTextToSize(stripped, contentW), x, y);
      } else if (cls === 'denied') {
        doc.setTextColor(...colors.amber);
        doc.text(doc.splitTextToSize(stripped, contentW), x, y);
      } else if (cls === 'notice') {
        doc.setTextColor(...colors.blue);
        doc.text(doc.splitTextToSize(stripped, contentW), x, y);
      } else if (cls === 'prompt-echo') {
        const firstSpace = text.indexOf(' ');
        const pfx = firstSpace === -1 ? text : text.slice(0, firstSpace);
        const rest = firstSpace === -1 ? '' : text.slice(firstSpace);
        doc.setFont('courier', 'bold');
        doc.setTextColor(...colors.blue);
        doc.text(pfx, x, y);
        x += doc.getTextWidth(pfx);
        doc.setFont('courier', 'normal');
        if (rest) { doc.setTextColor(...colors.text); doc.text(rest, x, y); }
      } else {
        renderAnsiLine(doc, text, x, y, colors.text, ansiToHtml);
      }

      y += leading;
    }

    return doc;
  }

  window.ExportPdfUtils = {
    parseCssColor,
    themeColors,
    buildTerminalExportPdf,
  };
})();
