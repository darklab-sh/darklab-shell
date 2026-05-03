// ── Shared search logic ──

const _searchCore = typeof DarklabSearchCore !== 'undefined' ? DarklabSearchCore : null;
const _SEARCH_SCOPE_LABELS = _searchCore.SEARCH_SCOPE_LABELS;
const _SEARCH_SUMMARY_LIMIT = _searchCore.SEARCH_SUMMARY_LIMIT;
const _TERMINAL_SEARCH_DELAY_MS = 200;
const _TERMINAL_LARGE_SEARCH_DELAY_MS = 600;
const _TERMINAL_LARGE_SEARCH_LINE_THRESHOLD = 2000;
const _TERMINAL_LARGE_SEARCH_CHAR_THRESHOLD = 500000;
const _TERMINAL_LARGE_SEARCH_MIN_CHARS = 3;

let _searchTogglePulseTimer = null;
let _searchDiscoverabilityRefreshTimer = null;
let _searchDiscoverabilityRefreshTimerType = '';
let _terminalSearchTimer = null;
let _terminalLazyHighlightedMatch = null;
let _terminalSearchLazyMode = false;

function _getSearchScope() {
  return typeof searchScope === 'string' ? searchScope : 'text';
}

function _setSearchCount(text) {
  if (searchCount) searchCount.textContent = text;
}

function _searchScopeButtonLabel(scope, count) {
  return _searchCore.searchScopeButtonLabel(scope, count);
}

function _searchScopeUnitLabel(scope, count) {
  return _searchCore.searchScopeUnitLabel(scope, count);
}

function _formatFindingSummary(counts) {
  return _searchCore.formatFindingSummary(counts);
}

function _renderCompactSignalSummary(container, counts) {
  if (!(container instanceof Element)) return;
  container.replaceChildren();
  const chips = [
    ['findings', 'F', counts.findings],
    ['warnings', 'W', counts.warnings],
    ['errors', 'E', counts.errors],
    ['summaries', 'S', counts.summaries],
  ].filter(([, , count]) => count > 0);
  chips.forEach(([scope, short, count], index) => {
    if (index > 0) {
      const sep = document.createElement('span');
      sep.className = 'search-signal-sep';
      sep.setAttribute('aria-hidden', 'true');
      sep.textContent = '•';
      container.appendChild(sep);
    }
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn-ghost btn-compact search-signal-chip chip chip-action';
    button.dataset.searchSignalScope = scope;
    button.setAttribute('aria-label', `${count} ${_searchScopeUnitLabel(scope, count)} available`);
    button.textContent = `${count}${short}`;
    container.appendChild(button);
  });
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
  return _searchCore.searchNoMatchesLabel(scope);
}

