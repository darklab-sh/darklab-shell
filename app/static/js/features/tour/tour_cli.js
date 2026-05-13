// Terminal-guided onboarding tour command.

function _tourChaptersForCurrentViewport() {
  const chapters = Array.isArray(APP_CONFIG?.tour_chapters) ? APP_CONFIG.tour_chapters : [];
  const mobileMode = typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode();
  return chapters.filter((chapter) => {
    if (!chapter || typeof chapter !== 'object') return false;
    if (mobileMode && String(chapter.id || '') === 'interactive_pty') return false;
    return true;
  });
}

function _tourSummaryLines(summary) {
  return String(summary || '')
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean);
}

const TOUR_CLI_TYPE_CHARS_PER_FRAME = 10;

function _cliTourOutput(tabId = null) {
  const id = tabId || (typeof activeTabId !== 'undefined' ? activeTabId : null);
  return typeof getOutput === 'function' ? getOutput(id) : null;
}

function _cliAppendTourDomLine(text = '', cls = '', tabId = null) {
  const out = _cliTourOutput(tabId);
  if (!out || typeof document === 'undefined') {
    if (String(text ?? '')) _cliAppendLine(text, cls, tabId);
    return null;
  }
  const line = document.createElement('span');
  line.className = `line${cls ? ` ${cls}` : ''}`;
  const content = document.createElement('span');
  content.className = 'line-content';
  content.textContent = String(text ?? '');
  line.appendChild(content);
  const prompt = (typeof shellPromptWrap !== 'undefined' && shellPromptWrap && shellPromptWrap.parentElement === out)
    ? shellPromptWrap
    : null;
  if (prompt) out.insertBefore(line, prompt);
  else out.appendChild(line);
  return { line, content };
}

function _cliTourAnimationFrame() {
  if (typeof requestAnimationFrame === 'function') {
    return new Promise(resolve => requestAnimationFrame(resolve));
  }
  return new Promise(resolve => setTimeout(resolve, 0));
}

async function _cliAppendTypedTourLine(text, cls = '', tabId = null, preserveTail = true) {
  const value = String(text ?? '');
  const rendered = _cliAppendTourDomLine('', cls, tabId);
  if (!rendered || !value) {
    if (value) _cliAppendLine(value, cls, tabId);
    _cliPreserveOutputTail(tabId, preserveTail);
    return;
  }
  let offset = 0;
  while (offset < value.length) {
    offset = Math.min(value.length, offset + TOUR_CLI_TYPE_CHARS_PER_FRAME);
    rendered.content.textContent = value.slice(0, offset);
    _cliPreserveOutputTail(tabId, preserveTail);
    await _cliTourAnimationFrame();
  }
}

function _openTourSampleInNewTab(command, sourceTabId = null) {
  const sample = String(command || '').trim();
  if (!sample) return;
  let targetTabId = null;
  if (typeof createTab === 'function') {
    targetTabId = createTab();
    if (!targetTabId) return;
    if (targetTabId && typeof activateTab === 'function') {
      activateTab(targetTabId);
    }
  } else if (sourceTabId && typeof activateTab === 'function') {
    activateTab(sourceTabId);
  }
  if (typeof setComposerValue === 'function') {
    setComposerValue(sample, sample.length, sample.length, { dispatch: true });
  }
  if (typeof refocusComposerAfterAction === 'function') {
    refocusComposerAfterAction({ defer: true });
  }
}

function _cliAppendTourSampleChip(sample, tabId = null) {
  const command = String(sample || '').trim();
  if (!command) return;
  const rendered = _cliAppendTourDomLine('', 'builtin-help-row builtin-tour-sample', tabId);
  if (!rendered || typeof document === 'undefined') {
    _cliAppendLine(command, 'builtin-help-row builtin-tour-sample', tabId, { faq_command: command });
    return;
  }
  const chip = document.createElement('span');
  chip.className = 'allowed-chip faq-chip chip chip-action';
  chip.tabIndex = 0;
  chip.setAttribute('role', 'button');
  chip.title = 'Open this command in a new tab';
  chip.dataset.faqCommand = command;
  chip.dataset.tourSample = '1';
  chip.textContent = command;
  const activate = () => _openTourSampleInNewTab(command, tabId);
  chip.addEventListener('click', activate);
  chip.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    activate();
  });
  rendered.content.appendChild(chip);
  _cliPreserveOutputTail(tabId, true);
}

