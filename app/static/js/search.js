// ── Shared search logic ──

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

function _lineServerSignals(line) {
  if (!(line instanceof Element)) return [];
  const raw = String(line.dataset?.signals || '').trim();
  if (!raw) return [];
  return raw.split(',').map(signal => signal.trim()).filter(Boolean);
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
  const metadataRoot = String(line.dataset?.commandRoot || '').trim();
  const useRoot = metadataRoot || (root === null ? _lineCommandRoot(line) : root);
  if (_isBuiltinCommandRoot(useRoot)) return false;
  const serverSignals = _lineServerSignals(line);
  return serverSignals.includes(scope);
}

function _getSearchSignalCounts(out) {
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

function _summaryCommandRoot(command) {
  return String(command || '').trim().split(/\s+/, 1)[0]?.toLowerCase() || '';
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
  return sections.reduce((sum, [, lines]) => sum + lines.length, 0);
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
      'fake-signal-summary-section',
      activeTabId,
    );
    compactLines.slice(0, _SEARCH_SUMMARY_LIMIT).forEach((line) => {
      appendLine(`- ${line}`, 'fake-signal-summary-row', activeTabId);
    });
    if (compactLines.length > _SEARCH_SUMMARY_LIMIT) {
      appendLine(
        `… ${compactLines.length - _SEARCH_SUMMARY_LIMIT} more ${_searchScopeUnitLabel(scope, compactLines.length - _SEARCH_SUMMARY_LIMIT)} not shown`,
        'fake-signal-summary-note',
        activeTabId,
      );
    }
  });
}

function _summaryCompactLines(lines) {
  const counts = new Map();
  const ordered = [];
  (Array.isArray(lines) ? lines : []).forEach((line) => {
    const text = String(line || '').trim();
    if (!text) return;
    if (!counts.has(text)) {
      ordered.push(text);
      counts.set(text, 0);
    }
    counts.set(text, counts.get(text) + 1);
  });
  return ordered.map((line) => {
    const count = counts.get(line) || 0;
    return count > 1 ? `${line} (${count})` : line;
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

function _summaryCommandLabels(items) {
  const counts = new Map();
  const ordered = [];
  items.forEach((item) => {
    const command = String(item?.command || '').trim();
    if (!command) return;
    if (!counts.has(command)) {
      ordered.push(command);
      counts.set(command, 0);
    }
    counts.set(command, counts.get(command) + 1);
  });
  return ordered.map((command) => {
    const count = counts.get(command) || 0;
    return count > 1 ? `${command} (${count})` : command;
  });
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
        const commandLabels = _summaryCommandLabels(targetGroup.items);
        appendLine(
          `full commands (${commandLabels.length})`,
          'fake-signal-summary-section',
          activeTabId,
        );
        commandLabels.forEach((command) => {
          appendLine(`- ${command}`, 'fake-signal-summary-row', activeTabId);
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
    const transcriptLines = Array.from(out.querySelectorAll('.line')).filter((line) => line instanceof Element);
    blocks.push({
      command: String(tab?.command || '').trim(),
      lines: transcriptLines,
    });
  }

  appendLine('Command Findings:', 'fake-signal-summary-header', activeTabId);

  const items = _summaryBuildItems(blocks, tab);
  const groupedCount = _summaryRenderGroupedItems(items);
  const ungroupedItems = items.filter((item) => !(item.root && item.target));
  if (groupedCount && ungroupedItems.length) appendLine('------------', 'fake-signal-summary-sep', activeTabId);
  _summaryRenderCommandItems(ungroupedItems);

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
  lines.forEach((line) => {
    if (!(line instanceof Element)) return;
    if (line.classList.contains('prompt-echo')) return;
    if (!_lineMatchesSearchScope(line, scope)) return;
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
