// ── Session workspace UI ──
// App-mediated file helper only. This does not expose shell navigation,
// redirection, or arbitrary host paths.

let _workspaceFiles = [];
let _workspaceDirs = [];
let _workspaceLimits = {};
let _workspaceLoaded = false;
let _workspaceCurrentDir = '';
let _workspaceViewedPath = '';
let _workspaceViewerPayloadCache = null;
let _workspaceViewerSearchController = null;
let _workspaceViewerRefreshTimer = null;
let _workspaceViewerAutoRefreshSeconds = 0;
let _workspaceViewerRefreshSpinTimer = null;
let _workspaceViewerRefreshInFlight = false;
let _workspaceViewerAutoRefreshEnabled = false;
let _workspaceViewedSize = null;
let _workspaceDragPath = '';
let _workspaceDragKind = '';
const WorkspaceCore = window.DarklabWorkspaceCore;

const WORKSPACE_PREVIEW_LINE_LIMIT = 10000;
const WORKSPACE_PREVIEW_TABLE_LIMIT = 250;
const WORKSPACE_VIEWER_AUTO_REFRESH_MS = 5000;
const WORKSPACE_VIEWER_AUTO_REFRESH_MAX_BYTES = 1024 * 1024;
const WORKSPACE_VIEWER_BOTTOM_THRESHOLD = 24;
const WORKSPACE_VIEWER_REFRESH_SPINNER_MS = 650;
const WORKSPACE_VIEWER_SEARCH_DELAY_MS = 250;
const WORKSPACE_VIEWER_LARGE_SEARCH_DELAY_MS = 600;
const WORKSPACE_VIEWER_LARGE_SEARCH_LINE_THRESHOLD = 2000;
const WORKSPACE_VIEWER_LARGE_SEARCH_CHAR_THRESHOLD = 500000;
const WORKSPACE_VIEWER_LARGE_SEARCH_SIZE_THRESHOLD = 1024 * 1024;
const WORKSPACE_VIEWER_LARGE_SEARCH_MIN_CHARS = 3;

function isWorkspaceEnabled() {
  return !!(typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.workspace_enabled === true);
}

function _formatWorkspaceBytes(bytes) {
  return WorkspaceCore.formatBytes(bytes);
}

function _workspaceErrorMessage(err, fallback = 'Files request failed') {
  if (err && typeof err.message === 'string' && err.message.trim()) return err.message.trim();
  return fallback;
}

async function _workspaceJson(resp) {
  let data = {};
  try {
    data = await resp.json();
  } catch (_) {
    data = {};
  }
  if (!resp.ok) {
    throw new Error(data && data.error ? data.error : `Files request failed (${resp.status})`);
  }
  return data;
}

function setWorkspaceMessage(message = '', tone = 'muted') {
  if (!workspaceMessage) return;
  workspaceMessage.textContent = message;
  workspaceMessage.classList.toggle('u-hidden', !message);
  workspaceMessage.classList.toggle('workspace-message-error', tone === 'error');
}

function _showWorkspaceToast(message, tone = 'error') {
  const text = String(message || '').trim();
  if (!text) return;
  if (typeof showToast === 'function') showToast(text, tone);
  else setWorkspaceMessage(text, tone);
}

function _workspaceViewerIsOpen() {
  return !!(
    workspaceViewer &&
    !workspaceViewer.classList.contains('u-hidden') &&
    (typeof workspaceViewerOverlay === 'undefined' || !workspaceViewerOverlay || !workspaceViewerOverlay.classList.contains('u-hidden'))
  );
}

function _workspaceViewerFileSize(path = '') {
  const target = String(path || '').split('/').filter(Boolean).join('/');
  const file = _workspaceFiles.find(item => String(item?.path || '').split('/').filter(Boolean).join('/') === target);
  const size = Number(file?.size);
  return Number.isFinite(size) ? size : null;
}

function _workspaceFileReadBlockedReason(path = '') {
  const maxFileBytes = Number(_workspaceLimits?.max_file_bytes);
  if (!(maxFileBytes > 0)) return '';
  const fileSize = _workspaceViewerFileSize(path);
  if (!(Number.isFinite(fileSize) && fileSize > maxFileBytes)) return '';
  return 'file exceeds session max file size';
}

function _workspaceAutoRefreshDisabledReason() {
  if (Number.isFinite(_workspaceViewedSize) && _workspaceViewedSize > WORKSPACE_VIEWER_AUTO_REFRESH_MAX_BYTES) {
    return 'Auto-refresh is disabled for files larger than 1 MB to avoid reformatting large previews while browsing.';
  }
  return '';
}

function _workspaceViewerShouldFollow() {
  if (!workspaceViewerText) return true;
  const maxScrollTop = Math.max(0, workspaceViewerText.scrollHeight - workspaceViewerText.clientHeight);
  if (maxScrollTop <= WORKSPACE_VIEWER_BOTTOM_THRESHOLD) return true;
  return workspaceViewerText.scrollTop >= maxScrollTop - WORKSPACE_VIEWER_BOTTOM_THRESHOLD;
}

function _workspaceViewerRestoreScroll({ follow = true, scrollTop = 0 } = {}) {
  if (!workspaceViewerText) return;
  if (follow) {
    workspaceViewerText.scrollTop = Math.max(0, workspaceViewerText.scrollHeight - workspaceViewerText.clientHeight);
    return;
  }
  workspaceViewerText.scrollTop = Math.max(0, Number(scrollTop) || 0);
}

function _workspaceStopViewerAutoRefresh() {
  if (_workspaceViewerRefreshTimer) {
    clearInterval(_workspaceViewerRefreshTimer);
    _workspaceViewerRefreshTimer = null;
  }
  _workspaceViewerAutoRefreshSeconds = 0;
}

function _workspaceSyncViewerAutoRefreshToggle() {
  if (typeof workspaceViewerAutoRefreshToggle === 'undefined' || !workspaceViewerAutoRefreshToggle) return;
  const disabledReason = _workspaceAutoRefreshDisabledReason();
  if (disabledReason && _workspaceViewerAutoRefreshEnabled) {
    _workspaceViewerAutoRefreshEnabled = false;
    _workspaceStopViewerAutoRefresh();
  }
  workspaceViewerAutoRefreshToggle.setAttribute('aria-disabled', disabledReason ? 'true' : 'false');
  workspaceViewerAutoRefreshToggle.setAttribute('aria-pressed', _workspaceViewerAutoRefreshEnabled ? 'true' : 'false');
  workspaceViewerAutoRefreshToggle.title = disabledReason || (_workspaceViewerAutoRefreshEnabled
    ? 'Disable viewer auto refresh'
    : 'Enable viewer auto refresh');
  const label = typeof workspaceViewerAutoRefreshLabel !== 'undefined' && workspaceViewerAutoRefreshLabel
    ? workspaceViewerAutoRefreshLabel
    : workspaceViewerAutoRefreshToggle.querySelector('span:last-child');
  if (label) {
    label.textContent = _workspaceViewerAutoRefreshEnabled
      ? `Auto - ${Math.max(1, _workspaceViewerAutoRefreshSeconds || Math.ceil(WORKSPACE_VIEWER_AUTO_REFRESH_MS / 1000))}s`
      : 'Auto - off';
  }
}

function _workspaceStartViewerAutoRefresh() {
  _workspaceStopViewerAutoRefresh();
  _workspaceViewerAutoRefreshSeconds = Math.ceil(WORKSPACE_VIEWER_AUTO_REFRESH_MS / 1000);
  _workspaceSyncViewerAutoRefreshToggle();
  if (!_workspaceViewerAutoRefreshEnabled || !_workspaceViewedPath || !_workspaceViewerIsOpen()) return;
  _workspaceViewerRefreshTimer = setInterval(() => {
    if (!_workspaceViewerAutoRefreshEnabled || !_workspaceViewerIsOpen()) {
      _workspaceStopViewerAutoRefresh();
      _workspaceSyncViewerAutoRefreshToggle();
      return;
    }
    _workspaceViewerAutoRefreshSeconds -= 1;
    _workspaceSyncViewerAutoRefreshToggle();
    if (_workspaceViewerAutoRefreshSeconds > 0 || _workspaceViewerRefreshInFlight) return;
    refreshWorkspaceViewedFile({ auto: true })
      .catch(() => {})
      .finally(() => {
        if (!_workspaceViewerAutoRefreshEnabled || !_workspaceViewerIsOpen()) return;
        _workspaceViewerAutoRefreshSeconds = Math.ceil(WORKSPACE_VIEWER_AUTO_REFRESH_MS / 1000);
        _workspaceSyncViewerAutoRefreshToggle();
      });
  }, 1000);
}

