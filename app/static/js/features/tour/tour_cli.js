// Terminal-guided onboarding tour command.

import { getAppConfig as importedGetAppConfig } from '../../core/config.js';
import { shellPromptWrap as importedShellPromptWrap } from '../../core/dom.js';
import { getActiveTabId as importedGetActiveTabId } from '../../core/state.js';
import { useMobileTerminalViewportMode as importedUseMobileTerminalViewportMode } from '../mobile/mobile_shell_layout.js';
import {
  _cliAppendLine as importedCliAppendLine,
  _cliPreserveOutputTail as importedCliPreserveOutputTail,
  _cliRecordSuccess as importedCliRecordSuccess,
  _cliSetStatus as importedCliSetStatus,
  _cliShouldPreserveOutputTail as importedCliShouldPreserveOutputTail,
} from '../terminal/local_commands.js';
import { appendCommandEcho as importedAppendCommandEcho } from '../../runner.js';
import {
  activateTab as importedActivateTab,
  createTab as importedCreateTab,
  getOutput as importedGetOutput,
} from '../../tabs.js';
import {
  refocusComposerAfterAction as importedRefocusComposerAfterAction,
  setComposerValue as importedSetComposerValue,
} from '../../ui/ui_helpers.js';
import { _recordTourOpenedOnceThisSession as importedRecordTourOpenedOnceThisSession } from '../preferences/preferences.js';

const TOUR_CLI_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _tourGlobalFunction(name) {
  const fn = TOUR_CLI_GLOBAL && TOUR_CLI_GLOBAL[name];
  return typeof fn === 'function' ? fn : null;
}

function _tourConfig() {
  const readConfig = typeof importedGetAppConfig !== 'undefined' ? importedGetAppConfig : null;
  if (typeof readConfig === 'function') return readConfig();
  return TOUR_CLI_GLOBAL.APP_CONFIG || {};
}

function _tourActiveTabId() {
  const readActiveTabId = (typeof importedGetActiveTabId !== 'undefined' && importedGetActiveTabId)
    || _tourGlobalFunction('getActiveTabId');
  if (typeof readActiveTabId === 'function') return readActiveTabId();
  return TOUR_CLI_GLOBAL.activeTabId || null;
}

function _tourAppendLine(text, cls = '', tabId = null, options = undefined) {
  const append = (typeof importedCliAppendLine !== 'undefined' && importedCliAppendLine)
    || _tourGlobalFunction('_cliAppendLine');
  if (typeof append === 'function') append(text, cls, tabId, options);
}

function _tourPreserveOutputTail(tabId = null, preserveTail = true) {
  const preserve = (typeof importedCliPreserveOutputTail !== 'undefined' && importedCliPreserveOutputTail)
    || _tourGlobalFunction('_cliPreserveOutputTail');
  if (typeof preserve === 'function') preserve(tabId, preserveTail);
}

function _tourRecordSuccess(cmd) {
  const record = (typeof importedCliRecordSuccess !== 'undefined' && importedCliRecordSuccess)
    || _tourGlobalFunction('_cliRecordSuccess');
  if (typeof record === 'function') record(cmd);
}

function _tourSetStatus(status) {
  const setCliStatus = (typeof importedCliSetStatus !== 'undefined' && importedCliSetStatus)
    || _tourGlobalFunction('_cliSetStatus');
  if (typeof setCliStatus === 'function') setCliStatus(status);
}

function _tourShouldPreserveOutputTail(tabId = null) {
  const shouldPreserve = (
    typeof importedCliShouldPreserveOutputTail !== 'undefined'
    && importedCliShouldPreserveOutputTail
  ) || _tourGlobalFunction('_cliShouldPreserveOutputTail');
  return typeof shouldPreserve === 'function' ? shouldPreserve(tabId) : true;
}

function _tourAppendCommandEcho(cmd, tabId = null) {
  const appendEcho = (typeof importedAppendCommandEcho !== 'undefined' && importedAppendCommandEcho)
    || _tourGlobalFunction('appendCommandEcho');
  if (typeof appendEcho === 'function') appendEcho(cmd, tabId);
}

function _tourUseMobileTerminalViewportMode() {
  const useMobile = (
    typeof importedUseMobileTerminalViewportMode !== 'undefined'
    && importedUseMobileTerminalViewportMode
  ) || _tourGlobalFunction('useMobileTerminalViewportMode');
  return typeof useMobile === 'function' && useMobile();
}

function _tourGetOutput(tabId) {
  const readOutput = (typeof importedGetOutput !== 'undefined' && importedGetOutput)
    || _tourGlobalFunction('getOutput');
  return typeof readOutput === 'function' ? readOutput(tabId) : null;
}

function _tourCreateTab() {
  const create = _tourGlobalFunction('createTab')
    || (typeof importedCreateTab !== 'undefined' && importedCreateTab);
  return typeof create === 'function' ? create() : null;
}

function _tourActivateTab(tabId) {
  const activate = _tourGlobalFunction('activateTab')
    || (typeof importedActivateTab !== 'undefined' && importedActivateTab);
  if (typeof activate === 'function') activate(tabId);
}

function _tourSetComposerValue(value, start, end, options) {
  const setValue = _tourGlobalFunction('setComposerValue')
    || (typeof importedSetComposerValue !== 'undefined' && importedSetComposerValue);
  if (typeof setValue === 'function') setValue(value, start, end, options);
}

