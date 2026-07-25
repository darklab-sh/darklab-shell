// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// ── Terminal-native theme/config commands ──
import { getActiveTabId, getTab as importedGetTab } from '../../core/state.js';
import { DarklabPreferenceCore as importedPreferenceCore } from '../../core/app_preferences_core.js';
import { getLineNumberMode, getTimestampMode, _stickOutputToBottom as importedStickOutputToBottom } from '../../output.js';
import { getOutput as importedGetOutput, updateOutputFollowButton as importedUpdateOutputFollowButton } from '../../tabs.js';
import {
  applyLineNumberPreference as importedApplyLineNumberPreference,
  applyTimestampPreference as importedApplyTimestampPreference,
  applyWelcomeIntroPreference as importedApplyWelcomeIntroPreference,
  getWelcomeIntroPreference as importedGetWelcomeIntroPreference,
  applyShareRedactionDefaultPreference as importedApplyShareRedactionDefaultPreference,
  getShareRedactionDefaultPreference as importedGetShareRedactionDefaultPreference,
  applyProjectAutoLinkExternalRunsPreference as importedApplyProjectAutoLinkExternalRunsPreference,
  getProjectAutoLinkExternalRunsPreference as importedGetProjectAutoLinkExternalRunsPreference,
  applyProjectAutoLinkRunEntitiesPreference as importedApplyProjectAutoLinkRunEntitiesPreference,
  getProjectAutoLinkRunEntitiesPreference as importedGetProjectAutoLinkRunEntitiesPreference,
  applyRunNotifyPreference as importedApplyRunNotifyPreference,
  getRunNotifyPreference as importedGetRunNotifyPreference,
  applyCommandOutcomeSummariesPreference as importedApplyCommandOutcomeSummariesPreference,
  getCommandOutcomeSummariesPreference as importedGetCommandOutcomeSummariesPreference,
  applyHudClockPreference as importedApplyHudClockPreference,
  getHudClockPreference as importedGetHudClockPreference,
  applyCompareViewModePreference as importedApplyCompareViewModePreference,
  getCompareViewModePreference as importedGetCompareViewModePreference,
  applyCompareContextPreference as importedApplyCompareContextPreference,
  getCompareContextPreference as importedGetCompareContextPreference,
  applyPromptUsernamePreference as importedApplyPromptUsernamePreference,
  getPromptUsernamePreference as importedGetPromptUsernamePreference,
} from '../preferences/preferences.js';
import {
  _compareThemeEntries as importedCompareThemeEntries,
  _findThemeEntry as importedFindThemeEntry,
  _getThemeThemes as importedGetThemeThemes,
  _normalizeThemeName as importedNormalizeThemeName,
  _resolveThemeEntry as importedResolveThemeEntry,
  _savedThemeName as importedSavedThemeName,
  applyThemeSelection as importedApplyThemeSelection,
} from '../theme/theme.js';
const LOCAL_COMMAND_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _cliGlobalFunction(name) {
  const fn = LOCAL_COMMAND_GLOBAL?.[name];
  return typeof fn === 'function' ? fn : null;
}

function _cliRequireExecution(execution) {
  if (!execution || typeof execution.appendLine !== 'function') {
    throw new Error('Terminal-native commands require a command execution');
  }
  return execution;
}

function _cliGetTab(id) {
  const getTab = (typeof importedGetTab !== 'undefined' && importedGetTab)
    || _cliGlobalFunction('getTab');
  return typeof getTab === 'function' ? getTab(id) : null;
}

function _cliGetOutput(id) {
  const getOutput = (typeof importedGetOutput !== 'undefined' && importedGetOutput)
    || _cliGlobalFunction('getOutput');
  return typeof getOutput === 'function' ? getOutput(id) : null;
}

function _cliActiveTabId() {
  const importedId = typeof getActiveTabId === 'function' ? getActiveTabId() : null;
  return importedId || LOCAL_COMMAND_GLOBAL?.activeTabId || null;
}

function _cliAppendLine(text, cls = '', tabId = null, metadata = null, execution) {
  _cliRequireExecution(execution).appendLine(text, cls, tabId, metadata);
}

function _cliShouldPreserveOutputTail(tabId = null) {
  const id = tabId || _cliActiveTabId();
  const tab = _cliGetTab(id);
  return !!tab && tab.followOutput !== false;
}

