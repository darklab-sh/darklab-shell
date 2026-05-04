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
  var transcriptModel = pd.transcript || {};
  var exportModel = pd.export || {};
  var headerModel = pd.header || {};
  var lines = window.ExportHtmlUtils && typeof ExportHtmlUtils.normalizeExportTranscriptLines === 'function'
    ? ExportHtmlUtils.normalizeExportTranscriptLines(transcriptModel.lines || pd.lines || [])
    : (transcriptModel.lines || pd.lines || []);
  var hasTimestampMetadata = transcriptModel.hasTimestampMetadata || pd.hasTimestampMetadata || false;
  var appName = exportModel.appName || pd.appName || headerModel.appName || '';
  var label = exportModel.label || pd.label || '';
  var created = exportModel.created || pd.created || '';
  var createdDisplay = exportModel.createdDisplay || pd.createdDisplay || headerModel.createdDisplay || '';
  var fontFacesCss = exportModel.fontFacesCss || pd.fontFacesCss || '';
  var permalinkMeta = window.ExportHtmlUtils && typeof ExportHtmlUtils.normalizeExportRunMeta === 'function'
    ? ExportHtmlUtils.normalizeExportRunMeta(exportModel.runMeta || pd.permalinkMeta || null)
    : (exportModel.runMeta || pd.permalinkMeta || null);

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
    var menu = wrap ? wrap.querySelector('.save-menu') : null;
    if (!wrap || !btn) return;
    function resetSaveMenuPosition() {
      if (!menu) return;
      menu.style.position = '';
      menu.style.top = '';
      menu.style.left = '';
      menu.style.right = '';
      menu.style.width = '';
      menu.style.maxWidth = '';
    }
    function positionSaveMenu() {
      if (!menu) return;
      if (!window.matchMedia || !window.matchMedia('(max-width: 640px)').matches) {
        resetSaveMenuPosition();
        return;
      }
      if (!wrap.classList.contains('open')) return;
      var margin = 12;
      var viewportWidth = Math.max(0, window.innerWidth || document.documentElement.clientWidth || 0);
      var rect = btn.getBoundingClientRect();
      var menuWidth = Math.min(220, Math.max(0, viewportWidth - margin * 2));
      var maxLeft = Math.max(margin, viewportWidth - menuWidth - margin);
      var left = Math.min(Math.max(rect.left, margin), maxLeft);
      menu.style.position = 'fixed';
      menu.style.top = Math.round(rect.bottom - 1) + 'px';
      menu.style.left = Math.round(left) + 'px';
      menu.style.right = 'auto';
      menu.style.width = Math.round(menuWidth) + 'px';
      menu.style.maxWidth = 'calc(100vw - 24px)';
    }
    function closeSaveMenu() {
      wrap.classList.remove('open');
      resetSaveMenuPosition();
    }
    btn.addEventListener('click', function () {
      wrap.classList.toggle('open');
      if (wrap.classList.contains('open')) positionSaveMenu();
      else resetSaveMenuPosition();
    });
    if (typeof window.addEventListener === 'function') {
      window.addEventListener('resize', positionSaveMenu);
      window.addEventListener('scroll', positionSaveMenu, true);
    }
    if (typeof bindOutsideClickClose === 'function') {
      bindOutsideClickClose(wrap, {
        triggers: btn,
        isOpen: function () { return wrap.classList.contains('open'); },
        onClose: closeSaveMenu,
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
    var exportModel = ExportHtmlUtils.buildExportDocumentModel({
      appName: appName,
      title: label,
      label: label,
      createdText: createdDisplay || created,
      runMeta: permalinkMeta,
      rawLines: lines,
    });
    var result = ExportHtmlUtils.buildExportLinesHtml(exportModel.rawLines, {
      getPrefix: function (entry, i) { return formatPrefix(i + 1, entry); },
      ansiToHtml: function (text) { return ansiUp.ansi_to_html(text); },
    });
    var linesHtml = result.linesHtml;
    var prefixWidth = result.prefixWidth;

    ExportHtmlUtils.fetchTerminalExportCss().catch(function () { return ''; }).then(function (exportCss) {
      var html = ExportHtmlUtils.buildTerminalExportHtml({
        appName: exportModel.appName,
        title: exportModel.title,
        metaLine: exportModel.metaLine,
        runMeta: exportModel.runMeta,
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
    var exportModel = ExportHtmlUtils.buildExportDocumentModel({
      appName: appName,
      title: label,
      label: label,
      createdText: createdDisplay || created,
      runMeta: permalinkMeta,
      rawLines: lines,
    });
    var ansiUpPdf = new AnsiUp();
    ansiUpPdf.use_classes = false;
    var doc = await ExportPdfUtils.buildTerminalExportPdf({
      jsPDF: jsPDF,
      appName: exportModel.appName,
      metaLine: exportModel.metaLine,
      runMeta: exportModel.runMeta,
      rawLines: exportModel.rawLines,
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