function _tourRefocusComposerAfterAction(options) {
  const refocus = _tourGlobalFunction('refocusComposerAfterAction')
    || (typeof importedRefocusComposerAfterAction !== 'undefined' && importedRefocusComposerAfterAction);
  if (typeof refocus === 'function') refocus(options);
}

function _tourShellPromptWrap() {
  return (typeof importedShellPromptWrap !== 'undefined' && importedShellPromptWrap)
    || TOUR_CLI_GLOBAL.shellPromptWrap
    || null;
}

function _tourChaptersForCurrentViewport() {
  const config = _tourConfig();
  const chapters = Array.isArray(config.tour_chapters) ? config.tour_chapters : [];
  const mobileMode = _tourUseMobileTerminalViewportMode();
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
  const id = tabId || _tourActiveTabId();
  return _tourGetOutput(id);
}

function _cliAppendTourDomLine(text = '', cls = '', tabId = null) {
  const out = _cliTourOutput(tabId);
  if (!out || typeof document === 'undefined') {
    if (String(text ?? '')) _tourAppendLine(text, cls, tabId);
    return null;
  }
  const line = document.createElement('span');
  line.className = `line${cls ? ` ${cls}` : ''}`;
  const content = document.createElement('span');
  content.className = 'line-content';
  content.textContent = String(text ?? '');
  line.appendChild(content);
  const shellPrompt = _tourShellPromptWrap();
  const prompt = (shellPrompt && shellPrompt.parentElement === out)
    ? shellPrompt
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
    if (value) _tourAppendLine(value, cls, tabId);
    _tourPreserveOutputTail(tabId, preserveTail);
    return;
  }
  let offset = 0;
  while (offset < value.length) {
    offset = Math.min(value.length, offset + TOUR_CLI_TYPE_CHARS_PER_FRAME);
    rendered.content.textContent = value.slice(0, offset);
    _tourPreserveOutputTail(tabId, preserveTail);
    await _cliTourAnimationFrame();
  }
}

function _openTourSampleInNewTab(command, sourceTabId = null) {
  const sample = String(command || '').trim();
  if (!sample) return;
  let targetTabId = null;
  if (typeof importedCreateTab !== 'undefined' || _tourGlobalFunction('createTab')) {
    targetTabId = _tourCreateTab();
    if (!targetTabId) return;
    _tourActivateTab(targetTabId);
  } else if (sourceTabId) {
    _tourActivateTab(sourceTabId);
  }
  _tourSetComposerValue(sample, sample.length, sample.length, { dispatch: true });
  _tourRefocusComposerAfterAction({ defer: true });
}

function _cliAppendTourSampleChip(sample, tabId = null) {
  const command = String(sample || '').trim();
  if (!command) return;
  const rendered = _cliAppendTourDomLine('', 'builtin-help-row builtin-tour-sample', tabId);
  if (!rendered || typeof document === 'undefined') {
    _tourAppendLine(command, 'builtin-help-row builtin-tour-sample', tabId, { faq_command: command });
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
  _tourPreserveOutputTail(tabId, true);
}

function _isTourTabActive(tabId = null) {
  if (!tabId) return true;
  return _tourActiveTabId() === tabId;
}

function _tourWaitForContinue(tabId = null, isLastChapter = false) {
  const prompt = isLastChapter
    ? 'Press any key to finish, or press q to quit the tour.'
    : 'Press any key to continue, or press q to quit the tour.';
  _cliAppendTourDomLine(prompt, 'builtin-note builtin-tour-prompt', tabId);
  _tourPreserveOutputTail(tabId, true);
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
  const preserveTail = _tourShouldPreserveOutputTail(tabId);
  _tourAppendCommandEcho(cmd, tabId);

  if (!(_tourConfig().tour_enabled === true)) {
    _tourAppendLine('tour: onboarding tour is disabled on this shell', 'exit-fail', tabId);
    _tourSetStatus('fail');
    return true;
  }

  if (parts.length > 1 && !['help', '--help', '-h'].includes(sub)) {
    _tourAppendLine('usage: tour', 'exit-fail', tabId);
    _tourSetStatus('fail');
    return true;
  }

  if (['help', '--help', '-h'].includes(sub)) {
    _tourAppendLine('usage: tour', '', tabId);
    _tourAppendLine('Print the onboarding tour inside the terminal.', 'builtin-note', tabId);
    _tourRecordSuccess(cmd);
    _tourSetStatus('ok');
    return true;
  }

  const recordOpened = (typeof importedRecordTourOpenedOnceThisSession === 'function'
    && importedRecordTourOpenedOnceThisSession)
    || _tourGlobalFunction('_recordTourOpenedOnceThisSession');
  if (typeof recordOpened === 'function') await recordOpened();
  const chapters = _tourChaptersForCurrentViewport();
  if (!chapters.length) {
    _tourAppendLine('tour: no onboarding chapters are visible for this shell', 'exit-fail', tabId);
    _tourSetStatus('fail');
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
  _tourPreserveOutputTail(tabId, preserveTail);
  _tourRecordSuccess(cmd);
  _tourSetStatus('ok');
  return true;
}

if (typeof window !== 'undefined') {
} else {
  TOUR_CLI_GLOBAL.handleTourCommand = handleTourCommand;
}

export { handleTourCommand };