function _workspaceFlashViewerRefreshSpinner(target = null) {
  const btn = target || (typeof workspaceViewerRefreshBtn !== 'undefined' ? workspaceViewerRefreshBtn : null);
  if (!btn) return;
  btn.classList.add('is-refreshing');
  if (_workspaceViewerRefreshSpinTimer) clearTimeout(_workspaceViewerRefreshSpinTimer);
  _workspaceViewerRefreshSpinTimer = setTimeout(() => {
    if (typeof workspaceViewerRefreshBtn !== 'undefined' && workspaceViewerRefreshBtn) {
      workspaceViewerRefreshBtn.classList.remove('is-refreshing');
    }
    if (typeof workspaceViewerAutoRefreshToggle !== 'undefined' && workspaceViewerAutoRefreshToggle) {
      workspaceViewerAutoRefreshToggle.classList.remove('is-refreshing');
    }
    _workspaceViewerRefreshSpinTimer = null;
  }, WORKSPACE_VIEWER_REFRESH_SPINNER_MS);
}

function _workspaceSetViewerRefreshBusy(isBusy = false) {
  if (typeof workspaceViewerRefreshBtn === 'undefined' || !workspaceViewerRefreshBtn) return;
  workspaceViewerRefreshBtn.disabled = !!isBusy;
  workspaceViewerRefreshBtn.setAttribute('aria-label', isBusy ? 'Refreshing viewed file' : 'Refresh viewed file');
  workspaceViewerRefreshBtn.title = isBusy ? 'Refreshing viewed file' : 'Refresh viewed file';
}

function hideWorkspaceEditor() {
  if (workspaceEditor) workspaceEditor.classList.add('u-hidden');
  if (workspacePathInput) {
    workspacePathInput.readOnly = false;
    workspacePathInput.classList.remove('workspace-path-readonly');
  }
  if (typeof workspaceEditorOverlay !== 'undefined' && workspaceEditorOverlay) {
    workspaceEditorOverlay.classList.add('u-hidden');
    workspaceEditorOverlay.classList.remove('open');
  }
}

function hideWorkspaceViewer() {
  _workspaceStopViewerAutoRefresh();
  if (workspaceViewer) workspaceViewer.classList.add('u-hidden');
  if (typeof workspaceViewerOverlay !== 'undefined' && workspaceViewerOverlay) {
    workspaceViewerOverlay.classList.add('u-hidden');
    workspaceViewerOverlay.classList.remove('open');
  }
  if (_workspaceViewerRefreshSpinTimer) {
    clearTimeout(_workspaceViewerRefreshSpinTimer);
    _workspaceViewerRefreshSpinTimer = null;
  }
  if (typeof workspaceViewerRefreshBtn !== 'undefined' && workspaceViewerRefreshBtn) {
    workspaceViewerRefreshBtn.classList.remove('is-refreshing');
    _workspaceSetViewerRefreshBusy(false);
  }
  if (typeof workspaceViewerAutoRefreshToggle !== 'undefined' && workspaceViewerAutoRefreshToggle) {
    workspaceViewerAutoRefreshToggle.classList.remove('is-refreshing');
  }
  if (_workspaceViewerSearchController) _workspaceViewerSearchController.clear();
  _workspaceViewerSearchController = null;
  if (typeof workspaceViewerControls !== 'undefined' && workspaceViewerControls) {
    workspaceViewerControls.replaceChildren();
  }
  _workspaceViewedPath = '';
  _workspaceViewedSize = null;
  _workspaceViewerPayloadCache = null;
}

function showWorkspaceViewerLoading(path = '', message = 'Loading preview...') {
  hideWorkspaceEditor();
  _workspaceStopViewerAutoRefresh();
  _workspaceViewedPath = String(path || '').trim();
  _workspaceViewedSize = _workspaceViewerFileSize(path);
  _workspaceViewerPayloadCache = null;
  if (_workspaceViewerSearchController) _workspaceViewerSearchController.clear();
  _workspaceViewerSearchController = null;
  if (workspaceViewer) {
    workspaceViewer.querySelector('.workspace-viewer-mode-controls')?.remove();
    workspaceViewer.dataset.format = 'loading';
    workspaceViewer.dataset.viewMode = 'preview';
    workspaceViewer.classList.remove('u-hidden');
    workspaceViewer.scrollTop = 0;
  }
  if (workspaceViewerTitle) workspaceViewerTitle.textContent = path;
  if (typeof workspaceViewerControls !== 'undefined' && workspaceViewerControls) {
    workspaceViewerControls.replaceChildren();
  }
  _workspaceSyncViewerAutoRefreshToggle();
  if (workspaceViewerText) {
    workspaceViewerText.className = 'workspace-viewer-text nice-scroll';
    workspaceViewerText.replaceChildren();
    const notice = document.createElement('div');
    notice.className = 'workspace-preview-notice workspace-preview-loading';
    notice.textContent = message;
    workspaceViewerText.appendChild(notice);
    workspaceViewerText.scrollTop = 0;
  }
  if (typeof workspaceViewerOverlay !== 'undefined' && workspaceViewerOverlay) {
    workspaceViewerOverlay.classList.remove('u-hidden');
    workspaceViewerOverlay.classList.add('open');
  }
}

function _workspaceShowViewerBusy(message = 'Loading preview...') {
  if (_workspaceViewerSearchController) _workspaceViewerSearchController.clear();
  _workspaceViewerSearchController = null;
  if (typeof workspaceViewerControls !== 'undefined' && workspaceViewerControls) {
    workspaceViewerControls.replaceChildren();
  }
  if (!workspaceViewerText) return;
  workspaceViewerText.className = 'workspace-viewer-text nice-scroll';
  workspaceViewerText.replaceChildren();
  const notice = document.createElement('div');
  notice.className = 'workspace-preview-notice workspace-preview-loading';
  notice.textContent = message;
  workspaceViewerText.appendChild(notice);
  workspaceViewerText.scrollTop = 0;
}

function _workspaceAfterPaint() {
  return new Promise(resolve => {
    if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(() => setTimeout(resolve, 0));
      return;
    }
    setTimeout(resolve, 0);
  });
}

function _workspaceFileExt(path = '') {
  const name = String(path || '').split('/').filter(Boolean).pop() || '';
  const match = name.match(/\.([a-z0-9]+)$/i);
  return match ? match[1].toLowerCase() : '';
}

function _workspaceLooksLikeHttpResponse(text = '') {
  const raw = String(text || '').replace(/^\uFEFF/, '');
  return /^HTTP\/\d(?:\.\d)?\s+\d{3}/i.test(raw.trimStart());
}

