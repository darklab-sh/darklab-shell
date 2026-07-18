// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Autocomplete dropdown rendering and keyboard interaction.
import { DarklabAutocompleteCore as importedAutocompleteCore } from './core/autocomplete_core.js';
import {
  acDropdown as importedAcDropdown,
  cmdInput as importedCmdInput,
  mobileCmdInput as importedMobileCmdInput,
  mobileComposerHost as importedMobileComposerHost,
  mobileComposerRow as importedMobileComposerRow,
  shellPromptWrap as importedShellPromptWrap,
} from './core/dom.js';
import {
  getAutocompleteState as importedGetAutocompleteState,
  getComposerState as importedGetComposerState,
  setAutocompleteState as importedSetAutocompleteState,
} from './core/state.js';
import { escapeHtml as importedEscapeHtml } from './core/utils.js';
import {
  getComposerValue as importedGetComposerValue,
  getVisibleComposerInput as importedGetVisibleComposerInput,
  hideAcDropdown as importedHideAcDropdown,
  isActiveTabRunning as importedIsActiveTabRunning,
  refocusComposerAfterAction as importedRefocusComposerAfterAction,
  setComposerValue as importedSetComposerValue,
  showAcDropdown as importedShowAcDropdown,
} from './ui/ui_helpers.js';
import { _autocompleteTokenContext as importedAutocompleteTokenContext } from './features/autocomplete/suggestions.js';
import { hasPendingTerminalConfirm as importedHasPendingTerminalConfirm } from './runner_bridge.js';

const AUTOCOMPLETE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _autocompleteGlobalFunction(name) {
  const fn = AUTOCOMPLETE_GLOBAL && AUTOCOMPLETE_GLOBAL[name];
  return typeof fn === 'function' ? fn : null;
}

const autocompleteDropdownCore = typeof importedAutocompleteCore !== 'undefined' && importedAutocompleteCore
  ? importedAutocompleteCore
  : AUTOCOMPLETE_GLOBAL.DarklabAutocompleteCore;

const _autocompleteDom = {
  acDropdown: (typeof importedAcDropdown !== 'undefined' && importedAcDropdown)
    || AUTOCOMPLETE_GLOBAL.acDropdown
    || null,
  cmdInput: (typeof importedCmdInput !== 'undefined' && importedCmdInput)
    || AUTOCOMPLETE_GLOBAL.cmdInput
    || null,
  mobileCmdInput: (typeof importedMobileCmdInput !== 'undefined' && importedMobileCmdInput)
    || AUTOCOMPLETE_GLOBAL.mobileCmdInput
    || null,
  mobileComposerHost: (typeof importedMobileComposerHost !== 'undefined' && importedMobileComposerHost)
    || AUTOCOMPLETE_GLOBAL.mobileComposerHost
    || null,
  mobileComposerRow: (typeof importedMobileComposerRow !== 'undefined' && importedMobileComposerRow)
    || AUTOCOMPLETE_GLOBAL.mobileComposerRow
    || null,
  shellPromptWrap: (typeof importedShellPromptWrap !== 'undefined' && importedShellPromptWrap)
    || AUTOCOMPLETE_GLOBAL.shellPromptWrap
    || null,
};

function _autocompleteGetState() {
  const readState = (typeof importedGetAutocompleteState !== 'undefined' && importedGetAutocompleteState)
    || _autocompleteGlobalFunction('getAutocompleteState');
  return typeof readState === 'function' ? readState() : {};
}

function _autocompleteSetState(next) {
  const writeState = (typeof importedSetAutocompleteState !== 'undefined' && importedSetAutocompleteState)
    || _autocompleteGlobalFunction('setAutocompleteState');
  if (typeof writeState === 'function') writeState(next);
}

function _autocompleteComposerState() {
  const readState = (typeof importedGetComposerState !== 'undefined' && importedGetComposerState)
    || _autocompleteGlobalFunction('getComposerState');
  return typeof readState === 'function' ? readState() : {};
}

function _autocompleteComposerValue() {
  const readValue = (typeof importedGetComposerValue !== 'undefined' && importedGetComposerValue)
    || _autocompleteGlobalFunction('getComposerValue');
  if (typeof readValue === 'function') return readValue();
  return _autocompleteDom.cmdInput ? _autocompleteDom.cmdInput.value : '';
}

