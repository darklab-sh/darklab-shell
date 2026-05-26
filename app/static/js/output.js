// ── Shared output logic ──
const _outputCore = typeof DarklabOutputCore !== 'undefined' ? DarklabOutputCore : null;

function createAnsiUpRenderer() {
  // ANSI rendering is optional. If the vendored parser fails to load, fall back
  // to escaped plain text rather than breaking transcript rendering entirely.
  if (typeof AnsiUp === 'function') {
    try {
      const instance = new AnsiUp();
      if (instance && typeof instance.ansi_to_html === 'function') {
        instance.use_classes = false;
        return instance;
      }
    } catch (err) {
      // Fall through to the plain-text renderer below.
    }
  }
  return {
    use_classes: false,
    ansi_to_html(text) {
      return escapeHtml(String(text ?? ''));
    },
  };
}

const _ansiRenderersByTab = new Map();

function _ansiTabKey(tabId) {
  return String(tabId || '__default__');
}

function _getAnsiRendererForTab(tabId) {
  const key = _ansiTabKey(tabId);
  let renderer = _ansiRenderersByTab.get(key);
  if (!renderer) {
    renderer = createAnsiUpRenderer();
    _ansiRenderersByTab.set(key, renderer);
  }
  return renderer;
}

function resetAnsiRendererForTab(tabId) {
  _ansiRenderersByTab.set(_ansiTabKey(tabId), createAnsiUpRenderer());
}

function dropAnsiRendererForTab(tabId) {
  _ansiRenderersByTab.delete(_ansiTabKey(tabId));
}

// ── Timestamp mode ──
// Cycles: 'off' → 'elapsed' → 'clock' → 'off'
// Body class 'ts-elapsed' / 'ts-clock' drives CSS ::before visibility — no JS
// needed to update existing lines when mode changes.
let tsMode = 'off';

// ── Line number mode ──
// Cycles: 'off' → 'on' → 'off'
// Body class 'ln-on' enables shared prefix rendering for output rows.
let lnMode = 'off';

const _OUTPUT_SYNC_BURST_LIMIT = 60;
const _OUTPUT_BATCH_SIZE = 300;
const _OUTPUT_APPEND_LINES_CHUNK_SIZE = 300;
const _OUTPUT_RESTORE_TAIL_DELAYS = [0, 16, 64, 160, 320];
const _OUTPUT_COALESCED_LINE_ROLES = new Set(['progress', 'status-line']);
const _pendingOutputBatches = new Map();
const _OUTPUT_SIGNAL_SCOPES = _outputCore.OUTPUT_SIGNAL_SCOPES;
const _HIGH_VOLUME_OUTPUT_DEFAULT_LINE_THRESHOLD = 50000;
const _HIGH_VOLUME_OUTPUT_DEFAULT_STATUS_INTERVAL_LINES = 50000;

function _promptUsernameOverride() {
  let value = '';
  if (typeof getPreference === 'function') {
    value = getPreference('pref_prompt_username');
  } else if (typeof document !== 'undefined') {
    const cookie = document.cookie.split(';').map(part => part.trim()).find(part => part.startsWith('pref_prompt_username='));
    try {
      value = cookie ? decodeURIComponent(cookie.slice('pref_prompt_username='.length)) : '';
    } catch (_) {
      value = '';
    }
  }
  const username = String(value || '').trim();
  return /^[A-Za-z0-9._-]{1,32}$/.test(username) ? username : '';
}

function _configuredPromptUsername() {
  const configured = typeof APP_CONFIG !== 'undefined' && APP_CONFIG && typeof APP_CONFIG.prompt_username === 'string'
    ? APP_CONFIG.prompt_username
    : 'anon';
  return _promptUsernameOverride() || String(configured || 'anon').trim() || 'anon';
}

function _configuredPromptDomain() {
  const configured = typeof APP_CONFIG !== 'undefined' && APP_CONFIG && typeof APP_CONFIG.prompt_domain === 'string'
    ? APP_CONFIG.prompt_domain
    : 'darklab.sh';
  return String(configured || 'darklab.sh').trim() || 'darklab.sh';
}

function promptIdentityPrefix(rawPrefix = null) {
  if (rawPrefix !== null) return _outputCore.promptIdentityPrefix(String(rawPrefix || ''));
  return _outputCore.promptIdentityFromParts(_configuredPromptUsername(), _configuredPromptDomain());
}

function currentPromptWorkspacePath() {
  if (
    typeof APP_CONFIG !== 'undefined'
    && APP_CONFIG
    && APP_CONFIG.workspace_enabled === true
  ) {
    const rawPath = typeof _workspaceCwd === 'function'
      ? _workspaceCwd(typeof activeTabId !== 'undefined' ? activeTabId : undefined)
      : '';
    const normalized = _outputCore.normalizeWorkspaceCwd(rawPath);
    if (typeof workspaceDisplayPath === 'function') return workspaceDisplayPath(normalized);
    return _outputCore.workspaceDisplayPath(normalized);
  }
  return '~';
}

function buildPromptLabel(rawPrefix = null, path = null) {
  const promptPath = path === null ? currentPromptWorkspacePath() : String(path || '~');
  if (rawPrefix !== null) return _outputCore.buildPromptLabel(String(rawPrefix || ''), promptPath);
  return _outputCore.buildPromptLabelFromParts(_configuredPromptUsername(), _configuredPromptDomain(), promptPath);
}

function stripPromptLabelFromEchoText(text = '') {
  return _outputCore.stripPromptLabelFromEchoText(text, buildPromptLabel(), promptIdentityPrefix());
}

function _outputPromptPrefix() {
  if (
    typeof APP_CONFIG !== 'undefined'
    && APP_CONFIG
    && APP_CONFIG.workspace_enabled === true
    && !(typeof shellPromptWrap !== 'undefined' && shellPromptWrap && shellPromptWrap.classList.contains('shell-prompt-confirm'))
  ) {
    return buildPromptLabel();
  }
  const promptPrefix = (typeof shellPromptWrap !== 'undefined' && shellPromptWrap)
    ? shellPromptWrap.querySelector('.prompt-prefix')
    : document.querySelector('#shell-prompt-wrap .prompt-prefix');
  const text = promptPrefix ? String(promptPrefix.textContent || '').trim() : '';
  return text || buildPromptLabel();
}

function _formatOutputPrefix(index, tsText, includeTimestamp) {
  return _outputCore.formatOutputPrefix(index, tsText, includeTimestamp, lnMode, tsMode);
}

function _outputPrefixesActive() {
  return lnMode === 'on' || tsMode === 'elapsed' || tsMode === 'clock';
}

function _lineTimestampPrefix(line) {
  if (tsMode === 'elapsed') return String(line?.dataset?.tsE || '');
  if (tsMode === 'clock') return String(line?.dataset?.tsC || '');
  return '';
}

function _promptTimestampPrefix() {
  if (tsMode === 'elapsed') return '+0.0s';
  if (tsMode === 'clock') return new Date().toTimeString().slice(0, 8);
  return '';
}

function _prefixWidthForOutput(out) {
  if (!_outputPrefixesActive()) return 0;
  const lineNumber = Number(out?.dataset?.outputLineCounter || 0) + 1;
  const lineDigits = lnMode === 'on' ? String(Math.max(1, lineNumber)).length : 0;
  const timestampWidth = tsMode === 'clock'
    ? 8
    : tsMode === 'elapsed'
      ? 8
      : 0;
  return lineDigits + timestampWidth + (lineDigits && timestampWidth ? 1 : 0);
}

function _tabForOutput(out) {
  const id = String(out?.id || '').replace(/^output-/, '');
  return id && typeof getTab === 'function' ? getTab(id) : null;
}

function _trimOutputToMaxLines(out) {
  const max = APP_CONFIG.max_output_lines;
  if (!(max > 0) || !out || typeof out.getElementsByClassName !== 'function') return 0;
  const lines = out.getElementsByClassName('line');
  const removed = Math.max(0, lines.length - max);
  if (!removed) return 0;
  const removedLines = [];
  for (let index = 0; index < removed; index += 1) {
    if (lines[index]) removedLines.push(lines[index]);
  }
  removedLines.forEach(line => line.remove());
  return removed;
}