function _workspaceParseDelimitedLine(line = '', delimiter = ',') {
  const cells = [];
  let cell = '';
  let quoted = false;
  const text = String(line || '');
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (char === '"') {
      if (quoted && text[index + 1] === '"') {
        cell += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (char === delimiter && !quoted) {
      cells.push(cell);
      cell = '';
    } else {
      cell += char;
    }
  }
  cells.push(cell);
  return cells;
}

function _workspaceParseDelimited(text = '', delimiter = ',') {
  const rows = String(text || '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .split('\n')
    .filter(line => line.length > 0)
    .slice(0, WORKSPACE_PREVIEW_TABLE_LIMIT + 1)
    .map(line => _workspaceParseDelimitedLine(line, delimiter));
  const width = Math.max(0, ...rows.map(row => row.length));
  if (rows.length < 2 || width < 2) return null;
  return rows.map(row => {
    const next = row.slice();
    while (next.length < width) next.push('');
    return next;
  });
}

function _workspaceFormatXml(text = '') {
  const raw = String(text || '').trim();
  if (!raw || !/^<[\s\S]*>$/.test(raw)) return null;
  if (typeof DOMParser !== 'undefined') {
    try {
      const parsed = new DOMParser().parseFromString(raw, 'application/xml');
      if (parsed.querySelector('parsererror')) return null;
    } catch (_) {
      return null;
    }
  }
  const lines = raw
    .replace(/>\s*</g, '>\n<')
    .split('\n');
  let depth = 0;
  return lines.map(line => {
    const trimmed = line.trim();
    if (/^<\//.test(trimmed)) depth = Math.max(0, depth - 1);
    const formatted = `${'  '.repeat(depth)}${trimmed}`;
    if (/^<[^!?/][^>]*[^/]>\s*$/.test(trimmed) && !/^<([^>\s]+)[^>]*>.*<\/\1>$/.test(trimmed)) {
      depth += 1;
    }
    return formatted;
  }).join('\n');
}

function _workspaceParseHttpResponse(text = '') {
  const normalized = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const [head = '', ...bodyParts] = normalized.split(/\n\n/);
  const lines = head.split('\n').filter(Boolean);
  if (!lines.length || !/^HTTP\/\d(?:\.\d)?\s+\d{3}/i.test(lines[0])) return null;
  return {
    status: lines[0],
    headers: lines.slice(1).map(line => {
      const index = line.indexOf(':');
      return index >= 0
        ? { name: line.slice(0, index).trim(), value: line.slice(index + 1).trim() }
        : { name: line.trim(), value: '' };
    }),
    body: bodyParts.join('\n\n'),
  };
}

function _workspaceFormatJsonLines(text = '') {
  const rawLines = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
  const nonEmptyLines = rawLines.map(line => line.trim()).filter(Boolean);
  const formatted = [];
  for (const line of nonEmptyLines) {
    try {
      formatted.push(JSON.stringify(JSON.parse(line), null, 2));
    } catch (_) {
      return null;
    }
  }
  return nonEmptyLines.length ? formatted.join('\n') : null;
}

function _workspaceLooksLikeJsonLines(text = '') {
  const nonEmptyLines = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n')
    .map(line => line.trim())
    .filter(Boolean);
  if (nonEmptyLines.length < 2) return false;
  return nonEmptyLines.every(line => /^[{[]/.test(line));
}

function _workspaceViewerPayload(path = '', text = '') {
  const rawText = String(text || '');
  const trimmed = rawText.trim();
  const ext = _workspaceFileExt(path);
  const http = _workspaceLooksLikeHttpResponse(rawText) ? _workspaceParseHttpResponse(rawText) : null;
  if (http) return { text: rawText, format: 'http', http };
  if (ext === 'jsonl' || ext === 'ndjson' || _workspaceLooksLikeJsonLines(rawText)) {
    const jsonl = _workspaceFormatJsonLines(rawText);
    if (jsonl) return { text: jsonl, rawText, format: 'jsonl' };
    if (ext === 'jsonl' || ext === 'ndjson') {
      return { text: rawText, format: 'text', notice: 'Malformed JSONL; showing raw text.' };
    }
  }
  const looksJson = ext === 'json' || /^[{[]/.test(trimmed);
  if (looksJson) {
    try {
      return {
        text: JSON.stringify(JSON.parse(trimmed), null, 2),
        rawText,
        format: 'json',
      };
    } catch (_) {
      if (ext === 'json') return { text: rawText, format: 'text', notice: 'Malformed JSON; showing raw text.' };
    }
  }
  if (ext === 'csv' || ext === 'tsv') {
    const table = _workspaceParseDelimited(rawText, ext === 'tsv' ? '\t' : ',');
    if (table) return { text: rawText, format: ext, table };
  }
  if (ext === 'xml' || /^<\?xml/.test(trimmed)) {
    const xml = _workspaceFormatXml(rawText);
    if (xml) return { text: xml, rawText, format: 'xml' };
    if (ext === 'xml') return { text: rawText, format: 'text', notice: 'Malformed XML; showing raw text.' };
  }
  return { text: rawText, format: 'text' };
}

function _workspaceViewerRawText(payload) {
  return String(payload?.rawText ?? payload?.text ?? '');
}

function _workspaceUsesLargeSearchMode({ lineCount = 0, charCount = 0, size = null } = {}) {
  const numericSize = size == null ? NaN : Number(size);
  return (
    Number(lineCount) >= WORKSPACE_VIEWER_LARGE_SEARCH_LINE_THRESHOLD ||
    Number(charCount) >= WORKSPACE_VIEWER_LARGE_SEARCH_CHAR_THRESHOLD ||
    (Number.isFinite(numericSize) && numericSize >= WORKSPACE_VIEWER_LARGE_SEARCH_SIZE_THRESHOLD)
  );
}

function _workspaceRenderViewerSearchControls(wrap, { lineCount = 0, charCount = 0 } = {}) {
  if (typeof workspaceViewerControls !== 'undefined' && workspaceViewerControls) {
    workspaceViewerControls.replaceChildren();
  }
  const controls = document.createElement('div');
  controls.className = 'workspace-viewer-search search-bar';
  const search = document.createElement('input');
  search.type = 'text';
  search.className = 'form-control form-control-compact form-control-quiet';
  search.placeholder = 'Search file...';
  search.setAttribute('aria-label', 'Search file preview');
  if (typeof applyMobileTextInputDefaults === 'function') applyMobileTextInputDefaults(search);

  const toggles = document.createElement('div');
  toggles.className = 'search-toggles';
  const caseBtn = document.createElement('button');
  caseBtn.type = 'button';
  caseBtn.className = 'toggle-btn';
  caseBtn.title = 'Case sensitive (Aa)';
  caseBtn.setAttribute('aria-label', 'Case sensitive');
  caseBtn.setAttribute('aria-pressed', 'false');
  caseBtn.textContent = 'Aa';
  const regexBtn = document.createElement('button');
  regexBtn.type = 'button';
  regexBtn.className = 'toggle-btn';
  regexBtn.title = 'Regular expression (.*)';
  regexBtn.setAttribute('aria-label', 'Regular expression');
  regexBtn.setAttribute('aria-pressed', 'false');
  regexBtn.textContent = '.*';
  toggles.append(caseBtn, regexBtn);

  const count = document.createElement('span');
  count.className = 'search-count';
  const nav = document.createElement('div');
  nav.className = 'search-nav';
  const prevBtn = document.createElement('button');
  prevBtn.type = 'button';
  prevBtn.className = 'btn btn-ghost btn-icon-only btn-compact';
  prevBtn.setAttribute('aria-label', 'Previous match');
  prevBtn.title = 'Previous match (Shift+Enter)';
  prevBtn.textContent = '↑';
  const nextBtn = document.createElement('button');
  nextBtn.type = 'button';
  nextBtn.className = 'btn btn-ghost btn-icon-only btn-compact';
  nextBtn.setAttribute('aria-label', 'Next match');
  nextBtn.title = 'Next match (Enter)';
  nextBtn.textContent = '↓';
  nav.append(prevBtn, nextBtn);

  controls.append(search, toggles, count, nav);

  if (typeof createTextSearchController === 'function') {
    const isLargePreview = _workspaceUsesLargeSearchMode({
      lineCount,
      charCount,
      size: _workspaceViewedSize,
    });
    _workspaceViewerSearchController = createTextSearchController({
      root: wrap,
      input: search,
      countEl: count,
      caseBtn,
      regexBtn,
      prevBtn,
      nextBtn,
      lineSelector: '.workspace-line-row',
      searchDelayMs: isLargePreview ? WORKSPACE_VIEWER_LARGE_SEARCH_DELAY_MS : WORKSPACE_VIEWER_SEARCH_DELAY_MS,
      minQueryLength: isLargePreview ? WORKSPACE_VIEWER_LARGE_SEARCH_MIN_CHARS : 0,
      minQueryMessage: `type ${WORKSPACE_VIEWER_LARGE_SEARCH_MIN_CHARS}+ chars`,
      lazyHighlight: isLargePreview,
      lineTextSelector: '.workspace-line-text',
    });
  }
  if (typeof workspaceViewerControls !== 'undefined' && workspaceViewerControls) {
    workspaceViewerControls.appendChild(controls);
  }
  return controls;
}

function _workspaceRenderTextPreview(payload, { raw = false } = {}) {
  const text = raw ? _workspaceViewerRawText(payload) : String(payload?.text || '');
  const lines = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
  const shown = lines.slice(0, WORKSPACE_PREVIEW_LINE_LIMIT);
  const wrap = document.createElement('div');
  wrap.className = 'workspace-line-preview';
  wrap.style.setProperty('--workspace-line-number-width', `${String(Math.max(1, shown.length)).length + 1}ch`);
  _workspaceRenderViewerSearchControls(wrap, { lineCount: shown.length, charCount: text.length });
  if (payload?.notice && !raw) {
    const notice = document.createElement('div');
    notice.className = 'workspace-preview-notice';
    notice.textContent = payload.notice;
    wrap.appendChild(notice);
  }
  shown.forEach((line, index) => {
    const row = document.createElement('div');
    row.className = 'workspace-line-row';
    row.dataset.lineNumber = String(index + 1);
    const number = document.createElement('span');
    number.className = 'workspace-line-number';
    number.textContent = String(index + 1);
    const body = document.createElement('span');
    body.className = 'workspace-line-text';
    body.textContent = line;
    row.append(number, body);
    wrap.appendChild(row);
  });
  if (lines.length > shown.length) {
    const notice = document.createElement('div');
    notice.className = 'workspace-preview-notice';
    notice.textContent = `Showing first ${shown.length} of ${lines.length} lines. Download or edit to inspect the full file.`;
    wrap.appendChild(notice);
  }
  return wrap;
}

function _workspaceRenderTablePreview(payload) {
  const rows = Array.isArray(payload?.table) ? payload.table : [];
  const table = document.createElement('table');
  table.className = 'workspace-preview-table';
  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  (rows[0] || []).forEach(cell => {
    const th = document.createElement('th');
    th.textContent = cell;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  rows.slice(1).forEach(row => {
    const tr = document.createElement('tr');
    row.forEach(cell => {
      const td = document.createElement('td');
      td.textContent = cell;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  const wrap = document.createElement('div');
  wrap.className = 'workspace-table-preview';
  wrap.appendChild(table);
  if (String(payload?.text || '').split(/\r\n|\r|\n/).filter(Boolean).length > WORKSPACE_PREVIEW_TABLE_LIMIT + 1) {
    const notice = document.createElement('div');
    notice.className = 'workspace-preview-notice';
    notice.textContent = `Showing first ${WORKSPACE_PREVIEW_TABLE_LIMIT} rows. Download or edit to inspect the full file.`;
    wrap.appendChild(notice);
  }
  return wrap;
}

function _workspaceRenderHttpPreview(payload) {
  const data = payload?.http || {};
  const wrap = document.createElement('div');
  wrap.className = 'workspace-http-preview';
  const status = document.createElement('div');
  status.className = 'workspace-http-status';
  status.textContent = data.status || 'HTTP response';
  wrap.appendChild(status);
  const headers = document.createElement('dl');
  headers.className = 'workspace-http-headers';
  (Array.isArray(data.headers) ? data.headers : []).forEach(header => {
    const dt = document.createElement('dt');
    dt.textContent = header.name;
    const dd = document.createElement('dd');
    dd.textContent = header.value;
    headers.append(dt, dd);
  });
  wrap.appendChild(headers);
  if (data.body) {
    const bodyLabel = document.createElement('div');
    bodyLabel.className = 'workspace-preview-subtitle';
    bodyLabel.textContent = 'Body';
    wrap.appendChild(bodyLabel);
    wrap.appendChild(_workspaceRenderTextPreview({ text: data.body }));
  }
  return wrap;
}

function _workspaceRenderViewerPayload(payload, { raw = false } = {}) {
  if (!workspaceViewerText) return;
  if (_workspaceViewerSearchController) _workspaceViewerSearchController.clear();
  _workspaceViewerSearchController = null;
  if (typeof workspaceViewerControls !== 'undefined' && workspaceViewerControls) {
    workspaceViewerControls.replaceChildren();
  }
  workspaceViewerText.replaceChildren();
  const format = raw ? 'raw' : (payload?.format || 'text');
  workspaceViewerText.className = 'workspace-viewer-text nice-scroll';
  workspaceViewerText.classList.toggle('workspace-viewer-json', format === 'json' || format === 'jsonl' || format === 'xml');
  workspaceViewerText.classList.toggle('workspace-viewer-table-wrap', !raw && (format === 'csv' || format === 'tsv'));
  if (!raw && (format === 'csv' || format === 'tsv') && payload?.table) {
    workspaceViewerText.appendChild(_workspaceRenderTablePreview(payload));
  } else if (!raw && format === 'http' && payload?.http) {
    workspaceViewerText.appendChild(_workspaceRenderHttpPreview(payload));
  } else {
    workspaceViewerText.appendChild(_workspaceRenderTextPreview(payload, { raw }));
  }
  workspaceViewerText.scrollTop = 0;
  if (workspaceViewer) {
    workspaceViewer.dataset.viewMode = raw ? 'raw' : 'preview';
    workspaceViewer.querySelectorAll('[data-workspace-preview-mode]').forEach((btn) => {
      const active = btn.dataset.workspacePreviewMode === workspaceViewer.dataset.viewMode;
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }
}

function _workspaceRenderViewerModeControls(payload) {
  if (!workspaceViewer || !payload) return;
  workspaceViewer.querySelector('.workspace-viewer-mode-controls')?.remove();
  if (payload.format === 'text') return;
  const controls = document.createElement('div');
  controls.className = 'workspace-viewer-mode-controls';
  const label = document.createElement('span');
  label.className = 'workspace-preview-kind';
  label.textContent = `${payload.format || 'plain'} preview`;
  const preview = document.createElement('button');
  preview.type = 'button';
  preview.className = 'toggle-btn';
  preview.dataset.workspacePreviewMode = 'preview';
  preview.setAttribute('aria-pressed', 'true');
  preview.textContent = 'Preview';
  const raw = document.createElement('button');
  raw.type = 'button';
  raw.className = 'toggle-btn';
  raw.dataset.workspacePreviewMode = 'raw';
  raw.setAttribute('aria-pressed', 'false');
  raw.textContent = 'Raw';
  controls.append(label, preview, raw);
  const header = workspaceViewer.querySelector('.workspace-viewer-header');
  if (header && header.parentNode) header.parentNode.insertBefore(controls, header.nextSibling);
}

async function switchWorkspaceViewerMode(raw = false) {
  if (!_workspaceViewerPayloadCache) return;
  _workspaceShowViewerBusy(raw ? 'Loading raw view...' : 'Loading preview...');
  await _workspaceAfterPaint();
  _workspaceRenderViewerPayload(_workspaceViewerPayloadCache, { raw });
}

function showWorkspaceEditor(path = '', text = '', { readOnlyPath = false } = {}) {
  if (!workspaceEditor) return;
  hideWorkspaceViewer();
  workspaceEditor.classList.remove('u-hidden');
  if (typeof workspaceEditorOverlay !== 'undefined' && workspaceEditorOverlay) {
    workspaceEditorOverlay.classList.remove('u-hidden');
    workspaceEditorOverlay.classList.add('open');
  }
  if (typeof workspaceEditorTitle !== 'undefined' && workspaceEditorTitle) {
    workspaceEditorTitle.textContent = path ? `Editing ${path}` : 'New file';
  }
  if (workspacePathInput) {
    workspacePathInput.value = path;
    workspacePathInput.readOnly = !!readOnlyPath;
    workspacePathInput.classList.toggle('workspace-path-readonly', !!readOnlyPath);
  }
  if (workspaceTextInput) workspaceTextInput.value = text;
  setTimeout(() => {
    if (workspacePathInput && !path) workspacePathInput.focus();
    else if (workspaceTextInput) workspaceTextInput.focus();
  }, 0);
}

function showWorkspaceViewer(path = '', text = '', { size = null } = {}) {
  hideWorkspaceEditor();
  _workspaceViewedPath = String(path || '').trim();
  const numericSize = size == null ? NaN : Number(size);
  _workspaceViewedSize = Number.isFinite(numericSize) ? numericSize : _workspaceViewerFileSize(path);
  const payload = _workspaceViewerPayload(path, text);
  _workspaceViewerPayloadCache = payload;
  if (workspaceViewerTitle) workspaceViewerTitle.textContent = path;
  _workspaceRenderViewerModeControls(payload);
  _workspaceRenderViewerPayload(payload, { raw: false });
  if (workspaceViewer) {
    workspaceViewer.dataset.format = payload.format;
    workspaceViewer.classList.remove('u-hidden');
    workspaceViewer.scrollTop = 0;
    if (typeof workspaceViewerOverlay !== 'undefined' && workspaceViewerOverlay) {
      workspaceViewerOverlay.classList.remove('u-hidden');
      workspaceViewerOverlay.classList.add('open');
    }
  }
  _workspaceSyncViewerAutoRefreshToggle();
  _workspaceStartViewerAutoRefresh();
}

async function refreshWorkspaceViewedFile({ auto = false, suppressErrorToast = false } = {}) {
  if (!_workspaceViewedPath || _workspaceViewerRefreshInFlight) return null;
  const viewedPath = _workspaceViewedPath;
  const scrollState = {
    follow: _workspaceViewerShouldFollow(),
    scrollTop: workspaceViewerText ? workspaceViewerText.scrollTop : 0,
  };
  const raw = workspaceViewer?.dataset?.viewMode === 'raw';
  _workspaceViewerRefreshInFlight = true;
  if (!auto) _workspaceSetViewerRefreshBusy(true);
  try {
    if (!auto) {
      _workspaceShowViewerBusy('Refreshing preview...');
      await _workspaceAfterPaint();
    }
    const data = await readWorkspaceFile(viewedPath);
    const nextPath = data.path || viewedPath;
    const numericSize = data.size == null ? NaN : Number(data.size);
    _workspaceViewedSize = Number.isFinite(numericSize) ? numericSize : _workspaceViewerFileSize(nextPath);
    const payload = _workspaceViewerPayload(nextPath, data.text || '');
    _workspaceViewedPath = String(nextPath || '').trim();
    _workspaceViewerPayloadCache = payload;
    if (workspaceViewerTitle) workspaceViewerTitle.textContent = nextPath;
    _workspaceRenderViewerModeControls(payload);
    _workspaceRenderViewerPayload(payload, { raw });
    if (workspaceViewer) workspaceViewer.dataset.format = payload.format;
    _workspaceSyncViewerAutoRefreshToggle();
    _workspaceViewerRestoreScroll(scrollState);
    _workspaceFlashViewerRefreshSpinner(auto && typeof workspaceViewerAutoRefreshToggle !== 'undefined'
      ? workspaceViewerAutoRefreshToggle
      : null);
    return data;
  } catch (err) {
    if (!auto && !suppressErrorToast) _showWorkspaceToast(_workspaceErrorMessage(err, 'Unable to refresh viewed file'), 'error');
    throw err;
  } finally {
    _workspaceViewerRefreshInFlight = false;
    if (!auto) _workspaceSetViewerRefreshBusy(false);
  }
}

function _normalizeWorkspaceDir(path = '') {
  return WorkspaceCore.normalizeDir(path);
}

function normalizeWorkspaceCommandPath(path = '', cwd = '') {
  return WorkspaceCore.normalizeCommandPath(path, cwd);
}

function workspaceDisplayPath(path = '') {
  return WorkspaceCore.displayPath(path);
}

function _workspaceParentDir(path = '') {
  return WorkspaceCore.parentDir(path);
}

function _workspaceFileBasename(path = '') {
  return WorkspaceCore.basename(path);
}

function _activateWorkspaceFolderRow(path, event = null) {
  if (event && event.target && event.target.closest && event.target.closest('[data-workspace-action]')) return;
  handleWorkspaceFileAction('open-folder', path);
}

function _bindWorkspaceFolderRow(row, path, label) {
  row.className = 'workspace-file-row workspace-folder-row panel-row panel-row-clickable';
  row.dataset.kind = 'folder';
  row.dataset.path = path;
  row.dataset.workspaceDropTarget = 'folder';
  row.tabIndex = 0;
  row.setAttribute('role', 'button');
  row.setAttribute('aria-label', label);
  if (typeof bindPressable === 'function') {
    bindPressable(row, {
      onActivate: event => _activateWorkspaceFolderRow(path, event),
      refocusComposer: false,
      clearPressStyle: true,
    });
  } else {
    row.addEventListener('click', event => _activateWorkspaceFolderRow(path, event));
    row.addEventListener('keydown', event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      _activateWorkspaceFolderRow(path, event);
    });
  }
}

function _workspacePathInCurrentDir(path = '') {
  const raw = String(path || '').trim();
  const current = _normalizeWorkspaceDir(_workspaceCurrentDir);
  if (!raw) return current ? `${current}/` : '';
  if (raw.includes('/')) return raw;
  return current ? `${current}/${raw}` : raw;
}

function _workspaceDestinationPathInCurrentDir(path = '') {
  const raw = String(path || '').trim();
  if (!raw || raw === '/') return '';
  return _workspacePathInCurrentDir(raw);
}

function _workspaceDirectEntries(dir = '') {
  const current = _normalizeWorkspaceDir(dir);
  const folders = new Map();
  const files = [];
  for (const directory of _workspaceDirs) {
    const path = String(directory.path || '').split('/').filter(Boolean).join('/');
    if (!path) continue;
    const prefix = current ? `${current}/` : '';
    if (current && path !== current && !path.startsWith(prefix)) continue;
    if (path === current) continue;
    const relative = current ? path.slice(prefix.length) : path;
    const parts = relative.split('/').filter(Boolean);
    if (parts.length >= 1) {
      const folderName = parts[0];
      const folderPath = current ? `${current}/${folderName}` : folderName;
      folders.set(folderPath, { name: folderName, path: folderPath });
    }
  }
  for (const file of _workspaceFiles) {
    const path = String(file.path || '').split('/').filter(Boolean).join('/');
    if (!path) continue;
    const prefix = current ? `${current}/` : '';
    if (current && path !== current && !path.startsWith(prefix)) continue;
    const relative = current ? path.slice(prefix.length) : path;
    if (!relative || relative === path && current && !path.startsWith(prefix)) continue;
    const parts = relative.split('/').filter(Boolean);
    if (parts.length > 1) {
      const folderName = parts[0];
      const folderPath = current ? `${current}/${folderName}` : folderName;
      folders.set(folderPath, { name: folderName, path: folderPath });
    } else if (parts.length === 1) {
      files.push({ ...file, path, name: parts[0] });
    }
  }
  return {
    folders: [...folders.values()].sort((a, b) => a.name.localeCompare(b.name)),
    files: files.sort((a, b) => String(a.name || '').localeCompare(String(b.name || ''))),
  };
}

function _workspaceFolderFileCount(path = '') {
  const normalized = _normalizeWorkspaceDir(path);
  if (!normalized) return 0;
  return _workspaceFiles.filter(file => {
    const filePath = String(file.path || '').split('/').filter(Boolean).join('/');
    return filePath.startsWith(`${normalized}/`);
  }).length;
}

function renderWorkspaceBreadcrumbs() {
  if (!workspaceBreadcrumbs) return;
  workspaceBreadcrumbs.textContent = '';
  const root = document.createElement('button');
  root.type = 'button';
  root.className = 'btn btn-secondary btn-compact';
  root.dataset.workspaceDir = '';
  root.textContent = 'Files';
  workspaceBreadcrumbs.appendChild(root);

  const parts = _normalizeWorkspaceDir(_workspaceCurrentDir).split('/').filter(Boolean);
  let acc = '';
  parts.forEach(part => {
    acc = acc ? `${acc}/${part}` : part;
    const separator = document.createElement('span');
    separator.className = 'workspace-breadcrumb-separator';
    separator.textContent = '/';
    const crumb = document.createElement('button');
    crumb.type = 'button';
    crumb.className = 'btn btn-secondary btn-compact';
    crumb.dataset.workspaceDir = acc;
    crumb.textContent = part;
    workspaceBreadcrumbs.appendChild(separator);
    workspaceBreadcrumbs.appendChild(crumb);
  });
}

function renderWorkspaceBrowser() {
  if (!workspaceFileList) return;
  workspaceFileList.textContent = '';
  renderWorkspaceBreadcrumbs();

  const { folders, files } = _workspaceDirectEntries(_workspaceCurrentDir);
  if (_workspaceCurrentDir) {
    const parent = document.createElement('div');
    const parentPath = _workspaceParentDir(_workspaceCurrentDir);
    _bindWorkspaceFolderRow(parent, parentPath, 'Open parent folder');
    parent.appendChild(_workspaceMetaNode('..', 'Parent folder', 'workspace-parent-icon', ''));
    parent.appendChild(_workspaceActionsNode([{ action: 'open-folder', label: 'Up', tone: 'secondary' }]));
    workspaceFileList.appendChild(parent);
  }

  for (const folder of folders) {
    const row = document.createElement('div');
    _bindWorkspaceFolderRow(row, folder.path, `Open folder ${folder.name}`);
    const count = _workspaceFolderFileCount(folder.path);
    row.appendChild(_workspaceMetaNode(
      folder.name,
      count ? `Folder · ${count} ${count === 1 ? 'file' : 'files'}` : 'Empty folder',
      'workspace-folder-icon',
      '>',
    ));
    row.appendChild(_workspaceActionsNode([
      { action: 'open-folder', label: 'Open', tone: 'secondary' },
      { action: 'move-folder', label: 'Move', tone: 'secondary' },
      { action: 'delete-folder', label: 'Delete', tone: 'secondary' },
    ]));
    row.draggable = true;
    workspaceFileList.appendChild(row);
  }

  for (const file of files) {
    const row = document.createElement('div');
    row.className = 'workspace-file-row panel-row';
    row.dataset.kind = 'file';
    row.dataset.path = file.path;
    row.draggable = true;
    row.appendChild(_workspaceMetaNode(
      file.name || _workspaceFileBasename(file.path),
      `${_formatWorkspaceBytes(file.size)}${file.mtime ? ` · ${file.mtime}` : ''}`,
    ));
    row.appendChild(_workspaceActionsNode([
      { action: 'view', label: 'View', tone: 'secondary' },
      { action: 'edit', label: 'Edit', tone: 'secondary' },
      { action: 'move', label: 'Move', tone: 'secondary' },
      { action: 'download', label: 'Download', tone: 'secondary' },
      { action: 'delete', label: 'Delete', tone: 'secondary' },
    ]));
    workspaceFileList.appendChild(row);
  }

  if (!folders.length && !files.length && !_workspaceCurrentDir) {
    const empty = document.createElement('div');
    empty.className = 'workspace-empty panel-row';
    empty.textContent = 'No session files yet. Create a text file or save command output to use with file-enabled commands.';
    workspaceFileList.appendChild(empty);
  } else if (!folders.length && !files.length) {
    const empty = document.createElement('div');
    empty.className = 'workspace-empty panel-row';
    empty.textContent = 'This folder is empty.';
    workspaceFileList.appendChild(empty);
  }
}

function _workspaceMetaNode(nameText, detailsText, iconClass = '', iconText = '') {
  const meta = document.createElement('div');
  meta.className = 'workspace-file-meta';
  if (iconText) {
    const icon = document.createElement('span');
    icon.className = iconClass;
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = iconText;
    meta.appendChild(icon);
  }
  const text = document.createElement('div');
  text.className = 'workspace-file-meta-text';
  const name = document.createElement('div');
  name.className = 'workspace-file-name';
  name.textContent = nameText;
  const details = document.createElement('div');
  details.className = 'workspace-file-details';
  details.textContent = detailsText;
  text.appendChild(name);
  text.appendChild(details);
  meta.appendChild(text);
  return meta;
}

function _workspaceActionsNode(items = []) {
  const actions = document.createElement('div');
  actions.className = 'workspace-file-actions';
  for (const item of items) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `btn btn-${item.tone === 'destructive' ? 'destructive' : 'secondary'} btn-compact`;
    btn.dataset.workspaceAction = item.action;
    btn.textContent = item.label;
    actions.appendChild(btn);
  }
  return actions;
}

function renderWorkspaceFiles(payload = {}) {
  _workspaceLoaded = true;
  _workspaceDirs = Array.isArray(payload.directories) ? payload.directories : [];
  _workspaceFiles = Array.isArray(payload.files) ? payload.files : [];
  _workspaceLimits = payload.limits && typeof payload.limits === 'object' ? payload.limits : {};
  const currentHasEntries = !_workspaceCurrentDir || _workspaceFiles.some(file => {
    const path = String(file.path || '').split('/').filter(Boolean).join('/');
    return path === _workspaceCurrentDir || path.startsWith(`${_workspaceCurrentDir}/`);
  }) || _workspaceDirs.some(directory => {
    const path = String(directory.path || '').split('/').filter(Boolean).join('/');
    return path === _workspaceCurrentDir || path.startsWith(`${_workspaceCurrentDir}/`);
  });
  if (!currentHasEntries) _workspaceCurrentDir = '';
  const usage = payload.usage || {};
  const limits = payload.limits || {};
  const fileCount = Number(usage.file_count) || 0;
  const maxFiles = Number(limits.max_files) || 0;
  const bytesUsed = Number(usage.bytes_used) || 0;
  const quotaBytes = Number(limits.quota_bytes) || 0;

  if (workspaceSummary) {
    workspaceSummary.textContent = `${fileCount}${maxFiles ? ` / ${maxFiles}` : ''} files · ${_formatWorkspaceBytes(bytesUsed)}${quotaBytes ? ` / ${_formatWorkspaceBytes(quotaBytes)}` : ''}`;
  }
  if (!workspaceFileList) return;
  renderWorkspaceBrowser();
}

async function refreshWorkspaceFiles() {
  if (!isWorkspaceEnabled()) throw new Error('Files are disabled on this instance');
  setWorkspaceMessage('');
  if (workspaceSummary) workspaceSummary.textContent = 'Loading…';
  const resp = await apiFetch('/workspace/files');
  const data = await _workspaceJson(resp);
  renderWorkspaceFiles(data);
  return data;
}

async function refreshWorkspaceFilesFromButton() {
  if (!workspaceRefreshBtn) return;
  workspaceRefreshBtn.disabled = true;
  workspaceRefreshBtn.setAttribute('aria-label', 'Refreshing files');
  workspaceRefreshBtn.title = 'Refreshing files';
  try {
    const viewedPath = _workspaceViewedPath;
    await refreshWorkspaceFiles();
    if (viewedPath) {
      try {
        await refreshWorkspaceViewedFile({ suppressErrorToast: true });
      } catch (err) {
        hideWorkspaceViewer();
        _showWorkspaceToast(_workspaceErrorMessage(err, 'Unable to refresh viewed file'), 'error');
      }
    }
  } catch (err) {
    _workspaceLoaded = false;
    _workspaceFiles = [];
    if (workspaceFileList) workspaceFileList.textContent = '';
    if (workspaceSummary) workspaceSummary.textContent = 'Unavailable';
    setWorkspaceMessage(_workspaceErrorMessage(err, 'Unable to refresh files'), 'error');
  } finally {
    workspaceRefreshBtn.disabled = false;
    workspaceRefreshBtn.setAttribute('aria-label', 'Refresh files');
    workspaceRefreshBtn.title = 'Refresh files';
  }
}

async function refreshWorkspaceFileCache() {
  if (!isWorkspaceEnabled()) return _workspaceFiles;
  try {
    const resp = await apiFetch('/workspace/files');
    const data = await _workspaceJson(resp);
    _workspaceLoaded = true;
    _workspaceDirs = Array.isArray(data.directories) ? data.directories : [];
    _workspaceFiles = Array.isArray(data.files) ? data.files : [];
    if (workspaceOverlay && workspaceOverlay.classList.contains('open')) renderWorkspaceFiles(data);
    return _workspaceFiles;
  } catch (_) {
    return _workspaceFiles;
  }
}

function getWorkspaceAutocompleteFileHints() {
  if (!_workspaceLoaded || !Array.isArray(_workspaceFiles) || !_workspaceFiles.length) return [];
  return _workspaceFiles.map(file => {
    const path = String(file.path || '').trim();
    return {
      value: path,
      description: `session file · ${_formatWorkspaceBytes(file.size)}`,
    };
  }).filter(item => item.value);
}

function getWorkspaceAutocompleteDirectoryHints() {
  if (!_workspaceLoaded || !Array.isArray(_workspaceDirs) || !_workspaceDirs.length) return [];
  return _workspaceDirs.map(directory => {
    const path = String(directory.path || '').trim();
    return {
      value: path,
      description: 'session folder',
    };
  }).filter(item => item.value);
}

function getWorkspaceDirectoryEntries(path = '') {
  return _workspaceDirectEntries(path);
}

async function saveWorkspaceFile(path, text) {
  const resp = await apiFetch('/workspace/files', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, text }),
  });
  const data = await _workspaceJson(resp);
  renderWorkspaceFiles(data.workspace || {});
  hideWorkspaceEditor();
  hideWorkspaceViewer();
  setWorkspaceMessage(`Saved ${data.file?.path || path}`);
  return data;
}

async function createWorkspaceDirectory(path) {
  const normalized = _normalizeWorkspaceDir(path);
  const resp = await apiFetch('/workspace/directories', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: normalized }),
  });
  const data = await _workspaceJson(resp);
  _workspaceCurrentDir = data.directory?.path || normalized;
  renderWorkspaceFiles(data.workspace || {});
  hideWorkspaceEditor();
  hideWorkspaceViewer();
  setWorkspaceMessage(`Created folder ${data.directory?.path || normalized}`);
  return data;
}

async function promptWorkspaceFolderName() {
  const current = _normalizeWorkspaceDir(_workspaceCurrentDir);
  const promptDefault = current ? `${current}/` : '';
  if (typeof showConfirm !== 'function') {
    setWorkspaceMessage('Unable to open folder prompt', 'error');
    return null;
  }

  const field = document.createElement('div');
  field.className = 'workspace-folder-form';
  const id = `workspace-folder-input-${Date.now()}`;
  const label = document.createElement('label');
  label.className = 'workspace-label';
  label.setAttribute('for', id);
  label.textContent = 'Folder Name';
  const input = document.createElement('input');
  input.id = id;
  input.className = 'form-input form-control';
  input.type = 'text';
  input.placeholder = current ? `${current}/reports` : 'reports';
  if (typeof applyMobileTextInputDefaults === 'function') {
    applyMobileTextInputDefaults(input);
  } else {
    input.autocomplete = 'off';
    input.autocapitalize = 'none';
    input.autocorrect = 'off';
    input.spellcheck = false;
    input.inputMode = 'text';
  }
  input.value = promptDefault;
  const error = document.createElement('div');
  error.className = 'workspace-folder-error u-hidden';
  field.append(label, input, error);

  const setError = (message = '') => {
    error.textContent = message;
    error.classList.toggle('u-hidden', !message);
  };
  let created = null;
  const createFromInput = async () => {
    setError('');
    const raw = String(input.value || '').trim();
    if (!raw) {
      setError('Enter a folder name.');
      input.focus();
      return false;
    }
    const path = current && !raw.includes('/') ? `${current}/${raw}` : raw;
    try {
      created = await createWorkspaceDirectory(path);
      return true;
    } catch (err) {
      setError(_workspaceErrorMessage(err, 'Unable to create folder'));
      input.focus();
      return false;
    }
  };
  input.addEventListener('keydown', event => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    const createBtn = document.querySelector('#confirm-host [data-confirm-action-id="create"]');
    if (createBtn && typeof createBtn.click === 'function') createBtn.click();
  });

  const choice = await showConfirm({
    body: {
      text: 'Create a session folder?',
      note: current ? `Current folder: ${current}` : 'Create it at the Files root or include a path.',
    },
    content: field,
    defaultFocus: input,
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'create', label: 'Create folder', role: 'primary', onActivate: createFromInput },
    ],
  });
  return choice === 'create' ? created : null;
}

async function promptWorkspaceMove(sourcePath, { kind = 'file' } = {}) {
  const source = String(sourcePath || '').trim();
  if (!source || typeof showConfirm !== 'function') {
    setWorkspaceMessage('Unable to open move prompt', 'error');
    return null;
  }

  const field = document.createElement('div');
  field.className = 'workspace-folder-form';
  const id = `workspace-move-input-${Date.now()}`;
  const label = document.createElement('label');
  label.className = 'workspace-label';
  label.setAttribute('for', id);
  label.textContent = 'Destination';
  const input = document.createElement('input');
  input.id = id;
  input.className = 'form-input form-control';
  input.type = 'text';
  input.placeholder = _workspaceCurrentDir ? `${_workspaceCurrentDir}/` : 'reports';
  input.value = _workspaceCurrentDir ? `${_workspaceCurrentDir}/` : '';
  if (typeof applyMobileTextInputDefaults === 'function') {
    applyMobileTextInputDefaults(input);
  }
  const error = document.createElement('div');
  error.className = 'workspace-folder-error u-hidden';
  field.append(label, input, error);

  const setError = (message = '') => {
    error.textContent = message;
    error.classList.toggle('u-hidden', !message);
  };
  let moved = null;
  const moveFromInput = async () => {
    setError('');
    try {
      const destination = _workspaceDestinationPathInCurrentDir(input.value);
      moved = await moveWorkspacePath(source, destination);
      return true;
    } catch (err) {
      setError(_workspaceErrorMessage(err, 'Unable to move item'));
      input.focus();
      return false;
    }
  };
  input.addEventListener('keydown', event => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    const moveBtn = document.querySelector('#confirm-host [data-confirm-action-id="move"]');
    if (moveBtn && typeof moveBtn.click === 'function') moveBtn.click();
  });

  const labelKind = kind === 'directory' || kind === 'folder' ? 'folder' : 'file';
  const choice = await showConfirm({
    body: {
      text: `Move ${labelKind} ${source}?`,
      note: 'Choose a destination folder, or enter a full destination path to rename while moving.',
    },
    content: field,
    defaultFocus: input,
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'move', label: 'Move', role: 'primary', onActivate: moveFromInput },
    ],
  });
  return choice === 'move' ? moved : null;
}

async function readWorkspaceFile(path) {
  const resp = await apiFetch(`/workspace/files/read?path=${encodeURIComponent(path)}`);
  return _workspaceJson(resp);
}

async function deleteWorkspacePath(path) {
  const resp = await apiFetch(`/workspace/files?path=${encodeURIComponent(path)}`, { method: 'DELETE' });
  const data = await _workspaceJson(resp);
  renderWorkspaceFiles(data.workspace || {});
  hideWorkspaceViewer();
  const deleted = data.deleted || {};
  const kind = deleted.kind === 'directory' ? 'folder' : 'file';
  setWorkspaceMessage(`Deleted ${kind} ${path}`);
  return data;
}

async function moveWorkspacePath(source, destination) {
  const resp = await apiFetch('/workspace/files/move', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source, destination }),
  });
  const data = await _workspaceJson(resp);
  renderWorkspaceFiles(data.workspace || {});
  hideWorkspaceViewer();
  const moved = data.moved || {};
  setWorkspaceMessage(`Moved ${moved.source || source} to ${moved.destination || destination || 'Files'}`);
  return data;
}