function _autocompleteSetComposerValue(value, start = null, end = null) {
  const writeValue = (typeof importedSetComposerValue !== 'undefined' && importedSetComposerValue)
    || _autocompleteGlobalFunction('setComposerValue');
  if (typeof writeValue === 'function') writeValue(value, start, end);
}

function _autocompleteVisibleInput() {
  const readInput = (typeof importedGetVisibleComposerInput !== 'undefined' && importedGetVisibleComposerInput)
    || _autocompleteGlobalFunction('getVisibleComposerInput');
  return typeof readInput === 'function' ? readInput() : _autocompleteDom.cmdInput;
}

function _autocompleteHideDropdown() {
  const hideDropdown = (typeof importedHideAcDropdown !== 'undefined' && importedHideAcDropdown)
    || _autocompleteGlobalFunction('hideAcDropdown');
  if (typeof hideDropdown === 'function') hideDropdown();
}

function _autocompleteShowDropdown() {
  const showDropdown = (typeof importedShowAcDropdown !== 'undefined' && importedShowAcDropdown)
    || _autocompleteGlobalFunction('showAcDropdown');
  if (typeof showDropdown === 'function') showDropdown();
}

function _autocompleteRefocusComposer() {
  const refocus = (typeof importedRefocusComposerAfterAction !== 'undefined' && importedRefocusComposerAfterAction)
    || _autocompleteGlobalFunction('refocusComposerAfterAction');
  if (typeof refocus === 'function') refocus({ preventScroll: true });
}

function _autocompleteEscapeHtml(value) {
  const escape = (typeof importedEscapeHtml !== 'undefined' && importedEscapeHtml)
    || _autocompleteGlobalFunction('escapeHtml');
  return typeof escape === 'function' ? escape(value) : String(value || '');
}

function _isAutocompleteBlockedByTerminalConfirm() {
  const hasPending = (typeof importedHasPendingTerminalConfirm === 'function' && importedHasPendingTerminalConfirm)
    || _autocompleteGlobalFunction('hasPendingTerminalConfirm');
  return typeof hasPending === 'function' && hasPending();
}

function _isAutocompleteBlockedByActiveRun() {
  const isRunning = (typeof importedIsActiveTabRunning === 'function' && importedIsActiveTabRunning)
    || _autocompleteGlobalFunction('isActiveTabRunning');
  return typeof isRunning === 'function' && isRunning();
}

function _readAutocompleteState() {
  const apiState = _autocompleteGetState();
  return {
    filtered: Array.isArray(apiState.filtered) ? apiState.filtered : [],
    index: apiState.index ?? -1,
    suppressInputOnce: !!apiState.suppressInputOnce,
  };
}

function _writeAutocompleteState(next = {}) {
  _autocompleteSetState(next);
  return _readAutocompleteState();
}

function _autocompleteTokenContextForValue(value, cursor) {
  const tokenContext = (typeof importedAutocompleteTokenContext !== 'undefined' && importedAutocompleteTokenContext)
    || _autocompleteGlobalFunction('_autocompleteTokenContext');
  return typeof tokenContext === 'function'
    ? tokenContext(value, cursor)
    : { currentToken: String(value || '') };
}