function _syncOutputLinePrefixMetadata(out, tab = null) {
  if (!out || typeof out.getElementsByClassName !== 'function') return;
  const lines = Array.from(out.getElementsByClassName('line'));
  const prefixStrings = [];
  let visibleIndex = 0;
  let maxLineNumber = Math.max(
    Number(tab?._outputLineCounter || 0),
    Number(out.dataset?.outputLineCounter || 0),
  );

  lines.forEach((line) => {
    if (_isPrefixExcludedLine(line)) {
      line.dataset.prefix = '';
      delete line.dataset.lineNumber;
      return;
    }
    visibleIndex += 1;
    const existingNumber = Number(line.dataset.lineNumber || 0);
    const lineNumber = existingNumber > 0 ? existingNumber : visibleIndex;
    line.dataset.lineNumber = String(lineNumber);
    maxLineNumber = Math.max(maxLineNumber, lineNumber);
    const tsText = _lineTimestampPrefix(line);
    line.dataset.prefix = tsText;
    prefixStrings.push(_formatOutputPrefix(lineNumber, tsText, true));
  });

  const prompt = out.querySelector?.('#shell-prompt-wrap');
  if (prompt) {
    const promptTsText = _promptTimestampPrefix();
    prompt.dataset.lineNumber = String(maxLineNumber + 1);
    prompt.dataset.prefix = promptTsText;
    prefixStrings.push(_formatOutputPrefix(maxLineNumber + 1, promptTsText, true));
  }

  out.dataset.outputLineCounter = String(maxLineNumber);
  const targetTab = tab || _tabForOutput(out);
  if (targetTab) targetTab._outputLineCounter = maxLineNumber;
  if (out.style) {
    const prefixWidth = Math.max(0, ...prefixStrings.map(s => String(s || '').length));
    out.style.setProperty('--output-prefix-width', `${prefixWidth}ch`);
  }
}

function _emptyOutputSignalCounts() {
  return _outputCore.emptySignalCounts();
}

function _isOutputSignalSummaryClassName(cls) {
  return _outputCore.isSignalSummaryClassName(cls);
}

function _outputLineHasClass(rawLine, className) {
  return _outputCore.lineHasClass(rawLine, className);
}

function _isOutputSignalCountableLine(rawLine) {
  return _outputCore.isSignalCountableLine(rawLine);
}

function _isOutputBuiltinCommandRoot(root) {
  const builtinRoots = (
    typeof acBuiltinCommandRoots !== 'undefined' && Array.isArray(acBuiltinCommandRoots)
  ) ? acBuiltinCommandRoots : [];
  return _outputCore.isBuiltinCommandRoot(root, builtinRoots);
}

function _countableOutputSignalScopes(rawLine) {
  const builtinRoots = (
    typeof acBuiltinCommandRoots !== 'undefined' && Array.isArray(acBuiltinCommandRoots)
  ) ? acBuiltinCommandRoots : [];
  return _outputCore.countableSignalScopes(rawLine, builtinRoots);
}

function _ensureTabOutputSignalCounts(tab) {
  if (!tab) return _emptyOutputSignalCounts();
  if (!tab._outputSignalCounts || typeof tab._outputSignalCounts !== 'object') {
    tab._outputSignalCounts = _emptyOutputSignalCounts();
  }
  _OUTPUT_SIGNAL_SCOPES.forEach((scope) => {
    tab._outputSignalCounts[scope] = Math.max(0, Number(tab._outputSignalCounts[scope] || 0));
  });
  return tab._outputSignalCounts;
}

function _adjustTabOutputSignalCounts(tab, rawLine, delta) {
  if (!tab || !rawLine || !delta) return;
  const scopes = _countableOutputSignalScopes(rawLine);
  if (!scopes.length) return;
  const counts = _ensureTabOutputSignalCounts(tab);
  scopes.forEach((scope) => {
    counts[scope] = Math.max(0, Number(counts[scope] || 0) + delta);
  });
  tab._outputSignalCountsValid = true;
}

function _resetTabOutputSignalCounts(tab, rawLines = []) {
  if (!tab) return;
  tab._outputSignalCounts = _emptyOutputSignalCounts();
  tab._outputSignalCountsValid = true;
  (Array.isArray(rawLines) ? rawLines : []).forEach((rawLine) => {
    _adjustTabOutputSignalCounts(tab, rawLine, 1);
  });
}

function _syncOutputPrefixesForAppend(out, appendedLine = null) {
  if (!out || !out.style) return;
  if (appendedLine) {
    appendedLine.dataset.prefix = _isPrefixExcludedLine(appendedLine) ? '' : _lineTimestampPrefix(appendedLine);
  }
  const prompt = out.querySelector?.('#shell-prompt-wrap');
  if (prompt) {
    prompt.dataset.lineNumber = String((Number(out.dataset.outputLineCounter || 0) || 0) + 1);
    prompt.dataset.prefix = _promptTimestampPrefix();
  }
  out.style.setProperty('--output-prefix-width', `${_prefixWidthForOutput(out)}ch`);
}

function _coalescedOutputRoleForEvent(event) {
  const role = String(event && event.role || '').trim();
  return _OUTPUT_COALESCED_LINE_ROLES.has(role) ? role : '';
}

function _coalescedOutputRoleForLine(line) {
  const role = String(line && line.dataset && line.dataset.outputRole || '').trim();
  if (_OUTPUT_COALESCED_LINE_ROLES.has(role)) return role;
  const classes = line && line.classList ? line.classList : null;
  if (classes?.contains?.('progress')) return 'progress';
  if (classes?.contains?.('status-line')) return 'status-line';
  return '';
}

function _lastRenderedOutputLine(out) {
  if (!out) return null;
  let node = out.lastElementChild;
  if (node && node.id === 'shell-prompt-wrap') node = node.previousElementSibling;
  return node && node.classList?.contains?.('line') ? node : null;
}

function _replaceLastRenderedLineIfCoalescible(out, entry) {
  const role = String(entry && entry.coalesceRole || '');
  if (!role) return false;
  const previous = _lastRenderedOutputLine(out);
  if (!previous || _coalescedOutputRoleForLine(previous) !== role) return false;
  const previousLineNumber = previous.dataset?.lineNumber || '';
  _updateRenderedOutputLineInPlace(previous, entry.span);
  if (previousLineNumber) previous.dataset.lineNumber = previousLineNumber;
  return true;
}

function _coalescedReplacementLineNumber(out, entry) {
  const role = String(entry && entry.coalesceRole || '');
  if (!role) return 0;
  const previous = _lastRenderedOutputLine(out);
  if (!previous || _coalescedOutputRoleForLine(previous) !== role) return 0;
  return Number(previous.dataset?.lineNumber || 0);
}

function _updateRenderedOutputLineInPlace(current, next) {
  if (!current || !next) return;
  Array.from(current.attributes || []).forEach(attr => current.removeAttribute(attr.name));
  Array.from(next.attributes || []).forEach(attr => current.setAttribute(attr.name, attr.value));
  current.replaceChildren(...Array.from(next.childNodes || []));
}

function _queuePendingOutputEntry(state, entry) {
  if (!state || !entry) return false;
  const role = String(entry.coalesceRole || '');
  const previous = state.items[state.items.length - 1];
  if (role && previous && String(previous.coalesceRole || '') === role) {
    state.items[state.items.length - 1] = entry;
    return true;
  }
  state.items.push(entry);
  return false;
}

function _isWelcomeLine(line) {
  if (!line || !line.classList) return false;
  return [...line.classList].some(cls => cls.startsWith('welcome-') || cls.startsWith('wlc-'));
}

function _isSyntheticSummaryLine(line) {
  if (!line || !line.classList) return false;
  return [
    'builtin-signal-summary-header',
    'builtin-signal-summary-section',
    'builtin-signal-summary-row',
    'builtin-signal-summary-note',
    'builtin-signal-summary-sep',
  ].some(cls => line.classList.contains(cls));
}

function _isPrefixExcludedLine(line) {
  return _isWelcomeLine(line) || _isSyntheticSummaryLine(line);
}

function _assignOutputLineNumber(out, tab, line) {
  if (!out || !line) return 0;
  if (_isPrefixExcludedLine(line)) {
    delete line.dataset.lineNumber;
    return 0;
  }
  const existing = Number(line.dataset.lineNumber || 0);
  if (existing > 0) {
    if (tab) tab._outputLineCounter = Math.max(Number(tab._outputLineCounter || 0), existing);
    out.dataset.outputLineCounter = String(Math.max(Number(out.dataset.outputLineCounter || 0), existing));
    return existing;
  }
  const base = Math.max(
    Number(tab?._outputLineCounter || 0),
    Number(out.dataset.outputLineCounter || 0),
  );
  const next = base + 1;
  line.dataset.lineNumber = String(next);
  if (tab) tab._outputLineCounter = next;
  out.dataset.outputLineCounter = String(next);
  return next;
}

function _assignRawOutputLineNumber(out, tab, rawLine) {
  if (!out || !rawLine) return 0;
  const existing = Number(rawLine.line_number || 0);
  if (existing > 0) {
    if (tab) tab._outputLineCounter = Math.max(Number(tab._outputLineCounter || 0), existing);
    out.dataset.outputLineCounter = String(Math.max(Number(out.dataset.outputLineCounter || 0), existing));
    return existing;
  }
  const base = Math.max(
    Number(tab?._outputLineCounter || 0),
    Number(out.dataset?.outputLineCounter || 0),
  );
  const next = base + 1;
  rawLine.line_number = next;
  if (tab) tab._outputLineCounter = next;
  out.dataset.outputLineCounter = String(next);
  return next;
}

