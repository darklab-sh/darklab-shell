// ── Shared search logic ──

const _SEARCH_SIGNAL_PATTERNS = {
  findings: [
    /^\d+\/(?:tcp|udp)\s+open\b/i,
    /\bdiscovered open port\b/i,
    /^\S+\s+\[[^\]]+\]\s+\d+\s+\([^)]+\)\s+open\b/i,
    /\[(?:info|low|medium|high|critical)\]/i,
    /^\s*\/\S+\s+\[status:\s*\d{3}\b/i,
    /\bHTTP\/[\d.]+\s+\d{3}\b/i,
    /\bVULNERABLE\b/i,
    /\bnot vulnerable\b/i,
    /\bverify return code:\s*0\b/i,
    /\bnotAfter=/i,
    /^\S+\.\s+\d+\s+(?:IN\s+)?(?:A|AAAA|CNAME|MX|NS|TXT|SOA|PTR)\b/i,
    /^\S+\s+(?:A|AAAA|CNAME|MX|NS|TXT|SOA|PTR)\s+\S+/,
    /^(?:\d{1,3}\.){3}\d{1,3}$/i,
    /^[0-9a-f:]+:+[0-9a-f:]+$/i,
    /^\S+\s+has address\s+[0-9a-f:.]+\b/i,
    /^\S+\s+mail is handled by\s+\d+\s+\S+/i,
    /\bService Info:/i,
    /\bOS details:/i,
    /\bssl-issuer\b/i,
  ],
  warnings: [
    /\bwarning\b/i,
    /\bwarn\b/i,
    /\bnote:/i,
    /\bunreliable\b/i,
    /\bretrying\b/i,
    /\brate limited\b/i,
  ],
  errors: [
    /\berror\b/i,
    /\bfailed\b/i,
    /\bdenied\b/i,
    /\btimeout\b/i,
    /\bunreachable\b/i,
    /\brefused\b/i,
    /no servers could be reached/i,
    /\bcould not\b/i,
    /\binvalid\b/i,
    /\bstalled\b/i,
  ],
  summaries: [
    /\bsummary\b/i,
    /\bNmap done:\b/i,
    /\bhosts? up\b/i,
    /\bpacket loss\b/i,
    /\brtt min\/avg\/max\b/i,
    /\berrors?:\s*\d+\b/i,
    /\bfound:\s*\d+\b/i,
    /\bTotal requests:\b/i,
    /\bDuration:\b/i,
    /\bRequests\/sec:\b/i,
    /\bProcessed Requests:\b/i,
  ],
};

const _SEARCH_FINDINGS_EXCLUDES = [
  /^Starting Nmap/i,
  /^Nmap \d/i,
  /^Nmap scan initiated/i,
  /^Progress:\s*/i,
  /^:: Progress:/i,
  /^Fuzz Faster U Fool/i,
  /^Templates loaded for current scan/i,
  /^Using Interactsh Server/i,
  /^; <<>> DiG/i,
  /^;;/i,
  /^Usage:\s+/i,
  /^usage:\s+/i,
  /^\[options\]$/i,
  /^the tool you love/i,
  /^rustscan$/i,
  /^Testing SSL server/i,
  /^CHECKING CONNECTIVITY/i,
  /^OpenSSL$/i,
  /^projectdiscovery\.io$/i,
];

const _SEARCH_SCOPE_LABELS = {
  text: 'text',
  findings: 'findings',
  warnings: 'warnings',
  errors: 'errors',
  summaries: 'summaries',
};

const _FINDINGS_FRIENDLY_ROOTS = new Set([
  'nmap',
  'ffuf',
  'gobuster',
  'feroxbuster',
  'nuclei',
  'dig',
  'testssl',
  'sslscan',
  'sslyze',
  'naabu',
  'rustscan',
]);

const _SEARCH_SUMMARY_LIMIT = 25;

let _searchTogglePulseTimer = null;
let _searchDiscoverabilityRefreshTimer = null;
let _searchDiscoverabilityRefreshTimerType = '';

function _getSearchScope() {
  return typeof searchScope === 'string' ? searchScope : 'text';
}

function _setSearchCount(text) {
  if (searchCount) searchCount.textContent = text;
}

function _searchScopeButtonLabel(scope, count) {
  if (scope === 'text') return 'text';
  return `${_SEARCH_SCOPE_LABELS[scope]} (${count})`;
}

function _searchScopeUnitLabel(scope, count) {
  if (scope === 'summaries') return count === 1 ? 'summary' : 'summaries';
  const base = _SEARCH_SCOPE_LABELS[scope] || 'matches';
  return count === 1 ? base.replace(/s$/, '') : base;
}