function _positionAutocomplete(itemsCount) {
  // Desktop anchors the dropdown to the prompt row; mobile anchors it above the
  // simplified composer so suggestions never hide behind the keyboard.
  const acDropdown = _autocompleteDom.acDropdown;
  if (!acDropdown) return false;
  const parentWrap = acDropdown.parentElement;
  const wrap = parentWrap && parentWrap.classList?.contains('shell-prompt-wrap')
    ? parentWrap
    : (_autocompleteDom.shellPromptWrap || parentWrap);
  const composerHost = _autocompleteDom.mobileComposerHost || null;
  const composerRow = _autocompleteDom.mobileComposerRow || null;
  const visibleInput = _autocompleteVisibleInput();
  const mobileTerminalMode = !!(document.body && document.body.classList.contains('mobile-terminal-mode'));
  const mobileComposerMode = mobileTerminalMode;
  let anchor = mobileTerminalMode && composerRow ? composerRow : (mobileTerminalMode && composerHost ? composerHost : wrap);
  if (!mobileTerminalMode && anchor && typeof anchor.getBoundingClientRect === 'function') {
    const anchorRect = anchor.getBoundingClientRect();
    if (
      anchorRect.width <= 0
      && anchorRect.height <= 0
      && anchorRect.top === 0
      && anchorRect.bottom === 0
      && visibleInput
    ) {
      anchor = visibleInput;
    }
  }
  const prefix = anchor === wrap && wrap && wrap.querySelector ? wrap.querySelector('.prompt-prefix') : null;
  acDropdown.classList.toggle('ac-mobile', mobileTerminalMode);
  if (mobileTerminalMode) {
    const rect = anchor && typeof anchor.getBoundingClientRect === 'function'
      ? anchor.getBoundingClientRect()
      : { top: 0 };
    const rowH = 44;
    const desired = Math.min(8, Math.max(1, itemsCount)) * rowH + 10;
    // Cap at 360px max but don't further cap by available space — the dropdown
    // grows upward (bottom: calc(100% + 4px)) and the parent container clips it
    // if it would go off-screen. This ensures all items are visible without
    // requiring the user to scroll, which is unreliable on touch due to item
    // tap handlers competing with the native scroll gesture.
    const maxHeight = Math.max(88, Math.min(360, desired));
    acDropdown.style.position = 'absolute';
    acDropdown.style.left = '0';
    acDropdown.style.right = '0';
    acDropdown.style.width = '100%';
    acDropdown.style.minWidth = '0';
    acDropdown.style.maxHeight = `${Math.round(maxHeight)}px`;
    acDropdown.style.top = 'auto';
    acDropdown.style.bottom = 'calc(100% + 4px)';
    acDropdown.classList.add('ac-up');
    acDropdown.classList.add('dropdown-up');
    return true;
  }
  acDropdown.classList.remove('ac-mobile');
  const prefixOffset = mobileComposerMode ? 0 : (prefix ? Math.max(0, Math.ceil(prefix.getBoundingClientRect().width) + 8) : 0);
  const wrapRect = anchor && typeof anchor.getBoundingClientRect === 'function' ? anchor.getBoundingClientRect() : null;
  acDropdown.style.position = 'fixed';
  acDropdown.style.left = `${Math.max(0, Math.round((wrapRect ? wrapRect.left : 0) + prefixOffset))}px`;
  acDropdown.style.right = 'auto';
  acDropdown.style.minWidth = mobileComposerMode ? '0' : '24ch';
  acDropdown.style.width = mobileComposerMode && wrapRect ? `${Math.max(220, Math.round(wrapRect.width || 0))}px` : '';

  if (!anchor || typeof anchor.getBoundingClientRect !== 'function') {
    acDropdown.classList.remove('ac-up');
    acDropdown.classList.remove('dropdown-up');
    return false;
  }
  const rect = anchor.getBoundingClientRect();
  const rowH = 22;
  const desired = Math.min(10, Math.max(1, itemsCount)) * rowH + 10;
  const targetHeight = Math.max(88, Math.min(260, desired));
  const spaceBelow = Math.max(0, window.innerHeight - rect.bottom - 8);
  const spaceAbove = Math.max(0, rect.top - 8);
  const safetyPad = 20;
  const canFitBelow = spaceBelow >= (targetHeight + safetyPad);
  const canFitAbove = spaceAbove >= (targetHeight + safetyPad);
  const showAbove = mobileComposerMode || (!canFitBelow && (canFitAbove || spaceAbove > spaceBelow));
  acDropdown.classList.toggle('ac-up', showAbove);
  acDropdown.classList.toggle('dropdown-up', showAbove);
  const available = showAbove ? spaceAbove : spaceBelow;
  const edgeBuffer = mobileComposerMode ? 12 : (showAbove ? 20 : 30);
  const maxHeight = Math.max(0, Math.min(mobileComposerMode ? 200 : 260, available > edgeBuffer ? available - edgeBuffer : available));
  acDropdown.style.maxHeight = `${Math.round(maxHeight)}px`;
  if (showAbove) {
    acDropdown.style.top = 'auto';
    acDropdown.style.bottom = `${Math.max(8, Math.round(window.innerHeight - rect.top + 2))}px`;
  } else {
    acDropdown.style.top = `${Math.max(8, Math.round(rect.bottom + 2))}px`;
    acDropdown.style.bottom = 'auto';
  }
  return showAbove;
}

