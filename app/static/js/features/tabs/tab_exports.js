// Tab transcript copy, export, and permalink actions.
function _getExportableRawLines(tab) {
  if (!tab || !Array.isArray(tab.rawLines)) return [];
  return tab.rawLines.filter(line => {
    if (!line || typeof line.text !== 'string') return false;
    const cls = String(line.cls || '');
    if (cls === 'wlc-live' || cls.startsWith('welcome-')) return false;
    const plain = line.text.replace(/\x1b\[[0-9;]*[A-Za-z]/g, '').trim();
    return plain.length > 0;
  });
}

function _getShareRedactionRules() {
  return APP_CONFIG && Array.isArray(APP_CONFIG.share_redaction_rules)
    ? APP_CONFIG.share_redaction_rules
    : [];
}

function _shareRedactionEnabled() {
  return !(APP_CONFIG && APP_CONFIG.share_redaction_enabled === false);
}

function _getRedactedLines(lines) {
  return typeof redactLineEntries === 'function'
    ? redactLineEntries(lines, _getShareRedactionRules())
    : (Array.isArray(lines) ? lines : []);
}

function _refocusAfterTabAction(options = { preventScroll: true }) {
  if (typeof refocusComposerAfterAction === 'function') {
    refocusComposerAfterAction(options);
  }
}

function _stripTabExportAnsi(text) {
  return String(text ?? '').replace(/\x1b\[[0-9;]*[A-Za-z]/g, '');
}

function copyTab(id) {
  const t = getTab(id);
  const lines = _getExportableRawLines(t);
  if (!lines.length) {
    showToast('No output to copy yet');
    _refocusAfterTabAction();
    return;
  }
  const text = lines.map(line => _stripTabExportAnsi(line.text)).join('\n');
  copyTextToClipboard(text)
    .then(() => showToast('Copied to clipboard'))
    .catch(() => showToast('Failed to copy', 'error'))
    .finally(() => _refocusAfterTabAction());
}

// Reads from rawLines rather than DOM innerText so that CSS ::before timestamp
// content and ANSI escape codes don't appear in the saved file.
function saveTab(id) {
  const t = getTab(id);
  const lines = _getExportableRawLines(t);
  if (!lines.length) {
    showToast('No output to export');
    _refocusAfterTabAction();
    return;
  }
  const text = lines.map(line => _stripTabExportAnsi(line.text)).join('\n');
  const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const blob = new Blob([text], { type: 'text/plain' });
  downloadBlobAsAttachment(blob, `${APP_CONFIG.app_name || 'shell'}-${ts}.txt`);
  _refocusAfterTabAction();
}

// Returns the gutter prefix for a raw line, respecting the current tsMode/lnMode
// toggles so exports match what the user sees in the terminal.
function _exportPrefix(line, zeroBasedIndex) {
  const parts = [];
  if (typeof lnMode !== 'undefined' && lnMode === 'on') {
    const absoluteLineNumber = Number(line && line.line_number || 0);
    parts.push(String(absoluteLineNumber > 0 ? absoluteLineNumber : zeroBasedIndex + 1));
  }
  if (typeof tsMode !== 'undefined') {
    if (tsMode === 'clock' && line.tsC) parts.push(line.tsC);
    else if (tsMode === 'elapsed' && line.tsE) parts.push(line.tsE);
  }
  return parts.join(' ');
}

function _normalizeTabTranscriptLine(line) {
  if (window.ExportHtmlUtils && typeof ExportHtmlUtils.normalizeExportTranscriptLine === 'function') {
    return ExportHtmlUtils.normalizeExportTranscriptLine(line);
  }
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

function _normalizeTabTranscriptLines(lines, { stripTruncationNotices = false } = {}) {
  if (window.ExportHtmlUtils && typeof ExportHtmlUtils.normalizeExportTranscriptLines === 'function') {
    return ExportHtmlUtils.normalizeExportTranscriptLines(lines, { stripTruncationNotices });
  }
  return (Array.isArray(lines) ? lines : [])
    .map(_normalizeTabTranscriptLine)
    .filter(line => {
      if (!line) return false;
      if (!stripTruncationNotices) return true;
      return !/^\[(?:preview|tab output) truncated/i.test(String(line.text || ''));
    });
}

function _omitRawOnlyExportLines(lines) {
  return typeof omitRawOnlyLineEntries === 'function'
    ? omitRawOnlyLineEntries(lines)
    : (Array.isArray(lines) ? lines : []);
}

function _buildTabExportModel(tab, { createdText = null, omitRawOnly = false } = {}) {
  const normalizedCreatedText = String(createdText || new Date().toLocaleString());
  const rawLines = omitRawOnly ? _omitRawOnlyExportLines(tab && tab.rawLines) : (tab && tab.rawLines);
  if (window.ExportHtmlUtils && typeof ExportHtmlUtils.buildExportDocumentModel === 'function') {
    return ExportHtmlUtils.buildExportDocumentModel({
      appName: APP_CONFIG.app_name || 'darklab_shell',
      title: String(tab && tab.label || ''),
      label: tab && tab.label,
      createdText: normalizedCreatedText,
      runMeta: {
        exitCode: tab ? tab.exitCode : null,
        duration: null,
        lines: `${_normalizeTabTranscriptLines(rawLines).length} lines`,
        version: APP_CONFIG.version || null,
      },
      rawLines,
    });
  }
  const normalizedRawLines = _normalizeTabTranscriptLines(rawLines);
  const appName = APP_CONFIG.app_name || 'darklab_shell';
  return {
    appName,
    title: String(tab && tab.label || ''),
    metaLine: ExportHtmlUtils.buildExportMetaLine({
      label: tab && tab.label,
      createdText: normalizedCreatedText,
    }),
    runMeta: {
      exitCode: tab ? tab.exitCode : null,
      duration: null,
      lines: `${normalizedRawLines.length} lines`,
      version: APP_CONFIG.version || null,
    },
    rawLines: normalizedRawLines,
  };
}

async function exportTabHtml(id) {
  const t = getTab(id);
  if (!t || !t.rawLines.length) {
    showToast('No output to export');
    _refocusAfterTabAction();
    return;
  }
  if (!window.ExportHtmlUtils) {
    showToast('Failed to export html', 'error');
    _refocusAfterTabAction();
    return;
  }
  try {
    const exportModel = _buildTabExportModel(t, { omitRawOnly: true });
    const ansiRenderer = typeof createAnsiUpRenderer === 'function' ? createAnsiUpRenderer() : null;
    const { linesHtml, prefixWidth } = ExportHtmlUtils.buildExportLinesHtml(exportModel.rawLines, {
      getPrefix: (line, i) => _exportPrefix(line, i),
      ansiToHtml: (text) => ansiRenderer ? ansiRenderer.ansi_to_html(text) : escapeHtml(String(text ?? '')),
    });
    const [fontFacesCss, exportCss] = await Promise.all([
      ExportHtmlUtils.fetchVendorFontFacesCss().catch(() => ''),
      ExportHtmlUtils.fetchTerminalExportCss().catch(() => ''),
    ]);
    const html = ExportHtmlUtils.buildTerminalExportHtml({
      appName: exportModel.appName,
      title: exportModel.title,
      metaLine: exportModel.metaLine,
      runMeta: exportModel.runMeta,
      linesHtml,
      prefixWidth,
      fontFacesCss,
      exportCss,
    });
    const blob = new Blob([html], { type: 'text/html' });
    downloadBlobAsAttachment(blob, `${exportModel.appName}-${ExportHtmlUtils.exportTimestamp()}.html`);
  } catch {
    showToast('Failed to export html', 'error');
  } finally {
    _refocusAfterTabAction();
  }
}

async function exportTabPdf(id) {
  const t = getTab(id);
  if (!t || !t.rawLines.length) {
    showToast('No output to export');
    _refocusAfterTabAction();
    return;
  }
  if (!window.jspdf) {
    showToast('PDF library not loaded', 'error');
    _refocusAfterTabAction();
    return;
  }
  try {
    const { jsPDF } = window.jspdf;
    const exportModel = _buildTabExportModel(t, { omitRawOnly: true });
    const ansiRenderer = typeof createAnsiUpRenderer === 'function' ? createAnsiUpRenderer() : null;
    const doc = await ExportPdfUtils.buildTerminalExportPdf({
      jsPDF,
      appName: exportModel.appName,
      metaLine: exportModel.metaLine,
      runMeta: exportModel.runMeta,
      rawLines: exportModel.rawLines,
      getPrefix: (line, i) => _exportPrefix(line, i),
      ansiToHtml: (text) => ansiRenderer ? ansiRenderer.ansi_to_html(text) : escapeHtml(String(text ?? '')),
    });
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    doc.save(`${exportModel.appName}-${ts}.pdf`);
  } catch {
    showToast('Failed to export pdf', 'error');
  } finally {
    _refocusAfterTabAction();
  }
}

function _shareLinesWithoutTruncationNotices(lines) {
  return _normalizeTabTranscriptLines(lines, { stripTruncationNotices: true });
}

function _extractLatestFullRunShareContent(tab, fullRun) {
  const rawLines = Array.isArray(tab.rawLines) ? tab.rawLines : [];
  const runStartIndex = typeof tab.currentRunStartIndex === 'number' && tab.currentRunStartIndex >= 0
    ? tab.currentRunStartIndex
    : rawLines.length;
  const exitIndex = (() => {
    for (let i = rawLines.length - 1; i >= 0; i -= 1) {
      const cls = String(rawLines[i] && rawLines[i].cls || '');
      if (cls === 'exit-ok' || cls === 'exit-fail') return i;
    }
    return rawLines.length;
  })();
  const fullOutput = Array.isArray(fullRun && fullRun.output_entries)
    ? fullRun.output_entries
    : _shareLinesWithoutTruncationNotices(fullRun && fullRun.output);

  return [
    ..._shareLinesWithoutTruncationNotices(rawLines.slice(0, runStartIndex)),
    ..._shareLinesWithoutTruncationNotices(fullOutput),
    ..._shareLinesWithoutTruncationNotices(rawLines.slice(exitIndex)),
  ];
}

function _shareSnapshotLabel(tab) {
  if (!tab) return 'snapshot';
  const customLabel = String(tab.label || '').trim();
  const latestCommand = String(tab.command || '').trim();
  if (tab.renamed && customLabel) return customLabel;
  return latestCommand || customLabel || 'snapshot';
}

async function permalinkTab(id) {
  const t = getTab(id);
  if (!t || !t.rawLines.length) {
    showToast('No output to share yet');
    return;
  }
  const redactionMode = typeof confirmPermalinkRedactionChoice === 'function'
    ? await confirmPermalinkRedactionChoice()
    : (_shareRedactionEnabled() ? 'redacted' : 'raw');
  if (redactionMode !== 'raw' && redactionMode !== 'redacted') {
    refocusComposerAfterAction();
    return;
  }
  let shareContent = _shareLinesWithoutTruncationNotices(t.rawLines);
  if (t.fullOutputAvailable && !t.fullOutputLoaded && t.historyRunId) {
    try {
      const res = await apiFetch(`/history/${t.historyRunId}?json`);
      const fullRun = await res.json();
      shareContent = _extractLatestFullRunShareContent(t, fullRun);
    } catch {
      shareContent = _shareLinesWithoutTruncationNotices(t.rawLines);
    }
  }
  const applyRedaction = redactionMode === 'redacted';
  if (applyRedaction) shareContent = _getRedactedLines(shareContent);
  apiFetch('/share', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      label: _shareSnapshotLabel(t),
      content: shareContent,
      apply_redaction: applyRedaction,
      run_id: String(t.historyRunId || ''),
    })
  }).then(r => r.json()).then(data => {
    const url = `${location.origin}${data.url}`;
    shareUrl(url).catch(() => showToast('Failed to copy link', 'error'));
  }).catch(() => showToast('Failed to create permalink', 'error'))
    .finally(() => {
      refocusComposerAfterAction();
    });
}