function _getPendingOutputBatch(tabId) {
  // Output can arrive very quickly from SSE. Batch DOM writes per tab so large
  // scans do not thrash layout on every single line.
  let state = _pendingOutputBatches.get(tabId);
  if (!state) {
    state = {
      items: [],
      rawLines: [],
      scheduled: false,
      burstCount: 0,
    };
    _pendingOutputBatches.set(tabId, state);
  }
  return state;
}

function _cancelPendingOutputBatch(tabId) {
  const state = _pendingOutputBatches.get(tabId);
  if (!state) return;
  if (state.handle != null) {
    clearTimeout(state.handle);
  }
  _pendingOutputBatches.delete(tabId);
}

function hasPendingOutputBatch(tabId) {
  const state = _pendingOutputBatches.get(tabId);
  return !!(state && (state.scheduled || state.items.length > 0 || state.rawLines.length > 0));
}

function discardPendingOutputBatch(tabId) {
  _cancelPendingOutputBatch(tabId);
}

function _schedulePendingOutputFlush(tabId) {
  const state = _getPendingOutputBatch(tabId);
  if (state.scheduled) return;
  state.scheduled = true;
  state.handle = setTimeout(() => _flushPendingOutputBatch(tabId), 16);
}

function _normalizeOutputSignals(signals) {
  return _outputCore.normalizeSignals(signals);
}

function _normalizeOutputEntities(entities) {
  return _outputCore.normalizeEntities(entities);
}

function _applyOutputSignalMetadata(span, rawLine, metadata) {
  if (!metadata || typeof metadata !== 'object') return;
  if (typeof metadata.kind === 'string' && metadata.kind) rawLine.kind = metadata.kind;
  if (typeof metadata.role === 'string' && metadata.role) rawLine.role = metadata.role;
  const signals = _normalizeOutputSignals(metadata.signals);
  if (signals.length) {
    rawLine.signals = signals;
    if (span) span.dataset.signals = signals.join(',');
  }
  if (Number.isInteger(metadata.line_index)) {
    rawLine.line_index = metadata.line_index;
    if (span) span.dataset.lineIndex = String(metadata.line_index);
  }
  if (Number.isInteger(metadata.line_number)) {
    rawLine.line_number = metadata.line_number;
    if (span) span.dataset.lineNumber = String(metadata.line_number);
  }
  if (typeof metadata.command_root === 'string' && metadata.command_root) {
    rawLine.command_root = metadata.command_root;
    if (span) span.dataset.commandRoot = metadata.command_root;
  }
  if (typeof metadata.target === 'string' && metadata.target) {
    rawLine.target = metadata.target;
    if (span) span.dataset.signalTarget = metadata.target;
  }
  const entities = _normalizeOutputEntities(metadata.entities);
  if (entities.length) {
    rawLine.entities = entities;
    if (span) span.dataset.entities = JSON.stringify(entities);
  }
}

function _atlasTabForOutputEntity(type) {
  const value = String(type || '').trim().toLowerCase();
  if (value === 'ip') return 'ip';
  if (value === 'host') return 'domain';
  if (value === 'domain') return 'domain';
  if (value === 'url') return 'url';
  if (value === 'hash') return 'hash';
  if (value === 'cve') return 'cve';
  return value || 'ip';
}

function _outputEntityValue(entity) {
  return String(entity && (entity.canonical_value || entity.value) || '').trim();
}

function _outputEntityRangeCandidates(text, entity) {
  const source = String(text || '');
  const value = String(entity && entity.value || '').trim();
  const canonical = _outputEntityValue(entity);
  const candidates = [];
  if (Number.isInteger(entity && entity.start) && Number.isInteger(entity && entity.end)) {
    const rangedText = source.slice(entity.start, entity.end);
    if ([value, canonical].filter(Boolean).includes(rangedText)) {
      candidates.push({ start: entity.start, end: entity.end });
    }
  }
  [value, canonical].filter(Boolean).forEach(needle => {
    const index = source.indexOf(needle);
    if (index >= 0) candidates.push({ start: index, end: index + needle.length });
  });
  return candidates;
}

function _outputEntityRanges(text, entities) {
  const source = String(text || '');
  const ranges = [];
  const overlaps = (start, end) => ranges.some(range => start < range.end && end > range.start);
  (Array.isArray(entities) ? entities : []).forEach(entity => {
    const type = String(entity && entity.type || '').trim();
    const value = _outputEntityValue(entity);
    if (!type || !value) return;
    const candidate = _outputEntityRangeCandidates(source, entity)
      .find(range => range.start >= 0 && range.end > range.start && range.end <= source.length);
    if (!candidate || overlaps(candidate.start, candidate.end)) return;
    ranges.push({ ...candidate, entity });
  });
  return ranges.sort((a, b) => a.start - b.start);
}

function _entityTokenFromText(text, entity, tabId) {
  const token = document.createElement('span');
  token.className = 'chip chip-action atlas-entity-token';
  token.setAttribute('role', 'button');
  token.setAttribute('tabindex', '0');
  token.dataset.atlasEntityType = String(entity && entity.type || '');
  token.dataset.atlasEntityValue = _outputEntityValue(entity);
  token.dataset.atlasEntityTab = _atlasTabForOutputEntity(entity && entity.type);
  token.title = `Open ${token.dataset.atlasEntityValue} in Atlas`;
  token.setAttribute('aria-label', token.title);
  token.innerHTML = _getAnsiRendererForTab(tabId).ansi_to_html(text);
  return token;
}

function _prepareOutputRenderedLinks(container) {
  if (!container || typeof container.querySelectorAll !== 'function') return;
  container.querySelectorAll('a[href]').forEach(link => {
    link.setAttribute('target', '_blank');
    const rel = new Set(String(link.getAttribute('rel') || '').split(/\s+/).filter(Boolean));
    rel.add('noopener');
    link.setAttribute('rel', Array.from(rel).join(' '));
  });
}

function _renderAnsiWithEntityTokens(content, text, entities, tabId) {
  const ranges = _outputEntityRanges(text, entities);
  if (!ranges.length) {
    content.innerHTML = _getAnsiRendererForTab(tabId).ansi_to_html(text);
    _prepareOutputRenderedLinks(content);
    return;
  }
  const renderer = _getAnsiRendererForTab(tabId);
  let cursor = 0;
  ranges.forEach(range => {
    if (range.start > cursor) {
      const plain = document.createElement('span');
      plain.innerHTML = renderer.ansi_to_html(text.slice(cursor, range.start));
      content.appendChild(plain);
    }
    content.appendChild(_entityTokenFromText(text.slice(range.start, range.end), range.entity, tabId));
    cursor = range.end;
  });
  if (cursor < text.length) {
    const trailing = document.createElement('span');
    trailing.innerHTML = renderer.ansi_to_html(text.slice(cursor));
    content.appendChild(trailing);
  }
  _prepareOutputRenderedLinks(content);
}

function _openAtlasForOutputEntity(token, options = {}) {
  if (!token || typeof openAtlas !== 'function') return;
  const entityType = String(token.dataset.atlasEntityType || '');
  const entityValue = String(token.dataset.atlasEntityValue || '');
  const tab = String(token.dataset.atlasEntityTab || _atlasTabForOutputEntity(entityType));
  if (!entityType || !entityValue) return;
  _closeOutputEntityMenu();
  void openAtlas({
    source: 'output-entity',
    tab,
    entityType,
    entityValue,
    forceView: 'detail',
    refreshIntel: !!options.refreshIntel,
    addActiveProject: !!options.addActiveProject,
  });
}

function _focusOutputEntityLine(token) {
  const line = token && token.closest ? token.closest('.line') : null;
  if (!line) return;
  line.scrollIntoView({ block: 'center', behavior: 'smooth' });
  line.classList.add('atlas-line-focus');
  setTimeout(() => line.classList.remove('atlas-line-focus'), 1600);
}

let _outputEntityMenu = null;
let _outputEntityMenuOpener = null;

function _hasOutputTextSelection() {
  const selection = typeof window !== 'undefined' && window.getSelection ? window.getSelection() : null;
  return !!(selection && !selection.isCollapsed && String(selection.toString() || '').length > 0);
}

function _closeOutputEntityMenu(options = {}) {
  const opener = _outputEntityMenuOpener;
  if (_outputEntityMenu) {
    _outputEntityMenu.remove();
    _outputEntityMenu = null;
  }
  _outputEntityMenuOpener = null;
  if (options.restoreFocus && opener && document.contains(opener) && typeof opener.focus === 'function') {
    opener.focus({ preventScroll: true });
  }
}

function _outputEntityMenuButton(label, action) {
  const item = document.createElement('button');
  item.type = 'button';
  item.className = 'dropdown-item dropdown-item-compact';
  item.dataset.outputEntityAction = action;
  item.setAttribute('role', 'menuitem');
  item.textContent = label;
  return item;
}