function _scrollAutocompleteActiveItem() {
  const acDropdown = _autocompleteDom.acDropdown;
  if (!acDropdown) return;
  const activeItem = acDropdown.querySelector('.ac-item.ac-active');
  if (!activeItem) return;

  const viewHeight = acDropdown.clientHeight || 0;
  const itemTop = typeof activeItem.offsetTop === 'number' ? activeItem.offsetTop : null;
  const itemHeight = typeof activeItem.offsetHeight === 'number' ? activeItem.offsetHeight : null;
  if (viewHeight > 0 && itemTop !== null && itemHeight !== null) {
    const itemBottom = itemTop + itemHeight;
    const viewTop = acDropdown.scrollTop || 0;
    const viewBottom = viewTop + viewHeight;
    const padding = 4;
    if (itemTop < viewTop + padding) {
      acDropdown.scrollTop = Math.max(0, itemTop - padding);
    } else if (itemBottom > viewBottom - padding) {
      acDropdown.scrollTop = Math.max(0, itemBottom - viewHeight + padding);
    }
    return;
  }

  if (typeof activeItem.scrollIntoView === 'function') {
    activeItem.scrollIntoView({ block: 'nearest' });
  }
}

function acIsHintOnly(item) {
  return !!(item && typeof item === 'object' && item.hintOnly);
}

function acSelectableItems(items) {
  return (Array.isArray(items) ? items : []).filter(item => !acIsHintOnly(item));
}

function acSelectableIndexes(items) {
  return (Array.isArray(items) ? items : [])
    .map((item, index) => (acIsHintOnly(item) ? -1 : index))
    .filter(index => index >= 0);
}

function acFirstSelectableIndex(items) {
  const indexes = acSelectableIndexes(items);
  return indexes.length ? indexes[0] : -1;
}

function acLastSelectableIndex(items) {
  const indexes = acSelectableIndexes(items);
  return indexes.length ? indexes[indexes.length - 1] : -1;
}

function acNextSelectableIndex(items, currentIndex, direction = 1) {
  const indexes = acSelectableIndexes(items);
  if (!indexes.length) return -1;
  const currentPos = indexes.indexOf(currentIndex);
  if (currentPos < 0) return direction < 0 ? indexes[indexes.length - 1] : indexes[0];
  const nextPos = direction < 0
    ? (currentPos <= 0 ? indexes.length - 1 : currentPos - 1)
    : ((currentPos + 1) % indexes.length);
  return indexes[nextPos];
}

