// darklab_shell session preference helpers and Options modal preference syncing.

import { DarklabPreferenceCore as importedPreferenceCore } from '../../core/app_preferences_core.js';
import { APP_CONFIG as importedAppConfig } from '../../core/config.js';
import {
  optionsCommandOutcomeSummariesToggle,
  optionsCompareContextSelect,
  optionsCompareViewModeSelect,
  optionsHudClockSelect,
  optionsLnToggle,
  optionsNotifyToggle,
  optionsProjectAutoLinkExternalRunsToggle,
  optionsProjectAutoLinkRunEntitiesToggle,
  optionsPromptUsernameError,
  optionsPromptUsernameInput,
  optionsShareRedactionSelect,
  optionsTsSelect,
  optionsWelcomeSelect,
} from '../../core/dom.js';
import {
  _defaultThemeEntry as importedDefaultThemeEntry,
  _savedThemeName as importedSavedThemeName,
  applyThemeSelection as importedApplyThemeSelection,
} from '../theme/theme.js';
import {
  _setLnMode as importedSetLineNumberMode,
  _setTsMode as importedSetTimestampMode,
  getLineNumberMode,
  getTimestampMode,
  refreshCommandOutcomeSummaries as importedRefreshCommandOutcomeSummaries,
} from '../../output.js';
import {
  apiFetch as importedApiFetch,
  logClientError as importedLogClientError,
} from '../../runtime_bridge.js';
import { showToast as importedShowToast } from '../../core/utils.js';
import { syncAppSelect as importedSyncAppSelect } from '../../ui/ui_helpers.js';
import { getActiveProjectContext as importedGetActiveProjectContext } from '../projects/project_context_bridge.js';
import {
  getComposerPromptMode as importedGetComposerPromptMode,
  hidePromptUsernameSavedIndicator as importedHidePromptUsernameSavedIndicator,
  setComposerPromptMode as importedSetComposerPromptMode,
  showPromptUsernameSavedIndicator as importedShowPromptUsernameSavedIndicator,
  syncShellPrompt as importedSyncShellPrompt,
} from '../terminal/composer_prompt_bridge.js';
import { renderHudClock as importedRenderHudClock } from '../projects/project_hud_bridge.js';

const PreferenceCore = typeof importedPreferenceCore !== 'undefined' && importedPreferenceCore
  ? importedPreferenceCore
  : null;
const PREFERENCE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;
const _welcomeIntroModes = PreferenceCore.WELCOME_INTRO_MODES;
const _shareRedactionDefaultModes = PreferenceCore.SHARE_REDACTION_DEFAULT_MODES;
const _hudClockModes = PreferenceCore.HUD_CLOCK_MODES;
function _timestampModes() {
  return Array.isArray(PREFERENCE_GLOBAL?._tsModes) ? PREFERENCE_GLOBAL._tsModes : ['off', 'elapsed', 'clock'];
}

function _preferenceGlobalFunction(name) {
  const fn = PREFERENCE_GLOBAL?.[name];
  return typeof fn === 'function' ? fn : null;
}

function _preferenceAppConfig() {
  return (typeof importedAppConfig !== 'undefined' && importedAppConfig)
    || PREFERENCE_GLOBAL?.APP_CONFIG
    || {};
}

function _preferenceDefaultThemeEntry() {
  const defaultThemeEntry = (typeof importedDefaultThemeEntry !== 'undefined' && importedDefaultThemeEntry)
    || _preferenceGlobalFunction('_defaultThemeEntry');
  return typeof defaultThemeEntry === 'function' ? defaultThemeEntry() : null;
}

function _preferenceSavedThemeName() {
  const savedThemeName = (typeof importedSavedThemeName !== 'undefined' && importedSavedThemeName)
    || _preferenceGlobalFunction('_savedThemeName');
  return typeof savedThemeName === 'function' ? savedThemeName() : '';
}

function _preferenceSessionId() {
  return typeof PREFERENCE_GLOBAL?.SESSION_ID === 'string' ? PREFERENCE_GLOBAL.SESSION_ID : '';
}

function _preferenceApiFetch(...args) {
  const fetcher = (typeof importedApiFetch === 'function' && importedApiFetch)
    || _preferenceGlobalFunction('apiFetch');
  if (!fetcher) throw new Error('apiFetch is not available');
  return fetcher(...args);
}

