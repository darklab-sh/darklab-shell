function getComposerStateSnapshot() {
  if (typeof getComposerState === 'function') {
    const composer = getComposerState();
    if (composer) return composer;
  }
  return null;
}

function getCmdSelection(value = null) {
  const composer = getComposerStateSnapshot();
  const sourceValue = typeof value === 'string'
    ? value
    : (composer && typeof composer.value === 'string'
      ? composer.value
      : (cmdInput.value || ''));
  let start = composer && typeof composer.selectionStart === 'number'
    ? composer.selectionStart
    : (typeof cmdInput.selectionStart === 'number' ? cmdInput.selectionStart : sourceValue.length);
  let end = composer && typeof composer.selectionEnd === 'number'
    ? composer.selectionEnd
    : (typeof cmdInput.selectionEnd === 'number' ? cmdInput.selectionEnd : sourceValue.length);
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
  setComposerValue(value.slice(0, start) + replacement + value.slice(end), nextPos, nextPos);
}

function moveCmdCaret(delta) {
  const value = typeof getComposerValue === 'function' ? getComposerValue() : (cmdInput.value || '');
  const { start, end } = getCmdSelection(value);
  const next = Math.max(0, Math.min(value.length, (delta < 0 ? start : end) + delta));
  if (typeof syncComposerSelection === 'function') syncComposerSelection(next, next, { input: getVisibleComposerInput() });
  else if (cmdInput && typeof cmdInput.setSelectionRange === 'function') cmdInput.setSelectionRange(next, next);
  syncShellPrompt();
}

function moveCmdCaretByWord(direction) {
  const input = typeof getVisibleComposerInput === 'function' ? getVisibleComposerInput() : cmdInput;
  if (typeof syncFocusedComposerState === 'function') syncFocusedComposerState(input);
  const value = typeof getComposerValue === 'function' ? getComposerValue() : (cmdInput.value || '');
  const { start, end } = getCmdSelection(value);
  const next = direction < 0
    ? findWordBoundaryLeft(value, start)
    : findWordBoundaryRight(value, end);
  if (typeof syncComposerSelection === 'function') syncComposerSelection(next, next, { input });
  if (input && typeof input.setSelectionRange === 'function' && input.selectionStart !== next) {
    input.setSelectionRange(next, next);
  } else if (!input && cmdInput && typeof cmdInput.setSelectionRange === 'function') {
    cmdInput.setSelectionRange(next, next);
  }
  syncShellPrompt();
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
  Object.assign(window, {
    getComposerStateSnapshot,
    getCmdSelection,
    getInputSelection,
    replaceCmdRange,
    moveCmdCaret,
    moveCmdCaretByWord,
    handleComposerWordArrowShortcut,
    isTerminalWordChar,
    findWordBoundaryLeft,
    findWordBoundaryRight,
  });
}
