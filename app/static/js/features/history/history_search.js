// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// darklab_shell history search module.
// Ctrl+R reverse-history search for the command composer.
import { acHide as importedAcHide } from '../../autocomplete.js';
import {
  cmdInput as importedCmdInput,
  histSearchDropdown as importedHistSearchDropdown,
  shellPromptWrap as importedShellPromptWrap,
} from '../../core/dom.js';
import { getAppState as importedGetAppState } from '../../core/state.js';
import {
  getComposerValue as importedGetComposerValue,
  setComposerValue as importedSetComposerValue,
} from '../../ui/ui_helpers.js';
import {
  apiFetch as importedRuntimeApiFetch,
  hasRuntimeHandler as importedHasRuntimeHandler,
} from '../../runtime_bridge.js';

let _histSearchMode = false;
let _histSearchQuery = '';
let _histSearchIndex = -1;
let _histSearchPreDraft = '';
let _histSearchRuns = null;     // null = not yet fetched; string[] = ready
let _histSearchFetchTimer = null;

const HISTORY_SEARCH_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _historySearchApiFetch(...args) {
  const fetcher = (
    typeof importedHasRuntimeHandler === 'function'
    && importedHasRuntimeHandler('apiFetch')
    && typeof importedRuntimeApiFetch === 'function'
      ? importedRuntimeApiFetch
      : null
  ) || (typeof HISTORY_SEARCH_GLOBAL.apiFetch === 'function' ? HISTORY_SEARCH_GLOBAL.apiFetch : null);
  return typeof fetcher === 'function' ? fetcher(...args) : Promise.reject(new Error('apiFetch unavailable'));
}

function _historySearchCmdHistory() {
  const state = typeof importedGetAppState === 'function'
    ? importedGetAppState()
    : (typeof HISTORY_SEARCH_GLOBAL.APP_STATE_API?.getState === 'function'
        ? HISTORY_SEARCH_GLOBAL.APP_STATE_API.getState()
        : HISTORY_SEARCH_GLOBAL.APP_STATE || null);
  if (state && Array.isArray(state.cmdHistory)) return state.cmdHistory;
  return [];
}

function _historySearchCmdInput() {
  return (typeof importedCmdInput !== 'undefined' && importedCmdInput)
    || HISTORY_SEARCH_GLOBAL.cmdInput
    || null;
}

function _historySearchDropdown() {
  return (typeof importedHistSearchDropdown !== 'undefined' && importedHistSearchDropdown)
    || HISTORY_SEARCH_GLOBAL.histSearchDropdown
    || null;
}

function _historySearchPromptWrap() {
  return (typeof importedShellPromptWrap !== 'undefined' && importedShellPromptWrap)
    || HISTORY_SEARCH_GLOBAL.shellPromptWrap
    || null;
}

function _historySearchGetComposerValue() {
  const getter = (typeof importedGetComposerValue !== 'undefined' && importedGetComposerValue)
    || HISTORY_SEARCH_GLOBAL.getComposerValue;
  const input = _historySearchCmdInput();
  return typeof getter === 'function' ? getter() : (input ? input.value : '');
}

function _historySearchSetComposerValue(...args) {
  const setter = (typeof importedSetComposerValue !== 'undefined' && importedSetComposerValue)
    || HISTORY_SEARCH_GLOBAL.setComposerValue;
  if (typeof setter === 'function') setter(...args);
}

function _historySearchHideAutocomplete() {
  const hide = (typeof importedAcHide !== 'undefined' && importedAcHide)
    || HISTORY_SEARCH_GLOBAL.acHide;
  if (typeof hide === 'function') hide();
}

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
  const fromClient = _historySearchCmdHistory().filter(c => c.toLowerCase().includes(q));
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
  _historySearchApiFetch(url).then(r => r.json()).then(data => {
    if (!_histSearchMode || query !== _histSearchQuery) return;
    const currentMatches = _histSearchMatches();
    const selectedCommand = _histSearchIndex >= 0
      ? currentMatches[_histSearchIndex] || ''
      : '';
    _histSearchRuns = Array.isArray(data.runs)
      ? [...new Set(data.runs.map(r => r.command))]
      : [];
    const nextMatches = _histSearchMatches();
    const preservedIndex = selectedCommand ? nextMatches.indexOf(selectedCommand) : -1;
    _histSearchIndex = preservedIndex >= 0 ? preservedIndex : (nextMatches.length ? 0 : -1);
    _renderHistSearch();
  }).catch(() => {
    if (_histSearchMode && query === _histSearchQuery && _histSearchRuns === null) {
      _histSearchRuns = [];
    }
  });
}

function _hideHistSearchDropdown() {
  const dropdown = _historySearchDropdown();
  if (dropdown) dropdown.classList.add('u-hidden');
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
  const dropdown = _historySearchDropdown();
  const promptWrap = _historySearchPromptWrap();
  if (!dropdown) return;
  const matches = _histSearchMatches();
  dropdown.replaceChildren();

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
  dropdown.appendChild(header);

  if (!matches.length) {
    const empty = document.createElement('div');
    empty.className = 'hist-search-empty';
    empty.textContent = '(no matches)';
    dropdown.appendChild(empty);
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
      dropdown.appendChild(item);
    });
  }

  // Flip above/below based on available space, mirroring the ac-dropdown so
  // the list stays on-screen when the prompt is near the top of the viewport.
  dropdown.classList.remove('u-hidden');
  if (promptWrap) {
    const rect = promptWrap.getBoundingClientRect();
    dropdown.style.position = 'fixed';
    dropdown.style.left = rect.left + 'px';
    dropdown.style.width = rect.width + 'px';
    dropdown.style.bottom = 'auto';
    dropdown.style.maxHeight = '';
    const desired = dropdown.offsetHeight;
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
    dropdown.style.maxHeight = `${Math.round(maxHeight)}px`;
    dropdown.style.top = showAbove
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
  _histSearchPreDraft = _historySearchGetComposerValue();
  // Clear the input so the user types a fresh query rather than appending to the draft.
  // The draft is preserved in _histSearchPreDraft and restored on Escape / Ctrl+G.
  _historySearchSetComposerValue('', 0, 0, { dispatch: false });
  _historySearchHideAutocomplete();

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
    _historySearchSetComposerValue(chosen, chosen.length, chosen.length);
  } else if (!keepCurrent) {
    _historySearchSetComposerValue(_histSearchPreDraft, _histSearchPreDraft.length, _histSearchPreDraft.length);
  }
  _histSearchQuery = '';
  _histSearchIndex = -1;
  _histSearchPreDraft = '';
  _histSearchRuns = null;
  if (_histSearchFetchTimer) { clearTimeout(_histSearchFetchTimer); _histSearchFetchTimer = null; }
  _historySearchHideAutocomplete();
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
}

export {
  enterHistSearch,
  exitHistSearch,
  handleHistSearchInput,
  handleHistSearchKey,
  isHistSearchMode,
};