async function deleteWorkspaceFile(path) {
  return deleteWorkspacePath(path);
}

async function downloadWorkspaceFile(path) {
  const resp = await apiFetch(`/workspace/files/download?path=${encodeURIComponent(path)}`);
  if (!resp.ok) {
    await _workspaceJson(resp);
    return false;
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = path.split('/').filter(Boolean).pop() || 'workspace-file.txt';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return true;
}

async function openWorkspace() {
  if (!isWorkspaceEnabled()) return;
  _closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  showWorkspaceOverlay();
  _workspaceCurrentDir = '';
  hideWorkspaceEditor();
  hideWorkspaceViewer();
  try {
    await refreshWorkspaceFiles();
  } catch (err) {
    _workspaceLoaded = false;
    _workspaceFiles = [];
    if (workspaceFileList) workspaceFileList.textContent = '';
    if (workspaceSummary) workspaceSummary.textContent = 'Unavailable';
    setWorkspaceMessage(_workspaceErrorMessage(err, 'Unable to load files'), 'error');
  }
  if (typeof markInteractionSurfaceReady === 'function') {
    markInteractionSurfaceReady('workspace', workspaceOverlay, workspaceModal);
  }
}

async function openWorkspaceEditorFromCommand(action = 'add', path = '') {
  if (!isWorkspaceEnabled()) return false;
  if (typeof hideWorkspaceOverlay === 'function') hideWorkspaceOverlay();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  hideWorkspaceViewer();
  const fileName = String(path || '').trim();
  if (String(action || '').toLowerCase() === 'edit' && fileName) {
    const blockedReason = _workspaceFileReadBlockedReason(fileName);
    if (blockedReason) {
      _showWorkspaceToast(blockedReason, 'error');
      return false;
    }
    try {
      const data = await readWorkspaceFile(fileName);
      showWorkspaceEditor(data.path || fileName, data.text || '', { readOnlyPath: true });
    } catch (err) {
      hideWorkspaceEditor();
      _showWorkspaceToast(_workspaceErrorMessage(err, 'Unable to load session file'), 'error');
      return false;
    }
    return true;
  }
  showWorkspaceEditor(fileName, '');
  return true;
}

function closeWorkspace() {
  hideWorkspaceOverlay();
  hideWorkspaceEditor();
  hideWorkspaceViewer();
  refocusComposerAfterAction({ defer: true });
}

async function handleWorkspaceFileAction(action, path) {
  try {
    setWorkspaceMessage('');
    if (action === 'open-folder') {
      _workspaceCurrentDir = _normalizeWorkspaceDir(path);
      hideWorkspaceViewer();
      renderWorkspaceBrowser();
    } else if (action === 'view') {
      const blockedReason = _workspaceFileReadBlockedReason(path);
      if (blockedReason) {
        _showWorkspaceToast(blockedReason, 'error');
        return;
      }
      showWorkspaceViewerLoading(path);
      await _workspaceAfterPaint();
      const data = await readWorkspaceFile(path);
      if (_workspaceViewedPath !== String(path || '').trim()) return;
      showWorkspaceViewer(data.path || path, data.text || '', { size: data.size });
    } else if (action === 'edit') {
      const blockedReason = _workspaceFileReadBlockedReason(path);
      if (blockedReason) {
        _showWorkspaceToast(blockedReason, 'error');
        return;
      }
      showWorkspaceViewerLoading(path, 'Loading file for edit...');
      await _workspaceAfterPaint();
      const data = await readWorkspaceFile(path);
      if (_workspaceViewedPath !== String(path || '').trim()) return;
      showWorkspaceEditor(data.path || path, data.text || '', { readOnlyPath: true });
    } else if (action === 'download') {
      await downloadWorkspaceFile(path);
    } else if (action === 'move') {
      await promptWorkspaceMove(path, { kind: 'file' });
    } else if (action === 'delete') {
      const confirmed = typeof showConfirm === 'function'
        ? await showConfirm({
            body: { text: `Delete ${path}?`, note: 'This only removes the session file.' },
            tone: 'danger',
            actions: [
              { id: 'cancel', label: 'Cancel', role: 'cancel' },
              { id: 'delete', label: 'Delete', role: 'destructive' },
            ],
          })
        : 'delete';
      if (confirmed === 'delete') await deleteWorkspacePath(path);
    } else if (action === 'delete-folder') {
      const count = _workspaceFolderFileCount(path);
      const note = count
        ? `This will also delete ${count} ${count === 1 ? 'file' : 'files'} in this folder.`
        : 'This only removes the empty session folder.';
      const confirmed = typeof showConfirm === 'function'
        ? await showConfirm({
            body: { text: `Delete folder ${path}?`, note },
            tone: 'danger',
            actions: [
              { id: 'cancel', label: 'Cancel', role: 'cancel' },
              { id: 'delete', label: 'Delete', role: 'destructive' },
            ],
          })
        : 'delete';
      if (confirmed === 'delete') await deleteWorkspacePath(path);
    } else if (action === 'move-folder') {
      await promptWorkspaceMove(path, { kind: 'folder' });
    }
  } catch (err) {
    if (action === 'view' || action === 'edit') hideWorkspaceViewer();
    _showWorkspaceToast(_workspaceErrorMessage(err), 'error');
  }
}

function _workspaceDragSourceFromEvent(event) {
  const row = event.target && event.target.closest ? event.target.closest('.workspace-file-row[draggable="true"]') : null;
  return row && workspaceFileList && workspaceFileList.contains(row) ? row : null;
}

function _workspaceDropTargetFromEvent(event) {
  const row = event.target && event.target.closest ? event.target.closest('[data-workspace-drop-target="folder"]') : null;
  return row && workspaceFileList && workspaceFileList.contains(row) ? row : null;
}

function _workspaceCanDropOnFolder(sourcePath, destinationPath) {
  const source = String(sourcePath || '').trim();
  const destination = String(destinationPath || '').trim();
  if (!source) return false;
  if (!destination) return true;
  return source !== destination && !destination.startsWith(`${source}/`);
}

async function _handleWorkspaceDropMove(event) {
  const target = _workspaceDropTargetFromEvent(event);
  if (!target || !_workspaceCanDropOnFolder(_workspaceDragPath, target.dataset.path || '')) return;
  event.preventDefault();
  target.classList.remove('workspace-drop-target');
  const destination = target.dataset.path || '';
  const source = _workspaceDragPath;
  const kind = _workspaceDragKind === 'folder' ? 'folder' : 'file';
  if (!source) return;
  const confirmed = typeof showConfirm === 'function'
    ? await showConfirm({
        body: {
          text: `Move ${kind} ${source}?`,
          note: destination ? `Destination folder: ${destination}` : 'Destination folder: Files',
        },
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'move', label: 'Move', role: 'primary' },
        ],
      })
    : 'move';
  if (confirmed !== 'move') return;
  try {
    await moveWorkspacePath(source, destination);
  } catch (err) {
    _showWorkspaceToast(_workspaceErrorMessage(err, 'Unable to move item'), 'error');
  }
}