function _showOutputEntityMenu(token, x, y) {
  _closeOutputEntityMenu();
  const menu = document.createElement('div');
  menu.className = 'atlas-output-entity-menu save-menu dropdown-surface';
  menu.setAttribute('role', 'menu');
  menu.setAttribute('tabindex', '-1');
  menu.append(
    _outputEntityMenuButton('Open in Atlas', 'open-atlas'),
    _outputEntityMenuButton('Edit labels/notes', 'edit-metadata'),
    _outputEntityMenuButton('Add to active project', 'promote'),
    _outputEntityMenuButton('Lookup intel', 'lookup-intel'),
    _outputEntityMenuButton('Copy value', 'copy-value'),
    _outputEntityMenuButton('See in run', 'see-run'),
  );
  menu.addEventListener('click', (event) => {
    const action = event.target && event.target.closest
      ? event.target.closest('[data-output-entity-action]')?.dataset.outputEntityAction
      : '';
    if (!action) return;
    event.preventDefault();
    event.stopPropagation();
    if (action === 'open-atlas') _openAtlasForOutputEntity(token);
    if (action === 'edit-metadata') _openAtlasForOutputEntity(token);
    if (action === 'promote') _openAtlasForOutputEntity(token, { addActiveProject: true });
    if (action === 'lookup-intel') _openAtlasForOutputEntity(token, { refreshIntel: true });
    if (action === 'copy-value') {
      copyTextToClipboard(String(token.dataset.atlasEntityValue || ''))
        .then(() => showToast('Entity copied'))
        .catch(() => showToast('Failed to copy entity', 'error'));
    }
    if (action === 'see-run') _focusOutputEntityLine(token);
    _closeOutputEntityMenu();
  });
  menu.addEventListener('keydown', (event) => {
    const items = Array.from(menu.querySelectorAll('[data-output-entity-action]'));
    if (!items.length) return;
    const currentIndex = Math.max(0, items.indexOf(document.activeElement));
    let nextIndex = currentIndex;
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      _closeOutputEntityMenu({ restoreFocus: true });
      return;
    }
    if (event.key === 'ArrowDown') nextIndex = (currentIndex + 1) % items.length;
    else if (event.key === 'ArrowUp') nextIndex = (currentIndex - 1 + items.length) % items.length;
    else if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = items.length - 1;
    else return;
    event.preventDefault();
    event.stopPropagation();
    items[nextIndex].focus({ preventScroll: true });
  });
  document.body.appendChild(menu);
  const rect = menu.getBoundingClientRect();
  const left = Math.max(8, Math.min(x, window.innerWidth - rect.width - 8));
  const top = Math.max(8, Math.min(y, window.innerHeight - rect.height - 8));
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
  _outputEntityMenu = menu;
  _outputEntityMenuOpener = token;
  const firstItem = menu.querySelector('[data-output-entity-action]');
  if (firstItem) firstItem.focus({ preventScroll: true });
}

let _outputEntityLongPressTimer = null;

function _bindOutputEntityTokenEvents() {
  if (typeof document === 'undefined' || document._darklabOutputEntityTokensBound) return;
  document._darklabOutputEntityTokensBound = true;
  document.addEventListener('click', (event) => {
    const token = event.target && event.target.closest ? event.target.closest('.atlas-entity-token') : null;
    if (token) {
      if (_hasOutputTextSelection()) return;
      event.preventDefault();
      event.stopPropagation();
      _openAtlasForOutputEntity(token);
    } else {
      _closeOutputEntityMenu();
    }
  });
  document.addEventListener('contextmenu', (event) => {
    const token = event.target && event.target.closest ? event.target.closest('.atlas-entity-token') : null;
    if (!token) return;
    event.preventDefault();
    event.stopPropagation();
    _showOutputEntityMenu(token, event.clientX, event.clientY);
  });
  document.addEventListener('touchstart', (event) => {
    const token = event.target && event.target.closest ? event.target.closest('.atlas-entity-token') : null;
    if (!token) return;
    const touch = event.touches && event.touches[0];
    clearTimeout(_outputEntityLongPressTimer);
    _outputEntityLongPressTimer = setTimeout(() => {
      _showOutputEntityMenu(token, touch ? touch.clientX : 12, touch ? touch.clientY : 12);
    }, 550);
  }, { passive: true });
  ['touchend', 'touchmove', 'touchcancel'].forEach(name => {
    document.addEventListener(name, () => clearTimeout(_outputEntityLongPressTimer), { passive: true });
  });
  document.addEventListener('keydown', (event) => {
    const token = event.target && event.target.closest ? event.target.closest('.atlas-entity-token') : null;
    if (token && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      event.stopPropagation();
      _openAtlasForOutputEntity(token);
      return;
    }
    if (token && (event.key === 'ContextMenu' || (event.key === 'F10' && event.shiftKey))) {
      event.preventDefault();
      event.stopPropagation();
      const rect = token.getBoundingClientRect();
      _showOutputEntityMenu(token, rect.left, rect.bottom);
      return;
    }
    if (event.key === 'Escape') _closeOutputEntityMenu({ restoreFocus: true });
  });
}

_bindOutputEntityTokenEvents();

function _highVolumeOutputLineThreshold() {
  const configured = Number(APP_CONFIG?.high_volume_output_line_threshold);
  if (Number.isFinite(configured)) return Math.max(0, Math.floor(configured));
  return _HIGH_VOLUME_OUTPUT_DEFAULT_LINE_THRESHOLD;
}

function _highVolumeOutputStatusIntervalLines() {
  const configured = Number(APP_CONFIG?.high_volume_output_status_interval_lines);
  if (Number.isFinite(configured)) return Math.max(1, Math.floor(configured));
  return _HIGH_VOLUME_OUTPUT_DEFAULT_STATUS_INTERVAL_LINES;
}

function _isLiveOutputMetadata(metadata) {
  return !!(metadata && typeof metadata === 'object' && metadata.live_output === true);
}

function _ensureHighVolumeOutputState(tab) {
  if (!tab) return null;
  if (!tab.highVolumeOutput || typeof tab.highVolumeOutput !== 'object') {
    tab.highVolumeOutput = {
      active: false,
      receivedLines: 0,
      skippedLines: 0,
      coalescedLines: 0,
      lastNoticeLine: 0,
      resumeRequested: false,
      resumeDisabled: false,
      finalSummaryShown: false,
    };
  }
  if (typeof tab.highVolumeOutput.finalSummaryShown !== 'boolean') {
    tab.highVolumeOutput.finalSummaryShown = false;
  }
  tab.highVolumeOutput.coalescedLines = Math.max(0, Number(tab.highVolumeOutput.coalescedLines || 0));
  return tab.highVolumeOutput;
}

function _formatHighVolumeCount(value) {
  return Number(value || 0).toLocaleString('en-US');
}

function _runOutputModel() {
  if (typeof DarklabRunOutputModel !== 'undefined') return DarklabRunOutputModel;
  if (typeof globalThis !== 'undefined' && globalThis.DarklabRunOutputModel) return globalThis.DarklabRunOutputModel;
  return null;
}

let _runOutputModelMissingReported = false;

function _reportMissingRunOutputModel() {
  if (_runOutputModelMissingReported) return;
  _runOutputModelMissingReported = true;
  if (typeof logClientError === 'function') {
    logClientError('run output model missing', new Error('DarklabRunOutputModel is not loaded'));
  }
}

function _fallbackLineEventKind(payload) {
  const kind = String(payload && payload.kind || '').trim();
  if (['info', 'notice', 'warn', 'error'].includes(kind)) return kind;
  const classes = String(payload && payload.cls || '').split(/\s+/).filter(Boolean);
  if (classes.includes('notice') || classes.includes('builtin-note') || classes.includes('welcome-output')) return 'notice';
  if (classes.includes('warn') || classes.includes('warning')) return 'warn';
  if (classes.includes('error')) return 'error';
  return 'info';
}

function _fallbackLineEventRole(payload) {
  const role = String(payload && payload.role || '').trim();
  if ([
    'body',
    'prompt-echo',
    'section-header',
    'kv',
    'help-row',
    'pty-marker',
    'progress',
    'status-line',
    'success',
    'denied',
    'exit-ok',
    'exit-fail',
  ].includes(role)) return role;
  const classes = String(payload && payload.cls || '').split(/\s+/).filter(Boolean);
  if (classes.includes('prompt-echo') || classes.includes('cmd')) return 'prompt-echo';
  if (classes.includes('builtin-section')) return 'section-header';
  if (classes.includes('builtin-kv')) return 'kv';
  if (classes.includes('builtin-help-row') || classes.includes('builtin-faq-q') || classes.includes('builtin-faq-a')) return 'help-row';
  if (classes.includes('pty-marker')) return 'pty-marker';
  if (classes.includes('progress')) return 'progress';
  if (classes.includes('status-line')) return 'status-line';
  if (classes.includes('builtin-success')) return 'success';
  if (classes.includes('denied')) return 'denied';
  if (classes.includes('exit-ok')) return 'exit-ok';
  if (classes.includes('exit-fail')) return 'exit-fail';
  return 'body';
}

