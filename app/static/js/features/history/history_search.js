// darklab_shell history search module.
// Ctrl+R reverse-history search for the command composer.

let _histSearchMode = false;
let _histSearchQuery = '';
let _histSearchIndex = -1;
let _histSearchPreDraft = '';
let _histSearchRuns = null;     // null = not yet fetched; string[] = ready
let _histSearchFetchTimer = null;

function isHistSearchMode() { return _histSearchMode; }

function _histSearchMatches() {
  if (!_histSearchQuery) return [];
  // Always include client-side matches from the in-memory recents so the
  // dropdown can't "clear" on the user when a server fetch returns fewer
  // items (or is stale from a prior keystroke). This mirrors bash reverse-
  // i-search, which searches in-memory history. Server results extend this
  // list with older runs beyond the recents cap; both lists are re-filtered
  // against the current query to guard against race conditions.
  const q = String(_histSearchQuery || '').toLowerCase();
  const fromClient = cmdHistory.filter(c => c.toLowerCase().includes(q));
  const seen = new Set();
  const merged = [];
  for (const cmd of fromClient) {
    if (!seen.has(cmd)) { merged.push(cmd); seen.add(cmd); }
  }
  if (_histSearchRuns !== null) {
    for (const cmd of _histSearchRuns) {
      if (!seen.has(cmd) && (!q || cmd.toLowerCase().includes(q))) {
        merged.push(cmd);
        seen.add(cmd);
      }
    }
  }
  return merged.slice(0, 10);
}

// Fetch /history?q=<query> from the server (same endpoint as the drawer).
// The query filter is applied server-side before LIMIT, so searches match
// the full history, not just the most-recent-N unfiltered runs.
// scope=command keeps this bash-like: match typed command text only, not
// output text (which FTS would otherwise mix in and surface unrelated runs).
function _histSearchFetch(q) {
  const query = String(q || '');
  const params = new URLSearchParams({ type: 'runs', scope: 'command' });
  if (query) params.set('q', query);
  const url = `/history?${params.toString()}`;
  apiFetch(url).then(r => r.json()).then(data => {
    if (!_histSearchMode) return;
    _histSearchRuns = Array.isArray(data.runs)
      ? [...new Set(data.runs.map(r => r.command))]
      : [];
    _histSearchIndex = _histSearchRuns.length > 0 ? 0 : -1;
    _renderHistSearch();
  }).catch(() => {
    if (_histSearchRuns === null) _histSearchRuns = [];
  });
}

function _hideHistSearchDropdown() {
  if (histSearchDropdown) histSearchDropdown.classList.add('u-hidden');
}

function _moveHistSearchSelection(delta) {
  const matches = _histSearchMatches();
  if (!matches.length) return false;
  if (_histSearchIndex < 0) {
    _histSearchIndex = delta < 0 ? matches.length - 1 : 0;
  } else {
    _histSearchIndex = (_histSearchIndex + delta + matches.length) % matches.length;
  }
  _renderHistSearch();
  return true;
}

function _renderHistSearch() {
  // Reverse-i-search intentionally mirrors shell behavior: current query at the
  // top, most relevant match preselected, and wraparound keyboard navigation.
  if (!histSearchDropdown) return;
  const matches = _histSearchMatches();
  histSearchDropdown.replaceChildren();

  const header = document.createElement('div');
  header.className = 'hist-search-header';
  const label = document.createElement('span');
  label.className = 'hist-search-label';
  label.textContent = 'reverse-i-search: ';
  const querySpan = document.createElement('span');
  querySpan.className = 'hist-search-query';
  querySpan.textContent = _histSearchQuery || '';
  header.appendChild(label);
  header.appendChild(querySpan);
  histSearchDropdown.appendChild(header);

  if (!matches.length) {
    const empty = document.createElement('div');
    empty.className = 'hist-search-empty';
    empty.textContent = '(no matches)';
    histSearchDropdown.appendChild(empty);
  } else {
    matches.forEach((cmd, i) => {
      const item = document.createElement('div');
      item.className = 'hist-search-item dropdown-item dropdown-item-compact'
        + (i === _histSearchIndex ? ' active dropdown-item-active' : '');
      if (_histSearchQuery) {
        const lower = cmd.toLowerCase();
        const qi = lower.indexOf(_histSearchQuery.toLowerCase());
        if (qi >= 0) {
          item.appendChild(document.createTextNode(cmd.slice(0, qi)));
          const mark = document.createElement('mark');
          mark.className = 'hist-search-match';
          mark.textContent = cmd.slice(qi, qi + _histSearchQuery.length);
          item.appendChild(mark);
          item.appendChild(document.createTextNode(cmd.slice(qi + _histSearchQuery.length)));
        } else {
          item.textContent = cmd;
        }
      } else {
        item.textContent = cmd;
      }
      item.addEventListener('mousedown', e => {
        e.preventDefault();
        _histSearchIndex = i;
        exitHistSearch(true);
      });
      histSearchDropdown.appendChild(item);
    });
  }

  // Flip above/below based on available space, mirroring the ac-dropdown so
  // the list stays on-screen when the prompt is near the top of the viewport.
  histSearchDropdown.classList.remove('u-hidden');
  if (shellPromptWrap) {
    const rect = shellPromptWrap.getBoundingClientRect();
    histSearchDropdown.style.position = 'fixed';
    histSearchDropdown.style.left = rect.left + 'px';
    histSearchDropdown.style.width = rect.width + 'px';
    histSearchDropdown.style.bottom = 'auto';
    histSearchDropdown.style.maxHeight = '';
    const desired = histSearchDropdown.offsetHeight;
    const spaceBelow = Math.max(0, window.innerHeight - rect.bottom - 8);
    const spaceAbove = Math.max(0, rect.top - 8);
    const safetyPad = 20;
    const canFitBelow = spaceBelow >= (desired + safetyPad);
    const canFitAbove = spaceAbove >= (desired + safetyPad);
    const showAbove = canFitAbove && (!canFitBelow || spaceAbove >= spaceBelow);
    const available = showAbove ? spaceAbove : spaceBelow;
    const edgeBuffer = showAbove ? 20 : 30;
    const maxHeight = Math.max(0, available > edgeBuffer ? available - edgeBuffer : available);
    const visibleHeight = Math.max(0, Math.min(desired, maxHeight || desired));
    histSearchDropdown.style.maxHeight = `${Math.round(maxHeight)}px`;
    histSearchDropdown.style.top = showAbove
      ? `${Math.max(8, Math.round(rect.top - visibleHeight - 4))}px`
      : `${Math.max(8, Math.round(rect.bottom + 4))}px`;
  }
}