function acShow(items) {
  if (_isAutocompleteBlockedByTerminalConfirm() || _isAutocompleteBlockedByActiveRun()) {
    acHide();
    return;
  }
  const acDropdown = _autocompleteDom.acDropdown;
  if (!acDropdown) return;
  acDropdown.innerHTML = '';
  if (!items.length) { _autocompleteHideDropdown(); return; }
  _positionAutocomplete(items.length);
  let nextIndex = _readAutocompleteState().index;
  if (nextIndex >= items.length) nextIndex = acLastSelectableIndex(items);
  if (nextIndex >= 0 && acIsHintOnly(items[nextIndex])) nextIndex = acFirstSelectableIndex(items);
  _writeAutocompleteState({ index: nextIndex });
  const currentValue = _autocompleteComposerValue();
  const composerState = _autocompleteComposerState();
  const cmdInput = _autocompleteDom.cmdInput;
  const currentCursor = typeof composerState.selectionStart === 'number'
    ? composerState.selectionStart
    : (cmdInput && typeof cmdInput.selectionStart === 'number' ? cmdInput.selectionStart : currentValue.length);
  const tokenCtx = _autocompleteTokenContextForValue(currentValue, currentCursor);
  const matchValue = (items.length && typeof items[0] === 'object') ? tokenCtx.currentToken : currentValue;
  const maxExampleLabelLen = items.reduce((max, s) =>
    (s && s.isExample ? Math.max(max, autocompleteDropdownCore.itemText(s).length) : max), 0);
  let hasRenderedConcrete = false;
  let hasRenderedHint = false;
  items.forEach((s, i) => {
    const hintOnly = acIsHintOnly(s);
    const hintSeparated = hintOnly && hasRenderedConcrete && !hasRenderedHint;
    const div = document.createElement('div');
    div.className = 'ac-item dropdown-item dropdown-item-dense'
      + (!hintOnly && i === nextIndex ? ' ac-active dropdown-item-active' : '')
      + (s && s.isExample ? ' ac-example' : '')
      + (hintOnly ? ' ac-hint-only' : '')
      + (hintSeparated ? ' ac-hint-separated' : '');
    if (hintOnly) div.setAttribute('aria-disabled', 'true');
    const label = autocompleteDropdownCore.itemText(s);
    const description = autocompleteDropdownCore.itemDescription(s);
    const val = s && typeof s === 'object' && s.matchQuery != null
      ? String(s.matchQuery || '')
      : String(matchValue || '');
    const main = document.createElement('span');
    main.className = 'ac-item-main';
    if (s && s.isExample && maxExampleLabelLen > 0) main.style.minWidth = maxExampleLabelLen + 'ch';
    main.innerHTML = hintOnly
      ? _autocompleteEscapeHtml(label)
      : autocompleteDropdownCore.highlightedLabel(label, val);
    div.appendChild(main);
    if (description) {
      const desc = document.createElement('span');
      desc.className = 'ac-item-desc';
      desc.textContent = description;
      div.appendChild(desc);
    }
    div.addEventListener('mousedown', e => {
      e.preventDefault();
      if (!hintOnly) acAccept(s);
    });
    // touchstart must not call preventDefault so the container can scroll.
    // We detect taps by checking that the finger barely moved; swipes fall
    // through to the browser's native scroll handling.
    let _touchStartX = 0, _touchStartY = 0;
    div.addEventListener('touchstart', e => {
      const t = e.touches[0];
      _touchStartX = t ? t.clientX : 0;
      _touchStartY = t ? t.clientY : 0;
    }, { passive: true });
    div.addEventListener('touchend', e => {
      const t = e.changedTouches[0];
      const dx = t ? Math.abs(t.clientX - _touchStartX) : 99;
      const dy = t ? Math.abs(t.clientY - _touchStartY) : 99;
      if (dx < 10 && dy < 10) {
        e.preventDefault();
        if (!hintOnly) acAccept(s);
      }
    }, { passive: false });
    acDropdown.appendChild(div);
    if (hintOnly) hasRenderedHint = true;
    else hasRenderedConcrete = true;
  });
  _autocompleteShowDropdown();
  _positionAutocomplete(items.length);
  _scrollAutocompleteActiveItem();
}

function acHide() {
  _autocompleteHideDropdown();
  _writeAutocompleteState({ index: -1, filtered: [] });
}

if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
  document.addEventListener('click', (event) => {
    const rawTarget = event.target;
    const target = rawTarget && rawTarget.nodeType === 1 ? rawTarget : rawTarget?.parentElement;
    if (!target || typeof target.closest !== 'function') return;
    if (target.closest('#ac-dropdown')) return;
    if (target === _autocompleteDom.cmdInput || target === _autocompleteDom.mobileCmdInput) return;
    acHide();
  }, true);
}