function _searchInputPlaceholder(scope) {
  return _searchCore.searchInputPlaceholder(scope);
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

function _lineServerSignals(line) {
  if (!(line instanceof Element)) return [];
  const raw = String(line.dataset?.signals || '').trim();
  if (!raw) return [];
  return raw.split(',').map(signal => signal.trim()).filter(Boolean);
}

function _lineMatchesSearchScopeForRoot(line, scope, root = null) {
  if (!(line instanceof Element) || scope === 'text') return false;
  const serverSignals = _lineServerSignals(line);
  if (!serverSignals.includes(scope)) return false;
  if (
    line.classList.contains('builtin-signal-summary-header')
    || line.classList.contains('builtin-signal-summary-section')
    || line.classList.contains('builtin-signal-summary-row')
    || line.classList.contains('builtin-signal-summary-note')
    || line.classList.contains('builtin-signal-summary-sep')
  ) {
    return false;
  }
  const metadataRoot = String(line.dataset?.commandRoot || '').trim();
  const useRoot = metadataRoot || (root === null ? _lineCommandRoot(line) : root);
  if (_isBuiltinCommandRoot(useRoot)) return false;
  return true;
}

function _normalizeSearchSignalCounts(counts) {
  return _searchCore.normalizeSignalCounts(counts);
}

function _getCachedSearchSignalCounts() {
  const tab = typeof getTab === 'function' ? getTab(activeTabId) : null;
  if (!tab || tab._outputSignalCountsValid !== true || !tab._outputSignalCounts) return null;
  return _normalizeSearchSignalCounts(tab._outputSignalCounts);
}

function _getSearchSignalCounts(out) {
  const cached = _getCachedSearchSignalCounts();
  if (cached) return cached;
  const counts = { findings: 0, warnings: 0, errors: 0, summaries: 0 };
  if (!(out instanceof Element)) return counts;
  const lines = Array.from(out.querySelectorAll('.line'));
  lines.forEach((line) => {
    if (!(line instanceof Element)) return;
    if (line.classList.contains('prompt-echo')) return;
    if (_lineMatchesSearchScope(line, 'findings')) counts.findings += 1;
    if (_lineMatchesSearchScope(line, 'warnings')) counts.warnings += 1;
    if (_lineMatchesSearchScope(line, 'errors')) counts.errors += 1;
    if (_lineMatchesSearchScope(line, 'summaries')) counts.summaries += 1;
  });
  return counts;
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
    } else if (counts.findings <= 0 || (typeof isSearchBarOpen === 'function' && isSearchBarOpen())) {
      _clearSearchDiscoverabilityPulse();
    }
  }
  if (typeof searchSignalSummary !== 'undefined' && searchSignalSummary) {
    const hasSignals = counts.findings > 0 || counts.warnings > 0 || counts.errors > 0 || counts.summaries > 0;
    searchSignalSummary.classList.toggle('u-hidden', !hasSignals);
    _renderCompactSignalSummary(searchSignalSummary, counts);
    searchSignalSummary.title = hasSignals ? _formatFindingSummary(counts) : '';
    searchSignalSummary.setAttribute('aria-label', hasSignals ? _formatFindingSummary(counts) : '');
    if (hasSignals) {
      searchSignalSummary.querySelectorAll('[data-search-signal-scope]').forEach((btn) => {
        const activate = () => {
          if (typeof openSearchFromSignal === 'function') openSearchFromSignal(btn.dataset.searchSignalScope || 'text');
        };
        if (typeof bindPressable === 'function') {
          bindPressable(btn, {
            refocusComposer: true,
            onActivate: (event) => {
              event.preventDefault();
              activate();
            },
          });
        } else {
          btn.addEventListener('click', activate);
        }
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
  refreshSearchDiscoverabilityUi();
  searchScope = 'text';
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

function _clearTextSearchHighlights(root) {
  if (!(root instanceof Element)) return;
  const touched = new Set();
  root.querySelectorAll('mark.search-hl').forEach((m) => {
    const line = m.closest('.line, .workspace-line-row');
    if (line) touched.add(line);
    m.replaceWith(document.createTextNode(m.textContent));
  });
  touched.forEach(line => line.normalize());
}

function _collectTextSearchMatches(root, query, {
  caseSensitive = false,
  regexMode = false,
  lineSelector = '.line',
} = {}) {
  if (!(root instanceof Element) || !query) return { matches: [], error: '' };
  const flags = caseSensitive ? 'g' : 'gi';
  const pattern = regexMode ? query : escapeRegex(query);
  let re;
  try {
    re = new RegExp(pattern, flags);
  } catch (_) {
    return { matches: [], error: 'invalid regex' };
  }
  let globalMatchIdx = 0;
  root.querySelectorAll(lineSelector).forEach((line) => {
    globalMatchIdx += _highlightSearchLine(line, re, globalMatchIdx);
  });
  const groups = new Map();
  root.querySelectorAll('mark.search-hl').forEach((mark) => {
    const idx = Number(mark.dataset.searchMatch);
    if (!groups.has(idx)) groups.set(idx, []);
    groups.get(idx).push(mark);
  });
  return { matches: Array.from(groups.values()), error: '' };
}

function _collectLazyTextSearchMatches(root, query, {
  caseSensitive = false,
  regexMode = false,
  lineSelector = '.line',
  lineTextSelector = null,
  preserveDom = false,
} = {}) {
  if (!(root instanceof Element) || !query) return { matches: [], error: '' };
  const flags = caseSensitive ? 'g' : 'gi';
  const pattern = regexMode ? query : escapeRegex(query);
  let re;
  try {
    re = new RegExp(pattern, flags);
  } catch (_) {
    return { matches: [], error: 'invalid regex' };
  }
  const matches = [];
  root.querySelectorAll(lineSelector).forEach((line) => {
    if (!(line instanceof Element)) return;
    const textEl = lineTextSelector ? line.querySelector(lineTextSelector) : line;
    if (!(textEl instanceof Element)) return;
    const text = textEl.textContent || '';
    re.lastIndex = 0;
    let match;
    while ((match = re.exec(text)) !== null) {
      if (!match[0]) {
        re.lastIndex += 1;
        continue;
      }
      matches.push({
        line,
        textEl,
        text,
        start: match.index,
        end: match.index + match[0].length,
        preserveDom,
      });
    }
  });
  return { matches, error: '' };
}

function _clearLazySearchHighlight(match) {
  const textEl = match?.textEl;
  if (!(textEl instanceof Element)) return;
  if (match?.preserveDom && Array.isArray(match.originalChildNodes)) {
    textEl.replaceChildren(...match.originalChildNodes.map(node => node.cloneNode(true)));
    match.originalChildNodes = null;
    return;
  }
  textEl.textContent = String(match?.text || textEl.textContent || '');
}

function _highlightLazySearchMatch(match, index) {
  const textEl = match?.textEl;
  if (!(textEl instanceof Element)) return null;
  const text = String(match?.text || '');
  const start = Math.max(0, Number(match?.start) || 0);
  const end = Math.max(start, Number(match?.end) || start);
  const frag = document.createDocumentFragment();
  frag.appendChild(document.createTextNode(text.slice(0, start)));
  const mark = document.createElement('mark');
  mark.className = 'search-hl current';
  mark.dataset.searchMatch = String(index);
  mark.textContent = text.slice(start, end);
  frag.appendChild(mark);
  frag.appendChild(document.createTextNode(text.slice(end)));
  if (match?.preserveDom && !Array.isArray(match.originalChildNodes)) {
    match.originalChildNodes = Array.from(textEl.childNodes).map(node => node.cloneNode(true));
  }
  textEl.replaceChildren(frag);
  return mark;
}

function createTextSearchController({
  root,
  input,
  countEl,
  caseBtn = null,
  regexBtn = null,
  prevBtn = null,
  nextBtn = null,
  lineSelector = '.line',
  getRoot = null,
  searchDelayMs = 0,
  minQueryLength = 0,
  minQueryMessage = '',
  lazyHighlight = false,
  lineTextSelector = null,
} = {}) {
  let matches = [];
  let matchIdx = -1;
  let caseSensitive = false;
  let regexMode = false;
  let pendingSearchTimer = null;
  let lazyHighlightedMatch = null;
  const currentRoot = () => (typeof getRoot === 'function' ? getRoot() : root);
  const setCount = text => { if (countEl) countEl.textContent = text; };
  const cancelPendingSearch = () => {
    if (pendingSearchTimer !== null) {
      clearTimeout(pendingSearchTimer);
      pendingSearchTimer = null;
    }
  };
  const clearLazyHighlight = () => {
    _clearLazySearchHighlight(lazyHighlightedMatch);
    lazyHighlightedMatch = null;
  };
  const highlight = () => {
    if (lazyHighlight) {
      clearLazyHighlight();
      const currentMatch = matches[matchIdx];
      const current = _highlightLazySearchMatch(currentMatch, matchIdx);
      lazyHighlightedMatch = currentMatch || null;
      if (current && typeof current.scrollIntoView === 'function') {
        current.scrollIntoView({ block: 'center' });
      }
      return;
    }
    matches.forEach((group, i) => {
      group.forEach((node) => node.classList.toggle('current', i === matchIdx));
    });
    const current = matches[matchIdx]?.[0];
    if (current && typeof current.scrollIntoView === 'function') {
      current.scrollIntoView({ block: 'center' });
    }
  };
  const run = () => {
    cancelPendingSearch();
    const targetRoot = currentRoot();
    if (lazyHighlight) clearLazyHighlight();
    else _clearTextSearchHighlights(targetRoot);
    matches = [];
    matchIdx = -1;
    const query = String(input?.value || '');
    if (!query) {
      setCount('');
      return matches;
    }
    if (minQueryLength > 0 && query.length < minQueryLength) {
      setCount(minQueryMessage || `type ${minQueryLength}+ chars`);
      return matches;
    }
    const result = lazyHighlight
      ? _collectLazyTextSearchMatches(targetRoot, query, { caseSensitive, regexMode, lineSelector, lineTextSelector })
      : _collectTextSearchMatches(targetRoot, query, { caseSensitive, regexMode, lineSelector });
    if (result.error) {
      setCount(result.error);
      return matches;
    }
    matches = result.matches;
    setCount(matches.length ? `1 / ${matches.length}` : 'no matches');
    if (matches.length) {
      matchIdx = 0;
      highlight();
    }
    return matches;
  };
  const scheduleRun = () => {
    cancelPendingSearch();
    const query = String(input?.value || '');
    if (minQueryLength > 0 && query.length < minQueryLength) {
      run();
      return;
    }
    if (!searchDelayMs || !query) {
      run();
      return;
    }
    setCount('searching...');
    pendingSearchTimer = setTimeout(() => {
      pendingSearchTimer = null;
      run();
    }, searchDelayMs);
  };
  const navigate = (dir) => {
    if (!matches.length) return;
    matchIdx = (matchIdx + dir + matches.length) % matches.length;
    setCount(`${matchIdx + 1} / ${matches.length}`);
    highlight();
  };
  const clear = () => {
    cancelPendingSearch();
    if (lazyHighlight) clearLazyHighlight();
    else _clearTextSearchHighlights(currentRoot());
    matches = [];
    matchIdx = -1;
    setCount('');
    if (input) input.value = '';
  };
  input?.addEventListener('input', scheduleRun);
  input?.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      event.preventDefault();
      event.stopPropagation();
      if (pendingSearchTimer !== null) run();
      navigate(event.shiftKey ? -1 : 1);
      if (input && document.activeElement !== input && typeof input.focus === 'function') {
        input.focus({ preventScroll: true });
      }
    }
  });
  prevBtn?.addEventListener('click', () => navigate(-1));
  nextBtn?.addEventListener('click', () => navigate(1));
  caseBtn?.addEventListener('click', () => {
    caseSensitive = !caseSensitive;
    caseBtn.setAttribute('aria-pressed', caseSensitive ? 'true' : 'false');
    run();
  });
  regexBtn?.addEventListener('click', () => {
    regexMode = !regexMode;
    regexBtn.setAttribute('aria-pressed', regexMode ? 'true' : 'false');
    run();
  });
  return {
    run,
    navigate,
    clear,
    get matches() { return matches; },
    get matchIdx() { return matchIdx; },
    setCaseSensitive(value) {
      caseSensitive = !!value;
      caseBtn?.setAttribute('aria-pressed', caseSensitive ? 'true' : 'false');
    },
    setRegexMode(value) {
      regexMode = !!value;
      regexBtn?.setAttribute('aria-pressed', regexMode ? 'true' : 'false');
    },
  };
}

function _promptEchoCommandText(line) {
  if (!(line instanceof Element)) return '';
  const text = (line.textContent || '').trim();
  const prefix = String(line.querySelector('.prompt-prefix')?.textContent || '').trim();
  if (prefix && text.startsWith(prefix)) return text.slice(prefix.length).trim();
  return text.replace(/^\$\s*/, '').trim();
}

function _summaryCommandRoot(command) {
  return _searchCore.summaryCommandRoot(command);
}

function _lineCommandRoot(line) {
  if (line instanceof Element) {
    const metadataRoot = String(line.dataset?.commandRoot || '').trim();
    if (metadataRoot) return metadataRoot;
  }
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
      line.classList.contains('builtin-signal-summary-header')
      || line.classList.contains('builtin-signal-summary-section')
      || line.classList.contains('builtin-signal-summary-row')
      || line.classList.contains('builtin-signal-summary-note')
      || line.classList.contains('builtin-signal-summary-sep')
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

function _summaryBlockSections(block, root = null) {
  return [
    ['findings', block.lines.filter((line) => _lineMatchesSearchScopeForRoot(line, 'findings', root)).map((line) => (line.textContent || '').trim()).filter(Boolean)],
    ['warnings', block.lines.filter((line) => _lineMatchesSearchScopeForRoot(line, 'warnings', root)).map((line) => (line.textContent || '').trim()).filter(Boolean)],
    ['errors', block.lines.filter((line) => _lineMatchesSearchScopeForRoot(line, 'errors', root)).map((line) => (line.textContent || '').trim()).filter(Boolean)],
    ['summaries', block.lines.filter((line) => _lineMatchesSearchScopeForRoot(line, 'summaries', root)).map((line) => (line.textContent || '').trim()).filter(Boolean)],
  ];
}

function _summaryFirstLineDatasetValue(lines, name) {
  for (const line of Array.isArray(lines) ? lines : []) {
    if (!(line instanceof Element)) continue;
    const value = String(line.dataset?.[name] || '').trim();
    if (value) return value;
  }
  return '';
}

function _summarySectionsTotal(sections) {
  return _searchCore.summarySectionsTotal(sections);
}

function _summaryBuildItems(blocks, tab) {
  const items = [];
  blocks.forEach((block, index) => {
    const commandLabel = block.command || String(tab?.command || '').trim() || `segment ${index + 1}`;
    const root = _summaryFirstLineDatasetValue(block.lines, 'commandRoot') || _summaryCommandRoot(commandLabel);
    const targetBuckets = new Map();
    const ungroupedLines = [];
    (Array.isArray(block.lines) ? block.lines : []).forEach((line) => {
      if (!(line instanceof Element)) return;
      const target = String(line.dataset?.signalTarget || '').trim();
      if (!target) {
        ungroupedLines.push(line);
        return;
      }
      if (!targetBuckets.has(target)) targetBuckets.set(target, []);
      targetBuckets.get(target).push(line);
    });

    if (targetBuckets.size) {
      targetBuckets.forEach((lines, target) => {
        const sections = _summaryBlockSections({ command: commandLabel, lines }, root);
        items.push({
          command: commandLabel,
          sections,
          total: _summarySectionsTotal(sections),
          root,
          target,
        });
      });
      if (ungroupedLines.length) {
        const sections = _summaryBlockSections({ command: commandLabel, lines: ungroupedLines }, root);
        items.push({
          command: commandLabel,
          sections,
          total: _summarySectionsTotal(sections),
          root,
          target: '',
        });
      }
      return;
    }

    const sections = _summaryBlockSections(block, root);
    items.push({
      command: commandLabel,
      sections,
      total: _summarySectionsTotal(sections),
      root,
      target: '',
    });
  });
  return items.filter((item) => item.total > 0);
}

function _summaryAppendSections(sections) {
  sections.forEach(([scope, lines]) => {
    if (!lines.length) return;
    const compactLines = _summaryCompactLines(lines);
    appendLine(
      `${_SEARCH_SCOPE_LABELS[scope]} (${compactLines.length})`,
      'builtin-signal-summary-section',
      activeTabId,
    );
    compactLines.slice(0, _SEARCH_SUMMARY_LIMIT).forEach((line) => {
      appendLine(`- ${line}`, 'builtin-signal-summary-row', activeTabId);
    });
    if (compactLines.length > _SEARCH_SUMMARY_LIMIT) {
      appendLine(
        `… ${compactLines.length - _SEARCH_SUMMARY_LIMIT} more ${_searchScopeUnitLabel(scope, compactLines.length - _SEARCH_SUMMARY_LIMIT)} not shown`,
        'builtin-signal-summary-note',
        activeTabId,
      );
    }
  });
}

function _summaryCompactLines(lines) {
  return _searchCore.summaryCompactLines(lines);
}

function _summaryMergeSections(items) {
  return _searchCore.summaryMergeSections(items);
}

function _summaryGroupedItems(items) {
  return _searchCore.summaryGroupedItems(items);
}

function _summaryCommandLabels(items) {
  return _searchCore.summaryCommandLabels(items);
}

function _summaryRenderGroupedItems(items) {
  const groupedItems = items.filter((item) => item.root && item.target);
  if (!groupedItems.length) return 0;
  let rendered = 0;
  let renderedSections = 0;
  const groups = _summaryGroupedItems(groupedItems);
  groups.forEach((rootGroup) => {
    if (renderedSections > 0) appendLine('------------', 'builtin-signal-summary-sep', activeTabId);
    appendLine(`command             ${rootGroup.root}`, 'builtin-kv', activeTabId);
    rootGroup.targets.forEach((targetGroup, targetIndex) => {
      if (targetIndex > 0) appendLine('------------', 'builtin-signal-summary-sep', activeTabId);
      appendLine(`target              ${targetGroup.target}`, 'builtin-kv', activeTabId);
      if (targetGroup.items.length > 1) {
        const commandLabels = _summaryCommandLabels(targetGroup.items);
        appendLine(
          `full commands (${commandLabels.length})`,
          'builtin-signal-summary-section',
          activeTabId,
        );
        commandLabels.forEach((command) => {
          appendLine(`- ${command}`, 'builtin-signal-summary-row', activeTabId);
        });
      } else {
        appendLine(`full command        ${targetGroup.items[0].command}`, 'builtin-kv', activeTabId);
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
    if (index > 0) appendLine('------------', 'builtin-signal-summary-sep', activeTabId);
    appendLine(`full command        ${item.command}`, 'builtin-kv', activeTabId);
    _summaryAppendSections(item.sections);
  });
}

function summarizeCurrentOutputSignals() {
  const out = getOutput(activeTabId);
  if (!out || typeof appendLine !== 'function') return false;
  const tab = typeof getTab === 'function' ? getTab(activeTabId) : null;
  const blocks = _collectSearchCommandBlocks(out);
  if (!blocks.length) {
    const transcriptLines = Array.from(out.querySelectorAll('.line')).filter((line) => line instanceof Element);
    blocks.push({
      command: String(tab?.command || '').trim(),
      lines: transcriptLines,
    });
  }

  appendLine('Command Findings:', 'builtin-signal-summary-header', activeTabId);

  const items = _summaryBuildItems(blocks, tab);
  const groupedCount = _summaryRenderGroupedItems(items);
  const ungroupedItems = items.filter((item) => !(item.root && item.target));
  if (groupedCount && ungroupedItems.length) appendLine('------------', 'builtin-signal-summary-sep', activeTabId);
  _summaryRenderCommandItems(ungroupedItems);

  if (!items.length) {
    appendLine(
      'No findings, warnings, errors, or summary lines detected in this tab.',
      'builtin-signal-summary-note',
      activeTabId,
    );
  }

  return true;
}

function _collectScopedSearchMatches(out, scope) {
  const lines = Array.from(out.querySelectorAll('.line'));
  const matches = [];
  lines.forEach((line) => {
    if (!(line instanceof Element)) return;
    if (line.classList.contains('prompt-echo')) return;
    if (!_lineMatchesSearchScope(line, scope)) return;
    line.classList.add('search-signal-hl');
    matches.push([line]);
  });
  return matches;
}

function _clearTerminalSearchTimer() {
  if (_terminalSearchTimer !== null) {
    clearTimeout(_terminalSearchTimer);
    _terminalSearchTimer = null;
  }
}

function _clearTerminalLazyHighlight() {
  _clearLazySearchHighlight(_terminalLazyHighlightedMatch);
  _terminalLazyHighlightedMatch = null;
}

function _terminalOutputSearchStats(out) {
  let lineCount = 0;
  let charCount = 0;
  if (!(out instanceof Element)) return { lineCount, charCount };
  out.querySelectorAll('.line').forEach((line) => {
    lineCount += 1;
    charCount += (line.textContent || '').length;
  });
  return { lineCount, charCount };
}

function _terminalUsesLargeSearchMode(out) {
  const { lineCount, charCount } = _terminalOutputSearchStats(out);
  return (
    lineCount >= _TERMINAL_LARGE_SEARCH_LINE_THRESHOLD ||
    charCount >= _TERMINAL_LARGE_SEARCH_CHAR_THRESHOLD
  );
}

function _scrollTerminalLazySearchMatchIntoView(match, mark) {
  const out = getOutput(activeTabId);
  const line = match?.line;
  if (out instanceof Element && line instanceof Element && out.contains(line)) {
    const outRect = out.getBoundingClientRect();
    const lineRect = line.getBoundingClientRect();
    const targetTop = Number(lineRect.top) - Number(outRect.top);
    const lineHeight = Number(lineRect.height) || 0;
    const outHeight = Number(out.clientHeight) || Number(outRect.height) || 0;
    if (Number.isFinite(targetTop) && outHeight > 0) {
      out.scrollTop += targetTop - (outHeight / 2) + (lineHeight / 2);
      return;
    }
  }
  if (mark && typeof mark.scrollIntoView === 'function') {
    mark.scrollIntoView({ block: 'center' });
  }
}

function runSearch() {
  _clearTerminalSearchTimer();
  clearHighlights();
  searchMatches = [];
  searchMatchIdx = -1;
  _terminalSearchLazyMode = false;
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
  const useLargeSearch = _terminalUsesLargeSearchMode(out);
  if (useLargeSearch && q.length < _TERMINAL_LARGE_SEARCH_MIN_CHARS) {
    _setSearchCount(`type ${_TERMINAL_LARGE_SEARCH_MIN_CHARS}+ chars`);
    return;
  }
  _terminalSearchLazyMode = useLargeSearch;
  const result = useLargeSearch
    ? _collectLazyTextSearchMatches(out, q, {
      caseSensitive: searchCaseSensitive,
      regexMode: searchRegexMode,
      lineSelector: '.line',
      preserveDom: true,
    })
    : _collectTextSearchMatches(out, q, {
      caseSensitive: searchCaseSensitive,
      regexMode: searchRegexMode,
      lineSelector: '.line',
    });
  if (result.error) {
    _setSearchCount(result.error);
    _terminalSearchLazyMode = false;
    return;
  }
  searchMatches = result.matches;
  _setSearchCount(searchMatches.length ? `1 / ${searchMatches.length}` : 'no matches');
  if (searchMatches.length) {
    searchMatchIdx = 0;
    highlightCurrent();
  }
}

function scheduleRunSearch() {
  _clearTerminalSearchTimer();
  const out = getOutput(activeTabId);
  const query = String(searchInput?.value || '');
  const useLargeSearch = _terminalUsesLargeSearchMode(out);
  if (!query || (useLargeSearch && query.length < _TERMINAL_LARGE_SEARCH_MIN_CHARS)) {
    runSearch();
    return;
  }
  _setSearchCount('searching...');
  _terminalSearchTimer = setTimeout(() => {
    _terminalSearchTimer = null;
    runSearch();
  }, useLargeSearch ? _TERMINAL_LARGE_SEARCH_DELAY_MS : _TERMINAL_SEARCH_DELAY_MS);
}

function navigateSearch(dir) {
  if (_terminalSearchTimer !== null) runSearch();
  if (!searchMatches.length) return;
  searchMatchIdx = (searchMatchIdx + dir + searchMatches.length) % searchMatches.length;
  _setSearchCount(`${searchMatchIdx + 1} / ${searchMatches.length}`);
  highlightCurrent();
}

function highlightCurrent() {
  if (_terminalSearchLazyMode) {
    _clearTerminalLazyHighlight();
    const currentMatch = searchMatches[searchMatchIdx];
    const current = _highlightLazySearchMatch(currentMatch, searchMatchIdx);
    _terminalLazyHighlightedMatch = currentMatch || null;
    _scrollTerminalLazySearchMatchIntoView(currentMatch, current);
    return;
  }
  searchMatches.forEach((group, i) => {
    group.forEach((node) => node.classList.toggle('current', i === searchMatchIdx));
  });
  const current = searchMatches[searchMatchIdx]?.[0];
  if (current && typeof current.scrollIntoView === 'function') {
    current.scrollIntoView({ block: 'center' });
  }
}

function clearHighlights() {
  const out = getOutput(activeTabId);
  if (!out) return;
  _clearTerminalLazyHighlight();
  _clearTextSearchHighlights(out);
  out.querySelectorAll('.line.search-signal-hl').forEach((line) => {
    line.classList.remove('search-signal-hl', 'current');
  });
}

function clearSearch() {
  _clearTerminalSearchTimer();
  clearHighlights();
  searchMatches = [];
  searchMatchIdx = -1;
  _terminalSearchLazyMode = false;
  _setSearchCount('');
  if (typeof searchInput !== 'undefined' && searchInput) searchInput.value = '';
  searchScope = 'text';
  syncSearchScopeUi();
  scheduleSearchDiscoverabilityRefresh();
}

syncSearchScopeUi();
refreshSearchDiscoverabilityUi();
