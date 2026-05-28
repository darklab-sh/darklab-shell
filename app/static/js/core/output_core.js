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
    return (Array.isArray(lines) ? lines : [])
      .filter(line => line && typeof line === 'object')
      .filter(line => {
        const role = String(line.role || '').trim();
        const cls = String(line.cls || '').split(/\s+/).filter(Boolean);
        if (role === 'prompt-echo' || role === 'exit-ok' || role === 'exit-fail') return false;
        if (cls.includes('prompt-echo') || cls.includes('exit-ok') || cls.includes('exit-fail')) return false;
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
