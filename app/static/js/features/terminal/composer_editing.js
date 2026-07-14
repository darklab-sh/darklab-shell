// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { cmdInput as importedCmdInput } from '../../core/dom.js';
import { getComposerState as importedGetComposerState } from '../../core/state.js';
import {
  getComposerValue as importedGetComposerValue,
  getVisibleComposerInput as importedGetVisibleComposerInput,
  setComposerValue as importedSetComposerValue,
  syncComposerSelection as importedSyncComposerSelection,
  syncFocusedComposerState as importedSyncFocusedComposerState,
} from '../../ui/ui_helpers.js';
import {
  hasComposerPromptHandler as importedHasComposerPromptHandler,
  syncShellPrompt as importedSyncShellPrompt,
} from './composer_prompt_bridge.js';

const COMPOSER_EDITING_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _composerEditingGlobalFunction(name) {
  const fn = COMPOSER_EDITING_GLOBAL?.[name];
  return typeof fn === 'function' ? fn : null;
}

function _composerEditingCmdInput() {
  return (typeof importedCmdInput !== 'undefined' && importedCmdInput)
    || (typeof document !== 'undefined' ? document.getElementById('cmd') : null);
}

function _composerEditingGetComposerState() {
  if (typeof importedGetComposerState !== 'undefined' && typeof importedGetComposerState === 'function') {
    return importedGetComposerState();
  }
  const getComposerState = _composerEditingGlobalFunction('getComposerState');
  return getComposerState ? getComposerState() : null;
}

function _composerEditingGetComposerValue() {
  if (typeof importedGetComposerValue !== 'undefined' && typeof importedGetComposerValue === 'function') {
    return importedGetComposerValue();
  }
  const input = _composerEditingCmdInput();
  const getComposerValue = _composerEditingGlobalFunction('getComposerValue');
  return getComposerValue
    ? getComposerValue()
    : (input && input.value || '');
}

function _composerEditingVisibleInput() {
  if (typeof importedGetVisibleComposerInput !== 'undefined' && typeof importedGetVisibleComposerInput === 'function') {
    return importedGetVisibleComposerInput();
  }
  const getVisibleComposerInput = _composerEditingGlobalFunction('getVisibleComposerInput');
  return getVisibleComposerInput ? getVisibleComposerInput() : _composerEditingCmdInput();
}

function _composerEditingSetValue(value, start, end) {
  const setValue = (typeof importedSetComposerValue !== 'undefined' && importedSetComposerValue)
    || _composerEditingGlobalFunction('setComposerValue');
  if (typeof setValue === 'function') setValue(value, start, end);
}

function _composerEditingSyncSelection(start, end, options = {}) {
  const syncSelection = (typeof importedSyncComposerSelection !== 'undefined' && importedSyncComposerSelection)
    || _composerEditingGlobalFunction('syncComposerSelection');
  if (typeof syncSelection === 'function') {
    syncSelection(start, end, options);
    return true;
  }
  return false;
}

function _composerEditingSyncFocusedState(input) {
  const syncFocused = (typeof importedSyncFocusedComposerState !== 'undefined' && importedSyncFocusedComposerState)
    || _composerEditingGlobalFunction('syncFocusedComposerState');
  if (typeof syncFocused === 'function') syncFocused(input);
}

function _composerEditingSyncShellPrompt() {
  const syncPrompt = (
    typeof importedHasComposerPromptHandler === 'function'
    && importedHasComposerPromptHandler('syncShellPrompt')
  ) ? importedSyncShellPrompt : _composerEditingGlobalFunction('syncShellPrompt');
  if (typeof syncPrompt === 'function') syncPrompt();
}

function getComposerStateSnapshot() {
  return _composerEditingGetComposerState();
}

function getCmdSelection(value = null) {
  const composer = getComposerStateSnapshot();
  const input = _composerEditingCmdInput();
  const sourceValue = typeof value === 'string'
    ? value
    : (composer && typeof composer.value === 'string'
      ? composer.value
      : (input && input.value || ''));
  let start = composer && typeof composer.selectionStart === 'number'
    ? composer.selectionStart
    : (input && typeof input.selectionStart === 'number' ? input.selectionStart : sourceValue.length);
  let end = composer && typeof composer.selectionEnd === 'number'
    ? composer.selectionEnd
    : (input && typeof input.selectionEnd === 'number' ? input.selectionEnd : sourceValue.length);
  if (start > end) [start, end] = [end, start];
  return { start, end };
}

function getInputSelection(input, value = input && input.value ? input.value : '') {
  let start = typeof input.selectionStart === 'number' ? input.selectionStart : value.length;
  let end = typeof input.selectionEnd === 'number' ? input.selectionEnd : value.length;
  if (start > end) [start, end] = [end, start];
  return { start, end };
}

function replaceCmdRange(value, start, end, replacement = '') {
  const nextPos = start + replacement.length;
  _composerEditingSetValue(value.slice(0, start) + replacement + value.slice(end), nextPos, nextPos);
}

function moveCmdCaret(delta) {
  const input = _composerEditingCmdInput();
  const value = _composerEditingGetComposerValue();
  const { start, end } = getCmdSelection(value);
  const next = Math.max(0, Math.min(value.length, (delta < 0 ? start : end) + delta));
  if (!_composerEditingSyncSelection(next, next, { input: _composerEditingVisibleInput() })
      && input
      && typeof input.setSelectionRange === 'function') {
    input.setSelectionRange(next, next);
  }
  _composerEditingSyncShellPrompt();
}

function moveCmdCaretByWord(direction) {
  const input = _composerEditingVisibleInput();
  const fallbackInput = _composerEditingCmdInput();
  _composerEditingSyncFocusedState(input);
  const value = _composerEditingGetComposerValue();
  const { start, end } = getCmdSelection(value);
  const next = direction < 0
    ? findWordBoundaryLeft(value, start)
    : findWordBoundaryRight(value, end);
  _composerEditingSyncSelection(next, next, { input });
  if (input && typeof input.setSelectionRange === 'function' && input.selectionStart !== next) {
    input.setSelectionRange(next, next);
  } else if (!input && fallbackInput && typeof fallbackInput.setSelectionRange === 'function') {
    fallbackInput.setSelectionRange(next, next);
  }
  _composerEditingSyncShellPrompt();
}

function handleComposerWordArrowShortcut(e) {
  if (!e || !e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return false;
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return false;
  e.preventDefault();
  e.stopPropagation();
  moveCmdCaretByWord(e.key === 'ArrowLeft' ? -1 : 1);
  return true;
}

function isTerminalWordChar(char) {
  return /[A-Za-z0-9]/.test(char || '');
}

function findWordBoundaryLeft(value, index) {
  let next = Math.max(0, index);
  while (next > 0 && !isTerminalWordChar(value[next - 1])) next--;
  while (next > 0 && isTerminalWordChar(value[next - 1])) next--;
  return next;
}

function findWordBoundaryRight(value, index) {
  let next = Math.min(value.length, index);
  while (next < value.length && !isTerminalWordChar(value[next])) next++;
  while (next < value.length && isTerminalWordChar(value[next])) next++;
  return next;
}

if (typeof window !== 'undefined') {
}

export {
  findWordBoundaryLeft,
  findWordBoundaryRight,
  getCmdSelection,
  getComposerStateSnapshot,
  getInputSelection,
  handleComposerWordArrowShortcut,
  isTerminalWordChar,
  moveCmdCaret,
  moveCmdCaretByWord,
  replaceCmdRange,
};