function _isTourTabActive(tabId = null) {
  if (!tabId || typeof activeTabId === 'undefined') return true;
  return activeTabId === tabId;
}

function _tourWaitForContinue(tabId = null, isLastChapter = false) {
  const prompt = isLastChapter
    ? 'Press any key to finish, or press q to quit the tour.'
    : 'Press any key to continue, or press q to quit the tour.';
  _cliAppendTourDomLine(prompt, 'builtin-note builtin-tour-prompt', tabId);
  _cliPreserveOutputTail(tabId, true);
  if (typeof document === 'undefined') return Promise.resolve(true);
  return new Promise(resolve => {
    const onKeyDown = (event) => {
      if (!_isTourTabActive(tabId)) return;
      if (['Alt', 'Control', 'Meta', 'Shift'].includes(event.key)) return;
      event.preventDefault();
      event.stopPropagation();
      document.removeEventListener('keydown', onKeyDown, true);
      const key = String(event.key || '').toLowerCase();
      resolve(key !== 'q' && key !== 'escape');
    };
    document.addEventListener('keydown', onKeyDown, true);
  });
}

async function handleTourCommand(cmd, tabId = null) {
  const parts = String(cmd || '').trim().split(/\s+/).filter(Boolean);
  const sub = String(parts[1] || '').toLowerCase();
  const preserveTail = _cliShouldPreserveOutputTail(tabId);
  if (typeof appendCommandEcho === 'function') appendCommandEcho(cmd, tabId);

  if (!(APP_CONFIG && APP_CONFIG.tour_enabled === true)) {
    _cliAppendLine('tour: onboarding tour is disabled on this shell', 'exit-fail', tabId);
    _cliSetStatus('fail');
    return true;
  }

  if (parts.length > 1 && !['help', '--help', '-h'].includes(sub)) {
    _cliAppendLine('usage: tour', 'exit-fail', tabId);
    _cliSetStatus('fail');
    return true;
  }

  if (['help', '--help', '-h'].includes(sub)) {
    _cliAppendLine('usage: tour', '', tabId);
    _cliAppendLine('Print the onboarding tour inside the terminal.', 'builtin-note', tabId);
    _cliRecordSuccess(cmd);
    _cliSetStatus('ok');
    return true;
  }

  await _recordTourOpenedOnceThisSession();
  const chapters = _tourChaptersForCurrentViewport();
  if (!chapters.length) {
    _cliAppendLine('tour: no onboarding chapters are visible for this shell', 'exit-fail', tabId);
    _cliSetStatus('fail');
    return true;
  }

  for (const [index, chapter] of chapters.entries()) {
    if (index > 0) _cliAppendTourDomLine('', 'builtin-spacer', tabId);
    await _cliAppendTypedTourLine(String(chapter.title || '').trim(), 'builtin-section', tabId, preserveTail);
    for (const line of _tourSummaryLines(chapter.summary)) {
      await _cliAppendTypedTourLine(line, 'builtin-note', tabId, preserveTail);
    }
    const sample = String(chapter.sample || '').trim();
    if (sample) {
      await _cliAppendTypedTourLine('Try this:', 'builtin-note', tabId, preserveTail);
      _cliAppendTourSampleChip(sample, tabId);
    }
    const shouldContinue = await _tourWaitForContinue(tabId, index === chapters.length - 1);
    if (!shouldContinue) {
      _cliAppendTourDomLine('tour stopped', 'builtin-note', tabId);
      break;
    }
  }
  _cliPreserveOutputTail(tabId, preserveTail);
  _cliRecordSuccess(cmd);
  _cliSetStatus('ok');
  return true;
}