function _cliPreserveOutputTail(tabId = null, shouldPreserve = true) {
  if (!shouldPreserve) return;
  const id = tabId || _cliActiveTabId();
  const tab = _cliGetTab(id);
  const out = _cliGetOutput(id);
  if (tab) tab.followOutput = true;
  const stickOutputToBottom = (typeof importedStickOutputToBottom !== 'undefined' && importedStickOutputToBottom)
    || _cliGlobalFunction('_stickOutputToBottom');
  if (out && stickOutputToBottom) {
    stickOutputToBottom(out, tab);
  } else if (out) {
    out.scrollTop = out.scrollHeight;
  }
  const updateOutputFollowButton = (typeof importedUpdateOutputFollowButton !== 'undefined' && importedUpdateOutputFollowButton)
    || _cliGlobalFunction('updateOutputFollowButton');
  if (updateOutputFollowButton) updateOutputFollowButton(id);
}

function _cliSetStatus(statusValue, execution) {
  _cliRequireExecution(execution).setStatus(statusValue);
}

function _cliRecordSuccess(_command, execution) {
  _cliRequireExecution(execution).setRecordRecent(true);
}

function _cliPreferenceCore() {
  return (typeof importedPreferenceCore !== 'undefined' && importedPreferenceCore) || {};
}

function _cliTimestampModes() {
  return Array.isArray(LOCAL_COMMAND_GLOBAL?._tsModes)
    ? LOCAL_COMMAND_GLOBAL._tsModes.slice()
    : ['off', 'elapsed', 'clock'];
}

function _cliTimestampMode() {
  const mode = typeof getTimestampMode === 'function'
    ? getTimestampMode()
    : (typeof LOCAL_COMMAND_GLOBAL?.tsMode === 'string' ? LOCAL_COMMAND_GLOBAL.tsMode : 'off');
  return _cliTimestampModes().includes(mode) ? mode : 'off';
}

function _cliLineNumberMode() {
  const mode = typeof getLineNumberMode === 'function'
    ? getLineNumberMode()
    : (typeof LOCAL_COMMAND_GLOBAL?.lnMode === 'string' ? LOCAL_COMMAND_GLOBAL.lnMode : 'off');
  return mode === 'on' ? 'on' : 'off';
}

function _cliPreferenceFunction(importedFn, name) {
  return (typeof importedFn !== 'undefined' && importedFn)
    || _cliGlobalFunction(name);
}

function _cliThemeSlug(entry) {
  const normalizeThemeName = (typeof importedNormalizeThemeName !== 'undefined' && importedNormalizeThemeName)
    || _cliGlobalFunction('_normalizeThemeName');
  return typeof normalizeThemeName === 'function'
    ? normalizeThemeName(entry?.name || entry?.filename || '')
    : String(entry?.name || entry?.filename || '').trim().replace(/\.yaml$/, '');
}

function _cliThemeEntries() {
  const getThemeThemes = (typeof importedGetThemeThemes !== 'undefined' && importedGetThemeThemes)
    || _cliGlobalFunction('_getThemeThemes');
  const compareThemeEntries = (typeof importedCompareThemeEntries !== 'undefined' && importedCompareThemeEntries)
    || _cliGlobalFunction('_compareThemeEntries');
  const entries = typeof getThemeThemes === 'function' ? getThemeThemes() : [];
  const compare = typeof compareThemeEntries === 'function' ? compareThemeEntries : undefined;
  return [...entries].sort(compare).filter(entry => _cliThemeSlug(entry));
}

function _cliThemeColorScheme(entry) {
  const scheme = String(entry?.color_scheme || '').trim().toLowerCase();
  if (scheme === 'light' || scheme === 'only light') return 'light';
  if (scheme === 'dark' || scheme === 'only dark') return 'dark';
  return 'other';
}

function _cliThemeColorSchemeLabel(scheme) {
  if (scheme === 'light') return 'Light themes:';
  if (scheme === 'dark') return 'Dark themes:';
  return 'Other themes:';
}

function _cliThemeEntriesByColorScheme() {
  const grouped = { dark: [], light: [], other: [] };
  _cliThemeEntries().forEach((entry) => {
    grouped[_cliThemeColorScheme(entry)].push(entry);
  });
  return grouped;
}