function _fallbackLineEventLegacyClass(event) {
  const cls = String(event && (event.legacy_cls || event.cls) || '').trim();
  if (cls) return cls;
  const role = String(event && event.role || 'body');
  if (role === 'prompt-echo') return 'prompt-echo';
  if (role === 'section-header') return 'builtin-section';
  if (role === 'kv') return 'builtin-kv';
  if (role === 'help-row') return 'builtin-help-row';
  if (role === 'pty-marker') return 'pty-marker';
  if (role === 'progress') return 'progress';
  if (role === 'status-line') return 'status-line';
  if (role === 'success') return 'builtin-success';
  if (['denied', 'exit-ok', 'exit-fail'].includes(role)) return role;
  const kind = String(event && event.kind || 'info');
  if (kind === 'notice') return 'notice';
  if (kind === 'warn') return 'warn';
  if (kind === 'error') return 'error';
  return '';
}

function _lineEventModelStub(payload) {
  const item = payload && typeof payload === 'object' ? payload : {};
  _reportMissingRunOutputModel();
  const cls = String(item.cls || '');
  return {
    text: String(item.text || ''),
    kind: _fallbackLineEventKind(item),
    role: _fallbackLineEventRole(item),
    legacy_cls: cls,
    ts_clock: String(item.tsC || item.ts_clock || ''),
    ts_elapsed: String(item.tsE || item.ts_elapsed || ''),
    signals: _normalizeOutputSignals(item.signals),
    line_index: Number.isInteger(item.line_index) ? item.line_index : null,
    line_number: Number.isInteger(item.line_number) ? item.line_number : undefined,
    command_root: String(item.command_root || ''),
    target: String(item.target || ''),
    entities: _normalizeOutputEntities(item.entities),
  };
}

function _lineEventFromWire(payload) {
  const model = _runOutputModel();
  if (model && typeof model.fromWireLineEvent === 'function') {
    const event = model.fromWireLineEvent(payload || {});
    if (payload && typeof payload === 'object' && Number.isInteger(payload.line_number)) {
      event.line_number = payload.line_number;
    }
    return event;
  }
  return _lineEventModelStub(payload);
}

function _lineEventLegacyPayload(event) {
  const model = _runOutputModel();
  if (model && typeof model.toLegacyWireLineEvent === 'function') {
    return model.toLegacyWireLineEvent(event || {});
  }
  _reportMissingRunOutputModel();
  return {
    text: String(event && event.text || ''),
    cls: _fallbackLineEventLegacyClass(event),
    tsC: String(event && (event.ts_clock || event.tsC) || ''),
    tsE: String(event && (event.ts_elapsed || event.tsE) || ''),
  };
}

function _mergeLineEventMetadata(payload, metadata = null) {
  const merged = {};
  const sources = [
    payload && typeof payload === 'object' ? payload.metadata : null,
    metadata,
    payload && typeof payload === 'object' ? payload : null,
  ];
  sources.forEach(source => {
    if (!source || typeof source !== 'object') return;
    ['kind', 'role', 'signals', 'line_index', 'line_number', 'command_root', 'target', 'entities', 'high_volume_resume', 'live_output', 'faq_command'].forEach(key => {
      if (source[key] !== undefined && source[key] !== null && source[key] !== '') merged[key] = source[key];
    });
  });
  return Object.keys(merged).length ? merged : null;
}

function _lineEventPayload(text, cls, metadata = null) {
  if (text && typeof text === 'object') {
    const payload = { ...text };
    if (payload.metadata && typeof payload.metadata === 'object') {
      ['kind', 'role', 'signals', 'line_index', 'line_number', 'command_root', 'target', 'entities'].forEach(key => {
        if (payload[key] === undefined && payload.metadata[key] !== undefined) payload[key] = payload.metadata[key];
      });
    }
    if (metadata && typeof metadata === 'object') {
      ['kind', 'role', 'signals', 'line_index', 'line_number', 'command_root', 'target', 'entities'].forEach(key => {
        if (metadata[key] !== undefined) payload[key] = metadata[key];
      });
    }
    return payload;
  }
  const payload = { text: String(text ?? ''), cls: String(cls || '') };
  if (metadata && typeof metadata === 'object') {
    ['kind', 'role', 'signals', 'line_index', 'line_number', 'command_root', 'target', 'entities'].forEach(key => {
      if (metadata[key] !== undefined) payload[key] = metadata[key];
    });
  }
  return payload;
}

function _normalizeLineEventInput(text, cls = '', metadata = null) {
  const payload = _lineEventPayload(text, cls, metadata);
  return {
    event: _lineEventFromWire(payload),
    metadata: _mergeLineEventMetadata(payload, metadata),
  };
}

function _normalizeAppendLineArgs(text, cls, tabId, metadata = null) {
  if (text && typeof text === 'object') {
    const tabIdValue = typeof tabId === 'string' && tabId ? tabId : (typeof cls === 'string' ? cls : '');
    const metadataValue = metadata || (tabId && typeof tabId === 'object' ? tabId : null);
    return {
      ..._normalizeLineEventInput(text, '', metadataValue),
      tabId: tabIdValue,
    };
  }
  return {
    ..._normalizeLineEventInput(text, cls, metadata),
    tabId,
  };
}

function _legacyClsForLineEvent(event) {
  return String(_lineEventLegacyPayload(event).cls || '');
}

function _isPromptEchoLineEvent(event) {
  return String(event && event.role || '') === 'prompt-echo';
}

function _isPlainOutputLineEvent(event) {
  const role = String(event && event.role || 'body');
  const kind = String(event && event.kind || 'info');
  return ['exit-ok', 'exit-fail', 'denied'].includes(role) || kind === 'notice';
}

function _rawOutputLine(event, tabId, now, runStart, metadata = null) {
  const tsC = new Date(now).toTimeString().slice(0, 8);
  const tsE = runStart ? '+' + ((now - runStart) / 1000).toFixed(1) + 's' : '+0.0s';
  let rawTextForStorage = String(event && event.text || '');
  if (_isPromptEchoLineEvent(event)) {
    const prefix = _outputPromptPrefix();
    rawTextForStorage = `${prefix}${event.text ? ' ' + event.text : ''}`;
  }
  const rawLine = { ..._lineEventLegacyPayload({ ...event, text: rawTextForStorage, ts_clock: tsC, ts_elapsed: tsE }), tsC, tsE };
  _applyOutputSignalMetadata(null, rawLine, metadata);
  return rawLine;
}

function _appendHighVolumeOutputNotice(tabId, state, { force = false } = {}) {
  if (!state || (!force && state.receivedLines - state.lastNoticeLine < _highVolumeOutputStatusIntervalLines())) return;
  state.lastNoticeLine = state.receivedLines;
  appendLine(
    `[high-volume output mode: ${_formatHighVolumeCount(state.receivedLines)} lines received; live rendering paused]`,
    'notice',
    tabId,
    { high_volume_resume: true },
  );
}

function _flushPendingOutputBeforeHighVolumeSkip(tabId) {
  const state = _pendingOutputBatches.get(tabId);
  if (!state || (!state.items.length && !state.rawLines.length)) return;
  while (state.items.length > 0 || state.rawLines.length > 0) {
    _flushPendingOutputBatch(tabId);
    const latest = _pendingOutputBatches.get(tabId);
    if (!latest || latest === state && !latest.items.length && !latest.rawLines.length) break;
  }
}

function _shouldSkipLiveOutputRender(tab, metadata) {
  if (!_isLiveOutputMetadata(metadata)) return false;
  const state = _ensureHighVolumeOutputState(tab);
  if (!state) return false;
  state.receivedLines += 1;
  const threshold = _highVolumeOutputLineThreshold();
  if (!threshold || state.resumeRequested || state.resumeDisabled) return false;
  if (!state.active && state.receivedLines > threshold) {
    state.active = true;
  }
  return state.active;
}

function resetHighVolumeOutputState(tabId) {
  const tab = getTab(tabId);
  if (!tab) return;
  tab.highVolumeOutput = {
    active: false,
    receivedLines: 0,
    skippedLines: 0,
    coalescedLines: 0,
    lastNoticeLine: 0,
    resumeRequested: false,
    resumeDisabled: false,
    finalSummaryShown: false,
  };
}

function appendHighVolumeOutputFinalSummary(tabId) {
  const tab = getTab(tabId);
  const state = _ensureHighVolumeOutputState(tab);
  if (!tab || !state || state.finalSummaryShown || (!state.skippedLines && !state.coalescedLines)) return false;
  state.finalSummaryShown = true;
  const parts = [];
  if (state.skippedLines) {
    const count = _formatHighVolumeCount(state.skippedLines);
    const lineWord = Number(state.skippedLines) === 1 ? 'line was' : 'lines were';
    parts.push(`${count} ${lineWord} not rendered live in this tab`);
  }
  if (state.coalescedLines) {
    parts.push('progress/status updates were collapsed in this tab, so live line numbers may differ from the saved transcript');
  }
  appendLine(
    `[live output summary: ${parts.join('; ')}; full transcript output is preserved in saved output, permalinks, and exports]`,
    'notice',
    tabId,
  );
  return true;
}