function _preferenceLogClientError(message, err) {
  const log = (typeof importedLogClientError === 'function' && importedLogClientError)
    || _preferenceGlobalFunction('logClientError');
  if (log) log(message, err);
}

function _preferenceShowToast(message) {
  const toast = (typeof importedShowToast !== 'undefined' && importedShowToast)
    || _preferenceGlobalFunction('showToast');
  if (toast) toast(message);
}

function _preferenceSyncAppSelect(select) {
  const sync = (typeof importedSyncAppSelect !== 'undefined' && importedSyncAppSelect)
    || _preferenceGlobalFunction('syncAppSelect');
  if (sync) sync(select);
}

function _preferenceComposerPromptMode() {
  const readMode = (typeof importedGetComposerPromptMode === 'function' && importedGetComposerPromptMode)
    || _preferenceGlobalFunction('getComposerPromptMode');
  return typeof readMode === 'function' ? readMode() : null;
}

function _preferenceHidePromptUsernameSavedIndicator() {
  const hide = (typeof importedHidePromptUsernameSavedIndicator === 'function' && importedHidePromptUsernameSavedIndicator)
    || _preferenceGlobalFunction('hidePromptUsernameSavedIndicator');
  if (typeof hide === 'function') hide();
}

function _preferenceShowPromptUsernameSavedIndicator() {
  const show = (typeof importedShowPromptUsernameSavedIndicator === 'function' && importedShowPromptUsernameSavedIndicator)
    || _preferenceGlobalFunction('showPromptUsernameSavedIndicator');
  if (typeof show === 'function') show();
}

function _preferenceSetComposerPromptMode(mode) {
  const setMode = (typeof importedSetComposerPromptMode === 'function' && importedSetComposerPromptMode)
    || _preferenceGlobalFunction('setComposerPromptMode');
  if (typeof setMode === 'function') {
    setMode(mode);
    return true;
  }
  return false;
}

function _preferenceSyncShellPrompt() {
  const sync = (typeof importedSyncShellPrompt === 'function' && importedSyncShellPrompt)
    || _preferenceGlobalFunction('syncShellPrompt');
  if (typeof sync === 'function') sync();
}

function _preferenceTimestampMode() {
  const readTimestampMode = _preferenceGlobalFunction('getTimestampMode')
    || (typeof getTimestampMode === 'function' ? getTimestampMode : null);
  let mode = readTimestampMode
    ? readTimestampMode()
    : (typeof PREFERENCE_GLOBAL?.tsMode === 'string' ? PREFERENCE_GLOBAL.tsMode : 'off');
  if (!_timestampModes().includes(mode) && typeof document !== 'undefined') {
    if (document.body.classList.contains('ts-elapsed')) mode = 'elapsed';
    else if (document.body.classList.contains('ts-clock')) mode = 'clock';
  }
  if (mode === 'off' && typeof document !== 'undefined') {
    if (document.body.classList.contains('ts-elapsed')) mode = 'elapsed';
    else if (document.body.classList.contains('ts-clock')) mode = 'clock';
  }
  return _timestampModes().includes(mode) ? mode : 'off';
}

function _preferenceLineNumberMode() {
  const mode = typeof getLineNumberMode === 'function'
    ? getLineNumberMode()
    : (typeof PREFERENCE_GLOBAL?.lnMode === 'string' ? PREFERENCE_GLOBAL.lnMode : 'off');
  return mode === 'on' ? 'on' : 'off';
}

const PREF_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;
const _sessionPreferenceKeys = PreferenceCore.SESSION_PREFERENCE_KEYS;
var _sessionPreferenceOverrides = null;
var _sessionPreferencePersistQueue = Promise.resolve();
let _sessionPreferenceLocalRevision = 0;
let _tourOpenedRecordedThisSession = false;
function getPreferenceCookie(name) {
  const prefix = `${name}=`;
  return document.cookie.split(';').map(part => part.trim()).find(part => part.startsWith(prefix))
    ?.slice(prefix.length) || '';
}