function _formatFindingSummary(counts) {
  const parts = [];
  if (counts.findings > 0) parts.push(`${counts.findings} finding${counts.findings === 1 ? '' : 's'}`);
  if (counts.warnings > 0) parts.push(`${counts.warnings} warning${counts.warnings === 1 ? '' : 's'}`);
  if (counts.errors > 0) parts.push(`${counts.errors} error${counts.errors === 1 ? '' : 's'}`);
  if (counts.summaries > 0) parts.push(`${counts.summaries} summar${counts.summaries === 1 ? 'y' : 'ies'}`);
  return parts.join(' • ');
}

function _formatCompactSignalSummary(counts) {
  const parts = [];
  const add = (scope, short, count) => {
    if (count <= 0) return;
    parts.push(
      `<button type="button" class="search-signal-chip" data-search-signal-scope="${scope}" ` +
      `aria-label="${count} ${_searchScopeUnitLabel(scope, count)} available">${count}${short}</button>`,
    );
  };
  add('findings', 'F', counts.findings);
  add('warnings', 'W', counts.warnings);
  add('errors', 'E', counts.errors);
  add('summaries', 'S', counts.summaries);
  return parts.join('<span class="search-signal-sep" aria-hidden="true">•</span>');
}

function _clearSearchDiscoverabilityPulse() {
  if (_searchTogglePulseTimer) {
    clearTimeout(_searchTogglePulseTimer);
    _searchTogglePulseTimer = null;
  }
  if (typeof searchToggleBtn !== 'undefined' && searchToggleBtn) {
    searchToggleBtn.classList.remove('search-discover-pulse');
  }
}

function _searchNoMatchesLabel(scope) {
  return scope === 'text' ? 'no matches' : `no ${_SEARCH_SCOPE_LABELS[scope] || 'matches'}`;
}

function _searchInputPlaceholder(scope) {
  if (scope === 'text') return 'Search output…';
  if (scope === 'summaries') return 'Jump between summary lines…';
  return `Jump between ${_SEARCH_SCOPE_LABELS[scope] || 'matches'}…`;
}

function syncSearchScopeUi() {
  const scope = _getSearchScope();
  if (typeof searchInput !== 'undefined' && searchInput) {
    searchInput.disabled = scope !== 'text';
    searchInput.placeholder = _searchInputPlaceholder(scope);
  }
  if (typeof searchCaseBtn !== 'undefined' && searchCaseBtn) searchCaseBtn.disabled = scope !== 'text';
  if (typeof searchRegexBtn !== 'undefined' && searchRegexBtn) searchRegexBtn.disabled = scope !== 'text';
  if (typeof searchScopeButtons !== 'undefined' && Array.isArray(searchScopeButtons)) {
    searchScopeButtons.forEach((btn) => {
      const active = btn?.dataset?.searchScope === scope;
      btn?.setAttribute('aria-pressed', active ? 'true' : 'false');
      btn?.classList.toggle('active', active);
    });
  }
}