function _cliCurrentThemeEntry() {
  const resolveThemeEntry = (typeof importedResolveThemeEntry !== 'undefined' && importedResolveThemeEntry)
    || _cliGlobalFunction('_resolveThemeEntry');
  const savedThemeName = (typeof importedSavedThemeName !== 'undefined' && importedSavedThemeName)
    || _cliGlobalFunction('_savedThemeName');
  const savedName = typeof savedThemeName === 'function' ? savedThemeName() : '';
  return typeof resolveThemeEntry === 'function' ? resolveThemeEntry(document.body?.dataset?.theme || savedName) : null;
}

function _cliCurrentThemeSlug() {
  return _cliThemeSlug(_cliCurrentThemeEntry());
}

function _formatCliRecord(key, value, width = 18) {
  return `${key.padEnd(width)}  ${value}`;
}

function _formatCliTableRow(values, widths) {
  const lastIndex = values.length - 1;
  return values.map((value, index) => (
    index === lastIndex ? String(value || '') : String(value || '').padEnd(widths[index] || 0)
  )).join('  ');
}

function _cliThemeDescription(entry) {
  const label = String(entry?.label || entry?.name || '').trim();
  const slug = _cliThemeSlug(entry);
  const current = slug && slug === _cliCurrentThemeSlug();
  return `${label || slug}${current ? ' (current)' : ''}`;
}

async function handleThemeCommand(cmd, tabId = null, execution) {
  _cliRequireExecution(execution);
  const parts = String(cmd || '').trim().split(/\s+/).filter(Boolean);
  const sub = (parts[1] || '').toLowerCase();

  if (parts.length === 1 || sub === 'list') {
    const current = _cliCurrentThemeEntry();
    _cliAppendLine(_formatCliRecord('current theme', _cliThemeDescription(current)), 'builtin-kv', tabId, null, execution);
    _cliAppendLine('', 'builtin-spacer', tabId, null, execution);
    _cliAppendLine('Available themes:', 'builtin-section', tabId, null, execution);
    const grouped = _cliThemeEntriesByColorScheme();
    ['dark', 'light', 'other'].forEach((scheme) => {
      const entries = grouped[scheme] || [];
      if (!entries.length) return;
      _cliAppendLine(_cliThemeColorSchemeLabel(scheme), 'builtin-section', tabId, null, execution);
      entries.forEach((entry) => {
        const slug = _cliThemeSlug(entry);
        const marker = slug === _cliCurrentThemeSlug() ? '*' : ' ';
        _cliAppendLine(`  ${marker} ${slug.padEnd(24)}  ${String(entry.label || slug)}`, 'builtin-help-row builtin-plain', tabId, null, execution);
      });
    });
    _cliRecordSuccess(cmd, execution);
    _cliSetStatus('ok', execution);
    return true;
  }

  if (sub === 'current') {
    _cliAppendLine(_formatCliRecord('current theme', _cliThemeDescription(_cliCurrentThemeEntry())), 'builtin-kv', tabId, null, execution);
    _cliRecordSuccess(cmd, execution);
    _cliSetStatus('ok', execution);
    return true;
  }

  const requested = sub === 'set' ? parts.slice(2).join(' ').trim() : '';
  if (!requested) {
    _cliAppendLine('usage: theme [list | current | set <theme>]', '', tabId, null, execution);
    _cliSetStatus('fail', execution);
    return true;
  }

  const findThemeEntry = (typeof importedFindThemeEntry !== 'undefined' && importedFindThemeEntry)
    || _cliGlobalFunction('_findThemeEntry');
  const entry = typeof findThemeEntry === 'function' ? findThemeEntry(requested) : null;
  if (!entry) {
    _cliAppendLine(`theme: unknown theme '${requested}'`, 'exit-fail', tabId, null, execution);
    _cliAppendLine("run 'theme list' to see available themes", '', tabId, null, execution);
    _cliSetStatus('fail', execution);
    return true;
  }

  const applyThemeSelection = (typeof importedApplyThemeSelection !== 'undefined' && importedApplyThemeSelection)
    || _cliGlobalFunction('applyThemeSelection');
  if (typeof applyThemeSelection === 'function') applyThemeSelection(entry.name);
  _cliAppendLine(`theme set: ${_cliThemeDescription(entry)}`, '', tabId, null, execution);
  _cliRecordSuccess(cmd, execution);
  _cliSetStatus('ok', execution);
  return true;
}