function recordLiveOutputCoalescedLines(tabId, count) {
  const value = Math.max(0, Number(count || 0));
  if (!value) return;
  const tab = getTab(tabId);
  const state = _ensureHighVolumeOutputState(tab);
  if (!state) return;
  state.coalescedLines = Math.max(0, Number(state.coalescedLines || 0) + value);
}

function disableHighVolumeOutputResumeControls(tabId) {
  const tab = getTab(tabId);
  const state = _ensureHighVolumeOutputState(tab);
  if (state) {
    state.active = false;
    state.resumeDisabled = true;
  }
  const out = getOutput(tabId);
  if (!out || typeof out.querySelectorAll !== 'function') return;
  out.querySelectorAll('[data-high-volume-resume-tab]').forEach(button => {
    if (String(button.dataset.highVolumeResumeTab || '') !== String(tabId || '')) return;
    button.disabled = true;
    button.setAttribute('aria-disabled', 'true');
    button.title = 'This command is no longer running';
  });
}

function _resumeHighVolumeLiveOutput(tabId) {
  const tab = getTab(tabId);
  const state = _ensureHighVolumeOutputState(tab);
  if (!tab || !state) return;
  if (state.resumeDisabled || tab.st !== 'running') {
    disableHighVolumeOutputResumeControls(tabId);
    return;
  }
  state.active = false;
  state.resumeRequested = true;
  appendLine(
    `[live output rendering resumed after ${_formatHighVolumeCount(state.skippedLines)} skipped lines; new lines will render live]`,
    'notice',
    tabId,
  );
}

function _bindHighVolumeOutputResumeButton(button) {
  if (!button) return;
  const onActivate = () => _resumeHighVolumeLiveOutput(String(button.dataset.highVolumeResumeTab || ''));
  const bind = typeof bindPressable === 'function'
    ? bindPressable
    : (typeof globalThis.bindPressable === 'function' ? globalThis.bindPressable : null);
  if (typeof bind === 'function') {
    bind(button, { onActivate, refocusComposer: false });
    return;
  }
  button.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    onActivate();
  });
}

function _activateOutputCommandChip(command) {
  const activate = typeof activateFaqCommandChip === 'function'
    ? activateFaqCommandChip
    : typeof globalThis.activateFaqCommandChip === 'function'
    ? globalThis.activateFaqCommandChip
    : null;
  if (typeof activate === 'function') activate(command);
}

function _appendOutputCommandChip(content, command, label = '') {
  const chip = document.createElement('span');
  chip.className = 'allowed-chip faq-chip chip chip-action';
  chip.tabIndex = 0;
  chip.setAttribute('role', 'button');
  chip.title = 'Load this command into the prompt';
  chip.dataset.faqCommand = command;
  chip.textContent = label || command;
  chip.addEventListener('click', () => _activateOutputCommandChip(command));
  chip.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    e.preventDefault();
    _activateOutputCommandChip(command);
  });
  content.appendChild(chip);
}