function _lineMatchesSearchScopeForRoot(line, scope, root = null) {
  if (!(line instanceof Element) || scope === 'text') return false;
  if (
    line.classList.contains('fake-signal-summary-header')
    || line.classList.contains('fake-signal-summary-section')
    || line.classList.contains('fake-signal-summary-row')
    || line.classList.contains('fake-signal-summary-note')
    || line.classList.contains('fake-signal-summary-sep')
  ) {
    return false;
  }
  const useRoot = root === null ? _lineCommandRoot(line) : root;
  if (_isBuiltinCommandRoot(useRoot)) return false;
  const text = (line.textContent || '').trim();
  if (!text) return false;
  if (scope === 'warnings' && line.classList.contains('notice')) return true;
  if (scope === 'errors' && (line.classList.contains('denied') || line.classList.contains('exit-fail'))) {
    if (/^\[killed by user(?:\b|[^\w])/i.test(text)) return false;
    return true;
  }
  if (scope === 'errors' && /^\[killed by user(?:\b|[^\w])/i.test(text)) return false;
  if (scope === 'findings' && _SEARCH_FINDINGS_EXCLUDES.some((pattern) => pattern.test(text))) {
    return false;
  }
  if (scope === 'findings') {
    if (/\bmail exchanger\s*=\s*\S+/i.test(text)) return true;
    if (/\btext\s*=\s*.+/i.test(text)) return true;
    if (/\bcanonical name\s*=\s*\S+/i.test(text)) return true;
    if (/^Address(?:es)?:\s+[0-9a-f:.]+\b/i.test(text)) {
      const prevText = String(line.previousElementSibling?.textContent || '').trim();
      if (/^Name:\s+\S+/i.test(prevText)) return true;
    }
  }
  const patterns = _SEARCH_SIGNAL_PATTERNS[scope] || [];
  return patterns.some((pattern) => pattern.test(text));
}

function _getSearchSignalCounts(out) {
  const counts = { findings: 0, warnings: 0, errors: 0, summaries: 0 };
  if (!(out instanceof Element)) return counts;
  const lines = Array.from(out.querySelectorAll('.line'));
  let currentRoot = _summaryCommandRoot(String((typeof getTab === 'function' ? getTab(activeTabId) : null)?.command || ''));
  lines.forEach((line) => {
    if (!(line instanceof Element)) return;
    if (line.classList.contains('prompt-echo')) {
      currentRoot = _summaryCommandRoot(_promptEchoCommandText(line));
      return;
    }
    if (_lineMatchesSearchScopeForRoot(line, 'findings', currentRoot)) counts.findings += 1;
    if (_lineMatchesSearchScopeForRoot(line, 'warnings', currentRoot)) counts.warnings += 1;
    if (_lineMatchesSearchScopeForRoot(line, 'errors', currentRoot)) counts.errors += 1;
    if (_lineMatchesSearchScopeForRoot(line, 'summaries', currentRoot)) counts.summaries += 1;
  });
  return counts;
}

function _shouldPreferFindingsScope(counts) {
  if (!counts || counts.findings <= 0) return false;
  const tab = typeof getTab === 'function' ? getTab(activeTabId) : null;
  const command = String(tab?.command || '').trim();
  const root = command.split(/\s+/, 1)[0]?.toLowerCase() || '';
  return _FINDINGS_FRIENDLY_ROOTS.has(root) || counts.findings >= 2;
}

function refreshSearchDiscoverabilityUi() {
  if (_searchDiscoverabilityRefreshTimer) {
    if (
      _searchDiscoverabilityRefreshTimerType === 'idle'
      && typeof cancelIdleCallback === 'function'
    ) {
      cancelIdleCallback(_searchDiscoverabilityRefreshTimer);
    } else {
      clearTimeout(_searchDiscoverabilityRefreshTimer);
    }
    _searchDiscoverabilityRefreshTimer = null;
    _searchDiscoverabilityRefreshTimerType = '';
  }
  const out = getOutput(activeTabId);
  const counts = _getSearchSignalCounts(out);
  searchSignalCounts = counts;
  if (typeof searchToggleBtn !== 'undefined' && searchToggleBtn) {
    const summary = _formatFindingSummary(counts);
    const buttonLabel = counts.findings > 0
      ? `search • ${counts.findings} finding${counts.findings === 1 ? '' : 's'}`
      : 'search';
    searchToggleBtn.dataset.searchLabel = buttonLabel;
    searchToggleBtn.textContent = `⌕ ${buttonLabel}`;
    searchToggleBtn.title = summary
      ? `Search output (${summary} available)`
      : 'Search output (Alt+S)';
    searchToggleBtn.setAttribute(
      'aria-label',
      summary ? `Search output, ${summary} available` : 'Search output',
    );
    const shouldPulse = counts.findings > 0
      && !searchDiscoverabilityPrompted
      && !(typeof isSearchBarOpen === 'function' && isSearchBarOpen());
    if (shouldPulse) {
      searchDiscoverabilityPrompted = true;
      searchToggleBtn.classList.add('search-discover-pulse');
      _searchTogglePulseTimer = setTimeout(() => {
        _clearSearchDiscoverabilityPulse();
      }, 8000);
    }
  }
  if (typeof searchSignalSummary !== 'undefined' && searchSignalSummary) {
    const compact = _formatCompactSignalSummary(counts);
    const hasSignals = counts.findings > 0 || counts.warnings > 0 || counts.errors > 0 || counts.summaries > 0;
    searchSignalSummary.classList.toggle('u-hidden', !hasSignals);
    searchSignalSummary.innerHTML = compact;
    searchSignalSummary.title = hasSignals ? _formatFindingSummary(counts) : '';
    searchSignalSummary.setAttribute('aria-label', hasSignals ? _formatFindingSummary(counts) : '');
    if (hasSignals) {
      searchSignalSummary.querySelectorAll('[data-search-signal-scope]').forEach((btn) => {
        btn.addEventListener('click', () => {
          if (typeof openSearchFromSignal === 'function') openSearchFromSignal(btn.dataset.searchSignalScope || 'text');
        });
      });
    }
  }
  if (typeof searchSummaryBtn !== 'undefined' && searchSummaryBtn) {
    const hasSignals = counts.findings > 0 || counts.warnings > 0 || counts.errors > 0 || counts.summaries > 0;
    searchSummaryBtn.disabled = !hasSignals;
    searchSummaryBtn.title = hasSignals
      ? 'Summarize findings, warnings, errors, and summary lines'
      : 'No findings, warnings, errors, or summary lines yet';
    searchSummaryBtn.setAttribute(
      'aria-label',
      hasSignals
        ? 'Summarize findings, warnings, errors, and summary lines'
        : 'No findings, warnings, errors, or summary lines yet',
    );
  }
  if (typeof searchScopeButtons !== 'undefined' && Array.isArray(searchScopeButtons)) {
    searchScopeButtons.forEach((btn) => {
      const scope = btn?.dataset?.searchScope || 'text';
      const count = scope === 'text' ? 0 : Number(counts[scope] || 0);
      btn.textContent = _searchScopeButtonLabel(scope, count);
      btn.title = scope === 'text'
        ? 'Text search'
        : `Jump between ${count} ${_searchScopeUnitLabel(scope, count)}`;
    });
  }
  return counts;
}

function scheduleSearchDiscoverabilityRefresh() {
  if (_searchDiscoverabilityRefreshTimer) return;
  const run = () => {
    _searchDiscoverabilityRefreshTimer = null;
    _searchDiscoverabilityRefreshTimerType = '';
    refreshSearchDiscoverabilityUi();
  };
  if (typeof requestIdleCallback === 'function') {
    _searchDiscoverabilityRefreshTimer = requestIdleCallback(run, { timeout: 500 });
    _searchDiscoverabilityRefreshTimerType = 'idle';
    return;
  }
  _searchDiscoverabilityRefreshTimer = setTimeout(run, 80);
  _searchDiscoverabilityRefreshTimerType = 'timeout';
}

function prepareSearchBarForOpen() {
  _clearSearchDiscoverabilityPulse();
  const counts = refreshSearchDiscoverabilityUi();
  if (_shouldPreferFindingsScope(counts)) {
    searchScope = 'findings';
  } else {
    searchScope = 'text';
  }
  syncSearchScopeUi();
}

function prepareSearchBarForScope(scope) {
  _clearSearchDiscoverabilityPulse();
  refreshSearchDiscoverabilityUi();
  searchScope = _SEARCH_SCOPE_LABELS[scope] ? scope : 'text';
  syncSearchScopeUi();
}

function setSearchScope(scope) {
  searchScope = _SEARCH_SCOPE_LABELS[scope] ? scope : 'text';
  syncSearchScopeUi();
  runSearch();
}

function _collectSearchTextNodes(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const parts = [];
  let offset = 0;
  let node;
  while ((node = walker.nextNode())) {
    const text = node.nodeValue || '';
    parts.push({ node, text, start: offset, end: offset + text.length });
    offset += text.length;
  }
  return parts;
}

function _highlightSearchLine(line, re, startMatchIdx) {
  // Search highlighting operates on a cloned line so the live transcript keeps
  // its original DOM structure until a match has actually been confirmed.
  // A single logical match that crosses an inline-element boundary (e.g. a
  // query that spans `.line-host`, ANSI-colour spans, or prompt wrappers)
  // cannot be wrapped in one `<mark>` — `<mark>` can't cross element
  // boundaries. Each segment gets its own `<mark>` but all segments of the
  // same logical match share a `data-search-match` index, so nav walks by
  // logical match, not DOM element.
  const clone = line.cloneNode(true);
  // Merge adjacent text nodes before walking — otherwise a prior
  // clearHighlights() pass leaves the line fragmented (mark replaced with a
  // sibling textNode, not merged with neighbours), and a fresh search emits
  // one `<mark>` per fragment instead of one per logical match, producing
  // visible pill-shape gaps that read as per-character highlighting.
  clone.normalize();
  const parts = _collectSearchTextNodes(clone);
  const text = parts.map(part => part.text).join('');
  if (!text) return 0;

  const matches = [];
  re.lastIndex = 0;
  let match;
  while ((match = re.exec(text)) !== null) {
    if (!match[0]) {
      re.lastIndex += 1;
      continue;
    }
    matches.push({ start: match.index, end: match.index + match[0].length });
  }
  if (!matches.length) return 0;

  let matchIdx = 0;
  for (const part of parts) {
    const { node, text: partText, start: partStart, end: partEnd } = part;
    let cursor = partStart;
    let localStart = 0;
    const frag = document.createDocumentFragment();

    while (cursor < partEnd) {
      while (matchIdx < matches.length && matches[matchIdx].end <= cursor) matchIdx += 1;
      const current = matches[matchIdx];
      if (!current || current.start >= partEnd) {
        frag.appendChild(document.createTextNode(partText.slice(localStart)));
        break;
      }

      if (cursor < current.start) {
        const plainEnd = Math.min(partEnd, current.start);
        const slice = partText.slice(localStart, localStart + (plainEnd - cursor));
        if (slice) frag.appendChild(document.createTextNode(slice));
        localStart += plainEnd - cursor;
        cursor = plainEnd;
        continue;
      }

      const markEnd = Math.min(partEnd, current.end);
      const mark = document.createElement('mark');
      mark.className = 'search-hl';
      mark.dataset.searchMatch = String(startMatchIdx + matchIdx);
      mark.textContent = partText.slice(localStart, localStart + (markEnd - cursor));
      frag.appendChild(mark);
      localStart += markEnd - cursor;
      cursor = markEnd;
    }

    node.replaceWith(frag);
  }

  line.replaceWith(clone);
  return matches.length;
}

function _lineMatchesSearchScope(line, scope) {
  return _lineMatchesSearchScopeForRoot(line, scope, null);
}

function _collectSearchSignalTexts(out, scope) {
  const lines = Array.from(out.querySelectorAll('.line'));
  return lines
    .filter((line) => _lineMatchesSearchScope(line, scope))
    .map((line) => (line.textContent || '').trim())
    .filter(Boolean);
}

function _promptEchoCommandText(line) {
  if (!(line instanceof Element)) return '';
  const text = (line.textContent || '').trim();
  const prefix = String(line.querySelector('.prompt-prefix')?.textContent || '').trim();
  if (prefix && text.startsWith(prefix)) return text.slice(prefix.length).trim();
  return text.replace(/^\$\s*/, '').trim();
}

function _lineCommandRoot(line) {
  let cursor = line;
  while (cursor instanceof Element) {
    if (cursor.classList.contains('prompt-echo')) {
      return _summaryCommandRoot(_promptEchoCommandText(cursor));
    }
    cursor = cursor.previousElementSibling;
  }
  const tab = typeof getTab === 'function' ? getTab(activeTabId) : null;
  return _summaryCommandRoot(String(tab?.command || ''));
}

function _lineBelongsToBuiltinCommand(line) {
  const root = _lineCommandRoot(line);
  return _isBuiltinCommandRoot(root);
}

function _isBuiltinCommandRoot(root) {
  const builtinRoots = (
    typeof acBuiltinCommandRoots !== 'undefined' && Array.isArray(acBuiltinCommandRoots)
  ) ? acBuiltinCommandRoots : [];
  return !!root && builtinRoots.includes(root);
}

function _collectSearchCommandBlocks(out) {
  const lines = Array.from(out.querySelectorAll('.line'));
  const blocks = [];
  let current = null;
  lines.forEach((line) => {
    if (!(line instanceof Element)) return;
    if (
      line.classList.contains('fake-signal-summary-header')
      || line.classList.contains('fake-signal-summary-section')
      || line.classList.contains('fake-signal-summary-row')
      || line.classList.contains('fake-signal-summary-note')
      || line.classList.contains('fake-signal-summary-sep')
    ) {
      return;
    }
    if (line.classList.contains('prompt-echo')) {
      current = {
        command: _promptEchoCommandText(line),
        lines: [],
      };
      blocks.push(current);
      return;
    }
    if (!current) {
      current = { command: '', lines: [] };
      blocks.push(current);
    }
    current.lines.push(line);
  });
  return blocks.filter((block) => block.command || block.lines.length);
}

function _tokenizeSummaryCommand(command) {
  const tokens = [];
  const source = String(command || '').trim();
  let current = '';
  let quote = '';
  for (let i = 0; i < source.length; i += 1) {
    const ch = source[i];
    if (quote) {
      if (ch === quote) {
        quote = '';
      } else if (ch === '\\' && i + 1 < source.length) {
        i += 1;
        current += source[i];
      } else {
        current += ch;
      }
      continue;
    }
    if (ch === '"' || ch === "'") {
      quote = ch;
      continue;
    }
    if (/\s/.test(ch)) {
      if (current) {
        tokens.push(current);
        current = '';
      }
      continue;
    }
    current += ch;
  }
  if (current) tokens.push(current);
  return tokens;
}

function _summaryCommandRoot(command) {
  const tokens = _tokenizeSummaryCommand(command);
  return String(tokens[0] || '').toLowerCase();
}

function _summaryStripUrlTarget(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  try {
    if (/^[a-z][a-z0-9+.-]*:\/\//i.test(raw)) {
      const parsed = new URL(raw);
      return parsed.host || raw;
    }
  } catch (_) {
    return raw;
  }
  return raw.replace(/^[a-z][a-z0-9+.-]*:\/\//i, '').replace(/[/?#].*$/, '');
}

function _summaryFindFlagValue(tokens, names) {
  const wanted = new Set(names);
  for (let i = 1; i < tokens.length; i += 1) {
    const token = tokens[i];
    if (wanted.has(token) && tokens[i + 1] && !tokens[i + 1].startsWith('-')) {
      return tokens[i + 1];
    }
    const eq = token.match(/^([^=]+)=(.+)$/);
    if (eq && wanted.has(eq[1])) return eq[2];
  }
  return '';
}

function _summaryPositionalTargets(tokens, { skipValuesAfter = new Set(), skipValuesForPrefix = /^$/ } = {}) {
  const result = [];
  for (let i = 1; i < tokens.length; i += 1) {
    const token = tokens[i];
    if (!token) continue;
    if (token.startsWith('-')) {
      if (skipValuesAfter.has(token) || skipValuesForPrefix.test(token)) {
        const next = tokens[i + 1] || '';
        if (next && !next.startsWith('-')) i += 1;
      }
      continue;
    }
    result.push(token);
  }
  return result;
}

function _summaryDnsTarget(tokens, root) {
  const recordTypes = new Set(['a', 'aaaa', 'cname', 'mx', 'ns', 'txt', 'soa', 'ptr', 'srv', 'caa', 'any']);
  const positionals = [];
  for (let i = 1; i < tokens.length; i += 1) {
    const token = tokens[i];
    if (!token || token.startsWith('-') || token.startsWith('+') || token.startsWith('@')) continue;
    if (recordTypes.has(token.toLowerCase())) continue;
    positionals.push(token);
  }
  if (root === 'nslookup' && /^server$/i.test(positionals[0] || '')) return positionals[1] || '';
  return positionals[0] || '';
}

function _summaryExtractTarget(command) {
  const tokens = _tokenizeSummaryCommand(command);
  const root = String(tokens[0] || '').toLowerCase();
  if (!root) return null;

  if (['dig', 'host', 'nslookup'].includes(root)) {
    const target = _summaryDnsTarget(tokens, root);
    return target ? _summaryStripUrlTarget(target) : null;
  }

  if (['curl', 'httpx', 'pd-httpx', 'wafw00f'].includes(root)) {
    const positionals = _summaryPositionalTargets(tokens, {
      skipValuesAfter: new Set(['-H', '--header', '-A', '--user-agent', '-o', '--output', '-w', '--write-out', '--connect-timeout', '-m', '--max-time']),
    });
    const target = positionals.find((token) => /^[a-z][a-z0-9+.-]*:\/\//i.test(token))
      || positionals.find((token) => /\./.test(token));
    return target ? _summaryStripUrlTarget(target) : null;
  }

  if (['ffuf', 'gobuster', 'feroxbuster', 'katana', 'nikto'].includes(root)) {
    const target = _summaryFindFlagValue(tokens, ['-u', '--url', '-target', '--target']);
    return target ? _summaryStripUrlTarget(target.replace(/\/FUZZ\b.*$/i, '')) : null;
  }

  if (['nmap', 'rustscan', 'naabu', 'sslscan', 'sslyze', 'testssl'].includes(root)) {
    const positionals = _summaryPositionalTargets(tokens, {
      skipValuesAfter: new Set([
        '-p', '--ports', '--top-ports', '-oA', '-oG', '-oN', '-oX', '-iL',
        '--script', '--script-args', '--rate', '--timeout', '--host-timeout',
      ]),
      skipValuesForPrefix: /^-o[AGNX]$/i,
    }).filter((token) => !/^\d+(?:,\d+)*$/.test(token));
    return positionals.length ? positionals.join(', ') : null;
  }

  if (root === 'nc') {
    const positionals = _summaryPositionalTargets(tokens, {
      skipValuesAfter: new Set(['-w', '-i', '-s', '-p']),
    }).filter((token) => !/^\d+(?:-\d+)?$/.test(token));
    return positionals.length ? _summaryStripUrlTarget(positionals[0]) : null;
  }

  if (root === 'openssl') {
    const connect = _summaryFindFlagValue(tokens, ['-connect']);
    return connect ? _summaryStripUrlTarget(connect) : null;
  }

  return null;
}

function _summaryBlockSections(block, root = null) {
  return [
    ['findings', block.lines.filter((line) => _lineMatchesSearchScopeForRoot(line, 'findings', root)).map((line) => (line.textContent || '').trim()).filter(Boolean)],
    ['warnings', block.lines.filter((line) => _lineMatchesSearchScopeForRoot(line, 'warnings', root)).map((line) => (line.textContent || '').trim()).filter(Boolean)],
    ['errors', block.lines.filter((line) => _lineMatchesSearchScopeForRoot(line, 'errors', root)).map((line) => (line.textContent || '').trim()).filter(Boolean)],
    ['summaries', block.lines.filter((line) => _lineMatchesSearchScopeForRoot(line, 'summaries', root)).map((line) => (line.textContent || '').trim()).filter(Boolean)],
  ];
}

function _summarySectionsTotal(sections) {
  return sections.reduce((sum, [, lines]) => sum + lines.length, 0);
}

function _summaryBuildItems(blocks, tab) {
  return blocks.map((block, index) => {
    const commandLabel = block.command || String(tab?.command || '').trim() || `segment ${index + 1}`;
    const root = _summaryCommandRoot(commandLabel);
    const sections = _summaryBlockSections(block, root);
    const target = _summaryExtractTarget(commandLabel);
    return {
      command: commandLabel,
      sections,
      total: _summarySectionsTotal(sections),
      root,
      target,
    };
  }).filter((item) => item.total > 0);
}

function _summaryAppendSections(sections) {
  sections.forEach(([scope, lines]) => {
    if (!lines.length) return;
    appendLine(
      `${_SEARCH_SCOPE_LABELS[scope]} (${lines.length})`,
      'fake-signal-summary-section',
      activeTabId,
    );
    lines.slice(0, _SEARCH_SUMMARY_LIMIT).forEach((line) => {
      appendLine(`- ${line}`, 'fake-signal-summary-row', activeTabId);
    });
    if (lines.length > _SEARCH_SUMMARY_LIMIT) {
      appendLine(
        `… ${lines.length - _SEARCH_SUMMARY_LIMIT} more ${_searchScopeUnitLabel(scope, lines.length - _SEARCH_SUMMARY_LIMIT)} not shown`,
        'fake-signal-summary-note',
        activeTabId,
      );
    }
  });
}

function _summaryMergeSections(items) {
  return ['findings', 'warnings', 'errors', 'summaries'].map((scope) => {
    const lines = [];
    items.forEach((item) => {
      const section = item.sections.find(([candidate]) => candidate === scope);
      if (section) lines.push(...section[1]);
    });
    return [scope, lines];
  });
}

function _summaryGroupedItems(items) {
  const groups = [];
  items.forEach((item) => {
    if (!item.root || !item.target) return;
    let rootGroup = groups.find((group) => group.root === item.root);
    if (!rootGroup) {
      rootGroup = { root: item.root, targets: [] };
      groups.push(rootGroup);
    }
    let targetGroup = rootGroup.targets.find((group) => group.target === item.target);
    if (!targetGroup) {
      targetGroup = { target: item.target, items: [] };
      rootGroup.targets.push(targetGroup);
    }
    targetGroup.items.push(item);
  });
  return groups;
}

function _summaryRenderGroupedItems(items) {
  const groupedItems = items.filter((item) => item.root && item.target);
  if (!groupedItems.length) return 0;
  let rendered = 0;
  let renderedSections = 0;
  const groups = _summaryGroupedItems(groupedItems);
  groups.forEach((rootGroup) => {
    if (renderedSections > 0) appendLine('------------', 'fake-signal-summary-sep', activeTabId);
    appendLine(`command             ${rootGroup.root}`, 'fake-kv', activeTabId);
    rootGroup.targets.forEach((targetGroup, targetIndex) => {
      if (targetIndex > 0) appendLine('------------', 'fake-signal-summary-sep', activeTabId);
      appendLine(`target              ${targetGroup.target}`, 'fake-kv', activeTabId);
      if (targetGroup.items.length > 1) {
        appendLine(
          `full commands (${targetGroup.items.length})`,
          'fake-signal-summary-section',
          activeTabId,
        );
        targetGroup.items.forEach((item) => {
          appendLine(`- ${item.command}`, 'fake-signal-summary-row', activeTabId);
        });
      } else {
        appendLine(`full command        ${targetGroup.items[0].command}`, 'fake-kv', activeTabId);
      }
      _summaryAppendSections(_summaryMergeSections(targetGroup.items));
      rendered += targetGroup.items.length;
      renderedSections += 1;
    });
  });
  return rendered;
}

function _summaryRenderCommandItems(items) {
  items.forEach((item, index) => {
    if (index > 0) appendLine('------------', 'fake-signal-summary-sep', activeTabId);
    appendLine(`full command        ${item.command}`, 'fake-kv', activeTabId);
    _summaryAppendSections(item.sections);
  });
}

function summarizeCurrentOutputSignals() {
  const out = getOutput(activeTabId);
  if (!out || typeof appendLine !== 'function') return false;
  const tab = typeof getTab === 'function' ? getTab(activeTabId) : null;
  const blocks = _collectSearchCommandBlocks(out);
  if (!blocks.length) {
    const fallbackLines = Array.from(out.querySelectorAll('.line')).filter((line) => line instanceof Element);
    blocks.push({
      command: String(tab?.command || '').trim(),
      lines: fallbackLines,
    });
  }

  appendLine('[command findings]', 'fake-signal-summary-header', activeTabId);

  const items = _summaryBuildItems(blocks, tab);
  const groupedCount = _summaryRenderGroupedItems(items);
  const fallbackItems = items.filter((item) => !(item.root && item.target));
  if (groupedCount && fallbackItems.length) appendLine('------------', 'fake-signal-summary-sep', activeTabId);
  _summaryRenderCommandItems(fallbackItems);

  if (!items.length) {
    appendLine(
      'No findings, warnings, errors, or summary lines detected in this tab.',
      'fake-signal-summary-note',
      activeTabId,
    );
  }

  return true;
}

function _collectScopedSearchMatches(out, scope) {
  const lines = Array.from(out.querySelectorAll('.line'));
  const matches = [];
  let currentRoot = _summaryCommandRoot(String((typeof getTab === 'function' ? getTab(activeTabId) : null)?.command || ''));
  lines.forEach((line) => {
    if (!(line instanceof Element)) return;
    if (line.classList.contains('prompt-echo')) {
      currentRoot = _summaryCommandRoot(_promptEchoCommandText(line));
      return;
    }
    if (!_lineMatchesSearchScopeForRoot(line, scope, currentRoot)) return;
    line.classList.add('search-signal-hl');
    matches.push([line]);
  });
  return matches;
}

function runSearch() {
  clearHighlights();
  searchMatches = [];
  searchMatchIdx = -1;
  const out = getOutput(activeTabId);
  if (!out) return;
  refreshSearchDiscoverabilityUi();

  const scope = _getSearchScope();
  if (scope !== 'text') {
    searchMatches = _collectScopedSearchMatches(out, scope);
    _setSearchCount(searchMatches.length ? `1 / ${searchMatches.length}` : _searchNoMatchesLabel(scope));
    if (searchMatches.length) {
      searchMatchIdx = 0;
      highlightCurrent();
    }
    return;
  }

  const q = searchInput.value;
  if (!q) {
    _setSearchCount('');
    return;
  }
  const lines = out.querySelectorAll('.line');
  const flags = searchCaseSensitive ? 'g' : 'gi';
  const pattern = searchRegexMode ? q : escapeRegex(q);
  let re;
  try {
    re = new RegExp(pattern, flags);
  } catch (e) {
    _setSearchCount('invalid regex');
    return;
  }
  let globalMatchIdx = 0;
  lines.forEach((line) => {
    globalMatchIdx += _highlightSearchLine(line, re, globalMatchIdx);
  });
  // Group marks by logical match — a single match that crossed an inline
  // boundary produces multiple marks with the same data-search-match, and
  // nav/highlight should treat them as one.
  const groups = new Map();
  out.querySelectorAll('mark.search-hl').forEach((mark) => {
    const idx = Number(mark.dataset.searchMatch);
    if (!groups.has(idx)) groups.set(idx, []);
    groups.get(idx).push(mark);
  });
  searchMatches = Array.from(groups.values());
  _setSearchCount(searchMatches.length ? `1 / ${searchMatches.length}` : 'no matches');
  if (searchMatches.length) {
    searchMatchIdx = 0;
    highlightCurrent();
  }
}

function navigateSearch(dir) {
  if (!searchMatches.length) return;
  searchMatchIdx = (searchMatchIdx + dir + searchMatches.length) % searchMatches.length;
  _setSearchCount(`${searchMatchIdx + 1} / ${searchMatches.length}`);
  highlightCurrent();
}

function highlightCurrent() {
  searchMatches.forEach((group, i) => {
    group.forEach((node) => node.classList.toggle('current', i === searchMatchIdx));
  });
  searchMatches[searchMatchIdx]?.[0]?.scrollIntoView({ block: 'center' });
}

function clearHighlights() {
  const out = getOutput(activeTabId);
  if (!out) return;
  const touched = new Set();
  out.querySelectorAll('mark.search-hl').forEach((m) => {
    const line = m.closest('.line');
    if (line) touched.add(line);
    m.replaceWith(document.createTextNode(m.textContent));
  });
  out.querySelectorAll('.line.search-signal-hl').forEach((line) => {
    line.classList.remove('search-signal-hl', 'current');
  });
  // Re-merge adjacent text nodes on every touched line so the next search
  // walks a clean DOM instead of an accumulation of single-character
  // fragments left behind by prior highlight cycles.
  touched.forEach(line => line.normalize());
}

function clearSearch() {
  clearHighlights();
  searchMatches = [];
  searchMatchIdx = -1;
  _setSearchCount('');
  if (typeof searchInput !== 'undefined' && searchInput) searchInput.value = '';
  searchScope = 'text';
  syncSearchScopeUi();
  scheduleSearchDiscoverabilityRefresh();
}

syncSearchScopeUi();
refreshSearchDiscoverabilityUi();