const _cliConfigValueLabels = {
  animated: 'animated',
  static: 'static',
  off: 'off',
  ask: 'ask',
};

function _cliNormalizeValue(value) {
  return String(value || '').trim().toLowerCase().replace(/_/g, '-');
}

function _cliNormalizePromptUsernameValue(value) {
  const raw = String(value || '').trim();
  const normalized = _cliNormalizeValue(raw);
  if (['default', 'clear', 'unset', 'server-default'].includes(normalized)) return '';
  const normalize = _cliPreferenceCore().normalizePromptUsername;
  return typeof normalize === 'function' ? normalize(raw) || null : null;
}

function _cliConfigEntries() {
  const preferenceCore = _cliPreferenceCore();
  const hudClockModes = Array.isArray(preferenceCore.HUD_CLOCK_MODES)
    ? preferenceCore.HUD_CLOCK_MODES
    : ['utc', 'local'];
  return [
    {
      key: 'line-numbers',
      description: 'Show line numbers beside output and the live prompt',
      values: ['on', 'off'],
      get: () => _cliLineNumberMode(),
      set: (value) => {
        const applyLineNumberPreference = _cliPreferenceFunction(
          typeof importedApplyLineNumberPreference !== 'undefined' ? importedApplyLineNumberPreference : null,
          'applyLineNumberPreference',
        );
        return typeof applyLineNumberPreference === 'function' ? applyLineNumberPreference(value) : undefined;
      },
    },
    {
      key: 'timestamps',
      description: 'Timestamp display mode',
      values: _cliTimestampModes(),
      get: () => _cliTimestampMode(),
      set: (value) => {
        const applyTimestampPreference = _cliPreferenceFunction(
          typeof importedApplyTimestampPreference !== 'undefined' ? importedApplyTimestampPreference : null,
          'applyTimestampPreference',
        );
        return typeof applyTimestampPreference === 'function' ? applyTimestampPreference(value) : undefined;
      },
    },
    {
      key: 'welcome',
      description: 'Welcome intro behavior',
      values: ['animated', 'static', 'off'],
      aliases: { disable_animation: 'static', disable: 'static', remove: 'off', removed: 'off' },
      toStored: { animated: 'animated', static: 'disable_animation', off: 'remove' },
      fromStored: { animated: 'animated', disable_animation: 'static', remove: 'off' },
      get: function getWelcomeCliValue() {
        const getWelcomeIntroPreference = _cliPreferenceFunction(
          typeof importedGetWelcomeIntroPreference !== 'undefined' ? importedGetWelcomeIntroPreference : null,
          'getWelcomeIntroPreference',
        );
        const value = typeof getWelcomeIntroPreference === 'function' ? getWelcomeIntroPreference() : 'animated';
        return this.fromStored[value] || 'animated';
      },
      set: function setWelcomeCliValue(value) {
        const applyWelcomeIntroPreference = _cliPreferenceFunction(
          typeof importedApplyWelcomeIntroPreference !== 'undefined' ? importedApplyWelcomeIntroPreference : null,
          'applyWelcomeIntroPreference',
        );
        if (typeof applyWelcomeIntroPreference === 'function') applyWelcomeIntroPreference(this.toStored[value] || value);
      },
    },
    {
      key: 'share-redaction',
      description: 'Default redaction behavior for shared snapshots',
      values: ['ask', 'redacted', 'raw'],
      aliases: { unset: 'ask', prompt: 'ask', redacted: 'redacted', raw: 'raw' },
      toStored: { ask: 'unset', redacted: 'redacted', raw: 'raw' },
      fromStored: { unset: 'ask', redacted: 'redacted', raw: 'raw' },
      get: function getShareRedactionCliValue() {
        const getShareRedactionDefaultPreference = _cliPreferenceFunction(
          typeof importedGetShareRedactionDefaultPreference !== 'undefined' ? importedGetShareRedactionDefaultPreference : null,
          'getShareRedactionDefaultPreference',
        );
        const value = typeof getShareRedactionDefaultPreference === 'function' ? getShareRedactionDefaultPreference() : 'unset';
        return this.fromStored[value] || 'ask';
      },
      set: function setShareRedactionCliValue(value) {
        const applyShareRedactionDefaultPreference = _cliPreferenceFunction(
          typeof importedApplyShareRedactionDefaultPreference !== 'undefined' ? importedApplyShareRedactionDefaultPreference : null,
          'applyShareRedactionDefaultPreference',
        );
        if (typeof applyShareRedactionDefaultPreference === 'function') applyShareRedactionDefaultPreference(this.toStored[value] || value);
      },
    },
    {
      key: 'project-auto-link-runs',
      description: 'Add completed external command runs to the active project',
      values: ['on', 'off'],
      get: () => {
        const getProjectAutoLinkExternalRunsPreference = _cliPreferenceFunction(
          typeof importedGetProjectAutoLinkExternalRunsPreference !== 'undefined' ? importedGetProjectAutoLinkExternalRunsPreference : null,
          'getProjectAutoLinkExternalRunsPreference',
        );
        return typeof getProjectAutoLinkExternalRunsPreference === 'function' ? getProjectAutoLinkExternalRunsPreference() : 'on';
      },
      set: (value) => {
        const applyProjectAutoLinkExternalRunsPreference = _cliPreferenceFunction(
          typeof importedApplyProjectAutoLinkExternalRunsPreference !== 'undefined' ? importedApplyProjectAutoLinkExternalRunsPreference : null,
          'applyProjectAutoLinkExternalRunsPreference',
        );
        return typeof applyProjectAutoLinkExternalRunsPreference === 'function' ? applyProjectAutoLinkExternalRunsPreference(value) : undefined;
      },
    },
    {
      key: 'project-auto-link-run-entities',
      description: 'Add generated Atlas entities when an auto-linked run is added to the active project',
      values: ['on', 'off'],
      get: () => {
        const getProjectAutoLinkRunEntitiesPreference = _cliPreferenceFunction(
          typeof importedGetProjectAutoLinkRunEntitiesPreference !== 'undefined' ? importedGetProjectAutoLinkRunEntitiesPreference : null,
          'getProjectAutoLinkRunEntitiesPreference',
        );
        return typeof getProjectAutoLinkRunEntitiesPreference === 'function' ? getProjectAutoLinkRunEntitiesPreference() : 'on';
      },
      set: (value) => {
        const applyProjectAutoLinkRunEntitiesPreference = _cliPreferenceFunction(
          typeof importedApplyProjectAutoLinkRunEntitiesPreference !== 'undefined' ? importedApplyProjectAutoLinkRunEntitiesPreference : null,
          'applyProjectAutoLinkRunEntitiesPreference',
        );
        return typeof applyProjectAutoLinkRunEntitiesPreference === 'function' ? applyProjectAutoLinkRunEntitiesPreference(value) : undefined;
      },
    },
    {
      key: 'run-notifications',
      description: 'Desktop notification when a run completes or is killed',
      values: ['on', 'off'],
      get: () => {
        const getRunNotifyPreference = _cliPreferenceFunction(
          typeof importedGetRunNotifyPreference !== 'undefined' ? importedGetRunNotifyPreference : null,
          'getRunNotifyPreference',
        );
        return typeof getRunNotifyPreference === 'function' ? getRunNotifyPreference() : 'off';
      },
      set: (value) => {
        const applyRunNotifyPreference = _cliPreferenceFunction(
          typeof importedApplyRunNotifyPreference !== 'undefined' ? importedApplyRunNotifyPreference : null,
          'applyRunNotifyPreference',
        );
        return typeof applyRunNotifyPreference === 'function' ? applyRunNotifyPreference(value) : undefined;
      },
    },
    {
      key: 'command-outcome-summaries',
      description: 'Show short app-generated summaries below completed command output',
      values: ['on', 'off'],
      get: () => {
        const getCommandOutcomeSummariesPreference = _cliPreferenceFunction(
          typeof importedGetCommandOutcomeSummariesPreference !== 'undefined' ? importedGetCommandOutcomeSummariesPreference : null,
          'getCommandOutcomeSummariesPreference',
        );
        return typeof getCommandOutcomeSummariesPreference === 'function' ? getCommandOutcomeSummariesPreference() : 'on';
      },
      set: (value) => {
        const applyCommandOutcomeSummariesPreference = _cliPreferenceFunction(
          typeof importedApplyCommandOutcomeSummariesPreference !== 'undefined' ? importedApplyCommandOutcomeSummariesPreference : null,
          'applyCommandOutcomeSummariesPreference',
        );
        return typeof applyCommandOutcomeSummariesPreference === 'function' ? applyCommandOutcomeSummariesPreference(value) : undefined;
      },
    },
    {
      key: 'hud-clock',
      description: 'HUD clock timezone',
      values: hudClockModes.slice(),
      get: () => {
        const getHudClockPreference = _cliPreferenceFunction(
          typeof importedGetHudClockPreference !== 'undefined' ? importedGetHudClockPreference : null,
          'getHudClockPreference',
        );
        return typeof getHudClockPreference === 'function' ? getHudClockPreference() : 'utc';
      },
      set: (value) => {
        const applyHudClockPreference = _cliPreferenceFunction(
          typeof importedApplyHudClockPreference !== 'undefined' ? importedApplyHudClockPreference : null,
          'applyHudClockPreference',
        );
        return typeof applyHudClockPreference === 'function' ? applyHudClockPreference(value) : undefined;
      },
    },
    {
      key: 'compare-view',
      description: 'Default run comparison view',
      values: ['auto', 'side-by-side', 'unified', 'changes-only', 'findings-only'],
      aliases: {
        automatic: 'auto',
        responsive: 'auto',
        default: 'auto',
        split: 'side-by-side',
        sidebyside: 'side-by-side',
        changes: 'changes-only',
        findings: 'findings-only',
      },
      toStored: {
        auto: 'auto',
        'side-by-side': 'side_by_side',
        unified: 'unified',
        'changes-only': 'changes_only',
        'findings-only': 'findings_only',
      },
      fromStored: {
        auto: 'auto',
        side_by_side: 'side-by-side',
        unified: 'unified',
        changes_only: 'changes-only',
        findings_only: 'findings-only',
      },
      get: function getCompareViewCliValue() {
        const getCompareViewModePreference = _cliPreferenceFunction(
          typeof importedGetCompareViewModePreference !== 'undefined' ? importedGetCompareViewModePreference : null,
          'getCompareViewModePreference',
        );
        const value = typeof getCompareViewModePreference === 'function' ? getCompareViewModePreference() : 'auto';
        return this.fromStored[value] || 'auto';
      },
      set: function setCompareViewCliValue(value) {
        const applyCompareViewModePreference = _cliPreferenceFunction(
          typeof importedApplyCompareViewModePreference !== 'undefined' ? importedApplyCompareViewModePreference : null,
          'applyCompareViewModePreference',
        );
        if (typeof applyCompareViewModePreference === 'function') applyCompareViewModePreference(this.toStored[value] || value);
      },
    },
    {
      key: 'compare-context',
      description: 'Default unchanged-line context in run comparison',
      values: ['3', '10', 'all'],
      aliases: { default: '3', minimal: '3', expanded: '10', full: 'all' },
      get: () => {
        const getCompareContextPreference = _cliPreferenceFunction(
          typeof importedGetCompareContextPreference !== 'undefined' ? importedGetCompareContextPreference : null,
          'getCompareContextPreference',
        );
        return typeof getCompareContextPreference === 'function' ? getCompareContextPreference() : '3';
      },
      set: (value) => {
        const applyCompareContextPreference = _cliPreferenceFunction(
          typeof importedApplyCompareContextPreference !== 'undefined' ? importedApplyCompareContextPreference : null,
          'applyCompareContextPreference',
        );
        return typeof applyCompareContextPreference === 'function' ? applyCompareContextPreference(value) : undefined;
      },
    },
    {
      key: 'prompt-username',
      description: 'Username shown before the prompt domain',
      values: null,
      valueHelp: '<username> | default',
      get: () => {
        const getPromptUsernamePreference = _cliPreferenceFunction(
          typeof importedGetPromptUsernamePreference !== 'undefined' ? importedGetPromptUsernamePreference : null,
          'getPromptUsernamePreference',
        );
        return (typeof getPromptUsernamePreference === 'function' ? getPromptUsernamePreference() : '') || 'default';
      },
      normalize: _cliNormalizePromptUsernameValue,
      set: (value) => {
        const applyPromptUsernamePreference = _cliPreferenceFunction(
          typeof importedApplyPromptUsernamePreference !== 'undefined' ? importedApplyPromptUsernamePreference : null,
          'applyPromptUsernamePreference',
        );
        return typeof applyPromptUsernamePreference === 'function' ? applyPromptUsernamePreference(value) : undefined;
      },
    },
  ];
}