function _appendOutputInlineText(content, text) {
  const parts = String(text || '').split(/(`[^`]+`)/g);
  parts.forEach((part) => {
    if (!part) return;
    if (part.length >= 2 && part.startsWith('`') && part.endsWith('`')) {
      const code = document.createElement('span');
      code.className = 'builtin-inline-code';
      code.textContent = part.slice(1, -1);
      content.appendChild(code);
      return;
    }
    content.appendChild(document.createTextNode(part));
  });
}

function _appendBuiltinMarkerRow(content, marker, text, textClass = '') {
  const markerEl = document.createElement('span');
  markerEl.className = 'builtin-row-marker';
  markerEl.textContent = marker;
  const textEl = document.createElement('span');
  textEl.className = ['builtin-row-text', textClass].filter(Boolean).join(' ');
  _appendOutputInlineText(textEl, text);
  content.append(markerEl, textEl);
}

function _appendBuiltinCommandCell(content, command) {
  const value = String(command || '').trim();
  const commandEl = document.createElement('span');
  commandEl.className = 'builtin-help-label';
  commandEl.textContent = value;
  content.appendChild(commandEl);
}

function _splitBuiltinHelpRow(value) {
  const columnMatch = value.match(/^(.+?)\s{2,}(.+)$/);
  if (columnMatch) return [columnMatch[1].trim(), columnMatch[2].trim()];
  const dashMatch = value.match(/^(.+?)\s+-\s+(.+)$/);
  if (dashMatch) return [dashMatch[1].trim(), dashMatch[2].trim()];
  return null;
}

function _appendStructuredBuiltinHelpRow(content, text) {
  const value = String(text || '').trim();
  if (!value) return false;
  const split = _splitBuiltinHelpRow(value);
  if (!split) {
    _appendOutputInlineText(content, value);
    return true;
  }
  const [command, description] = split;
  _appendBuiltinCommandCell(content, command);
  const desc = document.createElement('span');
  desc.className = 'builtin-help-description';
  _appendOutputInlineText(desc, description);
  content.appendChild(desc);
  return true;
}

function _appendStructuredBuiltinLine(content, text, cls) {
  const classes = String(cls || '').split(/\s+/).filter(Boolean);
  if (classes.includes('builtin-faq-q')) {
    _appendBuiltinMarkerRow(content, 'Q', String(text || '').replace(/^Q\s+/, ''), 'builtin-faq-question-text');
    return true;
  }
  if (classes.includes('builtin-faq-a')) {
    _appendBuiltinMarkerRow(content, 'A', String(text || '').replace(/^A\s+/, ''), 'builtin-faq-answer-text');
    return true;
  }
  if (classes.includes('builtin-plain')) {
    _appendOutputInlineText(content, text);
    return true;
  }
  if (classes.includes('builtin-table-header') || classes.includes('builtin-table-row')) {
    _appendOutputInlineText(content, text);
    return true;
  }
  if (classes.includes('builtin-help-row') || classes.includes('builtin-catalog-item')) {
    return _appendStructuredBuiltinHelpRow(content, text);
  }
  return false;
}

function _isBuiltinNoteLine(cls) {
  return String(cls || '').split(/\s+/).filter(Boolean).includes('builtin-note');
}

function _buildOutputLine(event, tabId, now, runStart, metadata = null) {
  const text = String(event && event.text || '');
  const cls = _legacyClsForLineEvent(event);
  const span = document.createElement('span');
  span.className = 'line' + (cls ? ' ' + cls : '');
  if (text === '' && !_isPromptEchoLineEvent(event)) span.classList.add('is-blank');
  const coalesceRole = _coalescedOutputRoleForEvent(event);
  if (event && event.role) span.dataset.outputRole = String(event.role || '');
  const content = document.createElement('span');
  content.className = 'line-content';

  const tsC = new Date(now).toTimeString().slice(0, 8);
  span.dataset.tsC = tsC;
  if (runStart) {
    span.dataset.tsE = '+' + ((now - runStart) / 1000).toFixed(1) + 's';
  } else {
    span.dataset.tsE = '+0.0s';
  }

  let rawTextForStorage = text;
  if (_isPromptEchoLineEvent(event)) {
    const prefix = _outputPromptPrefix();
    const prefixEl = document.createElement('span');
    prefixEl.className = 'prompt-prefix';
    prefixEl.textContent = prefix;
    content.appendChild(prefixEl);
    if (text) content.appendChild(document.createTextNode(text));
    rawTextForStorage = `${prefix}${text ? ' ' + text : ''}`;
  } else if (metadata && metadata.high_volume_resume) {
    content.appendChild(document.createTextNode(text));
    content.appendChild(document.createTextNode(' '));
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn-ghost btn-compact high-volume-output-resume';
    button.dataset.highVolumeResumeTab = String(tabId || '');
    button.textContent = 'Resume live rendering';
    button.title = 'Render new output lines live again';
    _bindHighVolumeOutputResumeButton(button);
    content.appendChild(button);
  } else if (metadata && typeof metadata.faq_command === 'string' && metadata.faq_command.trim()) {
    _appendOutputCommandChip(content, metadata.faq_command.trim(), String(text || '').trim());
  } else if (_isBuiltinNoteLine(cls)) {
    _renderAnsiWithEntityTokens(content, String(text || ''), [], tabId);
  } else if (_appendStructuredBuiltinLine(content, text, cls)) {
    // Rendered above from stable builtin output classes.
  } else if (_isPlainOutputLineEvent(event)) {
    content.textContent = text;
  } else {
    _renderAnsiWithEntityTokens(content, String(text || ''), _normalizeOutputEntities(metadata && metadata.entities), tabId);
  }
  span.appendChild(content);

  const rawLine = {
    ..._lineEventLegacyPayload({ ...event, text: rawTextForStorage, ts_clock: tsC, ts_elapsed: span.dataset.tsE || '' }),
    tsC,
    tsE: span.dataset.tsE || '',
  };
  _applyOutputSignalMetadata(span, rawLine, metadata);

  return { span, rawLine, coalesceRole };
}

function _appendOutputSpan(out, span) {
  const prompt = (typeof shellPromptWrap !== 'undefined' && shellPromptWrap && shellPromptWrap.parentElement === out)
    ? shellPromptWrap
    : null;
  if (prompt) out.insertBefore(span, prompt);
  else out.appendChild(span);
}

function _stickOutputToBottom(out, tab) {
  if (!out) return;
  if (tab) {
    tab._outputFollowToken = (tab._outputFollowToken || 0) + 1;
    tab.suppressOutputScrollTracking = true;
  }
  out.scrollTop = out.scrollHeight;
  if (tab) {
    const token = tab._outputFollowToken;
    // 16ms follow-up re-sticks the bottom once layout (fonts, images,
    // prompt mount) has settled. If the user or a caller flipped
    // followOutput to false during that window (e.g. scrolled up to read
    // earlier output) we must not yank them back — their scroll intent
    // wins over our layout-settle retry.
    setTimeout(() => {
      const live = getTab(tab.id);
      if (!live || live._outputFollowToken !== token) return;
      if (live.followOutput !== false) {
        out.scrollTop = out.scrollHeight;
      }
      live.suppressOutputScrollTracking = false;
    }, 16);
  }
}

function _restoreOutputTailAfterLayout(out, tab) {
  if (!out) return;
  const token = tab ? (tab._outputFollowToken || 0) + 1 : 0;
  if (tab) {
    tab._outputFollowToken = token;
    tab.followOutput = true;
    tab.suppressOutputScrollTracking = true;
  }

  const stick = (final = false) => {
    const live = tab ? getTab(tab.id) : null;
    if (tab && (!live || live._outputFollowToken !== token)) return;
    if (live && Date.now() <= Number(live.outputUserScrollUntil || 0)) {
      live.followOutput = false;
      live.suppressOutputScrollTracking = false;
      if (typeof updateOutputFollowButton === 'function') updateOutputFollowButton(live.id);
      return;
    }
    if (!live || live.followOutput !== false) {
      out.scrollTop = out.scrollHeight;
    }
    if (final && live) {
      live.suppressOutputScrollTracking = false;
      if (typeof updateOutputFollowButton === 'function') updateOutputFollowButton(live.id);
    }
  };

  stick(false);
  _OUTPUT_RESTORE_TAIL_DELAYS.forEach((delay, index) => {
    setTimeout(() => stick(index === _OUTPUT_RESTORE_TAIL_DELAYS.length - 1), delay);
  });
}

function _isMobileTerminalMode() {
  return !!(
    typeof document !== 'undefined'
    && document.body
    && document.body.classList
    && document.body.classList.contains('mobile-terminal-mode')
  );
}

function _followOutputAfterAppend(out, tab, { afterLargeBatch = false } = {}) {
  if (!out || !tab || tab.followOutput === false) return;
  if (afterLargeBatch && _isMobileTerminalMode()) {
    _restoreOutputTailAfterLayout(out, tab);
    return;
  }
  setTimeout(() => _stickOutputToBottom(out, tab), 0);
}

function _syncTabRawLines(tab, rawLine) {
  if (!tab || !rawLine) return;
  if (!Array.isArray(tab.rawLines)) tab.rawLines = [];
  tab.rawLines.push(rawLine);
  _adjustTabOutputSignalCounts(tab, rawLine, 1);
  const max = APP_CONFIG.max_output_lines;
  if (max > 0 && tab.rawLines.length > max) {
    const removed = tab.rawLines.length - max;
    const removedLines = tab.rawLines.splice(0, removed);
    removedLines.forEach(line => _adjustTabOutputSignalCounts(tab, line, -1));
    if (typeof tab.currentRunStartIndex === 'number' && tab.currentRunStartIndex >= 0) {
      tab.currentRunStartIndex = Math.max(0, tab.currentRunStartIndex - removed);
    }
  }
}

function _appendRestoredOutputSpan(out, rawLine, tabId) {
  const span = document.createElement('span');
  const event = _lineEventFromWire(rawLine || {});
  const cls = _legacyClsForLineEvent(event);
  const coalesceRole = _coalescedOutputRoleForEvent(event);
  span.className = 'line' + (cls ? ' ' + cls : '');
  if (String(event && event.text || '') === '') span.classList.add('is-blank');
  if (event && event.role) span.dataset.outputRole = String(event.role || '');
  span.dataset.tsC = String(rawLine && rawLine.tsC || '');
  if (rawLine && rawLine.tsE) span.dataset.tsE = String(rawLine.tsE);
  if (Number.isInteger(rawLine && rawLine.line_number)) span.dataset.lineNumber = String(rawLine.line_number);
  _applyOutputSignalMetadata(span, {}, rawLine);

  const content = document.createElement('span');
  content.className = 'line-content';
  const text = String(event && event.text || '');

  if (_isPromptEchoLineEvent(event)) {
    const prefix = _outputPromptPrefix();
    const prefixEl = document.createElement('span');
    prefixEl.className = 'prompt-prefix';
    prefixEl.textContent = prefix;
    content.appendChild(prefixEl);

    const bodyText = stripPromptLabelFromEchoText(text);
    if (bodyText) content.appendChild(document.createTextNode(bodyText));
  } else if (_isBuiltinNoteLine(cls)) {
    _renderAnsiWithEntityTokens(content, text, [], tabId);
  } else if (_appendStructuredBuiltinLine(content, text, cls)) {
    // Rendered above from stable builtin output classes.
  } else if (_isPlainOutputLineEvent(event)) {
    content.textContent = text;
  } else {
    _renderAnsiWithEntityTokens(content, text, _normalizeOutputEntities(rawLine && rawLine.entities), tabId);
  }
  span.appendChild(content);
  if (!coalesceRole || !_replaceLastRenderedLineIfCoalescible(out, { span, coalesceRole })) {
    _appendOutputSpan(out, span);
  }
}

function renderRestoredTabOutput(tabId, rawLines) {
  const out = getOutput(tabId);
  const tab = getTab(tabId);
  if (!out || !tab) return;
  const lines = Array.isArray(rawLines) ? rawLines.map(line => ({
    text: String(line && line.text || ''),
    cls: String(line && line.cls || ''),
    kind: String(line && line.kind || ''),
    role: String(line && line.role || ''),
    tsC: String(line && line.tsC || ''),
    tsE: String(line && line.tsE || ''),
    signals: _normalizeOutputSignals(line && line.signals),
    line_index: Number.isInteger(line && line.line_index) ? line.line_index : undefined,
    line_number: Number.isInteger(line && line.line_number) ? line.line_number : undefined,
    command_root: String(line && line.command_root || ''),
    target: String(line && line.target || ''),
    entities: _normalizeOutputEntities(line && line.entities),
  })) : [];
  out.innerHTML = '';
  resetAnsiRendererForTab(tabId);
  tab.rawLines = lines;
  _resetTabOutputSignalCounts(tab, lines);
  lines.forEach(line => _appendRestoredOutputSpan(out, line, tabId));
  syncOutputPrefixes(out);
  if (lines.length) {
    tab.followOutput = true;
    if (_isMobileTerminalMode()) _stickOutputToBottom(out, tab);
    else _restoreOutputTailAfterLayout(out, tab);
  }
  if (typeof updateOutputFollowButton === 'function') updateOutputFollowButton(tabId);
  if (tabId === activeTabId && typeof refreshSearchDiscoverabilityUi === 'function') {
    if (typeof isSearchBarOpen === 'function' && isSearchBarOpen()) runSearch();
    else if (typeof scheduleSearchDiscoverabilityRefresh === 'function') scheduleSearchDiscoverabilityRefresh();
    else refreshSearchDiscoverabilityUi();
  }
}

function _flushPendingOutputBatch(tabId) {
  const state = _pendingOutputBatches.get(tabId);
  if (!state) return;
  state.scheduled = false;
  state.handle = null;

  const out = getOutput(tabId);
  const tab = getTab(tabId);
  if (!out || !tab) {
    _cancelPendingOutputBatch(tabId);
    return;
  }

  const shouldStickToBottom = tab.followOutput !== false;
  const fragment = document.createDocumentFragment();
  const pendingItemCount = state.items.length;
  const wasLargeBurst = state.burstCount >= _OUTPUT_SYNC_BURST_LIMIT || pendingItemCount > 1;
  const batch = state.items.splice(0, _OUTPUT_BATCH_SIZE);
  const rawBatch = state.rawLines.splice(0, _OUTPUT_BATCH_SIZE);
  const mountBatch = batch.slice();
  mountBatch.forEach((entry, index) => {
    const replacementLineNumber = index === 0 ? _coalescedReplacementLineNumber(out, entry) : 0;
    const lineNumber = replacementLineNumber || _assignOutputLineNumber(out, tab, entry.span);
    if (replacementLineNumber > 0) entry.span.dataset.lineNumber = String(replacementLineNumber);
    if (lineNumber > 0) entry.rawLine.line_number = lineNumber;
  });
  mountBatch.forEach(entry => {
    entry.span.dataset.prefix = _isPrefixExcludedLine(entry.span) ? '' : _lineTimestampPrefix(entry.span);
  });
  if (mountBatch.length && _replaceLastRenderedLineIfCoalescible(out, mountBatch[0])) {
    mountBatch.shift();
  }
  mountBatch.forEach(entry => {
    fragment.appendChild(entry.span);
  });
  if (mountBatch.length) _appendOutputSpan(out, fragment);
  rawBatch.forEach(rawLine => _syncTabRawLines(tab, rawLine));

  if (mountBatch.length) _trimOutputToMaxLines(out);

  if (batch.length) _syncOutputPrefixesForAppend(out);
  if (shouldStickToBottom) {
    _followOutputAfterAppend(out, tab, { afterLargeBatch: wasLargeBurst || batch.length > 1 });
  }
  if (typeof updateOutputFollowButton === 'function') updateOutputFollowButton(tabId);
  if (tabId === activeTabId && typeof refreshSearchDiscoverabilityUi === 'function') {
    if (typeof isSearchBarOpen === 'function' && isSearchBarOpen()) runSearch();
    else if (typeof scheduleSearchDiscoverabilityRefresh === 'function') scheduleSearchDiscoverabilityRefresh();
    else refreshSearchDiscoverabilityUi();
  }

  if (state.items.length > 0 || state.rawLines.length > 0) {
    _schedulePendingOutputFlush(tabId);
    return;
  }

  state.burstCount = 0;
  _maybeMountDeferredPrompt(tabId);
}

function _refreshFollowingOutputsAfterLayout() {
  if (!Array.isArray(tabs)) return;
  tabs.forEach(tab => {
    if (!tab || tab.followOutput === false) return;
    const out = getOutput(tab.id);
    if (!out) return;
    setTimeout(() => _restoreOutputTailAfterLayout(out, tab), 16);
  });
}

function _maybeMountDeferredPrompt(tabId) {
  const tab = getTab(tabId);
  if (!tab || !tab.deferPromptMount || tab.st === 'running') return;
  if (typeof _tabSessionRestoreInProgress !== 'undefined' && _tabSessionRestoreInProgress) return;
  const state = _pendingOutputBatches.get(tabId);
  if (state && (state.scheduled || state.items.length > 0 || state.rawLines.length > 0)) return;
  tab.deferPromptMount = false;
  if (tabId === activeTabId && typeof mountShellPrompt === 'function') {
    mountShellPrompt(tabId, true);
  }
}

function syncOutputPrefixes(scope = document) {
  const isElement = scope && typeof scope.querySelectorAll === 'function';
  const looksLikeOutput = scope === document
    || (isElement && (
      scope.classList?.contains?.('output')
      || scope.querySelector?.('.line')
      || scope.querySelector?.('#shell-prompt-wrap')
    ));
  const outputs = scope === document
    ? [...document.querySelectorAll('.output')]
    : (looksLikeOutput ? [scope] : [...(scope?.querySelectorAll?.('.output') || [])]);

  outputs.forEach(out => _syncOutputLinePrefixMetadata(out, _tabForOutput(out)));
}

function _setLnMode(mode) {
  lnMode = mode;
  document.body.classList.toggle('ln-on', mode === 'on');
  const label = mode === 'on' ? 'line numbers: on' : 'line numbers: off';
  const lnBtn = document.getElementById('ln-btn');
  if (lnBtn) {
    lnBtn.textContent = label;
    lnBtn.classList.toggle('active', mode === 'on');
  }
  syncOutputPrefixes();
  try {
    _refreshFollowingOutputsAfterLayout();
  } catch (_) {}
}

function _setTsMode(mode) {
  tsMode = mode;
  document.body.classList.remove('ts-elapsed', 'ts-clock');
  if (mode === 'elapsed') document.body.classList.add('ts-elapsed');
  if (mode === 'clock') document.body.classList.add('ts-clock');
  syncOutputPrefixes();
  try {
    _refreshFollowingOutputsAfterLayout();
  } catch (_) {}
}

_setLnMode('off');

// Append a line of output to a tab's output panel.
// Stores raw text (with original ANSI codes) in tab.rawLines for permalink and
// HTML export — ansi_up processes codes into HTML spans, so we capture them
// before rendering. Each line also receives data-ts-e (elapsed) and data-ts-c
// (clock) attributes used by the CSS ::before timestamp display.
function appendLine(text, cls, tabId, metadata = null) {
  const normalized = _normalizeAppendLineArgs(text, cls, tabId, metadata);
  const { event } = normalized;
  const id = normalized.tabId || activeTabId;
  const out = getOutput(id);
  if (!out) return;

  const tab = getTab(id);
  const now = Date.now();
  const runStart = tab?.runStart || 0;
  if (_shouldSkipLiveOutputRender(tab, normalized.metadata)) {
    _flushPendingOutputBeforeHighVolumeSkip(id);
    const state = _ensureHighVolumeOutputState(tab);
    const rawLine = _rawOutputLine(event, id, now, runStart, normalized.metadata);
    _assignRawOutputLineNumber(out, tab, rawLine);
    _syncTabRawLines(tab, rawLine);
    if (state) {
      state.skippedLines += 1;
      _appendHighVolumeOutputNotice(id, state, { force: state.skippedLines === 1 });
    }
    return;
  }
  const state = _getPendingOutputBatch(id);
  const shouldBatch = state.scheduled || state.items.length > 0 || state.burstCount >= _OUTPUT_SYNC_BURST_LIMIT;
  const entry = _buildOutputLine(event, id, now, runStart, normalized.metadata);
  const { span, rawLine } = entry;
  if (!shouldBatch) {
    const replacementLineNumber = _coalescedReplacementLineNumber(out, entry);
    const lineNumber = replacementLineNumber || _assignOutputLineNumber(out, tab, span);
    if (replacementLineNumber > 0) span.dataset.lineNumber = String(replacementLineNumber);
    if (lineNumber > 0) rawLine.line_number = lineNumber;
  }

  if (shouldBatch) {
    _queuePendingOutputEntry(state, entry);
    state.rawLines.push(rawLine);
    _schedulePendingOutputFlush(id);
    return;
  }

  state.burstCount += 1;

  const replacedCoalescedLine = _replaceLastRenderedLineIfCoalescible(out, entry);
  if (!replacedCoalescedLine) _appendOutputSpan(out, span);

  // Enforce max output lines — drop oldest lines from the top.
  if (!replacedCoalescedLine) _trimOutputToMaxLines(out);

  _syncOutputPrefixesForAppend(out, span);
  _followOutputAfterAppend(out, tab);
  if (typeof updateOutputFollowButton === 'function') updateOutputFollowButton(id);
  _syncTabRawLines(tab, rawLine);
  if (id === activeTabId && typeof refreshSearchDiscoverabilityUi === 'function') {
    if (typeof isSearchBarOpen === 'function' && isSearchBarOpen()) runSearch();
    else if (typeof scheduleSearchDiscoverabilityRefresh === 'function') scheduleSearchDiscoverabilityRefresh();
    else refreshSearchDiscoverabilityUi();
  }
}

function _normalizeAppendLinesEntry(entry) {
  if (entry && typeof entry === 'object') return _normalizeLineEventInput(entry, '', entry.metadata || null);
  return _normalizeLineEventInput(String(entry ?? ''), '', null);
}

function appendLines(lines, tabId) {
  const id = tabId || activeTabId;
  const out = getOutput(id);
  const tab = getTab(id);
  const sourceLines = Array.isArray(lines) ? lines : [];
  if (!out || !sourceLines.length) return Promise.resolve();

  let index = 0;
  return new Promise((resolve) => {
    const queueChunk = () => {
      const state = _getPendingOutputBatch(id);
      const now = Date.now();
      const runStart = tab?.runStart || 0;
      const end = Math.min(index + _OUTPUT_APPEND_LINES_CHUNK_SIZE, sourceLines.length);
      for (; index < end; index += 1) {
        const entry = _normalizeAppendLinesEntry(sourceLines[index]);
        if (_shouldSkipLiveOutputRender(tab, entry.metadata)) {
          const state = _ensureHighVolumeOutputState(tab);
          const rawLine = _rawOutputLine(entry.event, id, now, runStart, entry.metadata);
          _assignRawOutputLineNumber(out, tab, rawLine);
          _syncTabRawLines(tab, rawLine);
          if (state) {
            state.skippedLines += 1;
            _appendHighVolumeOutputNotice(id, state, { force: state.skippedLines === 1 });
          }
          continue;
        }
        const outputEntry = _buildOutputLine(entry.event, id, now, runStart, entry.metadata);
        _queuePendingOutputEntry(state, outputEntry);
        state.rawLines.push(outputEntry.rawLine);
      }
      state.burstCount = Math.max(state.burstCount, _OUTPUT_SYNC_BURST_LIMIT);
      _schedulePendingOutputFlush(id);
      if (index < sourceLines.length) {
        setTimeout(queueChunk, 0);
        return;
      }
      resolve();
    };
    queueChunk();
  });
}
