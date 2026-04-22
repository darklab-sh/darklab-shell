// ── Permalink page controller ──────────────────────────────────────────────
// Handles live transcript rendering, toggle wiring, save actions, and copy/txt
// for /history/<run_id> and /share/<id> permalink pages.
//
// Server-rendered data is provided via window.PermData, set by the inline
// <script> block in the template before this module loads.
// Shared helpers come from ExportHtmlUtils (export_html.js), ExportPdfUtils
// (export_pdf.js), copyTextToClipboard and showToast (utils.js) — all loaded
// in permalink_base.html before this file.
(function () {
  var pd = window.PermData || {};
  var lines               = pd.lines               || [];
  var hasTimestampMetadata = pd.hasTimestampMetadata || false;
  var appName             = pd.appName             || '';
  var label               = pd.label               || '';
  var created             = pd.created             || '';
  var createdDisplay      = pd.createdDisplay      || '';
  var fontFacesCss        = pd.fontFacesCss        || '';
  var permalinkMeta       = pd.permalinkMeta       || null;

  var ansiUp = new AnsiUp();
  ansiUp.use_classes = false;

  var out = document.getElementById('output');
  var PLAIN_CLASSES = new Set(['exit-ok', 'exit-fail', 'denied', 'notice']);
  var tsModes = ['off', 'elapsed', 'clock'];

  // ── Preference cookies ─────────────────────────────────────────────────────
  function getCookie(name) {
    var prefix = name + '=';
    var match = document.cookie.split(';').map(function (p) { return p.trim(); }).find(function (p) { return p.startsWith(prefix); });
    return match ? decodeURIComponent(match.slice(prefix.length)) : '';
  }

  var lnMode = getCookie('pref_line_numbers') === 'on' ? 'on' : 'off';
  var tsMode = tsModes.includes(getCookie('pref_timestamps')) ? getCookie('pref_timestamps') : 'off';
  if (!hasTimestampMetadata) tsMode = 'off';

  // ── Prefix formatting ──────────────────────────────────────────────────────
  function timestampText(entry) {
    if (tsMode === 'clock') return entry.tsC || '';
    if (tsMode === 'elapsed') return entry.tsE || '';
    return '';
  }

  function formatPrefix(index, entry) {
    var parts = [];
    if (lnMode === 'on') parts.push(String(index));
    var ts = timestampText(entry);
    if (ts) parts.push(ts);
    return parts.join(' ');
  }

  function displayText(entry, index) {
    var prefix = formatPrefix(index + 1, entry);
    return (prefix ? prefix + '  ' : '') + String(entry.text || '');
  }

  // ── Transcript rendering ───────────────────────────────────────────────────
  function renderOutput() {
    out.innerHTML = '';
    var prefixes = lines.map(function (entry, index) { return formatPrefix(index + 1, entry); });
    var prefixWidth = Math.max(0, Math.max.apply(null, prefixes.map(function (p) { return p.length; })));
    out.style.setProperty('--perm-prefix-width', prefixWidth + 'ch');

    lines.forEach(function (entry, index) {
      var span = document.createElement('span');
      var cls = entry.cls || '';
      span.className = 'line' + (cls ? ' ' + cls : '');

      var prefix = prefixes[index];
      if (prefix) {
        var prefixEl = document.createElement('span');
        prefixEl.className = 'perm-prefix';
        prefixEl.textContent = prefix;
        span.appendChild(prefixEl);
      }

      var contentEl = document.createElement('span');
      contentEl.className = 'perm-content';
      if (cls === 'prompt-echo') {
        contentEl.innerHTML = ExportHtmlUtils.renderExportPromptEcho(entry.text);
      } else if (PLAIN_CLASSES.has(cls)) {
        contentEl.textContent = entry.text;
      } else {
        contentEl.innerHTML = ansiUp.ansi_to_html(entry.text);
      }
      span.appendChild(contentEl);
      out.appendChild(span);
    });

    document.getElementById('toggle-ln').textContent = 'line numbers: ' + lnMode;
    var tsBtn = document.getElementById('toggle-ts');
    tsBtn.textContent = hasTimestampMetadata ? 'timestamps: ' + tsMode : 'timestamps: unavailable';
  }

  // ── Toggle wiring ──────────────────────────────────────────────────────────
  document.getElementById('toggle-ln').addEventListener('click', function () {
    lnMode = lnMode === 'on' ? 'off' : 'on';
    renderOutput();
  });

  document.getElementById('toggle-ts').addEventListener('click', function () {
    if (!hasTimestampMetadata) return;
    tsMode = tsModes[(tsModes.indexOf(tsMode) + 1) % tsModes.length];
    renderOutput();
  });

  // ── Save dropdown ──────────────────────────────────────────────────────────
  (function () {
    var wrap = document.getElementById('perm-save-wrap');
    var btn = document.getElementById('perm-save-btn');
    if (!wrap || !btn) return;
    btn.addEventListener('click', function () {
      wrap.classList.toggle('open');
    });
    if (typeof bindOutsideClickClose === 'function') {
      bindOutsideClickClose(wrap, {
        triggers: btn,
        isOpen: function () { return wrap.classList.contains('open'); },
        onClose: function () { wrap.classList.remove('open'); },
      });
    }
  })();

  // ── Filename helper ────────────────────────────────────────────────────────
  function downloadName(ext) {
    return appName + '-' + ExportHtmlUtils.exportTimestamp() + '.' + ext;
  }

  // ── Export actions ─────────────────────────────────────────────────────────
  function copyTxt() {
    var text = lines.map(function (entry, index) { return displayText(entry, index); }).join('\n');
    copyTextToClipboard(text).then(function () { showToast('Copied to clipboard'); }).catch(function () {});
  }

  function saveTxt() {
    var text = lines.map(function (entry, index) { return displayText(entry, index); }).join('\n');
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], {type: 'text/plain'}));
    a.download = downloadName('txt');
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function saveHtml() {
    var result = ExportHtmlUtils.buildExportLinesHtml(lines, {
      getPrefix: function (entry, i) { return formatPrefix(i + 1, entry); },
      ansiToHtml: function (text) { return ansiUp.ansi_to_html(text); },
    });
    var linesHtml = result.linesHtml;
    var prefixWidth = result.prefixWidth;

    var runMeta = permalinkMeta ? {
      exitCode: permalinkMeta.exit_code,
      duration: permalinkMeta.duration || null,
      lines:    permalinkMeta.lines    || null,
      version:  permalinkMeta.version  || null,
    } : null;

    ExportHtmlUtils.fetchTerminalExportCss().catch(function () { return ''; }).then(function (exportCss) {
      var html = ExportHtmlUtils.buildTerminalExportHtml({
        appName: appName,
        title: label,
        metaLine: ExportHtmlUtils.buildExportMetaLine({
          label: label,
          createdText: createdDisplay || created,
        }),
        runMeta: runMeta,
        linesHtml: linesHtml,
        prefixWidth: prefixWidth,
        fontFacesCss: fontFacesCss,
        exportCss: exportCss,
      });
      var a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([html], {type: 'text/html'}));
      a.download = downloadName('html');
      a.click();
      URL.revokeObjectURL(a.href);
    });
  }

  async function savePdf() {
    if (!window.jspdf) { alert('PDF library not loaded'); return; }
    var jsPDF = window.jspdf.jsPDF;
    var runMeta = permalinkMeta ? {
      exitCode: permalinkMeta.exit_code,
      duration: permalinkMeta.duration || null,
      lines:    permalinkMeta.lines    || null,
      version:  permalinkMeta.version  || null,
    } : null;
    var ansiUpPdf = new AnsiUp();
    ansiUpPdf.use_classes = false;
    var doc = await ExportPdfUtils.buildTerminalExportPdf({
      jsPDF: jsPDF,
      appName: appName,
      metaLine: ExportHtmlUtils.buildExportMetaLine({
        label: label,
        createdText: createdDisplay || created,
      }),
      runMeta: runMeta,
      rawLines: lines,
      getPrefix: function (entry, i) { return formatPrefix(i + 1, entry); },
      ansiToHtml: function (text) { return ansiUpPdf.ansi_to_html(text); },
    });
    doc.save(downloadName('pdf'));
  }

  // ── Button action dispatch ─────────────────────────────────────────────────
  document.addEventListener('click', function (e) {
    var target = e.target.closest('[data-action]');
    if (!target) return;
    var action = target.dataset.action;
    if (action === 'copy-txt') copyTxt();
    else if (action === 'save-txt') saveTxt();
    else if (action === 'save-html') saveHtml();
    else if (action === 'save-pdf') void savePdf();
    else return;
    var saveWrap = document.getElementById('perm-save-wrap');
    if (saveWrap) saveWrap.classList.remove('open');
  });

  // ── Initial render ─────────────────────────────────────────────────────────
  renderOutput();
})();