function _findCliConfigEntry(key) {
  const normalized = _cliNormalizeValue(key);
  return _cliConfigEntries().find(entry => entry.key === normalized) || null;
}

function _normalizeCliConfigEntryValue(entry, value) {
  if (typeof entry.normalize === 'function') {
    const normalized = entry.normalize(value);
    return normalized === '' || normalized ? normalized : null;
  }
  const normalized = _cliNormalizeValue(value);
  const aliased = entry.aliases && Object.prototype.hasOwnProperty.call(entry.aliases, normalized)
    ? entry.aliases[normalized]
    : normalized;
  return entry.values.includes(aliased) ? aliased : null;
}

function _cliConfigDisplayValue(value) {
  return _cliConfigValueLabels[value] || value;
}

function _printCliConfigEntry(entry, tabId, execution = null) {
  _cliAppendLine(
    _formatCliRecord(entry.key, _cliConfigDisplayValue(entry.get()), 19),
    'builtin-kv',
    tabId,
    null,
    execution,
  );
}

function _printCliConfigList(tabId, execution = null) {
  _cliAppendLine('Current user config:', 'builtin-section', tabId, null, execution);
  const rows = _cliConfigEntries().map(entry => ({
    option: entry.key,
    value: _cliConfigDisplayValue(entry.get()),
  }));
  const widths = [
    Math.max('option'.length, ...rows.map(row => row.option.length)),
    Math.max('value'.length, ...rows.map(row => row.value.length)),
  ];
  _cliAppendLine(_formatCliTableRow(['option', 'value'], widths), 'builtin-table-header', tabId, null, execution);
  rows.forEach(row => {
    _cliAppendLine(_formatCliTableRow([row.option, row.value], widths), 'builtin-table-row', tabId, null, execution);
  });
}