workspaceRefreshBtn?.addEventListener('click', () => { refreshWorkspaceFilesFromButton(); });
workspaceViewerRefreshBtn?.addEventListener('click', () => { refreshWorkspaceViewedFile().catch(() => {}); });
workspaceViewerAutoRefreshToggle?.addEventListener('click', () => {
  if (workspaceViewerAutoRefreshToggle.getAttribute('aria-disabled') === 'true') return;
  _workspaceViewerAutoRefreshEnabled = !_workspaceViewerAutoRefreshEnabled;
  if (_workspaceViewerAutoRefreshEnabled) _workspaceStartViewerAutoRefresh();
  else {
    _workspaceStopViewerAutoRefresh();
    workspaceViewerAutoRefreshToggle.classList.remove('is-refreshing');
    _workspaceSyncViewerAutoRefreshToggle();
  }
});
workspaceNewBtn?.addEventListener('click', () => showWorkspaceEditor('', ''));
workspaceNewFolderBtn?.addEventListener('click', () => { promptWorkspaceFolderName(); });
workspaceCancelEditBtn?.addEventListener('click', () => hideWorkspaceEditor());
workspaceCloseViewerBtn?.addEventListener('click', () => hideWorkspaceViewer());
workspaceBreadcrumbs?.addEventListener('click', event => {
  const btn = event.target && event.target.closest ? event.target.closest('[data-workspace-dir]') : null;
  if (!btn) return;
  _workspaceCurrentDir = _normalizeWorkspaceDir(btn.dataset.workspaceDir || '');
  hideWorkspaceViewer();
  renderWorkspaceBrowser();
});
workspaceViewer?.addEventListener('click', event => {
  const refreshBtn = event.target && event.target.closest ? event.target.closest('[data-workspace-viewer-refresh]') : null;
  if (refreshBtn) {
    if (typeof workspaceViewerRefreshBtn !== 'undefined' && refreshBtn === workspaceViewerRefreshBtn) return;
    refreshWorkspaceViewedFile().catch(() => {});
    return;
  }
  const autoRefreshBtn = event.target && event.target.closest ? event.target.closest('[data-workspace-viewer-auto-refresh]') : null;
  if (autoRefreshBtn) {
    if (typeof workspaceViewerAutoRefreshToggle !== 'undefined' && autoRefreshBtn === workspaceViewerAutoRefreshToggle) return;
    if (autoRefreshBtn.getAttribute('aria-disabled') === 'true') return;
    _workspaceViewerAutoRefreshEnabled = !_workspaceViewerAutoRefreshEnabled;
    if (_workspaceViewerAutoRefreshEnabled) _workspaceStartViewerAutoRefresh();
    else {
      _workspaceStopViewerAutoRefresh();
      autoRefreshBtn.classList.remove('is-refreshing');
      _workspaceSyncViewerAutoRefreshToggle();
    }
    return;
  }
  const modeBtn = event.target && event.target.closest ? event.target.closest('[data-workspace-preview-mode]') : null;
  if (modeBtn && _workspaceViewerPayloadCache) {
    switchWorkspaceViewerMode(modeBtn.dataset.workspacePreviewMode === 'raw').catch(() => {});
    return;
  }
  const btn = event.target && event.target.closest ? event.target.closest('[data-workspace-viewer-action]') : null;
  if (!btn || !_workspaceViewedPath) return;
  handleWorkspaceFileAction(btn.dataset.workspaceViewerAction, _workspaceViewedPath);
});
workspaceEditor?.addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await saveWorkspaceFile(_workspacePathInCurrentDir(workspacePathInput?.value || ''), workspaceTextInput?.value || '');
  } catch (err) {
    setWorkspaceMessage(_workspaceErrorMessage(err, 'Unable to save session file'), 'error');
  }
});
workspaceFileList?.addEventListener('click', event => {
  const btn = event.target && event.target.closest ? event.target.closest('[data-workspace-action]') : null;
  if (!btn) return;
  const row = btn.closest('.workspace-file-row');
  if (!row || !workspaceFileList.contains(row)) return;
  const action = btn.dataset.workspaceAction;
  const path = row?.dataset.path || '';
  if (!path && action !== 'open-folder') return;
  handleWorkspaceFileAction(action, path);
});
workspaceFileList?.addEventListener('dragstart', event => {
  const row = _workspaceDragSourceFromEvent(event);
  if (!row) return;
  _workspaceDragPath = row.dataset.path || '';
  _workspaceDragKind = row.dataset.kind || '';
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', _workspaceDragPath);
  }
  row.classList.add('workspace-dragging');
});
workspaceFileList?.addEventListener('dragend', event => {
  const row = _workspaceDragSourceFromEvent(event);
  if (row) row.classList.remove('workspace-dragging');
  workspaceFileList.querySelectorAll('.workspace-drop-target').forEach(node => node.classList.remove('workspace-drop-target'));
  _workspaceDragPath = '';
  _workspaceDragKind = '';
});
workspaceFileList?.addEventListener('dragover', event => {
  const target = _workspaceDropTargetFromEvent(event);
  if (!target || !_workspaceCanDropOnFolder(_workspaceDragPath, target.dataset.path || '')) return;
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
  target.classList.add('workspace-drop-target');
});
workspaceFileList?.addEventListener('dragleave', event => {
  const target = _workspaceDropTargetFromEvent(event);
  if (!target) return;
  const related = event.relatedTarget;
  if (related && target.contains(related)) return;
  target.classList.remove('workspace-drop-target');
});
workspaceFileList?.addEventListener('drop', event => {
  void _handleWorkspaceDropMove(event);
});

if (typeof window !== 'undefined') {
  window.openWorkspace = openWorkspace;
  window.closeWorkspace = closeWorkspace;
  window.refreshWorkspaceFiles = refreshWorkspaceFiles;
  window.refreshWorkspaceFileCache = refreshWorkspaceFileCache;
  window.getWorkspaceAutocompleteFileHints = getWorkspaceAutocompleteFileHints;
  window.renderWorkspaceFiles = renderWorkspaceFiles;
  window.renderWorkspaceBrowser = renderWorkspaceBrowser;
  window.createWorkspaceDirectory = createWorkspaceDirectory;
  window.moveWorkspacePath = moveWorkspacePath;
  window.deleteWorkspacePath = deleteWorkspacePath;
  window.downloadWorkspaceFile = downloadWorkspaceFile;
  window.openWorkspaceEditorFromCommand = openWorkspaceEditorFromCommand;
  if (isWorkspaceEnabled()) setTimeout(() => { refreshWorkspaceFileCache(); }, 0);
}
