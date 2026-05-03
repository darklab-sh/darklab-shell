// ── Output pure helpers ──────────────────────────────────────────────────
// Loaded before output.js. DOM writes and batching stay in output.js; prompt
// label, prefix, and signal-count transforms live here.
var DarklabOutputCore = (function (global) {
  const OUTPUT_SIGNAL_SCOPES = Object.freeze(['findings', 'warnings', 'errors', 'summaries']);
  const OUTPUT_SIGNAL_SUMMARY_CLASSES = Object.freeze([
    'fake-signal-summary-header',
    'fake-signal-summary-section',
    'fake-signal-summary-row',
    'fake-signal-summary-note',
    'fake-signal-summary-sep',
  ]);

  function promptIdentityPrefix(rawPrefix = '') {
    let prefix = String(rawPrefix || '').trim() || 'anon@darklab';
    if (prefix.endsWith('$')) prefix = prefix.slice(0, -1).trimEnd();
    prefix = prefix.replace(/:[^\s:]+$/, '').trim() || 'anon@darklab';
    return prefix;
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

  function lineHasClass(rawLine, className) {
    const cls = String(rawLine?.cls || '');
    return cls.split(/\s+/).filter(Boolean).includes(className);
  }

  function isSignalCountableLine(rawLine) {
    if (!rawLine || lineHasClass(rawLine, 'prompt-echo')) return false;
    const classes = String(rawLine.cls || '').split(/\s+/).filter(Boolean);
    return !classes.some(cls => isSignalSummaryClassName(cls));
  }

  function isBuiltinCommandRoot(root, builtinRoots = []) {
    return !!root && Array.isArray(builtinRoots) && builtinRoots.includes(root);
  }

  function normalizeSignals(signals) {
    return Array.isArray(signals)
      ? signals.map(signal => String(signal || '')).filter(Boolean)
      : [];
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
    OUTPUT_SIGNAL_SCOPES,
    buildPromptLabel,
    countableSignalScopes,
    emptySignalCounts,
    formatOutputPrefix,
    isBuiltinCommandRoot,
    isSignalCountableLine,
    isSignalSummaryClassName,
    lineHasClass,
    normalizeSignals,
    normalizeWorkspaceCwd,
    promptIdentityPrefix,
    stripPromptLabelFromEchoText,
    workspaceDisplayPath,
  });
  global.DarklabOutputCore = api;
  return api;
})(typeof window !== 'undefined' ? window : globalThis);
