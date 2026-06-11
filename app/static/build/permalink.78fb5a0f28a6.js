;
/* /static/js/core/utils.js */
// ── Shared utility module ──

function escapeHtml(t) {
  return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function normalizeRedactionRules(rules) {
  if (!Array.isArray(rules)) return [];
  return rules
    .filter(rule => rule && typeof rule === 'object')
    .map(rule => {
      const pattern = typeof rule.pattern === 'string' ? rule.pattern : '';
      if (!pattern.trim()) return null;
      const replacement = typeof rule.replacement === 'string' ? rule.replacement : '[redacted]';
      const flags = typeof rule.flags === 'string'
        ? Array.from(new Set(rule.flags.toLowerCase().split('').filter(ch => ch === 'i' || ch === 'm'))).join('')
        : '';
      try {
        return {
          label: typeof rule.label === 'string' ? rule.label.trim() : '',
          pattern,
          replacement,
          flags,
          regex: new RegExp(pattern, `g${flags}`),
        };
      } catch (_) {
        return null;
      }
    })
    .filter(Boolean);
}

function applyRedactionRules(text, rules) {
  let value = String(text ?? '');
  for (const rule of normalizeRedactionRules(rules)) {
    value = value.replace(rule.regex, rule.replacement);
  }
  return value;
}

function redactLineEntries(entries, rules) {
  return (Array.isArray(entries) ? entries : [])
    .map(item => {
      if (typeof item === 'string') return applyRedactionRules(item, rules);
      if (!item || typeof item !== 'object' || typeof item.text !== 'string') return null;
      return {
        ...item,
        text: applyRedactionRules(item.text, rules),
      };
    })
    .filter(Boolean);
}

var RAW_ONLY_INTEL_PLACEHOLDER = 'Intel data omitted from share';

function _isRawOnlyIntelEntry(item) {
  return !!(item && typeof item === 'object' && String(item.command_root || '').trim().toLowerCase() === 'intel');
}

function _rawOnlyPlaceholderEntry(source = {}) {
  const entry = {
    text: RAW_ONLY_INTEL_PLACEHOLDER,
    cls: 'notice',
    raw_only: true,
    command_root: 'intel',
  };
  if (typeof source.tsC === 'string') entry.tsC = source.tsC;
  if (typeof source.tsE === 'string') entry.tsE = source.tsE;
  if (Number.isInteger(source.line_number)) entry.line_number = source.line_number;
  return entry;
}

function omitRawOnlyLineEntries(entries) {
  const omitted = [];
  let inIntelGroup = false;
  for (const item of Array.isArray(entries) ? entries : []) {
    if (_isRawOnlyIntelEntry(item)) {
      if (!inIntelGroup) {
        omitted.push(_rawOnlyPlaceholderEntry(item));
        inIntelGroup = true;
      }
      continue;
    }
    inIntelGroup = false;
    if (typeof item === 'string') omitted.push(item);
    else if (item && typeof item === 'object') omitted.push({ ...item });
  }
  return omitted;
}

// Render a small Markdown subset for MOTD: **bold**, `code`, [text](url), newlines.
// escapeHtml is applied first to prevent XSS, then patterns are applied so the
// operator notice stays useful without needing a full Markdown parser.
function renderMotd(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/\n/g, '<br>');
}

function _copyTextFallback(text) {
  return new Promise((resolve, reject) => {
    if (typeof document === 'undefined' || !document.body) {
      reject(new Error('Clipboard is not available'));
      return;
    }
    const textarea = document.createElement('textarea');
    textarea.value = String(text);
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.top = '-9999px';
    textarea.style.left = '-9999px';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    let copied = false;
    try {
      copied = typeof document.execCommand === 'function' && document.execCommand('copy');
    } catch (_) {
      copied = false;
    }
    textarea.remove();
    if (copied) resolve(true);
    else reject(new Error('Copy command failed'));
  });
}

async function copyTextToClipboard(text) {
  const value = String(text ?? '');
  if (!value) throw new Error('Cannot copy empty text');
  if (typeof navigator !== 'undefined' && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch (_) {
      // Fall through to the legacy copy command fallback below.
    }
  }
  return _copyTextFallback(value);
}

function downloadBlobAsAttachment(blob, filename, options = {}) {
  const opts = options && typeof options === 'object' ? options : {};
  const { revokeDelayMs = 2000, container = null } = opts;
  if (typeof URL === 'undefined' || typeof URL.createObjectURL !== 'function') {
    throw new Error('Blob downloads are not available');
  }
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename || 'download';
  const parent = container && typeof container.appendChild === 'function' ? container : document.body;
  parent.appendChild(anchor);
  anchor.click();
  anchor.remove();

  if (typeof URL.revokeObjectURL !== 'function') return;
  let revoked = false;
  const revoke = () => {
    if (revoked) return;
    revoked = true;
    URL.revokeObjectURL(url);
  };
  if (typeof window !== 'undefined' && typeof window.setTimeout === 'function') {
    window.setTimeout(revoke, revokeDelayMs);
  } else if (typeof setTimeout === 'function') {
    setTimeout(revoke, revokeDelayMs);
  }
  if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
    window.addEventListener('pagehide', revoke, { once: true });
  }
}