function enterHistSearch() {
  if (_histSearchMode) {
    // Ctrl+R again: cycle to next match
    _moveHistSearchSelection(1);
    return;
  }
  _histSearchMode = true;
  _histSearchQuery = '';
  _histSearchIndex = -1;
  _histSearchPreDraft = (typeof getComposerValue === 'function') ? getComposerValue() : (cmdInput ? cmdInput.value : '');
  // Clear the input so the user types a fresh query rather than appending to the draft.
  // The draft is preserved in _histSearchPreDraft and restored on Escape / Ctrl+G.
  if (typeof setComposerValue === 'function') {
    setComposerValue('', 0, 0, { dispatch: false });
  }
  if (typeof acHide === 'function') acHide();

  _histSearchRuns = null;
  _renderHistSearch();
}

function exitHistSearch(accept, { keepCurrent = false } = {}) {
  if (!_histSearchMode) return;
  _histSearchMode = false;
  _hideHistSearchDropdown();
  if (accept) {
    const matches = _histSearchMatches();
    const chosen = _histSearchIndex >= 0 ? matches[_histSearchIndex] : (matches[0] || _histSearchPreDraft);
    if (typeof setComposerValue === 'function') {
      setComposerValue(chosen, chosen.length, chosen.length);
    }
  } else if (!keepCurrent) {
    if (typeof setComposerValue === 'function') {
      setComposerValue(_histSearchPreDraft, _histSearchPreDraft.length, _histSearchPreDraft.length);
    }
  }
  _histSearchQuery = '';
  _histSearchIndex = -1;
  _histSearchPreDraft = '';
  _histSearchRuns = null;
  if (_histSearchFetchTimer) { clearTimeout(_histSearchFetchTimer); _histSearchFetchTimer = null; }
  if (typeof acHide === 'function') acHide();
}

function handleHistSearchInput(value) {
  _histSearchQuery = value;
  _histSearchIndex = -1;
  if (_histSearchFetchTimer) { clearTimeout(_histSearchFetchTimer); _histSearchFetchTimer = null; }
  if (!value) {
    _histSearchRuns = null;
    _renderHistSearch();
    return;
  }
  // Initialise index from the current pool (cmdHistory fallback or previous fetch results)
  // so keyboard navigation works immediately while the server fetch is in-flight.
  const matches = _histSearchMatches();
  if (matches.length > 0) _histSearchIndex = 0;
  _renderHistSearch();
  // Re-fetch with the new query so the server applies the filter before LIMIT.
  _histSearchFetchTimer = setTimeout(() => {
    _histSearchFetchTimer = null;
    _histSearchFetch(value);
  }, 120);
}

function handleHistSearchKey(e) {
  if (!_histSearchMode) return false;
  if (e.key === 'Escape') {
    e.preventDefault();
    exitHistSearch(false);
    return true;
  }
  if (e.key === 'Enter') {
    e.preventDefault();
    // Accept the selected match (if any) into the prompt without running it,
    // matching the autocomplete menu's Enter behavior.
    if (_histSearchIndex >= 0) {
      exitHistSearch(true);
    } else {
      exitHistSearch(false, { keepCurrent: true });
    }
    return true;
  }
  if (e.key === 'Tab' && !e.altKey && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    _moveHistSearchSelection(e.shiftKey ? -1 : 1);
    return true;
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    _moveHistSearchSelection(1);
    return true;
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    _moveHistSearchSelection(-1);
    return true;
  }
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'r' || e.key === 'R')) {
    e.preventDefault();
    enterHistSearch(); // cycle
    return true;
  }
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'g' || e.key === 'G')) {
    e.preventDefault();
    exitHistSearch(false);
    return true;
  }
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'c' || e.key === 'C')) {
    e.preventDefault();
    exitHistSearch(false, { keepCurrent: true });
    return true;
  }
  // Let printable characters and backspace fall through to the input event
  return false;
}

if (typeof window !== 'undefined') {
  Object.assign(window, {
    isHistSearchMode,
    enterHistSearch,
    exitHistSearch,
    handleHistSearchInput,
    handleHistSearchKey,
  });
}