function acExpandSharedPrefix(items) {
  if (!Array.isArray(items) || items.length < 2) return false;
  const currentValue = _autocompleteComposerValue();
  const firstItem = items[0];
  const sharedPrefix = autocompleteDropdownCore.sharedPrefix(items);
  if (!sharedPrefix) return false;
  if (firstItem && typeof firstItem === 'object') {
    const replaceStart = Number(firstItem.replaceStart);
    const replaceEnd = Number(firstItem.replaceEnd);
    if (!Number.isFinite(replaceStart) || !Number.isFinite(replaceEnd)) return false;
    const currentToken = currentValue.slice(replaceStart, replaceEnd);
    if (sharedPrefix.length <= currentToken.length) return false;
    if (!sharedPrefix.toLowerCase().startsWith(currentToken.toLowerCase())) return false;
    const next = currentValue.slice(0, replaceStart) + sharedPrefix + currentValue.slice(replaceEnd);
    const caret = replaceStart + sharedPrefix.length;
    _autocompleteSetComposerValue(next, caret, caret);
    return true;
  }
  if (sharedPrefix.length <= currentValue.length) return false;
  if (!sharedPrefix.toLowerCase().startsWith(currentValue.toLowerCase())) return false;
  _autocompleteSetComposerValue(sharedPrefix, sharedPrefix.length, sharedPrefix.length);
  return true;
}

function _acceptedSuggestionShouldRefresh(insertValue, suggestion) {
  const value = String(insertValue || '');
  if (value.endsWith('/')) return true;
  const trimmed = value.trim();
  if (!trimmed
      || trimmed !== value
      || /[\s|;&]/.test(trimmed)
      || trimmed.startsWith('-')
      || trimmed.startsWith('+')) {
    return false;
  }
  if (!suggestion || typeof suggestion !== 'object') return true;
  const replaceStart = Number(suggestion.replaceStart);
  const replaceEnd = Number(suggestion.replaceEnd);
  return !!(
    Number.isFinite(replaceStart)
    && Number.isFinite(replaceEnd)
    && replaceStart === 0
  );
}

function _scheduleAutocompleteRefreshAfterAccept(insertValue, suggestion = null) {
  if (!_acceptedSuggestionShouldRefresh(insertValue, suggestion)) return;
  setTimeout(() => {
    const input = _autocompleteVisibleInput();
    if (input && typeof input.dispatchEvent === 'function') {
      input.dispatchEvent(new Event('input'));
    }
  }, 0);
}

function acAccept(s) {
  let acceptedInsertValue = '';
  if (_isAutocompleteBlockedByTerminalConfirm()) {
    acHide();
    _autocompleteRefocusComposer();
    return;
  }
  if (s && typeof s === 'object') {
    // Placeholder-only hints (e.g. "<token>") are display-only: Tab should hide
    // the dropdown, not insert the literal placeholder text into the prompt.
    if (s.hintOnly) {
      _autocompleteRefocusComposer();
      return;
    }
    const currentValue = _autocompleteComposerValue();
    const insertValue = autocompleteDropdownCore.itemInsertText(s);
    acceptedInsertValue = insertValue;
    const replaceStart = Number(s.replaceStart);
    const replaceEnd = Number(s.replaceEnd);
    _writeAutocompleteState({ suppressInputOnce: true });
    if (Number.isFinite(replaceStart) && Number.isFinite(replaceEnd)) {
      const next = currentValue.slice(0, replaceStart) + insertValue + currentValue.slice(replaceEnd);
      const caret = replaceStart + insertValue.length;
      acHide();
      _autocompleteSetComposerValue(next, caret, caret);
    } else {
      acHide();
      _autocompleteSetComposerValue(insertValue, insertValue.length, insertValue.length);
    }
  } else {
    acceptedInsertValue = String(s || '');
    _writeAutocompleteState({ suppressInputOnce: true });
    acHide();
    _autocompleteSetComposerValue(s, s.length, s.length);
  }
  _autocompleteRefocusComposer();
  _scheduleAutocompleteRefreshAfterAccept(acceptedInsertValue, s);
}

if (typeof window !== 'undefined') {
  Object.assign(window, {
    acAccept,
    acAutocompleteIsHintOnly: acIsHintOnly,
    acAutocompleteNextSelectableIndex: acNextSelectableIndex,
    acAutocompleteSelectableIndexes: acSelectableIndexes,
    acAutocompleteSelectableItems: acSelectableItems,
    acExpandSharedPrefix,
    acHide,
    acIsHintOnly,
    acNextSelectableIndex,
    acSelectableIndexes,
    acSelectableItems,
    acShow,
  });
}

export {
  acAccept,
  acExpandSharedPrefix,
  acHide,
  acIsHintOnly,
  acNextSelectableIndex,
  acSelectableIndexes,
  acSelectableItems,
  acShow,
};