function downloadUrlAsAttachment(url, options = {}) {
  const href = String(url || '').trim();
  if (!href) throw new Error('Download URL is required');
  const opts = options && typeof options === 'object' ? options : {};
  const anchor = document.createElement('a');
  anchor.href = href;
  if (opts.filename) anchor.download = String(opts.filename);
  anchor.rel = 'noopener';
  const parent = opts.container && typeof opts.container.appendChild === 'function'
    ? opts.container
    : document.body;
  parent.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

async function shareUrl(url) {
  // navigator.share requires a user gesture and a secure context (HTTPS).
  // Because shareUrl is always called from inside a fetch .then() callback
  // (creating the snapshot), the transient activation has already expired by
  // the time we get here — a direct navigator.share() call will always fail
  // with NotAllowedError. Instead we always copy to clipboard first (reliable),
  // then surface a share button in the toast so the user can open the native
  // share sheet with a fresh gesture from that tap.
  const canShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function';
  try {
    await copyTextToClipboard(url);
  } catch (_) {
    // Clipboard unavailable — surface the URL in a native prompt as last resort.
    if (typeof window !== 'undefined' && typeof window.prompt === 'function') {
      window.prompt('Copy the link:', url);
    }
    return;
  }
  if (canShare) {
    showToast('Link copied to clipboard', 'success', {
      label: 'share ↗',
      onClick: () => { navigator.share({ url }).catch(() => {}); },
    });
  } else {
    showToast('Link copied to clipboard');
  }
}

function showToast(msg, tone = 'success', action = null) {
  // Toasts are transient UI feedback only; avoid stacking timers by resetting
  // the hide timer whenever a new message reuses the same element.
  const toast = document.getElementById('permalink-toast');
  const isError = tone === 'error' || /^(failed|unable|error|\[.*error\])/i.test(String(msg || ''));
  toast.classList.remove('toast-has-action');
  toast.textContent = msg;
  if (action && action.label && typeof action.onClick === 'function') {
    const btn = document.createElement('button');
    btn.className = 'toast-action-btn';
    btn.textContent = action.label;
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      toast.classList.remove('show');
      toast.classList.remove('toast-has-action');
      action.onClick();
    }, { once: true });
    toast.classList.add('toast-has-action');
    toast.appendChild(btn);
  }
  toast.classList.toggle('toast-error', isError);
  toast.classList.toggle('toast-success', !isError);
  toast.classList.add('show');
  setTimeout(() => {
    toast.classList.remove('show');
    toast.classList.remove('toast-has-action');
  }, action ? 5000 : 2500);
}
;
;
/* /static/js/core/run_output_model.js */
var DarklabRunOutputModel = (function (global) {
  'use strict';

  const LINE_EVENT_SCHEMA_VERSION = 1;
  const LINE_KIND_VALUES = Object.freeze(['info', 'notice', 'warn', 'error']);
  const LINE_ROLE_VALUES = Object.freeze([
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
  ]);
  const LINE_SIGNAL_VALUES = Object.freeze(['findings', 'warnings', 'errors', 'summaries']);
  const LINE_NOISE_KIND_VALUES = Object.freeze(['progress', 'status', 'boilerplate']);

  const LineKind = Object.freeze({
    INFO: 'info',
    NOTICE: 'notice',
    WARN: 'warn',
    ERROR: 'error',
  });

  const LineRole = Object.freeze({
    BODY: 'body',
    PROMPT_ECHO: 'prompt-echo',
    SECTION_HEADER: 'section-header',
    KV: 'kv',
    HELP_ROW: 'help-row',
    PTY_MARKER: 'pty-marker',
    PROGRESS: 'progress',
    STATUS_LINE: 'status-line',
    SUCCESS: 'success',
    DENIED: 'denied',
    EXIT_OK: 'exit-ok',
    EXIT_FAIL: 'exit-fail',
  });

  const LineSignal = Object.freeze({
    FINDINGS: 'findings',
    WARNINGS: 'warnings',
    ERRORS: 'errors',
    SUMMARIES: 'summaries',
  });

  const LineNoiseKind = Object.freeze({
    PROGRESS: 'progress',
    STATUS: 'status',
    BOILERPLATE: 'boilerplate',
  });

  const LEGACY_KIND_BY_CLS = Object.freeze({
    '': LineKind.INFO,
    output: LineKind.INFO,
    out: LineKind.INFO,
    cmd: LineKind.INFO,
    notice: LineKind.NOTICE,
    'builtin-note': LineKind.NOTICE,
    'welcome-output': LineKind.NOTICE,
    warn: LineKind.WARN,
    warning: LineKind.WARN,
    error: LineKind.ERROR,
  });

  const LEGACY_ROLE_BY_CLS = Object.freeze({
    '': LineRole.BODY,
    output: LineRole.BODY,
    out: LineRole.BODY,
    notice: LineRole.BODY,
    warn: LineRole.BODY,
    warning: LineRole.BODY,
    error: LineRole.BODY,
    'builtin-note': LineRole.BODY,
    'builtin-spacer': LineRole.BODY,
    'welcome-output': LineRole.BODY,
    cmd: LineRole.PROMPT_ECHO,
    'prompt-echo': LineRole.PROMPT_ECHO,
    'builtin-section': LineRole.SECTION_HEADER,
    'builtin-kv': LineRole.KV,
    'builtin-help-row': LineRole.HELP_ROW,
    'builtin-faq-q': LineRole.HELP_ROW,
    'builtin-faq-a': LineRole.HELP_ROW,
    'pty-marker': LineRole.PTY_MARKER,
    progress: LineRole.PROGRESS,
    'status-line': LineRole.STATUS_LINE,
    'builtin-success': LineRole.SUCCESS,
    denied: LineRole.DENIED,
    'exit-ok': LineRole.EXIT_OK,
    'exit-fail': LineRole.EXIT_FAIL,
  });

  const KIND_LEGACY_CLS = Object.freeze({
    info: '',
    notice: 'notice',
    warn: 'warn',
    error: 'error',
  });

  const ROLE_LEGACY_CLS = Object.freeze({
    body: '',
    'prompt-echo': 'prompt-echo',
    'section-header': 'builtin-section',
    kv: 'builtin-kv',
    'help-row': 'builtin-help-row',
    'pty-marker': 'pty-marker',
    progress: 'progress',
    'status-line': 'status-line',
    success: 'builtin-success',
    denied: 'denied',
    'exit-ok': 'exit-ok',
    'exit-fail': 'exit-fail',
  });

  const NOISE_KIND_BY_ROLE = Object.freeze({
    progress: LineNoiseKind.PROGRESS,
    'status-line': LineNoiseKind.STATUS,
  });

  function legacyClsTokens(value) {
    const text = String(value || '').trim();
    if (!text) return [''];
    return text.split(/\s+/).filter(Boolean);
  }

  function legacyClsToKind(value) {
    const tokens = legacyClsTokens(value);
    for (const token of tokens) {
      if (Object.prototype.hasOwnProperty.call(LEGACY_KIND_BY_CLS, token)) return LEGACY_KIND_BY_CLS[token];
    }
    return LineKind.INFO;
  }

  function legacyClsToRole(value) {
    const tokens = legacyClsTokens(value);
    for (const token of tokens) {
      if (Object.prototype.hasOwnProperty.call(LEGACY_ROLE_BY_CLS, token)) return LEGACY_ROLE_BY_CLS[token];
    }
    return LineRole.BODY;
  }

  function collectUnknown(unknownCollector, family, value) {
    if (typeof unknownCollector === 'function') unknownCollector(family, String(value));
  }

  function enumValue(values, value, fallback, family, unknownCollector) {
    if (value === undefined || value === null || value === '') return fallback;
    const stringValue = String(value);
    if (values.includes(stringValue)) return stringValue;
    collectUnknown(unknownCollector, family, stringValue);
    return fallback;
  }

  function optionalInt(value) {
    if (value === undefined || value === null || typeof value === 'boolean') return null;
    const parsed = Number.parseInt(String(value), 10);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function entityFromWire(payload) {
    if (!payload || typeof payload !== 'object') return null;
    const type = String(payload.type || '').trim();
    const canonicalValue = String(payload.canonical_value || '').trim();
    if (!type || !canonicalValue) return null;
    let start = optionalInt(payload.start);
    let end = optionalInt(payload.end);
    if (start === null || end === null) {
      start = null;
      end = null;
    }
    return {
      type,
      value: String(payload.value || '').trim() || canonicalValue,
      canonical_value: canonicalValue,
      confidence: String(payload.confidence || '').trim() || 'medium',
      source_line: optionalInt(payload.source_line),
      start,
      end,
    };
  }

  function entityToWire(entity) {
    const payload = {
      type: entity.type,
      value: entity.value,
      canonical_value: entity.canonical_value,
      confidence: entity.confidence,
    };
    if (entity.source_line !== null && entity.source_line !== undefined) payload.source_line = entity.source_line;
    if (entity.start !== null && entity.start !== undefined) payload.start = entity.start;
    if (entity.end !== null && entity.end !== undefined) payload.end = entity.end;
    return payload;
  }

  function signalsFromWire(value, unknownCollector) {
    if (!Array.isArray(value)) return [];
    const signals = [];
    value.forEach((item) => {
      const signal = String(item);
      if (LINE_SIGNAL_VALUES.includes(signal)) {
        signals.push(signal);
      } else {
        collectUnknown(unknownCollector, 'signal', signal);
      }
    });
    return signals;
  }

  function entitiesFromWire(value) {
    if (!Array.isArray(value)) return [];
    return value.map(entityFromWire).filter(Boolean);
  }

  function legacyClsForEvent(event) {
    if (event.legacy_cls) return String(event.legacy_cls);
    const role = event.role || LineRole.BODY;
    if (role !== LineRole.BODY) return ROLE_LEGACY_CLS[role] || '';
    return KIND_LEGACY_CLS[event.kind || LineKind.INFO] || '';
  }

  function noiseKindForRole(role) {
    return NOISE_KIND_BY_ROLE[role] || null;
  }

  function noiseKindForEvent(event) {
    if (!event || (Array.isArray(event.signals) && event.signals.length)) return null;
    if (event.kind === LineKind.WARN || event.kind === LineKind.ERROR) return null;
    if (event.noise_kind) return event.noise_kind;
    return noiseKindForRole(event.role || LineRole.BODY);
  }

  function isNoiseLineEvent(event) {
    return noiseKindForEvent(event) !== null;
  }

  function legacyPayload(event) {
    const payload = {
      text: String(event.text || ''),
      cls: legacyClsForEvent(event),
      tsC: String(event.ts_clock || event.tsC || ''),
      tsE: String(event.ts_elapsed || event.tsE || ''),
    };
    if (Array.isArray(event.signals) && event.signals.length) payload.signals = event.signals.slice();
    if (event.line_index !== null && event.line_index !== undefined) payload.line_index = event.line_index;
    if (event.command_root) payload.command_root = String(event.command_root);
    if (event.target) payload.target = String(event.target);
    if (Array.isArray(event.entities) && event.entities.length) payload.entities = event.entities.map(entityToWire);
    const noiseKind = noiseKindForEvent(event);
    if (noiseKind) {
      payload.noise_kind = noiseKind;
      if (event.noise_reason) payload.noise_reason = String(event.noise_reason);
    }
    return payload;
  }

  function fromWireLineEvent(payload, unknownCollector) {
    const item = payload && typeof payload === 'object' ? payload : {};
    const clsValue = item.cls || '';
    const kind = enumValue(LINE_KIND_VALUES, item.kind, legacyClsToKind(clsValue), 'kind', unknownCollector);
    const role = enumValue(LINE_ROLE_VALUES, item.role, legacyClsToRole(clsValue), 'role', unknownCollector);
    const noiseKind = enumValue(
      LINE_NOISE_KIND_VALUES,
      item.noise_kind,
      noiseKindForRole(role),
      'noise_kind',
      unknownCollector,
    );
    return {
      text: String(item.text || ''),
      kind,
      role,
      legacy_cls: String(clsValue || ''),
      ts_clock: String(item.tsC || ''),
      ts_elapsed: String(item.tsE || ''),
      signals: signalsFromWire(item.signals, unknownCollector),
      line_index: optionalInt(item.line_index),
      command_root: String(item.command_root || ''),
      target: String(item.target || ''),
      entities: entitiesFromWire(item.entities),
      noise_kind: noiseKind,
      noise_reason: noiseKind ? String(item.noise_reason || '') : '',
    };
  }

  function toLegacyWireLineEvent(event) {
    return legacyPayload(event || {});
  }

  function toWireLineEvent(event) {
    const payload = legacyPayload(event || {});
    payload.v = LINE_EVENT_SCHEMA_VERSION;
    payload.kind = (event && event.kind) || LineKind.INFO;
    payload.role = (event && event.role) || LineRole.BODY;
    return payload;
  }

  function eventSearchText(event) {
    return String((event && event.text) || '');
  }

  const api = Object.freeze({
    LINE_EVENT_SCHEMA_VERSION,
    LINE_KIND_VALUES,
    LINE_NOISE_KIND_VALUES,
    LINE_ROLE_VALUES,
    LINE_SIGNAL_VALUES,
    LineKind,
    LineNoiseKind,
    LineRole,
    LineSignal,
    eventSearchText,
    fromWireLineEvent,
    isNoiseLineEvent,
    legacyClsToKind,
    legacyClsToRole,
    noiseKindForEvent,
    noiseKindForRole,
    toLegacyWireLineEvent,
    toWireLineEvent,
  });

  global.DarklabRunOutputModel = api;
  return api;
})(typeof window !== 'undefined' ? window : globalThis);
;
;
/* /static/js/core/output_core.js */
// ── Output pure helpers ──────────────────────────────────────────────────
// Loaded before output.js. DOM writes and batching stay in output.js; prompt
// label, prefix, and signal-count transforms live here.
var DarklabOutputCore = (function (global) {
  const OUTPUT_SIGNAL_SCOPES = Object.freeze(['findings', 'warnings', 'errors', 'summaries']);
  const OUTPUT_SIGNAL_SUMMARY_CLASSES = Object.freeze([
    'builtin-signal-summary-header',
    'builtin-signal-summary-section',
    'builtin-signal-summary-row',
    'builtin-signal-summary-note',
    'builtin-signal-summary-sep',
  ]);
  const OUTPUT_COMMAND_OUTCOME_SUMMARY_CLASSES = Object.freeze([
    'command-outcome-summary',
    'command-outcome-summary-title',
    'command-outcome-summary-row',
    'command-outcome-summary-note',
  ]);
  const OUTPUT_SYNTHETIC_SUMMARY_CLASSES = Object.freeze([
    ...OUTPUT_SIGNAL_SUMMARY_CLASSES,
    ...OUTPUT_COMMAND_OUTCOME_SUMMARY_CLASSES,
  ]);

  function promptIdentityPrefix(rawPrefix = '') {
    let prefix = String(rawPrefix || '').trim() || 'anon@darklab';
    if (prefix.endsWith('$')) prefix = prefix.slice(0, -1).trimEnd();
    prefix = prefix.replace(/:[^\s:]+$/, '').trim() || 'anon@darklab';
    return prefix;
  }

  function promptIdentityFromParts(username = '', domain = '') {
    const cleanUsername = String(username || '').trim() || 'anon';
    const cleanDomain = String(domain || '').trim() || 'darklab.sh';
    return `${cleanUsername}@${cleanDomain}`;
  }

  function normalizeWorkspaceCwd(rawPath = '') {
    return String(rawPath || '').split('/').map(part => String(part || '').trim()).filter(Boolean).join('/');
  }

  function workspaceDisplayPath(path = '') {
    const normalized = normalizeWorkspaceCwd(path);
    return normalized ? `/${normalized}` : '/';
  }

  function buildPromptLabel(rawPrefix = '', path = '~') {
    return `${promptIdentityPrefix(rawPrefix)}:${String(path || '~')} $`;
  }

  function buildPromptLabelFromParts(username = '', domain = '', path = '~') {
    return `${promptIdentityFromParts(username, domain)}:${String(path || '~')} $`;
  }

  function _escapeRegex(text) {
    return String(text || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function stripPromptLabelFromEchoText(text = '', currentLabel = '', identityPrefix = '') {
    const value = String(text || '');
    const current = String(currentLabel || '');
    if (current && value.startsWith(current)) return value.slice(current.length).replace(/^\s+/, '');
    const identity = promptIdentityPrefix(identityPrefix);
    const legacyPattern = new RegExp(`^${_escapeRegex(identity)}:[^\\s]+\\$\\s*`);
    if (legacyPattern.test(value)) return value.replace(legacyPattern, '');
    const promptShapedPattern = /^[^\s:]+@[^\s:]+:[^\s]+\$\s*/;
    if (promptShapedPattern.test(value)) return value.replace(promptShapedPattern, '');
    if (value === '$') return '';
    if (value.startsWith('$ ')) return value.slice(2);
    return value;
  }

  function formatOutputPrefix(index, tsText, includeTimestamp, lineMode, timestampMode) {
    const parts = [];
    if (lineMode === 'on') parts.push(String(index));
    if (includeTimestamp && tsText && (timestampMode === 'elapsed' || timestampMode === 'clock')) {
      parts.push(tsText);
    }
    return parts.join(' ');
  }

  function emptySignalCounts() {
    return { findings: 0, warnings: 0, errors: 0, summaries: 0 };
  }

  function isSignalSummaryClassName(cls) {
    return OUTPUT_SIGNAL_SUMMARY_CLASSES.includes(cls);
  }

  function isSyntheticSummaryClassName(cls) {
    return OUTPUT_SYNTHETIC_SUMMARY_CLASSES.includes(cls);
  }

  function _normalizeOutcomeItem(item) {
    if (item == null) return null;
    if (typeof item === 'string' || typeof item === 'number' || typeof item === 'boolean') {
      const value = String(item).trim();
      return value ? { value } : null;
    }
    if (typeof item !== 'object') return null;
    const label = String(item.label || item.key || '').trim();
    const value = String(item.value || item.text || item.summary || '').trim();
    const tone = String(item.tone || '').trim();
    if (!label && !value) return null;
    return {
      ...(label ? { label } : {}),
      value,
      ...(tone ? { tone } : {}),
    };
  }

  function normalizeCommandOutcomeSummary(raw) {
    if (!raw) return null;
    if (typeof raw === 'string' || typeof raw === 'number' || typeof raw === 'boolean') {
      const value = String(raw).trim();
      if (!value) return null;
      return {
        kind: 'command_outcome',
        title: 'Command outcome',
        items: [{ value }],
      };
    }
    if (typeof raw !== 'object') return null;
    const title = String(raw.title || raw.heading || 'Command outcome').trim() || 'Command outcome';
    const sourceItems = Array.isArray(raw.items)
      ? raw.items
      : Array.isArray(raw.lines)
      ? raw.lines
      : Array.isArray(raw.summary)
      ? raw.summary
      : [];
    const items = sourceItems.map(_normalizeOutcomeItem).filter(Boolean);
    if (!items.length && typeof raw.text === 'string' && raw.text.trim()) {
      items.push({ value: raw.text.trim() });
    }
    if (!items.length) return null;
    return {
      kind: 'command_outcome',
      title,
      items,
    };
  }

  function _plainOutcomeLineText(line) {
    return String(line && typeof line === 'object' ? line.text || '' : line || '')
      .replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, '')
      .trimEnd();
  }

  function _outcomeCommandRoot(command = '') {
    return String(command || '').trim().split(/\s+/, 1)[0].toLowerCase();
  }

  function _outcomeLines(lines) {
    const model = window.DarklabRunOutputModel || null;
    return (Array.isArray(lines) ? lines : [])
      .filter(line => line && typeof line === 'object')
      .filter(line => {
        const role = String(line.role || '').trim();
        const cls = String(line.cls || '').split(/\s+/).filter(Boolean);
        if (role === 'prompt-echo' || role === 'exit-ok' || role === 'exit-fail') return false;
        if (cls.includes('prompt-echo') || cls.includes('exit-ok') || cls.includes('exit-fail')) return false;
        if (model && typeof model.isNoiseLineEvent === 'function') {
          try {
            if (model.isNoiseLineEvent(model.fromWireLineEvent(line))) return false;
          } catch (_) {
            // Fall through to class-based filtering when older payloads surprise the decoder.
          }
        }
        return !cls.some(name => isSyntheticSummaryClassName(name));
      })
      .map(_plainOutcomeLineText)
      .filter(Boolean);
  }

  function _formatLimitedList(values, limit = 8) {
    const unique = Array.from(new Set(values.map(value => String(value || '').trim()).filter(Boolean)));
    if (unique.length <= limit) return unique.join(', ');
    return `${unique.slice(0, limit).join(', ')} and ${unique.length - limit} more`;
  }

  function _pushOutcomeItem(items, label, value) {
    const text = String(value || '').trim();
    if (text) items.push({ label, value: text });
  }

  function _parseNmapOutcome(lines) {
    const openPorts = [];
    const osHints = [];
    let hostsUp = '';
    lines.forEach(line => {
      const portMatch = line.match(/^\s*(\d{1,5}\/(?:tcp|udp))\s+open\S*\s+([^\s]+)?\s*(.*)$/i);
      if (portMatch) {
        const port = portMatch[1].toLowerCase();
        const service = String(portMatch[2] || '').trim();
        const version = String(portMatch[3] || '').replace(/\s+/g, ' ').trim();
        openPorts.push([port, service, version].filter(Boolean).join(' '));
        return;
      }
      const doneMatch = line.match(/Nmap done:\s+.*\((\d+)\s+hosts?\s+up\)/i);
      if (doneMatch) hostsUp = `${Number(doneMatch[1]).toLocaleString()} up`;
      const serviceInfo = line.match(/Service Info:\s*(.+)$/i);
      if (serviceInfo) osHints.push(serviceInfo[1].replace(/\s+/g, ' ').trim());
      const osDetails = line.match(/(?:OS details|Running):\s*(.+)$/i);
      if (osDetails) osHints.push(osDetails[1].replace(/\s+/g, ' ').trim());
    });
    const items = [];
    _pushOutcomeItem(items, 'Hosts', hostsUp);
    _pushOutcomeItem(items, 'Open ports', openPorts.length ? `${openPorts.length.toLocaleString()} (${_formatLimitedList(openPorts, 10)})` : '');
    _pushOutcomeItem(items, 'OS / service hints', _formatLimitedList(osHints, 3));
    return items.length ? { title: 'Command outcome', items } : null;
  }

  function _parseDigOutcome(lines) {
    const recordTypes = [];
    const answerRecords = [];
    let status = '';
    let answerCount = null;
    let server = '';
    let queryTime = '';
    let inAnswer = false;
    lines.forEach(line => {
      const statusMatch = line.match(/HEADER<<-[^,]*,\s*status:\s*([A-Z0-9_-]+)/i);
      if (statusMatch) status = statusMatch[1].toUpperCase();
      const answerMatch = line.match(/\bANSWER:\s*(\d+)/i);
      if (answerMatch) answerCount = Number(answerMatch[1]);
      if (/^;;\s*ANSWER SECTION:/i.test(line)) {
        inAnswer = true;
        return;
      }
      if (/^;;\s*(AUTHORITY|ADDITIONAL|QUESTION) SECTION:/i.test(line)) inAnswer = false;
      if (inAnswer && !line.startsWith(';')) {
        const parts = line.trim().split(/\s+/);
        const inIndex = parts.findIndex(part => part.toUpperCase() === 'IN');
        if (inIndex >= 0 && parts[inIndex + 1]) {
          const owner = String(parts[0] || '').replace(/\.$/, '');
          const recordType = parts[inIndex + 1].toUpperCase();
          const value = parts.slice(inIndex + 2).join(' ').trim();
          recordTypes.push(recordType);
          if (owner && recordType && value) answerRecords.push(`${owner} ${recordType} ${value}`);
        }
      }
      const serverMatch = line.match(/^;;\s*SERVER:\s*(.+)$/i);
      if (serverMatch) server = serverMatch[1].trim();
      const timeMatch = line.match(/^;;\s*Query time:\s*(.+)$/i);
      if (timeMatch) queryTime = timeMatch[1].trim();
    });
    const items = [];
    _pushOutcomeItem(items, 'Status', status);
    _pushOutcomeItem(items, 'Answers', answerCount == null ? '' : String(answerCount));
    _pushOutcomeItem(items, 'Answer records', _formatLimitedList(answerRecords, 4));
    _pushOutcomeItem(items, 'Record types', _formatLimitedList(recordTypes, 6));
    _pushOutcomeItem(items, 'Resolver', server);
    _pushOutcomeItem(items, 'Query time', queryTime);
    return items.length ? { title: 'Command outcome', items } : null;
  }

  function _cleanNslookupName(value) {
    return String(value || '').trim().replace(/\.$/, '');
  }

  function _parseNslookupOutcome(lines) {
    const aRecords = [];
    const mxRecords = [];
    const txtRecords = [];
    const recordTypes = [];
    let resolver = '';
    let currentName = '';
    let inAnswer = false;
    lines.forEach(line => {
      const serverMatch = line.match(/^Server:\s*(.+)$/i);
      if (serverMatch) {
        resolver = serverMatch[1].trim();
        return;
      }
      const resolverAddressMatch = line.match(/^Address:\s*(.+)$/i);
      if (!inAnswer && resolverAddressMatch) {
        const address = resolverAddressMatch[1].trim();
        resolver = resolver ? `${resolver} (${address})` : address;
        return;
      }
      if (/^Non-authoritative answer:/i.test(line)) {
        inAnswer = true;
        return;
      }
      if (/^Authoritative answers can be found from:/i.test(line)) {
        inAnswer = false;
        return;
      }
      const nameMatch = line.match(/^Name:\s*(.+)$/i);
      if (nameMatch) {
        currentName = _cleanNslookupName(nameMatch[1]);
        return;
      }
      const addressMatch = line.match(/^Address:\s*(.+)$/i);
      if (inAnswer && currentName && addressMatch) {
        recordTypes.push('A');
        aRecords.push(`${currentName} A ${addressMatch[1].trim()}`);
        return;
      }
      const mxMatch = line.match(/^(\S+)\s+mail exchanger\s*=\s*(.+)$/i);
      if (mxMatch) {
        recordTypes.push('MX');
        mxRecords.push(`${_cleanNslookupName(mxMatch[1])} MX ${mxMatch[2].trim().replace(/\.$/, '')}`);
        return;
      }
      const txtMatch = line.match(/^(\S+)\s+text\s*=\s*(.+)$/i);
      if (txtMatch) {
        recordTypes.push('TXT');
        txtRecords.push(`${_cleanNslookupName(txtMatch[1])} TXT ${txtMatch[2].trim().replace(/^"|"$/g, '')}`);
      }
    });
    const answerCount = aRecords.length + mxRecords.length + txtRecords.length;
    const items = [];
    _pushOutcomeItem(items, 'Answers', answerCount ? String(answerCount) : '');
    _pushOutcomeItem(items, 'A records', _formatLimitedList(aRecords, 4));
    _pushOutcomeItem(items, 'MX records', _formatLimitedList(mxRecords, 4));
    _pushOutcomeItem(items, 'TXT records', _formatLimitedList(txtRecords, 3));
    _pushOutcomeItem(items, 'Record types', _formatLimitedList(recordTypes, 6));
    _pushOutcomeItem(items, 'Resolver', resolver);
    return items.length ? { title: 'Command outcome', items } : null;
  }

  function _parseCurlOutcome(lines) {
    const statuses = [];
    let contentType = '';
    let contentLength = '';
    let finalUrl = '';
    let tlsHint = '';
    lines.forEach(line => {
      const statusMatch = line.match(/^\s*<*\s*HTTP\/(?:\d(?:\.\d)?|2|3)\s+(\d{3})(?:\s+(.+))?$/i);
      if (statusMatch) statuses.push(`${statusMatch[1]}${statusMatch[2] ? ` ${statusMatch[2].trim()}` : ''}`);
      const typeMatch = line.match(/^\s*<*\s*content-type:\s*(.+)$/i);
      if (typeMatch) contentType = typeMatch[1].trim();
      const lengthMatch = line.match(/^\s*<*\s*content-length:\s*(.+)$/i);
      if (lengthMatch) contentLength = lengthMatch[1].trim();
      const locationMatch = line.match(/^\s*<*\s*location:\s*(.+)$/i);
      if (locationMatch) finalUrl = locationMatch[1].trim();
      if (/SSL certificate problem|certificate verify failed|TLS.*alert|Failed to connect|Could not resolve host/i.test(line)) {
        tlsHint = line.replace(/^\s*curl:\s*/i, '').replace(/\s+/g, ' ').trim();
      }
    });
    const items = [];
    _pushOutcomeItem(items, 'Final status', statuses.length ? statuses[statuses.length - 1] : '');
    _pushOutcomeItem(items, 'Redirects', statuses.length > 1 ? String(statuses.length - 1) : '');
    _pushOutcomeItem(items, 'Final URL', finalUrl);
    _pushOutcomeItem(items, 'Content type', contentType);
    _pushOutcomeItem(items, 'Content length', contentLength);
    _pushOutcomeItem(items, 'Connection / TLS', tlsHint);
    return items.length ? { title: 'Command outcome', items } : null;
  }

  function _parseOpenSslOutcome(command, lines) {
    if (!/\bs_client\b/i.test(command)) return null;
    let subject = '';
    let issuer = '';
    let notBefore = '';
    let notAfter = '';
    let verify = '';
    let protocol = '';
    let cipher = '';
    lines.forEach(line => {
      const subjectMatch = line.match(/^subject=\s*(.+)$/i);
      if (subjectMatch) subject = subjectMatch[1].trim();
      const issuerMatch = line.match(/^issuer=\s*(.+)$/i);
      if (issuerMatch) issuer = issuerMatch[1].trim();
      const beforeMatch = line.match(/^(?:notBefore|Not Before)\s*=\s*(.+)$/i);
      if (beforeMatch) notBefore = beforeMatch[1].trim();
      const afterMatch = line.match(/^(?:notAfter|Not After)\s*=\s*(.+)$/i);
      if (afterMatch) notAfter = afterMatch[1].trim();
      const verifyMatch = line.match(/Verify return code:\s*(.+)$/i);
      if (verifyMatch) verify = verifyMatch[1].trim();
      const protocolMatch = line.match(/^\s*Protocol\s*:\s*(.+)$/i);
      if (protocolMatch) protocol = protocolMatch[1].trim();
      const cipherMatch = line.match(/^\s*Cipher\s*:\s*(.+)$/i) || line.match(/^\s*New,\s*([^,]+),\s*Cipher is\s+(.+)$/i);
      if (cipherMatch) {
        if (!protocol && cipherMatch.length > 2) protocol = cipherMatch[1].trim();
        cipher = (cipherMatch.length > 2 ? cipherMatch[2] : cipherMatch[1]).trim();
      }
    });
    const items = [];
    _pushOutcomeItem(items, 'Subject', subject);
    _pushOutcomeItem(items, 'Issuer', issuer);
    _pushOutcomeItem(items, 'Validity', [notBefore, notAfter].filter(Boolean).join(' to '));
    _pushOutcomeItem(items, 'Verification', verify);
    _pushOutcomeItem(items, 'Protocol', protocol);
    _pushOutcomeItem(items, 'Cipher', cipher);
    return items.length ? { title: 'Command outcome', items } : null;
  }

  function buildCommandOutcomeSummary(command = '', rawLines = []) {
    const root = _outcomeCommandRoot(command);
    const lines = _outcomeLines(rawLines);
    if (!root || !lines.length) return null;
    try {
      if (root === 'nmap') return normalizeCommandOutcomeSummary(_parseNmapOutcome(lines));
      if (root === 'dig') return normalizeCommandOutcomeSummary(_parseDigOutcome(lines));
      if (root === 'nslookup') return normalizeCommandOutcomeSummary(_parseNslookupOutcome(lines));
      if (root === 'curl') return normalizeCommandOutcomeSummary(_parseCurlOutcome(lines));
      if (root === 'openssl') return normalizeCommandOutcomeSummary(_parseOpenSslOutcome(command, lines));
    } catch (_) {
      return null;
    }
    return null;
  }

  function lineHasClass(rawLine, className) {
    const cls = String(rawLine?.cls || '');
    return cls.split(/\s+/).filter(Boolean).includes(className);
  }

  function lineRole(rawLine) {
    const model = window.DarklabRunOutputModel || null;
    if (model && typeof model.fromWireLineEvent === 'function') {
      return String(model.fromWireLineEvent(rawLine || {}).role || 'body');
    }
    return lineHasClass(rawLine, 'prompt-echo') ? 'prompt-echo' : 'body';
  }

  function isSignalCountableLine(rawLine) {
    if (!rawLine || lineRole(rawLine) === 'prompt-echo') return false;
    const classes = String(rawLine.cls || '').split(/\s+/).filter(Boolean);
    return !classes.some(cls => isSyntheticSummaryClassName(cls));
  }

  function isBuiltinCommandRoot(root, builtinRoots = []) {
    return !!root && Array.isArray(builtinRoots) && builtinRoots.includes(root);
  }

  function normalizeSignals(signals) {
    return Array.isArray(signals)
      ? signals.map(signal => String(signal || '')).filter(Boolean)
      : [];
  }

  function normalizeEntities(entities) {
    if (!Array.isArray(entities)) return [];
    return entities.map(entity => {
      if (!entity || typeof entity !== 'object') return null;
      const type = String(entity.type || '').trim();
      const canonicalValue = String(entity.canonical_value || '').trim();
      if (!type || !canonicalValue) return null;
      const normalized = {
        type,
        value: String(entity.value || canonicalValue).trim() || canonicalValue,
        canonical_value: canonicalValue,
        confidence: String(entity.confidence || 'medium').trim() || 'medium',
      };
      if (Number.isInteger(entity.source_line)) normalized.source_line = entity.source_line;
      if (Number.isInteger(entity.start) && Number.isInteger(entity.end)) {
        normalized.start = entity.start;
        normalized.end = entity.end;
      }
      return normalized;
    }).filter(Boolean);
  }

  function countableSignalScopes(rawLine, builtinRoots = []) {
    if (!isSignalCountableLine(rawLine)) return [];
    const commandRoot = String(rawLine?.command_root || '').trim();
    if (isBuiltinCommandRoot(commandRoot, builtinRoots)) return [];
    const signals = normalizeSignals(rawLine?.signals);
    if (!signals.length) return [];
    const uniqueScopes = new Set(signals.filter(scope => OUTPUT_SIGNAL_SCOPES.includes(scope)));
    return Array.from(uniqueScopes);
  }

  const api = Object.freeze({
    OUTPUT_COMMAND_OUTCOME_SUMMARY_CLASSES,
    OUTPUT_SIGNAL_SCOPES,
    buildCommandOutcomeSummary,
    buildPromptLabel,
    buildPromptLabelFromParts,
    countableSignalScopes,
    emptySignalCounts,
    formatOutputPrefix,
    isBuiltinCommandRoot,
    isSignalCountableLine,
    isSignalSummaryClassName,
    isSyntheticSummaryClassName,
    lineHasClass,
    normalizeCommandOutcomeSummary,
    normalizeEntities,
    normalizeSignals,
    normalizeWorkspaceCwd,
    promptIdentityFromParts,
    promptIdentityPrefix,
    stripPromptLabelFromEchoText,
    workspaceDisplayPath,
  });
  global.DarklabOutputCore = api;
  return api;
})(typeof window !== 'undefined' ? window : globalThis);
;
;
/* /static/js/export_html.js */
// ── Shared HTML export helpers ───────────────────────────────────────────────
// Single source of truth for all export formatting (save html, save pdf,
// permalink save html). All callers go through these helpers so the rendered
// output is consistent across every save surface.
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
    '--terminal-font-size',
    '--terminal-line-height',
  ];
  function runOutputModel() {
    return window.DarklabRunOutputModel || null;
  }

  function fallbackLineEvent(line) {
    const cls = String(line && line.cls || '');
    return {
      text: String(line && line.text || ''),
      cls,
      kind: String(line && line.kind || (cls === 'notice' ? 'notice' : 'info')),
      role: String(line && line.role || (['prompt-echo', 'denied', 'exit-ok', 'exit-fail'].includes(cls) ? cls : 'body')),
      tsC: String(line && line.tsC || ''),
      tsE: String(line && line.tsE || ''),
      signals: Array.isArray(line && line.signals) ? line.signals.map(signal => String(signal || '')).filter(Boolean) : [],
      entities: Array.isArray(line && line.entities) ? line.entities : [],
      line_number: Number.isInteger(line && line.line_number) ? line.line_number : undefined,
    };
  }

  function lineEventFromWire(line) {
    const model = runOutputModel();
    if (model && typeof model.fromWireLineEvent === 'function') {
      const event = model.fromWireLineEvent(line || {});
      event.cls = lineLegacyClass(event);
      event.tsC = event.ts_clock || '';
      event.tsE = event.ts_elapsed || '';
      event.signals = Array.isArray(event.signals) ? event.signals : [];
      event.entities = Array.isArray(event.entities) ? event.entities : [];
      if (Number.isInteger(line && line.line_number)) event.line_number = line.line_number;
      return event;
    }
    return fallbackLineEvent(line || {});
  }

  function lineLegacyClass(event) {
    const model = runOutputModel();
    if (model && typeof model.toLegacyWireLineEvent === 'function') {
      return String(model.toLegacyWireLineEvent(event || {}).cls || '');
    }
    return String(event && (event.legacy_cls || event.cls || (event.role !== 'body' ? event.role : event.kind !== 'info' ? event.kind : '')) || '');
  }

  function isPromptEchoEvent(event) {
    return String(event && event.role || '') === 'prompt-echo';
  }

  function isPlainEvent(event) {
    const role = String(event && event.role || 'body');
    const kind = String(event && event.kind || 'info');
    return ['exit-ok', 'exit-fail', 'denied'].includes(role) || kind === 'notice';
  }

  function escapeExportHtml(text) {
    return String(text ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function escapeExportAttr(text) {
    return escapeExportHtml(text)
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderExportPromptEcho(text) {
    const raw = String(text || '');
    const firstSpace = raw.indexOf(' ');
    const prefix = firstSpace === -1 ? raw : raw.slice(0, firstSpace);
    const remainder = firstSpace === -1 ? '' : raw.slice(firstSpace + 1);
    return '<span class="prompt-prefix">' + escapeExportHtml(prefix) + '</span>'
      + (remainder ? escapeExportHtml(' ' + remainder) : '');
  }

  function exportEntityRanges(text, entities) {
    const length = String(text || '').length;
    return (Array.isArray(entities) ? entities : [])
      .map((entity) => {
        const start = Number(entity && entity.start);
        const end = Number(entity && entity.end);
        if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start || end > length) {
          return null;
        }
        return { start, end, entity };
      })
      .filter(Boolean)
      .sort((a, b) => a.start - b.start || a.end - b.end)
      .reduce((ranges, range) => {
        const previous = ranges[ranges.length - 1];
        if (previous && range.start < previous.end) return ranges;
        ranges.push(range);
        return ranges;
      }, []);
  }

  function renderExportEntityContent(text, entities, ansiToHtml) {
    const raw = String(text || '');
    const ranges = exportEntityRanges(raw, entities);
    if (!ranges.length) return ansiToHtml(raw);
    let cursor = 0;
    let html = '';
    ranges.forEach((range) => {
      if (range.start > cursor) html += ansiToHtml(raw.slice(cursor, range.start));
      const entity = range.entity || {};
      const entityType = String(entity.type || '');
      const entityValue = String(entity.canonical_value || entity.value || raw.slice(range.start, range.end));
      const tokenText = raw.slice(range.start, range.end);
      html += '<span class="export-entity-token"'
        + ' data-entity-type="' + escapeExportAttr(entityType) + '"'
        + ' data-entity-value="' + escapeExportAttr(entityValue) + '"'
        + ' title="Entity: ' + escapeExportAttr(entityValue) + '">'
        + ansiToHtml(tokenText)
        + '</span>';
      cursor = range.end;
    });
    if (cursor < raw.length) html += ansiToHtml(raw.slice(cursor));
    return html;
  }

  function exportLineBadgeHtml(line) {
    const kind = String(line && line.kind || 'info');
    const signals = Array.isArray(line && line.signals) ? line.signals.map(String) : [];
    if (kind === 'error') return '<span class="line-severity-badge line-severity-error">error</span>';
    if (kind === 'warn') return '<span class="line-severity-badge line-severity-warn">warn</span>';
    if (signals.includes('findings')) return '<span class="line-severity-badge line-severity-finding">finding</span>';
    return '';
  }

  function buildExportLineSummary(rawLines) {
    const summary = {
      findings: 0,
      warnings: 0,
      errors: 0,
      entityTypes: {},
    };
    rawLines.forEach((rawLine) => {
      const line = lineEventFromWire(rawLine);
      const signals = Array.isArray(line.signals) ? line.signals.map(String) : [];
      if (signals.includes('findings')) summary.findings += 1;
      if (line.kind === 'warn') summary.warnings += 1;
      if (line.kind === 'error') summary.errors += 1;
      (Array.isArray(line.entities) ? line.entities : []).forEach((entity) => {
        const type = String(entity && entity.type || '').trim();
        if (type) summary.entityTypes[type] = (summary.entityTypes[type] || 0) + 1;
      });
    });
    return summary;
  }

  function buildExportSummaryHtml(summary) {
    const chips = [];
    if (summary.findings) chips.push(`findings ${summary.findings}`);
    if (summary.errors) chips.push(`errors ${summary.errors}`);
    if (summary.warnings) chips.push(`warnings ${summary.warnings}`);
    Object.entries(summary.entityTypes || {})
      .sort((a, b) => a[0].localeCompare(b[0]))
      .slice(0, 8)
      .forEach(([type, count]) => chips.push(`${type} ${count}`));
    if (!chips.length) return '';
    return '<section class="export-findings-summary">'
      + chips.map(chip => `<span>${escapeExportHtml(chip)}</span>`).join('')
      + '</section>';
  }

  function renderExportLineContent(line, ansiToHtml) {
    const lineEvent = lineEventFromWire(line);
    const text = String(lineEvent.text || '');
    let content;
    if (isPromptEchoEvent(lineEvent)) {
      content = renderExportPromptEcho(text);
    } else if (isPlainEvent(lineEvent)) {
      content = escapeExportHtml(text);
    } else {
      content = renderExportEntityContent(text, lineEvent.entities, ansiToHtml);
    }
    return exportLineBadgeHtml(lineEvent) + content;
  }

  function exportTimestamp() {
    return new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  }

  function buildExportMetaLine({ label = '', createdText = '' }) {
    const trimmedLabel = String(label || '').trim();
    const trimmedCreated = String(createdText || '').trim();
    if (trimmedLabel && trimmedCreated) return `${trimmedLabel} · ${trimmedCreated}`;
    return trimmedLabel || trimmedCreated;
  }

  function normalizeExportTranscriptLine(line) {
    if (typeof line === 'string') {
      return lineEventFromWire({ text: line });
    }
    if (line && typeof line.text === 'string') {
      return lineEventFromWire(line);
    }
    return null;
  }

  function normalizeExportTranscriptLines(lines, { stripTruncationNotices = false } = {}) {
    return (Array.isArray(lines) ? lines : [])
      .map(normalizeExportTranscriptLine)
      .filter((line) => {
        if (!line) return false;
        if (!stripTruncationNotices) return true;
        return !/^\[(?:preview|tab output) truncated/i.test(String(line.text || ''));
      });
  }

  function isCommandOutcomeSummaryLine(line) {
    const cls = String(line && line.cls || line && line.legacy_cls || '');
    return cls.split(/\s+/).includes('command-outcome-summary')
      || Boolean(line && line.command_outcome_summary === true);
  }

  function commandOutcomeItemText(item) {
    if (!item || typeof item !== 'object') return '';
    const label = String(item.label || '').trim();
    const value = String(item.value || '').trim();
    if (label && value) return `${label}: ${value}`;
    return value || label;
  }

  function buildExportCommandOutcomeSummary(command, rawLines) {
    const core = window.DarklabOutputCore || null;
    if (!core || typeof core.buildCommandOutcomeSummary !== 'function') return null;
    const normalizer = typeof core.normalizeCommandOutcomeSummary === 'function'
      ? core.normalizeCommandOutcomeSummary
      : (value) => value;
    return normalizer(core.buildCommandOutcomeSummary(command, rawLines));
  }

  function commandOutcomeSummaryToLines(summary) {
    if (!summary || !Array.isArray(summary.items) || !summary.items.length) return [];
    const lines = [];
    const title = String(summary.title || 'Command outcome').trim() || 'Command outcome';
    lines.push({
      text: title,
      cls: 'command-outcome-summary command-outcome-summary-title',
      command_outcome_summary: true,
    });
    summary.items.forEach((item) => {
      const text = commandOutcomeItemText(item);
      if (!text) return;
      lines.push({
        text,
        cls: 'command-outcome-summary command-outcome-summary-row',
        command_outcome_summary: true,
      });
    });
    return lines;
  }

  function appendCommandOutcomeSummaryLines(rawLines, { command = '', enabled = true } = {}) {
    const normalized = normalizeExportTranscriptLines(rawLines);
    if (!enabled || normalized.some(isCommandOutcomeSummaryLine)) return normalized;
    const summary = buildExportCommandOutcomeSummary(command, normalized);
    if (!summary) return normalized;
    return normalized.concat(commandOutcomeSummaryToLines(summary));
  }

  function normalizeExportRunMeta(runMeta) {
    if (!runMeta) return null;
    return {
      exitCode: runMeta.exitCode !== undefined ? runMeta.exitCode : runMeta.exit_code,
      duration: runMeta.duration || null,
      lines: runMeta.lines || null,
      version: runMeta.version || null,
    };
  }

  function buildExportDocumentModel({
    appName = '',
    title = '',
    label = '',
    createdText = '',
    runMeta = null,
    rawLines = [],
    command = '',
    includeCommandOutcomeSummary = false,
  }) {
    return {
      appName: String(appName || ''),
      title: String(title || ''),
      metaLine: buildExportMetaLine({ label, createdText }),
      runMeta: normalizeExportRunMeta(runMeta),
      rawLines: includeCommandOutcomeSummary
        ? appendCommandOutcomeSummaryLines(rawLines, { command, enabled: true })
        : normalizeExportTranscriptLines(rawLines),
    };
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

  // ── Line rendering ────────────────────────────────────────────────────────
  // Shared helper used by all save surfaces (html, pdf prep, permalink).
  // rawLines: array of { text, cls, tsC?, ... }
  // getPrefix: (line, index) => string — caller controls what goes in the gutter
  // ansiToHtml: (text) => html string — caller supplies the ansi_up instance
  // Returns { linesHtml, prefixWidth } where prefixWidth is in characters.
  function buildExportLinesHtml(rawLines, { getPrefix = () => '', ansiToHtml }) {
    const prefixes = rawLines.map((line, i) => getPrefix(line, i));
    const prefixWidth = Math.max(0, ...prefixes.map(p => p.length));
    const summary = buildExportLineSummary(rawLines);
    const linesHtml = rawLines.map((rawLine, i) => {
      const line = lineEventFromWire(rawLine);
      const cls = lineLegacyClass(line);
      const prefix = prefixes[i];
      const prefixSpan = prefix
        ? `<span class="perm-prefix">${escapeExportHtml(prefix)}</span>`
        : '';
      const content = renderExportLineContent(line, ansiToHtml);
      return `<span class="line${cls ? ' ' + cls : ''}">${prefixSpan}<span class="perm-content">${content}</span></span>`;
    }).join('');
    return { linesHtml, prefixWidth, summary, summaryHtml: buildExportSummaryHtml(summary) };
  }

  // ── Header / run-meta model ───────────────────────────────────────────────
  // Shared by permalink save html, tab save html, and PDF prep so the browser
  // surfaces and the PDF renderer all consume the same content ordering.
  function buildExportRunMetaItems(runMeta) {
    if (!runMeta) return [];
    const items = [];
    const { exitCode, duration, lines, version } = runMeta;
    if (exitCode !== null && exitCode !== undefined) {
      items.push({
        kind: 'badge',
        tone: exitCode === 0 ? 'ok' : 'fail',
        text: `exit ${exitCode}`,
      });
    }
    if (duration) items.push({ kind: 'item', text: String(duration) });
    if (lines)    items.push({ kind: 'item', text: String(lines) });
    if (version)  items.push({ kind: 'item', text: `v${version}` });
    return items;
  }

  function buildExportHeaderModel({ appName, metaLine = '', runMeta = null }) {
    return {
      appName: String(appName || ''),
      metaLine: metaLine ? String(metaLine) : '',
      runMetaItems: buildExportRunMetaItems(runMeta),
    };
  }

  function buildExportRunMetaHtml(runMetaOrItems) {
    const items = Array.isArray(runMetaOrItems)
      ? runMetaOrItems
      : buildExportRunMetaItems(runMetaOrItems);
    return items.map((item) => {
      if (item.kind === 'badge') {
        const cls = item.tone === 'ok' ? 'meta-badge-ok' : 'meta-badge-fail';
        return `<span class="meta-badge ${cls}">${escapeExportHtml(item.text)}</span>`;
      }
      return `<span class="meta-item">${escapeExportHtml(item.text)}</span>`;
    }).join('');
  }

  function buildTerminalExportHeaderHtml(headerModel, { includeHighlightToggle = false } = {}) {
    const titleHtml = `<h1 class="export-title">${escapeExportHtml(headerModel.appName)}</h1>`;
    const metaHtml = headerModel.metaLine
      ? `<div class="export-meta">${escapeExportHtml(headerModel.metaLine)}</div>`
      : '';
    const runMetaHtml = headerModel.runMetaItems.length
      ? `<div class="export-run-meta">${buildExportRunMetaHtml(headerModel.runMetaItems)}</div>`
      : '';
    const actionsHtml = includeHighlightToggle
      ? `<div class="export-header-actions">
    <button type="button" class="export-highlight-toggle" data-export-toggle-highlights aria-pressed="true">highlights: on</button>
  </div>`
      : '';
    return `<header class="export-header">
  <div class="export-header-copy">
    ${titleHtml}
    ${metaHtml}
    ${runMetaHtml}
  </div>
  ${actionsHtml}
</header>`;
  }

  function buildTerminalExportScript() {
    return `<script>
(function () {
  var btn = document.querySelector('[data-export-toggle-highlights]');
  if (!btn) return;
  function sync() {
    var off = document.body.classList.contains('structured-highlights-off');
    btn.textContent = 'highlights: ' + (off ? 'off' : 'on');
    btn.setAttribute('aria-pressed', off ? 'false' : 'true');
  }
  btn.addEventListener('click', function () {
    document.body.classList.toggle('structured-highlights-off');
    sync();
  });
  sync();
}());
</script>`;
  }

  // ── Styles ────────────────────────────────────────────────────────────────
  // Produces the full inline CSS for an export document. exportCss is the
  // content of terminal_export.css (fetched and passed by the caller).
  // prefixWidth sets the --perm-prefix-width custom property.
  function buildTerminalExportStyles(fontFacesCss = '', prefixWidth = 0, exportCss = '') {
    const themeVars = getThemeExportVars();
    const themeDecls = Object.entries(themeVars)
      .map(([name, value]) => `    ${name}: ${value};`)
      .join('\n');
    return `${fontFacesCss}
  :root {
${themeDecls}
    --perm-prefix-width: ${prefixWidth}ch;
  }
  *, *::before, *::after { box-sizing: border-box; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  html, body { height: 100%; margin: 0; }
  body {
    display: flex;
    flex-direction: column;
    background: var(--bg);
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    font-size: var(--terminal-font-size, 14px);
    line-height: var(--terminal-line-height, 1.65);
  }
  ${exportCss}`;
  }

  // ── Document builder ──────────────────────────────────────────────────────
  // appName   — displayed in the header (green, letter-spaced)
  // title     — used in <title> tag
  // metaLine  — subtitle shown below app name in muted/uppercase style
  // runMeta   — optional { exitCode, duration, lines, version } for badge row
  // linesHtml — pre-built via buildExportLinesHtml
  // prefixWidth — gutter width in ch (for --perm-prefix-width)
  // fontFacesCss — @font-face declarations (base64 fonts)
  function buildTerminalExportHtml({
    appName,
    title,
    metaLine = '',
    runMeta = null,
    linesHtml = '',
    summaryHtml = '',
    prefixWidth = 0,
    fontFacesCss = '',
    exportCss = '',
    includeHighlightToggle = true,
    highlights = 'on',
  }) {
    const colorScheme = getThemeExportColorScheme();
    const headerModel = buildExportHeaderModel({ appName, metaLine, runMeta });
    const styles = buildTerminalExportStyles(fontFacesCss, prefixWidth, exportCss);
    const bodyClass = highlights === 'off' ? ' class="structured-highlights-off"' : '';
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="color-scheme" content="${escapeExportHtml(colorScheme)}">
<title>${escapeExportHtml(title)} — ${escapeExportHtml(appName)}</title>
<style>
${styles}
</style>
</head>
<body${bodyClass}>
${buildTerminalExportHeaderHtml(headerModel, { includeHighlightToggle })}
${summaryHtml || ''}
<main class="export-output nice-scroll">
${linesHtml}
</main>
${includeHighlightToggle ? buildTerminalExportScript() : ''}
</body>
</html>`;
  }

  let _cachedTerminalExportCss = null;

  async function fetchTerminalExportCss() {
    if (_cachedTerminalExportCss !== null) return _cachedTerminalExportCss;
    try {
      const res = await fetch('/static/css/terminal_export.css');
      _cachedTerminalExportCss = res.ok ? await res.text() : '';
    } catch (_) {
      _cachedTerminalExportCss = '';
    }
    return _cachedTerminalExportCss;
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
    buildExportMetaLine,
    normalizeExportTranscriptLine,
    normalizeExportTranscriptLines,
    appendCommandOutcomeSummaryLines,
    buildExportCommandOutcomeSummary,
    commandOutcomeSummaryToLines,
    isCommandOutcomeSummaryLine,
    normalizeExportRunMeta,
    lineEventFromWire,
    lineLegacyClass,
    isPromptEchoEvent,
    isPlainEvent,
    buildExportDocumentModel,
    escapeExportHtml,
    escapeExportAttr,
    renderExportPromptEcho,
    renderExportEntityContent,
    renderExportLineContent,
    buildExportLinesHtml,
    buildExportLineSummary,
    buildExportRunMetaItems,
    buildExportHeaderModel,
    buildExportRunMetaHtml,
    buildTerminalExportHeaderHtml,
    buildTerminalExportHtml,
    buildTerminalExportStyles,
    getThemeExportVars,
    getThemeExportColorScheme,
    fetchVendorFontFacesCss,
    fetchTerminalExportCss,
  };
})();
;
;
/* /static/js/export_pdf.js */
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

  function buildPdfLineSegments({ text, cls, kind, role, colors, ansiToHtml }) {
    const exportHtmlUtils = window.ExportHtmlUtils || null;
    const lineEvent = exportHtmlUtils && typeof exportHtmlUtils.lineEventFromWire === 'function'
      ? exportHtmlUtils.lineEventFromWire({ text, cls, kind, role })
      : { text: String(text || ''), kind: String(kind || (cls === 'notice' ? 'notice' : 'info')), role: String(role || (['prompt-echo', 'denied', 'exit-ok', 'exit-fail'].includes(cls) ? cls : 'body')) };
    const lineText = String(lineEvent.text || '');
    const lineKind = String(lineEvent.kind || 'info');
    const lineRole = String(lineEvent.role || 'body');
    const clsValue = String(cls || lineEvent.cls || lineEvent.legacy_cls || '');
    const stripped = lineText.replace(/\x1b\[[0-9;]*[A-Za-z]/g, '');
    if (clsValue.split(/\s+/).includes('command-outcome-summary-title')) {
      return [{ text: stripped, color: colors.blue, fontStyle: 'bold' }];
    }
    if (clsValue.split(/\s+/).includes('command-outcome-summary')) {
      return [{ text: stripped, color: colors.text, fontStyle: 'normal' }];
    }
    if (lineRole === 'exit-ok') return [{ text: stripped, color: colors.green, fontStyle: 'normal' }];
    if (lineRole === 'exit-fail') return [{ text: stripped, color: colors.red, fontStyle: 'normal' }];
    if (lineRole === 'denied') return [{ text: stripped, color: colors.amber, fontStyle: 'normal' }];
    if (lineKind === 'notice') return [{ text: stripped, color: colors.blue, fontStyle: 'normal' }];
    if (lineRole === 'prompt-echo') {
      const firstSpace = lineText.indexOf(' ');
      const prompt = firstSpace === -1 ? lineText : lineText.slice(0, firstSpace);
      const rest = firstSpace === -1 ? '' : lineText.slice(firstSpace);
      const segments = [{ text: prompt, color: colors.blue, fontStyle: 'bold' }];
      if (rest) segments.push({ text: rest, color: colors.text, fontStyle: 'normal' });
      return segments;
    }
    return parseAnsiSegments(lineText, colors.text, ansiToHtml);
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
    const summary = window.ExportHtmlUtils && typeof window.ExportHtmlUtils.buildExportLineSummary === 'function'
      ? window.ExportHtmlUtils.buildExportLineSummary(rawLines)
      : null;
    if (summary) {
      const summaryParts = [];
      if (summary.findings) summaryParts.push(`findings ${summary.findings}`);
      if (summary.errors) summaryParts.push(`errors ${summary.errors}`);
      if (summary.warnings) summaryParts.push(`warnings ${summary.warnings}`);
      Object.entries(summary.entityTypes || {}).slice(0, 6).forEach(([type, count]) => summaryParts.push(`${type} ${count}`));
      if (summaryParts.length) {
        doc.setFont(monoFontFamily, 'bold');
        doc.setTextColor(...colors.muted);
        doc.text(summaryParts.join('  ·  '), outputBoxPadX, y);
        doc.setFont(monoFontFamily, 'normal');
        y += leading * 1.4;
      }
    }
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
      const { text, cls, kind, role } = rawLines[i];
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

      const segments = buildPdfLineSegments({ text, cls, kind, role, colors, ansiToHtml });
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
;
;
/* /static/js/ui/ui_outside_click.js */
// Single source of truth for ambient outside-click dismissal.
//
// Companion to bindDismissible: where bindDismissible owns
// backdrop-click for surfaces with a visible scrim, bindOutsideClickClose
// owns ambient-click dismissal for dropdown-style menus and side panels
// where clicks can land anywhere in the document (or anywhere in a
// scoped subtree) without a dimming overlay to intercept them.
//
// The key contract this helper encodes is the trigger-exemption rule:
// a disclosure's trigger button has its own click handler that toggles
// the panel. The outside-click listener must NOT close the panel when
// the click lands on the trigger, otherwise you get a close-then-reopen
// loop (or the panel never opens at all, depending on listener order).
//
// Before this helper, every call site hand-rolled the same pattern:
//   - triggerBtn.addEventListener('click', e => { e.stopPropagation(); ... });
//   - document.addEventListener('click', () => closeThePanel());
// and the stopPropagation() was the workaround for the missing trigger
// exemption. Register the trigger with bindOutsideClickClose and the
// helper skips clicks landing on it (or inside it), so the trigger's
// own handler no longer needs to stopPropagation.
//
// Unlike bindDismissible, this helper does NOT own Escape — callers that
// need Escape-to-close should layer a bindDismissible on the same surface
// (when it has modal/panel/sheet semantics), or rely on the owning
// modal/sheet's Escape cascade for nested dropdowns.
(function (global) {
  'use strict';

  function _toArray(input) {
    if (!input) return [];
    if (Array.isArray(input)) return input.filter(Boolean);
    return [input];
  }

  function bindOutsideClickClose(panel, opts) {
    if (!opts) return null;
    if (typeof opts.isOpen !== 'function') return null;
    if (typeof opts.onClose !== 'function') return null;
    // panel may be null when the caller has no single containing element
    // (e.g. the recents-sheet case where several sibling dropdowns share a
    // parent scope and exemption is expressed purely via a CSS selector).
    // In that case, panel.contains() is skipped and trigger + exemptSelectors
    // are the sole exemption channels.

    const isOpenFn = opts.isOpen;
    const onCloseFn = opts.onClose;
    const triggers = _toArray(opts.triggers);
    const exemptSelectors = _toArray(opts.exemptSelectors);
    const scope = opts.scope || (typeof document !== 'undefined' ? document : null);
    const capture = !!opts.capture;
    if (!scope || typeof scope.addEventListener !== 'function') return null;

    const handler = (e) => {
      if (!isOpenFn()) return;
      const target = e.target;
      if (!target) return;
      if (panel && panel.contains && panel.contains(target)) return;
      for (let i = 0; i < triggers.length; i += 1) {
        const t = triggers[i];
        if (!t) continue;
        if (t === target) return;
        if (t.contains && t.contains(target)) return;
      }
      if (exemptSelectors.length && typeof target.closest === 'function') {
        for (let i = 0; i < exemptSelectors.length; i += 1) {
          if (target.closest(exemptSelectors[i])) return;
        }
      }
      onCloseFn();
    };

    scope.addEventListener('click', handler, capture);

    return {
      dispose: () => {
        scope.removeEventListener('click', handler, capture);
      },
    };
  }

  global.bindOutsideClickClose = bindOutsideClickClose;
})(typeof window !== 'undefined' ? window : globalThis);
;
;
/* /static/js/permalink.js */
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
  var rawLines = window.ExportHtmlUtils && typeof ExportHtmlUtils.normalizeExportTranscriptLines === 'function'
    ? ExportHtmlUtils.normalizeExportTranscriptLines(transcriptModel.lines || pd.lines || [])
    : (transcriptModel.lines || pd.lines || []);
  var hasTimestampMetadata = transcriptModel.hasTimestampMetadata || pd.hasTimestampMetadata || false;
  var appName = exportModel.appName || pd.appName || headerModel.appName || '';
  var label = exportModel.label || pd.label || '';
  var command = exportModel.command || transcriptModel.command || pd.command || label;
  var created = exportModel.created || pd.created || '';
  var createdDisplay = exportModel.createdDisplay || pd.createdDisplay || headerModel.createdDisplay || '';
  var fontFacesCss = exportModel.fontFacesCss || pd.fontFacesCss || '';
  var permalinkMeta = window.ExportHtmlUtils && typeof ExportHtmlUtils.normalizeExportRunMeta === 'function'
    ? ExportHtmlUtils.normalizeExportRunMeta(exportModel.runMeta || pd.permalinkMeta || null)
    : (exportModel.runMeta || pd.permalinkMeta || null);

  var ansiUp = new AnsiUp();
  ansiUp.use_classes = false;

  var out = document.getElementById('output');
  var tsModes = ['off', 'elapsed', 'clock'];

  // ── Preference cookies ─────────────────────────────────────────────────────
  function getCookie(name) {
    var prefix = name + '=';
    var match = document.cookie.split(';').map(function (p) { return p.trim(); }).find(function (p) { return p.startsWith(prefix); });
    return match ? decodeURIComponent(match.slice(prefix.length)) : '';
  }

  var lnMode = getCookie('pref_line_numbers') === 'on' ? 'on' : 'off';
  var tsMode = tsModes.includes(getCookie('pref_timestamps')) ? getCookie('pref_timestamps') : 'off';
  var highlightMode = getCookie('pref_structured_highlights') === 'off' ? 'off' : 'on';
  var commandOutcomeSummariesEnabled = getCookie('pref_command_outcome_summaries') !== 'off';
  var lines = window.ExportHtmlUtils && typeof ExportHtmlUtils.appendCommandOutcomeSummaryLines === 'function'
    ? ExportHtmlUtils.appendCommandOutcomeSummaryLines(rawLines, { command: command, enabled: commandOutcomeSummariesEnabled })
    : rawLines;
  if (!hasTimestampMetadata) tsMode = 'off';

  function setCookie(name, value) {
    document.cookie = name + '=' + encodeURIComponent(value) + '; path=/; max-age=31536000; SameSite=Lax';
  }

  function syncHighlightMode() {
    document.body.classList.toggle('structured-highlights-off', highlightMode === 'off');
    var highlightBtn = document.getElementById('toggle-highlights');
    if (highlightBtn) {
      highlightBtn.textContent = 'highlights: ' + highlightMode;
      highlightBtn.setAttribute('aria-pressed', highlightMode === 'on' ? 'true' : 'false');
    }
  }

  // ── Prefix formatting ──────────────────────────────────────────────────────
  function timestampText(entry) {
    if (tsMode === 'clock') return entry.tsC || '';
    if (tsMode === 'elapsed') return entry.tsE || '';
    return '';
  }

  function formatPrefix(index, entry) {
    if (window.ExportHtmlUtils
        && typeof ExportHtmlUtils.isCommandOutcomeSummaryLine === 'function'
        && ExportHtmlUtils.isCommandOutcomeSummaryLine(entry)) {
      return '';
    }
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
      var lineEvent = ExportHtmlUtils.lineEventFromWire(entry);
      var span = document.createElement('span');
      var cls = ExportHtmlUtils.lineLegacyClass(lineEvent);
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
      if (typeof ExportHtmlUtils.renderExportLineContent === 'function') {
        contentEl.innerHTML = ExportHtmlUtils.renderExportLineContent(lineEvent, function (text) {
          return ansiUp.ansi_to_html(text);
        });
      } else if (ExportHtmlUtils.isPromptEchoEvent(lineEvent)) {
        contentEl.innerHTML = ExportHtmlUtils.renderExportPromptEcho(lineEvent.text);
      } else if (ExportHtmlUtils.isPlainEvent(lineEvent)) {
        contentEl.textContent = lineEvent.text;
      } else {
        contentEl.innerHTML = ansiUp.ansi_to_html(lineEvent.text);
      }
      span.appendChild(contentEl);
      out.appendChild(span);
    });

    document.getElementById('toggle-ln').textContent = 'line numbers: ' + lnMode;
    var tsBtn = document.getElementById('toggle-ts');
    tsBtn.textContent = hasTimestampMetadata ? 'timestamps: ' + tsMode : 'timestamps: unavailable';
    syncHighlightMode();
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

  var highlightToggle = document.getElementById('toggle-highlights');
  if (highlightToggle) {
    highlightToggle.addEventListener('click', function () {
      highlightMode = highlightMode === 'on' ? 'off' : 'on';
      setCookie('pref_structured_highlights', highlightMode);
      syncHighlightMode();
    });
  }

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
    downloadBlobAsAttachment(new Blob([text], {type: 'text/plain'}), downloadName('txt'));
  }

  function saveHtml() {
    var exportModel = ExportHtmlUtils.buildExportDocumentModel({
      appName: appName,
      title: label,
      label: label,
      createdText: createdDisplay || created,
      runMeta: permalinkMeta,
      rawLines: rawLines,
      command: command,
      includeCommandOutcomeSummary: commandOutcomeSummariesEnabled,
    });
    var result = ExportHtmlUtils.buildExportLinesHtml(exportModel.rawLines, {
      getPrefix: function (entry, i) { return formatPrefix(i + 1, entry); },
      ansiToHtml: function (text) { return ansiUp.ansi_to_html(text); },
    });
    var linesHtml = result.linesHtml;
    var summaryHtml = result.summaryHtml;
    var prefixWidth = result.prefixWidth;

    ExportHtmlUtils.fetchTerminalExportCss().catch(function () { return ''; }).then(function (exportCss) {
      var html = ExportHtmlUtils.buildTerminalExportHtml({
        appName: exportModel.appName,
        title: exportModel.title,
        metaLine: exportModel.metaLine,
        runMeta: exportModel.runMeta,
        linesHtml: linesHtml,
        summaryHtml: summaryHtml,
        prefixWidth: prefixWidth,
        fontFacesCss: fontFacesCss,
        exportCss: exportCss,
        highlights: highlightMode,
      });
      downloadBlobAsAttachment(new Blob([html], {type: 'text/html'}), downloadName('html'));
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
      rawLines: rawLines,
      command: command,
      includeCommandOutcomeSummary: commandOutcomeSummariesEnabled,
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
;
