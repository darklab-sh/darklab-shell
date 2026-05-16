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
const _pendingOutputBatches = new Map();
const _OUTPUT_SIGNAL_SCOPES = _outputCore.OUTPUT_SIGNAL_SCOPES;

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

function _getPendingOutputBatch(tabId) {
  // Output can arrive very quickly from SSE. Batch DOM writes per tab so large
  // scans do not thrash layout on every single line.
  let state = _pendingOutputBatches.get(tabId);
  if (!state) {
    state = {
      items: [],
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
  return !!(state && (state.scheduled || state.items.length > 0));
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
  const signals = _normalizeOutputSignals(metadata.signals);
  if (signals.length) {
    rawLine.signals = signals;
    span.dataset.signals = signals.join(',');
  }
  if (Number.isInteger(metadata.line_index)) {
    rawLine.line_index = metadata.line_index;
    span.dataset.lineIndex = String(metadata.line_index);
  }
  if (Number.isInteger(metadata.line_number)) {
    rawLine.line_number = metadata.line_number;
    span.dataset.lineNumber = String(metadata.line_number);
  }
  if (typeof metadata.command_root === 'string' && metadata.command_root) {
    rawLine.command_root = metadata.command_root;
    span.dataset.commandRoot = metadata.command_root;
  }
  if (typeof metadata.target === 'string' && metadata.target) {
    rawLine.target = metadata.target;
    span.dataset.signalTarget = metadata.target;
  }
  const entities = _normalizeOutputEntities(metadata.entities);
  if (entities.length) {
    rawLine.entities = entities;
    span.dataset.entities = JSON.stringify(entities);
  }
}

function _atlasTabForOutputEntity(type) {
  const value = String(type || '').trim().toLowerCase();
  if (value === 'ip') return 'ip';
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
  const value = String(entity && entity.value || '').trim();
  const canonical = _outputEntityValue(entity);
  const candidates = [];
  if (Number.isInteger(entity && entity.start) && Number.isInteger(entity && entity.end)) {
    candidates.push({ start: entity.start, end: entity.end });
  }
  [value, canonical].filter(Boolean).forEach(needle => {
    const index = String(text || '').indexOf(needle);
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
  const token = document.createElement('button');
  token.type = 'button';
  token.className = 'chip chip-action atlas-entity-token';
  token.dataset.atlasEntityType = String(entity && entity.type || '');
  token.dataset.atlasEntityValue = _outputEntityValue(entity);
  token.dataset.atlasEntityTab = _atlasTabForOutputEntity(entity && entity.type);
  token.title = `Open ${token.dataset.atlasEntityValue} in Atlas`;
  token.setAttribute('aria-label', token.title);
  token.innerHTML = _getAnsiRendererForTab(tabId).ansi_to_html(text);
  return token;
}

function _renderAnsiWithEntityTokens(content, text, entities, tabId) {
  const ranges = _outputEntityRanges(text, entities);
  if (!ranges.length) {
    content.innerHTML = _getAnsiRendererForTab(tabId).ansi_to_html(text);
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

function _closeOutputEntityMenu() {
  if (_outputEntityMenu) {
    _outputEntityMenu.remove();
    _outputEntityMenu = null;
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
  document.body.appendChild(menu);
  const rect = menu.getBoundingClientRect();
  const left = Math.max(8, Math.min(x, window.innerWidth - rect.width - 8));
  const top = Math.max(8, Math.min(y, window.innerHeight - rect.height - 8));
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
  _outputEntityMenu = menu;
}

let _outputEntityLongPressTimer = null;

function _bindOutputEntityTokenEvents() {
  if (typeof document === 'undefined' || document._darklabOutputEntityTokensBound) return;
  document._darklabOutputEntityTokensBound = true;
  document.addEventListener('click', (event) => {
    const token = event.target && event.target.closest ? event.target.closest('.atlas-entity-token') : null;
    if (token) {
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
    if (event.key === 'Escape') _closeOutputEntityMenu();
  });
}

_bindOutputEntityTokenEvents();

function _activateOutputCommandChip(command) {
  const activate = typeof globalThis.activateFaqCommandChip === 'function'
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

function _buildOutputLine(text, cls, tabId, now, runStart, metadata = null) {
  const span = document.createElement('span');
  span.className = 'line' + (cls ? ' ' + cls : '');
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
  if (cls === 'prompt-echo') {
    const prefix = _outputPromptPrefix();
    const prefixEl = document.createElement('span');
    prefixEl.className = 'prompt-prefix';
    prefixEl.textContent = prefix;
    content.appendChild(prefixEl);
    if (text) content.appendChild(document.createTextNode(text));
    rawTextForStorage = `${prefix}${text ? ' ' + text : ''}`;
  } else if (cls === 'exit-ok' || cls === 'exit-fail' || cls === 'denied' || cls === 'notice') {
    content.textContent = text;
  } else if (metadata && typeof metadata.faq_command === 'string' && metadata.faq_command.trim()) {
    _appendOutputCommandChip(content, metadata.faq_command.trim(), String(text || '').trim());
  } else {
    _renderAnsiWithEntityTokens(content, String(text || ''), _normalizeOutputEntities(metadata && metadata.entities), tabId);
  }
  span.appendChild(content);

  const rawLine = { text: rawTextForStorage, cls: cls || '', tsC, tsE: span.dataset.tsE || '' };
  _applyOutputSignalMetadata(span, rawLine, metadata);

  return { span, rawLine };
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
  const cls = rawLine && typeof rawLine.cls === 'string' ? rawLine.cls : '';
  span.className = 'line' + (cls ? ' ' + cls : '');
  span.dataset.tsC = String(rawLine && rawLine.tsC || '');
  if (rawLine && rawLine.tsE) span.dataset.tsE = String(rawLine.tsE);
  if (Number.isInteger(rawLine && rawLine.line_number)) span.dataset.lineNumber = String(rawLine.line_number);
  _applyOutputSignalMetadata(span, {}, rawLine);

  const content = document.createElement('span');
  content.className = 'line-content';
  const text = String(rawLine && rawLine.text || '');

  if (cls === 'prompt-echo') {
    const prefix = _outputPromptPrefix();
    const prefixEl = document.createElement('span');
    prefixEl.className = 'prompt-prefix';
    prefixEl.textContent = prefix;
    content.appendChild(prefixEl);

    const bodyText = stripPromptLabelFromEchoText(text);
    if (bodyText) content.appendChild(document.createTextNode(bodyText));
  } else if (cls === 'notice' || cls === 'denied' || cls === 'exit-ok' || cls === 'exit-fail') {
    content.textContent = text;
  } else {
    _renderAnsiWithEntityTokens(content, text, _normalizeOutputEntities(rawLine && rawLine.entities), tabId);
  }
  span.appendChild(content);
  _appendOutputSpan(out, span);
}

function renderRestoredTabOutput(tabId, rawLines) {
  const out = getOutput(tabId);
  const tab = getTab(tabId);
  if (!out || !tab) return;
  const lines = Array.isArray(rawLines) ? rawLines.map(line => ({
    text: String(line && line.text || ''),
    cls: String(line && line.cls || ''),
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
  const wasLargeBurst = state.burstCount >= _OUTPUT_SYNC_BURST_LIMIT || state.items.length > 1;
  const batch = state.items.splice(0, _OUTPUT_BATCH_SIZE);
  batch.forEach(entry => {
    entry.span.dataset.prefix = _isPrefixExcludedLine(entry.span) ? '' : _lineTimestampPrefix(entry.span);
    fragment.appendChild(entry.span);
    _syncTabRawLines(tab, entry.rawLine);
  });
  _appendOutputSpan(out, fragment);

  _trimOutputToMaxLines(out);

  _syncOutputPrefixesForAppend(out);
  if (shouldStickToBottom) {
    _followOutputAfterAppend(out, tab, { afterLargeBatch: wasLargeBurst || batch.length > 1 });
  }
  if (typeof updateOutputFollowButton === 'function') updateOutputFollowButton(tabId);
  if (tabId === activeTabId && typeof refreshSearchDiscoverabilityUi === 'function') {
    if (typeof isSearchBarOpen === 'function' && isSearchBarOpen()) runSearch();
    else if (typeof scheduleSearchDiscoverabilityRefresh === 'function') scheduleSearchDiscoverabilityRefresh();
    else refreshSearchDiscoverabilityUi();
  }

  if (state.items.length > 0) {
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
  if (state && (state.scheduled || state.items.length > 0)) return;
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
  const id = tabId || activeTabId;
  const out = getOutput(id);
  if (!out) return;

  const tab = getTab(id);
  const now = Date.now();
  const runStart = tab?.runStart || 0;
  const state = _getPendingOutputBatch(id);
  const shouldBatch = state.scheduled || state.items.length > 0 || state.burstCount >= _OUTPUT_SYNC_BURST_LIMIT;
  const { span, rawLine } = _buildOutputLine(text, cls, id, now, runStart, metadata);
  const lineNumber = _assignOutputLineNumber(out, tab, span);
  if (lineNumber > 0) rawLine.line_number = lineNumber;

  if (shouldBatch) {
    state.items.push({ span, rawLine });
    _schedulePendingOutputFlush(id);
    return;
  }

  state.burstCount += 1;

  _appendOutputSpan(out, span);

  // Enforce max output lines — drop oldest lines from the top.
  _trimOutputToMaxLines(out);

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
  if (entry && typeof entry === 'object') {
    return {
      text: String(entry.text ?? ''),
      cls: String(entry.cls || ''),
      metadata: entry.metadata && typeof entry.metadata === 'object' ? entry.metadata : entry,
    };
  }
  return { text: String(entry ?? ''), cls: '', metadata: null };
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
        const { span, rawLine } = _buildOutputLine(entry.text, entry.cls, id, now, runStart, entry.metadata);
        const lineNumber = _assignOutputLineNumber(out, tab, span);
        if (lineNumber > 0) rawLine.line_number = lineNumber;
        state.items.push({ span, rawLine });
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
