// darklab_shell session preference helpers and Options modal preference syncing.

const PreferenceCore = window.DarklabPreferenceCore;
const _welcomeIntroModes = PreferenceCore.WELCOME_INTRO_MODES;
const _shareRedactionDefaultModes = PreferenceCore.SHARE_REDACTION_DEFAULT_MODES;
const _hudClockModes = PreferenceCore.HUD_CLOCK_MODES;

const PREF_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;
const _sessionPreferenceKeys = PreferenceCore.SESSION_PREFERENCE_KEYS;
let _sessionPreferenceOverrides = null;
let _sessionPreferencePersistQueue = Promise.resolve();
if (typeof window !== 'undefined') {
  window.__sessionPreferencesLoadState = 'idle';
}

function getPreferenceCookie(name) {
  const prefix = `${name}=`;
  return document.cookie.split(';').map(part => part.trim()).find(part => part.startsWith(prefix))
    ?.slice(prefix.length) || '';
}

function setPreferenceCookie(name, value) {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${PREF_COOKIE_MAX_AGE}; SameSite=Lax`;
}

function _primePreferenceValue(name, value) {
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
  const defaultTheme = _defaultThemeEntry?.()?.name || APP_CONFIG.default_theme || 'darklab_obsidian.yaml';
  return PreferenceCore.defaultSessionPreferences(defaultTheme);
}

function _normalizeSessionPreferences(raw) {
  return PreferenceCore.normalizeSessionPreferences(raw, _defaultSessionPreferences(), {
    timestampModes: _tsModes,
  });
}

function _sessionPreferenceCacheKey(sessionId = SESSION_ID) {
  return PreferenceCore.sessionPreferenceCacheKey(sessionId);
}

function _readCachedSessionPreferences(sessionId = SESSION_ID) {
  try {
    const raw = localStorage.getItem(_sessionPreferenceCacheKey(sessionId));
    if (!raw) return null;
    return _normalizeSessionPreferences(JSON.parse(raw));
  } catch (_) {
    return null;
  }
}

function _cacheSessionPreferences(prefs, sessionId = SESSION_ID) {
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
  const defaultTheme = _defaultThemeEntry?.()?.name || APP_CONFIG.default_theme || 'darklab_obsidian.yaml';
  const currentThemeName = (document.body && document.body.dataset && document.body.dataset.theme)
    || _savedThemeName()
    || defaultTheme;
  const rawPrefs = {
    pref_theme_name: currentThemeName,
    pref_timestamps: typeof tsMode === 'string' ? tsMode : 'off',
    pref_line_numbers: typeof lnMode === 'string' ? lnMode : 'off',
    pref_welcome_intro: getWelcomeIntroPreference(),
    pref_share_redaction_default: getShareRedactionDefaultPreference(),
    pref_project_auto_link_external_runs: getProjectAutoLinkExternalRunsPreference(),
    pref_project_auto_link_run_entities: getProjectAutoLinkRunEntitiesPreference(),
    pref_run_notify: getRunNotifyPreference(),
    pref_hud_clock: getHudClockPreference(),
    pref_prompt_username: getPromptUsernamePreference(),
    pref_compare_view_mode: getCompareViewModePreference(),
    pref_compare_context: getCompareContextPreference(),
    pref_options_modal_last_tab: getOptionsModalLastTabPreference(),
    pref_tour_seen_version: getTourSeenVersionPreference(),
    pref_constellation_full_day: getConstellationFullDayPreference(),
  };
  const activeProject = typeof globalThis.getActiveProjectContext === 'function'
    ? globalThis.getActiveProjectContext()
    : null;
  const activeProjectId = activeProject && activeProject.id ? String(activeProject.id) : getPreference('pref_active_project_id');
  if (/^prj_[0-9a-f]{16}$/.test(activeProjectId)) rawPrefs.pref_active_project_id = activeProjectId;
  return _normalizeSessionPreferences(rawPrefs);
}

async function _sendSessionPreferenceSnapshot(prefs) {
  const resp = await apiFetch('/session/preferences', {
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
  if (typeof window !== 'undefined') {
    window.__sessionPreferencesLoadState = 'pending';
  }
  try {
    const sessionId = (typeof SESSION_ID === 'string' && SESSION_ID.trim()) ? SESSION_ID.trim() : '';
    const defaults = _defaultSessionPreferences();
    const localFallback = sessionId && !sessionId.startsWith('tok_')
      ? _normalizeSessionPreferences(_buildCurrentSessionPreferenceSnapshot())
      : null;
    let prefs = null;
    try {
      const resp = await apiFetch('/session/preferences');
      if (resp && resp.ok === false) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const remote = _normalizeSessionPreferences(data && data.preferences);
      if (data && data.preferences && Object.keys(data.preferences).length) {
        prefs = remote;
      }
    } catch (err) {
      logClientError('failed to load /session/preferences', err);
    }
    if (!prefs) prefs = _readCachedSessionPreferences(sessionId);
    if (!prefs) prefs = localFallback;
    if (!prefs) prefs = defaults;
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
    applyConstellationFullDayPreference(prefs.pref_constellation_full_day, false);
    if (typeof applyRunNotifyPreference === 'function') {
      await applyRunNotifyPreference(prefs.pref_run_notify, false);
    }
    syncOptionsControls();
    return prefs;
  } finally {
    if (typeof window !== 'undefined') {
      window.__sessionPreferencesLoadState = 'settled';
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
    try { void _persistCurrentSessionPreferences(); } catch (err) { logClientError('failed to persist options tab preference', err); }
  }
  if (nextTab === 'notifications' && typeof refreshNotificationChannels === 'function') {
    void refreshNotificationChannels();
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
  const resp = await apiFetch('/session/tour-seen', {
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
    if (typeof logClientError === 'function') logClientError('failed to record tour open', err);
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
      showToast('Notifications are blocked in your browser settings.');
    } else if (Notification.permission !== 'granted') {
      const result = await Notification.requestPermission();
      if (result !== 'granted') nextMode = 'off';
    }
  }
  if (persist) {
    _primePreferenceValue('pref_run_notify', nextMode);
    try { await _persistCurrentSessionPreferences(); } catch (err) { logClientError('failed to persist run notify preference', err); }
  } else {
    _primePreferenceValue('pref_run_notify', nextMode);
  }
  syncOptionsControls();
}

function applyHudClockPreference(mode, persist = true) {
  const nextMode = PreferenceCore.coerceHudClockMode(mode);
  if (persist) {
    _primePreferenceValue('pref_hud_clock', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { logClientError('failed to persist HUD clock preference', err); }
  } else {
    _primePreferenceValue('pref_hud_clock', nextMode);
  }
  syncOptionsControls();
  if (typeof globalThis.renderHudClock === 'function') globalThis.renderHudClock();
}

function syncOptionsControls() {
  syncOptionsTabFromPreference();
  const tsSelect = optionsTsSelect;
  if (tsSelect) tsSelect.value = typeof tsMode === 'string' ? tsMode : 'off';
  const lnToggle = optionsLnToggle;
  if (lnToggle) lnToggle.checked = typeof lnMode === 'string' && lnMode === 'on';
  if (optionsWelcomeSelect) optionsWelcomeSelect.value = getWelcomeIntroPreference();
  if (optionsShareRedactionSelect) optionsShareRedactionSelect.value = getShareRedactionDefaultPreference();
  if (optionsNotifyToggle) optionsNotifyToggle.checked = getRunNotifyPreference() === 'on';
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
    const defaultUsername = String(APP_CONFIG?.prompt_username || 'anon').trim() || 'anon';
    optionsPromptUsernameInput.placeholder = `Use server default (${defaultUsername})`;
    syncPromptUsernameValidation();
  }
  if (typeof syncAppSelect === 'function') {
    syncAppSelect(optionsTsSelect);
    syncAppSelect(optionsWelcomeSelect);
    syncAppSelect(optionsShareRedactionSelect);
    syncAppSelect(optionsHudClockSelect);
    syncAppSelect(optionsCompareViewModeSelect);
    syncAppSelect(optionsCompareContextSelect);
  }
}

function applyThemePreference(theme, persist = true) {
  applyThemeSelection(theme, persist);
}

function applyTimestampPreference(mode, persist = true) {
  const nextMode = PreferenceCore.coerceTimestampMode(mode, _tsModes);
  _setTsMode(nextMode);
  if (persist) {
    _primePreferenceValue('pref_timestamps', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { logClientError('failed to persist timestamp preference', err); }
  }
  syncOptionsControls();
}

function applyLineNumberPreference(mode, persist = true) {
  const nextMode = PreferenceCore.coerceLineNumberMode(mode);
  _setLnMode(nextMode);
  if (persist) {
    _primePreferenceValue('pref_line_numbers', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { logClientError('failed to persist line-number preference', err); }
  }
  syncOptionsControls();
}

function applyWelcomeIntroPreference(mode, persist = true) {
  const nextMode = PreferenceCore.coerceWelcomeIntroMode(mode);
  if (persist) {
    _primePreferenceValue('pref_welcome_intro', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { logClientError('failed to persist welcome-intro preference', err); }
  }
  syncOptionsControls();
}

function applyShareRedactionDefaultPreference(mode, persist = true) {
  const nextMode = PreferenceCore.coerceShareRedactionDefaultMode(mode);
  if (persist) {
    _primePreferenceValue('pref_share_redaction_default', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { logClientError('failed to persist share-redaction preference', err); }
  }
  syncOptionsControls();
}

function applyProjectAutoLinkExternalRunsPreference(mode, persist = true) {
  const nextMode = mode === 'off' ? 'off' : 'on';
  if (persist) {
    _primePreferenceValue('pref_project_auto_link_external_runs', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { logClientError('failed to persist project auto-link preference', err); }
  } else {
    _primePreferenceValue('pref_project_auto_link_external_runs', nextMode);
  }
  syncOptionsControls();
}

function applyProjectAutoLinkRunEntitiesPreference(mode, persist = true) {
  const nextMode = mode === 'off' ? 'off' : 'on';
  if (persist) {
    _primePreferenceValue('pref_project_auto_link_run_entities', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { logClientError('failed to persist project entity auto-link preference', err); }
  } else {
    _primePreferenceValue('pref_project_auto_link_run_entities', nextMode);
  }
  syncOptionsControls();
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
    catch (err) { logClientError('failed to persist constellation full-day preference', err); }
  }
  return nextMode;
}

function applyCompareViewModePreference(mode, persist = true) {
  const nextMode = PreferenceCore.coerceCompareViewMode(mode);
  if (persist) {
    _primePreferenceValue('pref_compare_view_mode', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { logClientError('failed to persist compare view preference', err); }
  } else {
    _primePreferenceValue('pref_compare_view_mode', nextMode);
  }
  syncOptionsControls();
}

function applyCompareContextPreference(mode, persist = true) {
  const nextMode = PreferenceCore.coerceCompareContextMode(mode);
  if (persist) {
    _primePreferenceValue('pref_compare_context', nextMode);
    try { void _persistCurrentSessionPreferences(); } catch (err) { logClientError('failed to persist compare context preference', err); }
  } else {
    _primePreferenceValue('pref_compare_context', nextMode);
  }
  syncOptionsControls();
}

function applyPromptUsernamePreference(username, persist = true) {
  const rawUsername = String(username || '').trim();
  const nextUsername = PreferenceCore.normalizePromptUsername(rawUsername);
  if (rawUsername && !nextUsername) {
    hidePromptUsernameSavedIndicator();
    syncPromptUsernameValidation();
    return false;
  }
  if (persist) {
    _primePreferenceValue('pref_prompt_username', nextUsername);
    try {
      void _persistCurrentSessionPreferences()
        .then(() => showPromptUsernameSavedIndicator())
        .catch((err) => {
          hidePromptUsernameSavedIndicator();
          logClientError('failed to persist prompt username preference', err);
        });
    } catch (err) {
      hidePromptUsernameSavedIndicator();
      logClientError('failed to persist prompt username preference', err);
    }
  } else {
    _primePreferenceValue('pref_prompt_username', nextUsername);
  }
  syncOptionsControls();
  if (typeof setComposerPromptMode === 'function') setComposerPromptMode(_composerPromptMode);
  else if (typeof syncShellPrompt === 'function') syncShellPrompt();
  return true;
}