function setPreferenceCookie(name, value) {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${PREF_COOKIE_MAX_AGE}; SameSite=Lax`;
}

function _primePreferenceValue(name, value) {
  _sessionPreferenceLocalRevision += 1;
  setPreferenceCookie(name, value);
  if (_sessionPreferenceOverrides && Object.prototype.hasOwnProperty.call(_sessionPreferenceOverrides, name)) {
    _sessionPreferenceOverrides[name] = value;
  }
}

function getPreference(name) {
  if (_sessionPreferenceOverrides && Object.prototype.hasOwnProperty.call(_sessionPreferenceOverrides, name)) {
    return _sessionPreferenceOverrides[name];
  }
  const value = getPreferenceCookie(name);
  return value ? decodeURIComponent(value) : '';
}

function _defaultSessionPreferences() {
  const defaultTheme = _preferenceDefaultThemeEntry()?.name
    || _preferenceAppConfig().default_theme
    || 'darklab_obsidian.yaml';
  return PreferenceCore.defaultSessionPreferences(defaultTheme);
}

function _normalizeSessionPreferences(raw) {
  return PreferenceCore.normalizeSessionPreferences(raw, _defaultSessionPreferences(), {
    timestampModes: _timestampModes(),
  });
}

function _sessionPreferenceCacheKey(sessionId = _preferenceSessionId()) {
  return PreferenceCore.sessionPreferenceCacheKey(sessionId);
}

function _readCachedSessionPreferences(sessionId = _preferenceSessionId()) {
  try {
    const raw = localStorage.getItem(_sessionPreferenceCacheKey(sessionId));
    if (!raw) return null;
    return _normalizeSessionPreferences(JSON.parse(raw));
  } catch (_) {
    return null;
  }
}

function _cacheSessionPreferences(prefs, sessionId = _preferenceSessionId()) {
  try {
    localStorage.setItem(_sessionPreferenceCacheKey(sessionId), JSON.stringify(prefs));
  } catch (_) {}
}

function _writePreferenceSnapshotToStorage(prefs, { writeThemeToLocalStorage = true } = {}) {
  _sessionPreferenceKeys.forEach((key) => {
    if (Object.prototype.hasOwnProperty.call(prefs, key)) {
      setPreferenceCookie(key, prefs[key]);
    }
  });
  if (writeThemeToLocalStorage && prefs.pref_theme_name) {
    localStorage.setItem('theme', prefs.pref_theme_name);
  }
}

function _buildCurrentSessionPreferenceSnapshot() {
  const defaultTheme = _preferenceDefaultThemeEntry()?.name
    || _preferenceAppConfig().default_theme
    || 'darklab_obsidian.yaml';
  const currentThemeName = (document.body && document.body.dataset && document.body.dataset.theme)
    || _preferenceSavedThemeName()
    || defaultTheme;
  const rawPrefs = {
    pref_theme_name: currentThemeName,
    pref_timestamps: _preferenceTimestampMode(),
    pref_line_numbers: _preferenceLineNumberMode(),
    pref_welcome_intro: getWelcomeIntroPreference(),
    pref_share_redaction_default: getShareRedactionDefaultPreference(),
    pref_project_auto_link_external_runs: getProjectAutoLinkExternalRunsPreference(),
    pref_project_auto_link_run_entities: getProjectAutoLinkRunEntitiesPreference(),
    pref_run_notify: getRunNotifyPreference(),
    pref_command_outcome_summaries: getCommandOutcomeSummariesPreference(),
    pref_hud_clock: getHudClockPreference(),
    pref_prompt_username: getPromptUsernamePreference(),
    pref_compare_view_mode: getCompareViewModePreference(),
    pref_compare_context: getCompareContextPreference(),
    pref_options_modal_last_tab: getOptionsModalLastTabPreference(),
    pref_tour_seen_version: getTourSeenVersionPreference(),
    pref_constellation_full_day: getConstellationFullDayPreference(),
  };
  const activeProject = typeof importedGetActiveProjectContext === 'function'
    ? importedGetActiveProjectContext()
    : null;
  const activeProjectId = activeProject && activeProject.id ? String(activeProject.id) : getPreference('pref_active_project_id');
  if (/^prj_[0-9a-f]{16}$/.test(activeProjectId)) rawPrefs.pref_active_project_id = activeProjectId;
  return _normalizeSessionPreferences(rawPrefs);
}

function _buildCookieSessionPreferenceSnapshot() {
  const rawPrefs = {};
  _sessionPreferenceKeys.forEach((key) => {
    const value = getPreferenceCookie(key);
    if (value) rawPrefs[key] = decodeURIComponent(value);
  });
  return _normalizeSessionPreferences(rawPrefs);
}

async function _sendSessionPreferenceSnapshot(prefs) {
  const resp = await _preferenceApiFetch('/session/preferences', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ preferences: prefs }),
  });
  if (resp && resp.ok === false) {
    let detail = '';
    try {
      const data = await resp.json();
      detail = data && data.error ? `: ${data.error}` : '';
    } catch (_) {}
    throw new Error(`failed to save session preferences${detail}`);
  }
  return prefs;
}

function _persistCurrentSessionPreferences() {
  const prefs = _buildCurrentSessionPreferenceSnapshot();
  _sessionPreferenceOverrides = prefs;
  _writePreferenceSnapshotToStorage(prefs, { writeThemeToLocalStorage: false });
  _cacheSessionPreferences(prefs);
  const persist = _sessionPreferencePersistQueue
    .catch(() => {})
    .then(() => _sendSessionPreferenceSnapshot(prefs));
  _sessionPreferencePersistQueue = persist.catch(() => {});
  return persist;
}

async function loadSessionPreferences() {
  const loadStartedAtRevision = _sessionPreferenceLocalRevision;
  if (typeof window !== 'undefined') {
  }
  try {
    const sessionId = _preferenceSessionId().trim();
    const defaults = _defaultSessionPreferences();
    const localFallback = sessionId && !sessionId.startsWith('tok_')
      ? _buildCookieSessionPreferenceSnapshot()
      : null;
    let prefs = null;
    try {
      const resp = await _preferenceApiFetch('/session/preferences');
      if (resp && resp.ok === false) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const remote = _normalizeSessionPreferences(data && data.preferences);
      if (data && data.preferences && Object.keys(data.preferences).length) {
        prefs = remote;
      }
    } catch (err) {
      _preferenceLogClientError('failed to load /session/preferences', err);
    }
    if (!prefs) prefs = _readCachedSessionPreferences(sessionId);
    if (!prefs) prefs = localFallback;
    if (!prefs) prefs = defaults;
    if (_sessionPreferenceLocalRevision !== loadStartedAtRevision) {
      prefs = {
        ...prefs,
        ..._buildCurrentSessionPreferenceSnapshot(),
      };
    }
    _sessionPreferenceOverrides = prefs;
    _writePreferenceSnapshotToStorage(prefs);
    _cacheSessionPreferences(prefs, sessionId);
    applyThemePreference(prefs.pref_theme_name, false);
    applyTimestampPreference(prefs.pref_timestamps, false);
    applyLineNumberPreference(prefs.pref_line_numbers, false);
    applyWelcomeIntroPreference(prefs.pref_welcome_intro, false);
    applyShareRedactionDefaultPreference(prefs.pref_share_redaction_default, false);
    applyHudClockPreference(prefs.pref_hud_clock, false);
    applyPromptUsernamePreference(prefs.pref_prompt_username, false);
    applyCompareViewModePreference(prefs.pref_compare_view_mode, false);
    applyCompareContextPreference(prefs.pref_compare_context, false);
    applyCommandOutcomeSummariesPreference(prefs.pref_command_outcome_summaries, false);
    applyConstellationFullDayPreference(prefs.pref_constellation_full_day, false);
    await applyRunNotifyPreference(prefs.pref_run_notify, false);
    syncOptionsControls();
    return prefs;
  } finally {
    if (typeof window !== 'undefined') {
    }
  }
}

function getWelcomeIntroPreference() {
  return PreferenceCore.coerceWelcomeIntroMode(getPreference('pref_welcome_intro'));
}

function getShareRedactionDefaultPreference() {
  return PreferenceCore.coerceShareRedactionDefaultMode(getPreference('pref_share_redaction_default'));
}

function getProjectAutoLinkExternalRunsPreference() {
  return getPreference('pref_project_auto_link_external_runs') === 'off' ? 'off' : 'on';
}

function getProjectAutoLinkRunEntitiesPreference() {
  return getPreference('pref_project_auto_link_run_entities') === 'off' ? 'off' : 'on';
}

function getRunNotifyPreference() {
  return PreferenceCore.coerceRunNotifyMode(getPreference('pref_run_notify'));
}

function getCommandOutcomeSummariesPreference() {
  return PreferenceCore.coerceCommandOutcomeSummariesMode(getPreference('pref_command_outcome_summaries'));
}

function getConstellationFullDayPreference() {
  return PreferenceCore.coerceConstellationFullDayMode(getPreference('pref_constellation_full_day'));
}

function getHudClockPreference() {
  return PreferenceCore.coerceHudClockMode(getPreference('pref_hud_clock'));
}

function getPromptUsernamePreference() {
  return PreferenceCore.normalizePromptUsername(getPreference('pref_prompt_username'));
}

function getCompareViewModePreference() {
  return PreferenceCore.coerceCompareViewMode(getPreference('pref_compare_view_mode'));
}

function getCompareContextPreference() {
  return PreferenceCore.coerceCompareContextMode(getPreference('pref_compare_context'));
}

function getTourSeenVersionPreference() {
  return PreferenceCore.coerceTourSeenVersion(getPreference('pref_tour_seen_version'));
}

function getOptionsModalLastTabPreference() {
  return PreferenceCore.coerceOptionsModalTab(getPreference('pref_options_modal_last_tab'));
}

function _optionsTabButtons() {
  return Array.from(document.querySelectorAll('[data-options-tab]'));
}

function _optionsTabPanels() {
  return Array.from(document.querySelectorAll('[data-options-panel]'));
}

function activateOptionsTab(tab, { persist = true, focus = false } = {}) {
  const nextTab = PreferenceCore.coerceOptionsModalTab(tab);
  _optionsTabButtons().forEach((button) => {
    const active = button.dataset.optionsTab === nextTab;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-selected', active ? 'true' : 'false');
    button.setAttribute('tabindex', active ? '0' : '-1');
  });
  _optionsTabPanels().forEach((panel) => {
    const active = panel.dataset.optionsPanel === nextTab;
    panel.hidden = !active;
  });
  if (focus) {
    const activeButton = document.querySelector(`[data-options-tab="${nextTab}"]`);
    if (activeButton && typeof activeButton.focus === 'function') activeButton.focus();
  }
  _primePreferenceValue('pref_options_modal_last_tab', nextTab);
  if (persist) {
    try { void _persistCurrentSessionPreferences(); } catch (err) { _preferenceLogClientError('failed to persist options tab preference', err); }
  }
  const refreshNotifications = _preferenceGlobalFunction('refreshNotificationChannels');
  if (nextTab === 'notifications' && refreshNotifications) {
    void refreshNotifications();
  }
  const refreshTeams = _preferenceGlobalFunction('refreshOptionsTeams');
  if (nextTab === 'teams' && refreshTeams) {
    void refreshTeams();
  }
  return nextTab;
}

function cycleOptionsTab(offset = 1) {
  const buttons = _optionsTabButtons();
  if (!buttons.length) return false;
  const currentIndex = buttons.findIndex(button => button.getAttribute('aria-selected') === 'true');
  const startIndex = currentIndex >= 0 ? currentIndex : 0;
  const nextIndex = (startIndex + offset + buttons.length) % buttons.length;
  const nextTab = buttons[nextIndex]?.dataset?.optionsTab;
  if (!nextTab) return false;
  activateOptionsTab(nextTab, { persist: true, focus: false });
  return true;
}

function syncOptionsTabFromPreference() {
  activateOptionsTab(getOptionsModalLastTabPreference(), { persist: false });
}

async function recordTourOpened() {
  const resp = await _preferenceApiFetch('/session/tour-seen', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  if (resp && resp.ok === false) {
    let detail = '';
    try {
      const data = await resp.json();
      detail = data && data.error ? `: ${data.error}` : '';
    } catch (_) {}
    throw new Error(`failed to record tour open${detail}`);
  }
  const data = await resp.json();
  const prefs = _normalizeSessionPreferences(data && data.preferences);
  _sessionPreferenceOverrides = prefs;
  _writePreferenceSnapshotToStorage(prefs, { writeThemeToLocalStorage: false });
  _cacheSessionPreferences(prefs);
  return data;
}

async function _recordTourOpenedOnceThisSession() {
  if (_tourOpenedRecordedThisSession) return true;
  try {
    await recordTourOpened();
    _tourOpenedRecordedThisSession = true;
    return true;
  } catch (err) {
    _preferenceLogClientError('failed to record tour open', err);
    return false;
  }
}

function _promptUsernameInputValid(value) {
  const username = String(value || '').trim();
  return !username || PreferenceCore.normalizePromptUsername(username) === username;
}

function syncPromptUsernameValidation() {
  if (!optionsPromptUsernameInput) return true;
  const valid = _promptUsernameInputValid(optionsPromptUsernameInput.value);
  optionsPromptUsernameInput.setAttribute('aria-invalid', valid ? 'false' : 'true');
  if (optionsPromptUsernameError) {
    optionsPromptUsernameError.classList.toggle('u-hidden', valid);
  }
  return valid;
}

async function applyRunNotifyPreference(mode, persist = true) {
  let nextMode = mode === 'on' ? 'on' : 'off';
  if (persist && nextMode === 'on') {
    if (typeof Notification === 'undefined') {
      nextMode = 'off';
    } else if (Notification.permission === 'denied') {
      nextMode = 'off';
      _preferenceShowToast('Notifications are blocked in your browser settings.');
    } else if (Notification.permission !== 'granted') {
      const result = await Notification.requestPermission();
      if (result !== 'granted') nextMode = 'off';
    }
  }
  if (persist) {
    _primePreferenceValue('pref_run_notify', nextMode);
    try { await _persistCurrentSessionPreferences(); } catch (err) { _preferenceLogClientError('failed to persist run notify preference', err); }
  } else {
    _primePreferenceValue('pref_run_notify', nextMode);
  }
  syncOptionsControls();
}

function applyHudClockPreference(mode, persist = true) {
  const nextMode = PreferenceCore.coerceHudClockMode(mode);
  if (persist) {
    _primePreferenceValue('pref_hud_clock', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { _preferenceLogClientError('failed to persist HUD clock preference', err); }
  } else {
    _primePreferenceValue('pref_hud_clock', nextMode);
  }
  syncOptionsControls();
  if (typeof importedRenderHudClock === 'function') importedRenderHudClock();
}

function syncOptionsControls() {
  syncOptionsTabFromPreference();
  const tsSelect = optionsTsSelect;
  if (tsSelect) tsSelect.value = _preferenceTimestampMode();
  const lnToggle = optionsLnToggle;
  if (lnToggle) lnToggle.checked = _preferenceLineNumberMode() === 'on';
  if (optionsWelcomeSelect) optionsWelcomeSelect.value = getWelcomeIntroPreference();
  if (optionsShareRedactionSelect) optionsShareRedactionSelect.value = getShareRedactionDefaultPreference();
  if (optionsNotifyToggle) optionsNotifyToggle.checked = getRunNotifyPreference() === 'on';
  if (optionsCommandOutcomeSummariesToggle) {
    optionsCommandOutcomeSummariesToggle.checked = getCommandOutcomeSummariesPreference() === 'on';
  }
  if (optionsProjectAutoLinkExternalRunsToggle) {
    optionsProjectAutoLinkExternalRunsToggle.checked = getProjectAutoLinkExternalRunsPreference() !== 'off';
  }
  if (optionsProjectAutoLinkRunEntitiesToggle) {
    optionsProjectAutoLinkRunEntitiesToggle.checked = getProjectAutoLinkRunEntitiesPreference() !== 'off';
    optionsProjectAutoLinkRunEntitiesToggle.disabled = getProjectAutoLinkExternalRunsPreference() === 'off';
  }
  if (optionsHudClockSelect) optionsHudClockSelect.value = getHudClockPreference();
  if (optionsCompareViewModeSelect) optionsCompareViewModeSelect.value = getCompareViewModePreference();
  if (optionsCompareContextSelect) optionsCompareContextSelect.value = getCompareContextPreference();
  if (optionsPromptUsernameInput) {
    optionsPromptUsernameInput.value = getPromptUsernamePreference();
    const defaultUsername = String(_preferenceAppConfig().prompt_username || 'anon').trim() || 'anon';
    optionsPromptUsernameInput.placeholder = `Use server default (${defaultUsername})`;
    syncPromptUsernameValidation();
  }
  _preferenceSyncAppSelect(optionsTsSelect);
  _preferenceSyncAppSelect(optionsWelcomeSelect);
  _preferenceSyncAppSelect(optionsShareRedactionSelect);
  _preferenceSyncAppSelect(optionsHudClockSelect);
  _preferenceSyncAppSelect(optionsCompareViewModeSelect);
  _preferenceSyncAppSelect(optionsCompareContextSelect);
}

function applyThemePreference(theme, persist = true) {
  const applyThemeSelection = (typeof importedApplyThemeSelection !== 'undefined' && importedApplyThemeSelection)
    || _preferenceGlobalFunction('applyThemeSelection');
  if (applyThemeSelection) applyThemeSelection(theme, persist);
}

function applyTimestampPreference(mode, persist = true) {
  const nextMode = PreferenceCore.coerceTimestampMode(mode, _timestampModes());
  const setTimestampMode = (typeof importedSetTimestampMode !== 'undefined' && importedSetTimestampMode)
    || _preferenceGlobalFunction('_setTsMode');
  const applied = setTimestampMode ? setTimestampMode(nextMode) : false;
  if (applied === false) {
    _preferenceGlobalFunction('_setTsMode')?.(nextMode);
  }
  if (persist) {
    _primePreferenceValue('pref_timestamps', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { _preferenceLogClientError('failed to persist timestamp preference', err); }
  }
  syncOptionsControls();
}

function applyLineNumberPreference(mode, persist = true) {
  const nextMode = PreferenceCore.coerceLineNumberMode(mode);
  const setLineNumberMode = (typeof importedSetLineNumberMode !== 'undefined' && importedSetLineNumberMode)
    || _preferenceGlobalFunction('_setLnMode');
  if (setLineNumberMode) setLineNumberMode(nextMode);
  if (persist) {
    _primePreferenceValue('pref_line_numbers', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { _preferenceLogClientError('failed to persist line-number preference', err); }
  }
  syncOptionsControls();
}

function applyWelcomeIntroPreference(mode, persist = true) {
  const nextMode = PreferenceCore.coerceWelcomeIntroMode(mode);
  if (persist) {
    _primePreferenceValue('pref_welcome_intro', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { _preferenceLogClientError('failed to persist welcome-intro preference', err); }
  }
  syncOptionsControls();
}

function applyShareRedactionDefaultPreference(mode, persist = true) {
  const nextMode = PreferenceCore.coerceShareRedactionDefaultMode(mode);
  if (persist) {
    _primePreferenceValue('pref_share_redaction_default', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { _preferenceLogClientError('failed to persist share-redaction preference', err); }
  }
  syncOptionsControls();
}

function applyProjectAutoLinkExternalRunsPreference(mode, persist = true) {
  const nextMode = mode === 'off' ? 'off' : 'on';
  if (persist) {
    _primePreferenceValue('pref_project_auto_link_external_runs', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { _preferenceLogClientError('failed to persist project auto-link preference', err); }
  } else {
    _primePreferenceValue('pref_project_auto_link_external_runs', nextMode);
  }
  syncOptionsControls();
}

function applyProjectAutoLinkRunEntitiesPreference(mode, persist = true) {
  const nextMode = mode === 'off' ? 'off' : 'on';
  if (persist) {
    _primePreferenceValue('pref_project_auto_link_run_entities', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { _preferenceLogClientError('failed to persist project entity auto-link preference', err); }
  } else {
    _primePreferenceValue('pref_project_auto_link_run_entities', nextMode);
  }
  syncOptionsControls();
}

function applyCommandOutcomeSummariesPreference(mode, persist = true) {
  const nextMode = PreferenceCore.coerceCommandOutcomeSummariesMode(mode);
  if (persist) {
    _primePreferenceValue('pref_command_outcome_summaries', nextMode);
    try { void _persistCurrentSessionPreferences(); }
    catch (err) { _preferenceLogClientError('failed to persist command outcome summaries preference', err); }
  } else {
    _primePreferenceValue('pref_command_outcome_summaries', nextMode);
  }
  syncOptionsControls();
  const refreshSummaries = (typeof importedRefreshCommandOutcomeSummaries !== 'undefined' && importedRefreshCommandOutcomeSummaries)
    || _preferenceGlobalFunction('refreshCommandOutcomeSummaries');
  if (refreshSummaries) refreshSummaries();
  return nextMode;
}

function applyConstellationFullDayPreference(mode, persist = true) {
  // The Status Monitor Command Constellation auto-fits its X axis to the
  // operator's active hours by default ('off'). Setting this to 'on' falls
  // back to the strict 24-hour layout. The render layer reads the value via
  // `getConstellationFullDayPreference()` on each render, so this helper only
  // primes the cookie/override and persists. Panel-level re-render is owned
  // by the constellation legend toggle handler so the rest of the Status
  // Monitor (active runs, pulse strip, treemap, heatmap) stays untouched.
  const nextMode = PreferenceCore.coerceConstellationFullDayMode(mode);
  _primePreferenceValue('pref_constellation_full_day', nextMode);
  if (persist) {
    try { void _persistCurrentSessionPreferences(); }
    catch (err) { _preferenceLogClientError('failed to persist constellation full-day preference', err); }
  }
  return nextMode;
}

function applyCompareViewModePreference(mode, persist = true) {
  const nextMode = PreferenceCore.coerceCompareViewMode(mode);
  if (persist) {
    _primePreferenceValue('pref_compare_view_mode', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { _preferenceLogClientError('failed to persist compare view preference', err); }
  } else {
    _primePreferenceValue('pref_compare_view_mode', nextMode);
  }
  syncOptionsControls();
}

function applyCompareContextPreference(mode, persist = true) {
  const nextMode = PreferenceCore.coerceCompareContextMode(mode);
  if (persist) {
    _primePreferenceValue('pref_compare_context', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { _preferenceLogClientError('failed to persist compare context preference', err); }
  } else {
    _primePreferenceValue('pref_compare_context', nextMode);
  }
  syncOptionsControls();
}

function applyPromptUsernamePreference(username, persist = true) {
  const rawUsername = String(username || '').trim();
  const nextUsername = PreferenceCore.normalizePromptUsername(rawUsername);
  if (rawUsername && !nextUsername) {
    _preferenceHidePromptUsernameSavedIndicator();
    syncPromptUsernameValidation();
    return false;
  }
  if (persist) {
    _primePreferenceValue('pref_prompt_username', nextUsername);
    try {
      void _persistCurrentSessionPreferences()
        .then(() => _preferenceShowPromptUsernameSavedIndicator())
        .catch((err) => {
          _preferenceHidePromptUsernameSavedIndicator();
          _preferenceLogClientError('failed to persist prompt username preference', err);
        });
    } catch (err) {
      _preferenceHidePromptUsernameSavedIndicator();
      _preferenceLogClientError('failed to persist prompt username preference', err);
    }
  } else {
    _primePreferenceValue('pref_prompt_username', nextUsername);
  }
  syncOptionsControls();
  if (!_preferenceSetComposerPromptMode(_preferenceComposerPromptMode())) _preferenceSyncShellPrompt();
  return true;
}

if (typeof window !== 'undefined') {
}

export {
  getPreferenceCookie,
  setPreferenceCookie,
  getPreference,
  _persistCurrentSessionPreferences,
  loadSessionPreferences,
  getWelcomeIntroPreference,
  getShareRedactionDefaultPreference,
  getProjectAutoLinkExternalRunsPreference,
  getProjectAutoLinkRunEntitiesPreference,
  getRunNotifyPreference,
  getCommandOutcomeSummariesPreference,
  getConstellationFullDayPreference,
  getHudClockPreference,
  getPromptUsernamePreference,
  getCompareViewModePreference,
  getCompareContextPreference,
  getTourSeenVersionPreference,
  getOptionsModalLastTabPreference,
  activateOptionsTab,
  cycleOptionsTab,
  syncOptionsTabFromPreference,
  recordTourOpened,
  _recordTourOpenedOnceThisSession,
  syncPromptUsernameValidation,
  applyRunNotifyPreference,
  applyHudClockPreference,
  syncOptionsControls,
  applyThemePreference,
  applyTimestampPreference,
  applyLineNumberPreference,
  applyWelcomeIntroPreference,
  applyShareRedactionDefaultPreference,
  applyProjectAutoLinkExternalRunsPreference,
  applyProjectAutoLinkRunEntitiesPreference,
  applyCommandOutcomeSummariesPreference,
  applyConstellationFullDayPreference,
  applyCompareViewModePreference,
  applyCompareContextPreference,
  applyPromptUsernamePreference,
};