async function handleConfigCommand(cmd, tabId = null, execution) {
  _cliRequireExecution(execution);
  const parts = String(cmd || '').trim().split(/\s+/).filter(Boolean);
  const sub = (parts[1] || '').toLowerCase();
  const preserveTail = _cliShouldPreserveOutputTail(tabId);

  if (parts.length === 1 || sub === 'list') {
    _printCliConfigList(tabId, execution);
    _cliRecordSuccess(cmd, execution);
    _cliSetStatus('ok', execution);
    return true;
  }

  if (sub === 'get') {
    const key = parts[2] || '';
    const entry = _findCliConfigEntry(key);
    if (!entry) {
      _cliAppendLine(`config: unknown option '${key}'`, 'exit-fail', tabId, null, execution);
      _cliAppendLine("run 'config list' to see available options", '', tabId, null, execution);
      _cliSetStatus('fail', execution);
      return true;
    }
    _printCliConfigEntry(entry, tabId, execution);
    _cliRecordSuccess(cmd, execution);
    _cliSetStatus('ok', execution);
    return true;
  }

  const isSet = sub === 'set';
  const key = isSet ? parts[2] : '';
  const value = isSet ? parts[3] : '';
  const entry = _findCliConfigEntry(key);

  if (!entry || !value) {
    _cliAppendLine('usage: config [list | get <option> | set <option> <value>]', '', tabId, null, execution);
    _cliSetStatus('fail', execution);
    return true;
  }

  const normalizedValue = _normalizeCliConfigEntryValue(entry, value);
  if (normalizedValue === null) {
    _cliAppendLine(`config: invalid value '${value}' for ${entry.key}`, 'exit-fail', tabId, null, execution);
    _cliAppendLine(`allowed values: ${entry.values ? entry.values.join(', ') : entry.valueHelp}`, '', tabId, null, execution);
    _cliSetStatus('fail', execution);
    return true;
  }

  await entry.set(normalizedValue);
  _cliAppendLine(`config set: ${entry.key}=${_cliConfigDisplayValue(entry.get())}`, '', tabId, null, execution);
  _cliPreserveOutputTail(tabId, preserveTail);
  _cliRecordSuccess(cmd, execution);
  _cliSetStatus('ok', execution);
  return true;
}

if (typeof window !== 'undefined') {
}

export {
  _cliAppendLine,
  _cliConfigEntries,
  _cliPreserveOutputTail,
  _cliRecordSuccess,
  _cliSetStatus,
  _cliShouldPreserveOutputTail,
  _cliThemeDescription,
  _cliThemeEntries,
  _cliThemeSlug,
  handleConfigCommand,
  handleThemeCommand,
};
